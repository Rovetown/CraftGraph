"""Tests for craftgraph.hwnd_diag handle-counting helpers."""

from __future__ import annotations

import sys

import pytest

from PySide6 import QtWidgets


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestHandleCounters:
    def test_gui_handle_count_returns_int(self):
        from craftgraph.hwnd_diag import gui_handle_count

        result = gui_handle_count()
        assert isinstance(result, int)
        assert result >= 0

    def test_gdi_handle_count_returns_int(self):
        from craftgraph.hwnd_diag import gdi_handle_count

        result = gdi_handle_count()
        assert isinstance(result, int)
        assert result >= 0

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only metric")
    def test_gui_handle_count_is_positive_on_windows(self):
        from craftgraph.hwnd_diag import gui_handle_count

        # Even a bare process has a few USER objects allocated.
        assert gui_handle_count() > 0

    @pytest.mark.skipif(sys.platform == "win32", reason="non-Windows fallback")
    def test_gui_handle_count_is_zero_off_windows(self):
        from craftgraph.hwnd_diag import gui_handle_count

        assert gui_handle_count() == 0


class TestHandleSnapshot:
    def test_snapshot_fields(self):
        from craftgraph.hwnd_diag import HandleSnapshot, take_snapshot

        snap = take_snapshot()
        assert isinstance(snap, HandleSnapshot)
        assert isinstance(snap.gui_objects, int)
        assert isinstance(snap.gdi_objects, int)
        assert isinstance(snap.widget_count, int)

    def test_snapshot_delta_against(self):
        from craftgraph.hwnd_diag import HandleSnapshot

        before = HandleSnapshot(gui_objects=100, gdi_objects=50, widget_count=10)
        after = HandleSnapshot(gui_objects=130, gdi_objects=55, widget_count=14)
        delta = after.delta_against(before)
        assert delta.gui_objects == 30
        assert delta.gdi_objects == 5
        assert delta.widget_count == 4


class TestWidgetInventory:
    def test_widget_inventory_returns_class_counts(self, qapp):
        from PySide6 import QtWidgets

        from craftgraph.hwnd_diag import widget_inventory

        held: list[QtWidgets.QWidget] = []
        try:
            for _ in range(3):
                held.append(QtWidgets.QPushButton())
            inv = widget_inventory()
            assert inv.get("QPushButton", 0) >= 3
        finally:
            for w in held:
                w.deleteLater()
            qapp.processEvents()

    def test_widget_inventory_no_qapp(self, monkeypatch):
        from PySide6 import QtWidgets

        from craftgraph import hwnd_diag

        monkeypatch.setattr(QtWidgets.QApplication, "instance", staticmethod(lambda: None))
        assert hwnd_diag.widget_inventory() == {}


class TestMeasureContextManager:
    def test_measure_yields_before_snapshot(self):
        from craftgraph.hwnd_diag import HandleSnapshot, measure

        with measure("noop", log=False) as ctx:
            assert isinstance(ctx.before, HandleSnapshot)
        # After the block, .after and .delta are populated.
        assert isinstance(ctx.after, HandleSnapshot)
        assert ctx.delta.gui_objects == ctx.after.gui_objects - ctx.before.gui_objects

    def test_measure_records_action_name(self):
        from craftgraph.hwnd_diag import measure

        with measure("custom_action", log=False) as ctx:
            pass
        assert ctx.action == "custom_action"

    def test_measure_writes_log_line_when_logging_enabled(self, tmp_path, monkeypatch):
        from craftgraph import app_dirs, hwnd_diag

        monkeypatch.setattr(app_dirs, "log_dir", lambda: tmp_path)
        with hwnd_diag.measure("dialog_open"):
            pass
        log_path = tmp_path / "hwnd.log"
        assert log_path.is_file()
        contents = log_path.read_text(encoding="utf-8")
        assert "action=dialog_open" in contents
        assert "delta=" in contents

    def test_measure_does_not_write_log_when_disabled(self, tmp_path, monkeypatch):
        from craftgraph import app_dirs, hwnd_diag

        monkeypatch.setattr(app_dirs, "log_dir", lambda: tmp_path)
        with hwnd_diag.measure("silent", log=False):
            pass
        assert not (tmp_path / "hwnd.log").exists()


class TestThresholdLogger:
    def test_install_logger_attaches_callback(self):
        from craftgraph import hwnd_diag

        events: list[tuple[str, int]] = []
        hwnd_diag.install_logger(
            threshold=10,
            on_threshold_exceeded=lambda action, delta: events.append((action, delta)),
        )
        try:
            with hwnd_diag.measure("ok", log=False):
                pass
            assert events == []  # no widgets created -> no threshold breach
        finally:
            hwnd_diag.install_logger(threshold=10, on_threshold_exceeded=None)


class TestSnapshotToFile:
    def test_snapshot_to_file_writes_summary(self, qapp, tmp_path):
        from craftgraph.hwnd_diag import snapshot_to_file

        out = tmp_path / "snap.txt"
        path = snapshot_to_file(out)
        assert path == out
        text = out.read_text(encoding="utf-8")
        assert "gui_objects=" in text
        assert "gdi_objects=" in text
        assert "widget_count=" in text
        assert "Top widget classes:" in text

    def test_snapshot_to_file_default_path(self, qapp, tmp_path, monkeypatch):
        from craftgraph import app_dirs, hwnd_diag

        monkeypatch.setattr(app_dirs, "log_dir", lambda: tmp_path)
        path = hwnd_diag.snapshot_to_file()
        assert path.parent == tmp_path / "diagnostics"
        assert path.exists()
        assert path.name.startswith("hwnd_")
        assert path.suffix == ".txt"
