"""Per-construct screening calls inherited by dishes and fish."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish

GENOTYPE = "Tg(gfap:PMCA2-mCherry-zf)"


def _dish(cross_id, number, step=None, container="petri_dish", fish_count=10):
    dish = FishDish.create_new(
        cross_id=cross_id, dish_number=number, genotype=GENOTYPE,
        responsible="test-user", fish_count=fish_count, dof="20260930",
        container_type=container,
    ).model_dump(mode="json", exclude_none=True)
    if step:
        dish["screening_results"] = {"screenings": [step]}
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def _step(bucket=None, kept=None, when="20261005T11:18:00"):
    step = {"screening_datetime": when, "dpf_screened": 5, "indicators_screened": ["mCherry"],
            "count_screened_this_step": 10, "allocations": []}
    if bucket:
        step["allocations"] = [{"bucket": bucket, "disposition": "remain_parent", "count": 10}]
    if kept is not None:
        step["number_kept"] = kept
    return step


def _calls(body):
    return [(c["dish_construct"], c["result"], c["confidence"]) for c in body["calls"]]


def test_fish_inherits_its_origin_dish_call(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    pos = _dish(cross, 1, _step("positive_screened"))
    fish_id = client.post(f"/dishes/{pos}/fish", json={}).json()["fish_id"]

    body = client.get(f"/fish/{fish_id}/screening").json()

    assert body["origin_dish_id"] == pos
    # "mCherry" only names the readout, so the step-to-construct link is medium.
    assert _calls(body) == [(GENOTYPE, "positive", "medium")]
    assert body["calls"][0]["basis"] == "remained_in_dish_as_positive_screened"
    assert body["calls"][0]["source"] == "inherited"


def test_plate_of_mixed_fish_has_no_dish_call_but_each_fish_keeps_its_own(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    pos = _dish(cross, 1, _step("positive_screened"))
    neg = _dish(cross, 2, _step("negative_screened", when="20261005T11:20:00"))
    plate = _dish(cross, 3, container="well_plate", fish_count=0)
    wells = [client.post(f"/dishes/{plate}/units",
                         json={"unit_kind": "well", "position_label": p}).json()["unit_id"]
             for p in ("A1", "A3")]
    fish = []
    for source, well in ((pos, wells[0]), (neg, wells[1])):
        fid = client.post(f"/dishes/{source}/fish", json={}).json()["fish_id"]
        assert client.post(f"/fish/{fid}/assign", json={"unit_id": well}).status_code == 200
        fish.append(fid)

    plate_calls = client.get(f"/dishes/{plate}/screening-calls").json()
    assert plate_calls["calls"] == []
    assert plate_calls["status"] == "partial_mixed_sources"
    assert _calls(client.get(f"/fish/{fish[0]}/screening").json()) == [(GENOTYPE, "positive", "medium")]
    assert _calls(client.get(f"/fish/{fish[1]}/screening").json()) == [(GENOTYPE, "negative", "medium")]


def test_unclassified_remainder_gives_no_call(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    dish = _dish(cross, 1, _step("remaining_in_parent"))
    assert client.get(f"/dishes/{dish}/screening-calls").json()["calls"] == []


def test_legacy_kept_count_is_positive_capped_at_medium(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    dish = _dish(cross, 1, _step(kept=5))
    calls = client.get(f"/dishes/{dish}/screening-calls").json()["calls"]
    assert [(c["result"], c["confidence"], c["basis"]) for c in calls] == [
        ("positive", "medium", "legacy_number_kept")]


def test_unknown_fish_and_dish(client):
    assert client.get(f"/fish/{uuid.uuid4()}/screening").status_code == 404
    assert client.get("/dishes/NOPE/screening-calls").json()["detail"]["error"] == "dish_not_found"
