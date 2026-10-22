"""Hand-entered cross parents (docs/manual_cross_parents_design.md)."""

import uuid

from metazebrobot.api_server import _upsert_cross_parent_provenance
from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish

GAL4 = "Tg(elavl3:GAL4FF; myl7:mTagBFP2)"
PYRAT_PAYLOAD = {"tanks": {"parents": [{"tank_id": 9243, "strain_name": GAL4, "generation": "F3"}]}}


def _cross_with_dish():
    cross = f"X{uuid.uuid4().hex[:8]}"
    with data_manager.get_connection() as conn:
        conn.execute("INSERT INTO crosses (cross_id) VALUES (?)", (cross,))
        _upsert_cross_parent_provenance(conn, cross, PYRAT_PAYLOAD)
        conn.commit()
    dish = FishDish.create_new(
        cross_id=cross, dish_number=1, genotype="AQ Line Creation", responsible="t",
        fish_count=10, dof="20261020", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    dish["screening_results"] = {"screenings": [{
        "screening_datetime": "20261022T13:39:00", "dpf_screened": 2,
        "indicators_screened": ["gal4ff; myl7:mtagbfp2", "ReaChR-TagRFPt"],
        "count_screened_this_step": 10, "allocations": []}]}
    assert data_manager.save_fish_dish(dish)
    return cross, dish["dish_id"]


def _constructs(dish_id):
    with data_manager.get_connection() as conn:
        return sorted(r[0] for r in conn.execute(
            "SELECT construct FROM dish_transgenes WHERE dish_id = ?", (dish_id,)))


def _indicator_matches(dish_id):
    with data_manager.get_connection() as conn:
        return sorted((r["dish_construct"] or "") for r in conn.execute(
            "SELECT dish_construct FROM screening_step_indicators WHERE dish_id = ?", (dish_id,)))


def test_hand_entered_parent_adds_its_construct_and_survives_a_pyrat_refresh(client):
    cross, dish_id = _cross_with_dish()
    assert _constructs(dish_id) == [GAL4]
    assert _indicator_matches(dish_id) == ["", GAL4]  # ReaChR not matched yet

    resp = client.post(f"/crosses/{cross}/parents", data={
        "strain": "UAS:ReaChR-TagRFPt", "tank_id": "5342", "role": "sire",
        "reason": "IVF sperm donor; only in the PyRAT crossing description"},
        follow_redirects=False)
    assert resp.status_code == 303 and dish_id in resp.headers["location"]
    assert _constructs(dish_id) == sorted([GAL4, "Tg(UAS:ReaChR-TagRFPt)"])
    assert _indicator_matches(dish_id) == sorted([GAL4, "Tg(UAS:ReaChR-TagRFPt)"])

    page = client.get(f"/crosses/{cross}/parents").text
    assert "entered by hand" in page and "IVF sperm donor" in page and "5342" in page

    with data_manager.get_connection() as conn:  # PyRAT refresh replaces only its own rows
        _upsert_cross_parent_provenance(conn, cross, PYRAT_PAYLOAD)
        conn.commit()
        rows = conn.execute("SELECT parent_index, source FROM cross_parents WHERE cross_id = ? "
                            "ORDER BY parent_index", (cross,)).fetchall()
        summary = conn.execute("SELECT transgenes FROM cross_background_summaries WHERE cross_id = ?",
                               (cross,)).fetchone()[0]
    assert [(r[0], r[1]) for r in rows] == [(1, "pyrat"), (101, "manual")]
    assert "ReaChR" in summary

    client.post(f"/crosses/{cross}/parents/101/remove")
    assert _constructs(dish_id) == [GAL4]


def test_reason_and_strain_are_required_and_pyrat_rows_cannot_be_removed(client):
    cross, _ = _cross_with_dish()
    assert client.post(f"/crosses/{cross}/parents",
                       data={"strain": "Tg(UAS:ReaChR-TagRFPt)", "reason": ""}).status_code == 422
    assert client.post(f"/crosses/{cross}/parents",
                       data={"strain": "", "reason": "x"}).status_code == 422
    assert client.post(f"/crosses/{cross}/parents/1/remove").status_code == 404
    assert client.post("/crosses/NOPE/parents", data={"strain": "a:b", "reason": "x"}).status_code == 404
    assert client.get(f"/crosses/{cross}/parents").status_code == 200
