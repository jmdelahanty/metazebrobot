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
    _, big = _empty_plate(client, screened=20)  # 12 wells, room for 20 fish
    for _ in range(12):
        client.post(f"/dishes/{big}/plate/add-fish", data={})
    assert "No empty wells left" in client.post(f"/dishes/{big}/plate/add-fish", data={}).text


def test_plate_map_page_offers_setup(client):
    _, plate = _screened_dish(client)
    page = client.get(f"/dishes/{plate}/plate-map")
    assert "Set up wells" in page.text and "12-well plate" in page.text


def _empty_plate(client, screened=8):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1,
        genotype="Tg(gfap:PMCA2-mCherry-zf)", responsible="test-user", fish_count=20,
        dof="20261008", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    dish["screening_results"] = {"screenings": [{
        "screening_datetime": "20261014T10:00:00", "dpf_screened": 6,
        "indicators_screened": ["mCherry"], "count_screened_this_step": screened, "allocations": [],
    }]}
    assert data_manager.save_fish_dish(dish)
    resp = client.post(f"/screening/{dish['dish_id']}/steps/20261014T10:00:00/split",
                       data={"population_type": "positive_screened", "container_type": "well_plate",
                             "plate_wells": "12", "fish_count": ""}, follow_redirects=False)
    assert resp.status_code == 303
    plate = f"{dish['dish_id']}_pos1"
    assert resp.headers["location"] == f"/dishes/{plate}/fish/"
    return dish["dish_id"], plate


def _counts(client, *dish_ids):
    return tuple(client.get(f"/dishes/{d}").json()["current_fish_count"] for d in dish_ids)


def test_empty_plate_grows_with_each_fish_while_screening(client):
    parent, plate = _empty_plate(client)
    assert len(_wells(plate)) == 12
    assert _counts(client, parent, plate) == (20, 0)

    for _ in range(3):
        client.post(f"/dishes/{plate}/plate/add-fish", data={})

    assert _counts(client, parent, plate) == (17, 3)
    step = client.get(f"/dishes/{parent}").json()["data"]["screening_results"]["screenings"][0]
    assert [(a["bucket"], a["disposition"], a["count"]) for a in step["allocations"]] == [
        ("positive_screened", "derived_dish", 3)]
    page = client.get(f"/dishes/{plate}/plate-map").text
    assert "PMCA2-mCherry-zf+" in page


def test_cannot_place_more_fish_than_were_screened(client):
    parent, plate = _empty_plate(client, screened=2)
    client.post(f"/dishes/{plate}/plate/add-fish", data={})
    client.post(f"/dishes/{plate}/plate/add-fish", data={})
    third = client.post(f"/dishes/{plate}/plate/add-fish", data={})
    assert "already allocated" in third.text
    assert len(client.get(f"/dishes/{plate}/fish").json()["items"]) == 2
    assert _counts(client, parent, plate) == (18, 2)


def test_plate_created_with_a_count_only_grows_past_it(client):
    # Split with an explicit count of 5 from a step whose 20 fish are all allocated
    # (15 negatives stay): five fish fit the count, a sixth would exceed the screen.
    parent, plate = _screened_dish(client)
    client.post(f"/dishes/{plate}/plate/setup", data={"wells": 12})
    for _ in range(5):
        client.post(f"/dishes/{plate}/plate/add-fish", data={})
    assert _counts(client, parent, plate) == (15, 5)
    assert "already allocated" in client.post(f"/dishes/{plate}/plate/add-fish", data={}).text
    assert len(client.get(f"/dishes/{plate}/fish").json()["items"]) == 5


def test_count_still_required_for_other_containers(client):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1, genotype="Tg(x:y)",
        responsible="t", fish_count=5, dof="20261008", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    dish["screening_results"] = {"screenings": [{
        "screening_datetime": "20261014T10:00:00", "dpf_screened": 6,
        "indicators_screened": ["x"], "count_screened_this_step": 5, "allocations": []}]}
    data_manager.save_fish_dish(dish)
    resp = client.post(f"/screening/{dish['dish_id']}/steps/20261014T10:00:00/split",
                       data={"population_type": "positive_screened", "container_type": "petri_dish",
                             "fish_count": ""})
    assert "Enter a count" in resp.text


def test_screening_page_forms_carry_the_dish_id(client):
    parent, _ = _empty_plate(client)  # creates _pos1 and a step at 20261014T10:00:00
    page = client.get(f"/screening/{parent}").text
    assert "/screening//" not in page
    assert f'action="/screening/{parent}/steps/20261014T10:00:00/split"' in page

    # A stale page (rendered before the fix) gets a reload message; nothing is saved.
    for action in ("split", "allocations", "destination"):
        resp = client.post(f"/screening//steps/20261014T10:00:00/{action}", data={})
        assert resp.status_code == 200 and "out of date" in resp.text
