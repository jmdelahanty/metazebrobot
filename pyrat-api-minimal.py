#!/usr/bin/env python3
"""Absolute minimal example to test PyRAT API access"""

import requests
import urllib3
from urllib.parse import urljoin

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
base_url = "https://pyrataquatics.janelia.org/aquatic-test/"
user_token = "zebrobot"  # Replace with actual client token
client_token = "token"

# Construct API URLs
api_base = urljoin(base_url, 'api/v3/')
version_url = urljoin(api_base, 'version')
credentials_url = urljoin(api_base, 'credentials')

# Test 1: Access version endpoint (no auth)
print("Testing version endpoint...")
response = requests.get(version_url, verify=False)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}\n")

# Test 2: Access credentials endpoint (with auth)
print("Testing credentials endpoint...")
response = requests.get(
    credentials_url,
    auth=(client_token, user_token),  # Basic auth: (username, password)
    verify=False
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")