"""
Direct data_manager method tests — no HTTP layer.

Uses the same temp DB fixture from conftest.py.  The `client` fixture
is required because the TestClient context manager runs `lifespan()`,
which initialises data_manager and creates all tables.

    pixi run pytest tests/test_data.py -v
"""

import json
import re
import uuid
from io import BytesIO

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


class TestGenotypeReferenceImageData:
    """data_manager curated full-genotype reference image methods."""

    def test_save_and_get_genotype_reference_images(self, client, seed_dish):
        genotype = f"Tg(elavl3:GCaMP6s);test-{uuid.uuid4().hex[:6]}"
        ref_id = data_manager.save_genotype_reference_image(
            genotype,
            "elavl3_gcamp_ref.png",
            caption="Known good expression",
            source_dish_id=seed_dish,
        )

        assert ref_id is not None
        refs = data_manager.get_genotype_reference_images(genotype)
        assert len(refs) == 1
        assert refs[0]["image_filename"] == "elavl3_gcamp_ref.png"
        assert refs[0]["caption"] == "Known good expression"
        assert refs[0]["source_dish_id"] == seed_dish
        assert refs[0]["reference_group_key"] == data_manager.genotype_reference_key(genotype)
        assert refs[0]["display_role"] == "reference"

    def test_save_structured_genotype_reference_image(self, client, seed_dish):
        genotype = f"Tg(elavl3:jGCaMP8f);Tg(her4.1:PMCA2-mCherry);test-{uuid.uuid4().hex[:6]}"
        ref_id = data_manager.save_genotype_reference_image(
            genotype,
            "her4_mcherry_channel.png",
            caption="her4.1 channel",
            reference_group_label="2026-04-23 source acquisition",
            display_role="channel",
            transgene="Tg(her4.1:PMCA2-mCherry)",
            channel_index=1,
            channel_name="mCher",
            fluor="mCherry",
            color_hex="#FF0900",
            source_dish_id=seed_dish,
        )

        assert ref_id is not None
        refs = data_manager.get_genotype_reference_images(genotype)
        assert len(refs) == 1
        assert refs[0]["reference_group_label"] == "2026-04-23 source acquisition"
        assert refs[0]["reference_group_key"].endswith("::2026-04-23 source acquisition")
        assert refs[0]["display_role"] == "channel"
        assert refs[0]["transgene_key"] == "Tg(her4.1:PMCA2-mCherry)"
        assert refs[0]["display_transgene"] == "Tg(her4.1:PMCA2-mCherry)"
        assert refs[0]["channel_index"] == 1
        assert refs[0]["channel_name"] == "mCher"
        assert refs[0]["fluor"] == "mCherry"
        assert refs[0]["color_hex"] == "#FF0900"

    def test_genotype_reference_matching_is_exact_after_whitespace_normalization(self, client):
        genotype = f"Tg(elavl3:GCaMP6s);test-{uuid.uuid4().hex[:6]}"
        data_manager.save_genotype_reference_image(
            genotype,
            "elavl3_gcamp_ref.png",
        )

        assert data_manager.get_genotype_reference_images(genotype)
        assert data_manager.get_genotype_reference_images(f" {genotype} ")
        assert data_manager.get_genotype_reference_images(genotype.replace("GCaMP6s", "GCaMP6f")) == []

    def test_genotype_reference_matching_ignores_semicolon_spacing(self, client):
        genotype_with_space = "Tg(elavl3:jGCaMP8f); Tg(her4.1:PMCA2-mCherry)"
        genotype_without_space = "Tg(elavl3:jGCaMP8f);Tg(her4.1:PMCA2-mCherry)"
        ref_id = data_manager.save_genotype_reference_image(
            genotype_without_space,
            "two_transgene_ref.png",
        )

        assert ref_id is not None
        refs = data_manager.get_genotype_reference_images(genotype_with_space)
        assert len(refs) == 1
        assert refs[0]["genotype_key"] == genotype_without_space

    def test_inactive_genotype_reference_images_are_hidden_by_default(self, client):
        genotype = f"Tg(elavl3:GCaMP6s);test-{uuid.uuid4().hex[:6]}"
        data_manager.save_genotype_reference_image(
            genotype,
            "inactive_ref.png",
            is_active=False,
        )

        assert data_manager.get_genotype_reference_images(genotype) == []
        refs = data_manager.get_genotype_reference_images(
            genotype,
            active_only=False,
        )
        assert len(refs) == 1
        assert refs[0]["image_filename"] == "inactive_ref.png"

    def test_list_genotype_reference_images(self, client):
        genotype = f"Tg(elavl3:GCaMP6s);test-{uuid.uuid4().hex[:6]}"
        ref_id = data_manager.save_genotype_reference_image(
            genotype,
            "listed_ref.png",
            caption="listed",
        )

        refs = data_manager.list_genotype_reference_images()

        assert ref_id is not None
        assert any(ref["id"] == ref_id and ref["caption"] == "listed" for ref in refs)

    def test_set_genotype_reference_active(self, client):
        genotype = f"Tg(elavl3:GCaMP6s);test-{uuid.uuid4().hex[:6]}"
        ref_id = data_manager.save_genotype_reference_image(genotype, "toggle_ref.png")

        assert ref_id is not None
        assert data_manager.set_genotype_reference_active(ref_id, False)
        assert data_manager.get_genotype_reference_images(genotype) == []
        refs = data_manager.get_genotype_reference_images(genotype, active_only=False)
        assert len(refs) == 1
        assert refs[0]["is_active"] == 0

    def test_deactivate_genotype_reference_group(self, client):
        genotype = f"Tg(elavl3:jGCaMP8f);Tg(her4.1:PMCA2-mCherry);test-{uuid.uuid4().hex[:6]}"
        ref_a = data_manager.save_genotype_reference_image(
            genotype,
            "group_composite.png",
            reference_group_label="same acquisition",
            display_role="composite",
        )
        ref_b = data_manager.save_genotype_reference_image(
            genotype,
            "group_channel.png",
            reference_group_label="same acquisition",
            display_role="channel",
        )
        refs = data_manager.get_genotype_reference_images(genotype)
        group_key = refs[0]["reference_group_key"]

        assert ref_a is not None
        assert ref_b is not None
        assert data_manager.deactivate_genotype_reference_group(genotype, group_key) == 2
        assert data_manager.get_genotype_reference_images(genotype) == []


