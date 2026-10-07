"""Nightly cross-cache sync orchestration (scripts/sync_cross_cache.py)."""

import json
import sqlite3
from datetime import date, timedelta

import pytest

from metazebrobot.api_server import (
    _ensure_cross_parent_provenance_schema,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils.cross_sync import (
    SyncLockBusy,
    exclusive_lock,
    heritage_counts,
    run_cross_sync,
    unplaced_parent_tanks,
)

TODAY = date.today()
OLD_DOB = TODAY - timedelta(days=400)


def crossing(cross_id, parents, children):
    return {"crossing_id": cross_id,
            "tanks": {"parents": [{"tank_id": t, "strain_name": "AB", "strain_id": 29}
                                  for t in parents],
                      "children": [{"tank_id": t, "strain_name": "AB", "strain_id": 29}
                                   for t in children]}}


def release(dob):
    return [{"event_type_name": "ReleaseEvent", "event_date": f"{dob}T09:00:00",
             "related": [],
             "changes": {"date_of_birth_string": dob.strftime("%m/%d/%Y")}}]


# Cached already: cross 100 produced tank 20; cross 200 uses tanks 20 (placed)
# and 30 (no birth date in PyRAT). Recent PyRAT window: new cross 300 whose
# parent tank 40 came from cross 50, recorded just before 40's birth.
CROSS_100 = crossing(100, [], [20])
CROSS_200 = crossing(200, [20, 30], [])
CROSS_300 = crossing(300, [40], [])
CROSS_50 = crossing(50, [], [40])


class FakeClient:
    def __init__(self, recent, open_tanks=()):
        self.recent = recent
        self.open_tanks = [str(t) for t in open_tanks]
        self.history_calls = []
        self.search_calls = []

    def open_tank_ids(self):
        return list(self.open_tanks)

    def tank_history(self, tank_id):
        self.history_calls.append(str(tank_id))
        return {"40": release(OLD_DOB)}.get(str(tank_id), [])

    def crossings_recorded(self, since, until=None):
        self.search_calls.append((since, until))
        if until is None:  # the nightly window
            return list(self.recent)
        return [CROSS_50] if since <= OLD_DOB - timedelta(days=1) <= until else []


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _ensure_cross_parent_provenance_schema(conn)
    cacher(conn)([CROSS_100, CROSS_200])
    return conn


def cacher(conn):
    def cache(crossings):
        for payload in crossings:
            conn.execute("INSERT OR REPLACE INTO crosses (cross_id, data) VALUES (?, ?)",
                         (str(payload["crossing_id"]), json.dumps(payload)))
            _upsert_cross_parent_provenance(conn, str(payload["crossing_id"]), payload)
        conn.commit()
    return cache


def test_syncs_window_then_resolves_only_unplaced_parent_tanks(conn):
    assert unplaced_parent_tanks(conn) == ["30"]
    client = FakeClient([CROSS_300])
    result = run_cross_sync(conn, client, cacher(conn), days=30, today=TODAY)

    assert client.search_calls[0] == (TODAY - timedelta(days=30), None)
    assert result["fetched"] == 1
    assert result["unplaced_tanks"] == 2  # 30 and the new cross's parent 40
    assert sorted(client.history_calls) == ["30", "40"]  # never the placed tank 20
    assert result["resolver"]["found"] == 1
    assert unplaced_parent_tanks(conn) == ["30"]
    assert result["before"]["crosses"] == 2 and result["after"]["crosses"] == 4

    synced = {r[0] for r in conn.execute("SELECT day FROM crossing_search_days")}
    assert (TODAY - timedelta(days=30)).isoformat() in synced
    assert TODAY.isoformat() in synced


def test_second_run_with_nothing_new_is_a_no_op(conn):
    run_cross_sync(conn, FakeClient([CROSS_300]), cacher(conn), today=TODAY)
    before = heritage_counts(conn)
    origins = [dict(r) for r in conn.execute("SELECT * FROM tank_origins ORDER BY tank_id")]

    again = FakeClient([CROSS_300])
    result = run_cross_sync(conn, again, cacher(conn), today=TODAY)
    assert again.history_calls == []
    assert again.search_calls == [(TODAY - timedelta(days=30), None)]  # just the window
    assert result["before"] == result["after"] == before
    assert [dict(r) for r in conn.execute("SELECT * FROM tank_origins ORDER BY tank_id")] == origins


def test_cache_write_failure_fails_the_run(conn):
    with pytest.raises(RuntimeError, match="not cached"):
        run_cross_sync(conn, FakeClient([CROSS_300]), lambda rows: None, today=TODAY)


def test_lock_prevents_concurrent_runs(tmp_path):
    lock = tmp_path / "zebrobot.db.cross-sync.lock"
    with exclusive_lock(lock):
        with pytest.raises(SyncLockBusy):
            with exclusive_lock(lock):
                pass
    with exclusive_lock(lock):  # released after the first run finishes
        pass


def test_open_tank_that_is_not_a_parent_is_resolved(conn):
    client = FakeClient([CROSS_300], open_tanks=["77"])
    result = run_cross_sync(conn, client, cacher(conn), today=TODAY)
    assert "77" in client.history_calls
    assert result["open_tanks_unplaced"] == 1


def test_open_tanks_already_placed_cost_nothing(conn):
    run_cross_sync(conn, FakeClient([CROSS_300]), cacher(conn), today=TODAY)  # places 40
    again = FakeClient([CROSS_300], open_tanks=["40"])
    result = run_cross_sync(conn, again, cacher(conn), today=TODAY)
    assert "40" not in again.history_calls
    assert result["open_tanks_unplaced"] == 0


def test_open_tanks_can_be_skipped(conn):
    client = FakeClient([CROSS_300], open_tanks=["77"])
    result = run_cross_sync(conn, client, cacher(conn), today=TODAY, include_open_tanks=False)
    assert result["open_tanks_unplaced"] == 0
    assert "77" not in client.history_calls
