"""
Tests for the fish tracking API (Phases 1-4).

Runs against a temporary SQLite database via FastAPI's TestClient —
no live server required.

    pixi run pytest tests/test_fish_api.py -v
"""

import re
import json
import sqlite3
import uuid

import pytest

from metazebrobot.data.data_manager import data_manager

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


# -------------------------------------------------------------------
# Fish subject CRUD
# -------------------------------------------------------------------


class TestFishSubjectCRUD:
    """Create / read / update / delete individual fish subjects."""

    def test_register_fish_auto_uuid(self, client, seed_dish):
        resp = client.post(f"/dishes/{seed_dish}/fish", json={})
        assert resp.status_code == 201
        body = resp.json()
        assert UUID_RE.match(body["fish_id"])
        assert body["dish_id"] == seed_dish

    def test_register_fish_pre_minted_uuid(self, client, seed_dish):
        pre_minted = str(uuid.uuid4())
        resp = client.post(
            f"/dishes/{seed_dish}/fish",
            json={"fish_id": pre_minted, "subject_label": "F-01"},
        )
        assert resp.status_code == 201
        assert resp.json()["fish_id"] == pre_minted
        assert resp.json()["subject_label"] == "F-01"

    def test_register_fish_nonexistent_dish(self, client):
        resp = client.post("/dishes/NO_SUCH_DISH/fish", json={})
        assert resp.status_code == 404

    def test_list_fish_empty(self, client, seed_dish):
        resp = client.get(f"/dishes/{seed_dish}/fish")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_fish_populated(self, client, seed_dish):
        client.post(f"/dishes/{seed_dish}/fish", json={"subject_label": "A"})
        client.post(f"/dishes/{seed_dish}/fish", json={"subject_label": "B"})
        resp = client.get(f"/dishes/{seed_dish}/fish")
        assert len(resp.json()["items"]) >= 2

    def test_get_fish_found(self, client, seed_dish):
        fish_id = client.post(
            f"/dishes/{seed_dish}/fish", json={"subject_label": "get-me"}
        ).json()["fish_id"]
        resp = client.get(f"/fish/{fish_id}")
        assert resp.status_code == 200
        assert resp.json()["subject_label"] == "get-me"

    def test_get_fish_not_found(self, client):
        resp = client.get(f"/fish/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_fish_label(self, client, seed_dish):
        fish_id = client.post(
            f"/dishes/{seed_dish}/fish", json={"subject_label": "old"}
        ).json()["fish_id"]
        resp = client.patch(f"/fish/{fish_id}", json={"subject_label": "new"})
        assert resp.status_code == 200
        assert resp.json()["subject_label"] == "new"

    def test_update_preserves_unchanged_fields(self, client, seed_dish):
        fish_id = client.post(
            f"/dishes/{seed_dish}/fish",
            json={"subject_label": "keep", "sex": "male", "genotype": "wt"},
        ).json()["fish_id"]
        client.patch(f"/fish/{fish_id}", json={"sex": "female"})
        fish = client.get(f"/fish/{fish_id}").json()
        assert fish["sex"] == "female"
        assert fish["subject_label"] == "keep"
        assert fish["genotype"] == "wt"

    def test_update_nonexistent_fish(self, client):
        resp = client.patch(f"/fish/{uuid.uuid4()}", json={"sex": "female"})
        assert resp.status_code == 404

    def test_delete_fish(self, client, seed_dish):
        fish_id = client.post(f"/dishes/{seed_dish}/fish", json={}).json()["fish_id"]
        resp = client.delete(f"/fish/{fish_id}")
        assert resp.status_code == 204
        assert client.get(f"/fish/{fish_id}").status_code == 404

    def test_delete_nonexistent_fish(self, client):
        resp = client.delete(f"/fish/{uuid.uuid4()}")
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Housing units
# -------------------------------------------------------------------


class TestHousingUnits:
    """Create and query housing units."""

    def test_create_single_unit(self, client, seed_dish):
        resp = client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "position_label": "A1"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["unit_id"] == f"{seed_dish}:A1"

    def test_create_batch_numeric(self, client, seed_dish):
        resp = client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "lane", "count": 4, "label_format": "numeric"},
        )
        assert resp.status_code == 201
        ids = resp.json()["created"]
        assert len(ids) == 4
        assert ids[0] == f"{seed_dish}:1"
        assert ids[-1] == f"{seed_dish}:4"

    def test_create_batch_well_plate(self, client, seed_dish):
        resp = client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "count": 6, "label_format": "well_plate"},
        )
        assert resp.status_code == 201
        ids = resp.json()["created"]
        assert len(ids) == 6
        # First label should be A1
        assert ids[0] == f"{seed_dish}:A1"

    def test_list_units_with_occupancy(self, client, seed_dish):
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"position_label": "occ-test"},
        )
        resp = client.get(f"/dishes/{seed_dish}/units")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert "occupant_count" in items[0]

    def test_get_unit_with_fish(self, client, seed_dish):
        # Create unit
        unit_resp = client.post(
            f"/dishes/{seed_dish}/units",
            json={"position_label": "uf-test"},
        )
        unit_id = unit_resp.json()["unit_id"]
        # Create fish and assign
        fish_id = client.post(f"/dishes/{seed_dish}/fish", json={}).json()["fish_id"]
        client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_id})

        resp = client.get(f"/units/{unit_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "fish" in body
        assert any(f["fish_id"] == fish_id for f in body["fish"])

    def test_create_units_nonexistent_dish(self, client):
        resp = client.post("/dishes/NO_DISH/units", json={"count": 1})
        assert resp.status_code == 404

    def test_get_nonexistent_unit(self, client):
        resp = client.get("/units/NO_UNIT:0")
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Fish assignment and movement
# -------------------------------------------------------------------


class TestFishAssignment:
    """Assign and move fish between housing units."""

    def _make_fish_and_unit(self, client, seed_dish, label):
        fish_id = client.post(f"/dishes/{seed_dish}/fish", json={}).json()["fish_id"]
        unit_id = client.post(
            f"/dishes/{seed_dish}/units", json={"position_label": label}
        ).json()["unit_id"]
        return fish_id, unit_id

    def test_assign_fish(self, client, seed_dish):
        fish_id, unit_id = self._make_fish_and_unit(client, seed_dish, "assign-1")
        resp = client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_id})
        assert resp.status_code == 200
        assert resp.json()["current_unit_id"] == unit_id

    def test_move_fish_between_units(self, client, seed_dish):
        fish_id, unit_a = self._make_fish_and_unit(client, seed_dish, "move-a")
        client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_a})

        unit_b = client.post(
            f"/dishes/{seed_dish}/units", json={"position_label": "move-b"}
        ).json()["unit_id"]

        resp = client.post(
            f"/fish/{fish_id}/assign",
            json={"unit_id": unit_b, "reason": "experiment"},
        )
        assert resp.status_code == 200
        assert resp.json()["current_unit_id"] == unit_b

    def test_occupancy_history(self, client, seed_dish):
        fish_id, unit_a = self._make_fish_and_unit(client, seed_dish, "hist-a")
        client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_a})

        unit_b = client.post(
            f"/dishes/{seed_dish}/units", json={"position_label": "hist-b"}
        ).json()["unit_id"]
        client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_b})

        resp = client.get(f"/fish/{fish_id}/history")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        # First record should have moved_out_at set
        assert items[0]["moved_out_at"] is not None
        # Second record still open
        assert items[1]["moved_out_at"] is None

    def test_assign_nonexistent_fish(self, client, seed_dish):
        unit_id = client.post(
            f"/dishes/{seed_dish}/units", json={"position_label": "orphan"}
        ).json()["unit_id"]
        resp = client.post(
            f"/fish/{uuid.uuid4()}/assign", json={"unit_id": unit_id}
        )
        assert resp.status_code == 404

    def test_assign_nonexistent_unit(self, client, seed_dish):
        fish_id = client.post(f"/dishes/{seed_dish}/fish", json={}).json()["fish_id"]
        resp = client.post(
            f"/fish/{fish_id}/assign", json={"unit_id": "NO_UNIT:0"}
        )
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Housing unit checks
# -------------------------------------------------------------------


