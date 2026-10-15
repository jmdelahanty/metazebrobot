"""Propagation events (docs/propagation_events_design.md)."""

import uuid

import pytest

from metazebrobot.data import propagation
from metazebrobot.data.data_manager import data_manager


def _dish(cross_id, number, termination_reason="propagation", termination_date="20261015",
          count=10, promoter="gfap", construct_key="pmca2mcherryzf",
          construct="Tg(gfap:PMCA2-mCherry-zf)", parents=(("7472", "F2"), ("8131", "F1"))):
    dish_id = f"{cross_id}_{number}_pos1"
    with data_manager.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO crosses (cross_id) VALUES (?)", (cross_id,))
        conn.execute(
            """INSERT INTO dishes (dish_id, cross_id, genotype, status, current_fish_count,
                   termination_date, termination_reason) VALUES (?, ?, ?, 'terminated', ?, ?, ?)""",
            (dish_id, cross_id, construct, count, termination_date, termination_reason))
        conn.execute(
            """INSERT INTO dish_transgenes (dish_id, construct, promoter, construct_key)
               VALUES (?, ?, ?, ?)""", (dish_id, construct, promoter, construct_key))
        for index, (tank, generation) in enumerate(parents):
            conn.execute(
                """INSERT OR IGNORE INTO cross_parents (cross_id, parent_index, tank_id, generation)
                   VALUES (?, ?, ?, ?)""", (cross_id, index, tank, generation))
        conn.commit()
    return dish_id


@pytest.fixture()
def cross(client):
    return f"P{uuid.uuid4().hex[:8]}"


def _event_id(response):
    return response.headers["location"].rsplit("/", 1)[1]


def test_handover_date():
    assert propagation.handover_date("20261015") == "2026-10-15"
    assert propagation.handover_date(None) is None


def test_group_two_days_into_one_event_with_suggested_generation(client, cross):
    first = _dish(cross, 1, termination_date="20261014", count=12)
    second = _dish(cross, 2, termination_date="20261015", count=8)
    page = client.get("/propagation/")
    assert first in page.text and second in page.text

    created = client.post("/propagation/events", data={"dish_id": [first]}, follow_redirects=False)
    assert created.status_code == 303
    event_id = _event_id(created)
    client.post("/propagation/events", data={"dish_id": second, "event_id": event_id})

    with data_manager.get_connection() as conn:
        event = propagation.get_event(conn, event_id)
    assert [d["dish_id"] for d in event["dishes"]] == [first, second]
    assert (event["first_handover"], event["last_handover"]) == ("2026-10-14", "2026-10-15")
    assert event["fish_count"] == 20
    assert event["generation"] == "F3"
    assert event["generation_source"] == "suggested"
    assert "tank 7472 F2" in event["generation_basis"]

    view = client.get(f"/propagation/events/{event_id}")
    assert view.status_code == 200 and "suggested" in view.text
    assert f'name="dish_id" value="{first}"' not in client.get("/propagation/").text


def test_entered_generation_sticks_and_empty_returns_to_suggestion(client, cross):
    dish = _dish(cross, 1)
    event_id = _event_id(client.post("/propagation/events", data={"dish_id": dish},
                                     follow_redirects=False))
    client.post(f"/propagation/events/{event_id}",
                data={"generation": "f4", "resulting_tank_id": " 9001 ", "notes": ""})
    with data_manager.get_connection() as conn:
        event = propagation.get_event(conn, event_id)
    assert (event["generation"], event["generation_source"]) == ("F4", "entered")
    assert event["resulting_tank_id"] == "9001"

    other = _dish(cross, 2)  # adding a dish doesn't recompute an entered value
    client.post("/propagation/events", data={"dish_id": other, "event_id": event_id})
    client.post(f"/propagation/events/{event_id}", data={"generation": ""})
    with data_manager.get_connection() as conn:
        event = propagation.get_event(conn, event_id)
    assert (event["generation"], event["generation_source"]) == ("F3", "suggested")


def test_refuses_non_propagation_and_already_grouped_dishes(client, cross):
    euthanized = _dish(cross, 1, termination_reason="euthanasia")
    resp = client.post("/propagation/events", data={"dish_id": euthanized})
    assert resp.status_code == 409 and resp.json()["detail"]["error"] == "dish_not_propagated"

    dish = _dish(cross, 2)
    client.post("/propagation/events", data={"dish_id": dish})
    resp = client.post("/propagation/events", data={"dish_id": dish})
    assert resp.json()["detail"]["error"] == "dish_in_event"
    assert client.post("/propagation/events", data={}).status_code == 422


def test_no_parent_generation_gives_no_suggestion(client, cross):
    dish = _dish(cross, 1, parents=(("1", None), ("2", "")))
    event_id = _event_id(client.post("/propagation/events", data={"dish_id": dish},
                                     follow_redirects=False))
    with data_manager.get_connection() as conn:
        event = propagation.get_event(conn, event_id)
    assert event["generation"] is None and event["generation_source"] == "none"


def test_removing_last_dish_deletes_the_event(client, cross):
    dish = _dish(cross, 1)
    event_id = _event_id(client.post("/propagation/events", data={"dish_id": dish},
                                     follow_redirects=False))
    resp = client.post(f"/propagation/events/{event_id}/dishes/{dish}/remove", follow_redirects=False)
    assert resp.headers["location"] == "/propagation/"
    assert client.get(f"/propagation/events/{event_id}").status_code == 404


def test_line_history_separates_promoters(client, cross):
    gfap = _dish(cross, 1, termination_date="20261005", promoter="gfap",
                 construct_key="grabatp10", construct="Tg(gfap:GRABATP1.0)")
    elavl3 = _dish(cross, 2, termination_date="20260518", promoter="elavl3",
                   construct_key="grabatp10", construct="Tg(elavl3:GRABATP1.0)")
    for dish in (gfap, elavl3):
        client.post("/propagation/events", data={"dish_id": dish})
    page = client.get("/lines/gfap-grabatp10")
    assert page.status_code == 200
    assert gfap in page.text and elavl3 not in page.text
