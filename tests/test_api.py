"""Focused tests for the read-only JSON API using a temporary database."""

import json
import sqlite3
import uuid

import pytest

from metazebrobot import api_server
from metazebrobot.data.data_manager import data_manager


@pytest.fixture()
def api_cross(client, seed_cross_dishes):
    """Cache one cross that owns two active local dishes."""
    cross_id, dish_a, dish_b = seed_cross_dishes
    payload = {
        "crossing_id": cross_id,
        "status": "set-up",
        "date_of_record": "2026-08-20T00:00:00",
        "strain_name": "Tg(elavl3:GCaMP7ff)",
        "cross_type": "incross",
        "responsible_fullname": "Test Researcher",
        "tanks": {
            "parents": [
                {
                    "tank_id": 6311,
                    "location_rack_name": "M10",
                    "tank_position": "D1",
                }
            ]
        },
    }
    with data_manager.get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO crosses
            (cross_id, cross_status, line_strain, data, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                cross_id,
                payload["status"],
                payload["strain_name"],
                json.dumps(payload),
            ),
        )
        conn.commit()
    return cross_id, dish_a, dish_b


class TestHealthEndpoint:
    def test_health_basic(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_with_db_check(self, client):
        response = client.get("/health", params={"check_db": True})

        assert response.status_code == 200
        assert response.json()["db"] == "ok"


class TestDishesEndpoint:
    def test_list_dishes(self, client, seed_full_dish):
        response = client.get("/dishes")

        assert response.status_code == 200
        assert seed_full_dish in {item["dish_id"] for item in response.json()["items"]}

    def test_list_dishes_respects_limit(self, client, seed_full_dish):
        response = client.get("/dishes", params={"limit": 1})

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_list_dishes_filters_by_status(self, client, seed_full_dish):
        with data_manager.get_connection() as conn:
            conn.execute(
                "UPDATE dishes SET status = 'inactive' WHERE dish_id = ?",
                (seed_full_dish,),
            )
            conn.commit()

        response = client.get("/dishes", params={"status": "inactive"})

        assert response.status_code == 200
        matching = [
            item for item in response.json()["items"]
            if item["dish_id"] == seed_full_dish
        ]
        assert matching and matching[0]["status"] == "inactive"

    def test_list_dishes_filters_by_cross_id(self, client, api_cross):
        cross_id, dish_a, dish_b = api_cross

        response = client.get("/dishes", params={"cross_id": cross_id})

        assert response.status_code == 200
        assert {item["dish_id"] for item in response.json()["items"]} == {dish_a, dish_b}

    def test_get_single_dish(self, client, seed_full_dish):
        response = client.get(f"/dishes/{seed_full_dish}")

        assert response.status_code == 200
        assert response.json()["dish_id"] == seed_full_dish

    def test_get_nonexistent_dish(self, client):
        response = client.get("/dishes/NONEXISTENT_DISH_12345")

        assert response.status_code == 404


def _dish_uuid(dish_id):
    with data_manager.get_connection() as conn:
        return conn.execute(
            "SELECT dish_uuid FROM dishes WHERE dish_id = ?", (dish_id,)
        ).fetchone()["dish_uuid"]


class TestDishUuidEndpoints:
    def test_dish_detail_includes_uuid(self, client, seed_full_dish):
        response = client.get(f"/dishes/{seed_full_dish}")

        assert response.status_code == 200
        assert response.json()["dish_uuid"] == _dish_uuid(seed_full_dish)

    def test_list_dishes_includes_uuid(self, client, seed_full_dish):
        response = client.get("/dishes")

        items = {item["dish_id"]: item for item in response.json()["items"]}
        assert items[seed_full_dish]["dish_uuid"] == _dish_uuid(seed_full_dish)

    def test_get_dish_by_uuid(self, client, seed_full_dish):
        dish_uuid = _dish_uuid(seed_full_dish)

        response = client.get(f"/dishes/by-uuid/{dish_uuid}")

        assert response.status_code == 200
        assert response.json()["dish_id"] == seed_full_dish
        assert response.json() == client.get(f"/dishes/{seed_full_dish}").json()

    def test_get_dish_by_unknown_uuid(self, client):
        missing = str(uuid.uuid4())

        response = client.get(f"/dishes/by-uuid/{missing}")

        assert response.status_code == 404
        assert response.json()["detail"] == {
            "error": "dish_not_found",
            "dish_uuid": missing,
        }

    def test_acquisition_and_snapshot_include_uuid(self, client, api_cross):
        cross_id, dish_a, dish_b = api_cross

        acquisition = client.get("/acquisition/dishes", params={"cross_id": cross_id})
        snapshot = client.get(f"/dishes/{dish_a}/citrus-snapshot")

        items = {item["dish_id"]: item for item in acquisition.json()["items"]}
        assert items[dish_a]["dish_uuid"] == _dish_uuid(dish_a)
        assert snapshot.json()["dish_uuid"] == _dish_uuid(dish_a)


class TestRevisionEndpoints:
    def test_snapshot_reports_revision_and_tracks_changes(self, client, api_cross):
        cross_id, dish_a, dish_b = api_cross
        first = client.get(f"/dishes/{dish_a}/citrus-snapshot").json()
        assert first["schema_version"] == 2
        assert isinstance(first["revision"], int)
        assert first["updated_at"]

        with data_manager.get_connection() as conn:
            conn.execute(
                "UPDATE dishes SET genotype = 'Tg(changed)' WHERE dish_id = ?", (dish_a,)
            )
            conn.commit()

        second = client.get(f"/dishes/{dish_a}/citrus-snapshot").json()
        assert second["revision"] == first["revision"] + 1
        assert second["dish_uuid"] == first["dish_uuid"]

    def test_detail_list_and_acquisition_include_revision(self, client, api_cross):
        cross_id, dish_a, dish_b = api_cross
        dish_uuid = _dish_uuid(dish_a)
        revision = client.get(f"/dishes/{dish_a}").json()["revision"]

        assert client.get(f"/dishes/by-uuid/{dish_uuid}").json()["revision"] == revision
        listed = {i["dish_id"]: i for i in client.get("/dishes").json()["items"]}
        assert listed[dish_a]["revision"] == revision
        acquisition = client.get("/acquisition/dishes", params={"cross_id": cross_id}).json()
        assert acquisition["schema_version"] == 2
        items = {i["dish_id"]: i for i in acquisition["items"]}
        assert items[dish_a]["revision"] == revision

    def test_fish_includes_revision(self, client, seed_dish):
        fish_id = data_manager.create_fish_subject(dish_id=seed_dish)

        fish = client.get(f"/fish/{fish_id}").json()

        assert fish["revision"] == 1
        assert fish["updated_at"]


def _failing_connection(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


class TestStructuredErrors:
    """JSON read endpoints share one error shape so callers can record it."""

    def test_unknown_dish(self, client):
        response = client.get("/dishes/NONEXISTENT_DISH_12345")

        assert response.status_code == 404
        assert response.json()["detail"] == {
            "error": "dish_not_found",
            "dish_id": "NONEXISTENT_DISH_12345",
        }

    def test_unknown_dish_fish_list(self, client):
        response = client.get("/dishes/NONEXISTENT_DISH_12345/fish")

        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "dish_not_found"

    def test_unknown_fish(self, client):
        fish_id = str(uuid.uuid4())

        response = client.get(f"/fish/{fish_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == {"error": "fish_not_found", "fish_id": fish_id}

    @pytest.mark.parametrize(
        "path",
        ["/dishes", "/acquisition/dishes", "/dishes/ANY", "/dishes/ANY/citrus-snapshot",
         "/dishes/by-uuid/ANY", "/dishes/ANY/fish"],
    )
    def test_dish_reads_report_database_error(self, client, monkeypatch, path):
        monkeypatch.setattr(api_server, "_open_readonly_connection", _failing_connection)

        response = client.get(path)

        assert response.status_code == 503
        assert response.json()["detail"] == {
            "error": "database_error",
            "message": "database is locked",
        }

    def test_fish_database_error_is_not_reported_as_missing(self, client, monkeypatch):
        monkeypatch.setattr(data_manager, "get_connection", _failing_connection)

        response = client.get(f"/fish/{uuid.uuid4()}")

        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "database_error"


class TestVersionEndpoint:
    def test_version_reports_running_code_and_schema(self, client):
        import subprocess
        from metazebrobot.consumer_contract import CONSUMER_OPENAPI_PATH, digest

        body = client.get("/version").json()

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        assert body["service_commit"] == head
        assert isinstance(body["service_commit_dirty"], bool)
        assert body["api_schema_version"] == 2
        assert body["started_at_utc"].endswith("Z")
        # Computed from the running app, equal to the committed pin.
        assert body["consumer_schema_sha256"] == digest(CONSUMER_OPENAPI_PATH.read_text())


class TestServedDpfUsesLabCalendar:
    def test_snapshot_dpf_follows_lab_date_not_host_clock(self, client, seed_full_dish, monkeypatch):
        from datetime import date

        with data_manager.get_connection() as conn:
            conn.execute("UPDATE dishes SET dof = '20260714', status = 'active' WHERE dish_id = ?",
                         (seed_full_dish,))
            conn.commit()
        # Pretend the lab calendar says 2026-07-21 (i.e. 20:06 EDT, 00:06Z next day).
        monkeypatch.setattr(api_server, "lab_calendar_date", lambda instant=None: date(2026, 7, 21))

        snapshot = client.get(f"/dishes/{seed_full_dish}/citrus-snapshot").json()
        assert snapshot["dpf"] == 7


class TestCrossesEndpoint:
    def test_cross_list_has_explicit_openapi_schema(self, client):
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = (
            response.json()["paths"]["/crosses"]["get"]["responses"]["200"]
            ["content"]["application/json"]["schema"]
        )
        assert schema["$ref"].endswith("/CrossListResponse")

    def test_list_crosses_normalizes_cached_pyrat_fields(self, client, api_cross):
        cross_id, _, _ = api_cross

        response = client.get("/crosses", params={"limit": 500})

        assert response.status_code == 200
        item = next(item for item in response.json()["items"] if item["cross_id"] == cross_id)
        assert item == {
            "cross_id": cross_id,
            "line_strain": "Tg(elavl3:GCaMP7ff)",
            "cross_type": "incross",
            "cross_status": "set-up",
            "request_date": "2026-08-20T00:00:00",
            "responsible_requestor": "Test Researcher",
        }

    def test_list_crosses_respects_limit(self, client, api_cross):
        response = client.get("/crosses", params={"limit": 1})

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_list_crosses_filters_to_active_dishes(self, client, api_cross):
        active_cross_id, _, _ = api_cross
        empty_cross_id = f"EMPTY_{uuid.uuid4().hex[:8]}"
        with data_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO crosses (cross_id, cross_status, line_strain, data)
                VALUES (?, 'recorded', 'AB', ?)
                """,
                (empty_cross_id, json.dumps({"crossing_id": empty_cross_id})),
            )
            conn.commit()

        response = client.get(
            "/crosses",
            params={"has_active_dishes": True, "limit": 500},
        )

        assert response.status_code == 200
        cross_ids = {item["cross_id"] for item in response.json()["items"]}
        assert active_cross_id in cross_ids
        assert empty_cross_id not in cross_ids

    def test_get_single_cached_cross(self, client, api_cross):
        cross_id, _, _ = api_cross

        response = client.get(f"/crosses/{cross_id}")

        assert response.status_code == 200
        assert response.json() == {
            "cross_id": cross_id,
            "line_strain": "Tg(elavl3:GCaMP7ff)",
            "parents": [{"identifier": "6311_M10_D1", "sex": "unknown"}],
            "source": "cache",
            "dishes": None,
        }

    def test_get_cross_with_dishes(self, client, api_cross):
        cross_id, dish_a, dish_b = api_cross

        response = client.get(
            f"/crosses/{cross_id}",
            params={"include_dishes": True},
        )

        assert response.status_code == 200
        assert {dish["dish_id"] for dish in response.json()["dishes"]} == {dish_a, dish_b}

    def test_uncached_cross_without_pyrat_returns_structured_error(self, client, monkeypatch):
        import metazebrobot.api_server as api_server

        monkeypatch.setattr(api_server, "get_pyrat_api_credentials", lambda: None)
        cross_id = f"MISSING_{uuid.uuid4().hex[:8]}"

        response = client.get(f"/crosses/{cross_id}")

        assert response.status_code == 503
        assert response.json()["detail"] == {
            "error": "pyrat_not_configured",
            "message": "Cross is not cached locally and PyRAT credentials are not configured.",
            "cross_id": cross_id,
        }


class TestDataIntegrity:
    def test_cross_dish_count_matches_filtered_collection(self, client, api_cross):
        cross_id, _, _ = api_cross

        cross_response = client.get(
            f"/crosses/{cross_id}",
            params={"include_dishes": True},
        )
        dishes_response = client.get(
            "/dishes",
            params={"cross_id": cross_id, "limit": 1000},
        )

        assert cross_response.status_code == 200
        assert dishes_response.status_code == 200
        assert len(cross_response.json()["dishes"]) == len(dishes_response.json()["items"])
