#!/usr/bin/env python
"""Nightly incremental sync of the PyRAT crossing cache and tank origins.

Keeps docs/tank_heritage_design.md's derived cache current without manual
runs. Idempotent; safe to re-run at any time:

1. Fetch every owner's crossings recorded in the last --days days (status
   changes and newly raised children land on recent records) and cache them
   through the app's merge + provenance upsert (``_cache_cross_rows``).
2. Resolve parent tanks that still have no producing cross, plus every open
   PyRAT tank (so the tanks page's heritage links resolve), via tank history
   splits and targeted date-of-birth searches. Tanks already resolved cost no
   requests; negative results are retried after RETRY_AFTER_DAYS.
3. Refresh PyRAT strain names (``strains``/``strain_names``) and re-derive
   backgrounds for cached rows of renamed strains. Best-effort.
4. Fetch strain ancestry (step 2c) for strains that are new or older than
   REFRESH_AFTER_DAYS and used by a tank whose records give no background.
   Needs PyRAT frontend credentials; if they are missing or the (unofficial)
   pedigree endpoint fails, this step is skipped with a warning and the run
   still succeeds. ``--skip-ancestry`` turns it off.

Holds an exclusive lock (default: <db-path>.cross-sync.lock) so runs never
overlap; exits 75 if another run holds it, 1 on any other failure.

Reads PyRAT only (api/v3, GET). Writes only MetaZebrobot cache tables.

    pixi run python scripts/sync_cross_cache.py --db-path /nvme1/zebrobot.db
"""

import argparse
import os
import sys
import time
import traceback
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
from metazebrobot.utils.cross_sync import SyncLockBusy, exclusive_lock, run_cross_sync  # noqa: E402
from metazebrobot.utils.pyrat_api_client import PyratApiClient  # noqa: E402
from metazebrobot.utils.strain_registry import refresh_strain_registry  # noqa: E402
from metazebrobot.utils.strain_ancestry import (  # noqa: E402
    StrainPedigreeClient,
    fetch_strain_ancestry,
    strains_needing_ancestry,
)

EXIT_LOCKED = 75  # EX_TEMPFAIL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", default=os.getenv("METAZEBROBOT_DB_PATH"),
                        help="SQLite database (default: $METAZEBROBOT_DB_PATH)")
    parser.add_argument("--days", type=int, default=30,
                        help="Re-sync crossings recorded in the last N days")
    parser.add_argument("--max-generations", type=int, default=3)
    parser.add_argument("--pause", type=float, default=0.3, help="Seconds between PyRAT requests")
    parser.add_argument("--lock-file", help="Default: <db-path>.cross-sync.lock")
    parser.add_argument("--skip-open-tanks", action="store_true",
                        help="Only resolve unplaced parent tanks, not all open tanks")
    parser.add_argument("--skip-ancestry", action="store_true",
                        help="Do not fetch strain ancestry for new strains")
    args = parser.parse_args()
    if not args.db_path:
        parser.error("--db-path or METAZEBROBOT_DB_PATH is required")
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    lock_path = Path(args.lock_file or f"{db_path}.cross-sync.lock")

    started = time.monotonic()
    try:
        with exclusive_lock(lock_path):
            data_manager.database_path = db_path
            client = PyratApiClient(CROSSING_FIELDS, CROSSING_TANK_FIELDS, pause=args.pause)
            with data_manager.get_connection() as conn:
                _ensure_cross_parent_provenance_schema(conn)
                conn.commit()
                result = run_cross_sync(conn, client, _cache_cross_rows, days=args.days,
                                        max_generations=args.max_generations,
                                        include_open_tanks=not args.skip_open_tanks)
                strains = sync_strain_registry(conn, client)
                ancestry = None if args.skip_ancestry else sync_strain_ancestry(conn, args.pause)
    except SyncLockBusy as exc:
        print(f"Skipped: {exc}", file=sys.stderr)
        return EXIT_LOCKED
    except Exception:  # noqa: BLE001 - log to the journal and fail the unit
        traceback.print_exc()
        print("Cross-cache sync failed", file=sys.stderr)
        return 1

    print(f"Cross-cache sync of {db_path} ({time.monotonic() - started:.0f}s, "
          f"{client.requests} PyRAT requests)")
    print(f"Window: crossings recorded since {result['since']}: {result['fetched']} fetched")
    print(f"Tanks checked: {result['unplaced_tanks']} "
          f"(incl. {result['open_tanks_unplaced']} open tanks without a cached producing cross)")
    print("Resolver:", ", ".join(f"{k}={v}" for k, v in result["resolver"].items()))
    print(f"{'':22}{'before':>8}{'after':>8}")
    for key, before in result["before"].items():
        print(f"{key:22}{before:>8}{result['after'][key]:>8}")
    print(f"Strain registry: {strains}")
    if ancestry is not None:
        print(f"Strain ancestry: {ancestry}")
    return 0


def sync_strain_registry(conn, client) -> str:
    """Best-effort: strain names and rename re-derivation; never fails the run."""
    try:
        result = refresh_strain_registry(conn, client)
        return ", ".join(f"{k}={v}" for k, v in result.items())
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: strain registry refresh skipped: {exc}", file=sys.stderr)
        return f"skipped ({type(exc).__name__})"


def sync_strain_ancestry(conn, pause: float) -> str:
    """Best-effort step 3; never fails the run."""
    try:
        todo = strains_needing_ancestry(conn)
        if not todo:
            return "no new strains need a pedigree"
        client = StrainPedigreeClient()
        stats = fetch_strain_ancestry(conn, client, todo, pause=pause)
        return (f"{stats['fetched']} strain(s) fetched, "
                f"{stats['with_ancestors']} with recorded ancestors")
    except Exception as exc:  # noqa: BLE001 - optional, unofficial endpoint
        print(f"WARNING: strain ancestry skipped: {exc}", file=sys.stderr)
        return f"skipped ({type(exc).__name__})"


if __name__ == "__main__":
    sys.exit(main())
