# MetaZebrobot

A laboratory inventory management system for zebrafish research materials and dishes.

## Overview

MetaZebrobot is meant to start tracking metadata for my work at Janelia in the Johnson and Ahrens labs. There's a lot more information we can use to better understand our fish behavior and neural data if we just simply look at them I think. So this is a project to integrate literally as much metadata about my projects as I can so every experiment is completely documented from the fish being born down to the fish being studied in a particular place, time, condition, etc...

## Features

- **Agarose Solution Management**: Track agarose bottles and prepared solutions
- **Fish Water Management**: Monitor fish water batches and derivatives
- **Poly-L-Serine Management**: Track poly-l-serine bottles and aliquots
- **Fish Dish Tracking**: Monitor experimental fish dishes with quality checks
  and optional daily care images
- **PyRAT API Integration**: Query tanks/crossings from PyRAT and enrich
  crossing performance from authenticated frontend detail endpoints

## Project Structure

The project follows a Model-View-Controller (MVC) architecture:

```
metazebrobot/
├── src/
│   ├── metazebrobot/
│   │   ├── cli.py                  # Application entry point
│   │   ├── config/                 # Packaged JSON + image assets
│   │   ├── models/                 # Data models
│   │   ├── controllers/            # Business logic
│   │   ├── views/                  # UI components
│   │   ├── data/                   # Data access layer
│   │   └── utils/                  # Utility functions
├── bin/                            # Utility scripts
├── docs/                           # Design notes and web/API documentation
├── tests/                          # Test directory
├── config.example.json             # Example user config
├── pyrat_credentials_tool.py       # PyRAT credential setup / clear tool
├── pyrat_query_tool.py             # PyRAT API tank query tool
├── get_all_user_ids.py             # PyRAT user mapping tool
└── migrate_to_nosql.py             # JSON -> SQLite migration
```

## Installation

### Prerequisites

- Python 3.11+
- PySide6 (Qt for Python)
- Pydantic
- Rich (for console output)
- Requests (for API integration)

### Setup

Docs for this will show up maybe one day. For now, I don't think anyone else would want to use this thing or rely on it. Frankly, people shouldn't! Its at your discretion...

## Development

### Running Tests

Not currently doing, but want to add pytest at some point...

```
pytest
```

### PyRAT API Integration

