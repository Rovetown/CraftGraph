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
