#!/usr/bin/env python
"""Sync PyRAT users into MetaZebrobot's users table (names, picker members).

Fetches every active and inactive user the PyRAT account can see and
refreshes their names; local emails and picker membership are kept.
``--mark-lab OWNER`` adds that owner's lab members (everyone Responsible for
an open tank the owner owns) to the user picker; nobody is ever removed.

Reads PyRAT only (api/v3, GET). Writes only the users table.

    pixi run python scripts/sync_users.py --db-path /nvme1/zebrobot.db --mark-lab <lab-owner-username>
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.data import users  # noqa: E402
from metazebrobot.reports.f0_without_f1 import lab_members  # noqa: E402
from metazebrobot.data.fish_observations import utc_now  # noqa: E402
from metazebrobot.utils.pyrat_api_client import PyratApiClient  # noqa: E402


def sync(conn, client, mark_lab=None):
    """Refresh users from PyRAT; returns (users synced, lab members marked)."""
    users.ensure_schema(conn)
    stamp = utc_now()
    synced = sum(users.upsert_from_pyrat(conn, client.users(users.PYRAT_FIELDS, status), status, stamp)
                 for status in ("active", "inactive"))
    marked = 0
    if mark_lab:
        active = {r["pyrat_userid"] for r in conn.execute("SELECT pyrat_userid FROM users WHERE status = 'active'")}
        marked = users.mark_app_users(conn, [m["userid"] for m in lab_members(client, mark_lab)
                                             if m["userid"] in active])
    conn.commit()
    return synced, marked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--mark-lab", help="PyRAT username of a lab owner")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between PyRAT requests")
    args = parser.parse_args(argv)
    client = PyratApiClient([], [], pause=args.pause)
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        synced, marked = sync(conn, client, args.mark_lab)
        picker = [users.display_name(u) for u in users.app_users(conn)]
    print(f"{synced} users synced; {marked} lab members in the picker ({len(picker)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
