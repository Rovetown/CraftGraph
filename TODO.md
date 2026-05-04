#### BIG INBETWEEN NEEDED TO BE SOLVED!!!
The file "GEMINI_SOLUTION.md" has important info and potential bug fixes for us!

#### TEST RUNNER -- regression sweep hangs / times out

- [DONE] **Investigate why `uv run --extra qt pytest tests/test_qt_gui.py` hangs.** _Two layered causes. (1) Pipe buffering on the agent shell: `2>&1 | tail` and `Select-Object -Last` capture only the final tail of stdout, so progress dots never flush mid-run. Fix: redirect to a file with `>file 2>&1` and tail the file -- output streams as expected. (2) Real test hang at test #28, `tests/test_qt_gui.py::TestMenuBar::test_settings_dialog_opens` -- 27 prior tests pass in seconds, then pytest stalls indefinitely. Likely a modal `QDialog` call without monkey-patching to dismiss it; in an interactive shell the dialog can be closed by the user, but in the headless agent shell the modal loop waits forever. **Action items below.**_
- [DONE] **Add `just test-fast` and `just test-qt` recipes.** _`test-fast` runs every non-Qt-window test file (test_qt_nodes + parser/graph/sync/serializer/watcher/perf_diag/proc_diag/mem_diag) and finishes in ~10 s -- proven 629/634 in 9.37 s on this branch. `test-qt` runs the full Qt suite (test_qt_gui + test_qt_nodes) with PYTHONUNBUFFERED=1, `-s`, `--tb=line`; finishes 609/609 in ~38 s under the agent shell after the dialog-stub migration below._
- [DONE] **Patch modal-dialog tests so they never block headless.** _Production code migrated from `QDialog.exec_()` to `QDialog.exec()` in commit a46e127, but 10 monkey-patch stubs in test_qt_gui.py kept patching `exec_` -- a method nobody calls anymore -- so the real modal ran and stalled the headless agent shell. Migrated every `exec_` stub to `exec` (and dropped the redundant double-stub in TestMeasureWrappers.test_open_settings_writes_log_entry). Full sweep now passes 609/609 in 38 s._
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

- [DONE] **1. Tab persistence (close-time only, not lazy switch).** _`_tear_down_tabs()` now setParent(None) + deleteLater on each graph widget and editor after stack removal, deleteLater on each parse_timer, detaches the minimap, and clears per-tab `model_to_node`/`orphan_nodes`/`user_positions` dicts. Letting Qt's parent-chain destruction cascade naturally (instead of pre-emptively calling `NodeGraph.delete_node`, which only detaches QGraphicsItems from the scene without freeing them) drops widget growth from 4864 to 210 over 10 open/close cycles. Stress test `open_close_folder_x10` widget threshold ratcheted from 500 to 275. Remaining residue is NodeGraphQt's top-level TabSearch popup widgets (parent-less by design)._
- [DONE] **2. Context menu lifecycle.** _Audit-only fix. No `QMenu()` direct construction exists in our code. Menu bar is built once at startup (`menuBar().addMenu/addAction`); recent-files submenu uses `clear()` + `addAction` repopulation (pattern (a)); NodeGraphQt context menus are retrieved via `get_context_menu()` (reused instance, pattern (a)) and re-used by NodeGraphQt's own `contextMenuEvent`. Stable baseline over 3 runs: 0 widget delta and 0 HWND delta. Stress test `context_menu_x50` thresholds ratcheted from HWND=50 / widgets=100 to HWND=25 / widgets=25, with a new widget assertion._
- [DONE] **3. Settings dialog rebuild.** _SettingsDialog now scheduled for `deleteLater()` after the modal `exec_()` returns and `_apply_settings_from_dialog` has read its values. Stress test `open_close_settings_x20` widget threshold ratcheted from 200 to 150 (measured stable delta of 120 over 20 cycles, down from 9460 pre-fix). The audit-only "_clear_layout helper + signal-disconnect" approach in the original spec was unnecessary -- destroying the dialog disposes its children and disconnects its signals automatically.
- [DONE] **4. Multi-folder teardown.** _Largely subsumed by fix #1: `load_recipes()` already calls `_tear_down_tabs()` first, `_path_words` is fully replaced (not appended) on every load via `_recompute_path_completions()`, and `_id_words` does not depend on the folder so it stays correctly cached. The new `multi_folder_swap_x3` stress test surfaced one extra residual leak: NodeGraphQt's per-viewer `TabSearchMenuWidget` is parent-less, so the natural QWidget destruction chain leaves it orphaned. `_tear_down_tabs()` now `setParent(None) + deleteLater` on each viewer's `_search_widget`. Measured: 93 widgets / 9 loads. Threshold set to 150. As a side benefit, `open_close_folder_x10` widget delta dropped from 210 to 148 (threshold ratcheted 275 → 200)._
- [DONE] **5. Watcher rebuild (audit-first, fix optional).** _Audit-only. `_on_watcher_rebuild()` calls `self.load_recipes(self._source_path)`, which routes through the `_tear_down_tabs()` destruction path already hardened by fixes #1 and #4. No fresh leak surface. Stable baseline over 3 runs: 180 widgets / 10 rebuilds (~18/cycle, same NodeGraphQt popup residue), 1 HWND. Test tightened: added `widget_count` assertion, ratcheted HWND 100→25 and widgets 200→225 to lock the clean baseline. Model-diff (incremental rebuild) was scoped out -- the wholesale reload through `load_recipes()` is now efficient enough that the rewrite isn't justified by the data._

