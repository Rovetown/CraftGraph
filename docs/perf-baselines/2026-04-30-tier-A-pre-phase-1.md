# Tier A Pre-Phase-1 Baseline

**Date:** 2026-04-30
**Branch:** `feat/perf-phase-1` @ initial commit (HWND Phases 1-3 merged into master, no perf work yet)
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Machine:** Windows 11 Home 10.0.26200, dev mode (`uv run --extra qt`)
**Python:** 3.14
**Capture script:** `scripts/baseline_capture.py docs/perf-baselines/2026-04-30-pre-snapshots`

## Wall-clock measurements (manual)

| Action                 | Pre-Phase-1 | Notes                                                    |
|------------------------|-------------|----------------------------------------------------------|
| Folder load (Tier A)   | 8721.7 ms   | `win.load_recipes(...)` wall-clock around `processEvents` |
| HWND (USER) before     | 45          | take_snapshot pre-load                                   |
| HWND (USER) after      | 3272        | take_snapshot post-load (delta +3227)                    |
| GDI before             | 22          |                                                          |
| GDI after              | 1636        | delta +1614                                              |
| Widgets before         | 147         | `QApplication.allWidgets()`                              |
| Widgets after          | 3144        | delta +2997                                              |

Snapshot file: `docs/perf-baselines/2026-04-30-pre-snapshots/hwnd_post_load.txt`

## Notes

- No `perf_diag` / `mem_diag` modules exist yet; numbers are wall-clock and
  HWND only.
- Tier A folder load is the headline pain point (~8.7 s, blocking UI). HWND
  hardening (Phases 1-3) already landed; widget count post-load is bounded
  by the per-node proxy widgets that Phase 1 perf does not target.
- This baseline is the comparison point for the post-Phase-1 doc.
