#### BIG INBETWEEN NEEDED TO BE SOLVED!!!
The file "GEMINI_SOLUTION.md" has important info and potential bug fixes for us!

#### TEST RUNNER -- regression sweep hangs / times out

> **Resolved knowledge worth keeping:** Headless test hangs in the agent shell traced to two causes. (1) **Pipe buffering**: `2>&1 | tail` / `Select-Object -Last` only flushes the tail of stdout, hiding mid-run progress. Fix pattern: redirect to a file with `>file 2>&1` and tail the file. (2) **Modal dialog stubs**: production migrated from the deprecated `QDialog.exec_` form to the new `QDialog.exec` form (commit a46e127); test monkey-patches still targeting the underscore alias no longer intercepted the real modal, so it blocked the headless loop indefinitely. Same fix applies to any future modal stub.

- [ ] **Consider tagging slow / interactive tests with `@pytest.mark.slow`** and excluding them from the default `just test` recipe; opt-in via `just test-slow`. Same goal: the default sweep should finish fast enough that "did my change regress anything" never times out. Lower priority now that `just test-fast` exists.


## HWND Exhaustion: Hardening + Diagnostics Plan

The original 894-node `_NodeGroupBox` blow-up is patched, but HWND exhaustion still surfaces "here and there" through bugs or leaks we have not pinned down. Goal: stop it permanently by (1) measuring it so leaks become findable, (2) fixing the known suspects, (3) installing cheap preventive guards. Performance / multithreading work is out of scope here -- separate planning cycle once HWND is stable.

Three phases, each shippable independently. Each phase becomes its own implementation plan via `superpowers:writing-plans`.

| Phase | Scope | Ships | Success criterion |
|---|---|---|---|
| 1 | Diagnostics: status-bar counter, pytest stress harness, per-action delta log, snapshot dump | New `craftgraph/hwnd_diag.py` + status-bar wiring + `tests/test_hwnd_stress.py` | Can reproduce a leak in <2 minutes and identify which action caused it |
| 2 | Targeted fixes: tab persistence (close-time), context menu lifecycle, settings rebuild, multi-folder teardown, watcher rebuild | Edits to `qt_gui.py`, `watcher.py`, `qt_nodes.py` | Phase 1 stress tests stay under threshold across all 5 scenarios |
| 3 | Preventive hardening: `AA_DontCreateNativeWidgetSiblings` flag + parenting audit | One-line flag in CLI launcher + audit pass through GUI files | No regression after 30-min mixed-workload session |

Phase 2 starts only after Phase 1 lands so threshold values come from real measurements, not guesswork.

### Phase 1 -- Diagnostics

New module `craftgraph/hwnd_diag.py` (Windows-only with no-op fallback on Linux/macOS):

```python
def gui_handle_count() -> int            # GR_USEROBJECTS via ctypes; 0 on non-Windows
def gdi_handle_count() -> int            # GR_GDIOBJECTS
def widget_inventory() -> dict[str, int] # Qt-side: count by class via qApp.allWidgets()
@contextmanager
def measure(action: str, *, log: bool = True) -> Iterator[HandleSnapshot]
def install_logger(threshold: int = 20) -> None  # warns when delta exceeds threshold
def snapshot_to_file(path: Path) -> None  # for D / bug reports
```

- [ ] **Surface A -- Status-bar counter.** Small `QLabel` on far-right of status bar: `HWND: 4127 (+12)`. Updates every 2 s on a `QTimer`, plus immediately after any action wrapped by `measure()`. Color-codes: white < 5000, amber 5000-8000, red > 8000. Hidden by default; toggled by **View > Show Handle Counter** menu item, settings-persisted.
- [ ] **Surface B -- Pytest stress harness (`tests/test_hwnd_stress.py`).** Skipped on non-Windows + skipped if `--no-stress` flag passed. Each test: snapshot -> run scenario N times -> snapshot -> assert delta < threshold. Scenarios mirror Phase 2 suspects: open-folder x3, open-close-settings x20, right-click menu x50, watcher rebuild x10, switch tabs x30. Thresholds parameterised at top of file so they ratchet down as Phase 2 lands fixes.
- [ ] **Surface C -- Per-action delta logging.** `measure()` context manager around every menu callback, dialog open, file open, watcher rebuild handler. Logs `action=open_settings before=4112 after=4178 delta=+66` to `~/.craftgraph/logs/hwnd.log`. Threshold-warning surfaces in status bar (toast) when delta > 20 in a single action.
- [ ] **Surface D -- Snapshot dump.** **Help > Dump Handle Snapshot** menu item. Writes `~/.craftgraph/diagnostics/hwnd_<timestamp>.txt`: GR_USEROBJECTS, GR_GDIOBJECTS, widget class breakdown (top 20), open file tabs, last 50 entries from `hwnd.log`. Status-bar confirms path so users can attach to bug reports.

### Phase 2 -- Targeted fixes

Each fix is small, scoped, lands behind a Phase 1 stress test.

