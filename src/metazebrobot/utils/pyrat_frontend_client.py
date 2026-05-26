"""
Helpers for PyRAT frontend session authentication and backend/v1 requests.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import urllib3

from .pyrat_credentials import get_pyrat_frontend_credentials, normalize_base_url

logger = logging.getLogger(__name__)


def _disable_ssl_warnings() -> None:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _frontend_crossings_url(base_url: str, session_id: str) -> str:
    """Return the PyRAT frontend crossings page URL for a logged-in session."""
    return urljoin(
        normalize_base_url(base_url),
        f"frontend/tanks/tank_crossing_list?sessionid={session_id}",
    )


def _frontend_choose_alias_url(base_url: str) -> str:
    """Return the PyRAT frontend alias-selection endpoint URL."""
    return urljoin(normalize_base_url(base_url), "frontend/session/choose_alias")


def login_pyrat_frontend(
    base_url: str,
    username: str,
    password: str,
    verify_ssl: bool = False,
    debug_info: Optional[Dict[str, Any]] = None,
) -> Tuple[requests.Session, str]:
    """Create a logged-in PyRAT frontend session and return its session id."""
    _disable_ssl_warnings()

    root_url = normalize_base_url(base_url)
    login_url = urljoin(root_url, "frontend/session/login")
    origin = f"{urlparse(root_url).scheme}://{urlparse(root_url).netloc}"

    session = requests.Session()
    session.headers.update({"Accept": "text/html,application/xhtml+xml"})
    started = perf_counter()

    initial = session.get(root_url, verify=verify_ssl, timeout=15)
    initial.raise_for_status()
    if debug_info is not None:
        debug_info["root_status_code"] = initial.status_code
        debug_info["cookie_names_after_root"] = sorted(cookie.name for cookie in session.cookies)

    session.get(login_url, verify=verify_ssl, timeout=15).raise_for_status()
    if debug_info is not None:
        debug_info["login_page_cookie_names"] = sorted(cookie.name for cookie in session.cookies)

    login_response = session.post(
        login_url,
        data={
            "username": username,
            "password": password,
            "grant_type": "password",
        },
        headers={
            "Origin": origin,
            "Referer": login_url,
        },
        allow_redirects=False,
        verify=verify_ssl,
        timeout=15,
    )

    if login_response.status_code not in (302, 303):
        raise RuntimeError(
            f"PyRAT frontend login failed with status {login_response.status_code}"
        )

    location = login_response.headers.get("Location")
    if not location:
        raise RuntimeError("PyRAT frontend login response did not include a redirect location")

    redirect_url = urljoin(login_url, location)
    session_id = parse_qs(urlparse(redirect_url).query).get("sessionid", [None])[0]
    if not session_id:
        raise RuntimeError("PyRAT frontend login redirect did not include a session id")

    expected_session_cookie_name = f"session_{session_id}"
    if debug_info is not None:
        debug_info["login_post_status_code"] = login_response.status_code
        debug_info["login_post_location"] = location
        debug_info["login_post_set_cookie_present"] = bool(login_response.headers.get("Set-Cookie"))
        debug_info["login_post_response_cookie_names"] = sorted(login_response.cookies.keys())
        debug_info["cookie_names_after_login_post"] = sorted(cookie.name for cookie in session.cookies)
        debug_info["has_expected_session_cookie_after_login_post"] = (
            expected_session_cookie_name in debug_info["cookie_names_after_login_post"]
        )

    landing_response = session.get(redirect_url, verify=verify_ssl, timeout=15)
    landing_response.raise_for_status()
    if debug_info is not None:
        debug_info["landing_status_code"] = landing_response.status_code
        debug_info["landing_url"] = landing_response.url
        debug_info["cookie_names_after_landing"] = sorted(cookie.name for cookie in session.cookies)
        debug_info["has_expected_session_cookie_after_landing"] = (
            expected_session_cookie_name in debug_info["cookie_names_after_landing"]
        )

    if "choose_alias" in landing_response.url:
        alias_response = session.post(
            _frontend_choose_alias_url(base_url),
            data={
                "sessionid": session_id,
                "user_id": "",
            },
            headers={
                "Origin": origin,
                "Referer": landing_response.url,
            },
            allow_redirects=False,
            verify=verify_ssl,
            timeout=15,
        )
        if alias_response.status_code not in (302, 303):
            alias_response.raise_for_status()
        alias_location = alias_response.headers.get("Location")
        alias_redirect_response = None
        if alias_location:
            alias_redirect_response = session.get(
                urljoin(_frontend_choose_alias_url(base_url), alias_location),
                verify=verify_ssl,
                timeout=15,
            )
            alias_redirect_response.raise_for_status()

            if "welcome" in alias_redirect_response.url:
                welcome_response = session.post(
                    alias_redirect_response.url,
                    data={"sessionid": session_id},
                    headers={
                        "Origin": origin,
                        "Referer": alias_redirect_response.url,
                    },
                    allow_redirects=False,
                    verify=verify_ssl,
                    timeout=15,
                )
                if welcome_response.status_code in (302, 303):
                    welcome_location = welcome_response.headers.get("Location")
                    if welcome_location:
                        welcome_redirect_response = session.get(
                            urljoin(alias_redirect_response.url, welcome_location),
                            verify=verify_ssl,
                            timeout=15,
                        )
                        welcome_redirect_response.raise_for_status()
                    if debug_info is not None:
                        debug_info["welcome_continue_location"] = welcome_location
                else:
                    welcome_response.raise_for_status()
                if debug_info is not None:
                    debug_info["welcome_continue_status_code"] = welcome_response.status_code
                    debug_info["cookie_names_after_welcome_continue"] = sorted(cookie.name for cookie in session.cookies)
        if debug_info is not None:
            debug_info["alias_submit_status_code"] = alias_response.status_code
            debug_info["alias_submit_location"] = alias_location
            debug_info["alias_choice"] = "no_alias"
            debug_info["cookie_names_after_alias_submit"] = sorted(cookie.name for cookie in session.cookies)
            debug_info["has_expected_session_cookie_after_alias_submit"] = (
                expected_session_cookie_name in debug_info["cookie_names_after_alias_submit"]
            )
            if alias_location:
                debug_info["alias_redirect_url"] = urljoin(
                    _frontend_choose_alias_url(base_url),
                    alias_location,
                )

    crossings_response = session.get(
        _frontend_crossings_url(base_url, session_id),
        verify=verify_ssl,
        timeout=15,
    )
    crossings_response.raise_for_status()
    if debug_info is not None:
        debug_info["frontend_crossings_status_code"] = crossings_response.status_code
        debug_info["frontend_crossings_url"] = crossings_response.url
        debug_info["cookie_names_after_frontend_crossings"] = sorted(cookie.name for cookie in session.cookies)

    if debug_info is not None:
        debug_info["final_frontend_cookie_names"] = sorted(cookie.name for cookie in session.cookies)
        debug_info["has_expected_session_cookie_final"] = (
            expected_session_cookie_name in debug_info["final_frontend_cookie_names"]
        )
        debug_info["login_elapsed_seconds"] = round(perf_counter() - started, 3)
    logger.info("PyRAT frontend login completed in %.2fs", perf_counter() - started)
    return session, session_id


def fetch_crossing_detail(
    session: requests.Session,
    base_url: str,
    session_id: str,
    crossing_id: Any,
    verify_ssl: bool = False,
) -> Dict[str, Any]:
    """Fetch backend/v1 crossing detail payload for one crossing."""
    _disable_ssl_warnings()

    detail_url = urljoin(
        normalize_base_url(base_url),
        f"backend/v1/tanks/crossings/{crossing_id}/details",
    )
    response = session.get(
        detail_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {session_id}",
            "Referer": _frontend_crossings_url(base_url, session_id),
        },
        verify=verify_ssl,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def enrich_crossings_with_frontend_details(
    crossings: List[Dict[str, Any]],
    frontend_credentials: Optional[Dict[str, str]],
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
    verify_ssl: bool = False,
) -> List[Dict[str, Any]]:
    """Best-effort enrichment of crossings with backend/v1 detail counts."""
    if not crossings or not frontend_credentials:
        return list(crossings)

    started = perf_counter()
    try:
        session, session_id = login_pyrat_frontend(
            frontend_credentials["base_url"],
            frontend_credentials["username"],
            frontend_credentials["password"],
            verify_ssl=verify_ssl,
        )
    except Exception as exc:
        logger.warning("Unable to create PyRAT frontend session: %s", exc)
        return list(crossings)

    enriched: List[Dict[str, Any]] = []
    total = len(crossings)
    successful_details = 0

    for index, crossing in enumerate(crossings, start=1):
        merged = dict(crossing)
        crossing_id = merged.get("crossing_id")

        if crossing_id is not None:
            try:
                payload = fetch_crossing_detail(
                    session,
                    frontend_credentials["base_url"],
                    session_id,
                    crossing_id,
                    verify_ssl=verify_ssl,
                )
                detail = payload.get("crossing_detail", payload)

                merged["completed"] = detail.get("completed")
                merged["crossing_tanks"] = detail.get("crossing_tanks")
                merged["raised_tanks"] = detail.get("raised_tanks")
                merged["really_raised_tanks"] = detail.get("really_raised_tanks")

                detail_tanks = detail.get("tanks")
                if isinstance(detail_tanks, dict):
                    merged["tanks"] = detail_tanks

                for key in (
                    "status",
                    "date_of_record",
                    "date_of_set_up",
                    "date_of_raise",
                    "description",
                    "responsible_id",
                    "responsible_fullname",
                    "strain_id",
                ):
                    if detail.get(key) is not None:
                        merged[key] = detail.get(key)
                successful_details += 1
            except Exception as exc:
                logger.warning(
                    "Unable to enrich crossing %s from PyRAT backend/v1: %s",
                    crossing_id,
                    exc,
                )
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    if exc.response.status_code in (401, 403):
                        logger.warning(
                            "Stopping PyRAT backend/v1 enrichment after auth failure; "
                            "remaining crossings will use base API data."
                        )
                        enriched.append(merged)
                        enriched.extend(dict(item) for item in crossings[index:])
                        break

        enriched.append(merged)

        if progress_callback and (index == 1 or index % 10 == 0 or index == total):
            progress_callback(f"Loading PyRAT detail counts ({index}/{total})...")

    logger.info(
        "PyRAT frontend detail enrichment fetched %s/%s crossing details in %.2fs",
        successful_details,
        total,
        perf_counter() - started,
    )
    return enriched
