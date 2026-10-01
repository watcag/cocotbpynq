"""
Shared Memory Interface for Python <-> C++ simulation communication.

Provides read/write/reconfig operations via a shared memory mailbox
that the simulation binary monitors.
"""
import mmap
import struct
import os
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Command codes (must match shm_mailbox.h)
CMD_NOOP = 0
CMD_READ = 1
CMD_WRITE = 2
CMD_RECONFIG = 3
CMD_BATCH = 4
CMD_QUIT = 0xFF

# Batch command constants
MAX_BATCH = 32
OFFSET_BATCH_COUNT = 48       # uint32_t at offset 48 in ShmMailbox
OFFSET_BATCH_SLOTS = 56       # batch slot array starts at offset 56
BATCH_SLOT_SIZE = 32           # sizeof(ShmBatchSlot) = 32 bytes
# Offsets within each ShmBatchSlot:
BATCH_SLOT_CMD = 0
BATCH_SLOT_TARGET = 4
BATCH_SLOT_PORT_IDX = 8
# pad at 12
BATCH_SLOT_WRITE_VALUE = 16
BATCH_SLOT_READ_VALUE = 24

# Simulation status (must match shm_mailbox.h)
SIM_STATUS_INIT = 0
SIM_STATUS_RUNNING = 1
SIM_STATUS_DONE = 2
SIM_STATUS_ERROR = 3

# Target codes
TARGET_STATIC = 0
# Partition targets: 1, 2, 3, ... (1-based index)

# ShmMailbox struct layout:
#   uint32_t sim_status     (offset 0, size 4)
#   4 bytes padding         (offset 4)
#   uint64_t cycle_count    (offset 8, size 8)
#   uint32_t cmd            (offset 16, size 4)
#   uint32_t target         (offset 20, size 4)
#   uint32_t port_idx       (offset 24, size 4)
#   uint32_t rm_idx         (offset 28, size 4)
#   uint64_t write_value    (offset 32, size 8)
#   uint64_t read_value     (offset 40, size 8)
# Total: 48 bytes

OFFSET_SIM_STATUS = 0
OFFSET_CYCLE_COUNT = 8
OFFSET_CMD = 16
OFFSET_TARGET = 20
OFFSET_PORT_IDX = 24
OFFSET_RM_IDX = 28
OFFSET_WRITE_VALUE = 32
OFFSET_READ_VALUE = 40

MAILBOX_SIZE = 4096  # One page


