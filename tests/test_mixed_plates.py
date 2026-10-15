"""Mixed well plates: per-fish source and result (fish screening observations)."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish

GENOTYPE = "Tg(gfap:PMCA2-mCherry-zf)"


def _dish(cross, number, screened=None):
    dish = FishDish.create_new(
        cross_id=cross, dish_number=number, genotype=GENOTYPE, responsible="t",
        fish_count=10, dof="20261008", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    if screened:
        dish["screening_results"] = {"screenings": [{
            "screening_datetime": "20261015T15:13:00", "dpf_screened": 7,
            "indicators_screened": ["mCherry"], "count_screened_this_step": screened,
            "allocations": []}]}
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def _count(client, dish_id):
    return client.get(f"/dishes/{dish_id}").json()["current_fish_count"]


def _calls(client, fish_id):
    return [(c["dish_construct"], c["result"], c["source"])
            for c in client.get(f"/fish/{fish_id}/screening").json()["calls"]]


def _by_label(client, plate):
    return {f["subject_label"]: f for f in client.get(f"/dishes/{plate}/fish").json()["items"]}


def test_mixed_plate_with_positives_negatives_and_unscreened(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    screened = _dish(cross, 1, screened=10)
    other = _dish(cross, 2)

    resp = client.post(f"/dishes/{screened}/plate/new", data={"wells": 12}, follow_redirects=False)
    plate = f"{screened}_plate1"
    assert resp.headers["location"] == f"/dishes/{plate}/fish/"

    for result in ("positive", "positive", "negative"):
        page = client.post(f"/dishes/{plate}/plate/add-fish",
                           data={"source_dish_id": screened, "result": result})
        assert f"from {screened}" in page.text
    client.post(f"/dishes/{plate}/plate/add-fish", data={"source_dish_id": other})

    fish = _by_label(client, plate)
    assert {k: v["current_unit_id"].split(":")[-1] for k, v in fish.items()} == {
        "Z1": "A1", "Z2": "A2", "Z3": "A3", "Z4": "A4"}
    assert _calls(client, fish["Z1"]["fish_id"]) == [(GENOTYPE, "positive", "observed")]
    assert _calls(client, fish["Z3"]["fish_id"]) == [(GENOTYPE, "negative", "observed")]
    assert _calls(client, fish["Z4"]["fish_id"]) == []
    assert fish["Z1"]["origin_dish_id"] == screened and fish["Z4"]["origin_dish_id"] == other
    assert (_count(client, screened), _count(client, other), _count(client, plate)) == (7, 9, 4)

    step = client.get(f"/dishes/{screened}").json()["data"]["screening_results"]["screenings"][0]
    booked = {}
    for a in step["allocations"]:
        booked[a["bucket"]] = booked.get(a["bucket"], 0) + a["count"]
    assert booked == {"positive_screened": 2, "negative_screened": 1}

    page = client.get(f"/dishes/{plate}/plate-map").text
    assert "PMCA2-mCherry-zf+" in page and "PMCA2-mCherry-zf−" in page
    timeline = client.get(f"/fish/{fish['Z1']['fish_id']}/timeline").json()["entries"]
    assert any(e["kind"] == "observed" for e in timeline)


def test_result_needs_a_screening_step_on_the_source(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    source = _dish(cross, 1)
    client.post(f"/dishes/{source}/plate/new", data={"wells": 6})
    resp = client.post(f"/dishes/{source}_plate1/plate/add-fish",
                       data={"source_dish_id": source, "result": "positive"})
    assert "no screening step" in resp.text
    assert client.get(f"/dishes/{source}_plate1/fish").json()["items"] == []


def test_recheck_overrides_inherited_result(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    screened = _dish(cross, 1, screened=10)
    resp = client.post(f"/screening/{screened}/steps/20261015T15:13:00/split",
                       data={"population_type": "positive_screened", "container_type": "well_plate",
                             "plate_wells": "6", "fish_count": ""}, follow_redirects=False)
    plate = resp.headers["location"].split("/")[2]
    client.post(f"/dishes/{plate}/plate/add-fish", data={})
    z1 = _by_label(client, plate)["Z1"]["fish_id"]
    assert _calls(client, z1) == [(GENOTYPE, "positive", "inherited")]

    recheck = client.post(f"/fish/{z1}/observations",
                          json={"result": "negative", "dish_construct": GENOTYPE, "notes": "dim at 9 dpf"})
    assert recheck.status_code == 200
    assert _calls(client, z1) == [(GENOTYPE, "negative", "observed")]

    bad = client.post(f"/fish/{z1}/observations", json={"result": "negative", "dish_construct": "Tg(x:y)"})
    assert bad.status_code == 422 and bad.json()["detail"]["field"] == "dish_construct"


def test_result_on_a_split_plate_records_observation_from_its_step(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    screened = _dish(cross, 1, screened=10)
    resp = client.post(f"/screening/{screened}/steps/20261015T15:13:00/split",
                       data={"population_type": "positive_screened", "container_type": "well_plate",
                             "plate_wells": "6", "fish_count": ""}, follow_redirects=False)
    plate = resp.headers["location"].split("/")[2]
    client.post(f"/dishes/{plate}/plate/add-fish", data={"result": "negative"})
    z1 = _by_label(client, plate)["Z1"]["fish_id"]
    assert _calls(client, z1) == [(GENOTYPE, "negative", "observed")]


def test_screening_page_offers_new_plate(client):
    dish = _dish(f"CROSS_{uuid.uuid4().hex[:6]}", 1)
    assert "New well plate from this dish" in client.get(f"/screening/{dish}").text


def test_source_option_names_the_screening_group_and_mixed_plates_need_a_source(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    screened = _dish(cross, 1, screened=10)
    resp = client.post(f"/screening/{screened}/steps/20261015T15:13:00/split",
                       data={"population_type": "positive_screened", "container_type": "well_plate",
                             "plate_wells": "6", "fish_count": ""}, follow_redirects=False)
    split_plate = resp.headers["location"].split("/")[2]
    assert f"{screened} (screen 10-15 15:13, positives)" in client.get(
        f"/dishes/{split_plate}/plate-map").text

    client.post(f"/dishes/{screened}/plate/new", data={"wells": 6})
    mixed = f"{screened}_plate1"
    page = client.get(f"/dishes/{mixed}/plate-map").text
    assert "(screen " not in page
    assert f'<option value="{screened}" selected>' in page
    refused = client.post(f"/dishes/{mixed}/plate/add-fish", data={"source_dish_id": ""})
    assert "choose which dish the fish comes from" in refused.text
    assert client.get(f"/dishes/{mixed}/fish").json()["items"] == []
