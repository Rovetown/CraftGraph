"""Tests for the WelcomeWidget (startup/welcome screen).

Requires Qt optional dependencies.
Run: uv run --extra qt pytest tests/test_welcome.py -v
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtWidgets


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


def _noop(*_args: object) -> None:
    """No-op callback for tests that don't check callbacks."""


def _make_widget(
    qapp: QtWidgets.QApplication,
    recent_entries: list | None = None,
    **kwargs: object,
) -> QtWidgets.QWidget:
    from craftgraph.welcome import WelcomeWidget

    defaults: dict[str, object] = {
        "on_open_recent": _noop,
        "on_new_project": _noop,
        "on_open_folder": _noop,
        "on_open_project": _noop,
        "on_startup_toggle": _noop,
        "show_on_startup": True,
    }
    defaults.update(kwargs)
    return WelcomeWidget(recent_entries or [], **defaults)


class TestWelcomeConstruction:
    def test_creates_without_error(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        assert widget is not None

    def test_is_qwidget(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        assert isinstance(widget, QtWidgets.QWidget)

    def test_has_title_label(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        labels = widget.findChildren(QtWidgets.QLabel)
        texts = [label.text() for label in labels]
        assert any("CraftGraph" in t for t in texts)

    def test_has_version_label(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        labels = widget.findChildren(QtWidgets.QLabel)
        texts = [label.text() for label in labels]
        assert any("0." in t for t in texts)  # version string like v0.1.0

    def test_has_three_action_buttons(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        buttons = widget.findChildren(QtWidgets.QPushButton)
        button_texts = [b.text() for b in buttons]
        assert "New Project" in button_texts
        assert "Open Folder" in button_texts
        assert "Open Project" in button_texts

    def test_has_startup_checkbox(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        checkboxes = widget.findChildren(QtWidgets.QCheckBox)
        assert len(checkboxes) == 1
        assert "startup" in checkboxes[0].text().lower()

    def test_checkbox_reflects_show_on_startup_true(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp, show_on_startup=True)
        cb = widget.findChildren(QtWidgets.QCheckBox)[0]
        assert not cb.isChecked()  # "Don't show" unchecked means DO show

    def test_checkbox_reflects_show_on_startup_false(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp, show_on_startup=False)
        cb = widget.findChildren(QtWidgets.QCheckBox)[0]
        assert cb.isChecked()  # "Don't show" checked means DON'T show
