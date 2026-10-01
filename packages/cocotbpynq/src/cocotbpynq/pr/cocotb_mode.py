"""
Cocotb integration mode for partial reconfiguration.

Provides:
- CtrlMailbox: SHM-backed control channel for cross-process reconfiguration.
- pr_reconfigure: async reconfiguration used internally by Overlay.reconfigure().

Cross-process reconfiguration
------------------------------
cocotb tests run embedded inside a Verilator subprocess.  The live PRSystem
lives in the parent process (cocotb_runner.py).  Communication uses a tiny
SHM region (ctrl_mailbox.shm) inside the existing PR_SHM_DIR directory.

SHM layout (512 bytes):
  offset  0: uint32 magic     0xC0C0BA55
  offset  4: uint32 seq_req   test writes sequence number when submitting
  offset  8: uint32 seq_resp  control thread echoes seq_req when done
  offset 12: uint32 status    0=idle 1=pending 2=ok 3=error
  offset 16: char[64]  partition name (null-terminated)
  offset 80: char[64]  rm name (null-terminated)
  offset 144: char[256] error message (null-terminated)

Protocol:
  1. Test writes partition/rm/seq_req, then sets status=PENDING (release).
  2. Control thread polls status; on PENDING reads partition+rm, calls
     pr_system.reconfigure(), writes seq_resp, sets status=OK/ERROR.
  3. Test polls status+seq_resp; on completion resets to IDLE.
"""
import mmap
import os
import struct
import time


# -- CtrlMailbox ---------------------------------------------------------------

class CtrlMailbox:
    """Shared-memory control mailbox for cross-process reconfiguration."""

    SIZE = 512
    MAGIC = 0xC0C0BA55

    STATUS_IDLE    = 0
    STATUS_PENDING = 1
    STATUS_OK      = 2
    STATUS_ERROR   = 3

    OFF_MAGIC     = 0
    OFF_SEQ_REQ   = 4
    OFF_SEQ_RESP  = 8
    OFF_STATUS    = 12
    OFF_PARTITION = 16
    OFF_RM_NAME   = 80
    OFF_ERROR_MSG = 144

    def __init__(self, path: str, create: bool = False):
        self.path = path
        if create:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            os.ftruncate(fd, self.SIZE)
            self._mm = mmap.mmap(fd, self.SIZE)
            os.close(fd)
            self._mm.seek(0)
            self._mm.write(b'\x00' * self.SIZE)
            struct.pack_into('<I', self._mm, self.OFF_MAGIC, self.MAGIC)
            struct.pack_into('<I', self._mm, self.OFF_STATUS, self.STATUS_IDLE)
            self._mm.flush()
        else:
            fd = os.open(path, os.O_RDWR)
            self._mm = mmap.mmap(fd, self.SIZE)
            os.close(fd)

    def _read_u32(self, offset: int) -> int:
        return struct.unpack_from('<I', self._mm, offset)[0]

    def _write_u32(self, offset: int, value: int):
        struct.pack_into('<I', self._mm, offset, value)

    def _read_str(self, offset: int, max_len: int) -> str:
        raw = bytes(self._mm[offset:offset + max_len])
        return raw.split(b'\x00')[0].decode('utf-8', errors='replace')

    def _write_str(self, offset: int, max_len: int, value: str):
        encoded = value.encode('utf-8')[:max_len - 1]
        self._mm[offset:offset + max_len] = encoded + b'\x00' * (max_len - len(encoded))

    @property
    def status(self) -> int:
        return self._read_u32(self.OFF_STATUS)

    @property
    def seq_req(self) -> int:
        return self._read_u32(self.OFF_SEQ_REQ)

    @property
    def seq_resp(self) -> int:
        return self._read_u32(self.OFF_SEQ_RESP)

    @property
    def partition(self) -> str:
        return self._read_str(self.OFF_PARTITION, 64)

    @property
    def rm_name(self) -> str:
        return self._read_str(self.OFF_RM_NAME, 64)

    @property
    def error_msg(self) -> str:
        return self._read_str(self.OFF_ERROR_MSG, 256)

    def submit(self, partition: str, rm: str, seq: int):
        """Called by cocotb test: write request then set PENDING."""
        self._write_str(self.OFF_PARTITION, 64, partition)
        self._write_str(self.OFF_RM_NAME, 64, rm)
        self._write_u32(self.OFF_SEQ_REQ, seq)
        self._mm.flush()
        self._write_u32(self.OFF_STATUS, self.STATUS_PENDING)
        self._mm.flush()

    def complete_ok(self, seq: int):
        """Called by control thread on success."""
        self._write_u32(self.OFF_SEQ_RESP, seq)
        self._mm.flush()
        self._write_u32(self.OFF_STATUS, self.STATUS_OK)
        self._mm.flush()

    def complete_error(self, seq: int, msg: str):
        """Called by control thread on failure."""
        self._write_str(self.OFF_ERROR_MSG, 256, msg)
        self._write_u32(self.OFF_SEQ_RESP, seq)
        self._mm.flush()
        self._write_u32(self.OFF_STATUS, self.STATUS_ERROR)
        self._mm.flush()

    def reset(self):
        """Reset to IDLE after the test has consumed the response."""
        self._write_u32(self.OFF_STATUS, self.STATUS_IDLE)
        self._mm.flush()

    def close(self):
        self._mm.close()