class TestHousingUnitChecks:
    """Maintenance check logging for housing units."""

    def _make_unit(self, client, seed_dish, label):
        return client.post(
            f"/dishes/{seed_dish}/units", json={"position_label": label}
        ).json()["unit_id"]

    def test_log_check(self, client, seed_dish):
        unit_id = self._make_unit(client, seed_dish, "chk-1")
        resp = client.post(
            f"/units/{unit_id}/checks",
            json={"check_time": "2026-04-01T09:00:00", "fed": True, "feed_type": "brine shrimp"},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "ok"

    def test_log_check_missing_check_time(self, client, seed_dish):
        unit_id = self._make_unit(client, seed_dish, "chk-2")
        resp = client.post(f"/units/{unit_id}/checks", json={"fed": True})
        assert resp.status_code == 422

    def test_log_check_nonexistent_unit(self, client):
        resp = client.post(
            "/units/FAKE:0/checks",
            json={"check_time": "2026-04-01T09:00:00"},
        )
        assert resp.status_code == 404

    def test_check_history_descending(self, client, seed_dish):
        unit_id = self._make_unit(client, seed_dish, "chk-3")
        client.post(
            f"/units/{unit_id}/checks",
            json={"check_time": "2026-04-01T08:00:00"},
        )
        client.post(
            f"/units/{unit_id}/checks",
            json={"check_time": "2026-04-01T10:00:00"},
        )
        resp = client.get(f"/units/{unit_id}/checks")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        # Descending by check_time
        assert items[0]["check_time"] >= items[1]["check_time"]


# -------------------------------------------------------------------
# Dish splitting (derived dishes)
# -------------------------------------------------------------------


class TestDishSplit:
    """POST /screening/{dish_id}/split — create derived dishes."""

    def test_split_success(self, client, seed_full_dish):
        resp = client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 10, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # Derived dish should exist
        new_id = f"{seed_full_dish}_pos1"
        resp2 = client.get(f"/dishes/{new_id}")
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["parent_dish_id"] == seed_full_dish
        assert body["dish_population_type"] == "positive_screened"
        assert body["fish_count"] == 10

    def test_split_from_specific_screening_step_tracks_provenance(self, client, seed_full_dish):
        client.post(
            f"/screening/{seed_full_dish}/steps",
            data={
                "screening_datetime": "20260405T09:00:00",
                "dpf_screened": 4,
                "pigment_screened": "true",
                "count_screened_this_step": 20,
                "notes": "pigment step",
            },
        )

        resp = client.post(
            f"/screening/{seed_full_dish}/steps/20260405T09:00:00/split",
            data={
                "fish_count": 5,
                "population_type": "pigmented_screened",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        new_id = f"{seed_full_dish}_pig1"
        resp2 = client.get(f"/dishes/{new_id}")
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["parent_dish_id"] == seed_full_dish
        assert body["dish_population_type"] == "pigmented_screened"
        assert body["source_screening_datetime"] == "20260405T09:00:00"
        assert body["source_screening_bucket"] == "pigmented_screened"
        assert body["fish_count"] == 5

        parent = client.get(f"/dishes/{seed_full_dish}").json()["data"]
        step = parent["screening_results"]["screenings"][0]
        assert step["allocations"][0]["bucket"] == "pigmented_screened"
        assert step["allocations"][0]["disposition"] == "derived_dish"
        assert step["allocations"][0]["destination_dish_id"] == new_id
        assert step["allocations"][0]["derived_dish_id"] == new_id

    def test_allocate_screening_step_to_existing_same_cross_dish(self, client, seed_full_dish):
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 2, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        destination_id = f"{seed_full_dish}_pos1"

        client.post(
            f"/screening/{seed_full_dish}/steps",
            data={
                "screening_datetime": "20260406T09:00:00",
                "dpf_screened": 5,
                "indicators_screened": "GFP",
                "count_screened_this_step": 10,
            },
        )

        page = client.get(f"/screening/{seed_full_dish}")
        assert page.status_code == 200
        assert "Add To Existing Dish" in page.text
        assert f'value="{destination_id}"' in page.text

        resp = client.post(
            f"/screening/{seed_full_dish}/steps/20260406T09:00:00/destination",
            data={
                "bucket": "positive_screened",
                "count": 3,
                "destination_dish_id": destination_id,
                "notes": "top up positives",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 200
        assert "Screening fish allocated to existing dish." in resp.text

        parent = client.get(f"/dishes/{seed_full_dish}").json()["data"]
        step = parent["screening_results"]["screenings"][0]
        allocation = step["allocations"][0]
        assert allocation["bucket"] == "positive_screened"
        assert allocation["destination_dish_id"] == destination_id
        assert allocation["derived_dish_id"] == destination_id
        assert allocation["count"] == 3

        destination = client.get(f"/dishes/{destination_id}").json()["data"]
        assert destination["fish_count"] == 2
        assert destination["incoming_fish_count"] == 3
        assert destination["current_fish_count"] == 5

    def test_split_custom_container_type(self, client, seed_full_dish):
        resp = client.post(
            f"/screening/{seed_full_dish}/split",
            data={
                "fish_count": 5,
                "population_type": "negative_screened",
                "container_type": "beaker",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        new_id = f"{seed_full_dish}_neg1"
        resp2 = client.get(f"/dishes/{new_id}")
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["container_type"] == "beaker"

    def test_split_nonexistent_dish(self, client):
        resp = client.post(
            "/screening/NO_SUCH_DISH/split",
            data={"fish_count": 5},
        )
        # Returns an HTML error (not a redirect)
        assert resp.status_code == 200
        assert "not found" in resp.text.lower()

    def test_split_zero_fish_count(self, client, seed_full_dish):
        resp = client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 0},
        )
        assert resp.status_code == 200
        assert "greater than zero" in resp.text.lower()

    def test_split_inherits_parent_properties(self, client, seed_full_dish):
        """Derived dish inherits genotype, species, and enclosure from parent."""
        parent = client.get(f"/dishes/{seed_full_dish}").json()
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 3, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        new_id = f"{seed_full_dish}_pos1"
        child = client.get(f"/dishes/{new_id}").json()
        assert child["genotype"] == parent["genotype"]
        assert child["species"] == parent["species"]

    def test_split_increments_suffix(self, client, seed_full_dish):
        """Second split of the same type gets _pos2."""
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 5, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 3, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        assert client.get(f"/dishes/{seed_full_dish}_pos1").status_code == 200
        assert client.get(f"/dishes/{seed_full_dish}_pos2").status_code == 200


# -------------------------------------------------------------------
# Screening reference panels
# -------------------------------------------------------------------


class TestScreeningReferencePanels:
    """Reference panels on the screening page."""

    def test_screening_page_shows_genotype_reference_panel(self, client, seed_full_dish):
        resp = client.get(f"/screening/{seed_full_dish}")

        assert resp.status_code == 200
        assert "Genotype Reference" in resp.text
        assert f'hx-get="/screening/{seed_full_dish}/genotype-reference"' in resp.text
        assert "Atlas Reference" in resp.text

    def test_genotype_reference_partial_placeholder(self, client, seed_full_dish):
        from metazebrobot.models.fish_dish import FishDish

        unique_genotype = f"Tg(unique:placeholder-{uuid.uuid4().hex[:6]})"
        dish = FishDish.create_new(
            cross_id=f"CROSS_{uuid.uuid4().hex[:6]}",
            dish_number=1,
            genotype=unique_genotype,
            responsible="test-user",
            fish_count=1,
            dof="20260401",
        )
        assert data_manager.save_fish_dish(dish.model_dump(mode="json", exclude_none=True))

        resp = client.get(f"/screening/{dish.dish_id}/genotype-reference")

        assert resp.status_code == 200
        assert "No curated genotype reference image for this exact genotype yet." in resp.text
        assert "Tg(unique:placeholder-" in resp.text

    def test_genotype_reference_partial_renders_matching_reference(self, client, seed_full_dish):
        reference_id = data_manager.save_genotype_reference_image(
            "Tg(elavl3:GCaMP6s)",
            "elavl3_gcamp_ref.png",
            caption="Known good elavl3 GCaMP pattern",
            source_dish_id=seed_full_dish,
        )
        assert reference_id is not None

        resp = client.get(f"/screening/{seed_full_dish}/genotype-reference")

        assert resp.status_code == 200
        assert "/genotype-reference-images/elavl3_gcamp_ref.png" in resp.text
        assert "Known good elavl3 GCaMP pattern" in resp.text
        assert f"<code>{seed_full_dish}</code>" in resp.text
        assert "No curated genotype reference image" not in resp.text


# -------------------------------------------------------------------
# Reference library
# -------------------------------------------------------------------


class TestReferenceLibrary:
    """Read-only reference library page."""

    def test_reference_library_page_empty(self, client):
        conn = sqlite3.connect(str(data_manager.database_path))
        conn.execute("DELETE FROM genotype_reference_images")
        conn.commit()
        conn.close()

        resp = client.get("/references/")

        assert resp.status_code == 200
        assert "Reference Library" in resp.text
        assert "No curated genotype reference images yet." in resp.text

    def test_reference_library_page_lists_genotype_references(self, client, seed_full_dish):
        reference_id = data_manager.save_genotype_reference_image(
            "Tg(elavl3:GCaMP6s)",
            "library_ref.png",
            caption="Reference library example",
            source_dish_id=seed_full_dish,
        )
        assert reference_id is not None

        resp = client.get("/references/")

        assert resp.status_code == 200
        assert "Tg(elavl3:GCaMP6s)" in resp.text
        assert "Reference library example" in resp.text
        assert "/genotype-reference-images/library_ref.png" in resp.text
        assert f'href="/screening/{seed_full_dish}"' in resp.text


# -------------------------------------------------------------------
# Plate map visualization
# -------------------------------------------------------------------


class TestPlateMap:
    """GET /dishes/{dish_id}/plate-map — housing visualization."""

    def test_plate_map_no_units(self, client, seed_dish):
        resp = client.get(f"/dishes/{seed_dish}/plate-map")
        assert resp.status_code == 200
        assert "No housing units" in resp.text

    def test_plate_map_well_plate(self, client, seed_dish):
        # Create a 6-well plate
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "count": 6, "label_format": "well_plate"},
        )
        resp = client.get(f"/dishes/{seed_dish}/plate-map")
        assert resp.status_code == 200
        assert "plate-grid" in resp.text
        assert "A1" in resp.text

    def test_plate_map_shows_occupant(self, client, seed_dish):
        # Create units + fish + assign
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "count": 6, "label_format": "well_plate"},
        )
        fish_id = client.post(
            f"/dishes/{seed_dish}/fish",
            json={"subject_label": "wt-01"},
        ).json()["fish_id"]
        unit_id = f"{seed_dish}:A1"
        client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit_id})

        resp = client.get(f"/dishes/{seed_dish}/plate-map")
        assert resp.status_code == 200
        assert "plate-well--occupied" in resp.text
        assert "wt-01" in resp.text

    def test_plate_map_shows_unassigned(self, client, seed_dish):
        # Register fish but don't assign to any unit
        client.post(f"/dishes/{seed_dish}/fish", json={"subject_label": "loose-fish"})
        resp = client.get(f"/dishes/{seed_dish}/plate-map")
        assert resp.status_code == 200
        assert "loose-fish" in resp.text
        assert "Unassigned" in resp.text

    def test_plate_map_open_container(self, client, seed_dish):
        # Create a single open unit (petri dish style)
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "open", "position_label": "main"},
        )
        resp = client.get(f"/dishes/{seed_dish}/plate-map")
        assert resp.status_code == 200
        # Should NOT render a plate grid
        assert "plate-grid" not in resp.text


