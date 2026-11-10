"""Demo copy (METAZEBROBOT_DEMO=1): read-only, with a banner on every page."""

from fastapi.testclient import TestClient

from metazebrobot.api_server import create_app


def test_demo_copy_refuses_writes_and_shows_banner(tmp_db_path, monkeypatch):
    monkeypatch.setenv("METAZEBROBOT_DEMO", "1")
    with TestClient(create_app(str(tmp_db_path))) as demo:
        page = demo.get("/")
        assert page.status_code == 200
        assert "DEMO COPY" in page.text

        refused = demo.post("/dishes/DEMO_DISH/fish", json={})
        assert refused.status_code == 403
        assert refused.json()["error"] == "demo_read_only"
        assert demo.post("/walkthrough/setup").status_code == 403
        assert demo.patch("/fish/00000000-0000-4000-8000-000000000000", json={}).status_code == 403

        # Choosing who is viewing only sets a cookie, so it stays allowed.
        assert demo.post("/set-user", data={"username": "lovelacea"},
                         follow_redirects=False).status_code == 303


def test_normal_service_has_no_banner(tmp_db_path, monkeypatch):
    monkeypatch.delenv("METAZEBROBOT_DEMO", raising=False)
    with TestClient(create_app(str(tmp_db_path))) as normal:
        assert "DEMO COPY" not in normal.get("/").text
