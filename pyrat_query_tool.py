#!/usr/bin/env python3
"""
PyRAT API Tank Query Tool

Retrieves tanks from the PyRAT API with flexible filtering options.
Can filter tanks by responsible user (looking up the ID automatically),
location, status, and other parameters.

Usage examples:
  # Get all tanks for a specific user
  python get_pyrat_tanks.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --responsible "ahrensm"
  
  # Get tanks in a specific rack for a user
  python get_pyrat_tanks.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --responsible "ahrensm" --rack "R101.2"
  
  # Get tanks with specific status
  python get_pyrat_tanks.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --status "open"
  
  # Save output to a JSON file
  python get_pyrat_tanks.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --responsible "ahrensm" --output tanks.json
"""

import os
import sys
import json
import argparse
import requests
from urllib.parse import urljoin
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

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

def get_user_cache(base_url: str, client_token: str, user_token: str, 
                   verify_ssl: bool = False) -> Dict[int, str]:
    """
    Retrieve all users and build a cache mapping of user IDs to usernames.
    
    Args:
        base_url: Base URL of the PyRAT instance.
        client_token: API-Client-Token.
        user_token: API-User-Token.
        verify_ssl: Whether to verify SSL certificates.
    
    Returns:
        Dictionary mapping user IDs to usernames.
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
    
    cache_file = Path(os.path.expanduser("~/.pyrat_user_cache.json"))
    cache_max_age_days = 7  # Cache is valid for 7 days
    
    # Check if we have a recent cache file
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                # Check cache age
                cache_timestamp = cache_data.get("timestamp", 0)
                current_timestamp = datetime.now().timestamp()
                age_in_seconds = current_timestamp - cache_timestamp
                
                if age_in_seconds < (cache_max_age_days * 24 * 60 * 60):
                    print(f"Using cached user data ({len(cache_data['users'])} users)")
                    return {int(k): v for k, v in cache_data["users"].items()}
        except Exception as e:
            print(f"Error reading cache: {str(e)}")
    
    # Cache doesn't exist, is expired, or had an error - fetch fresh data
    all_users = []
    offset = 0
    limit = 100
    
    print("Fetching user data from PyRAT API...")
    while True:
        params = {
            'l': limit,
            'o': offset
        }
        try:
            response = requests.get(users_url, auth=auth, headers=headers, params=params, verify=verify_ssl)
            if response.status_code != 200:
                print(f"Error fetching users: {response.status_code} - {response.text}")
                break
                
            users = response.json()
            if not users:
                break
                
            all_users.extend(users)
            if len(users) < limit:
                break
                
            offset += limit
        except Exception as e:
            print(f"Error fetching users: {str(e)}")
            break
    
    # Build the user mapping
    user_mapping = {
        user.get("userid"): user.get("username") 
        for user in all_users 
        if user.get("userid") is not None
    }
    
    # Save to cache
    try:
        cache_data = {
            "timestamp": datetime.now().timestamp(),
            "users": user_mapping
        }
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f)
        print(f"Cached {len(user_mapping)} users to {cache_file}")
    except Exception as e:
        print(f"Error saving user cache: {str(e)}")
    
    return user_mapping

def get_tanks(base_url: str, client_token: str, user_token: str, 
              filters: Optional[Dict[str, Any]] = None,
              limit: int = 10000, verify_ssl: bool = False) -> Optional[List[Dict[str, Any]]]:
    """
    Get tanks with flexible filtering.
    
    Args:
        base_url: Base URL of the PyRAT API.
        client_token: API-Client-Token.
        user_token: API-User-Token.
        filters: Dictionary of filter parameters.
        limit: Maximum number of results to return.
        verify_ssl: Whether to verify SSL certificates.
        
    Returns:
        List of tank dictionaries if successful, None otherwise.
    """
    if not base_url.endswith('/'):
        base_url += '/'
    
    api_base = urljoin(base_url, 'api/v3/')
    tanks_url = urljoin(api_base, 'tanks')
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    auth = (client_token, user_token)
    
    # Default keys to request
    default_keys = [
        'tank_id', 'tank_label', 'tank_position', 'location_rack_name', 
        'location_room_name', 'location_area_name', 'location_building_name',
        'responsible_id', 'responsible_fullname', 'owner_fullname',
        'status', 'strain_name_with_id', 'age_level', 'number_of_male',
        'number_of_female', 'number_of_unknown', 'date_of_birth'
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
        print(f"Querying tanks with parameters: {params}")
        response = requests.get(
            tanks_url, 
            auth=auth, 
            headers=headers, 
            params=params, 
            verify=verify_ssl
        )
        
        if response.status_code == 200:
            all_tanks = response.json()
            print(f"API returned {len(all_tanks)} tanks")
            
            # Get total count from headers if available
            total_count = response.headers.get('X-Total-Count')
            if total_count and int(total_count) > len(all_tanks):
                print(f"Note: There are {total_count} total tanks, but only {len(all_tanks)} were returned due to the limit")
            
            return all_tanks
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def print_tank_summary(tanks: List[Dict[str, Any]], user_cache: Optional[Dict[int, str]] = None) -> None:
    """
    Print a summary of the tanks.
    
    Args:
        tanks: List of tank dictionaries.
        user_cache: Optional mapping of user IDs to usernames.
    """
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
        
        # If we have a user cache and the full name isn't in the tank data,
        # try to get it from the cache
        if user_cache and resp_id and (not resp_name or resp_name == "Unknown"):
            resp_name = user_cache.get(resp_id, f"ID:{resp_id}")
            
        responsible_counts[resp_name] = responsible_counts.get(resp_name, 0) + 1
    
    # Count by age level
    age_counts = {}
    for tank in tanks:
        age_level = tank.get('age_level', 'unknown')
        age_counts[age_level] = age_counts.get(age_level, 0) + 1
    
    # Print summary
    print("\n===== Tank Summary =====")
    print(f"Total tanks: {len(tanks)}")
    
    print("\nStatus distribution:")
    for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {status}: {count}")
    
    print("\nResponsible person distribution:")
    for resp, count in sorted(responsible_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {resp}: {count}")
        
    if len(responsible_counts) > 10:
        print(f"  ... and {len(responsible_counts) - 10} more")
    
    print("\nAge level distribution:")
    for age, count in sorted(age_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {age}: {count}")
    
    print("\n=========================")

def main() -> None:
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Query PyRAT API for tanks with flexible filtering')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance')
    parser.add_argument('client_token', help='API-Client-Token (formatted as API-Client-Id-API-Client-Key)')
    parser.add_argument('user_token', help='API-User-Token')
    parser.add_argument('--responsible', help='Responsible person identifier (full name or username)')
    parser.add_argument('--responsible-id', type=int, help='Responsible person ID (if known)')
    parser.add_argument('--rack', help='Rack name')
    parser.add_argument('--room', help='Room name')
    parser.add_argument('--area', help='Area name')
    parser.add_argument('--building', help='Building name')
    parser.add_argument('--status', help='Tank status (open, closed, exported, joined)')
    parser.add_argument('--strain', help='Strain name')
    parser.add_argument('--max-age-days', type=int, help='Maximum age of tanks in days')
    parser.add_argument('--min-age-days', type=int, help='Minimum age of tanks in days')
    parser.add_argument('--limit', type=int, default=10000, help='Maximum number of results to return')
    parser.add_argument('--verify-ssl', action='store_true', help='Enable SSL certificate verification')
    parser.add_argument('--output', help='Output file for the results (JSON format)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--cache-users', action='store_true', help='Cache user data for faster lookups')
    
    args = parser.parse_args()
    
    # Configure request verification
    verify_ssl = args.verify_ssl
    if not verify_ssl:
        print("ℹ️ SSL certificate verification is disabled")
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print(f"Connecting to: {args.base_url}")
    
    # Initialize filters
    filters = {}
    
    # Cache users if requested - will be used for summary statistics
    user_cache = None
    if args.cache_users:
        user_cache = get_user_cache(args.base_url, args.client_token, args.user_token, verify_ssl)
    
    # Look up the user ID based on the provided responsible identifier or use direct ID
    if args.responsible_id:
        filters['responsible_id'] = args.responsible_id
        print(f"Filtering tanks with responsible_id: {args.responsible_id}")
    elif args.responsible:
        user_id = get_user_id(args.base_url, args.client_token, args.user_token, args.responsible, verify_ssl)
        if user_id is not None:
            filters['responsible_id'] = user_id
            print(f"Filtering tanks with responsible_id: {user_id}")
        else:
            print("Error: Could not find a user matching the provided responsible identifier.")
            sys.exit(1)
    
    # Add other filters
    if args.rack:
        filters['location_rack_name'] = args.rack
    if args.room:
        filters['location_room_name'] = args.room
    if args.area:
        filters['location_area_name'] = args.area
    if args.building:
        filters['location_building_name'] = args.building
    if args.status:
        filters['status'] = args.status
    if args.strain:
        filters['strain_name_with_id'] = args.strain
        
    # Add age filters if specified
    from datetime import datetime, timedelta
    
    if args.max_age_days is not None:
        # Calculate the cutoff date for maximum age
        cutoff_date = (datetime.now() - timedelta(days=args.max_age_days)).strftime('%Y-%m-%d')
        filters['birth_date_from'] = cutoff_date
        print(f"Filtering tanks born after: {cutoff_date} (max age {args.max_age_days} days)")
        
    if args.min_age_days is not None:
        # Calculate the cutoff date for minimum age
        cutoff_date = (datetime.now() - timedelta(days=args.min_age_days)).strftime('%Y-%m-%d')
        filters['birth_date_to'] = cutoff_date
        print(f"Filtering tanks born before: {cutoff_date} (min age {args.min_age_days} days)")
    
    # Get the tanks
    all_tanks = get_tanks(
        args.base_url, 
        args.client_token, 
        args.user_token, 
        filters,
        args.limit,
        verify_ssl=verify_ssl
    )
    
    if all_tanks:
        # Print summary statistics
        print_tank_summary(all_tanks, user_cache)
        
        # Print detailed output if requested
        if args.verbose:
            print("\nTanks found:")
            for i, tank in enumerate(all_tanks, 1):
                tank_id = tank.get('tank_id', 'N/A')
                tank_label = tank.get('tank_label', 'N/A')
                location = f"{tank.get('location_room_name', '')} - {tank.get('location_rack_name', '')}"
                position = tank.get('tank_position', 'N/A')
                status = tank.get('status', 'N/A')
                strain = tank.get('strain_name_with_id', 'N/A')
                responsible = tank.get('responsible_fullname', 'N/A')
                
                # Fish counts
                males = tank.get('number_of_male', 0)
                females = tank.get('number_of_female', 0)
                unknown = tank.get('number_of_unknown', 0)
                total = males + females + unknown
                
                print(f"{i}. ID: {tank_id}, Label: {tank_label}")
                print(f"   Location: {location}, Position: {position}")
                print(f"   Status: {status}, Strain: {strain}")
                print(f"   Fish: {total} ({males}M/{females}F/{unknown}U)")
                print(f"   Responsible: {responsible}")
                print()
        else:
            print(f"\nFound {len(all_tanks)} tanks. Use --verbose for detailed listing.")
        
        # Save results if requested
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(all_tanks, f, indent=2)
                print(f"\nComplete results saved to {args.output}")
            except Exception as e:
                print(f"Error saving results: {str(e)}")
        
        sys.exit(0)
    else:
        print("No tanks found or there was an error with the request.")
        sys.exit(1)

if __name__ == "__main__":
    main()