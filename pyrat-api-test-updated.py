#!/usr/bin/env python3
"""
PyRAT API Authentication Test

Tests authentication with the PyRAT API following the exact documentation pattern.
"""

import requests
import argparse
import json
from urllib.parse import urljoin
import sys

def test_pyrat_auth(base_url, client_token, user_token, verify_ssl=False):
    """
    Test authentication with the PyRAT API.
    
    Args:
        base_url: Base URL of the PyRAT instance
        client_token: API-Client-Token (formatted as API-Client-Id-API-Client-Key)
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
    
    # Headers
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    # 1. First test /version endpoint which doesn't require authentication
    version_url = urljoin(api_base, 'version')
    print(f"\nTesting version endpoint: {version_url}")
    
    try:
        response = requests.get(version_url, headers=headers, verify=verify_ssl)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ Version endpoint accessible")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Failed to access version endpoint: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error accessing version endpoint: {str(e)}")
        return False
    
    # 2. Test /credentials endpoint with authentication
    credentials_url = urljoin(api_base, 'credentials')
    print(f"\nTesting credentials endpoint: {credentials_url}")
    
    # Set up authentication according to documentation
    # API-Client-Token as username, API-User-Token as password
    auth = (client_token, user_token)
    
    try:
        response = requests.get(credentials_url, auth=auth, headers=headers, verify=verify_ssl)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            
            if result.get("client_valid", False) and result.get("user_valid", False):
                print(f"✅ Authentication successful! Both client and user tokens are valid.")
                return True
            else:
                issues = []
                if not result.get("client_valid", False):
                    issues.append("Client token is not valid")
                if not result.get("client_enabled", False):
                    issues.append("Client is not enabled")
                if not result.get("user_valid", False):
                    issues.append("User token is not valid")
                if not result.get("user_enabled", False):
                    issues.append("User is not enabled")
                    
                print(f"⚠️ Authentication issues detected: {', '.join(issues)}")
                return False
        else:
            print(f"❌ Failed to authenticate: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error during authentication: {str(e)}")
        return False

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Test PyRAT API authentication')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance')
    parser.add_argument('client_token', help='API-Client-Token (formatted as API-Client-Id-API-Client-Key)')
    parser.add_argument('user_token', help='API-User-Token')
    parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    
    args = parser.parse_args()
    
    # Print warning for insecure connections
    if args.no_verify_ssl:
        print("⚠️ WARNING: SSL certificate verification disabled. This is insecure!")
    
    print("Testing PyRAT API authentication...")
    print(f"Base URL: {args.base_url}")
    print(f"Client token: {args.client_token}")
    print(f"User token: {args.user_token}")
    
    success = test_pyrat_auth(
        args.base_url, 
        args.client_token, 
        args.user_token, 
        verify_ssl=not args.no_verify_ssl
    )
    
    if success:
        print("\n✅ Authentication test passed successfully!")
        print("You can now integrate with the PyRAT API.")
    else:
        print("\n❌ Authentication test failed.")
        print("Please check:")
        print("  1. Your client token format (should be API-Client-Id-API-Client-Key)")
        print("  2. Your user token format")
        print("  3. That your client and user are enabled in the PyRAT system")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
