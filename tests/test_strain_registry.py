"""Strain names by id with history; renames re-derive backgrounds (design step 6).

Scenario: strain 1532 was cached as plain "Casper_HHMI cohort", then renamed in
PyRAT to "Casper_HHMI [AB-C] DEC25" once its background was confirmed.
"""

import json
import sqlite3
import uuid

import pytest

from metazebrobot.api_server import (
    _ensure_cross_parent_provenance_schema,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils.strain_ancestry import store_strain_ancestry, strain_ancestry_backgrounds
from metazebrobot.utils.strain_registry import (
    current_strain_name,
    former_names,
    record_cached_names,
    record_strains,
    refresh_strain_registry,
    stale_strain_ids,
)
from metazebrobot.utils.tank_heritage import derive_tank_heritage

OLD = "Casper_HHMI cohort"
NEW = "Casper_HHMI [AB-C IC] MAR26"


class FakeStrainsClient:
    def __init__(self, strains):
        self._strains = strains

    def strains(self):
        return list(self._strains)


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE crosses (cross_id TEXT PRIMARY KEY, data TEXT)")
    _ensure_cross_parent_provenance_schema(conn)
    return conn


def cache_cross(conn):
    payload = {"crossing_id": 17697, "tanks": {
        "parents": [{"tank_id": 8547, "strain_name": OLD, "strain_id": 1574},
                    {"tank_id": 8548, "strain_name": OLD, "strain_id": 1574}],
        "children": [{"tank_id": 9000, "strain_name": OLD, "strain_id": 1574,
                      "date_of_birth": "2026-03-10T00:00:00"}]}}
    conn.execute("INSERT INTO crosses (cross_id, data) VALUES (?, ?)", ("17697", json.dumps(payload)))
    _upsert_cross_parent_provenance(conn, "17697", payload)


class TestRecordStrains:
    def test_new_then_renamed(self, conn):
        assert record_strains(conn, [{"id": 1574, "name": OLD}]) == {"renamed": [], "new": 1}
        assert record_strains(conn, [{"id": 1574, "name": NEW}]) == {"renamed": ["1574"], "new": 0}
        assert current_strain_name(conn, 1574) == NEW
        assert former_names(conn, 1574) == [OLD]

    def test_unchanged_name_is_not_a_rename(self, conn):
        record_strains(conn, [{"id": 1574, "name": NEW}])
        assert record_strains(conn, [{"id": 1574, "name": NEW}])["renamed"] == []
        assert former_names(conn, 1574) == []

    def test_cached_names_become_history(self, conn):
        cache_cross(conn)
        record_strains(conn, [{"id": 1574, "name": NEW}])
        record_cached_names(conn)
        assert former_names(conn, 1574) == [OLD]
        assert stale_strain_ids(conn) == ["1574"]

    def test_missing_registry_is_harmless(self):
        bare = sqlite3.connect(":memory:")
        assert current_strain_name(bare, 1) is None


class TestRenameReDerivation:
    def test_refresh_reparses_cached_rows_and_summary(self, conn):
        cache_cross(conn)
        summary = conn.execute(
            "SELECT background_strains FROM cross_background_summaries WHERE cross_id = '17697'").fetchone()
        assert json.loads(summary[0]) == []  # old name carried no background

        result = refresh_strain_registry(conn, FakeStrainsClient([{"id": 1574, "name": NEW}]))

        assert result["stale_strains"] == 1 and result["parent_rows"] == 2 and result["crosses"] == 1
        rows = conn.execute(
            "SELECT raw_strain_name, parsed_background_strains FROM cross_parents WHERE cross_id = '17697'"
        ).fetchall()
        assert {r[0] for r in rows} == {OLD}                     # as-fetched name kept
        assert {r[1] for r in rows} == {json.dumps(["AB"])}      # parsed from the current name
        summary = conn.execute(
            "SELECT background_strains, mutant_backgrounds FROM cross_background_summaries "
            "WHERE cross_id = '17697'").fetchone()
        assert json.loads(summary[0]) == ["AB"] and json.loads(summary[1]) == ["casper"]

    def test_heritage_shows_current_name_and_reads_its_label(self, conn):
        cache_cross(conn)
        refresh_strain_registry(conn, FakeStrainsClient([{"id": 1574, "name": NEW}]))

        h = derive_tank_heritage(conn, 9000)
        assert h["tank"]["strain_name"] == NEW
        assert h["tank"]["fetched_strain_name"] == OLD
        assert h["tank"]["former_strain_names"] == [OLD]
        assert h["label"]["incross"] is True and h["label"]["cohort_month"] == "2026-03"
        assert [b["value"] for b in h["backgrounds"]] == ["AB"]   # parents re-derived too
        assert {p["strain_name"] for p in h["producing_cross"]["parents"]} == {NEW}

    def test_strain_ancestry_uses_current_ancestor_names(self, conn):
        store_strain_ancestry(conn, 2000, [("1574", OLD, 1)])
        assert strain_ancestry_backgrounds(conn, 2000)["backgrounds"] == []
        refresh_strain_registry(conn, FakeStrainsClient([{"id": 1574, "name": NEW}]))
        assert [b["value"] for b in strain_ancestry_backgrounds(conn, 2000)["backgrounds"]] == ["AB"]


class TestProvenancePageShowsFormerNames:
    def test_formerly_is_rendered(self, client):
        import metazebrobot.api_server as api_server
        from metazebrobot.data.data_manager import data_manager

        cross_id = str(60000 + uuid.uuid4().int % 9000)
        strain_id = 100000 + uuid.uuid4().int % 9000
        api_server._cache_cross_rows([{"crossing_id": cross_id, "tanks": {
            "parents": [{"tank_id": int(cross_id) + 1, "strain_name": OLD, "strain_id": strain_id}]}}])
        with data_manager.get_connection() as conn:
            refresh_strain_registry(conn, FakeStrainsClient([{"id": strain_id, "name": NEW}]))

        page = client.get(f"/crosses/{cross_id}/provenance/").text
        assert NEW in page
        assert f"formerly {OLD}" in page
