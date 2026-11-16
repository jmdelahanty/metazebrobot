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


def test_delivered_by_recorded_on_first_creation_and_not_compared(client, seed_dish):
    body = _link(seed_dish)
    first = client.post("/usage-links", json=body, headers={"X-Delivered-By": "palette"})
    assert first.status_code == 201 and first.json()["delivered_by"] == "palette"
    replay = client.post("/usage-links", json=body, headers={"X-Delivered-By": "citrus"})
    assert replay.status_code == 200 and replay.json()["delivered_by"] == "palette"
    no_header = _link(seed_dish)
    assert client.post("/usage-links", json=no_header).json()["delivered_by"] is None


def _other_dish():
    """A second minimal dish (seed_dish makes one per test)."""
    import json
    import sqlite3
    from metazebrobot.data.data_manager import data_manager
    dish_id = f"DISH_{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(str(data_manager.database_path))
    conn.execute("INSERT INTO dishes (dish_id, data, genotype, species) VALUES (?, ?, ?, ?)",
                 (dish_id, json.dumps({"dish_id": dish_id}), "Tg(elavl3:GCaMP6s)", "Danio rerio"))
    conn.commit()
    conn.close()
    return dish_id


def _mint(client, dish_id, label):
    return client.post(f"/dishes/{dish_id}/fish", json={"subject_label": label}).json()["fish_id"]


# A start after the fish are minted (they're created "now" in these tests).
LATER = "2099-01-01T12:00:00Z"