# -- internal helpers ----------------------------------------------------------

def _get_ctrl_mailbox() -> CtrlMailbox:
    path = os.environ.get('PR_CTRL_SHM')
    if not path:
        raise RuntimeError(
            "PR_CTRL_SHM not set. Use PRCocotbRunner to run tests."
        )
    return CtrlMailbox(path, create=False)


async def pr_reconfigure(partition: str, rm: str, timeout_ns: float = 5_000_000, poll_ns: int = 100):
    """
    Async reconfiguration for use inside plain cocotb @test coroutines.

    Polls using cocotb Timer ticks so the simulation clock keeps advancing
    (required for the barrier spin to complete) while we wait.
    """
    from cocotb.triggers import Timer
    from cocotbpynq._pr_engine import trace

    mb = _get_ctrl_mailbox()
    seq = int(time.time() * 1000) & 0xFFFFFF

    with trace.span('pr_reconfigure', partition=partition, rm=rm, seq=seq):
        mb.submit(partition, rm, seq)
        trace.event('pr_reconfigure.submit', partition=partition, rm=rm, seq=seq)

        elapsed = 0.0
        poll_iter = 0
        while elapsed < timeout_ns:
            await Timer(poll_ns, unit='ns')
            elapsed += poll_ns
            poll_iter += 1
            # Rate-limit poll-iteration events: emit every 1000 iters so we
            # know it's still alive without flooding the JSONL.
            if poll_iter % 1000 == 0:
                trace.event('pr_reconfigure.poll', seq=seq,
                            iter=poll_iter, sim_ns=elapsed)
            status = mb.status
            if status == CtrlMailbox.STATUS_OK and mb.seq_resp == seq:
                mb.reset()
                trace.event('pr_reconfigure.complete', seq=seq,
                            iter=poll_iter, sim_ns=elapsed)
                return
            if status == CtrlMailbox.STATUS_ERROR and mb.seq_resp == seq:
                msg = mb.error_msg
                mb.reset()
                trace.event('pr_reconfigure.error', seq=seq, msg=msg)
                raise RuntimeError(f"Reconfigure {partition} -> {rm} failed: {msg}")

        trace.event('pr_reconfigure.timeout', seq=seq,
                    iter=poll_iter, sim_ns=elapsed)
        raise TimeoutError(
            f"Reconfigure {partition} -> {rm} timed out after {timeout_ns/1e6:.1f} ms sim-time"
        )
