#### BIG INBETWEEN NEEDED TO BE SOLVED!!!
The file "GEMINI_SOLUTION.md" has important info and potential bug fixes for us!

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
- [ ] **2. Context menu lifecycle.** Audit every `QMenu()` construction in `qt_gui.py`. Two patterns acceptable: (a) reused instance -- menu created once on owning widget, populated/cleared per use; (b) disposable -- `menu.aboutToHide.connect(menu.deleteLater)` immediately after construction. Stress test: spawn-and-dismiss main context menu x50, delta < 50.
- [DONE] **3. Settings dialog rebuild.** _SettingsDialog now scheduled for `deleteLater()` after the modal `exec_()` returns and `_apply_settings_from_dialog` has read its values. Stress test `open_close_settings_x20` widget threshold ratcheted from 200 to 150 (measured stable delta of 120 over 20 cycles, down from 9460 pre-fix). The audit-only "_clear_layout helper + signal-disconnect" approach in the original spec was unnecessary -- destroying the dialog disposes its children and disconnects its signals automatically.
- [ ] **4. Multi-folder teardown.** On `_open_folder()` when a folder is already loaded: explicit `_teardown_current_project()` step before loading new. Iterates all file tabs, applies fix #1's destruction sequence. Clears `_path_words`, `_id_words` caches. Stress test: open folder A -> open folder B -> open folder A x3, delta < 500.
- [ ] **5. Watcher rebuild (audit-first, fix optional).** Currently unknown how the rebuild path constructs nodes. Step 1: audit -- trace the watcher -> `_apply_file_change()` -> node spawn path with Phase 1's `measure()` decorator. If audit shows leak: switch from wholesale rebuild to model-diff (added/removed/modified recipes only update affected nodes). Marked optional until audit confirms a leak.

### Phase 3 -- Preventive hardening

- [ ] **A. `AA_DontCreateNativeWidgetSiblings` flag.** One line in `craftgraph/cli.py` (`launch_qt_gui` entry) before `QApplication(sys.argv)`:
  ```python
  QtCore.QCoreApplication.setAttribute(
      QtCore.Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings,
  )
  ```
  Verify no regression on existing widgets (most embed via `QGraphicsProxyWidget` which does not trigger native sibling creation anyway, but confirm via Phase 1 stress tests).
- [ ] **B. Parenting audit.** Grep `craftgraph/qt_*.py`, `welcome.py`, `tooltips.py`, `minimap.py` for `Q[A-Z][a-zA-Z]*\(` constructors not stored on `self.*` and not passed `parent=`. For each hit: either `self._field = ...` with explicit parent, or document why local lifetime is intentional. Mostly mechanical; deliverable is one commit + a brief audit table noting which were already fine vs. fixed.

### After HWND: performance / multithreading

Tracked separately. Not started until Phases 1-3 land and stress tests stay green.

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