- [DONE] **1. Tab persistence (close-time only, not lazy switch).** _`_tear_down_tabs()` now setParent(None) + deleteLater on each graph widget and editor after stack removal, deleteLater on each parse_timer, detaches the minimap, clears per-tab `model_to_node`/`orphan_nodes`/`user_positions` dicts, and disposes NodeGraphQt's parent-less TabSearch popup widget per tab. Letting Qt's parent-chain destruction cascade naturally (instead of pre-emptively calling `NodeGraph.delete_node`, which only detaches QGraphicsItems from the scene without freeing them) drops widget growth from 4864 to a stable 148 over 10 open/close cycles. Stress test `open_close_folder_x10` widget threshold ratcheted 500 → 275 → 200 across the iterative tightening commits._
- [DONE] **2. Context menu lifecycle.** _Audit-only. No direct `QMenu()` construction; recent-files submenu uses `clear()` + `addAction`; NodeGraphQt context menus are reused via `get_context_menu()`. Stress test `context_menu_x50` ratcheted to HWND=25 / widgets=25._
- [DONE] **3. Settings dialog rebuild.** _SettingsDialog scheduled for `deleteLater()` after modal close. Stress test `open_close_settings_x20` widget threshold ratcheted 200 -> 150 (was 9460 pre-fix). Lesson: destroying the dialog disposes its children and disconnects its signals automatically -- no manual signal-disconnect helper needed._
- [DONE] **4. Multi-folder teardown.** _Subsumed by fix #1, plus one extra: NodeGraphQt's per-viewer `TabSearchMenuWidget` is parent-less, so it survives the QWidget destruction chain. `_tear_down_tabs()` now `setParent(None) + deleteLater` on each viewer's `_search_widget`. Side benefit: `open_close_folder_x10` widget delta dropped 210 -> 148._
- [DONE] **5. Watcher rebuild.** _Audit-only. `_on_watcher_rebuild()` routes through `_tear_down_tabs()`, already hardened by fixes #1 and #4. No fresh leak surface._

### Phase 3 -- Preventive hardening

- [DONE] **A. `AA_DontCreateNativeWidgetSiblings` flag.** _Set on `QtCore.QCoreApplication` in `launch_qt_gui()` before the first `QApplication`. Removes a class of accidental native HWND growth at scale._
- [DONE] **B. Parenting audit.** _No code changes needed; existing patterns sound. The single intentional unparented `QWidget()` is the module-level `_GROUPBOX_PARENT` singleton in `qt_nodes.py`, used as hidden parent for `_NodeGroupBox` instances; process-lifetime and annotated._

### After HWND: performance / multithreading

Tracked separately. Phases 1-3 of HWND have landed and stress tests stay green. This section captures the full menu of optimization vectors so brainstorming can pick up where it left off.

**Tier reference workloads:**
- **Tier B (small):** EquipmentSalvage (~165 lines)
- **Tier A (typical):** real-mod-examples (~50 recipes, 1240 lines)
- **Tier C (worst):** the 894-node reference set

#### v1 scope decisions (resolved)

- **Acceptance target:** **tier A only** (real-mod-examples). Tier B comes along for free; tier C is informational measurement only, no hard pass/fail gate.
- **Sections in scope:** 1-8, with three items demoted to Section 9 because their wins are tier-C-justified and don't pay off at tier A: **2.5 rustworkx**, **5.3 LOD on zoom**, **6.2 lazy widget allocation**. They keep escalation triggers in Section 9.
- **Risk-tiered phasing within v1:**
  - **Phase 1 -- No-brainers:** measurement infra + cheap wins that can't harm. 13 items spread across all sections. Lands first to establish baseline + ship safe gains.
  - **Phase 2 -- Tier-A targets:** real concurrency, native compile, architectural changes. 9 items. Lands after Phase 1 so each is gated on profiler data justifying the cost.
  - 3.4 (free-threaded Python 3.14) is **tracked only**, not implemented -- monitor PySide6 wheel compatibility.
- **DONE-marking convention:** v1 tables get a `Status` column. Values: `--` not started, `WIP` in progress, `DONE` landed with profiler-verified improvement. Mirrors HWND Phase 2 style. Section 9 entries do not get the column.

#### 1. Foundation — measure first  _(Phase 1 -- all entries)_

