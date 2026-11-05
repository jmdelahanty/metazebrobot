"""Who screened a step and who booked its fish (docs/user_scoped_workflow_design.md)."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish

GENOTYPE = "Tg(gfap:PMCA2-mCherry-zf)"
STEP = "20261104T18:23:00"


def _dish(cross, number):
    dish = FishDish.create_new(
        cross_id=cross, dish_number=number, genotype=GENOTYPE, responsible="t",
        fish_count=20, dof="20261028", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def _step(client, dish_id):
    return client.get(f"/dishes/{dish_id}").json()["data"]["screening_results"]["screenings"][0]


def test_step_and_allocations_name_who_did_them(client):
    dish_id = _dish(f"CROSS_{uuid.uuid4().hex[:6]}", 1)
    client.cookies.set("metazebrobot_user", "lovelacea")
    client.post(f"/screening/{dish_id}/steps", data={
        "screening_datetime": STEP, "dpf_screened": 7, "indicators_screened": "mCherry",
        "count_screened_this_step": 20})
    client.post(f"/screening/{dish_id}/steps/{STEP}/allocations", data={
        "bucket": "negative_screened", "disposition": "discarded", "count": 5})
    client.cookies.set("metazebrobot_user", "turinga")  # someone else finishes the step
    client.post(f"/screening/{dish_id}/steps/{STEP}/allocations", data={
        "bucket": "negative_screened", "disposition": "discarded", "count": 3})

    step = _step(client, dish_id)
    assert step["screened_by"] == "lovelacea"
    assert [a["recorded_by"] for a in step["allocations"]] == ["lovelacea", "turinga"]
    page = client.get(f"/screening/{dish_id}").text
    assert "recorded by turinga" in page


def test_placing_fish_from_a_new_step_names_the_screener(client):
    cross = f"CROSS_{uuid.uuid4().hex[:6]}"
    source = _dish(cross, 1)
    plate = client.post(f"/dishes/{source}/plate/new", data={"wells": 12},
                        follow_redirects=False).headers["location"].split("/")[2]
    client.cookies.set("metazebrobot_user", "lovelacea")
    client.post(f"/dishes/{plate}/plate/add-fish",
                data={"source_dish_id": source, "result": "positive", "step": "new"})
    step = _step(client, source)
    assert step["screened_by"] == "lovelacea"
    assert [a["recorded_by"] for a in step["allocations"]] == ["lovelacea"]


def test_saving_without_a_user_leaves_existing_records_unattributed(client):
    dish_id = _dish(f"CROSS_{uuid.uuid4().hex[:6]}", 1)
    client.post(f"/screening/{dish_id}/steps", data={
        "screening_datetime": STEP, "dpf_screened": 7, "indicators_screened": "mCherry",
        "count_screened_this_step": 20})
    client.cookies.set("metazebrobot_user", "lovelacea")
    client.post(f"/screening/{dish_id}/steps/{STEP}/allocations", data={
        "bucket": "negative_screened", "disposition": "discarded", "count": 5})
    step = _step(client, dish_id)
    assert step.get("screened_by") is None  # created with no user picked; a later save doesn't stamp it
    assert step["allocations"][0]["recorded_by"] == "lovelacea"


def test_backfill_fills_only_steps_with_one_observer(tmp_path):
    import importlib.util
    import sqlite3
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "backfill", Path(__file__).resolve().parents[1] / "scripts" / "backfill_screened_by.py")
    backfill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill)
    db = tmp_path / "b.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE screening_steps (dish_id, screening_datetime, screened_by)")
        conn.execute("CREATE TABLE fish_screening_observations (source_dish_id, screening_datetime, observed_by)")
        conn.executemany("INSERT INTO screening_steps VALUES (?, ?, ?)",
                         [("A", "t1", None), ("B", "t1", None), ("C", "t1", None), ("D", "t1", "kept")])
        conn.executemany("INSERT INTO fish_screening_observations VALUES (?, ?, ?)",
                         [("A", "t1", "lovelacea"), ("A", "t1", "lovelacea"),
                          ("B", "t1", "lovelacea"), ("B", "t1", "turinga"),
                          ("C", "t1", None), ("D", "t1", "lovelacea")])
    assert backfill.main(["--db-path", str(db)]) == 0
    with sqlite3.connect(db) as conn:
        assert dict(conn.execute("SELECT dish_id, screened_by FROM screening_steps")) == {
            "A": "lovelacea", "B": None, "C": None, "D": "kept"}


def test_screener_can_be_set_from_the_steps_table(client):
    import sqlite3
    from metazebrobot.data import users
    dish_id = _dish(f"CROSS_{uuid.uuid4().hex[:6]}", 1)
    client.post(f"/screening/{dish_id}/steps", data={
        "screening_datetime": STEP, "dpf_screened": 7, "indicators_screened": "mCherry",
        "count_screened_this_step": 20})
    with data_manager.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        users.upsert_from_pyrat(conn, [{"userid": 115, "username": "lovelacea", "first_name": "Ada",
                                        "last_name": "Lovelace", "fullname": "Lovelace Ada"}],
                                "active", "2026-11-04 00:00:00")
        users.mark_app_users(conn, [115])
        conn.commit()
    try:
        table = client.post(f"/screening/{dish_id}/steps/{STEP}/screened-by",
                            data={"screened_by": "lovelacea"}).text
        assert '<option value="lovelacea" selected>Ada Lovelace</option>' in table
        assert _step(client, dish_id)["screened_by"] == "lovelacea"
        assert client.post(f"/screening/{dish_id}/steps/{STEP}/screened-by",
                           data={"screened_by": "nobody"}).status_code == 422
        client.post(f"/screening/{dish_id}/steps/{STEP}/screened-by", data={"screened_by": ""})
        assert _step(client, dish_id).get("screened_by") is None
    finally:
        with data_manager.get_connection() as conn:
            conn.execute("DELETE FROM users")
            conn.commit()
