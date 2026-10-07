#!/usr/bin/env python
"""Refresh PyRAT strain names and re-derive backgrounds for renamed strains.

Step 6 of docs/tank_heritage_design.md (the nightly sync runs the same step).
Fetches PyRAT's strain list (api/v3/strains, ~9 requests), records name
history in ``strain_names`` (including names found in cached crossings),
and re-parses cached parent rows whose strain now has a different name.

Reads PyRAT only. Writes only strains / strain_names and the parsed columns
of cross_parents / cross_background_summaries. Back up first, or use a copy.

    pixi run python scripts/refresh_strain_registry.py --db-path copy.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.api_server import (  # noqa: E402
    CROSSING_FIELDS,
    CROSSING_TANK_FIELDS,
    _ensure_cross_parent_provenance_schema,
)
from metazebrobot.utils.pyrat_api_client import PyratApiClient  # noqa: E402
from metazebrobot.utils.strain_registry import refresh_strain_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    _ensure_cross_parent_provenance_schema(conn)
    conn.commit()
    client = PyratApiClient(CROSSING_FIELDS, CROSSING_TANK_FIELDS)
    result = refresh_strain_registry(conn, client)
    conn.close()
    print(f"PyRAT requests: {client.requests}")
    print("Strain registry:", ", ".join(f"{k}={v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
