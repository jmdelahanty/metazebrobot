"""Crossing tank group from the aquatics sticker, entered on the new-dish form."""

import uuid

import pytest

from metazebrobot.api_server import _normalize_source_group
from metazebrobot.data.data_manager import data_manager


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
