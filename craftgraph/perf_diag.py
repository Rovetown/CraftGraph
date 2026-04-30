"""Wall-clock and frame-budget measurement helpers.

Mirrors the structure of craftgraph.hwnd_diag: a pure-data measurement
module with no Qt-widget imports in the body. The Qt frame-time overlay
in qt_gui.py reads from this module rather than the other way around.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


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
