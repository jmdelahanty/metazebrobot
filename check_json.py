#!/usr/bin/env python3
"""
Validation script for MetaZebrobot fish dish JSON files.

Checks JSON files in the specified directory against the FishDish Pydantic model.
"""

import json
import logging
import sys
import argparse
from pathlib import Path

# --- Adjust imports based on where you save this script ---
# If saved in the project root:
# from src.metazebrobot.models.fish_dish import FishDish
# from src.metazebrobot.utils.config import config
# If saved in a 'tools' directory at the root:
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent)) # Add root to sys.path
# from src.metazebrobot.models.fish_dish import FishDish
# from src.metazebrobot.utils.config import config

# --- Assuming script is saved in project root for simplicity ---
# Make sure your project structure allows this import path
try:
    from src.metazebrobot.models.fish_dish import FishDish
    from src.metazebrobot.utils.config import config
    from pydantic import ValidationError
except ImportError as e:
    print(f"Import Error: {e}")
    print("Please ensure this script is run from the project root directory or adjust sys.path.")
    sys.exit(1)
# --- End Imports ---


# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()] # Log to console
)
# --- End Logging Setup ---

def validate_dishes(dishes_dir: Path):
    """
    Validates all JSON files in the given directory against the FishDish model.

    Args:
        dishes_dir: Path object pointing to the directory containing dish JSON files.
    """
    if not dishes_dir or not dishes_dir.is_dir():
        logging.error(f"Dishes directory not found or not valid: {dishes_dir}")
        return

    json_files = list(dishes_dir.glob("*.json"))
    if not json_files:
        logging.warning(f"No JSON files found in directory: {dishes_dir}")
        return

    logging.info(f"Found {len(json_files)} JSON files to validate in {dishes_dir}...")
    invalid_files_count = 0
    valid_files_count = 0

    for file_path in json_files:
        try:
            # 1. Load JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 2. Validate with Pydantic
            # Use model_validate for Pydantic v2+
            FishDish.model_validate(data)
            valid_files_count += 1
            # logging.debug(f"OK: {file_path.name}") # Uncomment for verbose valid files

        except json.JSONDecodeError:
            logging.error(f"INVALID JSON: {file_path.name} - Could not parse JSON.")
            invalid_files_count += 1
        except ValidationError as e:
            # Log specific Pydantic validation errors
            error_details = "\n".join([f"  - {err['loc']}: {err['msg']}" for err in e.errors()])
            logging.error(f"VALIDATION FAILED: {file_path.name}\n{error_details}\n")
            invalid_files_count += 1
        except Exception as e:
            # Catch any other unexpected errors during file processing
            logging.error(f"UNEXPECTED ERROR processing {file_path.name}: {e}", exc_info=True)
            invalid_files_count += 1

    logging.info("-" * 40)
    logging.info(f"Validation Summary:")
    logging.info(f"  Total files checked: {len(json_files)}")
    logging.info(f"  Valid files: {valid_files_count}")
    logging.info(f"  Invalid files: {invalid_files_count}")
    logging.info("-" * 40)

def main():
    """Parses arguments, loads config, and runs validation."""
    parser = argparse.ArgumentParser(description='Validate MetaZebrobot fish dish JSON files.')
    parser.add_argument(
        '--dishes-dir',
        type=str,
        help='Directory containing fish dish JSON files (overrides config.json setting)'
    )
    args = parser.parse_args()

    dishes_directory = None
    if args.dishes_dir:
        dishes_directory = Path(args.dishes_dir)
        logging.info(f"Using dishes directory from command line: {dishes_directory}")
    else:
        # Try loading from config
        logging.info("Attempting to load dish directory from config.json...")
        if config.load_config():
            dishes_directory = config.dish_data_dir # Uses the @property
            if dishes_directory:
                logging.info(f"Using dishes directory from config: {dishes_directory}")
            else:
                logging.error("Could not retrieve 'remote_dish_data_directory' from config.")
                sys.exit(1)
        else:
            logging.error("Failed to load config.json. Please specify --dishes-dir.")
            sys.exit(1)

    validate_dishes(dishes_directory)

if __name__ == "__main__":
    main()