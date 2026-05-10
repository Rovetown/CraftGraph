# Tier A Pre-Floating-Input-Pilot Baseline

**Date:** 2026-05-10
**Branch:** `feat/floating-input-pilot` (from master post-9.11 merge)
**Reference baseline:** `docs/perf-baselines/2026-05-10-tier-A-post-lazy-widgets.md`
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Capture scripts:** `scripts/baseline_capture.py`, `scripts/baseline_cprofile.py`
**Qt platform:** windows for wall-clock; offscreen for cProfile (script forces `QT_QPA_PLATFORM=offscreen` internally). The post-pilot capture in Task 7 must use the same platform split for an apples-to-apples comparison.

## Wall-clock measurements (3-run average, windows platform)

| Action                 | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Average (ms) |
|------------------------|-----------:|-----------:|-----------:|-------------:|
| Folder load (Tier A)   | 5069.0     | 4419.7     | 4346.5     | 4611.7       |
| HWND (USER) after load | 3271       | 3273       | 3273       | 3272.3       |
| GDI after load         | 1634       | 1634       | 1634       | 1634.0       |
| Widget count after     | 3145       | 3145       | 3145       | 3145.0       |

HWND/GDI/widgets before load (for reference): gui ~38-41, gdi=20, widgets=148.

## Profiler top hits (offscreen platform, single Tier-A folder load)

```
Sun May 10 19:17:41 2026    docs/perf-baselines/2026-05-10-pre-pilot-snapshots/tier_a.prof

         3069916 function calls (3066670 primitive calls) in 2.488 seconds

   Ordered by: cumulative time
   List reduced from 1509 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        6    0.001    0.000    2.062    0.344 craftgraph/qt_gui.py:7699(_create_file_tab)
      160    0.003    0.000    1.670    0.010 NodeGraphQt/base/graph.py:1189(create_node)
 2050/648    0.002    0.000    1.596    0.002 craftgraph/qt_nodes.py:1113(set_property)
      160    0.000    0.000    1.524    0.010 craftgraph/qt_nodes.py:1082(_maybe_build_widgets)
        6    0.000    0.000    1.482    0.247 craftgraph/sync.py:242(populate_graph)
      160    0.003    0.000    1.249    0.008 craftgraph/qt_nodes.py:987(_build_from_registry)
       41    0.000    0.000    1.056    0.026 craftgraph/sync.py:117(_create_recipe_node)
     3095    0.004    0.000    1.015    0.000 NodeGraphQt/qgraphics/node_base.py:702(draw_node)
     3095    0.039    0.000    1.009    0.000 NodeGraphQt/qgraphics/node_base.py:642(_draw_node_horizontal)
      807    0.004    0.000    0.809    0.001 craftgraph/qt_nodes.py:1013(_create_widget_for_field)
     1129    0.009    0.000    0.531    0.000 NodeGraphQt/nodes/base_node.py:418(add_input)
      597    0.004    0.000    0.516    0.001 NodeGraphQt/nodes/base_node.py:246(add_text_input)
     1129    0.004    0.000    0.512    0.000 NodeGraphQt/qgraphics/node_base.py:933(add_input)
     3095    0.005    0.000    0.492    0.000 NodeGraphQt/qgraphics/node_base.py:549(align_widgets)
     3095    0.062    0.000    0.485    0.000 NodeGraphQt/qgraphics/node_base.py:504(_align_widgets_horizontal)
        6    0.001    0.000    0.441    0.074 craftgraph/sync.py:1150(connect_ingredients)
     1280    0.094    0.000    0.435    0.000 NodeGraphQt/qgraphics/node_base.py:910(_add_port)
     1324    0.001    0.000    0.402    0.000 NodeGraphQt/qgraphics/node_base.py:714(post_init)
    17261    0.105    0.000    0.359    0.000 NodeGraphQt/widgets/node_widgets.py:21(setTitleAlign)
2050/1450    0.002    0.000    0.318    0.000 NodeGraphQt/nodes/base_node.py:78(set_property)
```

`_create_widget_for_field` cumtime in this capture is 809 ms, well below the ~3392 ms anchor referenced in the task description. This drift is consistent with the post-lazy-widgets baseline (812 ms in `2026-05-10-tier-A-post-lazy-widgets.md`), so it is not a regression. Per the task instructions, the new pre-pilot number (809 ms) is the comparison anchor going forward.

## Acceptance targets for the pilot (Task 7 verifies)

| Metric                                  | Pre        | Target     |
|-----------------------------------------|-----------:|-----------:|
| Widget count after load                 | 3145       | < 2700     |
| HWND USER after load                    | 3272       | < 2900     |
| Folder-load wall-clock                  | 4611.7 ms  | < 3000 ms  |
| `_create_widget_for_field` cumtime      | 809 ms     | < 1200 ms  |

Notes:

- Folder-load wall-clock is measured under `QT_QPA_PLATFORM=windows`. Task 7 must use the same platform.
- `_create_widget_for_field` cumtime is measured under `QT_QPA_PLATFORM=offscreen` (forced by `baseline_cprofile.py`). Task 7 must use the same platform.
- Widget count and HWND USER are taken from the windows-platform `baseline_capture.py` runs.