class TestGenotypeParser:
    """parse_genotype() — structured transgene extraction."""

    def test_single_transgene(self):
        result = data_manager.parse_genotype("Tg(elavl3:GCaMP6s)")
        assert len(result) == 1
        assert result[0]["promoter"] == "elavl3"
        assert result[0]["reporter"] == "gcamp6s"
        assert result[0]["fluorophore"] == "gcamp"
        assert result[0]["construct"] == "Tg(elavl3:GCaMP6s)"

    def test_double_transgene(self):
        result = data_manager.parse_genotype(
            "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)"
        )
        assert len(result) == 2
        assert result[0]["promoter"] == "gfap"
        assert result[0]["fluorophore"] == "gfp"
        assert result[1]["promoter"] == "elavl3"
        assert result[1]["fluorophore"] == "jrgeco"

    def test_wildtype_returns_empty(self):
        assert data_manager.parse_genotype("wt") == []
        assert data_manager.parse_genotype("wild-type AB") == []

    def test_promoter_only(self):
        result = data_manager.parse_genotype("Tg(elavl3)")
        assert len(result) == 1
        assert result[0]["promoter"] == "elavl3"
        assert result[0]["reporter"] is None
        assert result[0]["fluorophore"] is None

    def test_fluorophore_extraction(self):
        cases = [
            ("GCaMP6s", "gcamp"),
            ("jRGECO1b", "jrgeco"),
            ("TRPV1-T2A-GFP", "gfp"),
            ("EGFP", "gfp"),
            ("mCherry", "mcherry"),
            ("H2BRFP", "rfp"),
            ("lynTagRFP", "rfp"),
            ("CaMPARI", "campari"),
            ("Cerulean", "cerulean"),
            ("tdTomato", "tdtomato"),
            ("SomeUnknownProtein", None),
        ]
        for reporter, expected in cases:
            assert data_manager._extract_fluorophore(reporter) == expected, f"Failed for {reporter}"

    def test_legacy_parse_genotype_terms(self):
        """_parse_genotype_terms still works as before (mapzebrain compat)."""
        terms = data_manager._parse_genotype_terms("Tg(elavl3:GCaMP6s)")
        assert terms == [("elavl3", "gcamp6s")]

    def test_sensor_and_effector_classification(self):
        result = data_manager.parse_genotype(
            "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:GRAB-5HT)"
        )

        assert result[0]["construct_role"] == "effector"
        assert result[0]["effector_family"] == "TRPV1"
        assert result[0]["fluorophore"] == "gfp"

        assert result[1]["construct_role"] == "sensor"
        assert result[1]["sensor_family"] == "GRAB"
        assert result[1]["sensor_target"] == "serotonin"

    def test_grabatp_sensor_target_classification(self):
        result = data_manager.parse_genotype("Tg(elavl3:GRABATP1.0)")

        assert len(result) == 1
        assert result[0]["construct_role"] == "sensor"
        assert result[0]["sensor_family"] == "GRAB"
        assert result[0]["sensor_target"] == "ATP"

    def test_promoter_only_construct_is_driver(self):
        result = data_manager.parse_genotype("Tg(elavl3)")
        assert result[0]["construct_role"] == "driver"


