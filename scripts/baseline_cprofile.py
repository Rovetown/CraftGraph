"""Tier-A folder-load cProfile capture.

Run with: ``uv run --extra qt python scripts/baseline_cprofile.py <out_dir>``

Writes ``<out_dir>/tier_a.prof`` and prints the top-20 cumulative entries to
stdout so the caller can paste them into a baseline doc.

Mirrors ``scripts/baseline_capture.py`` for shape: offscreen Qt, real
``CraftGraphWindow``, real ``load_recipes`` against the Tier-A workload at
``craftgraph/cc3_reference_files/real-mod-examples``.
"""

from __future__ import annotations

import cProfile
import io
import os
import pstats
import sys
from pathlib import Path

# Force offscreen Qt before importing anything that pulls in QGuiApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from craftgraph.qt_gui import CraftGraphWindow


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: baseline_cprofile.py <out_dir>", file=sys.stderr)
        sys.exit(2)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)

    tier_a = Path("craftgraph/cc3_reference_files/real-mod-examples")

    app = QtWidgets.QApplication(sys.argv)
    win = CraftGraphWindow()
    win.show()
    app.processEvents()

    prof = cProfile.Profile()
    prof.enable()
    win.load_recipes(tier_a)
    app.processEvents()
    prof.disable()

    prof_path = out_dir / "tier_a.prof"
    prof.dump_stats(str(prof_path))

    buf = io.StringIO()
    stats = pstats.Stats(prof, stream=buf).sort_stats("cumulative")
    stats.print_stats(20)
    top = buf.getvalue()
    print(top)
    print(f"cProfile dump: {prof_path}")

    win.close()
    app.processEvents()


if __name__ == "__main__":
    main()
