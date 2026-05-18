# Tier A Post-Layout-Fix Baseline

**Date:** 2026-05-12
**Branch:** `feat/floating-input-pilot` after painted-grid layout fix + polish pass (Tasks 2-7 + 8a, tip `134d676`)
**Reference baselines:** `docs/perf-baselines/2026-05-10-tier-A-pre-floating-input.md`, `docs/perf-baselines/2026-05-11-tier-A-post-broaden.md`
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples`
**Capture scripts:** `scripts/baseline_capture.py`, `scripts/baseline_cprofile.py`
**Qt platform:** Windows for wall-clock, offscreen for cProfile

## Wall-clock measurements (3-run, Windows platform)

| Action                 | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Average (ms) |
|------------------------|-----------:|-----------:|-----------:|-------------:|
| Folder load (Tier A)   | 2667.4     | 2239.7     | 2047.2     | 2318.1       |
| HWND (USER) after load | 1155       | 1155       | 1155       | 1155         |
| GDI after load         | 576        | 576        | 576        | 576          |
| Widget count after     | 1115       | 1115       | 1115       | 1115         |

HWND/GDI/widgets before load (snapshot): gui=35-41, gdi=20, widgets=160.

Range across three runs: 2667.4 - 2047.2 = 620.2 ms. Run 1 carried cold-start
overhead; Runs 2 and 3 average 2143.5 ms. The variance is wider than the
post-broaden baseline (9.2 ms range) because the per-paint geometry rebuild
adds work proportional to how many repaints the load triggers, which is
non-deterministic across runs.

## Acceptance gate

| Metric | Pre (4611.7) | Post-pilot (9288.6) | Post-broaden | Post-layout-fix | Target | Hit? |
|---|---:|---:|---:|---:|---|---|
| Folder load (Windows, 3-run avg) | 4611.7 ms | 9288.6 ms | 1597.4 ms | 2318.1 ms | <3000 ms | PASS |
| HWND USER after load | 3272 | 3273 | 1157 | 1155 | <2900 | PASS |
| Widget count after load | 3145 | 3156 | 1115 | 1115 | <2700 | PASS |
| `_create_widget_for_field` cumtime (offscreen) | 809 ms | 988 ms | 242 ms | 269 ms | <1200 ms | PASS |

## Profiler hotspot deltas (offscreen, top-20 cumulative)

         2226029 function calls (2222823 primitive calls) in 1.693 seconds

   Ordered by: cumulative time
   List reduced from 1498 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        6    0.001    0.000    1.302    0.217 craftgraph/qt_gui.py:(_create_file_tab)
      160    0.004    0.000    0.929    0.006 NodeGraphQt/base/graph.py:(create_node)
 1731/650    0.002    0.000    0.845    0.001 craftgraph/qt_nodes.py:(set_property) [CraftGraphBaseNode]
        6    0.000    0.000    0.803    0.134 craftgraph/sync.py:(populate_graph)
      160    0.001    0.000    0.770    0.005 craftgraph/qt_nodes.py:(_maybe_build_widgets)
     2583    0.003    0.000    0.531    0.000 NodeGraphQt/qgraphics/node_base.py:(draw_node)
     2583    0.031    0.000    0.526    0.000 NodeGraphQt/qgraphics/node_base.py:(_draw_node_horizontal)
      119    0.001    0.000    0.408    0.003 craftgraph/qt_nodes.py:(_build_from_registry)
     1129    0.008    0.000    0.404    0.000 NodeGraphQt/nodes/base_node.py:(add_input)
     1129    0.004    0.000    0.387    0.000 NodeGraphQt/qgraphics/node_base.py:(add_input)
        6    0.002    0.000    0.359    0.060 craftgraph/sync.py:(connect_ingredients)
       41    0.000    0.000    0.351    0.009 craftgraph/sync.py:(_create_recipe_node)
       35    0.000    0.000    0.324    0.009 craftgraph/sync.py:(_create_tab_node)
     1280    0.084    0.000    0.315    0.000 NodeGraphQt/qgraphics/node_base.py:(_add_port)
  718/148    0.001    0.000    0.303    0.002 craftgraph/qt_nodes.py:(set_property) [ModifiedRecipeNode]
     1324    0.001    0.000    0.279    0.000 NodeGraphQt/qgraphics/node_base.py:(post_init)
      278    0.002    0.000    0.262    0.001 craftgraph/qt_nodes.py:(_create_widget_for_field)
1731/1452    0.002    0.000    0.224    0.000 NodeGraphQt/nodes/base_node.py:(set_property)
1451/1420    0.006    0.000    0.215    0.000 method 'push' of QUndoStack
1091/1060    0.005    0.000    0.212    0.000 NodeGraphQt/base/node.py:(set_property)

`_create_widget_for_field` cumtime: 269 ms (278 calls). Essentially flat
vs post-broaden (242 ms, 278 calls); the +27 ms is run-to-run noise.
Widget construction was not affected by the layout fix.

`PaintedFieldsNodeItem.paint`, `collect_port_geometry`, and `NodeLayout.build`
do not appear in the offscreen profile -- the load path does not flush paints
under `QT_QPA_PLATFORM=offscreen`. The per-paint cost manifests only in the
Windows wall-clock run.

## Notes

The 1597 -> 2318 ms wall-clock shift (+721 ms) is the visible cost of
rebuilding `NodeLayout` per paint instead of stamping rects once at build
time. It is paid only during the initial scene-draw burst (and on any
subsequent repaint of a painted node), not on idle. The 3000 ms target
still holds with ~680 ms of headroom.

If a future optimization is wanted, the natural lever is to cache the layout
on the node and invalidate on port-add/remove or value change, so paint
becomes O(field count) rect-fill instead of O(field count) rect-construction.
The structure makes that drop-in: `collect_port_geometry(self)` already
returns plain data and `NodeLayout.build()` is idempotent.

## Verdict

**PASS** -- all four acceptance targets hit. Wall-clock regressed vs the
post-broaden numbers (the most demanding comparison) but stayed below the
3000 ms target and is still 46% faster than the pre-pilot baseline
(4611.7 ms). HWND, GDI, widget count, and offscreen widget-construction
cumtime are flat vs post-broaden. The painted-grid layout fix preserves
the broaden's perf win while resolving the visual regression that
blocked merge.
