#!/usr/bin/env python3
"""
Inspect PyRAT credentials stored in the user's system keyring.

By default, secrets are masked. Use --show-secrets or --env-format only when
you are in a private terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    from metazebrobot.utils.pyrat_credentials import KEYRING_SERVICE
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))
    from metazebrobot.utils.pyrat_credentials import KEYRING_SERVICE

import keyring


KEYS = (
    "base_url",
    "client_token",
    "user_token",
    "frontend_base_url",
    "frontend_username",
    "frontend_password",
)

ENV_KEYS = {
    "base_url": "PYRAT_BASE_URL",
    "client_token": "PYRAT_CLIENT_TOKEN",
    "user_token": "PYRAT_USER_TOKEN",
    "frontend_base_url": "PYRAT_FRONTEND_BASE_URL",
    "frontend_username": "PYRAT_FRONTEND_USERNAME",
    "frontend_password": "PYRAT_FRONTEND_PASSWORD",
}


def mask_secret(value: Optional[str]) -> str:
    """Return a readable masked representation of a keyring value."""
    if value is None:
        return "<missing>"
    if value == "":
        return "<empty>"
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} ({len(value)} chars)"


def quote_systemd_env_value(value: str) -> str:
    """Quote a value for a systemd EnvironmentFile assignment."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def get_keyring_values(service: str) -> dict[str, Optional[str]]:
    """Load all PyRAT keyring values for a keyring service."""
    values: dict[str, Optional[str]] = {}
    for key in KEYS:
        values[key] = keyring.get_password(service, key)
    return values


def print_human(values: dict[str, Optional[str]], *, show_secrets: bool) -> None:
    """Print credentials in a human-readable form."""
    width = max(len(key) for key in KEYS)
    for key in KEYS:
        value = values[key]
        display = value if show_secrets else mask_secret(value)
        if display is None:
            display = "<missing>"
        print(f"{key:<{width}}  {display}")


def print_env(values: dict[str, Optional[str]], *, include_empty: bool) -> None:
    """Print credentials in systemd EnvironmentFile format."""
    print("# PyRAT credentials for metazebrobot-api")
    print("# Install with mode 0600 root:root, for example /etc/metazebrobot/pyrat.env")
    for key in KEYS:
        value = values[key]
        if value is None and not include_empty:
            continue
        env_key = ENV_KEYS[key]
        print(f"{env_key}={quote_systemd_env_value(value or '')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect PyRAT credentials stored in the system keyring.",
    )
    parser.add_argument(
        "--service",
        default=KEYRING_SERVICE,
        help=f"Keyring service name to read (default: {KEYRING_SERVICE})",
    )
    parser.add_argument(
        "--show-secrets",
        action="store_true",
        help="Print full keyring values instead of masked values.",
    )
    parser.add_argument(
        "--env-format",
        action="store_true",
        help="Print full values as PYRAT_* assignments for a systemd EnvironmentFile.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="With --env-format, include empty assignments for missing values.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        values = get_keyring_values(args.service)
    except Exception as exc:
        print(f"Error reading keyring service {args.service!r}: {exc}", file=sys.stderr)
        return 1

    if args.env_format:
        print(
            "Warning: --env-format prints full secrets. Do not paste this output into chat.",
            file=sys.stderr,
        )
        print_env(values, include_empty=args.include_empty)
    else:
        if args.show_secrets:
            print(
                "Warning: printing full secrets. Do not paste this output into chat.",
                file=sys.stderr,
            )
        print_human(values, show_secrets=args.show_secrets)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
