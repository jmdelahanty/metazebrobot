"""Fish timeline (docs/fish_timeline_design.md, step 1)."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


def _dish(cross_id, number, step=None, container="petri_dish", fish_count=10):
    dish = FishDish.create_new(
        cross_id=cross_id, dish_number=number, genotype="Tg(gfap:PMCA2-mCherry-zf)",
        responsible="test-user", fish_count=fish_count, dof="20260930",
        container_type=container,
    ).model_dump(mode="json", exclude_none=True)
    if step:
        dish["screening_results"] = {"screenings": [step]}
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def _setup(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    pos = _dish(cross, 1, {
        "screening_datetime": "20261005T11:18:00", "dpf_screened": 5,
        "indicators_screened": ["mCherry"], "count_screened_this_step": 10,
        "allocations": [{"bucket": "positive_screened", "disposition": "remain_parent", "count": 10}],
    })
    plate = _dish(cross, 2, container="well_plate", fish_count=0)
    a1 = client.post(f"/dishes/{plate}/units",
                     json={"unit_kind": "well", "position_label": "A1"}).json()["unit_id"]
    fish_id = client.post(f"/dishes/{pos}/fish", json={"subject_label": "Z1"}).json()["fish_id"]
    client.post(f"/fish/{fish_id}/assign", json={"unit_id": a1})
    client.patch(f"/fish/{fish_id}", json={"notes": "bright"})
    return pos, plate, fish_id


def test_timeline_follows_fish_from_screening_to_well(client):
    pos, plate, fish_id = _setup(client)

    t = client.get(f"/fish/{fish_id}/timeline").json()

    kinds = [e["kind"] for e in t["entries"]]
    assert kinds[:2] == ["fertilized", "screening"]
    assert {"registered", "placed", "edited"} <= set(kinds)
    assert (t["dish_id"], t["origin_dish_id"]) == (plate, pos)
    screening = next(e for e in t["entries"] if e["kind"] == "screening")
    assert screening["details"]["result"] == "positive"
    registered = next(e for e in t["entries"] if e["kind"] == "registered")
    assert registered["details"]["dish_id"] == pos
    placed = next(e for e in t["entries"] if e["kind"] == "placed")
    assert placed["details"]["dish_id"] == plate
    assert [e["at"] for e in t["entries"]] == sorted(e["at"] for e in t["entries"])
    assert any("notes" in e["details"].get("fields", []) for e in t["entries"] if e["kind"] == "edited")


def test_fish_page_renders(client):
    _, plate, fish_id = _setup(client)
    page = client.get(f"/fish/{fish_id}/view")
    assert page.status_code == 200
    assert "Z1" in page.text and plate in page.text and "positive" in page.text


def test_unknown_fish(client):
    assert client.get(f"/fish/{uuid.uuid4()}/timeline").json()["detail"]["error"] == "fish_not_found"
    assert client.get(f"/fish/{uuid.uuid4()}/view").status_code == 404


def test_registration_provenance(client, seed_dish):
    api_fish = client.post(f"/dishes/{seed_dish}/fish", json={},
                           headers={"X-Client-Name": "citrus"}).json()["fish_id"]
    client.cookies.set("metazebrobot_user", "Jeremy")
    client.post(f"/dishes/{seed_dish}/fish/register", data={"subject_label": "W1"})
    client.cookies.clear()
    web_fish = next(f["fish_id"] for f in client.get(f"/dishes/{seed_dish}/fish").json()["items"]
                    if f["subject_label"] == "W1")

    def registered(fid):
        return next(e for e in client.get(f"/fish/{fid}/timeline").json()["entries"]
                    if e["kind"] == "registered")

    assert registered(api_fish)["details"] == {**registered(api_fish)["details"],
                                               "created_via": "api", "created_by": "citrus"}
    assert "via the API by citrus" in registered(api_fish)["summary"]
    assert registered(web_fish)["details"]["created_via"] == "web_form"
    assert "by Jeremy" in registered(web_fish)["summary"]
