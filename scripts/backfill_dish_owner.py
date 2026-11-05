#!/usr/bin/env python
"""Fill each dish's responsible_user (owner username) from evidence.

For a dish without one:

1. the user its free-text ``responsible`` names (PyRAT "Last First" or
   "First Last", ignoring case), because the text records who the dish was
   for, which can differ from the cross owner;
2. else the cross's PyRAT ``responsible_id`` from the cross cache;
3. else nothing, and the dish is listed.

Needs the users table (scripts/sync_users.py). See
docs/user_scoped_workflow_design.md, "Owners, screeners and names".

    pixi run python scripts/backfill_dish_owner.py --db-path /nvme1/zebrobot.db --dry-run
"""

import argparse
import json
import sqlite3
from collections import Counter


def _name_index(conn):
    index = {}
    for u in conn.execute("SELECT username, first_name, last_name, fullname FROM users"):
        for name in (u["fullname"], f"{u['first_name'] or ''} {u['last_name'] or ''}".strip()):
            if name:
                index.setdefault(" ".join(name.lower().split()), set()).add(u["username"])
    return index


def plan(conn):
    """[(dish_id, username or None, how)] for dishes without an owner."""
    names = _name_index(conn)
    by_id = {r["pyrat_userid"]: r["username"] for r in conn.execute("SELECT pyrat_userid, username FROM users")}
    out = []
    for d in conn.execute(
            """SELECT d.dish_id, d.responsible, json_extract(c.data, '$.responsible_id') AS rid
               FROM dishes d LEFT JOIN crosses c ON c.cross_id = d.cross_id
               WHERE json_extract(d.data, '$.responsible_user') IS NULL ORDER BY d.dish_id"""):
        named = names.get(" ".join((d["responsible"] or "").lower().split()), set())
        if len(named) == 1:
            out.append((d["dish_id"], next(iter(named)), "named in responsible"))
        elif d["rid"] is not None and d["rid"] in by_id:
            out.append((d["dish_id"], by_id[d["rid"]], "cross owner"))
        else:
            out.append((d["dish_id"], None, f"no match for {d['responsible']!r}"))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        found = plan(conn)
        for dish_id, username, how in found:
            if username is None:
                print(f"unmatched {dish_id}: {how}")
            elif not args.dry_run:
                conn.execute("UPDATE dishes SET data = json_set(data, '$.responsible_user', ?) "
                             "WHERE dish_id = ?", (username, dish_id))
        tally = Counter((u, how) for _, u, how in found if u)
        for (username, how), n in sorted(tally.items()):
            print(f"{n:4d} -> {username} ({how})")
        print(f"{sum(tally.values())} dish(es) {'would get' if args.dry_run else 'got'} an owner; "
              f"{sum(1 for _, u, _ in found if u is None)} unmatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