class TestMembers:
    """docs/fish_timeline_design.md, "Group members on usage links"."""

    def test_group_link_names_members_compared_as_a_set(self, client, seed_dish):
        fish = [_mint(client, seed_dish, f"Z{i}") for i in range(3)]
        body = _link(seed_dish, subject_count=3, started_at=LATER,
                     members=[{"fish_id": f, "fish_revision": 1} for f in fish])
        first = client.post("/usage-links", json=body)
        assert first.status_code == 201
        assert first.json()["fish_id"] is None
        assert [m["fish_id"] for m in first.json()["members"]] == sorted(fish)
        assert all(m["flag"] is None and m["fish_revision"] == 1 for m in first.json()["members"])
        reordered = {**body, "members": list(reversed(body["members"]))}
        assert client.post("/usage-links", json=reordered).status_code == 200
        other = _mint(client, seed_dish, "Z9")
        changed = {**body, "members": body["members"][:2] + [{"fish_id": other, "fish_revision": 1}]}
        assert client.post("/usage-links", json=changed).status_code == 409
        without = {k: v for k, v in body.items() if k != "members"}
        assert client.post("/usage-links", json=without).status_code == 409

    def test_links_without_members_are_unchanged(self, client, seed_dish):
        body = _link(seed_dish, subject_count=5)
        assert client.post("/usage-links", json=body).json()["members"] == []
        assert client.post("/usage-links", json=body).status_code == 200

    @pytest.mark.parametrize("members, count, with_fish", [
        ([], 1, False),                                    # empty list
        (["not-a-dict"], 1, False),
        ([{"fish_id": "NOT-A-UUID"}], 1, False),
        ([{"fish_id": "F0", "unit_id": "X:A1"}], 1, False),  # no unit per member
        ([{"fish_id": "F0"}, {"fish_id": "F0"}], 2, False),  # listed twice
        ([{"fish_id": "F0"}], 2, False),                   # count differs
        ([{"fish_id": "F0"}], 1, True),                    # an individual link
    ])
    def test_invalid_members_are_422(self, client, seed_dish, members, count, with_fish):
        real = _mint(client, seed_dish, "Z1")
        members = [{**m, "fish_id": real} if isinstance(m, dict) and m.get("fish_id") == "F0" else m
                   for m in members]
        extra = {"fish_id": real} if with_fish else {}
        resp = client.post("/usage-links", json=_link(
            seed_dish, subject_count=count, members=members, **extra))
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "members"

    def test_unknown_member_is_404(self, client, seed_dish):
        missing = str(uuid.uuid4())
        resp = client.post("/usage-links", json=_link(
            seed_dish, subject_count=1, members=[{"fish_id": missing}]))
        assert resp.status_code == 404
        assert resp.json()["detail"] == {"error": "fish_not_found", "fish_id": missing}

    def test_fish_query_matches_members_and_dish_query_lists_them(self, client, seed_dish):
        a, b, outsider = (_mint(client, seed_dish, z) for z in ("Z1", "Z2", "Z3"))
        body = _link(seed_dish, subject_count=2, started_at=LATER,
                     members=[{"fish_id": a}, {"fish_id": b}])
        client.post("/usage-links", json=body)
        refs = [l["recording_ref"] for l in client.get(f"/usage-links?fish_id={a}").json()["items"]]
        assert refs == [body["recording_ref"]]
        assert client.get(f"/usage-links?fish_id={outsider}").json()["items"] == []
        by_dish = client.get(f"/usage-links?dish_id={seed_dish}").json()["items"]
        assert len(by_dish) == 1 and len(by_dish[0]["members"]) == 2

    def test_member_flags_are_judged_at_start(self, client, seed_dish):
        elsewhere = _mint(client, _other_dish(), "Z1")
        died_before = _mint(client, seed_dish, "Z2")
        died_after = _mint(client, seed_dish, "Z3")
        client.post(f"/fish/{died_before}/end", json={"reason": "found_dead",
                                                    "at": "2026-10-01T12:00:00Z"})
        client.post(f"/fish/{died_after}/end", json={"reason": "euthanized"})
        body = _link(seed_dish, subject_count=3, started_at="2026-10-09T20:00:18Z",
                     members=[{"fish_id": f} for f in (elsewhere, died_before, died_after)])
        flags = {m["fish_id"]: m["flag"]
                 for m in client.post("/usage-links", json=body).json()["members"]}
        assert flags == {elsewhere: "not_in_dish_at_start", died_before: "dead_at_start",
                         died_after: None}

    def test_member_timeline_and_no_possibly_used_for_the_rest(self, client, seed_dish):
        member, outsider = _mint(client, seed_dish, "Z1"), _mint(client, seed_dish, "Z2")
        client.post("/usage-links", json=_link(seed_dish, subject_count=1, started_at=LATER,
                                               members=[{"fish_id": member}]))
        member_entries = [e for e in client.get(f"/fish/{member}/timeline").json()["entries"]
                          if e["kind"] == "recorded"]
        assert len(member_entries) == 1
        assert member_entries[0]["details"]["group_member"] is True
        assert "one of 1 from dish" in member_entries[0]["summary"]
        kinds = [e["kind"] for e in client.get(f"/fish/{outsider}/timeline").json()["entries"]]
        assert "recorded" not in kinds and "possibly_recorded" not in kinds
        # A dish-level link that names no members still marks every fish.
        client.post("/usage-links", json=_link(seed_dish, subject_count=4, started_at=LATER))
        kinds = [e["kind"] for e in client.get(f"/fish/{outsider}/timeline").json()["entries"]]
        assert "possibly_recorded" in kinds


def _kinds(client, fish_id):
    return [e["kind"] for e in client.get(f"/fish/{fish_id}/timeline").json()["entries"]]


