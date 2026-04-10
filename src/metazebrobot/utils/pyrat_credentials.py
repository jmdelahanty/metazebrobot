"""
Shared helpers for PyRAT API and frontend credential storage and retrieval.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

import keyring

KEYRING_SERVICE = "pyrat-api"
DEFAULT_PYRAT_BASE_URL = "https://pyrataquatics.janelia.org/aquatic/"


def normalize_base_url(base_url: str) -> str:
    """Ensure PyRAT base URLs always end with a trailing slash."""
    return base_url if base_url.endswith("/") else f"{base_url}/"


def get_stored_base_url() -> Optional[str]:
    """Return the stored API base URL from keyring, if available."""
    try:
        return keyring.get_password(KEYRING_SERVICE, "base_url")
    except Exception:
        return None


def get_stored_pyrat_api_credentials() -> Optional[Dict[str, str]]:
    """Load PyRAT API credentials from keyring only."""
    try:
        base_url = keyring.get_password(KEYRING_SERVICE, "base_url")
        client_token = keyring.get_password(KEYRING_SERVICE, "client_token")
        user_token = keyring.get_password(KEYRING_SERVICE, "user_token")
    except Exception:
        return None

    if base_url and client_token and user_token:
        return {
            "base_url": normalize_base_url(base_url),
            "client_token": client_token,
            "user_token": user_token,
        }
    return None


def get_stored_pyrat_frontend_credentials(
    default_base_url: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Load optional PyRAT frontend credentials from keyring only."""
    try:
        base_url = (
            keyring.get_password(KEYRING_SERVICE, "frontend_base_url")
            or default_base_url
            or keyring.get_password(KEYRING_SERVICE, "base_url")
        )
        username = keyring.get_password(KEYRING_SERVICE, "frontend_username")
        password = keyring.get_password(KEYRING_SERVICE, "frontend_password")
    except Exception:
        return None

    if base_url and username and password:
        return {
            "base_url": normalize_base_url(base_url),
            "username": username,
            "password": password,
        }
    return None


def get_pyrat_api_credentials(
    cli_base_url: Optional[str] = None,
    cli_client_token: Optional[str] = None,
    cli_user_token: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Load PyRAT API credentials from CLI args, env vars, or keyring."""
    if cli_base_url and cli_client_token and cli_user_token:
        return {
            "base_url": normalize_base_url(cli_base_url),
            "client_token": cli_client_token,
            "user_token": cli_user_token,
        }

    env_base_url = os.environ.get("PYRAT_BASE_URL")
    env_client_token = os.environ.get("PYRAT_CLIENT_TOKEN")
    env_user_token = os.environ.get("PYRAT_USER_TOKEN")
    if env_base_url and env_client_token and env_user_token:
        return {
            "base_url": normalize_base_url(env_base_url),
            "client_token": env_client_token,
            "user_token": env_user_token,
        }

    return get_stored_pyrat_api_credentials()


def get_pyrat_frontend_credentials(default_base_url: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Load optional PyRAT frontend credentials from env vars or keyring."""
    env_base_url = os.environ.get("PYRAT_FRONTEND_BASE_URL")
    env_username = os.environ.get("PYRAT_FRONTEND_USERNAME")
    env_password = os.environ.get("PYRAT_FRONTEND_PASSWORD")

    if env_username and env_password:
        base_url = env_base_url
        if not base_url:
            try:
                base_url = keyring.get_password(KEYRING_SERVICE, "frontend_base_url")
            except Exception:
                base_url = None
        base_url = base_url or default_base_url or get_stored_base_url()
        if base_url:
            return {
                "base_url": normalize_base_url(base_url),
                "username": env_username,
                "password": env_password,
            }

    return get_stored_pyrat_frontend_credentials(default_base_url=default_base_url)


def save_pyrat_credentials(
    *,
    base_url: str,
    client_token: str,
    user_token: str,
    frontend_username: Optional[str] = None,
    frontend_password: Optional[str] = None,
    frontend_base_url: Optional[str] = None,
) -> None:
    """Persist PyRAT API and optional frontend credentials to keyring."""
    keyring.set_password(KEYRING_SERVICE, "base_url", normalize_base_url(base_url))
    keyring.set_password(KEYRING_SERVICE, "client_token", client_token)
    keyring.set_password(KEYRING_SERVICE, "user_token", user_token)

    if frontend_username and frontend_password:
        if frontend_base_url:
            keyring.set_password(
                KEYRING_SERVICE,
                "frontend_base_url",
                normalize_base_url(frontend_base_url),
            )
        keyring.set_password(KEYRING_SERVICE, "frontend_username", frontend_username)
        keyring.set_password(KEYRING_SERVICE, "frontend_password", frontend_password)
        return

    for key in ("frontend_username", "frontend_password", "frontend_base_url"):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass


def clear_pyrat_credentials() -> None:
    """Remove PyRAT API and frontend credentials from keyring."""
    for key in (
        "base_url",
        "client_token",
        "user_token",
        "frontend_username",
        "frontend_password",
        "frontend_base_url",
    ):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass
