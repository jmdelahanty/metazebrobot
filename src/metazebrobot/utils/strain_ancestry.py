"""Strain-level ancestry as a last-resort background source.

Step 2c of docs/tank_heritage_design.md. When the tank-level record walk
(producing crosses, splits) finds no recognizable background -- typically an
imported line whose founders were never crossed in this facility -- PyRAT's
strain pedigree can still name founder strains (e.g. ``Tg(ubi:Switch)`` <-
``Casper_HHMI``, ``AB Casper_HHMI``).

This is *strain*-level, not parentage: it says what a strain was derived from,
not which fish were bred. Results are therefore reported as "inferred from
strain ancestry", never merged into the record-derived background.

The pedigree comes from ``backend/v1/reports/colony_pedigree``, a PyRAT
frontend internal with no compatibility guarantee; fetches happen only from
scripts and are cached in ``strain_ancestry`` so pages never call PyRAT. The
graph can contain cycles (``Casper_HHMI`` <-> ``AB Casper_HHMI``) and
placeholder nodes (``SENTINEL``), which are handled here.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

from .cross_provenance import parse_parent_background

REPORT_ENDPOINT = "backend/v1/reports/colony_pedigree"
GENERATIONS = 6
REFRESH_AFTER_DAYS = 90
PLACEHOLDER_NAMES = {"SENTINEL"}


def ensure_strain_ancestry_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strain_ancestry (
            strain_id TEXT NOT NULL,
            ancestor_id TEXT NOT NULL,
            ancestor_name TEXT,
            depth INTEGER NOT NULL,            -- 1 = direct parent strain
            PRIMARY KEY (strain_id, ancestor_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strain_ancestry_fetches (
            strain_id TEXT PRIMARY KEY,
            fetched_at TEXT NOT NULL,
            ancestor_count INTEGER NOT NULL
        )
    """)


