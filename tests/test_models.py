"""
Pydantic model validation tests — no database needed.

    pixi run pytest tests/test_models.py -v
"""

import pytest
from pydantic import ValidationError

from metazebrobot.models.fish_dish import (
    FishDish,
    QualityCheckData,
    ScreeningStep,
)


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
        indicator_screened="GFP",
        criteria="fluorescence",
        count_screened_this_step=20,
        number_positive=12,
    )

    def test_valid_step(self):
        step = ScreeningStep(**self.VALID_STEP)
        assert step.number_positive == 12

    def test_negative_count_screened(self):
        data = {**self.VALID_STEP, "count_screened_this_step": -1}
        with pytest.raises(ValidationError):
            ScreeningStep(**data)

    def test_negative_number_positive(self):
        data = {**self.VALID_STEP, "number_positive": -5}
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
