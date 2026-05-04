"""Optional tracemalloc snapshot helper.

Pairs with :mod:`craftgraph.hwnd_diag`: both write to the same
diagnostics directory so users can attach a complete picture to bug
reports. ``tracemalloc`` must be started by the caller before snapshots
have content; the helper degrades gracefully when it isn't.
"""

from __future__ import annotations

import tracemalloc
from datetime import datetime
from pathlib import Path


def snapshot_to_file(path: Path, *, top_n: int = 20) -> None:
    """Write a tracemalloc snapshot to *path*; degrade if tracemalloc off."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not tracemalloc.is_tracing():
        path.write_text(
            f"# Memory snapshot {datetime.now().isoformat()}\n"
            "tracemalloc disabled -- start with tracemalloc.start() to capture\n",
            encoding="utf-8",
        )
        return
    snap = tracemalloc.take_snapshot()
    stats = snap.statistics("lineno")[:top_n]
    lines = [
        f"# Memory snapshot {datetime.now().isoformat()}",
        f"# Top {top_n} allocations",
        "",
    ]
    lines.extend(str(s) for s in stats)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
