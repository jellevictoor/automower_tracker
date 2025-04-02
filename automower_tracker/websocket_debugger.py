#!/usr/bin/env python3
"""
Automower WebSocket Listener
----------------------------
This script connects to the Husqvarna Automower WebSocket API and
outputs all events to the command line.

Requirements:
- Python 3.6+
- websocket-client package (pip install websocket-client)
- requests package (pip install requests)
- python-dotenv package (pip install python-dotenv)
"""

import json
import os
import time
import argparse
import websocket
import threading
import sys
import requests
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Authentication and API endpoints
AUTH_API_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
MOWERS_API_URL = "https://api.amc.husqvarna.dev/v1/mowers"
WEBSOCKET_URL = "wss://ws.openapi.husqvarna.dev/v1"
PING_INTERVAL = 60  # Send ping every 60 seconds to keep connection alive
def on_data(ws, data, *args):
    """Handle incoming WebSocket data"""
    try:
        event = json.loads(data)
        # Pretty print the event with event type highlighted
        event_type = event.get("type", "unknown-event")
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Event: {event_type}")
        print(json.dumps(event, indent=2))
    except json.JSONDecodeError:
        print(f"Received non-JSON message: {data}")
    except Exception as e:
        print(f"Error processing data: {e}")

def on_message(ws, message):
    """Handle incoming WebSocket messages"""
    try:
        event = json.loads(message)
        # Pretty print the event with event type highlighted
        event_type = event.get("type", "unknown-event")
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Event: {event_type}")
        print(json.dumps(event, indent=2))
    except json.JSONDecodeError:
        print(f"Received non-JSON message: {message}")
    except Exception as e:
        print(f"Error processing message: {e}")

def on_error(ws, error):
    """Handle WebSocket errors"""
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket connection closure"""
    print(f"WebSocket closed: Status: {close_status_code}, Message: {close_msg}")
    # Reconnect if closed unexpectedly (and not due to Ctrl+C)
    if close_status_code is not None:  # None means closed by client
        print("Reconnecting in 5 seconds...")
        time.sleep(5)
        start_connection()

def on_open(ws):
    """Handle WebSocket connection opening"""
    print("WebSocket connection established!")
    print("Listening for Automower events...")

    # Start a thread to send pings periodically to keep the connection alive
    def ping_thread():
        while ws.sock and ws.sock.connected:
            try:
                ws.send("ping")
                print(".", end="", flush=True)  # Print a dot to show activity
                time.sleep(PING_INTERVAL)
            except Exception as e:
                print(f"\nPing error: {e}")
                break

    threading.Thread(target=ping_thread, daemon=True).start()

def start_connection(token=None):
    """Start WebSocket connection"""
    if not token:
        print("Error: Access token is required")
        sys.exit(1)

    # Set up headers with the authentication token
    headers = {
        "Authorization": f"Bearer {token}"
    }

    # Create and start the WebSocket connection
    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    # WebSocket connection will run in a separate thread
    wst = threading.Thread(target=ws.run_forever, kwargs={
        "ping_interval": 60,
        "ping_timeout": 10
    })
    wst.daemon = True
    wst.start()

    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        ws.close()
        sys.exit(0)

def get_access_token(client_id, client_secret):
    """Get access token from Husqvarna Authentication API"""
    print("Obtaining access token...")

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
        token_data = response.json()
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Authentication error: {e}")
        if hasattr(e, "response") and e.response:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def list_mowers(token, api_key):
    """List mowers associated with the account"""
    print("Fetching mowers...")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": api_key,
        "Authorization-Provider": "husqvarna"
    }

    try:
        response = requests.get(MOWERS_API_URL, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching mowers: {e}")
        if hasattr(e, "response") and e.response:
            print(f"Response: {e.response.text}")
        return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Automower WebSocket Listener")
    parser.add_argument("-t", "--token", help="Access token for Husqvarna API (optional if credentials provided)")
    parser.add_argument("-i", "--client-id", help="Husqvarna API client ID (required if no token)")
    parser.add_argument("-s", "--client-secret", help="Husqvarna API client secret (required if no token)")
    parser.add_argument("-k", "--api-key", help="Husqvarna API key (required to list mowers)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable WebSocket debug output")
    parser.add_argument("-l", "--list-mowers", action="store_true", help="List available mowers and exit")

    args = parser.parse_args()

    # Set up debug mode if requested
    if args.debug:
        websocket.enableTrace(True)

    # Get credentials from arguments or environment variables
    client_id = args.client_id or os.getenv("HUSQVARNA_CLIENT_ID")
    client_secret = args.client_secret or os.getenv("HUSQVARNA_CLIENT_SECRET")
    api_key = args.api_key or os.getenv("HUSQVARNA_API_KEY")
    token = args.token

    # Get token if not provided
    if not token and (client_id and client_secret):
        token = get_access_token(client_id, client_secret)
        print(f"Access token obtained successfully!")
    elif not token:
        print("Error: Either provide a token with -t or client credentials with -i and -s")
        sys.exit(1)

    # List mowers if requested
    if args.list_mowers:
        if not api_key:
            print("Error: API key is required to list mowers. Provide with -k or set HUSQVARNA_API_KEY environment variable.")
            sys.exit(1)

        mowers_data = list_mowers(token, api_key)
        if mowers_data and "data" in mowers_data:
            print("\nAvailable mowers:")
            for mower in mowers_data["data"]:
                mower_id = mower.get("id", "Unknown ID")
                name = mower.get("attributes", {}).get("system", {}).get("name", "Unknown name")
                model = mower.get("attributes", {}).get("system", {}).get("model", "Unknown model")
                print(f"- {name} ({model}): {mower_id}")
        sys.exit(0)

    print("Starting Automower WebSocket Listener...")
    start_connection(token)

if __name__ == "__main__":
    websocket.enableTrace(True)
    main()