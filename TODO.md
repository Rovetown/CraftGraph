# CraftGraph -- TODO

> Priority-ordered, step-by-step build plan.
> Each step lists what it depends on so nothing is started out of order.
> Checkboxes track completion; update as we go.
>
> Completed steps have been moved to [CHANGELOG.md](CHANGELOG.md).

---

## Cross-Platform Distribution Notes

> Reference for distribution and Phase 2 planning.

### Platform compatibility

| Dependency | Windows | Linux | macOS | Type |
|---|---|---|---|---|
| Python 3.14 | Yes | Yes | Yes | Runtime |
| NetworkX | Yes | Yes | Yes | Pure Python |
| Click | Yes | Yes | Yes | Pure Python |
| Watchdog | Yes | Yes | Yes | Platform-specific backends (ReadDirectoryChangesW / inotify / FSEvents) |
| Pyvis | Yes | Yes | Yes | Generates static HTML |
| Dear PyGui | Yes | Yes | Yes | Pre-built wheels; OpenGL on Win/Linux, Metal on macOS |
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
- `craftgraph check|view|watch` -- CLI commands, no GUI window
- `craftgraph gui` (Phase 2) -- native Dear PyGui window via OpenGL/Metal

Dear PyGui is an optional dependency (`pip install craftgraph[gui]`), so
the CLI-only binary stays small. The GUI binary includes the extra dependency.

---

## Phase 2 -- GUI Editor (Continued)

> Remaining sub-steps for the interactive GUI editor.

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

