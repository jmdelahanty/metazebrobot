"""Mortality inventory regressions, including legacy care and count corrections."""

import json

import pytest

from metazebrobot.data.data_manager import DataManager
from metazebrobot.models.fish_dish import FishDish, QualityCheckData, ScreeningResults, ScreeningStep


@pytest.fixture
def inventory_manager(tmp_db_path):
    manager = DataManager()
    manager.database_path = tmp_db_path
    assert manager.ensure_schema()
    return manager


def create_dish(manager, count=31):
    dish = FishDish.create_new(cross_id='19219', dish_number=1, genotype='wt',
                               responsible='test', fish_count=count, dof='20260928')
    assert manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True))
    return dish.dish_id


def current_count(manager, dish_id):
    with manager.get_connection() as conn:
        return conn.execute('SELECT current_fish_count FROM dishes WHERE dish_id = ?',
                            (dish_id,)).fetchone()[0]


def test_historical_relational_checks_backfill_and_reload(inventory_manager):
    manager = inventory_manager
    dish_id = create_dish(manager)
    with manager.get_connection() as conn:
        payload = json.loads(conn.execute('SELECT data FROM dishes WHERE dish_id = ?', (dish_id,)).fetchone()[0])
        payload.pop('mortality_inventory_version')
        # The normalized table must win over stale embedded JSON.
        payload['quality_checks'] = {'20261002T13:02:45': {'num_dead': 1}}
        conn.execute('UPDATE dishes SET data = ? WHERE dish_id = ?', (json.dumps(payload), dish_id))
        for index in range(25):
            conn.execute('INSERT INTO quality_checks (dish_id, check_time, num_dead) VALUES (?, ?, ?)',
                         (dish_id, f'20261001T12:{index:02d}:00', 0))
        conn.execute('INSERT INTO quality_checks (dish_id, check_time, num_dead) VALUES (?, ?, ?)',
                     (dish_id, '20261002T13:02:45', 8))
        conn.commit()
    assert manager.backfill_mortality_inventory()
    assert current_count(manager, dish_id) == 23
    dish = FishDish(**manager.load_single_dish(dish_id))
    assert dish.current_fish_count == 23
    assert len(dish.quality_checks) == 26
    assert FishDish(**manager.get_fish_dishes()[dish_id]).current_fish_count == 23
    assert manager.backfill_mortality_inventory()
    assert current_count(manager, dish_id) == 23
    # A subsequent whole-dish save must retain relational care history.
    assert manager.save_fish_dish(dish.model_dump(mode='json', exclude_none=True))
    assert len(manager.get_dish_quality_checks(dish_id, limit=100)) == 26


def test_legacy_recount_covers_earlier_deaths_but_never_later_deaths(inventory_manager):
    manager = inventory_manager
    dish_id = create_dish(manager, count=23)
    with manager.get_connection() as conn:
        payload = json.loads(conn.execute('SELECT data FROM dishes WHERE dish_id = ?', (dish_id,)).fetchone()[0])
        payload.pop('mortality_inventory_version')
        conn.execute('UPDATE dishes SET data = ? WHERE dish_id = ?', (json.dumps(payload), dish_id))
        conn.execute('INSERT INTO quality_checks (dish_id, check_time, num_dead) VALUES (?, ?, ?)',
                     (dish_id, '20261001T12:00:00', 8))
        conn.commit()
    assert manager.save_dish_count_event({'dish_id': dish_id, 'event_datetime': '20261001T13:00:00',
                                         'new_current_fish_count': 23, 'new_fish_count': 23,
                                         'reason': 'manual_recount'})
    assert manager.backfill_mortality_inventory()
    assert current_count(manager, dish_id) == 23
    assert manager.save_dish_quality_check(dish_id, {'check_time': '20261002T12:00:00', 'num_dead': 3})
    assert current_count(manager, dish_id) == 20
    assert manager.save_dish_quality_check(dish_id, {'check_time': '20261001T12:00:00', 'num_dead': 0})
    assert current_count(manager, dish_id) == 20
    assert manager.backfill_mortality_inventory()
    assert current_count(manager, dish_id) == 20


