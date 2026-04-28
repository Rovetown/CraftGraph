"""HWND stress harness for Phase 1 diagnostics.

Each test runs a scenario N times against a real CraftGraphWindow and
asserts the GR_USEROBJECTS delta stays under a per-scenario threshold.
Skipped on non-Windows (the metric is undefined) and when ``--no-stress``
is passed for fast local iteration. Thresholds intentionally start
loose; they ratchet down as Phase 2 fixes land.

Run on Windows:  uv run --extra qt pytest tests/test_hwnd_stress.py -v
Skip during dev:  uv run --extra qt pytest --no-stress
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="HWND metric is Windows-only"),
]


# Per-scenario thresholds. Tuned loose initially; tighten as Phase 2 fixes land.
THRESHOLDS = {
    "open_close_settings_x20": 100,
    "context_menu_x50": 50,
    "open_close_folder_x10": 200,
    "tab_switch_x30": 50,
    "watcher_rebuild_x10": 100,
}

# Widget-count thresholds. The Settings dialog leak surfaced as widget
# growth long before USER object growth, because most settings sub-widgets
# are non-toplevel. Keep both so future leaks are caught regardless of
# which counter they show up in.
WIDGET_THRESHOLDS = {
    "open_close_settings_x20": 200,
    "context_menu_x50": 100,
    "open_close_folder_x10": 500,
    "tab_switch_x30": 100,
    "watcher_rebuild_x10": 200,
}


@pytest.fixture(autouse=True)
def _skip_when_no_stress(request):
    if request.config.getoption("--no-stress"):
        pytest.skip("--no-stress flag set")


from pathlib import Path

from PySide6 import QtCore, QtWidgets

# Smallest reference folder with multiple block types (3 .txt files).
SAMPLE_FOLDER = (
    Path(__file__).resolve().parent.parent
    / "craftgraph"
    / "cc3_reference_files"
    / "original-source"
    / "CustomCraft3"
    / "SampleFiles"
    / "EquipmentSalvage"
)


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    from craftgraph import app_dirs
    from craftgraph.qt_gui import CraftGraphWindow

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_dirs, "log_dir", lambda: tmp_path)
    return CraftGraphWindow()


def _drain_deferred_delete():
    """Pump the deferred-delete queue so widget counts measure convergence."""
    QtWidgets.QApplication.processEvents()
    QtWidgets.QApplication.sendPostedEvents(
        None, QtCore.QEvent.Type.DeferredDelete,
    )
    QtWidgets.QApplication.processEvents()


def _delta_around(window, callable_):
    from craftgraph.hwnd_diag import take_snapshot

    _drain_deferred_delete()
    before = take_snapshot()
    callable_()
    _drain_deferred_delete()
    after = take_snapshot()
    return after.delta_against(before)


class TestStressScaffold:
    def test_thresholds_are_defined(self):
        # Sentinel test: every scenario in this module must have an HWND threshold.
        expected = {
            "open_close_settings_x20",
            "context_menu_x50",
            "open_close_folder_x10",
            "tab_switch_x30",
            "watcher_rebuild_x10",
        }
        assert set(THRESHOLDS.keys()) == expected
        assert set(WIDGET_THRESHOLDS.keys()) == expected


class TestSettingsDialogStress:
    def test_open_close_settings_x20(self, window, monkeypatch):
        from craftgraph.qt_gui import _SettingsDialog

        # Auto-accept each dialog instead of blocking. Both `exec` and the
        # deprecated `exec_` are stubbed because the real handler still uses
        # the legacy form.
        monkeypatch.setattr(_SettingsDialog, "exec", lambda self: 1)
        monkeypatch.setattr(_SettingsDialog, "exec_", lambda self: 1)

        def scenario():
            for _ in range(20):
                window._on_settings()

        delta_snap = _delta_around(window, scenario)
        assert delta_snap.gui_objects < THRESHOLDS["open_close_settings_x20"], (
            f"Settings dialog leaked {delta_snap.gui_objects} HWNDs over 20 opens "
            f"(threshold {THRESHOLDS['open_close_settings_x20']})"
        )
        assert delta_snap.widget_count < WIDGET_THRESHOLDS["open_close_settings_x20"], (
            f"Settings dialog leaked {delta_snap.widget_count} widgets over 20 opens "
            f"(threshold {WIDGET_THRESHOLDS['open_close_settings_x20']})"
        )


class TestContextMenuStress:
    def test_context_menu_x50(self, window):
        # The graph viewer must exist before context menus can target it.
        assert window.graph is not None

        def scenario():
            for _ in range(50):
                window._spawn_main_context_menu_for_test()

        delta_snap = _delta_around(window, scenario)
        assert delta_snap.gui_objects < THRESHOLDS["context_menu_x50"], (
            f"Context menu leaked {delta_snap.gui_objects} HWNDs over 50 spawns "
            f"(threshold {THRESHOLDS['context_menu_x50']})"
        )


class TestFolderOpenCloseStress:
    def test_open_close_folder_x10(self, window):
        assert SAMPLE_FOLDER.is_dir(), f"Sample folder missing: {SAMPLE_FOLDER}"

        def scenario():
            for _ in range(10):
                window.load_recipes(SAMPLE_FOLDER)
                # `_tear_down_tabs` mirrors what users see when they switch
                # folders -- clears the per-file tab state without re-parsing.
                window._tear_down_tabs()

        delta_snap = _delta_around(window, scenario)
        assert delta_snap.gui_objects < THRESHOLDS["open_close_folder_x10"], (
            f"Folder open/close leaked {delta_snap.gui_objects} HWNDs over 10 cycles "
            f"(threshold {THRESHOLDS['open_close_folder_x10']})"
        )


class TestTabSwitchStress:
    def test_tab_switch_x30(self, window):
        window.load_recipes(SAMPLE_FOLDER)
        # Need at least 2 file tabs to make tab switching meaningful.
        if len(window._file_tabs) < 2:
            pytest.skip("Sample folder has fewer than 2 files")

        tab_bar = window._tab_bar  # QTabBar driving _graph_stack/_editor_stack
        n_tabs = tab_bar.count()

        def scenario():
            for i in range(30):
                tab_bar.setCurrentIndex(i % n_tabs)

        delta_snap = _delta_around(window, scenario)
        assert delta_snap.gui_objects < THRESHOLDS["tab_switch_x30"], (
            f"Tab switch leaked {delta_snap.gui_objects} HWNDs over 30 switches "
            f"(threshold {THRESHOLDS['tab_switch_x30']})"
        )


class TestWatcherRebuildStress:
    def test_watcher_rebuild_x10(self, window):
        window.load_recipes(SAMPLE_FOLDER)
        if not window._file_tabs:
            pytest.skip("Sample folder did not yield any file tabs")

        # Trigger the watcher rebuild handler directly so the test does not
        # depend on real filesystem event timing. The handler signature takes
        # the cycles list (here empty -- no cycles in EquipmentSalvage).
        def scenario():
            for _ in range(10):
                window._on_watcher_rebuild([])

        delta_snap = _delta_around(window, scenario)
        assert delta_snap.gui_objects < THRESHOLDS["watcher_rebuild_x10"], (
            f"Watcher rebuild leaked {delta_snap.gui_objects} HWNDs over 10 cycles "
            f"(threshold {THRESHOLDS['watcher_rebuild_x10']})"
        )