### Phase 3 -- Preventive hardening

- [DONE] **A. `AA_DontCreateNativeWidgetSiblings` flag.** _Set on `QtCore.QCoreApplication` in `launch_qt_gui()` immediately before constructing the first `QApplication`. Removes a class of accidental native HWND growth at scale. Existing stress tests pass at the previously ratcheted thresholds; live snapshot for a fresh window with EquipmentSalvage loaded reports 395 USER / 206 GDI / 602 widgets, well within Windows soft caps._
- [DONE] **B. Parenting audit.** _Targeted review of leak-prone QObject constructors across `qt_gui.py`, `qt_nodes.py`, `qt_variable_nodes.py`, `welcome.py`, `tooltips.py`, `minimap.py`. Findings: zero `QMenu()` direct constructions; all `QDialog`/`QMessageBox`/`QInputDialog` calls pass an explicit parent (1 site); all 5 `QTimer` constructions pass `self` as parent; both `QCompleter` calls pass `parent or self`. The remaining ~326 `Qt*.Q*` hits in `qt_gui.py` are dominated by value objects (`QColor`, `QPen`, `QRectF`, `QPointF`, `QPixmap`) or widgets that are immediately added to a layout via `addWidget`/`addLayout` (which reparents). The single intentional unparented `QWidget()` is the module-level `_GROUPBOX_PARENT` singleton in `qt_nodes.py:102`, used as a hidden parent for `_NodeGroupBox` instances; it has process lifetime and is correctly annotated. No code changes were needed -- the existing patterns are sound._

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
| 1.1 | cProfile harness with tiered workloads (B/A/C) | tests/test_perf_*.py analog of test_hwnd_stress.py | low | establishes truth before tuning | DONE -- tests/test_perf_stress.py with Tier A regression gate |
| 1.2 | perf_diag.measure(action) analog of hwnd_diag.measure | wraps _open_folder, _on_watcher_rebuild, code-edit handler | low | per-action wall-clock + frame budget | DONE -- perf_diag module; wired around load_recipes / settings / watcher / code-edit |
| 1.3 | Qt frame-time overlay (debug-only) | qt_gui.py View menu toggle | low | visible fps during pan/zoom | DONE -- View > Show Frame Time + report_frame budget logger |
| 1.4 | tracemalloc snapshots tied to actions | new mem_diag.py | low | pairs with hwnd_diag for total picture | DONE -- mem_diag module + Help > Dump Memory Snapshot |
| 1.5 | Release-vs-dev baseline: pyinstaller --onefile build, run same workload | one-time | medium | quantifies how much "feels slow" is the dev interpreter | -- |
| 1.6 | Live CPU% / RSS readout in status bar (psutil) | new perf widget in qt_gui.py status bar | low | per-second CPU + memory visible without dumping snapshots | DONE -- proc_diag module + _ProcStatsWidget on 1 Hz QTimer |
| 1.7 | Per-node paint timing (instrument QGraphicsItem.paint) | qt_nodes.py + perf_diag aggregator | medium | identifies which node subclass dominates pan/zoom paint cost | DONE -- record_paint / paint_stats / reset_paint_stats API in perf_diag (paint-side wiring deferred with the rolled-back lazy-build patch) |
| 1.8 | Per-action perf history view (Help > Show Perf Log) | new dialog reading perf_diag log file | low | trend visibility without grepping log files | DONE -- _PerfLogDialog (perf.log tail + paint_stats table) |

