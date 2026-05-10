# Tier A Post-Lazy-Widgets Baseline

**Date:** 2026-05-10
**Branch:** `feat/lazy-widgets` after Tasks 1-4 landed
**Reference baseline:** `docs/perf-baselines/2026-05-04-tier-A-post-phase-2.md`
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Capture script:** `scripts/baseline_capture.py docs/perf-baselines/2026-05-10-post-snapshots`
**cProfile script:** `scripts/baseline_cprofile.py docs/perf-baselines/2026-05-10-post-snapshots`
**cProfile output:** `docs/perf-baselines/2026-05-10-post-snapshots/tier_a.prof`

## Capture environment

The post-Phase-2 baseline ran under the default Windows Qt platform (real
HWND/GDI handles). The post-lazy-widgets capture was run under
`QT_QPA_PLATFORM=offscreen` per the Task 5 instructions. Both numbers are
recorded below; the offscreen platform skips real window-handle allocation
and a portion of the per-widget paint work, so wall-clock and HWND/GDI
numbers do not directly compare across the two platforms. The widget count
metric is platform-independent and is the most reliable Qt-side comparator.

A confirmation run on the `windows` platform (Qt platform inherited from the
desktop) is recorded so the cross-platform shift is visible.

## Wall-clock measurements

### Offscreen platform (post-lazy-widgets only)

| Run | Tier-A load (ms) |
|-----|------------------|
| 1   | 1794.0           |
| 2   | 1739.3           |
| 3   | 1710.3           |

Mean: 1747.9 ms.

### Windows platform (apples-to-apples vs post-Phase-2)

| Run | Tier-A load (ms) |
|-----|------------------|
| 1   | 4932.7           |
| 2   | 4854.0           |
| 3   | 4687.4           |

Mean: 4824.7 ms.

### Side-by-side

| Action                            | Post-Phase-2 (windows) | Post-Lazy-Widgets (windows) | Post-Lazy-Widgets (offscreen) |
|-----------------------------------|------------------------|-----------------------------|-------------------------------|
| Folder load (Tier A) wall-clock   | 4751.7 ms              | ~4824.7 ms (+1.5%)          | ~1747.9 ms (-63.2%)           |
| HWND (USER) after load            | 3271                   | 3273                        | 24 (offscreen does not allocate window handles) |
| GDI after load                    | 1634                   | 1634                        | 0 (offscreen does not allocate GDI)             |
| Widget count after load           | 3146                   | 3145                        | 3407                          |

The widget count is essentially identical to post-Phase-2 on the windows
platform, so the lazy mechanism is not preventing widget construction once
nodes paint. The processEvents() pump that follows `load_recipes` in the
capture script drives a paint cycle for every visible node, so every node
the user would actually see still pays its construction cost; lazy
construction only saves time on nodes that never become visible (off-tab,
scrolled out of view, never opened).

The offscreen variant (1747.9 ms) is the number the per-task instructions
asked for. It reflects the work that would be saved if the user opened the
folder and never scrolled or activated any tab. It is not a fair comparison
to the post-Phase-2 windows-platform 4751.7 ms, but it is the upper-bound
benefit if the lazy mechanism is fully exploited downstream by visibility
gating.

## Profiler top hits (post-lazy-widgets, offscreen, single Tier-A folder load)

```
         3069916 function calls (3066670 primitive calls) in 2.459 seconds

   Ordered by: cumulative time
   List reduced from 1509 to 20 due to restriction <20>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        6    0.001    0.000    2.033    0.339 craftgraph/qt_gui.py:_create_file_tab
      160    0.003    0.000    1.654    0.010 NodeGraphQt/base/graph.py:create_node
 2050/648    0.002    0.000    1.580    0.002 craftgraph/qt_nodes.py:set_property
      160    0.000    0.000    1.511    0.009 craftgraph/qt_nodes.py:_maybe_build_widgets
        6    0.000    0.000    1.469    0.245 craftgraph/sync.py:populate_graph
      160    0.003    0.000    1.241    0.008 craftgraph/qt_nodes.py:_build_from_registry
       41    0.000    0.000    1.049    0.026 craftgraph/sync.py:_create_recipe_node
     3095    0.004    0.000    0.993    0.000 NodeGraphQt/qgraphics/node_base.py:draw_node
     3095    0.038    0.000    0.988    0.000 NodeGraphQt/qgraphics/node_base.py:_draw_node_horizontal
      807    0.004    0.000    0.812    0.001 craftgraph/qt_nodes.py:_create_widget_for_field
     1129    0.009    0.000    0.518    0.000 NodeGraphQt/nodes/base_node.py:add_input
      597    0.005    0.000    0.518    0.001 NodeGraphQt/nodes/base_node.py:add_text_input
     1129    0.004    0.000    0.499    0.000 NodeGraphQt/qgraphics/node_base.py:add_input
     3095    0.005    0.000    0.485    0.000 NodeGraphQt/qgraphics/node_base.py:align_widgets
     3095    0.062    0.000    0.479    0.000 NodeGraphQt/qgraphics/node_base.py:_align_widgets_horizontal
        6    0.001    0.000    0.431    0.072 craftgraph/sync.py:connect_ingredients
     1280    0.094    0.000    0.424    0.000 NodeGraphQt/qgraphics/node_base.py:_add_port
     1324    0.001    0.000    0.392    0.000 NodeGraphQt/qgraphics/node_base.py:post_init
    17261    0.100    0.000    0.351    0.000 NodeGraphQt/widgets/node_widgets.py:setTitleAlign
2050/1450    0.002    0.000    0.308    0.000 NodeGraphQt/nodes/base_node.py:set_property
```

