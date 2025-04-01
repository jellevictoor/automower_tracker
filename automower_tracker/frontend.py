#!/usr/bin/env python3
"""
Automower Tracker Frontend - A FastAPI web interface for visualizing
Automower location and status data stored in InfluxDB.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from influxdb_client import InfluxDBClient
import uvicorn

# Load environment variables
dotenv.load_dotenv()

# InfluxDB configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "automower")

# Create FastAPI app
app = FastAPI(title="Automower Tracker", description="Visualize Automower location and status")

# Create templates directory
os.makedirs("automower_tracker/templates", exist_ok=True)
templates = Jinja2Templates(directory="automower_tracker/templates")

# Create static files directory
os.makedirs("automower_tracker/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="automower_tracker/static"), name="static")

# Initialize InfluxDB client
influx_client = InfluxDBClient(
    url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG
)
query_api = influx_client.query_api()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main page with the map."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/mowers")
async def get_mowers():
    """Get a list of all mowers."""
    query = '''
from(bucket: "automower")
  |> range(start: -1d)
  |> filter(fn: (r) => r._measurement == "mower_status")
  |> keep(columns: ["mower_id", "name"])
  |> distinct(column: "mower_id")
  |> yield(name: "distinct")
    '''

    try:
        result = query_api.query(query)
        mowers = []
        seen_ids = set()

        for table in result:
            for record in table.records:
                mower_id = record.values.get("mower_id")
                if mower_id not in seen_ids:
                    mowers.append({
                        "mower_id": mower_id,
                        "name": record.values.get("name")
                    })
                    seen_ids.add(mower_id)

        return mowers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying InfluxDB: {str(e)}")
@app.get("/api/positions")
async def get_positions(hours: int = 24, mower_id: Optional[str] = None):
    """Get mower positions for the specified time range."""
    time_range = f"-{hours}h"

    mower_filter = ""
    if mower_id:
        mower_filter = f'|> filter(fn: (r) => r.mower_id == "{mower_id}")'

    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
        |> range(start: {time_range})
        |> filter(fn: (r) => r._measurement == "mower_position")
        {mower_filter}
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''

    try:
        result = query_api.query(query)
        positions = []

        for table in result:
            for record in table.records:
                position = {
                    "time": record.get_time().isoformat(),
                    "mower_id": record.values.get("mower_id"),
                    "name": record.values.get("name", "Unknown"),
                    "latitude": record.values.get("latitude"),
                    "longitude": record.values.get("longitude"),
                    "error_code": record.values.get("error_code", 0)
                }
                positions.append(position)

        return positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying InfluxDB: {str(e)}")

@app.get("/api/status/{mower_id}")
async def get_mower_status(mower_id: str):
    """Get the latest status for a specific mower."""
    query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
        |> range(start: -1h)
        |> filter(fn: (r) => r._measurement == "mower_status")
        |> filter(fn: (r) => r.mower_id == "{mower_id}")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: 1)
    '''

    try:
        result = query_api.query(query)

        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail=f"No status found for mower {mower_id}")

        for table in result:
            for record in table.records:
                status = {
                    "time": record.get_time().isoformat(),
                    "mower_id": record.values.get("mower_id"),
                    "name": record.values.get("name", "Unknown"),
                    "model": record.values.get("model", "Unknown"),
                    "battery_percent": record.values.get("battery_percent", 0),
                    "mode": record.values.get("mode", "UNKNOWN"),
                    "activity": record.values.get("activity", "UNKNOWN"),
                    "state": record.values.get("state", "UNKNOWN"),
                    "error_code": record.values.get("error_code", 0),
                    "error": record.values.get("error", "")
                }
                return status

        raise HTTPException(status_code=404, detail=f"No status found for mower {mower_id}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error querying InfluxDB: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("frontend:app", host="0.0.0.0", port=8000, reload=True)
