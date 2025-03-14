#!/usr/bin/env python3
"""
PyRAT API Tank Query

Retrieves tanks from the PyRAT API with flexible filtering options.
It looks up a user by a supplied identifier (full name or username) and then
filters tanks by the found user's ID using the `responsible_id` parameter.
"""

import requests
import argparse
import json
from urllib.parse import urljoin
import sys

def get_user_id(base_url, client_token, user_token, identifier, verify_ssl=False):
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
    api_base = urljoin(base_url, 'api/v3/')
    users_url = urljoin(api_base, 'users')
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    auth = (client_token, user_token)
    # Use wildcards for partial matching if not provided.
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
                    return user.get("userid")
            print(f"Warning: No user found with identifier matching: {identifier}")
            return None
        else:
            print(f"Error fetching user list: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching user: {str(e)}")
        return None

def get_tanks(base_url, client_token, user_token, filters=None, limit=10000, verify_ssl=False):
    """
    Get tanks with flexible filtering.
    
    Args:
        base_url: Base URL of the PyRAT API.
        client_token: API-Client-Token.
        user_token: API-User-Token.
        filters: Dictionary of filter parameters.
        limit: Maximum number of results to return.
        verify_ssl: Whether to verify SSL certificates.
    """
    if not base_url.endswith('/'):
        base_url += '/'
    
    api_base = urljoin(base_url, 'api/v3/')
    
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    auth = (client_token, user_token)
    
    # The tanks endpoint
    tanks_url = urljoin(api_base, 'tanks')
    
    params = {
        'k': ['tank_id', 'tank_label', 'tank_position', 'location_rack_name', 
              'location_room_name', 'responsible_fullname', 'status'],
        's': ['location_rack_name:asc', 'tank_position:asc'],
        'l': limit,
        'o': 0
    }
    
    if filters:
        params.update(filters)
    
    try:
        print(f"Querying tanks with filters: {filters}")
        response = requests.get(
            tanks_url, 
            auth=auth, 
            headers=headers, 
            params=params, 
            verify=verify_ssl
        )
        
        print(f"Request URL: {response.url}")
        
        if response.status_code == 200:
            all_tanks = response.json()
            print(f"API returned {len(all_tanks)} tanks")
            return all_tanks
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Query PyRAT API for tanks with flexible filtering')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance')
    parser.add_argument('client_token', help='API-Client-Token (formatted as API-Client-Id-API-Client-Key)')
    parser.add_argument('user_token', help='API-User-Token')
    parser.add_argument('--responsible', help='Responsible person identifier (full name or username, e.g., "ahrensm")')
    parser.add_argument('--rack', help='Rack name')
    parser.add_argument('--room', help='Room name')
    parser.add_argument('--status', help='Tank status (open, closed, exported, joined)')
    parser.add_argument('--limit', type=int, default=10000, help='Maximum number of results to return')
    parser.add_argument('--verify-ssl', action='store_true', help='Enable SSL certificate verification')
    parser.add_argument('--output', help='Output file for the results (JSON format)')
    
    args = parser.parse_args()
    verify_ssl = args.verify_ssl
    if not verify_ssl:
        print("ℹ️ SSL certificate verification is disabled")
    
    print(f"Connecting to: {args.base_url}")
    
    filters = {}
    
    # Look up the user ID based on the provided responsible identifier.
    if args.responsible:
        user_id = get_user_id(args.base_url, args.client_token, args.user_token, args.responsible, verify_ssl)
        if user_id is not None:
            filters['responsible_id'] = user_id
            print(f"Filtering tanks with responsible_id: {user_id}")
        else:
            print("Error: Could not find a user matching the provided responsible identifier.")
            sys.exit(1)
    
    if args.rack:
        filters['location_rack_name'] = args.rack
    if args.room:
        filters['location_room_name'] = args.room
    if args.status:
        filters['status'] = args.status
    
    all_tanks = get_tanks(
        args.base_url, 
        args.client_token, 
        args.user_token, 
        filters,
        args.limit,
        verify_ssl=verify_ssl
    )
    
    if all_tanks:
        print("\nTanks found:")
        for i, tank in enumerate(all_tanks, 1):
            tank_id = tank.get('tank_id', 'N/A')
            tank_label = tank.get('tank_label', 'N/A')
            location = f"{tank.get('location_room_name', '')} - {tank.get('location_rack_name', '')}"
            position = tank.get('tank_position', 'N/A')
            status = tank.get('status', 'N/A')
            responsible = tank.get('responsible_fullname', 'N/A')
            print(f"{i}. ID: {tank_id}, Label: {tank_label}, Location: {location}, Position: {position}, Status: {status}, Responsible: {responsible}")
        
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
