"""The PYNQ release cocotbpynq simulates (cocotbpynq.pynq_api) and the PYNQ 3 / 4 buffer semantics.

Pure Python: no simulator is started.
"""
import importlib
import os
import warnings

import numpy as np
import pytest

from cocotbpynq import buffer, pynq_api, xrt


@pytest.fixture
def pynq(monkeypatch, request):
    """Reload pynq_api as PYNQ <param> (default 4.0.0) with the given device tree."""
    def select(version="4.0.0", tree=None):
        monkeypatch.setenv("COCOTBPYNQ_PYNQ_VERSION", version)
        if tree is None:
            monkeypatch.delenv("COCOTBPYNQ_DEVICE_TREE", raising=False)
        else:
            monkeypatch.setenv("COCOTBPYNQ_DEVICE_TREE", str(tree))
        return importlib.reload(pynq_api)
    yield select
    monkeypatch.delenv("COCOTBPYNQ_PYNQ_VERSION", raising=False)
    monkeypatch.delenv("COCOTBPYNQ_DEVICE_TREE", raising=False)
    importlib.reload(pynq_api)


def board_tree(tmp_path, pynq_board=True):
    chosen = tmp_path / "device-tree" / "chosen"
    chosen.mkdir(parents=True)
    if pynq_board:
        (chosen / "pynq_board").write_bytes(b"KV260\0")
    return chosen.parent


def test_default_is_pynq4_on_a_configured_board(pynq):
    api = pynq()
    assert api.VERSION == "4.0.0" and api.PYNQ4 and api.on_target()


def test_unknown_version_is_refused(monkeypatch):
    monkeypatch.setenv("COCOTBPYNQ_PYNQ_VERSION", "3.1")
    with pytest.raises(ImportError, match="3.0.1 or 4.0.0"):
        importlib.reload(pynq_api)
    monkeypatch.delenv("COCOTBPYNQ_PYNQ_VERSION")
    importlib.reload(pynq_api)


def test_a_board_without_pynq_board_fails_like_pynq4(pynq, tmp_path):
    pynq(tree=board_tree(tmp_path, pynq_board=False))
    for call in (lambda: buffer.allocate((4,)), lambda: pynq_api.require_device("Overlay")):
        with pytest.raises(NameError, match="name 'pyxrt' is not defined.*chosen/pynq_board"):
            call()


def test_a_board_with_pynq_board_is_on_target(pynq, tmp_path):
    api = pynq(tree=board_tree(tmp_path))
    assert api.on_target()
    assert buffer.allocate((4,)).shape == (4,)


def test_pynq3_has_no_target_gate(pynq, tmp_path):
    api = pynq("3.0.1", tree=board_tree(tmp_path, pynq_board=False))
    assert api.on_target()
    buffer.allocate((4,))


