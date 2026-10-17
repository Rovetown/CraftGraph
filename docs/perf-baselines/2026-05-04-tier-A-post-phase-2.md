# Tier A Post-Phase-2 Baseline

**Date:** 2026-05-04
**Branch:** `feat/perf-phase-2` after Tasks 1-9 landed (Task 5 fell back; see notes)
**Workload:** `craftgraph/cc3_reference_files/real-mod-examples` (~50 recipes, 1240 lines)
**Machine:** Windows 11 Home 10.0.26200, dev mode (`uv run --extra qt`)
**Python:** 3.14
**Capture script:** `scripts/baseline_capture.py docs/perf-baselines/2026-05-04-post-snapshots`
**cProfile output:** `docs/perf-baselines/2026-05-04-post-snapshots/tier_a.prof`

## Wall-clock measurements

| Action                 | Pre-Phase-2 (ms) | Post-Phase-2 (ms) | Delta            | Notes                                    |
|------------------------|------------------|-------------------|------------------|------------------------------------------|
| Folder load (Tier A)   | 9290.6           | 4751.7            | -4538.9 (-48.9%) | crossed the original < 5 s acceptance gate |
| HWND (USER) after load | 3270             | 3271              | +1               | unchanged (widgets still proxied)        |
| GDI after load         | 1634             | 1634              | 0                | identical                                |
| Widget count after     | 3145             | 3146              | +1               | unchanged                                |

**Read:** Phase 2 hit its goal -- folder load dropped from 9.3 s to 4.75 s,
just under the 5 s target the plan set. The win is almost entirely from the
stylesheet-cache patch (Task 4), which killed ~3 s of redundant QSS reparse;
the time-slicing yield (Task 6) keeps the UI from completely freezing during
the remaining cost. HWND / widget counts are unchanged because Phase 2 did
not remove any widgets -- the lazy-widget refactor (Task 5) was attempted
and reverted (see "Plan deviation" below).

## Profiler top hits (cumulative time, single Tier A folder load)

```
Total profile time: 5469.2 ms (cProfile overhead included)

  cumtime    pct   ncalls  function                                                      delta vs pre
  -------   ----   ------  --------                                                      ------------
   4833 ms   88%        6  craftgraph/qt_gui.py:_create_file_tab                         -2311 ms (-32%)
   4213 ms   77%      160  NodeGraphQt/base/graph.py:create_node                          -597 ms (-12%)
   4094 ms   75%        6  craftgraph/sync.py:populate_graph                             -1930 ms (-32%)
   3779 ms   69%      160  NodeGraphQt/base/factory.py:create_node_instance               -478 ms (-11%)
   3751 ms   69%      160  craftgraph/qt_nodes.py:CraftGraphBaseNode.__init__             -479 ms (-11%)
   3614 ms   66%      160  craftgraph/qt_nodes.py:_build_from_registry                    -477 ms (-12%)
   3392 ms   62%      807  craftgraph/qt_nodes.py:_create_widget_for_field                -481 ms (-12%)
   2664 ms   49%      807  craftgraph/qt_nodes.py:_patched_set_custom_widget              +274 ms (cache install overhead)
   2546 ms   47%      807  QGraphicsProxyWidget.setWidget                                 +251 ms (jitter)
   2372 ms   43%      597  NodeGraphQt/nodes/base_node.py:add_text_input                  -373 ms (-14%)
   1153 ms   21%     2288  NodeGraphQt/qgraphics/node_base.py:_draw_node_horizontal      -2876 ms (-71%)
    688 ms   13%     2288  NodeGraphQt/qgraphics/node_base.py:_align_widgets_horizontal  -2905 ms (-81%)
    580 ms   11%    14580  NodeGraphQt/widgets/node_widgets.py:setTitleAlign             -2863 ms (-83%)
   <0.1s            ~5000  QWidget.setStyleSheet (cache hits short-circuit)              -3322 ms (-100%)
```

The stylesheet cache obliterated the `setTitleAlign` / `_align_widgets_horizontal`
chain: `setStyleSheet` no longer dominates, and the redundant QSS-reparse work
disappeared. Per-node widget construction (`_build_from_registry`,
`_create_widget_for_field`) is now the leading cost, but at ~3.4 s combined
across 807 widgets it is no longer a single dominant hotspot.

(See `docs/perf-baselines/2026-05-04-post-snapshots/tier_a.prof` for the full
profile.)

## Plan deviation: Task 5 (lazy widget construction)

Task 5 of the perf Phase 2 plan -- defer
`_build_from_registry()` until first paint -- was implemented per spec, the
plan's own tests passed, but the full regression suite produced (a) widespread
test failures and (b) a Windows heap-corruption crash (`0xc0000374`). Root
causes:

