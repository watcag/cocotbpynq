"""
Cocotb Runner for PR simulation.

Orchestrates:
1. Building RM binaries (rm_only mode)
2. Creating SHM files and starting RM processes
3. Building and running the cocotb simulation (static region + DPI bridges)
4. Cleanup on exit

The static region runs inside cocotb's Verilator process. RM binaries run
as separate processes communicating via mmap'd shared memory and barriers.
"""
from typing import Dict, Optional
from pathlib import Path
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)


def _control_thread(pr_system, ctrl_shm_path: str, stop_event: threading.Event):
    """
    Background thread: polls SHM ctrl_mailbox for reconfiguration requests.
    """
    from .cocotb_mode import CtrlMailbox
    from cocotbpynq._pr_engine import trace
    mb = CtrlMailbox(ctrl_shm_path, create=False)
    last_seq = -1
    print(f"[control] thread started, SHM={ctrl_shm_path}", flush=True)
    trace.event('control_thread.started', shm=ctrl_shm_path)

    while not stop_event.is_set():
        if mb.status == CtrlMailbox.STATUS_PENDING:
            seq = mb.seq_req
            if seq != last_seq:
                last_seq = seq
                partition = mb.partition
                rm = mb.rm_name
                print(f"[control] reconfigure {partition} -> {rm}", flush=True)
                trace.event('control_thread.pending_detected',
                            partition=partition, rm=rm, seq=seq)
                try:
                    with trace.span('control_thread.reconfigure_call',
                                    partition=partition, rm=rm, seq=seq):
                        pr_system.reconfigure(partition, rm)
                    mb.complete_ok(seq)
                    trace.event('control_thread.response_written',
                                seq=seq, status='ok')
                    print(f"[control] reconfigure complete", flush=True)
                except Exception as e:
                    mb.complete_error(seq, str(e))
                    trace.event('control_thread.response_written',
                                seq=seq, status='error', error=str(e))
                    print(f"[control] reconfigure failed: {e}", flush=True)
        # Tight polling — 100 µs yields a measurable wall-clock reduction in
        # E2 vs the previous 5 ms; CPU cost is negligible (control thread is
        # idle ≥99% of the time during normal simulation).
        time.sleep(0.0001)

    trace.event('control_thread.stopped')
    mb.close()


