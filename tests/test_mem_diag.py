"""Tests for craftgraph.mem_diag tracemalloc snapshot helper."""

from __future__ import annotations

import tracemalloc
from pathlib import Path

from craftgraph import mem_diag


def test_snapshot_to_file_writes_top_allocations(tmp_path: Path) -> None:
    tracemalloc.start()
    try:
        # Allocate something so the snapshot has content.
        _payload = ["x" * 1024 for _ in range(100)]  # noqa: F841
        out = tmp_path / "mem.txt"
        mem_diag.snapshot_to_file(out, top_n=5)
        text = out.read_text(encoding="utf-8")
        assert "Top 5 allocations" in text
    finally:
        tracemalloc.stop()


def test_snapshot_to_file_handles_tracemalloc_disabled(tmp_path: Path) -> None:
    out = tmp_path / "mem.txt"
    mem_diag.snapshot_to_file(out, top_n=5)
    text = out.read_text(encoding="utf-8")
    assert "tracemalloc disabled" in text


def test_snapshot_to_file_creates_parent_dirs(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "mem.txt"
    mem_diag.snapshot_to_file(out, top_n=5)
    assert out.exists()
