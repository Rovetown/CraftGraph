"""Reusable tooltip utilities for CraftGraph Qt widgets.

Provides helpers for attaching floating tooltips to Qt menus, actions,
widgets, and NodeGraphQt nodes.  Centralises tooltip text so the same
descriptions can be reused across context menus, node headers, field
widgets, and help panels.

Usage with NodeGraphQt context menus::

    from craftgraph.tooltips import NODE_DESCRIPTIONS, enable_menu_tooltips

    cmd = menu.add_command("Modified Recipe", func=callback)
    cmd.qaction.setToolTip(NODE_DESCRIPTIONS["Modified Recipe"])
    enable_menu_tooltips(graph_menu.qmenu)

Usage with plain Qt widgets::

    widget.setToolTip(format_tooltip("Field", "Short explanation"))
"""

from __future__ import annotations

from PySide6.QtWidgets import QMenu

# ---------------------------------------------------------------------------
# Qt menu tooltip helpers
# ---------------------------------------------------------------------------

def enable_menu_tooltips(menu: QMenu) -> None:
    """Enable tooltip visibility on *menu* and all nested submenus.

    Qt hides ``QAction`` tooltips inside ``QMenu`` by default.  Call this
    once on the top-level ``QMenu`` to recursively opt in throughout the
    entire hierarchy.
    """
    menu.setToolTipsVisible(True)
    for action in menu.actions():
        child = action.menu()
        if child is not None:
            enable_menu_tooltips(child)


def format_tooltip(title: str, description: str) -> str:
    """Return an HTML tooltip string with a bold *title* and *description*.

    Qt renders HTML in tooltips automatically, so the returned string can
    be passed directly to ``QWidget.setToolTip()`` or
    ``QAction.setToolTip()``.
    """
    return f"<b>{title}</b><br>{description}"


# ---------------------------------------------------------------------------
# Centralised tooltip descriptions
# ---------------------------------------------------------------------------

NODE_DESCRIPTIONS: dict[str, str] = {
    "Ingredient": "Standalone orphan ingredient node",
    "Modified Recipe": "Change an existing in-game recipe",
    "Added Recipe": "New recipe at a crafting path",
    "Alias Recipe": "Clone and rename an existing recipe",
    "Custom Food": "Food or drink with nutrition values",
    "Fabricator": "Custom crafting station",
    "Crafting Tab": "Organise recipes into tabs",
    "Custom Size": "Change inventory slot size",
    "Moved Recipe": "Relocate an existing recipe",
    "Custom BioFuel": "Set bioreactor energy value",
    "Custom Fragment Count": "Change scan requirements",
    "Sprite": "Assign an image to a node",
}
"""Short descriptions for CC3 node types, keyed by display name."""

VARIABLE_DESCRIPTIONS: dict[str, str] = {
    "String Variable": "Reusable text value (names, IDs, paths)",
    "Int Variable": "Reusable integer value (amounts, counts)",
    "Float Variable": "Reusable decimal value (multipliers, ratios)",
    "Bool Variable": "Reusable YES/NO toggle",
    "CSV List Variable": "Reusable comma-separated list of IDs",
    "Enum Variable": "Reusable enumeration value",
    "Path Variable": "Reusable crafting tree path",
    "Color Variable": "Reusable colour value",
    "Get Fabricator": "Reference a fabricator defined elsewhere",
    "Get Tab": "Reference a crafting tab defined elsewhere",
}
"""Short descriptions for variable node types, keyed by display name."""

OPERATION_DESCRIPTIONS: dict[str, str] = {
    "Delete Ingredient...": "Remove an ingredient connection from this recipe",
    "Promote Ingredient to Recipe...": "Create a new recipe node for an ingredient",
    "Promote to Variable...": "Extract a field value into a reusable variable node",
}
"""Short descriptions for node context-menu operations."""