#### 2. Algorithmic / data structure

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2.1 | Hash-based file change detection (mtime + size + sha1 fast path) before reparse | 1 | watcher.py -> parser.py boundary | low | watcher rebuild only re-parses changed files | DONE -- (st_ino, st_mtime_ns, st_size) triple cached in _RecipeEventHandler |
| 2.2 | Incremental graph rebuild (model diff, not full reload) | 2 | graph.py, _on_watcher_rebuild | high | watcher hitch on save vanishes | -- |
| 2.3 | Cycle-detection cache (dirty flag invalidation) | 1 | graph.py find_cycle() | low | skip cycle re-run when graph unchanged | DONE -- find_cycles memoized on graph.graph keyed by (n_nodes, n_edges) |
| 2.4 | Bulk node creation in NodeGraphQt (signal blocker) | 1 | qt_gui.py load_recipes() | medium | folder load drops 50%+ at scale | DONE -- QSignalBlocker added to _suspend_graph_updates; tooltip patches replayed after exit |
| 2.7 | Lazy parse -- background-prefetch variant | 2 | qt_gui.py tab open hook | medium | folder open finishes in O(file count) | -- |

#### 3. Concurrency (Python-level)

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 3.1 | QThread + worker for parser signals (anchor) | 2 | _open_folder, _on_watcher_rebuild | medium | folder open no longer freezes UI | -- |
| 3.2 | QThreadPool + QRunnable for parallel parse | 2 | parser.py | medium | tier A folder load parallelizes | -- |
| 3.3 | ProcessPoolExecutor with persistent worker pool | 2 | parser orchestrator | medium | bypasses GIL on multi-core | -- |
| 3.4 | Python 3.14 free-threaded build (no-GIL) | track | runtime selection | high | parallel parse without process overhead -- track only, gated on PySide6 wheel compat | -- |
| 3.5 | Coalesce watcher events (audit existing debounce) | 1 | watcher.py | low | reduces duplicate rebuilds | DONE -- audit-only. `_schedule_rebuild` already cancels-and-restarts the debounce Timer on every event so an arbitrary burst within `watcher_debounce_sec` collapses to exactly one rebuild. Per-event reparse is filtered by the (st_ino, st_mtime_ns, st_size) fast path from 2.1. No change warranted. |
| 3.6 | Cooperative time-slicing (QTimer-chained build) | 2 | load_recipes() | medium | UI stays responsive during big load | DONE -- populate_graph gained on_node_created hook; CraftGraphWindow yields every 50 nodes via processEvents (10 ms budget, ExcludeUserInputEvents) |

#### 4. Native code / compiled extensions

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 4.1 | mypyc compile parser (parser ladder rung 1) | 2 | parser.py, serializer.py | low | 2-4x parse speed | DONE -- decision: skip. Measured parser-only cost on Tier A is **75.6 ms** (1.6% of the 4751 ms folder load). Even a 10x mypyc speedup saves <70 ms, invisible to users, in exchange for non-trivial build-hook complexity (hatch_mypyc, wheel distribution, CI changes). Re-evaluate only if Tier C becomes a real acceptance gate. Parser ladder satisfied: no rung selected. |
| 4.5 | msgspec for JSON layout cache | 1 | layout_store.py | low | freebie for large layout files | DONE -- save/load_layout uses msgspec.json.encode/decode |

> **Parser native-compilation ladder.** 4.1, 9.3, 9.4, 9.5 all attack the same target (parser CPU time). Pick **at most one** rung. The escalation rule lives in Section 9: only climb if profiler proves the previous rung was not enough. Replace, don't stack -- one parser implementation at a time.

