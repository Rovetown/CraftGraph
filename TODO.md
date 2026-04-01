# CraftGraph -- TODO

> Priority-ordered build plan. Checkboxes track completion.
> Completed Phase 1 (CLI pipeline) and GUI migration (Steps M1-M8) are in
> [CHANGELOG.md](CHANGELOG.md).

---

## GUI Stack

> **Stack:** PySide6 (Qt6 bindings, LGPL) + NodeGraphQt (node editor, MIT)
> + QPlainTextEdit + QSyntaxHighlighter (code editor, built into Qt).
> Install: `pip install craftgraph[qt]`. See [chatgpt.md](chatgpt.md) for
> the original DPG-to-Qt migration evaluation.

### Optional Fallbacks (Do NOT use unless needed)

- [ ] **OdenGraphQt** ([PyPI](https://pypi.org/project/OdenGraphQt/)): NodeGraphQt fork
  with PySide6 type hints. Fall back if upstream has blocking PySide6 issues.
- [ ] **QtMonaco** ([PyPI](https://pypi.org/project/qtmonaco/)): Monaco editor as Qt
  widget. **Currently incompatible** with PySide6 6.10.2 (pins `<=6.9.0`).
  Monitor for updates.

---

## Cross-Platform Distribution Notes

> Reference for distribution planning.

### Platform compatibility

| Dependency | Windows | Linux | macOS | Type |
|---|---|---|---|---|
| Python 3.14 | Yes | Yes | Yes | Runtime |
| NetworkX | Yes | Yes | Yes | Pure Python |
| Click | Yes | Yes | Yes | Pure Python |
| Watchdog | Yes | Yes | Yes | Platform-specific backends (ReadDirectoryChangesW / inotify / FSEvents) |
| Pyvis | Yes | Yes | Yes | Generates static HTML |
| PySide6 | Yes | Yes | Yes | Pre-built wheels; Qt6 native rendering per platform |
| NodeGraphQt | Yes | Yes | Yes | Pure Python (depends on PySide6) |
| PyInstaller | Yes | Yes | Yes | **Cannot cross-compile** (see below) |

### PyInstaller limitation: no cross-compilation

PyInstaller bundles the Python interpreter into the binary, so it must run
on the target OS. Build on Windows to get `.exe`, on Linux to get a Linux
binary, on macOS to get a macOS binary. You cannot build a Linux binary
from a Windows machine (or vice versa).

**Solution:** GitHub Actions matrix build (`windows-latest`, `ubuntu-latest`,
`macos-latest`). Each runner builds for its OS and attaches the artifact to
a GitHub Release. This is standard practice for Python desktop tools.

### Nuitka as a possible alternative

Nuitka compiles Python to C, then to native machine code. Produces smaller,
faster binaries. Same cross-compile limitation applies. Worth evaluating if
binary size or cold-start time becomes an issue.

### CLI + GUI coexistence

The architecture supports both in a single binary:
- `craftgraph check|view|watch|export` -- CLI commands, no GUI window
- `craftgraph gui` -- PySide6 + NodeGraphQt node editor window

PySide6/NodeGraphQt are optional dependencies (`pip install craftgraph[qt]`),
so the CLI-only binary stays small. The GUI binary includes the extra deps.

---

## Phase 2 -- GUI Editor (Continued)

> Remaining sub-steps for the interactive GUI editor.

### References and Knowledge Base

- [ ] **Mini Dependency Graph Panel** -- Evaluate rendering options for an interactive
  mini dependency graph inside PySide6 (bottom-right panel, zoomable/pannable overview
  of recipe dependencies). Candidates: QGraphicsView, Pyvis in QWebEngineView,
  matplotlib FigureCanvas, Mermaid via QWebEngineView, dedicated graph-viz libraries.
- [x] **CC3/EasyMarkup Source Knowledge Document** -- Create `docs/source-knowledge.md`
  covering all CC3 block types, EasyMarkup syntax rules, recipe file structure, field
  semantics, and practical examples. Audience: developers, modders, and players alike.

#### Mini Dependency Graph Panel -- Evaluation

Six approaches were evaluated. Top two recommendations:

| Option | New Deps | Weight | Zoom/Pan | Click | 1000 Nodes | Lines | Risk |
|--------|----------|--------|----------|-------|------------|-------|------|
| **1. QGraphicsView** (built-in) | None | 0 MB | Native Qt | Native Qt | Excellent | ~200 | None |
| **2. PyQtGraph GraphItem** | pyqtgraph | ~15 MB | Native Qt | sigClicked | Very good | ~50 | PySide6 compat TBD |

**Rejected options:**
- **Pyvis in QWebEngineView:** Works but adds Chromium (+130 MB disk, +175 MB PyInstaller). Overkill.
- **Matplotlib FigureCanvas:** Toolbar-only zoom, blurry on zoom (rasterized), known memory leak.
- **Mermaid via QWebEngineView:** Cannot handle 500+ nodes. Layout engine (dagre) designed for docs.
- **QtGraphVisuals:** Ideal API but dormant (last release Oct 2023), no community adoption.

**Recommendation:** Start with **QGraphicsView** (zero deps, native Qt, full control). Qt's
official [NetworkX Viewer Example](https://doc.qt.io/qtforpython-6/examples/example_external_networkx.html)
provides `Node(QGraphicsObject)` + `GraphView(QGraphicsView)` starter code. If code
brevity matters more, **PyQtGraph** (`GraphItem.setData(pos=..., adj=...)`) is ~50 lines
but needs PySide6 6.10+ compatibility testing first.

#### CC3/EasyMarkup Source Knowledge

> See [`docs/source-knowledge.md`](docs/source-knowledge.md) for the full reference.

**Scope:** Complete reference for CC3 recipe files, covering:
- EasyMarkup syntax (7 special characters, quoting, escaping, comments, nesting)
- All 10 block types with field tables, validation rules, and annotated examples
- Recipe type inheritance chain (Modified -> Added -> Alias -> CustomFood)
- CustomFabricator nesting structure and ownership diagram
- Ingredients syntax (compact and expanded forms, Required range 1-25)
- Crafting path format and built-in fabricator types
- Unlock system (Unlocks vs UnlockedBy, OR logic)
- Sprite resolution order
- Full enum reference (FabricatorModel, FoodModel, TechGroup, TechCategory)
- CC3 processing order (10-step global sequence)
- Common mistakes section for new modders

**Audience:** Written for three levels -- players tweaking recipes, modders building
fabricators, and developers working on CraftGraph.

---

### Phase 2 Node System Overhaul -- UE5-Style Field-Level Nodes

> Full plan and detailed specs: [`phase2-plan.md`](phase2-plan.md)

#### Phase A -- Pin Infrastructure (foundation)

- [x] Refactor node classes to declare input pins from a field registry
- [x] Add inline widget rendering per pin type (text, spin, combo, checkbox)
- [x] Add output pins based on block type capabilities
- [x] Wire pin connections to model field updates

#### Phase B -- Variable Nodes

- [x] Create variable node base class with output pin
- [x] Implement all 9 variable node types (StringVar, IntVar, FloatVar, BoolVar,
  CSVListVar, EnumVar, IngredientListVar, PathVar, ColorVar)
- [x] Implement connected-overrides-inline behavior
- [x] "Promote to Variable" context menu action on pins
- [x] **Fabricator/Tab reference nodes (Get/Set pattern)** -- Specialized reference
  nodes ("Get Fabricator", "Get Tab") that, when connected to a recipe's Path field
  pin, auto-resolve and set the full fabricator path (e.g., `MyFab/ScienceTab`).
  The app computes the path from the tab's actual hierarchy position. Eliminates
  manual path typing. Similar to UE5 Get Variable nodes.

#### Phase C -- Context Menu and File/Project Creation

- [x] Restructure context menu into categorized submenus (Recipe/Container/Utility/Variables)
- [x] If keeping "Add Ingredient" context menu, use the same categorized dropdown as node creation (split by TechType category or similar grouping instead of a flat list)
- [x] Implement New File dialog with block type templates and starter nodes
- [x] Implement New Project dialog (name, location, 10 starter files + Assets/ + .craftgraph/)
- [x] Starter node spawning per block type

#### Phase D -- Layout, Placement, and Window Fixes

- [x] Processing-order column layout for initial file load (left-to-right: Fabricators -> ... -> BioFuels)
- [x] Variable node smart placement algorithm (between earliest non-connected and first connected consumer)
- [x] Layout persistence updates for new node types
- [x] Fix node selection bug
- [x] Investigate and fix dialogs/windows not contained inside the main window
- [x] Tune node spacing (vertical and horizontal) so nodes never overlap or crowd on initial load
- [x] Implement minimap widget (View > Minimap menu entry exists but is disabled; NodeGraphQt has no built-in minimap)
- [x] Add labels to variable node input ports (show the field name the variable feeds into)

#### Phase D-B -- Bug Fixes (Post-Phase-D)

- [x] Minimap not rendering (no visible widget on screen)
- [x] Node spacing still cramped on initial load (dynamic _node_step not applied visually)
- [x] Dialogs (add ingredient, etc.) still spawn as separate OS windows instead of app-contained
- [x] Reset Layout does not deselect the currently selected node
- [x] Variable/Get nodes spawn at fixed position instead of cursor position
- [x] Red error highlight missing on rejection messages (e.g. "cannot add X recipe type here")
- [x] Category dropdown: scrollwheel does not work when hovering
- [x] Category dropdown: z-order/layer issues (deferred to Phase F)
- [x] Get Tab/Fab node spawns with oversized transparent dropdown (very wide until switching selection)
- [x] Node selection bugs after adding/deleting nodes (tab-specific, reappears after reset layout)
- [x] Smart placement edge cases (defer to later bug-fix pass)

#### Phase E -- Validation and Error Prevention

- [x] Required-field highlighting (red border on empty required pins)
- [x] Mutual exclusion enforcement (Copied/Hidden, PdaGroup/PdaCategory)
- [x] Path reference validation (does the referenced tab exist?)
- [x] Export-time validation summary dialog
- [x] Syntax highlighter rules for common text-level mistakes (missing `;`, wrong separator, unquoted spaces)

#### Phase F -- Reference Panel and Polish

- [x] CraftTree.Type Centrifuge marked as Below Zero / cut content for SN1
- [x] Floating tooltips for context menu entries (show description on hover instead of inlining it in the label text)
- [x] Floating tooltips for node headers (show node type description on hover over a node in the graph)
- [x] Floating tooltips for node field widgets (show field-level help text on hover, e.g. "TechType ID", "Valid range 1-25")
- [x] Enum combo box population with full value lists (FabricatorModel, FoodModel, TechGroup, TechCategory, CraftTree.Type)
- [x] Rich text menu labels (QWidgetAction + QLabel with HTML) to replace `--` separators with bold names and styled descriptions
- [x] Category dropdown: z-order/layer issues (proxy widgets below bleed through open dropdown -- assign descending z-values so the topmost combo+label pair sits above all others, each successive pair one layer lower, preventing lower widgets from bleeding through open dropdowns)
- [x] Vanilla ItemID categorized reference panel (dockable, 498 IDs by TechGroup/TechCategory)
- [x] Drag-from-panel-to-pin interaction
- [x] Case-insensitive autocomplete audit (deduplicate mixed-case TechType IDs, ensure canonical PascalCase insertion, verify camelCase prefix matching across code editor and node widgets)

#### Phase G -- Context Menu + Field UX Fixes

- [x] **Revert context menu to regular QActions with hover highlight:** The Phase F `add_rich_command()` / `QWidgetAction + QLabel` approach broke the selection highlight on menu items (QLabel sits on top of `QMenu::item:selected` styling). Revert all "Add Node" submenu entries back to regular `QAction`s via `add_command()`. Remove `add_rich_command()` from tooltips.py and the `_make_rich_create_cb` / `_make_rich_var_create_cb` wrappers from qt_gui.py. Remove import of `add_rich_command`. Update tests in `TestRichMenuLabels` accordingly.
- [x] **Rich HTML tooltips on context menu actions:** The original Phase F intent was rich text in the *tooltips*, not in the menu labels. After reverting to regular QActions, set each action's tooltip to `format_tooltip(name, description)` (bold name + description via HTML). This uses the existing `format_tooltip()` helper in tooltips.py. The `enable_menu_tooltips()` call already makes these visible on hover.
- [x] **Overflow tooltips for truncated node fields and tab labels:** Hovering a truncated QLineEdit, combo box, or int/float editor shows the full value. Tab bar labels show the full file path on hover.
- [x] **Mouse middle button (MMB) pan behavior fix:** Root cause: NodeGraphQt viewer tracks ALT_state via keyPressEvent/keyReleaseEvent, but if focus leaves the viewer (e.g. ALT activates menu bar, dock widget takes focus), keyReleaseEvent is delivered elsewhere, leaving ALT_state stuck True. Fix: _ViewerModifierSyncFilter event filter syncs modifier states from actual event.modifiers() on every mouse press.

---

### Step 11f -- Complete Node Types and CC3 Field Inventory

> Checkboxes 1-4 done -- see CHANGELOG.md. Remaining: Checkbox 5 (color tuning).

#### CC3 field reference (kept as design reference for future steps)

**All 10 CC3 block types and their fields:**

##### Recipe types (inheritance chain: Modified -> Added -> Alias -> CustomFood)

| Field | ModifiedRecipe | AddedRecipe | AliasRecipe | CustomFood | Type | Default | Constraint |
|-------|:-:|:-:|:-:|:-:|------|---------|------------|
| ItemID | R | R | R | R | string | -- | Required, TechType ID |
| AmountCrafted | o | o | o | o | int | 1 | >= 0 |
| Ingredients | o | o | o | o | list[Ingredient] | [] | Each: Required 1-25 |
| LinkedItemIDs | o | o | o | o | CSV string | [] | TechType IDs |
| Unlocks | o | o | o | o | CSV string | [] | TechType IDs; crafting this unlocks ALL listed items |
| UnlockedBy | o | o | o | o | CSV string | [] | TechType IDs; OR logic -- unlocks when ANY ONE is scanned |
| ForceUnlockAtStart | o | o | o | o | bool | NO | YES/NO |
| Path | -- | R | R | R | string | "" | Fabricator/Tab/Tab path |
| PdaGroup | -- | o | o | o | TechGroup | Uncategorized | Game enum (see below) |
| PdaCategory | -- | o | o | o | TechCategory | Misc | Game enum (see below) |
| DisplayName | -- | -- | R | R | string | "" | Quoted |
| Tooltip | -- | -- | R | R | string | "" | Quoted |
| FunctionalID | -- | -- | o | o | string | None | Existing TechType to clone behavior |
| SpriteItemID | -- | -- | o | o | string | None | Existing TechType for sprite fallback |
| FoodValue | -- | -- | -- | * | int | 0 | -200 to +200 |
| WaterValue | -- | -- | -- | * | int | 0 | -200 to +200 |
| OxygenValue | -- | -- | -- | o | int | 0 | -200 to +200 |
| HealthValue | -- | -- | -- | o | int | 0 | -200 to +200 |
| DecayRateMod | -- | -- | -- | o | float | 0.0 | 0.0 = never decays |
| FoodType | -- | -- | -- | o | FoodModel | None | See FoodModel enum |
| UseDrinkSound | -- | -- | -- | o | bool | auto | YES/NO |

R = required, o = optional, * = at least one of FoodValue/WaterValue must be non-zero, -- = not present

##### CustomFabricator (extends AliasRecipe, plus:)

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| Model | FabricatorModel | "Fabricator" | Fabricator / Workbench / MoonPool (SN1 only) |
| ColorTint | list[float] | [] | 3 (RGB) or 4 (RGBA), each 0.0-1.0 |
| AllowedInBase | bool | YES | YES/NO |
| AllowedInCyclops | bool | YES | YES/NO (both NO = invalid) |
| CustomCraftingTabs | nested list | [] | CraftingTab entries |
| AddedRecipes | nested list | [] | AddedRecipe entries |
| AliasRecipes | nested list | [] | AliasRecipe entries |
| MovedRecipes | nested list | [] | MovedRecipe entries |
| CustomFoods | nested list | [] | CustomFood entries |
| *(plus all AliasRecipe fields)* | | | |

##### CraftingTab

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| TabID | string | -- | Required, unique within fabricator |
| DisplayName | string | "" | Quoted |
| SpriteItemID | string | None | Existing TechType for icon |
| ParentTabPath | string | "" | Slash-separated fabricator path |

##### MovedRecipe

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| ItemID | string | -- | Required, existing recipe TechType |
| OldPath | string | None | Required if not Hidden |
| NewPath | string | None | Required if not Hidden |
| Copied | bool | NO | YES = copy, NO = move |
| Hidden | bool | NO | YES = remove from tree |

##### CustomSize

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| ItemID | string | -- | Required |
| Width | int | 1 | 1-6 |
| Height | int | 1 | 1-6 |

##### CustomBioFuel

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| ItemID | string | -- | Required |
| Energy | float | 0.0 | >= 0 recommended |

##### CustomFragmentCount

| Field | Type | Default | Constraint |
|-------|------|---------|------------|
| ItemID | string | -- | Required |
| FragmentsToScan | int | 1 | >= 1 |

##### Enum reference (from CC3 + Subnautica game assembly)

**FabricatorModel** (Nautilus `FabricatorTemplate.Model`):

| Value | Description |
|-------|-------------|
| Fabricator | Standard wall-mounted fabricator (default) |
| Workbench | Modification station (ground-placed) |
| MoonPool | Moon pool fabricator (Subnautica 1 only) |
| Custom | Custom model (requires prefab -- not used in CC3 text files) |

**FoodModel** (CC3 `FoodModel.cs`, 36 values):

| Category | Values |
|----------|--------|
| None | None |
| Water | BigFilteredWater, DisinfectedWater, FilteredWater, WaterFiltrationSuitWater |
| Plants | BulboTreePiece, PurpleVegetable, CreepvinePiece, JellyPlant, KooshChunk, HangingFruit, Melon, NutrientBlock |
| Cooked fish | CookedPeeper, CookedHoleFish, CookedGarryFish, CookedReginald, CookedBladderfish, CookedHoverfish, CookedSpadefish, CookedBoomerang, CookedEyeye, CookedOculus, CookedHoopfish, CookedSpinefish, CookedLavaEyeye, CookedLavaBoomerang |
| Cured fish | CuredPeeper, CuredHoleFish, CuredGarryFish, CuredReginald, CuredBladderfish, CuredHoverfish, CuredSpadefish, CuredBoomerang, CuredEyeye, CuredOculus, CuredHoopfish, CuredSpinefish, CuredLavaEyeye, CuredLavaBoomerang |

**TechGroup** (Subnautica game enum, resolved via `Enum.TryParse` case-insensitive):

| Value | Usage |
|-------|-------|
| Uncategorized | Default for AddedRecipe/AliasRecipe |
| Resources | Raw/crafted materials |
| Survival | Food, water, first aid |
| Personal | Equipment, tools |
| Machines | Deployables |
| InteriorModules | Base interior buildables |
| InteriorPieces | Base interior structure |
| ExteriorModules | Base exterior buildables |
| BasePieces | Base structural components |
| Cyclops | Cyclops upgrades |
| Constructor | Mobile vehicle bay items |
| Miscellaneous | Uncategorized buildables |
| VehicleUpgrades | Seamoth/Prawn upgrades |
| MapRoomUpgrades | Scanner room upgrades |

**TechCategory** (Subnautica game enum, resolved via `Enum.TryParse` case-insensitive):

| Value | Parent TechGroup(s) |
|-------|---------------------|
| Misc | fallback default |
| BasicMaterials | Resources |
| AdvancedMaterials | Resources |
| Electronics | Resources |
| Water | Survival |
| CookedFood | Survival |
| CuredFood | Survival |
| FoodAndDrinks | Survival (Below Zero) |
| Equipment | Personal |
| Tools | Personal |
| Machines | Machines |
| InteriorModule | InteriorModules |
| InteriorPiece | InteriorPieces |
| ExteriorModule | ExteriorModules |
| BasePiece | BasePieces |
| BaseRoom | BasePieces |
| BaseWall | BasePieces |
| CyclopsUpgrades | Cyclops |
| Constructor | Constructor |
| VehicleUpgrades | VehicleUpgrades |
| MapRoomUpgrades | MapRoomUpgrades |
| Rocket | Rocket |
| Workbench | Workbench |

**CraftTree.Type** (vanilla fabricator identifiers, used as Path prefix):

| Value | In-game name |
|-------|-------------|
| None | (invalid/unset) |
| Fabricator | Standard Fabricator |
| Workbench | Modification Station |
| Constructor | Mobile Vehicle Bay |
| CyclopsFabricator | Cyclops Fabricator |
| SeamothUpgrades | Vehicle Upgrade Console |
| MapRoom | Scanner Room |
| Centrifuge | Centrifuge (Below Zero) |
| Rocket | Neptune Launch Platform |

##### Custom Fabricator Architecture (verified against CC3 C# source)

Understanding how fabricators, tabs, and recipes relate is critical for the editor.

**One block type per file:** `WorkingFileParser.cs` enforces that each `.txt` file has
exactly one primary block keyword (`CustomFabricators:`, `AddedRecipes:`, etc.).
A single file cannot contain both top-level `CustomFabricators:` and top-level
`AddedRecipes:` blocks. However, a `CustomFabricator` block can contain nested
`CustomCraftingTabs`, `AddedRecipes`, `AliasRecipes`, `MovedRecipes`, and `CustomFoods`.

**Path is always absolute:** The `Path` field on recipes and `ParentTabPath` on tabs
always start from the fabricator ID, even for entries nested inside a fabricator block.
Example: `Path: MyFab/WeaponsTab;` not `Path: WeaponsTab;`.

**Cross-file references are valid:** A recipe in `recipes.txt` can reference a tab
defined in `customfab.txt` via its `Path` field. CC3 processes the entire mod folder
as a unit with a fixed global ordering.

**CC3 processing order** (from `WorkingFileParser.OrderedPackages`):

```
CustomFabricators -> CustomCraftingTabs -> AddedRecipes ->
AliasRecipes -> ModifiedRecipes -> CustomFoods -> MovedRecipes ->
CustomSizes -> CustomBioFuels -> CustomFragmentCounts
```

Tabs must exist before recipes reference them.

**Nesting and ownership diagram:**

```
CustomFabricator (item_id: "MyFab", model: "Fabricator")
|
|-- CustomCraftingTabs (nested, defined inside fabricator block):
|   |-- CraftingTab (tab_id: "Weapons", parent_tab_path: "MyFab")
|   |-- CraftingTab (tab_id: "Heavy",   parent_tab_path: "MyFab/Weapons")
|
|-- AddedRecipes (nested, defined inside fabricator block):
|   |-- AddedRecipe (item_id: "LaserGun",  path: "MyFab/Weapons")
|   |-- AddedRecipe (item_id: "RailGun",   path: "MyFab/Weapons/Heavy")
|
|-- AliasRecipes (nested):
|   |-- AliasRecipe (item_id: "CustomBlade", path: "MyFab/Weapons")
|
|-- MovedRecipes (nested):
    |-- MovedRecipe (item_id: "Knife", old_path: "Fabricator/...", new_path: "MyFab/Weapons")
```

**Visual relationships for the node editor:**

```
[Fabricator: MyFab] ---owns---> [Tab: Weapons] ---owns---> [Tab: Heavy]
                                     |                          |
                              contains recipes:          contains recipes:
                                     |                          |
                               [LaserGun]                  [RailGun]
                               [CustomBlade]
```

- **Fabricator -> Tab**: tab's `ParentTabPath` starts with the fabricator ID
- **Tab -> Recipe**: recipe's `Path` points into the tab
- **Tab -> Sub-tab**: child tab's `ParentTabPath` includes parent tab
- **Recipe -> Ingredients**: existing ingredient edges (already implemented)

**Editor implication:** Recipe nodes that support `Path` (AddedRecipe, AliasRecipe,
CustomFood) should expose a visual connection point for tab/fabricator assignment.
See "Recipe Path slot" note under Checkbox 4.

#### Dynamic Input Slots (universal design for all nodes)

**Replaces the earlier "Path / ParentTabPath slots" approach.** Instead of reserving static
input pins for specific fields (Path, ParentTabPath), every node type gets a universal
dynamic input slot system:

1. **Every node always has one empty input pin.** This is the "open" slot, waiting for a
   connection. It appears on all node types: recipes, ingredients, tabs, fabricators,
   properties -- everything.
2. **When a connection is made to the open slot, a new empty slot spawns below it.** The
   previously empty slot becomes "filled" (showing the connected node's label/ID), and a
   fresh empty slot appears so the user can always add more connections.
3. **Disconnecting a filled slot removes it** (or collapses it back), keeping the node tidy.
   The last slot always stays empty.
4. **Slot semantics depend on what is connected:**
   - Ingredient node -> recipe input = adds that ingredient to the recipe
   - CraftingTab -> recipe input = sets the recipe's `Path` to the tab's full path
   - Fabricator/Tab -> tab input = sets the tab's `ParentTabPath`
   - Recipe -> recipe input = direct dependency link (crafted ingredient, Step 11h)
5. **This replaces hard-coded pin counts.** No need to pre-allocate ingredient pins or
   Path pins. The node grows organically as connections are made.

Implementation touches: `qt_nodes.py` (node port creation, link callbacks),
`sync.py` / `qt_gui.py` (connection handler must detect what was connected and dispatch to the
right command: AddIngredient, ChangeRecipeField for Path, etc.). Likely Step 11h or Step 12.

#### Checkbox 5 -- Color swatch example recipe

Create a test/example recipe directory that produces one node of every `NodeKind` on the canvas
simultaneously, plus special states (orphan, cycle, intermediate). This serves as a live color
swatch so all title bar colors can be compared at a glance for differentiability and contrast
against the dark background. Use the result to tune `_KIND_COLORS` values before locking them in.

- [x] Create `scripts/color_swatch/` directory with 10 files (one per block type): modified.txt,
  added.txt, alias.txt, food.txt, fabricator.txt, tabs.txt, moved.txt, sizes.txt, biofuel.txt,
  fragments.txt. Includes a cycle pair (CycleA/CycleB), an orphan (OrphanItem), and an
  intermediate ingredient (Knife used by SuperKnife). 14 distinct visual states total.
- [x] Load in `craftgraph gui scripts/color_swatch/` and review all colors side by side.
  **Note:** END_PRODUCT dark gold color never appears in the node editor -- recipe nodes use
  NodeKind colors, and END_PRODUCT items never appear as ingredient instances.
- [ ] Adjust any node color entries that are too similar or lack contrast; document final palette in a comment in `qt_nodes.py`.

### Step 11g -- Node Sprite/Image Display

> Checkboxes 1-4 done -- see CHANGELOG.md. Design notes kept below for reference.

#### Design: universal sprite support for all nodes

**Every node type** gets sprite display capability. No node type is excluded.
The sprite is purely a CraftGraph visual aid (it does not write `SpriteItemID` to the
EasyMarkup file unless the modder explicitly sets that field).

**Auto-assign behavior:** When a recipe directory has an `Assets/` subfolder (the standard
CC3 convention), CraftGraph scans it for PNGs. Any node whose ItemID (or TabID for tabs)
matches a filename (case-insensitive, e.g., `Assets/titanium.png` matches ItemID `Titanium`)
automatically gets that image displayed on its node. This happens:
- On initial load (scan `Assets/` once, build an ItemID-to-path lookup)
- On node creation (if the new node's ItemID matches an existing PNG, auto-assign)
- On file watcher rebuild (re-scan `Assets/` for new/removed PNGs)

**Manual override:** Every node's edit dialog includes a "Browse Image" button for manually
selecting a PNG. This is useful when:
- The PNG filename doesn't match the ItemID (rare, but possible)
- The modder wants to preview an image before placing it in `Assets/`
- The `Assets/` folder doesn't exist yet (CraftGraph doesn't create it)

**No image is fine:** Nodes without a matched or manually-set image simply show no thumbnail.
The game itself falls back to a black question-mark sprite for missing images, so this is
a valid state. No warnings needed.

**CC3's in-game sprite resolution** (for reference, not replicated in CraftGraph):
1. PNG in `Assets/` matching ItemID
2. `SpriteItemID` field -> existing TechType's sprite
3. First `LinkedItemID`'s sprite
4. Fallback: black question-mark

CraftGraph only implements step 1 (Assets/ auto-assign) and manual browse. Steps 2-3 are
in-game runtime behavior that we don't need to replicate in the editor.

#### Checkboxes 1-4 -- DONE (see CHANGELOG)

All sprite/image work complete: Assets/ auto-scanning, QPixmap thumbnails on nodes,
Browse/Clear image via SpriteNode connections, SpriteItemID field for
AliasRecipe/CustomFood/CraftingTab.

### Step 11i -- Fabricator/Tab/Recipe Hierarchy Connections

**Priority:** High (next up after dynamic input slots bug fix)
**Depends on:** Dynamic input slots fix (done), Step 11f (node types exist)
**Effort:** Medium-Large -- wires non-recipe nodes into the connection system

Currently non-recipe nodes (fabricators, tabs) exist as standalone visual placeholders.
`on_link()` silently rejects any connection targeting them because it checks
`target_recipe is not None`. The data model already supports containment
(`CustomFabricator.tabs`, `CustomFabricator.added_recipes`) and
`ChangeNonRecipeFieldCommand` exists but is not wired to drag-and-drop connections.

**Goal:** Enable the visual hierarchy Fabricator -> Tab -> Recipe via drag-and-drop
connections, matching the CC3 data model's containment structure:

```
[Fabricator: MyFab] ---owns---> [Tab: Weapons] ---owns---> [Tab: Heavy]
                                     |                          |
                              contains recipes:          contains recipes:
                                     |                          |
                               [LaserGun]                  [RailGun]
                               [CustomBlade]
```

- [x] **Extend `on_link()` to handle non-recipe targets** (`sync.py`): When the target
  node is a non-recipe (fabricator or tab) and the source is a recipe, tab, or fabricator,
  dispatch to the appropriate command instead of silently returning. The dispatch table:
  - Recipe -> Fabricator `__empty__` pin: nest recipe inside `fabricator.added_recipes` (or
    alias/food based on recipe kind) and set `recipe.path` to fabricator root
  - Recipe -> Tab `__empty__` pin: set `recipe.path` to the tab's full path
  - Tab -> Fabricator `__empty__` pin: nest tab inside `fabricator.tabs` and set
    `tab.parent_tab_path` to fabricator ID
  - Tab -> Tab `__empty__` pin: set child `tab.parent_tab_path` to parent tab's full path
  - Fabricator -> Fabricator: reject (no nesting of fabricators)
- [x] **Extend `on_delink()` for non-recipe disconnections** (`sync.py`): Reverse the
  above operations. Disconnecting a recipe from a tab clears its `path` field. Disconnecting
  a tab from a fabricator removes it from `fabricator.tabs` and clears `parent_tab_path`.
- [x] **Display nested fabricator contents** (`sync.py`): Currently
  `_spawn_non_recipe_nodes()` only shows top-level entries. Fabricators contain nested
  `tabs`, `added_recipes`, `alias_recipes`, `moved_recipes`, and `custom_foods` that are
  invisible in the GUI. Spawn these as connected child nodes during visual rebuild.
- [x] **Fabricator/tab output pin semantics** (`qt_nodes.py`): Fabricator and tab output
  pins show "Contains: N" with the total child count (tabs + recipes + moved_recipes).
  Updated dynamically during `_spawn_nested_fab_contents()` via `update_output_label()`.
- [x] **Layout for hierarchy** (`sync.py`): 3-column hierarchy-aware positioning:
  fabricators leftmost (min_recipe_x - 500), tabs in the middle (min_recipe_x - 250),
  recipes on the right. Other non-recipe entries (sizes, biofuels) cluster below.
  Implemented via `_compute_non_recipe_positions()`.
- [x] **Filled slot labels for non-recipe connections**: When a hierarchy link is created
  via `_create_hierarchy_link()`, the child node's hierarchy pin label updates from
  "Parent" to "Parent: {parent_id}". Resets on rebuild when no link exists.
- [x] **Label hierarchy input pins**: Hierarchy input pins show "Parent" in dimmed gray
  text (150, 150, 150, 128 alpha). Fabricators have no hierarchy input pin (top-level).
  Label stored in `hierarchy_label_id` for dynamic updates.
- [x] **Enforce CC3 processing order in serializer** (`serializer.py`): CC3 processes blocks
  in a strict global order: `CustomFabricators -> CustomCraftingTabs -> AddedRecipes ->
  AliasRecipes -> ModifiedRecipes -> CustomFoods -> MovedRecipes -> CustomSizes ->
  CustomBioFuels -> CustomFragmentCounts`. Tabs must exist before recipes reference them.
  The serializer already emits in correct order within `_serialize_custom_fabricator()`
  (tabs -> added -> alias -> moved -> foods). One block type per file makes top-level
  ordering inherent.
- [x] **Connection-time order validation**: `_try_fabricator_hierarchy()` returns `None`
  when a tab's parent fabricator is not found, and rejects fabricator-to-fabricator
  connections. Basic validation is in place; user-facing warnings deferred to Step 11j.
- [x] **Tests**: Command round-trip tests in `test_hierarchy.py` (15 tests including
  AliasRecipe and CustomFood nesting). Serializer order tests in `test_serializer.py`
  (`TestFabricatorInternalOrder`: tabs before recipes, full CC3 order). 566 total tests
  passing.

---

### Step 11h -- Recipe-to-Recipe Links + Orphan Ingredient Nodes

**Priority:** High (must fix before Step 12)
**Depends on:** Step 11c (Node Kind system)
**Effort:** Medium -- extend connect_ingredients, add orphan creation, update layout

**Current state:** `connect_ingredients()` in `sync.py` already wires recipe-to-recipe
links: if recipe B is an ingredient of recipe A, B's output port connects to A's
ingredient slot. This works today. What is missing: raw-material ingredients (items with
no recipe on the canvas) leave ingredient slots unconnected with no visual indication of
what they represent.

**Expected behavior:** After wiring recipe-to-recipe links, every remaining unmatched
ingredient gets an `OrphanIngredientNode` (output-only, visual, no model_ref). One
orphan per unique raw-material ItemID; its `output` port (multi=True) connects to every
recipe that uses it. The graph becomes fully connected and self-documenting.

- [x] **Auto-create OrphanIngredientNodes for unmatched ingredients** (`sync.py`):
  Extend `connect_ingredients()`. After the existing recipe-to-recipe wiring pass,
  collect ingredient ItemIDs that had no matching recipe node. For each unique unmatched
  ID, create one `OrphanIngredientNode` with `item_id` set, then connect its `output`
  port to every consuming recipe's first unconnected `ingredient_N` slot. Return the
  orphan nodes alongside the connection count so the caller can track them.
- [x] **Include orphan nodes in layout** (`sync.py`): `compute_hierarchy_layout()`
  positions only model-backed nodes (keyed by `id(model)`). Orphan nodes have no model,
  so they need a separate positioning pass. Place them in a column to the left of the
  recipe columns, ordered alphabetically or by connection count.
- [x] **Register orphans with the active tab**: The loading pipeline in `qt_gui.py`
  needs to store orphan nodes so they can receive completers, sprites, and be included
  in export/save flows. Track them in a side map (e.g. `tab.orphan_nodes`) since they
  are not in `model_to_node`.
- [x] **Verify interactive editor compatibility** (`sync.py`): The
  `_handle_ingredient_connected` / `_handle_ingredient_disconnected` handlers check
  `model_ref` on the source node. OrphanIngredientNodes have `model_ref=None`, so
  connecting FROM an orphan to a recipe is a data-model no-op (correct -- orphans are
  visual-only, the user edits the ingredient list via text fields or by connecting
  recipe nodes). Disconnecting must also handle None gracefully. Verify both paths
  with manual testing and add test coverage.
- [x] **Cycle highlighting verification**: `highlight_cycle_edges()` already works for
  recipe-to-recipe edges (matches `item_id` pairs from the NetworkX graph). Orphan
  nodes cannot participate in cycles (they have no incoming edges). Verify with a test
  that the existing highlighting still works correctly with orphan nodes present.
- [x] **Tests**: Verify that loading a file with A -> B -> C (all recipes) produces
  direct recipe-to-recipe links (no orphans for B or C). Verify that A -> X (X is raw)
  creates an OrphanIngredientNode for X wired to A. Verify one orphan per unique raw
  material (if both A and B use Titanium, one orphan feeds both). Verify layout assigns
  positions to orphan nodes. Verify cycle highlighting ignores orphan edges.

### Step 11g.2 -- Enhanced SpriteNode: File Picker, Preview, and Drag-Drop

**Priority:** Medium (quality-of-life for sprite workflow)
**Depends on:** Step 11g (sprite infrastructure exists)
**Effort:** Medium -- enhances existing SpriteNode, adds drag-drop handler on viewer

The current SpriteNode has only a plain text field for the file path. This step
makes sprite assignment intuitive by adding a file browser, live preview, and
drag-drop support from the OS file manager.

**Design decisions:**
- Enhance existing SpriteNode (no new node types)
- Header icon (64x64) serves as the image preview (consistent with all other nodes)
- Smart drag-drop: dropping on a node sets its sprite directly, dropping on empty canvas creates a SpriteNode
- Connecting a SpriteNode to a recipe extracts the filename stem as the sprite ID (existing behavior, unchanged)

- [x] **SpriteNode self-preview:** Hook `file_path` textChanged to call `self.set_sprite(Path(value))` on the SpriteNode itself, so its header icon always reflects the current file. Clearing the field clears the preview.
- [x] **Browse button widget:** Add a `_BrowseButtonWidget(NodeBaseWidget)` to SpriteNode -- a "Browse..." QPushButton that opens `QFileDialog.getOpenFileName()` filtered to `*.png`. On selection, writes the path into the node's `file_path` property. Both the text field and the button update the same underlying value. Remembers last-used directory between clicks.
- [x] **Canvas drag-drop (dragEnterEvent):** Install drag-enter/drop handlers on the NodeGraphQt viewer. Accept drags carrying file URLs that end in `.png`. Reject everything else.
- [x] **Canvas drag-drop (dropEvent -- smart drop on node):** On drop, map position to scene coordinates and check for an existing node under the cursor. If a node with a `sprite_in` port is found, set the sprite directly on that node and store a manual override (reuse the existing `_on_set_sprite` flow).
- [x] **Canvas drag-drop (dropEvent -- create SpriteNode on empty canvas):** If no node is under the drop cursor, create a new SpriteNode at the drop position with `file_path` pre-filled to the dropped file's path. The self-preview hook displays the image automatically.
- [x] **Tests:** SpriteNode browse button exists, textChanged triggers self-preview, drag-drop event acceptance/rejection, drop-on-node sets sprite, drop-on-canvas creates SpriteNode.

### Step 11g.3 -- Autocomplete Popup: "New Item" Entry for Custom IDs

**Priority:** Medium (quality-of-life for custom items)
**Depends on:** Step 11g.2 (autocomplete popup already functional)
**Effort:** Small -- modifies filtering logic in `NodeCompletionPopup`

The autocomplete popup currently filters suggestions as you type, showing the closest
matches from vanilla/mod-compat word lists. The problem: when typing a custom item ID
like `test`, the popup suggests existing items like `devdefaulttest` and pressing Enter
accepts that suggestion instead of keeping the intended custom value. There is no way to
dismiss the autocomplete and keep your exact typed text without clicking away.

This is a standard UX pattern in node editors (Blender, UE5): the popup always includes
an entry at the bottom representing the literal text you typed, so you can explicitly
select it to keep your input as-is. Selecting this entry closes the popup and preserves
the raw typed value. The entry updates live with every keystroke.

**Design decisions:**
- A "New item: {current input}" entry appears as the **last** item in the popup list
  (below all matching suggestions), matching the Blender/UE5 convention
- The entry updates live on every keystroke (textEdited signal already fires per character)
- Selecting the "New item" entry keeps the typed text exactly as-is and closes the popup
- The popup never hides due to zero word-list matches -- the "New item" entry keeps it
  visible as long as there is non-empty text
- If the typed text exactly matches a known word (case-insensitive), the "New item" entry
  is still shown (the user may want to type something that is a substring of a known ID
  but is itself a new custom item)

- [x] **Add "New item" entry to popup** (`qt_gui.py`): In
  `NodeCompletionPopup._on_text_edited()`, after populating the list with word-list
  matches, always append a `New item: {text}` entry as the last item. Style it
  distinctly (e.g. italic or gray text) so it is visually separate from real matches.
  Change the hide condition: only hide when `text` is empty, never when word-list
  matches are empty (the "New item" entry keeps the popup open).
- [x] **Selecting "New item" keeps typed text** (`qt_gui.py`): In `_accept_current()`
  and `_on_item_clicked`, detect if the selected item is the "New item" entry (check
  prefix `New item: `). If so, extract just the raw text after the prefix, write it
  into the line edit, and close the popup. This preserves the user's exact input.
- [x] **Live update on every keystroke**: The entry text must reflect the current
  input at all times. Since `_on_text_edited` already fires on each character via
  `textEdited`, the list rebuild naturally keeps the "New item" entry current. Verify
  backspace/delete also update it.
- [x] **Tests**: Typing unknown text shows "New item: ..." as the last entry. Selecting
  "New item: test" writes "test" into the line edit. Pressing Enter when "New item" is
  highlighted keeps exact typed text. Entry updates when text changes. Empty text hides
  popup entirely (no "New item" entry for blank input). Entry appears even when there
  are word-list matches (so user can always choose their exact input over a suggestion).

### Step 11j -- User-Facing Validation Warnings

**Priority:** Medium (polish, after core connections work)
**Depends on:** Step 11i (hierarchy connections), Step 11h (recipe-to-recipe links)
**Effort:** Small -- most validation feedback already exists

The editor warns users about invalid states via the status bar notification system
(`_show_error_status` with auto-dismiss, red background for errors). Cycle detection,
port constraints, required-field borders, and paired-field borders are all in place.
Remaining items are small targeted additions.

Ordered by effort (smallest first) and independence:

- [x] **Notification system**: Status bar with `_show_error_status()` (red background,
  5-second auto-dismiss via `QTimer.singleShot`). Used by cycle rejection, block type
  enforcement, nesting checks, and 70+ status messages throughout the GUI. Sufficient
  for this application -- floating toasts would be overengineering.
- [x] **Visual indicators on nodes**: Red borders on empty required fields
  (`validate_required_fields`), orange borders on incomplete paired fields
  (`validate_paired_fields`), red 3px cycle edges, distinct node colors per type,
  grey orphan ingredients. Core validation visuals are complete.
- [x] **Fabricator nesting blocked**: Port type constraints prevent invalid hierarchy
  wires. "No fabricator to nest into" and "one block type per file" errors shown.
- ~~**CC3 processing order warnings**~~: Removed. CC3 does two-pass parsing (parse then
  resolve) and does not require forward declarations. We already enforce one block type
  per file. Ordering within a block type is handled by CC3 internally.
- [x] **Cycle path in rejection message**: Currently shows "Rejected: adding X to Y would
  create a circular dependency." Add the full cycle path (A -> B -> C -> A) by extracting
  it from NetworkX. Small, fully independent change in `sync.py` + `qt_gui.py`.
- [x] **Recipe reassignment warning**: When connecting a recipe that already has a `path`
  to a different tab, show "Recipe 'X' already assigned to 'Y'. Reassign?" in the status
  bar. Small check in `_handle_hierarchy_connected`. Fully independent.
- [x] **Tab-to-tab cycle check**: Detect cycles in the tab parent chain (tab A -> tab B ->
  tab A). Similar to the ingredient cycle check but for `parent_tab_path` links. Small,
  fully independent.
- [x] **Save/export validation summary**: On save/export, scan for broken references:
  paths pointing to non-existent tabs, `parent_tab_path` targeting missing fabricators,
  ingredients referencing unknown ItemIDs (not in vanilla or loaded files). Show a summary
  dialog listing all issues before writing. Medium effort, independent.
- [x] **Tests**: Add tests alongside each new item above. Existing tests already cover
  cycle rejection, required/paired borders, port constraints, and block type enforcement.

---

### Step 12 -- Multi-Panel Layout + Bidirectional Code Editor (High complexity)

**Priority:** Deferred
**Depends on:** Step 11j (validation), Step 11h (recipe-to-recipe links)
**Effort:** Large -- this is a major feature and likely its own release

This is the most ambitious step. It adds the full IDE-like layout with
bidirectional sync between visual editing and code editing. Each panel
needs to stay in sync with the others in real time.

**Scoping notes:**
- **Code folding: out of scope.** High complexity, low benefit for ~200-line files.
- **Syntax highlighting and code editor:** Already implemented (QSyntaxHighlighter +
  QPlainTextEdit via `code_editor.py` and `highlighter.py`). Bidirectional sync done
  in Step M5.
- **Thread safety:** Watchdog file watcher runs its own thread. GUI updates must
  be marshalled into Qt's event loop via signals/slots or QTimer.

- [x] **Multi-panel layout** -- 1x2 horizontal split:
  - **Left panel (large):** Node-based editor from Step 11
  - **Right panel:** EasyMarkup code editor (bidirectional)
- [x] **Bidirectional code editor:**
  - Editable text area showing live EasyMarkup output
  - Node changes serialize to code in real time (model -> text via serializer)
  - Code changes parse back to nodes in real time (text -> model via parser)
  - Debounced re-parsing (don't parse on every keystroke, wait for pause)
  - Error-tolerant parsing mode: keep last valid state when code is mid-edit, show parse errors inline without breaking the editor

---

## Known Bugs / UX Fixes (High Priority)

> Issues observed during testing that impact core editing usability.

- [x] **Node click-selection not switching focus:** Single-clicking a different
  node does not always deselect the previously selected node, requiring 2-3
  clicks to move selection between nodes. **Fixed:** `_ViewerModifierSyncFilter`
  resets stale ALT/CTRL/SHIFT states on every mouse press, preventing
  NodeGraphQt from misinterpreting clicks as pan gestures.

---

## Accessibility and Settings (Medium Priority)

> Settings infrastructure and accessibility options.

### Settings Infrastructure

- [x] **Settings dialog window:** Proper `QDialog` with title bar, 8 tabs, dark theme.
  Opened via Help > Settings. Layout-only for now; wiring comes per-feature below.
- [ ] **Settings persistence:** Save user settings to a JSON/TOML file (e.g.,
  `~/.craftgraph/settings.toml` or alongside the project). Load on startup, apply
  before building nodes. All tabs below depend on this.

---

### Tab: General

> Sorted: simple toggles first, then paths (need QFileDialog wiring), then
> startup behavior (needs recent-files tracking infra).

- [ ] **Check for updates:** Toggle update check on startup *(deferred -- needs GitHub
  releases / versioning infrastructure first)*
  `[low complexity | self-contained | just a bool flag]`
- [x] **Backup on save:** Keep `.bak` copy of previous version
  `[low complexity | self-contained | copy-before-write in save path]`
  Implemented: `save_utils.save_with_backup()`, wired into `_on_save` + `_save_all`,
  toggle in Settings > General > Saving. 6 tests in `test_save_utils.py`.
- [x] **Auto-save:** Enable toggle + interval (seconds)
  `[medium complexity | needs QTimer + save-path integration]`
  Implemented: `_set_auto_save()` + `_auto_save_tick()` on CraftGraphWindow,
  QTimer-based with silent save (no validation prompt). Settings dialog wired
  with enable checkbox + interval spinbox. 12 tests in `TestAutoSave`.
- [x] **Default paths:** Default project folder + Subnautica CC3 folder (Browse)
  `[medium complexity | QFileDialog + path validation + used by Open/New]`
  Implemented: `craftgraph/paths.py` with `detect_subnautica_cc3_path()` (walks
  C:/D: Steam library roots segment-by-segment) and `default_project_folder()`
  (~/Documents/CraftGraph). Browse buttons open QFileDialog. Settings dialog
  wired with pass-in/read-back. 9 tests in `test_paths.py`, 6 in `TestDefaultPaths`.
- [x] **Wire CC3 path into file operations:** Use the detected/configured CC3 path as the
  default directory for File > Open Folder, File > Open File, New File, and New Project.
  If CC3 path is empty (no detection, no manual selection), dialogs open without a default
  and prompt the user to select a folder.
  `[low-medium complexity | thread CC3 path through existing dialog calls]`
  - [x] File > Open Folder defaults to `<CC3 path>/WorkingFiles/` (recipe files)
  - [x] File > Open File defaults to `<CC3 path>/WorkingFiles/`
  - [x] New File defaults to `<CC3 path>/WorkingFiles/` as save location
  - [x] New Project defaults to `<CC3 path>/WorkingFiles/` as base location
  - [x] Sprite/asset lookups default to `<CC3 path>/Assets/` folder
  - [x] Auto-detect `WorkingFiles/` inside CC3 folder if it exists, fall back to CC3 root
  - [x] Node editor path lookups (tabs, fabricators) use CC3 path for resolution
  Implemented: `cc3_working_files()` and `cc3_assets()` in `paths.py`, convenience
  methods `_cc3_working_dir()` / `_cc3_assets_dir()` on `CraftGraphWindow`. All file
  dialogs default to `WorkingFiles/`, sprite loading uses `Assets/` as primary source.
  Silent OS-default fallback when CC3 path is unset. Node editor path resolution works
  indirectly: the CC3 default paths feed file loading, which populates the nodes that
  crafting-tree path validation resolves against.
- [x] **Project file format (.craftgraph):** Workspace bookmark stored as a single binary
  file using **MessagePack** serialization (pip: `msgpack`). Lives in the project folder
  (`~/Documents/CraftGraph/`). Does NOT contain recipe data (recipes stay in CC3 folder).
  `[high complexity | needs file format design, serialization, restore logic]`
  **Format decision:** MessagePack chosen over alternatives:
  - ZIP+JSON: overkill, no binary assets to embed alongside JSON
  - Custom binary (like VMware .vmdk): too much versioning/struct work
  - Plain JSON: users would hand-edit and break it
  - MessagePack: single `msgpack.pack()`/`unpack()` call, binary so not hand-editable,
    trivially extensible (just a dict), tiny well-maintained dependency, can dump to
    JSON with a 3-line debug script if needed
  **Contents of a `.craftgraph` project file:**
  - `version`: schema version for future migration
  - `cc3_path`: the Subnautica CC3 folder this project points to
  - `open_files`: list of recipe `.txt` file paths (relative to cc3_path) that were open
  - `active_tab`: which tab was focused
  - `node_positions`: per-file dict of `{node_key: [x, y]}` (replaces sidecar layout.json)
  - `editor_state`: per-file code editor cursor position, scroll offset, etc.
  - `settings_overrides`: any per-project settings that differ from global defaults
  **Behavior:**
  - File > New Project creates a `.craftgraph` file in `~/Documents/CraftGraph/`
  - File > Open Project loads a `.craftgraph` file, restores full workspace state
  - File > Save auto-saves both the recipe `.txt` files (to CC3 folder) and the project
    file (to project folder) so node positions and editor state persist
  - If no project file is loaded (user opened raw .txt files), behaves as today
    (sidecar `.craftgraph/layout.json` for positions, no project-level state)
  - Double-clicking a `.craftgraph` file in Explorer should open the app (file association,
    later step)
- [x] **File association (.craftgraph):** Register `.craftgraph` as a file type so
  double-clicking a project file in Windows Explorer launches CraftGraph and loads
  the project. Cross-platform: Windows (registry), Linux (XDG MIME + .desktop),
  macOS (Info.plist guidance). CLI: `craftgraph register` / `craftgraph unregister`.
  Icon infrastructure wired; icon files pending.
  `[medium complexity | Windows registry, CLI entry point, icon asset]`
- [x] **Recent files:** Configurable max recent-files count
  `[medium complexity | needs recent-files list tracking, used by startup]`
- [x] **Startup behavior:** On-launch action (open last project / welcome screen / empty)
  `[high complexity | depends on recent-files + default paths being wired first]`

---

### Tab: Appearance

> Sorted per subtab. Theme basics first (swap a stylesheet), then node colors
> (remap existing dicts), then code colors (touch highlighter). Colorblind
> mode and UI scale are the hardest since they touch multiple systems.

*Subtabs: Theme | Node Colors | Code Colors*

**Theme:**
- [ ] **Application theme:** Dark / Light / System selector
  `[medium complexity | swap root stylesheet, persist choice]`
- [ ] **Accent color:** Blue / Teal / Green / Orange / Purple / Red
  `[medium complexity | parameterize existing accent in stylesheets]`
- [ ] **High contrast borders:** Accessibility toggle
  `[low complexity | add/remove a border-width override class]`
- [ ] **UI scale:** 100% through 200%
  `[high complexity | QApplication font + widget scaling, affects all layouts]`
- [ ] **Colorblind mode:** Deuteranopia, Protanopia, Tritanopia palettes.
  Remaps `_KIND_COLORS` and `_NODE_COLORS` to distinguishable palettes
  (Wong 2011 or Okabe-Ito). Persists across sessions.
  `[high complexity | palette dicts + node repaint + visualizer + tests]`

**Node Colors:**
- [ ] **Highlight colors:** Cycle edges color, selected node border color
  `[low complexity | two color values fed into existing highlight logic]`
- [ ] **Per-block-type colors:** Color swatch + picker for each of the 10 CC3 node types
  `[medium complexity | 10 swatches -> _KIND_COLORS dict + node repaint]`

**Code Colors:**
- [ ] **Editor background colors:** Background, current line highlight, line number gutter
  `[low complexity | 3 color values applied to CodeEditor stylesheet]`
- [ ] **Syntax token colors:** Keywords, field names, strings, numbers, comments, delimiters
  `[medium complexity | 6 color values -> EasyMarkupHighlighter formats]`

---

### Tab: Node Editor

> Sorted: toggles that flip existing NodeGraphQt properties first, then
> features needing new rendering logic.

- [ ] **Navigation:** Zoom speed, invert zoom direction, pan-with-MMB toggle, show minimap
  `[low complexity | NodeGraphQt viewer properties + minimap visibility]`
- [ ] **Grid:** Show/hide toggle, grid size (px), snap-to-grid, grid style (Dots/Lines/None)
  `[low complexity | NodeGraphQt has grid_mode / set_grid_size APIs]`
- [ ] **Nodes:** Show thumbnails toggle, thumbnail size (px), show port labels,
  warn-before-creating-cycles toggle
  `[medium complexity | thumbnail size needs sprite reload, cycle warn exists]`
- [ ] **Connections:** Pipe style (Curved/Straight/Angle), line width, animate toggle
  `[medium complexity | NodeGraphQt pipe layout enum + custom paint override]`

---

### Tab: Code Editor

> Sorted: font (instant visual feedback, simple) first, display toggles
> second, editing helpers third, sync tuning last.

- [ ] **Font:** Family (QFontComboBox) + size (pt)
  `[low complexity | setFont() on CodeEditor, immediate effect]`
- [ ] **Display:** Show line numbers, highlight current line, word wrap, tab width (spaces)
  `[low complexity | toggle existing LineNumberArea visibility + QTextOption]`
- [ ] **Editing:** Auto-indent, auto-close brackets, strip trailing whitespace on save
  `[medium complexity | keyPressEvent overrides + save-hook logic]`
- [ ] **Bidirectional sync:** Parse debounce interval (ms), show parse errors inline
  `[medium complexity | parameterize existing QTimer delay + error display]`

---

### Tab: Autocomplete

> Sorted: behavior tweaks on existing autocomplete first, then new ID
> sources, then import/export (needs parser integration + file I/O).

- [ ] **Behavior:** Case-insensitive matching toggle, min chars to trigger, max visible suggestions
  `[low complexity | tweak existing completer config values]`
- [ ] **ID sources:** Toggles for vanilla IDs (498), mod-compat IDs (120), IDs from open files
  `[low complexity | filter which ID sets feed into completer word list]`
- [ ] **Custom TechType IDs:** Add/remove list of user-defined IDs that appear in autocomplete
  `[medium complexity | list widget + merge into completer on change]`
- [ ] **Custom data persistence:** Per-project (`.craftgraph/custom_data.json`) and/or
  global (`~/.craftgraph/custom_data.json`). Project-level overrides global.
  `[medium complexity | load/save JSON, merge logic, project vs global scope]`
- [ ] **Import IDs from recipe file:** Browse for a `.txt` file, extract all referenced IDs
  `[medium complexity | reuse parser to extract IDs + dedup into custom list]`
- [ ] **Import IDs from mod folder:** Scan entire mod folder, harvest all referenced IDs
  `[medium complexity | walk directory + parse each file + dedup]`
- [ ] **Export custom data:** Share custom ID lists as standalone JSON
  `[low complexity | JSON dump of custom ID list, but depends on persistence]`

---

### Tab: File Watching

> Sorted: parameterize existing watcher constants first, then add new
> behavior modes.

- [ ] **Debounce interval:** Configurable delay before rebuild (ms)
  `[low complexity | replace _DEBOUNCE_SECONDS constant with setting]`
- [ ] **Enable file watching:** Master on/off toggle
  `[low complexity | start/stop watcher thread based on flag]`
- [ ] **Notifications:** Status bar message on reload, flash tab, sound on cycle detection
  `[medium complexity | status bar exists, tab flash + sound are new]`
- [ ] **On external change:** Auto-reload / Prompt before reloading / Ignore
  `[medium complexity | new dialog prompt path + ignore mode in watcher callback]`

---

### Tab: Keybindings

> Sorted: shortcut editing first (bulk of the work), reset is trivial once
> the data model exists.

- [ ] **Customizable shortcuts:** QKeySequenceEdit for: Save, Save All, Undo, Redo,
  Delete nodes, Select All, Zoom to Fit, Add Recipe, Open Settings, Toggle Code Editor,
  Find Node by ID
  `[high complexity | need action registry mapping names->QActions, persist bindings]`
- [ ] **Reset to defaults:** One-click restore of all default keybindings
  `[low complexity | clear overrides, re-apply defaults from registry]`

---

## Node Title and Label Improvements (Medium Priority)

> Visual clarity improvements for node labels.

- [ ] **Simplify ingredient instance labels:** Currently ingredient instance nodes show
  `node-type(connected-node-int)` (e.g., `Titanium(3)`). Change to show just the node type /
  item ID without the connection index suffix. The index is internal bookkeeping and clutters
  the canvas.
- [ ] **Show AmountCrafted in recipe node titles:** Recipe nodes should display the crafted
  quantity in parentheses after the ItemID when `amount_crafted > 1`. Example: `SuperKnife (x3)`.
  When `amount_crafted` is 1 (the default), show nothing extra to keep labels clean.

---

## Niche QOL Ideas (Low Priority)

> Nice-to-have polish items. Not blocking any step.

### Project Config / Constants

- [ ] **Config file for reusable paths and settings:** Create a `craftgraph/config.py` (or TOML
  config loaded at startup) that centralizes frequently reused values: default asset paths,
  sprite thumbnail size, layout constants, debounce intervals, default fabricator models, etc.
  Currently these are scattered as module-level constants across `qt_nodes.py`, `sync.py`,
  `qt_gui.py`, `watcher.py`
  (debounce delay), and others. A single config module makes them discoverable, overridable
  (e.g., via CLI flags or a user config file), and testable.
- [ ] **Magic number audit and extraction:** Sweep the codebase for unnamed numeric literals
  (magic numbers) and extract them into named constants. Known candidates: layout constants
  in `sync.py`, `300` debounce ms in `watcher.py`, `48` thumbnail size, dialog dimensions. Each
  should become a named constant in the config module or at module level with a clear name.

### Editor UX

- [ ] **Enter key to apply in dialogs:** Pressing Enter in the edit/add-recipe dialog should confirm (same as clicking Apply/Create). Optionally Tab to cycle focus between input fields and buttons.
- [ ] **Spawn new nodes at cursor position:** Right-click > Add Recipe should place the new node where the user clicked, not at a default position. Pass the right-click coordinates through to the recipe creation flow.
- [ ] Warning triangle icon next to node titles that have issues (circular dependencies, incompatible inputs, missing references). Could use a unicode prefix in the node label or a node widget overlay.
- [ ] Node search/filter: type an ItemID to highlight or jump to the matching node in the editor.
- [ ] **"Go to Definition" for nodes:** Double-click (or context menu "Open Source") on a node to switch to the file tab where that node's recipe is defined. Useful for cross-file references: if a recipe in `fabs.txt` uses an ingredient whose recipe lives in `recipes.txt`, opening it jumps to the right tab and selects the node. Two tab concepts: file tabs we *create content in* vs file tabs we *open for reference* (read-only navigation). This lets end users trace ingredients back to their origin without manually searching.
- [ ] Tooltip on hover showing full recipe details (source file, all fields, cycle membership).

### Context Menu Improvements

- [x] **Ingredient node spawning:** Canvas right-click > Add Ingredient spawns a standalone orphan ingredient node. Orphans persist across rebuilds and auto-dissolve when wired to a recipe. *(Done in Step 11c)*
- [x] **Promote ingredient to recipe:** Right-click ingredient > Promote to Recipe submenu (Modified/Added/Alias/CustomFood). Creates a new recipe with that ItemID. *(Done in Step 11c)*
- [ ] **CustomFood skeleton node:** Context menu option to spawn a pre-filled CustomFood recipe with sensible defaults (food/water values, ingredients, display name). Makes creating custom foods faster than starting from an empty recipe.
- [ ] **CustomBattery support:** Model/parser/serializer support for the CustomBattery block type, then context menu entry + dialog for spawning battery nodes.

### Recipe Import / Snippet Paste

- [ ] **Import recipe from known IDs:** Context menu submenu listing all known recipes (vanilla 498 + mod-compat 120). Selecting one spawns a fully linked recipe node into the graph with all ingredients pre-wired. Acts like a "snippet paste" so modders can quickly import an existing recipe, then modify its ingredients/amounts rather than building from scratch.
- [ ] **Batch import:** Import multiple related recipes at once (e.g., all Basic Materials recipes, or all Alchemy recipes) as a connected subgraph.
- [ ] **Template recipes:** User-defined recipe templates saved to a file, available in the context menu for quick insertion of common patterns.

---

## Post-Release Features

> Larger features that build on the completed editor. Not tied to numbered steps.

### Tab ID Autocomplete

- [ ] **Extend autocomplete to CraftingTab IDs:** The autocomplete system (Step 11b) currently covers TechType IDs (vanilla 498 + mod-compat 120). Extend it to also suggest CraftingTab path segments when editing `Path` fields on AliasRecipe/AddedRecipe nodes. Source tab IDs from parsed CustomFabricator/CustomCraftingTab entries + a static list of vanilla fabricator tabs.

### Unlock Condition Visualization and Editing

> Requested by CC3 mod developer. Unlock conditions are a key part of mod design
> but currently invisible in the graph.

**CC3 unlock semantics (verified against C# source, `ModifiedRecipe.HandleUnlocks()`):**

- **`Unlocks: X, Y;`** -- crafting this recipe unlocks ALL listed items (batch call
  to `KnownTechHandler.SetAnalysisTechEntry`).
- **`UnlockedBy: A, B, C;`** -- OR logic. This recipe unlocks when **any one** of the
  listed items is scanned. CC3 loops through each prerequisite and registers this
  recipe independently against each one.

**Feature scope:**

- [ ] **Unlock edges in the dependency graph:** Add a distinct edge type (dashed or
  different color) for unlock relationships alongside the existing ingredient edges.
  `Unlocks: X` = edge from this recipe to X ("crafting me unlocks X").
  `UnlockedBy: A` = edge from A to this recipe ("scanning A unlocks me").
  Multiple `UnlockedBy` entries produce multiple incoming edges (OR semantics --
  any single edge being satisfied is sufficient).
- [ ] **Unlock fields in edit dialogs:** Per-recipe editing of `Unlocks` and `UnlockedBy`
  as comma-separated TechType lists with autocomplete. Show the OR semantics
  clearly in the UI (e.g. label: "Unlocked by (any of):").
- [ ] **Visual distinction for OR vs AND:** Unlock edges could use a different line
  style or color to distinguish "any-of" (UnlockedBy) from "all-of" (Unlocks)
  relationships. Consider a small "OR" / "ALL" badge on the edge or at the
  target pin.

### ~~Tabs as Nodes (formerly Step 11d)~~ -- Absorbed into Step 11f

> Merged into Step 11f (Complete Node Types). All tab/fabricator NodeKind work,
> visuals, context menu entries, and serializer round-trip are covered there.

---

## AFTER ALPHA ROADMAP

> Large architectural features that require their own branch and design cycle.
> These are not blocking alpha release but represent the long-term vision.

### Unified Project Editor (replaces per-file tab model)

**Priority:** Post-alpha, high impact
**Depends on:** All Phase A-C steps complete, stable per-file editing
**Effort:** Large -- own design + plan + implementation cycle

The current editor is **file-centric**: each open file gets its own tab with its own
NodeGraph. This mirrors CC3's one-block-type-per-file constraint, but it means
fabricators/tabs and the recipes that reference them live in separate graphs. Users
must manually type path strings (e.g., `MyFab/ScienceTab`) to assign recipes to
fabricators, which is error-prone and disconnected from the visual editor.

The unified project editor replaces per-file tabs with a **single project-wide graph**
that shows all fabricators, tabs, and recipes from all files in one canvas. Recipes
connect directly to fabricator/tab nodes visually. On export, the app auto-splits
the unified graph back into per-file format (one block type per file, as CC3 requires).

**What this enables:**
- Direct visual wiring of recipes to fabricators/tabs (drag a connection instead of
  typing a path string)
- Full project overview in one canvas -- see the entire mod's recipe tree at a glance
- Eliminates the need for "Get Fabricator" / "Get Tab" reference nodes entirely, since
  fabs and recipes coexist in the same graph
- Hierarchy changes (moving a tab, renaming a fabricator) auto-propagate to all
  connected recipes

**What already exists in the codebase:**
- Parser handles directory loading, returns `list[ParsedFile]` with `source_path`
- `connect_hierarchy()` already wires fabs/tabs/recipes across the full model
- Serializer works per-ParsedFile independently
- CC3's one-block-type-per-file rule makes auto-splitting deterministic

**What needs building:**
- [ ] **Project view mode**: Single NodeGraph showing nodes from all loaded files,
  replacing the current per-file FileTab model. May keep per-file tabs as a
  secondary "file focus" view.
- [ ] **File-assignment logic**: When creating a new node in the unified view, determine
  which file it belongs to. Rules: match by block type to existing files, or create
  new files when needed. User override via context menu ("Move to file...").
- [ ] **Visual file grouping**: Color-code or label nodes by source file so users can
  see which file each node comes from. Optional: collapsible file groups, file
  boundary indicators on the canvas.
- [ ] **Auto-split export**: On save/export, group models by block type and source file,
  serialize each ParsedFile independently. Handle new nodes that don't have a source
  file yet (assign based on block type or prompt the user).
- [ ] **Cross-file hierarchy wiring**: Direct node connections replace path strings.
  When a recipe connects to a tab node, the app computes and stores the path string
  in the model automatically. When the hierarchy changes, all affected paths update.
- [ ] **Migration path**: Ensure per-file editing still works during transition. The
  unified view is additive -- users can switch between project view and file view.

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