class PRCocotbRunner:
    """Builds and runs a cocotb-based PR simulation.

    Parameters
    ----------
    pr_system : PRSystem
        The configured PRSystem instance (after add_partition/add_rm calls).
    test_module : str
        Python module name containing cocotb tests (e.g. 'my_test').
    test_dir : str or Path, optional
        Directory containing the test module. Defaults to cwd.
    extra_env : dict, optional
        Additional environment variables for the cocotb test process.
    hwh_location_dir : str or Path, optional
        Directory containing the HWH file (for cocotbpynq overlay).
    waves : bool
        Enable waveform dumping (static region via cocotb + RMs via their own tracers).
        When True, PRSystem.trace is also enabled so RM binaries get VCD/FST support.
    merge_waveforms : bool
        After the test completes, merge static region + RM traces into a single
        unified VCD. Requires waves=True. Output path: test_dir / 'merged.vcd'.
    merged_waveform_path : str or Path, optional
        Override output path for merged waveform (default: test_dir / 'merged.vcd').
    """

    def __init__(
        self,
        pr_system,
        test_module: str,
        test_dir: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
        hwh_location_dir: Optional[str] = None,
        waves: bool = False,
        merge_waveforms: bool = False,
        merged_waveform_path: Optional[str] = None,
    ):
        self.pr_system = pr_system
        self.test_module = test_module
        self.test_dir = Path(test_dir) if test_dir else Path.cwd()
        self.extra_env = extra_env or {}
        self.hwh_location_dir = hwh_location_dir
        self.waves = waves
        self.merge_waveforms = merge_waveforms
        self.merged_waveform_path = merged_waveform_path

        # When waves is requested, make sure PRSystem also enables trace
        # so RM binaries are built with VCD/FST dumping support.
        if self.waves and not self.pr_system.trace:
            self.pr_system.trace = True

    def _generate_hwh(self, build_dir: Path) -> Path:
        """
        Auto-generate a HWH file from the PRConfig's static_region.interfaces.

        Returns the directory containing the generated .hwh file so it can
        be passed to cocotbpynq via HWH_LOCATION_DIR.
        """
        from cocotbpynq._pr_engine.codegen.hwh_generator import HwhGenerator

        builder = self.pr_system._builder
        design_name      = builder._static_design or 'static_region'
        clock_name       = builder._static_clock_name or 'clk'
        reset_name       = builder._static_reset_name
        reset_active_low = builder._static_reset_active_low

        sr = (self.pr_system.config.static_region or {}) if self.pr_system.config else {}
        interfaces = sr.get('interfaces', {})

        hwh_dir = build_dir / 'hwh'
        gen = HwhGenerator(build_dir=str(hwh_dir))
        gen.generate(
            design_name=design_name,
            interfaces=interfaces,
            clock_name=clock_name,
            reset_name=reset_name,
            reset_active_low=reset_active_low,
            output_name='design',
        )
        logger.info(f"Auto-generated HWH in {hwh_dir}")
        return hwh_dir

    def run(self):
        """Execute the full cocotb PR simulation.

        Steps:
        1. Build with cocotb_mode=True (generates bridges, barrier C++, RM binaries)
        2. Create SHM files and start RM processes
        3. Create SHM ctrl_mailbox and start control thread
        4. Build cocotb simulation (static region + DPI bridges)
        5. Run cocotb test
        6. Cleanup

        Returns the number of failed cocotb tests (0 on success).
        """
        from cocotb_tools.runner import get_results, get_runner
        from .cocotb_mode import CtrlMailbox

        # Step 1: Build (must come before we can access builder)
        logger.info("Step 1: Building PR simulation (cocotb mode)...")
        self.pr_system.build(cocotb_mode=True)

        builder   = self.pr_system._builder
        build_dir = builder.build_dir
        dpi_dir   = build_dir / 'dpi'
        bridges_dir = build_dir / 'bridges'

        # Persistent waveform directory (RM binaries read PR_TRACE_DIR from env)
        import os
        trace_dir = build_dir / 'waves'
        if self.waves:
            trace_dir.mkdir(parents=True, exist_ok=True)
            os.environ['PR_TRACE_DIR'] = str(trace_dir.resolve())
        self._trace_dir = trace_dir

        # Step 2: Create SHM and start RM processes
        logger.info("Step 2: Creating SHM and starting RM processes...")
        process_mgr = self.pr_system._start_rm_processes_only()

        # Step 3: Create SHM ctrl mailbox and start control thread
        ctrl_shm_path = str(process_mgr.shm_dir.resolve() / 'ctrl_mailbox.shm')
        CtrlMailbox(ctrl_shm_path, create=True).close()

        stop_event = threading.Event()
        ctrl_thread = threading.Thread(
            target=_control_thread,
            args=(self.pr_system, ctrl_shm_path, stop_event),
            daemon=True,
        )
        ctrl_thread.start()

        try:
            # Step 4: Build cocotb simulation
            logger.info("Step 4: Building cocotb simulation...")
            runner = get_runner("verilator")

            sv_sources = list(builder._static_sources)
            cocotb_top = bridges_dir / 'pr_cocotb_top.sv'
            if cocotb_top.exists():
                sv_sources.append(str(cocotb_top))

            cpp_files = []
            barrier_cpp = dpi_dir / 'pr_cocotb_barrier.cpp'
            if barrier_cpp.exists():
                cpp_files.append(str(barrier_cpp))
            for cpp_path in sorted(dpi_dir.glob('dpi_static_*.cpp')):
                cpp_files.append(str(cpp_path))

            build_args = [
                '-CFLAGS', f'-I{dpi_dir}',
                '--public-flat-rw',
                '-Wno-WIDTHTRUNC',
            ]
            for cpp_file in cpp_files:
                build_args.append(cpp_file)
            for inc_dir in builder._static_include_dirs:
                build_args.extend(['-I', inc_dir])

            runner.build(
                sources=[str(s) for s in sv_sources],
                hdl_toplevel='pr_cocotb_top',
                always=True,
                build_args=build_args,
                timescale=('1ns', '1ps'),
                waves=self.waves,
            )

            # Step 5: Run cocotb test
            logger.info("Step 5: Running cocotb test...")

            hwh_dir = self.hwh_location_dir
            if hwh_dir is None:
                hwh_dir = self._generate_hwh(build_dir)
            hwh_dir = Path(hwh_dir).resolve()

            env = {
                'PR_SHM_DIR':        str(process_mgr.shm_dir.resolve()),
                'PR_CTRL_SHM':       ctrl_shm_path,
                'HWH_LOCATION_DIR':  str(hwh_dir),
                'COCOTB_SYS_ARGV':   ' '.join(sys.argv),
            }

            # Pass partition map and switch info for Overlay.chain()
            import json
            partition_map = {}
            sr = (self.pr_system.config.static_region or {}) if self.pr_system.config else {}
            interfaces = sr.get('interfaces', {})
            for idx, part_cfg in enumerate(self.pr_system.config.partitions):
                partition_map[part_cfg['name']] = idx
            env['PR_PARTITION_MAP'] = json.dumps(partition_map)

            # Detect switch from axil interfaces
            for iface_name, iface_def in interfaces.items():
                if iface_def.get('type') == 'axil' and 'switch' in iface_name.lower():
                    env['PR_SWITCH_ADDR'] = hex(iface_def.get('base_addr', 0))
                    env['PR_SWITCH_RANGE'] = hex(iface_def.get('addr_range', 0x10000))
                    env['PR_NUM_SWITCH_PORTS'] = str(2 * len(partition_map))
                    break

            # Map partition names to their DMA instance names
            dma_map = {}
            for iface_name, iface_def in interfaces.items():
                if iface_def.get('type') == 'sb' and iface_def.get('dma_instance'):
                    dma_inst = iface_def['dma_instance']
                    if dma_inst not in dma_map:
                        dma_map[dma_inst] = iface_name
            # Associate DMAs with partitions by order
            dma_instances = sorted(set(
                iface_def.get('dma_instance')
                for iface_def in interfaces.values()
                if iface_def.get('type') == 'sb' and iface_def.get('dma_instance')
            ))
            for idx, part_cfg in enumerate(self.pr_system.config.partitions):
                if idx < len(dma_instances):
                    env[f"PR_DMA_{part_cfg['name']}"] = dma_instances[idx]

            env.update(self.extra_env)

            results_xml = runner.test(
                hdl_toplevel='pr_cocotb_top',
                hdl_toplevel_lang='verilog',
                test_dir=str(self.test_dir),
                test_module=[self.test_module],
                extra_env=env,
                waves=self.waves,
            )

            _, num_failed = get_results(results_xml)

            # Step 5b: Merge waveforms if requested
            if self.merge_waveforms:
                self._run_merger(build_dir)

        finally:
            # Step 6: Cleanup
            stop_event.set()
            ctrl_thread.join(timeout=2.0)
            process_mgr.terminate()

        return num_failed

    def _run_merger(self, build_dir):
        """Invoke the waveform merger as a subprocess in a py3.14+ewal env.

        cocotbpynq itself runs on 3.13 (cocotb caps there) while ewal requires
        3.14. We bridge via `uv run --no-project --python 3.14 --with <ewal>`.
        """
        import subprocess
        import shutil

        if not self.waves:
            logger.warning("merge_waveforms=True but waves=False — nothing to merge.")
            return

        static_vcd = (self.test_dir / 'dump.vcd').resolve()
        rm_dir = self._trace_dir.resolve()
        output = (Path(self.merged_waveform_path) if self.merged_waveform_path
                  else (self.test_dir / 'merged.vcd')).resolve()

        if not static_vcd.exists() and not rm_dir.is_dir():
            logger.warning("No traces found to merge.")
            return

        # Locate ewal: user can set EWAL_PATH env var; default is ../ewal relative
        # to the cocotbpynq checkout — adjust as needed for deployment.
        ewal_path = os.environ.get('EWAL_PATH')
        if ewal_path is None:
            guess = Path(__file__).resolve().parents[3] / 'ewal'
            if not guess.exists():
                guess = Path.home() / 'projects' / 'ewal'
            ewal_path = str(guess)

        if shutil.which('uv') is None:
            logger.warning("`uv` not on PATH — cannot run waveform merger. "
                           "Install uv or run manually: "
                           f"python -m cocotbpynq.pr.waveform_merger "
                           f"--static {static_vcd} --rm-dir {rm_dir} --output {output}")
            return

        # Run the merger as a standalone script (bypasses cocotbpynq's
        # __init__.py which imports cocotb, unavailable on py3.14).
        merger_script = Path(__file__).resolve().parent / 'waveform_merger.py'

        cmd = [
            'uv', 'run', '--no-project', '--python', '3.14',
            '--with', ewal_path,
            'python', str(merger_script),
            '--rm-dir', str(rm_dir),
            '--output', str(output),
        ]
        if static_vcd.exists():
            cmd += ['--static', str(static_vcd)]

        # Build variant→partition map so merged scopes read top/rm/{partition}/{variant}/pid{N}
        import json
        variant_to_partition = {}
        if self.pr_system and self.pr_system.partitions:
            for part_name, partition in self.pr_system.partitions.items():
                for rm_name in partition.registered_rms:
                    variant_to_partition[rm_name] = part_name
        if variant_to_partition:
            cmd += ['--partition-map', json.dumps(variant_to_partition)]

        env = os.environ.copy()
        # Scrub env vars that would leak cocotbpynq's py3.13 environment into
        # the py3.14 uv subprocess (uv respects VIRTUAL_ENV/UV_* etc).
        for var in list(env):
            if var.startswith('UV_') or var in ('VIRTUAL_ENV', 'PYTHONPATH',
                                                 'PYTHONHOME'):
                env.pop(var, None)

        logger.info(f"Running waveform merger → {output}")
        # Run from /tmp so uv doesn't discover the parent cocotbpynq pyproject.
        result = subprocess.run(cmd, env=env, cwd='/tmp',
                                capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Merger failed (exit {result.returncode}):\n"
                         f"stdout: {result.stdout}\nstderr: {result.stderr}")
            return
        # Forward merger log lines so users see the summary
        for line in result.stderr.splitlines():
            if line.strip():
                print(line)
        print(f"Merged waveform: {output}")
