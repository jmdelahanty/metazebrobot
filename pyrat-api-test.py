#!/usr/bin/env python3
"""
PyRAT API v3 Extended Test Script

This script tests connectivity to a PyRAT API v3 instance and demonstrates using listing endpoints.
"""

import requests
import sys
import json
import argparse
from urllib.parse import urljoin

class PyRatApiClient:
    """Client for interacting with the PyRAT API v3."""
    
    def __init__(self, base_url, client_token, user_token, verify_ssl=True):
        """
        Initialize the PyRAT API client.
        
        Args:
            base_url: Base URL of the PyRAT instance (e.g., 'https://example.com/pyrat/')
            client_token: API-Client-Token (format: 'API-Client-Id-API-Client-Key')
            user_token: API-User-Token (format: 'API-User-Id-API-User-Key')
            verify_ssl: Whether to verify SSL certificates (set to False to disable verification)
        """
        # Ensure base_url ends with a slash
        if not base_url.endswith('/'):
            base_url += '/'
        
        self.base_url = base_url
        self.api_base = urljoin(base_url, 'api/v3/')
        self.auth = (client_token, user_token)
        self.verify_ssl = verify_ssl
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def get_version(self):
        """Get PyRAT version information."""
        url = urljoin(self.api_base, 'version')
        response = requests.get(url, headers=self.headers, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()
    
    def get_credentials(self):
        """Get information about the current API credentials."""
        url = urljoin(self.api_base, 'credentials')
        response = requests.get(url, auth=self.auth, headers=self.headers, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()
    
    def get_permissions(self):
        """Get available permissions information."""
        url = urljoin(self.api_base, 'permissions.json')
        response = requests.get(url, auth=self.auth, headers=self.headers, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()
    
    def get_openapi_spec(self):
        """Get the OpenAPI specification."""
        url = urljoin(self.api_base, 'openapi.json')
        response = requests.get(url, auth=self.auth, headers=self.headers, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()
    
    def get_list(self, endpoint, keys=None, sort=None, limit=None, offset=None, **filters):
        """
        Get a list from a listing endpoint.
        
        Args:
            endpoint: API endpoint path (e.g., 'animals')
            keys: List of keys to include in the response
            sort: List of sort expressions (e.g., ['owner_full_name:asc', 'age_days:desc'])
            limit: Maximum number of rows to return
            offset: Number of rows to skip
            **filters: Additional filter parameters
            
        Returns:
            JSON response from the API
        """
        url = urljoin(self.api_base, endpoint)
        params = {}
        
        # Add keys
        if keys:
            params['k'] = keys
        
        # Add sort
        if sort:
            params['s'] = sort
        
        # Add limit and offset
        if limit is not None:
            params['l'] = limit
        if offset is not None:
            params['o'] = offset
        
        # Add filters
        params.update(filters)
        
        response = requests.get(url, params=params, auth=self.auth, headers=self.headers, verify=self.verify_ssl)
        response.raise_for_status()
        return response.json()

def run_tests(client):
    """Run a series of tests against the PyRAT API."""
    tests = [
        {
            'name': 'Get Version',
            'function': client.get_version,
            'args': []
        },
        {
            'name': 'Get Credentials',
            'function': client.get_credentials,
            'args': []
        }
    ]
    
    # Optional tests that might not be accessible depending on permissions
    optional_tests = [
        {
            'name': 'Get Permissions',
            'function': client.get_permissions,
            'args': []
        },
        {
            'name': 'Get OpenAPI Spec (may be large)',
            'function': client.get_openapi_spec,
            'args': []
        },
        # Example of using a listing endpoint - uncomment if you have access to animals
        # {
        #    'name': 'List Animals',
        #    'function': client.get_list,
        #    'args': ['animals'],
        #    'kwargs': {'keys': ['eartag_or_id', 'sex', 'strain_name'], 'limit': 5}
        # }
    ]
    
    results = {'success': 0, 'failure': 0}
    
    print("\n=== Running Required Tests ===")
    
    # Run required tests
    for test in tests:
        print(f"\nRunning test: {test['name']}")
        try:
            if 'kwargs' in test:
                response = test['function'](*test['args'], **test['kwargs'])
            else:
                response = test['function'](*test['args'])
            
            print(f"✅ Success!")
            print(f"Response: {json.dumps(response, indent=2)}")
            results['success'] += 1
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            results['failure'] += 1
    
    print("\n=== Running Optional Tests ===")
    
    # Run optional tests
    for test in optional_tests:
        print(f"\nRunning test: {test['name']}")
        try:
            if 'kwargs' in test:
                response = test['function'](*test['args'], **test['kwargs'])
            else:
                response = test['function'](*test['args'])
            
            # For large responses, don't print the full content
            if test['name'] == 'Get OpenAPI Spec (may be large)':
                print(f"✅ Success! (Response too large to display)")
            else:
                print(f"✅ Success!")
                print(f"Response: {json.dumps(response, indent=2)}")
            
            results['success'] += 1
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
            # Don't count optional test failures
    
    return results

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Test PyRAT API v3 connectivity')
    parser.add_argument('base_url', help='Base URL of the PyRAT instance (e.g., https://example.com/pyrat/)')
    parser.add_argument('client_token', help='API-Client-Token (format: API-Client-Id-API-Client-Key)')
    parser.add_argument('user_token', help='API-User-Token (format: API-User-Id-API-User-Key)')
    parser.add_argument('--save-spec', help='Save OpenAPI specification to this file')
    parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    
    args = parser.parse_args()
    
    # Add warning for SSL verification
    if args.no_verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("⚠️ WARNING: SSL certificate verification disabled. This is insecure!")
    
    print(f"Testing PyRAT API v3 at {args.base_url}...")
    
    try:
        client = PyRatApiClient(args.base_url, args.client_token, args.user_token, verify_ssl=not args.no_verify_ssl)
        results = run_tests(client)
        
        if args.save_spec:
            try:
                spec = client.get_openapi_spec()
                with open(args.save_spec, 'w') as f:
                    json.dump(spec, f, indent=2)
                print(f"\nOpenAPI specification saved to {args.save_spec}")
            except Exception as e:
                print(f"\nFailed to save OpenAPI specification: {str(e)}")
        
        print(f"\n=== Test Results ===")
        print(f"Successful tests: {results['success']}")
        print(f"Failed tests: {results['failure']}")
        
        if results['failure'] > 0:
            sys.exit(1)
        else:
            print("\n✅ All required tests passed successfully!")
            sys.exit(0)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()