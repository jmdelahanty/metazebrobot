#!/usr/bin/env python
"""Resolve producing crosses for parent tanks the cache can't place yet.

Step 2b of docs/tank_heritage_design.md. For each starting tank (and its
ancestors, up to --max-generations), follows PyRAT tank history through splits
(SeparateEvent source tanks) and, for tanks released straight from an uncached
cross, searches crossings recorded just before the tank's date of birth.
Results go into ``tank_origins`` and the crossing cache, so each tank is
fetched at most once.

Reads PyRAT only (api/v3, GET). Writes only MetaZebrobot cache tables
(tank_origins, crosses, cross_parents, cross_children,
cross_background_summaries). Back up first, or use --db-path on a copy.

    pixi run python scripts/resolve_tank_origins.py --db-path copy.db --cross-id 19220
    pixi run python scripts/resolve_tank_origins.py --db-path copy.db --all-parents
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.api_server import (  # noqa: E402
    CROSSING_FIELDS,
    CROSSING_TANK_FIELDS,
    _cache_cross_rows,
    _ensure_cross_parent_provenance_schema,
)
from metazebrobot.data.data_manager import data_manager  # noqa: E402
from metazebrobot.utils.pyrat_api_client import PyratApiClient  # noqa: E402
from metazebrobot.utils.tank_origins import resolve_tank_origins  # noqa: E402


def counts(conn):
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--cross-id", action="append", help="Resolve this cross's parent tanks")
    target.add_argument("--tank-id", action="append", help="Resolve these tanks")
    target.add_argument("--all-parents", action="store_true",
                        help="Every cached parent tank without a producing cross")
    parser.add_argument("--max-generations", type=int, default=3)
    parser.add_argument("--pause", type=float, default=0.3)
    args = parser.parse_args()

    data_manager.database_path = Path(args.db_path)
    with data_manager.get_connection() as conn:
        _ensure_cross_parent_provenance_schema(conn)
        conn.commit()
        if args.cross_id:
            tanks = [r[0] for r in conn.execute(
                f"SELECT tank_id FROM cross_parents WHERE cross_id IN "
                f"({','.join('?' * len(args.cross_id))})", args.cross_id)]
        elif args.tank_id:
            tanks = args.tank_id
        else:
            tanks = [r[0] for r in conn.execute("""
                SELECT DISTINCT p.tank_id FROM cross_parents p
                WHERE p.tank_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM cross_children c WHERE c.tank_id = p.tank_id)
            """)]
        before = counts(conn)

        client = PyratApiClient(CROSSING_FIELDS, CROSSING_TANK_FIELDS, pause=args.pause)
        stats = resolve_tank_origins(conn, client, _cache_cross_rows, tanks,
                                     max_generations=args.max_generations)
        after = counts(conn)

    print(f"Starting tanks: {len(tanks)}; PyRAT requests: {client.requests}")
    print("Resolver:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"{'':22}{'before':>8}{'after':>8}")
    for key in before:
        print(f"{key:22}{before[key]:>8}{after[key]:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
