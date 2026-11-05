"""Short labels for screening results, shared by pages and reports."""

import re
from typing import Any, Dict, List, Optional, Tuple


def short_construct(construct: Optional[str]) -> str:
    """'Tg(gfap:PMCA2-mCherry-zf)' -> 'PMCA2-mCherry-zf' for compact display."""
    match = re.search(r":([^)]+)\)", construct or "")
    return match.group(1) if match else (construct or "?")


def result_label(calls: List[Dict[str, Any]]) -> str:
    """A fish's screening calls in short form, e.g. 'PMCA2-mCherry-zf+ pig'."""
    return " ".join(
        ("pig" if c["kind"] == "pigment" else short_construct(c["dish_construct"]))
        + {"positive": "+", "negative": "−", "pigmented": ""}.get(c["result"], "?")
        for c in calls)


def well_sort_key(label: str) -> Tuple[str, int]:
    """Row-major order: A1, A2, ..., A12, B1 (not text order A1, A10, A2)."""
    match = re.match(r"^([A-Za-z]+)(\d+)$", label or "")
    return (match.group(1), int(match.group(2))) if match else (label or "", 0)


def plate_layout(well_labels: List[str]) -> Optional[Dict[str, Any]]:
    """Rows and columns of a well plate from its well labels (A1..C4 -> A-C, 1-4)."""
    keys = [well_sort_key(w) for w in well_labels]
    if not keys or any(col == 0 for _, col in keys):
        return None
    return {"rows": sorted({row for row, _ in keys}), "cols": list(range(1, max(c for _, c in keys) + 1))}
