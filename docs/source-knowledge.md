# CustomCraft3 and EasyMarkup -- Complete Reference

This document explains everything you need to know about writing recipe files for
the CustomCraft3 (CC3) Subnautica mod. It covers the EasyMarkup syntax, all 10
block types, their fields, validation rules, and practical examples.

Whether you are a player tweaking recipes, a modder building a full fabricator, or
a developer working on CraftGraph, this guide has you covered.

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

CustomCraft3 (CC3) is a Subnautica mod by MrPurple6411 that lets you customize
crafting recipes without writing any code. You create plain text files using a
format called EasyMarkup, drop them in the mod folder, and CC3 reads them when
the game starts.

You can:
- Change ingredients for existing recipes
- Add entirely new craftable items
- Create custom fabricators with their own tabs and recipes
- Adjust inventory sizes, bioreactor energy, and fragment scan counts
- Move or hide recipes from fabricator menus

---

## What is EasyMarkup?

EasyMarkup is the text format CC3 uses. Think of it as a simpler alternative to
JSON or XML, designed specifically for modders who may not be programmers. It uses
a small set of special characters to structure data.

---

## EasyMarkup Syntax

### Special Characters

| Character | Name | Purpose |
|-----------|------|---------|
| `:` | Colon | Separates a key from its value |
| `;` | Semicolon | Ends a value |
| `(` `)` | Parentheses | Wraps a block (group of key-value pairs) |
| `,` | Comma | Separates items in a list or between entries |
| `#` | Hash | Opens and closes a comment |
| `"` | Double quote | Wraps a string that contains spaces |
| `\` | Backslash | Escapes a special character |

### Key-Value Pairs

The basic building block. A key, a colon, a value, and a semicolon:

```
ItemID: Titanium;
```

Whitespace is flexible. These are all identical:

```
ItemID:Titanium;
ItemID: Titanium;
ItemID:   Titanium  ;
```

### Blocks (Complex Values)

When a value contains multiple key-value pairs, wrap them in parentheses:

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

Comma-separated values on the same key:

```
LinkedItemIDs: Titanium, Gold, Silver;
```

Lists of blocks use commas between entries and a semicolon after the last one:

```
Ingredients:
    ( ItemID: Titanium; Required: 2; ),
    ( ItemID: Gold;     Required: 1; );
```

### Comments

Wrap comment text between `#` signs. Comments can appear anywhere:

```
# This is a comment #
ItemID: Titanium; # Inline comment #
```

Both `#` signs are required. A comment opened with `#` must be closed with `#`.

### Quoted Strings

Values that contain spaces must be wrapped in double quotes:

```
DisplayName: "Water Jug - 1 gallon";
```

Single-word values do not need quotes:

```
DisplayName: Titanium;
```

### Escaping

