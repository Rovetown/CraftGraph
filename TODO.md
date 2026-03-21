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
- [ ] Mutual exclusion enforcement (Copied/Hidden, PdaGroup/PdaCategory)
- [ ] Path reference validation (does the referenced tab exist?)
- [ ] Export-time validation summary dialog
- [ ] Syntax highlighter rules for common text-level mistakes (missing `;`, wrong separator, unquoted spaces)

#### Phase F -- Reference Panel and Polish

- [ ] Vanilla ItemID categorized reference panel (dockable, 498 IDs by TechGroup/TechCategory)
- [ ] Drag-from-panel-to-pin interaction
- [ ] Enum combo box population with full value lists (FabricatorModel, FoodModel, TechGroup, TechCategory, CraftTree.Type)
- [ ] CraftTree.Type Centrifuge marked as Below Zero / cut content for SN1
- [ ] Rich text menu labels (QWidgetAction + QLabel with HTML) to replace `--` separators with bold names and styled descriptions
- [x] Floating tooltips for context menu entries (show description on hover instead of inlining it in the label text)
- [ ] Floating tooltips for node headers (show node type description on hover over a node in the graph)
- [ ] Floating tooltips for node field widgets (show field-level help text on hover, e.g. "TechType ID", "Valid range 1-25")
- [ ] Category dropdown: z-order/layer issues (proxy widgets below bleed through open dropdown -- needs z-value or native popup approach)

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

### Step 11h -- Direct Recipe-to-Recipe Connections

**Priority:** High (must fix before Step 12)
**Depends on:** Step 11c (Node Kind system)
**Effort:** Medium -- rework visual graph builder and node wiring, update layout

The current instance-per-usage model creates a separate ingredient instance node for every
edge in the dependency graph, even when the ingredient is itself a recipe already on the
canvas. This means recipe A and a duplicate "instance of A" both appear, which looks like
two unrelated things and confuses the dependency chain.

**Expected behavior:** When an ingredient ItemID matches an existing recipe node, the link
goes directly from that recipe node's output pin to the consuming recipe's input pin. No
intermediate instance node is created. Instance nodes are only created for **raw materials**
(items that have no recipe of their own in the loaded file set).

This turns the flat two-layer layout into a true dependency DAG where recipe chains are
visually connected, making the graph actually useful for understanding crafting dependencies.

- [ ] **Rework `_build_visual_graph()`** (`qt_nodes.py`): For edges where `ing_id` has
  `is_crafted=True` in the data graph, add a direct edge from `ing_id` to `recipe_id`
  (both are recipe nodes) instead of creating an instance node. Instance nodes remain only
  for edges where `ing_id` is NOT crafted.
- [ ] **Update `RecipeNodeEditor.load()` wiring loop** (`qt_nodes.py`): After creating
  recipe nodes, wire direct links from recipe output attrs to consuming recipe input attrs
  for crafted ingredients. Keep the instance-node creation loop for raw materials only.
- [ ] **Layout adjustments**: The multipartite layout assumed two layers (instances left,
  recipes right). With recipe-to-recipe edges, the layout needs to handle a multi-level
  DAG. Consider topological-sort-based layering or a hierarchical spring layout.
- [ ] **Interactive editor compatibility** (`sync.py`): Verify that drag-and-drop
  wiring, link deletion, and swap logic still work when the source node is a recipe (not
  just an instance). The `_find_recipe_for_ingredient()` helper and delink logic may need
  updates since the source of a link can now be a recipe node, not just an ingredient node.
- [ ] **Cycle highlighting**: Ensure cycle detection still highlights both the recipe nodes
  and the direct edges between them (no instance nodes to color for crafted-ingredient edges).
- [ ] **Tests**: Update or add tests for the new visual graph topology. Verify that a graph
  with A -> B -> C (all recipes) produces direct links, while A -> X (X is raw) still
  creates an instance node for X.

### Step 11j -- User-Facing Validation Warnings and Error Popups

**Priority:** Medium (polish, after core connections work)
**Depends on:** Step 11i (hierarchy connections), Step 11h (recipe-to-recipe links)
**Effort:** Small-Medium -- UI feedback layer on top of existing validation logic

The editor should warn users about invalid states rather than silently rejecting connections
or producing broken output. Currently, invalid operations (self-loops, duplicate ingredients,
cycles) either silently fail or show a basic modal dialog (the cycle warning from checkbox 9).
This step standardizes all validation feedback into a consistent, non-blocking notification
system.

- [ ] **Notification/toast system**: Add a lightweight notification area (bottom-right or
  status bar) that shows temporary warnings without blocking interaction. Toasts auto-dismiss
  after a few seconds. More severe errors (data loss risk) use the existing modal dialog
  pattern. Avoid blocking the user for recoverable issues.
- [ ] **Circular dependency warning** (already exists as modal -- migrate to toast or keep as
  modal with more detail). Show the full cycle path (A -> B -> C -> A) so the user knows
  exactly what to fix.