def parse_strain_pedigree(payload: Dict[str, Any], strain_id: Any) -> List[Tuple[str, str, int]]:
    """(ancestor_id, ancestor_name, depth) for every ancestor of ``strain_id``.

    Breadth-first from the strain through ``parents``; each ancestor keeps its
    shallowest depth, cycles are cut, and placeholder nodes are skipped.
    """
    nodes = {str(n.get("id")): n for n in (payload.get("pedigree") or {}).get("nodes") or []}
    names = {node_id: node.get("name") for node_id, node in nodes.items()}
    start = str(strain_id)
    found: Dict[str, Tuple[str, int]] = {}
    frontier = [(start, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        for parent in (nodes.get(current) or {}).get("parents") or []:
            parent_id = str(parent.get("parent_id"))
            name = parent.get("parent_name") or names.get(parent_id)
            if parent_id == start or parent_id in found or not name:
                continue
            if name.strip().upper() in PLACEHOLDER_NAMES:
                continue
            found[parent_id] = (name, depth + 1)
            frontier.append((parent_id, depth + 1))
    return [(ancestor_id, name, depth) for ancestor_id, (name, depth) in found.items()]


def store_strain_ancestry(conn: sqlite3.Connection, strain_id: Any,
                          ancestors: Iterable[Tuple[str, str, int]]) -> None:
    strain_id = str(strain_id)
    ancestors = list(ancestors)
    conn.execute("DELETE FROM strain_ancestry WHERE strain_id = ?", (strain_id,))
    conn.executemany(
        "INSERT INTO strain_ancestry (strain_id, ancestor_id, ancestor_name, depth) VALUES (?, ?, ?, ?)",
        [(strain_id, a_id, name, depth) for a_id, name, depth in ancestors],
    )
    conn.execute(
        "INSERT INTO strain_ancestry_fetches (strain_id, fetched_at, ancestor_count) VALUES (?, ?, ?) "
        "ON CONFLICT(strain_id) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "ancestor_count = excluded.ancestor_count",
        (strain_id, datetime.now().isoformat(timespec="seconds"), len(ancestors)),
    )


def needs_fetch(conn: sqlite3.Connection, strain_id: Any) -> bool:
    row = conn.execute(
        "SELECT fetched_at FROM strain_ancestry_fetches WHERE strain_id = ?", (str(strain_id),)
    ).fetchone()
    if not row:
        return True
    try:
        fetched = datetime.fromisoformat(row[0])
    except ValueError:
        return True
    return fetched < datetime.now() - timedelta(days=REFRESH_AFTER_DAYS)


def strain_ancestry_backgrounds(conn: sqlite3.Connection, strain_id: Any) -> Dict[str, Any]:
    """Backgrounds named anywhere in a strain's cached ancestry (no PyRAT calls)."""
    backgrounds: Dict[str, List[str]] = {}
    mutants: Dict[str, List[str]] = {}
    try:
        rows = conn.execute(
            "SELECT ancestor_name, depth FROM strain_ancestry WHERE strain_id = ? ORDER BY depth, ancestor_name",
            (str(strain_id),),
        ).fetchall()
    except sqlite3.OperationalError:  # table not created yet
        rows = []
    for name, _depth in rows:
        parsed = parse_parent_background(name or "")
        source = f"strain ancestry: {name}"
        for value in parsed["background_strains"]:
            backgrounds.setdefault(value, []).append(source)
        for value in parsed["mutant_backgrounds"]:
            mutants.setdefault(value, []).append(source)
    return {
        "fetched": bool(rows),
        "backgrounds": [{"value": k, "sources": v} for k, v in sorted(backgrounds.items())],
        "mutant_backgrounds": [{"value": k, "sources": v} for k, v in sorted(mutants.items())],
    }


def strains_needing_ancestry(conn: sqlite3.Connection) -> List[str]:
    """Strains worth a pedigree fetch: not fetched (or stale), named without
    any recognizable background, and used by at least one cached tank whose
    records give no background either."""
    from .tank_heritage import derive_tank_heritage  # avoid import cycle

    ensure_strain_ancestry_schema(conn)
    tanks_by_strain: Dict[str, List[str]] = {}
    names: Dict[str, str] = {}
    for strain_id, name, tank_id in conn.execute("""
        SELECT DISTINCT json_extract(raw_payload, '$.strain_id'), raw_strain_name, tank_id
        FROM cross_parents
        WHERE tank_id IS NOT NULL AND json_extract(raw_payload, '$.strain_id') IS NOT NULL
        UNION
        SELECT DISTINCT strain_id, strain_name, tank_id FROM cross_children
        WHERE strain_id IS NOT NULL
    """):
        tanks_by_strain.setdefault(str(strain_id), []).append(str(tank_id))
        if name:
            names[str(strain_id)] = name

    needed = []
    for strain_id, tank_ids in tanks_by_strain.items():
        if not needs_fetch(conn, strain_id):
            continue
        named = parse_parent_background(names.get(strain_id, ""))
        if named["background_strains"] or named["mutant_backgrounds"]:
            continue  # the name already says it; ancestry adds little
        for tank_id in tank_ids:
            heritage = derive_tank_heritage(conn, tank_id)
            if not (heritage["backgrounds"] or heritage["mutant_backgrounds"]):
                needed.append(strain_id)
                break
    return sorted(needed, key=lambda s: int(s) if s.isdigit() else 0)


def fetch_strain_ancestry(conn: sqlite3.Connection, client: Any, strain_ids: Iterable[Any],
                          pause: float = 0.5) -> Dict[str, int]:
    """Fetch and store pedigrees for ``strain_ids`` (one request each)."""
    import time

    stats = {"fetched": 0, "with_ancestors": 0}
    for index, strain_id in enumerate(strain_ids):
        if index:
            time.sleep(pause)
        ancestors = parse_strain_pedigree(client.pedigree(strain_id), strain_id)
        store_strain_ancestry(conn, strain_id, ancestors)
        conn.commit()
        stats["fetched"] += 1
        stats["with_ancestors"] += bool(ancestors)
    return stats


class StrainPedigreeClient:
    """Logged-in PyRAT frontend session for the colony-pedigree report."""

    def __init__(self, credentials: Optional[Dict[str, str]] = None, verify_ssl: bool = False):
        from .pyrat_credentials import get_pyrat_frontend_credentials, normalize_base_url
        from .pyrat_frontend_client import login_pyrat_frontend

        credentials = credentials or get_pyrat_frontend_credentials()
        if not credentials:
            raise RuntimeError("PyRAT frontend credentials are not configured.")
        self.base_url = normalize_base_url(credentials["base_url"])
        self.verify_ssl = verify_ssl
        self.session, self.session_id = login_pyrat_frontend(
            credentials["base_url"], credentials["username"], credentials["password"],
            verify_ssl=verify_ssl,
        )
        self.requests = 0

    def pedigree(self, strain_id: Any) -> Dict[str, Any]:
        self.requests += 1
        response = self.session.get(
            urljoin(self.base_url, REPORT_ENDPOINT),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.session_id}",
                "Referer": urljoin(
                    self.base_url,
                    f"frontend/reports/colony_pedigree?sessionid={self.session_id}",
                ),
            },
            params={"kind": "strain_pedigree", "label": str(strain_id),
                    "generations": str(GENERATIONS)},
            verify=self.verify_ssl,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