| # | Item | Where in CraftGraph | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1.1 | cProfile harness with tiered workloads (B/A/C) | tests/test_perf_stress.py | low | DONE -- Tier A regression gate |
| 1.2 | perf_diag.measure(action) wrapper | perf_diag module | low | DONE -- wired around load_recipes / settings / watcher / code-edit |
| 1.3 | Qt frame-time overlay (debug-only) | qt_gui.py View menu | low | DONE -- View > Show Frame Time + report_frame logger |
| 1.4 | tracemalloc snapshots tied to actions | mem_diag.py | low | DONE -- Help > Dump Memory Snapshot |
| 1.5 | Release-vs-dev baseline: pyinstaller --onefile build | one-time | medium | DONE -- **Surprising finding: release is 3.9x SLOWER than dev** (`uv run` 725 ms vs `--onefile` binary 2793 ms on Tier A). The `--onefile` extraction tax (whole bundle to `%TEMP%` per launch) dominates. Side-fix: build recipe was missing `--collect-data craftgraph` so the binary crashed on missing config.toml; fixed. **Action item:** if release startup ever becomes a real complaint, switch to `--onedir` (folder ships, no extraction tax). Distribution implications need their own design pass. |
| 1.6 | Live CPU% / RSS readout in status bar (psutil) | proc_diag module | low | DONE -- _ProcStatsWidget on 1 Hz QTimer |
| 1.7 | Per-node paint timing (instrument QGraphicsItem.paint) | qt_nodes.py + perf_diag | medium | DONE -- class-level `NodeItem.paint` patch; subclass name stamped on `view._cg_node_class_name`. Real-session: ~9300 paints / ~975 ms / 0.105 ms avg, so paint() itself is **not** the pan/zoom bottleneck. |
| 1.8 | Per-action perf history view (Help > Show Perf Log) | _PerfLogDialog | low | DONE -- perf.log tail + paint_stats table |
| 1.9 | Pan/zoom-scoped cProfile capture | qt_gui.py View menu | low | DONE -- View > Profile Pan/Zoom (10s) dumps `panzoom_<ts>.prof` for `snakeviz`/`pstats`. |
| 1.10 | MinimapWidget pixmap cache | craftgraph/minimap.py | low | minimap was the dominant pan/zoom hotspot (0.797 s cum / 51% of a 1.56 s pan/zoom profile, 227 paintEvents at ~22 Hz, each walking every scene item incl. ports through `sceneBoundingRect`/`parentItem`/`hasattr` -- 236k port boundingRect calls, 199k parentItem calls, 199k hasattr calls). Static layer (background + node dots) only changes on topology/position edits, so we cache it as a QPixmap and only redraw the viewport overlay each paint. | DONE -- `_render_content_pixmap` builds the cached layer; `paintEvent` blits + overlays the viewport rect. Cache invalidates on resize, detach, and a 1 s rolling rebuild interval (catches node-move edits without wiring graph signals). Top-level filter moved before `sceneBoundingRect` so we never pay for ports we discard. Tests: `tests/test_minimap.py` (5 cases). **Profiler-verified:** minimap dropped from 0.797 s to 0.062 s (~13x cut) in the next pan/zoom capture; total profile 1.561 s -> 1.030 s. |
| 1.11 | Gate per-node paint instrumentation behind opt-in flag | craftgraph/perf_diag.py + craftgraph/qt_nodes.py | low | the `timed_paint` wrapper installed by `_install_node_paint_timing` was unconditional, so every NodeItem.paint paid a closure call + `from craftgraph import perf_diag` inline import + `getattr` + lock acquire on every paint, even when no one was looking at paint stats. Post-minimap profile showed it as the new #2 hotspot at 0.211 s cum (1794 paints -> ~24 ms pure wrapper overhead, ~11% of node paint cost). Data is only viewed via Help > Show Perf Log, so default the recording off. | DONE -- `perf_diag.set_paint_recording(bool)` + `is_paint_recording()`; `record_paint` early-returns when disabled; the `timed_paint` wrapper checks the flag first and only times+records when enabled. Hoisted `perf_counter_ns` / `record_paint` / module ref into the closure so the recording-on path is also cheaper (no per-paint inline import). `_PerfLogDialog` gained a `Record paint stats` checkbox + `Reset Stats` button so the diagnostic stays reachable on demand. Tests: `TestPaintRecordingToggle` in `tests/test_perf_diag.py` + `test_paint_does_not_record_when_disabled` in `tests/test_qt_nodes.py`. **Profiler-verified:** per-paint cost dropped from 0.118 ms to 0.087 ms (-26%); wrapper self time effectively zero (matched original_paint cumulative within noise). |
| 1.12 | Cache `PortItem.boundingRect` on the instance | craftgraph/qt_nodes.py monkey-patch over NodeGraphQt | low | post-wrapper-gate profile showed `PortItem.boundingRect` as the dominant raw call site at 193,684 calls / 0.171 s self / ~16% of profile. Each call rebuilt a `QRectF` from `_width + CLICK_FALLOFF, _height` -- values set once in `PortItem.__init__` (`PortEnum.SIZE.value`) and never mutated by NodeGraphQt or by us. Qt's scene index hit-tests every port on every mouse move, plus `PortItem.paint()` calls `self.boundingRect()` twice. | DONE -- `_install_port_bounding_rect_cache` patches `PortItem.boundingRect` once at module load: first call delegates to the original and stashes the QRectF on the instance as `_cg_br_cache`; subsequent calls return the cached instance. Idempotent via the `_cg_bounding_rect_cached` class sentinel, mirrors `_install_node_paint_timing`. Tests: `TestPortBoundingRectCache` in `tests/test_qt_nodes.py` (3 cases: cache identity, dimensions match original, per-instance isolation). **Profiler-verified:** per-call cost dropped from 0.88us to 0.28us (~3x); the original `port.py:41 boundingRect` is now bypassed (gone from the top hotspots). |
| 1.13 | Tiled `QBrush(QPixmap)` background grid | craftgraph/qt_gui.py | medium | post-port-cache profile showed `_patched_draw_bg` (our drawBackground patch) as the dominant remaining hotspot at 0.203 s / 412 paints / 0.49 ms each (~16% of frame budget). NodeScene's stock drawBackground iterates every visible grid coordinate per frame and issues `drawLines` calls for both the minor (`gs`) and major (`gs * 8`) grids; `drawLines` self time alone was 0.119 s. The grid pattern is static -- only its alignment with scene coordinates matters as the user scrolls. | DONE -- `_build_scene_grid_brush(scene)` renders one period of the grid (LINES: `gs * 8` square tile with minor lines at 1..7*gs and a major line at the tile boundary; DOTS: `gs` square tile with one pixel; NONE: solid bg color) into a QPixmap. Scene's `setBackgroundBrush(QBrush(pixmap))` makes Qt tile the pattern at the dirty-rect fill stage, replacing thousands of QPainter line ops with one cached blit per paint. `_patched_draw_bg` is now a no-op forward to `super(NodeScene, scene).drawBackground`. `_apply_node_editor_settings` rebuilds the brush via `_rebuild_grid_brush` whenever `grid_size` / `grid_style` / `show_grid` changes. Trade-off: zoom-dependent fade on the major grid is sacrificed (would need a brush rebuild per wheel step, which negates the win). Tests: `TestTiledGridBrush` in `tests/test_qt_gui.py` (3 cases: brush style is TexturePattern, tile dimensions match `gs * 8`, grid-size change rebuilds brush). **Profiler-verified:** per-paint cost dropped from 0.49 ms to 0.38 ms (-22%); `drawLines` and `_draw_grid` are gone from the top-20. Smaller cut than predicted because the tile blit itself isn't free (cProfile attributes the blit cost to `NodeScene.drawBackground` at 0.173 s self). |
| 1.14 | `cached_bounding_rect` lookup via `__dict__.get` | craftgraph/qt_nodes.py | low | DONE -- swapped `getattr` for `__dict__.get`; ~2x faster on the cache-hit path (skips descriptor protocol + default setup). ~30 ms shave on a 10s pan/zoom session. |

