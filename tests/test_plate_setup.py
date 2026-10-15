"""Plate setup while screening: wells, then place positive fish one by one."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


def _screened_dish(client):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1,
        genotype="Tg(gfap:PMCA2-mCherry-zf)", responsible="test-user", fish_count=20,
        dof="20261008", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    dish["screening_results"] = {"screenings": [{
        "screening_datetime": "20261013T11:00:00", "dpf_screened": 5,
        "indicators_screened": ["mCherry"], "count_screened_this_step": 20,
        "allocations": [{"bucket": "negative_screened", "disposition": "remain_parent", "count": 15}],
    }]}
    assert data_manager.save_fish_dish(dish)
    resp = client.post(f"/screening/{dish['dish_id']}/steps/20261013T11:00:00/split",
                       data={"fish_count": 5, "population_type": "positive_screened",
                             "container_type": "well_plate"}, follow_redirects=False)
    assert resp.status_code == 303
    return dish["dish_id"], f"{dish['dish_id']}_pos1"


def _wells(plate):
    return sorted(u["position_label"] for u in data_manager.get_housing_units_with_fish(plate))


def test_set_up_wells_then_place_fish_in_order_and_by_click(client):
    _, plate = _screened_dish(client)

    page = client.post(f"/dishes/{plate}/plate/setup", data={"wells": 12})
    assert "Created 12 wells" in page.text
    assert _wells(plate) == sorted(f"{r}{c}" for r in "ABC" for c in range(1, 5))
    assert client.post(f"/dishes/{plate}/plate/setup", data={"wells": 12}).text.count("Created 0 wells") == 1

    first = client.post(f"/dishes/{plate}/plate/add-fish", data={})
    assert "Placed Z1 in A1" in first.text and 'id="fish-table"' in first.text
    client.post(f"/dishes/{plate}/plate/add-fish", data={})
    c3 = f"{plate}:C3"
    clicked = client.post(f"/dishes/{plate}/plate/add-fish", data={"unit_id": c3})
    assert "Placed Z3 in C3" in clicked.text
    assert client.post(f"/dishes/{plate}/plate/add-fish", data={"unit_id": c3}).text.count(
        "empty well of this plate") == 1

    placed = {f["subject_label"]: f for f in client.get(f"/dishes/{plate}/fish").json()["items"]}
    assert {k: v["current_unit_id"].split(":")[-1] for k, v in placed.items()} == {
        "Z1": "A1", "Z2": "A2", "Z3": "C3"}
    z1 = placed["Z1"]
    assert z1["origin_dish_id"] == plate
    calls = client.get(f"/fish/{z1['fish_id']}/screening").json()["calls"]
    assert [(c["dish_construct"], c["result"]) for c in calls] == [
        ("Tg(gfap:PMCA2-mCherry-zf)", "positive")]
    registered = next(e for e in client.get(f"/fish/{z1['fish_id']}/timeline").json()["entries"]
                      if e["kind"] == "registered")
    assert "via plate setup" in registered["summary"]


def test_full_plate_and_bad_size(client):
    _, plate = _screened_dish(client)
    assert "Unsupported plate size" in client.post(f"/dishes/{plate}/plate/setup",
                                                   data={"wells": 7}).text
    client.post(f"/dishes/{plate}/plate/setup", data={"wells": 6})
    for _ in range(6):
        client.post(f"/dishes/{plate}/plate/add-fish", data={})
    assert "No empty wells left" in client.post(f"/dishes/{plate}/plate/add-fish", data={}).text


def test_plate_map_page_offers_setup(client):
    _, plate = _screened_dish(client)
    page = client.get(f"/dishes/{plate}/plate-map")
    assert "Set up wells" in page.text and "12-well plate" in page.text
