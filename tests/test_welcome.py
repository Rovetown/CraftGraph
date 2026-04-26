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


class TestUIScalePropagation:
    """Hardcoded font-size stylesheets respect the active UI scale at construction."""

    def test_title_font_size_scales(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.theme import ThemeColors, active_theme, set_active_theme

        original = active_theme()
        try:
            set_active_theme(ThemeColors(ui_scale=200))
            widget = _make_widget(qapp)
            titles = [
                lbl
                for lbl in widget.findChildren(QtWidgets.QLabel)
                if lbl.text() == "CraftGraph"
            ]
            assert titles, "expected a CraftGraph title label"
            # Base 20pt at 200% should produce a stylesheet referencing 40pt.
            assert "font-size: 40pt" in titles[0].styleSheet()
        finally:
            set_active_theme(original)


from craftgraph.recent import RecentEntry


def _make_entries(*paths_and_types: tuple[str, str]) -> list[RecentEntry]:
    """Helper: list of RecentEntry from (path, type) tuples."""
    return [
        RecentEntry(path=p, entry_type=t, timestamp="2026-03-31T12:00:00")
        for p, t in paths_and_types
    ]


class TestRecentEntries:
    def test_entries_shown_as_labels(self, qapp: QtWidgets.QApplication, tmp_path: object) -> None:
        d = tmp_path / "MyMod"
        d.mkdir()
        entries = _make_entries((str(d), "folder"))
        widget = _make_widget(qapp, recent_entries=entries)
        labels = widget.findChildren(QtWidgets.QLabel)
        texts = [lb.text() for lb in labels]
        assert any("MyMod" in t for t in texts)

    def test_empty_state_message(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp, recent_entries=[])
        labels = widget.findChildren(QtWidgets.QLabel)
        texts = [lb.text() for lb in labels]
        assert any("No recent" in t for t in texts)

    def test_stale_entry_has_strikethrough(self, qapp: QtWidgets.QApplication) -> None:
        entries = _make_entries(("/nonexistent/path/FakeProject", "folder"))
        widget = _make_widget(qapp, recent_entries=entries)
        from craftgraph.welcome import _RecentEntryItem

        items = widget.findChildren(_RecentEntryItem)
        assert len(items) == 1
        assert items[0]._stale is True


class TestCallbacks:
    def test_new_project_button_fires_callback(self, qapp: QtWidgets.QApplication) -> None:
        fired: list[str] = []
        widget = _make_widget(qapp, on_new_project=lambda: fired.append("new"))
        btn = [b for b in widget.findChildren(QtWidgets.QPushButton) if b.text() == "New Project"][0]
        btn.click()
        assert fired == ["new"]

    def test_open_folder_button_fires_callback(self, qapp: QtWidgets.QApplication) -> None:
        fired: list[str] = []
        widget = _make_widget(qapp, on_open_folder=lambda: fired.append("folder"))
        btn = [b for b in widget.findChildren(QtWidgets.QPushButton) if b.text() == "Open Folder"][0]
        btn.click()
        assert fired == ["folder"]

    def test_open_project_button_fires_callback(self, qapp: QtWidgets.QApplication) -> None:
        fired: list[str] = []
        widget = _make_widget(qapp, on_open_project=lambda: fired.append("proj"))
        btn = [b for b in widget.findChildren(QtWidgets.QPushButton) if b.text() == "Open Project"][0]
        btn.click()
        assert fired == ["proj"]

    def test_recent_entry_click_fires_callback(self, qapp: QtWidgets.QApplication, tmp_path: object) -> None:
        d = tmp_path / "TestMod"
        d.mkdir()
        fired: list[tuple[str, str]] = []
        entries = _make_entries((str(d), "folder"))
        widget = _make_widget(
            qapp,
            recent_entries=entries,
            on_open_recent=lambda path, etype: fired.append((path, etype)),
        )
        from craftgraph.welcome import _RecentEntryItem

        items = widget.findChildren(_RecentEntryItem)
        assert len(items) == 1
        # Simulate mouse press
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QMouseEvent, Qt

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPoint(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        items[0].mousePressEvent(event)
        assert fired == [(str(d), "folder")]

    def test_startup_checkbox_fires_callback(self, qapp: QtWidgets.QApplication) -> None:
        toggled: list[bool] = []
        widget = _make_widget(
            qapp,
            on_startup_toggle=lambda checked: toggled.append(checked),
            show_on_startup=True,
        )
        cb = widget.findChildren(QtWidgets.QCheckBox)[0]
        cb.setChecked(True)  # "Don't show" = checked
        assert toggled == [True]