class TestSetMembers:
    """A group link created without members is given them once, later."""

    def _group(self, client, seed_dish, n=2):
        fish = [_mint(client, seed_dish, f"Z{i}") for i in range(n)]
        body = _link(seed_dish, subject_count=n, started_at=LATER)
        assert client.post("/usage-links", json=body).status_code == 201
        return body, fish

    def _put(self, client, ref, members, **headers):
        return client.put(f"/usage-links/{quote(ref, safe='')}/members",
                          json={"members": members}, headers=headers)

    def test_set_once_then_same_set_200_and_different_409(self, client, seed_dish):
        body, fish = self._group(client, seed_dish)
        outsider = _mint(client, seed_dish, "Z9")
        assert "possibly_recorded" in _kinds(client, outsider)
        members = [{"fish_id": f, "fish_revision": 1} for f in fish]
        first = self._put(client, body["recording_ref"], members, **{"X-Delivered-By": "orchard"})
        assert first.status_code == 201
        link = first.json()
        assert [m["fish_id"] for m in link["members"]] == sorted(fish)
        assert link["members_added_at"] and link["members_added_by"] == "orchard"
        assert link["delivered_by"] is None
        # The members are recorded; the dish's other fish no longer "possibly used".
        assert "recorded" in _kinds(client, fish[0])
        assert "possibly_recorded" not in _kinds(client, outsider)
        again = self._put(client, body["recording_ref"], list(reversed(members)))
        assert again.status_code == 200
        assert again.json()["members_added_by"] == "orchard"
        changed = members[:1] + [{"fish_id": outsider, "fish_revision": 1}]
        resp = self._put(client, body["recording_ref"], changed)
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "usage_link_members_conflict"

    def test_creation_replays_after_members_are_set(self, client, seed_dish):
        body, fish = self._group(client, seed_dish)
        members = [{"fish_id": f, "fish_revision": 1} for f in fish]
        self._put(client, body["recording_ref"], members)
        # Citrus's outbox replays the original body: still 200.
        assert client.post("/usage-links", json=body).status_code == 200
        assert client.post("/usage-links", json={**body, "members": members}).status_code == 200
        other = [members[0], {"fish_id": _mint(client, seed_dish, "Z9"), "fish_revision": 1}]
        resp = client.post("/usage-links", json={**body, "members": other})
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "usage_link_members_conflict"
        moved = {**body, "rig_id": "other_rig", "members": members}
        assert client.post("/usage-links", json=moved).json()["detail"]["error"] == "usage_link_conflict"

    def test_a_replay_carrying_members_sets_them(self, client, seed_dish):
        body, fish = self._group(client, seed_dish)
        resp = client.post("/usage-links", json={**body, "members": [{"fish_id": f} for f in fish]},
                           headers={"X-Delivered-By": "palette"})
        assert resp.status_code == 200
        assert len(resp.json()["members"]) == 2
        assert resp.json()["members_added_by"] == "palette"

    def test_members_sent_at_start_have_no_added_stamp(self, client, seed_dish):
        fish = _mint(client, seed_dish, "Z1")
        body = _link(seed_dish, subject_count=1, started_at=LATER, members=[{"fish_id": fish}])
        assert client.post("/usage-links", json=body).json()["members_added_at"] is None
        same = self._put(client, body["recording_ref"], [{"fish_id": fish}])
        assert same.status_code == 200 and same.json()["members_added_at"] is None
        other = self._put(client, body["recording_ref"], [{"fish_id": _mint(client, seed_dish, "Z2")}])
        assert other.status_code == 409

    @pytest.mark.parametrize("payload", [
        {},                                             # no members
        {"members": []},
        {"members": [{"fish_id": "F0"}]},               # count differs from subject_count 2
        {"members": [{"fish_id": "F0"}, {"fish_id": "F0"}]},
        {"members": [{"fish_id": "F0"}, {"fish_id": "F1"}], "subject_count": 2},
    ])
    def test_invalid_bodies_are_422(self, client, seed_dish, payload):
        body, fish = self._group(client, seed_dish)
        swap = {"F0": fish[0], "F1": fish[1]}
        if "members" in payload:
            payload = {**payload, "members": [{"fish_id": swap[m["fish_id"]]}
                                              for m in payload["members"]]}
        resp = client.put(f"/usage-links/{quote(body['recording_ref'], safe='')}/members",
                          json=payload)
        assert resp.status_code == 422
        assert client.get(f"/usage-links/{quote(body['recording_ref'], safe='')}").json()["members"] == []

    def test_individual_link_is_422_and_unknown_link_or_fish_404(self, client, fish):
        dish_id, fish_id = fish
        body = _link(dish_id, fish_id=fish_id)
        client.post("/usage-links", json=body)
        resp = self._put(client, body["recording_ref"], [{"fish_id": fish_id}])
        assert resp.status_code == 422 and resp.json()["detail"]["field"] == "members"
        assert self._put(client, _ref(), [{"fish_id": fish_id}]).json()["detail"]["error"] == \
            "usage_link_not_found"
        group = _link(dish_id, subject_count=1)
        client.post("/usage-links", json=group)
        missing = str(uuid.uuid4())
        resp = self._put(client, group["recording_ref"], [{"fish_id": missing}])
        assert resp.status_code == 404
        assert resp.json()["detail"] == {"error": "fish_not_found", "fish_id": missing}
        assert client.get(f"/usage-links/{quote(group['recording_ref'], safe='')}").json()[
            "members_added_at"] is None
