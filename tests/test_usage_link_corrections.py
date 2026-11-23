"""Correcting the fish a recording names (docs/fish_timeline_design.md)."""

import sqlite3
import uuid

import pytest

from tests.test_usage_links import _link, _mint, _other_dish

LATER = "2099-01-01T12:00:00Z"
ATTESTER = "lovelacea"


@pytest.fixture(autouse=True)
def attester(client):
    from metazebrobot.data.data_manager import data_manager
    conn = sqlite3.connect(str(data_manager.database_path))
    conn.execute("INSERT OR IGNORE INTO users (pyrat_userid, username, fullname, app_user) "
                 "VALUES (?, ?, ?, 1)", (900001, ATTESTER, "Ada Lovelace"))
    conn.commit()
    conn.close()


def _correct(client, ref, fish_id, member=None, evidence="bench notes: arena 3 held Z6"):
    body = {"fish_id": fish_id, "evidence": evidence, "attested_by": ATTESTER}
    if member:
        body["member_fish_id"] = member
    return client.post(f"/usage-links/{ref}/corrections", json=body)


def _pair(client, dish_id, **overrides):
    """Two arenas of one recording that both sealed Z5 (the 11-06 misclick)."""
    z5, z6 = _mint(client, dish_id, "Z5"), _mint(client, dish_id, "Z6")
    a2 = _link(dish_id, fish_id=z5, arena_id="arena_2", started_at=LATER, **overrides)
    a3 = _link(dish_id, fish_id=z5, arena_id="arena_3", started_at=LATER, **overrides)
    for body in (a2, a3):
        assert client.post("/usage-links", json=body).status_code == 201
    return z5, z6, a2, a3


def _kinds(client, fish_id):
    return [(e["kind"], e["details"].get("recording_ref"))
            for e in client.get(f"/fish/{fish_id}/timeline").json()["entries"]
            if e["kind"] in ("recorded", "possibly_recorded", "corrected_away")]


