#!/usr/bin/env python
"""Cache PyRAT strain ancestry for strains the record walk can't place.

Step 2c of docs/tank_heritage_design.md. Fetches PyRAT's strain pedigree
(``backend/v1/reports/colony_pedigree``, a frontend internal; needs PyRAT
frontend credentials) once per strain and stores the ancestors in
``strain_ancestry``. Heritage reports what those ancestors name as
"inferred from strain ancestry", separate from record-derived backgrounds.
Cached strains are refetched after 90 days.

Reads PyRAT only. Writes only strain_ancestry / strain_ancestry_fetches.
Back up first, or use --db-path on a copy.

    # strains of parent tanks whose records give no background (default)
    pixi run python scripts/resolve_strain_ancestry.py --db-path copy.db --unresolved
    pixi run python scripts/resolve_strain_ancestry.py --db-path copy.db --strain-id 1145
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.api_server import _ensure_cross_parent_provenance_schema  # noqa: E402
from metazebrobot.utils.strain_ancestry import (  # noqa: E402
    StrainPedigreeClient,
    ensure_strain_ancestry_schema,
    fetch_strain_ancestry,
    needs_fetch,
    strains_needing_ancestry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--unresolved", action="store_true",
                        help="Strains of parent tanks with no record-derived background")
    target.add_argument("--strain-id", action="append")
    parser.add_argument("--pause", type=float, default=0.5)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    _ensure_cross_parent_provenance_schema(conn)
    ensure_strain_ancestry_schema(conn)
    conn.commit()

    if args.unresolved:
        todo = strains_needing_ancestry(conn)
    else:
        todo = [s for s in args.strain_id if needs_fetch(conn, s)]
    print(f"Strains needing a pedigree fetch: {len(todo)}")
    if not todo:
        return 0

    client = StrainPedigreeClient()
    stats = fetch_strain_ancestry(conn, client, todo, pause=args.pause)
    print(f"PyRAT pedigree requests: {client.requests}; "
          f"strains with recorded ancestors: {stats['with_ancestors']} of {stats['fetched']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
