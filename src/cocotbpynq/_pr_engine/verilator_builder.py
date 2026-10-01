"""
Verilator Builder for multi-binary DPI-based simulation.

Orchestrates:
1. Source registration for static region and all RMs
2. DPI bridge/wrapper generation (SystemVerilog)
3. DPI C++ code generation (multi-binary: static_driver, rm_drivers, channels)
4. Makefile generation (separate targets per binary)
5. Verilation and compilation via make

Uses pyslang to validate boundary port widths against actual RTL,
catching config/RTL mismatches before they become cryptic Verilator errors.
"""
from typing import Dict, List, Optional, Any, Set
from pathlib import Path
import os
import subprocess
import logging

from .codegen.dpi_bridge_generator import (
    DpiBridgeGenerator, PartitionBoundaryDef, BoundaryPort
)
from .codegen.dpi_cpp_generator import DpiCppGenerator, PartitionInfo, StaticInfo
from .codegen.makefile_generator import MakefileGenerator, ModuleBuildInfo, RmBinaryInfo
from .codegen.cocotb_generator import CocotbGenerator

logger = logging.getLogger(__name__)

# Common clock signal name patterns (case-insensitive match)
_CLOCK_PATTERNS = {'clk', 'clock', 'clk_i', 'clock_i', 'i_clk', 'i_clock', 'sys_clk'}


def _slang_compile(sources: List[str]):
    """
    Parse SystemVerilog sources with pyslang and return (compilation, trees).

    Returns (None, None) if pyslang is unavailable or parsing fails.
    """
    try:
        import pyslang
    except ImportError:
        return None, None

    try:
        trees = []
        for src in sources:
            p = Path(src)
            if p.exists():
                trees.append(pyslang.syntax.SyntaxTree.fromFile(str(p)))
        if not trees:
            return None, None

        comp = pyslang.ast.Compilation()
        for tree in trees:
            comp.addSyntaxTree(tree)
        comp.getAllDiagnostics()  # triggers elaboration
        return comp, trees
    except Exception as e:
        logger.debug(f"pyslang compilation failed: {e}")
        return None, None


def _slang_find_instance(comp, module_name: str):
    """Find a top-level instance by name in a pyslang Compilation."""
    for inst in comp.getRoot().topInstances:
        if inst.name == module_name:
            return inst
    return None


def _pyslang_parse_module(sources: List[str], module_name: str) -> Optional[Dict[str, Dict]]:
    """
    Parse a SystemVerilog module with pyslang and return its port map.

    Returns
    -------
    dict or None
        {port_name: {'width': int, 'direction': str}} or None if parsing fails.
        direction is the raw pyslang string, e.g. 'ArgumentDirection.In'.
    """
    comp, _ = _slang_compile(sources)
    if comp is None:
        return None

    try:
        import pyslang
        inst = _slang_find_instance(comp, module_name)
        if inst is None:
            return None

        ports = {}
        for member in inst.body:
            if member.kind == pyslang.ast.SymbolKind.Port:
                width = member.internalSymbol.type.bitWidth
                ports[member.name] = {
                    'width': width,
                    'direction': str(member.direction),
                }
        return ports
    except Exception as e:
        logger.debug(f"pyslang parse failed for '{module_name}': {e}")
        return None


def _find_posedge_clocks(inst) -> List[str]:
    """
    Walk all ProceduralBlock members and extract port names that appear
    as the signal in a posedge TimingControl (SignalEvent or EventList).

    Uses pyslang's AST: ProceduralBlock → body (Timed statement) →
    timing (SignalEvent/EventList) → edge + expr.getSymbolReference().
    """
    import pyslang

    found = []

    for member in inst.body:
        if member.kind != pyslang.ast.SymbolKind.ProceduralBlock:
            continue

        body = member.body
        if body is None or body.kind != pyslang.ast.StatementKind.Timed:
            continue

        timing = body.timing

        if timing.kind == pyslang.ast.TimingControlKind.SignalEvent:
            _collect_posedge_signal(timing, found)

        elif timing.kind == pyslang.ast.TimingControlKind.EventList:
            for event in timing.events:
                if event.kind == pyslang.ast.TimingControlKind.SignalEvent:
                    _collect_posedge_signal(event, found)

    return found


