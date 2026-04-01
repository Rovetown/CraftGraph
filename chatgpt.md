# GUI Migration Evaluation: DearPyGui to Qt-Based Node Editor

> **Status:** Research and evaluation only. Migration planning is a separate future step.
>
> **Origin:** ChatGPT recommendation, independently verified and corrected.

---

## Why Migrate Away from DearPyGui?

DearPyGui wraps the ImGui/imnodes C++ library using an immediate-mode rendering model.
This creates a fundamental constraint: **you cannot add or remove pins (ports) on a node
after it has been created.** Every structural change requires tearing down the entire node
and rebuilding it from scratch. This causes:

- Visual flicker on every model mutation
- Loss of user state (selection, scroll position)
- Complex diffing logic to minimize unnecessary rebuilds
- Drag-order bugs in link callbacks (imnodes reports in drag order, not normalized)
- No per-node subclassing -- everything routes through a single `RecipeNode` dataclass
  with branching logic keyed on `NodeKind`

A retained-mode Qt scene graph does not have any of these problems. Nodes are objects
that persist. You add ports, remove ports, change labels, embed widgets -- all without
destroying and recreating anything.

---

## What ChatGPT Got Wrong

ChatGPT recommended `QNodeEditor + PyQt6`. That recommendation has several factual errors:

| Claim | Reality |
|-------|---------|
| `pip install PyQt6 QNodeEditor` | **Would fail.** QNodeEditor requires PyQt5, not PyQt6. |
| QNodeEditor is a solid choice | ~40 GitHub stars, 9 forks. Tiny community, minimal maintenance. |
| No mention of NodeGraphQt | NodeGraphQt has ~1,600 stars, MIT license, active maintenance (v0.6.44, Feb 2026). |
| PyQt6 recommended without caveats | PyQt6 is GPL. Fine for open-source projects, but NodeGraphQt **does not work with PyQt6** (see binding tension below). |
| PySide6 mentioned as parenthetical | PySide6 is LGPL. More permissive, and the only binding that works with NodeGraphQt. |
| Recommends pydantic | We already have clean dataclasses in `models.py`. Pydantic adds unnecessary weight. |
| Recommends blinker | Qt has its own signal system. Adding a second signal library creates confusion. |
| Recommends deepdiff | Overkill for known-structure models. Simple attribute comparison suffices. |
| Generic node types (IngredientNode, ResultNode, ConditionNode, InventoryNode) | These don't map to CC3 types. Our types are: RecipeNode, CustomFabricator, CraftingTab, AddedRecipe, AliasRecipe, etc. |
| Timeline estimates provided | Not useful without knowing implementation details. |

---

## Corrected Recommendation: NodeGraphQt + PySide6

### Why NodeGraphQt

[NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) is a Python node graph framework
built on Qt's `QGraphicsScene`. It is the most mature Python node editor available.

**Features directly relevant to CraftGraph:**

| Feature | What it solves for us |
|---------|-----------------------|
| Dynamic port add/remove at runtime | No more teardown-rebuild on model mutation |
| Embedded custom widgets inside nodes | Inline editing of ItemID, AmountCrafted, etc. |
| Built-in undo/redo (QUndoStack) | Free undo/redo for all node operations |
| Port type constraints | Prevent invalid connections (e.g. recipe-to-recipe) |
| Connection callbacks | Replace our manual `on_link()` dispatch |
| Tab search (node search dialog) | Quick node lookup in large graphs |
| Minimap | Navigation for 894+ node graphs |
| Group nodes | Visual grouping of fabricator hierarchies |
| Serialization (JSON) | Layout persistence without custom code |
| MIT license | No copyleft, no commercial license needed |

**Maturity:**

| Metric | QNodeEditor | NodeGraphQt |
|--------|-------------|-------------|
| GitHub stars | ~40 | ~1,600 |
| Forks | ~9 | ~400+ |
| Last release | May 2024 | Feb 2026 (v0.6.44) |
| Qt version | PyQt5 only | PySide2/PySide6 |
| License | MIT | MIT |
| Dynamic ports | Unknown | Yes |
| Embedded widgets | Unknown | Yes |
| Built-in undo/redo | No | Yes (QUndoStack) |
| Documentation | Minimal | Full API docs + examples |

