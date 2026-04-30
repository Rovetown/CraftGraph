"""Tests for craftgraph.perf_diag wall-clock measurement helpers."""

from __future__ import annotations

import pytest

from craftgraph import perf_diag


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
