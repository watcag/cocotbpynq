"""
Cocotb Integration Code Generator.

Generates files needed for cocotb to host the static region while RM binaries
run as separate processes communicating via shared memory and barriers:

1. pr_cocotb_top.sv — Wrapper module that cocotb sees as DUT. Contains a
   negedge DPI barrier call and instantiates the user's static region.

2. pr_cocotb_barrier.cpp — DPI C++ library (no main()). Implements the
   collapsed 3-phase barrier protocol in a single negedge DPI call,
   plus swap_channels() and process_commands().
"""
from typing import List, Dict, Any
from pathlib import Path
import logging

from .dpi_cpp_generator import PartitionInfo, StaticInfo, _num_chunks, _total_slots, _slot_offsets, _create_env

logger = logging.getLogger(__name__)


class CocotbGenerator:
    """Generates cocotb integration files for the PR simulation."""

    def __init__(self, build_dir: str):
        self.build_dir = Path(build_dir)
        self.dpi_dir = self.build_dir / 'dpi'
        self.bridges_dir = self.build_dir / 'bridges'
        self.dpi_dir.mkdir(parents=True, exist_ok=True)
        self.bridges_dir.mkdir(parents=True, exist_ok=True)
        self._env = _create_env()

    def generate_all(
        self,
        partitions: List[PartitionInfo],
        static_info: StaticInfo,
    ) -> Dict[str, Path]:
        top_sv = self.generate_cocotb_top_sv(partitions, static_info)
        barrier_cpp = self.generate_cocotb_barrier_cpp(partitions, static_info)
        return {
            'top_sv': top_sv,
            'barrier_cpp': barrier_cpp,
        }

    def generate_cocotb_top_sv(
        self,
        partitions: List[PartitionInfo],
        static_info: StaticInfo,
    ) -> Path:
        template = self._env.get_template('pr_cocotb_top.sv.j2')
        content = template.render(static_info=static_info)
        path = self.bridges_dir / "pr_cocotb_top.sv"
        path.write_text(content)
        logger.info(f"Generated: {path}")
        return path

    def generate_cocotb_barrier_cpp(
        self,
        partitions: List[PartitionInfo],
        static_info: StaticInfo,
    ) -> Path:
        template = self._env.get_template('pr_cocotb_barrier.cpp.j2')
        content = template.render(
            partitions=partitions,
            num_partitions=len(partitions),
        )
        path = self.dpi_dir / "pr_cocotb_barrier.cpp"
        path.write_text(content)
        logger.info(f"Generated: {path}")
        return path
