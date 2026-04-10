"""
Pydantic model validation tests — no database needed.

    pixi run pytest tests/test_models.py -v
"""

import pytest
from pydantic import ValidationError

from metazebrobot.models.fish_dish import (
    Enclosure,
    FishDish,
    QualityCheckData,
    ScreeningStep,
)
from metazebrobot.models.pyrat_crossing import PyRATCrossing


class TestQualityCheckData:
    """Validate QualityCheckData date format constraints."""

    def test_valid_check_time(self):
        qc = QualityCheckData(check_time="20260401T09:30:00", fed=True)
        assert qc.check_time == "20260401T09:30:00"

    def test_invalid_check_time_no_t_separator(self):
        with pytest.raises(ValidationError, match="Missing 'T' separator"):
            QualityCheckData(check_time="2026-04-01 09:30:00")

    def test_invalid_check_time_bad_date(self):
        with pytest.raises(ValidationError):
            QualityCheckData(check_time="99999999T09:30:00")

    def test_invalid_check_time_bad_time(self):
        with pytest.raises(ValidationError):
            QualityCheckData(check_time="20260401T25:00:00")


class TestScreeningStep:
    """Validate ScreeningStep constraints."""

    VALID_STEP = dict(
        screening_datetime="20260401T14:00:00",
        dpf_screened=5,
        indicators_screened=["GFP"],
        pigment_screened=False,
        criteria="fluorescence",
        count_screened_this_step=20,
        number_kept=12,
    )

    def test_valid_step(self):
        step = ScreeningStep(**self.VALID_STEP)
        assert step.number_kept == 12
        assert step.indicators_screened == ["GFP"]

    def test_pigment_only_step(self):
        data = {**self.VALID_STEP, "indicators_screened": [], "pigment_screened": True}
        step = ScreeningStep(**data)
        assert step.indicators_screened == []
        assert step.pigment_screened is True

    def test_multi_indicator_step(self):
        data = {**self.VALID_STEP, "indicators_screened": ["GFP", "jRGECO"], "pigment_screened": True}
        step = ScreeningStep(**data)
        assert step.indicators_screened == ["GFP", "jRGECO"]
        assert step.pigment_screened is True

    def test_negative_count_screened(self):
        data = {**self.VALID_STEP, "count_screened_this_step": -1}
        with pytest.raises(ValidationError):
            ScreeningStep(**data)

    def test_negative_number_kept(self):
        data = {**self.VALID_STEP, "number_kept": -5}
        with pytest.raises(ValidationError):
            ScreeningStep(**data)

    def test_invalid_screening_datetime(self):
        data = {**self.VALID_STEP, "screening_datetime": "not-a-date"}
        with pytest.raises(ValidationError):
            ScreeningStep(**data)

    def test_screening_datetime_required(self):
        data = {**self.VALID_STEP, "screening_datetime": ""}
        with pytest.raises(ValidationError, match="screening_datetime is required"):
            ScreeningStep(**data)

    def test_negative_removed_pigmented(self):
        data = {**self.VALID_STEP, "number_removed_pigmented": -1}
        with pytest.raises(ValidationError):
            ScreeningStep(**data)


class TestEnclosure:
    """Validate Enclosure container_type Literal."""

    def test_default_container_type(self):
        enc = Enclosure()
        assert enc.container_type == "petri_dish"

    def test_valid_container_types(self):
        for ct in ("petri_dish", "beaker", "well_plate", "tank"):
            enc = Enclosure(container_type=ct)
            assert enc.container_type == ct

    def test_invalid_container_type(self):
        from pydantic import ValidationError as VE
        with pytest.raises(VE):
            Enclosure(container_type="bucket")

    def test_no_in_beaker_field(self):
        """in_beaker was removed — it should not appear on the model."""
        enc = Enclosure()
        assert not hasattr(enc, "in_beaker")
        assert enc.container_type == "petri_dish"


class TestFishDish:
    """Validate FishDish population_type and date constraints."""

    def test_invalid_population_type(self):
        with pytest.raises(ValidationError):
            FishDish(
                dish_id="X",
                date_created="20260401",
                cross_id="C1",
                dof="20260301",
                genotype="wt",
                responsible="jd",
                fish_count=10,
                breeding={"parents": []},
                enclosure={},
                dish_population_type="INVALID",
            )

    def test_valid_population_types(self):
        for pt in ("primary", "negative_screened", "positive_screened", "other"):
            dish = FishDish(
                dish_id="X",
                date_created="20260401",
                cross_id="C1",
                dof="20260301",
                genotype="wt",
                responsible="jd",
                fish_count=10,
                breeding={"parents": []},
                enclosure={},
                dish_population_type=pt,
            )
            assert dish.dish_population_type == pt

    def test_invalid_dof_format(self):
        with pytest.raises(ValidationError, match="Invalid date format"):
            FishDish(
                dish_id="X",
                date_created="20260401",
                cross_id="C1",
                dof="2026-03-01",
                genotype="wt",
                responsible="jd",
                fish_count=10,
                breeding={"parents": []},
                enclosure={},
            )

    def test_sex_literal(self):
        with pytest.raises(ValidationError):
            FishDish(
                dish_id="X",
                date_created="20260401",
                cross_id="C1",
                dof="20260301",
                genotype="wt",
                responsible="jd",
                fish_count=10,
                sex="hermaphrodite",
                breeding={"parents": []},
                enclosure={},
            )


class TestPyRATCrossingPerformance:
    """Validate PyRAT crossing performance precedence rules."""

    def test_prefers_backend_v1_counts_over_children_and_description(self):
        crossing = PyRATCrossing.from_api_dict(
            {
                "crossing_id": 14783,
                "description": "2 Groups for Robot Avoidance Assay",
                "crossing_tanks": 2,
                "raised_tanks": 1,
                "really_raised_tanks": 1,
                "tanks": {"children": []},
            }
        )

        assert crossing.raised_count == 1
        assert crossing.performance_target_count == 2
        assert crossing.performance == 0.5
        assert crossing.performance_display == "50%"
        assert crossing.performance_ratio_display == "1 / 2"

    def test_falls_back_to_children_and_description_when_detail_counts_missing(self):
        crossing = PyRATCrossing.from_api_dict(
            {
                "crossing_id": 20001,
                "description": "2 groups for screening",
                "tanks": {
                    "children": [
                        {"tank_id": 1},
                    ]
                },
            }
        )

        assert crossing.raised_count == 1
        assert crossing.performance_target_count == 2
        assert crossing.performance == 0.5
        assert crossing.performance_ratio_display == "1 / 2"
