"""
Data manager for MetaZebrobot.

This module provides the main interface for accessing and manipulating application data.
Handles dish filenames including the date of fertilization (DOF): <dish_id>_<dof>.json
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple

from ..utils.config import config
# Use JsonStorage for individual cross/dish files
from .json_storage import CategoryJsonStorage, JsonStorage
# Import file operations utilities
from ..utils.file_operations import ensure_directory, load_json_file, save_json_file, list_json_files

logger = logging.getLogger(__name__)


class DataManager:
    """
    Manages all data operations for the application.

    This class centralizes access to all data storage and retrieval operations,
    providing a clean interface for the rest of the application.
    """

    # File name constants for materials (assuming single file per category)
    AGAROSE_BOTTLES_FILE = "agarose_bottles.json"
    AGAROSE_SOLUTIONS_FILE = "agarose_solutions.json"
    FISH_WATER_SOURCES_FILE = "fish_water_sources.json" # Consider renaming file/key to fish_water_batches
    FISH_WATER_DERIVATIVES_FILE = "fish_water_derivatives.json"
    POLY_L_SERINE_BOTTLES_FILE = "poly-l-serine_bottles.json"
    POLY_L_SERINE_DERIVATIVES_FILE = "poly-l-serine_derivatives.json"

    # Constant for protocol file (relative to src/config)
    SCREENING_PROTOCOLS_FILE = "screening_protocols.json"
    # Constant for indicator images mapping (relative to src/config)
    INDICATOR_IMAGES_FILE = "indicator_images.json"

    def __init__(self):
        """Initialize the data manager with default values."""
        # Initialize with empty paths - will be set properly in initialize()
        self.material_data_dir: Optional[Path] = None
        self.dish_data_dir: Optional[Path] = None
        self.cross_data_dir: Optional[Path] = None

        # Storage handlers - will be initialized in initialize()
        self.agarose_bottles_storage: Optional[CategoryJsonStorage] = None
        self.agarose_solutions_storage: Optional[CategoryJsonStorage] = None
        self.fish_water_sources_storage: Optional[CategoryJsonStorage] = None
        self.fish_water_derivatives_storage: Optional[CategoryJsonStorage] = None
        self.poly_l_serine_bottles_storage: Optional[CategoryJsonStorage] = None
        self.poly_l_serine_derivatives_storage: Optional[CategoryJsonStorage] = None
        self.dish_storage: Optional[JsonStorage] = None
        self.cross_storage: Optional[JsonStorage] = None

        # In-memory cache of all data
        self.data_cache: Dict[str, Dict[str, Any]] = {
            'agarose_bottles': {},
            'agarose_solutions': {},
            'fish_water_sources': {},
            'fish_water_derivatives': {},
            'poly_l_serine_bottles': {},
            'poly_l_serine_derivatives': {},
            'fish_dishes': {},
            'crosses': {},
            'screening_protocols': {}, # Cache for protocols
            'indicator_images': {} # Cache for image map
        }

        # Flag to track initialization state
        self._is_initialized = False

    def initialize(self) -> bool:
        """
        Initialize the data manager with configuration settings.
        This should be called after config is loaded.

        Returns:
            bool: True if initialization successful
        """
        logger.info("Initializing DataManager...")

        # Get paths from config (for data directories)
        self.material_data_dir = config.get_path('remote_material_data_directory')
        self.dish_data_dir = config.get_path('remote_dish_data_directory')
        self.cross_data_dir = config.get_path('remote_cross_data_directory')

        # Fall back to local directories if remote ones don't exist or aren't configured
        if not self.material_data_dir:
            logger.warning("No material directory configured or found, using local 'materials/'")
            self.material_data_dir = Path.cwd() / "materials"

        if not self.dish_data_dir:
            logger.warning("No dish directory configured or found, using local 'dishes/'")
            self.dish_data_dir = Path.cwd() / "dishes"

        if not self.cross_data_dir:
            logger.warning("No cross directory configured or found, using local 'crosses/'")
            self.cross_data_dir = Path.cwd() / "crosses"

        # Ensure data directories exist
        if not ensure_directory(self.material_data_dir): return False
        if not ensure_directory(self.dish_data_dir): return False
        if not ensure_directory(self.cross_data_dir): return False

        # Initialize storage handlers
        self.agarose_bottles_storage = CategoryJsonStorage(self.material_data_dir, "agarose_bottles")
        self.agarose_solutions_storage = CategoryJsonStorage(self.material_data_dir, "agarose_solutions")
        self.fish_water_sources_storage = CategoryJsonStorage(self.material_data_dir, "fish_water_batches")
        self.fish_water_derivatives_storage = CategoryJsonStorage(self.material_data_dir, "fish_water_derivatives")
        self.poly_l_serine_bottles_storage = CategoryJsonStorage(self.material_data_dir, "poly_l_serine_bottles")
        self.poly_l_serine_derivatives_storage = CategoryJsonStorage(self.material_data_dir, "poly_l_serine_derivatives")
        self.dish_storage = JsonStorage(self.dish_data_dir)
        self.cross_storage = JsonStorage(self.cross_data_dir)

        # Mark as initialized
        self._is_initialized = True
        logger.info("DataManager initialized successfully.")
        return True

    @property
    def is_initialized(self) -> bool:
        """Check if data manager has been initialized."""
        return self._is_initialized

    def load_all_data(self) -> bool:
        """
        Load all data from storage into memory.

        Returns:
            bool: True if all data was loaded successfully, False if there were any errors
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot load data.")
            return False

        logger.info("Loading all data...")
        success = True

        # --- Load Material Data ---
        try:
            self.data_cache['agarose_bottles'] = self.agarose_bottles_storage.load_category(self.AGAROSE_BOTTLES_FILE) if self.agarose_bottles_storage else {}
            self.data_cache['agarose_solutions'] = self.agarose_solutions_storage.load_category(self.AGAROSE_SOLUTIONS_FILE) if self.agarose_solutions_storage else {}
            self.data_cache['fish_water_sources'] = self.fish_water_sources_storage.load_category(self.FISH_WATER_SOURCES_FILE) if self.fish_water_sources_storage else {}
            self.data_cache['fish_water_derivatives'] = self.fish_water_derivatives_storage.load_category(self.FISH_WATER_DERIVATIVES_FILE) if self.fish_water_derivatives_storage else {}
            self.data_cache['poly_l_serine_bottles'] = self.poly_l_serine_bottles_storage.load_category(self.POLY_L_SERINE_BOTTLES_FILE) if self.poly_l_serine_bottles_storage else {}
            self.data_cache['poly_l_serine_derivatives'] = self.poly_l_serine_derivatives_storage.load_category(self.POLY_L_SERINE_DERIVATIVES_FILE) if self.poly_l_serine_derivatives_storage else {}
            logger.info("Material data loaded.")
        except Exception as e:
            logger.error(f"Error loading material data: {str(e)}", exc_info=True)
            success = False

        # --- Load Fish Dishes ---
        if not self.load_fish_dishes():
            success = False
            logger.error("Failed to load fish dishes.")
        else:
             logger.info("Fish dish data loaded.")

        # --- Load Crosses ---
        if not self.load_crosses():
            success = False
            logger.error("Failed to load crosses.")
        else:
             logger.info("Cross data loaded.")

        # --- Load Screening Protocols (from src/config only) ---
        if not self.load_screening_protocols():
             logger.warning("Failed to load screening protocols.")
        else:
             logger.info("Screening protocols loaded.")

        # --- Load Indicator Images (from src/config only) ---
        if not self.load_indicator_images():
             logger.warning("Failed to load indicator images.")
        else:
             logger.info("Indicator images loaded.")

        # --- Validate Cache Structure ---
        self.validate_data_structure() # Ensure all top-level keys exist

        if success:
            logger.info("All data loaded successfully.")
        else:
            logger.warning("Errors occurred during data loading.")

        return success

    def load_screening_protocols(self) -> bool:
        """
        Load screening protocols from the JSON file located within src/config/.
        """
        try:
            protocol_file_path = Path(__file__).parent.parent.parent / 'config' / self.SCREENING_PROTOCOLS_FILE
            logger.info(f"Attempting to load screening protocols from default path: {protocol_file_path}")

            protocols = load_json_file(protocol_file_path)
            if protocols is not None:
                self.data_cache['screening_protocols'] = protocols
                logger.info(f"Loaded {len(protocols)} screening protocol entries from {protocol_file_path}.")
                return True
            else:
                logger.warning(f"Screening protocols file not found or failed to load at {protocol_file_path}.")
                self.data_cache['screening_protocols'] = {}
                return False
        except Exception as e:
            logger.error(f"Error calculating path or loading screening protocols: {e}", exc_info=True)
            self.data_cache['screening_protocols'] = {}
            return False

    def load_indicator_images(self) -> bool:
        """
        Load indicator -> image path mapping from the JSON file located within src/config/.
        """
        try:
            image_map_file_path = Path(__file__).parent.parent.parent / 'config' / self.INDICATOR_IMAGES_FILE
            logger.info(f"Attempting to load indicator images map from default path: {image_map_file_path}")

            image_map = load_json_file(image_map_file_path)
            if image_map is not None:
                self.data_cache['indicator_images'] = image_map
                logger.info(f"Loaded {len(image_map)} indicator image mappings from {image_map_file_path}.")
                return True
            else:
                logger.warning(f"Indicator images file not found or failed to load at {image_map_file_path}.")
                self.data_cache['indicator_images'] = {}
                return False
        except Exception as e:
            logger.error(f"Error calculating path or loading indicator images: {e}", exc_info=True)
            self.data_cache['indicator_images'] = {}
            return False

    def load_fish_dishes(self) -> bool:
        """Load all fish dishes from individual files into the cache."""
        if not self.dish_storage or not self.dish_data_dir:
            logger.error("Dish storage or directory not initialized.")
            return False
        logger.debug(f"Loading fish dishes from {self.dish_data_dir}...")
        dishes = {}
        try:
            # Use glob to find all files matching the pattern *_*.json to catch dated files
            dish_files = self.dish_storage.list_files("*_*.json")
            for dish_file_path in dish_files:
                dish_data = load_json_file(dish_file_path)
                if dish_data:
                    # Use the internal dish_id (without date) as the cache key
                    dish_id = dish_data.get('dish_id')
                    if dish_id:
                        # If multiple files exist for the same internal dish_id (e.g., different dates),
                        # this will overwrite with the last one found by list_files.
                        # Consider adding logic here to pick the latest date if needed.
                        dishes[dish_id] = dish_data
                    else:
                        logger.warning(f"Dish file {dish_file_path.name} missing 'dish_id' key inside JSON. Skipping.")
                else:
                     logger.warning(f"Failed to load or parse dish file {dish_file_path.name}.")

            self.data_cache['fish_dishes'] = dishes
            logger.debug(f"Loaded {len(dishes)} fish dishes into cache (using internal dish_id as key).")
            return True
        except Exception as e:
            logger.error(f"Error loading fish dishes: {str(e)}", exc_info=True)
            self.data_cache['fish_dishes'] = {}
            return False

    def load_crosses(self) -> bool:
        """Load all crosses from individual files into the cache."""
        if not self.cross_storage or not self.cross_data_dir:
            logger.error("Cross storage or directory not initialized.")
            return False
        logger.debug(f"Loading crosses from {self.cross_data_dir}...")
        crosses = {}
        try:
            cross_files = self.cross_storage.list_files("*.json")
            for cross_file_path in cross_files:
                cross_data = load_json_file(cross_file_path)
                if cross_data:
                    cross_id_from_data = cross_data.get('cross_id')
                    cross_id_from_name = cross_file_path.stem
                    if cross_id_from_name:
                         if cross_id_from_data and cross_id_from_data != cross_id_from_name:
                              logger.warning(f"Cross file {cross_file_path.name} 'cross_id' ({cross_id_from_data}) doesn't match filename stem ({cross_id_from_name}). Using ID from filename.")
                         cross_data['cross_id'] = cross_id_from_name
                         crosses[cross_id_from_name] = cross_data
                    else:
                        logger.warning(f"Could not determine cross_id from filename for {cross_file_path.name}. Skipping.")
                else:
                     logger.warning(f"Failed to load or parse cross file {cross_file_path.name}.")

            self.data_cache['crosses'] = crosses
            logger.debug(f"Loaded {len(crosses)} crosses.")
            return True
        except Exception as e:
            logger.error(f"Error loading crosses: {str(e)}", exc_info=True)
            self.data_cache['crosses'] = {}
            return False

    def save_fish_dish(self, dish_data: Dict[str, Any]) -> bool:
        """
        Save a single fish dish. Uses filename format: <dish_id>_<dof>.json
        """
        if not self.dish_storage:
            logger.error("Dish storage not initialized.")
            return False
        try:
            dish_id = dish_data.get('dish_id')
            dof = dish_data.get('dof') # Date of fertilization

            if not dish_id:
                logger.error("Cannot save dish: missing 'dish_id'")
                return False
            if not dof:
                # Fallback or error handling if DOF is missing
                logger.error(f"Cannot save dish {dish_id}: missing 'dof' (date of fertilization).")
                # Option 1: Use date_created as fallback?
                # dof = dish_data.get('date_created')
                # if not dof:
                #    logger.error(f"Cannot save dish {dish_id}: 'dof' and 'date_created' are missing.")
                #    return False
                # Option 2: Return error
                return False

            # Construct filename with date
            filename = f"{dish_id}_{dof}.json"
            logger.debug(f"Attempting to save dish {dish_id} with DOF {dof} to {filename}")

            if self.dish_storage.save(filename, dish_data):
                # Update cache using the internal dish_id (without date) as the key
                self.data_cache['fish_dishes'][dish_id] = dish_data
                logger.info(f"Successfully saved dish {dish_id} to {filename}")
                return True
            else:
                logger.error(f"Failed to save dish {dish_id} using storage handler.")
                return False
        except Exception as e:
            logger.error(f"Error saving fish dish {dish_data.get('dish_id', 'UNKNOWN')}: {str(e)}", exc_info=True)
            return False

    def save_cross(self, cross_data: Dict[str, Any]) -> bool:
        """
        Save a single cross to its own file. Uses filename format: <cross_id>.json
        """
        if not self.cross_storage:
            logger.error("Cross storage not initialized.")
            return False
        try:
            cross_id = cross_data.get('cross_id')
            if not cross_id:
                logger.error("Cannot save cross: missing 'cross_id'")
                return False

            filename = f"{cross_id}.json"
            logger.debug(f"Attempting to save cross {cross_id} to {filename}")

            if self.cross_storage.save(filename, cross_data):
                self.data_cache['crosses'][cross_id] = cross_data
                logger.info(f"Successfully saved cross {cross_id} to {filename}")
                return True
            else:
                logger.error(f"Failed to save cross {cross_id} using storage handler.")
                return False
        except Exception as e:
            logger.error(f"Error saving cross {cross_data.get('cross_id', 'UNKNOWN')}: {str(e)}", exc_info=True)
            return False

    def load_single_dish(self, dish_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a single dish file by finding the file matching <dish_id>_*.json pattern.
        If multiple matches, loads the first one found.
        """
        if not self.dish_storage or not self.dish_data_dir:
            logger.error("Dish storage or directory not initialized.")
            return None
        logger.debug(f"Attempting to load single dish with internal ID: {dish_id}")
        try:
            # Use glob to find potential files matching the pattern
            pattern = f"{dish_id}_*.json"
            possible_files = list(self.dish_data_dir.glob(pattern))

            if not possible_files:
                logger.warning(f"No file found matching pattern '{pattern}' in {self.dish_data_dir} for dish ID {dish_id}")
                return None

            # If multiple files match (e.g., different dates saved), load the first one found.
            # Consider adding sorting logic here if you need to specifically load the latest date.
            if len(possible_files) > 1:
                logger.warning(f"Multiple files found for dish ID {dish_id}: {[f.name for f in possible_files]}. Loading the first one: {possible_files[0].name}")
                # Example sorting by date in filename (descending):
                # possible_files.sort(key=lambda p: p.stem.split('_')[-1], reverse=True)


            file_to_load = possible_files[0]
            logger.debug(f"Found potential file via glob: {file_to_load.name}. Loading...")
            return self.dish_storage.load(file_to_load.name)

        except Exception as e:
            logger.error(f"Error loading single dish {dish_id}: {str(e)}", exc_info=True)
            return None

    def load_single_cross(self, cross_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a single cross file using <cross_id>.json.
        """
        if not self.cross_storage or not self.cross_data_dir: # Check directory too
            logger.error("Cross storage or directory not initialized.")
            return None
        logger.debug(f"Attempting to load single cross {cross_id}")
        try:
            filename = f"{cross_id}.json"
            file_path = self.cross_data_dir / filename
            if not file_path.exists():
                 logger.warning(f"Cross file not found: {file_path}")
                 return None
            return self.cross_storage.load(filename)
        except Exception as e:
            logger.error(f"Error loading single cross {cross_id}: {str(e)}", exc_info=True)
            return None

    def update_dish_quality_check(self, dish_id: str, check_data: Dict[str, Any]) -> bool:
        """
        Update the quality checks for a dish. Loads, modifies, and saves the dish file.
        Uses load_single_dish which handles the dated filename.
        """
        logger.debug(f"Updating quality check for dish {dish_id}")
        try:
            # Load using the method that finds the dated file
            dish_data = self.load_single_dish(dish_id)
            if not dish_data:
                logger.error(f"Cannot update quality check for dish {dish_id}: dish data not found.")
                return False

            check_time = check_data.get('check_time')
            if not check_time:
                logger.error("Cannot add quality check: 'check_time' is missing from check_data.")
                return False

            if 'quality_checks' not in dish_data or not isinstance(dish_data['quality_checks'], dict):
                dish_data['quality_checks'] = {}

            dish_data['quality_checks'][check_time] = check_data
            logger.debug(f"Added quality check for time {check_time} to dish {dish_id} data.")

            # Save using the method that saves with the date in the filename
            if self.save_fish_dish(dish_data):
                logger.info(f"Successfully updated quality check for dish {dish_id}.")
                # save_fish_dish already updates cache
                return True
            else:
                logger.error(f"Failed to save updated dish data for dish {dish_id} after adding quality check.")
                return False

        except Exception as e:
            logger.error(f"Error updating quality check for dish {dish_id}: {str(e)}", exc_info=True)
            return False

    def validate_data_structure(self) -> bool:
        """
        Validate the data structure has all required top-level keys in the cache.
        """
        logger.debug("Validating data cache structure...")
        required_keys = [
            'agarose_bottles', 'agarose_solutions', 'fish_water_sources',
            'fish_water_derivatives', 'poly_l_serine_bottles',
            'poly_l_serine_derivatives', 'fish_dishes', 'crosses',
            'screening_protocols', 'indicator_images'
        ]

        updated = False
        for key in required_keys:
            if key not in self.data_cache:
                logger.warning(f"Missing top-level key in cache: '{key}'. Initializing.")
                self.data_cache[key] = {}
                updated = True

        if updated:
             logger.debug("Data cache structure validation complete (keys added).")
        else:
             logger.debug("Data cache structure validation complete (no changes).")
        return True

    # --- Convenience Getters ---

    def get_category_data(self, category: str) -> Dict[str, Any]:
        """
        Get data for a specific category from the cache. Ensures key exists.
        """
        if category not in self.data_cache:
            logger.warning(f"Requested unknown category '{category}' from cache. Initializing key.")
            self.data_cache[category] = {}
        data = self.data_cache.get(category, {})
        return data if isinstance(data, dict) else {}


    def get_agarose_bottles(self) -> Dict[str, Any]:
        return self.get_category_data('agarose_bottles')

    def get_agarose_solutions(self) -> Dict[str, Any]:
        return self.get_category_data('agarose_solutions')

    def get_fish_water_batches(self) -> Dict[str, Any]:
        return self.get_category_data('fish_water_sources')

    def get_fish_water_derivatives(self) -> Dict[str, Any]:
        return self.get_category_data('fish_water_derivatives')

    def get_poly_l_serine_bottles(self) -> Dict[str, Any]:
        return self.get_category_data('poly_l_serine_bottles')

    def get_poly_l_serine_derivatives(self) -> Dict[str, Any]:
        return self.get_category_data('poly_l_serine_derivatives')

    def get_fish_dishes(self) -> Dict[str, Any]:
        return self.get_category_data('fish_dishes')

    def get_crosses(self) -> Dict[str, Any]:
        return self.get_category_data('crosses')

    def get_screening_protocols(self) -> Dict[str, Dict[str, Any]]:
        """Get the loaded screening protocols."""
        protocols = self.get_category_data('screening_protocols')
        if isinstance(protocols, dict):
             return protocols
        logger.warning("Screening protocols data in cache is not in the expected format (Dict[str, Dict]). Returning empty dict.")
        return {}

    def get_indicator_images(self) -> Dict[str, str]:
        """Get the loaded indicator -> image path mapping."""
        image_map = self.get_category_data('indicator_images')
        if isinstance(image_map, dict) and all(isinstance(v, str) for v in image_map.values()):
             return image_map
        logger.warning("Indicator images data in cache is not in the expected format (Dict[str, str]). Returning empty dict.")
        return {}

    # --- Convenience Adders/Savers ---

    def add_agarose_solution(self, solution_id: str, solution_data: Dict[str, Any]) -> bool:
        """
        Add/Update an agarose solution in cache and save the category file.
        """
        if not self.agarose_solutions_storage:
            logger.error("Agarose solution storage not initialized.")
            return False
        try:
            if 'agarose_solutions' not in self.data_cache:
                self.data_cache['agarose_solutions'] = {}
            self.data_cache['agarose_solutions'][solution_id] = solution_data
            logger.debug(f"Updated cache for agarose solution {solution_id}")

            return self.agarose_solutions_storage.save_category(
                self.AGAROSE_SOLUTIONS_FILE,
                self.data_cache['agarose_solutions']
            )
        except Exception as e:
            logger.error(f"Error adding/saving agarose solution {solution_id}: {str(e)}", exc_info=True)
            return False

    # --- Save All Data (Materials Only) ---

    def save_all_data(self) -> bool:
        """
        Save all *material* data from memory to storage.
        Dishes and Crosses are saved individually. Protocols/Images are read-only.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot save data.")
            return False

        logger.info("Saving all material data...")
        success = True

        material_categories = [
            ('agarose_bottles', self.agarose_bottles_storage, self.AGAROSE_BOTTLES_FILE),
            ('agarose_solutions', self.agarose_solutions_storage, self.AGAROSE_SOLUTIONS_FILE),
            ('fish_water_sources', self.fish_water_sources_storage, self.FISH_WATER_SOURCES_FILE),
            ('fish_water_derivatives', self.fish_water_derivatives_storage, self.FISH_WATER_DERIVATIVES_FILE),
            ('poly_l_serine_bottles', self.poly_l_serine_bottles_storage, self.POLY_L_SERINE_BOTTLES_FILE),
            ('poly_l_serine_derivatives', self.poly_l_serine_derivatives_storage, self.POLY_L_SERINE_DERIVATIVES_FILE),
        ]

        for category_key, storage_handler, filename in material_categories:
            if storage_handler:
                category_data = self.get_category_data(category_key)
                if not storage_handler.save_category(filename, category_data):
                    logger.error(f"Failed to save material category: {category_key}")
                    success = False
                else:
                    logger.debug(f"Saved material category: {category_key}")
            else:
                logger.warning(f"Storage handler not initialized for material category: {category_key}. Cannot save.")

        if success:
            logger.info("All material data saved successfully.")
        else:
            logger.warning("Errors occurred during material data saving.")

        return success

# Create a singleton instance for global access
data_manager = DataManager()
