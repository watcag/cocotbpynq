"""
Makefile Generator for multi-binary DPI-based Verilator simulation.

Generates a Makefile that:
1. Verilates each module separately into .a library archives
2. Compiles DPI C++ sources (separate for static-side and RM-side)
3. Links a static_binary and per-RM rm_binary executables
"""
from typing import List, Dict, Any
from pathlib import Path
from dataclasses import dataclass, field
import logging

from .dpi_cpp_generator import _create_env

logger = logging.getLogger(__name__)


@dataclass
class ModuleBuildInfo:
    """Build info for a single Verilator module."""
    name: str  # Module name (used for obj_dir naming)
    top_module: str  # Top-level module name for verilator
    sources: List[str]  # List of RTL source file paths
    include_dirs: List[str] = field(default_factory=list)
    verilator_flags: List[str] = field(default_factory=list)
    obj_dir_prefix: str = ''  # 'static/', 'rm/counter_rm/', etc.
    verilator_public: bool = True  # RMs only: --public-flat-rw (off for large netlists: it blocks inlining)


@dataclass
class RmBinaryInfo:
    """Build info for one RM binary."""
    name: str  # RM variant name (e.g. 'counter_rm')
    module: ModuleBuildInfo  # The RM's Verilator module
    partition_name: str  # Which partition this RM belongs to
    driver_cpp: str  # Path to rm_driver_{name}.cpp
    dpi_rm_cpp: str  # Path to dpi_rm_{partition}.cpp


class MakefileGenerator:
    """Generates Makefile for building multi-binary DPI simulation."""

    def __init__(self, build_dir: str):
        self.build_dir = Path(build_dir)
        self.dpi_dir = self.build_dir / 'dpi'
        self._env = _create_env()
        # Add custom filter for basename_stem
        self._env.filters['basename_stem'] = lambda p: Path(p).stem

    def generate(
        self,
        static_module: ModuleBuildInfo,
        rm_binaries: List[RmBinaryInfo],
        static_dpi_cpp_files: List[str],
        static_driver_cpp: str,
        trace: bool = False,
        trace_type: str = 'vcd',
        extra_cflags: str = '',
        extra_ldflags: str = '',
        rm_only: bool = False,
    ) -> Path:
        # Compute trace cflags
        trace_cflags = ""
        if trace:
            trace_cflags = " -DVM_TRACE=1"
            if trace_type == 'fst':
                trace_cflags += " -DVM_TRACE_FST=1"

        # Verilator flags split into (prefix, suffix) around -Mdir OBJDIR.
        # Template: {{ verilator_common }} {{ obj_dir }} {{ verilator_trace }} --top-module ...
        verilator_common = "--cc -Mdir"
        verilator_trace = ""
        if trace:
            verilator_trace = "--trace-fst" if trace_type == 'fst' else "--trace"

        # Static module paths
        static_obj_dir = f"$(BUILD_DIR)/{static_module.obj_dir_prefix}obj_dir"
        static_lib = f"{static_obj_dir}/V{static_module.top_module}__ALL.a"
        static_vflags = ""
        if static_module.verilator_flags:
            static_vflags = " " + " ".join(static_module.verilator_flags)
        static_include_str = " ".join(f"-I{d}" for d in static_module.include_dirs)

        # Support objects
        support_objs = ["$(DPI_DIR)/verilated.o", "$(DPI_DIR)/verilated_threads.o"]
        if trace:
            trace_obj = f"$(DPI_DIR)/verilated_{'fst' if trace_type == 'fst' else 'vcd'}_c.o"
            support_objs.append(trace_obj)

        # Static binary objects
        static_driver_obj = "$(DPI_DIR)/static_driver.o"
        static_dpi_objs = [static_driver_obj]
        for cpp_file in static_dpi_cpp_files:
            obj_name = Path(cpp_file).stem + ".o"
            static_dpi_objs.append(f"$(DPI_DIR)/{obj_name}")
        static_all_objs = static_dpi_objs + support_objs

        # RM binary vars
        rm_binary_vars = [f"$(RM_BINARY_{rm.name.upper()})" for rm in rm_binaries]
        rm_lib_vars = [f"$(RM_LIB_{rm.name.upper()})" for rm in rm_binaries]

        # All binaries
        if rm_only:
            all_binaries = rm_binary_vars
        else:
            all_binaries = ["$(STATIC_BINARY)"] + rm_binary_vars

        # Platform shared-library extension + linker flags
        import platform
        if platform.system() == 'Darwin':
            shlib_ext = '.dylib'
            shlib_ldflags = ('-dynamiclib -Wl,-undefined,dynamic_lookup '
                             '-Wl,-install_name,@rpath/$(notdir $@)')
        else:
            shlib_ext = '.so'
            shlib_ldflags = '-shared'

        template = self._env.get_template('makefile.j2')
        content = template.render(
            build_dir=self.build_dir,
            dpi_dir=self.dpi_dir,
            static_module=static_module,
            rm_binaries=rm_binaries,
            trace=trace,
            trace_type=trace_type,
            trace_cflags=trace_cflags,
            extra_cflags=extra_cflags,
            extra_ldflags=extra_ldflags,
            rm_only=rm_only,
            verilator_common=verilator_common,
            verilator_trace=verilator_trace,
            static_obj_dir=static_obj_dir,
            static_lib=static_lib,
            static_vflags=static_vflags,
            static_include_str=static_include_str,
            support_objs=support_objs,
            static_driver_obj=static_driver_obj,
            static_driver_cpp=static_driver_cpp,
            static_dpi_cpp_files=static_dpi_cpp_files,
            static_all_objs=static_all_objs,
            all_binaries=all_binaries,
            all_rm_libs=rm_lib_vars,
            shlib_ext=shlib_ext,
            shlib_ldflags=shlib_ldflags,
        )

        output_path = self.build_dir / "Makefile"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        logger.info(f"Generated: {output_path}")
        return output_path
