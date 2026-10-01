"""
Waveform merger for cocotbpynq PR simulation.

In a PR simulation, the static region dumps a VCD from cocotb's Verilator
process while each RM binary dumps its own VCD in a separate process. These
are cycle-aligned via the sense-reversing barrier but land in different
files under different module scopes.

This module merges them into a single unified VCD with:
    top/
      static/           ← signals from cocotb's static region trace
      rm/
        {partition}/
          {rm_variant}/
            {pid}/      ← one scope per RM process (reconfigure creates new pids)

The merged timebase uses the longest trace's max_index as the end point and
cycles in each sub-trace align naturally because all RM processes advance one
cycle per barrier and the static process advances one cycle per cocotb clock.

This module runs under Python 3.14 (for ewal) via an isolated `uv run
--no-project` subprocess — cocotbpynq itself stays on 3.13.  The __main__
entry point is what PRCocotbRunner spawns.

Usage (programmatic, from a 3.14 env):
    from cocotbpynq.pr.waveform_merger import merge_waveforms
    merge_waveforms(
        static_vcd='dump.vcd',
        rm_vcds=[('rp_add', 'add_5', 12345, 'rm_add_5_12345.vcd'), ...],
        output_path='merged.vcd',
    )

Usage (CLI):
    python -m cocotbpynq.pr.waveform_merger \\
        --static dump.vcd \\
        --rm-dir build/waves \\
        --output merged.vcd
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# VCD identifier generation
# ══════════════════════════════════════════════════════════════════════════
# VCD uses printable ASCII 33..126 for short signal ids. Single chars first,
# then two chars, etc.  With 94 printable chars per position, a single char
# covers 94 signals, two chars cover 8836, three covers 830K — plenty for us.

_VCD_ID_MIN = 33   # '!'
_VCD_ID_MAX = 126  # '~'
_VCD_ID_RANGE = _VCD_ID_MAX - _VCD_ID_MIN + 1


def _vcd_id(n: int) -> str:
    """Generate the n-th VCD identifier (0-indexed)."""
    chars = []
    n += 1
    while n > 0:
        n -= 1
        chars.append(chr(_VCD_ID_MIN + (n % _VCD_ID_RANGE)))
        n //= _VCD_ID_RANGE
    return "".join(reversed(chars))


# ══════════════════════════════════════════════════════════════════════════
# Source trace description
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class TraceSource:
    """One input trace to merge with its placement in the merged scope tree."""
    path: Path
    scope_path: List[str]   # e.g. ['top', 'static']  or  ['top','rm','rp_add','add_5','pid12345']
    label: str              # human-readable label for logging


# ══════════════════════════════════════════════════════════════════════════
# Loading traces via ewal
# ══════════════════════════════════════════════════════════════════════════

def _load_trace(path: Path):
    """Load a VCD via ewal. Returns the underlying _core PyTrace."""
    import ewal  # imported lazily so this module can be imported w/o ewal
    t = ewal.load(str(path))
    return t


# ══════════════════════════════════════════════════════════════════════════
# Signal value formatting
# ══════════════════════════════════════════════════════════════════════════

def _format_vcd_value(value, width: int, vcd_id: str) -> str:
    """Render one value-change line for a VCD at a given time."""
    if value is None:
        if width == 1:
            return f"x{vcd_id}"
        return f"b{'x' * width} {vcd_id}"

    if isinstance(value, str):
        # ewal may return 'x' / 'z' / '1'… keep single-char as-is
        if width == 1 and value in ('0', '1', 'x', 'z'):
            return f"{value}{vcd_id}"
        # Multi-bit string (binary text)
        return f"b{value} {vcd_id}"

    # Numeric
    ival = int(value)
    if width == 1:
        return f"{ival & 1}{vcd_id}"
    if ival < 0:
        ival &= (1 << width) - 1
    bits = format(ival, f"0{width}b") if width > 0 else "0"
    return f"b{bits} {vcd_id}"


# ══════════════════════════════════════════════════════════════════════════
# Scope tree
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class ScopeNode:
    """One node in the merged hierarchy tree."""
    name: str
    children: Dict[str, "ScopeNode"] = field(default_factory=dict)
    signals: List[Tuple[str, int, str]] = field(default_factory=list)
    # list of (leaf_name, width, vcd_id)


def _insert_signal(root: ScopeNode, scope_parts: List[str], leaf: str,
                   width: int, vcd_id: str):
    node = root
    for part in scope_parts:
        # Sanitize scope component to VCD-legal identifier chars
        safe = re.sub(r'[^A-Za-z0-9_]', '_', part)
        if safe not in node.children:
            node.children[safe] = ScopeNode(name=safe)
        node = node.children[safe]
    node.signals.append((leaf, width, vcd_id))


def _emit_scope(node: ScopeNode, out: list, indent: int = 0):
    """Emit $scope / $upscope declarations recursively."""
    pad = "  " * indent
    out.append(f"{pad}$scope module {node.name} $end")
    for leaf, width, vcd_id in node.signals:
        safe_leaf = re.sub(r'[^A-Za-z0-9_\[\]:]', '_', leaf)
        out.append(f"{pad}  $var wire {width} {vcd_id} {safe_leaf} $end")
    for child in node.children.values():
        _emit_scope(child, out, indent + 1)
    out.append(f"{pad}$upscope $end")


# ══════════════════════════════════════════════════════════════════════════
# Index ↔ timestamp mapping
# ══════════════════════════════════════════════════════════════════════════

def _build_timestamp_map(trace_core) -> List[int]:
    """Returns a list mapping index→timestamp for a trace."""
    n = trace_core.max_index() + 1
    return [trace_core.timestamp(i) for i in range(n)]


# ══════════════════════════════════════════════════════════════════════════
# Leaf name helpers
# ══════════════════════════════════════════════════════════════════════════

def _split_signal(full_path: str) -> Tuple[List[str], str]:
    """Split a signal path like 'tb.dut.counter' into (['tb','dut'], 'counter').

    ewal prefixes top-level signals of raw-dump VCDs with '$rootio.', which we
    strip so the merged tree is cleaner.
    """
    if full_path.startswith('$rootio.'):
        full_path = full_path[len('$rootio.'):]
    parts = full_path.split('.')
    if len(parts) == 1:
        return [], parts[0]
    return parts[:-1], parts[-1]


# ══════════════════════════════════════════════════════════════════════════
# Main merge routine
# ══════════════════════════════════════════════════════════════════════════

def merge_waveforms(
    sources: List[TraceSource],
    output_path: Path,
    timescale: str = "1ns",
) -> Path:
    """Merge all trace sources into a single VCD at `output_path`."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Load every source ─────────────────────────────────────────────
    loaded = []  # (TraceSource, trace, core, ts_map)
    total_signals = 0
    for src in sources:
        if not src.path.exists():
            logger.warning(f"Skipping missing trace: {src.path}")
            continue
        try:
            trace = _load_trace(src.path)
        except Exception as e:
            logger.warning(f"Failed to load {src.path}: {e}")
            continue
        core = trace._core
        ts_map = _build_timestamp_map(core)
        loaded.append((src, trace, core, ts_map))
        total_signals += len(trace.signals)
        logger.info(f"Loaded {src.label}: {trace.max_index + 1} indices, "
                    f"{len(trace.signals)} signals")

    if not loaded:
        raise RuntimeError("No traces could be loaded.")

    # ── Build merged scope tree and assign VCD ids ────────────────────
    root = ScopeNode(name="merged")
    # entries: (core, signal_name, vcd_id, width, prev_value)
    entries: List[List] = []
    id_counter = 0
    for src, trace, core, _ts_map in loaded:
        for sig in trace.signals:
            scope_prefix, leaf = _split_signal(sig)
            vcd_id = _vcd_id(id_counter)
            id_counter += 1
            width = trace.width(sig) or 1
            _insert_signal(root, src.scope_path + scope_prefix, leaf, width, vcd_id)
            entries.append([core, sig, vcd_id, width, _LAST_VALUE_SENTINEL])
    logger.info(f"Merged tree: {id_counter} signals across {len(loaded)} traces")

    # ── Build timeline: merge all traces' index streams by timestamp ──
    # Strategy: for each source, iterate its indices and find what time each
    # maps to; global output times = union of all per-source times.
    # To keep memory bounded we iterate lazily per source and emit value
    # changes sorted by (timestamp, source_order).

    # Collect (timestamp, source_id, src_index) tuples, sorted.
    events: List[Tuple[int, int, int]] = []
    for src_id, (_src, _tr, _core, ts_map) in enumerate(loaded):
        for idx, ts in enumerate(ts_map):
            events.append((ts, src_id, idx))
    events.sort()

    # ── Emit VCD ──────────────────────────────────────────────────────
    import datetime
    lines: List[str] = []
    lines.append(f"$date {datetime.datetime.now().isoformat()} $end")
    lines.append("$version cocotbpynq waveform_merger $end")
    lines.append(f"$timescale {timescale} $end")
    _emit_scope(root, lines, indent=0)
    lines.append("$enddefinitions $end")

    with output_path.open('w') as f:
        f.write("\n".join(lines))
        f.write("\n")

        # Per-source: track cursor into its entries list for fast access.
        # entries is ordered so entries with matching core are contiguous
        # if we group by source — but we didn't group. Build per-source lists.
        per_source_entries: Dict[int, List[List]] = {i: [] for i in range(len(loaded))}
        core_to_source_id = {id(loaded[i][2]): i for i in range(len(loaded))}
        for e in entries:
            sid = core_to_source_id[id(e[0])]
            per_source_entries[sid].append(e)

        current_time = -1
        dumpvars_written = False
        for ts, src_id, idx in events:
            if ts != current_time:
                if current_time != -1:
                    # flush line break before new time
                    pass
                if not dumpvars_written:
                    # First emit initial values as $dumpvars
                    f.write("#0\n")
                    f.write("$dumpvars\n")
                    for src_id0, s_entries in per_source_entries.items():
                        core = loaded[src_id0][2]
                        for e in s_entries:
                            _c, name, vid, width, _prev = e
                            try:
                                val = core.signal_value(name, 0)
                            except Exception:
                                val = None
                            e[4] = val
                            f.write(_format_vcd_value(val, width, vid) + "\n")
                    f.write("$end\n")
                    dumpvars_written = True
                if ts > 0:
                    f.write(f"#{ts}\n")
                current_time = ts

            # For this (src_id, idx), diff each signal's value against prev
            core = loaded[src_id][2]
            for e in per_source_entries[src_id]:
                _c, name, vid, width, prev = e
                try:
                    val = core.signal_value(name, idx)
                except Exception:
                    val = None
                if val != prev:
                    f.write(_format_vcd_value(val, width, vid) + "\n")
                    e[4] = val

        if not dumpvars_written:
            # Trace was empty — still emit a stub
            f.write("#0\n$dumpvars\n$end\n")

    logger.info(f"Wrote merged waveform: {output_path}")
    return output_path


