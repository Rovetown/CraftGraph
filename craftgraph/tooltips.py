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

from collections.abc import Iterable
from html import escape

from PySide6.QtWidgets import QMenu

from craftgraph.theme import scaled_pt

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


# ---------------------------------------------------------------------------
# Rich node-details tooltip
# ---------------------------------------------------------------------------


_LABEL_COLOR = "#9ec1ff"
_VALUE_COLOR = "#e6e6e6"
_MUTED_COLOR = "#888"
_HEADER_COLOR = "#ffd166"
_ERROR_COLOR = "#ff7171"
_WARNING_COLOR = "#f0c64a"


def _row(label: str, value: str) -> str:
    """Render one ``<label>: <value>`` line with consistent coloring."""
    return (
        f'<tr><td style="color:{_LABEL_COLOR};padding-right:8px;'
        f'white-space:nowrap;">{escape(label)}</td>'
        f'<td style="color:{_VALUE_COLOR};">{value}</td></tr>'
    )


def _mono(text: str) -> str:
    """Render *text* in a monospace span (for IDs, paths, ingredient names)."""
    return (
        f'<span style="font-family:Consolas,monospace;color:{_VALUE_COLOR};">{escape(text)}</span>'
    )


def _ingredient_html(ingredients: object) -> str:
    """Render a list of Ingredient dataclasses as an HTML list."""
    if not ingredients or not isinstance(ingredients, Iterable):
        return f'<i style="color:{_MUTED_COLOR};">none</i>'
    parts: list[str] = []
    for ing in ingredients:
        item_id = getattr(ing, "item_id", "?")
        required = getattr(ing, "required", 1)
        parts.append(
            f'{_mono(str(item_id))}<span style="color:{_MUTED_COLOR};"> '
            f"x{escape(str(required))}</span>"
        )
    return "<br>".join(parts)


def _csv_html(values: object) -> str:
    """Render a list of strings (or a comma-separated string) inline."""
    if values in (None, "", []):
        return f'<i style="color:{_MUTED_COLOR};">none</i>'
    if isinstance(values, str):
        items = [v.strip() for v in values.split(",") if v.strip()]
    elif isinstance(values, Iterable):
        items = [str(v) for v in values if str(v).strip()]
    else:
        items = [str(values)]
    if not items:
        return f'<i style="color:{_MUTED_COLOR};">none</i>'
    return ", ".join(_mono(v) for v in items)


def _bool_html(value: object) -> str:
    if value is True:
        return '<span style="color:#9bd17a;">YES</span>'
    if value is False:
        return '<span style="color:#d17a7a;">NO</span>'
    return f'<i style="color:{_MUTED_COLOR};">default</i>'


