#!/usr/bin/env python3
"""
Gather All User IDs and Usernames from the PyRAT API

This script retrieves all users via the /users endpoint (using pagination)
and outputs a mapping from user IDs to usernames.
"""

import requests
import argparse
import json
from urllib.parse import urljoin
import sys

def get_users(base_url, client_token, user_token, limit=100, verify_ssl=False):
    """
    Retrieve all users from the PyRAT API with pagination.
    
    Args:
        base_url (str): Base URL of the PyRAT instance.
        client_token (str): API-Client-Token.
        user_token (str): API-User-Token.
        limit (int): Maximum number of users to retrieve per request.
        verify_ssl (bool): Whether to verify SSL certificates.
    
    Returns:
        list: A list of user dictionaries.
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
    
    all_users = []
    offset = 0
    while True:
        params = {
            'l': limit,
            'o': offset
        }
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
    return all_users

def main():
    parser = argparse.ArgumentParser(description='Gather all user IDs and usernames from the PyRAT API.')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance')
    parser.add_argument('client_token', help='API-Client-Token (formatted as API-Client-Id-API-Client-Key)')
    parser.add_argument('user_token', help='API-User-Token')
    parser.add_argument('--verify-ssl', action='store_true', help='Enable SSL certificate verification')
    parser.add_argument('--output', help='Output file to save the mapping (JSON format)')
    
    args = parser.parse_args()
    verify_ssl = args.verify_ssl
    
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print(f"Connecting to: {args.base_url}")
    users = get_users(args.base_url, args.client_token, args.user_token, limit=100, verify_ssl=verify_ssl)
    
    if not users:
        print("No users found or there was an error with the request.")
        sys.exit(1)
    
    # Build a mapping of user_id to username.
    user_mapping = { user.get("userid"): user.get("username") for user in users if user.get("userid") is not None }
    
    print(f"Found {len(user_mapping)} user IDs with usernames:")
    for uid, username in user_mapping.items():
        print(f"{uid}: {username}")
    
    if args.output:
        try:
            with open(args.output, 'w') as f:
                json.dump(user_mapping, f, indent=2)
            print(f"User mapping saved to {args.output}")
        except Exception as e:
            print(f"Error saving output: {str(e)}")
    
    sys.exit(0)

if __name__ == "__main__":
    main()
