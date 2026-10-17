"""Tests for craftgraph.log_setup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from rich.logging import RichHandler

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _restore_craftgraph_logger():
    """Strip handlers off the shared craftgraph logger after each test."""
    yield
    from craftgraph import log_setup

    pkg = logging.getLogger("craftgraph")
    for handler in list(pkg.handlers):
        pkg.removeHandler(handler)
        handler.close()
    pkg.setLevel(logging.NOTSET)
    log_setup._installed_handlers.clear()


def test_installs_one_rich_and_one_file_handler(tmp_path):
    from craftgraph.log_setup import configure_logging

    configure_logging(level=logging.INFO, log_dir=tmp_path)
    pkg = logging.getLogger("craftgraph")

    rich_handlers = [h for h in pkg.handlers if isinstance(h, RichHandler)]
    file_handlers = [h for h in pkg.handlers if isinstance(h, logging.FileHandler)]
    assert len(rich_handlers) == 1
    assert len(file_handlers) == 1
    assert file_handlers[0].level == logging.WARNING
    assert pkg.level == logging.INFO


def test_is_idempotent(tmp_path):
    from craftgraph.log_setup import configure_logging

    configure_logging(level=logging.INFO, log_dir=tmp_path)
    configure_logging(level=logging.DEBUG, log_dir=tmp_path)
    pkg = logging.getLogger("craftgraph")

    assert len(pkg.handlers) == 2  # not duplicated
    assert pkg.level == logging.DEBUG


def test_warning_reaches_log_file(tmp_path):
    from craftgraph.log_setup import configure_logging

    configure_logging(level=logging.INFO, log_dir=tmp_path)
    logging.getLogger("craftgraph.sometest").warning("disk on fire")

    log_file = tmp_path / "craftgraph.log"
    assert log_file.exists()
    assert "disk on fire" in log_file.read_text(encoding="utf-8")


def test_info_does_not_reach_log_file(tmp_path):
    from craftgraph.log_setup import configure_logging

    configure_logging(level=logging.INFO, log_dir=tmp_path)
    logging.getLogger("craftgraph.sometest").info("just chatter")

    log_file = tmp_path / "craftgraph.log"
    contents = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert "just chatter" not in contents


def test_unwritable_log_dir_does_not_raise(tmp_path, monkeypatch):
    from craftgraph import log_setup

    # Capture the real FileHandler class before monkeypatching.
    real_file_handler = logging.FileHandler

    def _boom(*_args, **_kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(log_setup.logging, "FileHandler", _boom)
    # Must fall back to console-only, never propagate the error.
    log_setup.configure_logging(level=logging.INFO, log_dir=tmp_path)

    pkg = logging.getLogger("craftgraph")
    assert any(isinstance(h, RichHandler) for h in pkg.handlers)
    assert not any(isinstance(h, real_file_handler) for h in pkg.handlers)


def test_cleanup_old_logs_drops_files_past_cutoff(tmp_path):
    """Files mtime'd > max_age_days ago are deleted; recent ones survive."""
    import os
    import time

    from craftgraph.log_setup import cleanup_old_logs

    old_log = tmp_path / "craftgraph.log"
    old_log.write_text("ancient", encoding="utf-8")
    recent_log = tmp_path / "hwnd.log"
    recent_log.write_text("yesterday", encoding="utf-8")
    dump = tmp_path / "modules-gui.txt"
    dump.write_text("dump", encoding="utf-8")
    foreign = tmp_path / "user-notes.md"
    foreign.write_text("user file", encoding="utf-8")

    # Backdate the "old" files; leave the others at "now".
    long_ago = time.time() - 30 * 86400
    os.utime(old_log, (long_ago, long_ago))
    os.utime(dump, (long_ago, long_ago))

    removed = cleanup_old_logs(tmp_path, max_age_days=7)

    assert removed == 2
    assert not old_log.exists()
    assert not dump.exists()
    assert recent_log.exists()
    # Files not matching the cleanup patterns are preserved even when stale.
    foreign_long_ago = tmp_path / "stale-but-foreign.txt"
    foreign_long_ago.write_text("stale", encoding="utf-8")
    os.utime(foreign_long_ago, (long_ago, long_ago))
    cleanup_old_logs(tmp_path, max_age_days=7)
    assert foreign_long_ago.exists()
    assert foreign.exists()


def test_cleanup_old_logs_no_dir_is_noop(tmp_path):
    """Missing log dir returns 0 and does not raise."""
    from craftgraph.log_setup import cleanup_old_logs

    missing = tmp_path / "does-not-exist"
    assert cleanup_old_logs(missing) == 0


def test_cleanup_old_logs_handles_diagnostics_subdir(tmp_path):
    """Files under ``diagnostics/`` (perf.log) are also pruned when stale."""
    import os
    import time

    from craftgraph.log_setup import cleanup_old_logs

    (tmp_path / "diagnostics").mkdir()
    perf = tmp_path / "diagnostics" / "perf.log"
    perf.write_text("ancient perf data", encoding="utf-8")
    long_ago = time.time() - 30 * 86400
    os.utime(perf, (long_ago, long_ago))

    cleanup_old_logs(tmp_path, max_age_days=7)
    assert not perf.exists()


def test_configure_logging_invokes_cleanup(tmp_path, monkeypatch):
    """``configure_logging`` calls ``cleanup_old_logs`` for the target dir."""
    import logging as _logging

    from craftgraph import log_setup

    seen: list[Path] = []
    monkeypatch.setattr(
        log_setup,
        "cleanup_old_logs",
        lambda d, **_kw: seen.append(d) or 0,
    )
    log_setup.configure_logging(level=_logging.INFO, log_dir=tmp_path)
    assert seen == [tmp_path]


def test_fallback_when_rich_is_missing(tmp_path, monkeypatch):
    """When rich is not installed, install a stdlib StreamHandler instead.

    Simulated by monkeypatching ``_import_rich`` to return the
    all-``None`` sentinel that the real helper returns on ImportError.
    """
    from craftgraph import log_setup

    monkeypatch.setattr(log_setup, "_import_rich", lambda: (None, None, None))
    log_setup.configure_logging(level=logging.INFO, log_dir=tmp_path)

    pkg = logging.getLogger("craftgraph")
    rich_handlers = [h for h in pkg.handlers if isinstance(h, RichHandler)]
    assert rich_handlers == []
    # A bare StreamHandler is the fallback; FileHandler is a subclass of
    # StreamHandler so filter it out before asserting.
    stream_handlers = [
        h
        for h in pkg.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].level == logging.INFO