def _model_field_rows(model: object) -> list[str]:
    """Return the field rows for *model* in stable, type-aware order."""
    if model is None:
        return []
    rows: list[str] = []

    item_id = getattr(model, "item_id", None)
    if isinstance(item_id, str) and item_id:
        rows.append(_row("ItemID", _mono(item_id)))
    tab_id = getattr(model, "tab_id", None)
    if isinstance(tab_id, str) and tab_id:
        rows.append(_row("TabID", _mono(tab_id)))

    display_name = getattr(model, "display_name", None)
    if isinstance(display_name, str) and display_name:
        rows.append(_row("DisplayName", escape(display_name)))
    tooltip_text = getattr(model, "tooltip", None)
    if isinstance(tooltip_text, str) and tooltip_text:
        rows.append(_row("Tooltip", escape(tooltip_text)))

    path = getattr(model, "path", None)
    if isinstance(path, str) and path:
        rows.append(_row("Path", _mono(path)))
    parent_tab_path = getattr(model, "parent_tab_path", None)
    if isinstance(parent_tab_path, str) and parent_tab_path:
        rows.append(_row("ParentTabPath", _mono(parent_tab_path)))
    old_path = getattr(model, "old_path", None)
    if isinstance(old_path, str) and old_path:
        rows.append(_row("OldPath", _mono(old_path)))
    new_path = getattr(model, "new_path", None)
    if isinstance(new_path, str) and new_path:
        rows.append(_row("NewPath", _mono(new_path)))

    amount = getattr(model, "amount_crafted", None)
    if isinstance(amount, int) and amount and amount != 1:
        rows.append(_row("AmountCrafted", _mono(str(amount))))

    if hasattr(model, "ingredients"):
        rows.append(_row("Ingredients", _ingredient_html(model.ingredients)))

    linked = getattr(model, "linked_item_ids", None)
    if linked:
        rows.append(_row("LinkedItemIDs", _csv_html(linked)))
    unlocks = getattr(model, "unlocks", None)
    if unlocks:
        rows.append(_row("Unlocks", _csv_html(unlocks)))
    unlocked_by = getattr(model, "unlocked_by", None)
    if unlocked_by:
        rows.append(_row("UnlockedBy", _csv_html(unlocked_by)))

    pda_group = getattr(model, "pda_group", None)
    if isinstance(pda_group, str) and pda_group:
        rows.append(_row("PdaGroup", _mono(pda_group)))
    pda_category = getattr(model, "pda_category", None)
    if isinstance(pda_category, str) and pda_category:
        rows.append(_row("PdaCategory", _mono(pda_category)))

    fab_model = getattr(model, "model", None)
    if isinstance(fab_model, str) and fab_model:
        rows.append(_row("Model", _mono(fab_model)))

    width = getattr(model, "width", None)
    height = getattr(model, "height", None)
    if isinstance(width, int) and isinstance(height, int) and (width != 1 or height != 1):
        rows.append(_row("Size", f"{_mono(str(width))} x {_mono(str(height))}"))

    energy = getattr(model, "energy", None)
    if isinstance(energy, (int, float)) and energy:
        rows.append(_row("Energy", _mono(str(energy))))

    fragments = getattr(model, "fragments_to_scan", None)
    if isinstance(fragments, int) and fragments and fragments != 1:
        rows.append(_row("FragmentsToScan", _mono(str(fragments))))

    food_value = getattr(model, "food_value", None)
    water_value = getattr(model, "water_value", None)
    if isinstance(food_value, int) and food_value:
        rows.append(_row("FoodValue", _mono(str(food_value))))
    if isinstance(water_value, int) and water_value:
        rows.append(_row("WaterValue", _mono(str(water_value))))
    health_value = getattr(model, "health_value", None)
    if isinstance(health_value, int) and health_value:
        rows.append(_row("HealthValue", _mono(str(health_value))))

    copied = getattr(model, "copied", None)
    hidden = getattr(model, "hidden", None)
    if copied is True:
        rows.append(_row("Copied", _bool_html(True)))
    if hidden is True:
        rows.append(_row("Hidden", _bool_html(True)))

    force_unlock = getattr(model, "force_unlock_at_start", None)
    if force_unlock is True:
        rows.append(_row("ForceUnlockAtStart", _bool_html(True)))

    return rows


def format_node_details_tooltip(
    *,
    type_name: str,
    type_desc: str | None,
    model: object,
    fallback_id: str | None = None,
    source_file: str | None = None,
    issues: list[str] | None = None,
    cycle_paths: list[str] | None = None,
) -> str:
    """Build a rich HTML tooltip with the node's recipe details.

    Renders type header, source file (if known), all populated model fields,
    cycle membership, and validation issues using a consistent palette so the
    tooltip is legible against any node header colour.
    """
    parts: list[str] = []
    title = escape(type_name)
    parts.append(
        f'<div style="color:{_HEADER_COLOR};font-weight:bold;'
        f'font-size:{scaled_pt(11)}pt;">{title}</div>'
    )
    if type_desc:
        parts.append(
            f'<div style="color:{_MUTED_COLOR};font-style:italic;'
            f'margin-bottom:4px;">{escape(type_desc)}</div>'
        )

    rows = _model_field_rows(model)
    if not rows and fallback_id:
        rows = [_row("ItemID", _mono(fallback_id))]
    if source_file:
        rows.insert(
            0,
            _row(
                "Source",
                f'<span style="color:{_MUTED_COLOR};">{escape(source_file)}</span>',
            ),
        )

    if rows:
        parts.append(
            '<table cellspacing="0" cellpadding="1" style="margin-top:2px;">'
            + "".join(rows)
            + "</table>"
        )

    if cycle_paths:
        cycle_lines = "<br>".join(_mono(p) for p in cycle_paths)
        parts.append(
            f'<div style="margin-top:6px;color:{_ERROR_COLOR};">'
            f"<b>In dependency cycle</b><br>{cycle_lines}</div>"
        )

    if issues:
        bullets = "".join(f"<li>{escape(item)}</li>" for item in issues)
        parts.append(
            f'<div style="margin-top:6px;color:{_WARNING_COLOR};">'
            f'<b>Issues</b><ul style="margin:2px 0 0 16px;padding:0;">'
            f"{bullets}</ul></div>"
        )

    return "".join(parts)