_LAST_VALUE_SENTINEL = object()


# ══════════════════════════════════════════════════════════════════════════
# Discovery of trace files produced by PRCocotbRunner
# ══════════════════════════════════════════════════════════════════════════

_RM_VCD_RE = re.compile(r'^rm_(?P<variant>.+)_(?P<pid>\d+)\.(?:vcd|fst)$')


def discover_rm_traces(trace_dir: Path) -> List[Tuple[str, str, int, Path]]:
    """Return [(partition_hint, variant, pid, path), ...] for RM VCDs.

    partition_hint is derived from variant name; caller may override with an
    explicit mapping if it knows the RM→partition relation.
    """
    results = []
    if not trace_dir.is_dir():
        return results
    for p in sorted(trace_dir.iterdir()):
        m = _RM_VCD_RE.match(p.name)
        if not m:
            continue
        variant = m.group('variant')
        pid = int(m.group('pid'))
        results.append((variant, variant, pid, p))
    return results


def build_sources(
    static_vcd: Optional[Path],
    rm_entries: Iterable[Tuple[str, str, int, Path]],
) -> List[TraceSource]:
    """Build the canonical TraceSource list from static + RM entries."""
    sources: List[TraceSource] = []
    if static_vcd is not None and static_vcd.exists():
        sources.append(TraceSource(
            path=static_vcd,
            scope_path=['top', 'static'],
            label=f"static ({static_vcd.name})",
        ))
    for partition, variant, pid, path in rm_entries:
        sources.append(TraceSource(
            path=path,
            scope_path=['top', 'rm', partition, variant, f"pid{pid}"],
            label=f"rm/{partition}/{variant}/pid{pid}",
        ))
    return sources


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format='[merger] %(message)s')
    parser = argparse.ArgumentParser(description="Merge cocotbpynq PR waveforms.")
    parser.add_argument('--static', type=Path, default=None,
                        help='Path to cocotb static region VCD (e.g. dump.vcd).')
    parser.add_argument('--rm-dir', type=Path, required=True,
                        help='Directory containing rm_*.vcd files.')
    parser.add_argument('--output', type=Path, required=True,
                        help='Output merged VCD path.')
    parser.add_argument('--partition-map', type=str, default=None,
                        help='JSON mapping variant→partition, e.g. '
                             '\'{"add_5":"rp_add","sub_3":"rp_sub"}\'.')
    args = parser.parse_args(argv)

    part_map = {}
    if args.partition_map:
        import json
        part_map = json.loads(args.partition_map)

    rm_entries = []
    for variant, _v, pid, path in discover_rm_traces(args.rm_dir):
        partition = part_map.get(variant, variant)
        rm_entries.append((partition, variant, pid, path))

    sources = build_sources(args.static, rm_entries)
    if not sources:
        print("No traces found to merge.", file=sys.stderr)
        return 1

    merge_waveforms(sources, args.output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
