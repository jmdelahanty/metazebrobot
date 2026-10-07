"""PyRAT strain names by id, with history (docs/tank_heritage_design.md step 6).

Strain names change in PyRAT as information arrives (a background added, a
typo fixed). The strain ``id`` never changes, so it is the identity; names
are labels with a history. PyRAT exposes no modification date, so renames are
detected by comparing each refresh with what was seen before.

- ``strains``: current name per strain id (refreshed from ``api/v3/strains``).
- ``strain_names``: every name each strain has been seen with, including names
  found in already-cached crossing payloads (renames that happened before this
  table existed).

When a strain's current name differs from a cached row's name-as-fetched, the
row's parsed background columns are re-derived from the current name; the
fetched name itself is kept, so "formerly ..." can be shown.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .cross_provenance import parse_parent_background, summarize_cross_background


def ensure_strain_registry_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strains (
            strain_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            official_name TEXT,
            active INTEGER,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strain_names (
            strain_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,              -- pyrat | cached_crossing
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (strain_id, name)
        )
    """)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _remember_name(conn: sqlite3.Connection, strain_id: str, name: str, source: str,
                   seen: str) -> None:
    conn.execute(
        """
        INSERT INTO strain_names (strain_id, name, source, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(strain_id, name) DO UPDATE SET
            last_seen = MAX(strain_names.last_seen, excluded.last_seen),
            first_seen = MIN(strain_names.first_seen, excluded.first_seen)
        """,
        (strain_id, name, source, seen, seen),
    )


def record_strains(conn: sqlite3.Connection, strains: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Store PyRAT's current strain list; return renamed and new strain ids."""
    ensure_strain_registry_schema(conn)
    stamp = _now()
    renamed: List[str] = []
    new = 0
    for strain in strains:
        if strain.get("id") is None or not strain.get("name"):
            continue
        strain_id, name = str(strain["id"]), strain["name"]
        row = conn.execute("SELECT name FROM strains WHERE strain_id = ?", (strain_id,)).fetchone()
        if row is None:
            new += 1
            conn.execute(
                "INSERT INTO strains (strain_id, name, official_name, active, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (strain_id, name, strain.get("official_name") or None,
                 None if strain.get("active") is None else int(bool(strain["active"])), stamp, stamp),
            )
        else:
            if row[0] != name:
                renamed.append(strain_id)
            conn.execute(
                "UPDATE strains SET name = ?, official_name = ?, active = ?, last_seen = ? "
                "WHERE strain_id = ?",
                (name, strain.get("official_name") or None,
                 None if strain.get("active") is None else int(bool(strain["active"])), stamp,
                 strain_id),
            )
        _remember_name(conn, strain_id, name, "pyrat", stamp)
    return {"renamed": renamed, "new": new}


def record_cached_names(conn: sqlite3.Connection) -> int:
    """Add names found in cached crossing rows to the history (as-fetched names)."""
    ensure_strain_registry_schema(conn)
    rows = conn.execute("""
        SELECT json_extract(raw_payload, '$.strain_id') AS sid, raw_strain_name AS name,
               MIN(updated_at) AS first, MAX(updated_at) AS last
        FROM cross_parents
        WHERE json_extract(raw_payload, '$.strain_id') IS NOT NULL AND COALESCE(raw_strain_name, '') != ''
        GROUP BY sid, name
        UNION ALL
        SELECT strain_id, strain_name, MIN(updated_at), MAX(updated_at) FROM cross_children
        WHERE strain_id IS NOT NULL AND COALESCE(strain_name, '') != ''
        GROUP BY strain_id, strain_name
    """).fetchall()
    for sid, name, first, last in rows:
        _remember_name(conn, str(sid), name, "cached_crossing", first or _now())
        if last and last != first:
            _remember_name(conn, str(sid), name, "cached_crossing", last)
    return len(rows)


def current_strain_name(conn: sqlite3.Connection, strain_id: Any) -> Optional[str]:
    if strain_id is None:
        return None
    try:
        row = conn.execute("SELECT name FROM strains WHERE strain_id = ?", (str(strain_id),)).fetchone()
    except sqlite3.OperationalError:  # registry not created yet
        return None
    return row[0] if row else None


