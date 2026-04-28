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


# Per-scenario thresholds. Tuned loose initially; tighten in Phase 2.
THRESHOLDS = {
    "open_close_settings_x20": 100,
    "context_menu_x50": 50,
    "open_close_folder_x10": 200,
    "tab_switch_x30": 50,
    "watcher_rebuild_x10": 100,
}


@pytest.fixture(autouse=True)
def _skip_when_no_stress(request):
    if request.config.getoption("--no-stress"):
        pytest.skip("--no-stress flag set")


from pathlib import Path

from PySide6 import QtWidgets

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


def _delta_around(window, callable_):
    from craftgraph.hwnd_diag import take_snapshot

    QtWidgets.QApplication.processEvents()
    before = take_snapshot()
    callable_()
    QtWidgets.QApplication.processEvents()
    after = take_snapshot()
    return after.delta_against(before).gui_objects


class TestStressScaffold:
    def test_thresholds_are_defined(self):
        # Sentinel test: every scenario in this module must have a threshold.
        expected = {
            "open_close_settings_x20",
            "context_menu_x50",
            "open_close_folder_x10",
            "tab_switch_x30",
            "watcher_rebuild_x10",
        }
        assert set(THRESHOLDS.keys()) == expected


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

        delta = _delta_around(window, scenario)
        assert delta < THRESHOLDS["open_close_settings_x20"], (
            f"Settings dialog leaked {delta} HWNDs over 20 opens "
            f"(threshold {THRESHOLDS['open_close_settings_x20']})"
        )


class TestContextMenuStress:
    def test_context_menu_x50(self, window):
        # The graph viewer must exist before context menus can target it.
        assert window.graph is not None

        def scenario():
            for _ in range(50):
                window._spawn_main_context_menu_for_test()

        delta = _delta_around(window, scenario)
        assert delta < THRESHOLDS["context_menu_x50"], (
            f"Context menu leaked {delta} HWNDs over 50 spawns "
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

        delta = _delta_around(window, scenario)
        assert delta < THRESHOLDS["open_close_folder_x10"], (
            f"Folder open/close leaked {delta} HWNDs over 10 cycles "
            f"(threshold {THRESHOLDS['open_close_folder_x10']})"
        )
