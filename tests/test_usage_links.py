"""Usage links (docs/fish_timeline_design.md, step 3)."""

import uuid
from urllib.parse import quote

import pytest


def _ref():
    return "obsctx_" + uuid.uuid4().hex + uuid.uuid4().hex


def _link(dish_id, **overrides):
    body = {"recording_ref": _ref(), "ref_kind": "observation_context",
            "recording_id": "2026_10_09_16_00_03", "dish_id": dish_id,
            "rig_id": "omnifin0", "arena_id": "arena_2",
            "started_at": "2026-10-09T20:00:18Z"}
    body.update(overrides)
    return body


@pytest.fixture()
def fish(client, seed_dish):
    fish_id = client.post(f"/dishes/{seed_dish}/fish", json={"subject_label": "Z5"}).json()["fish_id"]
    return seed_dish, fish_id


class TestCreate:
    def test_new_is_201_identical_replay_200_different_409(self, client, fish):
        dish_id, fish_id = fish
        body = _link(dish_id, fish_id=fish_id, fish_revision=1, subject_count=1)
        first = client.post("/usage-links", json=body)
        assert first.status_code == 201
        assert first.json()["rig_id"] == "omnifin0" and first.json()["ended_at"] is None
        assert client.post("/usage-links", json=body).status_code == 200
        conflict = client.post("/usage-links", json={**body, "arena_id": "arena_3"})
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == {"error": "usage_link_conflict",
                                            "recording_ref": body["recording_ref"]}

    def test_existing_ref_answered_before_fish_check(self, client, fish):
        dish_id, fish_id = fish
        body = _link(dish_id, fish_id=fish_id)
        client.post("/usage-links", json=body)
        client.delete(f"/fish/{fish_id}")
        assert client.post("/usage-links", json=body).status_code == 200

    def test_unknown_dish_or_fish_for_new_link_is_404(self, client, seed_dish):
        assert client.post("/usage-links", json=_link("NO_DISH")).json()["detail"]["error"] \
            == "dish_not_found"
        resp = client.post("/usage-links", json=_link(seed_dish, fish_id=str(uuid.uuid4())))
        assert resp.status_code == 404 and resp.json()["detail"]["error"] == "fish_not_found"

    def test_dish_level_row_without_fish(self, client, seed_dish):
        resp = client.post("/usage-links", json=_link(seed_dish, subject_count=10))
        assert resp.status_code == 201 and resp.json()["fish_id"] is None

    @pytest.mark.parametrize("change, field", [
        ({"recording_ref": "obsctx_NOTHEX"}, "recording_ref"),
        ({"ref_kind": "citrus_session", "recording_ref": "a/b"}, "recording_ref"),
        ({"ref_kind": "other"}, "ref_kind"),
        ({"fish_revision": 2}, "fish_revision"),
        ({"unit_id": "X:A1"}, "unit_id"),
        ({"started_at": "2026-10-09 16:00:18"}, "started_at"),
        ({"started_at": "2026-10-09T16:00:18-04:00"}, "started_at"),
        ({"subject_count": 0}, "subject_count"),
        ({"surprise": 1}, "surprise"),
        ({"rig_id": None}, "rig_id"),
    ])
    def test_invalid_bodies_are_422_with_field(self, client, seed_dish, change, field):
        resp = client.post("/usage-links", json=_link(seed_dish, **change))
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "invalid_usage_link"
        assert resp.json()["detail"]["field"] == field