MetaZebrobot integrates with [PyRAT](https://www.scionics.com/pyrat.html), which Janelia relies on for animal management. The integration includes several features:

#### Credential Setup

Store PyRAT API tokens and optional frontend username/password in the system keyring:

```bash
python pyrat_credentials_tool.py --setup-credentials
```

The query tool still supports `--setup-credentials`, but the dedicated credentials tool is now the primary setup path.

For systemd deployments, PyRAT credentials can also be provided through
environment variables (`PYRAT_BASE_URL`, `PYRAT_CLIENT_TOKEN`,
`PYRAT_USER_TOKEN`, and optionally `PYRAT_FRONTEND_USERNAME` /
`PYRAT_FRONTEND_PASSWORD`). `scripts/inspect_pyrat_keyring.py --env-format`
prints the stored keyring values in a format suitable for a protected
`EnvironmentFile`.

#### Tank Query Tool

The `pyrat_query_tool.py` script provides a flexible way to query the PyRAT API for tank information:

```bash
# Use stored credentials from the system keyring
python pyrat_query_tool.py --responsible "delahantyj"

# Get all tanks for a specific user
python pyrat_query_tool.py --base-url "https://pyrataquatics.janelia.org/aquatic/" --client-token "client-token" --user-token "user-token" --responsible "delahantyj"

# Get tanks in a specific rack
python pyrat_query_tool.py --base-url "https://pyrataquatics.janelia.org/aquatic/" --client-token "client-token" --user-token "user-token" --rack "M08"

# Filter by age
python pyrat_query_tool.py --base-url "https://pyrataquatics.janelia.org/aquatic/" --client-token "client-token" --user-token "user-token" --min-age-days 90 --max-age-days 180

# Save results to a JSON file
python pyrat_query_tool.py --output tanks.json
```

Features:
- **User Mapping**: Maintains a local cache of user ID mappings to avoid repeated lookups
- **Age Analysis**: Calculates and categorizes tank ages (OK, WARNING, URGENT)
- **Flexible Filtering**: Filter by responsible person, location, status, strain, and age
- **Detailed Reporting**: Generates summary statistics and detailed tank listings
- **Export**: Save query results as JSON for further analysis

#### User ID Mapping Tool

The `get_all_user_ids.py` script creates a mapping between usernames and user IDs:

```bash
python get_all_user_ids.py https://pyrataquatics.janelia.org/aquatic/ "client-token" "user-token" --output user_mapping.json
```

### Shoddy analysis notebook

The analysis notebook is pretty bad, but its a start I guess. Density matters for fish health. We all knew this. The next steps are to integrate some things with freely swimming behavior batteries to monitor the fish health over time and use these metrics to choose fish for behavior in our rigs and under the scopes. I'm guessing, in the end, it won't actually offer much of a useful pre-screening beyond what we currently do (look at the dish and pick one that's swimming). But my interest in knowing what my animals are like before I plop them into a weird situation is strong and my stubbornness about doing things like this may be even stronger.

### Adding New Features

1. Create or update model classes in the `models` directory
2. Implement business logic in the `controllers` directory
3. Create UI components in the `views` directory
4. Update the `main_window.py` to integrate new components

## Configuration

Create a local `config.json` (see `config.example.json`) to point the app at your
SQLite database. This file is user-specific and should not be committed.

## Web/API Server (FastAPI)

The FastAPI server powers both the browser-based dish workflows and the JSON
HTTP endpoints while the SQLite file stays local to the host.

For local testing from this repo, use Pixi:

```
pixi run python -m metazebrobot.api_server --db-path ./zebrobot.db --port 8000
```

Then open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/dishes/new`
- `http://127.0.0.1:8000/care/`
- `http://127.0.0.1:8000/pyrat/crossings/`

If you prefer a plain Python environment instead of Pixi:

```
python3 -m pip install -e . fastapi uvicorn
METAZEBROBOT_DB_PATH=/path/to/zebrobot.db \
python3 -m metazebrobot.api_server --port 8000
```

Add `--lab-network` only if you explicitly want other machines on the LAN to
connect.

Example routes:

- `GET /`
- `GET /dishes/new`
- `GET /dishes/`
- `GET /screening/`
- `GET /care/`
- `GET /fish/`
- `GET /references/`
- `GET /pyrat/tanks/`
- `GET /pyrat/crossings/`
- `GET /health`
- `GET /dishes?status=active&limit=200&offset=0`
- `GET /dishes/{dish_id}?include_checks=true`

See `docs/web_pages.md` for the current page-by-page capability map.

### systemd service (Ubuntu)

An example unit file is provided at `deploy/metazebrobot-api.service`. Copy it to
`/etc/systemd/system/`, edit the `User`, `WorkingDirectory`,
`METAZEBROBOT_DB_PATH`, and `ExecStart` flags as needed, then enable it:

```
sudo cp deploy/metazebrobot-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now metazebrobot-api.service
```

The checked-in unit binds to `127.0.0.1`. If you intentionally want LAN access,
update `ExecStart` to add `--lab-network`.

## Data Structure

The application uses a SQLite database (`zebrobot.db`) for core data:

- **Dishes, crosses, materials, quality checks**: stored in SQLite tables
- **JSON blobs** are retained in the DB for flexible record storage
- **Uploaded images** are stored on disk beside the SQLite database
  (`screening_images/`, `fish_images/`, `dish_images/`, `care_images/`) with
  paths/filenames stored in SQLite
- **PyRAT data** query results can still be exported to JSON for analysis

The `migrate_to_nosql.py` script can migrate legacy JSON directories into the
SQLite database.

## License

[MIT License](LICENSE)

## Contributors

Whoever feels like it!

## Acknowledgements

The awesome team at Scionics, the Janelia Aquatics team and especially Jared for putting up with my constant questions, and the Johnson and Ahrens labs for letting me be in the lab! <3