Implementation touches: `gui_nodes.py` (node attribute creation, link callbacks),
`gui_editor.py` (connection handler must detect what was connected and dispatch to the
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
- [ ] Adjust any `_KIND_COLORS` entries that are too similar or lack contrast; document final palette in a comment in `gui_nodes.py`.

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

All sprite/image work complete: DPG texture pipeline, Assets/ auto-scanning, 48px thumbnails
on nodes, Browse/Clear image buttons in all edit dialogs, SpriteItemID field for
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

- [x] **Extend `on_link()` to handle non-recipe targets** (`gui_editor.py`): When the target
  node is a non-recipe (fabricator or tab) and the source is a recipe, tab, or fabricator,
  dispatch to the appropriate command instead of silently returning. The dispatch table:
  - Recipe -> Fabricator `__empty__` pin: nest recipe inside `fabricator.added_recipes` (or
    alias/food based on recipe kind) and set `recipe.path` to fabricator root
  - Recipe -> Tab `__empty__` pin: set `recipe.path` to the tab's full path
  - Tab -> Fabricator `__empty__` pin: nest tab inside `fabricator.tabs` and set
    `tab.parent_tab_path` to fabricator ID
  - Tab -> Tab `__empty__` pin: set child `tab.parent_tab_path` to parent tab's full path
  - Fabricator -> Fabricator: reject (no nesting of fabricators)
- [x] **Extend `on_delink()` for non-recipe disconnections** (`gui_editor.py`): Reverse the
  above operations. Disconnecting a recipe from a tab clears its `path` field. Disconnecting
  a tab from a fabricator removes it from `fabricator.tabs` and clears `parent_tab_path`.
- [x] **Display nested fabricator contents** (`gui_editor.py`): Currently
  `_spawn_non_recipe_nodes()` only shows top-level entries. Fabricators contain nested
  `tabs`, `added_recipes`, `alias_recipes`, `moved_recipes`, and `custom_foods` that are
  invisible in the GUI. Spawn these as connected child nodes during visual rebuild.
- [ ] **Fabricator/tab output pin semantics** (`gui_nodes.py`): Fabricator and tab output
  pins should visually indicate they are "containers" (label like "Contains:" or child
  count). Consider whether fabricators need multiple output pins (one per nested list type)
  or a single output with dispatch-on-connect.
- [ ] **Layout for hierarchy** (`gui_nodes.py`): The current two-layer layout does not
  account for fabricator -> tab -> recipe depth. Add hierarchy-aware positioning so that
  fabricators appear leftmost, tabs in the middle, and their recipes on the right.
- [ ] **Filled slot labels for non-recipe connections**: When a tab is connected to a
  fabricator's `__empty__` pin, the filled slot should show the tab's ID. When a recipe
  is connected to a tab, the slot should show the recipe's ItemID. Matches the UE5 pattern
  from the Dynamic Input Slots design.
- [ ] **Label hierarchy input pins**: The dedicated `hierarchy_input_attr` pin (added to
  prevent `__empty__` consumption) currently shows an invisible empty string. Give it a
  meaningful label that hints at what should be connected. Examples: "Parent" or
  "Container" for recipe/tab nodes (expects a fab or tab connection), "Fabricator" for
  tab nodes (expects a fab connection). The label should be subtle (dimmed or small text)
  so it doesn't compete with ingredient pin labels.
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
- [ ] **Tests**: Verify fabricator-tab, tab-recipe, and fabricator-recipe connections
  dispatch to the correct commands. Verify disconnect reverses the field changes. Verify
  nested content is spawned during rebuild. Verify serializer output order matches CC3
  processing order.

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

- [ ] **Rework `_build_visual_graph()`** (`gui_nodes.py`): For edges where `ing_id` has
  `is_crafted=True` in the data graph, add a direct edge from `ing_id` to `recipe_id`
  (both are recipe nodes) instead of creating an instance node. Instance nodes remain only
  for edges where `ing_id` is NOT crafted.
- [ ] **Update `RecipeNodeEditor.load()` wiring loop** (`gui_nodes.py`): After creating
  recipe nodes, wire direct links from recipe output attrs to consuming recipe input attrs
  for crafted ingredients. Keep the instance-node creation loop for raw materials only.
- [ ] **Layout adjustments**: The multipartite layout assumed two layers (instances left,
  recipes right). With recipe-to-recipe edges, the layout needs to handle a multi-level
  DAG. Consider topological-sort-based layering or a hierarchical spring layout.
- [ ] **Interactive editor compatibility** (`gui_editor.py`): Verify that drag-and-drop
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
- **Syntax highlighting approach:** Invisible `input_text` + rendered drawlist
  overlay (known ImGui pattern). Must handle cursor alignment + scroll sync.
- **Layout approach:** Use `child_window` with manual sizing or `dearpygui-grid`,
  NOT DPG's experimental docking API (unstable).
- **Thread safety:** Watchdog file watcher runs its own thread. GUI updates must
  be marshalled into DPG's render loop via a thread-safe queue, not direct
  DPG calls from the watcher thread (see `dpg-examples` threading pattern).

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

- [x] ~~**CRITICAL -- Node connections broken + dynamic input slots missing:**~~ Fixed.
  Root cause: `on_link()` always routed output-to-input to `_swap_link()`, which silently
  failed for the default `__input__` pin. Fix: replaced `__input__` with `__empty__` sentinel
  pin on all nodes; `on_link()` now routes `__empty__` to `AddIngredientCommand` (full rebuild),
  occupied pins still use incremental swap. 3 contract tests added. Remaining slot semantics
  (non-recipe dispatch, filled-slot labels) moved to Step 11i.
- [ ] **Node click-selection not switching focus:** Single-clicking a different node does not always deselect the previously selected node, requiring 2-3 clicks to move selection between nodes. This appears to be a DPG/imnodes interaction issue where the node editor doesn't properly clear the old selection on a new click. Investigate whether `dpg.clear_selected_nodes()` needs to be called on a left-click handler, or if a DPG callback (`node_clicked_handler` / `deselect_handler`) is needed to force single-selection behavior. Files: `gui.py` (input handlers), `gui_editor.py`.
- ~~**Recipe-to-recipe instance duplication:**~~ Promoted to Step 11h (see above).

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
  persist across sessions (save to a config file or DPG's built-in value registry).
- [ ] **Settings persistence:** Save user settings to a JSON/TOML file (e.g., `~/.craftgraph/settings.toml`
  or alongside the project). Load on startup, apply before building nodes.

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
  Currently these are scattered as module-level constants across `gui_nodes.py` (`_THUMB_SIZE`,
  `_NODE_BOX_PADDING`, `_CLUSTER_GAP`, `_LAYOUT_MARGIN`, `_MAX_ROW_WIDTH`), `watcher.py`
  (debounce delay), and others. A single config module makes them discoverable, overridable
  (e.g., via CLI flags or a user config file), and testable.
- [ ] **Magic number audit and extraction:** Sweep the codebase for unnamed numeric literals
  (magic numbers) and extract them into named constants. Known candidates: `600.0` default
  x-position for non-recipe nodes in `gui_editor.py:_spawn_non_recipe_nodes()`, `130` scale
  factor in `gui_nodes.py:_layout_component()`, `50` margin pixels, `300` debounce ms in
  `watcher.py`, `48` thumbnail size, `420`/`140` dialog dimensions in cycle warning. Each
  should become a named constant in the config module or at module level with a clear name.

### Editor UX

- [ ] **Enter key to apply in dialogs:** Pressing Enter in the edit/add-recipe dialog should confirm (same as clicking Apply/Create). Optionally Tab to cycle focus between input fields and buttons.
- [ ] **Spawn new nodes at cursor position:** Right-click > Add Recipe should place the new node where the user clicked, not at a default position. Pass the right-click coordinates through to the recipe creation flow.
- [ ] Warning triangle icon next to node titles that have issues (circular dependencies, incompatible inputs, missing references). Could use a unicode prefix in the node label or a small DPG text overlay.
- [ ] Node search/filter: type an ItemID to highlight or jump to the matching node in the editor.
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

## Phase 2 -- Dear PyGui Add-ons and References

> Potential libraries, examples, and inspiration for the GUI editor.
> Not all of these will be used -- they're here as a reference when
> deciding what to integrate at each step.

### Libraries / Add-ons

| Repo | What it does | Relevant to |
|---|---|---|
| [totallynotdrait/file_dialog](https://github.com/totallynotdrait/file_dialog) | Customizable file dialog with file type icons, drive shortcuts, modern UI | Step 9 (replace built-in DPG file dialog) |
| [awcook97/DearPyGui_EditThemePlugin](https://github.com/awcook97/DearPyGui_EditThemePlugin) | Runtime theme/font editor plugin with save/load | Step 9-12 (user-customizable themes) |
| [Atlamillias/dearpygui-grid](https://github.com/Atlamillias/dearpygui-grid) | Grid-based layout manager without separate containers | Step 12 (multi-panel layout) |
| [fabriciochamon/DearPyGui_Extend](https://github.com/fabriciochamon/DearPyGui_Extend) | Extra widgets: draggable groups, file browser, text-based layout | Step 12 (alternative layout system) |
| [IvanNazaruk/DearPyGui-ImageController](https://github.com/IvanNazaruk/DearPyGui-ImageController) | Auto load/unload textures by viewport visibility | Step 9-11 (performance with many nodes/icons) |

### Node Editor References

| Repo | What it does | Relevant to |
|---|---|---|
| [Cresliant/Cresliant](https://github.com/Cresliant/Cresliant) | Node-based image editor in DPG -- visual node wiring for processing pipelines | Step 9-11 (potential alternative to raw DPG node editor) |
| [DataExplorerUser/drag_drop_node_editor](https://github.com/DataExplorerUser/drag_drop_node_editor) | Minimal DPG drag-and-drop node editor example | Step 9 (reference for basic node wiring) |

### General Inspiration

| Repo | What it does | Relevant to |
|---|---|---|
| [thomasroessl/FlowTutor](https://github.com/thomasroessl/FlowTutor) | Visual flowchart programming environment with node connections and debugging | Step 12 (layout and UX inspiration for the multi-panel flow) |
| [my1e5/dpg-examples (threading/progress_bar)](https://github.com/my1e5/dpg-examples/blob/main/threading/progress_bar.py) | Background thread with start/pause/resume driving a DPG progress bar | Step 6+9 (async file watching + GUI rebuild without freezing) |

---

## Quick Reference: Dependency Graph

```
  Phase 1 (Steps 0-8) ......... DONE (see CHANGELOG.md)
  Step 9  (Node Viewer) ....... DONE
  Step 9b (Viewer Polish) ..... DONE
  Step 10 (Serializer) ........ DONE
  Step 11  (Interactive Editor)  DONE
  Step 11b (Autocomplete) ..... DONE
  Step 11c (Node Kind System) . DONE
  Step 11e (Parser Refinements) DONE
          |
  (All above -> CHANGELOG.md)
  Step 11f (All Node Types + Field Inventory) -- checkbox 5 remaining
  Step 11g (Sprite/Image Support) ------------- DONE (checkboxes 1-4)
  BUG FIX: Node connections + dynamic slots ---- DONE
          |
  Step 11i (Fab/Tab/Recipe Hierarchy) --------- High, next up
          |
  Step 11h (Direct Recipe-to-Recipe Links) ---- Medium, UX correctness
          |
  Step 11j (Validation Warnings/Popups) ------- Medium, polish
          |
    Step 12  (Multi-Panel + Bidir) -- High, IDE-like experience

  Post-release (no step number):
    Tab ID Autocomplete ........ Small, extends 11b
```
