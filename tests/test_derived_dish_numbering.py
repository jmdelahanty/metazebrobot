"""Derived dishes and plates take the cross's next dish number (docs/derived_dish_numbering_design.md)."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish


def _dish(cross, number, group=None, screened=None):
    dish = FishDish.create_new(
        cross_id=cross, dish_number=number, genotype="Tg(gfap:PMCA2-mCherry-zf)", responsible="t",
        fish_count=10, dof="20261023", container_type="petri_dish", source_group_id=group,
    ).model_dump(mode="json", exclude_none=True)
    if screened:
        dish["screening_results"] = {"screenings": [{
            "screening_datetime": "20261028T10:00:00", "dpf_screened": 5,
            "indicators_screened": ["mCherry"], "count_screened_this_step": screened,
            "allocations": []}]}
    assert data_manager.save_fish_dish(dish)
    return dish["dish_id"]


def test_split_and_plate_are_the_next_numbers_and_the_list_shows_container_and_parent(client):
    cross = f"9{uuid.uuid4().int % 10**8}"
    first = _dish(cross, 1, group=f"{cross}-G1", screened=10)
    _dish(cross, 2)
    _dish(cross, 4)  # numbering continues after the highest, gaps are left alone

    resp = client.post(f"/screening/{first}/steps/20261028T10:00:00/split",
                       data={"fish_count": 3, "population_type": "positive_screened"},
                       follow_redirects=False)
    assert resp.status_code == 303
    split = data_manager.load_single_dish(f"{cross}_5")
    assert split["parent_dish_id"] == first and split["dish_number"] == 5
    assert split["source_group_id"] == f"{cross}-G1"  # one group in, one group out

    plate = client.post(f"/dishes/{first}/plate/new", data={"wells": 12},
                        follow_redirects=False).headers["location"].split("/")[2]
    assert plate == f"{cross}_6"
    assert not data_manager.load_single_dish(plate).get("source_group_id")  # may mix groups

    page = client.get("/screening/").text
    row = page[page.index(f"<td>{plate}"):]
    row = row[:row.index("</tr>")]
    assert f"from {first}" in row and "well plate" in row
