"""
DPI Bridge Generator for partition boundaries.

Generates two SystemVerilog modules per partition:
1. Static-side DPI bridge: Same port signature as the RM (drop-in replacement
   in the static region). Uses DPI-C function calls to read/write shared memory.
2. RM-side DPI wrapper: Wraps real RM with DPI channel I/O.

Width-aware: DPI types are selected based on actual port widths to avoid
Verilator WIDTHEXPAND/WIDTHTRUNC warnings. Ports are classified into
DPI type bands:
  - 1-32 bits  -> DPI `int`     (C++ `int`)
  - 33-64 bits -> DPI `longint` (C++ `long long`)
  - >64 bits   -> chunked into multiple 64-bit DPI calls
"""
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass, field
import logging

import jinja2

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / 'templates'


def num_chunks(width: int) -> int:
    """Number of 64-bit SHM slots needed for a port of the given width."""
    return (width + 63) // 64


@dataclass
class BoundaryPort:
    """A port on the partition boundary."""
    name: str
    width: int
    direction: str  # 'to_rm' or 'from_rm'
    clock: Optional[str] = None  # per-port clock override; None = use partition primary

    @property
    def num_chunks(self) -> int:
        return (self.width + 63) // 64


@dataclass
class PartitionBoundaryDef:
    """Definition of a partition boundary for DPI bridge generation."""
    partition_name: str
    rm_module_name: str
    ports: List[BoundaryPort]
    clock_names: List[str] = field(default_factory=lambda: ['clk'])
    reset_name: Optional[str] = None
    reset_polarity: str = 'negative'  # 'negative' (active-low) or 'positive'

    @property
    def clock_name(self) -> str:
        """Backward-compat: primary clock."""
        return self.clock_names[0]


def _dpi_type(width: int) -> str:
    """Select the DPI-C type for a chunk of the given bit width (max 64)."""
    if width <= 32:
        return 'int'
    else:
        return 'longint'


def _chunk_width(port_width: int, chunk_idx: int) -> int:
    """Return the effective bit width of a specific chunk."""
    lo = chunk_idx * 64
    hi = min(lo + 63, port_width - 1)
    return hi - lo + 1


def _sv_send_cast(port: BoundaryPort, chunk_idx: int = 0) -> str:
    """
    Generate the SV expression that widens a port value to the DPI type width.

    For exact-width matches (32 or 64), no cast needed.
    For narrower signals, zero-extend to the DPI type width.
    For wide ports (>64), extract the appropriate chunk slice.
    """
    lo = chunk_idx * 64
    hi = min(lo + 63, port.width - 1)
    cw = hi - lo + 1
    dpi = _dpi_type(cw)

    if port.width > 64:
        src = f"{port.name}[{hi}:{lo}]"
    elif port.width > 1 and cw < port.width:
        src = f"{port.name}[{hi}:{lo}]"
    else:
        src = port.name

    if dpi == 'int':
        if cw == 32:
            return src
        pad = 32 - cw
        return f"int'({{{pad}'d0, {src}}})"
    else:  # longint
        if cw == 64:
            return src
        pad = 64 - cw
        return f"longint'({{{pad}'d0, {src}}})"


def _sv_recv_trunc(port: BoundaryPort, expr: str, chunk_idx: int = 0):
    """
    Generate the SV expression that truncates a DPI return value to port width.

    For wide ports (>64), returns (lhs_slice, rhs_expr) tuple.
    For narrow ports, returns the expression string.
    """
    lo = chunk_idx * 64
    hi = min(lo + 63, port.width - 1)
    cw = hi - lo + 1

    if port.width > 64:
        trunc = expr if cw in (32, 64) else f"{expr}[{cw - 1}:0]"
        return (f"{port.name}[{hi}:{lo}]", trunc)
    else:
        dpi = _dpi_type(port.width)
        if dpi == 'int' and port.width == 32:
            return expr
        if dpi == 'longint' and port.width == 64:
            return expr
        return f"{expr}[{port.width - 1}:0]"


def _group_by_clock(ports: List[BoundaryPort], default_clock: str) -> Dict[str, List[BoundaryPort]]:
    """Group ports by their effective clock."""
    groups = {}
    for p in ports:
        clk = p.clock or default_clock
        groups.setdefault(clk, []).append(p)
    return groups


