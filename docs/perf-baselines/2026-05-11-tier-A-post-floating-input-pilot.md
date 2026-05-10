# Tier A Post-Floating-Input-Pilot Baseline

**Date:** 2026-05-11
**Branch:** `feat/floating-input-pilot` after Tasks 1-6 landed (commit `f8e11cd` + this baseline)
**Reference baseline:** `docs/perf-baselines/2026-05-10-tier-A-pre-floating-input.md`
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Capture scripts:** `scripts/baseline_capture.py`, `scripts/baseline_cprofile.py`
**Qt platform:** Windows for wall-clock, offscreen for cProfile (matches pre-pilot for apples-to-apples)

## Wall-clock measurements (3-run average, windows platform)

| Action                 | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Average (ms) |
|------------------------|-----------:|-----------:|-----------:|-------------:|
| Folder load (Tier A)   | 8167.4     | 9896.0     | 9802.3     | 9288.6       |
| HWND (USER) after load | 3271       | 3274       | 3273       | 3272.7       |
| GDI after load         | 1634       | 1634       | 1634       | 1634.0       |
| Widget count after     | 3156       | 3156       | 3156       | 3156.0       |

HWND/GDI/widgets before load (for reference): gui ~37-40, gdi=20, widgets=159.

## Wall-clock comparison (Windows platform, 3-run average)

| Action                 | Pre (ms) | Post (ms) | Delta            | Target | Hit? |
|------------------------|---------:|----------:|------------------|--------|------|
| Folder load (Tier A)   | 4611.7   | 9288.6    | +4676.9 (+101.4%) | <3000  | FAIL |
| HWND USER after load   | 3272     | 3273      | +1                | <2900  | FAIL |
| GDI after load         | 1634     | 1634      | +0                | -      | -    |
| Widget count after     | 3145     | 3156      | +11               | <2700  | FAIL |

## Profiler hotspot deltas (offscreen, top-20 cumulative)

Pre-pilot top-20:

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

Post-pilot top-20:

```
         3071695 function calls (3067558 primitive calls) in 3.034 seconds

   Ordered by: cumulative time
   List reduced from 1521 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        6    0.002    0.000    2.523    0.420 craftgraph/qt_gui.py:7758(_create_file_tab)
      160    0.004    0.000    2.044    0.013 NodeGraphQt/base/graph.py:1189(create_node)
 2050/648    0.002    0.000    1.937    0.003 craftgraph/qt_nodes.py:1232(set_property)
      160    0.001    0.000    1.848    0.012 craftgraph/qt_nodes.py:1201(_maybe_build_widgets)
        6    0.000    0.000    1.808    0.301 craftgraph/sync.py:242(populate_graph)
      160    0.004    0.000    1.516    0.009 craftgraph/qt_nodes.py:1106(_build_from_registry)
 1039/148    0.001    0.000    1.306    0.009 craftgraph/qt_nodes.py:1603(set_property)
       41    0.000    0.000    1.277    0.031 craftgraph/sync.py:117(_create_recipe_node)
     3095    0.005    0.000    1.188    0.000 NodeGraphQt/qgraphics/node_base.py:702(draw_node)
     3095    0.046    0.000    1.181    0.000 NodeGraphQt/qgraphics/node_base.py:642(_draw_node_horizontal)
       41    0.000    0.000    1.038    0.025 craftgraph/qt_nodes.py:1556(_build_from_registry)
      807    0.006    0.000    0.988    0.001 craftgraph/qt_nodes.py:1132(_create_widget_for_field)
     1129    0.011    0.000    0.636    0.001 NodeGraphQt/nodes/base_node.py:418(add_input)
      597    0.006    0.000    0.629    0.001 NodeGraphQt/nodes/base_node.py:246(add_text_input)
     1129    0.005    0.000    0.614    0.001 NodeGraphQt/qgraphics/node_base.py:933(add_input)
     3095    0.006    0.000    0.578    0.000 NodeGraphQt/qgraphics/node_base.py:549(align_widgets)
     3095    0.075    0.000    0.571    0.000 NodeGraphQt/qgraphics/node_base.py:504(_align_widgets_horizontal)
        6    0.002    0.000    0.548    0.091 craftgraph/sync.py:1150(connect_ingredients)
     1280    0.119    0.000    0.519    0.000 NodeGraphQt/qgraphics/node_base.py:910(_add_port)
     1324    0.001    0.000    0.475    0.000 NodeGraphQt/qgraphics/node_base.py:714(post_init)
```

Key hotspot comparison:

| Function                             | Pre cumtime (ms) | Post cumtime (ms) | Delta   | Target | Hit? |
|--------------------------------------|-----------------:|------------------:|--------:|--------|------|
| `_create_file_tab`                   | 2062             | 2523              | +461    | -      | -    |
| `create_node`                        | 1670             | 2044              | +374    | -      | -    |
| `set_property` (qt_nodes)            | 1596             | 1937              | +341    | -      | -    |
| `_maybe_build_widgets`               | 1524             | 1848              | +324    | -      | -    |
| `populate_graph`                     | 1482             | 1808              | +326    | -      | -    |
| `_build_from_registry` (base)        | 1249             | 1516              | +267    | -      | -    |
| `_build_from_registry` (Modified)    | -                | 1038 (NEW)        | +1038   | -      | -    |
| `_create_widget_for_field`           | 809              | 988               | +179    | <1200  | PASS |
| `add_text_input`                     | 516              | 629               | +113    | -      | -    |
| `PaintedFieldsNodeItem.paint` (NEW)  | -                | (not in top-20)   | -       | -      | -    |

Note: there is no separate `_patched_set_custom_widget` entry in either top-20.

