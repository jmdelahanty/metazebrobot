"""Crossing tank group from the aquatics sticker, entered on the new-dish form."""

import uuid

from metazebrobot.data.data_manager import data_manager


def test_new_dish_records_and_shows_crossing_tank_group(client):
    cross = f"G{uuid.uuid4().hex[:8]}"
    assert 'name="source_group_id"' in client.get("/dishes/new").text
    resp = client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 1, "genotype": "wt", "responsible": "t",
        "dof": "2026-10-23", "source_group_id": "  19445-G2 "}, follow_redirects=False)
    assert resp.status_code == 303
    dish = data_manager.load_single_dish(f"{cross}_1")
    assert dish["source_group_id"] == "19445-G2"
    assert "group 19445-G2" in client.get(f"/screening/{cross}_1").text

    client.post("/dishes/new", data={
        "cross_id": cross, "dish_number": 2, "genotype": "wt", "responsible": "t",
        "dof": "2026-10-23", "source_group_id": ""})
    assert data_manager.load_single_dish(f"{cross}_2").get("source_group_id") is None
