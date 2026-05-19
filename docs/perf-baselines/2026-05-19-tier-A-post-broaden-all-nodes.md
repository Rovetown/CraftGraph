# Tier-A baseline: post-broaden-all-nodes (2026-05-19)

Branch: `feat/painted-fields-broaden-all-nodes` (tip: `f11ec9e`)
Workload: `craftgraph/cc3_reference_files/real-mod-examples` (160 visible nodes)

## Wall-clock and resource snapshot

| Metric                                       | Pre-broaden-all-nodes (2026-05-12 post layout-fix) | Post-broaden-all-nodes | Target   | Hit? |
|----------------------------------------------|---------------------------------------------------:|-----------------------:|----------|------|
| Folder load (Windows, 3-run avg)             | 2318.1 ms                                          | 1047.7 ms              | <3000 ms | PASS |
| HWND USER (gui_objects) after load           | 1155                                               | 305                    | <2900    | PASS |
| Widget count after load                      | 1115                                               | 531                    | <2700    | PASS |
| Painted-registry build cumtime (offscreen)   | 269 ms (`_create_widget_for_field`)                | 260 ms (`_build_painted_registry`) | <1200 ms | PASS |

Run-by-run wall-clock: 1045.4 ms, 1055.9 ms, 1041.8 ms (sigma ~ 7 ms).

## What moved

The broaden-all-nodes work converted six structural node classes and ten variable
node classes from embedded Qt widgets to painted fields. It also deleted the
`NodeIntEdit` and `NodeFloatEdit` spinner widgets (and their inner `_IntEditWidget` /
`_FloatEditWidget` helpers), removing four widget classes worth of HWND/QObject
allocation per int- or float-typed field.

The drop in wall-clock (-55%) tracks the widget-count drop (-52%) and the gui-objects
drop (-74%). Each painted node now allocates only the structural ports it actually
needs (hierarchy, ingredient slots) plus property records; the value display lives
entirely in the paint path with zero per-field QWidget overhead.

## Methodology

- `scripts/baseline_capture.py` — wall-clock from `time.perf_counter_ns()` around
  `win.load_recipes(...)` + one `app.processEvents()`. HWND/widget snapshot via
  `craftgraph.hwnd_diag.take_snapshot()` before and after the load.
- `scripts/baseline_cprofile.py` — cProfile from `prof.enable()` around the same
  `load_recipes` call. Sorted by cumulative time; the relevant line is
  `_build_painted_registry` (95 calls, 260 ms cumulative).
- Three independent runs for wall-clock; the resource counters were identical
  across all three.

## Targets

The four targets from the original floating-input pilot still apply: folder-load
under 3000 ms, HWND USER under 2900, widget count under 2700, and the painted
build cumtime under 1200 ms. All four pass with substantial headroom; the next
natural lever (caching `NodeLayout` per node and invalidating on port-add /
value-change) would claw back additional cumulative paint cost if needed.