def _collect_posedge_signal(event, found: List[str]):
    """
    If *event* is a posedge SignalEvent referencing a symbol,
    append that symbol's name to *found* (deduped).
    """
    import pyslang

    if event.edge not in (pyslang.ast.EdgeKind.PosEdge,
                          pyslang.ast.EdgeKind.BothEdges):
        return

    sym = event.expr.getSymbolReference()
    if sym is not None and sym.name not in found:
        found.append(sym.name)


def _detect_clock_from_rtl(sources: List[str], module_name: str) -> Optional[str]:
    """
    Use pyslang AST analysis to detect the clock signal from RTL.

    Detection strategy (never returns None for valid modules with 1-bit inputs):
      1. Parse module with pyslang, gather all 1-bit input ports.
      2. Single 1-bit input → unambiguous clock.
      3. Walk ProceduralBlock timing controls for posedge signals
         (pyslang AST: TimingControlKind.SignalEvent, EdgeKind.PosEdge).
      4. Name-pattern matching fallback.
      5. Last resort: first 1-bit input.
    """
    try:
        import pyslang
    except ImportError:
        return None

    comp, _ = _slang_compile(sources)
    if comp is None:
        return None

    try:
        inst = _slang_find_instance(comp, module_name)
        if inst is None:
            return None

        # Gather 1-bit input ports (in declaration order)
        inputs_1bit: List[str] = []
        for member in inst.body:
            if member.kind == pyslang.ast.SymbolKind.Port:
                width = member.internalSymbol.type.bitWidth
                if width == 1 and member.direction == pyslang.ast.ArgumentDirection.In:
                    inputs_1bit.append(member.name)

        if not inputs_1bit:
            return None

        # Strategy 1: single 1-bit input is unambiguously the clock
        if len(inputs_1bit) == 1:
            logger.info(
                f"pyslang: '{inputs_1bit[0]}' is sole 1-bit input "
                f"in {module_name} — using as clock"
            )
            return inputs_1bit[0]

        # Strategy 2: AST timing-control analysis
        posedge_sigs = _find_posedge_clocks(inst)
        # Keep only those that are actually 1-bit input ports
        posedge_ports = [s for s in posedge_sigs if s in inputs_1bit]

        if len(posedge_ports) == 1:
            logger.info(
                f"pyslang: '{posedge_ports[0]}' detected as clock "
                f"via posedge analysis in {module_name}"
            )
            return posedge_ports[0]

        # Strategy 3: name-pattern matching among candidates
        candidates = posedge_ports if posedge_ports else inputs_1bit

        for name in candidates:
            if name.lower() in _CLOCK_PATTERNS:
                logger.info(f"pyslang: '{name}' matches clock pattern in {module_name}")
                return name

        for name in candidates:
            nl = name.lower()
            if 'clk' in nl or 'clock' in nl:
                logger.info(
                    f"pyslang: '{name}' matches clock substring in {module_name}"
                )
                return name

        # Strategy 4: last resort — first candidate
        name = candidates[0]
        logger.warning(
            f"pyslang: using first 1-bit input '{name}' as clock "
            f"for {module_name}"
        )
        return name

    except Exception as e:
        logger.debug(f"pyslang clock detection failed for '{module_name}': {e}")
        return None


_RESET_ACTIVE_LOW_PATTERNS = (
    'rst_n', 'rstn', 'reset_n', 'resetn', 'nreset', 'arst_n', 'rst_ni',
)
_RESET_ACTIVE_HIGH_PATTERNS = (
    'rst', 'reset', 'arst', 'srst',
)


