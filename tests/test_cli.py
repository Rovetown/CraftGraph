"""Tests for the CraftGraph CLI."""

from __future__ import annotations

import logging

from click.testing import CliRunner

from craftgraph.cli import main


def test_log_level_flag_configures_logging(monkeypatch, tmp_path):
    """--log-level resolves to the matching logging level and is passed
    to configure_logging."""
    captured: dict[str, object] = {}

    def _spy(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("craftgraph.log_setup.configure_logging", _spy)

    runner = CliRunner()
    result = runner.invoke(main, ["--log-level", "debug", "check", str(tmp_path)])

    assert result.exit_code == 0
    assert captured.get("level") == logging.DEBUG
