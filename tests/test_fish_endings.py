"""Fish deaths and endings (docs/fish_deaths_design.md)."""

import uuid

import pytest

from metazebrobot.controllers.fish_dish_controller import FishDishController
from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


def _dish(fish_count=10, container="well_plate"):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1, genotype="Tg(elavl3:GCaMP6s)",
        responsible="test-user", fish_count=fish_count, dof="20260930", container_type=container,
    ).model_dump(mode="json", exclude_none=True)
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def _fish_in_well(client, dish_id, label="Z1", well="A1"):
    unit = client.post(f"/dishes/{dish_id}/units",
                       json={"unit_kind": "well", "position_label": well}).json()["unit_id"]
    fish_id = client.post(f"/dishes/{dish_id}/fish", json={"subject_label": label}).json()["fish_id"]
    assert client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit}).status_code == 200
    return fish_id, unit


def _count(client, dish_id):
    return client.get(f"/dishes/{dish_id}").json()["current_fish_count"]


class TestFishDeath:
    def test_found_dead_in_well(self, client):
        dish = _dish()
        fish_id, unit = _fish_in_well(client, dish)

        body = {"reason": "found_dead", "at": "2026-10-15T14:00:00Z", "notes": "Z1 still"}
        resp = client.post(f"/fish/{fish_id}/end", json=body)

        assert resp.status_code == 200
        fish = resp.json()
        assert (fish["status"], fish["end_reason"], fish["ended_precision"]) == ("dead", "found_dead", "time")
        assert fish["ended_at"] == "2026-10-15 14:00:00"
        assert _count(client, dish) == 9
        assert client.get(f"/dishes/{dish}/fish").json()["items"] == []  # hidden by default
        listed = client.get(f"/dishes/{dish}/fish", params={"include_ended": "true"}).json()["items"]
        assert [f["status"] for f in listed] == ["dead"]
        assert client.get(f"/units/{unit}").status_code == 200
        history = client.get(f"/fish/{fish_id}/history").json()["items"]
        assert all(h["moved_out_at"] for h in history)

        assert client.post(f"/fish/{fish_id}/end", json=body).status_code == 200  # identical repeat
        assert _count(client, dish) == 9  # not counted twice
        other = client.post(f"/fish/{fish_id}/end", json={**body, "reason": "euthanized"})
        assert other.status_code == 409 and other.json()["detail"]["error"] == "fish_already_ended"
        moved = client.post(f"/fish/{fish_id}/assign", json={"unit_id": unit})
        assert moved.status_code == 409 and moved.json()["detail"]["error"] == "fish_ended"

    def test_death_without_well_counts_on_the_dish(self, client):
        dish = _dish(container="petri_dish")
        fish_id = client.post(f"/dishes/{dish}/fish", json={}).json()["fish_id"]
        assert client.post(f"/fish/{fish_id}/end", json={"reason": "euthanized"}).status_code == 200
        assert _count(client, dish) == 9

    @pytest.mark.parametrize("body, field", [
        ({"reason": "lost"}, "reason"),
        ({"reason": "found_dead", "at": "2026-10-15 14:00"}, "at"),
    ])
    def test_invalid(self, client, seed_dish, body, field):
        fish_id = client.post(f"/dishes/{seed_dish}/fish", json={}).json()["fish_id"]
        resp = client.post(f"/fish/{fish_id}/end", json=body)
        assert resp.status_code == 422 and resp.json()["detail"]["field"] == field

    def test_unknown_fish(self, client):
        assert client.post(f"/fish/{uuid.uuid4()}/end", json={"reason": "other"}).status_code == 404


class TestDishTermination:
    def test_euthanasia_ends_living_fish_and_reactivation_restores_them(self, client):
        dish = _dish()
        fish_id, unit = _fish_in_well(client, dish)
        ctrl = FishDishController()

        ok, _ = ctrl.update_dish_status(dish, "inactive", "20261015", "euthanasia")
        assert ok
        fish = client.get(f"/fish/{fish_id}").json()
        assert (fish["status"], fish["end_reason"], fish["ended_precision"], fish["ended_at"]) \
            == ("dead", "euthanized", "day", "2026-10-15")

        ok, _ = ctrl.update_dish_status(dish, "active")
        assert ok
        fish = client.get(f"/fish/{fish_id}").json()
        assert (fish["status"], fish["ended_at"]) == ("alive", None)
        open_rows = [h for h in client.get(f"/fish/{fish_id}/history").json()["items"]
                     if not h["moved_out_at"]]
        assert [h["unit_id"] for h in open_rows] == [unit]

    def test_fish_death_survives_dish_reactivation(self, client):
        dish = _dish()
        dead, _ = _fish_in_well(client, dish, "Z1", "A1")
        client.post(f"/fish/{dead}/end", json={"reason": "found_dead"})
        ctrl = FishDishController()
        ctrl.update_dish_status(dish, "inactive", "20261015", "euthanasia")
        ctrl.update_dish_status(dish, "active")
        assert client.get(f"/fish/{dead}").json()["end_reason"] == "found_dead"

    def test_propagation_and_transfer(self, client):
        prop = _dish()
        p_fish, _ = _fish_in_well(client, prop)
        FishDishController().update_dish_status(prop, "inactive", "20261015", "propagation")
        assert client.get(f"/fish/{p_fish}").json()["status"] == "propagated"

        moved = _dish()
        m_fish, _ = _fish_in_well(client, moved)
        FishDishController().update_dish_status(moved, "inactive", "20261015", "transfer")
        assert client.get(f"/fish/{m_fish}").json()["status"] == "alive"

    def test_batch_termination_ends_fish(self, client):
        dish = _dish()
        fish_id, _ = _fish_in_well(client, dish)
        resp = client.post("/dishes/batch-terminate", data={
            "dish_ids": [dish], "termination_date": "2026-10-15",
            "termination_reason": "euthanasia"}, follow_redirects=False)
        assert resp.status_code == 303
        assert client.get(f"/fish/{fish_id}").json()["status"] == "dead"


class TestCarePage:
    def test_single_fish_well_death_is_recorded_on_the_fish_once(self, client):
        dish = _dish()
        fish_id, unit = _fish_in_well(client, dish)
        resp = client.post(f"/care/{dish}/unit-checks", data={
            "check_time": "20261015T10:00:00", f"num_dead_{unit}": "1"})
        assert resp.status_code == 200
        assert client.get(f"/fish/{fish_id}").json()["status"] == "dead"
        assert _count(client, dish) == 9  # one death, not two


class TestTimeline:
    def test_ended_entry(self, client):
        dish = _dish()
        fish_id, _ = _fish_in_well(client, dish)
        FishDishController().update_dish_status(dish, "inactive", "20261015", "euthanasia")
        t = client.get(f"/fish/{fish_id}/timeline").json()
        ended = [e for e in t["entries"] if e["kind"] == "ended"]
        assert ended and ended[0]["at"] == "2026-10-15"
        assert "euthanized" in ended[0]["summary"] and "termination" in ended[0]["summary"]
        assert t["status"] == "dead"