def _detect_reset_from_rtl(
    sources: List[str],
    module_name: str,
    clock_name: str = None,
) -> Optional[tuple]:
    """
    Use pyslang AST analysis to detect the reset signal from RTL.

    Returns (reset_name, active_low: bool) or None if not found.

    Detection strategy:
      1. Walk all 1-bit input ports, exclude the known clock.
      2. Look for negedge references in always blocks (active-low resets).
      3. Name-pattern matching: *_n / *n variants → active-low, else active-high.
      4. Return the best candidate.
    """
    try:
        import pyslang
    except ImportError:
        return None

    comp, _ = _slang_compile(sources)
    if comp is None:
        return None

    try:
        inst = _slang_find_instance(comp, module_name)
        if inst is None:
            return None

        # Collect 1-bit input ports, excluding clock
        candidates: List[str] = []
        for member in inst.body:
            if member.kind == pyslang.ast.SymbolKind.Port:
                if member.direction != pyslang.ast.ArgumentDirection.In:
                    continue
                if member.internalSymbol.type.bitWidth != 1:
                    continue
                if member.name == clock_name:
                    continue
                candidates.append(member.name)

        if not candidates:
            return None

        # Strategy 1: look for negedge signals in always blocks → active-low
        negedge_sigs: List[str] = []
        for member in inst.body:
            if member.kind != pyslang.ast.SymbolKind.ProceduralBlock:
                continue
            body = member.body
            if body.kind != pyslang.ast.StatementKind.Timed:
                continue
            tc = body.timing
            if tc.kind == pyslang.ast.TimingControlKind.SignalEvent:
                if tc.edge == pyslang.ast.EdgeKind.NegEdge:
                    sym = tc.expr.getSymbolReference()
                    if sym is not None and sym.name not in negedge_sigs:
                        negedge_sigs.append(sym.name)
            elif tc.kind == pyslang.ast.TimingControlKind.EventList:
                for event in tc.events:
                    if event.edge == pyslang.ast.EdgeKind.NegEdge:
                        sym = event.expr.getSymbolReference()
                        if sym is not None and sym.name not in negedge_sigs:
                            negedge_sigs.append(sym.name)

        # Negedge candidates that are 1-bit inputs (not the clock) → active-low
        negedge_resets = [s for s in negedge_sigs if s in candidates]
        if negedge_resets:
            name = negedge_resets[0]
            logger.info(
                f"pyslang: '{name}' detected as active-low reset "
                f"via negedge analysis in {module_name}"
            )
            return name, True

        # Strategy 2: name-pattern matching
        for name in candidates:
            nl = name.lower()
            if nl in _RESET_ACTIVE_LOW_PATTERNS or nl.endswith('_n') or nl.endswith('n'):
                logger.info(
                    f"pyslang: '{name}' matches active-low reset pattern in {module_name}"
                )
                return name, True

        for name in candidates:
            nl = name.lower()
            if nl in _RESET_ACTIVE_HIGH_PATTERNS or 'rst' in nl or 'reset' in nl:
                logger.info(
                    f"pyslang: '{name}' matches active-high reset pattern in {module_name}"
                )
                return name, False

        # Strategy 3: first remaining 1-bit input after clock
        name = candidates[0]
        logger.warning(
            f"pyslang: guessing '{name}' as reset for {module_name} "
            f"(no pattern match)"
        )
        return name, True  # assume active-low by convention

    except Exception as e:
        logger.debug(f"pyslang reset detection failed for '{module_name}': {e}")
        return None