class TestEnd:
    def test_end_replay_and_conflict(self, client, seed_dish):
        body = _link(seed_dish)
        client.post("/usage-links", json=body)
        end = {"ended_at": "2026-10-09T20:35:02Z", "end_status": "completed"}
        first = client.patch(f"/usage-links/{body['recording_ref']}", json=end)
        assert first.status_code == 200 and first.json()["end_status"] == "completed"
        assert client.patch(f"/usage-links/{body['recording_ref']}", json=end).status_code == 200
        other = client.patch(f"/usage-links/{body['recording_ref']}",
                             json={**end, "end_status": "aborted"})
        assert other.status_code == 409
        assert other.json()["detail"]["error"] == "usage_link_end_conflict"

    def test_same_end_in_another_format_is_not_a_conflict(self, client, seed_dish):
        body = _link(seed_dish)
        client.post("/usage-links", json=body)
        client.patch(f"/usage-links/{body['recording_ref']}",
                     json={"ended_at": "2026-10-09T20:35:02Z", "end_status": "completed"})
        again = client.patch(f"/usage-links/{body['recording_ref']}",
                             json={"ended_at": "2026-10-09T20:35:02.000Z", "end_status": "completed"})
        assert again.status_code == 200
        assert again.json()["ended_at"] == "2026-10-09T20:35:02Z"  # first value kept as sent

    def test_patch_before_post_is_404(self, client):
        resp = client.patch(f"/usage-links/{_ref()}",
                            json={"ended_at": "2026-10-09T20:35:02Z", "end_status": "completed"})
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "usage_link_not_found"

    def test_end_before_start_is_422(self, client, seed_dish):
        body = _link(seed_dish)
        client.post("/usage-links", json=body)
        resp = client.patch(f"/usage-links/{body['recording_ref']}",
                            json={"ended_at": "2026-10-09T19:00:00Z", "end_status": "interrupted"})
        assert resp.status_code == 422 and resp.json()["detail"]["field"] == "ended_at"

    def test_unbound_session_ref_percent_encoded(self, client, seed_dish):
        ref = "2026-10-09T20:00:18Z_arena_2"
        body = _link(seed_dish, ref_kind="citrus_session", recording_ref=ref, recording_id=None)
        assert client.post("/usage-links", json=body).status_code == 201
        resp = client.patch(f"/usage-links/{quote(ref, safe='')}",
                            json={"ended_at": "2026-10-09T20:10:00Z", "end_status": "completed"})
        assert resp.status_code == 200 and resp.json()["recording_ref"] == ref


class TestQueries:
    def test_by_fish_dish_and_active_at(self, client, fish):
        dish_id, fish_id = fish
        a = _link(dish_id, fish_id=fish_id, started_at="2026-10-09T20:00:00Z")
        b = _link(dish_id, started_at="2026-10-09T21:20:00Z")
        for body in (a, b):
            client.post("/usage-links", json=body)
        client.patch(f"/usage-links/{a['recording_ref']}",
                     json={"ended_at": "2026-10-09T20:35:00Z", "end_status": "completed"})

        by_fish = client.get("/usage-links", params={"fish_id": fish_id}).json()["items"]
        assert [l["recording_ref"] for l in by_fish] == [a["recording_ref"]]
        by_dish = client.get("/usage-links", params={"dish_id": dish_id}).json()["items"]
        assert [l["recording_ref"] for l in by_dish] == [a["recording_ref"], b["recording_ref"]]
        at = client.get("/usage-links", params={"active_at": "2026-10-09T21:25:00Z",
                                                "dish_id": dish_id}).json()["items"]
        assert [l["recording_ref"] for l in at] == [b["recording_ref"]]
        assert client.get(f"/usage-links/{a['recording_ref']}").json()["end_status"] == "completed"


class TestTimeline:
    def test_own_and_dish_level_links_on_timeline(self, client, fish):
        dish_id, fish_id = fish
        own = _link(dish_id, fish_id=fish_id, fish_revision=1, started_at="2030-01-01T17:00:00Z")
        dish_only = _link(dish_id, subject_count=10, started_at="2030-01-01T18:20:00Z")
        client.post("/usage-links", json=own)
        client.post("/usage-links", json=dish_only)
        client.patch(f"/usage-links/{own['recording_ref']}",
                     json={"ended_at": "2030-01-01T17:35:00Z", "end_status": "completed"})

        entries = client.get(f"/fish/{fish_id}/timeline").json()["entries"]
        recorded = next(e for e in entries if e["kind"] == "recorded")
        assert "omnifin0" in recorded["summary"] and "(completed)" in recorded["summary"]
        assert recorded["at"] == "2030-01-01T12:00:00"  # lab time (EST)
        possibly = next(e for e in entries if e["kind"] == "possibly_recorded")
        assert "no fish was named" in possibly["summary"]


def test_link_for_fish_that_has_since_died_is_accepted(client, fish):
    """A late replay (e.g. Palette's backup delivery) of a real recording must land."""
    dish_id, fish_id = fish
    assert client.post(f"/fish/{fish_id}/end", json={"reason": "found_dead"}).status_code == 200
    body = _link(dish_id, fish_id=fish_id, started_at="2026-10-09T20:00:18Z")
    assert client.post("/usage-links", json=body).status_code == 201
