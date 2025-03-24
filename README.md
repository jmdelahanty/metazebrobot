# MetaZebrobot

A laboratory inventory management system for zebrafish research materials and dishes.

## Overview

MetaZebrobot is meant to start tracking metadata for my work at Janelia in the Johnson and Ahrens labs. There's a lot more information we can use to better understand our fish behavior and neural data if we just simply look at them I think. So this is a project to integrate literally as much metadata about my projects as I can so every experiment is completely documented from the fish being born down to the fish being studied in a particular place, time, condition, etc...

## Features

- **Agarose Solution Management**: Track agarose bottles and prepared solutions
- **Fish Water Management**: Monitor fish water batches and derivatives
- **Poly-L-Serine Management**: Track poly-l-serine bottles and aliquots
- **Fish Dish Tracking**: Monitor experimental fish dishes with quality checks
- **PyRAT API Integration**: Query and analyze data from the PyRAT aquatics system

## Project Structure

The project follows a Model-View-Controller (MVC) architecture:

```
metazebrobot/
├── src/
│   ├── main.py                     # Application entry point
│   ├── metazebrobot/
│       ├── models/                 # Data models
│       ├── controllers/            # Business logic
│       ├── views/                  # UI components
│       ├── data/                   # Data access layer
│       └── utils/                  # Utility functions
├── tests/                          # Test directory
├── config.json                     # Configuration file
└── tools/                          # Utility scripts and tools
    ├── pyrat_query_tool.py         # PyRAT API tank query tool
    └── get_all_user_ids.py         # PyRAT user mapping tool
```

## Installation

### Prerequisites

- Python 3.9+
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

#### Tank Query Tool

The `pyrat_query_tool.py` script provides a flexible way to query the PyRAT API for tank information:

```bash
# Get all tanks for a specific user
python pyrat_query_tool.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --responsible "delahantyj"

# Get tanks in a specific rack
python pyrat_query_tool.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --rack "M08"

# Filter by age
python pyrat_query_tool.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --min-age-days 90 --max-age-days 180

# Save results to a JSON file
python pyrat_query_tool.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --output tanks.json
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
python get_all_user_ids.py https://pyrataquatics.janelia.org/aquatic-test/ "client-token" "user-token" --output user_mapping.json
```

### Shoddy analysis notebook

The analysis notebook is pretty bad, but its a start I guess. Density matters for fish health. We all knew this. The next steps are to integrate some things with freely swimming behavior batteries to monitor the fish health over time and use these metrics to choose fish for behavior in our rigs and under the scopes. I'm guessing, in the end, it won't actually offer much of a useful pre-screening beyond what we currently do (look at the dish and pick one that's swimming). But my interest in knowing what my animals are like before I plop them into a weird situation is strong and my stubbornness about doing things like this may be even stronger.

### Adding New Features

1. Create or update model classes in the `models` directory
2. Implement business logic in the `controllers` directory
3. Create UI components in the `views` directory
4. Update the `main_window.py` to integrate new components

## Data Structure

The application uses JSON files for data storage:

- **Materials**: Stored in JSON files in the materials directory
- **Fish Dishes**: Each dish has its own JSON file in the dishes directory
- **PyRAT Data**: Query results from PyRAT can be saved as JSON files for analysis

In the future, having a database instead is very obviously the right move especially as we do this more and more with ever greater numbers of fish, dishes, etc.

## License

[MIT License](LICENSE)

## Contributors

Whoever feels like it!

## Acknowledgements

The awesome team at Scionics, the Janelia Aquatics team and especially Jared for putting up with my constant questions, and the Johnson and Ahrens labs for letting me be in the lab! <3