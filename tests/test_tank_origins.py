"""Tank origins through splits and targeted crossing searches (design step 2b).

Fixtures follow the real chain checked on 2026-10-06: tank 6728 was split from
6643 (SeparateEvent), 6643 came from outcross 14979 (Casper_HHMI x
Tg(gfap:b-ARK)), and its Casper_HHMI parent 6190 came from an AB Casper cross.
"""

import json
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from metazebrobot.api_server import (
    _ensure_cross_parent_provenance_schema,
    _upsert_cross_parent_provenance,
)
from metazebrobot.utils import tank_origins
from metazebrobot.utils.tank_heritage import derive_tank_heritage
from metazebrobot.utils.tank_origins import (
    RETRY_AFTER_DAYS,
    fetch_crossings_for_window,
    origin_chain,
    parse_tank_history,
    record_search_days,
    resolve_tank_origins,
    uncovered_span,
)


def separate(source, destination, when):
    return {"event_type_name": "SeparateEvent", "event_date": f"{when}T10:00:00",
            "related": [{"tank_id": source, "relation": "source"},
                        {"tank_id": destination, "relation": None}]}


def release(tank_id, when, dob):
    month, day, year = dob[5:7], dob[8:10], dob[:4]
    return {"event_type_name": "ReleaseEvent", "event_date": f"{when}T09:00:00",
            "related": [{"tank_id": tank_id, "relation": None}],
            "changes": {"date_of_birth_string": f"{month}/{day}/{year}"}}


def crossing(cross_id, parents, children):
    return {"crossing_id": cross_id, "date_of_set_up": "2025-02-25T08:00:00",
            "tanks": {"parents": parents, "children": children}}


CROSS_14979 = crossing(14979,
                       [{"tank_id": 6190, "strain_name": "Casper_HHMI", "strain_id": 20},
                        {"tank_id": 4014, "strain_name": "Tg(gfap:b-ARK)", "strain_id": 786}],
                       [{"tank_id": 6643, "strain_name": "Tg(gfap:b-ARK)", "strain_id": 786,
                         "date_of_birth": "2025-02-26T00:00:00"}])
CROSS_13000 = crossing(13000,
                       [{"tank_id": 5000, "strain_name": "AB Casper_HHMI", "strain_id": 14}],
                       [{"tank_id": 6190, "strain_name": "Casper_HHMI", "strain_id": 20,
                         "date_of_birth": "2024-10-30T00:00:00"}])


class FakeClient:
    def __init__(self, histories, windows):
        self.histories = histories
        self.windows = windows  # [(first_day, last_day, [crossings])]
        self.history_calls = []
        self.search_calls = []

    def tank_history(self, tank_id):
        self.history_calls.append(str(tank_id))
        return self.histories.get(str(tank_id), [])

    def crossings_recorded(self, since, until=None):
        self.search_calls.append((since, until))
        return [c for start, end, found in self.windows
                if since <= start and end <= until for c in found]


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE crosses (cross_id TEXT PRIMARY KEY, data TEXT)")
    _ensure_cross_parent_provenance_schema(conn)
    return conn


def cacher(conn):
    def cache(crossings):
        for payload in crossings:
            conn.execute("INSERT OR REPLACE INTO crosses (cross_id, data) VALUES (?, ?)",
                         (str(payload["crossing_id"]), json.dumps(payload)))
            _upsert_cross_parent_provenance(conn, str(payload["crossing_id"]), payload)
        conn.commit()
    return cache


def target_cross(conn):
    cacher(conn)([crossing(19220, [{"tank_id": 6728, "strain_name": "Tg(gfap:b-ARK)",
                                    "strain_id": 786}], [])])


class TestParseTankHistory:
    def test_split_source_and_release_birth_date(self):
        history = [  # newest first, as PyRAT serves it
            separate(6643, 6728, "2025-03-25"),
            release(6728, "2025-03-05", "2025-02-26"),
        ]
        assert parse_tank_history(6728, history) == {
            "status": "split", "source_tank_id": "6643",
            "event_date": "2025-03-25", "date_of_birth": "2025-02-26",
        }

    def test_copy_relations_and_self_source_are_ignored(self):
        history = [
            {"event_type_name": "ExportEvent", "related": [{"tank_id": 9, "relation": "copy"}]},
            separate(6728, 7000, "2025-06-01"),  # 6728 split *into* 7000
            release(6728, "2025-03-05", "2025-02-26"),
        ]
        facts = parse_tank_history(6728, history)
        assert facts["status"] == "released"
        assert facts["source_tank_id"] is None
        assert facts["date_of_birth"] == "2025-02-26"

    def test_earliest_split_wins(self):
        history = [separate(2, 1, "2025-05-01"), separate(3, 1, "2025-04-01")]
        assert parse_tank_history(1, history)["source_tank_id"] == "3"


