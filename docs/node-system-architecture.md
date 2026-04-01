# CraftGraph Node System Architecture

> A guide for anyone -- including people unfamiliar with GUI programming or
> node editors -- explaining how CraftGraph's visual node system works, what
> limits it, and why certain bugs keep happening.

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

A node editor is a visual programming interface where concepts are represented as
**boxes (nodes)** connected by **wires (links)**. Each box has **pins** on its left
and right sides:

```
                    ┌──────────────────┐
   Input pins ──>   │                  │   <── Output pins
    (left side)     │   Recipe Node    │      (right side)
                    │                  │
                    └──────────────────┘
```

- **Output pins** (right): "I produce something." An ingredient node's output
  represents the item itself.
- **Input pins** (left): "I need something." A recipe node's input pins represent
  the ingredients it requires.
- **Links/wires**: A line drawn from an output pin to an input pin, meaning
  "this item is used as an ingredient in that recipe."

Think of it like a flowchart where arrows show what feeds into what. In
CraftGraph, this visualizes Subnautica crafting recipes: which items are needed
to build which other items, and how they all chain together.

---

## Our Architecture: Class-Based Data-Driven

CraftGraph uses a **single class** (`RecipeNode`) to represent every kind of
node in the editor. There is no inheritance tree of node subclasses. Instead,
each `RecipeNode` carries a `kind` field (a `NodeKind` enum) that tells the
system what type of CC3 concept the node represents:

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

When a `RecipeNode` is created, its `create()` method looks at `kind` and
decides **at creation time** which pins, labels, and visual elements to add.
This is not runtime composition -- it's **branching inside a single method**.

### Why "data-driven"?

Because the node's visual appearance is determined entirely by data fields
(`kind`, `ingredients`, `non_recipe`, `recipe`), not by which subclass it is.
There is one class. The data tells it what to become.

---

## The Three Layers

CraftGraph separates concerns into three layers. Understanding these layers is
critical to understanding why the node system works the way it does.

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

### The flow of an edit

When a user drags a wire from one node to another:

1. DPG fires a callback with two numeric attribute IDs (just numbers).
2. `InteractiveNodeEditor.on_link()` resolves those numbers to actual
   `RecipeNode` objects and their pin roles (ingredient name, `__empty__`,
   `__hierarchy__`, `__output__`).
3. Based on the pin roles, it decides what command to create:
   - Ingredient addition? -> `AddIngredientCommand`
   - Hierarchy nesting? -> `NestTabInFabricatorCommand`
   - Link swap? -> `ChangeIngredientCommand`
4. The command mutates the data model (`models.py` objects).
5. The visual is **completely rebuilt** from scratch using the updated model.

That last point is the key. **Every model change triggers a full visual
rebuild.** Every node is destroyed and recreated. Every link is destroyed and
recreated. This is not by choice -- it's because of how DPG/imnodes works.

---

## How a Node Gets Created

Here is what happens inside `RecipeNode.create()`, step by step:

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

Notice: **everything is decided inside this one method.** There's no "attach a
SpriteComponent" or "add a HierarchyInputPlugin." It's all sequential
if/else branching within a single function.

---

## Pin Types and What They Mean

Every node can have up to 5 categories of pins/elements. Here is what each
one means and how the dispatch system interprets connections to them:

| Pin                  | Side   | Role in Code     | What It Means                             | Who Has It               |
|----------------------|--------|------------------|-------------------------------------------|--------------------------|
| **Output**           | Right  | `__output__`     | "I am this item / I produce this"         | All nodes                |
| **Ingredient Input** | Left   | ingredient name  | "I need this specific ingredient"         | Recipe nodes only        |
| **Hierarchy Input**  | Left   | `__hierarchy__`  | "I belong to a parent (fab/tab)"          | Tabs, recipes, non-fabs  |
| **Empty Input**      | Left   | `__empty__`      | "Drop something new here"                 | All nodes                |
| **Static**           | None   | (not tracked)    | Display-only (sprites, info text)         | All nodes                |

When a user drags a wire, `on_link()` receives two attribute IDs. It resolves
each to a `(RecipeNode, role)` pair. Then it uses the roles to decide what to
do:

```
source_role     target_role        Action
─────────────   ────────────────   ──────────────────────────────────────
__output__      __hierarchy__      Hierarchy connection (fab->tab, tab->recipe)
__output__      __empty__          Add new ingredient (if target is a recipe)
__output__      ingredient_name    Swap existing ingredient connection
__output__      __output__         Recipe-to-recipe dependency (output chaining)
```

If none of these patterns match, the connection is silently rejected. This is
the source of most connection bugs: valid user actions that fall through all
the dispatch cases without matching anything.

---

## Why Not OOP Inheritance / ECS / Components?

### "Can't we have a base Node class and subclass it for each type?"

That's OOP inheritance. You'd have:

