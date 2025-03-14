#!/usr/bin/env python3
"""
PyRAT Page Inspector

This script inspects the PyRAT main page to look for clues about API endpoints.
"""

import requests
import argparse
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def inspect_pyrat_page(base_url, verify_ssl=False):
    """
    Inspect the PyRAT main page for API clues.
    
    Args:
        base_url: Base URL of the PyRAT server
        verify_ssl: Whether to verify SSL certificates
    """
    # Ensure base_url ends with a slash
    if not base_url.endswith('/'):
        base_url += '/'
    
    # Disable SSL verification warning if needed
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print(f"Inspecting PyRAT page at: {base_url}")
    
    try:
        # Get the main page
        response = requests.get(base_url, verify=verify_ssl, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to access page: Status {response.status_code}")
            return
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get the page title
        title = soup.title.string if soup.title else "No title found"
        print(f"\nPage title: {title}")
        
        # Look for version information
        version_pattern = re.compile(r'version\s*[:\-]?\s*(\d+\.\d+(?:\.\d+)?)', re.IGNORECASE)
        version_text = soup.find(string=version_pattern)
        if version_text:
            version_match = version_pattern.search(version_text)
            version = version_match.group(1) if version_match else "Unknown"
            print(f"Detected PyRAT version: {version}")
        
        # Look for API-related elements
        api_links = []
        api_pattern = re.compile(r'api', re.IGNORECASE)
        
        # Check meta tags
        meta_api = soup.find('meta', attrs={'name': api_pattern})
        if meta_api:
            print(f"Found API meta tag: {meta_api}")
            api_links.append(meta_api.get('content', ''))
        
        # Check script sources
        for script in soup.find_all('script', src=True):
            src = script['src']
            if 'api' in src.lower():
                print(f"Found API in script source: {src}")
                api_links.append(src)
        
        # Check links
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'api' in href.lower():
                print(f"Found API in link: {href}")
                api_links.append(href)
                
        # Look for any JavaScript with API configuration
        for script in soup.find_all('script'):
            if script.string and 'api' in script.string.lower():
                print("\nFound API reference in JavaScript:")
                # Try to find API base URL in the JavaScript
                api_url_pattern = re.compile(r'["\']api[/\\][^"\']*["\']', re.IGNORECASE)
                api_urls = api_url_pattern.findall(script.string)
                if api_urls:
                    print("Potential API endpoints found in JavaScript:")
                    for url in api_urls:
                        # Clean up the URL (remove quotes)
                        clean_url = url.strip('"\'')
                        print(f"  - {clean_url}")
                        api_links.append(clean_url)
        
        # Look for network request paths in app.js or similar files
        print("\nChecking for app.js file...")
        app_js_url = urljoin(base_url, 'static/js/app.js')
        try:
            js_response = requests.get(app_js_url, verify=verify_ssl, timeout=5)
            if js_response.status_code == 200:
                print("Found app.js, searching for API paths...")
                # Look for URL patterns in the JavaScript
                js_text = js_response.text
                api_patterns = re.findall(r'["\'](?:/[^"\']*api[^"\']*)["\']', js_text)
                if api_patterns:
                    print("Potential API endpoints found in app.js:")
                    for pattern in api_patterns:
                        clean_pattern = pattern.strip('"\'')
                        print(f"  - {clean_pattern}")
                        api_links.append(clean_pattern)
            else:
                print(f"app.js not found at {app_js_url} (status: {js_response.status_code})")
                
                # Try other common JS file locations
                for js_path in ['js/app.js', 'app.js', 'static/app.js', 'dist/app.js']:
                    alt_js_url = urljoin(base_url, js_path)
                    try:
                        alt_response = requests.get(alt_js_url, verify=verify_ssl, timeout=5)
                        if alt_response.status_code == 200:
                            print(f"Found JavaScript at {alt_js_url}")
                            # Don't analyze all JS files to avoid too much output
                            break
                    except:
                        pass
                
        except requests.exceptions.RequestException as e:
            print(f"Error checking app.js: {str(e)}")
        
        # Try to find documentation links
        print("\nLooking for documentation links...")
        doc_patterns = ['docs', 'documentation', 'swagger', 'api']
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if any(pattern in href for pattern in doc_patterns):
                link_text = link.get_text().strip()
                print(f"Documentation link: {href} (Text: {link_text})")
        
        # If we found API links, try to access them
        if api_links:
            print("\nTrying to access potential API endpoints:")
            for link in set(api_links):  # Use set to remove duplicates
                # Construct absolute URL if needed
                if not link.startswith('http'):
                    link = urljoin(base_url, link)
                
                print(f"\nTesting: {link}")
                try:
                    api_response = requests.get(link, verify=verify_ssl, timeout=5)
                    print(f"  Status: {api_response.status_code}")
                    print(f"  Content-Type: {api_response.headers.get('Content-Type', 'unknown')}")
                    
                    if api_response.status_code == 200:
                        content_type = api_response.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            print(f"  Response (JSON): {api_response.json()}")
                        else:
                            # For HTML or other content, just show first 100 chars
                            content_preview = api_response.text[:100].replace('\n', ' ')
                            print(f"  Response (preview): {content_preview}...")
                except requests.exceptions.RequestException as e:
                    print(f"  Error: {str(e)}")
        else:
            print("\nNo potential API endpoints found.")
    
    except requests.exceptions.RequestException as e:
        print(f"Error accessing page: {str(e)}")
    except Exception as e:
        print(f"Error during page inspection: {str(e)}")

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Inspect PyRAT page for API clues')
    parser.add_argument('base_url', help='Base URL of the PyRAT server')
    parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
    
    args = parser.parse_args()
    
    # Print warning for insecure connections
    if args.no_verify_ssl:
        print("⚠️ WARNING: SSL certificate verification disabled. This is insecure!")
    
    inspect_pyrat_page(args.base_url, verify_ssl=not args.no_verify_ssl)

if __name__ == "__main__":
    main()