def former_names(conn: sqlite3.Connection, strain_id: Any) -> List[str]:
    """Names this strain was seen with that differ from its current name."""
    current = current_strain_name(conn, strain_id)
    if current is None:
        return []
    return [r[0] for r in conn.execute(
        "SELECT name FROM strain_names WHERE strain_id = ? AND name != ? ORDER BY first_seen",
        (str(strain_id), current),
    )]


def stale_strain_ids(conn: sqlite3.Connection) -> List[str]:
    """Strains whose cached parent rows still carry a name other than the current one."""
    return [str(r[0]) for r in conn.execute("""
        SELECT DISTINCT json_extract(p.raw_payload, '$.strain_id')
        FROM cross_parents p
        JOIN strains s ON s.strain_id = CAST(json_extract(p.raw_payload, '$.strain_id') AS TEXT)
        WHERE COALESCE(p.raw_strain_name, '') != s.name
    """)]


def rederive_for_strains(conn: sqlite3.Connection, strain_ids: Iterable[str]) -> Dict[str, int]:
    """Re-parse cached parent rows of these strains from their current names
    and recompute the affected crosses' background summaries."""
    stats = {"parent_rows": 0, "crosses": 0}
    affected = set()
    for strain_id in strain_ids:
        current = current_strain_name(conn, strain_id)
        if current is None:
            continue
        parsed = parse_parent_background(current)
        for row in conn.execute(
            "SELECT id, cross_id FROM cross_parents WHERE CAST(json_extract(raw_payload, '$.strain_id') AS TEXT) = ?",
            (str(strain_id),),
        ).fetchall():
            conn.execute(
                """
                UPDATE cross_parents SET parsed_background_strains = ?, parsed_line_labels = ?,
                    parsed_transgenes = ?, parsed_mutant_alleles = ?, confidence = ?
                WHERE id = ?
                """,
                (json.dumps(parsed["background_strains"]), json.dumps(parsed["line_labels"]),
                 json.dumps(parsed["transgenes"]), json.dumps(parsed["mutant_backgrounds"]),
                 parsed["confidence"], row[0]),
            )
            stats["parent_rows"] += 1
            affected.add(row[1])
    for cross_id in affected:
        rows = [
            {
                "parsed_background_strains": json.loads(r[0] or "[]"),
                "parsed_line_labels": json.loads(r[1] or "[]"),
                "parsed_mutant_alleles": json.loads(r[2] or "[]"),
                "parsed_transgenes": json.loads(r[3] or "[]"),
            }
            for r in conn.execute(
                "SELECT parsed_background_strains, parsed_line_labels, parsed_mutant_alleles, "
                "parsed_transgenes FROM cross_parents WHERE cross_id = ?",
                (cross_id,),
            )
        ]
        summary = summarize_cross_background(rows)
        conn.execute(
            """
            UPDATE cross_background_summaries SET background_summary = ?, background_strains = ?,
                line_labels = ?, mutant_backgrounds = ?, transgenes = ?, has_mixed_background = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE cross_id = ?
            """,
            (summary["background_summary"], json.dumps(summary["background_strains"]),
             json.dumps(summary["line_labels"]), json.dumps(summary["mutant_backgrounds"]),
             json.dumps(summary["transgenes"]), int(summary["has_mixed_background"]), cross_id),
        )
        stats["crosses"] += 1
    return stats


def refresh_strain_registry(conn: sqlite3.Connection, client: Any) -> Dict[str, Any]:
    """Nightly step: fetch PyRAT's strain list, record history, re-derive renames."""
    result = record_strains(conn, client.strains())
    record_cached_names(conn)
    stale = stale_strain_ids(conn)
    rederived = rederive_for_strains(conn, stale)
    conn.commit()
    return {"strains": conn.execute("SELECT COUNT(*) FROM strains").fetchone()[0],
            "new": result["new"], "renamed": len(result["renamed"]),
            "stale_strains": len(stale), **rederived}
