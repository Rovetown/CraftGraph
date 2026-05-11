# Tier A Post-Broaden Baseline

**Date:** 2026-05-11
**Branch:** `feat/floating-input-pilot` after Tasks 1-6 of the broaden plan (tip `3c46b01`)
**Reference baseline:** `docs/perf-baselines/2026-05-10-tier-A-pre-floating-input.md`
**Predecessor (pre-broaden):** `docs/perf-baselines/2026-05-11-tier-A-post-floating-input-pilot.md`
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples`
**Capture scripts:** `scripts/baseline_capture.py`, `scripts/baseline_cprofile.py`
**Qt platform:** Windows for wall-clock, offscreen for cProfile

## Wall-clock measurements (3-run average, Windows platform)

| Action                 | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Average (ms) |
|------------------------|-----------:|-----------:|-----------:|-------------:|
| Folder load (Tier A)   | 1603.0     | 1593.8     | 1595.5     | 1597.4       |
| HWND (USER) after load | 1157       | 1157       | 1157       | 1157         |
| GDI after load         | 576        | 576        | 576        | 576          |
| Widget count after     | 1115       | 1115       | 1115       | 1115         |

HWND/GDI/widgets before load (for reference): gui=39, gdi=20, widgets=160 (run-1 snapshot).

Range across three runs: 1603.0 - 1593.8 = 9.2 ms -- no extra runs needed.

## Acceptance gate

| Metric | Pre (4611.7) | Post-pilot (9288.6) | Post-broaden | Target | Hit? |
|---|---:|---:|---:|---|---|
| Folder load (Windows, 3-run avg) | 4611.7 ms | 9288.6 ms | 1597.4 ms | <3000 ms | PASS |
| HWND USER after load | 3272 | 3273 | 1157 | <2900 | PASS |
| Widget count after load | 3145 | 3156 | 1115 | <2700 | PASS |
| `_create_widget_for_field` cumtime (offscreen) | 809 ms | 988 ms | 242 ms | <1200 ms | PASS |

## Profiler hotspot deltas (offscreen, top-20 cumulative)

         2227922 function calls (2224748 primitive calls) in 1.563 seconds

   Ordered by: cumulative time
   List reduced from 1499 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        6    0.001    0.000    1.201    0.200 craftgraph/qt_gui.py:(_create_file_tab)
      160    0.003    0.000    0.852    0.005 NodeGraphQt/base/graph.py:(create_node)
 1729/648    0.001    0.000    0.788    0.001 craftgraph/qt_nodes.py:(set_property) [CraftGraphBaseNode]
        6    0.000    0.000    0.741    0.123 craftgraph/sync.py:(populate_graph)
      160    0.000    0.000    0.719    0.004 craftgraph/qt_nodes.py:(_maybe_build_widgets)
     2583    0.003    0.000    0.498    0.000 NodeGraphQt/qgraphics/node_base.py:(draw_node)
     2583    0.029    0.000    0.495    0.000 NodeGraphQt/qgraphics/node_base.py:(_draw_node_horizontal)
      119    0.001    0.000    0.382    0.003 craftgraph/qt_nodes.py:(_build_from_registry)
     1129    0.008    0.000    0.379    0.000 NodeGraphQt/nodes/base_node.py:(add_input)
     1129    0.004    0.000    0.362    0.000 NodeGraphQt/qgraphics/node_base.py:(add_input)
        6    0.001    0.000    0.329    0.055 craftgraph/sync.py:(connect_ingredients)
       41    0.000    0.000    0.323    0.008 craftgraph/sync.py:(_create_recipe_node)
       35    0.000    0.000    0.305    0.009 craftgraph/sync.py:(_create_tab_node)
     1280    0.078    0.000    0.294    0.000 NodeGraphQt/qgraphics/node_base.py:(_add_port)
  718/148    0.001    0.000    0.285    0.002 craftgraph/qt_nodes.py:(set_property) [ModifiedRecipeNode]
     1324    0.001    0.000    0.260    0.000 NodeGraphQt/qgraphics/node_base.py:(post_init)
      278    0.001    0.000    0.242    0.001 craftgraph/qt_nodes.py:(_create_widget_for_field)
1729/1450    0.001    0.000    0.208    0.000 NodeGraphQt/nodes/base_node.py:(set_property)
1447/1416    0.005    0.000    0.197    0.000 {method 'push' of 'PySide6.QtGui.QUndoStack' objects}
1087/1056    0.004    0.000    0.196    0.000 NodeGraphQt/base/node.py:(set_property)

`_create_widget_for_field` cumtime: 242 ms (278 calls). This covers only the non-recipe-chain nodes
(CustomSize, MovedRecipe, CustomBioFuel, CustomFragmentCount, CustomFabricator, CraftingTab).
Recipe-chain nodes (ModifiedRecipe, AddedRecipe, AliasRecipe, CustomFood) now use painted fields
and do not call `_create_widget_for_field` at all.

## Verdict

**PASS** -- all four acceptance targets hit. Folder load dropped from 9288.6 ms (post-pilot,
inconclusive) to 1597.4 ms (-83%, well below the 3000 ms target). HWND USER went from 3273 to
1157 (-65%, target <2900). Widget count fell from 3156 to 1115 (-65%, target <2700).
`_create_widget_for_field` cumtime collapsed from 988 ms to 242 ms (-76%, target <1200 ms).

The broaden plan (Tasks 1-6) fully resolves the pilot's INCONCLUSIVE result: extending painted
fields to AddedRecipe, AliasRecipe, and CustomFood was the correct move. The pre-pilot HWND
regression (+3x wall-clock) is now more than recovered -- post-broaden is 65% lighter than the
original pre-floating-input baseline (4611.7 ms). Recommended next step: merge to main.
