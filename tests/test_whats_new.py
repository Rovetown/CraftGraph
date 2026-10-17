"""Tests for craftgraph.whats_new."""

from __future__ import annotations

import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from craftgraph import whats_new


def test_slides_for_known_version_returns_list() -> None:
    """0.1.0-alpha.1 ships a populated slide list."""
    slides = whats_new.slides_for("0.1.0-alpha.1")
    assert slides is not None
    assert len(slides) > 0


def test_slides_for_unknown_version_returns_none() -> None:
    assert whats_new.slides_for("999.99.99") is None


def test_should_show_first_time_for_known_version(monkeypatch, tmp_path) -> None:
    """Fresh install: setting absent -> should_show True for a known version."""
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    assert whats_new.should_show("0.1.0-alpha.1") is True


def test_should_show_false_for_unknown_version(monkeypatch, tmp_path) -> None:
    """No slides for the version -> should_show False even on fresh install."""
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    assert whats_new.should_show("999.99.99") is False


def test_mark_shown_persists_version(monkeypatch, tmp_path) -> None:
    """After mark_shown, should_show returns False for the same version."""
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    assert whats_new.should_show("0.1.0-alpha.1") is True
    whats_new.mark_shown("0.1.0-alpha.1")
    assert whats_new.should_show("0.1.0-alpha.1") is False


def test_mark_shown_one_version_does_not_silence_another(
    monkeypatch,
    tmp_path,
) -> None:
    """Marking 0.1.0-alpha.1 as seen does not affect a hypothetical 0.2.0."""
    from craftgraph import app_dirs

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    whats_new.mark_shown("0.1.0-alpha.1")
    # Inject a fake newer version's slides for the test.
    monkeypatch.setitem(
        whats_new.SLIDES_BY_VERSION,
        "0.2.0",
        list(whats_new.SLIDES_BY_VERSION["0.1.0-alpha.1"]),
    )
    assert whats_new.should_show("0.2.0") is True