### PySide6 vs PyQt6

CraftGraph is fully open-source, so GPL licensing is not a problem. The choice
between PySide6 and PyQt6 comes down to **ecosystem compatibility**:

| | PySide6 | PyQt6 |
|---|---------|-------|
| License | LGPL | GPL |
| Maintainer | Qt Company (official) | Riverbank Computing (third-party) |
| API | Nearly identical to PyQt6 | Nearly identical to PySide6 |
| NodeGraphQt | Works (confirmed by community) | **Broken** -- `DeviceCoordinateCache` removed in Qt6 |
| QScintilla | **No official bindings** | Official bindings (`PyQt6-QScintilla`) |
| Ko-fi / donations | Compatible | Compatible |

> **Licensing and donations:** Neither GPL nor LGPL restricts how you fund a project.
> You can accept Ko-fi tips, Patreon memberships, or any other donations for GPL/LGPL
> software. The licenses govern code distribution rights, not revenue. Projects like
> VLC, GIMP, and LMMS are all GPL and accept donations.

**The binding tension:**

NodeGraphQt does not work with PyQt6 (Qt6 removed `QGraphicsItem.DeviceCoordinateCache`,
which NodeGraphQt still references -- see [issue #483](https://github.com/jchanvfx/NodeGraphQt/issues/483)).
QScintilla's official Python bindings only exist for PyQt5/PyQt6 (Riverbank does not
ship PySide bindings). This means:

- **PySide6 + NodeGraphQt:** Node editor works. No QScintilla (must use alternatives).
- **PyQt6 + QScintilla:** Code editor works. Node editor is broken.
- **Mixing PySide6 and PyQt6 in one app:** Not supported. Qt only allows one binding per process.

**Bottom line:** PySide6 is the only viable option because the node editor is the core
of the application. The code editor has viable alternatives (see below). If NodeGraphQt
merges [PR #420](https://github.com/jchanvfx/NodeGraphQt/issues/423) (QtPy abstraction
for all bindings), PyQt6 support may come later.

### NodeGraphQt Forks

| Fork | Qt support | Status | Notes |
|------|-----------|--------|-------|
| [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt) (upstream) | PySide2, PySide6, PyQt5 | Active (v0.6.44, Feb 2026) | PyQt6 broken |
| [OdenGraphQt](https://github.com/OdenTech/OdenGraphQt) | PySide6 (tested), PyQt6 (untested) | v0.7.4, Apr 2024 | Adds type hints |
| [NodeGraphQt-PySide6](https://github.com/C3RV1/NodeGraphQt-PySide6) | PySide6 only | Community fork | Minimal changes |

Start with upstream NodeGraphQt + PySide6. Fall back to OdenGraphQt if rough edges appear.

---

## What We Keep (No Rewrite)

ChatGPT got this part right. Our core layer is already UI-agnostic:

- `parser.py` -- EasyMarkup parser
- `serializer.py` -- EasyMarkup serializer
- `models.py` -- Recipe/fabricator/tab data models
- `graph.py` -- NetworkX dependency graph + cycle detection
- `watcher.py` -- Watchdog file watcher
- `cli.py` -- Click CLI
- `commands.py` -- Edit command pattern (undo/redo-ready)
- `vanilla_ids.py` -- TechType ID loader
- `sprite_loader.py` -- Sprite loading (needs Qt pixmap adapter)
- `layout_store.py` -- Node position persistence

Only `gui.py`, `gui_nodes.py`, `gui_editor.py`, and `gui_autocomplete.py` get replaced.

---

## High-Level Architecture (Corrected)

```
Core Layer (Pure Python, unchanged)
    parser.py           -- EasyMarkup parser
    serializer.py       -- EasyMarkup serializer
    models.py           -- Recipe/fabricator/tab data models
    graph.py            -- NetworkX dependency graph
    watcher.py          -- File watcher
    commands.py         -- Edit commands (undo/redo)
    vanilla_ids.py      -- TechType ID registry

UI Layer (Qt/NodeGraphQt, new)
    Node graph view     -- NodeGraphQt graph widget
    Code editor         -- QPlainTextEdit + QSyntaxHighlighter
    Inspector panel     -- QWidget with form fields
    Sprite renderer     -- QPixmap-based

Sync Layer (new, thin)
    Model-to-UI mapper  -- Creates/updates Qt nodes from ParsedFile
    UI-to-Model mapper  -- Translates node edits into EditCommands
    Change guard        -- Prevents recursive update loops
```

**Critical rule (unchanged from ChatGPT, and already in our CLAUDE.md):**

- Model is authoritative
- UI reflects model
- UI changes mutate model via commands
- Never let UI be source of truth

---

## Comparison: Current DPG vs NodeGraphQt Migration

| Capability | Current (DPG/imnodes) | After Migration (NodeGraphQt) |
|------------|----------------------|-------------------------------|
| Add/remove pins at runtime | No -- full node rebuild required | Yes -- `node.add_input()` / `node.delete_input()` |
| Embedded widgets in nodes | No -- only text labels and static attributes | Yes -- any QWidget (dropdowns, spinboxes, text fields) |
| Per-node subclassing | No -- single RecipeNode with branching | Yes -- subclass `BaseNode` per CC3 type |
| Undo/redo | Manual (our commands.py) | Built-in QUndoStack + our commands.py |
| Zoom | Not exposed in DPG Python bindings | Built-in (mouse wheel) |
| Minimap | Manual implementation | Built-in |
| Node search | Not available | Built-in tab search |
| Connection validation | Manual dispatch in on_link() | Port type constraints + callbacks |
| Custom node painting | Not possible (ImGui draws everything) | Override `paint()` on QGraphicsItem |
| Group nodes | Not available | Built-in |
| Layout persistence | Manual (our layout_store.py) | Built-in JSON serialization + our layout_store.py |
| Link drag-order bugs | Yes (imnodes reports in drag order) | No (Qt normalizes connection events) |

---

## CC3-Specific Node Types (Corrected)

ChatGPT used generic names. Our actual CC3 node types are:

| Node Kind | CC3 Model | Ports |
|-----------|-----------|-------|
| AddedRecipe | `AddedRecipe` | Ingredient inputs, hierarchy input, output |
| AliasRecipe | `AliasRecipe` | Ingredient inputs, linked items, hierarchy input, output |
| ModifiedRecipe | `ModifiedRecipe` | Ingredient inputs, output |
| CustomFood | `CustomFood` | Ingredient inputs, hierarchy input, output |
| CustomFabricator | `CustomFabricator` | Hierarchy output (children: tabs, recipes) |
| CraftingTab | `CraftingTab` | Hierarchy input, hierarchy output (children: subtabs, recipes) |

A node registry maps these to Qt node subclasses:

```python
NODE_REGISTRY: dict[NodeKind, type[BaseNode]] = {
    NodeKind.ADDED_RECIPE: AddedRecipeNode,
    NodeKind.ALIAS_RECIPE: AliasRecipeNode,
    NodeKind.MODIFIED_RECIPE: ModifiedRecipeNode,
    NodeKind.CUSTOM_FOOD: CustomFoodNode,
    NodeKind.CUSTOM_FABRICATOR: FabricatorNode,
    NodeKind.CUSTOM_CRAFTING_TAB: CraftingTabNode,
}
```

---

## Code Editor Options

Since QScintilla is not available with PySide6, here are the viable alternatives
for the EasyMarkup code editor panel. Our files are small (~200 lines max) with
simple syntax (8 delimiters, ~10 block type keywords), so we do not need a full IDE.

### Option 1: QPlainTextEdit + QSyntaxHighlighter (Recommended)

Built into Qt. No extra dependencies.

- `QPlainTextEdit` provides a performant plain text editor widget
- `QSyntaxHighlighter` lets you define custom highlighting rules via regex
- Line numbers: add a custom `QWidget` sidebar (standard Qt pattern, ~50 lines)
- No code folding (out of scope per CLAUDE.md anyway)

**Pros:** Zero dependencies, lightweight, fully sufficient for EasyMarkup.
**Cons:** No built-in line numbers (trivial to add). No folding. No autocomplete widget
(we would implement our own popup, similar to current `gui_autocomplete.py`).

This is the right choice for EasyMarkup files. We only need to highlight `:`, `;`,
`( )`, `,`, `#` comments, quoted strings, and block type keywords.

### Option 2: QScintilla (PyQt6 only -- incompatible)

[QScintilla](https://riverbankcomputing.com/software/qscintilla/) is the Qt port
of the Scintilla editor component. It provides line numbers, folding, custom lexers,
autocomplete, and brace matching out of the box.

**The problem:** Official Python bindings (`PyQt6-QScintilla`, GPL v3) only exist for
PyQt6. There are no PySide6 bindings. A community PySide6 port existed on
[GitLab](https://gitlab.com/iborco-pyside/pyside6-scintilla) but is **archived and
unmaintained** (MIT license, 53 commits, read-only since 2023).

**Verdict:** Not usable with our PySide6 + NodeGraphQt stack. If NodeGraphQt gains
PyQt6 support in the future, QScintilla becomes an option.

### Option 3: QtMonaco (Overkill)

[QtMonaco](https://github.com/bec-project/qtmonaco) embeds the full Monaco editor
(the engine behind VS Code) inside a Qt widget via a WebEngine view.

| Aspect | Details |
|--------|---------|
| Qt bindings | PySide6 and PyQt6 (via `qtpy`) |
| License | BSD 3-Clause |
| Status | Active (v0.8.2, Oct 2025) |
| Features | Full Monaco: syntax highlighting, find/replace, minimap, LSP support |
| Platform | macOS and Linux confirmed; Windows not explicitly listed |
| Dependencies | Bundles a web engine (QtWebEngine), TypeScript build |

**Why it is overkill for CraftGraph:**
- Embeds an entire Chromium-based web engine for a ~200-line text editor
- Adds significant binary size (QtWebEngine alone is ~100+ MB)
- LSP support is unnecessary (we only need TechType ID autocomplete)
- Monaco's syntax highlighting system is designed for full programming languages,
  not 8-delimiter markup formats
- Windows support is not explicitly confirmed

**Additional blocker:** QtMonaco pins PySide6 to `<=6.9.0`. Our stack uses PySide6 6.10.2.
They cannot coexist. Even as a fallback, QtMonaco would require downgrading PySide6.

**Verdict:** Incompatible with our PySide6 version, and massively overbuilt for EasyMarkup
editing. Not a viable option unless QtMonaco updates its PySide6 cap.

### Code Editor Comparison

| Feature | QPlainTextEdit + QSyntaxHighlighter | QScintilla | QtMonaco |
|---------|-------------------------------------|------------|----------|
| PySide6 compatible | Yes (built-in) | No | Yes (via qtpy) |
| Extra dependencies | None | PyQt6 only | QtWebEngine (~100+ MB) |
| Syntax highlighting | Custom via QSyntaxHighlighter | Built-in lexers + custom | Monaco language grammars |
| Line numbers | Manual sidebar (~50 LOC) | Built-in | Built-in |
| Code folding | No (out of scope) | Built-in | Built-in |
| Autocomplete | Manual popup | Built-in | Built-in LSP |
| Complexity | Low | Medium | High |
| Binary size impact | None | Small | Large |
| Sufficient for EasyMarkup | Yes | Yes (but unavailable) | Yes (but overkill) |

**Recommendation:** QPlainTextEdit + QSyntaxHighlighter. It covers everything we need
with zero extra dependencies. QtMonaco is not a viable fallback due to PySide6 version
incompatibility (caps at 6.9.0, we use 6.10.2).

---

## Libraries Assessment

### Already using (keep as-is)

| Library | Purpose |
|---------|---------|
| networkx | Dependency graph, cycle detection |
| watchdog | File watching |
| click | CLI |

### New (migration requires)

| Library | Purpose |
|---------|---------|
| PySide6 | Qt6 bindings (LGPL) |
| NodeGraphQt | Node editor framework (MIT) |

### Optional (evaluate during migration)

| Library | Purpose | Notes |
|---------|---------|-------|
| QtMonaco | Rich code editor | **Currently incompatible** -- pins PySide6 `<=6.9.0`, we use 6.10.2. Monitor for updates. |
| OdenGraphQt | NodeGraphQt fork | Fall back if upstream has PySide6 rough edges. |

### Unnecessary (ChatGPT recommended, we should skip)

| Library | Why skip |
|---------|----------|
| pydantic | We have clean dataclasses. Adding pydantic would require rewriting models.py for no benefit. |
| blinker | Qt has signals built in. A second signal system creates confusion. |
| deepdiff | Our models have known structure. Simple attribute comparison is clearer and faster. |
| QScintilla | No PySide6 bindings. Incompatible with our Qt binding choice. |

---

## Risk Areas (Corrected)

1. **Recursive update loop** -- Same risk as DPG. Solved with a change guard flag.
2. **Node ID mapping** -- Need stable mapping between `ParsedFile` entries and Qt node instances.
3. **Thread safety** -- Watchdog runs in its own thread. Qt updates must go through `QMetaObject.invokeMethod()` or signal/slot across threads.
4. **Model-Qt decoupling** -- Same rule as now: `models.py`, `parser.py`, `serializer.py` must never import Qt.
5. **NodeGraphQt learning curve** -- Need to understand its node lifecycle, port API, and serialization format.
6. **Sprite loading** -- Current PIL-based sprite loader needs a Qt adapter (PIL Image to QPixmap).

---

## What Migration Does NOT Change

- EasyMarkup parsing and serialization (parser.py, serializer.py)
- Data models (models.py)
- Graph algorithms (graph.py)
- File watching (watcher.py)
- CLI interface (cli.py)
- Edit command pattern (commands.py)
- TechType ID registry (vanilla_ids.py)
- Test suite for core logic (all non-GUI tests)

---

## Decision Summary

| Option | Verdict |
|--------|---------|
| Stay on DearPyGui | Viable but increasingly painful. Every new feature fights imnodes constraints. |
| QNodeEditor + PyQt6 (ChatGPT's pick) | **Do not use.** QNodeEditor is PyQt5-only with ~40 stars. |
| NodeGraphQt + PyQt6 | **Not viable yet.** NodeGraphQt crashes on PyQt6 (missing `DeviceCoordinateCache`). |
| NodeGraphQt + PySide6 | **Recommended.** Confirmed working. Largest community, MIT + LGPL, dynamic ports, built-in undo/redo. |
| Custom QGraphicsScene (no framework) | Maximum flexibility but highest effort. Only if NodeGraphQt proves insufficient. |

---

## Next Steps (For Future Planning Session)

> These are not actionable now. They outline what a migration plan would cover.

1. Evaluate NodeGraphQt hands-on: install, create a test graph, verify dynamic port behavior
2. Design the node subclass hierarchy matching our CC3 types
3. Plan the GUI module replacement (gui.py, gui_nodes.py, gui_editor.py, gui_autocomplete.py)
4. Design the sync layer (model-to-UI, UI-to-model via commands)
5. Plan the sprite loader adapter (PIL to QPixmap)
6. Build EasyMarkup QSyntaxHighlighter (keywords, delimiters, comments, quoted strings)
7. Port autocomplete popup from DPG to QCompleter or custom QListWidget
8. Update CHANGELOG.md at migration planning stage