# -------------------------------------------------------------------
# Daily care
# -------------------------------------------------------------------


class TestDailyCare:
    """Daily care web form endpoints."""

    def test_care_dish_list(self, client, seed_dish):
        resp = client.get("/care/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_care_form_simple_dish(self, client, seed_dish):
        resp = client.get(f"/care/{seed_dish}")
        assert resp.status_code == 200
        assert "Log Check" in resp.text

    def test_care_form_nonexistent_dish(self, client):
        resp = client.get("/care/NO_SUCH_DISH")
        assert resp.status_code == 404

    def test_submit_dish_check(self, client, seed_dish):
        resp = client.post(
            f"/care/{seed_dish}/check",
            data={
                "check_time": "20260403T09:00:00",
                "fed": "true",
                "feed_type": "paramecia",
                "water_changed": "true",
                "vol_water_changed": 50,
                "num_dead": 1,
                "notes": "test check",
            },
        )
        assert resp.status_code == 200
        assert "Check saved" in resp.text

    def test_checks_table_partial(self, client, seed_dish):
        # Submit a check first
        client.post(
            f"/care/{seed_dish}/check",
            data={"check_time": "20260403T10:00:00", "num_dead": 0},
        )
        resp = client.get(f"/care/{seed_dish}/checks-table")
        assert resp.status_code == 200
        assert "20260403T10:00:00" in resp.text

    def test_unit_checks_well_plate(self, client, seed_dish):
        # Create wells and submit unit checks
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "count": 3, "label_format": "well_plate"},
        )
        unit_id = f"{seed_dish}:A1"
        resp = client.post(
            f"/care/{seed_dish}/unit-checks",
            data={
                "check_time": "20260403T11:00:00",
                f"fed_{unit_id}": "on",
                f"feed_type_{unit_id}": "rotifers",
                f"num_dead_{unit_id}": "0",
            },
        )
        assert resp.status_code == 200
        assert "Saved 1 unit checks" in resp.text

    def test_care_form_shows_units(self, client, seed_dish):
        # Create wells
        client.post(
            f"/dishes/{seed_dish}/units",
            json={"unit_kind": "well", "count": 4, "label_format": "well_plate"},
        )
        resp = client.get(f"/care/{seed_dish}")
        assert resp.status_code == 200
        assert "Log Unit Checks" in resp.text
        assert "A1" in resp.text


