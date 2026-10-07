"""
DPI C++ Code Generator for multi-binary simulation.

Generates C++ code for the multi-process simulation architecture:
- dpi_shm_channel.h: Shared memory channel layout structs
- barrier_sync.h: Sense-reversing atomic barrier for cross-process sync
- shm_mailbox.h: Python<->C++ shared memory command mailbox struct
- signal_access.h: Generated port->signal accessor functions
- static_driver.cpp: Static binary main driver (single-threaded)
- rm_driver_{variant}.cpp: Per-RM-variant driver (single-threaded)
- dpi_static_{partition}.cpp: Static-side DPI function implementations
- dpi_rm_{partition}.cpp: RM-side DPI function implementations
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field
import logging

import jinja2

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / 'templates'


@dataclass
class PartitionInfo:
    """Info about a partition for code generation."""
    name: str
    index: int  # 0-based partition index
    rm_module_name: str  # Default RM module name (for bridge)
    clock_names: List[str]  # All clocks for this partition
    to_rm_ports: List[Dict[str, Any]]  # [{name, width}, ...]
    from_rm_ports: List[Dict[str, Any]]
    rm_variants: List[Dict[str, Any]] = field(default_factory=list)
    # [{name, design, wrapper_name, index}, ...]
    initial_rm_index: int = 0
    reset_name: Optional[str] = None
    reset_polarity: str = 'negative'
    reset_cycles: int = 10
    reset_behavior: str = 'fresh'  # 'fresh', 'gsr_xilinx', 'none_intel'

    @property
    def clock_name(self) -> str:
        """Backward-compat: primary clock."""
        return self.clock_names[0]


@dataclass
class StaticInfo:
    """Info about the static region for code generation."""
    design_name: str
    ports: List[Dict[str, Any]]  # [{name, width, direction}, ...]
    # direction: 'input' or 'output'
    clock_name: str = 'clk'
    reset_name: str = None          # e.g. 'rst_n'; None = no reset port
    reset_active_low: bool = True   # True = ACTIVE_LOW


def _num_chunks(width: int) -> int:
    """Number of 64-bit SHM slots needed for a port of the given width."""
    return (width + 63) // 64


def _chunk_width(port_width: int, chunk_idx: int) -> int:
    """Return the effective bit width of a specific chunk."""
    lo = chunk_idx * 64
    hi = min(lo + 63, port_width - 1)
    return hi - lo + 1


def _slot_offsets(ports: List[Dict]) -> List[int]:
    """Return the starting slot index for each port in the list."""
    offsets, idx = [], 0
    for p in ports:
        offsets.append(idx)
        idx += _num_chunks(p.get('width', 32))
    return offsets


def _total_slots(ports: List[Dict]) -> int:
    """Total number of SHM slots for a port list."""
    return sum(_num_chunks(p.get('width', 32)) for p in ports)


def _cpp_type(width: int) -> str:
    """Select the C++ type that matches the DPI-C type for a given bit width (per-chunk)."""
    if width <= 32:
        return 'int'
    else:
        return 'long long'


def _cpp_unsigned_type(width: int) -> str:
    """Select the unsigned C++ storage type for a given bit width (per-chunk)."""
    if width <= 32:
        return 'uint32_t'
    else:
        return 'uint64_t'


def _mask_expr(width: int) -> str:
    """Generate a C++ mask expression for the given bit width, or empty if full-width."""
    if width == 32 or width == 64 or width > 64:
        return ''
    if width < 32:
        mask = (1 << width) - 1
        return f" & 0x{mask:X}u"
    # 33-63 bits
    mask = (1 << width) - 1
    return f" & 0x{mask:X}ull"


def _create_env():
    """Create Jinja2 environment with template directory and custom globals."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
        extensions=['jinja2.ext.do'],
    )
    env.globals['num_chunks'] = _num_chunks
    env.globals['cpp_unsigned_type'] = _cpp_unsigned_type
    return env


