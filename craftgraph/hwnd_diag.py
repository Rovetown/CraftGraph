"""Process-level GUI handle measurement and leak diagnostics.

On Windows this module reads ``GR_USEROBJECTS`` and ``GR_GDIOBJECTS``
via ``GetGuiResources`` so the rest of CraftGraph can detect HWND
leaks (each top-level Qt widget allocates a USER object; Windows
enforces a per-process cap of ~10,000). On non-Windows platforms the
counters return 0 and the rest of the API stays usable so calling
code does not need platform branches.
"""

from __future__ import annotations

import sys
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator, Optional

_GR_GDIOBJECTS = 0
_GR_USEROBJECTS = 1


def _windows_handle_count(flag: int) -> int:
    """Return the per-process handle count for *flag* on Windows.

    Returns 0 on non-Windows platforms or if the ctypes call fails
    for any reason -- diagnostics never raises into the GUI thread.
    """
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        user32.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        user32.GetGuiResources.restype = wintypes.DWORD
        handle = kernel32.GetCurrentProcess()
        return int(user32.GetGuiResources(handle, flag))
    except (OSError, AttributeError):
        return 0


def gui_handle_count() -> int:
    """Return the current process's USER object count (HWNDs, menus, timers)."""
    return _windows_handle_count(_GR_USEROBJECTS)


def gdi_handle_count() -> int:
    """Return the current process's GDI object count (DCs, brushes, fonts)."""
    return _windows_handle_count(_GR_GDIOBJECTS)


@dataclass(frozen=True)
class HandleSnapshot:
    """Point-in-time process resource counts.

    ``gui_objects`` and ``gdi_objects`` are 0 on non-Windows.
    ``widget_count`` is the number of live Qt widgets owned by the
    current ``QApplication`` instance, or 0 if none exists.
    """

    gui_objects: int
    gdi_objects: int
    widget_count: int

    def delta_against(self, before: HandleSnapshot) -> HandleSnapshot:
        return HandleSnapshot(
            gui_objects=self.gui_objects - before.gui_objects,
            gdi_objects=self.gdi_objects - before.gdi_objects,
            widget_count=self.widget_count - before.widget_count,
        )


def widget_inventory() -> dict[str, int]:
    """Return a {QObject class name: count} mapping for live widgets.

    Returns an empty dict if PySide6 is not installed or no
    QApplication has been created yet.
    """
    try:
        from PySide6 import QtWidgets
    except ImportError:
        return {}
    app = QtWidgets.QApplication.instance()
    if app is None:
        return {}
    return dict(Counter(type(w).__name__ for w in app.allWidgets()))


def take_snapshot() -> HandleSnapshot:
    """Capture a HandleSnapshot of the current process state."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        widget_count = 0
    else:
        app = QtWidgets.QApplication.instance()
        widget_count = len(app.allWidgets()) if app is not None else 0
    return HandleSnapshot(
        gui_objects=gui_handle_count(),
        gdi_objects=gdi_handle_count(),
        widget_count=widget_count,
    )


@dataclass
class Measurement:
    action: str
    before: HandleSnapshot
    after: HandleSnapshot | None = None

    @property
    def delta(self) -> HandleSnapshot:
        if self.after is None:
            raise RuntimeError("Measurement not yet completed")
        return self.after.delta_against(self.before)


_threshold: int = 20
_on_threshold_exceeded: Optional[Callable[[str, int], None]] = None


def install_logger(
    *,
    threshold: int = 20,
    on_threshold_exceeded: Optional[Callable[[str, int], None]] = None,
) -> None:
    """Configure how measure() reports large deltas.

    threshold is the gui_objects delta beyond which the callback fires.
    Pass on_threshold_exceeded=None to disable the callback.
    """
    global _threshold, _on_threshold_exceeded
    _threshold = threshold
    _on_threshold_exceeded = on_threshold_exceeded


def _append_log(line: str) -> None:
    from craftgraph import app_dirs

    log_dir = app_dirs.log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "hwnd.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


@contextmanager
def measure(action: str, *, log: bool = True) -> Iterator[Measurement]:
    """Capture a before/after HandleSnapshot around a block of work.

    If log is true (default), writes a one-line summary to
    app_dirs.log_dir() / "hwnd.log". If the gui_objects delta exceeds
    the configured threshold, also invokes any callback registered
    through install_logger.
    """
    m = Measurement(action=action, before=take_snapshot())
    try:
        yield m
    finally:
        m.after = take_snapshot()
        delta = m.delta
        if log:
            _append_log(
                f"action={action} "
                f"before={m.before.gui_objects} "
                f"after={m.after.gui_objects} "
                f"delta={delta.gui_objects:+d} "
                f"widgets={delta.widget_count:+d}",
            )
        if (
            _on_threshold_exceeded is not None
            and delta.gui_objects > _threshold
        ):
            _on_threshold_exceeded(action, delta.gui_objects)


def snapshot_to_file(path: Path | None = None, *, top_n: int = 20) -> Path:
    """Write a human-readable diagnostic snapshot to *path* (or default).

    Default location is ``app_dirs.log_dir() / "diagnostics" / "hwnd_<ts>.txt"``.
    Includes USER/GDI counts, total Qt widget count, top-N widget class
    breakdown, and the last 50 lines of ``hwnd.log`` if it exists.
    """
    if path is None:
        from craftgraph import app_dirs

        diag_dir = app_dirs.log_dir() / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = diag_dir / f"hwnd_{timestamp}.txt"

    snap = take_snapshot()
    inv = widget_inventory()
    top = sorted(inv.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    lines = [
        f"# CraftGraph HWND snapshot {datetime.now().isoformat(timespec='seconds')}",
        f"gui_objects={snap.gui_objects}",
        f"gdi_objects={snap.gdi_objects}",
        f"widget_count={snap.widget_count}",
        "",
        "Top widget classes:",
    ]
    for class_name, count in top:
        lines.append(f"  {class_name}: {count}")

    from craftgraph import app_dirs

    log_path = app_dirs.log_dir() / "hwnd.log"
    if log_path.is_file():
        tail = log_path.read_text(encoding="utf-8").splitlines()[-50:]
        lines.append("")
        lines.append("Recent hwnd.log entries:")
        lines.extend(tail)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
