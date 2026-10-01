"""
Simulation Process Manager for multi-binary architecture.

Manages N+1 processes:
- 1 static binary (persistent for the simulation lifetime)
- N RM binaries (one per partition, can be killed/restarted on reconfiguration)

Creates shared memory files:
- cmd_mailbox.shm: Python <-> static binary command mailbox
- barrier.shm: Cross-process cycle barrier
- partition_N.shm: Per-partition DPI channel (one per partition)
"""
import mmap
import struct
import subprocess
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .shm_interface import (
    SharedMemoryInterface, SIM_STATUS_RUNNING, MAILBOX_SIZE,
    OFFSET_CMD, OFFSET_TARGET, OFFSET_PORT_IDX, OFFSET_RM_IDX,
    CMD_NOOP, CMD_RECONFIG,
)
from .barrier import CycleBarrier

logger = logging.getLogger(__name__)

# Constants matching dpi_shm_channel.h
SHM_MAGIC = 0x50525348
SHM_VERSION = 1


def _compute_partition_shm_size(num_to_rm: int, num_from_rm: int) -> int:
    """Compute the page-aligned shared memory size for a partition channel.

    Parameters are slot counts (not port counts). A port of width W
    occupies ceil(W/64) slots.
    """
    raw = 64 + num_to_rm * 192 + num_from_rm * 128
    return (raw + 4095) & ~4095


