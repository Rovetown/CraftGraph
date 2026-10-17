"""Tests for the WelcomeWidget (startup/welcome screen).

Requires Qt optional dependencies.
Run: uv run --extra qt pytest tests/test_welcome.py -v
"""

from __future__ import annotations


import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtWidgets


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
        "on_clear_recent": _noop,
        "show_on_startup": True,
    }
    defaults.update(kwargs)
    return WelcomeWidget(recent_entries or [], **defaults)


def _clear_button(widget: QtWidgets.QWidget) -> QtWidgets.QPushButton | None:
    """Locate the 'Clear' button in the recent-projects header."""
    for btn in widget.findChildren(QtWidgets.QPushButton):
        if btn.text().lower().startswith("clear"):
            return btn
    return None


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

    def test_recent_entry_click_fires_callback(self, qapp: QtWidgets.QApplication, qtbot, tmp_path: object) -> None:
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
        # Simulate mouse press through qtbot so the widget's event filters fire
        from PySide6.QtCore import QPoint, Qt

        qtbot.mousePress(items[0], Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
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


class TestClearRecent:
    """The welcome screen exposes a one-click 'Clear' for the recent list."""

    def test_clear_button_present_when_entries_exist(
        self, qapp: QtWidgets.QApplication, tmp_path: object,
    ) -> None:
        d = tmp_path / "ModA"
        d.mkdir()
        widget = _make_widget(
            qapp, recent_entries=_make_entries((str(d), "folder")),
        )
        btn = _clear_button(widget)
        assert btn is not None
        assert btn.isVisible() or btn.isEnabled()

    def test_clear_button_absent_or_disabled_when_no_entries(
        self, qapp: QtWidgets.QApplication,
    ) -> None:
        widget = _make_widget(qapp, recent_entries=[])
        btn = _clear_button(widget)
        # Either it is not rendered at all, or it is rendered + disabled.
        assert btn is None or not btn.isEnabled()

    def test_clear_button_fires_callback(
        self, qapp: QtWidgets.QApplication, tmp_path: object,
    ) -> None:
        d = tmp_path / "ModB"
        d.mkdir()
        fired: list[bool] = []
        widget = _make_widget(
            qapp,
            recent_entries=_make_entries((str(d), "folder")),
            on_clear_recent=lambda: fired.append(True),
        )
        btn = _clear_button(widget)
        assert btn is not None
        btn.click()
        assert fired == [True]

    def test_clear_rebuilds_recents_to_empty_state(
        self, qapp: QtWidgets.QApplication, tmp_path: object,
    ) -> None:
        """After Clear, the recent list re-renders as the empty-state message."""
        d = tmp_path / "ModC"
        d.mkdir()
        widget = _make_widget(
            qapp, recent_entries=_make_entries((str(d), "folder")),
        )
        btn = _clear_button(widget)
        assert btn is not None
        btn.click()
        labels = widget.findChildren(QtWidgets.QLabel)
        texts = [lb.text() for lb in labels]
        assert any("No recent" in t for t in texts)


class TestExternalLinks:
    """Right-column links must be real, browser-openable hyperlinks."""

    def _link_labels(self, widget: QtWidgets.QWidget) -> list[QtWidgets.QLabel]:
        """Return only the QLabels that carry an ``<a href="...">`` body."""
        return [
            lb for lb in widget.findChildren(QtWidgets.QLabel)
            if "<a href=" in lb.text()
        ]

    def test_each_link_opens_externally(self, qapp: QtWidgets.QApplication) -> None:
        widget = _make_widget(qapp)
        link_labels = self._link_labels(widget)
        from craftgraph.welcome import _LINKS

        assert len(link_labels) == len(_LINKS)
        for lb in link_labels:
            assert lb.openExternalLinks() is True, lb.text()

    def test_links_use_real_http_urls(self, qapp: QtWidgets.QApplication) -> None:
        """No leftover ``href="#"`` placeholders -- clicks must open the browser."""
        widget = _make_widget(qapp)
        for lb in self._link_labels(widget):
            html = lb.text()
            assert 'href="#"' not in html, html
            assert 'href="https://' in html, html

    def test_link_set_matches_module_constants(
        self, qapp: QtWidgets.QApplication,
    ) -> None:
        """Each declared (label, url) pair from ``_LINKS`` is rendered exactly once."""
        from craftgraph.welcome import _LINKS

        widget = _make_widget(qapp)
        rendered = [lb.text() for lb in self._link_labels(widget)]
        for label, url in _LINKS:
            assert any(label in html and url in html for html in rendered), (
                f"missing link for ({label!r}, {url!r}) in {rendered!r}"
            )
