#!/usr/bin/env python3
"""
Automower Tracker - Monitors Husqvarna Automower location and status
using polling and stores the data in InfluxDB 2 for analysis.
"""

import os
import time
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

import requests
import dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("automower_tracker")

# Load environment variables
dotenv.load_dotenv()

# API URLs
AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
MOWERS_URL = "https://api.amc.husqvarna.dev/v1/mowers"

# Authentication and API credentials
CLIENT_ID = os.getenv("HUSQVARNA_CLIENT_ID")
CLIENT_SECRET = os.getenv("HUSQVARNA_CLIENT_SECRET")
API_KEY = os.getenv("HUSQVARNA_API_KEY")

# InfluxDB configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "automower")

# Polling interval in seconds
POLL_INTERVAL = 30

# Position interval in seconds (time between consecutive position readings)
POSITION_INTERVAL = 30

# Error codes to track
ERROR_CODES = {
    0: "No message",
    1: "Outside working area",
    2: "No loop signal",
    3: "Wrong loop signal",
    4: "Loop sensor problem, front",
    5: "Loop sensor problem, rear",
    6: "Loop sensor problem, left",
    7: "Loop sensor problem, right",
    8: "Wrong PIN code",
    9: "Trapped",
    10: "Upside down",
    11: "Low battery",
    12: "Empty battery",
    13: "No drive",
    14: "Mower lifted",
    15: "Lifted",
    16: "Stuck in charging station",
    17: "Charging station blocked",
}