class SharedMemoryInterface:
    """
    Python interface for communicating with the simulation binary
    via a shared memory mailbox.

    Protocol:
    1. Python writes target, port_idx, write_value fields
    2. Python writes cmd field LAST (this signals to C++)
    3. C++ processes command, writes read_value if needed
    4. C++ sets cmd = CMD_NOOP to signal completion
    5. Python polls cmd until NOOP, then reads read_value
    """

    def __init__(
        self,
        shm_path: str,
        target: int = TARGET_STATIC,
        create: bool = False,
        timeout: float = 30.0,
    ):
        """
        Initialize shared memory interface.

        Parameters
        ----------
        shm_path : str
            Path to the shared memory file.
        target : int
            Target ID for commands (0=static, 1+=partition index 1-based).
        create : bool
            If True, create the shared memory file (called by SimulationProcessManager).
            If False, connect to existing file (normal usage).
        timeout : float
            Timeout for waiting for simulation to be ready.
        """
        self.shm_path = Path(shm_path)
        self.target = target
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._mm: Optional[mmap.mmap] = None
        self._closed = False
        self._is_creator = create

        if create:
            self._create_shm()
        else:
            self._open_shm()

    def _create_shm(self):
        """Create the shared memory file."""
        self.shm_path.parent.mkdir(parents=True, exist_ok=True)
        if self.shm_path.exists():
            self.shm_path.unlink()

        self._fd = os.open(str(self.shm_path), os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        os.ftruncate(self._fd, MAILBOX_SIZE)
        self._mm = mmap.mmap(self._fd, MAILBOX_SIZE)

        # Initialize to zeros
        self._mm.seek(0)
        self._mm.write(b'\x00' * MAILBOX_SIZE)

        logger.info(f"Created shared memory mailbox: {self.shm_path}")

    def _open_shm(self):
        """Open existing shared memory file and wait for sim to be ready."""
        start = time.time()

        # Wait for file to exist
        while not self.shm_path.exists():
            if time.time() - start > self.timeout:
                raise TimeoutError(
                    f"Timeout waiting for shared memory file: {self.shm_path}"
                )
            time.sleep(0.01)

        self._fd = os.open(str(self.shm_path), os.O_RDWR)

        # Wait for file to be properly sized
        while True:
            stat = os.fstat(self._fd)
            if stat.st_size >= MAILBOX_SIZE:
                break
            if time.time() - start > self.timeout:
                raise TimeoutError(
                    f"Timeout waiting for shared memory file to be sized: {self.shm_path}"
                )
            time.sleep(0.01)

        self._mm = mmap.mmap(self._fd, MAILBOX_SIZE)

        # Wait for simulation to be running
        while self._read_u32(OFFSET_SIM_STATUS) != SIM_STATUS_RUNNING:
            status = self._read_u32(OFFSET_SIM_STATUS)
            if status == SIM_STATUS_ERROR:
                raise RuntimeError("Simulation reported error status")
            if status == SIM_STATUS_DONE:
                raise RuntimeError("Simulation already done")
            if time.time() - start > self.timeout:
                raise TimeoutError(
                    f"Timeout waiting for simulation to start (status={status})"
                )
            time.sleep(0.01)

        logger.info(f"Connected to simulation via shared memory: {self.shm_path}")

    def _read_u32(self, offset: int) -> int:
        self._mm.seek(offset)
        return struct.unpack('<I', self._mm.read(4))[0]

    def _write_u32(self, offset: int, value: int):
        self._mm.seek(offset)
        self._mm.write(struct.pack('<I', value))

    def _read_u64(self, offset: int) -> int:
        self._mm.seek(offset)
        return struct.unpack('<Q', self._mm.read(8))[0]

    def _write_u64(self, offset: int, value: int):
        self._mm.seek(offset)
        self._mm.write(struct.pack('<Q', value))

    def _send_command(self, cmd: int, port_idx: int = 0,
                      rm_idx: int = 0, write_value: int = 0,
                      poll_timeout: float = 10.0) -> int:
        """
        Send a command to the simulation binary and wait for response.

        Returns the read_value from the response.
        """
        if self._closed:
            raise RuntimeError("SharedMemoryInterface is closed")

        # Write fields first (order matters - cmd must be LAST)
        self._write_u32(OFFSET_TARGET, self.target)
        self._write_u32(OFFSET_PORT_IDX, port_idx)
        self._write_u32(OFFSET_RM_IDX, rm_idx)
        self._write_u64(OFFSET_WRITE_VALUE, write_value)

        # Write cmd LAST to signal to C++
        self._write_u32(OFFSET_CMD, cmd)

        # Poll until cmd becomes NOOP (C++ has processed it)
        start = time.time()
        while self._read_u32(OFFSET_CMD) != CMD_NOOP:
            if time.time() - start > poll_timeout:
                raise TimeoutError(
                    f"Timeout waiting for command response (cmd={cmd})"
                )
            # Tight polling - simulation processes commands each cycle
            time.sleep(0.0001)

        return self._read_u64(OFFSET_READ_VALUE)

    def read_port(self, port_idx: int) -> int:
        """
        Read a port value from the simulation.

        Parameters
        ----------
        port_idx : int
            Port index in the signal access table.

        Returns
        -------
        int
            The read value.
        """
        return self._send_command(CMD_READ, port_idx=port_idx)

    def write_port(self, port_idx: int, value: int):
        """
        Write a value to a simulation port.

        Parameters
        ----------
        port_idx : int
            Port index in the signal access table.
        value : int
            Value to write.
        """
        self._send_command(CMD_WRITE, port_idx=port_idx, write_value=int(value) & 0xFFFFFFFFFFFFFFFF)

    def reconfigure(self, rm_idx: int, poll_timeout: float = 30.0):
        """
        Request reconfiguration of the target partition.

        Parameters
        ----------
        rm_idx : int
            Index of the RM to switch to.
        poll_timeout : float
            Timeout waiting for reconfiguration to complete.
        """
        self._send_command(CMD_RECONFIG, rm_idx=rm_idx, poll_timeout=poll_timeout)
        logger.info(f"Reconfiguration complete: target={self.target}, rm_idx={rm_idx}")

    def _write_batch_slot(self, slot_idx: int, cmd: int, target: int,
                          port_idx: int, write_value: int = 0):
        """Write a single batch slot."""
        base = OFFSET_BATCH_SLOTS + slot_idx * BATCH_SLOT_SIZE
        self._write_u32(base + BATCH_SLOT_CMD, cmd)
        self._write_u32(base + BATCH_SLOT_TARGET, target)
        self._write_u32(base + BATCH_SLOT_PORT_IDX, port_idx)
        self._write_u64(base + BATCH_SLOT_WRITE_VALUE, write_value)

    def _read_batch_slot_result(self, slot_idx: int) -> int:
        """Read the read_value result from a batch slot."""
        base = OFFSET_BATCH_SLOTS + slot_idx * BATCH_SLOT_SIZE
        return self._read_u64(base + BATCH_SLOT_READ_VALUE)

    def batch_read_write(self, ops: list, poll_timeout: float = 10.0) -> list:
        """
        Send up to MAX_BATCH read/write commands in a single cycle.

        Parameters
        ----------
        ops : list of (cmd, port_idx, write_value) tuples
            cmd: CMD_READ or CMD_WRITE
        poll_timeout : float
            Timeout for waiting for batch response.

        Returns
        -------
        list of int
            Results for each op (read_value for CMD_READ, 0 for CMD_WRITE).
        """
        if self._closed:
            raise RuntimeError("SharedMemoryInterface is closed")
        if len(ops) > MAX_BATCH:
            raise ValueError(f"Too many batch ops: {len(ops)} > {MAX_BATCH}")

        for i, (cmd, port_idx, write_value) in enumerate(ops):
            self._write_batch_slot(i, cmd, self.target, port_idx,
                                   int(write_value) & 0xFFFFFFFFFFFFFFFF)

        self._write_u32(OFFSET_BATCH_COUNT, len(ops))
        self._write_u32(OFFSET_CMD, CMD_BATCH)  # trigger — written LAST

        start = time.time()
        while self._read_u32(OFFSET_CMD) != CMD_NOOP:
            if time.time() - start > poll_timeout:
                raise TimeoutError("Timeout waiting for batch command response")
            time.sleep(0.0001)

        return [
            self._read_batch_slot_result(i) if cmd == CMD_READ else 0
            for i, (cmd, _, _) in enumerate(ops)
        ]

    def quit(self):
        """Send quit command to simulation."""
        if self._closed:
            return
        try:
            self._send_command(CMD_QUIT, poll_timeout=5.0)
        except (TimeoutError, RuntimeError):
            pass  # Sim may exit before responding

    @property
    def cycle_count(self) -> int:
        """Get current simulation cycle count."""
        if self._closed:
            return 0
        return self._read_u64(OFFSET_CYCLE_COUNT)

    @property
    def sim_status(self) -> int:
        """Get simulation status."""
        if self._closed:
            return SIM_STATUS_DONE
        return self._read_u32(OFFSET_SIM_STATUS)

    @property
    def is_running(self) -> bool:
        """Check if simulation is running."""
        return self.sim_status == SIM_STATUS_RUNNING

    def close(self):
        """Close shared memory interface."""
        if self._closed:
            return
        self._closed = True

        if self._mm is not None:
            self._mm.close()
            self._mm = None

        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

        if self._is_creator and self.shm_path.exists():
            try:
                self.shm_path.unlink()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()
