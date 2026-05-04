"""Tests for craftgraph.proc_diag CPU/RSS process sampler."""

from __future__ import annotations

from craftgraph import proc_diag


def test_sample_returns_cpu_percent_and_rss_bytes():
    snap = proc_diag.sample()
    assert isinstance(snap.cpu_percent, float)
    assert isinstance(snap.rss_bytes, int)
    assert snap.rss_bytes > 0


def test_sample_repeated_calls_return_independent_snapshots():
    a = proc_diag.sample()
    b = proc_diag.sample()
    assert a is not b