#### 5. GPU / rendering

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 5.1 | QOpenGLWidget viewport | 2 | NodeGraphQt viewer | low | pan/zoom 2-5x smoother | DONE -- decision: skip until profiler signals it. The change itself is one line (`graph.viewer().setViewport(QOpenGLWidget())`), but `QGraphicsView` + `QGraphicsProxyWidget` (which every CraftGraph node uses for embedded text inputs / combo boxes) has known rendering issues under OpenGL on some GPUs. Phase 2's stylesheet cache already cut `_align_widgets_horizontal` cost 81% (`_draw_node_horizontal` 71%); post-Phase-2 frame-budget log shows pan/zoom is no longer the bottleneck at Tier A. Re-evaluate only if Tier C pan/zoom degrades or the live frame-time overlay shows steady-state >budget frames after section-6 wins. |
| 5.2 | Painter caching (ItemCoordinateCache, decoration items only) | 1 | qt_nodes.py decoration overlays | low | skip repaint on unchanged decorations | DONE -- _WarningOverlay uses ItemCoordinateCache |

#### 6. Qt/UI-specific

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 6.3 | Throttle code-edit -> reparse (audit existing _parse_timer) | 1 | qt_gui.py _parse_timer | low | typing latency drops | DONE -- audited; default 400 ms already adequate |
| 6.6 | Pre-render node icons to QPixmap cache (lru_cache) | 1 | sprite_loader.py | low | first-paint flash reduced | DONE -- _render_sprite_pixmap lru_cache(maxsize=256) in qt_nodes.py |
| 6.7 | setStyleSheet cache on _NodeGroupBox (skip no-op restyles) | 2 | qt_nodes.py _patched_set_custom_widget | low | NodeGraphQt's setTitleAlign re-applies an identical stylesheet thousands of times per redraw; cache short-circuits ~3.3 s of QSS reparse on Tier A | DONE -- _install_stylesheet_cache wired onto every _NodeGroupBox at construction |

#### 7. Architectural

| # | Item | Phase | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 7.2 | Read-through layout cache (verify-and-swap order) | 1 | layout_store.py | low | skip auto-layout on second open | DONE -- verified load_layout precedes compute_hierarchy_layout; saved positions overlay solver result |
| 7.3 | Move serializer onto worker thread on save | 2 | _on_save_* actions | low | save no longer blocks | -- |

#### 8. Build / runtime mode  _(Phase 1 -- all entries)_

| # | Item | Where | Cost | Benefit | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 8.1 | PYTHONOPTIMIZE=2 for release builds | PyInstaller spec | low | strips assertions, docstrings | DONE -- just build passes --optimize 2 (zero asserts in craftgraph/, safe to strip) |
| 8.2 | uv run with --no-dev for smoke tests | dev workflow | low | catches dev-mode-only artifacts | DONE -- just smoke-no-dev recipe + smoke-no-dev CI job |

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
| 9.11 | Lazy widget allocation _(was 6.2, demoted from v1; inline-widget ladder rung 1)_ | `qt_nodes.py` | medium | partial floating-input win | **ATTEMPTED in Phase 2 -- reverted.** Deferring `_build_from_registry()` to first paint broke `populate_from_model` (called synchronously after node create) -- newly built widgets re-seeded from default values instead of populated model state, and the per-instance paint patch produced heap corruption (0xc0000374) under the regression suite. Needs a redesign that handles populate-before-paint and patches paint at the class level. **Inline-widget ladder:** 9.11 is rung 1, 9.6 (floating-input refactor) is rung 2. |
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
- [ ] **Lazy custom-widget allocation.** Softer alternative to the floating-input refactor. Keep proxy widgets but only instantiate them when a node enters the visible viewport (or on first focus). Out-of-view nodes hold stub widgets.
  - **Pros:** less invasive than the floating-input refactor; partial saving (proportional to off-screen ratio); preserves existing widget behavior.
  - **Cons:** clever lifecycle is bug-prone (focus loss on scroll, drag-drop into stubs); complexity grows for marginal saving compared to the floating-input refactor.
  - **When justified:** skip unless data points clearly to it -- the floating-input refactor wins on every axis except invasiveness.

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
