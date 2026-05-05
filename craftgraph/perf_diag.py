"""Wall-clock and frame-budget measurement helpers.

Mirrors the structure of craftgraph.hwnd_diag: a pure-data measurement
module with no Qt-widget imports in the body. The Qt frame-time overlay
in qt_gui.py reads from this module rather than the other way around.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)
# Track installed handlers so install_logger() is idempotent across
# repeat launches in the same process (e.g. test reruns).
_installed_handlers: list[logging.Handler] = []


def install_logger(
    *,
    log_path: Path | None = None,
    console: bool = True,
    level: int = logging.INFO,
) -> None:
    """Wire up perf_diag log output to a file and (optionally) stderr.

    Without this the logger inherits the root level (WARNING by default),
    so ``measure()``'s INFO lines are silenced -- only ``report_frame()``
    WARNINGs surface. Call once during app start (CLI / GUI entry point).

    Args:
        log_path: File to append perf records to. ``None`` skips file output.
        console: Whether to also stream records to stderr.
        level: Minimum level the perf_diag logger surfaces (default INFO).
    """
    # Detach any handlers we previously installed so repeat calls do not
    # double-log. Leaves third-party handlers alone.
    for h in _installed_handlers:
        logger.removeHandler(h)
    _installed_handlers.clear()

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        _installed_handlers.append(file_handler)

    if console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        _installed_handlers.append(stream_handler)

    # Stop propagation so records do not also flow to the root logger
    # (which may have its own handlers configured by callers).
    logger.propagate = False


@dataclass(frozen=True, slots=True)
class PerfSnapshot:
    """A single point-in-time perf measurement."""

    action: str
    perf_counter_ns: int

    @classmethod
    def now(cls, *, action: str) -> "PerfSnapshot":
        return cls(action=action, perf_counter_ns=time.perf_counter_ns())

    def delta_ms_since(self, other: "PerfSnapshot") -> float:
        return (self.perf_counter_ns - other.perf_counter_ns) / 1_000_000.0


FRAME_BUDGET_MS = 33.0


def report_frame(frame_ms: float, *, budget_ms: float = FRAME_BUDGET_MS) -> None:
    """Log a WARNING when *frame_ms* exceeds *budget_ms*; no-op otherwise."""
    if frame_ms > budget_ms:
        logger.warning(
            "frame_budget_violation frame_ms=%.3f budget_ms=%.3f",
            frame_ms,
            budget_ms,
        )


@contextmanager
def measure(action: str) -> Iterator[PerfSnapshot]:
    """Log wall-clock delta around a block.

    Emits one INFO line on exit::

        action=<action> delta_ms=<float>
    """
    before = PerfSnapshot.now(action=action)
    try:
        yield before
    finally:
        after = PerfSnapshot.now(action=action)
        logger.info(
            "action=%s delta_ms=%.3f",
            action,
            after.delta_ms_since(before),
        )


# ---------------------------------------------------------------------------
# Per-node paint timing aggregator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PaintAggregate:
    """Aggregated paint timing for one node class."""

    count: int
    total_ms: float


_paint_lock = threading.Lock()
_paint_totals: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])

# Global enable flag for per-paint instrumentation. Default False so the
# wrapper installed by ``qt_nodes._install_node_paint_timing`` can early-out
# without touching the lock or accumulator dict on every paint. Flip via
# ``set_paint_recording(True)`` to capture data for the Perf Log dialog.
_paint_recording_enabled = False


def set_paint_recording(enabled: bool) -> None:
    """Enable or disable per-class paint timing recording."""
    global _paint_recording_enabled
    _paint_recording_enabled = enabled


def is_paint_recording() -> bool:
    """Return True when ``record_paint`` will accumulate samples."""
    return _paint_recording_enabled


def record_paint(node_class: str, ms: float) -> None:
    """Add one paint sample for *node_class*. Thread-safe; no-op when disabled."""
    if not _paint_recording_enabled:
        return
    with _paint_lock:
        bucket = _paint_totals[node_class]
        bucket[0] += 1
        bucket[1] += ms


def paint_stats() -> dict[str, PaintAggregate]:
    """Return a snapshot of per-class paint aggregates."""
    with _paint_lock:
        return {
            name: PaintAggregate(count=int(b[0]), total_ms=b[1])
            for name, b in _paint_totals.items()
        }


def reset_paint_stats() -> None:
    """Clear all accumulated paint stats."""
    with _paint_lock:
        _paint_totals.clear()
