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


from PySide6 import QtWidgets


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
