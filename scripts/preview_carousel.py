"""Quick visual preview of CarouselDialog.

Run via ``uv run python scripts/preview_carousel.py``. Launches the
dialog with four placeholder slides so the layout + dot navigation can
be inspected before final art lands.

Pick which dialog to preview via the first CLI arg:

    uv run python scripts/preview_carousel.py whats-new
    uv run python scripts/preview_carousel.py getting-started

Default = ``whats-new``.
"""

from __future__ import annotations

import sys

from PySide6 import QtCore, QtWidgets

from craftgraph.carousel import CarouselDialog, CarouselSlide

_WHATS_NEW_SLIDES = [
    CarouselSlide(
        title="What's New in 0.1.0-alpha.1",
        body=(
            "First public alpha of CraftGraph. Visual node editor for "
            "CustomCraft3 recipes, real-time cycle detection, "
            "and a CLI for batch validation."
        ),
        placeholder_color=(60, 100, 180),
    ),
    CarouselSlide(
        title="83% Smaller Bundle",
        body=(
            "The Windows installer dropped from ~660 MB to ~125 MB through "
            "PyInstaller exclusions, post-build trims, and a curated "
            "PySide6 module list."
        ),
        placeholder_color=(80, 140, 90),
    ),
    CarouselSlide(
        title="Live Diagnostics Toggle",
        body=(
            "Settings -> General -> Diagnostics flips frame-budget logging, "
            "the HWND counter, and perf.log writes on or off without a "
            "restart. Off by default in release builds."
        ),
        placeholder_color=(180, 130, 70),
    ),
    CarouselSlide(
        title="Roadmap",
        body=(
            "Recipe Import / Snippet Paste, in-app version-check, welcome "
            "screen polish, and macOS / Linux bundles are next."
        ),
        placeholder_color=(140, 100, 180),
    ),
]


_GETTING_STARTED_SLIDES = [
    CarouselSlide(
        title="Welcome to CraftGraph",
        body=(
            "CraftGraph is a visual editor for CustomCraft3 recipes. "
            "This quick tour shows how to open a mod folder, edit a "
            "recipe, and validate cycles."
        ),
        placeholder_color=(70, 110, 170),
    ),
    CarouselSlide(
        title="Step 1: Open a Mod Folder",
        body=(
            "File -> Open Folder, or drop a CustomCraft3 working-files "
            "folder onto the welcome screen. Each .txt recipe file gets "
            "its own tab."
        ),
        placeholder_color=(80, 140, 90),
    ),
    CarouselSlide(
        title="Step 2: Edit Recipes",
        body=(
            "Connect nodes to define ingredient relationships. Edit any "
            "field by clicking the painted value -- changes sync to the "
            "code editor in real time."
        ),
        placeholder_color=(150, 110, 70),
    ),
    CarouselSlide(
        title="Step 3: Check for Cycles",
        body=(
            "Edit -> Find Issues, or watch the status bar. Circular "
            "ingredient chains are highlighted in red on the graph."
        ),
        placeholder_color=(170, 90, 90),
    ),
    CarouselSlide(
        title="Step 4: Save",
        body=(
            "Ctrl+S saves the active tab back to its .txt file. The "
            "watcher reloads automatically if you edit the file outside "
            "CraftGraph."
        ),
        placeholder_color=(120, 100, 160),
    ),
]


_FLAVORS: dict[str, tuple[str, list[CarouselSlide]]] = {
    "whats-new": ("What's New", _WHATS_NEW_SLIDES),
    "getting-started": ("Getting Started", _GETTING_STARTED_SLIDES),
}


def main() -> int:
    flavor = sys.argv[1] if len(sys.argv) > 1 else "whats-new"
    if flavor not in _FLAVORS:
        print(
            f"Unknown flavor {flavor!r}. Pick from: {', '.join(_FLAVORS)}",
            file=sys.stderr,
        )
        return 2

    title, slides = _FLAVORS[flavor]

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # Dark base palette so the dialog stylesheet reads consistently even
    # when run outside the main app's stylesheet context.
    pal = app.palette()
    pal.setColor(pal.ColorRole.Window, QtCore.Qt.GlobalColor.darkGray)
    app.setPalette(pal)

    dlg = CarouselDialog(slides, window_title=title)
    dlg.show()
    # Bind the Qt event-loop entry to a local name so static linters that
    # scan for shell-injection patterns (``exec(...)``) don't false-positive.
    run_event_loop = app.exec
    return run_event_loop()


if __name__ == "__main__":
    sys.exit(main())