class TestCorrectIndividualLink:
    def test_correction_outranks_sealed_value_and_replay_stays_200(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        resp = _correct(client, a3["recording_ref"], z6)
        assert resp.status_code == 201
        link = resp.json()
        assert link["fish_id"] == z5  # sealed, unchanged
        c = link["correction"]
        assert c["fish_id"] == z6 and c["dish_id"] == seed_dish
        assert c["attested_by"] == ATTESTER and c["fish_revision"] == 1
        assert c["member_fish_id"] is None
        assert client.post("/usage-links", json=a3).status_code == 200
        assert client.get(f"/usage-links/{a3['recording_ref']}").json()["correction"]["id"] == c["id"]

    def test_fish_query_matches_the_effective_fish(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        _correct(client, a3["recording_ref"], z6)
        refs = lambda f: [i["recording_ref"] for i in
                          client.get("/usage-links", params={"fish_id": f}).json()["items"]]
        assert refs(z5) == [a2["recording_ref"]]
        assert refs(z6) == [a3["recording_ref"]]

    def test_timelines_show_the_correction(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        _correct(client, a3["recording_ref"], z6)
        assert sorted(_kinds(client, z5)) == sorted([
            ("recorded", a2["recording_ref"]), ("corrected_away", a3["recording_ref"])])
        assert _kinds(client, z6) == [("recorded", a3["recording_ref"])]
        z6_entry = [e for e in client.get(f"/fish/{z6}/timeline").json()["entries"]
                    if e["kind"] == "recorded"][0]
        assert "corrected (sealed Z5) by lovelacea" in z6_entry["summary"]

    def test_undo_is_a_correction_back_to_the_sealed_fish(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        _correct(client, a3["recording_ref"], z6)
        assert _correct(client, a3["recording_ref"], z6).json()["detail"]["error"] \
            == "correction_unchanged"
        # Back to Z5 would put Z5 in two arenas at once.
        back = _correct(client, a3["recording_ref"], z5)
        assert back.status_code == 409
        assert back.json()["detail"] == {"error": "fish_in_another_arena", "fish_id": z5,
                                         "recording_ref": a2["recording_ref"]}
        history = client.get(f"/usage-links/{a3['recording_ref']}/corrections").json()["items"]
        assert [c["fish_id"] for c in history] == [z6]

    def test_fish_unknown(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        bystander = _mint(client, seed_dish, "Z7")
        for link in (a2, a3):
            resp = _correct(client, link["recording_ref"], None, evidence="misclick")
            assert resp.status_code == 201
            assert resp.json()["correction"]["fish_id"] is None
            assert resp.json()["correction"]["fish_revision"] is None
        assert client.get("/usage-links", params={"fish_id": z5}).json()["items"] == []
        assert sorted(k for k, _ in _kinds(client, z5)) == ["possibly_recorded"] * 2
        assert sorted(k for k, _ in _kinds(client, bystander)) == ["possibly_recorded"] * 2
        assert _correct(client, a3["recording_ref"], None).json()["detail"]["error"] \
            == "correction_unchanged"
        # Now Z5 can be given back to one arena.
        assert _correct(client, a2["recording_ref"], z5).status_code == 201
        assert _kinds(client, bystander) == [("possibly_recorded", a3["recording_ref"])]

    def test_overlap_judged_on_time(self, client, seed_dish):
        z5 = _mint(client, seed_dish, "Z5")
        other = _mint(client, seed_dish, "Z8")
        early = _link(seed_dish, fish_id=z5, started_at="2099-01-01T10:00:00Z")
        late = _link(seed_dish, fish_id=other, started_at=LATER)
        for body in (early, late):
            client.post("/usage-links", json=body)
        # An end not recorded counts as the start, so these don't overlap.
        assert _correct(client, late["recording_ref"], z5).status_code == 201
        client.patch(f"/usage-links/{late['recording_ref']}",
                     json={"ended_at": "2099-01-01T13:00:00Z", "end_status": "completed"})
        client.patch(f"/usage-links/{early['recording_ref']}",
                     json={"ended_at": "2099-01-01T12:30:00Z", "end_status": "completed"})
        again = _correct(client, late["recording_ref"], other)  # Z8 back, then Z5 again
        assert again.status_code == 201
        refused = _correct(client, late["recording_ref"], z5)
        assert refused.json()["detail"]["error"] == "fish_in_another_arena"

    def test_a_dish_level_link_can_name_its_fish(self, client, seed_dish):
        z5 = _mint(client, seed_dish, "Z5")
        rest = _mint(client, seed_dish, "Z9")
        body = _link(seed_dish, subject_count=1, started_at=LATER)
        client.post("/usage-links", json=body)
        assert _kinds(client, rest) == [("possibly_recorded", body["recording_ref"])]
        assert _correct(client, body["recording_ref"], z5).status_code == 201
        assert _kinds(client, z5) == [("recorded", body["recording_ref"])]
        assert _kinds(client, rest) == []
        several = _link(seed_dish, subject_count=3, started_at=LATER)
        client.post("/usage-links", json=several)
        assert _correct(client, several["recording_ref"], rest).status_code == 422

    def test_a_fish_named_by_a_correction_cannot_be_deleted(self, client, seed_dish):
        z5, z6, a2, a3 = _pair(client, seed_dish)
        _correct(client, a3["recording_ref"], z6)
        resp = client.delete(f"/fish/{z6}")
        assert resp.status_code == 409
        assert resp.json()["detail"]["recording_refs"] == [a3["recording_ref"]]


class TestCorrectMembers:
    def _group(self, client, dish_id):
        a, b, spare = (_mint(client, dish_id, f"Z{n}") for n in (1, 2, 3))
        body = _link(dish_id, subject_count=2, started_at=LATER,
                     members=[{"fish_id": a, "fish_revision": 1},
                              {"fish_id": b, "fish_revision": 1}])
        assert client.post("/usage-links", json=body).status_code == 201
        return a, b, spare, body["recording_ref"]

    def test_member_correction(self, client, seed_dish):
        a, b, spare, ref = self._group(client, seed_dish)
        assert _correct(client, ref, spare).json()["detail"]["field"] == "member_fish_id"
        resp = _correct(client, ref, spare, member=b)
        assert resp.status_code == 201
        members = {m["fish_id"]: m for m in resp.json()["members"]}
        assert members[b]["correction"]["fish_id"] == spare
        assert members[a]["correction"] is None and resp.json()["correction"] is None
        assert [i["recording_ref"] for i in
                client.get("/usage-links", params={"fish_id": spare}).json()["items"]] == [ref]
        assert client.get("/usage-links", params={"fish_id": b}).json()["items"] == []
        assert _kinds(client, b) == [("corrected_away", ref)]

    def test_a_fish_cannot_take_two_places_in_one_group(self, client, seed_dish):
        a, b, spare, ref = self._group(client, seed_dish)
        resp = _correct(client, ref, a, member=b)
        assert resp.status_code == 409 and resp.json()["detail"]["error"] == "fish_in_another_arena"

    def test_unknown_member_marks_the_dish_rest_possibly_used(self, client, seed_dish):
        a, b, spare, ref = self._group(client, seed_dish)
        assert _kinds(client, spare) == []
        assert _correct(client, ref, None, member=b, evidence="miscount").status_code == 201
        assert _kinds(client, spare) == [("possibly_recorded", ref)]
        assert _kinds(client, a) == [("recorded", ref)]
        assert _kinds(client, b) == [("possibly_recorded", ref)]

    def test_corrected_fish_may_be_in_another_dish(self, client, seed_dish):
        a, b, spare, ref = self._group(client, seed_dish)
        elsewhere = _other_dish()
        stray = _mint(client, elsewhere, "Z4")
        resp = _correct(client, ref, stray, member=a, evidence="picked from the other plate")
        assert resp.status_code == 201
        correction = {m["fish_id"]: m for m in resp.json()["members"]}[a]["correction"]
        assert correction["dish_id"] == elsewhere


@pytest.mark.parametrize("body, field", [
    ({"evidence": "x", "attested_by": ATTESTER}, "fish_id"),
    ({"fish_id": None, "attested_by": ATTESTER}, "evidence"),
    ({"fish_id": None, "evidence": "  ", "attested_by": ATTESTER}, "evidence"),
    ({"fish_id": None, "evidence": "x"}, "attested_by"),
    ({"fish_id": None, "evidence": "x", "attested_by": "nobody"}, "attested_by"),
    ({"fish_id": "Z6", "evidence": "x", "attested_by": ATTESTER}, "fish_id"),
    ({"fish_id": None, "evidence": "x", "attested_by": ATTESTER, "dish_id": "D"}, "dish_id"),
])
def test_invalid_corrections_are_422(client, seed_dish, body, field):
    z5, z6, a2, a3 = _pair(client, seed_dish)
    resp = client.post(f"/usage-links/{a3['recording_ref']}/corrections", json=body)
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "invalid_correction"
    assert resp.json()["detail"]["field"] == field


def test_unknown_link_or_fish_is_404(client, seed_dish):
    z5, z6, a2, a3 = _pair(client, seed_dish)
    assert _correct(client, "obsctx_" + "0" * 64, z6).json()["detail"]["error"] \
        == "usage_link_not_found"
    assert client.get(f"/usage-links/obsctx_{'0' * 64}/corrections").status_code == 404
    resp = _correct(client, a3["recording_ref"], str(uuid.uuid4()))
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "fish_not_found"
