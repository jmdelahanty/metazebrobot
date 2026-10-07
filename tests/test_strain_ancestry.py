"""Strain ancestry as a separate, last-resort background layer (design step 2c).

The pedigree payload mirrors PyRAT's colony_pedigree report for
Tg(ubi:Switch) (1145), including the real quirks: a Casper_HHMI <-> AB
Casper_HHMI cycle, a SENTINEL placeholder, and a parent without a name.
"""

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from metazebrobot.api_server import (
    _ensure_cross_parent_provenance_schema,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils import strain_ancestry
from metazebrobot.utils.strain_ancestry import (
    fetch_strain_ancestry,
    needs_fetch,
    parse_strain_pedigree,
    store_strain_ancestry,
    strain_ancestry_backgrounds,
    strains_needing_ancestry,
)
from metazebrobot.utils.tank_heritage import derive_tank_heritage

PEDIGREE_1145 = {"pedigree": {"nodes": [
    {"id": 1145, "name": "Tg(ubi:Switch)", "parents": [
        {"parent_id": 20, "parent_name": "Casper_HHMI", "strain_id": 1145},
        {"parent_id": 14, "parent_name": "AB Casper_HHMI", "strain_id": 1145}]},
    {"id": 20, "name": "Casper_HHMI", "parents": [
        {"parent_id": 14, "parent_name": "AB Casper_HHMI", "strain_id": 20},
        {"parent_id": 1306, "parent_name": "Casper_UVA", "strain_id": 20}]},
    {"id": 14, "name": "AB Casper_HHMI", "parents": [
        {"parent_id": 20, "parent_name": "Casper_HHMI", "strain_id": 14},
        {"parent_id": 29, "parent_name": "AB", "strain_id": 14},
        {"parent_id": 626, "parent_name": "SENTINEL", "strain_id": 14}]},
    {"id": 29, "name": "AB", "parents": [{"parent_id": 1, "strain_id": 29}]},
]}}


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE crosses (cross_id TEXT PRIMARY KEY, data TEXT)")
    _ensure_cross_parent_provenance_schema(conn)
    return conn


class TestParseStrainPedigree:
    def test_walks_ancestors_with_shallowest_depth(self):
        ancestors = {a_id: (name, depth) for a_id, name, depth in parse_strain_pedigree(PEDIGREE_1145, 1145)}
        assert ancestors == {
            "20": ("Casper_HHMI", 1),
            "14": ("AB Casper_HHMI", 1),
            "1306": ("Casper_UVA", 2),
            "29": ("AB", 2),
        }

    def test_cycles_placeholders_and_nameless_parents_are_dropped(self):
        names = [name for _, name, _ in parse_strain_pedigree(PEDIGREE_1145, 1145)]
        assert "SENTINEL" not in names
        assert "Tg(ubi:Switch)" not in names  # no cycle back to itself
        assert len(names) == len(set(names))

    def test_strain_without_recorded_parents(self):
        payload = {"pedigree": {"nodes": [{"id": 1130, "name": "Tg(elavl3:GRAB-Ado1.0)"}]}}
        assert parse_strain_pedigree(payload, 1130) == []


class TestStoredAncestry:
    def test_backgrounds_from_ancestor_names(self, conn):
        store_strain_ancestry(conn, 1145, parse_strain_pedigree(PEDIGREE_1145, 1145))
        result = strain_ancestry_backgrounds(conn, 1145)
        assert result["fetched"] is True
        assert [b["value"] for b in result["backgrounds"]] == ["AB"]
        assert [m["value"] for m in result["mutant_backgrounds"]] == ["casper"]
        assert "strain ancestry: AB" in result["backgrounds"][0]["sources"]

    def test_refetch_after_interval(self, conn, monkeypatch):
        assert needs_fetch(conn, 1145)
        store_strain_ancestry(conn, 1145, [])
        assert not needs_fetch(conn, 1145)
        later = datetime.now() + timedelta(days=strain_ancestry.REFRESH_AFTER_DAYS + 1)

        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return later

        monkeypatch.setattr(strain_ancestry, "datetime", Later)
        assert needs_fetch(conn, 1145)

    def test_missing_table_is_harmless(self):
        bare = sqlite3.connect(":memory:")
        assert strain_ancestry_backgrounds(bare, 1)["fetched"] is False


class TestHeritageUsesAncestryOnlyAsInference:
    def cache(self, conn, payload):
        conn.execute("INSERT INTO crosses (cross_id, data) VALUES (?, ?)",
                     (str(payload["crossing_id"]), json.dumps(payload)))
        _upsert_cross_parent_provenance(conn, str(payload["crossing_id"]), payload)

    def test_imported_line_gets_inferred_not_record_background(self, conn):
        # Producing cross whose parents are the same un-backgrounded line.
        self.cache(conn, {"crossing_id": 1, "tanks": {
            "parents": [{"tank_id": 10, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145}],
            "children": [{"tank_id": 11, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145,
                          "date_of_birth": "2025-08-12T00:00:00"}]}})
        store_strain_ancestry(conn, 1145, parse_strain_pedigree(PEDIGREE_1145, 1145))

        h = derive_tank_heritage(conn, 11)
        assert h["backgrounds"] == [] and h["mutant_backgrounds"] == []
        assert [b["value"] for b in h["strain_ancestry"]["backgrounds"]] == ["AB"]
        assert [m["value"] for m in h["strain_ancestry"]["mutant_backgrounds"]] == ["casper"]

    def test_ancestry_does_not_repeat_record_derived_values(self, conn):
        self.cache(conn, {"crossing_id": 2, "tanks": {
            "parents": [{"tank_id": 20, "strain_name": "AB Casper_HHMI", "strain_id": 14}],
            "children": [{"tank_id": 21, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145,
                          "date_of_birth": "2025-08-12T00:00:00"}]}})
        store_strain_ancestry(conn, 1145, parse_strain_pedigree(PEDIGREE_1145, 1145))

        h = derive_tank_heritage(conn, 21)
        assert [b["value"] for b in h["backgrounds"]] == ["AB"]
        assert h["strain_ancestry"]["backgrounds"] == []
        assert h["strain_ancestry"]["mutant_backgrounds"] == []


class FakePedigreeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def pedigree(self, strain_id):
        self.calls.append(str(strain_id))
        return self.payloads.get(str(strain_id), {"pedigree": {"nodes": []}})


class TestNightlyAncestrySelection:
    def cache(self, conn, payload):
        TestHeritageUsesAncestryOnlyAsInference().cache(conn, payload)

    def test_selects_only_unfetched_strains_without_record_background(self, conn):
        # 1145 parent has no record background; 14 (AB Casper) has one.
        self.cache(conn, {"crossing_id": 1, "tanks": {
            "parents": [{"tank_id": 10, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145}],
            "children": [{"tank_id": 11, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145}]}})
        self.cache(conn, {"crossing_id": 2, "tanks": {
            "parents": [{"tank_id": 20, "strain_name": "AB Casper_HHMI", "strain_id": 14}],
            "children": [{"tank_id": 21, "strain_name": "AB Casper_HHMI", "strain_id": 14}]}})

        assert strains_needing_ancestry(conn) == ["1145"]

    def test_fetch_stores_and_then_nothing_is_needed(self, conn):
        self.cache(conn, {"crossing_id": 1, "tanks": {
            "parents": [{"tank_id": 10, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145}],
            "children": [{"tank_id": 11, "strain_name": "Tg(ubi:Switch)", "strain_id": 1145}]}})
        client = FakePedigreeClient({"1145": PEDIGREE_1145})

        stats = fetch_strain_ancestry(conn, client, strains_needing_ancestry(conn), pause=0)

        assert stats == {"fetched": 1, "with_ancestors": 1}
        assert client.calls == ["1145"]
        assert strains_needing_ancestry(conn) == []
        assert [b["value"] for b in derive_tank_heritage(conn, 11)["strain_ancestry"]["backgrounds"]] == ["AB"]


class TestNightlyAncestryStepIsBestEffort:
    def test_missing_frontend_credentials_skip_without_failing(self, conn, monkeypatch):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "sync_cross_cache", Path(__file__).resolve().parents[1] / "scripts" / "sync_cross_cache.py")
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)

        monkeypatch.setattr(script, "strains_needing_ancestry", lambda c: ["1145"])

        def no_credentials():
            raise RuntimeError("PyRAT frontend credentials are not configured.")

        monkeypatch.setattr(script, "StrainPedigreeClient", no_credentials)
        assert script.sync_strain_ancestry(conn, pause=0) == "skipped (RuntimeError)"