class SimulationProcessManager:
    """
    Manages the multi-process DPI-based simulation.

    Lifecycle:
    1. start() - creates shared memory, starts static + initial RM binaries
    2. reconfigure() - kills old RM, starts new RM for a partition
    3. terminate() - sends quit, cleans up all processes and shared memory
    """

    def __init__(self, build_dir: str):
        self.build_dir = Path(build_dir)
        self.shm_dir = self.build_dir / 'shm'

        self._static_process: Optional[subprocess.Popen] = None
        self._rm_processes: Dict[str, subprocess.Popen] = {}  # partition_name -> Popen
        self._rm_names: Dict[str, str] = {}  # partition_name -> current rm_name

        self._shm: Optional[SharedMemoryInterface] = None
        self._barrier: Optional[CycleBarrier] = None
        self._partition_fds: Dict[str, int] = {}  # partition_name -> fd
        self._partition_mms: Dict[str, mmap.mmap] = {}  # partition_name -> mmap
        self._partition_sizes: Dict[str, int] = {}  # partition_name -> size
        self._partition_infos: Dict[str, Dict[str, Any]] = {}  # name -> {num_to_rm, num_from_rm, index}

        self._running = False

    def start(
        self,
        static_binary: str,
        rm_binaries: Dict[str, str],
        partition_configs: List[Dict[str, Any]],
        initial_rm_map: Dict[str, str],
        timeout: float = 30.0,
    ) -> SharedMemoryInterface:
        """
        Start the simulation: create shared memory, launch all processes.

        Parameters
        ----------
        static_binary : str
            Path to the static binary.
        rm_binaries : dict
            Map of rm_name -> binary_path for all RM variants.
        partition_configs : list of dict
            Per-partition config: [{name, index, num_to_rm, num_from_rm}, ...].
        initial_rm_map : dict
            Map of partition_name -> initial_rm_name to load.
        timeout : float
            Timeout for startup.

        Returns
        -------
        SharedMemoryInterface
            Shared memory interface for Python commands.
        """
        if self._running:
            raise RuntimeError("Simulation is already running")

        if not Path(static_binary).exists():
            raise FileNotFoundError(f"Static binary not found: {static_binary}")

        num_partitions = len(partition_configs)
        # Total processes: 1 static + N RM binaries
        num_processes = 1 + num_partitions

        # Store partition info
        for pc in partition_configs:
            self._partition_infos[pc['name']] = pc

        # Create shm directory
        self.shm_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create command mailbox
        mailbox_path = self.shm_dir / 'cmd_mailbox.shm'
        self._shm = SharedMemoryInterface(
            shm_path=str(mailbox_path),
            create=True,
        )

        # 2. Create barrier
        barrier_path = self.shm_dir / 'barrier.shm'
        self._barrier = CycleBarrier(
            uri=str(barrier_path),
            create=True,
            num_processes=num_processes,
        )

        # 3. Create partition channels
        for pc in partition_configs:
            self._create_partition_channel(
                pc['name'], pc['index'],
                pc['num_to_rm'], pc['num_from_rm']
            )

        # 4. Start static binary
        cmd = [
            static_binary,
            '--shm-dir', str(self.shm_dir),
        ]
        logger.info(f"Starting static binary: {' '.join(cmd)}")
        self._static_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # 5. Start initial RM binaries
        for part_name, rm_name in initial_rm_map.items():
            rm_binary = rm_binaries[rm_name]
            pc = self._partition_infos[part_name]
            self._start_rm_process(
                part_name, rm_name, rm_binary, pc['index']
            )

        # 6. Wait for simulation to be ready
        start_time = time.time()
        while True:
            if self._static_process.poll() is not None:
                stdout = self._static_process.stdout.read().decode() if self._static_process.stdout else ''
                stderr = self._static_process.stderr.read().decode() if self._static_process.stderr else ''
                raise RuntimeError(
                    f"Static binary exited with code {self._static_process.returncode}\n"
                    f"stdout: {stdout}\nstderr: {stderr}"
                )

            status = self._shm.sim_status
            if status == SIM_STATUS_RUNNING:
                break

            if time.time() - start_time > timeout:
                self._force_kill_all()
                raise TimeoutError(
                    f"Timeout waiting for simulation to start (status={status})"
                )
            time.sleep(0.01)

        self._running = True
        logger.info(
            f"Simulation started: 1 static (PID {self._static_process.pid}) "
            f"+ {len(self._rm_processes)} RM processes"
        )
        return self._shm

    def _create_partition_channel(
        self, name: str, index: int,
        num_to_rm: int, num_from_rm: int,
    ):
        """Create and initialize a partition shared memory channel."""
        path = self.shm_dir / f'partition_{index}.shm'
        if path.exists():
            path.unlink()

        size = _compute_partition_shm_size(num_to_rm, num_from_rm)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        os.ftruncate(fd, size)
        mm = mmap.mmap(fd, size)

        # Zero-fill
        mm.seek(0)
        mm.write(b'\x00' * size)

        # Write header
        mm.seek(0)
        mm.write(struct.pack('<IIIIIII',
            SHM_MAGIC,      # magic
            SHM_VERSION,     # version
            num_to_rm,       # num_to_rm
            num_from_rm,     # num_from_rm
            1,               # initialized
            0,               # quit
            0,               # rm_ready
        ))

        self._partition_fds[name] = fd
        self._partition_mms[name] = mm
        self._partition_sizes[name] = size

        logger.info(
            f"Created partition channel: {path} "
            f"(T={num_to_rm}, F={num_from_rm}, size={size})"
        )

    def _start_rm_process(
        self, partition_name: str, rm_name: str,
        rm_binary: str, partition_index: int,
    ):
        """Start a single RM binary process."""
        if not Path(rm_binary).exists():
            raise FileNotFoundError(f"RM binary not found: {rm_binary}")

        cmd = [
            rm_binary,
            '--shm-dir', str(self.shm_dir),
            '--partition-index', str(partition_index),
        ]
        logger.info(f"Starting RM '{rm_name}': {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self._rm_processes[partition_name] = proc
        self._rm_names[partition_name] = rm_name

    def reconfigure(
        self,
        partition_name: str,
        new_rm_name: str,
        new_rm_binary: str,
        timeout: float = 30.0,
    ):
        """
        Reconfigure a partition: kill old RM, start new RM.

        Protocol (pause-based V1):
        1. Python sends CMD_RECONFIG to static binary via mailbox
        2. Static sets quit=1 in partition channel header
        3. Old RM sees quit, exits cleanly
        4. Python detects old RM exit, starts new RM binary
        5. New RM sets rm_ready=1 in partition channel header
        6. Static detects rm_ready, resumes barrier cycling
        7. Static sets CMD_NOOP in mailbox -> Python sees completion

        Parameters
        ----------
        partition_name : str
            Name of the partition to reconfigure.
        new_rm_name : str
            Name of the new RM variant to load.
        new_rm_binary : str
            Path to the new RM binary.
        timeout : float
            Timeout for the entire reconfiguration.
        """
        from . import trace
        if not self._running:
            raise RuntimeError("Simulation is not running")

        pc = self._partition_infos[partition_name]
        partition_index = pc['index']
        partition_target = partition_index + 1  # 1-based for mailbox

        old_rm_name = self._rm_names.get(partition_name)
        logger.info(
            f"Reconfiguring partition '{partition_name}': "
            f"'{old_rm_name}' -> '{new_rm_name}'"
        )

        # Tracing covers each step individually so any orphan begin in the
        # JSONL points at exactly which subphase hung (cmd send, old-exit,
        # new-start, NOOP wait, or settle cycles).
        with trace.span('sim_process.reconfigure',
                        partition=partition_name,
                        old_rm=old_rm_name, new_rm=new_rm_name):

            reconfig_shm = SharedMemoryInterface(
                shm_path=str(self.shm_dir / 'cmd_mailbox.shm'),
                target=partition_target,
                create=False,
                timeout=5.0,
            )

            # Step 1: Write CMD_RECONFIG fields then cmd (no polling)
            reconfig_shm._write_u32(OFFSET_TARGET, partition_target)
            reconfig_shm._write_u32(OFFSET_PORT_IDX, 0)
            reconfig_shm._write_u32(OFFSET_RM_IDX, 0)
            reconfig_shm._write_u32(OFFSET_CMD, CMD_RECONFIG)
            trace.event('sim_process.send_cmd_reconfig',
                        partition=partition_name, target=partition_target)

            # Step 2: Wait for old RM to exit (it sees quit=1 and breaks)
            old_proc = self._rm_processes.get(partition_name)
            with trace.span('sim_process.wait_old_exit',
                            partition=partition_name,
                            old_pid=(old_proc.pid if old_proc is not None else None)):
                if old_proc is not None:
                    start_time = time.time()
                    while old_proc.poll() is None:
                        if time.time() - start_time > timeout:
                            trace.event('sim_process.wait_old_exit.timeout',
                                        elapsed_s=time.time() - start_time)
                            old_proc.kill()
                            old_proc.wait()
                            break
                        # 100 µs polling (was 10 ms) — surfaced by the
                        # structured tracer as 57% of every swap's wall time.
                        # Old RM exits in microseconds once it sees quit=1;
                        # 10 ms polling was a 100× overshoot per swap.
                        time.sleep(0.0001)
                    logger.info(f"Old RM '{old_rm_name}' exited (code={old_proc.returncode})")

            # Step 3: Clear quit and rm_ready in partition channel header
            mm = self._partition_mms[partition_name]
            mm.seek(20)  # quit offset within ShmPartitionHeader
            mm.write(struct.pack('<I', 0))
            mm.seek(24)  # rm_ready offset
            mm.write(struct.pack('<I', 0))

            # Step 4: Start new RM binary (it will set rm_ready=1)
            with trace.span('sim_process.start_new_rm',
                            partition=partition_name, new_rm=new_rm_name):
                self._start_rm_process(
                    partition_name, new_rm_name,
                    new_rm_binary, partition_index,
                )

            # Step 5: Poll for CMD_NOOP — static sets it after seeing rm_ready
            with trace.span('sim_process.wait_noop',
                            partition=partition_name):
                start_time = time.time()
                poll_iter = 0
                while reconfig_shm._read_u32(OFFSET_CMD) != CMD_NOOP:
                    if time.time() - start_time > timeout:
                        trace.event('sim_process.wait_noop.timeout',
                                    elapsed_s=time.time() - start_time,
                                    iter=poll_iter)
                        reconfig_shm.close()
                        raise TimeoutError(
                            f"Timeout waiting for reconfiguration to complete "
                            f"(partition '{partition_name}')"
                        )
                    # 100 µs polling (was 1 ms) — keeps wall-clock honest for E2.
                    time.sleep(0.0001)
                    poll_iter += 1

            # Step 6: Wait for at least 2 cycles so swap_channels propagates
            # the new RM's output data from outbox to inbox.
            from .shm_interface import OFFSET_CYCLE_COUNT
            cycle_before = reconfig_shm._read_u64(OFFSET_CYCLE_COUNT)
            with trace.span('sim_process.settle_cycles',
                            partition=partition_name,
                            cycle_before=cycle_before):
                deadline = time.time() + 2.0
                while reconfig_shm._read_u64(OFFSET_CYCLE_COUNT) < cycle_before + 2:
                    if time.time() > deadline:
                        trace.event('sim_process.settle_cycles.timeout',
                                    last_cycle=reconfig_shm._read_u64(OFFSET_CYCLE_COUNT))
                        break
                    time.sleep(0.0001)

            reconfig_shm.close()

            logger.info(
                f"Reconfiguration complete: partition '{partition_name}' "
                f"now running '{new_rm_name}'"
            )

    def get_interface(self, target: int = 0) -> SharedMemoryInterface:
        """
        Get a shared memory interface for a specific target.

        Parameters
        ----------
        target : int
            Target ID (0=static, 1+=partition 1-based index).

        Returns
        -------
        SharedMemoryInterface
            Interface configured for the specified target.
        """
        if not self._running:
            raise RuntimeError("Simulation is not running")

        return SharedMemoryInterface(
            shm_path=str(self.shm_dir / 'cmd_mailbox.shm'),
            target=target,
            create=False,
        )

    @property
    def shm(self) -> Optional[SharedMemoryInterface]:
        """Get the primary shared memory interface."""
        return self._shm

    @property
    def barrier(self) -> Optional[CycleBarrier]:
        """Get the cycle barrier."""
        return self._barrier

    @property
    def is_running(self) -> bool:
        """Check if simulation is running (static process alive)."""
        if self._static_process is None:
            return False
        return self._static_process.poll() is None

    @property
    def cycle_count(self) -> int:
        """Get current simulation cycle count."""
        if self._shm is None:
            return 0
        return self._shm.cycle_count

    def get_rm_name(self, partition_name: str) -> Optional[str]:
        """Get name of currently loaded RM for a partition."""
        return self._rm_names.get(partition_name)

    def terminate(self, timeout: float = 10.0):
        """
        Gracefully terminate the simulation.

        1. Send CMD_QUIT via shared memory -> static sets quit on all partitions
        2. Wait for RM processes to exit
        3. Wait for static process to exit
        4. Clean up shared memory files
        """
        if not self._running:
            return

        # Try graceful quit via shared memory
        if self._shm is not None and self._shm.is_running:
            try:
                self._shm.quit()
            except (TimeoutError, RuntimeError):
                pass

        # Wait for static process
        if self._static_process is not None and self._static_process.poll() is None:
            try:
                self._static_process.wait(timeout=timeout / 2)
            except subprocess.TimeoutExpired:
                self._static_process.terminate()
                try:
                    self._static_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._static_process.kill()
                    self._static_process.wait()

        # Wait for RM processes
        for part_name, proc in self._rm_processes.items():
            if proc.poll() is None:
                try:
                    proc.wait(timeout=timeout / 4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        self._cleanup()

    def _force_kill_all(self):
        """Force kill all processes (used on startup failure)."""
        if self._static_process is not None and self._static_process.poll() is None:
            self._static_process.kill()
            self._static_process.wait()

        for proc in self._rm_processes.values():
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        self._cleanup()

    def _cleanup(self):
        """Clean up all resources."""
        self._running = False
        self._static_process = None
        self._rm_processes.clear()
        self._rm_names.clear()

        if self._shm is not None:
            self._shm.close()
            self._shm = None

        if self._barrier is not None:
            self._barrier.close()
            self._barrier = None

        # Close partition channel mmaps
        for name, mm in self._partition_mms.items():
            mm.close()
        for name, fd in self._partition_fds.items():
            os.close(fd)
        self._partition_mms.clear()
        self._partition_fds.clear()
        self._partition_sizes.clear()

        # Remove shm files
        if self.shm_dir.exists():
            for f in self.shm_dir.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass

        logger.info("Simulation terminated and cleaned up")

    def wait(self, timeout: float = None) -> int:
        """
        Wait for simulation to complete.

        Returns
        -------
        int
            Static process return code.
        """
        if self._static_process is None:
            return 0
        rc = self._static_process.wait(timeout=timeout)
        self._cleanup()
        return rc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()
        return False