class AutomowerTracker:
    """Tracks Automower location and status data via polling."""

    def __init__(self):
        self.access_token = None
        self.token_expires_at = 0
        self.mowers = []
        self.running = False

        # Initialize InfluxDB client
        try:
            self.influx_client = InfluxDBClient(
                url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG
            )
            self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
            # Test InfluxDB connection
            health = self.influx_client.health()
            logger.info(f"InfluxDB connection: {health.status}")
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB client: {e}")
            raise

    def authenticate(self) -> None:
        """Get OAuth2 token for Husqvarna API access using client credentials flow."""
        logger.info("Authenticating with Husqvarna API")
        data = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }

        try:
            response = requests.post(AUTH_URL, data=data)
            response.raise_for_status()

            auth_data = response.json()
            self.access_token = auth_data["access_token"]
            # Set token expiry time (with a safety margin)
            self.token_expires_at = time.time() + auth_data["expires_in"] - 60
            logger.info(f"Authentication successful, token expires in {auth_data['expires_in']} seconds")
        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication failed: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise

    def get_mowers(self) -> list:
        """Get list of mowers linked to the account."""
        if time.time() > self.token_expires_at:
            self.authenticate()

        logger.info("Fetching mowers list")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Authorization-Provider": "husqvarna",
            "X-Api-Key": API_KEY,
        }

        try:
            response = requests.get(MOWERS_URL, headers=headers)
            response.raise_for_status()

            data = response.json()
            mowers = data.get("data", [])
            logger.info(f"Found {len(mowers)} mowers")

            return mowers
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get mowers: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            raise

    def get_mower_details(self, mower_id: str) -> dict:
        """Get detailed information about a specific mower."""
        if time.time() > self.token_expires_at:
            self.authenticate()

        logger.info(f"Fetching details for mower {mower_id}")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Authorization-Provider": "husqvarna",
            "X-Api-Key": API_KEY,
        }

        try:
            response = requests.get(f"{MOWERS_URL}/{mower_id}", headers=headers)
            response.raise_for_status()

            return response.json().get("data", {})
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get mower details: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text}")
            return {}

    def store_mower_data(self, mower_data: Dict[str, Any]) -> None:
        """Store mower data in InfluxDB."""

        try:
            mower_id = mower_data.get("id")
            attributes = mower_data.get("attributes", {})

            # Extract relevant data
            system = attributes.get("system", {})
            battery = attributes.get("battery", {})
            mower = attributes.get("mower", {})
            positions = attributes.get("positions", [])
            metadata = attributes.get("metadata", {})

            # Get statusTimestamp from metadata
            status_timestamp_ms = metadata.get("statusTimestamp", 0)

            # Convert milliseconds to datetime object with UTC timezone
            if status_timestamp_ms > 0:
                status_timestamp = datetime.fromtimestamp(status_timestamp_ms / 1000, timezone.utc)
            else:
                # Fallback to current time if statusTimestamp is not available
                status_timestamp = datetime.now(timezone.utc)
                logger.warning(f"statusTimestamp not available, using current time: {status_timestamp}")

            # Log basic information
            name = system.get("name", "Unknown")
            model = system.get("model", "Unknown")
            battery_percent = battery.get("batteryPercent", 0)
            mode = mower.get("mode", "UNKNOWN")
            activity = mower.get("activity", "UNKNOWN")
            state = mower.get("state", "UNKNOWN")
            error_code = mower.get("errorCode", 0)

            logger.info(f"Mower: {name}, Battery: {battery_percent}%, "
                        f"Status: {activity}, Error Code: {error_code}")
            logger.info(f"Status timestamp: {status_timestamp}")

            # Create status point
            status_point = Point("mower_status") \
                .tag("mower_id", mower_id) \
                .tag("name", name) \
                .tag("model", model) \
                .tag("mode", mode) \
                .tag("activity", activity) \
                .tag("state", state) \
                .field("battery_percent", battery_percent) \
                .field("error_code", error_code) \
                .time(status_timestamp)

            # Add error information if there's an error
            if error_code > 0:
                error_description = ERROR_CODES.get(error_code, f"Unknown error {error_code}")
                status_point.tag("error", error_description)
                logger.warning(f"Mower error: {error_description} (code {error_code})")

            # Add additional fields from mower status
            for key, value in mower.items():
                if key not in ["mode", "activity", "state", "errorCode"] and isinstance(value, (int, float, bool)):
                    status_point.field(key, value)

            # Write status point to InfluxDB
            self.write_api.write(bucket=INFLUXDB_BUCKET, record=status_point)

            # Only process position data if the mower is actually mowing
            if activity == "MOWING":
                # Create position points if available
                if positions and len(positions) > 0:
                    logger.info(f"Processing {len(positions)} position points for MOWING status")

                    # The positions array is ordered with most recent position first
                    # Each position is POSITION_INTERVAL seconds apart
                    for i, position in enumerate(positions):
                        if "latitude" in position and "longitude" in position:
                            lat = float(position["latitude"])
                            lon = float(position["longitude"])

                            # Calculate timestamp for this position
                            # The most recent position (index 0) gets the status_timestamp
                            # Earlier positions get proportionally earlier timestamps
                            position_timestamp = status_timestamp - timedelta(seconds=i * POSITION_INTERVAL)

                            position_point = Point("mower_position") \
                                .tag("mower_id", mower_id) \
                                .tag("name", name) \
                                .tag("activity", activity) \
                                .field("latitude", lat) \
                                .field("longitude", lon) \
                                .time(position_timestamp)

                            # Add error information to position if there's an error
                            if error_code > 0:
                                error_description = ERROR_CODES.get(error_code, f"Unknown error {error_code}")
                                position_point.tag("error", error_description)
                                position_point.field("error_code", error_code)

                            # Write position point to InfluxDB
                            self.write_api.write(bucket=INFLUXDB_BUCKET, record=position_point)

                            if i == 0:  # Only log the most recent position to avoid excessive logging
                                logger.info(f"Most recent position: {lat}, {lon} at {position_timestamp}")
                        else:
                            logger.warning(f"Position data incomplete for position {i}")
                else:
                    logger.warning("No position data available while mower is MOWING")
            else:
                logger.info(f"Skipping position tracking as mower is not MOWING (current activity: {activity})")

            logger.info(f"Stored data for mower {mower_id}")

        except Exception as e:
            logger.error(f"Error storing mower data: {e}")

    def poll_mowers(self):
        """Poll for mower data at regular intervals."""
        while self.running:
            try:
                # Get list of mowers
                mowers = self.get_mowers()

                for mower in mowers:
                    mower_id = mower.get("id")
                    # Get detailed information for each mower
                    mower_details = self.get_mower_details(mower_id)
                    if mower_details:
                        self.store_mower_data(mower_details)

                # Sleep for the polling interval
                logger.info(f"Sleeping for {POLL_INTERVAL} seconds before next poll")
                time.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error during polling: {e}")
                # Sleep a bit before retrying
                time.sleep(10)

                # Re-authenticate if needed
                if time.time() > self.token_expires_at:
                    try:
                        self.authenticate()
                    except Exception as auth_error:
                        logger.error(f"Failed to re-authenticate: {auth_error}")
                        time.sleep(30)  # Longer delay after auth failure

    def run(self):
        """Main method to run the tracker."""
        try:
            # Initial authentication
            self.authenticate()

            # Start polling
            self.running = True
            self.poll_mowers()

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            self.influx_client.close()
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            self.running = False
            self.influx_client.close()


if __name__ == "__main__":
    tracker = AutomowerTracker()
    tracker.run()