def _validate_boundary_with_pyslang(
    boundary: PartitionBoundaryDef,
    rm_sources: List[str],
    rm_design: str,
) -> PartitionBoundaryDef:
    """
    Validate (and auto-correct) boundary port widths against actual RTL using pyslang.

    Parses the RM module's SystemVerilog sources and compares each boundary port's
    configured width against the RTL-declared width. Mismatches are logged as
    warnings and auto-corrected to the RTL truth.
    """
    rtl_ports = _pyslang_parse_module(rm_sources, rm_design)
    if rtl_ports is None:
        return boundary

    corrected_ports = []
    for port in boundary.ports:
        if port.name in rtl_ports:
            rtl_width = rtl_ports[port.name]['width']
            if port.width != rtl_width:
                logger.warning(
                    f"Boundary port '{port.name}' width mismatch: "
                    f"config={port.width}, RTL={rtl_width} — "
                    f"using RTL width ({rm_design})"
                )
                corrected_ports.append(BoundaryPort(
                    name=port.name,
                    width=rtl_width,
                    direction=port.direction,
                    clock=port.clock,
                ))
            else:
                corrected_ports.append(port)
        else:
            logger.warning(
                f"Boundary port '{port.name}' not found in RTL module '{rm_design}' "
                f"— keeping config width={port.width}"
            )
            corrected_ports.append(port)

    logger.info(
        f"pyslang validated {len(rtl_ports)} ports for '{rm_design}' "
        f"(partition '{boundary.partition_name}')"
    )

    return PartitionBoundaryDef(
        partition_name=boundary.partition_name,
        rm_module_name=boundary.rm_module_name,
        ports=corrected_ports,
        clock_names=boundary.clock_names,
        reset_name=boundary.reset_name,
        reset_polarity=boundary.reset_polarity,
    )


