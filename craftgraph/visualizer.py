"""Interactive HTML graph visualizer via Pyvis."""

import webbrowser
from pathlib import Path

import networkx
from pyvis.network import Network

from craftgraph.graph import NodeType, classify_nodes

# -- Node styling constants ----------------------------------------------------

_NODE_COLORS: dict[NodeType, str] = {
    NodeType.RAW_MATERIAL: "#2ecc71",  # green
    NodeType.INTERMEDIATE: "#3498db",  # blue
    NodeType.END_PRODUCT: "#f1c40f",  # gold
}

_BASE_NODE_SIZE = 10
_SIZE_SCALE = 3


# -- Edge styling constants ----------------------------------------------------

_NORMAL_EDGE_COLOR = "#888888"
_CYCLE_EDGE_COLOR = "#e74c3c"  # red
_NORMAL_EDGE_WIDTH = 1
_CYCLE_EDGE_WIDTH = 3


def _build_cycle_edge_set(cycles: list[list[str]]) -> set[tuple[str, str]]:
    """Convert cycle lists into a set of directed (source, target) edge pairs.

    Each cycle ``[A, B, C]`` produces edges ``(A, B), (B, C), (C, A)``.
    """
    cycle_edges: set[tuple[str, str]] = set()
    for cycle in cycles:
        for i in range(len(cycle)):
            source = cycle[i]
            target = cycle[(i + 1) % len(cycle)]
            cycle_edges.add((source, target))
    return cycle_edges


def _build_tooltip(node_id: str, graph: networkx.DiGraph[str]) -> str:
    """Build an HTML tooltip showing recipe details for a node."""
    attrs = graph.nodes[node_id]
    lines = [f"<b>{node_id}</b>"]

    if attrs.get("is_crafted"):
        recipe_type = attrs.get("recipe_type", "Unknown")
        source_file = attrs.get("source_file", "")
        lines.append(f"Type: {recipe_type}")
        if source_file:
            lines.append(f"File: {Path(source_file).name}")

    # Show ingredients (successors in graph = dependencies)
    successors = list(graph.successors(node_id))
    if successors:
        lines.append("<br><b>Ingredients:</b>")
        for ing_id in sorted(successors):
            edge_data = graph.edges[node_id, ing_id]
            required = edge_data.get("required", 1)
            lines.append(f"  {ing_id} x{required}")

    # Show what uses this item (predecessors = dependents)
    predecessors = list(graph.predecessors(node_id))
    if predecessors:
        lines.append(f"<br><b>Used by:</b> {', '.join(sorted(predecessors))}")

    return "<br>".join(lines)


def generate_html(
    graph: networkx.DiGraph[str],
    output_path: Path,
    cycles: list[list[str]] | None = None,
    *,
    open_browser: bool = False,
) -> Path:
    """Render the dependency graph as an interactive HTML file via Pyvis.

    Nodes are colored by classification (raw material, intermediate, end
    product) and sized proportionally to their connection count.  Edges
    belonging to circular dependencies are highlighted in red.

    When *open_browser* is True, the generated file is opened in the
    default web browser after saving.

    Returns the resolved output path.
    """
    net = Network(
        height="100vh",
        width="100%",
        directed=True,
        bgcolor="#1a1a2e",
        font_color="#e0e0e0",
        cdn_resources="in_line",
    )
    # Hierarchical layout: dependency flow from end products (top) to
    # raw materials (bottom).  vis.js "directed" sort uses edge direction
    # to assign levels automatically.
    net.set_options("""{
        "layout": {
            "hierarchical": {
                "enabled": true,
                "direction": "UD",
                "sortMethod": "directed",
                "levelSeparation": 100,
                "nodeSpacing": 100,
                "treeSpacing": 150,
                "blockShifting": true,
                "edgeMinimization": true,
                "parentCentralization": true
            }
        },
        "physics": {
            "hierarchicalRepulsion": {
                "centralGravity": 0.0,
                "springLength": 100,
                "springConstant": 0.01,
                "nodeDistance": 120,
                "damping": 0.09
            },
            "solver": "hierarchicalRepulsion",
            "stabilization": {
                "iterations": 2000,
                "updateInterval": 25
            }
        },
        "edges": {
            "smooth": {
                "type": "cubicBezier",
                "forceDirection": "vertical"
            }
        }
    }""")

    classifications = classify_nodes(graph)
    cycle_edges = _build_cycle_edge_set(cycles or [])

    # Add nodes
    for node_id in graph.nodes:
        node_type = classifications.get(node_id, NodeType.RAW_MATERIAL)
        degree = graph.in_degree(node_id) + graph.out_degree(node_id)
        size = _BASE_NODE_SIZE + degree * _SIZE_SCALE

        net.add_node(
            node_id,
            label=node_id,
            color=_NODE_COLORS[node_type],
            size=size,
            title=_build_tooltip(node_id, graph),
            shape="dot",
        )

    # Add edges
    for source, target in graph.edges:
        if (source, target) in cycle_edges:
            color = _CYCLE_EDGE_COLOR
            width = _CYCLE_EDGE_WIDTH
        else:
            color = _NORMAL_EDGE_COLOR
            width = _NORMAL_EDGE_WIDTH

        net.add_edge(source, target, color=color, width=width)

    # Pyvis's save_graph/write_html uses the default system encoding,
    # which on Windows (cp1252) can't handle Unicode in tooltips.
    # Generate the HTML string ourselves and write with UTF-8.
    html = net.generate_html()
    output_path.write_text(html, encoding="utf-8")

    resolved = output_path.resolve()
    if open_browser:
        webbrowser.open(resolved.as_uri())
    return resolved