If a value contains a special character and is not quoted, escape it with `\`:

```
SomeValue: Price\: 100;
```

Inside quoted strings, no escaping is needed.

### Case Sensitivity

- **Keys** are case-insensitive: `ItemID`, `itemid`, and `ITEMID` all work.
- **TechType IDs** (item names) are case-insensitive: `Titanium` = `titanium`.
- **Boolean values** are case-insensitive: `YES`, `yes`, `True`, `true` all work.
- **Enum values** (like TechGroup, FoodModel) are case-insensitive.

### Booleans

CC3 recognizes these boolean values:

| True values | False values |
|-------------|-------------|
| `YES` | `NO` |
| `TRUE` | `FALSE` |

Booleans are always written as `YES` or `NO` in output.

---

## File Rules

### One Block Type Per File

Each `.txt` file must contain exactly **one** primary block type. The first
non-comment content in the file determines the type.

Valid: A file containing only `ModifiedRecipes:` entries.
Invalid: A file with both `ModifiedRecipes:` and `AddedRecipes:` at the top level.

**Exception:** A `CustomFabricator` block can contain nested `CustomCraftingTabs`,
`AddedRecipes`, `AliasRecipes`, `MovedRecipes`, and `CustomFoods` inside it.
This nesting is part of the fabricator definition, not separate top-level blocks.

### Multiple Entries Per File

You can have multiple entries of the same type in one file. Separate them with
commas, and end the last one with a semicolon:

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

Files should be UTF-8. CC3 handles Windows BOM (byte-order mark) gracefully.

### Cross-File References

Items defined in one file can be referenced from another file in the same mod
folder. CC3 processes the entire folder as a unit. For example, a recipe in
`recipes.txt` can reference a custom tab defined in `tabs.txt`.

---

## Block Types Overview

CC3 supports 10 block types, organized into three categories:

### Recipe Types (inheritance chain)

These share fields through inheritance. Each type adds fields on top of its parent.

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
| CustomFabricator | Create a new crafting station |
| CustomCraftingTab | Add tabs to existing or custom fabricators |

### Utility Types

| Type | Purpose |
|------|---------|
| MovedRecipe | Move, copy, or hide recipes in fabricator menus |
| CustomSize | Change inventory slot dimensions |
| CustomBioFuel | Set bioreactor energy values |
| CustomFragmentCount | Change how many fragments unlock a blueprint |

---

## Recipe Types (Detailed)

### 1. ModifiedRecipe

**Purpose:** Change the ingredients or unlock conditions of recipes that already
exist in the base game.

**When to use:** You want to make an existing item cheaper/more expensive to
craft, or add unlock conditions to it.

**Important:** This only works with items that are already craftable in the
unmodded game. For items that are not normally craftable, use AddedRecipe instead.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | The in-game item to modify (TechType ID) |
| AmountCrafted | int | No | 1 | How many items one craft produces |
| Ingredients | list | No | [] | What materials are needed (see [Ingredients](#ingredients)) |
| LinkedItemIDs | CSV | No | [] | Extra items produced alongside the main item |
| Unlocks | CSV | No | [] | Items unlocked when this recipe is crafted |
| UnlockedBy | CSV | No | [] | Items that unlock this recipe when scanned |
| ForceUnlockAtStart | bool | No | NO | Whether the recipe is available from game start |

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

**Purpose:** Add a new crafting recipe for an existing in-game item that is not
normally craftable.

**When to use:** You want to make a non-craftable item craftable (like adding a
recipe for Depleted Reactor Rods), or add an alternative recipe for an existing item.

**Inherits all fields from:** ModifiedRecipe

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| Path | string | Yes | -- | Where to place the recipe in a fabricator (see [Crafting Paths](#crafting-paths)) |
| PdaGroup | enum | No | Uncategorized | PDA encyclopedia group (see [Enum Reference](#enum-reference)) |
| PdaCategory | enum | No | Misc | PDA encyclopedia category |

**Note:** If you set PdaGroup, you must also set PdaCategory (and vice versa).

**Default difference:** `ForceUnlockAtStart` defaults to `YES` for AddedRecipe
(unlike `NO` for ModifiedRecipe).

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

**Purpose:** Create a completely new item with a custom name and description.
Can also create alternate recipes that produce existing items.

**When to use:**
- You want to create a brand-new item that does not exist in the base game.
- You want an alternate recipe that produces an existing item (using LinkedItemIDs
  with AmountCrafted set to 0).

**Inherits all fields from:** AddedRecipe (and therefore ModifiedRecipe)

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| DisplayName | string | Yes | "" | The name shown in-game (use quotes if it contains spaces) |
| Tooltip | string | Yes | "" | Description text shown below the name (use quotes for spaces) |
| FunctionalID | string | No | None | Clone the behavior of an existing item. Without this, the custom item has no function. |
| SpriteItemID | string | No | None | Use the icon of an existing item as this item's icon |

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

CC3 resolves the icon for an AliasRecipe in this order:
1. A PNG file in the `Assets/` folder matching the ItemID (e.g., `Assets/GallonWater.png`)
2. The `SpriteItemID` field (use another item's icon)
3. The first item in `LinkedItemIDs`
4. Fallback: black question-mark icon

---

### 4. CustomFood

**Purpose:** Create a custom food or drink item with nutritional values.

**When to use:** You want to create a new edible item with specific food, water,
health, or oxygen effects.

**Inherits all fields from:** AliasRecipe (and therefore AddedRecipe and ModifiedRecipe)

#### Additional Fields

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| FoodValue | int | Yes* | 0 | -200 to 200 | Food points restored on consumption |
| WaterValue | int | Yes* | 0 | -200 to 200 | Water points restored on consumption |
| OxygenValue | int | No | 0 | -200 to 200 | Oxygen restored (useful for underwater items) |
| HealthValue | int | No | 0 | -200 to 200 | Health points restored |
| DecayRateMod | float | No | 0.0 | 0.0+ | Decomposition speed (0 = never, 1 = normal cooked fish rate, 2 = double) |
| FoodType | enum | No | None | -- | Visual model in inventory (see [FoodModel Enum](#foodmodel)) |
| UseDrinkSound | bool | No | auto | -- | YES = drinking sound, NO = eating sound |

*At least one of FoodValue or WaterValue must be non-zero.

**Default differences:**
- `AmountCrafted` defaults to 1
- `PdaGroup` defaults to Survival
- `PdaCategory` defaults to CookedFood

**Sound auto-detection:** If `UseDrinkSound` is not set, CC3 uses the drinking
sound when `WaterValue > FoodValue * 5`, otherwise the eating sound.

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

**Purpose:** Create an entirely new crafting station that the player can build
and place in their base or Cyclops.

**When to use:** You have enough custom recipes to warrant their own dedicated
crafting station, separate from the default Fabricator.

A CustomFabricator is both an item (it needs to be built) and a container (it
holds tabs and recipes inside it).

**Inherits all fields from:** AliasRecipe (so it has DisplayName, Tooltip, Path,
Ingredients, etc.)

#### Additional Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| Model | string | No | Fabricator | Visual model: `Fabricator`, `Workbench`, or `MoonPool` |
| ColorTint | floats | No | None | RGB color tint (3 values, each 0.0 to 1.0) |
| AllowedInBase | bool | No | YES | Can the player build this in a base? |
| AllowedInCyclops | bool | No | YES | Can the player build this in a Cyclops? |
| CustomCraftingTabs | nested | No | [] | Tabs inside this fabricator |
| AddedRecipes | nested | No | [] | Recipes added to this fabricator |
| AliasRecipes | nested | No | [] | Alias recipes in this fabricator |
| CustomFoods | nested | No | [] | Food recipes in this fabricator |
| MovedRecipes | nested | No | [] | Moved recipes in this fabricator |

**Constraint:** Both `AllowedInBase` and `AllowedInCyclops` cannot both be `NO`.

#### Nesting Structure

A CustomFabricator is unique because it contains other block types nested inside
its definition. The fabricator owns its tabs and recipes:

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

**Purpose:** Add new organizational tabs to existing fabricators (or custom ones).

**When to use:** You want to organize your recipes into categories within a
fabricator's crafting tree.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| TabID | string | Yes | -- | Internal identifier for the tab |
| DisplayName | string | Yes | "" | Name shown in-game (quote if it has spaces) |
| SpriteItemID | string | No | None | Use an existing item's icon for the tab |
| ParentTabPath | string | Yes | -- | Where to place the tab (see [Crafting Paths](#crafting-paths)) |

#### Ordering Rule

**Parent tabs must be defined before child tabs in the file.** The file is read
top to bottom. If tab B is a child of tab A, tab A must appear first.

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

1. A PNG file in `Assets/` matching the TabID (e.g., `Assets/Doodads.png`)
2. The `SpriteItemID` field

---

## Utility Types (Detailed)

### 7. MovedRecipe

**Purpose:** Move, copy, or hide existing recipes in fabricator menus.

**When to use:**
- Move a recipe to a different tab or fabricator.
- Copy a recipe so it appears in multiple locations.
- Hide a recipe from its current location.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | The item to move/copy/hide |
| OldPath | string | Conditional | None | Original location in the fabricator tree |
| NewPath | string | Conditional | None | Destination location |
| Copied | bool | No | NO | YES = copy (keep original), NO = move |
| Hidden | bool | No | NO | YES = hide from OldPath |

#### Constraints

- `Copied` and `Hidden` cannot both be `YES`.
- If `Hidden: YES` -- `OldPath` is required, `NewPath` is ignored.
- If `Copied: YES` -- `NewPath` is required, `OldPath` is optional.
- If neither -- both `OldPath` and `NewPath` are required (move operation).

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

**Purpose:** Change how many inventory slots an item takes up.

#### Fields

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| ItemID | string | Yes | -- | -- | Item to resize |
| Width | int | Yes | 1 | 1-6 | Horizontal slots |
| Height | int | Yes | 1 | 1-6 | Vertical slots |

Values outside 1-6 are clamped to 1.

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

**Purpose:** Set how much energy an item provides in a Bioreactor.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | Item to configure |
| Energy | float | Yes | 0.0 | Energy value (0 = disable, higher = more energy) |

Setting Energy to 0 for an item that normally works in a bioreactor effectively
disables it. Setting Energy on an item that normally cannot go in a bioreactor
adds bioreactor compatibility.

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

**Purpose:** Change how many fragments the player must scan to unlock a blueprint.

#### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| ItemID | string | Yes | -- | Blueprint item |
| FragmentsToScan | int | Yes | -- | Number of fragments required |

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

Ingredients define what materials a recipe requires. Each ingredient is a block
with two fields:

| Field | Type | Required | Default | Range | Description |
|-------|------|----------|---------|-------|-------------|
| ItemID | string | Yes | -- | -- | The material needed |
| Required | int | Yes | 1 | 1-25 | How many of that material |

### Syntax

Single ingredient:

```
Ingredients: ( ItemID: Titanium; Required: 2; );
```

Multiple ingredients (comma between entries, semicolon after last):

```
Ingredients:
    ( ItemID: Titanium; Required: 2; ),
    ( ItemID: Gold;     Required: 1; ),
    ( ItemID: Silver;   Required: 1; );