class DpiCppGenerator:
    """Generates all C++ source files for the multi-binary DPI simulation."""

    def __init__(self, build_dir: str):
        self.build_dir = Path(build_dir)
        self.dpi_dir = self.build_dir / 'dpi'
        self.dpi_dir.mkdir(parents=True, exist_ok=True)
        self._env = _create_env()

    def generate_all(
        self,
        partitions: List[PartitionInfo],
        static_info: StaticInfo,
        trace: bool = False,
        trace_type: str = 'vcd',
    ):
        """Generate all C++ files for the multi-binary architecture."""
        self.generate_dpi_shm_channel_h(partitions)
        self.generate_barrier_sync_h()
        self.generate_shm_mailbox_h()
        self.generate_signal_access_h(partitions, static_info)
        self.generate_static_driver_cpp(partitions, static_info, trace, trace_type)
        for part in partitions:
            self.generate_dpi_static_partition_cpp(part)
            self.generate_dpi_rm_partition_cpp(part)
        for part in partitions:
            for rm in part.rm_variants:
                self.generate_rm_driver_cpp(part, rm, trace, trace_type)
                if rm.get('simulator', 'verilator') == 'xsim':
                    self.generate_rm_driver_xsim_cpp(part, rm)

    def generate_rm_driver_xsim_cpp(self, part: PartitionInfo, rm: Dict[str, Any]):
        """Driver of an RM simulated by the Vivado simulator (XSI), and its DPI library's channel pointers."""
        assert_val = deassert_val = None
        if part.reset_name is not None and part.reset_behavior != 'none_intel':
            assert_val = 0 if part.reset_polarity == 'negative' else 1
            deassert_val = 1 - assert_val
        self._render('rm_driver_xsim.cpp.j2', self.dpi_dir / f"rm_driver_xsim_{rm['name']}.cpp",
                     part=part, variant_name=rm['name'], rm_dir=str((self.build_dir / 'rm' / rm['name']).resolve()),
                     assert_val=assert_val, deassert_val=deassert_val)
        (self.dpi_dir / 'xsim_rm_globals.cpp').write_text(
            '// Channel pointers of the DPI library of an xsim RM (set by rm_driver_xsim_*.cpp)\n'
            '#include "dpi_shm_channel.h"\n'
            'void* g_channel_base = nullptr;\nShmPartitionHeader* g_channel_header = nullptr;\n')

    def _render(self, template_name: str, output_path: Path, **kwargs):
        """Render a template and write to output_path."""
        template = self._env.get_template(template_name)
        content = template.render(**kwargs)
        output_path.write_text(content)
        logger.info(f"Generated: {output_path}")

    def generate_dpi_shm_channel_h(self, partitions: List[PartitionInfo]):
        self._render('dpi_shm_channel.h.j2', self.dpi_dir / "dpi_shm_channel.h")

    def generate_barrier_sync_h(self):
        self._render('barrier_sync.h.j2', self.dpi_dir / "barrier_sync.h")

    def generate_shm_mailbox_h(self):
        self._render('shm_mailbox.h.j2', self.dpi_dir / "shm_mailbox.h")

    def generate_signal_access_h(self, partitions: List[PartitionInfo], static_info: StaticInfo):
        self._render('signal_access.h.j2', self.dpi_dir / "signal_access.h",
                     partitions=partitions, static_info=static_info)

    def generate_static_driver_cpp(
        self,
        partitions: List[PartitionInfo],
        static_info: StaticInfo,
        trace: bool = False,
        trace_type: str = 'vcd',
    ):
        self._render('static_driver.cpp.j2', self.dpi_dir / "static_driver.cpp",
                     partitions=partitions, static_info=static_info,
                     num_partitions=len(partitions), trace=trace, trace_type=trace_type)

    def generate_rm_driver_cpp(
        self,
        part: PartitionInfo,
        rm: Dict[str, Any],
        trace: bool = False,
        trace_type: str = 'vcd',
    ):
        model_type = f"V{rm['wrapper_name']}"
        variant_name = rm['name']

        assert_val = None
        deassert_val = None
        if part.reset_name is not None and part.reset_behavior != 'none_intel':
            assert_val = 0 if part.reset_polarity == 'negative' else 1
            deassert_val = 1 if part.reset_polarity == 'negative' else 0

        self._render('rm_driver.cpp.j2', self.dpi_dir / f"rm_driver_{variant_name}.cpp",
                     part=part, model_type=model_type, variant_name=variant_name,
                     trace=trace, trace_type=trace_type,
                     assert_val=assert_val, deassert_val=deassert_val)

        # Also emit the dlopen-variant shared-library entry point. This file
        # exposes rm_init/rm_run/rm_destroy as C ABI for benchmark E7 and any
        # future host that swaps RMs via dlopen instead of fork+exec.
        self._render('rm_lib.cpp.j2', self.dpi_dir / f"rm_lib_{variant_name}.cpp",
                     part=part, model_type=model_type, variant_name=variant_name,
                     assert_val=assert_val, deassert_val=deassert_val)

    def generate_dpi_static_partition_cpp(self, part: PartitionInfo):
        num_to_rm_slots = _total_slots(part.to_rm_ports)

        to_rm_slots = []
        slot = 0
        for port in part.to_rm_ports:
            w = port.get('width', 32)
            nc = _num_chunks(w)
            for c in range(nc):
                cw = _chunk_width(w, c)
                suffix = f"_chunk{c}_send" if nc > 1 else "_send"
                to_rm_slots.append({
                    'fname': f"dpi_static_{part.name}_{port['name']}{suffix}",
                    'cpp_type': _cpp_type(cw),
                    'slot': slot,
                    'mask': _mask_expr(cw),
                })
                slot += 1

        from_rm_slots = []
        from_slot = 0
        for port in part.from_rm_ports:
            w = port.get('width', 32)
            nc = _num_chunks(w)
            for c in range(nc):
                cw = _chunk_width(w, c)
                suffix_d = f"_chunk{c}_recv_data" if nc > 1 else "_recv_data"
                suffix_v = f"_chunk{c}_recv_valid" if nc > 1 else "_recv_valid"
                ch_expr = f"shm_from_rm_inbox(g_partition_bases[{part.index}], {num_to_rm_slots}, {from_slot})"
                from_rm_slots.append({
                    'fname_data': f"dpi_static_{part.name}_{port['name']}{suffix_d}",
                    'fname_valid': f"dpi_static_{part.name}_{port['name']}{suffix_v}",
                    'cpp_type': _cpp_type(cw),
                    'ch_expr': ch_expr,
                    'mask': _mask_expr(cw),
                })
                from_slot += 1

        self._render('dpi_static_partition.cpp.j2', self.dpi_dir / f"dpi_static_{part.name}.cpp",
                     part=part, to_rm_slots=to_rm_slots, from_rm_slots=from_rm_slots)

    def generate_dpi_rm_partition_cpp(self, part: PartitionInfo):
        to_rm_slots = []
        slot = 0
        for port in part.to_rm_ports:
            w = port.get('width', 32)
            nc = _num_chunks(w)
            for c in range(nc):
                cw = _chunk_width(w, c)
                suffix_d = f"_chunk{c}_recv_data" if nc > 1 else "_recv_data"
                suffix_v = f"_chunk{c}_recv_valid" if nc > 1 else "_recv_valid"
                to_rm_slots.append({
                    'fname_data': f"dpi_rm_{part.name}_{port['name']}{suffix_d}",
                    'fname_valid': f"dpi_rm_{part.name}_{port['name']}{suffix_v}",
                    'cpp_type': _cpp_type(cw),
                    'inbox_expr': f"shm_to_rm_inbox(g_channel_base, {slot})",
                    'ovr_expr': f"shm_to_rm_override(g_channel_base, {slot})",
                    'mask': _mask_expr(cw),
                })
                slot += 1

        from_rm_slots = []
        from_slot = 0
        for port in part.from_rm_ports:
            w = port.get('width', 32)
            nc = _num_chunks(w)
            for c in range(nc):
                cw = _chunk_width(w, c)
                suffix = f"_chunk{c}_send" if nc > 1 else "_send"
                ch_expr = f"shm_from_rm_outbox(g_channel_base, g_channel_header->num_to_rm, {from_slot})"
                from_rm_slots.append({
                    'fname': f"dpi_rm_{part.name}_{port['name']}{suffix}",
                    'cpp_type': _cpp_type(cw),
                    'ch_expr': ch_expr,
                    'mask': _mask_expr(cw),
                })
                from_slot += 1

        self._render('dpi_rm_partition.cpp.j2', self.dpi_dir / f"dpi_rm_{part.name}.cpp",
                     part=part, to_rm_slots=to_rm_slots, from_rm_slots=from_rm_slots)
