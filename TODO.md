# TODO

Remaining build plan. Completed work lives in `CHANGELOG.md` and git history; this
file tracks only what is left, plus a record of the performance techniques shipped.

---

## Test infrastructure

- [x] **Faster, nicer test runs.** `test_qt_gui`, `test_perf_stress`, `test_hwnd_stress`,
  and `test_incremental_rebuild_parity` are tagged `@pytest.mark.slow` at module level.
  `just test` excludes them (1490 passed / 5 skipped in ~10s); `just test-all` runs
  the full suite; `just test-slow` runs only the tagged set. The autouse
  `_reap_file_watchers` reaper was hoisted from `test_qt_gui.py` to `tests/conftest.py`
  so any test file that builds a `CraftGraphWindow` is still safe from the leaked
  Watchdog thread / heap-corruption regression once test_qt_gui is excluded. Later
  retired entirely at `f29057c` after sub-project 4 routed every construction
  through `make_test_window(qtbot)` and qtbot's lifecycle replaced the reaper.

- [x] **Defensive `save_project` / closeEvent on empty `project_path`.** Shipped:
  `closeEvent` (both fast path and DISCARD) now routes through a `_persist_project_state`
  helper that no-ops when `self._project is None or not self._project.project_path`.
  The two `TestProjectCustomIdPersistence` try/finally workarounds are gone; a new
  `test_close_with_empty_project_path_is_no_op` regression test guards the contract.

- [x] **Robust patch-script pattern for mass test-file refactors.** Documented in
  CLAUDE.md (`Bulk test-file refactors` section): use ` *` (not `\s+`) for indent,
  handle multi-line `def test_x(...):` signatures across newlines, run the suite
  after each script.

> **Resolved knowledge -- headless test hangs.** Traced to three causes:
> (1) **Pipe buffering** -- `2>&1 | tail` only flushes the tail of stdout; redirect to
> a file with `>file 2>&1` and tail the file instead.
> (2) **Modal dialog stubs** -- production moved from `QDialog.exec_` to `QDialog.exec`
> (commit a46e127); test monkey-patches still on the underscore alias stopped
> intercepting the real modal and blocked the headless loop.
> (3) **Leaked watcher threads -> heap corruption** -- `test_qt_gui.py` windows that
> load a folder start a Watchdog observer thread; tests never closed their windows,
> so observer threads leaked and one racing main-thread GC corrupted the heap.
> Fixed by the autouse `_reap_file_watchers` teardown. Any future fixture that starts
> background threads must reap them on teardown.

---

## Pre-alpha

- [x] **TabID autocomplete in `Path` fields.** Shipped: `_update_path_completions`
  now mirrors `_path_targets_from_parsed_files` and adds `Fab/TabID` and
  `parent/TabID` composites to `_path_words` for every CraftingTab (both top-level
  `pf.crafting_tabs` and ones nested inside `pf.custom_fabricators`). Previously the
  validator accepted those paths but the autocomplete dropdown only suggested them
  after a recipe already used them once. Regression guard: `TestPathAutocompleteTabIDs`
  in `test_qt_gui.py` (2 tests).
- [x] **Unlock / UnlockedBy visualization + editing.** Shipped in three pieces:
  (1) `_ID_WIDGET_NAMES` extended with `unlocks`, `unlocked_by`, `linked_item_ids`
  so TechType autocomplete attaches to all three CSV fields on summon; (2) `build_graph`
  now emits unlock edges with an `edge_kind` attribute (`ingredient`/`unlocks`/
  `unlocked_by`), and ingredient takes precedence when a pair overlaps; (3)
  `visualizer.generate_html` reads `edge_kind` and styles `unlocks` solid green
  (`UNLOCKS_EDGE_COLOR`), `unlocked_by` dashed orange (`UNLOCKED_BY_EDGE_COLOR`);
  cycle red still overrides. Regression guards: `TestNodeAutocomplete` (+2 tests),
  `TestBuildGraphUnlocks` (5 tests in `test_graph.py`), `test_visualizer.py` (new file,
  4 tests). NOT shipped: in-Qt-node-editor visual overlay for unlock relationships --
  CSV-content-driven overlay edges between nodes were deferred as a separate sub-project.
- [x] **Full filename tooltip on tab hover.** Shipped: all 3 production
  `setTabToolTip` call sites in `qt_gui.py` (initial `_create_file_tab`, watcher
  diff add path, folder-load loop) now pass `pf.source_path.name` instead of
  `str(pf.source_path)`. Hover shows `MyRecipes.txt` instead of leaking the parent
  directory path. `TestTabBarTooltips::test_loaded_file_tab_tooltip_is_filename`
  guards both halves: filename is present, directory string is not.

