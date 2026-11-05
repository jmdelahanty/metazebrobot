"""The guided tour's cleanup leaves no rows behind."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


def test_cleanup_removes_every_tour_row(client):
    real = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1, genotype="Tg(gfap:PMCA2-mCherry-zf)",
        responsible="t", fish_count=10, dof="20261008", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    assert data_manager.save_fish_dish(real)
    setup = client.post("/walkthrough/setup")
    assert setup.status_code == 200
    assert client.post("/walkthrough/cleanup", json={}).json()["status"] == "ok"
    with data_manager.get_connection() as conn:
        for table in ("dishes", "screening_steps", "screening_step_allocations",
                      "screening_step_indicators", "housing_units", "dish_transgenes"):
            left = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE dish_id LIKE 'TOUR%'").fetchone()[0]
            assert left == 0, table
        assert conn.execute("SELECT COUNT(*) FROM dishes WHERE dish_id = ?", (real["dish_id"],)).fetchone()[0] == 1
