from typing import Dict, List, Optional, Union, Any
from pathlib import Path
import logging

from .config import PRConfig
from .partition import Partition
from .module import ReconfigurableModule
from .static import StaticRegion
from .exceptions import PRConfigError, PRReconfigurationError, PRBuildError
from .barrier import CycleBarrier
from .verilator_builder import VerilatorBuilder
from .sim_process import SimulationProcessManager
from .shm_interface import SharedMemoryInterface

logger = logging.getLogger(__name__)


class PRSystem:
    """Top-level orchestrator for partial reconfiguration simulation."""

    def __init__(
        self,
        config: Union[str, Path, PRConfig, dict] = None,
        tool: str = 'verilator',
        trace: bool = False,
        trace_type: str = 'vcd',
        frequency: float = 100e6,
        max_rate: float = -1,
        start_delay: float = None,
        build_dir: str = None,
        require_static_region: bool = True,
        cycle_accurate: bool = False,
    ):
        self.config: Optional[PRConfig] = None
        self.tool = tool
        self.trace = trace
        self.trace_type = trace_type
        self.frequency = frequency
        self.max_rate = max_rate
        self.start_delay = start_delay
        self.build_dir = build_dir or 'build/pr'
        self.require_static_region = require_static_region
        self.cycle_accurate = cycle_accurate
        self._static_region: Optional[StaticRegion] = None
        self.partitions: Dict[str, Partition] = {}
        self.modules: Dict[str, ReconfigurableModule] = {}
        self._sim_process: Optional[SimulationProcessManager] = None
        self._builder: Optional[VerilatorBuilder] = None
        self._shm_interfaces: Dict[str, SharedMemoryInterface] = {}
        self._binary_paths: Dict[str, Path] = {}
        self._rm_binary_map: Dict[str, str] = {}
        self._built = False
        self._running = False

        if config is not None:
            self.load_config(config)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.terminate()
        return False

    def load_config(self, config: Union[str, Path, PRConfig, dict]) -> 'PRSystem':
        if isinstance(config, PRConfig):
            self.config = config
        elif isinstance(config, dict):
            self.config = PRConfig.from_dict(config)
        else:
            self.config = PRConfig.load(config)
        self._setup_from_config()
        return self

    def _setup_from_config(self):
        if self.config is None:
            return

        sim = self.config.simulation
        if 'tool' in sim:
            self.tool = sim['tool']
        if 'trace' in sim:
            self.trace = sim['trace']
        if 'trace_type' in sim:
            self.trace_type = sim['trace_type']
        if 'frequency' in sim:
            self.frequency = float(sim['frequency'])
        if 'max_rate' in sim:
            self.max_rate = float(sim['max_rate'])
        if 'start_delay' in sim:
            self.start_delay = float(sim['start_delay'])
        if 'build_dir' in sim:
            self.build_dir = sim['build_dir']

        if self.config.static_region:
            self._setup_static_region(self.config.static_region)

        for part_cfg in self.config.partitions:
            interface = part_cfg.get('interface', {})
            partition = Partition(
                name=part_cfg['name'],
                interface=interface,
                system=self,
                initial_rm=part_cfg.get('initial_rm')
            )
            self.partitions[part_cfg['name']] = partition

        for rm_cfg in self.config.reconfigurable_modules:
            rm = ReconfigurableModule(
                name=rm_cfg['name'],
                partition_name=rm_cfg['partition'],
                design=rm_cfg.get('design'),
                sources=rm_cfg.get('sources', []),
                parameters=rm_cfg.get('parameters', {}),
                port_mapping=rm_cfg.get('port_mapping', {}),
                port_compatibility=rm_cfg.get('port_compatibility', {}),
                clocks=rm_cfg.get('clocks', ['clk']),
                resets=rm_cfg.get('resets', []),
                tieoffs=rm_cfg.get('tieoffs', {}),
                interfaces=rm_cfg.get('interfaces', {}),
                system=self,
                auto_wrap=rm_cfg.get('auto_wrap', False),
                auto_wrap_config=rm_cfg.get('auto_wrap_config', {}),
                ports_override=rm_cfg.get('ports')
            )
            self.modules[rm_cfg['name']] = rm
            partition = self.partitions[rm_cfg['partition']]
            partition.register_rm(rm)

    def _setup_static_region(self, sr_cfg: Dict):
        if 'clock' in sr_cfg:
            clocks = [sr_cfg['clock']]
        else:
            clocks = sr_cfg.get('clocks', ['clk'])

        self._static_region = StaticRegion(
            name=sr_cfg.get('name', 'static_region'),
            design=sr_cfg.get('design'),
            sources=sr_cfg.get('sources', []),
            parameters=sr_cfg.get('parameters', {}),
            interfaces=sr_cfg.get('interfaces', {}),
            clocks=clocks,
            resets=sr_cfg.get('resets', []),
            system=self,
            build_dir=f"{self.build_dir}/static",
            auto_wrap=sr_cfg.get('auto_wrap', False),
            auto_wrap_config=sr_cfg.get('auto_wrap_config', {}),
            ports_override=sr_cfg.get('ports')
        )

    @property
    def static_region(self) -> Optional[StaticRegion]:
        return self._static_region

    def add_partition(
        self,
        name: str,
        interface: Dict[str, Dict],
        initial_rm: str = None
    ) -> Partition:
        partition = Partition(
            name=name,
            interface=interface,
            system=self,
            initial_rm=initial_rm
        )
        self.partitions[name] = partition
        return partition

    def add_rm(
        self,
        name: str,
        partition: str,
        design: str = None,
        sources: List[str] = None,
        parameters: Dict = None,
        port_mapping: Dict[str, str] = None,
        clocks: List[str] = None,
        resets: List = None,
        tieoffs: Dict = None
    ) -> ReconfigurableModule:
        if partition not in self.partitions:
            raise PRConfigError(f"Partition '{partition}' does not exist")

        rm = ReconfigurableModule(
            name=name,
            partition_name=partition,
            design=design,
            sources=sources or [],
            parameters=parameters or {},
            port_mapping=port_mapping or {},
            clocks=clocks or ['clk'],
            resets=resets or [],
            tieoffs=tieoffs or {},
            system=self
        )
        self.modules[name] = rm
        self.partitions[partition].register_rm(rm)
        return rm

    def build(self, fast: bool = False, cocotb_mode: bool = False) -> 'PRSystem':
        from cocotbpynq._toolchain import ensure_verilator
        ensure_verilator()
        if self.require_static_region and self._static_region is None:
            raise PRBuildError("No static region configured")

        static_binary_path = Path(self.build_dir) / 'static_binary'
        if fast and static_binary_path.exists():
            logger.info("Skipping build (fast=True and static_binary exists)")
            self._built = True
            self._binary_paths = {'static': static_binary_path}
            for part_name, partition in self.partitions.items():
                for rm_name, rm in partition.registered_rms.items():
                    rm_path = Path(self.build_dir) / 'rm' / rm_name / 'rm_binary'
                    if rm_path.exists():
                        self._binary_paths[f'rm/{rm_name}'] = rm_path
                        self._rm_binary_map[rm_name] = str(rm_path)
                    if not rm._built:
                        rm.build()
            return self

        self._builder = VerilatorBuilder(
            build_dir=self.build_dir,
            trace=self.trace,
            trace_type=self.trace_type,
        )

        self._setup_builder()
        self._binary_paths = self._builder.build(cocotb_mode=cocotb_mode)

        if self._static_region and not self._static_region._built:
            self._static_region.build()
        for partition in self.partitions.values():
            for rm in partition.registered_rms.values():
                if not rm._built:
                    rm.build()

        for key, path in self._binary_paths.items():
            if key.startswith('rm/'):
                rm_name = key[3:]
                self._rm_binary_map[rm_name] = str(path)

        self._built = True
        return self

    def _setup_builder(self):
        if self._builder is None:
            raise PRBuildError("Builder not initialized")
        if self._static_region is None:
            raise PRBuildError("No static region configured")

        # Auto-generate static region RTL if no sources provided
        if not self._static_region.sources and self.config and self.config.partitions:
            self._auto_generate_static()

        static_sources = self._resolve_sources(self._static_region.sources)
        static_design = self._static_region.design if isinstance(
            self._static_region.design, str
        ) else self._static_region.name

        # Collect static region ports
        static_ports = []
        if self._static_region.ports_override:
            for port_name, port_def in self._static_region.ports_override.items():
                static_ports.append({
                    'name': port_name,
                    'width': port_def.get('width', 1),
                    'direction': port_def.get('direction', 'input'),
                })
        elif self._static_region.sources:
            from .rtl_parser import RTLParser
            parser = RTLParser()
            module_name = static_design
            resolved_sources = self._resolve_sources(self._static_region.sources)
            try:
                module_info = parser.parse_module(resolved_sources, module_name)
                for port_name, port in module_info.ports.items():
                    if port_name in ('clk', 'rst', 'reset', 'rst_n', 'reset_n'):
                        continue
                    static_ports.append({
                        'name': port_name,
                        'width': port.width,
                        'direction': port.direction,
                    })
            except Exception as e:
                logger.warning(f"Could not parse static region RTL for port info: {e}")

        # Detect clock/reset from RTL
        from .verilator_builder import _detect_clock_from_rtl, _detect_reset_from_rtl
        static_clock = _detect_clock_from_rtl(static_sources, static_design)
        if static_clock is None:
            static_clock = self._static_region.clocks[0] if self._static_region.clocks else 'clk'

        reset_result = _detect_reset_from_rtl(static_sources, static_design, clock_name=static_clock)
        if reset_result is not None:
            static_reset, static_reset_active_low = reset_result
        else:
            static_reset = None
            static_reset_active_low = True

        self._builder.set_static_region(
            design_name=static_design,
            sources=static_sources,
            ports=static_ports,
            clock_name=static_clock,
            reset_name=static_reset,
            reset_active_low=static_reset_active_low,
        )

        if self.config is None:
            return

        for part_idx, part_cfg in enumerate(self.config.partitions):
            if 'boundary' not in part_cfg:
                continue

            partition_name = part_cfg['name']
            rm_module = part_cfg.get('rm_module')
            clock_names = part_cfg.get('clocks', [part_cfg.get('clock', 'clk')])

            resets = part_cfg.get('resets', [])
            reset_name = resets[0]['name'] if resets else None
            reset_polarity = resets[0].get('polarity', 'negative') if resets else 'negative'
            reset_cycles = part_cfg.get('reset_cycles', 10)
            reset_behavior = part_cfg.get('reset_behavior', 'fresh')

            if not rm_module:
                logger.warning(f"Partition '{partition_name}' has boundary but no rm_module specified")
                continue

            to_rm_ports = []
            from_rm_ports = []
            for port_cfg in part_cfg['boundary']:
                port_dict = {'name': port_cfg['name'], 'width': port_cfg.get('width', 1)}
                if port_cfg['direction'] == 'to_rm':
                    to_rm_ports.append(port_dict)
                else:
                    from_rm_ports.append(port_dict)

            partition = self.partitions.get(partition_name)
            rm_variants = []
            if partition:
                for rm_idx, (rm_name, rm) in enumerate(partition.registered_rms.items()):
                    rm_design = rm.design or rm_name
                    rm_sources = self._resolve_sources(rm.sources)
                    if rm.parameters:
                        safe_params = "_".join(f"{k}{v}" for k, v in rm.parameters.items())
                        wrapper_name = f"{rm_design}_{safe_params}_dpi_wrapper"
                    else:
                        wrapper_name = f"{rm_design}_dpi_wrapper"
                    rm_variants.append({
                        'name': rm_name,
                        'design': rm_design,
                        'wrapper_name': wrapper_name,
                        'index': rm_idx,
                        'sources': rm_sources,
                        'include_dirs': [],
                        'parameters': rm.parameters,
                    })
                    rm._rm_index = rm_idx

            initial_rm_index = 0
            if partition and partition.initial_rm_name:
                for i, rm_name in enumerate(partition.registered_rms.keys()):
                    if rm_name == partition.initial_rm_name:
                        initial_rm_index = i
                        break

            self._builder.add_partition(
                name=partition_name,
                index=part_idx,
                rm_module_name=rm_module,
                clock_names=clock_names,
                to_rm_ports=to_rm_ports,
                from_rm_ports=from_rm_ports,
                rm_variants=rm_variants,
                initial_rm_index=initial_rm_index,
                reset_name=reset_name,
                reset_polarity=reset_polarity,
                reset_cycles=reset_cycles,
                reset_behavior=reset_behavior,
            )

            if partition:
                partition._partition_index = part_idx

    def _auto_generate_static(self):
        """Auto-generate static region RTL from config when no sources are provided."""
        from .codegen.static_generator import generate_static_region

        sr_cfg = self.config.static_region or {}
        awc = sr_cfg.get('auto_wrap_config', {})
        clock_name = awc.get('clock_name', 'clk')
        reset_name = awc.get('reset_name')
        design_name = self._static_region.design or self._static_region.name

        gen_dir = str(Path(self.build_dir) / 'generated')
        gen_path = generate_static_region(
            design_name=design_name,
            clock_name=clock_name,
            reset_name=reset_name,
            partitions=self.config.partitions,
            interfaces=sr_cfg.get('interfaces', {}),
            build_dir=gen_dir,
        )
        self._static_region.sources = [str(gen_path)]
        logger.info(f"Auto-generated static region: {gen_path}")

        # If switch is used, also include axis_switch.sv
        interfaces = sr_cfg.get('interfaces', {})
        for iface_name, iface_def in interfaces.items():
            if iface_def.get('type') == 'axil' and 'switch' in iface_name.lower():
                switch_sv = Path(gen_dir) / 'axis_switch.sv'
                if not switch_sv.exists():
                    # Copy the packaged switch RTL
                    packaged_switch = Path(__file__).parent / 'rtl' / 'axis_switch.sv'
                    if not packaged_switch.exists():
                        raise FileNotFoundError(
                            f"packaged axis_switch.sv missing: {packaged_switch} "
                            "(broken cocotbpynq install?)")
                    import shutil
                    shutil.copy2(str(packaged_switch), str(switch_sv))
                    logger.info(f"Copied axis_switch.sv to {switch_sv}")
                if switch_sv.exists() and str(switch_sv) not in self._static_region.sources:
                    self._static_region.sources.append(str(switch_sv))
                break

    def _resolve_sources(self, sources: List[str]) -> List[str]:
        resolved = []
        for source in sources:
            source_path = Path(source)
            if source_path.exists():
                resolved.append(str(source_path.resolve()))
            elif self.config and self.config._source_path:
                config_dir = self.config._source_path.parent
                rel_path = config_dir / source
                if rel_path.exists():
                    resolved.append(str(rel_path.resolve()))
                else:
                    resolved.append(source)
            else:
                resolved.append(source)
        return resolved

    def simulate(
        self,
        initial_rms: Dict[str, str] = None,
        start_delay: float = None
    ) -> SimulationProcessManager:
        if not self._built:
            self.build()

        if initial_rms is None:
            initial_rms = {}
        for part_name, partition in self.partitions.items():
            if part_name not in initial_rms and partition.initial_rm_name:
                initial_rms[part_name] = partition.initial_rm_name

        partition_configs = []
        for part_name, partition in self.partitions.items():
            part_idx = getattr(partition, '_partition_index', 0)
            num_to_rm = 0
            num_from_rm = 0
            if self._builder:
                for pi in self._builder._partitions:
                    if pi.name == part_name:
                        num_to_rm = sum((p.get('width', 32) + 63) // 64 for p in pi.to_rm_ports)
                        num_from_rm = sum((p.get('width', 32) + 63) // 64 for p in pi.from_rm_ports)
                        break
            partition_configs.append({
                'name': part_name,
                'index': part_idx,
                'num_to_rm': num_to_rm,
                'num_from_rm': num_from_rm,
            })

        for partition_name, rm_name in initial_rms.items():
            if partition_name not in self.partitions:
                raise PRReconfigurationError(f"Unknown partition: '{partition_name}'")
            if rm_name not in self.modules and rm_name not in self._rm_binary_map:
                raise PRReconfigurationError(f"Unknown RM: '{rm_name}'")

        static_binary = str(self._binary_paths.get('static', Path(self.build_dir) / 'static_binary'))

        self._sim_process = SimulationProcessManager(build_dir=self.build_dir)
        self._sim_process.start(
            static_binary=static_binary,
            rm_binaries=self._rm_binary_map,
            partition_configs=partition_configs,
            initial_rm_map=initial_rms,
        )

        for partition_name, rm_name in initial_rms.items():
            partition = self.partitions[partition_name]
            rm = self.modules.get(rm_name)
            if rm:
                partition.active_rm = rm

        self._running = True
        if self._static_region:
            self._static_region._running = True
        logger.info(
            f"Simulation started: {1 + len(initial_rms)} processes "
            f"({len(initial_rms)} partitions)"
        )
        return self._sim_process

    def _start_rm_processes_only(
        self,
        initial_rms: Dict[str, str] = None,
    ) -> SimulationProcessManager:
        """Start only RM processes (no static binary). Used in cocotb mode."""
        if initial_rms is None:
            initial_rms = {}
        for part_name, partition in self.partitions.items():
            if part_name not in initial_rms and partition.initial_rm_name:
                initial_rms[part_name] = partition.initial_rm_name

        partition_configs = []
        for part_name, partition in self.partitions.items():
            part_idx = getattr(partition, '_partition_index', 0)
            num_to_rm = 0
            num_from_rm = 0
            if self._builder:
                for pi in self._builder._partitions:
                    if pi.name == part_name:
                        num_to_rm = sum((p.get('width', 32) + 63) // 64 for p in pi.to_rm_ports)
                        num_from_rm = sum((p.get('width', 32) + 63) // 64 for p in pi.from_rm_ports)
                        break
            partition_configs.append({
                'name': part_name,
                'index': part_idx,
                'num_to_rm': num_to_rm,
                'num_from_rm': num_from_rm,
            })

        self._sim_process = SimulationProcessManager(build_dir=self.build_dir)
        shm_dir = self._sim_process.shm_dir
        shm_dir.mkdir(parents=True, exist_ok=True)

        from .shm_interface import SharedMemoryInterface
        self._sim_process._shm = SharedMemoryInterface(
            shm_path=str(shm_dir / 'cmd_mailbox.shm'),
            create=True,
        )

        num_processes = 1 + len(partition_configs)
        from .barrier import CycleBarrier
        self._sim_process._barrier = CycleBarrier(
            uri=str(shm_dir / 'barrier.shm'),
            create=True,
            num_processes=num_processes,
        )

        for pc in partition_configs:
            self._sim_process._partition_infos[pc['name']] = pc
            self._sim_process._create_partition_channel(
                pc['name'], pc['index'],
                pc['num_to_rm'], pc['num_from_rm'],
            )

        for part_name, rm_name in initial_rms.items():
            rm_binary = self._rm_binary_map.get(rm_name)
            if rm_binary is None:
                raise RuntimeError(f"No binary found for RM '{rm_name}'")
            pc = self._sim_process._partition_infos[part_name]
            self._sim_process._start_rm_process(
                part_name, rm_name, rm_binary, pc['index'],
            )

        self._sim_process._running = True
        self._running = True
        return self._sim_process

    def reconfigure(
        self,
        partition: str,
        new_rm: str,
        timeout: float = 10.0
    ) -> bool:
        from . import trace
        if partition not in self.partitions:
            raise PRReconfigurationError(f"Unknown partition: '{partition}'")
        if new_rm not in self.modules:
            raise PRReconfigurationError(f"Unknown RM: '{new_rm}'")
        if new_rm not in self._rm_binary_map:
            raise PRReconfigurationError(f"RM '{new_rm}' has no binary path - was the system built?")

        part = self.partitions[partition]
        rm = self.modules[new_rm]
        old_name = part.active_rm.name if part.active_rm else None

        try:
            with trace.span('pr_system.reconfigure',
                            partition=partition, new_rm=new_rm, old_rm=old_name):
                self._sim_process.reconfigure(
                    partition_name=partition,
                    new_rm_name=new_rm,
                    new_rm_binary=self._rm_binary_map[new_rm],
                    timeout=timeout,
                )
            part.active_rm = rm
            self._shm_interfaces.pop(f'_shm_{partition}', None)
            logger.info(f"Partition '{partition}': reconfigured '{old_name}' -> '{new_rm}'")
            return True
        except Exception as e:
            raise PRReconfigurationError(
                f"Failed to reconfigure partition '{partition}' to '{new_rm}': {e}"
            ) from e

    def get_partition(self, name: str) -> Optional[Partition]:
        return self.partitions.get(name)

    def get_rm(self, name: str) -> Optional[ReconfigurableModule]:
        return self.modules.get(name)

    def shm_for_partition(self, partition_name: str) -> SharedMemoryInterface:
        if partition_name not in self.partitions:
            raise PRReconfigurationError(f"Unknown partition: '{partition_name}'")
        cache_key = f'_shm_{partition_name}'
        if cache_key in self._shm_interfaces:
            return self._shm_interfaces[cache_key]
        if self._sim_process is None:
            raise PRReconfigurationError("Simulation is not running")
        partition = self.partitions[partition_name]
        target = getattr(partition, '_partition_index', 0) + 1
        shm = self._sim_process.get_interface(target=target)
        self._shm_interfaces[cache_key] = shm
        return shm

    def shm_for_static(self) -> SharedMemoryInterface:
        if self._static_region is None:
            raise PRReconfigurationError("No static region configured")
        if not self._running:
            raise PRReconfigurationError("Simulation is not running")
        cache_key = '_shm_static'
        if cache_key in self._shm_interfaces:
            return self._shm_interfaces[cache_key]
        from .shm_interface import TARGET_STATIC
        shm = self._sim_process.get_interface(target=TARGET_STATIC)
        self._shm_interfaces[cache_key] = shm
        return shm

    def terminate(self, timeout: float = 10.0):
        for key, shm in list(self._shm_interfaces.items()):
            try:
                shm.close()
            except Exception:
                pass
        self._shm_interfaces.clear()

        if self._sim_process is not None:
            self._sim_process.terminate(timeout=timeout)
            self._sim_process = None

        self._running = False
        logger.info("Simulation terminated")

    def wait(self, timeout: float = None):
        if self._sim_process is not None:
            self._sim_process.wait(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_built(self) -> bool:
        return self._built

    def __repr__(self) -> str:
        return (
            f"<PRSystem partitions={len(self.partitions)} "
            f"modules={len(self.modules)} "
            f"running={self._running}>"
        )
