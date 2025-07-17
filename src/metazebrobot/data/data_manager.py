"""
Data manager for MetaZebrobot - SQLite Database Version.

This module provides the main interface for accessing and manipulating application data
using SQLite with JSON columns for flexible NoSQL-style storage.
"""

import logging
import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
from contextlib import contextmanager

from ..utils.config import config
from ..utils.file_operations import ensure_directory, load_json_file

logger = logging.getLogger(__name__)


class DataManager:
    """
    Manages all data operations for the application using SQLite database.

    This class centralizes access to all data storage and retrieval operations,
    providing a clean interface for the rest of the application while using
    SQLite for better performance and data integrity.
    """

    def __init__(self):
        """Initialize the data manager with default values."""
        # Database path - will be set properly in initialize()
        self.database_path: Optional[Path] = None
        
        # Configuration paths for protocol and image files (still file-based)
        self.config_dir: Optional[Path] = None

        # In-memory cache of all data (for compatibility with existing code)
        self.data_cache: Dict[str, Dict[str, Any]] = {
            'agarose_bottles': {},
            'agarose_solutions': {},
            'fish_water_sources': {},
            'fish_water_derivatives': {},
            'poly_l_serine_bottles': {},
            'poly_l_serine_derivatives': {},
            'fish_dishes': {},
            'crosses': {},
            'screening_protocols': {},
            'indicator_images': {}
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
        logger.info("Initializing SQLite-based DataManager...")

        # Set database path
        configured_db_path = config.get_path('database_path')
        if configured_db_path:
            self.database_path = configured_db_path
        else:
            # Default to current directory
            self.database_path = Path.cwd() / "zebrobot.db"
            logger.info(f"No database path configured, using: {self.database_path}")

        # Check if database exists
        if not self.database_path.exists():
            logger.error(f"Database file not found: {self.database_path}")
            logger.error("Please run the migration script first!")
            return False

        # Set config directory for protocols and images
        self.config_dir = Path(__file__).parent.parent.parent / 'config'

        # Test database connection
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                expected_tables = ['crosses', 'dishes', 'quality_checks', 'materials']
                
                missing_tables = [t for t in expected_tables if t not in tables]
                if missing_tables:
                    logger.error(f"Missing required tables: {missing_tables}")
                    return False
                    
                logger.info(f"Database connection successful. Found tables: {tables}")
                
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

        # Mark as initialized
        self._is_initialized = True
        logger.info("DataManager initialized successfully with SQLite backend.")
        return True

    @property
    def is_initialized(self) -> bool:
        """Check if data manager has been initialized."""
        return self._is_initialized

    @contextmanager
    def get_connection(self):
        """Get a database connection with proper error handling."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
            conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def load_all_data(self) -> bool:
        """
        Load all data from database into memory cache.
        This maintains compatibility with existing code that expects cached data.

        Returns:
            bool: True if all data was loaded successfully
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot load data.")
            return False

        logger.info("Loading all data from SQLite database...")
        success = True

        try:
            # Load crosses
            if not self._load_crosses_to_cache():
                success = False
                logger.error("Failed to load crosses.")
            else:
                logger.info("Crosses loaded to cache.")

            # Load dishes
            if not self._load_dishes_to_cache():
                success = False
                logger.error("Failed to load dishes.")
            else:
                logger.info("Dishes loaded to cache.")

            # Load materials
            if not self._load_materials_to_cache():
                success = False
                logger.error("Failed to load materials.")
            else:
                logger.info("Materials loaded to cache.")

            # Load screening protocols (from file)
            if not self.load_screening_protocols():
                logger.warning("Failed to load screening protocols.")
            else:
                logger.info("Screening protocols loaded.")

            # Load indicator images (from file)
            if not self.load_indicator_images():
                logger.warning("Failed to load indicator images.")
            else:
                logger.info("Indicator images loaded.")

            # Validate cache structure
            self.validate_data_structure()

            if success:
                logger.info("All data loaded successfully from database.")
            else:
                logger.warning("Errors occurred during data loading.")

        except Exception as e:
            logger.error(f"Error loading data from database: {e}", exc_info=True)
            success = False

        return success

    def _load_crosses_to_cache(self) -> bool:
        """Load crosses from database to cache."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT cross_id, data FROM crosses")
                
                crosses = {}
                for row in cursor.fetchall():
                    cross_id = row['cross_id']
                    cross_data = json.loads(row['data'])
                    crosses[cross_id] = cross_data
                
                self.data_cache['crosses'] = crosses
                logger.debug(f"Loaded {len(crosses)} crosses to cache.")
                return True
                
        except Exception as e:
            logger.error(f"Error loading crosses to cache: {e}", exc_info=True)
            self.data_cache['crosses'] = {}
            return False

    def _load_dishes_to_cache(self) -> bool:
        """Load dishes from database to cache."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT dish_id, data FROM dishes")
                
                dishes = {}
                for row in cursor.fetchall():
                    dish_id = row['dish_id']
                    dish_data = json.loads(row['data'])
                    dishes[dish_id] = dish_data
                
                self.data_cache['fish_dishes'] = dishes
                logger.debug(f"Loaded {len(dishes)} dishes to cache.")
                return True
                
        except Exception as e:
            logger.error(f"Error loading dishes to cache: {e}", exc_info=True)
            self.data_cache['fish_dishes'] = {}
            return False

    def _load_materials_to_cache(self) -> bool:
        """Load materials from database to cache."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT material_type, material_id, data FROM materials")
                
                # Group materials by type
                materials_by_type = {}
                for row in cursor.fetchall():
                    material_type = row['material_type']
                    material_id = row['material_id']
                    material_data = json.loads(row['data'])
                    
                    if material_type not in materials_by_type:
                        materials_by_type[material_type] = {}
                    
                    materials_by_type[material_type][material_id] = material_data
                
                # Update cache with materials
                for material_type, materials in materials_by_type.items():
                    cache_key = material_type
                    if cache_key in self.data_cache:
                        self.data_cache[cache_key] = materials
                
                total_materials = sum(len(materials) for materials in materials_by_type.values())
                logger.debug(f"Loaded {total_materials} materials across {len(materials_by_type)} types to cache.")
                return True
                
        except Exception as e:
            logger.error(f"Error loading materials to cache: {e}", exc_info=True)
            return False

    def load_screening_protocols(self) -> bool:
        """Load screening protocols from JSON file (unchanged from original)."""
        try:
            protocol_file_path = self.config_dir / 'screening_protocols.json'
            logger.info(f"Attempting to load screening protocols from: {protocol_file_path}")

            protocols = load_json_file(protocol_file_path)
            if protocols is not None:
                self.data_cache['screening_protocols'] = protocols
                logger.info(f"Loaded {len(protocols)} screening protocol entries.")
                return True
            else:
                logger.warning(f"Screening protocols file not found: {protocol_file_path}")
                self.data_cache['screening_protocols'] = {}
                return False
        except Exception as e:
            logger.error(f"Error loading screening protocols: {e}", exc_info=True)
            self.data_cache['screening_protocols'] = {}
            return False

    def load_indicator_images(self) -> bool:
        """Load indicator images map from JSON file (unchanged from original)."""
        try:
            image_map_file_path = self.config_dir / 'indicator_images.json'
            logger.info(f"Attempting to load indicator images from: {image_map_file_path}")

            image_map = load_json_file(image_map_file_path)
            if image_map is not None:
                self.data_cache['indicator_images'] = image_map
                logger.info(f"Loaded {len(image_map)} indicator image mappings.")
                return True
            else:
                logger.warning(f"Indicator images file not found: {image_map_file_path}")
                self.data_cache['indicator_images'] = {}
                return False
        except Exception as e:
            logger.error(f"Error loading indicator images: {e}", exc_info=True)
            self.data_cache['indicator_images'] = {}
            return False

    def save_fish_dish(self, dish_data: Dict[str, Any]) -> bool:
        """Save a single fish dish to database."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False

        try:
            dish_id = dish_data.get('dish_id')
            if not dish_id:
                logger.error("Cannot save dish: missing 'dish_id'")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Insert or update dish
                cursor.execute("""
                INSERT OR REPLACE INTO dishes 
                (dish_id, cross_id, date_created, dof, genotype, responsible, 
                 status, fish_count, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    dish_id,
                    dish_data.get('cross_id'),
                    dish_data.get('date_created'),
                    dish_data.get('dof'),
                    dish_data.get('genotype'),
                    dish_data.get('responsible'),
                    dish_data.get('status', 'active'),
                    dish_data.get('fish_count'),
                    json.dumps(dish_data)
                ))

                # Update quality checks
                self._save_quality_checks(cursor, dish_id, dish_data.get('quality_checks', {}))

                conn.commit()
                
                # Update cache
                self.data_cache['fish_dishes'][dish_id] = dish_data
                logger.info(f"Successfully saved dish {dish_id} to database")
                return True

        except Exception as e:
            logger.error(f"Error saving dish {dish_id}: {e}", exc_info=True)
            return False

    def _save_quality_checks(self, cursor, dish_id: str, quality_checks: Dict[str, Any]):
        """Save quality checks for a dish."""
        # Delete existing quality checks for this dish
        cursor.execute("DELETE FROM quality_checks WHERE dish_id = ?", (dish_id,))
        
        # Insert new quality checks
        for check_time, check_data in quality_checks.items():
            cursor.execute("""
            INSERT INTO quality_checks 
            (dish_id, check_time, fed, feed_type, water_changed, 
             vol_water_changed, num_dead, notes, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dish_id,
                check_time,
                check_data.get('fed'),
                check_data.get('feed_type'),
                check_data.get('water_changed'),
                check_data.get('vol_water_changed'),
                check_data.get('num_dead'),
                check_data.get('notes'),
                json.dumps(check_data)
            ))

    def save_cross(self, cross_data: Dict[str, Any]) -> bool:
        """Save a single cross to database."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False

        try:
            cross_id = cross_data.get('cross_id')
            if not cross_id:
                logger.error("Cannot save cross: missing 'cross_id'")
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                INSERT OR REPLACE INTO crosses 
                (cross_id, request_date, responsible_requestor, line_strain, 
                 cross_type, cross_status, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    cross_id,
                    cross_data.get('request_date'),
                    cross_data.get('responsible_requestor'),
                    cross_data.get('line_strain'),
                    cross_data.get('cross_type'),
                    cross_data.get('cross_status'),
                    json.dumps(cross_data)
                ))

                conn.commit()
                
                # Update cache
                self.data_cache['crosses'][cross_id] = cross_data
                logger.info(f"Successfully saved cross {cross_id} to database")
                return True

        except Exception as e:
            logger.error(f"Error saving cross {cross_id}: {e}", exc_info=True)
            return False

    def load_single_dish(self, dish_id: str) -> Optional[Dict[str, Any]]:
        """Load a single dish by ID from database."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM dishes WHERE dish_id = ?", (dish_id,))
                row = cursor.fetchone()
                
                if row:
                    dish_data = json.loads(row['data'])
                    # Update cache
                    self.data_cache['fish_dishes'][dish_id] = dish_data
                    return dish_data
                else:
                    logger.warning(f"Dish {dish_id} not found in database")
                    return None

        except Exception as e:
            logger.error(f"Error loading dish {dish_id}: {e}", exc_info=True)
            return None

    def load_single_cross(self, cross_id: str) -> Optional[Dict[str, Any]]:
        """Load a single cross by ID from database."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM crosses WHERE cross_id = ?", (cross_id,))
                row = cursor.fetchone()
                
                if row:
                    cross_data = json.loads(row['data'])
                    # Update cache
                    self.data_cache['crosses'][cross_id] = cross_data
                    return cross_data
                else:
                    logger.warning(f"Cross {cross_id} not found in database")
                    return None

        except Exception as e:
            logger.error(f"Error loading cross {cross_id}: {e}", exc_info=True)
            return None

    def update_dish_quality_check(self, dish_id: str, check_data: Dict[str, Any]) -> bool:
        """Update quality checks for a dish."""
        logger.debug(f"Updating quality check for dish {dish_id}")
        
        # Load current dish data
        dish_data = self.load_single_dish(dish_id)
        if not dish_data:
            logger.error(f"Cannot update quality check: dish {dish_id} not found")
            return False

        check_time = check_data.get('check_time')
        if not check_time:
            logger.error("Cannot add quality check: 'check_time' is missing")
            return False

        # Update dish data
        if 'quality_checks' not in dish_data:
            dish_data['quality_checks'] = {}
        
        dish_data['quality_checks'][check_time] = check_data
        
        # Save updated dish
        return self.save_fish_dish(dish_data)

    def validate_data_structure(self) -> bool:
        """Validate the data structure has all required top-level keys in the cache."""
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

    # --- Convenience Getters (maintain compatibility) ---

    def get_category_data(self, category: str) -> Dict[str, Any]:
        """Get data for a specific category from the cache."""
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
        logger.warning("Screening protocols data not in expected format. Returning empty dict.")
        return {}

    def get_indicator_images(self) -> Dict[str, str]:
        """Get the loaded indicator -> image path mapping."""
        image_map = self.get_category_data('indicator_images')
        if isinstance(image_map, dict) and all(isinstance(v, str) for v in image_map.values()):
            return image_map
        logger.warning("Indicator images data not in expected format. Returning empty dict.")
        return {}

    # --- Material Management (using database backend) ---

    def add_agarose_solution(self, solution_id: str, solution_data: Dict[str, Any]) -> bool:
        """Add/Update an agarose solution in database and cache."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT OR REPLACE INTO materials 
                (material_type, material_id, data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    'agarose_solutions',
                    solution_id,
                    json.dumps(solution_data)
                ))
                conn.commit()
                
                # Update cache
                if 'agarose_solutions' not in self.data_cache:
                    self.data_cache['agarose_solutions'] = {}
                self.data_cache['agarose_solutions'][solution_id] = solution_data
                
                logger.debug(f"Added agarose solution {solution_id} to database")
                return True
                
        except Exception as e:
            logger.error(f"Error adding agarose solution {solution_id}: {e}", exc_info=True)
            return False

    def save_all_data(self) -> bool:
        """
        Save all material data from cache to database.
        Dishes and crosses are already saved individually.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot save data.")
            return False

        logger.info("Saving all material data to database...")
        success = True

        material_categories = [
            'agarose_bottles', 'agarose_solutions', 'fish_water_sources',
            'fish_water_derivatives', 'poly_l_serine_bottles', 'poly_l_serine_derivatives'
        ]

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for category in material_categories:
                    category_data = self.get_category_data(category)
                    
                    for material_id, material_data in category_data.items():
                        cursor.execute("""
                        INSERT OR REPLACE INTO materials 
                        (material_type, material_id, data, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            category,
                            material_id,
                            json.dumps(material_data)
                        ))
                    
                    logger.debug(f"Saved {len(category_data)} items for {category}")
                
                conn.commit()
                logger.info("All material data saved successfully to database.")
                
        except Exception as e:
            logger.error(f"Error saving material data: {e}", exc_info=True)
            success = False

        return success

    # --- Database-specific utility methods ---
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a custom SQL query and return results."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return []

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                # Convert rows to dictionaries
                columns = [description[0] for description in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                return results
                
        except Exception as e:
            logger.error(f"Error executing query: {e}", exc_info=True)
            return []

    def get_active_dishes_summary(self) -> List[Dict[str, Any]]:
        """Get summary of active dishes using the database view."""
        return self.execute_query("SELECT * FROM active_dishes")

    def get_recent_quality_checks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent quality checks using the database view."""
        return self.execute_query(f"SELECT * FROM recent_quality_checks LIMIT ?", (limit,))

    def get_dishes_needing_attention(self, days: int = 2) -> List[Dict[str, Any]]:
        """Get dishes that haven't been checked in specified number of days."""
        query = """
        SELECT dish_id, last_check, genotype, responsible
        FROM active_dishes 
        WHERE last_check < date('now', '-{} days') OR last_check IS NULL
        ORDER BY last_check ASC
        """.format(days)
        return self.execute_query(query)


# Create a singleton instance for global access
data_manager = DataManager()