def test_check_replacement_and_invalid_mortality(inventory_manager):
    manager = inventory_manager
    dish_id = create_dish(manager)
    for deaths, expected in [(8, 23), (8, 23), (5, 26), (0, 31), (40, 0)]:
        assert manager.update_dish_quality_check(dish_id, {'check_time': '20261002T12:00:00', 'num_dead': deaths})
        assert current_count(manager, dish_id) == expected
    assert not manager.save_dish_quality_check(dish_id, {'check_time': '20261002T12:00:00', 'num_dead': -1})
    assert current_count(manager, dish_id) == 0
    assert manager.get_dish_quality_checks(dish_id)[0]['num_dead'] == 40


def test_care_save_rolls_back_when_recalculation_fails(inventory_manager, monkeypatch):
    manager = inventory_manager
    dish_id = create_dish(manager)
    original = manager._refresh_dish_inventory
    calls = []
    def fail_after_insert(conn, dish_id):
        calls.append(dish_id)
        if len(calls) == 2:
            raise ValueError('simulated recalculation failure')
        original(conn, dish_id)
    monkeypatch.setattr(manager, '_refresh_dish_inventory', fail_after_insert)
    assert not manager.save_dish_quality_check(dish_id, {'check_time': '20261002T12:00:00', 'num_dead': 8})
    assert manager.get_dish_quality_checks(dish_id) == []
    assert current_count(manager, dish_id) == 31


def test_mortality_and_screening_history_are_chronological():
    dish = FishDish.create_new(cross_id='19219', dish_number=1, genotype='wt',
                               responsible='test', fish_count=31, dof='20260928')
    dish.add_quality_check(QualityCheckData(check_time='20261001T12:00:00', num_dead=8))
    step = ScreeningStep(screening_datetime='20261001T13:00:00', dpf_screened=3,
                         indicators_screened=[], criteria='test', count_screened_this_step=10,
                         allocations=[{'bucket': 'other', 'disposition': 'discarded', 'count': 5}])
    dish.screening_results = ScreeningResults(screenings=[step])
    dish.unit_mortality = {'20261001T14:00:00': 2}
    dish.refresh_screening_state()
    assert step.count_before_step == 23
    assert step.count_after_step == 18
    assert dish.current_fish_count == 16


def test_legacy_recount_before_first_death_does_not_cover_future_loss(inventory_manager):
    manager = inventory_manager
    dish_id = create_dish(manager, count=23)
    with manager.get_connection() as conn:
        payload = json.loads(conn.execute('SELECT data FROM dishes WHERE dish_id = ?', (dish_id,)).fetchone()[0])
        payload.pop('mortality_inventory_version')
        conn.execute('UPDATE dishes SET data = ? WHERE dish_id = ?', (json.dumps(payload), dish_id))
        conn.commit()
    assert manager.save_dish_count_event({'dish_id': dish_id, 'event_datetime': '20261001T13:00:00',
                                         'new_current_fish_count': 23, 'new_fish_count': 23,
                                         'reason': 'manual_recount'})
    assert manager.backfill_mortality_inventory()
    assert manager.save_dish_quality_check(dish_id, {'check_time': '20261002T12:00:00', 'num_dead': 8})
    assert current_count(manager, dish_id) == 15


def test_unit_iso_date_is_compared_to_compact_screening_time(inventory_manager):
    manager = inventory_manager
    dish_id = create_dish(manager)
    unit_id = manager.create_housing_unit(dish_id=dish_id, position_label='main')
    assert manager.log_housing_unit_check(unit_id, check_time='2026-10-01T12:00:00', num_dead=8)
    dish = FishDish(**manager.load_single_dish(dish_id))
    step = ScreeningStep(screening_datetime='20261001T11:00:00', dpf_screened=3,
                         indicators_screened=[], criteria='test', count_screened_this_step=10,
                         allocations=[])
    dish.screening_results = ScreeningResults(screenings=[step])
    dish.refresh_screening_state()
    assert step.count_before_step == 31
    assert step.count_after_step == 31
    assert dish.current_fish_count == 23


@pytest.mark.parametrize('invalid_deaths', [-1, 1.5, 'invalid'])
def test_unit_invalid_mortality_cannot_change_inventory(inventory_manager, invalid_deaths):
    manager = inventory_manager
    dish_id = create_dish(manager)
    unit_id = manager.create_housing_unit(dish_id=dish_id, position_label='main')
    assert not manager.log_housing_unit_check(unit_id, check_time='2026-10-01T12:00:00',
                                              num_dead=invalid_deaths)
    assert current_count(manager, dish_id) == 31
    assert manager.get_housing_unit_checks(unit_id) == []
