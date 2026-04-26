# CraftGraph Node System Architecture

> Guide for anyone -- including GUI/node editor newcomers -- on how CraftGraph's visual node system works, its limits, and recurring bug patterns.

---

## Table of Contents

1. [What is a Node Editor?](#what-is-a-node-editor)
2. [Our Architecture: Class-Based Data-Driven](#our-architecture-class-based-data-driven)
3. [The Three Layers](#the-three-layers)
4. [How a Node Gets Created](#how-a-node-gets-created)
5. [Pin Types and What They Mean](#pin-types-and-what-they-mean)
6. [Why Not OOP Inheritance / ECS / Components?](#why-not-oop-inheritance--ecs--components)
7. [The Big Constraint: imnodes](#the-big-constraint-imnodes)
8. [The Connection Dispatch Problem](#the-connection-dispatch-problem)
9. [The Hierarchy Regression Bug](#the-hierarchy-regression-bug)
10. [What Would a Better System Look Like?](#what-would-a-better-system-look-like)

---

## What is a Node Editor?

Visual programming interface: **boxes (nodes)** connected by **wires (links)**. Each box has **pins** on left/right:

```
                    ┌──────────────────┐
   Input pins ──>   │                  │   <── Output pins
    (left side)     │   Recipe Node    │      (right side)
                    │                  │
                    └──────────────────┘
```

- **Output pins** (right): "I produce something." Ingredient node output = item itself.
- **Input pins** (left): "I need something." Recipe node inputs = required ingredients.
- **Links/wires**: Line from output to input pin = "this item used as ingredient in that recipe."

Flowchart where arrows show what feeds into what. In CraftGraph: visualizes Subnautica crafting recipes -- which items needed to build others, how they chain.

---

## Our Architecture: Class-Based Data-Driven

CraftGraph uses **single class** (`RecipeNode`) for every node. No inheritance tree of subclasses. Each `RecipeNode` carries `kind` field (`NodeKind` enum) telling system what CC3 concept node represents:

```
RecipeNode
├── kind: NodeKind.MODIFIED_RECIPE     (a recipe that changes an existing item)
├── kind: NodeKind.ADDED_RECIPE        (a brand-new recipe)
├── kind: NodeKind.ALIAS_RECIPE        (a cloned item with new name/icon)
├── kind: NodeKind.CUSTOM_FOOD         (a new food item)
├── kind: NodeKind.INGREDIENT          (a raw material or intermediate item)
├── kind: NodeKind.CUSTOM_FABRICATOR   (a crafting station, like the Fabricator)
├── kind: NodeKind.CUSTOM_CRAFTING_TAB (a tab inside a fabricator's menu)
├── kind: NodeKind.MOVED_RECIPE        (a recipe moved to a different location)
├── kind: NodeKind.CUSTOM_SIZE         (override an item's inventory size)
├── kind: NodeKind.CUSTOM_BIO_FUEL     (override an item's bioreactor energy)
└── kind: NodeKind.CUSTOM_FRAGMENT_COUNT (override fragment scan count)
```

`create()` method checks `kind` and decides **at creation time** which pins, labels, visuals to add. Not runtime composition -- **branching inside single method**.

### Why "data-driven"?

Node visual appearance determined entirely by data fields (`kind`, `ingredients`, `non_recipe`, `recipe`), not by subclass. One class. Data tells it what to become.

---

## The Three Layers

Three separated layers. Understanding these = understanding why node system works this way.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: DATA MODEL  (models.py)                                   │
│                                                                     │
│  ModifiedRecipe, AddedRecipe, AliasRecipe, CustomFood,             │
│  CustomFabricator, CraftingTab, MovedRecipe, ...                    │
│                                                                     │
│  Pure Python dataclasses. No GUI code. No DPG imports.              │
│  This is the SINGLE SOURCE OF TRUTH for all recipe data.            │
│  The parser reads files into these. The serializer writes them out.  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   │  references via .recipe / .non_recipe
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│  Layer 2: VISUAL NODES  (gui_nodes.py)                              │
│                                                                     │
│  RecipeNode dataclass: wraps a DPG node widget.                     │
│  NodeTheme: cached color themes per NodeKind.                       │
│  RecipeNodeEditor: manages all nodes, links, layout.                │
│                                                                     │
│  Creates DPG widgets (nodes, pins, links). Does NOT contain any     │
│  editing logic -- purely display.                                   │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
                                   │  composes (owns an editor instance)
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│  Layer 3: INTERACTIVE EDITOR  (gui_editor.py)                       │
│                                                                     │
│  InteractiveNodeEditor: handles drag-and-drop connections,          │
│  context menus, edit dialogs, undo/redo, save-to-disk.              │
│                                                                     │
│  GUI event --> resolve DPG IDs --> create EditCommand -->            │
│  execute via EditHistory --> model mutates --> visual rebuilds       │
└─────────────────────────────────────────────────────────────────────┘
```

### Edit flow

When user drags wire from one node to another:

1. DPG fires callback with two numeric attribute IDs (just numbers).
2. `InteractiveNodeEditor.on_link()` resolves those to actual `RecipeNode` objects + pin roles (ingredient name, `__empty__`, `__hierarchy__`, `__output__`).
3. Based on pin roles, decides command:
   - Ingredient addition? -> `AddIngredientCommand`
   - Hierarchy nesting? -> `NestTabInFabricatorCommand`
   - Link swap? -> `ChangeIngredientCommand`
4. Command mutates data model (`models.py` objects).
5. Visual **completely rebuilt** from scratch using updated model.

Key point: **every model change triggers full visual rebuild.** All nodes destroyed + recreated. All links destroyed + recreated. Not by choice -- how DPG/imnodes works.

---

## How a Node Gets Created

Inside `RecipeNode.create()`, step by step:

```python
def create(self, editor, pos, theme, texture_cache=None):
    with dpg.node(label=self.item_id, pos=pos, parent=editor) as node_id:

        # 1. OUTPUT PIN (right side) -- always present on every node
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Output):
            dpg.add_text("Modified Recipe (3)")  # type + ingredient count

        # 2. SPRITE THUMBNAIL (no pin) -- if an image exists
        if self.sprite_path:
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                dpg.add_image(texture, width=48, height=48)

        # 3. CONTENT -- depends on node kind
        if self.is_non_recipe:
            # Static info lines for non-recipe nodes (fabricators, tabs, etc.)
            for line in self._non_recipe_info_lines():
                with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
                    dpg.add_text(line)  # e.g. "Model: Fabricator"
        else:
            # Input pins for each ingredient (recipe/ingredient nodes)
            for ing_id, required in self.ingredients:
                with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input):
                    dpg.add_text(f"{ing_id} x{required}")

        # 4. HIERARCHY INPUT PIN (left side) -- for containment links
        #    Only on non-fabricator, non-ingredient nodes
        if not self.is_ingredient and self.kind != CUSTOM_FABRICATOR:
            with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input):
                dpg.add_text("Parent")  # dimmed gray label

        # 5. EMPTY INPUT PIN (left side) -- always present, drop target
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Input):
            dpg.add_text("+ drop ingredient")  # or item_id for non-recipes
```

**Everything decided inside this one method.** No "attach SpriteComponent" or "add HierarchyInputPlugin." All sequential if/else branching within single function.

---

## Pin Types and What They Mean

Every node can have up to 5 pin/element categories. What each means and how dispatch interprets connections:

| Pin                  | Side   | Role in Code     | What It Means                             | Who Has It               |
|----------------------|--------|------------------|-------------------------------------------|--------------------------|
| **Output**           | Right  | `__output__`     | "I am this item / I produce this"         | All nodes                |
| **Ingredient Input** | Left   | ingredient name  | "I need this specific ingredient"         | Recipe nodes only        |
| **Hierarchy Input**  | Left   | `__hierarchy__`  | "I belong to a parent (fab/tab)"          | Tabs, recipes, non-fabs  |
| **Empty Input**      | Left   | `__empty__`      | "Drop something new here"                 | All nodes                |
| **Static**           | None   | (not tracked)    | Display-only (sprites, info text)         | All nodes                |

When user drags wire, `on_link()` receives two attribute IDs, resolves each to `(RecipeNode, role)` pair, then uses roles to decide action:

```
source_role     target_role        Action
─────────────   ────────────────   ──────────────────────────────────────
__output__      __hierarchy__      Hierarchy connection (fab->tab, tab->recipe)
__output__      __empty__          Add new ingredient (if target is a recipe)
__output__      ingredient_name    Swap existing ingredient connection
__output__      __output__         Recipe-to-recipe dependency (output chaining)
```

No match = silently rejected. Source of most connection bugs: valid user actions falling through all dispatch cases.

---

## Why Not OOP Inheritance / ECS / Components?

### "Base Node class with subclass per type?"

OOP inheritance:

```
BaseNode
├── RecipeNode (adds ingredient input pins)
├── IngredientNode (minimal, just output)
├── FabricatorNode (adds info fields, no hierarchy input)
├── TabNode (adds hierarchy input)
├── MovedRecipeNode (adds path info)
└── ...
```

**Why not:** DPG uses immediate-mode pattern from ImGui. Widgets built by calling functions in sequence inside `with` block. "Object" = just integer ID from DPG. `RecipeNode` dataclass = our wrapper, not something DPG understands.

Subclasses would override `create()` for different pin layouts. Possible, but dispatch in `on_link()` still needs to know subclass to decide command. Same `if isinstance(node, FabricatorNode)` checks as current `if node.kind == NodeKind.CUSTOM_FABRICATOR`. Hierarchy adds ceremony without reducing complexity.

### "Entity-Component-System (ECS)?"

ECS pattern (Unity DOTS, Bevy):
- **Entities** = just IDs (no data, no behavior)
- **Components** = pure data bags (Position, Sprite, InputPins)
- **Systems** = functions processing entities with specific component combos

**Why not:** DPG is not ECS. Node editor expects all attributes (pins) declared at creation time inside `with` block. Can't "query all nodes with HierarchyInput component" -- DPG lacks that concept. Would build ECS abstraction on non-ECS toolkit, adding complexity without performance benefits (cache locality, parallelism over 10,000+ entities).

### "Template/preset system -- one base, compose features per type?"

Closest to what CraftGraph does, without formal abstraction. `RecipeNode.create()` IS the "template" -- base skeleton conditionally adding features based on `kind`. Branching IS composition, expressed as if/else instead of pluggable components.

**Real answer:** Constraint is DPG/imnodes, not Python architecture. Even with beautiful component system, still must flatten everything into linear sequence of `dpg.node_attribute()` calls inside single `with dpg.node()` block. GUI toolkit doesn't support post-creation node modification. Formal component system adds abstraction without changing DPG-level behavior.

---

## The Big Constraint: imnodes

Everything about this design traces to one fundamental limitation of underlying C++ library.

### What is imnodes?

Dear PyGui's node editor = Python wrapper around **imnodes**, C++ library for ImGui providing visual node-and-wire editing surface. DPG exposes via `dpg.node_editor()`, `dpg.node()`, `dpg.node_attribute()`, `dpg.add_node_link()`.

### What imnodes cannot do

1. **Cannot add/remove pins after node creation.** Once `with dpg.node()` block exits, attribute list frozen. Adding new ingredient pin = destroy ENTIRE node editor + rebuild ALL nodes from scratch.

2. **Cannot modify pin type after creation.** `mvNode_Attr_Input` stays input forever. No conversion to output or static.

3. **Widget IDs are transient.** Every rebuild = new integer IDs from DPG. Old ID references break. Why we maintain `_attr_to_node` reverse lookup repopulated on every rebuild.

4. **Links reference pins by ID.** Pin IDs change on rebuild = all links invalid. Links must also be recreated from scratch.

### In practice

**Every model change = full visual teardown + rebuild.** No "add one pin to existing node." Cycle:

```
User drags a wire
  -> on_link() fires
  -> command created and executed
  -> command mutates the data model (add an ingredient)
  -> refresh_visual() called
  -> save all current node positions
  -> destroy entire DPG node editor widget
  -> rebuild every node from the updated model
  -> reapply saved positions
  -> recreate all links between nodes
  -> re-register all attribute-to-node mappings
```

Why "dynamic input slots" (`__empty__` pin spawning new pins on connect) requires full rebuild. Can't insert new pin into existing node. Destroy everything, recreate with new pin included.

### Why "swap" optimization exists

Full rebuild expensive with hundreds of nodes (reference files produce 894). `_swap_link()` = shortcut for one case: replacing ingredient connection. Instead of full rebuild:
1. Mutates model silently (no rebuild callback)
2. Manually severs old DPG link
3. Relabels existing input pin text
4. Wires new link to same pin

Avoids full rebuild for common wire re-routing. Only works because PIN STILL EXISTS -- just changing which output it connects to. Not adding/removing pins (that needs full rebuild).

---

## The Connection Dispatch Problem

Root cause of most connection-related bugs, including hierarchy regression.

### The Problem

User drags wire between pins -> DPG fires `on_link(sender, (attr1, attr2))`. We receive **two integer IDs** and must figure out:

1. Which node each attribute belongs to?
2. What role each attribute plays (output, ingredient input, hierarchy input, empty slot)?
3. User's intent (add ingredient, create hierarchy link, swap existing)?
4. Which command to create?

**Classification problem** with many combos:

```
Combinations = (roles of attr1) x (roles of attr2) x (node kinds of both)
             = 4 roles x 4 roles x 11 kinds x 11 kinds
             = ~1,936 theoretical combinations
```

~10-15 handled explicitly. Everything else silently rejected. Each new node kind or pin type grows combinations; chance of missing valid case increases.

### How on_link() dispatches (simplified)

```
on_link(attr1, attr2)
│
├── Is either role "__hierarchy__"?
│   └── YES: Try _try_hierarchy_link()
│            If it returns a command, execute it.
│            If it returns None, silently reject.
│            RETURN (never falls through to ingredient logic)
│
├── Is source_role "__output__" and target_role not "__output__"?
│   └── YES: Standard output-to-input connection.
│            Resolve ingredient ID and target recipe.
│
├── Is target_role "__output__" and source_role not "__output__"?
│   └── YES: Reverse direction (user dragged input to output).
│
├── Are BOTH roles "__output__"?
│   └── YES: Recipe-to-recipe chaining.
│
├── Could we resolve a target_recipe and ingredient_id?
│   ├── NO:  Last-resort: try _try_hierarchy_link() again.
│   │        If still None, silently reject. RETURN.
│   └── YES: Continue...
│
├── Is target_role "__empty__"?
│   └── YES: AddIngredientCommand (full rebuild)
│
├── Is there a replaced ingredient to swap?
│   └── YES: _swap_link() (incremental, no rebuild)
│
└── Fallback: AddIngredientCommand (full rebuild)
```

Each new pin type (`__output__`, `__empty__`, `__hierarchy__`, named ingredient pins) adds branch to dispatch tree. Hierarchy dispatch (Step 11i) introduced early-return path taking priority over ingredient dispatch. Valid connection patterns falling through hierarchy check but not matching ingredient patterns get silently dropped.

---

## The Hierarchy Regression Bug

### What broke

After Step 11i added hierarchy pin system (`__hierarchy__` input for parent-child containment), drag-and-drop from fabricators/tabs to other tabs stopped working. Connection silently rejected.

### Root cause

Issue in `on_link()` hierarchy dispatch. User drags from fabricator output to tab hierarchy input:

```
source: (fabricator_node, "__output__")
target: (tab_node, "__hierarchy__")

on_link() sees target_role == "__hierarchy__"
  -> calls _try_hierarchy_link(fab_node, tab_node, "__output__", "__hierarchy__")
  -> _try_hierarchy_link checks:
       source_role != "__output__" ? NO  (pass)
       target_role not in ("__empty__", "__hierarchy__") ? NO  (pass)
  -> parent = fab_node, child = tab_node
  -> checks parsed_file.block_type == CUSTOM_FABRICATORS
  -> calls _try_fabricator_hierarchy(fab_node, tab_node)
```

`_try_fabricator_hierarchy()` checks conditions using `isinstance()` on `non_recipe` field. Likely failure points:

1. **Nested-tab key collision:** Tabs from `_spawn_nested_fab_contents()` use different node key format (`custom_crafting_tab::TabId::fab::FabId`) than top-level tabs (`custom_crafting_tab::TabId`). Connected tab node's `non_recipe` may point to different `CraftingTab` instance than one in top-level `parsed_file.crafting_tabs`.

2. **Output-to-empty fallback:** User drags tab output to fabricator `__empty__` pin (reverse of "correct" direction) -> dispatch treats tab as parent, fabricator as child. `_try_fabricator_hierarchy()` has no "Tab parent, Fabricator child" case -- fabricators don't nest inside tabs. Returns `None`. But user INTENT was nesting tab inside fabricator, just wrong drag direction.

3. **Early-return trap:** When `target_role == "__hierarchy__"`, code always returns after hierarchy dispatch, even if it returned `None`. No fallback to ingredient logic, no error message, no log. Connection vanishes.

### Why this bug class recurs

Each new pin type or connection semantic adds branches to dispatch tree originally designed for two cases (output-to-input ingredient connections). Tree lacks exhaustive match -- no Rust `match` forcing all-case handling. Unhandled combos fall through silently.

Fix for any individual case = small (add condition to dispatch), but underlying problem is architectural: dispatch tree grows linearly per feature while combination space grows quadratically.

---

## What Would a Better System Look Like?

Starting from scratch (or if DPG/imnodes supported it):

### Option A: Component-based nodes with custom renderer

Instead of DPG node editor, render nodes via DPG draw list API. Full control over:
- Adding/removing pins dynamically (no rebuild)
- Custom hit-testing for connections
- Component-based node construction

But means reimplementing: node rendering, pin rendering, link rendering, link dragging, minimap, scrolling, selection, multi-select, keyboard navigation... writing own node editor from scratch. Months of work for marginal benefit.

### Option B: Explicit connection type registration

Instead of dispatch tree, define all valid connection types as table:

```python
VALID_CONNECTIONS = [
    ConnectionRule(
        source_kind=NodeKind.CUSTOM_FABRICATOR,
        target_pin="__hierarchy__",
        target_kind=NodeKind.CUSTOM_CRAFTING_TAB,
        command_factory=lambda src, tgt: NestTabInFabricatorCommand(...),
    ),
    ConnectionRule(
        source_kind=NodeKind.CUSTOM_CRAFTING_TAB,
        target_pin="__hierarchy__",
        target_kind={any recipe kind},
        command_factory=lambda src, tgt: NestRecipeUnderTabCommand(...),
    ),
    # ... etc
]
```

Dispatch becomes exhaustive, self-documenting, testable. New connection types added as data, not new if/else branches. Trivial to add "reverse direction" support (both directions as separate rules).

### Option C: Accept current design, improve error reporting

Pragmatic path. Current architecture works. Dispatch tree complex but manageable. Key improvement: visible feedback on connection rejection (toast saying "Cannot connect X to Y: reason") instead of silent rejection. Easier debugging + clear user feedback for invalid connections.

**CraftGraph currently follows hybrid B + C** -- dispatch moving toward structured pattern (separate methods per hierarchy type), Step 11j adds user-facing validation warnings.

---

## Summary

| Question                          | Answer                                                    |
|-----------------------------------|-----------------------------------------------------------|
| What pattern do the nodes use?    | Single class + kind enum (data-driven branching)          |
| Why not subclasses?               | Same dispatch complexity, more ceremony                   |
| Why not ECS?                      | DPG is not an ECS toolkit; overhead without benefit       |
| Why not composable components?    | imnodes requires all pins declared at creation time       |
| Why full rebuild on every edit?   | imnodes cannot add/remove pins after node creation        |
| Why do connection bugs happen?    | Dispatch tree doesn't cover all role x kind combinations  |
| What's the hierarchy regression?  | New pin type added dispatch paths that don't cover all valid user actions |
| Can we fix the architecture?      | Not without replacing imnodes or building a custom renderer |

System is pragmatic: works within DPG constraints, keeps data model fully decoupled from GUI. Cost = complex dispatch layer growing with each feature. Mitigation = better error reporting (Step 11j) + structured dispatch (connection rule tables).