```
BaseNode
├── RecipeNode (adds ingredient input pins)
├── IngredientNode (minimal, just output)
├── FabricatorNode (adds info fields, no hierarchy input)
├── TabNode (adds hierarchy input)
├── MovedRecipeNode (adds path info)
└── ...
```

**Why we don't do this:** DPG (Dear PyGui) uses an immediate-mode pattern
borrowed from ImGui. You build widgets by calling functions in sequence inside
a `with` block. The "object" is just an integer ID that DPG assigned to the
widget. There is no Python object backing the DPG node -- the `RecipeNode`
dataclass we created is our own wrapper, not something DPG understands.

Using subclasses would mean each subclass overrides `create()` to build
different pin layouts. This is certainly possible, but it creates a problem:
the dispatch logic in `on_link()` would need to know what subclass the target
is to decide what command to create. You'd end up with the same
`if isinstance(node, FabricatorNode)` checks that we currently do with
`if node.kind == NodeKind.CUSTOM_FABRICATOR`. The subclass hierarchy adds
ceremony without reducing complexity.

### "What about Entity-Component-System (ECS)?"

ECS is a pattern from game engines (Unity DOTS, Bevy, etc.) where:
- **Entities** are just IDs (no data, no behavior)
- **Components** are pure data bags (Position, Sprite, InputPins)
- **Systems** are functions that process entities with specific component combos

In theory, you'd define components like `HasIngredientInputs`,
`HasHierarchyInput`, `HasSpriteDisplay`, and systems that process them.

**Why we don't do this:** DPG is not an ECS framework. Its node editor expects
you to declare all attributes (pins) at node creation time inside a `with`
block. You can't "query all nodes that have a HierarchyInput component" --
DPG doesn't have that concept. You'd be building an ECS abstraction layer
on top of a non-ECS toolkit, adding complexity without the performance benefits
that make ECS worthwhile (cache locality, parallelism over 10,000+ entities).

### "What about a template/preset system -- one base, compose features per type?"

This is closest to what CraftGraph actually does, just without the formal
abstraction. The `RecipeNode.create()` method IS the "template" -- it's the
base node skeleton that conditionally adds features based on `kind`. The
branching IS the composition, just expressed as if/else rather than as
pluggable component objects.

**The honest answer for why we don't formalize it further:** The constraint
is DPG/imnodes, not our Python architecture. Even if we had a beautiful
component system in Python, we'd still need to flatten everything into a
linear sequence of `dpg.node_attribute()` calls inside a single `with dpg.node()`
block. The GUI toolkit doesn't support post-creation modification of nodes.
A formal component system would add abstraction without changing what actually
happens at the DPG level.

---

## The Big Constraint: imnodes

Everything about this system's design traces back to one fundamental limitation
of the underlying C++ library.

### What is imnodes?

Dear PyGui's node editor is a Python wrapper around **imnodes**, a C++ library
for ImGui that provides the visual node-and-wire editing surface. DPG exposes
it via `dpg.node_editor()`, `dpg.node()`, `dpg.node_attribute()`, and
`dpg.add_node_link()`.

### What imnodes cannot do

1. **You cannot add or remove pins after a node is created.** Once the
   `with dpg.node()` block exits, the node's attribute list is frozen. Want
   to add a new ingredient pin when the user drops a connection? You must
   destroy the ENTIRE node editor and rebuild ALL nodes from scratch.

2. **You cannot modify a pin's type after creation.** A pin that was created
   as `mvNode_Attr_Input` stays an input forever. You can't convert it to
   an output or static pin.

3. **Widget IDs are transient.** Every time you rebuild, DPG assigns new
   integer IDs. Any code holding references to old IDs is now broken. This
   is why we maintain a `_attr_to_node` reverse lookup that gets repopulated
   on every rebuild.

4. **Links reference pins by ID.** If the pin IDs change (because of a
   rebuild), all links become invalid. So links must also be recreated from
   scratch.

### What this means in practice

**Every model change = full visual teardown + rebuild.** There's no
"add one pin to an existing node." The cycle is:

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

This is why the "dynamic input slots" concept (the `__empty__` pin that spawns
new pins when connected to) requires a full rebuild. You can't just insert a
new pin into an existing node. You have to destroy everything and recreate it
with the new pin included.

### Why the "swap" optimization exists

The full rebuild is expensive with hundreds of nodes (the reference files
produce 894). The `_swap_link()` method is a shortcut for one specific case:
replacing an ingredient connection. Instead of a full rebuild, it:
1. Mutates the model silently (no rebuild callback)
2. Manually severs the old DPG link
3. Relabels the existing input pin's text
4. Wires a new link to the same pin

This avoids a full rebuild for the common case of re-routing a wire. But it
only works because the PIN STILL EXISTS -- we're just changing which output
it's connected to. We're not adding or removing pins, which would require the
full rebuild.

---

## The Connection Dispatch Problem

This is the root cause of most connection-related bugs, including the current
hierarchy regression.

### The Problem

When a user drags a wire between two pins, DPG fires `on_link(sender, (attr1, attr2))`.
We receive **two integer IDs** and must figure out:

