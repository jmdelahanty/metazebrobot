# MetaZebrobot

A laboratory inventory management system for zebrafish research materials and dishes.

## Overview

MetaZebrobot provides a comprehensive solution for managing laboratory materials, solutions, and fish dishes used in zebrafish research. It allows researchers to track inventory, create solutions, and monitor experiments through a user-friendly desktop application.

## Features

- **Agarose Solution Management**: Track agarose bottles and prepared solutions
- **Fish Water Management**: Monitor fish water batches and derivatives
- **Poly-L-Serine Management**: Track poly-l-serine bottles and aliquots
- **Fish Dish Tracking**: Monitor experimental fish dishes with quality checks

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
└── config.json                     # Configuration file
```

## Installation

### Prerequisites

- Python 3.9+
- PySide6 (Qt for Python)
- Pydantic

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/metazebrobot.git
   cd metazebrobot
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create a `config.json` file in the project root:
   ```json
   {
     "remote_material_data_directory": "/path/to/materials",
     "remote_dish_data_directory": "/path/to/dishes"
   }
   ```

5. Run the application:
   ```
   python src/main.py
   ```

## Development

### Running Tests

```
pytest
```

### Adding New Features

1. Create or update model classes in the `models` directory
2. Implement business logic in the `controllers` directory
3. Create UI components in the `views` directory
4. Update the `main_window.py` to integrate new components

## Data Structure

The application uses JSON files for data storage:

- **Materials**: Stored in JSON files in the materials directory
- **Fish Dishes**: Each dish has its own JSON file in the dishes directory

## License

[MIT License](LICENSE)

## Contributors
Whoever feels like it!