After 1.14, the remaining pan/zoom budget is dominated by Qt / NodeGraphQt internals (~80%): C++ scene index hit-tests, virtual paint dispatch, port circle rendering, pipe path drawing. Further significant cuts would require LOD rendering at low zoom, OpenGL viewport (5.1 INVESTIGATE -- risky with proxy widgets), or the alpha-roadmap GPU/Rust rewrite. **Pan/zoom optimization is parked here** -- per-paint cost has dropped from 6.9 ms (initial) to ~2.2 ms, frame budget violations are within 4 ms of the 33 ms target, and remaining wins are sub-50 ms per session.

#### 2. Algorithmic / data structure

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2.1 | Hash-based file change detection before reparse | 1 | watcher.py | low | DONE -- (st_ino, st_mtime_ns, st_size) triple cached in _RecipeEventHandler |
| 2.2 | Incremental graph rebuild (model diff, not full reload) | 2 | graph.py, _on_watcher_rebuild | high | watcher hitch on save vanishes | DONE -- new `craftgraph/model_diff.py` (`compute_diff`, `FileDiff`, `ProjectDiff`) plus `sync.apply_file_diff` (three-pass remove/add/modify with delete-and-re-add fallback for port-topology changes, runs inside the FileTab's existing `sync_guard` so the `UIToModelHandler` doesn't translate intermediate port_disconnected signals into spurious EditCommands); `_on_watcher_rebuild` rewritten as diff path with silent fallback to `load_recipes` on any exception; `SyncGuard.suspend_undo_for` extension + `_suspend_undo` context clear the NodeGraphQt undo stack on exit (matches existing full-reload behavior since QUndoStack has no pop-without-apply API); nine-scenario parity harness in `tests/test_incremental_rebuild_parity.py` (slow-marked) all green in 29.5 s. Also fixed a pre-existing bug where `QTimer.singleShot` from the Watchdog observer thread never fired (no Qt event loop on that thread) -- the watcher had been silently no-op for any actual file change. **Profiler-verified:** Tier-A one-file save→reload dropped from ~5067 ms to ~15 ms (337x speedup, well under the <200 ms target). Spec: `docs/superpowers/specs/2026-05-05-incremental-graph-rebuild-design.md`. Plan: `docs/superpowers/plans/2026-05-05-incremental-graph-rebuild.md`. |
| 2.2a | Port topology surgery without rebuild | 2 | sync.apply_file_diff topology fallback | medium | preserves connections + node identity when ingredient count changes | INVESTIGATE -- 2.2 currently delete-and-re-adds a node when `Ingredients` / `LinkedItemIDs` length changes. Cheap and correct, but discards inbound edges + node ID. An `apply_port_diff(node, added_ports, removed_ports, edge_map)` helper that mutates the existing node's input ports in place would preserve edges by ItemID. Trigger to revisit: profiler signals the delete-and-re-add path dominating watcher rebuild cost on Tier C, or user-visible edge-loss is reported. |
| 2.3 | Cycle-detection cache (dirty flag invalidation) | 1 | graph.py | low | DONE -- find_cycles memoized on graph keyed by (n_nodes, n_edges) |
| 2.4 | Bulk node creation in NodeGraphQt (signal blocker) | 1 | qt_gui.py load_recipes() | medium | DONE -- QSignalBlocker in _suspend_graph_updates; tooltip patches replayed on exit. Folder load 50%+ faster at scale. |
| 2.7 | Lazy parse -- background-prefetch variant | 2 | qt_gui.py tab open hook | medium | folder open finishes in O(file count) | INVESTIGATE -- evaluate later. Parse-all on Tier A is **75.6 ms** (1.6% of folder load); background-prefetch would shave at most that much. Cost: thread or QThreadPool wiring, cross-thread error paths, file-order preservation for stable tab ordering. Re-evaluate only if Tier C parse cost becomes a real fraction of the load wall-clock, or if the project moves to a directory-watcher model that re-parses on every save. |

