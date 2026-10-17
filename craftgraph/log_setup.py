"""Central logging configuration for CraftGraph.

Installs a console handler and a plain-text file handler on the ``craftgraph``
package logger. UI-agnostic -- safe to call from the CLI entry point, the
GUI, or tests.

``rich`` is an optional dependency: when present we install ``RichHandler``
plus ``rich.traceback`` for nicer dev-time rendering; when absent we fall
back to a stdlib ``StreamHandler`` so release builds shipped without rich
still log correctly.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from craftgraph import app_dirs

if TYPE_CHECKING:
    pass


_DEFAULT_LOG_RETENTION_DAYS = 7
# Subset of the log dir we are willing to delete. Anything else (e.g.
# user-dropped notes, screenshots) is left alone -- the cleanup only
# touches files we know we create.
_CLEANUP_PATTERNS: tuple[str, ...] = (
    "*.log",                # craftgraph.log, hwnd.log
    "modules-*.txt",        # CRAFTGRAPH_DUMP_MODULES diagnostic dumps
    "diagnostics/*.log",    # perf.log under the diagnostics/ subdir
)


def cleanup_old_logs(
    log_dir: Path,
    *,
    max_age_days: int = _DEFAULT_LOG_RETENTION_DAYS,
) -> int:
    """Delete log + diagnostic files in *log_dir* older than *max_age_days*.

    Returns the number of files removed. Quiet on individual file errors
    (a locked file -- e.g. the active log file on Windows -- is skipped
    rather than crashing startup). Returns 0 if *log_dir* does not exist.

    The mtime test naturally preserves any file currently being written
    to (the active ``craftgraph.log`` for the session, ``perf.log`` for
    a fresh dev session, etc.) because their mtime is "now".

    Only files matching the patterns in ``_CLEANUP_PATTERNS`` are
    candidates; an unknown file dropped into the log dir by the user
    survives.
    """
    if not log_dir.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for pattern in _CLEANUP_PATTERNS:
        for entry in log_dir.glob(pattern):
            if not entry.is_file():
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                # Locked / permission-denied / disappeared between glob
                # and unlink -- not actionable; skip silently.
                continue
    return removed


def _import_rich() -> tuple[type[logging.Handler] | None, object | None, object | None]:
    """Best-effort import of rich's logging+console+traceback symbols.

    Returns ``(RichHandler, Console, install_rich_traceback)`` when rich
    is importable; an all-``None`` tuple otherwise. Kept as a helper so
    tests can monkeypatch the lookup without touching ``sys.modules``.
    """
    try:
        from rich.console import Console
        from rich.logging import RichHandler
        from rich.traceback import install as install_rich_traceback
    except ImportError:
        return None, None, None
    return RichHandler, Console, install_rich_traceback


_PACKAGE_LOGGER = "craftgraph"
_GENERAL_LOG_FILENAME = "craftgraph.log"

# Handlers this module installed, tracked so configure_logging() is
# idempotent: a re-call (a live level change, a test rerun) removes them
# before installing fresh ones, so handlers never accumulate.
_installed_handlers: list[logging.Handler] = []


def configure_logging(
    *,
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> None:
    """Install console + plain file logging on the ``craftgraph`` logger.

    Idempotent: removes handlers installed by a previous call before
    installing fresh ones.

    The ``craftgraph`` logger keeps its default ``propagate=True``, so
    records also reach any handler on the root logger (such as pytest's
    log capture). The app never adds handlers to the root logger, so this
    produces no duplicate output.

    Console handler choice:

    - When ``rich`` is importable, install ``RichHandler`` (colored,
      structured) and ``rich.traceback`` for unhandled exceptions.
    - When ``rich`` is missing (release builds), install a stdlib
      ``StreamHandler`` on stderr with a compact format.

    Args:
        level: Minimum level for the console handler and the package logger.
        log_dir: Directory for ``craftgraph.log``. Defaults to the app log dir.
    """
    pkg_logger = logging.getLogger(_PACKAGE_LOGGER)

    for handler in _installed_handlers:
        pkg_logger.removeHandler(handler)
        handler.close()
    _installed_handlers.clear()

    pkg_logger.setLevel(level)

    RichHandler, Console, install_rich_traceback = _import_rich()
    console_handler: logging.Handler
    if RichHandler is not None and Console is not None:
        console_handler = RichHandler(
            level=level,
            console=Console(stderr=True),
            rich_tracebacks=True,
            show_path=True,
        )
    else:
        console_handler = logging.StreamHandler(stream=sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    pkg_logger.addHandler(console_handler)
    _installed_handlers.append(console_handler)

    # File: plain text, WARNING and up -- errors and frame-budget violations,
    # the bug-report material. A log-file failure must never crash the app.
    target_dir = log_dir if log_dir is not None else app_dirs.log_dir()

    # Prune stale logs once per launch BEFORE opening the active file
    # handler. Files older than the retention window get dropped (default
    # 7 days). The active session's craftgraph.log is preserved because
    # its mtime is "now"; an old hwnd.log from two months ago is the
    # exact pattern we want to delete.
    cleanup_old_logs(target_dir)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            target_dir / _GENERAL_LOG_FILENAME, encoding="utf-8"
        )
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        pkg_logger.addHandler(file_handler)
        _installed_handlers.append(file_handler)
    except OSError as exc:
        pkg_logger.warning("could not open log file in %s: %s", target_dir, exc)

    # Pretty rendering for unhandled exceptions (rich-only sugar).
    if install_rich_traceback is not None:
        install_rich_traceback(show_locals=False)
