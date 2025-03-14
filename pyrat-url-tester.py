#!/usr/bin/env python3
"""
PyRAT API URL Pattern Tester

This script tests different URL patterns to find the correct one for the PyRAT API.
"""

import requests
import argparse
from urllib.parse import urljoin

def test_url_patterns(base_url, client_token=None, user_token=None, verify_ssl=False):
    """
    Test various URL patterns to find the correct one for the PyRAT API.
    
    Args:
        base_url: Base URL of the server
        client_token: API-Client-Token (optional)
        user_token: API-User-Token (optional)
        verify_ssl: Whether to verify SSL certificates
    """
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url += '/'
    
    # Disable SSL verification warning if needed
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Set up auth if tokens are provided
    auth = (client_token, user_token) if client_token and user_token else None
    
    # Different URL patterns to try
    patterns = [
        'api/v3/version',              # Standard API path
        'pyrat/api/v3/version',        # PyRAT under /pyrat
        'api/v3/swagger-ui',           # Try swagger UI path
        'pyrat/api/v3/swagger-ui',     # PyRAT under /pyrat with swagger
        'api/v3/docs',                 # Documentation path
        'pyrat/api/v3/docs',           # PyRAT under /pyrat with docs
        'swagger-ui',                  # Direct swagger UI
        'docs',                        # Direct docs
        'api/v2/version',              # Try v2 API
        'pyrat/api/v2/version',        # PyRAT under /pyrat with v2 API
    ]
    
    print(f"Testing various URL patterns from base: {base_url}")
    
    for pattern in patterns:
        url = urljoin(base_url, pattern)
        
        print(f"\nTesting URL: {url}")
        try:
            # Try without auth first
            response = requests.get(url, verify=verify_ssl, timeout=5)
            status = response.status_code
            content_type = response.headers.get('Content-Type', 'unknown')
            
            print(f"  Status: {status}")
            print(f"  Content-Type: {content_type}")
            
            if status == 200:
                print(f"  ✅ Success! This URL pattern works.")
                if 'application/json' in content_type:
                    print(f"  Response (JSON): {response.json()}")
                else:
                    # For HTML or other content, just show first 100 chars
                    content_preview = response.text[:100].replace('\n', ' ')
                    print(f"  Response (preview): {content_preview}...")
            elif status == 401:
                print(f"  ⚠️ Authentication required.")
                
                # If we have auth credentials, try with them
                if auth:
                    print(f"  Retrying with authentication...")
                    auth_response = requests.get(url, auth=auth, verify=verify_ssl, timeout=5)
                    auth_status = auth_response.status_code
                    
                    print(f"  Auth Status: {auth_status}")
                    if auth_status == 200:
                        print(f"  ✅ Success with authentication!")
                        content_type = auth_response.headers.get('Content-Type', 'unknown')
                        if 'application/json' in content_type:
                            print(f"  Response (JSON): {auth_response.json()}")
                        else:
                            # For HTML or other content, just show first 100 chars
                            content_preview = auth_response.text[:100].replace('\n', ' ')
                            print(f"  Response (preview): {content_preview}...")
            else:
                print(f"  ❌ This URL pattern returned status {status}.")
                
        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error: {str(e)}")
    
    # Try a direct request to the base URL as well
    print(f"\nTesting base URL directly: {base_url}")
    try:
        response = requests.get(base_url, verify=verify_ssl, timeout=5)
        status = response.status_code
        content_type = response.headers.get('Content-Type', 'unknown')
        
        print(f"  Status: {status}")
        print(f"  Content-Type: {content_type}")
        
        if status == 200:
            if 'text/html' in content_type:
                # For HTML, look for clues in the content
                if 'pyrat' in response.text.lower():
                    print(f"  ✅ Found PyRAT-related HTML content at the base URL")
                else:
                    print(f"  ⚠️ Found HTML content but doesn't seem PyRAT-related")
            
            content_preview = response.text[:100].replace('\n', ' ')
            print(f"  Response (preview): {content_preview}...")
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error accessing base URL: {str(e)}")

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Test PyRAT API URL patterns')
    parser.add_argument('base_url', help='Base URL of the server (e.g., https://example.com/)')
    parser.add_argument('--client-token', help='API-Client-Token (optional)', default=None)
    parser.add_argument('--user-token', help='API-User-Token (optional)', default=None)
    parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    
    args = parser.parse_args()
    
    # Print warning for insecure connections
    if args.no_verify_ssl:
        print("⚠️ WARNING: SSL certificate verification disabled. This is insecure!")
    
    test_url_patterns(
        args.base_url, 
        client_token=args.client_token, 
        user_token=args.user_token, 
        verify_ssl=not args.no_verify_ssl
    )

if __name__ == "__main__":
    main()