- [x] **Project Issues window.** Shipped. Menu entry `Edit -> Find Issues...`
  opens a modeless QDialog with a `QTreeWidget` of 3 sections (Orphans / Cycles /
  Unresolved References) populated from the pure-Python
  `craftgraph.diagnostics.find_project_issues`. Click a row to jump to the
  defining tab + node via `_jump_to_id`. Auto-refreshes on model change and
  watcher diff via a 300 ms debounced `QTimer`. All 5 sub-tasks below complete.

  - [x] **(1) Issue-detection data layer.** Shipped: `craftgraph/diagnostics.py`
    is a pure-Python (no Qt) module exporting `OrphanIssue`, `CycleIssue`,
    `UnresolvedRefIssue`, `ProjectIssues`, and
    `find_project_issues(parsed_files, *, known_extra_ids=None) -> ProjectIssues`.
    Orphans = recipe items with in-degree 0 across ingredient + unlock edges;
    cycles delegate to `graph.find_cycles`; unresolved refs scan `ingredients`,
    `unlocks`, `unlocked_by`, and `linked_item_ids` against a case-insensitive
    known set (project-defined IDs + vanilla + mod-compat). `Path` validation is
    intentionally NOT covered yet -- requires moving `_path_targets_from_parsed_files`
    out of `qt_gui.py`; leave that for a follow-on. 18 tests in
    `tests/test_diagnostics.py`, including an integration test against the
    committed `tests/fixtures/mini_mod/`.
  - [x] **(2) Empty window scaffolding.** Shipped: `_ProjectIssuesDialog` is a
    modeless `QDialog` (does not block the main window). New menu entry
    `Edit -> Find &Issues...` sits next to `Find Node...`. `CraftGraphWindow`
    lazily creates the dialog on first trigger and stores it on
    `self._project_issues_window`; `_on_open_project_issues` raises and activates
    on every subsequent trigger so the action is idempotent. The dialog shows a
    centered placeholder QLabel: "No project loaded -- open a folder or file to
    scan for issues." 6 tests in `TestProjectIssuesWindow` cover: menu-action
    presence, first-trigger creation, second-trigger same-instance,
    placeholder-text visible, close-doesn't-unload-data, reopen-after-close.
  - [x] **(3) Render the data.** Shipped: `_ProjectIssuesDialog` now uses a
    `QTreeWidget` with 3 top-level sections (`Orphans`, `Cycles`,
    `Unresolved References`), counts in headers (`Orphans (3)`), empty sections
    show a single literal "None" child (visible, so users see the gate passed).
    Row formatting: orphans = `ItemID  -  filename.txt`, cycles =
    `A -> B -> A` (loop closed visually), unresolved = `Owner.ref_type -> Target  -  filename.txt`.
    `CraftGraphWindow._refresh_project_issues` collects parsed files from open
    tabs, runs `find_project_issues`, and calls `populate`. Refresh fires on
    every menu trigger (open or already-open) so the user always sees current
    state. NOT yet shipped: auto-refresh on save / file change -- sub-task (5).
    Line numbers in rows -- parser doesn't track line offsets in the model;
    deferred until that becomes a separate need. 5 new tests in
    `TestProjectIssuesWindow` (sections, empty-state, orphan row, cycle row,
    unresolved row); the placeholder-text test from sub-task (2) was replaced
    with `test_window_shows_section_headers` to track the new contract.
  - [x] **(4) Jump-to-tab/node on row click.** Shipped: extracted `_jump_to_id`
    from the existing `_go_to_definition` so the same plumbing accepts a bare
    item id (no source node needed). `_ProjectIssuesDialog` gained an
    `item_activated = Signal(str)` and stores per-row jump targets in
    `Qt.UserRole` data; double-click / Enter on a row emits the signal.
    `_on_open_project_issues` connects the signal to `_jump_to_id` on first
    creation. Target id per row: orphan -> the item itself; cycle -> the cycle's
    first item; unresolved -> the OWNER recipe (target doesn't exist by
    definition). Section headers and the "None" placeholder rows carry no
    target and are silently ignored. NOT shipped: auto-opening files that are
    in the project folder but not currently in any tab -- the issues window
    only sees data from open tabs, so the case doesn't arise yet. 4 new tests
    in `TestProjectIssuesWindow` (orphan / cycle / unresolved / none-row noop).
  - [x] **(5) Auto-refresh on change.** Shipped: `CraftGraphWindow` gained a
    single-shot 300 ms `QTimer` (`_project_issues_refresh_timer`) and a
    `_schedule_project_issues_refresh()` helper that restarts the timer on each
    call (multiple rapid edits collapse to one refresh). Hooked into
    `_on_model_changed` (covers EditHistory paths -- user edits, undo, redo,
    code-editor reparse) and `_apply_watcher_diff` (covers external file
    changes via Watchdog). Schedule is a no-op when the dialog has never been
    opened or is hidden -- no point scanning while nobody is looking. 4 new
    tests in `TestProjectIssuesWindow`: no-op when never opened, no-op when
    hidden, model-change starts the timer, end-to-end count update on refresh.

