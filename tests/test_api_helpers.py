import sqlite3
from types import SimpleNamespace

from metazebrobot.api_server import (
    _cross_prefill_complete,
    _cross_prefill_from_payload,
    _ensure_cross_parent_provenance_schema,
    _load_cross_parent_provenance,
    _merge_cross_payload,
    _next_dish_number_for_cross,
    _prepare_crossings_for_display,
    _screening_indicator_suggestions,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils.cross_provenance import parse_parent_background


class TestScreeningIndicatorSuggestions:
    def test_single_catalog_backed_construct_prefills_field(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            }
        ]

        suggestions, default_value = _screening_indicator_suggestions(transgenes)

        assert default_value == "GRAB-5HT"
        assert suggestions == [
            {
                "value": "GRAB-5HT",
                "meta": "sensor · GRAB · serotonin · green",
            }
        ]

    def test_current_protocol_step_overrides_default_value(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            }
        ]
        current_step = SimpleNamespace(indicators=["GFP", "GRAB-5HT"])

        suggestions, default_value = _screening_indicator_suggestions(transgenes, current_step)

        assert default_value == "GFP, GRAB-5HT"
        assert [entry["value"] for entry in suggestions] == ["GFP", "GRAB-5HT"]

    def test_multiple_constructs_do_not_autofill(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            },
            {
                "catalog_name": "jRGECO1b",
                "reporter": "jrgeco1b",
                "construct_role": "sensor",
                "family": "jRGECO",
                "target": "calcium",
                "screen_color": "red",
            },
        ]

        suggestions, default_value = _screening_indicator_suggestions(transgenes)

        assert default_value == ""
        assert [entry["value"] for entry in suggestions] == ["GRAB-5HT", "jRGECO1b"]


