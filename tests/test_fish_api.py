"""
Tests for the fish tracking API (Phases 1-4).

Runs against a temporary SQLite database via FastAPI's TestClient —
no live server required.

    pixi run pytest tests/test_fish_api.py -v
"""

import re
import uuid

import pytest

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
# Dish labels
# -------------------------------------------------------------------


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