def _create_bridge_env() -> jinja2.Environment:
    """Create Jinja2 environment with bridge-specific globals."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
        extensions=['jinja2.ext.do'],
    )
    env.globals['sv_send_cast'] = _sv_send_cast
    env.globals['sv_recv_trunc'] = _sv_recv_trunc
    env.globals['dpi_type'] = _dpi_type
    env.globals['chunk_width'] = _chunk_width
    return env


class DpiBridgeGenerator:
    """
    Generates DPI-based bridge modules for partition boundaries.

    For each partition, generates:
    1. Static-side bridge: same module name as RM, uses DPI-C send/recv
    2. RM-side DPI wrapper: wraps real RM, uses DPI-C send/recv
    """

    def __init__(self, build_dir: str = None):
        self.build_dir = Path(build_dir) if build_dir else Path('build/pr')
        self.bridges_dir = self.build_dir / 'bridges'
        self.wrappers_dir = self.build_dir / 'wrappers'
        self.bridges_dir.mkdir(parents=True, exist_ok=True)
        self.wrappers_dir.mkdir(parents=True, exist_ok=True)
        self._env = _create_bridge_env()

    def generate_static_side_bridge(self, boundary: PartitionBoundaryDef) -> Path:
        """Generate the static-side DPI bridge (drop-in replacement for RM)."""
        to_rm = [p for p in boundary.ports if p.direction == 'to_rm']
        from_rm = [p for p in boundary.ports if p.direction == 'from_rm']
        default_clk = boundary.clock_names[0]

        template = self._env.get_template('dpi_static_bridge.sv.j2')
        content = template.render(
            part=boundary.partition_name,
            module_name=boundary.rm_module_name,
            clock_names=boundary.clock_names,
            reset_name=boundary.reset_name,
            ports=boundary.ports,
            to_rm=to_rm,
            from_rm=from_rm,
            to_rm_by_clock=_group_by_clock(to_rm, default_clk),
            from_rm_by_clock=_group_by_clock(from_rm, default_clk),
        )

        output_path = self.bridges_dir / f"{boundary.rm_module_name}.sv"
        output_path.write_text(content)
        logger.info(f"Generated static-side DPI bridge: {output_path}")
        return output_path

    def generate_rm_side_wrapper(
        self,
        boundary: PartitionBoundaryDef,
        rm_design_name: str,
        parameters: dict = None,
    ) -> Path:
        """Generate the RM-side DPI wrapper (wraps real RM with DPI channels)."""
        to_rm = [p for p in boundary.ports if p.direction == 'to_rm']
        from_rm = [p for p in boundary.ports if p.direction == 'from_rm']
        # Use unique wrapper name when parameters are provided to avoid
        # collisions between RM variants sharing the same design module.
        if parameters:
            safe_params = "_".join(f"{k}{v}" for k, v in parameters.items())
            wrapper_name = f"{rm_design_name}_{safe_params}_dpi_wrapper"
        else:
            wrapper_name = f"{rm_design_name}_dpi_wrapper"
        default_clk = boundary.clock_names[0]

        template = self._env.get_template('dpi_rm_wrapper.sv.j2')
        content = template.render(
            part=boundary.partition_name,
            rm_design_name=rm_design_name,
            wrapper_name=wrapper_name,
            clock_names=boundary.clock_names,
            reset_name=boundary.reset_name,
            to_rm=to_rm,
            from_rm=from_rm,
            to_rm_by_clock=_group_by_clock(to_rm, default_clk),
            from_rm_by_clock=_group_by_clock(from_rm, default_clk),
            parameters=parameters or {},
        )

        output_path = self.wrappers_dir / f"{wrapper_name}.sv"
        output_path.write_text(content)
        logger.info(f"Generated RM-side DPI wrapper: {output_path}")
        return output_path

    def generate_both(
        self,
        boundary: PartitionBoundaryDef,
        rm_design_name: str,
    ) -> tuple:
        """Generate both static-side bridge and RM-side wrapper."""
        bridge_path = self.generate_static_side_bridge(boundary)
        wrapper_path = self.generate_rm_side_wrapper(boundary, rm_design_name)
        return bridge_path, wrapper_path