def test_loads_write_loaded_xclbin_into_the_cwd_on_pynq4(pynq, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api = pynq()
    path = api.xrt_download()
    assert path == str(tmp_path / "loaded.xclbin")
    assert (tmp_path / "loaded.xclbin").read_bytes().startswith(b"xclbin2\0")
    os.remove(path)
    assert pynq("3.0.1").xrt_download() is None and os.listdir(tmp_path) == []


def test_load_from_a_read_only_cwd_fails_like_pynq4(pynq, tmp_path, monkeypatch):
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    sealed.chmod(0o555)
    monkeypatch.chdir(sealed)
    try:
        if os.access(sealed, os.W_OK):
            pytest.skip("running as a user that can write a read-only directory")
        with pytest.raises(PermissionError):
            pynq().xrt_download()
    finally:
        sealed.chmod(0o755)


def cacheable(pynq_version, pynq, n=8):
    pynq(pynq_version)
    buf = buffer.allocate((n,), np.uint64)
    buf[:] = np.arange(n, dtype=np.uint64)
    buf.flush()
    return buf


@pytest.mark.parametrize("version", ["3.0.1", "4.0.0"])
def test_a_slice_keeps_the_allocation_address(version, pynq):
    buf = cacheable(version, pynq)
    view = buf[2:6]
    assert view.physical_address == buf.physical_address + 16 == view.device_address
    assert view.cacheable and buf[::2].physical_address == buf.physical_address
    assert (buf + 1).physical_address == 0          # a computed array is not device memory


@pytest.mark.parametrize("version,after", [("3.0.1", [0, 1, 92, 93, 4, 5, 6, 7]),
                                           ("4.0.0", [90, 91, 92, 93, 94, 95, 96, 97])])
def test_flushing_a_slice(version, after, pynq):
    buf = cacheable(version, pynq)
    buf[:] += np.uint64(90)                          # CPU writes, not yet flushed
    buf[2:4].flush()                                 # PYNQ 3: these 16 bytes; PYNQ 4: the whole bo
    assert list(buf._dram) == after


@pytest.mark.parametrize("version,after", [("3.0.1", [90, 91, 2, 3, 94, 95, 96, 97]),
                                           ("4.0.0", [0, 1, 2, 3, 4, 5, 6, 7])])
def test_invalidating_a_slice(version, after, pynq):
    buf = cacheable(version, pynq)
    buf[:] += np.uint64(90)                          # unflushed CPU writes everywhere
    buf[2:4].invalidate()                            # PYNQ 4 drops all of them
    assert list(buf) == after


def test_pynq4_buffers_take_at_least_8_kib(pynq):
    pynq()
    a, b = buffer.allocate((1,), np.uint8), buffer.allocate((1,), np.uint8)
    assert b.physical_address - a.physical_address == 8192
    pynq("3.0.1")
    a, b = buffer.allocate((1,), np.uint8), buffer.allocate((1,), np.uint8)
    assert b.physical_address - a.physical_address == 4096


def test_dma_memory_is_dram_at_the_slice(pynq):
    buf = cacheable("4.0.0", pynq)
    mem = buf[2:6]._dma_memory(8, 16)
    mem[:] = 0xFF
    assert list(buf._dram) == [0, 1, 2, 2**64 - 1, 2**64 - 1, 5, 6, 7]


def test_freed_buffers_and_slices_cannot_be_used(pynq):
    buf = cacheable("4.0.0", pynq)
    view = buf[1:3]
    buf.freebuffer()
    for use in (buf.flush, buf.invalidate, view.flush, lambda: view._dma_memory(0, 8)):
        with pytest.raises(RuntimeError, match="after freebuffer"):
            use()


def test_scope_exit_frees_and_close_only_warns(pynq):
    pynq()
    with buffer.allocate((4,)) as buf:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            buf.close()
        assert caught and caught[0].category is DeprecationWarning
        buf.flush()
    with pytest.raises(RuntimeError):
        buf.flush()


def test_non_cacheable_buffers_are_one_array(pynq):
    pynq()
    buf = buffer.allocate((4,), np.uint32, cacheable=False)
    buf[1:3].invalidate()
    buf[:] = 5
    assert buf._dma_memory(0, 16).view(np.uint32).tolist() == [5] * 4


def test_xrt_buffers_sync_their_bytes_and_refuse_use_after_free():
    class Banks:
        def __init__(self):
            self.mem = bytearray(64)

        def alloc(self, desc, nbytes):
            return 0

        def write(self, address, data):
            self.mem[address:address + len(data)] = data

        def read(self, address, nbytes):
            return bytes(self.mem[address:address + nbytes])

    memory = xrt.Memory(Banks(), {"idx": 0, "size": 64, "base_address": 0})
    buf = memory.allocate((8,), np.uint64)
    buf[:] = np.arange(8, dtype=np.uint64)
    buf[2:4].sync_to_device()
    assert np.frombuffer(memory.banks.mem, np.uint64).tolist() == [0, 0, 2, 3, 0, 0, 0, 0]
    view = buf[4:]
    buf.freebuffer()
    for use in (buf.sync_to_device, view.sync_from_device):
        with pytest.raises(RuntimeError, match="after freebuffer"):
            use()
