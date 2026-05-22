"""Tests for craftgraph.log_setup."""

from __future__ import annotations

import logging

import pytest

from rich.logging import RichHandler


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