## Acceptance verdict

The pilot's acceptance gate requires ALL FOUR targets to hit:

- [ ] FAIL: Widget count after Tier-A load 3156 (target <2700, pre 3145, delta +11)
- [ ] FAIL: HWND USER after load 3273 (target <2900, pre 3272, delta +1)
- [ ] FAIL: Folder-load wall-clock (Windows) 9288.6 ms (target <3000 ms, pre 4611.7 ms, delta +4676.9 ms / +101.4%)
- [x] PASS: `_create_widget_for_field` cumtime 988 ms (target <1200 ms, pre 809 ms, delta +179 ms — already under target before the pilot due to lazy widgets, irrelevant indicator)

**Verdict:** FAIL. Three of four targets missed. Only the `_create_widget_for_field` cProfile target is hit, and that one was already under the threshold pre-pilot (the task brief calls this metric "informational, not a meaningful gate" for the pilot).

## Root-cause analysis

The Tier-A workload (`real-mod-examples`) contains zero direct `ModifiedRecipes` blocks. Listing of the directory:

- `BigFilteredWater.txt` -> `AddedRecipes`
- `_Alch_AliasRecipes_0_NEW_Lab_Equipment.txt` -> `AliasRecipes`
- `_Alch_AliasRecipes_1_NEW_Basic_&_Organic.txt` -> `AliasRecipes`
- `customfab3.txt` -> `AliasRecipes` (inside CustomFabricators)
- `__Alch_NEW_CustomFAB__.txt` -> CustomFabricators / CustomCraftingTabs
- `BigFilteredWater.txt` -> `AddedRecipes`
- `customsizze.txt` -> `CustomSizes`

The pilot's painted-fields path is gated by `type(self) is ModifiedRecipeNode` (see `craftgraph/qt_nodes.py:1548`, `:1562`, `:1605`, `:1614`, `:1634`, `:1646`). All recipe instances created from this workload are subclasses (`AddedRecipeNode`, `AliasRecipeNode`, `CustomFoodNode`), so the strict `type(self) is ModifiedRecipeNode` check evaluates False on every node and the standard widget-building path runs unchanged. Confirmed by the cProfile diff: same `_build_from_registry` (base) call count (160) and `_create_widget_for_field` call count (807) pre and post.

The wall-clock regression (+4677 ms) is therefore not a measurement of the pilot saving anything (it didn't engage). The likely cause is the cumulative cost of the new infrastructure that runs on every node regardless of subclass:

- New `_build_from_registry` override on the ModifiedRecipeNode class shows up as a new top-20 entry (1038 ms cumtime, 41 calls — fires for every recipe in `_create_recipe_node` because the override is on the base of the recipe chain).
- Added attribute lookups and `super()` chains (`type(self) is not ModifiedRecipeNode: super()._build_from_registry()` on every subclass instance build) add per-node overhead.
- The Windows-platform wall-clock measurement is also more variable than the offscreen cProfile measurement; the three runs spread 8167 -> 9896 ms (range 1729 ms, ~21% of mean), so noise contributes to the gap, but every individual run exceeds the 4611 ms pre-pilot mean by at least 3.5 seconds.

The widget-count delta of +11 (3145 -> 3156) is consistent with the new instrumentation creating a small, fixed number of additional widgets at window setup (matching the `widgets=159` before-load value vs the pre-pilot `widgets=148`).

## Caveat on cProfile target

The `_create_widget_for_field <1200 ms` target was set against the post-Phase-2 baseline of 3392 ms (Windows platform). cProfile measurement is offscreen-only because the script uses `QT_QPA_PLATFORM=offscreen`. Under offscreen, lazy-widgets already prevented eager widget construction, so the pre-pilot cumtime was 809 ms — already inside the target before the pilot. The pilot's effect on `_create_widget_for_field` cumtime under cProfile is therefore informational, not a meaningful gate. The REAL acceptance signal lives in the three platform-relevant metrics: widget count, HWND, Windows wall-clock — all three FAILED.

## What to do next

The pilot did not engage on the Tier-A workload because the workload contains no direct `ModifiedRecipeNode` instances; all recipes in `real-mod-examples` parse as subclasses (Added/Alias/CustomFood). Options to consider for the closeout:

1. **Broaden the painted-fields path to recipe subclasses** (Added/Alias/CustomFood). This is the most direct way to get the pilot to actually exercise the infrastructure on the existing Tier-A workload.
2. **Re-baseline against a workload that contains direct `ModifiedRecipeNode` instances** (any of the CC3 reference files under `cc3_reference_files/original-source/CustomCraft3/SampleFiles` that use `ModifiedRecipes`). This would isolate the painted-fields effect for the narrow subset the pilot currently covers, but it would not validate the pilot for real-world mod loads.
3. **Investigate the +4677 ms wall-clock regression on Windows platform.** Even though the painted-fields path didn't engage for any node, the Windows wall-clock more than doubled. Possibilities: the post-load `app.processEvents()` paint pump is now doing extra work, the new `_build_from_registry` override is adding a per-node `super()` dispatch overhead that compounds across 160 nodes, or environmental noise on this run. A 3-run average isn't enough to disambiguate noise from signal at this magnitude; a follow-up should bisect against `f8e11cd^` to confirm.

Recommended next step: **(1)** above. The plan's intent was to drop widget count for recipe nodes, and the gating is too strict to do that on real workloads.

## Files

- Wall-clock snapshots: `docs/perf-baselines/2026-05-11-pilot-snapshots/hwnd_post_load.txt`
- cProfile dump: `docs/perf-baselines/2026-05-11-pilot-snapshots/tier_a.prof`
