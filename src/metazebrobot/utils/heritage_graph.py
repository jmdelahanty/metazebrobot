"""Lineage graph for a tank's heritage (docs/tank_heritage_design.md step 3).

Builds tank -> producing cross -> parent tanks (recursively), including the
recorded splits between them, from the local cache only, and lays it out for
a server-rendered SVG, pedigree-chart style: the tank on the left, ancestors
spreading to the right.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from .tank_heritage import _producing_cross, _tank_record

DEFAULT_GENERATIONS = 3
MAX_NODES = 120  # keeps incross-heavy pedigrees readable

COLUMN_WIDTH = 250
ROW_HEIGHT = 92
NODE_WIDTH = 200
TANK_HEIGHT = 70
CROSS_HEIGHT = 46
MARGIN = 24


def build_heritage_graph(
    conn: sqlite3.Connection,
    tank_id: Any,
    generations: int = DEFAULT_GENERATIONS,
) -> Dict[str, Any]:
    """Nodes and edges for a tank's ancestry, each node at a ``depth``.

    Depth counts graph steps back from the tank (0); columns are derived from
    it. Shared ancestors appear once. Stops at ``generations`` crosses back or
    ``MAX_NODES`` nodes, and marks where it stopped.
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    truncated = False

    def add_tank(tid: str, depth: int, role: str = "ancestor") -> str:
        node_id = f"tank:{tid}"
        if node_id not in nodes:
            record = _tank_record(conn, tid)
            nodes[node_id] = {
                "id": node_id, "kind": "tank", "tank_id": tid, "role": role,
                "strain_id": record.get("strain_id"),
                "strain_name": record.get("strain_name"),
                "generation": record.get("generation"),
                "date_of_birth": (record.get("date_of_birth") or "")[:10] or None,
                "depth": depth, "origin": "unknown",
            }
        else:
            nodes[node_id]["depth"] = max(nodes[node_id]["depth"], depth)
        return node_id

    def walk(tid: str, depth: int, cross_generation: int) -> None:
        nonlocal truncated
        tank_node = add_tank(tid, depth)
        producing = _producing_cross(conn, tid)
        if not producing:
            return
        if cross_generation >= generations or len(nodes) >= MAX_NODES:
            nodes[tank_node]["origin"] = "not expanded"
            truncated = True
            return

        # Splits: tid <- ... <- origin tank listed by the cross.
        child_node = tank_node
        step_depth = depth
        for split in producing["via_splits"]:
            step_depth += 1
            source_node = add_tank(split["from_tank_id"], step_depth)
            edges.append({"source": source_node, "target": child_node, "kind": "split",
                          "label": f"split {split['date'] or ''}".strip()})
            nodes[child_node]["origin"] = "split"
            child_node = source_node

        cross_node = f"cross:{producing['cross_id']}"
        cross_depth = step_depth + 1
        if cross_node not in nodes:
            nodes[cross_node] = {
                "id": cross_node, "kind": "cross", "cross_id": producing["cross_id"],
                "cross_type": producing["cross_type"],
                "date_of_set_up": (producing.get("date_of_set_up") or "")[:10] or None,
                "depth": cross_depth,
            }
            expand = True
        else:
            nodes[cross_node]["depth"] = max(nodes[cross_node]["depth"], cross_depth)
            expand = False
        edges.append({"source": cross_node, "target": child_node, "kind": "produced",
                      "label": None})
        nodes[child_node]["origin"] = "cross"
        if not expand:
            return
        for parent in producing["parents"]:
            if parent.get("tank_id") is None:
                continue
            parent_node = add_tank(str(parent["tank_id"]), cross_depth + 1)
            edges.append({"source": parent_node, "target": cross_node, "kind": "parent",
                          "label": None})
            walk(str(parent["tank_id"]), cross_depth + 1, cross_generation + 1)

    root = str(tank_id)
    walk(root, 0, 0)
    nodes[f"tank:{root}"]["role"] = "subject"
    # Edges may repeat when an ancestor is reached twice; keep one of each.
    unique = {(e["source"], e["target"], e["kind"]): e for e in edges}
    return {"nodes": list(nodes.values()), "edges": list(unique.values()),
            "truncated": truncated, "generations": generations}


def layout_heritage_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Assign SVG coordinates: the tank left, deeper ancestors further right."""
    nodes = graph["nodes"]
    if not nodes:
        return {**graph, "width": 0, "height": 0}
    # An ancestor reached by two routes must still sit left of every
    # descendant: relax depth so each edge's source is deeper than its target.
    by_id = {node["id"]: node for node in nodes}
    for _ in range(len(nodes)):
        changed = False
        for edge in graph["edges"]:
            source, target = by_id.get(edge["source"]), by_id.get(edge["target"])
            if source and target and source["depth"] <= target["depth"]:
                source["depth"] = target["depth"] + 1
                changed = True
        if not changed:
            break
    columns: Dict[int, List[Dict[str, Any]]] = {}
    for node in nodes:
        columns.setdefault(node["depth"], []).append(node)

    height_rows = max(len(col) for col in columns.values())
    for column, col_nodes in columns.items():
        col_nodes.sort(key=lambda n: (n["kind"], str(n.get("cross_id") or n.get("tank_id"))))
        offset = (height_rows - len(col_nodes)) * ROW_HEIGHT / 2
        for row, node in enumerate(col_nodes):
            node["width"] = NODE_WIDTH
            node["height"] = TANK_HEIGHT if node["kind"] == "tank" else CROSS_HEIGHT
            node["x"] = MARGIN + column * COLUMN_WIDTH
            node["y"] = MARGIN + offset + row * ROW_HEIGHT + (TANK_HEIGHT - node["height"]) / 2

    laid_edges = []
    for edge in graph["edges"]:
        source, target = by_id.get(edge["source"]), by_id.get(edge["target"])
        if not source or not target:
            continue
        # Ancestor (right) -> descendant (left): leave the source's left side,
        # arrive at the target's right side.
        x1, y1 = source["x"], source["y"] + source["height"] / 2
        x2, y2 = target["x"] + target["width"], target["y"] + target["height"] / 2
        mid = (x1 + x2) / 2
        laid_edges.append({
            **edge,
            "path": f"M{x1:.0f},{y1:.0f} C{mid:.0f},{y1:.0f} {mid:.0f},{y2:.0f} {x2:.0f},{y2:.0f}",
            "label_x": mid, "label_y": (y1 + y2) / 2 - 6,
        })
    width = MARGIN * 2 + (max(columns) + 1) * COLUMN_WIDTH - (COLUMN_WIDTH - NODE_WIDTH)
    height = MARGIN * 2 + height_rows * ROW_HEIGHT
    return {**graph, "nodes": nodes, "edges": laid_edges, "width": width, "height": height}
