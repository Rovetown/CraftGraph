"""Process-level CPU and RSS measurement via psutil.

Pairs with craftgraph.perf_diag (action wall-clock) and craftgraph.hwnd_diag
(handle counts) so the GUI can show one live status-bar widget covering
all three. Pure-data; no Qt imports in the body.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil

_proc = psutil.Process(os.getpid())


@dataclass(frozen=True, slots=True)
class ProcSnapshot:
    """A single point-in-time process measurement."""

    cpu_percent: float
    rss_bytes: int


def sample() -> ProcSnapshot:
    """Return the current process's CPU% and RSS.

    First call to ``cpu_percent()`` always returns 0.0 (psutil needs a
    baseline); subsequent calls return the average since the previous
    call to ``cpu_percent()`` on this process. Callers polling at 1 Hz
    will get steady values after the second call.
    """
    return ProcSnapshot(
        cpu_percent=_proc.cpu_percent(interval=None),
        rss_bytes=_proc.memory_info().rss,
    )
