"""Wall-clock and frame-budget measurement helpers.

Mirrors the structure of craftgraph.hwnd_diag: a pure-data measurement
module with no Qt-widget imports in the body. The Qt frame-time overlay
in qt_gui.py reads from this module rather than the other way around.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
# Track installed handlers so install_logger() is idempotent across
# repeat launches in the same process (e.g. test reruns).
_installed_handlers: list[logging.Handler] = []


def install_logger(
    *,
    log_path: Path | None = None,
    level: int = logging.INFO,
) -> None:
    """Wire perf_diag's records to a dedicated perf log file.

    perf_diag keeps its own ``perf.log`` file handler (the Perf Log dialog
    tails it) and propagates to the ``craftgraph`` logger, so its frametime
    and ``measure()`` records also reach the central rich console handler
    configured by ``craftgraph.log_setup.configure_logging``. The perf_diag
    logger level is pinned (default INFO) so ``perf.log`` stays complete
    regardless of the console verbosity the user chose. Call once at app
    start (the GUI entry point).

    Args:
        log_path: File to append perf records to. ``None`` skips file output.
        level: Level for the perf_diag logger and its file handler.
    """
    # Detach handlers we previously installed so repeat calls do not
    # double-log. Leaves third-party handlers alone.
    for h in _installed_handlers:
        logger.removeHandler(h)
        h.close()
    _installed_handlers.clear()

    logger.setLevel(level)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)
        _installed_handlers.append(file_handler)

    # Propagate to the central craftgraph logger so perf records also reach
    # its rich console handler. (This was False only because there was no
    # controlled central config to propagate into; log_setup provides one.)
    logger.propagate = True


@dataclass(frozen=True, slots=True)
class PerfSnapshot:
    """A single point-in-time perf measurement."""

    action: str
    perf_counter_ns: int

    @classmethod
    def now(cls, *, action: str) -> PerfSnapshot:
        return cls(action=action, perf_counter_ns=time.perf_counter_ns())

    def delta_ms_since(self, other: PerfSnapshot) -> float:
        return (self.perf_counter_ns - other.perf_counter_ns) / 1_000_000.0


FRAME_BUDGET_MS = 33.0


def report_frame(frame_ms: float, *, budget_ms: float = FRAME_BUDGET_MS) -> None:
    """Log a WARNING when *frame_ms* exceeds *budget_ms*, when diagnostics are on.

    Frame-budget warnings are a diagnostic signal aimed at developers and
    advanced users: they pinpoint expensive paints during real interactive
    use. In a release binary they would pollute ``craftgraph.log`` without
    actionable value for the average user, so this no-ops unless
    :func:`craftgraph.app_dirs.perf_diagnostics_enabled` returns True --
    that is, either the build is dev or the user opted in via Settings.
    """
    from craftgraph import app_dirs

    if not app_dirs.perf_diagnostics_enabled():
        return
    if frame_ms > budget_ms:
        logger.warning(
            "frame_budget_violation frame_ms=%.3f budget_ms=%.3f",
            frame_ms,
            budget_ms,
        )


@contextmanager
def measure(action: str) -> Iterator[PerfSnapshot]:
    """Log wall-clock delta around a block, when diagnostics are on.

    Emits one INFO line on exit::

        action=<action> delta_ms=<float>

    No-ops in release builds where
    :func:`craftgraph.app_dirs.perf_diagnostics_enabled` is False -- the
    context still yields a snapshot so callers using ``with measure(..) as s``
    keep working, but nothing is logged.
    """
    from craftgraph import app_dirs

    enabled = app_dirs.perf_diagnostics_enabled()
    before = PerfSnapshot.now(action=action)
    try:
        yield before
    finally:
        if enabled:
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
