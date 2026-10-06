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
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.api_server import _ensure_cross_parent_provenance_schema  # noqa: E402
from metazebrobot.utils.strain_ancestry import (  # noqa: E402
    StrainPedigreeClient,
    ensure_strain_ancestry_schema,
    needs_fetch,
    parse_strain_pedigree,
    store_strain_ancestry,
)
from metazebrobot.utils.tank_heritage import derive_tank_heritage  # noqa: E402


def unresolved_strain_ids(conn: sqlite3.Connection) -> list:
    strain_ids = set()
    tanks = [r[0] for r in conn.execute(
        "SELECT DISTINCT tank_id FROM cross_parents WHERE tank_id IS NOT NULL")]
    for tank_id in tanks:
        heritage = derive_tank_heritage(conn, tank_id)
        if heritage["backgrounds"] or heritage["mutant_backgrounds"]:
            continue
        strain_id = heritage["tank"].get("strain_id")
        if strain_id is not None:
            strain_ids.add(str(strain_id))
    return sorted(strain_ids, key=int)


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

    strain_ids = unresolved_strain_ids(conn) if args.unresolved else args.strain_id
    todo = [s for s in strain_ids if needs_fetch(conn, s)]
    print(f"Strains: {len(strain_ids)} selected, {len(todo)} need fetching")
    if not todo:
        return 0

    client = StrainPedigreeClient()
    with_ancestors = 0
    for index, strain_id in enumerate(todo):
        if index:
            time.sleep(args.pause)
        ancestors = parse_strain_pedigree(client.pedigree(strain_id), strain_id)
        store_strain_ancestry(conn, strain_id, ancestors)
        conn.commit()
        with_ancestors += bool(ancestors)

    print(f"PyRAT pedigree requests: {client.requests}; "
          f"strains with recorded ancestors: {with_ancestors} of {len(todo)}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
