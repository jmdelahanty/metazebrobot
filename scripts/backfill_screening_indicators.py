#!/usr/bin/env python
"""Match every existing screening step's indicators to dish constructs.

Dry run by default: opens the database read-only and prints a Markdown review
report of what would be written to screening_step_indicators. With --apply,
rewrites the rows for every dish that has screening steps (back up first).
New and edited steps are matched automatically on save; this script covers
steps saved before matching existed.

    pixi run python scripts/backfill_screening_indicators.py --db-path /nvme1/zebrobot.db
    pixi run python scripts/backfill_screening_indicators.py --db-path /nvme1/zebrobot.db --apply
"""

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from metazebrobot.data.data_manager import DataManager  # noqa: E402


def connect(db_path: Path, apply: bool) -> sqlite3.Connection:
    uri = f"file:{db_path}" + ("" if apply else "?mode=ro")
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def report(rows, steps) -> str:
    by_step = {}
    for row in rows:
        by_step.setdefault((row["dish_id"], row["screening_datetime"]), []).append(row)
    out = ["# Screening indicator backfill (dry run)", "",
           f"{len(steps)} steps on {len({s['dish_id'] for s in steps})} dishes, {len(rows)} indicator rows.", ""]
    counts = Counter((r["kind"], r["match_confidence"]) for r in rows)
    out += ["| kind | confidence | rows |", "|---|---|---|"]
    out += [f"| {k} | {c} | {n} |" for (k, c), n in sorted(counts.items())]
    out += ["", "| dish | step | dpf | raw indicators | pigment box | → kind | construct | rule | confidence | note |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for step in steps:
        matches = by_step.get((step["dish_id"], step["screening_datetime"]), [])
        first = True
        for m in matches or [None]:
            lead = (f"| {step['dish_id']} | {step['screening_datetime']} | {step['dpf_screened']} | "
                    f"`{step['indicators_screened']}` | {bool(step['pigment_screened'])} "
                    if first else "| | | | | ")
            first = False
            if m is None:
                out.append(lead + "| (none) | | | | |")
            else:
                out.append(lead + f"| {m['kind']} | {m['dish_construct'] or ''} | {m['match_rule']} | "
                           f"{m['match_confidence']} | {m['note'] or ''} |")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Write the rows (default: report only)")
    args = parser.parse_args()

    dm = DataManager()  # only its matching helpers; no initialize()
    with connect(args.db_path, args.apply) as conn:
        steps = conn.execute(
            "SELECT dish_id, screening_datetime, dpf_screened, indicators_screened, pigment_screened "
            "FROM screening_steps ORDER BY dish_id, screening_datetime"
        ).fetchall()
        dish_ids = sorted({s["dish_id"] for s in steps})
        if args.apply:
            written = sum(dm.derive_step_indicators(conn, d) for d in dish_ids)
            conn.commit()
            print(f"Wrote {written} indicator rows for {len(dish_ids)} dishes.")
            return 0
        rows = [r for d in dish_ids for r in dm.step_indicator_matches(conn, d)]
        sys.stdout.write(report(rows, steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
