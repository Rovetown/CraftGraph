# Tier A Pre-Phase-2 Baseline

**Date:** 2026-05-04
**Branch:** `feat/perf-phase-2` @ initial commit (Phase 1 perf landed, no Phase 2 work yet)
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Machine:** Windows 11 Home 10.0.26200, dev mode (`uv run --extra qt`)
**Python:** 3.14
**Capture script:** `scripts/baseline_capture.py docs/perf-baselines/2026-05-04-pre-snapshots`
**cProfile output:** `docs/perf-baselines/2026-05-04-pre-snapshots/tier_a.prof`

## Wall-clock measurements

| Action                 | Phase 1 post (ms) | Phase 2 pre (ms) | Notes                                              |
|------------------------|-------------------|------------------|----------------------------------------------------|
| Folder load (Tier A)   | 9128.2            | 9290.6           | within run-to-run jitter on a single sample        |
| HWND (USER) after load | 3270              | 3270             | identical                                          |
| GDI after load         | 1634              | 1634             | identical                                          |
| Widget count after     | 3144              | 3145             | ~identical                                         |

Snapshot file: `docs/perf-baselines/2026-05-04-pre-snapshots/hwnd_post_load.txt`

## Profiler top hits (cumulative time, single Tier A folder load)

```
Total profile time: 7945.7 ms (cProfile overhead included)

  cumtime    pct   ncalls  function
  -------   ----   ------  --------
   7144 ms   90%        6  craftgraph/qt_gui.py:_create_file_tab
   6024 ms   76%        6  craftgraph/sync.py:populate_graph
   4810 ms   61%      160  NodeGraphQt/base/graph.py:create_node
   4760 ms   60%       41  craftgraph/sync.py:_create_recipe_node
   4257 ms   54%      160  NodeGraphQt/base/factory.py:create_node_instance
   4230 ms   53%      160  craftgraph/qt_nodes.py:CraftGraphBaseNode.__init__
   4091 ms   52%      160  craftgraph/qt_nodes.py:_build_from_registry
   4036 ms   51%     2288  NodeGraphQt/qgraphics/node_base.py:draw_node
   4029 ms   51%     2288  NodeGraphQt/qgraphics/node_base.py:_draw_node_horizontal
   3873 ms   49%      807  craftgraph/qt_nodes.py:_create_widget_for_field
   3593 ms   45%     2288  NodeGraphQt/qgraphics/node_base.py:_align_widgets_horizontal
   3443 ms   43%    14580  NodeGraphQt/widgets/node_widgets.py:setTitleAlign
   3322 ms   42%    15876  QWidget.setStyleSheet               <-- direct Qt cost
   3036 ms   38%       41  craftgraph/qt_nodes.py:1117 (subclass __init__)
   2745 ms   35%      597  NodeGraphQt/nodes/base_node.py:add_text_input
   2390 ms   30%      807  craftgraph/qt_nodes.py:_patched_set_custom_widget
   2295 ms   29%      807  QGraphicsProxyWidget.setWidget      <-- direct Qt cost
```

(See `docs/perf-baselines/2026-05-04-pre-snapshots/tier_a.prof` for the full
profile, or load it with `pstats.Stats('...').sort_stats('cumulative').print_stats()`.)

## Notes

- Numbers consistent with the Phase 1 post-baseline. The Phase 1 cheap wins
  did not change the dominant cost (per-node Qt proxy-widget construction).
- Phase 2 attacks the dominant hotspots:
  - `setStyleSheet` x15876 / `setTitleAlign` -- cache no-op restyles (~3.3 s).
  - `_create_widget_for_field` x807 / `_build_from_registry` -- defer to first paint.
  - `_create_file_tab` UI freeze -- cooperative time-slicing during `populate_graph`.
- Foundation extensions also land in Phase 2: live CPU/RSS readout
  (`proc_diag` + status bar), per-node paint timing (`record_paint`), and a
  Help > Show Perf Log dialog.