1. Which node does each attribute belong to?
2. What role does each attribute play (output, ingredient input, hierarchy
   input, empty slot)?
3. What is the user's intent (add ingredient, create hierarchy link, swap
   an existing connection)?
4. Which command should we create?

This is a **classification problem** with many possible combinations:

```
Combinations = (roles of attr1) x (roles of attr2) x (node kinds of both)
             = 4 roles x 4 roles x 11 kinds x 11 kinds
             = ~1,936 theoretical combinations
```

We handle maybe 10-15 of these explicitly. Everything else is silently rejected.
Each time we add a new node kind or pin type, the number of combinations grows,
and the chance of missing a valid case increases.

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

The complexity here is that each new pin type (we now have `__output__`,
`__empty__`, `__hierarchy__`, and named ingredient pins) adds another branch
to this dispatch tree. The hierarchy dispatch was added in Step 11i, and it
introduced an early-return path that takes priority over ingredient dispatch.
If any valid connection pattern falls through the hierarchy check but doesn't
match any ingredient pattern, it gets silently dropped.

---

## The Hierarchy Regression Bug

### What broke

After Step 11i added the hierarchy pin system (the `__hierarchy__` input pin for
parent-child containment links), drag-and-drop connections from fabricators/tabs
to other tabs stopped working. The connection is silently rejected.

### Root cause analysis

The issue is in how `on_link()` dispatches hierarchy connections. When the
user drags from a fabricator's output pin to a tab's hierarchy input pin,
the dispatch path is:

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

The `_try_fabricator_hierarchy()` method checks conditions using `isinstance()`
on the `non_recipe` field. The likely failure points:

1. **The nested-tab key collision:** Tabs spawned by `_spawn_nested_fab_contents()`
   use a different node key format (`custom_crafting_tab::TabId::fab::FabId`)
   than top-level tabs (`custom_crafting_tab::TabId`). If the tab node being
   connected was already spawned as a nested node, its `non_recipe` reference
   points to a different `CraftingTab` instance than the one in the top-level
   `parsed_file.crafting_tabs` list.

2. **Output-to-empty fallback path:** When a user drags from a tab's output
   to a fabricator's `__empty__` pin (instead of the "correct" direction), the
   dispatch treats the tab as the parent and the fabricator as the child.
   `_try_fabricator_hierarchy()` has no case for "Tab is parent, Fabricator
   is child" -- fabricators don't nest inside tabs. So it returns `None`.
   But the user's INTENT was to nest the tab inside the fabricator; they just
   dragged in the "wrong" direction.

3. **The early-return trap:** When `target_role == "__hierarchy__"`, the code
   always returns after the hierarchy dispatch, even if it returned `None`.
   There's no fallback to the ingredient logic, no error message, no log line.
   The connection just vanishes.

### Why this class of bug keeps happening

Every time we add a new pin type or connection semantic, we're adding branches
to a dispatch tree that was originally designed for just two cases (output-to-input
ingredient connections). The tree doesn't have an exhaustive match -- there's no
equivalent of a Rust `match` that forces you to handle every case. Unhandled
combinations fall through silently.

The fix for any individual case is usually small (add another condition to the
dispatch), but the underlying problem is architectural: the dispatch tree grows
linearly with each new feature while the combination space grows quadratically.

---

## What Would a Better System Look Like?

If we were starting from scratch (or if DPG/imnodes supported it), a better
architecture might look like:

### Option A: Component-based nodes with a custom renderer

Instead of using DPG's node editor, render nodes ourselves using DPG's draw
list API. This gives full control over:
- Adding/removing pins dynamically (no rebuild needed)
- Custom hit-testing for connections
- Component-based node construction

But this means reimplementing: node rendering, pin rendering, link rendering,
link dragging, minimap, scrolling, selection, multi-select, keyboard
navigation... essentially writing our own node editor from scratch. That's
months of work for marginal benefit.

### Option B: Explicit connection type registration

Instead of the current dispatch tree, define all valid connection types as
a table:

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

This makes the dispatch exhaustive, self-documenting, and testable. New
connection types are added as data, not as new branches in a nested if/else.
It also makes it trivial to add "reverse direction" support (just add both
directions as separate rules).

### Option C: Accept the current design, improve error reporting

The pragmatic path. The current architecture works. The dispatch tree is
complex but manageable. The key improvement would be adding visible feedback
when a connection is rejected (a toast/notification saying "Cannot connect X
to Y: reason") instead of silent rejection. This makes debugging much easier
and gives users clear feedback when they try an invalid connection.

**CraftGraph currently follows a hybrid of B and C** -- the dispatch is
moving toward a more structured pattern (separate methods per hierarchy type),
and Step 11j will add user-facing validation warnings.

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

The system is pragmatic: it works within DPG's constraints and keeps the data
model completely decoupled from the GUI. The cost is a complex dispatch layer
that grows with each new feature. The mitigation is better error reporting
(Step 11j) and more structured dispatch (connection rule tables).