1. `populate_from_model()` runs synchronously after node create (in
   `sync.py:populate_graph`). It calls `set_property(name, value)` per field.
   With widgets deferred, NodeGraphQt's set_property stored values on the
   internal node model; when widgets were later built on first paint,
   `_create_widget_for_field` re-seeded them from `fp.default` instead of
   the populated model state -- the data the user expected to see was lost.
2. The first-paint patch assigns to `view.paint` at the instance level. Qt's
   C++ scene dispatch goes through the class virtual table, not the Python
   instance attribute, so the patch interacts strangely with NodeGraphQt's
   own paint machinery -- the heap corruption surfaced inside the first
   `populate_graph` call after the regression suite stressed the path.

Fix is non-trivial (needs a populate-before-paint reseed path plus a
class-level paint patch). Documented as ATTEMPTED-reverted on TODO.md row
9.11; revisit only if Phase 3 profiler still pins per-node widget construction
as dominant.

The paint-stats API (`record_paint` / `paint_stats` / `reset_paint_stats`)
from Task 7 still landed -- the dialog from Task 8 reads it -- but no Qt
caller is wired into it. The wiring would have lived inside the rolled-back
paint patch; Phase 3 can plumb it via a class-level `NodeItem.paint` wrap.

## What landed

| Task | Status   | Wall-clock attribution |
|------|----------|------------------------|
| 1    | DONE     | -- (baseline)          |
| 2    | DONE     | foundation (no perf)   |
| 3    | DONE     | foundation (no perf)   |
| 4    | DONE     | **~3.0 s**: stylesheet cache killed setTitleAlign / setStyleSheet / _align_widgets_horizontal redundancy |
| 5    | REVERTED | 0 (see above)          |
| 6    | DONE     | ~0 (responsiveness only -- doesn't cut total work, just frees the UI thread between batches of 50 nodes) |
| 7    | DONE     | foundation (API only)  |
| 8    | DONE     | foundation (no perf)   |
| 9    | DONE     | -- (TODO.md flips)     |
| 10   | DONE     | -- (this doc)          |

The remaining ~1.5 s of the wall-clock improvement (4540 ms total - 3 s from
Task 4) comes from the `_align_widgets_horizontal` chain shrinking faster
than its callers (it dropped 81% while its parent `_draw_node_horizontal`
dropped 71%) -- the cache short-circuits don't just skip QSS parsing, they
also skip the painter dirty-region work Qt would have queued.

## Phase 3 candidates -- ordered by current profiler signal

The single dominant cost is gone. Remaining cost is spread across the
per-node-widget construction path. None of the remaining hotspots is large
enough to justify a high-cost rewrite; recommend Phase 3 stays cheap.

| Target                                                                | Cumulative cost | Approach                                                                                                                                              | TODO row |
|-----------------------------------------------------------------------|-----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|----------|
| `QGraphicsProxyWidget.setWidget` x807                                 | 2546 ms         | Floating-input refactor (TODO 9.6) is the only thing that actually removes proxy widgets. **Major rewrite -- own design cycle.** Skip unless Tier C is the target. | 9.6      |
| `_create_widget_for_field` x807 / `add_text_input` x597               | 3392 / 2372 ms  | Lazy widget construction (TODO 9.11), redesigned to handle populate-before-paint and patch paint at the class level. Already attempted in Phase 2 and reverted; needs a real spec, not the bullet list from this plan. | 9.11     |
| `_patched_set_custom_widget` x807 -- 274 ms of cache-install overhead | 274 ms          | Marginal: `_install_stylesheet_cache` allocates a closure + `MethodType` per node. Could be class-level once instead of per-instance. Tiny win.        | --       |
| Wire `record_paint` into a class-level `NodeItem.paint` wrap          | n/a             | Picks up Task 7's API. Class-level patch sidesteps the Qt vtable issue that broke Task 5. Cheap; gives Help > Show Perf Log real data.                | 1.7 (extension) |

**Out of scope based on this profile (still):**

- Parser native compilation. Parser is < 0.5 s of the 4.75 s.
- Graph algorithms. NetworkX work is sub-second.
- Concurrency. The remaining cost is Qt scene mutation, which must run on
  the main thread anyway (NodeGraphQt is not thread-safe).

## Recommended Phase 3 order

1. **Cheap wiring win:** class-level `NodeItem.paint` wrap that calls
   `perf_diag.record_paint(...)` so Help > Show Perf Log has real data.
   Validates the safe paint-patch pattern Task 5 needed.
2. **Reduce cache-install overhead** (per-instance closure -> per-class once).
   Tiny but free.
3. **Decide:** stop here (4.75 s is acceptable for Tier A) or escalate to a
   Tier-C-targeted lazy-widget redesign (9.11 / 9.6). Recommend stopping
   unless Tier C becomes a real acceptance target -- the next two ladder
   rungs cost more than they save at Tier A.
