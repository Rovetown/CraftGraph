"""Central logging configuration for CraftGraph.

Installs a rich-rendered console handler and a plain-text file handler on
the ``craftgraph`` package logger. UI-agnostic -- safe to call from the CLI
entry point, the GUI, or tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

from craftgraph import app_dirs

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
    """Install rich console + plain file logging on the ``craftgraph`` logger.

    Idempotent: removes handlers installed by a previous call before
    installing fresh ones.

    The ``craftgraph`` logger keeps its default ``propagate=True``, so
    records also reach any handler on the root logger (such as pytest's
    log capture). The app never adds handlers to the root logger, so this
    produces no duplicate output.

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

    # Console: rich-rendered, on stderr so stdout stays clean for CLI output.
    console_handler = RichHandler(
        level=level,
        console=Console(stderr=True),
        rich_tracebacks=True,
        show_path=True,
    )
    pkg_logger.addHandler(console_handler)
    _installed_handlers.append(console_handler)

    # File: plain text, WARNING and up -- errors and frame-budget violations,
    # the bug-report material. A log-file failure must never crash the app.
    target_dir = log_dir if log_dir is not None else app_dirs.log_dir()
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

    # Pretty rendering for unhandled exceptions.
    install_rich_traceback(show_locals=False)