- [ ] **Invalid hierarchy connection warnings**: When the user tries to:
  - Connect a recipe to a tab whose fabricator doesn't exist: toast "Tab 'X' has no parent
    fabricator on canvas"
  - Connect a fabricator to another fabricator: toast "Fabricators cannot be nested"
  - Connect a tab to itself or create a tab cycle: toast with cycle path
  - Connect a recipe that already has a Path to a different tab: toast "Recipe 'X' already
    assigned to tab 'Y'. Reassign?" (or swap automatically)
- [ ] **Missing reference warnings**: On save/export, scan for:
  - Recipes with `path` pointing to a tab that doesn't exist in the file
  - Tabs with `parent_tab_path` pointing to a non-existent fabricator or parent tab
  - Ingredients referencing ItemIDs that don't exist in vanilla or loaded files
  Show a summary warning dialog listing all issues before writing the file.
- [ ] **CC3 processing order warnings**: If the serializer detects that the output would
  have a tab referenced before it's defined (due to ordering), show a warning explaining
  the issue and offer to auto-fix (reorder blocks).
- [ ] **Visual indicators on nodes**: Add a warning icon or colored border on nodes that
  have validation issues (orphan paths, missing references, cycle membership). Could use
  a unicode warning prefix in the node label or a theme override.
- [ ] **Tests**: Verify each warning type triggers for the correct condition. Verify toasts
  auto-dismiss. Verify modal dialogs block appropriately.

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

- [ ] **Multi-panel layout** -- 1x2 split (or 2x2 grid):
  - **Left panel (large):** Node-based editor from Step 11
  - **Top-right panel:** EasyMarkup code editor (bidirectional)
  - **Bottom-right panel:** Mini dependency graph overview
  - Alternative: 1x2 where right side is a vertical split (code on top, mini graph on bottom)
- [ ] **Bidirectional code editor:**
  - Editable text area showing live EasyMarkup output
  - Node changes serialize to code in real time (model -> text via serializer)
  - Code changes parse back to nodes in real time (text -> model via parser)
  - Debounced re-parsing (don't parse on every keystroke, wait for pause)
  - Error-tolerant parsing mode: keep last valid state when code is mid-edit, show parse errors inline without breaking the editor
- [ ] **Mini dependency graph:**
  - Small auto-updating overview of the full dependency tree
  - Highlights the currently selected node/recipe
  - Click-to-navigate: clicking a node in the mini graph selects it in the main editor
  - Helps orient the user in large mod projects with hundreds of recipes

---

## Known Bugs / UX Fixes (High Priority)

> Issues observed during testing that impact core editing usability.

- [ ] **Node click-selection not switching focus:** Single-clicking a different
  node does not always deselect the previously selected node, requiring 2-3
  clicks to move selection between nodes. Investigate whether this is a
  NodeGraphQt quirk or a custom event handler issue. Files: `qt_gui.py`.

---

## Accessibility and Settings (Medium Priority)

> Settings infrastructure and accessibility options.

### Settings Menu

- [ ] **Add a general settings menu** accessible from the GUI menu bar or a gear icon. This is the
  centralized place for all user preferences (theme, accessibility, editor behavior, etc.).
- [ ] **Colorblind mode:** Add colorblind-friendly palette options under Settings > Accessibility.
  At minimum: Deuteranopia (red-green), Protanopia (red-green variant), Tritanopia (blue-yellow).
  Each mode remaps `_KIND_COLORS` and `_NODE_COLORS` to a distinguishable palette. Consider using
  established colorblind-safe palettes (e.g., Wong 2011, Okabe-Ito). The active palette should
  persist across sessions (save to a config file or Qt settings).
- [ ] **Settings persistence:** Save user settings to a JSON/TOML file (e.g., `~/.craftgraph/settings.toml`
  or alongside the project). Load on startup, apply before building nodes.
- [ ] **Custom fields and mod imports (Settings > Custom Data):** Allow users to extend
  CraftGraph's knowledge beyond vanilla + built-in mod-compat IDs:
  - **Manual custom fields:** Add custom TechType IDs, custom enum values, or custom
    block fields via a settings dialog. These appear in autocomplete and are valid
    targets for ItemID pins.
  - **Import from recipe file:** Point at an existing CC3 `.txt` file and extract all
    ItemIDs, tab IDs, fabricator IDs, ingredient references, and enum values found in
    it. Auto-adds them to the custom data pool.
  - **Import from mod folder:** Scan an entire mod folder and harvest all referenced
    IDs across all files. Useful for loading another modder's recipes as a dependency.
  - **Custom data persistence:** Saved per-project (in `.craftgraph/custom_data.json`)
    and/or globally (in `~/.craftgraph/custom_data.json`). Project-level overrides
    global.
  - **Export custom data:** Share your custom ID lists with other modders as a
    standalone JSON file they can import.

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
  Step 11j (Validation Warnings) ------ User-facing error feedback
          |
  Step 12 (Bidirectional Code Editor) - Multi-panel IDE layout
          |
  Known Bugs / UX Fixes
  Accessibility / Settings
  Niche QOL Ideas
  Post-Release Features
```
