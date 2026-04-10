"""
Interactive CLI helpers for storing and clearing PyRAT credentials.
"""

from __future__ import annotations

import argparse
import getpass
from typing import Callable, Optional, Sequence

from rich.console import Console

from .pyrat_credentials import (
    DEFAULT_PYRAT_BASE_URL,
    KEYRING_SERVICE,
    clear_pyrat_credentials,
    get_stored_pyrat_api_credentials,
    get_stored_pyrat_frontend_credentials,
    save_pyrat_credentials,
)


def setup_credentials(
    console: Console,
    *,
    input_func: Callable[[str], str] = input,
    getpass_func: Callable[[str], str] = getpass.getpass,
) -> bool:
    """Interactively collect and store PyRAT credentials in keyring."""
    console.print("\n[bold blue]PyRAT Credential Setup[/bold blue]")
    console.print(
        "API tokens and optional frontend login credentials will be stored securely "
        "in your system keyring.\n"
    )

    existing_api = get_stored_pyrat_api_credentials()
    existing_frontend = get_stored_pyrat_frontend_credentials(
        default_base_url=existing_api["base_url"] if existing_api else None
    )

    if existing_api:
        console.print(
            f"[yellow]Existing API credentials found for: {existing_api['base_url']}[/yellow]"
        )
        console.print("[dim]Press Enter to keep an existing value.[/dim]")
    if existing_frontend:
        console.print(
            f"[yellow]Existing frontend username: {existing_frontend['username']}[/yellow]"
        )

    console.print("[dim]Enter your PyRAT API credentials:[/dim]\n")

    default_base_url = (
        existing_api["base_url"] if existing_api else DEFAULT_PYRAT_BASE_URL
    )
    base_url = input_func(f"Base URL [{default_base_url}]: ").strip()
    if not base_url:
        base_url = default_base_url

    console.print(
        "[dim]Client token format: ClientId-ClientKey "
        "(e.g. myapp123-secretkey456)[/dim]"
    )
    client_prompt = "Client Token"
    if existing_api:
        client_prompt += " [press Enter to keep existing]"
    client_token = getpass_func(f"{client_prompt}: ")
    if not client_token and existing_api:
        client_token = existing_api["client_token"]
    if not client_token:
        console.print("[bold red]Error: Client token is required[/bold red]")
        return False

    console.print(
        "[dim]User token: Your personal API token from PyRAT[/dim]"
    )
    user_prompt = "User Token"
    if existing_api:
        user_prompt += " [press Enter to keep existing]"
    user_token = getpass_func(f"{user_prompt}: ")
    if not user_token and existing_api:
        user_token = existing_api["user_token"]
    if not user_token:
        console.print("[bold red]Error: User token is required[/bold red]")
        return False

    console.print(
        "\n[dim]Optional: store PyRAT frontend login credentials for backend/v1 "
        "session access.[/dim]"
    )
    if existing_frontend:
        console.print(
            "[dim]Press Enter to keep the stored frontend username, or type '-' to clear it.[/dim]"
        )
        frontend_username = input_func(
            f"Frontend Username [{existing_frontend['username']}]: "
        ).strip()
    else:
        console.print(
            "[dim]Leave username blank to skip storing frontend credentials.[/dim]"
        )
        frontend_username = input_func("Frontend Username [skip]: ").strip()

    frontend_password: Optional[str] = None
    if existing_frontend and not frontend_username:
        frontend_username = existing_frontend["username"]
        frontend_password = existing_frontend["password"]
    elif frontend_username == "-":
        frontend_username = None
    elif frontend_username:
        password_prompt = "Frontend Password"
        if (
            existing_frontend
            and frontend_username == existing_frontend["username"]
        ):
            password_prompt += " [press Enter to keep existing]"
        frontend_password = getpass_func(f"{password_prompt}: ")
        if not frontend_password:
            if (
                existing_frontend
                and frontend_username == existing_frontend["username"]
            ):
                frontend_password = existing_frontend["password"]
            else:
                console.print(
                    "[yellow]Frontend password left blank; frontend credential storage was skipped.[/yellow]"
                )
                frontend_username = None

    try:
        save_pyrat_credentials(
            base_url=base_url,
            client_token=client_token,
            user_token=user_token,
            frontend_username=frontend_username or None,
            frontend_password=frontend_password if frontend_username else None,
        )
    except Exception as exc:
        console.print(f"[bold red]Error saving credentials: {exc}[/bold red]")
        return False

    console.print("\n[bold green]✓ Credentials saved to system keyring![/bold green]")
    console.print(f"[dim]Service: {KEYRING_SERVICE}[/dim]")
    console.print(f"[dim]Base URL: {base_url}[/dim]")
    if frontend_username:
        console.print(f"[dim]Frontend Username: {frontend_username}[/dim]")
    console.print("\n[cyan]Recommended usage:[/cyan]")
    console.print("[dim]  python pyrat_credentials_tool.py --setup-credentials[/dim]")
    console.print("[dim]  python pyrat_query_tool.py --responsible \"username\"[/dim]\n")
    return True


def clear_credentials(console: Console) -> bool:
    """Remove stored PyRAT credentials from keyring."""
    if not get_stored_pyrat_api_credentials():
        console.print("[yellow]No credentials found in keyring[/yellow]")
        return True

    try:
        clear_pyrat_credentials()
    except Exception as exc:
        console.print(f"[bold red]Error clearing credentials: {exc}[/bold red]")
        return False

    console.print("[bold green]✓ Credentials removed from system keyring[/bold green]")
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the standalone PyRAT credential management CLI."""
    parser = argparse.ArgumentParser(
        description="Store or clear PyRAT API and optional frontend credentials",
    )
    parser.add_argument(
        "--setup-credentials",
        action="store_true",
        help="Interactively store PyRAT credentials in the system keyring",
    )
    parser.add_argument(
        "--clear-credentials",
        action="store_true",
        help="Remove stored PyRAT credentials from the system keyring",
    )

    args = parser.parse_args(argv)
    console = Console()

    if args.setup_credentials:
        return 0 if setup_credentials(console) else 1
    if args.clear_credentials:
        return 0 if clear_credentials(console) else 1

    parser.print_help()
    return 1
