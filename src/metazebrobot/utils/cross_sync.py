"""Incremental upkeep of the PyRAT crossing cache and tank origins.

Shared by scripts/refresh_cross_cache.py, scripts/resolve_tank_origins.py and
the nightly scripts/sync_cross_cache.py (see docs/tank_heritage_design.md).
PyRAT stays the source of truth; everything written here is a derived cache.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from .tank_origins import ensure_tank_origins_schema, record_search_days, resolve_tank_origins
from .lab_time import lab_today

CACHE_CHUNK_SIZE = 200  # crossings per _cache_cross_rows call


class SyncLockBusy(RuntimeError):
    """Another sync holds the lock."""


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Hold a non-blocking exclusive flock on ``path`` or raise SyncLockBusy."""
    handle = open(path, "a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncLockBusy(f"another cross-cache sync holds {path}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield
    finally:
        handle.close()  # releases the lock


def cache_in_chunks(
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    crossings: List[Dict[str, Any]],
) -> None:
    for start in range(0, len(crossings), CACHE_CHUNK_SIZE):
        cache_crossings(crossings[start:start + CACHE_CHUNK_SIZE])


def sync_recorded_crossings(
    conn: sqlite3.Connection,
    client: Any,
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    since: date,
    until: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Fetch all owners' crossings recorded since ``since`` and cache them.

    Always re-fetches (status changes and newly raised children arrive on old
    records), then marks the days as fetched so targeted searches skip them.
    """
    until = until or lab_today()
    crossings = client.crossings_recorded(since)
    conn.commit()  # release our read snapshot before another connection writes
    cache_in_chunks(cache_crossings, crossings)
    ensure_tank_origins_schema(conn)
    record_search_days(conn, since, until)
    conn.commit()
    return crossings


def missing_cached_ids(conn: sqlite3.Connection, crossings: List[Dict[str, Any]]) -> List[str]:
    """Fetched crossing ids that are not in ``crosses`` (a silent cache failure)."""
    cached = {str(r[0]) for r in conn.execute("SELECT cross_id FROM crosses")}
    return sorted({str(c["crossing_id"]) for c in crossings if c.get("crossing_id")} - cached)


def unplaced_parent_tanks(conn: sqlite3.Connection) -> List[str]:
    """Cached parent tanks whose producing cross is not cached."""
    return [str(r[0]) for r in conn.execute("""
        SELECT DISTINCT p.tank_id FROM cross_parents p
        WHERE p.tank_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM cross_children c WHERE c.tank_id = p.tank_id)
    """)]


def heritage_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    ensure_tank_origins_schema(conn)
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "crosses": q("SELECT COUNT(*) FROM crosses"),
        "parent tanks": q("SELECT COUNT(DISTINCT tank_id) FROM cross_parents"),
        "parent tanks placed": q("""
            SELECT COUNT(DISTINCT p.tank_id) FROM cross_parents p
            WHERE EXISTS (SELECT 1 FROM cross_children c WHERE c.tank_id = p.tank_id)
               OR EXISTS (SELECT 1 FROM tank_origins o WHERE o.tank_id = p.tank_id
                          AND o.status = 'split')
        """),
        "tank_origins": q("SELECT COUNT(*) FROM tank_origins"),
    }


def run_cross_sync(
    conn: sqlite3.Connection,
    client: Any,
    cache_crossings: Callable[[List[Dict[str, Any]]], None],
    days: int = 30,
    max_generations: int = 3,
    today: Optional[date] = None,
    include_open_tanks: bool = True,
) -> Dict[str, Any]:
    """Nightly job body: sync the recent window, then resolve unplaced parents
    and (by default) every open PyRAT tank, so the tanks page's heritage links
    resolve. Tanks already resolved cost no requests (cached in tank_origins).

    Raises RuntimeError if fetched crossings did not reach the cache.
    """
    today = today or lab_today()
    since = today - timedelta(days=days)
    before = heritage_counts(conn)

    crossings = sync_recorded_crossings(conn, client, cache_crossings, since, today)
    missing = missing_cached_ids(conn, crossings)
    if missing:
        raise RuntimeError(
            f"{len(missing)} fetched crossing(s) were not cached, e.g. {missing[:5]}")

    tanks = unplaced_parent_tanks(conn)
    open_unplaced: List[str] = []
    if include_open_tanks:
        placed = {str(r[0]) for r in conn.execute("SELECT DISTINCT tank_id FROM cross_children")}
        open_unplaced = [t for t in client.open_tank_ids() if t not in placed]
        tanks = list(dict.fromkeys(tanks + open_unplaced))
    resolver = resolve_tank_origins(conn, client, cache_crossings, tanks,
                                    max_generations=max_generations)
    return {
        "since": since,
        "fetched": len(crossings),
        "unplaced_tanks": len(tanks),
        "open_tanks_unplaced": len(open_unplaced),
        "resolver": resolver,
        "before": before,
        "after": heritage_counts(conn),
    }
