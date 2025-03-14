#!/usr/bin/env python3
"""
PyRAT Token Format Test

Tests different variations of client token format.
"""

import requests
import argparse
import json
from urllib.parse import urljoin
import sys

def test_token_format(base_url, client_id, client_token, user_token, verify_ssl=False):
    """
    Test different client token formats.
    
    Args:
        base_url: Base URL of the PyRAT instance
        client_id: Client ID number
        client_token: Client token or key part
        user_token: API-User-Token
        verify_ssl: Whether to verify SSL certificates
    """
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url += '/'
    
    # Construct API base URL 
    api_base = urljoin(base_url, 'api/v3/')
    
    # Disable SSL verification warning if requested
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Endpoint to test
    endpoint = 'credentials'
    url = urljoin(api_base, endpoint)
    
    # Different token formats to try
    token_formats = [
        # 1. Just client name/token
        client_token,
        # 2. Client ID + client token
        f"{client_id}-{client_token}",
        # 3. Client ID only
        f"{client_id}",
        # 4. Common prefix formats
        f"API-Client-{client_id}-{client_token}",
        f"api-client-{client_id}-{client_token}",
        # 5. Client ID with hyphens
        f"{client_id}-{client_token.replace('-', '')}",
    ]
    
    # Headers
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    print(f"Testing different token formats against: {url}")
    
    success = False
    correct_format = None
    
    for token_format in token_formats:
        print(f"\nTrying client token format: '{token_format}'")
        
        auth = (token_format, user_token)
        
        try:
            response = requests.get(url, auth=auth, headers=headers, verify=verify_ssl, timeout=10)
            status = response.status_code
            
            print(f"Status: {status}")
            
            if status == 200:
                try:
                    result = response.json()
                    print(f"Response: {json.dumps(result, indent=2)}")
                    
                    # Check if credentials are valid
                    if result.get("client_valid", False) and result.get("user_valid", False):
                        print(f"✅ SUCCESS! This token format works correctly.")
                        success = True
                        correct_format = token_format
                    else:
                        print(f"⚠️ Got 200 response but tokens not valid according to response.")
                except:
                    print(f"Response (not JSON): {response.text[:100]}...")
            else:
                print(f"Failed with status code: {status}")
                print(f"Response: {response.text}")
        
        except Exception as e:
            print(f"Error: {str(e)}")
    
    if success:
        print(f"\n✅ Success! The correct client token format is: '{correct_format}'")
    else:
        print("\n❌ None of the tested formats worked correctly.")
        print("Please check with PyRAT documentation or administrator for the correct token format.")
    
    return success, correct_format

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Test PyRAT API token formats')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance')
    parser.add_argument('client_id', help='Client ID number (usually a number like "1")')
    parser.add_argument('client_token', help='Client token or key part')
    parser.add_argument('user_token', help='Complete API-User-Token')
    parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    
    args = parser.parse_args()
    
    # Print warning for insecure connections
    if args.no_verify_ssl:
        print("⚠️ WARNING: SSL certificate verification disabled. This is insecure!")
    
    success, _ = test_token_format(
        args.base_url, 
        args.client_id,
        args.client_token, 
        args.user_token, 
        verify_ssl=not args.no_verify_ssl
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()