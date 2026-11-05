#!/usr/bin/env python
"""Fill screening_steps.screened_by from evidence only.

A step with no screener gets one when every fish observation recorded
against it (fish placed from that step with a result) names the same,
non-empty observer. Every other step stays blank: nothing is guessed. See
docs/user_scoped_workflow_design.md, "Owners, screeners and names".

Dishes load their steps from screening_steps, so that column is the record.

    pixi run python scripts/backfill_screened_by.py --db-path /nvme1/zebrobot.db --dry-run
"""

import argparse
import sqlite3


def candidates(conn):
    """(dish_id, screening_datetime, observer) for steps the evidence settles."""
    return [tuple(r) for r in conn.execute(
        """SELECT s.dish_id, s.screening_datetime, MIN(o.observed_by)
           FROM screening_steps s
           JOIN fish_screening_observations o
             ON o.source_dish_id = s.dish_id AND o.screening_datetime = s.screening_datetime
           WHERE s.screened_by IS NULL
           GROUP BY s.dish_id, s.screening_datetime
           HAVING COUNT(DISTINCT COALESCE(o.observed_by, '')) = 1 AND MIN(o.observed_by) <> ''
           ORDER BY s.dish_id, s.screening_datetime""")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with sqlite3.connect(args.db_path) as conn:
        found = candidates(conn)
        for dish_id, step, observer in found:
            print(f"{dish_id} {step}: {observer}")
            if not args.dry_run:
                conn.execute("UPDATE screening_steps SET screened_by = ? WHERE dish_id = ? "
                             "AND screening_datetime = ? AND screened_by IS NULL", (observer, dish_id, step))
        print(f"{len(found)} step(s) {'would be' if args.dry_run else ''} filled".replace("  ", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