class TestDishTransgenes:
    """dish_transgenes table populated on save."""

    def test_transgenes_populated_on_split(self, client, seed_full_dish):
        """Splitting a dish populates dish_transgenes for the new dish."""
        client.post(
            f"/screening/{seed_full_dish}/split",
            data={"fish_count": 5, "population_type": "positive_screened"},
            follow_redirects=False,
        )
        new_id = f"{seed_full_dish}_pos1"
        tgs = data_manager.get_dish_transgenes(new_id)
        # seed_full_dish has genotype Tg(elavl3:GCaMP6s) — but let's check
        # what the parent has and verify child inherited it
        parent_tgs = data_manager.get_dish_transgenes(seed_full_dish)
        assert len(tgs) == len(parent_tgs)
        assert tgs[0]["construct_role"] == "sensor"
        assert tgs[0]["sensor_family"] == "GCaMP"
        assert tgs[0]["sensor_target"] == "calcium"
        assert tgs[0]["source_type"] == "parent_dish"
        assert tgs[0]["source_id"] == seed_full_dish

    def test_get_transgenes_empty(self, client, seed_dish):
        """Minimal seed dish (genotype without Tg prefix) has no transgenes."""
        # seed_dish has genotype "Tg(elavl3:GCaMP6s)" in conftest
        tgs = data_manager.get_dish_transgenes(seed_dish)
        # seed_dish is created via raw SQL, not save_fish_dish,
        # so transgenes are NOT auto-populated
        assert tgs == []

    def test_catalog_match_enriches_dish_transgenes(self, client):
        dish_data = {
            "dish_id": f"DISH_{uuid.uuid4().hex[:8]}",
            "cross_id": "17907",
            "date_created": "20260410",
            "dof": "20260407",
            "genotype": "Tg(elavl3:GRAB-5HT)",
            "responsible": "test-user",
            "fish_count": 10,
            "species": "Danio rerio",
            "sex": "unknown",
            "status": "active",
        }

        assert data_manager.save_fish_dish(dish_data)
        tgs = data_manager.get_dish_transgenes(dish_data["dish_id"])

        assert len(tgs) == 1
        assert tgs[0]["catalog_id"] is not None
        assert tgs[0]["catalog_name"] == "GRAB-5HT"
        assert tgs[0]["match_method"] == "alias_exact"
        assert tgs[0]["source_type"] == "crossing"
        assert tgs[0]["source_id"] == "17907"
        assert tgs[0]["construct_role"] == "sensor"
        assert tgs[0]["sensor_family"] == "GRAB"
        assert tgs[0]["sensor_target"] == "serotonin"
        assert tgs[0]["fluorophore"] == "gfp"
        assert tgs[0]["spectra"]["ex"] == 488
        assert tgs[0]["spectra"]["em"] == 509

    def test_grabatp_catalog_match_enriches_dish_transgenes(self, client):
        dish_data = {
            "dish_id": f"DISH_{uuid.uuid4().hex[:8]}",
            "cross_id": "18178",
            "date_created": "20260518",
            "dof": "20260512",
            "genotype": "Tg(elavl3:GRABATP1.0)",
            "responsible": "test-user",
            "fish_count": 10,
            "species": "Danio rerio",
            "sex": "unknown",
            "status": "active",
        }

        assert data_manager.save_fish_dish(dish_data)
        tgs = data_manager.get_dish_transgenes(dish_data["dish_id"])

        assert len(tgs) == 1
        assert tgs[0]["catalog_id"] is not None
        assert tgs[0]["catalog_name"] == "GRABATP1.0"
        assert tgs[0]["match_method"] == "alias_exact"
        assert tgs[0]["construct_role"] == "sensor"
        assert tgs[0]["sensor_family"] == "GRAB"
        assert tgs[0]["sensor_target"] == "ATP"
        assert tgs[0]["fluorophore"] == "cpEGFP"
        assert tgs[0]["spectra"]["ex"] == 500
        assert tgs[0]["spectra"]["em"] == 520


