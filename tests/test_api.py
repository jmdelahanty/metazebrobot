"""
Tests for the MetaZebrobot read-only API.

These are integration tests that run against a live API server.
Make sure the service is running before executing:
    sudo systemctl start metazebrobot-api

Run tests with:
    pixi run pytest tests/test_api.py -v
"""

import requests
import pytest

# Configure the API base URL
API_BASE_URL = "http://localhost:8000"


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_basic(self):
        """Health check should return ok status."""
        response = requests.get(f"{API_BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_with_db_check(self):
        """Health check with database verification should succeed."""
        response = requests.get(f"{API_BASE_URL}/health", params={"check_db": True})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"


class TestDishesEndpoint:
    """Tests for the /dishes endpoint."""

    def test_list_dishes(self):
        """Should return a list of dishes."""
        response = requests.get(f"{API_BASE_URL}/dishes")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_list_dishes_with_limit(self):
        """Should respect the limit parameter."""
        response = requests.get(f"{API_BASE_URL}/dishes", params={"limit": 5})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5

    def test_list_dishes_filter_by_status(self):
        """Should filter dishes by status."""
        response = requests.get(f"{API_BASE_URL}/dishes", params={"status": "inactive"})
        assert response.status_code == 200
        data = response.json()
        # All returned dishes should have the requested status
        for dish in data["items"]:
            assert dish["status"] == "inactive"

    def test_list_dishes_filter_by_cross_id(self):
        """Should filter dishes by cross_id."""
        # First get a cross_id from the database
        crosses_response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 1})
        if crosses_response.json()["items"]:
            cross_id = crosses_response.json()["items"][0]["cross_id"]

            response = requests.get(f"{API_BASE_URL}/dishes", params={"cross_id": cross_id})
            assert response.status_code == 200
            data = response.json()
            # All returned dishes should have the requested cross_id
            for dish in data["items"]:
                assert dish["cross_id"] == cross_id

    def test_get_single_dish(self):
        """Should return details for a single dish."""
        # First get a dish_id from the list
        list_response = requests.get(f"{API_BASE_URL}/dishes", params={"limit": 1})
        if list_response.json()["items"]:
            dish_id = list_response.json()["items"][0]["dish_id"]

            response = requests.get(f"{API_BASE_URL}/dishes/{dish_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["dish_id"] == dish_id

    def test_get_nonexistent_dish(self):
        """Should return 404 for a dish that doesn't exist."""
        response = requests.get(f"{API_BASE_URL}/dishes/NONEXISTENT_DISH_12345")
        assert response.status_code == 404


class TestCrossesEndpoint:
    """Tests for the /crosses endpoint."""

    def test_list_crosses(self):
        """Should return a list of crosses."""
        response = requests.get(f"{API_BASE_URL}/crosses")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_list_crosses_with_limit(self):
        """Should respect the limit parameter."""
        response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 3

    def test_list_crosses_has_expected_fields(self):
        """Crosses should have expected fields."""
        response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 1})
        assert response.status_code == 200
        data = response.json()
        if data["items"]:
            cross = data["items"][0]
            assert "cross_id" in cross
            assert "line_strain" in cross
            assert "cross_type" in cross

    def test_list_crosses_with_active_dishes_filter(self):
        """Should filter to crosses with active dishes."""
        response = requests.get(f"{API_BASE_URL}/crosses", params={"has_active_dishes": True})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        # Note: May be empty if no dishes are active

    def test_get_single_cross(self):
        """Should return details for a single cross."""
        # First get a cross_id from the list
        list_response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 1})
        if list_response.json()["items"]:
            cross_id = list_response.json()["items"][0]["cross_id"]

            response = requests.get(f"{API_BASE_URL}/crosses/{cross_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["cross_id"] == cross_id

    def test_get_cross_with_dishes(self):
        """Should include dishes when requested."""
        # First get a cross_id from the list
        list_response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 1})
        if list_response.json()["items"]:
            cross_id = list_response.json()["items"][0]["cross_id"]

            response = requests.get(
                f"{API_BASE_URL}/crosses/{cross_id}",
                params={"include_dishes": True}
            )
            assert response.status_code == 200
            data = response.json()
            assert "dishes" in data
            assert isinstance(data["dishes"], list)

    def test_get_nonexistent_cross(self):
        """Should return 404 for a cross that doesn't exist."""
        response = requests.get(f"{API_BASE_URL}/crosses/NONEXISTENT_CROSS_12345")
        assert response.status_code == 404


class TestDataIntegrity:
    """Tests to verify data relationships and integrity."""

    def test_dish_cross_relationship(self):
        """Dishes should reference valid crosses."""
        # Get some dishes
        dishes_response = requests.get(f"{API_BASE_URL}/dishes", params={"limit": 10})
        dishes = dishes_response.json()["items"]

        # Get all crosses
        crosses_response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 100})
        cross_ids = {c["cross_id"] for c in crosses_response.json()["items"]}

        # Each dish's cross_id should exist in crosses
        for dish in dishes:
            if dish["cross_id"]:  # cross_id might be null
                assert dish["cross_id"] in cross_ids, \
                    f"Dish {dish['dish_id']} references unknown cross {dish['cross_id']}"

    def test_cross_dishes_count_matches(self):
        """Number of dishes for a cross should match filtered query."""
        # Get a cross with its dishes
        list_response = requests.get(f"{API_BASE_URL}/crosses", params={"limit": 1})
        if list_response.json()["items"]:
            cross_id = list_response.json()["items"][0]["cross_id"]

            # Get cross with included dishes
            cross_response = requests.get(
                f"{API_BASE_URL}/crosses/{cross_id}",
                params={"include_dishes": True}
            )
            embedded_dishes = cross_response.json().get("dishes", [])

            # Get dishes filtered by cross_id
            dishes_response = requests.get(
                f"{API_BASE_URL}/dishes",
                params={"cross_id": cross_id, "limit": 1000}
            )
            filtered_dishes = dishes_response.json()["items"]

            assert len(embedded_dishes) == len(filtered_dishes), \
                f"Cross {cross_id}: embedded dishes ({len(embedded_dishes)}) != filtered dishes ({len(filtered_dishes)})"
