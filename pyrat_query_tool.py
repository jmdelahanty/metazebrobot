#!/usr/bin/env python3
"""
PyRAT API Tank Query Tool

Retrieves tanks from the PyRAT API with flexible filtering options.
Can filter tanks by responsible user (looking up the ID automatically),
location, status, and other parameters.

Credentials can be stored securely in your system keyring. Run with
--setup-credentials to store them once, then use without specifying tokens.

Usage examples:
  # First time: store credentials in system keyring
  python pyrat_query_tool.py --setup-credentials

  # Then query without specifying credentials
  python pyrat_query_tool.py --responsible "ahrensm"
  python pyrat_query_tool.py --responsible "ahrensm" --rack "R101.2"
  python pyrat_query_tool.py --status "open"

  # Or override with explicit credentials
  python pyrat_query_tool.py --base-url "https://..." --client-token "..." --user-token "..." --responsible "ahrensm"

  # Save output to a JSON file
  python pyrat_query_tool.py --responsible "ahrensm" --output tanks.json
"""

import os
import sys
import json
import argparse
import requests
import keyring
import getpass
from urllib.parse import urljoin
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from rich.console import Console
from rich import print as rprint

# Keyring service name for storing PyRAT credentials
KEYRING_SERVICE = "pyrat-api"


def setup_credentials(console: Console) -> bool:
    """
    Interactively set up PyRAT API credentials in the system keyring.

    Args:
        console: Rich console for output

    Returns:
        True if credentials were saved successfully
    """
    console.print("\n[bold blue]PyRAT API Credential Setup[/bold blue]")
    console.print("Credentials will be stored securely in your system keyring.\n")

    # Check for existing credentials
    existing_url = keyring.get_password(KEYRING_SERVICE, "base_url")
    if existing_url:
        console.print(f"[yellow]Existing credentials found for: {existing_url}[/yellow]")
        overwrite = input("Overwrite existing credentials? [y/N]: ").strip().lower()
        if overwrite != 'y':
            console.print("[dim]Setup cancelled.[/dim]")
            return False

    # Get credentials from user
    console.print("[dim]Enter your PyRAT API credentials:[/dim]\n")

    base_url = input("Base URL [https://pyrataquatics.janelia.org/aquatic/]: ").strip()
    if not base_url:
        base_url = "https://pyrataquatics.janelia.org/aquatic/"

    console.print("[dim]Client token format: ClientId-ClientKey (e.g., myapp123-secretkey456)[/dim]")
    client_token = getpass.getpass("Client Token: ")
    if not client_token:
        console.print("[bold red]Error: Client token is required[/bold red]")
        return False

    console.print("[dim]User token: Your personal API token from PyRAT[/dim]")
    user_token = getpass.getpass("User Token: ")
    if not user_token:
        console.print("[bold red]Error: User token is required[/bold red]")
        return False

    # Store in keyring
    try:
        keyring.set_password(KEYRING_SERVICE, "base_url", base_url)
        keyring.set_password(KEYRING_SERVICE, "client_token", client_token)
        keyring.set_password(KEYRING_SERVICE, "user_token", user_token)

        console.print("\n[bold green]✓ Credentials saved to system keyring![/bold green]")
        console.print(f"[dim]Service: {KEYRING_SERVICE}[/dim]")
        console.print(f"[dim]Base URL: {base_url}[/dim]")
        console.print("\n[cyan]You can now run queries without specifying credentials:[/cyan]")
        console.print("[dim]  python pyrat_query_tool.py --responsible \"username\"[/dim]\n")
        return True
    except Exception as e:
        console.print(f"[bold red]Error saving credentials: {e}[/bold red]")
        return False