class TestCrossPrefillHelpers:
    def test_next_dish_number_for_cross_uses_primary_numeric_suffixes(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE dishes (dish_id TEXT, cross_id TEXT)")
        cross_id = "CROSS_AUTO"
        for dish_id, row_cross_id in (
            ("CROSS_AUTO_1", cross_id),
            ("CROSS_AUTO_2", cross_id),
            ("CROSS_AUTO_5", cross_id),
            ("CROSS_AUTO_5_pos1", cross_id),
            ("OTHER_CROSS_20", "OTHER_CROSS"),
        ):
            conn.execute(
                "INSERT INTO dishes (dish_id, cross_id) VALUES (?, ?)",
                (dish_id, row_cross_id),
            )

        assert _next_dish_number_for_cross(conn, cross_id) == 6
        assert _next_dish_number_for_cross(conn, "NEW_CROSS") == 1
        assert _next_dish_number_for_cross(conn, None) == 1

    def test_cross_prefill_complete_requires_core_fields(self):
        assert not _cross_prefill_complete({
            "genotype": "Tg(elavl3:GRAB-5HT)",
            "responsible": "Delahanty Jeremy",
            "parents": "",
            "dof": "2026-04-07",
        })
        assert _cross_prefill_complete({
            "genotype": "Tg(elavl3:GRAB-5HT)",
            "responsible": "Delahanty Jeremy",
            "parents": "#6489_M12>D9, #6402_M24>C8",
            "dof": "2026-04-07",
        })

    def test_cross_prefill_from_payload_uses_setup_plus_one_for_dof(self):
        payload = {
            "strain_name": "Tg(elavl3:GRAB-5HT)",
            "responsible_fullname": "Delahanty Jeremy",
            "date_of_set_up": "2026-04-06T08:40:12",
            "date_of_record": "2026-04-06T00:00:00",
            "tanks": {
                "parents": [
                    {
                        "tank_id": 6489,
                        "location_rack_name": "M12",
                        "tank_position": "D9",
                    },
                    {
                        "tank_id": 6402,
                        "location_rack_name": "M24",
                        "tank_position": "C8",
                    },
                ]
            },
        }

        prefill = _cross_prefill_from_payload(payload)

        assert prefill["genotype"] == "Tg(elavl3:GRAB-5HT)"
        assert prefill["responsible"] == "Delahanty Jeremy"
        assert prefill["cross_setup_date"] == "2026-04-06"
        assert prefill["dof"] == "2026-04-07"
        assert prefill["dof_source"] == "pyrat_setup_plus_1"
        assert prefill["parents"] == "#6489_M12>D9, #6402_M24>C8"

    def test_cross_prefill_prefers_tank_label_over_bare_tank_id(self):
        payload = {
            "strain_name": "Tg(elavl3:GRAB-5HT)",
            "responsible_fullname": "Delahanty Jeremy",
            "date_of_set_up": "2026-04-06T08:40:12",
            "tanks": {
                "parents": [
                    {
                        "tank_id": 6489,
                        "tank_label": "#6489_M12>D9",
                    },
                ]
            },
        }

        prefill = _cross_prefill_from_payload(payload)

        assert prefill["parents"] == "#6489_M12>D9"

    def test_cross_prefill_includes_parent_provenance(self):
        payload = {
            "strain_name": "Tg(elavl3:GCaMP7ff)",
            "responsible_fullname": "How Javier",
            "date_of_set_up": "2026-05-05T09:42:29",
            "tanks": {
                "parents": [
                    {
                        "tank_id": 6507,
                        "strain_name": "WIK Casper_HHMI",
                        "number_of_female": 1,
                        "generation": "F1",
                        "location_rack_name": "M12",
                        "tank_position": "E4",
                    },
                    {
                        "tank_id": 5724,
                        "strain_name": "Tg(elavl3:GCaMP7ff)",
                        "number_of_male": 1,
                        "generation": "F1",
                    },
                ],
            },
        }

        prefill = _cross_prefill_from_payload(payload)

        provenance = prefill["parent_provenance"]
        assert provenance["summary"]["background_summary"] == "WIK + Casper_HHMI + casper"
        assert provenance["parents"][0]["role"] == "female"
        assert provenance["parents"][0]["background_strains"] == ["WIK"]
        assert provenance["parents"][0]["line_labels"] == ["Casper_HHMI"]
        assert provenance["parents"][0]["mutant_backgrounds"] == ["casper"]
        assert provenance["parents"][1]["role"] == "male"


class TestCrossParentProvenance:
    def test_parse_parent_background_keeps_backgrounds_separate_from_transgenes(self):
        wik = parse_parent_background("WIK Casper_HHMI")
        assert wik["background_strains"] == ["WIK"]
        assert wik["line_labels"] == ["Casper_HHMI"]
        assert wik["mutant_backgrounds"] == ["casper"]
        assert wik["transgenes"] == []

        transgene = parse_parent_background("Tg(elavl3:jRGECO1b)")
        assert transgene["background_strains"] == []
        assert transgene["line_labels"] == []
        assert transgene["transgenes"][0]["promoter"] == "elavl3"

    def test_upsert_cross_parent_provenance_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE crosses (cross_id TEXT PRIMARY KEY, data TEXT)")
        _ensure_cross_parent_provenance_schema(conn)

        payload = {
            "crossing_id": 18055,
            "tanks": {
                "parents": [
                    {
                        "tank_id": 6507,
                        "strain_name": "WIK Casper_HHMI",
                        "number_of_female": 1,
                        "generation": "F1",
                    },
                    {
                        "tank_id": 5724,
                        "strain_name": "Tg(elavl3:GCaMP7ff)",
                        "number_of_male": 1,
                        "generation": "F1",
                    },
                ],
            },
        }

        _upsert_cross_parent_provenance(conn, "18055", payload)
        _upsert_cross_parent_provenance(conn, "18055", payload)

        count = conn.execute("SELECT COUNT(*) FROM cross_parents WHERE cross_id = '18055'").fetchone()[0]
        summary = conn.execute(
            "SELECT background_summary, has_mixed_background FROM cross_background_summaries WHERE cross_id = '18055'"
        ).fetchone()
        display = _load_cross_parent_provenance(conn, "18055")

        assert count == 2
        assert summary["background_summary"] == "WIK + Casper_HHMI + casper"
        assert summary["has_mixed_background"] == 1
        assert display["parents"][0]["generation"] == "F1"
        assert display["summary"]["background_strains"] == ["WIK"]


class TestCrossingDisplayHelpers:
    def test_merge_cross_payload_preserves_cached_children_and_enriched_counts(self):
        cached = {
            "crossing_id": 17907,
            "raised_tanks": 2,
            "crossing_tanks": 2,
            "tanks": {
                "parents": [{"tank_id": 6489}],
                "children": [{"tank_id": 9001}],
            },
        }
        raw = {
            "crossing_id": 17907,
            "status": "set-up",
            "tanks": {
                "parents": [{"tank_id": 6489}],
            },
        }

        merged = _merge_cross_payload(cached, raw)

        assert merged["raised_tanks"] == 2
        assert merged["crossing_tanks"] == 2
        assert merged["tanks"]["children"] == [{"tank_id": 9001}]
        assert merged["status"] == "set-up"

    def test_merge_cross_payload_preserves_cached_parent_locations_from_sparse_fetch(self):
        cached = {
            "crossing_id": 17990,
            "tanks": {
                "parents": [
                    {
                        "tank_id": 6319,
                        "location_rack_name": "M10",
                        "tank_position": "E7",
                        "status": "open",
                    },
                    {
                        "tank_id": 5060,
                        "location_rack_name": "M21",
                        "tank_position": "F5",
                        "status": "open",
                    },
                ],
            },
        }
        sparse = {
            "crossing_id": 17990,
            "tanks": {
                "parents": [
                    {"tank_id": 6319, "status": "closed"},
                    {"tank_id": 5060, "status": "closed"},
                ],
            },
        }

        merged = _merge_cross_payload(cached, sparse)
        prefill = _cross_prefill_from_payload(merged)

        assert merged["tanks"]["parents"][0]["status"] == "closed"
        assert prefill["parents"] == "#6319_M10>E7, #5060_M21>F5"

    def test_prepare_crossings_for_display_uses_cached_detail_fields(self):
        raw = [{
            "crossing_id": 17907,
            "status": "set-up",
            "date_of_set_up": "2026-04-06T08:40:12",
            "strain_name": "Tg(elavl3:GRAB-5HT)",
            "description": "2 Groups for propagation please",
            "tanks": {"parents": []},
        }]
        cached = {
            "17907": {
                "crossing_id": 17907,
                "raised_tanks": 2,
                "crossing_tanks": 2,
            }
        }

        prepared = _prepare_crossings_for_display(raw, {"17907": 1}, cached)

        assert len(prepared) == 1
        assert prepared[0]["raised_count"] == 2
        assert prepared[0]["performance_target_count"] == 2
        assert prepared[0]["performance_display"] == "100%"
        assert prepared[0]["performance_ratio_display"] == "2 / 2"
        assert prepared[0]["local_dish_count"] == 1
