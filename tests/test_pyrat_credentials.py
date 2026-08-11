"""
Tests for shared PyRAT credential helpers.
"""

from rich.console import Console

from metazebrobot.utils import pyrat_credentials
from metazebrobot.utils import pyrat_credentials_cli


class _KeyringStub:
    def __init__(self):
        self.store = {}

    def get_password(self, service, key):
        return self.store.get((service, key))

    def set_password(self, service, key, value):
        self.store[(service, key)] = value

    def delete_password(self, service, key):
        if (service, key) not in self.store:
            raise RuntimeError("credential not found")
        del self.store[(service, key)]


def test_get_pyrat_api_credentials_prefers_cli_over_env_and_keyring(monkeypatch):
    keyring_stub = _KeyringStub()
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "base_url", "https://stored.example/aquatic/")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "client_token", "stored-client")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "user_token", "stored-user")
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    monkeypatch.setenv("PYRAT_BASE_URL", "https://env.example/aquatic/")
    monkeypatch.setenv("PYRAT_CLIENT_TOKEN", "env-client")
    monkeypatch.setenv("PYRAT_USER_TOKEN", "env-user")

    credentials = pyrat_credentials.get_pyrat_api_credentials(
        cli_base_url="https://cli.example/aquatic",
        cli_client_token="cli-client",
        cli_user_token="cli-user",
    )

    assert credentials == {
        "base_url": "https://cli.example/aquatic/",
        "client_token": "cli-client",
        "user_token": "cli-user",
    }


def test_get_pyrat_frontend_credentials_falls_back_to_api_base_url(monkeypatch):
    keyring_stub = _KeyringStub()
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "base_url", "https://stored.example/aquatic")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "frontend_username", "frontend-user")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "frontend_password", "frontend-pass")
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    monkeypatch.delenv("PYRAT_FRONTEND_BASE_URL", raising=False)
    monkeypatch.delenv("PYRAT_FRONTEND_USERNAME", raising=False)
    monkeypatch.delenv("PYRAT_FRONTEND_PASSWORD", raising=False)

    credentials = pyrat_credentials.get_pyrat_frontend_credentials()

    assert credentials == {
        "base_url": "https://stored.example/aquatic/",
        "username": "frontend-user",
        "password": "frontend-pass",
    }


def test_get_pyrat_frontend_credentials_uses_api_env_base_url(monkeypatch):
    keyring_stub = _KeyringStub()
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    monkeypatch.setenv("PYRAT_BASE_URL", "https://env.example/aquatic")
    monkeypatch.delenv("PYRAT_FRONTEND_BASE_URL", raising=False)
    monkeypatch.setenv("PYRAT_FRONTEND_USERNAME", "frontend-user")
    monkeypatch.setenv("PYRAT_FRONTEND_PASSWORD", "frontend-pass")

    credentials = pyrat_credentials.get_pyrat_frontend_credentials()

    assert credentials == {
        "base_url": "https://env.example/aquatic/",
        "username": "frontend-user",
        "password": "frontend-pass",
    }


def test_save_pyrat_credentials_clears_stale_frontend_values_when_skipped(monkeypatch):
    keyring_stub = _KeyringStub()
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "frontend_username", "old-user")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "frontend_password", "old-pass")
    keyring_stub.set_password(pyrat_credentials.KEYRING_SERVICE, "frontend_base_url", "https://old.example/aquatic/")
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    pyrat_credentials.save_pyrat_credentials(
        base_url="https://new.example/aquatic",
        client_token="new-client",
        user_token="new-user",
    )

    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "base_url") == "https://new.example/aquatic/"
    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "client_token") == "new-client"
    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "user_token") == "new-user"
    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "frontend_username") is None
    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "frontend_password") is None
    assert keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "frontend_base_url") is None


def test_setup_credentials_keeps_existing_api_tokens_when_left_blank(monkeypatch):
    keyring_stub = _KeyringStub()
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE,
        "base_url",
        "https://stored.example/aquatic/",
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "client_token", "stored-client"
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "user_token", "stored-user"
    )
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    inputs = iter(["", ""])
    passwords = iter(["", ""])

    success = pyrat_credentials_cli.setup_credentials(
        Console(record=True),
        input_func=lambda _prompt: next(inputs),
        getpass_func=lambda _prompt: next(passwords),
    )

    assert success is True
    assert (
        keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "base_url")
        == "https://stored.example/aquatic/"
    )
    assert (
        keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "client_token")
        == "stored-client"
    )
    assert (
        keyring_stub.get_password(pyrat_credentials.KEYRING_SERVICE, "user_token")
        == "stored-user"
    )


def test_setup_credentials_keeps_existing_frontend_credentials_when_left_blank(monkeypatch):
    keyring_stub = _KeyringStub()
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE,
        "base_url",
        "https://stored.example/aquatic/",
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "client_token", "stored-client"
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "user_token", "stored-user"
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "frontend_username", "frontend-user"
    )
    keyring_stub.set_password(
        pyrat_credentials.KEYRING_SERVICE, "frontend_password", "frontend-pass"
    )
    monkeypatch.setattr(pyrat_credentials, "keyring", keyring_stub)

    inputs = iter(["", ""])
    passwords = iter(["", ""])

    success = pyrat_credentials_cli.setup_credentials(
        Console(record=True),
        input_func=lambda _prompt: next(inputs),
        getpass_func=lambda _prompt: next(passwords),
    )

    assert success is True
    assert (
        keyring_stub.get_password(
            pyrat_credentials.KEYRING_SERVICE, "frontend_username"
        )
        == "frontend-user"
    )
    assert (
        keyring_stub.get_password(
            pyrat_credentials.KEYRING_SERVICE, "frontend_password"
        )
        == "frontend-pass"
    )