class TestResolveTankOrigins:
    def client(self):
        return FakeClient(
            histories={
                "6728": [separate(6643, 6728, "2025-03-25"), release(6728, "2025-03-05", "2025-02-26")],
                "6643": [release(6643, "2025-03-05", "2025-02-26")],
                "6190": [release(6190, "2024-11-06", "2024-10-30")],
            },
            windows=[
                (date(2025, 2, 10), date(2025, 2, 28), [CROSS_14979]),
                (date(2024, 10, 15), date(2024, 11, 1), [CROSS_13000]),
            ],
        )

    def test_follows_split_then_finds_older_crosses(self, conn):
        target_cross(conn)
        client = self.client()
        stats = resolve_tank_origins(conn, client, cacher(conn), ["6728"])

        origins = {r["tank_id"]: dict(r) for r in conn.execute("SELECT * FROM tank_origins")}
        assert origins["6728"]["status"] == "split"
        assert origins["6728"]["source_tank_id"] == "6643"
        assert origins["6643"]["cross_search"] == "found"
        assert origins["6190"]["cross_search"] == "found"
        assert stats["splits"] == 1 and stats["found"] == 2
        assert origin_chain(conn, "6728")["origin_tank_id"] == "6643"

    def test_second_run_makes_no_pyrat_calls(self, conn):
        target_cross(conn)
        resolve_tank_origins(conn, self.client(), cacher(conn), ["6728"])
        again = self.client()
        resolve_tank_origins(conn, again, cacher(conn), ["6728"])
        assert again.history_calls == [] and again.search_calls == []

    def test_released_tank_without_birth_date_is_not_searched(self, conn):
        client = FakeClient({"1": [{"event_type_name": "ReleaseEvent", "related": []}]}, [])
        resolve_tank_origins(conn, client, cacher(conn), ["1"])
        row = conn.execute("SELECT cross_search FROM tank_origins WHERE tank_id = '1'").fetchone()
        assert row["cross_search"] == "no_dob"
        assert client.search_calls == []

    def test_search_window_brackets_birth_date(self, conn):
        client = self.client()
        resolve_tank_origins(conn, client, cacher(conn), ["6643"], max_generations=0)
        since, until = client.search_calls[0]
        assert since == date(2025, 2, 5) and until == date(2025, 3, 5)


class TestSearchCoverageAndExpiry:
    def test_overlapping_windows_fetch_only_uncovered_days(self, conn):
        client = FakeClient({}, [])
        cache = cacher(conn)
        assert fetch_crossings_for_window(conn, client, cache, date(2025, 2, 1), date(2025, 2, 28))
        assert fetch_crossings_for_window(conn, client, cache, date(2025, 2, 20), date(2025, 3, 10))
        assert not fetch_crossings_for_window(conn, client, cache, date(2025, 2, 5), date(2025, 3, 1))
        assert client.search_calls == [
            (date(2025, 2, 1), date(2025, 2, 28)),
            (date(2025, 3, 1), date(2025, 3, 10)),  # only the tail was new
        ]

    def test_covered_days_expire(self, conn, monkeypatch):
        record_search_days(conn, date(2025, 2, 1), date(2025, 2, 3))
        assert uncovered_span(conn, date(2025, 2, 1), date(2025, 2, 3)) is None
        later = datetime.now() + timedelta(days=RETRY_AFTER_DAYS + 1)
        monkeypatch.setattr(tank_origins, "_now", lambda: later)
        assert uncovered_span(conn, date(2025, 2, 1), date(2025, 2, 3)) == (
            date(2025, 2, 1), date(2025, 2, 3))

    def test_negative_results_are_retried_after_expiry(self, conn, monkeypatch):
        history = {"1": [release(1, "2025-03-05", "2025-02-26")]}
        resolve_tank_origins(conn, FakeClient(history, []), cacher(conn), ["1"])
        row = conn.execute("SELECT cross_search FROM tank_origins WHERE tank_id = '1'").fetchone()
        assert row["cross_search"] == "not_found"

        soon = FakeClient(history, [])
        resolve_tank_origins(conn, soon, cacher(conn), ["1"])
        assert soon.history_calls == []  # still fresh: trusted

        later = datetime.now() + timedelta(days=RETRY_AFTER_DAYS + 1)
        monkeypatch.setattr(tank_origins, "_now", lambda: later)
        fixed = FakeClient(history, [(date(2025, 2, 10), date(2025, 2, 28), [
            crossing(500, [{"tank_id": 2, "strain_name": "AB", "strain_id": 29}],
                     [{"tank_id": 1, "strain_name": "AB", "strain_id": 29}])])])
        stats = resolve_tank_origins(conn, fixed, cacher(conn), ["1"])
        assert stats["retried"] == 1
        assert fixed.history_calls[0] == "1"  # then the walk continues to its parent
        row = conn.execute("SELECT cross_search FROM tank_origins WHERE tank_id = '1'").fetchone()
        assert row["cross_search"] == "found"

    def test_found_results_never_expire(self, conn, monkeypatch):
        target_cross(conn)
        resolve_tank_origins(conn, TestResolveTankOrigins().client(), cacher(conn), ["6728"])
        later = datetime.now() + timedelta(days=RETRY_AFTER_DAYS + 1)
        monkeypatch.setattr(tank_origins, "_now", lambda: later)
        again = TestResolveTankOrigins().client()
        resolve_tank_origins(conn, again, cacher(conn), ["6728"])
        # Resolved tanks are not re-fetched; only stale negatives (4014, 5000) are.
        assert not {"6728", "6643", "6190"} & set(again.history_calls)


class TestHeritageThroughSplits:
    def test_split_tank_inherits_backgrounds_across_generations(self, conn):
        target_cross(conn)
        client = TestResolveTankOrigins().client()
        resolve_tank_origins(conn, client, cacher(conn), ["6728"])

        h = derive_tank_heritage(conn, 6728)
        assert h["producing_cross"]["cross_id"] == "14979"
        assert h["producing_cross"]["cross_type"] == "outcross"
        assert h["producing_cross"]["via_splits"] == [
            {"from_tank_id": "6643", "to_tank_id": "6728", "date": "2025-03-25"}]
        assert h["tank"]["date_of_birth"] == "2025-02-26"
        assert h["generations_traced"] == 2
        assert {b["value"]: b["sources"] for b in h["backgrounds"]} == {
            "AB": ["generation 2 (cross 13000)"]}
        assert {m["value"] for m in h["mutant_backgrounds"]} == {"casper"}

    def test_origin_chain_without_table_is_harmless(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE cross_children (cross_id TEXT, tank_id TEXT)")
        assert origin_chain(conn, "1") == {"origin_tank_id": "1", "splits": []}
