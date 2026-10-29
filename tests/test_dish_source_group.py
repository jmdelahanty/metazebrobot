"""Crossing tank group from the aquatics sticker, entered on the new-dish form."""

import uuid

import pytest

from metazebrobot.api_server import _normalize_source_group
from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


@pytest.mark.parametrize("typed,saved", [
    ("1", "19445-G1"), (" 2 ", "19445-G2"), ("G3", "19445-G3"), ("g03", "19445-G3"),
    ("19445-G1", "19445-G1"), ("", None), (None, None),
    ("19329-G1", "19329-G1"),  # another cross's group is kept as typed
    ("tank 4", "tank 4"),
])
def test_normalize_source_group(typed, saved):
    assert _normalize_source_group("19445", typed) == saved


def test_new_dish_records_and_shows_crossing_tank_group(client):
    cross = f"9{uuid.uuid4().int % 10**8}"
    assert 'name="source_group_id"' in client.get("/dishes/new").text
    resp = client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 1, "genotype": "wt", "responsible": "t",
        "dof": "2026-10-23", "source_group_id": " 2 "}, follow_redirects=False)
    assert resp.status_code == 303
    assert data_manager.load_single_dish(f"{cross}_1")["source_group_id"] == f"{cross}-G2"
    assert f"group {cross}-G2" in client.get(f"/screening/{cross}_1").text

    client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 2, "genotype": "wt", "responsible": "t",
        "dof": "2026-10-23", "source_group_id": ""})
    assert data_manager.load_single_dish(f"{cross}_2").get("source_group_id") is None


def test_count_screened_defaults_to_the_dish_total(client):
    cross = f"9{uuid.uuid4().int % 10**8}"
    client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 1, "genotype": "wt", "responsible": "t",
        "dof": "2026-10-23", "fish_count": 37})
    page = client.get(f"/screening/{cross}_1").text
    assert 'name="count_screened_this_step" min="0" value="37"' in page


def test_new_step_time_defaults_to_now(client):
    dish = FishDish.create_new(
        cross_id=f"9{uuid.uuid4().int % 10**8}", dish_number=1, genotype="Tg(x:y)", responsible="t",
        fish_count=5, dof="20261023", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    assert data_manager.save_fish_dish(dish)
    page = client.get(f"/screening/{dish['dish_id']}").text
    assert 'hx-on::config-request="stampStepTime(event)"' in page and "function nowLocalDT()" in page
