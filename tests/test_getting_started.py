"""Tests for craftgraph.getting_started."""

from __future__ import annotations

import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from craftgraph import getting_started


def test_slides_module_constant_is_populated() -> None:
    assert len(getting_started.SLIDES) > 0


def test_show_on_startup_default_is_true(monkeypatch, tmp_path) -> None:
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    assert getting_started.should_show_on_startup() is True


def test_show_on_new_project_default_is_true(monkeypatch, tmp_path) -> None:
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    assert getting_started.should_show_on_new_project() is True


def test_set_show_on_startup_persists(monkeypatch, tmp_path) -> None:
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    getting_started.set_show_on_startup(False)
    assert getting_started.should_show_on_startup() is False
    getting_started.set_show_on_startup(True)
    assert getting_started.should_show_on_startup() is True


def test_set_show_on_new_project_persists(monkeypatch, tmp_path) -> None:
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    getting_started.set_show_on_new_project(False)
    assert getting_started.should_show_on_new_project() is False