#### 3. Concurrency (Python-level)

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 3.1 | QThread + worker for parser signals (anchor) | 2 | _open_folder, _on_watcher_rebuild | medium | folder open no longer freezes UI | INVESTIGATE -- evaluate later. Profile-driven, same as 2.7 / 4.1: parse-all on Tier A is **75.6 ms** (1.6% of folder load). The freeze users feel is the post-parse Qt scene mutation (populate_graph + per-node widget construction = ~4 s), and **NodeGraphQt is not thread-safe** -- nodes must be created on the main thread, so a parser worker thread cannot help with the actual cost. Phase 2's cooperative time-slicing (3.6) already keeps the UI responsive during the 4 s populate. |
| 3.2 | QThreadPool + QRunnable for parallel parse | 2 | parser.py | medium | tier A folder load parallelizes | INVESTIGATE -- evaluate later. Parallelizing 75 ms of work across cores would save tens of ms in the best case and could cost more from QThreadPool overhead + result aggregation. Same NodeGraphQt main-thread constraint as 3.1: post-parse populate must run serially anyway. |
| 3.3 | ProcessPoolExecutor with persistent worker pool | 2 | parser orchestrator | medium | bypasses GIL on multi-core | INVESTIGATE -- evaluate later. Same profile data as 3.1/3.2 plus cross-process serialization overhead (pickling ParsedFile dataclasses) likely costs more than the 75 ms it would save. Re-evaluate only if Tier C parse cost ever becomes >500 ms. |
| 3.4 | Python 3.14 free-threaded build (no-GIL) | track | runtime selection | high | parallel parse without process overhead -- track only, gated on PySide6 wheel compat | -- |
| 3.5 | Coalesce watcher events | 1 | watcher.py | low | DONE -- audit-only. `_schedule_rebuild` cancels-and-restarts debounce Timer on every event; per-event reparse filtered by 2.1's fast-path. |
| 3.6 | Cooperative time-slicing (QTimer-chained build) | 2 | load_recipes() | medium | DONE -- populate_graph `on_node_created` hook; CraftGraphWindow yields every 50 nodes via `processEvents(ExcludeUserInputEvents)` with a 10 ms budget. UI stays responsive during big load. |

#### 4. Native code / compiled extensions

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4.1 | mypyc compile parser (parser ladder rung 1) | 2 | parser.py, serializer.py | low | 2-4x parse speed | INVESTIGATE -- evaluate later. Measured parser-only cost on Tier A is **75.6 ms** (1.6% of the 4751 ms folder load). Even a 10x mypyc speedup saves <70 ms, invisible to users, in exchange for non-trivial build-hook complexity (hatch_mypyc, wheel distribution, CI changes). Re-evaluate only if Tier C becomes a real acceptance gate. Parser ladder satisfied: no rung selected. |
| 4.5 | msgspec for JSON layout cache | 1 | layout_store.py | low | DONE -- save/load_layout uses msgspec.json.encode/decode |

> **Parser native-compilation ladder.** 4.1, 9.3, 9.4, 9.5 all attack the same target (parser CPU time). Pick **at most one** rung. The escalation rule lives in Section 9: only climb if profiler proves the previous rung was not enough. Replace, don't stack -- one parser implementation at a time.

#### 5. GPU / rendering

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 5.1 | QOpenGLWidget viewport | 2 | NodeGraphQt viewer | low | pan/zoom 2-5x smoother | INVESTIGATE -- evaluate later when profiler signals it. The change itself is one line (`graph.viewer().setViewport(QOpenGLWidget())`), but `QGraphicsView` + `QGraphicsProxyWidget` (which every CraftGraph node uses for embedded text inputs / combo boxes) has known rendering issues under OpenGL on some GPUs. Phase 2's stylesheet cache already cut `_align_widgets_horizontal` cost 81% (`_draw_node_horizontal` 71%); post-Phase-2 frame-budget log shows pan/zoom is no longer the bottleneck at Tier A. Re-evaluate only if Tier C pan/zoom degrades or the live frame-time overlay shows steady-state >budget frames after section-6 wins. |
| 5.2 | Painter caching (ItemCoordinateCache, decoration items only) | 1 | qt_nodes.py | low | DONE -- _WarningOverlay uses ItemCoordinateCache |

