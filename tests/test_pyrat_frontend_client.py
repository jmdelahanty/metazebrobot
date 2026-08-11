"""
Tests for PyRAT frontend-session helpers.
"""

import requests

from metazebrobot.utils import pyrat_frontend_client


class _Cookie:
    def __init__(self, name):
        self.name = name


class _CookieJar:
    def __init__(self):
        self._names = []

    def add(self, name):
        if name not in self._names:
            self._names.append(name)

    def __iter__(self):
        return iter(_Cookie(name) for name in self._names)


class _Response:
    def __init__(self, status_code=200, *, headers=None, url=None, text="", cookies=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url or "https://pyrat.example/aquatic/"
        self.text = text
        self.cookies = cookies or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error


class _FrontendSession:
    def __init__(self):
        self.headers = {}
        self.cookies = _CookieJar()
        self.get_urls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_urls.append(url)
        if url.endswith("/aquatic/"):
            self.cookies.add("client_reference")
            return _Response(url=url)
        if url.endswith("/frontend/session/login"):
            return _Response(url=url)
        if "choose_alias" in url:
            return _Response(
                url=(
                    "https://pyrat.example/aquatic/frontend/session/choose_alias"
                    "?sessionid=session123"
                ),
            )
        if "welcome?sessionid=session123" in url:
            return _Response(url=url)
        if "tank_crossing_list?sessionid=session123" in url:
            return _Response(url=url)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs.get("data") or {}))
        if url.endswith("/frontend/session/login"):
            self.cookies.add("session_session123")
            return _Response(
                status_code=303,
                headers={"Location": "choose_alias?sessionid=session123"},
                url=url,
                cookies={"session_session123": "cookie"},
            )
        if url.endswith("/frontend/session/choose_alias"):
            return _Response(
                status_code=303,
                headers={"Location": "welcome?sessionid=session123"},
                url=url,
            )
        if "welcome?sessionid=session123" in url:
            return _Response(
                status_code=303,
                headers={"Location": "../tanks/tank_crossing_list?sessionid=session123"},
                url=url,
            )
        raise AssertionError(f"unexpected POST {url}")


def test_login_pyrat_frontend_visits_crossings_page(monkeypatch):
    session = _FrontendSession()
    monkeypatch.setattr(pyrat_frontend_client.requests, "Session", lambda: session)

    debug_info = {}
    returned_session, session_id = pyrat_frontend_client.login_pyrat_frontend(
        "https://pyrat.example/aquatic/",
        "user",
        "password",
        debug_info=debug_info,
    )

    assert returned_session is session
    assert session_id == "session123"
    assert (
        "https://pyrat.example/aquatic/frontend/tanks/"
        "tank_crossing_list?sessionid=session123"
    ) in session.get_urls
    assert debug_info["frontend_crossings_status_code"] == 200
    assert debug_info["alias_choice"] == "no_alias"
    assert debug_info["welcome_continue_status_code"] == 303
    assert (
        "https://pyrat.example/aquatic/frontend/session/choose_alias",
        {"sessionid": "session123", "user_id": ""},
    ) in session.post_calls


def test_enrich_crossings_reauthenticates_once_after_auth_failure(monkeypatch):
    crossings = [
        {"crossing_id": 1, "status": "recorded"},
        {"crossing_id": 2, "status": "recorded"},
    ]

    login_calls = []

    def fake_login(*args, **kwargs):
        login_calls.append(args)
        return object(), f"session{len(login_calls)}"

    monkeypatch.setattr(pyrat_frontend_client, "login_pyrat_frontend", fake_login)

    calls = []

    def fake_fetch_detail(*args, **kwargs):
        session_id = args[2]
        crossing_id = kwargs.get("crossing_id") or args[3]
        calls.append((session_id, crossing_id))
        if session_id == "session1" and crossing_id == 1:
            response = _Response(status_code=401, text='{"detail":"Login chain not finished."}')
            error = requests.HTTPError("401 unauthorized")
            error.response = response
            raise error
        return {
            "crossing_detail": {
                "crossing_id": crossing_id,
                "crossing_tanks": 2,
                "raised_tanks": 1,
                "really_raised_tanks": 1,
            },
        }

    monkeypatch.setattr(pyrat_frontend_client, "fetch_crossing_detail", fake_fetch_detail)

    enriched = pyrat_frontend_client.enrich_crossings_with_frontend_details(
        crossings,
        {
            "base_url": "https://pyrat.example/aquatic/",
            "username": "user",
            "password": "password",
        },
    )

    assert len(login_calls) == 2
    assert calls == [("session1", 1), ("session2", 1), ("session2", 2)]
    assert [item["crossing_tanks"] for item in enriched] == [2, 2]
    assert [item["raised_tanks"] for item in enriched] == [1, 1]


def test_enrich_crossings_stops_after_auth_retry_fails(monkeypatch):
    crossings = [
        {"crossing_id": 1, "status": "recorded"},
        {"crossing_id": 2, "status": "recorded"},
        {"crossing_id": 3, "status": "recorded"},
    ]

    login_calls = []

    def fake_login(*args, **kwargs):
        login_calls.append(args)
        return object(), f"session{len(login_calls)}"

    monkeypatch.setattr(pyrat_frontend_client, "login_pyrat_frontend", fake_login)

    calls = []

    def fake_fetch_detail(*args, **kwargs):
        calls.append(kwargs.get("crossing_id") or args[3])
        response = _Response(status_code=401, text='{"detail":"Login chain not finished."}')
        error = requests.HTTPError("401 unauthorized")
        error.response = response
        raise error

    monkeypatch.setattr(pyrat_frontend_client, "fetch_crossing_detail", fake_fetch_detail)

    enriched = pyrat_frontend_client.enrich_crossings_with_frontend_details(
        crossings,
        {
            "base_url": "https://pyrat.example/aquatic/",
            "username": "user",
            "password": "password",
        },
    )

    assert len(login_calls) == 2
    assert calls == [1, 1]
    assert enriched == crossings