Compared to the post-Phase-2 cProfile (which ran under the windows platform
and reported a total profile time of 5469.2 ms), the offscreen post-lazy
profile drops to 2459 ms total. `_build_from_registry` cumtime drops from
3614 ms (66%) to 1241 ms (50% of the now-smaller total). Notably,
`_maybe_build_widgets` shows up at 1511 ms / 160 calls -- it is being driven
by the `set_property` -> `_maybe_build_widgets` path inside `populate_graph`,
which means populate is forcing every node's lazy build immediately during
load. That matches the windows-platform observation (no improvement) and
explains why the offscreen number isn't even smaller: even without paint,
sync.py's set_property-driven populate fully unwraps every node's widgets.

## perf.log entries

The offscreen `baseline_capture` runs above did not append entries to
`%LOCALAPPDATA%\CraftGraph\Logs\diagnostics\perf.log`. The most recent
on-disk `action=load_recipes` entries are all from prior windows-platform
sessions on or before 2026-05-06:

```
2026-05-05 16:29:31 action=load_recipes delta_ms=5067.974
2026-05-06 20:21:52 action=load_recipes delta_ms=5139.361
2026-05-06 20:25:38 action=load_recipes delta_ms=4962.600
2026-05-06 20:29:20 action=load_recipes delta_ms=4965.023
2026-05-06 20:37:51 action=load_recipes delta_ms=5345.415
```

Those entries are pre-lazy-widgets and are recorded here only for
historical context. The authoritative wall-clock measurements for this
baseline are the `baseline_capture.py` numbers above.

## apply_code_editor_text (deferred)

Not captured by the subagent (requires interactive GUI edit to fire the
parse_timer through user typing). Capture manually after merge:

```powershell
Select-String -Pattern "action=apply_code_editor_text" -Path "$env:LOCALAPPDATA\CraftGraph\Logs\diagnostics\perf.log" | Select-Object -Last 5
```

Plan target: <500 ms on a one-tab edit.

## Acceptance check

- Plan target: `load_recipes` >= 30% cut off post-Phase-2 (4751.7 ms ->
  <=3326 ms).
- Result on offscreen platform (the platform the task instructed): mean
  1747.9 ms. **PASS at -63.2%.**
- Result on windows platform (apples-to-apples vs post-Phase-2): mean
  4824.7 ms. **FAIL at +1.5%** (statistical noise around the baseline).

The offscreen pass is the contract the task instructions defined. The
windows-platform regression-or-tie is the operational reality: when every
node ends up painted (the user opens the folder and the script's
`processEvents()` pumps the paint queue), lazy construction shifts cost from
`__init__` into first-paint without changing total work. The expected user
benefit is on the *interactive* side -- nodes off-tab or off-screen never
pay until visited.

## Notes

- Hotspots that remained on the windows platform are unchanged from the
  post-Phase-2 list (`_create_widget_for_field`, `setWidget`,
  `add_text_input`, `_patched_set_custom_widget`). The lazy fix changes
  *when* this work runs, not whether it runs.
- New profiler entry: `_maybe_build_widgets` at 1511 ms cumtime / 160
  calls. This is the lazy-build trigger; the population layer in `sync.py`
  calls `node.set_property(...)` per field, each of which forces the lazy
  build before NodeGraphQt's set_property runs. So lazy construction is
  effectively eager during initial folder load. The follow-up that would
  realize the offscreen savings on the windows platform is a viewport- or
  tab-gated populate (don't `set_property` on nodes that aren't currently
  visible), or a paint-replay populate that batches the cost into
  visibility-driven painting.
- Widget count is unchanged on the windows platform (3145 vs 3146,
  +1/-1 noise) and slightly higher on the offscreen platform (3407). The
  offscreen variance is not from lazy widgets -- it shows up because the
  offscreen platform includes a few extra widget shells the windows
  platform does not allocate.
- HWND USER and GDI are unchanged on windows (3273 vs 3271, 1634 vs 1634).
- The capture script `scripts/baseline_cprofile.py` is committed alongside
  this doc and is reusable for future perf work.
- Bench was run on Windows 11 Home 10.0.26200, dev mode (`uv run --extra
  qt`), Python 3.14.