class TestCrossingIndicatorNormalization:
    """crossing indicator rows should persist normalized construct metadata."""

    def test_save_and_load_crossing_indicators_include_normalized_fields(self, client):
        indicators = [
            {
                "modification_type": "tg",
                "promoter_driver": "elavl3",
                "reporter_effector": "GRAB-5HT",
                "color": "Green",
                "expected_expression": "pan-neuronal",
            }
        ]

        assert data_manager.save_crossing_indicators("17907", indicators)
        saved = data_manager.get_crossing_indicators("17907")

        assert len(saved) == 1
        assert saved[0]["promoter_norm"] == "elavl3"
        assert saved[0]["reporter_norm"] == "grab-5ht"
        assert saved[0]["catalog_id"] is not None
        assert saved[0]["catalog_name"] == "GRAB-5HT"
        assert saved[0]["match_method"] == "alias_exact"
        assert saved[0]["construct_role"] == "sensor"
        assert saved[0]["sensor_family"] == "GRAB"
        assert saved[0]["sensor_target"] == "serotonin"
        assert saved[0]["fluorophore"] == "gfp"
        assert saved[0]["spectra"]["color"] == "green"


class TestConstructCatalog:
    """construct catalog seed and alias resolution."""

    def test_alias_resolution_uses_seed_catalog(self, client):
        catalog_id, match_method = data_manager.resolve_construct_catalog_match("grab_5ht")

        assert catalog_id is not None
        assert match_method == "alias_exact"

    def test_grabatp_alias_resolution_uses_seed_catalog(self, client):
        for alias in ("GRABATP1.0", "GRAB_ATP1.0", "GRAB-ATP"):
            catalog_id, match_method = data_manager.resolve_construct_catalog_match(alias)

            assert catalog_id is not None
            assert match_method == "alias_exact"


