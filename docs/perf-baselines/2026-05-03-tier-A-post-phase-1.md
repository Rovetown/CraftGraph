# Tier A Post-Phase-1 Baseline

**Date:** 2026-05-03
**Branch:** `feat/perf-phase-1` after Tasks 1-21 landed
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Machine:** Windows 11 Home 10.0.26200, dev mode (`uv run --extra qt`)
**Python:** 3.14
**Capture script:** `scripts/baseline_capture.py docs/perf-baselines/2026-05-03-post-snapshots`
**cProfile output:** `docs/perf-baselines/2026-05-03-post-snapshots/tier_a.prof`

## Wall-clock measurements

| Action                 | Pre-Phase-1 (ms) | Post-Phase-1 (ms) | Delta      | Notes                                                |
|------------------------|------------------|-------------------|------------|------------------------------------------------------|
| Folder load (Tier A)   | 8721.7           | 9128.2            | +406 (+5%) | within run-to-run jitter on a single sample          |
| HWND (USER) after load | 3272             | 3270              | -2         | identical                                            |
| GDI after load         | 1636             | 1634              | -2         | identical                                            |
| Widget count after     | 3144             | 3144              | 0          | identical                                            |

**Read:** Phase 1 cheap wins did not move the Tier A folder-load wall-clock. None
of the eight perf changes target the dominant cost (per-node Qt proxy-widget
construction). HWND counts and widget counts are unchanged because Phase 1
neither added nor removed widgets. Phase 1 still shipped value:

- `perf_diag.measure()` and `report_frame()` now log every long action and every
  frame-budget violation, so future regressions surface immediately.
- `mem_diag.snapshot_to_file()` complements the existing handle snapshot for bug
  reports.
- The watcher mtime fast-path and graph cycle cache eliminate redundant reparse
  / recompute work that does not show up in a one-shot Tier A folder-load
  profile but matters during ongoing edit sessions.
- `QSignalBlocker` over the bulk-load region prevents future signal listeners
  from accidentally fanning out per-node work.
- `--no-dev` smoke job and `--optimize 2` build flag harden the release path
  before any further perf work changes binary size.

## Profiler top hits (cumulative time, single Tier A folder load)

```
Total profile time: 9607.0 ms (cProfile overhead included)

  cumtime    pct   ncalls  function
  -------   ----   ------  --------
   8851 ms   92%        6  craftgraph/qt_gui.py:_create_file_tab
   7568 ms   79%        6  craftgraph/sync.py:populate_graph
   6627 ms   69%      160  NodeGraphQt/base/graph.py:create_node
   6061 ms   63%      160  craftgraph/qt_nodes.py:CraftGraphBaseNode.__init__
   5929 ms   62%      160  craftgraph/qt_nodes.py:_build_from_registry
   5716 ms   60%      807  craftgraph/qt_nodes.py:_create_widget_for_field
   4257 ms   44%      807  craftgraph/qt_nodes.py:_patched_set_custom_widget
   4164 ms   43%      807  QGraphicsProxyWidget.setWidget         <-- direct Qt cost
   4069 ms   42%      597  NodeGraphQt/nodes/base_node.py:add_text_input
   3891 ms   41%     2288  NodeGraphQt/qgraphics/node_base.py:_draw_node_horizontal
   3461 ms   36%     2288  NodeGraphQt/qgraphics/node_base.py:_align_widgets_horizontal
   3318 ms   35%    14580  NodeGraphQt/widgets/node_widgets.py:setTitleAlign
   3199 ms   33%    15876  QWidget.setStyleSheet                  <-- 15.8k calls, all from setTitleAlign
```

(See `docs/perf-baselines/2026-05-03-post-snapshots/tier_a.prof` for the full
profile, or load it with `pstats.Stats('...').sort_stats('cumulative').print_stats()`.)

## Phase 2 candidates -- ordered by profiler signal

The data is unambiguous: **per-node Qt widget construction dominates**, not
parsing or graph algorithms. Sequence Phase 2 against widget cost, not the
nominally-listed sections of TODO.md.

| Target                                                                | Cumulative cost | Approach                                                                                                                                                                              | TODO row    |
|-----------------------------------------------------------------------|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|
| `setStyleSheet` x15876 from `setTitleAlign` (NodeGraphQt internal)    | 3.2 s           | Cache the title stylesheet on the widget class so repeated `setTitleAlign` calls become no-ops when the value is unchanged. Patchable in CraftGraph; one-line guard in widget patcher. | 9.6 (entry) |
| `QGraphicsProxyWidget.setWidget` x807                                 | 4.2 s           | Floating-input refactor (drop proxy widgets entirely). High-cost rewrite of focus / autocomplete / undo / drag-drop -- own design cycle. ~90% widget reduction at Tier C.              | 9.6         |
| `_create_widget_for_field` x807 / `_build_from_registry` x160         | 5.7 s / 5.9 s   | Lazy widget construction: only build per-field widgets when the node enters the viewport or the user expands it. Defers cost from load to interaction.                                | 6.2         |
| `add_text_input` x597 (4.1 s) and `add_combo_menu` x131 (1.0 s)       | 5.1 s combined  | Same lazy-widgets target -- text inputs and combos are 90% of the per-field cost.                                                                                                      | 6.2         |
| `_align_widgets_horizontal` x2288 (3.5 s)                             | 3.5 s           | Same target: every widget added triggers a realign. Lazy widgets reduce calls; alternatively block during populate then realign once at the end.                                       | 6.2         |
| Cooperative time-slicing during `load_recipes` so UI does not freeze  | n/a             | Even if widget cost stays, slicing keeps the UI responsive (frame-budget log already shows ~3 s frames).                                                                               | 3.6         |

**Out of scope based on this profile:**

- Parser native-compilation ladder (4.1 / 9.3 / 9.4 / 9.5). Parsing is well
  under 1 s of the 9.6 s; even a 10x parser speedup would shave <1 s.
- Graph algorithms (cycle detection, classify_nodes). NetworkX work is sub-1 s
  here; rustworkx (9.9) would not move the needle at Tier A.
- Async I/O for file reads (9.2). The file scan is ms.

## Recommended Phase 2 order

1. **Quick patch:** stylesheet-cache guard on the `setTitleAlign` patch (small,
   low-risk, captures ~3 s).
2. **Lazy widgets (TODO 6.2):** scoped, reversible -- defers 5-6 s of widget
   cost to interaction time.
3. **QThread / time-slicing (TODO 3.1 / 3.6):** keep UI responsive during the
   remaining cost. Doesn't shrink total time, but kills the freeze.
4. **Floating-input refactor (TODO 9.6):** only after 1-3 land and Tier C is the
   real target. Major rewrite -- own design cycle.
