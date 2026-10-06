"""Record-derived tank heritage (docs/tank_heritage_design.md step 2a).

Fixtures mirror real PyRAT cases checked on 2026-10-06: cross 17211 (AB
Casper incross -> [AB-C] DEC25), cross 17697 ([AB-C] DEC25 incross ->
[AB-C IC] MAR26), and cross 14979 (Casper_HHMI x Tg(gfap:b-ARK) outcross).
"""

import json
import sqlite3

import pytest

from metazebrobot.api_server import (
    _ensure_cross_parent_provenance_schema,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils.tank_heritage import derive_tank_heritage, parse_strain_label


def tank(tank_id, strain, generation="F1", dob=None, **extra):
    row = {"tank_id": tank_id, "strain_name": strain, "generation": generation, **extra}
    if dob:
        row["date_of_birth"] = f"{dob}T00:00:00"
    return row


def cross(cross_id, parents, children):
    return {
        "crossing_id": cross_id,
        "date_of_set_up": "2026-03-09T08:00:00",
        "tanks": {"parents": parents, "children": children},
    }


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE crosses (cross_id TEXT PRIMARY KEY, data TEXT)")
    _ensure_cross_parent_provenance_schema(conn)
    return conn


def cache(conn, *payloads):
    for payload in payloads:
        conn.execute("INSERT OR REPLACE INTO crosses (cross_id, data) VALUES (?, ?)",
                     (str(payload["crossing_id"]), json.dumps(payload)))
        _upsert_cross_parent_provenance(conn, str(payload["crossing_id"]), payload)


DEC25 = "Casper_HHMI [AB-C] DEC25"
MAR26_IC = "Casper_HHMI [AB-C IC] MAR26"
CROSS_17211 = cross(17211,
                    [tank(6485, "AB Casper_HHMI", strain_id=14), tank(6486, "AB Casper_HHMI", strain_id=14)],
                    [tank(8130, DEC25, dob="2025-12-23", strain_id=1532)])
CROSS_17697 = cross(17697,
                    [tank(8129, DEC25, strain_id=1532), tank(8130, DEC25, strain_id=1532)],
                    [tank(8547, MAR26_IC, dob="2026-03-10", strain_id=1574)])
CROSS_14979 = cross(14979,
                    [tank(6190, "Casper_HHMI", "F2", strain_id=20), tank(4014, "Tg(gfap:b-ARK)", "F2", strain_id=786)],
                    [tank(6643, "Tg(gfap:b-ARK)", "F3", dob="2025-02-26", strain_id=786)])


class TestParseStrainLabel:
    def test_incross_cohort_label(self):
        assert parse_strain_label("Casper_HHMI [AB-C IC] MAR26") == {
            "backgrounds": ["AB"], "mutant_backgrounds": ["casper"],
            "incross": True, "cohort_month": "2026-03",
        }

    def test_missing_ic_means_unstated_not_outcross(self):
        label = parse_strain_label("Casper_HHMI [WIK-C] JAN26")
        assert label["backgrounds"] == ["WIK"]
        assert label["incross"] is None
        assert label["cohort_month"] == "2026-01"

    def test_names_without_shorthand_have_no_label(self):
        assert parse_strain_label("Tg(gfap:b-ARK)") is None
        assert parse_strain_label("AB Casper_HHMI") is None
        assert parse_strain_label(None) is None


class TestDeriveTankHeritage:
    def test_incross_cohort_matches_label(self, conn):
        cache(conn, CROSS_17211, CROSS_17697)
        h = derive_tank_heritage(conn, 8547)

        assert h["producing_cross"]["cross_id"] == "17697"
        assert h["producing_cross"]["cross_type"] == "incross"
        assert h["cohort_month"] == "2026-03"
        assert [b["value"] for b in h["backgrounds"]] == ["AB"]
        assert h["backgrounds"][0]["sources"] == [
            "parents in cross 17697",
            "generation 2 (cross 17211)",  # the DEC25 parents' own AB Casper incross
        ]
        assert h["generations_traced"] == 2
        assert [m["value"] for m in h["mutant_backgrounds"]] == ["casper"]
        assert h["label_checks"] == {"incross": True, "cohort_month": True, "backgrounds": True}
        assert h["flags"] == []

    def test_unstated_incross_is_not_checked(self, conn):
        cache(conn, CROSS_17211)
        h = derive_tank_heritage(conn, 8130)
        assert h["producing_cross"]["cross_type"] == "incross"
        assert h["label_checks"]["incross"] is None
        assert h["flags"] == []

    def test_outcross_picks_up_parent_backgrounds(self, conn):
        cache(conn, CROSS_14979)
        h = derive_tank_heritage(conn, 6643)
        assert h["producing_cross"]["cross_type"] == "outcross"
        assert [m["value"] for m in h["mutant_backgrounds"]] == ["casper"]
        assert h["label"] is None

    def test_tank_without_producing_cross_has_no_derived_background(self, conn):
        cache(conn, CROSS_17697)  # 8130 appears only as a parent here
        h = derive_tank_heritage(conn, 8130)
        assert h["producing_cross"] is None
        assert h["backgrounds"] == []
        assert h["tank"]["strain_name"] == DEC25
        # The name still suggests AB + casper, but only as a separate reading.
        assert h["name_only"] == {"backgrounds": ["AB"], "mutant_backgrounds": ["casper"]}

    def test_records_win_and_label_disagreements_are_flagged(self, conn):
        mislabeled = cross(
            9001,
            [tank(1, "Casper_HHMI", strain_id=20), tank(2, "Tg(elavl3:GCaMP6s)", strain_id=99)],
            [tank(3, MAR26_IC, dob="2026-04-02", strain_id=1574)],
        )
        cache(conn, mislabeled)
        h = derive_tank_heritage(conn, 3)

        assert h["producing_cross"]["cross_type"] == "outcross"
        assert [b["value"] for b in h["backgrounds"]] == []  # records show no AB
        assert h["name_only"]["backgrounds"] == ["AB"]        # only the name claims it
        assert h["label_checks"] == {"incross": False, "cohort_month": False, "backgrounds": None}
        assert len(h["flags"]) == 2

    def test_single_parent_tank_cross_is_incross(self, conn):
        cache(conn, cross(9002, [tank(10, "WIK Casper_HHMI", strain_id=31)],
                          [tank(11, "WIK Casper_HHMI", dob="2026-03-08", strain_id=31)]))
        assert derive_tank_heritage(conn, 11)["producing_cross"]["cross_type"] == "incross"

    def test_unknown_parent_strain_leaves_cross_type_unknown(self, conn):
        cache(conn, cross(9003, [{"tank_id": 20}, tank(21, "AB", strain_id=29)],
                          [tank(22, "AB", dob="2026-03-08", strain_id=29)]))
        assert derive_tank_heritage(conn, 22)["producing_cross"]["cross_type"] is None
