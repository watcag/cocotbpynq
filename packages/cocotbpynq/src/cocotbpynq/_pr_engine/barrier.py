import mmap
import struct
import os
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class CycleBarrier:
    """
    Python interface to shared cycle barrier.

    The barrier enables cycle-accurate simulation by synchronizing all
    Verilator processes (static region + RMs) at each clock cycle.

    Memory layout (matches C++ barrier_sync.h):
    - cycle_count: uint64 at offset 0 (aligned to 64)
    - barrier_count: uint32 at offset 64
    - num_processes: uint32 at offset 128
    - generation: uint32 at offset 192
    - initialized: uint32 at offset 256
    """

    # Cache line alignment used in C++ implementation
    CACHE_LINE_SIZE = 64

    # Offsets for each field (cache-line aligned)
    OFFSET_CYCLE_COUNT = 0
    OFFSET_BARRIER_COUNT = CACHE_LINE_SIZE
    OFFSET_NUM_PROCESSES = CACHE_LINE_SIZE * 2
    OFFSET_SENSE = CACHE_LINE_SIZE * 3
    OFFSET_INITIALIZED = CACHE_LINE_SIZE * 4

    # Total size needed (5 cache lines)
    BARRIER_SIZE = CACHE_LINE_SIZE * 5

    def __init__(
        self,
        uri: str,
        create: bool = False,
        num_processes: int = 0,
        timeout: float = 10.0
    ):
        """
        Initialize barrier interface.

        Parameters
        ----------
        uri : str
            Path to shared memory file
        create : bool
            If True, create and initialize the barrier (leader mode)
            If False, connect to existing barrier (follower mode)
        num_processes : int
            Total number of processes (only used when create=True)
        timeout : float
            Timeout for waiting for barrier to be ready
        """
        self.uri = Path(uri)
        self.fd: Optional[int] = None
        self.mm: Optional[mmap.mmap] = None
        self.is_leader = create
        self._closed = False

        if create:
            # the leader creates the barrier
            self._create_barrier(num_processes)
        else:
            # and follower opens existing barrier
            self._open_barrier(timeout)

    def _create_barrier(self, num_processes: int):
        """Create and initialize barrier as leader."""
        # create parent directory if needed
        self.uri.parent.mkdir(parents=True, exist_ok=True)
        if self.uri.exists():
            self.uri.unlink() # remove existing file if present
        # create+size the file
        self.fd = os.open(str(self.uri), os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        os.ftruncate(self.fd, 4096)  # One page
        # map the file
        self.mm = mmap.mmap(self.fd, 4096)
        # initialize barrier state
        self._write_uint64(self.OFFSET_CYCLE_COUNT, 0)
        self._write_uint32(self.OFFSET_BARRIER_COUNT, 0)
        self._write_uint32(self.OFFSET_NUM_PROCESSES, num_processes)
        self._write_uint32(self.OFFSET_SENSE, 0)
        self._write_uint32(self.OFFSET_INITIALIZED, 1)

        logger.info(f"Created cycle barrier at {self.uri} for {num_processes} processes")

    def _open_barrier(self, timeout: float):
        """Open existing barrier as follower."""
        start_time = time.time()
        # wait for file to exist
        while not self.uri.exists():
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Timeout waiting for barrier file: {self.uri}"
                )
            time.sleep(0.01)
        # open file
        self.fd = os.open(str(self.uri), os.O_RDWR)
        # wait for file to be properly sized
        while True:
            stat = os.fstat(self.fd)
            if stat.st_size >= 4096:
                break
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Timeout waiting for barrier file to be sized: {self.uri}"
                )
            time.sleep(0.01)
        # map the file
        self.mm = mmap.mmap(self.fd, 4096)
        # wait for initialization
        while self._read_uint32(self.OFFSET_INITIALIZED) != 1:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Timeout waiting for barrier initialization: {self.uri}"
                )
            time.sleep(0.01)

        logger.info(f"Connected to cycle barrier at {self.uri}")

    def _read_uint32(self, offset: int) -> int:
        """Read uint32 from shared memory."""
        self.mm.seek(offset)
        data = self.mm.read(4)
        return struct.unpack('<I', data)[0]

    def _write_uint32(self, offset: int, value: int):
        """Write uint32 to shared memory."""
        self.mm.seek(offset)
        self.mm.write(struct.pack('<I', value))

    def _read_uint64(self, offset: int) -> int:
        """Read uint64 from shared memory."""
        self.mm.seek(offset)
        data = self.mm.read(8)
        return struct.unpack('<Q', data)[0]

    def _write_uint64(self, offset: int, value: int):
        """Write uint64 to shared memory."""
        self.mm.seek(offset)
        self.mm.write(struct.pack('<Q', value))

    def get_cycle(self) -> int:
        """
        Get current synchronized cycle count.

        Returns
        -------
        int
            Current global cycle count
        """
        if self._closed:
            raise RuntimeError("Barrier is closed")
        return self._read_uint64(self.OFFSET_CYCLE_COUNT)

    def get_num_processes(self) -> int:
        """
        Get number of processes in barrier.

        Returns
        -------
        int
            Number of processes
        """
        if self._closed:
            raise RuntimeError("Barrier is closed")
        return self._read_uint32(self.OFFSET_NUM_PROCESSES)

    def set_num_processes(self, num_processes: int):
        """
        Update number of processes (leader only).

        This should only be called when all processes are synchronized
        and waiting, typically during reconfiguration.

        Parameters
        ----------
        num_processes : int
            New number of processes
        """
        if self._closed:
            raise RuntimeError("Barrier is closed")
        if not self.is_leader:
            raise RuntimeError("Only leader can update num_processes")
        self._write_uint32(self.OFFSET_NUM_PROCESSES, num_processes)
        logger.debug(f"Updated barrier num_processes to {num_processes}")

    def is_ready(self) -> bool:
        """
        Check if barrier is initialized and ready.

        Returns
        -------
        bool
            True if barrier is ready
        """
        if self._closed or self.mm is None:
            return False
        return self._read_uint32(self.OFFSET_INITIALIZED) == 1

    def close(self):
        """Close barrier and release resources."""
        if self._closed:
            return

        self._closed = True

        if self.mm is not None:
            self.mm.close()
            self.mm = None

        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

        # Leader removes the file
        if self.is_leader and self.uri.exists():
            try:
                self.uri.unlink()
                logger.debug(f"Removed barrier file: {self.uri}")
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        self.close()
