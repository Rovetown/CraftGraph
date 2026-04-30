"""Wall-clock and frame-budget measurement helpers.

Mirrors the structure of craftgraph.hwnd_diag: a pure-data measurement
module with no Qt-widget imports in the body. The Qt frame-time overlay
in qt_gui.py reads from this module rather than the other way around.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

logger = logging.getLogger(__name__)


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
