# CustomCraft3 and EasyMarkup -- Complete Reference

Doc covers writing recipe files for CustomCraft3 (CC3) Subnautica mod. Covers EasyMarkup syntax, all 10 block types, fields, validation, examples.

Player tweaking recipes, modder building fabricator, dev on CraftGraph -- guide got you.

---

## Table of Contents

1. [What is CustomCraft3?](#what-is-customcraft3)
2. [What is EasyMarkup?](#what-is-easymarkup)
3. [EasyMarkup Syntax](#easymarkup-syntax)
4. [File Rules](#file-rules)
5. [Block Types Overview](#block-types-overview)
6. [Recipe Types (Detailed)](#recipe-types-detailed)
   - [ModifiedRecipe](#1-modifiedrecipe)
   - [AddedRecipe](#2-addedrecipe)
   - [AliasRecipe](#3-aliasrecipe)
   - [CustomFood](#4-customfood)
7. [Container Types (Detailed)](#container-types-detailed)
   - [CustomFabricator](#5-customfabricator)
   - [CustomCraftingTab](#6-customcraftingtab)
8. [Utility Types (Detailed)](#utility-types-detailed)
   - [MovedRecipe](#7-movedrecipe)
   - [CustomSize](#8-customsize)
   - [CustomBioFuel](#9-custombioFuel)
   - [CustomFragmentCount](#10-customfragmentcount)
9. [Ingredients](#ingredients)
10. [Crafting Paths](#crafting-paths)
11. [Unlock System](#unlock-system)
12. [Sprites and Icons](#sprites-and-icons)
13. [Enum Reference](#enum-reference)
14. [Processing Order](#processing-order)
15. [Common Mistakes](#common-mistakes)

---

## What is CustomCraft3?

CC3 -- Subnautica mod by MrPurple6411. Customize crafting recipes, no code. Plain text files in EasyMarkup format, drop in mod folder, CC3 reads on game start.

Can:
- Change ingredients for existing recipes
- Add new craftable items
- Create custom fabricators w/ own tabs and recipes
- Adjust inventory sizes, bioreactor energy, fragment scan counts
- Move or hide recipes from fabricator menus

---

## What is EasyMarkup?

Text format CC3 uses. Simpler alternative to JSON/XML, designed for modders who may not be programmers. Small set of special characters structures data.

---

## EasyMarkup Syntax

### Special Characters

| Character | Name | Purpose |
|-----------|------|---------|
| `:` | Colon | Separates key from value |
| `;` | Semicolon | Ends value |
| `(` `)` | Parentheses | Wraps block (group of key-value pairs) |
| `,` | Comma | Separates list items or entries |
| `#` | Hash | Opens/closes comment |
| `"` | Double quote | Wraps string w/ spaces |
| `\` | Backslash | Escapes special character |

### Key-Value Pairs

Basic building block. Key, colon, value, semicolon:

```
ItemID: Titanium;
```

Whitespace flexible. All identical:

```
ItemID:Titanium;
ItemID: Titanium;
ItemID:   Titanium  ;
```

### Blocks (Complex Values)

Value w/ multiple key-value pairs -- wrap in parentheses:

```
ComplexKey:
(
    SubKey1: Value1;
    SubKey2: Value2;
);
```

Compact form works too:

```
ComplexKey: ( SubKey1: Value1; SubKey2: Value2; );
```

### Lists

Comma-separated values on same key:

```
LinkedItemIDs: Titanium, Gold, Silver;
```

Lists of blocks -- commas between entries, semicolon after last:

```
Ingredients:
    ( ItemID: Titanium; Required: 2; ),
    ( ItemID: Gold;     Required: 1; );
```

### Comments

Wrap text between `#` signs. Can appear anywhere:

```
# This is a comment #
ItemID: Titanium; # Inline comment #
```

Both `#` signs required. Opened `#` must be closed w/ `#`.

### Quoted Strings

Values w/ spaces need double quotes:

```
DisplayName: "Water Jug - 1 gallon";
```

Single-word values -- no quotes needed:

```
DisplayName: Titanium;
```

### Escaping

Special character in unquoted value -- escape w/ `\`:

```
SomeValue: Price\: 100;
```

Inside quoted strings, no escaping needed.

### Case Sensitivity

- **Keys** case-insensitive: `ItemID`, `itemid`, `ITEMID` all work.
- **TechType IDs** case-insensitive: `Titanium` = `titanium`.
- **Booleans** case-insensitive: `YES`, `yes`, `True`, `true` all work.
- **Enum values** (TechGroup, FoodModel) case-insensitive.

### Booleans

CC3 recognized values:

| True values | False values |
|-------------|-------------|
| `YES` | `NO` |
| `TRUE` | `FALSE` |

Output always `YES` or `NO`.

---

## File Rules

### One Block Type Per File

Each `.txt` file -- exactly **one** primary block type. First non-comment content determines type.

Valid: File w/ only `ModifiedRecipes:` entries.
Invalid: File w/ both `ModifiedRecipes:` and `AddedRecipes:` at top level.

**Exception:** `CustomFabricator` block can contain nested `CustomCraftingTabs`, `AddedRecipes`, `AliasRecipes`, `MovedRecipes`, `CustomFoods` inside it. Part of fabricator definition, not separate top-level blocks.

### Multiple Entries Per File

Multiple entries of same type OK. Comma-separated, semicolon after last:

```
ModifiedRecipes:
(
    ItemID: Welder;
    AmountCrafted: 1;
    Ingredients: ( ItemID: Titanium; Required: 1; );
),
(
    ItemID: Knife;
    AmountCrafted: 1;
    Ingredients: ( ItemID: Silicone; Required: 1; );
);
```

### File Encoding

UTF-8. CC3 handles Windows BOM gracefully.

### Cross-File References

Items from one file referenceable from another in same mod folder. CC3 processes entire folder as unit. Recipe in `recipes.txt` can reference tab from `tabs.txt`.

---

## Block Types Overview

10 block types, three categories:

### Recipe Types (inheritance chain)

Shared fields through inheritance. Each type adds fields on top of parent.

```
ModifiedRecipe          (base: change existing recipes)
  |
  +-- AddedRecipe       (adds Path, PDA location)
        |
        +-- AliasRecipe (adds DisplayName, Tooltip, FunctionalID)
              |
              +-- CustomFood (adds food/water/health values)
```

### Container Types

| Type | Purpose |
|------|---------|
| CustomFabricator | Create new crafting station |
| CustomCraftingTab | Add tabs to existing/custom fabricators |

### Utility Types

| Type | Purpose |
|------|---------|
| MovedRecipe | Move, copy, or hide recipes in fabricator menus |
| CustomSize | Change inventory slot dimensions |
| CustomBioFuel | Set bioreactor energy values |
| CustomFragmentCount | Change fragment count to unlock blueprint |

---

## Recipe Types (Detailed)

### 1. ModifiedRecipe

**Purpose:** Change ingredients or unlock conditions of existing base game recipes.

**When to use:** Make existing item cheaper/more expensive, or add unlock conditions.

**Important:** Only works w/ items already craftable in unmodded game. Non-craftable items -- use AddedRecipe.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | In-game item to modify (TechType ID) |
| AmountCrafted | int | No | 1 | Items per craft |
| Ingredients | list | No | [] | Materials needed (see [Ingredients](#ingredients)) |
| LinkedItemIDs | CSV | No | [] | Extra items produced alongside main |
| Unlocks | CSV | No | [] | Items unlocked when crafted |
| UnlockedBy | CSV | No | [] | Items that unlock this when scanned |
| ForceUnlockAtStart | bool | No | NO | Available from game start |

#### Example

```
# Make the Repair Tool require a Battery #
ModifiedRecipes:
(
    ItemID: Welder;
    AmountCrafted: 1;
    Ingredients:
        ( ItemID: Silicone;    Required: 1; ),
        ( ItemID: CrashPowder; Required: 1; ),
        ( ItemID: Titanium;    Required: 1; ),
        ( ItemID: Battery;     Required: 1; );
);
```

#### Example: Unlock-only modification

```
# Don't change the recipe, just add an unlock chain #
ModifiedRecipes:
(
    ItemID: ReactorRod;
    Unlocks: DepletedReactorRod;
);
```

---

### 2. AddedRecipe

**Purpose:** Add crafting recipe for existing in-game item not normally craftable.

**When to use:** Make non-craftable item craftable (e.g. Depleted Reactor Rods), or add alternative recipe.

**Inherits all fields from:** ModifiedRecipe

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| Path | string | Yes | -- | Where in fabricator (see [Crafting Paths](#crafting-paths)) |
| PdaGroup | enum | No | Uncategorized | PDA encyclopedia group (see [Enum Reference](#enum-reference)) |
| PdaCategory | enum | No | Misc | PDA encyclopedia category |

**Note:** Setting PdaGroup requires PdaCategory too (and vice versa).

**Default difference:** `ForceUnlockAtStart` defaults `YES` for AddedRecipe (unlike `NO` for ModifiedRecipe).

#### Example

```
AddedRecipes:
(
    ItemID: DepletedReactorRod;
    AmountCrafted: 1;
    Ingredients:
        ( ItemID: ReactorRod; Required: 1; );
    LinkedItemIDs: UraniniteCrystal, UraniniteCrystal, UraniniteCrystal;
    Path: Fabricator/Resources/Electronics;
    ForceUnlockAtStart: NO;
);
```

---

### 3. AliasRecipe

**Purpose:** Create new item w/ custom name/description. Also alternate recipes producing existing items.

**When to use:**
- Brand-new item not in base game.
- Alternate recipe producing existing item (via `LinkedItemIDs` w/ `AmountCrafted` 0).

**Inherits all fields from:** AddedRecipe (and ModifiedRecipe)

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| DisplayName | string | Yes | "" | Name shown in-game (quote if spaces) |
| Tooltip | string | Yes | "" | Description below name (quote if spaces) |
| FunctionalID | string | No | None | Clone behavior of existing item. Without -- item has no function. |
| SpriteItemID | string | No | None | Use existing item's icon |

#### Example: New custom item

```
AliasRecipes:
(
    ItemID: GallonWater;
    DisplayName: "Water Jug - 1 gallon";
    Tooltip: "Large water jug. Useful for storing large quantities of water";
    AmountCrafted: 1;
    Ingredients:
        ( ItemID: DisinfectedWater; Required: 10; );
    Path: Fabricator/Survival/Water;
);
```

#### Example: Alternate recipe producing existing items

```
# This doesn't produce "WaterFromGallon" itself (AmountCrafted: 0).
# Instead it produces 10 DisinfectedWater via LinkedItemIDs. #
AliasRecipes:
(
    ItemID: WaterFromGallon;
    DisplayName: "Disinfected water (x10)";
    Tooltip: "Split the water jug into smaller containers";
    AmountCrafted: 0;
    LinkedItemIDs: DisinfectedWater, DisinfectedWater, DisinfectedWater,
                   DisinfectedWater, DisinfectedWater, DisinfectedWater,
                   DisinfectedWater, DisinfectedWater, DisinfectedWater,
                   DisinfectedWater;
    Ingredients:
        ( ItemID: GallonWater; Required: 1; );
    Path: Fabricator/Survival/Water;
);
```

#### Sprite Resolution Order

CC3 resolves AliasRecipe icon:
1. PNG in `Assets/` matching ItemID (e.g., `Assets/GallonWater.png`)
2. `SpriteItemID` field
3. First item in `LinkedItemIDs`
4. Fallback: black question-mark icon

---

### 4. CustomFood

**Purpose:** Create custom food/drink w/ nutritional values.

**When to use:** New edible item w/ specific food, water, health, oxygen effects.

**Inherits all fields from:** AliasRecipe (and AddedRecipe, ModifiedRecipe)

#### Additional Fields

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| FoodValue | int | Yes* | 0 | -200 to 200 | Food points on consumption |
| WaterValue | int | Yes* | 0 | -200 to 200 | Water points on consumption |
| OxygenValue | int | No | 0 | -200 to 200 | Oxygen restored |
| HealthValue | int | No | 0 | -200 to 200 | Health restored |
| DecayRateMod | float | No | 0.0 | 0.0+ | Decomposition speed (0=never, 1=normal cooked fish, 2=double) |
| FoodType | enum | No | None | -- | Visual model in inventory (see [FoodModel Enum](#foodmodel)) |
| UseDrinkSound | bool | No | auto | -- | YES=drink sound, NO=eat sound |

*At least one of FoodValue/WaterValue must be non-zero.

**Default differences:**
- `AmountCrafted` defaults 1
- `PdaGroup` defaults Survival
- `PdaCategory` defaults CookedFood

**Sound auto-detection:** If `UseDrinkSound` unset, CC3 uses drink sound when `WaterValue > FoodValue * 5`, else eat sound.

#### Example

```
CustomFoods:
(
    ItemID: Peeperburger;
    DisplayName: "Peeperburger";
    Tooltip: "Made from peepers and other items";
    AmountCrafted: 1;
    Ingredients:
        ( ItemID: Peeper;         Required: 2; ),
        ( ItemID: CoralChunk;     Required: 2; ),
        ( ItemID: CreepvinePiece; Required: 1; );
    Path: Fabricator/CustomFood3/Food;
    FoodValue: 20;
    WaterValue: 11;
    DecayRateMod: 0.5;
    ForceUnlockAtStart: YES;
);
```

---

## Container Types (Detailed)

### 5. CustomFabricator

**Purpose:** Create new crafting station player can build in base or Cyclops.

**When to use:** Enough custom recipes to warrant dedicated station separate from default Fabricator.

CustomFabricator = both item (must be built) and container (holds tabs/recipes).

**Inherits all fields from:** AliasRecipe (has DisplayName, Tooltip, Path, Ingredients, etc.)

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| Model | string | No | Fabricator | Visual model: `Fabricator`, `Workbench`, or `MoonPool` |
| ColorTint | floats | No | None | RGB color tint (3 values, 0.0-1.0 each) |
| AllowedInBase | bool | No | YES | Buildable in base? |
| AllowedInCyclops | bool | No | YES | Buildable in Cyclops? |
| CustomCraftingTabs | nested | No | [] | Tabs inside fabricator |
| AddedRecipes | nested | No | [] | Recipes in fabricator |
| AliasRecipes | nested | No | [] | Alias recipes in fabricator |
| CustomFoods | nested | No | [] | Food recipes in fabricator |
| MovedRecipes | nested | No | [] | Moved recipes in fabricator |

**Constraint:** `AllowedInBase` and `AllowedInCyclops` cannot both be `NO`.

#### Nesting Structure

CustomFabricator unique -- contains other block types nested inside. Fabricator owns its tabs and recipes:

```
CustomFabricators:
(
    ItemID: MyFab;
    DisplayName: "My Fabricator";
    Tooltip: "A custom crafting station";
    Model: Workbench;
    AllowedInBase: YES;
    AllowedInCyclops: YES;
    ColorTint: 1.0, 0.64, 0.0;
    Ingredients:
        ( ItemID: ComputerChip; Required: 1; ),
        ( ItemID: Titanium;     Required: 2; );
    ForceUnlockAtStart: YES;
    PdaGroup: InteriorModules;
    PdaCategory: InteriorModule;

    # Tabs inside this fabricator #
    CustomCraftingTabs:
    (
        TabID: ScienceTab;
        DisplayName: Science!;
        SpriteItemID: LabEquipment3;
        ParentTabPath: MyFab;
    );

    # Recipes inside this fabricator #
    AddedRecipes:
    (
        ItemID: LabEquipment1;
        AmountCrafted: 1;
        Ingredients:
            ( ItemID: Glass;    Required: 1; ),
            ( ItemID: Titanium; Required: 1; );
        Path: MyFab/ScienceTab;
    );
);
```

#### Ownership Diagram

```
CustomFabricator (ItemID: "MyFab")
|
+-- CustomCraftingTabs:
|   +-- Tab (TabID: "Weapons",  ParentTabPath: "MyFab")
|   +-- Tab (TabID: "Heavy",    ParentTabPath: "MyFab/Weapons")
|
+-- AddedRecipes:
|   +-- Recipe (ItemID: "LaserGun",  Path: "MyFab/Weapons")
|   +-- Recipe (ItemID: "RailGun",   Path: "MyFab/Weapons/Heavy")
|
+-- AliasRecipes:
|   +-- Recipe (ItemID: "CustomBlade", Path: "MyFab/Weapons")
|
+-- MovedRecipes:
    +-- Moved (ItemID: "Knife", NewPath: "MyFab/Weapons")
```

---

### 6. CustomCraftingTab

**Purpose:** Add organizational tabs to existing or custom fabricators.

**When to use:** Organize recipes into categories within fabricator's crafting tree.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| TabID | string | Yes | -- | Internal tab identifier |
| DisplayName | string | Yes | "" | Name in-game (quote if spaces) |
| SpriteItemID | string | No | None | Existing item's icon for tab |
| ParentTabPath | string | Yes | -- | Tab placement (see [Crafting Paths](#crafting-paths)) |

#### Ordering Rule

**Parent tabs must be defined before child tabs in file.** Read top-to-bottom. Tab B child of Tab A -- Tab A must appear first.

#### Example

```
CustomCraftingTabs:
(
    TabID: Doodads;
    DisplayName: "Doodads and Gizmos";
    SpriteItemID: AdvancedWiringKit;
    ParentTabPath: Fabricator/Personal;
),
(
    # This tab goes inside the one we just created above #
    TabID: ExtraSpecialItems;
    DisplayName: "Extra Special Items";
    SpriteItemID: PrecursorIonPowerCell;
    ParentTabPath: Fabricator/Personal/Doodads;
);
```

#### Tab Sprite Resolution

1. PNG in `Assets/` matching TabID (e.g., `Assets/Doodads.png`)
2. `SpriteItemID` field

---

## Utility Types (Detailed)

### 7. MovedRecipe

**Purpose:** Move, copy, or hide existing recipes in fabricator menus.

**When to use:**
- Move recipe to different tab/fabricator.
- Copy recipe to multiple locations.
- Hide recipe from current location.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | Item to move/copy/hide |
| OldPath | string | Conditional | None | Original fabricator tree location |
| NewPath | string | Conditional | None | Destination location |
| Copied | bool | No | NO | YES=copy (keep original), NO=move |
| Hidden | bool | No | NO | YES=hide from OldPath |

#### Constraints

- `Copied` and `Hidden` cannot both be `YES`.
- `Hidden: YES` -- `OldPath` required, `NewPath` ignored.
- `Copied: YES` -- `NewPath` required, `OldPath` optional.
- Neither -- both `OldPath` and `NewPath` required (move).

#### Examples

```
MovedRecipes:
(
    # Hide Titanium from its normal location #
    ItemID: Titanium;
    OldPath: Fabricator/Resources/BasicMaterials;
    Hidden: YES;
),
(
    # Move TitaniumIngot to a different tab #
    ItemID: TitaniumIngot;
    OldPath: Fabricator/Resources/BasicMaterials;
    NewPath: Fabricator/MoreIngots/packed/metallic;
),
(
    # Copy HeatBlade to also appear under Tools #
    ItemID: HeatBlade;
    NewPath: Fabricator/Personal/Tools;
    Copied: YES;
);
```

---

### 8. CustomSize

**Purpose:** Change inventory slot count for item.

#### Fields

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| ItemID | string | Yes | -- | -- | Item to resize |
| Width | int | Yes | 1 | 1-6 | Horizontal slots |
| Height | int | Yes | 1 | 1-6 | Vertical slots |

Values outside 1-6 clamped to 1.

#### Example

```
CustomSizes:
(
    ItemID: CreepvineSeedCluster;
    Width: 1;
    Height: 1;
),
(
    ItemID: CreepvinePiece;
    Width: 1;
    Height: 1;
);
```

---

### 9. CustomBioFuel

**Purpose:** Set bioreactor energy for item.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | Item to configure |
| Energy | float | Yes | 0.0 | Energy value (0=disable, higher=more) |

Energy 0 on normally-compatible item = disables it. Energy on normally-incompatible item = adds bioreactor compatibility.

#### Example

```
CustomBioFuels:
(
    ItemID: Oculus;
    Energy: 650;
),
(
    ItemID: NutrientBlock;
    Energy: 400;
),
(
    # Disable CreepvineSeedCluster as biofuel #
    ItemID: CreepvineSeedCluster;
    Energy: 0;
);
```

---

### 10. CustomFragmentCount

**Purpose:** Change fragments needed to unlock blueprint.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | Blueprint item |
| FragmentsToScan | int | Yes | -- | Fragments required |

#### Example

```
CustomFragmentCounts:
(
    ItemID: Seaglide;
    FragmentsToScan: 4;
),
(
    ItemID: Seamoth;
    FragmentsToScan: 6;
);
```

---

## Ingredients

Define materials a recipe requires. Each ingredient = block w/ two fields:

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| ItemID | string | Yes | -- | -- | Material needed |
| Required | int | Yes | 1 | 1-25 | Amount needed |

### Syntax

Single ingredient:

```
Ingredients: ( ItemID: Titanium; Required: 2; );
```

Multiple (comma between, semicolon after last):

```
Ingredients:
    ( ItemID: Titanium; Required: 2; ),
    ( ItemID: Gold;     Required: 1; ),
    ( ItemID: Silver;   Required: 1; );
```

### Compact vs. Expanded

Both valid:

```
# Compact #
Ingredients: ( ItemID: Titanium; Required: 2; ), ( ItemID: Gold; Required: 1; );

# Expanded #
Ingredients:
(
    ItemID: Titanium;
    Required: 2;
),
(
    ItemID: Gold;
    Required: 1;
);
```

---

## Crafting Paths

Paths tell CC3 where to place recipe/tab in fabricator menu tree.

### Format

```
FabricatorType/Tab1/Tab2/.../FinalTab
```

First segment = fabricator type (or custom fabricator ItemID).

### Built-in Fabricator Types

| Value | In-game Name |
|-------|-------------|
| Fabricator | Standard Fabricator |
| Workbench | Modification Station |
| Constructor | Mobile Vehicle Bay |
| CyclopsFabricator | Cyclops Fabricator |
| SeamothUpgrades | Vehicle Upgrade Console |
| MapRoom | Scanner Room |
| Centrifuge | Centrifuge (Below Zero only) |
| Rocket | Neptune Launch Platform |

### Examples

| Path | Meaning |
|------|---------|
| `Fabricator/Resources/BasicMaterials` | Standard Fabricator > Resources > Basic Materials |
| `Fabricator/Survival/Water` | Standard Fabricator > Survival > Water |
| `SeamothUpgrades` | Vehicle Upgrade Console (root) |
| `SeamothUpgrades/SpecialItems` | Vehicle Upgrade Console > Special Items |
| `MyFab/ScienceTab` | Custom fabricator "MyFab" > Science tab |

### Path Rules

- Always **absolute** (from fabricator root), even for recipes nested inside CustomFabricator.
- Fabricator type segment case-insensitive.
- All tabs in path must exist before recipe references them.

---

## Unlock System

Two fields control recipe availability:

### Unlocks

```
Unlocks: DepletedReactorRod, AdvancedWiringKit;
```

Player crafts/scans this item -> **all listed items** unlock. Batch unlock: craft one, unlock many.

### UnlockedBy

```
UnlockedBy: Seaglide, Seamoth;
```

Recipe unlocks when **any one** listed item scanned/unlocked. OR logic: scanning either unlocks this.

### ForceUnlockAtStart

```
ForceUnlockAtStart: YES;
```

Available from game start, regardless of scan/craft progression.

---

## Sprites and Icons

### For Recipes (AliasRecipe, CustomFood)

Icon resolution order:
1. PNG in `Assets/` matching ItemID (e.g., `Assets/GallonWater.png` for ItemID `GallonWater`)
2. `SpriteItemID` field (borrows another item's icon)
3. First item in `LinkedItemIDs`
4. Fallback: black question-mark icon

### For Tabs

1. PNG in `Assets/` matching TabID
2. `SpriteItemID` field

### Asset Folder Convention

Custom PNGs in `Assets/` subfolder next to recipe files. Name each PNG matching ItemID or TabID (case-insensitive).

```
MyMod/
  recipes.txt
  Assets/
    GallonWater.png
    Peeperburger.png
    ScienceTab.png
```

---

## Enum Reference

### FabricatorModel

| Value | Description |
|-------|-------------|
| Fabricator | Standard wall-mounted (default) |
| Workbench | Modification station (ground-placed) |
| MoonPool | Moon pool fabricator (Subnautica 1 only) |

### FoodModel

Visual appearance of food in inventory.

| Category | Values |
|----------|--------|
| None | None |
| Water | BigFilteredWater, DisinfectedWater, FilteredWater, WaterFiltrationSuitWater |
| Plants | BulboTreePiece, PurpleVegetable, CreepvinePiece, JellyPlant, KooshChunk, HangingFruit, Melon, NutrientBlock |
| Cooked fish | CookedPeeper, CookedHoleFish, CookedGarryFish, CookedReginald, CookedBladderfish, CookedHoverfish, CookedSpadefish, CookedBoomerang, CookedEyeye, CookedOculus, CookedHoopfish, CookedSpinefish, CookedLavaEyeye, CookedLavaBoomerang |
| Cured fish | CuredPeeper, CuredHoleFish, CuredGarryFish, CuredReginald, CuredBladderfish, CuredHoverfish, CuredSpadefish, CuredBoomerang, CuredEyeye, CuredOculus, CuredHoopfish, CuredSpinefish, CuredLavaEyeye, CuredLavaBoomerang |

### TechGroup (PDA encyclopedia groups)

| Value | Usage |
|-------|-------|
| Uncategorized | Default |
| Resources | Raw and crafted materials |
| Survival | Food, water, first aid |
| Personal | Equipment, tools |
| Machines | Deployables |
| InteriorModules | Base interior buildables |
| InteriorPieces | Base interior structure |
| ExteriorModules | Base exterior buildables |
| BasePieces | Base structural components |
| Cyclops | Cyclops upgrades |
| Constructor | Mobile Vehicle Bay items |
| Miscellaneous | Uncategorized buildables |
| VehicleUpgrades | Seamoth/Prawn upgrades |
| MapRoomUpgrades | Scanner Room upgrades |

### TechCategory (PDA encyclopedia subcategories)

| Value | Typical Parent Group |
|-------|---------------------|
| Misc | Fallback default |
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

---

## Processing Order

CC3 processes block types in strict global order. Tabs must exist before recipes reference them, fabricators before their tabs.

```
1. CustomFabricators      (create the stations first)
2. CustomCraftingTabs     (add tabs to stations)
3. AddedRecipes           (add recipes to tabs)
4. AliasRecipes           (add alias recipes)
5. ModifiedRecipes        (modify existing recipes)
6. CustomFoods            (add food recipes)
7. MovedRecipes           (move/copy/hide recipes -- last)
8. CustomFragmentCounts   (adjust scan requirements)
9. CustomSizes            (adjust inventory sizes)
10. CustomBioFuels        (adjust bioreactor values)
```

Order enforced across all files. Even if fabricator file named `zzz_last.txt`, fabricators still processed before recipes in `aaa_first.txt`.

---

## Common Mistakes

### Missing semicolons

Every value must end w/ `;`. Forgetting causes parser to run into next line, unexpected results.

```
# Wrong #
ItemID: Titanium
AmountCrafted: 1;

# Right #
ItemID: Titanium;
AmountCrafted: 1;
```

### Wrong entry separator

Commas between entries, semicolon after last:

```
# Wrong (semicolons between entries) #
ModifiedRecipes:
( ItemID: Knife; );
( ItemID: Welder; );

# Right #
ModifiedRecipes:
( ItemID: Knife; ),
( ItemID: Welder; );
```

### Referencing tabs before they exist

Recipe uses `Path: Fabricator/MyTab` but `MyTab` not defined yet -- recipe fails silently. Define tabs first.

### Mixing block types in one file

One top-level block type per file. No `AddedRecipes:` and `ModifiedRecipes:` in same file.

### Unquoted display names with spaces

Names/tooltips w/ spaces must be quoted:

```
# Wrong #
DisplayName: Water Jug;

# Right #
DisplayName: "Water Jug";
```

### Both Copied and Hidden set to YES

Mutually exclusive on MovedRecipe. Both = invalid.

### Required value outside 1-25

Ingredient `Required` must be 1-25. Outside range -- silently clamped or rejected.

### Forgetting Path on AddedRecipe/AliasRecipe

Unlike ModifiedRecipe (modifies in place), Added/Alias need `Path` to know fabricator placement. Without -- recipe exists but player can't find it.