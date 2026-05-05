"""Tests for craftgraph.perf_diag wall-clock measurement helpers."""

from __future__ import annotations

import logging
import time

import pytest

from craftgraph import perf_diag
from craftgraph.perf_diag import measure


def test_perf_snapshot_records_perf_counter_ns() -> None:
    snap = perf_diag.PerfSnapshot.now(action="test")
    assert isinstance(snap.perf_counter_ns, int)
    assert snap.perf_counter_ns > 0
    assert snap.action == "test"


def test_perf_snapshot_delta_ms_returns_float_milliseconds() -> None:
    a = perf_diag.PerfSnapshot.now(action="x")
    b = perf_diag.PerfSnapshot(
        action="x", perf_counter_ns=a.perf_counter_ns + 5_000_000
    )
    assert b.delta_ms_since(a) == pytest.approx(5.0, rel=0.01)


def test_measure_logs_action_and_delta(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="craftgraph.perf_diag")
    with measure("open_folder"):
        time.sleep(0.005)
    record = next(r for r in caplog.records if "action=open_folder" in r.message)
    assert "delta_ms=" in record.message
    delta_part = next(p for p in record.message.split() if p.startswith("delta_ms="))
    delta_ms = float(delta_part.split("=", 1)[1])
    assert delta_ms >= 4.0


def test_frame_budget_violation_logs_when_over_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="craftgraph.perf_diag")
    perf_diag.report_frame(frame_ms=50.0)
    assert any(
        "frame_budget_violation" in r.message and "frame_ms=50.000" in r.message
        for r in caplog.records
    )


def test_frame_under_budget_does_not_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="craftgraph.perf_diag")
    perf_diag.report_frame(frame_ms=10.0)
    assert not any("frame_budget_violation" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# install_logger
# ---------------------------------------------------------------------------


class TestInstallLogger:
    """install_logger() routes perf_diag output to file + stderr."""

    def teardown_method(self) -> None:
        # Reset state so other tests are not affected by our handler installs.
        perf_diag.install_logger(log_path=None, console=False)
        # Then detach the no-op handlers we just registered.
        for h in list(perf_diag._installed_handlers):
            perf_diag.logger.removeHandler(h)
        perf_diag._installed_handlers.clear()

    def test_install_logger_creates_file_handler_writing_action_lines(
        self, tmp_path
    ) -> None:
        log_path = tmp_path / "diag" / "perf.log"
        perf_diag.install_logger(log_path=log_path, console=False)

        with measure("test_action"):
            time.sleep(0.001)

        # Flush handler before reading.
        for h in perf_diag.logger.handlers:
            h.flush()

        text = log_path.read_text(encoding="utf-8")
        assert "action=test_action" in text
        assert "delta_ms=" in text

    def test_install_logger_is_idempotent(self, tmp_path) -> None:
        log_path = tmp_path / "perf.log"
        perf_diag.install_logger(log_path=log_path, console=False)
        perf_diag.install_logger(log_path=log_path, console=False)

        with measure("only_once"):
            pass
        for h in perf_diag.logger.handlers:
            h.flush()

        text = log_path.read_text(encoding="utf-8")
        # Exactly one record per call -- handler not duplicated.
        assert text.count("action=only_once") == 1

    def test_install_logger_disables_propagation(self, tmp_path) -> None:
        # Without propagate=False, perf_diag records would also reach the
        # root logger and could surprise unrelated consumers.
        perf_diag.install_logger(log_path=tmp_path / "perf.log", console=False)
        assert perf_diag.logger.propagate is False


class TestPaintStats:
    """record_paint accumulates per-class paint time; paint_stats reports it."""

    def setup_method(self):
        perf_diag.set_paint_recording(True)

    def teardown_method(self):
        perf_diag.set_paint_recording(False)
        perf_diag.reset_paint_stats()

    def test_record_paint_accumulates_total_and_count(self):
        perf_diag.record_paint("ModifiedRecipeNode", 1.5)
        perf_diag.record_paint("ModifiedRecipeNode", 2.5)
        perf_diag.record_paint("AliasRecipeNode", 0.5)
        stats = perf_diag.paint_stats()
        assert stats["ModifiedRecipeNode"].count == 2
        assert stats["ModifiedRecipeNode"].total_ms == 4.0
        assert stats["AliasRecipeNode"].count == 1

    def test_reset_paint_stats_clears_all(self):
        perf_diag.record_paint("X", 1.0)
        perf_diag.reset_paint_stats()
        assert perf_diag.paint_stats() == {}


class TestPaintRecordingToggle:
    """set_paint_recording / is_paint_recording gate the recording cost."""

    def teardown_method(self):
        perf_diag.set_paint_recording(False)
        perf_diag.reset_paint_stats()

    def test_recording_disabled_by_default(self):
        # Module must boot with recording off so per-paint instrumentation is
        # free in the default case.
        assert perf_diag.is_paint_recording() is False

    def test_record_paint_is_noop_when_disabled(self):
        perf_diag.set_paint_recording(False)
        perf_diag.record_paint("X", 1.0)
        assert perf_diag.paint_stats() == {}

    def test_record_paint_records_when_enabled(self):
        perf_diag.set_paint_recording(True)
        perf_diag.record_paint("X", 1.0)
        assert "X" in perf_diag.paint_stats()

    def test_toggle_off_stops_recording(self):
        perf_diag.set_paint_recording(True)
        perf_diag.record_paint("X", 1.0)
        perf_diag.set_paint_recording(False)
        perf_diag.record_paint("X", 99.0)
        # Second call must not have been counted.
        assert perf_diag.paint_stats()["X"].count == 1