#### 6. Qt/UI-specific

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 6.3 | Throttle code-edit -> reparse | 1 | qt_gui.py _parse_timer | low | DONE -- audited; default 400 ms already adequate |
| 6.6 | Pre-render node icons to QPixmap cache | 1 | qt_nodes.py | low | DONE -- `_render_sprite_pixmap` lru_cache(maxsize=256) |
| 6.7 | setStyleSheet cache on _NodeGroupBox | 2 | qt_nodes.py | low | DONE -- **~3.3 s saved on Tier A.** NodeGraphQt's `setTitleAlign` re-applies an identical stylesheet ~15,876 times per folder load (measured); per-instance cache short-circuits the no-op QSS reparse. Wired via `_install_stylesheet_cache_on_class(_NodeGroupBox)` so every group instance picks it up. |

#### 7. Architectural

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 7.2 | Read-through layout cache (verify-and-swap order) | 1 | layout_store.py | low | DONE -- verified `load_layout` precedes `compute_hierarchy_layout`; saved positions overlay solver result |
| 7.3 | Move serializer onto worker thread on save | 2 | _on_save_* actions | low | save no longer blocks | INVESTIGATE -- evaluate later. Measured serialize-all on Tier A: **0.3 ms** for all 6 files combined (faster than a single 16 ms frame). Threading overhead (signal hop + lifecycle) would cost more than the work it offloads. Re-evaluate only if a workload appears where serialize wall-clock ever shows up in the perf log. |

#### 8. Build / runtime mode  _(Phase 1 -- all entries)_

| # | Item | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 8.1 | PYTHONOPTIMIZE=2 for release builds | PyInstaller spec | low | DONE -- `just build` passes `--optimize 2` (zero asserts in `craftgraph/`, safe to strip) |
| 8.2 | uv run --no-dev smoke test | dev workflow | low | DONE -- `just smoke-no-dev` recipe + CI job |

#### 9. Post-optimization ideas (revisit after sections 1-8 land)

Items here are explicitly *out of scope* for the first performance pass. They go in only if the corresponding pathology shows up in profiler data after the main work lands. Documented so the option is not lost.

