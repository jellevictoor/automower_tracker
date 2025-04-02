#!/usr/bin/env python3
"""
Simple Automower Status Checker
------------------------------
This script queries the Husqvarna Automower API and simply prints the full response.

Requirements:
- Python 3.6+
- requests package (pip install requests)
- python-dotenv package (pip install python-dotenv)
"""

import os
import sys
import json
import argparse
import requests
import dotenv

# Load environment variables
dotenv.load_dotenv()

# API endpoints
AUTH_API_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
MOWERS_API_URL = "https://api.amc.husqvarna.dev/v1/mowers"

def get_access_token(client_id, client_secret):
    """Get access token from Husqvarna Authentication API"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "iam:read amc:api"
    }

    try:
        response = requests.post(AUTH_API_URL, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Authentication error: {e}")
        if hasattr(e, "response") and e.response:
            print(f"Response: {e.response.text}")
        return None

def get_mower_data(token, api_key, mower_id=None):
    """Get data for a specific mower or all mowers"""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": api_key,
        "Authorization-Provider": "husqvarna"
    }

    url = MOWERS_API_URL
    if mower_id:
        url = f"{MOWERS_API_URL}/{mower_id}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching mower data: {e}")
        if hasattr(e, "response") and e.response:
            print(f"Response: {e.response.text}")
        return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Simple Automower Status Checker")
    parser.add_argument("-m", "--mower-id", help="Specific mower ID to check (optional)")
    parser.add_argument("-p", "--pretty", action="store_true", help="Pretty print the JSON output")

    args = parser.parse_args()

    # Get credentials from environment variables
    client_id = os.getenv("HUSQVARNA_CLIENT_ID")
    client_secret = os.getenv("HUSQVARNA_CLIENT_SECRET")
    api_key = os.getenv("HUSQVARNA_API_KEY")

    # Validate required credentials
    if not all([client_id, client_secret, api_key]):
        print("Error: Missing credentials. Please set the following environment variables:")
        print("  HUSQVARNA_CLIENT_ID")
        print("  HUSQVARNA_CLIENT_SECRET")
        print("  HUSQVARNA_API_KEY")
        sys.exit(1)

    # Get token
    token = get_access_token(client_id, client_secret)
    if not token:
        print("Failed to obtain access token.")
        sys.exit(1)

    # Get mower data
    data = get_mower_data(token, api_key, args.mower_id)

    # Print the raw JSON response
    if data:
        print(json.dumps(data, indent=2))
    else:
        print("No data received from the API.")

if __name__ == "__main__":
    main()