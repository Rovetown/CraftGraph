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
from dataclasses import dataclass

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
