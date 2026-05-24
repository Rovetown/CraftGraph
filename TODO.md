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

- [ ] **Defensive `save_project` / closeEvent on empty `project_path`.** Sub-project 4
  surfaced that `closeEvent` (DISCARD branch) calls `save_project(self._project)` at
  teardown, which crashes with `PermissionError: '.'` when `project_path == ""`.
  Currently 2 tests in `TestProjectCustomIdPersistence` (`test_qt_gui.py`) work around
  this with `try/finally: window._project = None`. The proper fix is either
  `save_project` to no-op on empty path, or `closeEvent` to skip the save branch
  when `not self._project.project_path`. Either way, drop the try/finally workaround
  from the two tests once production is defensive.

- [ ] **Robust patch-script pattern for mass test-file refactors.** Sub-project 4's
  test_qt_gui conversion needed two patch scripts because the first regex used
  `\s+` (greedy cross-line whitespace) for indent and required `)` on the same line
  as `def test_x(`. Future bulk edits should use ` *` for indent and handle
  multi-line signatures in one pass. Either codify the pattern as a small reusable
  utility (e.g., `scripts/_patch_helpers.py`) or document the rules in CLAUDE.md so
  the next round avoids the same regressions.

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

- [ ] **TabID autocomplete in `Path` fields.** Suggest CraftingTab path segments when
  editing a recipe's `Path`. Path-field autocomplete already exists via `_path_words` /
  `_collect_valid_path_targets`; verify whether it already surfaces tab path segments
  and close this if it does.
- [ ] **Unlock / UnlockedBy visualization + editing.** A distinct edge type for unlock
  relationships (`Unlocks: X` -> edge recipe->X; `UnlockedBy: A` -> edge A->recipe, OR
  semantics); per-recipe editing of `Unlocks`/`UnlockedBy` as comma-separated TechType
  lists with autocomplete; a visual distinction for OR (`UnlockedBy`, any-of) vs ALL
  (`Unlocks`). Verify how much, if any, already exists.
- [ ] **Full filename tooltip on tab hover.** Hovering a file tab shows the complete
  file name (tab labels truncate; the tooltip should show the full filename, not a
  directory path).

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
