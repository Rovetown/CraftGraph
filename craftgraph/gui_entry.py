"""Windowed entry point for the bundled CraftGraph executable.

PyInstaller ``--windowed`` uses this module instead of ``cli.py`` so the
double-clicked ``craftgraph.exe`` goes straight to the Qt main window
without flashing a console. The Click CLI still works for source-install
users via ``uv run craftgraph ...``; the bundled binary is GUI-only by
design.

Single optional positional arg: a recipe folder or file path to open at
launch. Without it, the welcome screen comes up.

Diagnostic: set ``CRAFTGRAPH_DUMP_MODULES=1`` in the environment before
launching to dump every imported module name to ``modules-gui.txt`` in
the working directory at process exit. Used by Step 7 of the bundle
size reduction plan -- walk every feature in the GUI with the env set,
close, and the resulting file is the empirical "needed list" for
refining the ``--collect-submodules`` / ``--hidden-import`` flags.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def _install_modules_dump() -> None:
    """Write the startup ``sys.modules`` snapshot if the diagnostic env is set.

    Writes ``modules-gui-startup.txt`` into the user log directory
    (``%LOCALAPPDATA%\\CraftGraph\\Logs\\`` on Windows; same root as
    ``craftgraph.log``) immediately, so a crashed app or a Task Manager
    kill still leaves evidence the instrumentation ran.

    The matching **exit snapshot** (``modules-gui.txt``) is wired
    separately in ``qt_gui.launch_qt_gui`` via Qt's ``aboutToQuit``
    signal -- PyInstaller's ``--windowed`` bootloader does not drain
    Python's ``atexit`` chain on Qt shutdown, so a plain ``atexit``
    hook never fires in a release bundle.

    Logged paths show up in ``craftgraph.log`` at WARNING level so the
    user can locate them. No-op when ``CRAFTGRAPH_DUMP_MODULES`` is
    unset or empty.
    """
    if not os.environ.get("CRAFTGRAPH_DUMP_MODULES"):
        return

    from craftgraph import app_dirs

    log_dir = app_dirs.log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    startup_path = log_dir / "modules-gui-startup.txt"

    logger = logging.getLogger("craftgraph.gui_entry")
    logger.warning(
        "CRAFTGRAPH_DUMP_MODULES=1 -- writing module list snapshots to %s",
        log_dir,
    )

    try:
        startup_path.write_text(
            "\n".join(sorted(sys.modules)),
            encoding="utf-8",
        )
        logger.warning(
            "startup snapshot: %s (%d modules)",
            startup_path,
            len(sys.modules),
        )
    except OSError as exc:
        logger.warning("startup snapshot FAILED: %s", exc)


def main() -> None:
    recipe_path: Path | None = None
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists():
            recipe_path = candidate

    # File-based logging still works in windowed mode (no console attached).
    from craftgraph.log_setup import configure_logging

    configure_logging(level=logging.INFO)

    # Module dump runs AFTER configure_logging so the logger handlers are
    # already attached when the diagnostic writes its progress messages.
    _install_modules_dump()

    from craftgraph.qt_gui import launch_qt_gui

    launch_qt_gui(recipe_path)


if __name__ == "__main__":
    main()