---

## Distribution / installer

Ships CraftGraph as a real Windows desktop app instead of a portable `--onefile`
binary. Solves the ~2.8 s PyInstaller bootloader cost on every launch by extracting
the bundle once at install time, then running directly from the installed location
on every subsequent launch (~250 ms cold start, dev parity).

- [ ] **Switch PyInstaller from `--onefile` to `--onedir`.** Change `just build` to
  produce `dist/craftgraph/` (a folder with `craftgraph.exe` plus `_internal/`) instead
  of a single-file self-extracting `.exe`. Add a separate `just build-file` recipe if
  the single-file artifact is still useful for ad-hoc CLI use. Re-run
  `just compare-release` after the switch -- expect the work-only ratio to stay ~1.0
  and the *total* ratio to collapse to ~1.0 as well (no more bootloader to amortize).
- [ ] **Inno Setup installer.** Add `craftgraph.iss` (Inno Setup script,
  Pascal-flavored). Compiles `dist/craftgraph/` into `dist/CraftGraph-Setup-X.Y.Z.exe`
  (~30 MB compressed). Default install location `%LOCALAPPDATA%\Programs\CraftGraph\`
  (per-user, no admin prompt). Registers Start Menu entry, optional desktop shortcut,
  Add/Remove Programs uninstaller. `AppId` UUID locks future versions to the same
  product so upgrade installs replace files cleanly. Add `just installer` recipe
  (depends on `just build-dir`; requires `ISCC.exe` from Inno Setup 6 on PATH).
- [ ] **Code signing decision.** Unsigned installers trigger Windows SmartScreen
  ("unrecognized app") on first run; some users will bounce. Options: (a) accept it
  for v1 with a README note explaining "More info -> Run anyway"; (b) apply for free
  open-source signing via SignPath; (c) buy a code-signing cert (~$100-300/yr). Self-
  signed certs don't help -- SmartScreen ignores them. Decide before public release.
- [ ] **Update story.** Inno Setup handles upgrade installs natively (same `AppId`).
  Decide whether to: (a) require users to download a new Setup.exe and rerun it
  (simplest); (b) ship WinSparkle inside the app for in-app "check for updates";
  (c) defer entirely until v1 ships. (a) is the right default for an early release.

---

## Post-alpha

- [ ] **Recipe Import / Snippet Paste.** Context menu to import a recipe from known IDs
  (vanilla 498 + mod-compat 120) as a fully-wired node with ingredients pre-linked;
  batch-import related recipes at once as a connected subgraph; user-defined template
  recipes saved to file and offered in the context menu.
- [ ] **Welcome screen polish.** Full-path tooltip on recent entries; visual separation
  of projects vs folders (headers / dividers / grouped sections); fix non-C: drive
  paths wrapping wrong (drive letter splits onto its own line).
- [ ] **Load-path frame jank.** Loading a real mod project janks: `perf_diag` logs a
  burst of `frame_budget_violation` warnings, individual frames 178-294 ms against the
  33 ms budget, during the `load_recipes` window (~1148 ms total, which is NOT a
  regression -- it matches the baseline). Profile the load path as thoroughly as
  possible (the in-app harness or an external profiler, manual work acceptable) to
  attribute the spikes -- `_maybe_build_widgets` bursts, layout solve, or scene
  populate. Leading hypothesis: the `app.processEvents()` paint pump force-builds every
  visible node's widgets during load (~9.4 ms each); the fix may be finer time-slicing
  (yield on an elapsed-time budget, not a node count) or building only viewport-visible
  nodes and letting pan reveal the rest lazily.

---

## Performance techniques shipped

Optimizations already landed and profiler-verified, kept as a record so the techniques
are not lost. Acceptance target was tier A (~50-recipe real-mod set); tier C (the
894-node worst case) was informational only.

- **Incremental graph rebuild on watcher save** -- model diff instead of full reload
  (~337x: ~5067 ms -> ~15 ms).
- **`setStyleSheet` cache on `_NodeGroupBox`** -- short-circuits NodeGraphQt's ~15.8k
  redundant identical QSS re-applies per load (~3.3 s saved on tier A).
- **Lazy widget allocation** -- defer node widget construction to first paint.
- **Painted-fields architecture** -- painted text plus a shared floating-editor pool
  replace per-node embedded widgets (HWND ~74% down, widget count ~52% down).
- **Cooperative time-slicing during folder load** -- yield to the UI every 50 nodes on
  a 10 ms budget.
- **Bulk node creation under a `QSignalBlocker`.**
- **Hash-based file-change detection** (`st_ino` / `st_mtime_ns` / `st_size`) before
  reparse.
- **Cycle-detection memoization** keyed by `(n_nodes, n_edges)`.
- **Watcher event coalescing** (cancel-and-restart debounce timer).
- **Minimap static-layer `QPixmap` cache** (~13x cut on minimap paint).
- **Tiled `QBrush(QPixmap)` background grid** -- one cached blit replaces thousands of
  per-frame `drawLines` calls.
- **`PortItem.boundingRect` cached on the instance** (~3x per call).
- **`cached_bounding_rect` lookup via `__dict__.get`** (skips the descriptor protocol).
- **Per-node paint instrumentation gated behind an opt-in flag** (zero overhead when
  not recording).
- **`ItemCoordinateCache` on warning-overlay decoration items.**
- **Pre-rendered node-icon `QPixmap` LRU cache.**
- **Settings dialog lazy tab construction** -- each tab builds on first view.
- **Read-through layout cache** plus `msgspec` for the JSON layout cache.
- **Code-edit -> reparse debounce** (400 ms).
- **`PYTHONOPTIMIZE=2` for release builds.**

---

## Deferred / tier-C performance

Out of scope unless profiler data proves the need. Tier C = the 894-node worst-case
set; v1 acceptance was tier A only.

**Parser native-compile ladder:** mypyc, Cython, Rust (PyO3), and C++ (pybind11) all
target the same parser CPU time -- pick at most one rung, escalate to the next only if
the previous proved insufficient, and replace rather than stack.

| Item | Where | Trigger to revisit |
|---|---|---|
| Port-topology surgery without node rebuild | `sync.apply_file_diff` | incremental rebuild's delete-and-re-add dominates watcher cost on tier C, or edge-loss is reported |
| Lazy parse -- background prefetch | tab open hook | tier-C parse cost becomes a real fraction of folder-load wall-clock |
| QThread worker for parser signals | `_open_folder`, watcher | profiler justifies it; NodeGraphQt is main-thread-only, so the post-parse populate cannot move off-thread |
| QThreadPool parallel parse | `parser.py` | tier-C parse cost justifies the pool overhead |
| ProcessPoolExecutor worker pool | parser orchestrator | tier-C parse cost exceeds ~500 ms |
| Python 3.14 free-threaded (no-GIL) build | runtime selection | track only -- gated on PySide6 wheel compatibility |
| mypyc-compile parser + serializer (ladder rung 1) | `parser.py`, `serializer.py` | tier C becomes a real acceptance gate |
| `QOpenGLWidget` viewport | NodeGraphQt viewer | tier-C pan/zoom degrades; risky with `QGraphicsProxyWidget` embedded widgets |
| Serializer on a worker thread | `_on_save_*` actions | a workload appears where serialize wall-clock shows up at all (currently 0.3 ms on tier A) |
| Spatial index (R-tree) for node hit-testing | NodeGraphQt scene | Qt's built-in `BspTreeIndex` proves insufficient at tier C |
| Async / threaded file reads | parser entry | file I/O dominates parse cost at tier C (>50 files) |
| Cython annotation of parser hot loops (ladder rung 2) | `parser.parse_blocks` | escalate from mypyc only if it rejects code or measurable time remains |
| Rust parser via PyO3 + maturin (ladder rung 3) | new crate | parser still >50% of tier-C folder-load wall-clock after rungs 1-2 |
| C++ extension via pybind11 (last resort) | parser hot path | every other parser rung is blocked |
| Diff-based code-edit reapply | parser | full reparse exceeds 50 ms on tier-C typing after debounce + time-slicing |
| Background pre-build of inactive tab graphs | tab manager | tab switches still hitch; NodeGraphQt main-thread constraint applies |
| Replace NetworkX with rustworkx | `graph.py` | graph algorithms become a meaningful fraction of wall-clock, or tier C becomes a gate |
| Level-of-detail: hide widgets when zoomed out | `qt_nodes.py` `paint()` | frame-time log shows pan/zoom over budget at tier A, or tier C becomes a gate |
| Real GPU usage queries (D3D / Vulkan / Metal) | new `gpu_diag.py` | frame-time overlay shows steady >budget frames AND CPU profile rules out widget cost |
