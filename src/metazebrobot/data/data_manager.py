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
        self.config_dir = Path(__file__).parent.parent / 'config'

        # Test database connection and apply schema updates
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

                # Apply schema updates (safe to run multiple times)
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_checks_unique
                    ON quality_checks(dish_id, check_time)
                """)

                # Phase 1: Create screening_steps table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS screening_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        screening_datetime TEXT NOT NULL,
                        dpf_screened INTEGER,
                        indicator_screened TEXT,
                        criteria TEXT,
                        count_screened_this_step INTEGER,
                        number_positive INTEGER,
                        tricaine_used BOOLEAN DEFAULT FALSE,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id),
                        UNIQUE(dish_id, screening_datetime)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_screening_steps_dish_id
                    ON screening_steps(dish_id)
                """)

                # Add removal tracking columns to screening_steps table (if not exist)
                cursor.execute("PRAGMA table_info(screening_steps)")
                screening_cols = {row[1] for row in cursor.fetchall()}
                if 'number_removed_pigmented' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_pigmented INTEGER")
                if 'number_removed_negative' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_negative INTEGER")
                if 'number_removed_other' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_other INTEGER")

                # Add screening result columns to dishes table (if not exist)
                # SQLite doesn't have ADD COLUMN IF NOT EXISTS, so we check first
                cursor.execute("PRAGMA table_info(dishes)")
                existing_columns = {row[1] for row in cursor.fetchall()}

                if 'screening_final_positive_count' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN screening_final_positive_count INTEGER")
                if 'screening_date_finalized' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN screening_date_finalized TEXT")

                # Phase 2: Create transgenic_indicators table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transgenic_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cross_id TEXT NOT NULL,
                        modification_type TEXT DEFAULT 'tg',
                        promoter_driver TEXT,
                        reporter_effector TEXT NOT NULL,
                        color TEXT,
                        expected_expression TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (cross_id) REFERENCES crosses(cross_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_transgenic_indicators_cross_id
                    ON transgenic_indicators(cross_id)
                """)

                # Add aggregate columns to crosses table (if not exist)
                cursor.execute("PRAGMA table_info(crosses)")
                crosses_columns = {row[1] for row in cursor.fetchall()}

                if 'agg_total_initially_produced' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN agg_total_initially_produced INTEGER")
                if 'agg_total_positive_final' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN agg_total_positive_final INTEGER")
                if 'agg_yield_percentage' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN agg_yield_percentage REAL")
                if 'agg_date_aggregated' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN agg_date_aggregated TEXT")

                # Phase 4: Add remaining columns to crosses table for full flattening
                if 'requested_groups' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN requested_groups INTEGER")
                if 'groups_produced' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN groups_produced INTEGER")
                if 'notes' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN notes TEXT")
                if 'parents' not in crosses_columns:
                    cursor.execute("ALTER TABLE crosses ADD COLUMN parents TEXT")  # JSON array
                # TODO: If incross queries become common, consider adding an indexed is_incross column
                # derived from parents length to avoid JSON parsing in SQLite queries.

                # Phase 3: Add remaining columns to dishes table for full flattening
                # Re-fetch dishes columns after previous changes
                cursor.execute("PRAGMA table_info(dishes)")
                existing_columns = {row[1] for row in cursor.fetchall()}

                # Core fields
                if 'species' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN species TEXT DEFAULT 'Danio rerio'")
                if 'sex' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN sex TEXT DEFAULT 'unknown'")
                if 'parent_dish_id' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN parent_dish_id TEXT")
                if 'dish_population_type' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN dish_population_type TEXT")
                if 'notes' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN notes TEXT")
                if 'room' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN room TEXT")

                # Enclosure fields (flattened)
                if 'enclosure_temperature' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_temperature REAL")
                if 'enclosure_in_beaker' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_in_beaker BOOLEAN")
                if 'enclosure_vol_water_total' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_vol_water_total INTEGER")
                if 'enclosure_light_duration' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_light_duration TEXT")
                if 'enclosure_dawn_dusk' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_dawn_dusk TEXT")

                # Breeding parents (stored as JSON array for simplicity)
                if 'breeding_parents' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN breeding_parents TEXT")

                # Termination tracking columns
                if 'termination_date' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN termination_date TEXT")
                if 'termination_reason' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN termination_reason TEXT")

                # Phase 5: Add additional indexes for common query patterns
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_genotype ON dishes(genotype)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_responsible ON dishes(responsible)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_dof ON dishes(dof)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_date_created ON dishes(date_created)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crosses_cross_type ON crosses(cross_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crosses_cross_status ON crosses(cross_status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_crosses_responsible_requestor ON crosses(responsible_requestor)")

                conn.commit()
                logger.debug("Schema updates applied successfully")

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
        Load static configuration data (protocols, images).
        Dynamic data (dishes, crosses, materials) is loaded on-demand from database.

        Returns:
            bool: True if static data was loaded successfully
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot load data.")
            return False

        logger.info("Loading static configuration data...")
        success = True

        try:
            # Load screening protocols (from file - static config)
            if not self.load_screening_protocols():
                logger.warning("Failed to load screening protocols.")
            else:
                logger.info("Screening protocols loaded.")

            # Load indicator images (from file - static config)
            if not self.load_indicator_images():
                logger.warning("Failed to load indicator images.")
            else:
                logger.info("Indicator images loaded.")

            logger.info("Static configuration loaded. Dynamic data will be loaded on-demand from database.")

        except Exception as e:
            logger.error(f"Error loading static data: {e}", exc_info=True)
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
        """Save a single fish dish to database.

        All database operations are wrapped in a transaction - if any operation
        fails, all changes are rolled back to maintain data integrity.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False

        dish_id = dish_data.get('dish_id')
        if not dish_id:
            logger.error("Cannot save dish: missing 'dish_id'")
            return False

        conn = None
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Begin explicit transaction
            cursor.execute("BEGIN TRANSACTION")

            # Extract nested data for flattened columns
            enclosure = dish_data.get('enclosure', {})
            light_cycle = enclosure.get('light_cycle', {}) if enclosure else {}
            breeding = dish_data.get('breeding', {})
            breeding_parents = breeding.get('parents', []) if breeding else []

            # Insert or update dish with all flattened columns
            cursor.execute("""
            INSERT OR REPLACE INTO dishes
            (dish_id, cross_id, date_created, dof, genotype, responsible,
             status, fish_count, species, sex, parent_dish_id, dish_population_type,
             notes, room, enclosure_temperature, enclosure_in_beaker,
             enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
             breeding_parents, termination_date, termination_reason, data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                dish_id,
                dish_data.get('cross_id'),
                dish_data.get('date_created'),
                dish_data.get('dof'),
                dish_data.get('genotype'),
                dish_data.get('responsible'),
                dish_data.get('status', 'active'),
                dish_data.get('fish_count'),
                dish_data.get('species', 'Danio rerio'),
                dish_data.get('sex', 'unknown'),
                dish_data.get('parent_dish_id'),
                dish_data.get('dish_population_type'),
                dish_data.get('notes'),
                enclosure.get('room') if enclosure else None,
                enclosure.get('temperature') if enclosure else None,
                enclosure.get('in_beaker') if enclosure else None,
                enclosure.get('vol_water_total') if enclosure else None,
                light_cycle.get('light_duration') if light_cycle else None,
                light_cycle.get('dawn_dusk') if light_cycle else None,
                json.dumps(breeding_parents) if breeding_parents else None,
                dish_data.get('termination_date'),
                dish_data.get('termination_reason'),
                json.dumps(dish_data)  # Keep JSON for backward compatibility during transition
            ))

            # Update quality checks (within same transaction)
            self._save_quality_checks(cursor, dish_id, dish_data.get('quality_checks', {}))

            # Update screening steps (within same transaction)
            self._save_screening_steps(cursor, dish_id, dish_data.get('screening_results'))

            # Commit transaction - all or nothing
            conn.commit()

            logger.info(f"Successfully saved dish {dish_id} to database")
            return True

        except Exception as e:
            logger.error(f"Error saving dish {dish_id}: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

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

    def _save_screening_steps(self, cursor, dish_id: str, screening_results: Optional[Dict[str, Any]]):
        """Save screening steps for a dish to the normalized table."""
        # Delete existing screening steps for this dish
        cursor.execute("DELETE FROM screening_steps WHERE dish_id = ?", (dish_id,))

        if not screening_results:
            return

        # Insert screening steps
        screenings = screening_results.get('screenings', [])
        for step in screenings:
            cursor.execute("""
            INSERT INTO screening_steps
            (dish_id, screening_datetime, dpf_screened, indicator_screened,
             criteria, count_screened_this_step, number_positive,
             number_removed_pigmented, number_removed_negative, number_removed_other,
             tricaine_used, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dish_id,
                step.get('screening_datetime'),
                step.get('dpf_screened'),
                step.get('indicator_screened'),
                step.get('criteria'),
                step.get('count_screened_this_step'),
                step.get('number_positive'),
                step.get('number_removed_pigmented'),
                step.get('number_removed_negative'),
                step.get('number_removed_other'),
                step.get('tricaine_used', False),
                step.get('notes')
            ))

        # Update the dish's screening result columns
        cursor.execute("""
            UPDATE dishes
            SET screening_final_positive_count = ?,
                screening_date_finalized = ?
            WHERE dish_id = ?
        """, (
            screening_results.get('final_positive_count'),
            screening_results.get('date_finalized'),
            dish_id
        ))

    def get_screening_steps(self, dish_id: str) -> List[Dict[str, Any]]:
        """Get all screening steps for a dish from the normalized table."""
        if not self.is_initialized:
            return []

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT screening_datetime, dpf_screened, indicator_screened,
                           criteria, count_screened_this_step, number_positive,
                           number_removed_pigmented, number_removed_negative, number_removed_other,
                           tricaine_used, notes
                    FROM screening_steps
                    WHERE dish_id = ?
                    ORDER BY screening_datetime ASC
                """, (dish_id,))

                steps = []
                for row in cursor.fetchall():
                    steps.append({
                        'screening_datetime': row['screening_datetime'],
                        'dpf_screened': row['dpf_screened'],
                        'indicator_screened': row['indicator_screened'],
                        'criteria': row['criteria'],
                        'count_screened_this_step': row['count_screened_this_step'],
                        'number_positive': row['number_positive'],
                        'number_removed_pigmented': row['number_removed_pigmented'],
                        'number_removed_negative': row['number_removed_negative'],
                        'number_removed_other': row['number_removed_other'],
                        'tricaine_used': bool(row['tricaine_used']),
                        'notes': row['notes']
                    })
                return steps

        except Exception as e:
            logger.error(f"Error loading screening steps for dish {dish_id}: {e}")
            return []

    def _save_transgenic_indicators(self, cursor, cross_id: str, transgenic_details: Optional[Dict[str, Any]]):
        """Save transgenic indicators for a cross to the normalized table."""
        # Delete existing indicators for this cross
        cursor.execute("DELETE FROM transgenic_indicators WHERE cross_id = ?", (cross_id,))

        if not transgenic_details:
            return

        # Insert indicators
        indicators = transgenic_details.get('indicators', [])
        for indicator in indicators:
            cursor.execute("""
                INSERT INTO transgenic_indicators
                (cross_id, modification_type, promoter_driver, reporter_effector,
                 color, expected_expression)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cross_id,
                indicator.get('modification_type', 'tg'),
                indicator.get('promoter_driver'),
                indicator.get('reporter_effector'),
                indicator.get('color'),
                indicator.get('expected_expression')
            ))

        # Update the cross's aggregate columns if present
        aggregate_results = transgenic_details.get('aggregate_results')
        if aggregate_results:
            cursor.execute("""
                UPDATE crosses
                SET agg_total_initially_produced = ?,
                    agg_total_positive_final = ?,
                    agg_yield_percentage = ?,
                    agg_date_aggregated = ?
                WHERE cross_id = ?
            """, (
                aggregate_results.get('total_initially_produced'),
                aggregate_results.get('total_positive_final'),
                aggregate_results.get('yield_percentage'),
                aggregate_results.get('date_aggregated'),
                cross_id
            ))

    def get_transgenic_indicators(self, cross_id: str) -> List[Dict[str, Any]]:
        """Get all transgenic indicators for a cross from the normalized table."""
        if not self.is_initialized:
            return []

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT modification_type, promoter_driver, reporter_effector,
                           color, expected_expression
                    FROM transgenic_indicators
                    WHERE cross_id = ?
                    ORDER BY id ASC
                """, (cross_id,))

                indicators = []
                for row in cursor.fetchall():
                    indicators.append({
                        'modification_type': row['modification_type'],
                        'promoter_driver': row['promoter_driver'],
                        'reporter_effector': row['reporter_effector'],
                        'color': row['color'],
                        'expected_expression': row['expected_expression']
                    })
                return indicators

        except Exception as e:
            logger.error(f"Error loading transgenic indicators for cross {cross_id}: {e}")
            return []

    def save_cross(self, cross_data: Dict[str, Any]) -> bool:
        """Save a single cross to database.

        All database operations are wrapped in a transaction - if any operation
        fails, all changes are rolled back to maintain data integrity.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False

        cross_id = cross_data.get('cross_id')
        if not cross_id:
            logger.error("Cannot save cross: missing 'cross_id'")
            return False

        # Extract aggregate results (can be at top-level or in transgenic_details)
        aggregate_results = cross_data.get('aggregate_results')
        transgenic_details = cross_data.get('transgenic_details')
        if transgenic_details and transgenic_details.get('aggregate_results'):
            aggregate_results = transgenic_details.get('aggregate_results')

        conn = None
        try:
            conn = sqlite3.connect(str(self.database_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            # Begin explicit transaction
            cursor.execute("BEGIN TRANSACTION")

            # Extract parents list
            parents = cross_data.get('parents', [])

            cursor.execute("""
                INSERT OR REPLACE INTO crosses
                (cross_id, request_date, responsible_requestor, line_strain,
                 cross_type, cross_status, requested_groups, groups_produced,
                 notes, parents, data,
                 agg_total_initially_produced, agg_total_positive_final,
                 agg_yield_percentage, agg_date_aggregated, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                cross_id,
                cross_data.get('request_date'),
                cross_data.get('responsible_requestor'),
                cross_data.get('line_strain'),
                cross_data.get('cross_type'),
                cross_data.get('cross_status'),
                cross_data.get('requested_groups'),
                cross_data.get('groups_produced'),
                cross_data.get('notes'),
                json.dumps(parents) if parents else None,
                json.dumps(cross_data),  # Keep JSON for backward compatibility during transition
                aggregate_results.get('total_initially_produced') if aggregate_results else None,
                aggregate_results.get('total_positive_final') if aggregate_results else None,
                aggregate_results.get('yield_percentage') if aggregate_results else None,
                aggregate_results.get('date_aggregated') if aggregate_results else None
            ))

            # Save transgenic indicators (within same transaction)
            self._save_transgenic_indicators(cursor, cross_id, transgenic_details)

            # Commit transaction - all or nothing
            conn.commit()

            logger.info(f"Successfully saved cross {cross_id} to database")
            return True

        except Exception as e:
            logger.error(f"Error saving cross {cross_id}: {e}", exc_info=True)
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def load_single_dish(self, dish_id: str) -> Optional[Dict[str, Any]]:
        """Load a single dish by ID from database.

        Loads dish data primarily from flattened columns, supplemented with
        normalized screening_steps and quality_checks data.
        Falls back to JSON column for any fields not yet in columns.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT dish_id, cross_id, date_created, dof, genotype, responsible,
                           status, fish_count, species, sex, parent_dish_id, dish_population_type,
                           notes, room, enclosure_temperature, enclosure_in_beaker,
                           enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
                           breeding_parents, screening_final_positive_count, screening_date_finalized,
                           termination_date, termination_reason, data
                    FROM dishes WHERE dish_id = ?
                """, (dish_id,))
                row = cursor.fetchone()

                if row:
                    # Start with JSON data as base (for backward compatibility)
                    dish_data = json.loads(row['data']) if row['data'] else {}

                    # Override with flattened column values (columns are authoritative)
                    dish_data['dish_id'] = row['dish_id']
                    dish_data['cross_id'] = row['cross_id']
                    dish_data['date_created'] = row['date_created']
                    dish_data['dof'] = row['dof']
                    dish_data['genotype'] = row['genotype']
                    dish_data['responsible'] = row['responsible']
                    dish_data['status'] = row['status']
                    dish_data['fish_count'] = row['fish_count']
                    dish_data['species'] = row['species'] or 'Danio rerio'
                    dish_data['sex'] = row['sex'] or 'unknown'
                    dish_data['parent_dish_id'] = row['parent_dish_id']
                    dish_data['dish_population_type'] = row['dish_population_type']
                    dish_data['notes'] = row['notes']
                    dish_data['termination_date'] = row['termination_date']
                    dish_data['termination_reason'] = row['termination_reason']

                    # Reconstruct enclosure structure from flattened columns
                    dish_data['enclosure'] = {
                        'temperature': row['enclosure_temperature'],
                        'in_beaker': bool(row['enclosure_in_beaker']) if row['enclosure_in_beaker'] is not None else None,
                        'vol_water_total': row['enclosure_vol_water_total'],
                        'room': row['room'],
                        'light_cycle': {
                            'light_duration': row['enclosure_light_duration'],
                            'dawn_dusk': row['enclosure_dawn_dusk']
                        }
                    }

                    # Reconstruct breeding structure
                    breeding_parents = json.loads(row['breeding_parents']) if row['breeding_parents'] else []
                    dish_data['breeding'] = {'parents': breeding_parents}

                    # Load screening steps from normalized table
                    screening_steps = self.get_screening_steps(dish_id)
                    dish_data['screening_results'] = {
                        'screenings': screening_steps,
                        'final_positive_count': row['screening_final_positive_count'],
                        'date_finalized': row['screening_date_finalized']
                    }

                    # Quality checks are still loaded from the quality_checks table
                    # (already normalized, loaded via JSON for now but could be optimized)

                    return dish_data
                else:
                    logger.warning(f"Dish {dish_id} not found in database")
                    return None

        except Exception as e:
            logger.error(f"Error loading dish {dish_id}: {e}", exc_info=True)
            return None

    def load_single_cross(self, cross_id: str) -> Optional[Dict[str, Any]]:
        """Load a single cross by ID from database.

        Loads cross data primarily from flattened columns, supplemented with
        normalized transgenic_indicators data.
        Falls back to JSON column for any fields not yet in columns.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cross_id, request_date, responsible_requestor, line_strain,
                           cross_type, cross_status, requested_groups, groups_produced,
                           notes, parents, data,
                           agg_total_initially_produced, agg_total_positive_final,
                           agg_yield_percentage, agg_date_aggregated
                    FROM crosses WHERE cross_id = ?
                """, (cross_id,))
                row = cursor.fetchone()

                if row:
                    # Start with JSON data as base (for backward compatibility)
                    cross_data = json.loads(row['data']) if row['data'] else {}

                    # Override with flattened column values (columns are authoritative)
                    cross_data['cross_id'] = row['cross_id']
                    cross_data['request_date'] = row['request_date']
                    cross_data['responsible_requestor'] = row['responsible_requestor']
                    cross_data['line_strain'] = row['line_strain']
                    cross_data['cross_type'] = row['cross_type']
                    cross_data['cross_status'] = row['cross_status']
                    cross_data['requested_groups'] = row['requested_groups']
                    cross_data['groups_produced'] = row['groups_produced']
                    cross_data['notes'] = row['notes']

                    # Reconstruct parents from flattened column
                    if row['parents']:
                        cross_data['parents'] = json.loads(row['parents'])

                    # Load transgenic indicators from normalized table
                    indicators = self.get_transgenic_indicators(cross_id)

                    # If we have normalized transgenic data, use it
                    if indicators:
                        if cross_data.get('transgenic_details') is None:
                            cross_data['transgenic_details'] = {}
                        cross_data['transgenic_details']['indicators'] = indicators

                    # If we have normalized aggregate data, use it
                    if row['agg_total_initially_produced'] is not None:
                        aggregate_results = {
                            'total_initially_produced': row['agg_total_initially_produced'],
                            'total_positive_final': row['agg_total_positive_final'],
                            'yield_percentage': row['agg_yield_percentage'],
                            'date_aggregated': row['agg_date_aggregated']
                        }
                        # Store in transgenic_details if it exists, otherwise at top level
                        if cross_data.get('transgenic_details') is not None:
                            cross_data['transgenic_details']['aggregate_results'] = aggregate_results
                        else:
                            cross_data['aggregate_results'] = aggregate_results

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

    def _get_materials_from_db(self, material_type: str) -> Dict[str, Any]:
        """Get materials of a specific type from database."""
        if not self.is_initialized:
            return {}
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT material_id, data FROM materials WHERE material_type = ?",
                    (material_type,)
                )
                materials = {}
                for row in cursor.fetchall():
                    materials[row['material_id']] = json.loads(row['data'])
                return materials
        except Exception as e:
            logger.error(f"Error loading materials {material_type} from database: {e}")
            return {}

    def get_agarose_bottles(self) -> Dict[str, Any]:
        return self._get_materials_from_db('agarose_bottles')

    def get_agarose_solutions(self) -> Dict[str, Any]:
        return self._get_materials_from_db('agarose_solutions')

    def get_fish_water_batches(self) -> Dict[str, Any]:
        return self._get_materials_from_db('fish_water_sources')

    def get_fish_water_derivatives(self) -> Dict[str, Any]:
        return self._get_materials_from_db('fish_water_derivatives')

    def get_poly_l_serine_bottles(self) -> Dict[str, Any]:
        return self._get_materials_from_db('poly_l_serine_bottles')

    def get_poly_l_serine_derivatives(self) -> Dict[str, Any]:
        return self._get_materials_from_db('poly_l_serine_derivatives')

    def get_fish_dishes(self) -> Dict[str, Any]:
        """Get all fish dishes from database in a single bulk query."""
        if not self.is_initialized:
            return {}
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Single bulk query for all dishes
                cursor.execute("""
                    SELECT dish_id, cross_id, date_created, dof, genotype, responsible,
                           status, fish_count, species, sex, parent_dish_id, dish_population_type,
                           notes, room, enclosure_temperature, enclosure_in_beaker,
                           enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
                           breeding_parents, screening_final_positive_count, screening_date_finalized,
                           termination_date, termination_reason
                    FROM dishes
                """)

                dishes = {}
                for row in cursor.fetchall():
                    dish_id = row['dish_id']

                    # Reconstruct dish data from columns
                    dish_data = {
                        'dish_id': dish_id,
                        'cross_id': row['cross_id'],
                        'date_created': row['date_created'],
                        'dof': row['dof'],
                        'genotype': row['genotype'],
                        'responsible': row['responsible'],
                        'status': row['status'],
                        'fish_count': row['fish_count'],
                        'species': row['species'] or 'Danio rerio',
                        'sex': row['sex'] or 'unknown',
                        'parent_dish_id': row['parent_dish_id'],
                        'dish_population_type': row['dish_population_type'],
                        'notes': row['notes'],
                        'termination_date': row['termination_date'],
                        'termination_reason': row['termination_reason'],
                        'enclosure': {
                            'temperature': row['enclosure_temperature'],
                            'in_beaker': bool(row['enclosure_in_beaker']) if row['enclosure_in_beaker'] is not None else None,
                            'vol_water_total': row['enclosure_vol_water_total'],
                            'room': row['room'],
                            'light_cycle': {
                                'light_duration': row['enclosure_light_duration'],
                                'dawn_dusk': row['enclosure_dawn_dusk']
                            }
                        },
                        'breeding': {
                            'parents': json.loads(row['breeding_parents']) if row['breeding_parents'] else []
                        },
                        'screening_results': {
                            'screenings': [],  # Loaded separately if needed
                            'final_positive_count': row['screening_final_positive_count'],
                            'date_finalized': row['screening_date_finalized']
                        },
                        'quality_checks': {}  # Loaded separately if needed
                    }
                    dishes[dish_id] = dish_data

                return dishes
        except Exception as e:
            logger.error(f"Error loading dishes from database: {e}")
            return {}

    def get_crosses(self) -> Dict[str, Any]:
        """Get all crosses from database in a single bulk query."""
        if not self.is_initialized:
            return {}
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Single bulk query for all crosses
                cursor.execute("""
                    SELECT cross_id, request_date, responsible_requestor, line_strain,
                           cross_type, cross_status, requested_groups, groups_produced,
                           notes, parents, data,
                           agg_total_initially_produced, agg_total_positive_final,
                           agg_yield_percentage, agg_date_aggregated
                    FROM crosses
                """)

                crosses = {}
                for row in cursor.fetchall():
                    cross_id = row['cross_id']

                    # Start with JSON data as base (for backward compatibility)
                    cross_data = json.loads(row['data']) if row['data'] else {}

                    # Override with flattened column values (columns are authoritative)
                    cross_data['cross_id'] = cross_id
                    cross_data['request_date'] = row['request_date']
                    cross_data['responsible_requestor'] = row['responsible_requestor']
                    cross_data['line_strain'] = row['line_strain']
                    cross_data['cross_type'] = row['cross_type']
                    cross_data['cross_status'] = row['cross_status']
                    cross_data['requested_groups'] = row['requested_groups']
                    cross_data['groups_produced'] = row['groups_produced']
                    cross_data['notes'] = row['notes']

                    # Reconstruct parents from flattened column
                    if row['parents']:
                        cross_data['parents'] = json.loads(row['parents'])

                    # Include aggregate results if available
                    if row['agg_total_initially_produced'] is not None:
                        aggregate_results = {
                            'total_initially_produced': row['agg_total_initially_produced'],
                            'total_positive_final': row['agg_total_positive_final'],
                            'yield_percentage': row['agg_yield_percentage'],
                            'date_aggregated': row['agg_date_aggregated']
                        }
                        if cross_data.get('transgenic_details') is not None:
                            cross_data['transgenic_details']['aggregate_results'] = aggregate_results
                        else:
                            cross_data['aggregate_results'] = aggregate_results

                    crosses[cross_id] = cross_data

                return crosses
        except Exception as e:
            logger.error(f"Error loading crosses from database: {e}")
            return {}

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
        WHERE last_check < date('now', ?) OR last_check IS NULL
        ORDER BY last_check ASC
        """
        return self.execute_query(query, (f'-{days} days',))

    # --- Migration Functions ---

    def migrate_screening_data_to_normalized_table(self) -> Tuple[int, int]:
        """
        Migrate screening_results data from JSON column to normalized screening_steps table.

        Returns:
            Tuple of (dishes_processed, steps_migrated)
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return (0, 0)

        dishes_processed = 0
        steps_migrated = 0

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all dishes with their JSON data
                cursor.execute("SELECT dish_id, data FROM dishes")
                dishes = cursor.fetchall()

                for row in dishes:
                    dish_id = row['dish_id']
                    try:
                        dish_data = json.loads(row['data'])
                        screening_results = dish_data.get('screening_results')

                        if screening_results:
                            # Check if already migrated (screening_steps table has data for this dish)
                            cursor.execute(
                                "SELECT COUNT(*) FROM screening_steps WHERE dish_id = ?",
                                (dish_id,)
                            )
                            existing_count = cursor.fetchone()[0]

                            if existing_count == 0:
                                # Migrate screening steps
                                screenings = screening_results.get('screenings', [])
                                for step in screenings:
                                    cursor.execute("""
                                        INSERT OR IGNORE INTO screening_steps
                                        (dish_id, screening_datetime, dpf_screened, indicator_screened,
                                         criteria, count_screened_this_step, number_positive,
                                         tricaine_used, notes)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        dish_id,
                                        step.get('screening_datetime'),
                                        step.get('dpf_screened'),
                                        step.get('indicator_screened'),
                                        step.get('criteria'),
                                        step.get('count_screened_this_step'),
                                        step.get('number_positive'),
                                        step.get('tricaine_used', False),
                                        step.get('notes')
                                    ))
                                    steps_migrated += 1

                                # Update dish columns
                                cursor.execute("""
                                    UPDATE dishes
                                    SET screening_final_positive_count = ?,
                                        screening_date_finalized = ?
                                    WHERE dish_id = ?
                                """, (
                                    screening_results.get('final_positive_count'),
                                    screening_results.get('date_finalized'),
                                    dish_id
                                ))

                        dishes_processed += 1

                    except Exception as e:
                        logger.warning(f"Error migrating dish {dish_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Migration complete: {dishes_processed} dishes processed, "
                           f"{steps_migrated} screening steps migrated")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)

        return (dishes_processed, steps_migrated)

    def migrate_transgenic_data_to_normalized_table(self) -> Tuple[int, int]:
        """
        Migrate transgenic_details data from JSON column to normalized tables.

        Returns:
            Tuple of (crosses_processed, indicators_migrated)
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return (0, 0)

        crosses_processed = 0
        indicators_migrated = 0

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all crosses with their JSON data
                cursor.execute("SELECT cross_id, data FROM crosses")
                crosses = cursor.fetchall()

                for row in crosses:
                    cross_id = row['cross_id']
                    try:
                        cross_data = json.loads(row['data'])
                        transgenic_details = cross_data.get('transgenic_details')

                        if transgenic_details:
                            # Check if already migrated
                            cursor.execute(
                                "SELECT COUNT(*) FROM transgenic_indicators WHERE cross_id = ?",
                                (cross_id,)
                            )
                            existing_count = cursor.fetchone()[0]

                            if existing_count == 0:
                                # Migrate transgenic indicators
                                indicators = transgenic_details.get('indicators', [])
                                for indicator in indicators:
                                    cursor.execute("""
                                        INSERT OR IGNORE INTO transgenic_indicators
                                        (cross_id, modification_type, promoter_driver,
                                         reporter_effector, color, expected_expression)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (
                                        cross_id,
                                        indicator.get('modification_type', 'tg'),
                                        indicator.get('promoter_driver'),
                                        indicator.get('reporter_effector'),
                                        indicator.get('color'),
                                        indicator.get('expected_expression')
                                    ))
                                    indicators_migrated += 1

                                # Update aggregate columns
                                aggregate_results = transgenic_details.get('aggregate_results')
                                if aggregate_results:
                                    cursor.execute("""
                                        UPDATE crosses
                                        SET agg_total_initially_produced = ?,
                                            agg_total_positive_final = ?,
                                            agg_yield_percentage = ?,
                                            agg_date_aggregated = ?
                                        WHERE cross_id = ?
                                    """, (
                                        aggregate_results.get('total_initially_produced'),
                                        aggregate_results.get('total_positive_final'),
                                        aggregate_results.get('yield_percentage'),
                                        aggregate_results.get('date_aggregated'),
                                        cross_id
                                    ))

                        # Also check for top-level aggregate_results (non-transgenic crosses)
                        aggregate_results = cross_data.get('aggregate_results')
                        if aggregate_results and not transgenic_details:
                            cursor.execute("""
                                UPDATE crosses
                                SET agg_total_initially_produced = ?,
                                    agg_total_positive_final = ?,
                                    agg_yield_percentage = ?,
                                    agg_date_aggregated = ?
                                WHERE cross_id = ?
                            """, (
                                aggregate_results.get('total_initially_produced'),
                                aggregate_results.get('total_positive_final'),
                                aggregate_results.get('yield_percentage'),
                                aggregate_results.get('date_aggregated'),
                                cross_id
                            ))

                        crosses_processed += 1

                    except Exception as e:
                        logger.warning(f"Error migrating cross {cross_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Migration complete: {crosses_processed} crosses processed, "
                           f"{indicators_migrated} indicators migrated")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)

        return (crosses_processed, indicators_migrated)

    def migrate_dishes_to_flattened_columns(self) -> Tuple[int, int]:
        """
        Migrate dish data from JSON column to flattened columns.

        This extracts nested data (enclosure, breeding, notes, etc.) from the JSON
        column and populates the dedicated flattened columns.

        Returns:
            Tuple of (dishes_processed, dishes_updated)
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return (0, 0)

        dishes_processed = 0
        dishes_updated = 0

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all dishes with their JSON data
                cursor.execute("SELECT dish_id, data FROM dishes")
                dishes = cursor.fetchall()

                for row in dishes:
                    dish_id = row['dish_id']
                    try:
                        dish_data = json.loads(row['data']) if row['data'] else {}

                        # Extract nested data
                        enclosure = dish_data.get('enclosure', {}) or {}
                        light_cycle = enclosure.get('light_cycle', {}) or {}
                        breeding = dish_data.get('breeding', {}) or {}
                        breeding_parents = breeding.get('parents', []) or []

                        # Update flattened columns
                        cursor.execute("""
                            UPDATE dishes
                            SET species = COALESCE(species, ?),
                                sex = COALESCE(sex, ?),
                                parent_dish_id = COALESCE(parent_dish_id, ?),
                                dish_population_type = COALESCE(dish_population_type, ?),
                                notes = COALESCE(notes, ?),
                                room = COALESCE(room, ?),
                                enclosure_temperature = COALESCE(enclosure_temperature, ?),
                                enclosure_in_beaker = COALESCE(enclosure_in_beaker, ?),
                                enclosure_vol_water_total = COALESCE(enclosure_vol_water_total, ?),
                                enclosure_light_duration = COALESCE(enclosure_light_duration, ?),
                                enclosure_dawn_dusk = COALESCE(enclosure_dawn_dusk, ?),
                                breeding_parents = COALESCE(breeding_parents, ?)
                            WHERE dish_id = ?
                        """, (
                            dish_data.get('species', 'Danio rerio'),
                            dish_data.get('sex', 'unknown'),
                            dish_data.get('parent_dish_id'),
                            dish_data.get('dish_population_type'),
                            dish_data.get('notes'),
                            enclosure.get('room'),
                            enclosure.get('temperature'),
                            enclosure.get('in_beaker'),
                            enclosure.get('vol_water_total'),
                            light_cycle.get('light_duration'),
                            light_cycle.get('dawn_dusk'),
                            json.dumps(breeding_parents) if breeding_parents else None,
                            dish_id
                        ))

                        if cursor.rowcount > 0:
                            dishes_updated += 1

                        dishes_processed += 1

                    except Exception as e:
                        logger.warning(f"Error migrating dish {dish_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Dish flattening complete: {dishes_processed} dishes processed, "
                           f"{dishes_updated} dishes updated")

        except Exception as e:
            logger.error(f"Dish flattening migration failed: {e}", exc_info=True)

        return (dishes_processed, dishes_updated)

    def migrate_crosses_to_flattened_columns(self) -> Tuple[int, int]:
        """
        Migrate cross data from JSON column to flattened columns.

        This extracts data (requested_groups, groups_produced, notes, parents)
        from the JSON column and populates the dedicated flattened columns.

        Returns:
            Tuple of (crosses_processed, crosses_updated)
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return (0, 0)

        crosses_processed = 0
        crosses_updated = 0

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all crosses with their JSON data
                cursor.execute("SELECT cross_id, data FROM crosses")
                crosses = cursor.fetchall()

                for row in crosses:
                    cross_id = row['cross_id']
                    try:
                        cross_data = json.loads(row['data']) if row['data'] else {}

                        # Extract data for flattened columns
                        parents = cross_data.get('parents', []) or []

                        # Update flattened columns
                        cursor.execute("""
                            UPDATE crosses
                            SET requested_groups = COALESCE(requested_groups, ?),
                                groups_produced = COALESCE(groups_produced, ?),
                                notes = COALESCE(notes, ?),
                                parents = COALESCE(parents, ?)
                            WHERE cross_id = ?
                        """, (
                            cross_data.get('requested_groups'),
                            cross_data.get('groups_produced'),
                            cross_data.get('notes'),
                            json.dumps(parents) if parents else None,
                            cross_id
                        ))

                        if cursor.rowcount > 0:
                            crosses_updated += 1

                        crosses_processed += 1

                    except Exception as e:
                        logger.warning(f"Error migrating cross {cross_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Crosses flattening complete: {crosses_processed} crosses processed, "
                           f"{crosses_updated} crosses updated")

        except Exception as e:
            logger.error(f"Crosses flattening migration failed: {e}", exc_info=True)

        return (crosses_processed, crosses_updated)


# Create a singleton instance for global access
data_manager = DataManager()