# -------------------------------------------------------------------
# Dish inventory
# -------------------------------------------------------------------


class TestDishInventory:
    """Top-level dish inventory web page."""

    def test_dishes_inventory_page(self, client, seed_dish):
        resp = client.get("/dishes/")
        assert resp.status_code == 200
        assert "Dishes" in resp.text
        assert seed_dish in resp.text
        assert f'href="/screening/{seed_dish}"' in resp.text
        assert f'href="/care/{seed_dish}"' in resp.text
        assert f'href="/dishes/{seed_dish}/fish/"' in resp.text
        assert f'href="/dishes/{seed_dish}/label"' in resp.text

    def test_dishes_inventory_page_shows_terminate_for_active_dishes(self, client, seed_full_dish):
        resp = client.get("/dishes/")

        assert resp.status_code == 200
        assert f'action="/dishes/{seed_full_dish}/terminate"' in resp.text
        assert 'name="return_status" value="all"' in resp.text
        assert 'name="termination_reason"' in resp.text
        assert '<option value="euthanasia">Euthanasia</option>' in resp.text
        assert '<option value="propagation">Propagation</option>' in resp.text
        assert '<option value="transfer">Transfer</option>' in resp.text
        assert "Terminate" in resp.text

    def test_dishes_inventory_page_shows_transfer_for_same_cross_dishes(self, client, seed_full_dish):
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 2, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        destination_id = f"{seed_full_dish}_pos1"

        resp = client.get("/dishes/")

        assert resp.status_code == 200
        assert f'action="/dishes/{seed_full_dish}/transfer"' in resp.text
        assert f'value="{destination_id}"' in resp.text
        assert '<option value="manual_transfer">Manual transfer</option>' in resp.text
        assert '<option value="well_plate_setup">Well plate setup</option>' in resp.text
        assert '<option value="consolidation">Consolidation</option>' in resp.text

    def test_transfer_dish_fish_web_persists_event_and_counts(self, client, seed_full_dish, tmp_db_path):
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 2, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        destination_id = f"{seed_full_dish}_pos1"

        resp = client.post(
            f"/dishes/{seed_full_dish}/transfer",
            data={
                "destination_dish_id": destination_id,
                "count": 4,
                "reason": "well_plate_setup",
                "notes": "seed wells",
                "return_status": "active",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"] == f"/dishes/?status=active&transferred={seed_full_dish}"

        conn = sqlite3.connect(str(tmp_db_path))
        row = conn.execute(
            """
            SELECT source_dish_id, destination_dish_id, cross_id, count, reason, notes
            FROM dish_transfer_events
            WHERE source_dish_id = ?
            """,
            (seed_full_dish,),
        ).fetchone()
        conn.close()

        assert row == (seed_full_dish, destination_id, seed_full_dish.rsplit("_", 1)[0], 4, "well_plate_setup", "seed wells")

        source = client.get(f"/dishes/{seed_full_dish}").json()["data"]
        destination = client.get(f"/dishes/{destination_id}").json()["data"]
        assert source["fish_count"] == 50
        assert source["outgoing_transfer_count"] == 4
        assert source["current_fish_count"] == 46
        assert destination["fish_count"] == 2
        assert destination["incoming_transfer_count"] == 4
        assert destination["current_fish_count"] == 6

    def test_transfer_all_dish_fish_web_terminates_empty_source(self, client, seed_full_dish, tmp_db_path):
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 2, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        destination_id = f"{seed_full_dish}_pos1"

        resp = client.post(
            f"/dishes/{seed_full_dish}/transfer",
            data={
                "destination_dish_id": destination_id,
                "count": 50,
                "reason": "consolidation",
                "return_status": "active",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303

        conn = sqlite3.connect(str(tmp_db_path))
        source_row = conn.execute(
            """
            SELECT status, current_fish_count, termination_date, termination_reason
            FROM dishes
            WHERE dish_id = ?
            """,
            (seed_full_dish,),
        ).fetchone()
        destination_row = conn.execute(
            """
            SELECT current_fish_count
            FROM dishes
            WHERE dish_id = ?
            """,
            (destination_id,),
        ).fetchone()
        conn.close()

        assert source_row is not None
        assert source_row[0] == "inactive"
        assert source_row[1] == 0
        assert re.fullmatch(r"\d{8}", source_row[2])
        assert source_row[3] == "transfer"
        assert destination_row == (52,)

    def test_transfer_dish_fish_web_rejects_cross_mismatch(self, client, seed_full_dish):
        create_resp = client.post(
            "/dishes/new",
            data={
                "cross_id": "OTHER_CROSS",
                "dish_number": 1,
                "genotype": "wt",
                "responsible": "test",
                "dof": "2026-03-27",
            },
            follow_redirects=False,
        )
        assert create_resp.status_code == 303

        resp = client.post(
            f"/dishes/{seed_full_dish}/transfer",
            data={
                "destination_dish_id": "OTHER_CROSS_1",
                "count": 1,
                "reason": "manual_transfer",
                "return_status": "all",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 400
        assert "same cross ID" in resp.text

    def test_terminate_dish_web_marks_inactive(self, client, seed_full_dish, tmp_db_path):
        resp = client.post(
            f"/dishes/{seed_full_dish}/terminate",
            data={
                "termination_reason": "euthanasia",
                "return_status": "active",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"] == f"/dishes/?status=active&terminated={seed_full_dish}"

        conn = sqlite3.connect(str(tmp_db_path))
        row = conn.execute(
            """
            SELECT status, termination_date, termination_reason
            FROM dishes
            WHERE dish_id = ?
            """,
            (seed_full_dish,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "inactive"
        assert re.fullmatch(r"\d{8}", row[1])
        assert row[2] == "euthanasia"

    def test_terminate_dish_web_rejects_unrecognized_reason(self, client, seed_full_dish):
        resp = client.post(
            f"/dishes/{seed_full_dish}/terminate",
            data={
                "termination_reason": "No embryos remaining",
                "return_status": "all",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 400
        assert "Termination reason is required" in resp.text

    def test_inactive_dishes_page_shows_termination_metadata(self, client, seed_full_dish):
        client.post(
            f"/dishes/{seed_full_dish}/terminate",
            data={
                "termination_reason": "propagation",
                "return_status": "all",
            },
            follow_redirects=False,
        )

        resp = client.get("/dishes/?status=inactive")

        assert resp.status_code == 200
        assert seed_full_dish in resp.text
        assert "inactive" in resp.text
        assert "Terminated" in resp.text
        assert "Propagation" in resp.text
        assert f'action="/dishes/{seed_full_dish}/terminate"' not in resp.text


# -------------------------------------------------------------------
# Dish labels
# -------------------------------------------------------------------


class TestDishCreation:
    """Web dish creation form."""

    def test_new_dish_form_renders(self, client):
        resp = client.get("/dishes/new")
        assert resp.status_code == 200
        assert "Create New Dish" in resp.text
        assert resp.text.count('id="dof-input"') == 1

    def test_new_dish_form_prefills_selected_cross(self, client, monkeypatch):
        import metazebrobot.api_server as api_server

        def fake_fetch_pyrat(endpoint, params=None):
            assert endpoint == "tanks/crossings"
            assert params["crossing_id"] == "17907"
            return [{
                "crossing_id": "17907",
                "strain_name": "Tg(elavl3:GRAB-5HT)",
                "responsible_fullname": "Delahanty Jeremy",
                "date_of_set_up": "2026-04-06",
                "tanks": {
                    "parents": [
                        {
                            "tank_id": 123,
                            "location_rack_name": "M11",
                            "tank_position": "E1",
                        },
                    ],
                },
            }]

        monkeypatch.setattr(api_server, "_fetch_pyrat", fake_fetch_pyrat)

        resp = client.get("/dishes/new?cross_id=17907")

        assert resp.status_code == 200
        assert 'name="cross_id"' in resp.text
        assert 'value="17907"' in resp.text
        assert 'value="Tg(elavl3:GRAB-5HT)"' in resp.text
        assert 'value="Delahanty Jeremy"' in resp.text
        assert 'value="#123_M11&gt;E1"' in resp.text
        assert 'name="cross_setup_date"' in resp.text
        assert 'value="2026-04-06"' in resp.text
        assert resp.text.count('id="dof-input"') == 1
        assert 'value="2026-04-07"' in resp.text
        assert 'name="dof_source"' in resp.text
        assert 'value="pyrat_setup_plus_1"' in resp.text

    def test_create_dish_success(self, client):
        resp = client.post(
            "/dishes/new",
            data={
                "cross_id": "TEST_CROSS",
                "dish_number": 1,
                "genotype": "Tg(elavl3:GCaMP6s)",
                "responsible": "test-user",
                "dof": "2026-03-27",
                "fish_count": 10,
                "species": "Danio rerio",
                "sex": "unknown",
                "container_type": "petri_dish",
                "temperature": 28.5,
                "room": "2E.282",
                "light_duration": "14:10",
                "dawn_dusk": "8:00",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/screening/TEST_CROSS_1" in resp.headers["location"]

    def test_create_dish_persists_cross_setup_date_and_dof_source(self, client, tmp_db_path):
        resp = client.post(
            "/dishes/new",
            data={
                "cross_id": "TEST_CROSS_META",
                "dish_number": 1,
                "genotype": "Tg(elavl3:GCaMP6s)",
                "responsible": "test-user",
                "cross_setup_date": "2026-04-06",
                "dof": "2026-04-07",
                "dof_source": "pyrat_setup_plus_1",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303

        conn = sqlite3.connect(str(tmp_db_path))
        row = conn.execute(
            "SELECT dof, cross_setup_date, dof_source FROM dishes WHERE dish_id = ?",
            ("TEST_CROSS_META_1",),
        ).fetchone()
        conn.close()

        assert row == ("20260407", "20260406", "pyrat_setup_plus_1")

    def test_create_dish_duplicate(self, client):
        # Create first
        client.post(
            "/dishes/new",
            data={
                "cross_id": "DUP_CROSS",
                "dish_number": 1,
                "genotype": "wt",
                "responsible": "test",
                "dof": "2026-03-27",
            },
            follow_redirects=False,
        )
        # Try duplicate
        resp = client.post(
            "/dishes/new",
            data={
                "cross_id": "DUP_CROSS",
                "dish_number": 1,
                "genotype": "wt",
                "responsible": "test",
                "dof": "2026-03-27",
            },
        )
        assert resp.status_code == 200
        assert "already exists" in resp.text.lower()

    def test_cross_info_partial(self, client):
        resp = client.get("/dishes/new/cross-info?cross_id=NO_SUCH_CROSS")
        assert resp.status_code == 200
        # Should render the partial with empty fields (no PyRAT configured in tests)
        assert "Genotype" in resp.text

    def test_cross_info_partial_prefills_from_pyrat(self, client, monkeypatch):
        import metazebrobot.api_server as api_server

        def fake_fetch_pyrat(endpoint, params=None):
            assert endpoint == "tanks/crossings"
            assert params["crossing_id"] == "17907"
            return [{
                "crossing_id": "17907",
                "strain_name": "Tg(elavl3:GRAB-5HT)",
                "responsible_fullname": "Delahanty Jeremy",
                "date_of_set_up": "2026-04-06",
                "tanks": {
                    "parents": [
                        {
                            "tank_id": 123,
                            "location_rack_name": "M11",
                            "tank_position": "E1",
                        },
                        {
                            "tank_id": 456,
                            "location_rack_name": "M11",
                            "tank_position": "E2",
                        },
                    ],
                },
            }]

        monkeypatch.setattr(api_server, "_fetch_pyrat", fake_fetch_pyrat)

        resp = client.get("/dishes/new/cross-info?cross_id=17907")

        assert resp.status_code == 200
        assert 'value="Tg(elavl3:GRAB-5HT)"' in resp.text
        assert 'value="Delahanty Jeremy"' in resp.text
        assert 'value="#123_M11&gt;E1, #456_M11&gt;E2"' in resp.text
        assert 'name="cross_setup_date"' in resp.text
        assert 'value="2026-04-06"' in resp.text
        assert 'value="2026-04-07"' in resp.text
        assert 'value="pyrat_setup_plus_1"' in resp.text

    def test_cross_info_partial_prefills_from_existing_dish(self, client, tmp_db_path):
        cross_id = f"CROSS_{uuid.uuid4().hex[:6]}"
        parents = ["#123_M11>E1", "#456_M11>E2"]
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            """
            INSERT INTO dishes (
                dish_id, data, genotype, species, cross_id, dof, cross_setup_date, dof_source, responsible, breeding_parents
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{cross_id}_1",
                json.dumps({"dish_id": f"{cross_id}_1", "cross_id": cross_id}),
                "Tg(elavl3:GCaMP6s)",
                "Danio rerio",
                cross_id,
                "20260403",
                "20260402",
                "manual_override",
                "Test User",
                json.dumps(parents),
            ),
        )
        conn.commit()
        conn.close()

        resp = client.get(f"/dishes/new/cross-info?cross_id={cross_id}")

        assert resp.status_code == 200
        assert 'value="Tg(elavl3:GCaMP6s)"' in resp.text
        assert 'value="Test User"' in resp.text
        assert 'value="#123_M11&gt;E1, #456_M11&gt;E2"' in resp.text
        assert 'value="2026-04-02"' in resp.text
        assert 'id="dof-input"' in resp.text
        assert 'value="2026-04-03"' in resp.text
        assert 'value="manual_override"' in resp.text


class TestDishLabel:
    """GET /dishes/{dish_id}/label — PNG label with QR code."""

    def test_label_returns_png(self, client, seed_dish):
        resp = client.get(f"/dishes/{seed_dish}/label")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # PNG magic bytes
        assert resp.content[:4] == b"\x89PNG"

    def test_label_nonexistent_dish(self, client):
        resp = client.get("/dishes/NO_SUCH_DISH/label")
        assert resp.status_code == 404


# -------------------------------------------------------------------
# Cross-level fish views
# -------------------------------------------------------------------


class TestCrossLevelFish:
    """List all fish for a cross across multiple dishes."""

    def test_list_fish_for_cross_empty(self, client, seed_cross_dishes):
        cross_id, _, _ = seed_cross_dishes
        resp = client.get(f"/crosses/{cross_id}/fish")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_fish_for_cross_populated(self, client, seed_cross_dishes):
        cross_id, dish_a, dish_b = seed_cross_dishes
        client.post(f"/dishes/{dish_a}/fish", json={"subject_label": "A-1"})
        client.post(f"/dishes/{dish_a}/fish", json={"subject_label": "A-2"})
        client.post(f"/dishes/{dish_b}/fish", json={"subject_label": "B-1"})

        resp = client.get(f"/crosses/{cross_id}/fish")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 3
        # All should carry the cross_id
        assert all(f["cross_id"] == cross_id for f in items)
        # Should span both dishes
        dish_ids = {f["dish_id"] for f in items}
        assert dish_ids == {dish_a, dish_b}

    def test_cross_fish_web_page(self, client, seed_cross_dishes):
        cross_id, dish_a, _ = seed_cross_dishes
        client.post(f"/dishes/{dish_a}/fish", json={"subject_label": "web-1"})
        resp = client.get(f"/crosses/{cross_id}/fish/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_nonexistent_cross_returns_empty(self, client):
        resp = client.get("/crosses/NO_SUCH_CROSS/fish")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_cross_fish_includes_dish_metadata(self, client, seed_cross_dishes):
        cross_id, dish_a, _ = seed_cross_dishes
        client.post(f"/dishes/{dish_a}/fish", json={"subject_label": "meta-1"})
        resp = client.get(f"/crosses/{cross_id}/fish")
        items = resp.json()["items"]
        assert "parent_dish_id" in items[0]
        assert "dish_population_type" in items[0]

    def test_cross_fish_web_page_renders_deep_lineage(self, client, seed_full_dish):
        parent = client.get(f"/dishes/{seed_full_dish}").json()
        cross_id = parent["cross_id"]

        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 5, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        child_id = f"{seed_full_dish}_pos1"

        client.post(
            f"/screening/{child_id}/split",
            data={"fish_count": 2, "population_type": "negative_screened"},
            follow_redirects=False,
        )
        grandchild_id = f"{child_id}_neg1"

        resp = client.get(f"/crosses/{cross_id}/fish/")
        assert resp.status_code == 200
        assert child_id in resp.text
        assert grandchild_id in resp.text


# -------------------------------------------------------------------
# Fish index page
# -------------------------------------------------------------------


class TestFishIndex:
    """Top-level fish index page."""

    def test_index_page_renders(self, client):
        resp = client.get("/fish/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_index_shows_crosses_with_fish(self, client, seed_cross_dishes):
        cross_id, dish_a, _ = seed_cross_dishes
        client.post(f"/dishes/{dish_a}/fish", json={})
        resp = client.get("/fish/")
        assert resp.status_code == 200
        assert cross_id in resp.text


# -------------------------------------------------------------------
# Dish-level reference images
# -------------------------------------------------------------------


class TestDishImages:
    """Upload and retrieve dish-level reference images."""

    def test_get_dish_images_empty(self, client, seed_dish):
        resp = client.get(f"/dishes/{seed_dish}/images")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_upload_dish_image(self, client, seed_dish):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        resp = client.post(
            f"/dishes/{seed_dish}/images",
            files={"file": ("test.png", fake_png, "image/png")},
            data={"caption": "positive example"},
        )
        assert resp.status_code == 200
        assert "positive example" in resp.text

    def test_upload_dish_image_nonexistent_dish(self, client):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        resp = client.post(
            "/dishes/NO_DISH/images",
            files={"file": ("test.png", fake_png, "image/png")},
        )
        assert resp.status_code == 404

    def test_upload_invalid_file_type(self, client, seed_dish):
        resp = client.post(
            f"/dishes/{seed_dish}/images",
            files={"file": ("test.gif", b"GIF89a", "image/gif")},
        )
        assert resp.status_code == 200
        assert "Invalid file type" in resp.text

    def test_multiple_uploads(self, client, seed_dish):
        fake_jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        client.post(
            f"/dishes/{seed_dish}/images",
            files={"file": ("a.jpg", fake_jpg, "image/jpeg")},
            data={"caption": "first"},
        )
        client.post(
            f"/dishes/{seed_dish}/images",
            files={"file": ("b.jpg", fake_jpg, "image/jpeg")},
            data={"caption": "second"},
        )
        resp = client.get(f"/dishes/{seed_dish}/images")
        assert "first" in resp.text
        assert "second" in resp.text


# -------------------------------------------------------------------
# PyRAT crossings page
# -------------------------------------------------------------------


class TestPyRATCrossingsPage:
    """Crossings page should prefer backend/v1 detail counts when available."""

    def test_crossings_page_prefers_frontend_detail_counts(self, client, monkeypatch):
        import metazebrobot.api_server as api_server

        def fake_fetch_pyrat(endpoint, params=None):
            assert endpoint == "tanks/crossings"
            return [
                {
                    "crossing_id": 14783,
                    "status": "set-up",
                    "date_of_record": "2025-01-20T00:00:00",
                    "date_of_set_up": "2025-01-20T08:21:19",
                    "date_of_raise": None,
                    "strain_name": "Robot Avoidance",
                    "description": "2 Groups for Robot Avoidance Assay",
                    "tanks": {"children": []},
                }
            ]

        def fake_get_frontend_credentials():
            return {"base_url": "https://example.invalid/aquatic/", "username": "tester", "password": "secret"}

        def fake_enrich(crossings, frontend_credentials, **kwargs):
            assert frontend_credentials["username"] == "tester"
            enriched = list(crossings)
            enriched[0] = {
                **enriched[0],
                "crossing_tanks": 2,
                "raised_tanks": 1,
                "really_raised_tanks": 1,
            }
            return enriched

        monkeypatch.setattr(api_server, "_fetch_pyrat", fake_fetch_pyrat)
        monkeypatch.setattr(api_server, "get_pyrat_frontend_credentials", fake_get_frontend_credentials)
        monkeypatch.setattr(api_server, "enrich_crossings_with_frontend_details", fake_enrich)

        resp = client.get("/pyrat/crossings/")
        assert resp.status_code == 200
        assert "Crossing Tanks" in resp.text
        assert "50%" in resp.text
        assert 'title="1 / 2"' in resp.text
        assert 'href="/dishes/new?cross_id=14783"' in resp.text
        assert "New dish" in resp.text