def get_credentials(console: Console,
                    cli_base_url: Optional[str] = None,
                    cli_client_token: Optional[str] = None,
                    cli_user_token: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Get PyRAT API credentials from CLI args, environment, or keyring.

    Priority order:
    1. CLI arguments (if all three provided)
    2. Environment variables (PYRAT_BASE_URL, PYRAT_CLIENT_TOKEN, PYRAT_USER_TOKEN)
    3. System keyring

    Args:
        console: Rich console for output
        cli_base_url: Base URL from CLI args
        cli_client_token: Client token from CLI args
        cli_user_token: User token from CLI args

    Returns:
        Dict with base_url, client_token, user_token or None if not found
    """
    # 1. Check CLI arguments
    if cli_base_url and cli_client_token and cli_user_token:
        console.print("[dim]Using credentials from command line arguments[/dim]\n")
        return {
            "base_url": cli_base_url,
            "client_token": cli_client_token,
            "user_token": cli_user_token
        }

    # 2. Check environment variables
    env_base_url = os.environ.get("PYRAT_BASE_URL")
    env_client_token = os.environ.get("PYRAT_CLIENT_TOKEN")
    env_user_token = os.environ.get("PYRAT_USER_TOKEN")

    if env_base_url and env_client_token and env_user_token:
        console.print("[dim]Using credentials from environment variables[/dim]\n")
        return {
            "base_url": env_base_url,
            "client_token": env_client_token,
            "user_token": env_user_token
        }

    # 3. Check system keyring
    try:
        kr_base_url = keyring.get_password(KEYRING_SERVICE, "base_url")
        kr_client_token = keyring.get_password(KEYRING_SERVICE, "client_token")
        kr_user_token = keyring.get_password(KEYRING_SERVICE, "user_token")

        if kr_base_url and kr_client_token and kr_user_token:
            console.print("[dim]Using credentials from system keyring[/dim]\n")
            return {
                "base_url": kr_base_url,
                "client_token": kr_client_token,
                "user_token": kr_user_token
            }
    except Exception as e:
        console.print(f"[yellow]Warning: Could not access keyring: {e}[/yellow]")

    return None


def clear_credentials(console: Console) -> bool:
    """
    Remove PyRAT API credentials from the system keyring.

    Args:
        console: Rich console for output

    Returns:
        True if credentials were cleared successfully
    """
    try:
        # Check if credentials exist
        existing = keyring.get_password(KEYRING_SERVICE, "base_url")
        if not existing:
            console.print("[yellow]No credentials found in keyring[/yellow]")
            return True

        # Delete each credential
        keyring.delete_password(KEYRING_SERVICE, "base_url")
        keyring.delete_password(KEYRING_SERVICE, "client_token")
        keyring.delete_password(KEYRING_SERVICE, "user_token")

        console.print("[bold green]✓ Credentials removed from system keyring[/bold green]")
        return True
    except Exception as e:
        console.print(f"[bold red]Error clearing credentials: {e}[/bold red]")
        return False


def get_user_id(base_url: str, client_token: str, user_token: str, 
                identifier: str, verify_ssl: bool = False) -> Optional[int]:
    """
    Look up the user ID based on the given identifier using the /users endpoint.
    
    The lookup is case-insensitive and checks if the identifier is contained
    in either the "fullname" or "username" fields.
    
    Args:
        base_url: Base URL of the PyRAT instance.
        client_token: API-Client-Token.
        user_token: API-User-Token.
        identifier: The full name or username string to search for.
        verify_ssl: Whether to verify SSL certificates.
        
    Returns:
        The user id (integer) if found, otherwise None.
    """
    if not base_url.endswith('/'):
        base_url += '/'
    
    api_base = urljoin(base_url, 'api/v3/')
    users_url = urljoin(api_base, 'users')
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    auth = (client_token, user_token)
    
    # Use wildcards for partial matching
    query_identifier = identifier if '*' in identifier else f"*{identifier}*"
    params = {
        'fullname': query_identifier,
        'l': 100  # limit results
    }
    
    try:
        response = requests.get(users_url, auth=auth, headers=headers, params=params, verify=verify_ssl)
        if response.status_code == 200:
            users = response.json()
            for user in users:
                # Check if the identifier is a substring of either the fullname or username
                fullname = user.get("fullname", "").lower()
                username = user.get("username", "").lower()
                if identifier.lower() in fullname or identifier.lower() in username:
                    print(f"Found user: {user.get('fullname')} (ID: {user.get('userid')})")
                    return user.get("userid")
            
            # If not found, try a different approach with exact username match
            params = {
                'user_name': identifier,
                'l': 100
            }
            response = requests.get(users_url, auth=auth, headers=headers, params=params, verify=verify_ssl)
            if response.status_code == 200:
                users = response.json()
                if users:
                    print(f"Found user: {users[0].get('fullname')} (ID: {users[0].get('userid')})")
                    return users[0].get("userid")
            
            print(f"Warning: No user found matching: {identifier}")
            return None
        else:
            print(f"Error fetching user list: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching user: {str(e)}")
        return None

def load_user_mapping(mapping_file: str) -> Dict[str, int]:
    """
    Load user mapping (username:userid) from a JSON file.
    
    Args:
        mapping_file: Path to the JSON file containing username to user ID mappings
        
    Returns:
        Dictionary mapping usernames to user IDs
    """
    try:
        with open(mapping_file, 'r') as f:
            mapping = json.load(f)
            
        # Convert the mapping to ensure keys are strings and values are integers
        # This handles both formats: username->id and id->username
        result = {}
        for key, value in mapping.items():
            # Handle if the JSON is in id:username format
            if key.isdigit() and isinstance(value, str):
                result[value] = int(key)
            # Handle if the JSON is in username:id format
            elif isinstance(key, str) and (isinstance(value, int) or (isinstance(value, str) and value.isdigit())):
                result[key] = int(value)
                
        print(f"Loaded {len(result)} username-to-ID mappings from {mapping_file}")
        return result
    except Exception as e:
        print(f"Error loading user mapping file: {str(e)}")
        return {}

def load_and_update_user_mapping(mapping_file: str,
                               base_url: str = None, 
                               client_token: str = None, 
                               user_token: str = None,
                               refresh: bool = False, 
                               verify_ssl: bool = False,
                               console: Optional[Console] = None
                           ) -> Dict[str, int]:
    """
    Load user mapping (username:userid) from a JSON file and optionally update it with API data.
    
    Args:
        mapping_file: Path to the JSON file containing username to user ID mappings
        base_url: Base URL of the PyRAT instance for API updates
        client_token: API-Client-Token for API updates
        user_token: API-User-Token for API updates
        refresh: Whether to refresh the mapping from the API
        verify_ssl: Whether to verify SSL certificates
        console: Rich console object for output (optional)
        
    Returns:
        Dictionary mapping usernames to user IDs
    """
    # Use provided console or create a new one if none provided
    if console is None:
        console = Console()
    
    # Initialize mapping
    username_to_id = {}
    
    # Check if mapping file exists
    mapping_exists = os.path.exists(mapping_file)
    
    # Load existing mapping if it exists
    if mapping_exists:
        try:
            with open(mapping_file, 'r') as f:
                mapping_data = json.load(f)
                
            # Convert the mapping - handle both formats
            if isinstance(mapping_data, dict):
                for key, value in mapping_data.items():
                    # Handle id:username format (convert to username:id)
                    if key.isdigit() and isinstance(value, str):
                        username_to_id[value] = int(key)
                    # Handle username:id format
                    elif isinstance(key, str) and (isinstance(value, int) or 
                                                 (isinstance(value, str) and value.isdigit())):
                        username_to_id[key] = int(value)
                
                console.print(f"[green]Loaded {len(username_to_id)} username-to-ID mappings from {mapping_file}[/green]\n")
        except Exception as e:
            console.print(f"[bold red]Error loading user mapping file: {str(e)}[/bold red]\n")
    
    # If refresh is requested and we have API credentials, update from API
    if refresh and base_url and client_token and user_token:
        console.print("[bold blue]Refreshing user mapping from API...[/bold blue]")
        
        if not base_url.endswith('/'):
            base_url += '/'
        
        api_base = urljoin(base_url, 'api/v3/')
        users_url = urljoin(api_base, 'users')
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        auth = (client_token, user_token)
        
        # Fetch all users
        all_users = []
        offset = 0
        limit = 100
        
        with console.status("[bold cyan]Fetching users from API...[/bold cyan]"):
            while True:
                params = {
                    'l': limit,
                    'o': offset
                }
                try:
                    response = requests.get(users_url, auth=auth, headers=headers, params=params, verify=verify_ssl)
                    if response.status_code != 200:
                        console.print(f"[bold red]Error fetching users: {response.status_code} - {response.text}[/bold red]")
                        break
                        
                    users = response.json()
                    if not users:
                        break
                        
                    all_users.extend(users)
                    if len(users) < limit:
                        break
                        
                    offset += limit
                except Exception as e:
                    console.print(f"[bold red]Error fetching users: {str(e)}[/bold red]")
                    break
        
        # Update mapping with API data
        added_count = 0
        for user in all_users:
            username = user.get("username")
            user_id = user.get("userid")
            
            if username and user_id and username not in username_to_id:
                username_to_id[username] = user_id
                added_count += 1
        
        if added_count > 0:
            console.print(f"[green]Added {added_count} new users from API to mapping[/green]\n")
        else:
            console.print("[yellow]No new users found to add to mapping[/yellow]\n")
        
        # Save updated mapping
        if added_count > 0:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(os.path.abspath(mapping_file)), exist_ok=True)
                
                with open(mapping_file, 'w') as f:
                    json.dump(username_to_id, f, indent=2)
                console.print(f"[green]Updated mapping saved to {mapping_file}[/green]")
            except Exception as e:
                console.print(f"[bold red]Error saving updated mapping: {str(e)}[/bold red]")
    
    return username_to_id

def add_age_information(tanks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Add age information to each tank in the list.
    
    Args:
        tanks: List of tank dictionaries.
        
    Returns:
        Tuple containing:
        - Updated list of tank dictionaries with age information
        - Dictionary with age status counts
    """
    from datetime import datetime
    current_date = datetime.now().date()
    
    # Initialize counters for age status
    status_counts = {
        "URGENT": 0,
        "WARNING": 0,
        "OK": 0,
        "UNKNOWN": 0
    }
    
    for tank in tanks:
        birth_date_str = tank.get('date_of_birth')
        
        # Initialize age fields
        tank['age_days'] = None
        tank['age_weeks'] = None
        tank['age_months'] = None
        tank['age_status'] = "UNKNOWN"
        
        if birth_date_str:
            try:
                # Handle different date formats
                if 'T' in birth_date_str:
                    # ISO format with time part
                    birth_date = datetime.fromisoformat(birth_date_str.split('T')[0]).date()
                elif '-' in birth_date_str:
                    # YYYY-MM-DD format
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                else:
                    # Try YYYYMMDD format as fallback
                    birth_date = datetime.strptime(birth_date_str, '%Y%m%d').date()
                
                # Calculate age in days
                age_days = (current_date - birth_date).days
                tank['age_days'] = age_days
                
                # Calculate age in weeks and months for convenience
                tank['age_weeks'] = age_days // 7
                tank['age_months'] = age_days // 30
                
                # Set age status
                if age_days > 365:
                    tank['age_status'] = "URGENT"
                    status_counts["URGENT"] += 1
                elif age_days > (365 - 50):  # Within 50 days of being one year old
                    tank['age_status'] = "WARNING"
                    status_counts["WARNING"] += 1
                else:
                    tank['age_status'] = "OK"
                    status_counts["OK"] += 1
                
            except (ValueError, TypeError):
                # Keep age as None for tanks with invalid date formats
                status_counts["UNKNOWN"] += 1
        else:
            status_counts["UNKNOWN"] += 1
    
    return tanks, status_counts

def get_tanks(base_url: str, client_token: str, user_token: str, 
              filters: Optional[Dict[str, Any]] = None,
              limit: int = 10000, verify_ssl: bool = False,
              console: Optional[Console] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Get tanks with flexible filtering.
    
    Args:
        base_url: Base URL of the PyRAT API.
        client_token: API-Client-Token.
        user_token: API-User-Token.
        filters: Dictionary of filter parameters.
        limit: Maximum number of results to return.
        verify_ssl: Whether to verify SSL certificates.
        console: Rich console object for output (optional)
        
    Returns:
        List of tank dictionaries if successful, None otherwise.
    """
    # Use provided console or create a new one if none provided
    if console is None:
        console = Console()
        
    if not base_url.endswith('/'):
        base_url += '/'
    
    api_base = urljoin(base_url, 'api/v3/')
    tanks_url = urljoin(api_base, 'tanks')
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    auth = (client_token, user_token)
    
    # Default keys to request - ensure we have all date fields that could be useful for age calculation
    default_keys = [
        'tank_id', 'tank_label', 'tank_position', 'location_rack_name', 
        'location_room_name', 'location_area_name', 'location_building_name',
        'responsible_id', 'responsible_fullname', 'owner_fullname',
        'status', 'strain_name_with_id', 'age_level', 'number_of_male',
        'number_of_female', 'number_of_unknown', 
        'date_of_birth', 'date_of_release', 'export_date', 'close_date'
    ]
    
    params = {
        'k': default_keys,
        's': ['location_rack_name:asc', 'tank_position:asc'],
        'l': limit,
        'o': 0
    }
    
    if filters:
        params.update(filters)
    
    try:
        with console.status("[bold cyan]Querying PyRAT API...[/bold cyan]"):
            response = requests.get(
                tanks_url, 
                auth=auth, 
                headers=headers, 
                params=params, 
                verify=verify_ssl
            )
            
            if response.status_code == 200:
                all_tanks = response.json()
                console.print(f"[green]API returned {len(all_tanks)} tanks[/green]")
                
                # Get total count from headers if available
                total_count = response.headers.get('X-Total-Count')
                if total_count and int(total_count) > len(all_tanks):
                    console.print(f"[yellow]Note: There are {total_count} total tanks, but only {len(all_tanks)} were returned due to the limit[/yellow]")
                
                return all_tanks
            else:
                console.print(f"[bold red]Error: {response.status_code} - {response.text}[/bold red]")
                return None
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        return None

def print_tank_summary(tanks: List[Dict[str, Any]], 
                      id_to_username: Optional[Dict[int, str]] = None,
                      age_status_counts: Optional[Dict[str, int]] = None,
                      console: Optional[Console] = None) -> None:
    """
    Print a summary of the tanks.
    
    Args:
        tanks: List of tank dictionaries.
        id_to_username: Optional mapping of user IDs to usernames.
        age_status_counts: Optional dictionary with age status counts.
        console: Rich console object for output (optional)
    """
    # Use provided console or throw an error if one isn't provided
    if console is None:
        raise ValueError("A Rich console object is required for output but none was provided.")

    # Count tanks by status
    status_counts = {}
    for tank in tanks:
        status = tank.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count by responsible person
    responsible_counts = {}
    for tank in tanks:
        resp_id = tank.get('responsible_id')
        resp_name = tank.get('responsible_fullname', 'Unknown')
        
        # If we have an ID mapping and the full name isn't in the tank data,
        # try to get it from the mapping
        if id_to_username and resp_id and (not resp_name or resp_name == "Unknown"):
            resp_name = id_to_username.get(resp_id, f"ID:{resp_id}")
            
        responsible_counts[resp_name] = responsible_counts.get(resp_name, 0) + 1
    
    # Count by age level
    age_counts = {}
    for tank in tanks:
        age_level = tank.get('age_level', 'unknown')
        age_counts[age_level] = age_counts.get(age_level, 0) + 1

    # Use the pre-calculated age fields
    ages = []
    age_data = []  # Will store (tank_id, tank_label, age_days) tuples for detailed reporting

    for tank in tanks:
        age_days = tank.get('age_days')
        tank_id = tank.get('tank_id', 'N/A')
        tank_label = tank.get('tank_label', 'N/A')
        
        if age_days is not None:
            ages.append(age_days)
            age_data.append((tank_id, tank_label, age_days))

    # Print summary
    console.print("\n[bold white on blue]===== Tank Summary =====[/bold white on blue]")
    console.print(f"[bold]Total tanks:[/bold] {len(tanks)}")
    
    console.print("\n[bold]Status distribution:[/bold]")
    for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
        console.print(f"  {status}: {count}")
        
    if len(responsible_counts) > 10:
        console.print(f"  ... and {len(responsible_counts) - 10} more")
    
    console.print("\n[bold]Age level distribution:[/bold]")
    for age, count in sorted(age_counts.items(), key=lambda x: x[1], reverse=True):
        console.print(f"  {age}: {count}")
    
    # Print age statistics
    if ages:
        
        # Count tanks by age ranges
        age_ranges = {
            "0-30 days": 0,
            "31-60 days": 0,
            "61-90 days": 0,
            "91-180 days": 0,
            "181-365 days": 0,
            "366+ days": 0,
        }
        
        for age in ages:
            if age <= 30:
                age_ranges["0-30 days"] += 1
            elif age <= 60:
                age_ranges["31-60 days"] += 1
            elif age <= 90:
                age_ranges["61-90 days"] += 1
            elif age <= 180:
                age_ranges["91-180 days"] += 1
            elif age <= 365:
                age_ranges["181-365 days"] += 1
            else:
                age_ranges["366+ days"] += 1
        
        console.print("\n[bold]Age statistics (days):[/bold]")

        console.print("\n[bold]Age distribution:[/bold]")
        for range_name, count in age_ranges.items():
            if count > 0:
                percent = (count / len(ages)) * 100
                console.print(f"  {range_name}: {count} ({percent:.1f}%)")
                
        # Print oldest tanks (top 5)
        if len(age_data) > 0:
            console.print("\n[bold]Oldest tanks:[/bold]")
            for tank_id, tank_label, age in sorted(age_data, key=lambda x: x[2], reverse=True)[:5]:
                console.print(f"  Tank {tank_id} ({tank_label}): {age} days")
                
        # Print youngest tanks (top 5)
        if len(age_data) > 0:
            console.print("\n[bold]Youngest tanks:[/bold]")
            for tank_id, tank_label, age in sorted(age_data, key=lambda x: x[2])[:5]:
                console.print(f"  Tank {tank_id} ({tank_label}): {age} days")
    else:
        console.print("\n[yellow]No age data available[/yellow]")

    # Print age status summary if provided
    if age_status_counts:
        console.print("\n[bold]Age Status Summary:[/bold]")
        console.print(f"[bold red]URGENT (>365 days):[/bold red] {age_status_counts.get('URGENT', 0)} tanks")
        console.print(f"[bold yellow]WARNING (315-365 days):[/bold yellow] {age_status_counts.get('WARNING', 0)} tanks")
        console.print(f"[bold green]OK (<315 days):[/bold green] {age_status_counts.get('OK', 0)} tanks")
        console.print(f"[bold]UNKNOWN:[/bold] {age_status_counts.get('UNKNOWN', 0)} tanks")
    
    console.print("\n[bold white on blue]=========================[/bold white on blue]")

def main() -> None:
    """Main function to run the script."""
    parser = argparse.ArgumentParser(
        description='Query PyRAT API for tanks with flexible filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Credential sources (checked in order):
  1. Command line arguments (--base-url, --client-token, --user-token)
  2. Environment variables (PYRAT_BASE_URL, PYRAT_CLIENT_TOKEN, PYRAT_USER_TOKEN)
  3. System keyring (run --setup-credentials to store)

Examples:
  # Set up credentials (one time)
  %(prog)s --setup-credentials

  # Query tanks
  %(prog)s --responsible "ahrensm"
  %(prog)s --responsible "ahrensm" --rack "R101.2" --status "open"
  %(prog)s --responsible "ahrensm" --output tanks.json
"""
    )

    # Credential management
    cred_group = parser.add_argument_group('credential management')
    cred_group.add_argument('--setup-credentials', action='store_true',
                           help='Interactively set up and store API credentials in system keyring')
    cred_group.add_argument('--clear-credentials', action='store_true',
                           help='Remove stored credentials from system keyring')

    # Optional credential overrides (no longer positional)
    cred_group.add_argument('--base-url', help='Base URL of the PyRAT instance')
    cred_group.add_argument('--client-token', help='API client token (format: ClientId-ClientKey)')
    cred_group.add_argument('--user-token', help='API-User-Token')

    # Tank filters
    filter_group = parser.add_argument_group('tank filters')
    filter_group.add_argument('--responsible', help='Responsible person identifier (full name or username)')
    filter_group.add_argument('--responsible-id', type=int, help='Responsible person ID (if known)')
    filter_group.add_argument('--rack', help='Rack name')
    filter_group.add_argument('--room', help='Room name')
    filter_group.add_argument('--area', help='Area name')
    filter_group.add_argument('--building', help='Building name')
    filter_group.add_argument('--status', help='Tank status (open, closed, exported, joined)')
    filter_group.add_argument('--strain', help='Strain name')
    filter_group.add_argument('--max-age-days', type=int, help='Maximum age of tanks in days')
    filter_group.add_argument('--min-age-days', type=int, help='Minimum age of tanks in days')

    # Output options
    output_group = parser.add_argument_group('output options')
    output_group.add_argument('--limit', type=int, default=10000, help='Maximum number of results to return')
    output_group.add_argument('--output', help='Output file for the results (JSON format)')
    output_group.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')

    # Other options
    parser.add_argument('--verify-ssl', action='store_true', help='Enable SSL certificate verification')
    parser.add_argument('--user-mapping', default='~/.pyrat_user_mapping.json',
                       help='JSON file containing username:userid mappings')
    parser.add_argument('--refresh-mapping', action='store_true', help='Refresh user mapping with data from API')

    args = parser.parse_args()

    # Create rich console
    console = Console()

    # Handle credential management commands
    if args.setup_credentials:
        success = setup_credentials(console)
        sys.exit(0 if success else 1)

    if args.clear_credentials:
        success = clear_credentials(console)
        sys.exit(0 if success else 1)

    # Get credentials from available sources
    credentials = get_credentials(
        console,
        cli_base_url=args.base_url,
        cli_client_token=args.client_token,
        cli_user_token=args.user_token
    )

    if not credentials:
        console.print("[bold red]Error: No credentials found![/bold red]")
        console.print("\nPlease provide credentials via one of these methods:")
        console.print("  1. Run [cyan]--setup-credentials[/cyan] to store in system keyring")
        console.print("  2. Set environment variables: PYRAT_BASE_URL, PYRAT_CLIENT_TOKEN, PYRAT_USER_TOKEN")
        console.print("  3. Pass [cyan]--base-url[/cyan], [cyan]--client-token[/cyan], [cyan]--user-token[/cyan] arguments")
        sys.exit(1)

    base_url = credentials["base_url"]
    client_token = credentials["client_token"]
    user_token = credentials["user_token"]

    # Configure request verification
    verify_ssl = args.verify_ssl
    if not verify_ssl:
        console.print("[yellow]\n⚠️   SSL certificate verification is disabled[/yellow]\n")
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    console.print(f"[bold blue]Connecting to:[/bold blue] {base_url}\n")
    
    # Initialize filters
    filters = {}
    
    # Expand the user mapping path if it begins with ~
    user_mapping_path = os.path.expanduser(args.user_mapping)
    
    # Load and potentially update user mapping
    user_mapping = load_and_update_user_mapping(
        user_mapping_path,
        base_url if args.refresh_mapping else None,
        client_token if args.refresh_mapping else None,
        user_token if args.refresh_mapping else None,
        args.refresh_mapping,
        verify_ssl,
        console
    )
    
    # Create reverse mapping for summary display (id -> username)
    id_to_username = {v: k for k, v in user_mapping.items()}
    
    # Look up the user ID based on the provided responsible identifier, mapping, or direct ID
    if args.responsible_id:
        filters['responsible_id'] = args.responsible_id
        console.print(f"[cyan]Filtering tanks with responsible_id:[/cyan] {args.responsible_id}")
    elif args.responsible:
        # First try to look up the user ID in the mapping
        user_id = None
        if args.responsible in user_mapping:
            user_id = user_mapping[args.responsible]
            console.print(f"[green]Found user ID {user_id} for {args.responsible} in mapping file[/green]\n")
        else:
            # Fall back to API lookup if not in mapping
            user_id = get_user_id(base_url, client_token, user_token, args.responsible, verify_ssl)
            
            # If found via API, add to mapping and save
            if user_id is not None and args.responsible:
                user_mapping[args.responsible] = user_id
                id_to_username[user_id] = args.responsible
                try:
                    with open(user_mapping_path, 'w') as f:
                        json.dump(user_mapping, f, indent=2)
                    console.print(f"[green]Updated mapping with new user: {args.responsible} -> {user_id}[/green]")
                except Exception as e:
                    console.print(f"[bold red]Error updating mapping file: {str(e)}[/bold red]")
        
        if user_id is not None:
            filters['responsible_id'] = user_id
            console.print(f"[cyan]Filtering tanks with responsible_id:[/cyan] {user_id}")
        else:
            console.print("[bold red]Error: Could not find a user matching the provided responsible identifier.[/bold red]")
            sys.exit(1)
    
    # Add other filters
    if args.rack:
        filters['location_rack_name'] = args.rack
        console.print(f"[cyan]Filtering by rack:[/cyan] {args.rack}")
    if args.room:
        filters['location_room_name'] = args.room
        console.print(f"[cyan]Filtering by room:[/cyan] {args.room}")
    if args.area:
        filters['location_area_name'] = args.area
        console.print(f"[cyan]Filtering by area:[/cyan] {args.area}")
    if args.building:
        filters['location_building_name'] = args.building
        console.print(f"[cyan]Filtering by building:[/cyan] {args.building}")
    if args.status:
        filters['status'] = args.status
        console.print(f"[cyan]Filtering by status:[/cyan] {args.status}")
    if args.strain:
        filters['strain_name_with_id'] = args.strain
        console.print(f"[cyan]Filtering by strain:[/cyan] {args.strain}")
        
    # Add age filters if specified
    from datetime import datetime, timedelta
    
    if args.max_age_days is not None:
        # Calculate the cutoff date for maximum age
        cutoff_date = (datetime.now() - timedelta(days=args.max_age_days)).strftime('%Y-%m-%d')
        filters['birth_date_from'] = cutoff_date
        console.print(f"[cyan]Filtering tanks born after:[/cyan] {cutoff_date} [dim](max age {args.max_age_days} days)[/dim]")
        
    if args.min_age_days is not None:
        # Calculate the cutoff date for minimum age
        cutoff_date = (datetime.now() - timedelta(days=args.min_age_days)).strftime('%Y-%m-%d')
        filters['birth_date_to'] = cutoff_date
        console.print(f"[cyan]Filtering tanks born before:[/cyan] {cutoff_date} [dim](min age {args.min_age_days} days)[/dim]")
    
    # Get the tanks
    console.print(f"[bold]Querying tanks from PyRAT API...[/bold]")
    all_tanks = get_tanks(
        base_url,
        client_token,
        user_token,
        filters,
        args.limit,
        verify_ssl=verify_ssl,
        console=console
    )
    
    if all_tanks:
        # Add age information to each tank
        console.print("[bold]Processing tank data...[/bold]")
        all_tanks, age_status_counts = add_age_information(all_tanks)
        
        # Print summary statistics
        print_tank_summary(
            all_tanks,
            id_to_username,
            age_status_counts,
            console
            )

        # Print detailed output if requested
        if args.verbose:
            console.print("\n[bold white on blue]Tanks found:[/bold white on blue]")
            
            for i, tank in enumerate(all_tanks, 1):
                tank_id = tank.get('tank_id', 'N/A')
                tank_label = tank.get('tank_label', 'N/A')
                location = f"{tank.get('location_room_name', '')} - {tank.get('location_rack_name', '')}"
                position = tank.get('tank_position', 'N/A')
                status = tank.get('status', 'N/A')
                strain = tank.get('strain_name_with_id', 'N/A')
                
                # Get responsible name - first try fullname from API, then from mapping
                resp_id = tank.get('responsible_id')
                responsible = tank.get('responsible_fullname', 'N/A')
                if responsible == 'N/A' and resp_id in id_to_username:
                    responsible = f"{id_to_username[resp_id]} (ID: {resp_id})"
                
                # Fish counts
                males = tank.get('number_of_male', 0)
                females = tank.get('number_of_female', 0)
                unknown = tank.get('number_of_unknown', 0)
                total = males + females + unknown
                
                # Age information
                age_days = tank.get('age_days')
                age_status = tank.get('age_status', 'UNKNOWN')
                
                # Format tank header with number
                console.print(f"[bold]{i}. ID: {tank_id}, Label: {tank_label}[/bold]")
                console.print(f"   Location: {location}, Position: {position}")
                console.print(f"   Status: {status}, Strain: {strain}")
                console.print(f"   Fish: {total} ({males}M/{females}F/{unknown}U)")
                console.print(f"   Responsible: {responsible}")
                
                # Display age with appropriate styling
                if age_days is not None:
                    if age_status == "URGENT":
                        console.print(f"   Age: [bold red]URGENT: {age_days} days[/bold red]")
                    elif age_status == "WARNING":
                        console.print(f"   Age: [bold yellow]WARNING: {age_days} days[/bold yellow]")
                    elif age_status == "OK":
                        console.print(f"   Age: [bold green]OK: {age_days} days[/bold green]")
                    else:
                        console.print(f"   Age: {age_days} days")
                
                console.print()
        else:
            console.print(f"\n[bold green]Found {len(all_tanks)} tanks.[/bold green] Use --verbose for detailed listing.")
        
        # Save results if requested
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(all_tanks, f, indent=2)
                console.print(f"\n[bold green]Complete results saved to {args.output}[/bold green]")
            except Exception as e:
                console.print(f"[bold red]Error saving results: {str(e)}[/bold red]")
        
        sys.exit(0)
    else:
        console.print("[bold red]No tanks found or there was an error with the request.[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
