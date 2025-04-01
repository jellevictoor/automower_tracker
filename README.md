# Automower Tracker

This Python application tracks the location and status of your Husqvarna Automower and stores the data in InfluxDB 2. It's designed to help identify problematic areas in your lawn where the mower might get stuck or encounter errors like "no_loop_signal".

## Features

- Connects to Husqvarna Automower Connect API
- Uses WebSocket for real-time updates
- Tracks mower position, status, errors, and battery level
- Stores data in InfluxDB 2 for visualization and analysis
- Can be used to create heatmaps of error locations

## Setup

### Prerequisites

- Python 3.8 or newer
- InfluxDB 2.x instance
- Husqvarna developer account and API credentials
- Poetry for dependency management

### Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/automower-tracker.git
cd automower-tracker
```

2. Install dependencies with Poetry:
```bash
poetry install
```

3. Copy the environment template and fill in your values:
```bash
cp .env.template .env
# Edit .env with your actual credentials
```

### Obtaining Husqvarna API Credentials

1. Register for a developer account at [Husqvarna Group Developers Portal](https://developer.husqvarnagroup.cloud/)
2. Create a new application to get your Client ID, Client Secret, and API Key
3. Ensure your application has permissions for the Automower Connect API

### Configuring InfluxDB

1. Set up an InfluxDB 2.x instance
2. Create an organization, bucket, and API token
3. Add these details to your `.env` file

## Usage

Start the tracker:

```bash
poetry run python automower_tracker.py
```

The application will:
1. Authenticate with the Husqvarna API
2. Connect to your mowers
3. Start receiving WebSocket events with position and status updates
4. Store all data points in InfluxDB

## Visualizing the Data

### FastAPI Web Interface

The project includes a FastAPI-based web interface that provides a map visualization of your mower's GPS locations:

1. Start the frontend service:
```bash
# If using Docker Compose
docker-compose up automower-frontend

# Or run directly
poetry run python automower_tracker/frontend.py
```

2. Access the web interface at http://localhost:8000

Features of the web interface:
- Interactive map showing mower paths and positions
- Color-coded markers (green for normal operation, red for errors)
- Hover over points to see detailed mower status
- Filter by time range (last hour to last week)
- Select specific mowers if you have multiple

### Other Visualization Options

You can also:

1. Use Grafana or the InfluxDB UI to create dashboards
2. Generate heatmaps to see where errors occur most frequently
3. Analyze patterns in mower behavior

## Example InfluxDB Queries

Finding locations where "no_loop_signal" errors occur:

```flux
from(bucket: "automower")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "mower_event")
  |> filter(fn: (r) => r.error == "No loop signal")
  |> filter(fn: (r) => r._field == "latitude" or r._field == "longitude")
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