class VerilatorBuilder:
    """
    Orchestrates building the multi-binary DPI simulation.

    Produces N+1 binaries:
    - static_binary: drives the static region model + coordinates barriers
    - rm/{name}/rm_binary: one per RM variant, each drives one RM model
    """

    def __init__(
        self,
        build_dir: str = 'build/pr',
        trace: bool = False,
        trace_type: str = 'vcd',
    ):
        self.build_dir = Path(build_dir)
        self.trace = trace
        self.trace_type = trace_type

        # Registered modules
        self._static_design: Optional[str] = None
        self._static_reset_name: Optional[str] = None
        self._static_reset_active_low: bool = True
        self._static_sources: List[str] = []
        self._static_include_dirs: List[str] = []
        self._static_ports: List[Dict[str, Any]] = []
        self._static_clock_name: str = 'clk'

        self._partitions: List[PartitionInfo] = []
        self._partition_boundaries: Dict[str, PartitionBoundaryDef] = {}

        self._rm_modules: Dict[str, ModuleBuildInfo] = {}  # rm_name -> build info
        self._rm_partition_map: Dict[str, str] = {}  # rm_name -> partition_name

        self._bridge_gen = DpiBridgeGenerator(build_dir=str(self.build_dir))
        self._cpp_gen = DpiCppGenerator(build_dir=str(self.build_dir))
        self._make_gen = MakefileGenerator(build_dir=str(self.build_dir))
        self._cocotb_gen = CocotbGenerator(build_dir=str(self.build_dir))

        # Populated after build
        self._binary_paths: Dict[str, Path] = {}
        self._cocotb_files: Dict[str, Path] = {}  # populated in cocotb_mode

    def set_static_region(
        self,
        design_name: str,
        sources: List[str],
        ports: List[Dict[str, Any]] = None,
        include_dirs: List[str] = None,
        clock_name: str = 'clk',
        reset_name: str = None,
        reset_active_low: bool = True,
    ):
        """
        Register the static region module.

        Parameters
        ----------
        design_name : str
            Top-level module name for the static region.
        sources : list of str
            RTL source files.
        ports : list of dict
            Port definitions [{name, width, direction}, ...].
            direction: 'input' or 'output'.
        include_dirs : list of str
            Verilog include directories.
        clock_name : str
            Clock signal name (default: 'clk').
        """
        self._static_design = design_name
        self._static_sources = [str(Path(s).resolve()) for s in sources]
        self._static_ports = ports or []
        self._static_include_dirs = include_dirs or []
        self._static_clock_name = clock_name
        self._static_reset_name = reset_name
        self._static_reset_active_low = reset_active_low

    def add_partition(
        self,
        name: str,
        index: int,
        rm_module_name: str,
        clock_name: str = 'clk',
        clock_names: List[str] = None,
        to_rm_ports: List[Dict[str, Any]] = None,
        from_rm_ports: List[Dict[str, Any]] = None,
        rm_variants: List[Dict[str, Any]] = None,
        initial_rm_index: int = 0,
        reset_name: str = None,
        reset_polarity: str = 'negative',
        reset_cycles: int = 10,
        reset_behavior: str = 'fresh',
    ):
        """
        Register a partition with its boundary ports and RM variants.

        Parameters
        ----------
        name : str
            Partition name.
        index : int
            0-based partition index.
        rm_module_name : str
            Module name of the RM in the static region.
        clock_name : str
            Primary clock signal name (backward compat).
        clock_names : list of str, optional
            All clock names. Supersedes clock_name if provided.
        to_rm_ports : list of dict
            Ports going from static to RM [{name, width}, ...].
        from_rm_ports : list of dict
            Ports going from RM to static [{name, width}, ...].
        rm_variants : list of dict
            RM variants [{name, design, wrapper_name, index, sources, include_dirs}, ...].
        initial_rm_index : int
            Index of the initial RM to load.
        reset_name : str, optional
            Reset signal name (e.g. 'rst_n'). None = no reset port.
        reset_polarity : str
            'negative' (active-low) or 'positive' (active-high).
        reset_cycles : int
            Number of clock cycles to hold reset before rm_ready.
        reset_behavior : str
            'fresh', 'gsr_xilinx', or 'none_intel'.
        """
        to_rm_ports = to_rm_ports or []
        from_rm_ports = from_rm_ports or []
        rm_variants = rm_variants or []
        effective_clocks = clock_names if clock_names is not None else [clock_name]

        part_info = PartitionInfo(
            name=name,
            index=index,
            rm_module_name=rm_module_name,
            clock_names=effective_clocks,
            to_rm_ports=to_rm_ports,
            from_rm_ports=from_rm_ports,
            rm_variants=rm_variants,
            initial_rm_index=initial_rm_index,
            reset_name=reset_name,
            reset_polarity=reset_polarity,
            reset_cycles=reset_cycles,
            reset_behavior=reset_behavior,
        )
        self._partitions.append(part_info)

        # Build boundary definition for bridge generation
        boundary_ports = []
        for p in to_rm_ports:
            boundary_ports.append(BoundaryPort(
                name=p['name'], width=p['width'], direction='to_rm',
                clock=p.get('clock'),
            ))
        for p in from_rm_ports:
            boundary_ports.append(BoundaryPort(
                name=p['name'], width=p['width'], direction='from_rm',
                clock=p.get('clock'),
            ))

        self._partition_boundaries[name] = PartitionBoundaryDef(
            partition_name=name,
            rm_module_name=rm_module_name,
            ports=boundary_ports,
            clock_names=effective_clocks,
            reset_name=reset_name,
            reset_polarity=reset_polarity,
        )

        # Track RM->partition mapping
        for rm in rm_variants:
            self._rm_partition_map[rm['name']] = name

    def build(self, cocotb_mode: bool = False) -> Dict[str, Path]:
        """
        Execute the full build pipeline.

        1. Generate DPI bridges (SV) for each partition
        2. Generate DPI C++ code (multi-binary architecture)
        3. Generate cocotb wrapper files (if cocotb_mode)
        4. Generate Makefile (rm_only in cocotb_mode)
        5. Run make to verilate, compile, and link

        Parameters
        ----------
        cocotb_mode : bool
            When True, skip static binary build. Generate cocotb wrapper
            files (pr_cocotb_top.sv, pr_cocotb_barrier.cpp) instead.
            cocotb handles static region compilation.

        Returns
        -------
        dict
            Binary paths: {'static': Path, 'rm/{name}': Path, ...}
            In cocotb_mode, 'static' key is absent.
        """
        if self._static_design is None:
            raise RuntimeError("No static region registered. Call set_static_region() first.")

        mode_str = " (cocotb mode)" if cocotb_mode else ""
        logger.info(f"=== Build Pipeline Starting{mode_str} ===")

        # Step 1: Generate DPI bridges and wrappers
        logger.info("Step 1: Generating DPI bridges and wrappers...")
        self._generate_bridges()

        # Step 2: Generate DPI C++ code
        logger.info("Step 2: Generating DPI C++ code...")
        static_info = StaticInfo(
            design_name=self._static_design,
            ports=self._static_ports,
            clock_name=self._static_clock_name,
            reset_name=self._static_reset_name,
            reset_active_low=self._static_reset_active_low,
        )
        self._cpp_gen.generate_all(
            partitions=self._partitions,
            static_info=static_info,
            trace=self.trace,
            trace_type=self.trace_type,
        )

        # Step 2b: Generate cocotb integration files (if cocotb_mode)
        if cocotb_mode:
            logger.info("Step 2b: Generating cocotb integration files...")
            self._cocotb_files = self._cocotb_gen.generate_all(
                partitions=self._partitions,
                static_info=static_info,
            )

        # Step 3: Generate Makefile (rm_only in cocotb_mode)
        logger.info("Step 3: Generating Makefile...")
        self._generate_makefile(rm_only=cocotb_mode)

        # Step 4: Run make (only RM binaries if cocotb_mode)
        if self._partitions:
            logger.info("Step 4: Running make...")
            self._run_make()
        else:
            logger.info("Step 4: No partitions to build, skipping make")

        # Collect binary paths
        self._binary_paths = {}
        if not cocotb_mode:
            self._binary_paths['static'] = self.build_dir / 'static_binary'
        for part_info in self._partitions:
            for rm in part_info.rm_variants:
                rm_name = rm['name']
                self._binary_paths[f"rm/{rm_name}"] = (
                    self.build_dir / 'rm' / rm_name / 'rm_binary'
                )

        logger.info(f"=== Build Complete: {len(self._binary_paths)} binaries ===")
        for key, path in self._binary_paths.items():
            logger.info(f"  {key}: {path}")
        return dict(self._binary_paths)

    @property
    def binary_paths(self) -> Dict[str, Path]:
        """Get built binary paths (available after build())."""
        return dict(self._binary_paths)

    @property
    def static_binary_path(self) -> Optional[Path]:
        """Get path to the static binary."""
        return self._binary_paths.get('static')

    def get_rm_binary_path(self, rm_name: str) -> Optional[Path]:
        """Get path to a specific RM binary."""
        return self._binary_paths.get(f"rm/{rm_name}")

    @property
    def cocotb_files(self) -> Dict[str, Path]:
        """Get cocotb integration file paths (available after cocotb_mode build)."""
        return dict(self._cocotb_files)

    def _generate_bridges(self):
        """Generate DPI bridge SV files and register RM module build info."""
        for part_info in self._partitions:
            boundary = self._partition_boundaries[part_info.name]

            # Validate boundary port widths against actual RTL using pyslang.
            # This catches config/RTL mismatches (e.g. width: 32 in YAML
            # but 1-bit in RTL) before they become cryptic Verilator errors.
            if part_info.rm_variants:
                first_rm = part_info.rm_variants[0]
                rm_sources = first_rm.get('sources', [])
                rm_design = first_rm.get('design', '')
                if rm_sources and rm_design:
                    boundary = _validate_boundary_with_pyslang(
                        boundary, rm_sources, rm_design
                    )
                    self._partition_boundaries[part_info.name] = boundary
                    # Update PartitionInfo port widths to match validated boundary
                    for bp in boundary.ports:
                        if bp.direction == 'to_rm':
                            for p in part_info.to_rm_ports:
                                if p['name'] == bp.name:
                                    p['width'] = bp.width
                        else:
                            for p in part_info.from_rm_ports:
                                if p['name'] == bp.name:
                                    p['width'] = bp.width

            # Static-side bridge (replaces RM in static region)
            bridge_path = self._bridge_gen.generate_static_side_bridge(boundary)
            self._static_sources.append(str(bridge_path))

            # RM-side wrappers (one per RM variant)
            for rm in part_info.rm_variants:
                wrapper_path = self._bridge_gen.generate_rm_side_wrapper(
                    boundary, rm['design'], parameters=rm.get('parameters', {})
                )

                rm_sources = rm.get('sources', [])
                rm_sources = [str(Path(s).resolve()) for s in rm_sources]

                self._rm_modules[rm['name']] = ModuleBuildInfo(
                    name=rm['wrapper_name'],
                    top_module=rm['wrapper_name'],
                    sources=[str(wrapper_path)] + rm_sources,
                    include_dirs=rm.get('include_dirs', []),
                    obj_dir_prefix=f"rm/{rm['name']}/",
                )

    def _generate_makefile(self, rm_only: bool = False):
        """Generate the multi-binary Makefile."""
        # Static module build info
        static_module = ModuleBuildInfo(
            name='static',
            top_module=self._static_design,
            sources=self._static_sources,
            include_dirs=self._static_include_dirs,
            obj_dir_prefix='static/',
        )

        dpi_dir = self.build_dir / 'dpi'

        # Static-side DPI C++ files: dpi_static_*.cpp
        static_dpi_cpp_files = [
            str(p) for p in sorted(dpi_dir.glob('dpi_static_*.cpp'))
        ]

        # Static driver
        static_driver_cpp = str(dpi_dir / 'static_driver.cpp')

        # RM binary infos
        rm_binaries = []
        for part_info in self._partitions:
            for rm in part_info.rm_variants:
                rm_name = rm['name']
                rm_binaries.append(RmBinaryInfo(
                    name=rm_name,
                    module=self._rm_modules[rm_name],
                    partition_name=part_info.name,
                    driver_cpp=str(dpi_dir / f'rm_driver_{rm_name}.cpp'),
                    dpi_rm_cpp=str(dpi_dir / f'dpi_rm_{part_info.name}.cpp'),
                ))

        self._make_gen.generate(
            static_module=static_module,
            rm_binaries=rm_binaries,
            static_dpi_cpp_files=static_dpi_cpp_files,
            static_driver_cpp=static_driver_cpp,
            trace=self.trace,
            trace_type=self.trace_type,
            rm_only=rm_only,
        )

    def _run_make(self):
        """Run make to compile everything."""
        makefile_path = self.build_dir / 'Makefile'
        if not makefile_path.exists():
            raise RuntimeError(f"Makefile not found: {makefile_path}")

        # Bound make's parallelism. A bare `make -j` is unbounded: with many
        # RMs (e.g. the 24-RM video pipeline) it launches every Verilator +
        # g++ compile at once — each ~0.4 GB — and can spike to >10 GB RAM.
        # Cap to the CPU count by default; PR_BUILD_JOBS overrides.
        jobs = os.environ.get('PR_BUILD_JOBS')
        if jobs is None:
            jobs = str(os.cpu_count() or 4)
        logger.info(f"Running make with -j{jobs}")

        result = subprocess.run(
            ['make', f'-j{jobs}', '-f', str(makefile_path), 'all'],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Make failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
            raise RuntimeError(
                f"Build failed (make returned {result.returncode}):\n{result.stderr}"
            )

        logger.info("Make completed successfully")
