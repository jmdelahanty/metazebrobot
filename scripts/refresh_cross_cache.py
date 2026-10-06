#!/usr/bin/env python
"""Refill the local PyRAT crossing cache with full parent/child tank fields.

Step 1b of docs/tank_heritage_design.md. Two modes, both writing through the
app's own merge + provenance upsert (``_cache_cross_rows``), so cached payloads
are merged, never truncated:

- ``--refetch-cached``: re-fetch every crossing already in ``crosses`` with
  CROSSING_FIELDS / CROSSING_TANK_FIELDS (batched by ``crossing_id``).
- ``--sync-months N``: fetch every owner's crossings recorded in the last N
  months, so producing crosses for parent tanks are local even when another
  person owns them.

Reads PyRAT only (api/v3, GET). Writes only the MetaZebrobot SQLite cache
tables (crosses, cross_parents, cross_children, cross_background_summaries).
Back up the database first, or point --db-path at a copy to preview.

    pixi run python scripts/refresh_cross_cache.py --db-path /path/to/copy.db \\
        --refetch-cached --sync-months 12
"""

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.api_server import (  # noqa: E402
    CROSSING_FIELDS,
    CROSSING_TANK_FIELDS,
    _cache_cross_rows,
    _ensure_cross_parent_provenance_schema,
)
from metazebrobot.data.data_manager import data_manager  # noqa: E402
from metazebrobot.utils.pyrat_api_client import PAGE_SIZE, PyratApiClient  # noqa: E402
from metazebrobot.utils.tank_origins import record_search_days  # noqa: E402

def counts(conn: sqlite3.Connection) -> Dict[str, int]:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "crosses": q("SELECT COUNT(*) FROM crosses"),
        "parents": q("SELECT COUNT(*) FROM cross_parents"),
        "parents_with_strain": q(
            "SELECT COUNT(*) FROM cross_parents WHERE COALESCE(raw_strain_name, '') != ''"
        ),
        "children": q("SELECT COUNT(*) FROM cross_children"),
        "children_with_dob": q(
            "SELECT COUNT(*) FROM cross_children WHERE COALESCE(date_of_birth, '') != ''"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True, help="SQLite database to update")
    parser.add_argument("--refetch-cached", action="store_true")
    parser.add_argument("--sync-months", type=int, default=0, help="All-owner window; 0 = skip")
    parser.add_argument("--pause", type=float, default=0.5, help="Seconds between PyRAT requests")
    args = parser.parse_args()
    if not args.refetch_cached and not args.sync_months:
        parser.error("choose --refetch-cached and/or --sync-months N")

    data_manager.database_path = Path(args.db_path)
    with data_manager.get_connection() as conn:
        _ensure_cross_parent_provenance_schema(conn)
        conn.commit()
        before = counts(conn)
        cached_ids = sorted(int(r[0]) for r in conn.execute("SELECT cross_id FROM crosses")
                            if str(r[0]).isdigit())

    pyrat = PyratApiClient(CROSSING_FIELDS, CROSSING_TANK_FIELDS, pause=args.pause)
    fetched: Dict[Any, Dict[str, Any]] = {}
    if args.refetch_cached:
        for crossing in pyrat.crossings_by_ids(cached_ids):
            fetched[crossing.get("crossing_id")] = crossing
        print(f"Re-fetched {len(fetched)} of {len(cached_ids)} cached crossings")
    if args.sync_months:
        since = date.today() - timedelta(days=round(args.sync_months * 30.44))
        window = pyrat.crossings_recorded(since)
        print(f"Fetched {len(window)} crossings recorded since {since} (all owners)")
        for crossing in window:
            fetched[crossing.get("crossing_id")] = crossing

    rows = list(fetched.values())
    for start in range(0, len(rows), PAGE_SIZE):
        _cache_cross_rows(rows[start:start + PAGE_SIZE])

    with data_manager.get_connection() as conn:
        if args.sync_months:
            # Later targeted searches (resolve_tank_origins) skip these days.
            record_search_days(conn, since, date.today())
            conn.commit()
        after = counts(conn)
    print(f"PyRAT requests: {pyrat.requests}")
    print(f"{'':22}{'before':>8}{'after':>8}")
    for key in before:
        print(f"{key:22}{before[key]:>8}{after[key]:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
