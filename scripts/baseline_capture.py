"""Pre/post-Phase-1 baseline capture: wall-clock + HWND/widget snapshot.

Run with: ``uv run --extra qt python scripts/baseline_capture.py <out_dir>``
Writes hwnd_<ts>.txt to <out_dir> and prints wall-clock to stdout.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6 import QtWidgets

from craftgraph import hwnd_diag
from craftgraph.qt_gui import CraftGraphWindow


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: baseline_capture.py <out_dir>", file=sys.stderr)
        sys.exit(2)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)

    tier_a = Path("craftgraph/cc3_reference_files/real-mod-examples")

    app = QtWidgets.QApplication(sys.argv)
    win = CraftGraphWindow()
    win.show()
    app.processEvents()

    before = hwnd_diag.take_snapshot()
    t0 = time.perf_counter_ns()
    win.load_recipes(tier_a)
    app.processEvents()
    t1 = time.perf_counter_ns()
    after = hwnd_diag.take_snapshot()

    delta_ms = (t1 - t0) / 1_000_000.0
    snap_path = hwnd_diag.snapshot_to_file(out_dir / "hwnd_post_load.txt")

    print(f"Tier A load: {delta_ms:.1f} ms")
    print(f"HWND before: gui={before.gui_objects} gdi={before.gdi_objects} widgets={before.widget_count}")
    print(f"HWND after:  gui={after.gui_objects} gdi={after.gdi_objects} widgets={after.widget_count}")
    print(f"Snapshot written: {snap_path}")

    win.close()
    app.processEvents()


if __name__ == "__main__":
    main()
