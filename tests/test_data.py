"""
Direct data_manager method tests — no HTTP layer.

Uses the same temp DB fixture from conftest.py.  The `client` fixture
is required because the TestClient context manager runs `lifespan()`,
which initialises data_manager and creates all tables.

    pixi run pytest tests/test_data.py -v
"""

import re
import uuid

import pytest

from metazebrobot.data.data_manager import data_manager

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class TestFishSubjectData:
    """data_manager fish subject methods."""

    def test_create_auto_uuid(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        assert fish_id is not None
        assert UUID_RE.match(fish_id)

    def test_create_with_pre_minted_uuid(self, client, seed_dish):
        pre = str(uuid.uuid4())
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish, fish_id=pre)
        assert fish_id == pre

    def test_get_fish_subjects_ordered(self, client, seed_dish):
        data_manager.create_fish_subject(dish_id=seed_dish, subject_label="first")
        data_manager.create_fish_subject(dish_id=seed_dish, subject_label="second")
        subjects = data_manager.get_fish_subjects(seed_dish)
        labels = [s["subject_label"] for s in subjects if s["subject_label"]]
        # Should be ordered by created_at — first before second
        assert labels.index("first") < labels.index("second")

    def test_update_allowed_fields(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(
            dish_id=seed_dish, subject_label="orig", sex="unknown"
        )
        assert data_manager.update_fish_subject(fish_id, sex="male")
        fish = data_manager.get_fish_subject(fish_id)
        assert fish["sex"] == "male"
        assert fish["subject_label"] == "orig"

    def test_update_ignores_disallowed_fields(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        # dish_id is not in the allowed set
        result = data_manager.update_fish_subject(fish_id, dish_id="SNEAKY")
        assert result is True  # nothing to do → True
        assert data_manager.get_fish_subject(fish_id)["dish_id"] == seed_dish

    def test_delete_cascades_to_images(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        data_manager.save_fish_image(fish_id, "test.png")
        assert len(data_manager.get_fish_images(fish_id)) == 1
        data_manager.delete_fish_subject(fish_id)
        assert data_manager.get_fish_subject(fish_id) is None
        assert len(data_manager.get_fish_images(fish_id)) == 0

    def test_delete_cascades_to_occupancy(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        unit_id = data_manager.create_housing_unit(
            dish_id=seed_dish, position_label="cascade-test"
        )
        data_manager.assign_fish_to_unit(fish_id, unit_id)
        assert len(data_manager.get_fish_occupancy_history(fish_id)) == 1
        data_manager.delete_fish_subject(fish_id)
        # occupancy should be gone (ON DELETE CASCADE)
        assert len(data_manager.get_fish_occupancy_history(fish_id)) == 0


class TestHousingUnitData:
    """data_manager housing unit methods."""

    def test_well_plate_labels_6(self, client, seed_dish):
        ids = data_manager.create_housing_units_for_dish(
            dish_id=seed_dish, unit_kind="well", count=6, label_format="well_plate"
        )
        assert len(ids) == 6
        # First is A1
        assert ids[0].endswith(":A1")

    def test_well_plate_labels_24(self, client, seed_dish):
        ids = data_manager.create_housing_units_for_dish(
            dish_id=seed_dish, unit_kind="well", count=24, label_format="well_plate"
        )
        assert len(ids) == 24

    def test_numeric_labels(self, client, seed_dish):
        ids = data_manager.create_housing_units_for_dish(
            dish_id=seed_dish, unit_kind="lane", count=3, label_format="numeric"
        )
        assert ids[0].endswith(":1")
        assert ids[2].endswith(":3")


class TestAssignmentData:
    """data_manager assignment and occupancy methods."""

    def test_assign_creates_occupancy(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        unit_id = data_manager.create_housing_unit(
            dish_id=seed_dish, position_label="da-1"
        )
        assert data_manager.assign_fish_to_unit(fish_id, unit_id)
        history = data_manager.get_fish_occupancy_history(fish_id)
        assert len(history) == 1
        assert history[0]["unit_id"] == unit_id

    def test_move_closes_old_occupancy(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)
        u1 = data_manager.create_housing_unit(dish_id=seed_dish, position_label="dm-a")
        u2 = data_manager.create_housing_unit(dish_id=seed_dish, position_label="dm-b")
        data_manager.assign_fish_to_unit(fish_id, u1)
        data_manager.move_fish(fish_id, u2, reason="transfer")
        history = data_manager.get_fish_occupancy_history(fish_id)
        assert len(history) == 2
        assert history[0]["moved_out_at"] is not None
        assert history[1]["moved_out_at"] is None


class TestCrossLevelData:
    """data_manager cross-level fish queries."""

    def test_get_fish_subjects_for_cross(self, client, seed_cross_dishes):
        cross_id, dish_a, dish_b = seed_cross_dishes
        data_manager.create_fish_subject(dish_id=dish_a, subject_label="xa")
        data_manager.create_fish_subject(dish_id=dish_b, subject_label="xb")
        results = data_manager.get_fish_subjects_for_cross(cross_id)
        assert len(results) == 2
        assert {r["dish_id"] for r in results} == {dish_a, dish_b}
        assert all(r["cross_id"] == cross_id for r in results)

    def test_get_fish_subjects_for_cross_empty(self, client):
        results = data_manager.get_fish_subjects_for_cross("NO_CROSS")
        assert results == []

    def test_get_crosses_with_fish_counts(self, client, seed_cross_dishes):
        cross_id, dish_a, dish_b = seed_cross_dishes
        data_manager.create_fish_subject(dish_id=dish_a)
        data_manager.create_fish_subject(dish_id=dish_a)
        data_manager.create_fish_subject(dish_id=dish_b)
        crosses = data_manager.get_crosses_with_fish_counts()
        match = [c for c in crosses if c["cross_id"] == cross_id]
        assert len(match) == 1
        assert match[0]["fish_count"] == 3
        assert match[0]["dish_count"] == 2

    def test_get_dishes_for_cross(self, client, seed_cross_dishes):
        cross_id, dish_a, dish_b = seed_cross_dishes
        dishes = data_manager.get_dishes_for_cross(cross_id)
        dish_ids = {d["dish_id"] for d in dishes}
        assert dish_ids == {dish_a, dish_b}
        assert all("fish_count" in d for d in dishes)


class TestDishImageData:
    """data_manager dish-level image methods."""

    def test_save_and_get_dish_images(self, client, seed_dish):
        assert data_manager.save_dish_image(seed_dish, "001.png", caption="positive ref")
        images = data_manager.get_dish_images(seed_dish)
        assert len(images) == 1
        assert images[0]["dish_id"] == seed_dish
        assert images[0]["caption"] == "positive ref"

    def test_get_dish_images_empty(self, client, seed_dish):
        images = data_manager.get_dish_images(seed_dish)
        assert images == []

    def test_multiple_dish_images_ordered(self, client, seed_dish):
        data_manager.save_dish_image(seed_dish, "001.png", caption="first")
        data_manager.save_dish_image(seed_dish, "002.png", caption="second")
        images = data_manager.get_dish_images(seed_dish)
        assert len(images) == 2
        assert images[0]["caption"] == "first"
        assert images[1]["caption"] == "second"


class TestMapzebrainParsing:
    """Genotype parsing for mapzebrain atlas lookup."""

    def test_parse_single_transgene(self):
        terms = data_manager._parse_genotype_terms("Tg(elavl3:GCaMP6s)")
        assert terms == [("elavl3", "gcamp6s")]

    def test_parse_double_transgene(self):
        terms = data_manager._parse_genotype_terms(
            "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)"
        )
        assert len(terms) == 2
        assert terms[0] == ("gfap", "trpv1-t2a-gfp")
        assert terms[1] == ("elavl3", "jrgeco1b")

    def test_parse_no_tg(self):
        terms = data_manager._parse_genotype_terms("wild-type AB")
        assert terms == []

    def test_parse_promoter_only(self):
        terms = data_manager._parse_genotype_terms("Tg(elavl3)")
        assert terms == [("elavl3", "")]