```

### Compact vs. Expanded

Both forms are valid:

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

Paths tell CC3 where to place a recipe or tab in a fabricator's menu tree.

### Format

```
FabricatorType/Tab1/Tab2/.../FinalTab
```

The first segment is always the fabricator type (or custom fabricator ItemID).

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
| `SeamothUpgrades` | Vehicle Upgrade Console (root level) |
| `SeamothUpgrades/SpecialItems` | Vehicle Upgrade Console > Special Items tab |
| `MyFab/ScienceTab` | Custom fabricator "MyFab" > Science tab |

### Path Rules

- Paths are always **absolute** (start from the fabricator root), even for
  recipes nested inside a CustomFabricator block.
- The fabricator type segment is case-insensitive.
- All tabs in the path must exist before a recipe references them.

---

## Unlock System

CC3 provides two fields for controlling when recipes become available:

### Unlocks

```
Unlocks: DepletedReactorRod, AdvancedWiringKit;
```

When the player crafts (or scans) this item, **all listed items** are unlocked.
This is a batch unlock: craft one thing, unlock many.

### UnlockedBy

```
UnlockedBy: Seaglide, Seamoth;
```

This recipe unlocks when **any one** of the listed items is scanned or unlocked.
This is OR logic: scanning either a Seaglide or a Seamoth would unlock this recipe.

### ForceUnlockAtStart

```
ForceUnlockAtStart: YES;
```

Makes the recipe available from the start of the game, regardless of scanning
or crafting progression.

---

## Sprites and Icons

### For Recipes (AliasRecipe, CustomFood)

CC3 looks for an icon in this order:
1. A PNG file in the `Assets/` folder matching the ItemID
   (e.g., `Assets/GallonWater.png` for ItemID `GallonWater`)
2. The `SpriteItemID` field (borrows another item's icon)
3. The first item listed in `LinkedItemIDs`
4. Fallback: black question-mark icon

### For Tabs

1. A PNG file in `Assets/` matching the TabID
2. The `SpriteItemID` field

### Asset Folder Convention

Place your custom PNG icons in an `Assets/` subfolder next to your recipe files.
Name each PNG to match the ItemID or TabID (case-insensitive).

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
| Fabricator | Standard wall-mounted fabricator (default) |
| Workbench | Modification station (ground-placed) |
| MoonPool | Moon pool fabricator (Subnautica 1 only) |

### FoodModel

Controls the visual appearance of food items in the inventory.

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

CC3 processes block types in a strict global order. This matters because tabs
must exist before recipes can reference them, and fabricators must exist before
their tabs are created.

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

This order is enforced across all files in the mod folder. Even if your
fabricator file is named `zzz_last.txt`, fabricators are still processed
before recipes in `aaa_first.txt`.

---

## Common Mistakes

### Missing semicolons

Every value must end with `;`. Forgetting it causes the parser to run into the
next line and produce unexpected results.

```
# Wrong #
ItemID: Titanium
AmountCrafted: 1;

# Right #
ItemID: Titanium;
AmountCrafted: 1;
```

### Wrong entry separator

Use commas between entries and a semicolon after the last one:

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

If your recipe uses `Path: Fabricator/MyTab` but `MyTab` is not defined yet
(either in a CustomCraftingTabs block or a CustomFabricator), the recipe will
fail silently. Define tabs first.

### Mixing block types in one file

Each file can only have one top-level block type. Do not put `AddedRecipes:`
and `ModifiedRecipes:` in the same file.

### Unquoted display names with spaces

Display names and tooltips with spaces must be quoted:

```
# Wrong #
DisplayName: Water Jug;

# Right #
DisplayName: "Water Jug";
```

### Both Copied and Hidden set to YES

These are mutually exclusive on MovedRecipe. Setting both is invalid.

### Required value outside 1-25

Ingredient `Required` values must be between 1 and 25. Values outside this
range may be silently clamped or rejected.

### Forgetting Path on AddedRecipe/AliasRecipe

Unlike ModifiedRecipe (which modifies an existing recipe in place), Added and
Alias recipes need a `Path` field to know where in the fabricator to appear.
Without it, the recipe exists but cannot be found by the player.