| # | Item | Where | Cost | Benefit | Trigger to revisit |
|---|---|---|---|---|---|
| 9.1 | Spatial index (R-tree via `rtree`) for hit-testing nodes _(was 2.8, optional)_ | NodeGraphQt scene | medium | O(log N) hit-test vs O(N) at tier C | Only if Qt's built-in `BspTreeIndex` proves insufficient on the 894-node reference set after section 5/6 land. Verify `setItemIndexMethod(BspTreeIndex)` first. |
| 9.2 | Async I/O for file reads (`asyncio.to_thread`, `aiofiles`) _(was 3.7, optional)_ | parser entry | low | helps when scanning many files | Only if profiler shows file I/O dominates parse cost on tier C (>50 files). Prefer `concurrent.futures.ThreadPoolExecutor` if revisited -- avoids the asyncio/Qt event-loop bridge. |
| 9.3 | Cython annotation of parser hot loops _(was 4.2, parser ladder rung 2)_ | `parser.py` `parse_blocks()` | medium | granular control over typed locals on inner-most loops | Only escalate from 4.1 (mypyc) if mypyc rejects code or measurable parser time remains after compile. Source files become `.pyx`, divergent from rest of codebase. Replaces 4.1, does not stack. |
| 9.4 | Rust parser via PyO3 + maturin _(was 4.3, parser ladder rung 3)_ | new `craftgraph_parser_rs/` | high | 10-50x parse speed; cross-platform wheels via `cibuildwheel` | Only escalate if 4.1 and 9.3 are insufficient and profiler still pins parser as >50% of folder-load wall-clock at tier C. Replaces the Python parser entirely -- do not maintain two implementations in parallel. |
| 9.5 | C++ extension via pybind11 _(was 4.4, last-resort rung)_ | parser hot path | high | comparable speedup to Rust | **Last resort** if 4.1, 9.3, and 9.4 all fail to deliver (e.g. Rust toolchain proves untenable for distribution). C++ has no memory safety, no clear advantage over Rust today; only consider if every other rung is blocked. |
| 9.6 | Floating-input refactor _(was 6.1, inline-widget ladder rung 2)_ | `qt_nodes.py` + every node subclass | high | ~90% widget reduction at tier C; faster paint as bonus | Escalate from 6.2 (lazy widgets) only if profiler/HWND data still shows proxy widgets dominating cost. Major rewrite of focus, autocomplete, undo, drag-drop. **Belongs in its own design cycle** -- reference, do not bundle into perf spec. Already documented in TODO.md "HWND Scaling -- Future Architectural Options". |
| 9.7 | Diff-based code-edit reapply _(was 6.4, optional)_ | parser | medium | only re-parses changed lines; tier-C typing in big files no longer rebuilds whole tab | Trigger to revisit: profiler shows full reparse > 50ms on tier C typing after 6.3 (throttle) and 3.6 (time-slicing) land. Requires partial-reparse support in parser; serializer round-trip becomes harder. |
| 9.8 | Background pre-build of inactive tab graphs _(was 7.1, optional)_ | `qt_gui.py` tab manager | medium | tab switch instant after pre-build completes | NodeGraphQt is not thread-safe -- nodes must be created on the main thread, so this isn't true off-thread work. Covered in v1 by 2.7 (background prefetch parse). Revisit only if tab switches still hitch after that lands. |
| 9.9 | Replace NetworkX with rustworkx _(was 2.5, demoted from v1)_ | `graph.py` | medium | 5-50x on cycle/topo at tier C | Demoted because at tier A (~50 nodes) NetworkX is plenty fast and gain is negligible. Revisit if Phase 1 profiler shows graph algos are a meaningful fraction of folder-load wall-clock at tier A, or if tier C becomes a real acceptance target. |
| 9.10 | Level-of-detail: hide widgets when zoomed out _(was 5.3, demoted from v1)_ | `qt_nodes.py` paint() | medium | tier C pan/zoom dramatic improvement | Demoted because at tier A node count, pan/zoom is bounded by total widget count, not LOD. Revisit if Phase 1 frame-time log shows pan/zoom exceeding budget at tier A, or if tier C becomes a real acceptance target. |
| 9.11 | Lazy widget allocation _(was 6.2; inline-widget ladder rung 1)_ | `qt_nodes.py` | medium | partial floating-input win | **DONE on `feat/lazy-widgets`** (Tasks 1-4: d4f0736, 1c76dcf, 0ef0d0f, 1ad4c62, f047e05). Class-level `NodeItem.paint` patch (`_install_lazy_widget_build`) defers `_build_from_registry` / `_fix_widget_z_order` / `validate_required_fields` to first paint. Lazy `populate_from_model` defers + replays inside `_maybe_build_widgets` (fixes the prior populate-before-paint failure). Lazy `get_property` / `set_property` cover sync-layer + test paths. Two production fixes uncovered by tests: deserialize wrapper forces eager build during paste/duplicate (NodeGraphQt's `_deserialize` writes via `node.model.set_property` directly, bypassing our override), and `SpriteNode.__init__` forces eager build for its `textChanged` listener. **Two-run heap-corruption gate clean** across `test_qt_nodes` (167/167), `test_qt_gui` (467/467), `test_sync` (106/106), `test_apply_file_diff` (11/11), `test_minimap` (5/5), parity (9/9). **Profiler-verified:** offscreen Tier-A load drops from 4751 ms (post-Phase-2) to 1748 ms (-63%, exceeds 30% target), but on the Windows platform the `app.processEvents()` paint pump triggers `_maybe_build_widgets` on all 160 visible nodes during load (1511 ms / 160 calls), so wall-clock load is statistically flat (+1.5%). The architecture is correct; benefit materializes when nodes stay off-viewport in real-user pan/zoom workflows -- not during the initial paint-everything load. `apply_code_editor_text` measurement deferred for hand-driven user capture. Baselines: `docs/perf-baselines/2026-05-10-tier-A-post-lazy-widgets.md`. Plan: `docs/superpowers/plans/2026-05-06-lazy-widget-construction.md`. **Inline-widget ladder:** 9.11 is rung 1, 9.6 (floating-input refactor) is rung 2 -- escalate only if real off-viewport workflows still show widget cost dominating. |
| 9.12 | Real GPU usage queries (D3D / Vulkan / Metal) | new gpu_diag.py | high | quantifies render-side cost vs CPU widget cost | Heavy: needs platform-specific bindings (D3D query interface on Windows, MoltenVK / Metal on macOS). Only revisit if frame-time overlay (1.3) consistently shows >budget frames AND CPU profile rules out widget construction. Until then, frame_ms from `report_frame()` is the best signal we have. |

---

### Recipe Import / Snippet Paste

- [ ] **Import recipe from known IDs:** Context menu listing all known recipes (vanilla 498 + mod-compat 120). Spawns fully linked recipe node with ingredients pre-wired. "Snippet paste" for modders.
- [ ] **Batch import:** Import multiple related recipes at once as connected subgraph.
- [ ] **Template recipes:** User-defined templates saved to file, available in context menu.

---

## Post-Release Features

### Tab ID Autocomplete

- [ ] **Extend autocomplete to CraftingTab IDs:** Suggest tab path segments when editing `Path` fields. Source from parsed CustomFabricator/CustomCraftingTab entries + static vanilla fabricator tabs.

### Unlock Condition Visualization and Editing

> Requested by CC3 mod developer. Unlock conditions are key to mod design but invisible in graph.

**CC3 unlock semantics (verified against C# `ModifiedRecipe.HandleUnlocks()`):**
- **`Unlocks: X, Y;`** -- crafting this unlocks ALL listed items (batch `KnownTechHandler.SetAnalysisTechEntry`).
- **`UnlockedBy: A, B, C;`** -- OR logic. Unlocks when **any one** scanned. CC3 loops through each prerequisite, registers recipe independently.

**Feature scope:**
- [ ] **Unlock edges in dependency graph:** Distinct edge type (dashed/different color) for unlock relationships. `Unlocks: X` = edge from recipe to X. `UnlockedBy: A` = edge from A to recipe (OR semantics).
- [ ] **Unlock fields in edit dialogs:** Per-recipe editing of `Unlocks`/`UnlockedBy` as comma-separated TechType lists with autocomplete. Show OR semantics clearly (label: "Unlocked by (any of):").
- [ ] **Visual distinction for OR vs AND:** Different line style/color for "any-of" (UnlockedBy) vs "all-of" (Unlocks). Consider "OR" / "ALL" badge.

### Welcome Screen / Recent Files Polish

- [ ] **Full path tooltip on recent entries:** Show complete path on hover.
- [ ] **Visual separation between projects and folders:** Headers, dividers, or grouped sections.
- [ ] **Non-C: drive paths split across two lines:** Drive letter (e.g. `D:`) on one line, rest on next. Likely label word-wrap/elide treating `:` as line-break point. `[high priority]`

### ~~Tabs as Nodes (formerly Step 11d)~~ -- Absorbed into Step 11f

> Merged into Step 11f. All tab/fabricator NodeKind work, visuals, context menu, serializer round-trip covered there.

### HWND Scaling -- Future Architectural Options

> Documented now so the options are not lost. Neither is committed to. Only consider if the HWND hardening plan's Phase 1 numbers, after Phases 2 and 3 land, still show proxy widgets dominating handle usage.

- [ ] **Floating-input refactor (the "Blender / UE5" pattern).** Replace per-node embedded widgets (`QLineEdit`, `QSpinBox`, combo) with painted text in the node's `paint()` and a single shared editor widget that flies to the clicked field, commits on Enter, then hides. Goes from ~8 widgets per node x N nodes down to 1 floating widget total.
  - **Pros:** dramatic handle reduction (potentially 90%+ at 894 nodes); rendering is faster too; matches how Blender / UE5 / Houdini node editors handle inline editing at scale.
  - **Cons:** big architectural change touching `qt_nodes.py`, `qt_variable_nodes.py`, every node subclass; keyboard focus, autocomplete attachment, undo, drag-drop into pins all need rework; loses NodeGraphQt's built-in widget conveniences.
  - **When justified:** only if Phase 1 numbers + Phase 2 fixes still show proxy widgets dominating the leak; otherwise the cost is not earned.
- [DONE] **Lazy custom-widget allocation.** See row 9.11 above for full closeout. Architecture works (offscreen 63% cut), but Tier-A wall-clock load is flat because the initial paint pump still builds every visible node. The deeper floating-input refactor (9.6) is the next rung if real off-viewport workflows still show widget cost dominating. Branch `feat/lazy-widgets` retained; merge per `superpowers:finishing-a-development-branch`.

---

## AFTER ALPHA ROADMAP

> Big architectural features requiring own branch and design cycle. Not blocking alpha.

### Unified Project Editor (replaces per-file tab model)

**Priority:** Post-alpha, high impact
**Depends on:** All Phase A-C complete, stable per-file editing
**Effort:** Large -- own design + plan + implementation cycle

Current editor is **file-centric**: each file gets own tab with own NodeGraph. Mirrors CC3's one-block-type-per-file constraint, but fabs/tabs and referencing recipes live in separate graphs. Users must manually type path strings, error-prone and disconnected from visual editor.

Unified project editor replaces per-file tabs with **single project-wide graph** showing all fabs, tabs, recipes from all files. Recipes connect directly to fab/tab nodes visually. Export auto-splits back into per-file format.

**Enables:**
- Direct visual wiring of recipes to fabs/tabs (drag connection instead of typing path)
- Full project overview in one canvas
- Eliminates "Get Fabricator" / "Get Tab" reference nodes (fabs and recipes coexist)
- Hierarchy changes auto-propagate to all connected recipes

**Already exists:**
- Parser handles directory loading, returns `list[ParsedFile]` with `source_path`
- `connect_hierarchy()` wires fabs/tabs/recipes across full model
- Serializer works per-ParsedFile independently
- CC3's one-block-type-per-file rule makes auto-splitting deterministic

**Needs building:**
- [ ] **Project view mode**: Single NodeGraph showing nodes from all loaded files. May keep per-file tabs as secondary "file focus" view.
- [ ] **File-assignment logic**: Determine which file new node belongs to. Match by block type to existing files, or create new files. User override via "Move to file..." context menu.
- [ ] **Visual file grouping**: Color-code or label nodes by source file. Optional: collapsible file groups, file boundary indicators.
- [ ] **Auto-split export**: Group models by block type and source file, serialize each ParsedFile independently. Handle new nodes without source file.
- [ ] **Cross-file hierarchy wiring**: Direct node connections replace path strings. App computes and stores path string auto. Hierarchy changes update all affected paths.
- [ ] **Migration path**: Per-file editing still works during transition. Unified view is additive.

---

## Quick Reference: Remaining Work

```
  Phase 1 (CLI pipeline) ........... DONE (see CHANGELOG.md)
  GUI Migration (M1-M8) ............ DONE (see CHANGELOG.md)
  Steps 11f-11i (Qt GUI) ........... DONE (see CHANGELOG.md)
          |
  Step 11h (Recipe-to-Recipe Links) --- Direct DAG wiring
  Step 11j (Validation Warnings) ------ DONE (cycle paths, tab cycles, reassignment, export checks)
          |
  Step 12 (Bidirectional Code Editor) - Multi-panel IDE layout
          |
  Known Bugs / UX Fixes
  Accessibility / Settings
  Niche QOL Ideas
  Post-Release Features
```
