"""Structured tracing for PR simulation pipeline debugging.

Env-gated, JSONL output, cross-process safe (append-only file). Designed
to localise hangs to a specific phase of the reconfig protocol without
distorting the timings we already measure.

Activation:
    PR_TRACE=1              enable tracing
    PR_TRACE_FILE=/path     output path (default: ./pr_trace.jsonl)
    PR_TRACE_STDERR=1       also mirror events to stderr

When PR_TRACE is unset (the common case), `event()` and `span()` are
no-ops — a single attribute lookup + truthy check per call (~30 ns),
small enough to leave in hot paths.

Record format (one JSON object per line):
    {
      "ts":        int  — perf_counter_ns(), same clock as runner_wrap measurements
      "ts_wall":   float — time.time() (absolute UTC seconds), useful for cross-host
      "pid":       int  — os.getpid() — distinguishes cocotb subprocess from parent
      "thread":    str  — threading.current_thread().name
      "event":     str  — dot-separated phase tag, e.g. "sim_process.reconfigure.begin"
      "span_id":   int  — only for span begin/end pairs
      ... custom k=v fields added by the caller
    }

Common event names used in the codebase (grep these):
    overlay.pr_download.{begin,end}
    pr_reconfigure.{submit,poll,complete,error,timeout}
    control_thread.{pending_detected,reconfigure_call.begin,reconfigure_call.end,response_written}
    pr_system.reconfigure.{begin,end}
    sim_process.reconfigure.{begin,end}
    sim_process.{send_cmd_reconfig,wait_old_exit.begin,wait_old_exit.end,
                 start_new_rm.begin,start_new_rm.end,
                 wait_rm_ready.begin,wait_rm_ready.end,
                 wait_noop.begin,wait_noop.end,settle_cycles}

To analyze: read the JSONL, sort by ts, pair span begin/end, and report
    per-phase durations and any orphan begins (the last orphan = where it hung).
"""
from __future__ import annotations

import contextlib
import itertools
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, TextIO


# Read enable state once at import time — env changes after import don't
# flip behavior, but that matches the typical "set env, then run" workflow.
ENABLED = bool(os.environ.get('PR_TRACE'))
_MIRROR_STDERR = bool(os.environ.get('PR_TRACE_STDERR'))
_TRACE_FILE_PATH: Optional[Path] = None
_SINK: Optional[TextIO] = None
_SINK_LOCK = threading.Lock()
_SPAN_COUNTER = itertools.count(1)


def _get_sink() -> Optional[TextIO]:
    """Lazily open the trace file on first use. Append mode — multiple
    processes (cocotb subprocess + control-thread parent) can share."""
    global _SINK, _TRACE_FILE_PATH
    if not ENABLED:
        return None
    if _SINK is not None:
        return _SINK
    path = os.environ.get('PR_TRACE_FILE') or 'pr_trace.jsonl'
    _TRACE_FILE_PATH = Path(path).resolve()
    _TRACE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Line-buffered text mode; append is atomic for line-sized writes on
    # POSIX, so concurrent writers from different processes are safe.
    _SINK = open(_TRACE_FILE_PATH, 'a', buffering=1)
    return _SINK


def _emit(event: str, **fields: Any) -> None:
    """Internal: format and write one JSON line. Caller must already have
    verified ENABLED."""
    sink = _get_sink()
    if sink is None:
        return
    record = {
        'ts': time.perf_counter_ns(),
        'ts_wall': time.time(),
        'pid': os.getpid(),
        'thread': threading.current_thread().name,
        'event': event,
        **fields,
    }
    line = json.dumps(record, default=str) + '\n'
    with _SINK_LOCK:
        sink.write(line)
        if _MIRROR_STDERR:
            sys.stderr.write(f'[trace] {line}')


def event(name: str, **fields: Any) -> None:
    """Emit a single-point event (no begin/end pair). Cheap no-op when
    PR_TRACE is unset."""
    if not ENABLED:
        return
    _emit(name, **fields)


@contextlib.contextmanager
def span(name: str, **fields: Any):
    """Context manager that emits `<name>.begin` and `<name>.end` events
    sharing a span_id. The end event carries elapsed_ns computed from the
    same perf_counter_ns() clock used by all other measurements.

    Usage:
        with span('sim_process.reconfigure', partition=name, rm=rm_name):
            ...

    On exception, the end event includes 'exception': '<type>: <msg>' so
    the analyzer can flag failed spans separately from hung ones.
    """
    if not ENABLED:
        yield None
        return
    sid = next(_SPAN_COUNTER)
    t0 = time.perf_counter_ns()
    _emit(f'{name}.begin', span_id=sid, **fields)
    exc_kv: dict = {}
    try:
        yield sid
    except BaseException as e:
        exc_kv['exception'] = f'{type(e).__name__}: {e}'
        raise
    finally:
        _emit(
            f'{name}.end',
            span_id=sid,
            elapsed_ns=time.perf_counter_ns() - t0,
            **exc_kv,
        )


def flush() -> None:
    """Force the sink to flush (used at process shutdown so a crash
    doesn't lose the last few events)."""
    sink = _SINK
    if sink is not None:
        try:
            sink.flush()
        except Exception:
            pass