class TestMapzebrainLookup:
    """mapzebrain matching should not fall back to promoter-only hits."""

    def test_best_catalog_match_requires_reporter_match(self):
        catalog = [
            {
                "name": "jf9Tg",
                "synonyms": "elavl3:CaMPARI, Tg[elavl3:CaMPARI]",
                "stack": "https://api.mapzebrain.org/media/Lines/elavl3CaMPARI/average_data/T_AVG_jf9Tg.zip",
            }
        ]

        assert data_manager._find_best_catalog_match(catalog, "elavl3", "grab-5ht") is None

    def test_best_catalog_match_allows_exact_gene_expression_promoter_match(self):
        catalog = [
            {
                "name": "her4.1",
                "category": "Gene expression",
                "types": ["HCR in situ"],
                "synonyms": None,
                "stack": "https://api.mapzebrain.org/media/Lines/her41/average_data/T_AVG_her4.1.zip",
            }
        ]

        result = data_manager._find_best_catalog_match(catalog, "her4.1", "pmca-mcherry")

        assert result is not None
        assert result["name"] == "her4.1"
        assert result["folder"] == "her41"

    def test_best_catalog_match_prefers_reporter_hit_over_gene_expression_fallback(self):
        catalog = [
            {
                "name": "her4.1",
                "category": "Gene expression",
                "types": ["HCR in situ"],
                "synonyms": None,
                "stack": "https://api.mapzebrain.org/media/Lines/her41/average_data/T_AVG_her4.1.zip",
            },
            {
                "name": "hypotheticalHer41Tg",
                "category": "Transgenic line",
                "synonyms": "her4.1:PMCA-mCherry",
                "stack": "https://api.mapzebrain.org/media/Lines/her41PMCA/average_data/T_AVG_hypothetical.zip",
            },
        ]

        result = data_manager._find_best_catalog_match(catalog, "her4.1", "pmca-mcherry")

        assert result is not None
        assert result["name"] == "hypotheticalHer41Tg"
        assert result["folder"] == "her41PMCA"

    def test_best_catalog_match_prefers_positive_reporter_hit(self):
        catalog = [
            {
                "name": "jf9Tg",
                "synonyms": "elavl3:CaMPARI, Tg[elavl3:CaMPARI]",
                "stack": "https://api.mapzebrain.org/media/Lines/elavl3CaMPARI/average_data/T_AVG_jf9Tg.zip",
            },
            {
                "name": "jf4Tg",
                "synonyms": "HuC:GCaMP6s, elavl3:GCaMP6s",
                "stack": "https://api.mapzebrain.org/media/Lines/elavl3GCaMP6s/average_data/T_AVG_elavl3GCaMP6s.zip",
            },
        ]

        result = data_manager._find_best_catalog_match(catalog, "elavl3", "gcamp6s")

        assert result is not None
        assert result["name"] == "jf4Tg"
        assert result["display_name"] == "jf4Tg"

    def test_fetch_mapzebrain_catalog_prefers_live_api_then_updates_cache(self, monkeypatch, tmp_path):
        cache_path = tmp_path / "mapzebrain_catalog.json"
        cache_path.write_text(json.dumps([{"name": "cached", "synonyms": "", "stack": "cached"}]))

        class DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return BytesIO(
                    json.dumps([{"name": "live", "synonyms": "", "stack": "live"}]).encode("utf-8")
                ).read()

        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: DummyResponse())
        monkeypatch.setattr(data_manager, "config_dir", tmp_path)
        monkeypatch.setattr(data_manager, "_mapzebrain_catalog", None)

        result = data_manager.fetch_mapzebrain_catalog()

        assert result == [{"name": "live", "synonyms": "", "stack": "live"}]
        assert json.loads(cache_path.read_text()) == result

    def test_fetch_mapzebrain_catalog_falls_back_to_cache(self, monkeypatch, tmp_path):
        cached = [{"name": "cached", "synonyms": "", "stack": "cached"}]
        (tmp_path / "mapzebrain_catalog.json").write_text(json.dumps(cached))

        import urllib.request

        def fail_urlopen(req, timeout=10):
            raise OSError("network down")

        monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
        monkeypatch.setattr(data_manager, "config_dir", tmp_path)
        monkeypatch.setattr(data_manager, "_mapzebrain_catalog", None)

        result = data_manager.fetch_mapzebrain_catalog()

        assert result == cached
