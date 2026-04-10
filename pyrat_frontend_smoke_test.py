#!/usr/bin/env python3
"""
Smoke test for PyRAT frontend-session authentication and backend/v1 crossing detail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

_SRC_DIR = Path(__file__).resolve().parent / "src"
if _SRC_DIR.exists():
    sys.path.insert(0, str(_SRC_DIR))

from metazebrobot.utils.pyrat_credentials import get_pyrat_frontend_credentials
from metazebrobot.utils.pyrat_frontend_client import (
    fetch_crossing_detail,
    login_pyrat_frontend,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Test stored PyRAT frontend credentials by logging into the web "
            "frontend and fetching one backend/v1 crossing detail payload."
        )
    )
    parser.add_argument(
        "--crossing-id",
        type=int,
        default=17907,
        help="Crossing ID to fetch from backend/v1 after login",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Enable SSL certificate verification",
    )
    parser.add_argument(
        "--full-payload",
        action="store_true",
        help="Print the full JSON payload instead of the summary subset",
    )
    args = parser.parse_args()

    credentials = get_pyrat_frontend_credentials()
    credential_summary = {
        "has_creds": bool(credentials),
        "base_url": credentials["base_url"] if credentials else None,
        "username": credentials["username"] if credentials else None,
        "has_password": bool(credentials and credentials.get("password")),
    }
    print("Credential summary:")
    print(json.dumps(credential_summary, indent=2, sort_keys=True))

    if not credentials:
        print("\nERROR: No frontend credentials found in env or keyring.", file=sys.stderr)
        return 1

    login_debug = {}
    try:
        session, session_id = login_pyrat_frontend(
            credentials["base_url"],
            credentials["username"],
            credentials["password"],
            verify_ssl=args.verify_ssl,
            debug_info=login_debug,
        )
    except Exception as exc:
        print(f"\nERROR: Frontend login failed: {exc}", file=sys.stderr)
        if login_debug:
            print(json.dumps(login_debug, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    print("\nLogin summary:")
    print(
        json.dumps(
            {
                "login_ok": True,
                "has_session_id": bool(session_id),
                "cookie_names": sorted(cookie.name for cookie in session.cookies),
                "debug": login_debug,
            },
            indent=2,
            sort_keys=True,
        )
    )

    try:
        payload = fetch_crossing_detail(
            session,
            credentials["base_url"],
            session_id,
            args.crossing_id,
            verify_ssl=args.verify_ssl,
        )
    except requests.HTTPError as exc:
        response = exc.response
        error_summary = {
            "status_code": response.status_code if response is not None else None,
            "response_text": (
                response.text[:500] if response is not None and response.text else None
            ),
            "cookie_names": sorted(cookie.name for cookie in session.cookies),
        }
        print(
            f"\nERROR: Crossing detail fetch failed for {args.crossing_id}:",
            file=sys.stderr,
        )
        print(json.dumps(error_summary, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"\nERROR: Crossing detail fetch failed for {args.crossing_id}: {exc}",
            file=sys.stderr,
        )
        return 1

    detail = payload.get("crossing_detail", payload)
    summary = {
        "crossing_id": detail.get("crossing_id"),
        "status": detail.get("status"),
        "date_of_raise": detail.get("date_of_raise"),
        "crossing_tanks": detail.get("crossing_tanks"),
        "raised_tanks": detail.get("raised_tanks"),
        "really_raised_tanks": detail.get("really_raised_tanks"),
        "children_count": len((detail.get("tanks") or {}).get("children", []) or []),
    }

    print("\nCrossing detail summary:")
    print(json.dumps(summary if not args.full_payload else payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
