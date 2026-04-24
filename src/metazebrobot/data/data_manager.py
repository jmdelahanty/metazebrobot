"""
Data manager for MetaZebrobot - SQLite Database Version.

This module provides the main interface for accessing and manipulating application data
using SQLite with JSON columns for flexible NoSQL-style storage.
"""

import logging
import re
import sqlite3
import json
import uuid
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

    _CONSTRUCT_PATTERN = re.compile(
        r'(?:(\w+)\s*)?'
        r'\('
        r'([^)]+)'
        r'\)'
    )

    _PREFIX_TO_TYPE = {
        "tg": "tg",
        "tgbac": "tg",
        "et": "other",
    }

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

        return self.ensure_schema()

    def ensure_schema(self) -> bool:
        """Verify required tables exist and apply all known schema migrations."""
        if not self.database_path:
            logger.error("Database path not configured.")
            return False

        if not self.database_path.exists():
            logger.error(f"Database file not found: {self.database_path}")
            logger.error("Please run the migration script first!")
            return False

        # Test database connection and apply schema updates
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                expected_tables = ['dishes', 'quality_checks', 'materials']

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
                        indicators_screened TEXT,
                        pigment_screened BOOLEAN DEFAULT FALSE,
                        criteria TEXT,
                        count_screened_this_step INTEGER,
                        count_before_step INTEGER,
                        count_after_step INTEGER,
                        number_kept INTEGER,
                        number_removed_pigmented INTEGER,
                        number_removed_negative INTEGER,
                        number_removed_other INTEGER,
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
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS screening_step_allocations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        screening_datetime TEXT NOT NULL,
                        bucket TEXT NOT NULL,
                        disposition TEXT NOT NULL,
                        count INTEGER NOT NULL,
                        destination_dish_id TEXT,
                        derived_dish_id TEXT,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_dish_step
                    ON screening_step_allocations(dish_id, screening_datetime)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_derived_dish
                    ON screening_step_allocations(derived_dish_id)
                """)
                cursor.execute("PRAGMA table_info(screening_step_allocations)")
                allocation_cols = {row[1] for row in cursor.fetchall()}
                if 'destination_dish_id' not in allocation_cols:
                    cursor.execute("ALTER TABLE screening_step_allocations ADD COLUMN destination_dish_id TEXT")
                cursor.execute("""
                    UPDATE screening_step_allocations
                    SET destination_dish_id = derived_dish_id
                    WHERE destination_dish_id IS NULL
                      AND derived_dish_id IS NOT NULL
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_destination_dish
                    ON screening_step_allocations(destination_dish_id)
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dish_transfer_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_dish_id TEXT NOT NULL,
                        destination_dish_id TEXT NOT NULL,
                        cross_id TEXT NOT NULL,
                        count INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        event_datetime TEXT NOT NULL,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (source_dish_id) REFERENCES dishes(dish_id),
                        FOREIGN KEY (destination_dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_source
                    ON dish_transfer_events(source_dish_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_destination
                    ON dish_transfer_events(destination_dish_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_cross
                    ON dish_transfer_events(cross_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_datetime
                    ON dish_transfer_events(event_datetime)
                """)

                # Migrate screening_steps columns for new screening model
                cursor.execute("PRAGMA table_info(screening_steps)")
                screening_cols = {row[1] for row in cursor.fetchall()}
                if 'number_removed_pigmented' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_pigmented INTEGER")
                if 'number_removed_negative' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_negative INTEGER")
                if 'number_removed_other' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_removed_other INTEGER")
                if 'count_before_step' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN count_before_step INTEGER")
                if 'count_after_step' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN count_after_step INTEGER")
                # New columns: indicators_screened (JSON list), pigment_screened, number_kept
                if 'indicators_screened' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN indicators_screened TEXT")
                    # Migrate old indicator_screened → indicators_screened JSON array
                    if 'indicator_screened' in screening_cols:
                        cursor.execute("""
                            UPDATE screening_steps
                            SET indicators_screened = CASE
                                WHEN indicator_screened IS NOT NULL AND indicator_screened != ''
                                THEN '["' || indicator_screened || '"]'
                                ELSE '[]'
                            END
                            WHERE indicators_screened IS NULL
                        """)
                if 'pigment_screened' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN pigment_screened BOOLEAN DEFAULT FALSE")
                if 'number_kept' not in screening_cols:
                    cursor.execute("ALTER TABLE screening_steps ADD COLUMN number_kept INTEGER")
                    # Migrate: number_kept = number_positive where it existed
                    if 'number_positive' in screening_cols:
                        cursor.execute("""
                            UPDATE screening_steps
                            SET number_kept = number_positive
                            WHERE number_kept IS NULL AND number_positive IS NOT NULL
                        """)

                # Add screening result columns to dishes table (if not exist)
                # SQLite doesn't have ADD COLUMN IF NOT EXISTS, so we check first
                cursor.execute("PRAGMA table_info(dishes)")
                existing_columns = {row[1] for row in cursor.fetchall()}

                if 'screening_final_positive_count' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN screening_final_positive_count INTEGER")
                if 'screening_date_finalized' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN screening_date_finalized TEXT")
                if 'current_fish_count' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN current_fish_count INTEGER")
                cursor.execute("""
                    UPDATE dishes
                    SET current_fish_count = fish_count
                    WHERE current_fish_count IS NULL
                """)

                # Canonical construct/reporter registry
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS construct_catalog (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        canonical_name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL UNIQUE,
                        construct_role TEXT,
                        family TEXT,
                        target TEXT,
                        fluorophore TEXT,
                        excitation_nm INTEGER,
                        emission_nm INTEGER,
                        screen_color TEXT,
                        notes TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_construct_catalog_canonical_name
                    ON construct_catalog(canonical_name)
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS construct_aliases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        catalog_id INTEGER NOT NULL,
                        alias_name TEXT NOT NULL,
                        normalized_alias TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (catalog_id) REFERENCES construct_catalog(id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_construct_aliases_catalog_id
                    ON construct_aliases(catalog_id)
                """)

                # Crossing-level transgenic indicators (keyed by PyRAT crossing_id)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS crossing_transgenic_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        crossing_id TEXT NOT NULL,
                        modification_type TEXT DEFAULT 'tg',
                        promoter_driver TEXT,
                        promoter_norm TEXT,
                        reporter_effector TEXT NOT NULL,
                        reporter_norm TEXT,
                        fluorophore TEXT,
                        construct_role TEXT,
                        sensor_family TEXT,
                        sensor_target TEXT,
                        effector_family TEXT,
                        catalog_id INTEGER,
                        match_method TEXT,
                        color TEXT,
                        expected_expression TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (catalog_id) REFERENCES construct_catalog(id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crossing_tg_indicators_crossing_id
                    ON crossing_transgenic_indicators(crossing_id)
                """)
                cursor.execute("PRAGMA table_info(crossing_transgenic_indicators)")
                crossing_indicator_cols = {row[1] for row in cursor.fetchall()}
                if 'promoter_norm' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN promoter_norm TEXT")
                if 'reporter_norm' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN reporter_norm TEXT")
                if 'fluorophore' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN fluorophore TEXT")
                if 'construct_role' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN construct_role TEXT")
                if 'sensor_family' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN sensor_family TEXT")
                if 'sensor_target' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN sensor_target TEXT")
                if 'effector_family' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN effector_family TEXT")
                if 'catalog_id' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN catalog_id INTEGER")
                if 'match_method' not in crossing_indicator_cols:
                    cursor.execute("ALTER TABLE crossing_transgenic_indicators ADD COLUMN match_method TEXT")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crossing_tg_indicators_catalog_id
                    ON crossing_transgenic_indicators(catalog_id)
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dish_transgenes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        construct TEXT NOT NULL,
                        modification_type TEXT,
                        promoter TEXT NOT NULL,
                        reporter TEXT,
                        fluorophore TEXT,
                        construct_role TEXT,
                        sensor_family TEXT,
                        sensor_target TEXT,
                        effector_family TEXT,
                        catalog_id INTEGER,
                        source_type TEXT,
                        source_id TEXT,
                        match_method TEXT,
                        excitation_nm INTEGER,
                        emission_nm INTEGER,
                        fluorophore_color TEXT,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id),
                        FOREIGN KEY (catalog_id) REFERENCES construct_catalog(id),
                        UNIQUE(dish_id, construct)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transgenes_dish_id
                    ON dish_transgenes(dish_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transgenes_promoter
                    ON dish_transgenes(promoter)
                """)
                cursor.execute("PRAGMA table_info(dish_transgenes)")
                dish_transgene_cols = {row[1] for row in cursor.fetchall()}
                if 'modification_type' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN modification_type TEXT")
                if 'construct_role' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN construct_role TEXT")
                if 'sensor_family' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN sensor_family TEXT")
                if 'sensor_target' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN sensor_target TEXT")
                if 'effector_family' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN effector_family TEXT")
                if 'catalog_id' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN catalog_id INTEGER")
                if 'source_type' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN source_type TEXT")
                if 'source_id' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN source_id TEXT")
                if 'match_method' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN match_method TEXT")
                if 'excitation_nm' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN excitation_nm INTEGER")
                if 'emission_nm' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN emission_nm INTEGER")
                if 'fluorophore_color' not in dish_transgene_cols:
                    cursor.execute("ALTER TABLE dish_transgenes ADD COLUMN fluorophore_color TEXT")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transgenes_construct_role
                    ON dish_transgenes(construct_role)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transgenes_sensor_family
                    ON dish_transgenes(sensor_family)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_transgenes_catalog_id
                    ON dish_transgenes(catalog_id)
                """)

                # Add remaining columns to dishes table for full flattening
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
                if 'source_screening_datetime' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN source_screening_datetime TEXT")
                if 'source_screening_bucket' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN source_screening_bucket TEXT")
                if 'cross_setup_date' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN cross_setup_date TEXT")
                if 'dof_source' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN dof_source TEXT")
                if 'notes' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN notes TEXT")
                if 'room' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN room TEXT")

                # Enclosure fields (flattened)
                if 'enclosure_temperature' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_temperature REAL")
                if 'enclosure_in_beaker' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN enclosure_in_beaker BOOLEAN")
                # Migrate enclosure_in_beaker → container_type
                if 'container_type' not in existing_columns:
                    cursor.execute("ALTER TABLE dishes ADD COLUMN container_type TEXT")
                    # Backfill: in_beaker=True → "beaker", else → "petri_dish"
                    cursor.execute("""
                        UPDATE dishes SET container_type = CASE
                            WHEN enclosure_in_beaker = 1 THEN 'beaker'
                            ELSE 'petri_dish'
                        END
                        WHERE container_type IS NULL
                    """)
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
                cursor.execute("""
                    UPDATE dishes
                    SET termination_reason = 'euthanasia'
                    WHERE lower(trim(termination_reason)) = 'euthanasia'
                """)
                cursor.execute("""
                    UPDATE dishes
                    SET termination_reason = 'propagation'
                    WHERE lower(trim(termination_reason)) IN (
                        'propagation',
                        'aquatics propagation handoff',
                        'aquatics_propagation_handoff',
                        'handoff_to_aquatics_for_propagation',
                        'handed_off_to_aquatics_for_propagation',
                        'handed off to aquatics for propagation'
                    )
                """)

                # Phase 5: Add additional indexes for common query patterns
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_genotype ON dishes(genotype)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_responsible ON dishes(responsible)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_dof ON dishes(dof)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_date_created ON dishes(date_created)")

                # Screening step images (filesystem paths)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS screening_step_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        screening_datetime TEXT NOT NULL,
                        image_filename TEXT NOT NULL,
                        image_type TEXT DEFAULT 'screening',
                        caption TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_screening_images_dish_datetime
                    ON screening_step_images(dish_id, screening_datetime)
                """)

                # Individual fish tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fish_subjects (
                        fish_id TEXT PRIMARY KEY,
                        dish_id TEXT NOT NULL,
                        subject_label TEXT,
                        sex TEXT,
                        genotype TEXT,
                        species TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fish_subjects_dish_id
                    ON fish_subjects(dish_id)
                """)

                # Add current_unit_id to fish_subjects if not present
                cursor.execute("PRAGMA table_info(fish_subjects)")
                fish_cols = {row[1] for row in cursor.fetchall()}
                if 'current_unit_id' not in fish_cols:
                    cursor.execute(
                        "ALTER TABLE fish_subjects ADD COLUMN current_unit_id TEXT REFERENCES housing_units(unit_id)"
                    )

                # Housing units — physical positions within a dish
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS housing_units (
                        unit_id TEXT PRIMARY KEY,
                        dish_id TEXT NOT NULL,
                        position_label TEXT,
                        unit_kind TEXT NOT NULL DEFAULT 'open',
                        capacity INTEGER DEFAULT 1,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_housing_units_dish_id
                    ON housing_units(dish_id)
                """)

                # Per-position maintenance checks
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS housing_unit_checks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        unit_id TEXT NOT NULL,
                        check_time TEXT NOT NULL,
                        fed BOOLEAN,
                        feed_type TEXT,
                        water_changed BOOLEAN,
                        vol_water_changed INTEGER,
                        num_dead INTEGER DEFAULT 0,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (unit_id) REFERENCES housing_units(unit_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_housing_unit_checks_unit_id
                    ON housing_unit_checks(unit_id)
                """)

                # Fish occupancy history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS housing_unit_occupancy (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fish_id TEXT NOT NULL,
                        unit_id TEXT NOT NULL,
                        moved_in_at TEXT NOT NULL,
                        moved_out_at TEXT,
                        reason TEXT,
                        FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE,
                        FOREIGN KEY (unit_id) REFERENCES housing_units(unit_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_housing_occupancy_fish_id
                    ON housing_unit_occupancy(fish_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_housing_occupancy_unit_id
                    ON housing_unit_occupancy(unit_id)
                """)

                # Per-fish reference images
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fish_subject_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fish_id TEXT NOT NULL,
                        image_filename TEXT NOT NULL,
                        image_type TEXT DEFAULT 'reference',
                        caption TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fish_subject_images_fish_id
                    ON fish_subject_images(fish_id)
                """)

                # Dish-level reference images (for bulk populations without individual fish)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dish_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        image_filename TEXT NOT NULL,
                        image_type TEXT DEFAULT 'reference',
                        caption TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dish_images_dish_id
                    ON dish_images(dish_id)
                """)

                # Curated full-genotype reference images
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS genotype_reference_images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        genotype_key TEXT NOT NULL,
                        display_genotype TEXT NOT NULL,
                        image_filename TEXT NOT NULL,
                        caption TEXT,
                        source_image_id INTEGER,
                        source_dish_id TEXT,
                        source_fish_id TEXT,
                        channels_json TEXT,
                        notes TEXT,
                        is_active INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_genotype_reference_images_key
                    ON genotype_reference_images(genotype_key, is_active)
                """)

                conn.commit()
                logger.debug("Schema updates applied successfully")

        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

        # Mark as initialized
        self._is_initialized = True
        self.seed_construct_catalog()
        self.backfill_dish_transgenes()
        self.backfill_crossing_indicator_metadata()
        logger.info("DataManager schema is up to date.")
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
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
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
        Dynamic data (dishes, materials) is loaded on-demand from database.

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
            (dish_id, cross_id, date_created, dof, cross_setup_date, dof_source, genotype, responsible,
             status, fish_count, current_fish_count, species, sex, parent_dish_id, dish_population_type,
             source_screening_datetime, source_screening_bucket,
             notes, room, enclosure_temperature, container_type,
             enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
             breeding_parents, termination_date, termination_reason, data, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                dish_id,
                dish_data.get('cross_id'),
                dish_data.get('date_created'),
                dish_data.get('dof'),
                dish_data.get('cross_setup_date'),
                dish_data.get('dof_source'),
                dish_data.get('genotype'),
                dish_data.get('responsible'),
                dish_data.get('status', 'active'),
                dish_data.get('fish_count'),
                dish_data.get('current_fish_count', dish_data.get('fish_count')),
                dish_data.get('species', 'Danio rerio'),
                dish_data.get('sex', 'unknown'),
                dish_data.get('parent_dish_id'),
                dish_data.get('dish_population_type'),
                dish_data.get('source_screening_datetime'),
                dish_data.get('source_screening_bucket'),
                dish_data.get('notes'),
                enclosure.get('room') if enclosure else None,
                enclosure.get('temperature') if enclosure else None,
                enclosure.get('container_type', 'petri_dish') if enclosure else 'petri_dish',
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

            # Update normalized transgenes (within same transaction)
            self._save_dish_transgenes(cursor, dish_data)

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
        cursor.execute("DELETE FROM screening_step_allocations WHERE dish_id = ?", (dish_id,))

        if not screening_results:
            return

        # Insert screening steps
        screenings = screening_results.get('screenings', [])
        for step in screenings:
            # Serialize indicators_screened list to JSON
            indicators = step.get('indicators_screened', [])
            indicators_json = json.dumps(indicators) if isinstance(indicators, list) else indicators
            cursor.execute("""
            INSERT INTO screening_steps
            (dish_id, screening_datetime, dpf_screened, indicators_screened,
             pigment_screened, criteria, count_screened_this_step, count_before_step, count_after_step, number_kept,
             number_removed_pigmented, number_removed_negative, number_removed_other,
             tricaine_used, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dish_id,
                step.get('screening_datetime'),
                step.get('dpf_screened'),
                indicators_json,
                step.get('pigment_screened', False),
                step.get('criteria'),
                step.get('count_screened_this_step'),
                step.get('count_before_step'),
                step.get('count_after_step'),
                step.get('number_kept'),
                step.get('number_removed_pigmented'),
                step.get('number_removed_negative'),
                step.get('number_removed_other'),
                step.get('tricaine_used', False),
                step.get('notes')
            ))

            for allocation in step.get('allocations', []) or []:
                cursor.execute("""
                INSERT INTO screening_step_allocations
                (dish_id, screening_datetime, bucket, disposition, count, destination_dish_id, derived_dish_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dish_id,
                    step.get('screening_datetime'),
                    allocation.get('bucket'),
                    allocation.get('disposition'),
                    allocation.get('count'),
                    allocation.get('destination_dish_id') or allocation.get('derived_dish_id'),
                    allocation.get('derived_dish_id') or allocation.get('destination_dish_id'),
                    allocation.get('notes'),
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

    @staticmethod
    def _legacy_screening_step_allocations(step: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Derive fallback allocations from legacy kept/removed summary counts."""
        allocations: List[Dict[str, Any]] = []

        legacy_counts = [
            ("remaining_in_parent", "remain_parent", step.get("number_kept")),
            ("pigmented_screened", "discarded", step.get("number_removed_pigmented")),
            ("negative_screened", "discarded", step.get("number_removed_negative")),
            ("other", "discarded", step.get("number_removed_other")),
        ]

        for bucket, disposition, count in legacy_counts:
            if isinstance(count, int) and count > 0:
                allocations.append({
                    "bucket": bucket,
                    "disposition": disposition,
                    "count": count,
                    "destination_dish_id": None,
                    "derived_dish_id": None,
                    "notes": "Legacy summary migration",
                })

        return allocations

    def get_screening_step_allocations(self, dish_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get explicit outcome allocations grouped by screening step datetime."""
        if not self.is_initialized:
            return {}

        try:
            with self.get_connection() as conn:
                rows = conn.execute("""
                    SELECT
                        screening_datetime,
                        bucket,
                        disposition,
                        count,
                        destination_dish_id,
                        derived_dish_id,
                        notes
                    FROM screening_step_allocations
                    WHERE dish_id = ?
                    ORDER BY screening_datetime ASC, id ASC
                """, (dish_id,)).fetchall()

            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault(row["screening_datetime"], []).append({
                    "bucket": row["bucket"],
                    "disposition": row["disposition"],
                    "count": row["count"],
                    "destination_dish_id": row["destination_dish_id"] or row["derived_dish_id"],
                    "derived_dish_id": row["derived_dish_id"],
                    "notes": row["notes"],
                })
            return grouped
        except Exception as e:
            logger.error(f"Error loading screening step allocations for dish {dish_id}: {e}")
            return {}

    def _extra_incoming_allocation_count(
        self,
        conn: sqlite3.Connection,
        dish_id: str,
        parent_dish_id: Optional[str],
        source_screening_datetime: Optional[str],
        source_screening_bucket: Optional[str],
        fish_count: int,
    ) -> int:
        """Count incoming destination allocations beyond the dish's creation allocation."""
        rows = conn.execute("""
            SELECT dish_id, screening_datetime, bucket, count
            FROM screening_step_allocations
            WHERE disposition = 'derived_dish'
              AND COALESCE(destination_dish_id, derived_dish_id) = ?
        """, (dish_id,)).fetchall()

        incoming_total = sum(int(row["count"] or 0) for row in rows)
        if incoming_total <= 0:
            return 0

        creation_match_total = 0
        if parent_dish_id and source_screening_datetime:
            for row in rows:
                if (
                    row["dish_id"] == parent_dish_id
                    and row["screening_datetime"] == source_screening_datetime
                    and (not source_screening_bucket or row["bucket"] == source_screening_bucket)
                ):
                    creation_match_total += int(row["count"] or 0)

        creation_count = min(creation_match_total, fish_count or 0)
        return max(incoming_total - creation_count, 0)

    def _transfer_counts_for_dish(
        self,
        conn: sqlite3.Connection,
        dish_id: str,
    ) -> Tuple[int, int]:
        """Return incoming and outgoing dish-to-dish transfer counts for a dish."""
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN destination_dish_id = ? THEN count ELSE 0 END), 0) AS incoming,
                COALESCE(SUM(CASE WHEN source_dish_id = ? THEN count ELSE 0 END), 0) AS outgoing
            FROM dish_transfer_events
            WHERE destination_dish_id = ? OR source_dish_id = ?
        """, (dish_id, dish_id, dish_id, dish_id)).fetchone()
        return int(row["incoming"] or 0), int(row["outgoing"] or 0)

    def save_dish_transfer_event(self, transfer_data: Dict[str, Any]) -> bool:
        """Persist a dish-to-dish transfer event."""
        if not self.is_initialized:
            logger.error("DataManager not initialized. Cannot save transfer event.")
            return False

        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO dish_transfer_events
                    (source_dish_id, destination_dish_id, cross_id, count, reason, event_datetime, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    transfer_data["source_dish_id"],
                    transfer_data["destination_dish_id"],
                    transfer_data["cross_id"],
                    transfer_data["count"],
                    transfer_data["reason"],
                    transfer_data["event_datetime"],
                    transfer_data.get("notes"),
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving dish transfer event: {e}", exc_info=True)
            return False

    def get_dish_transfer_events(self, dish_id: str) -> List[Dict[str, Any]]:
        """Load transfer events where the dish was either source or destination."""
        if not self.is_initialized:
            return []

        try:
            with self.get_connection() as conn:
                rows = conn.execute("""
                    SELECT
                        id,
                        source_dish_id,
                        destination_dish_id,
                        cross_id,
                        count,
                        reason,
                        event_datetime,
                        notes,
                        created_at
                    FROM dish_transfer_events
                    WHERE source_dish_id = ? OR destination_dish_id = ?
                    ORDER BY event_datetime DESC, id DESC
                """, (dish_id, dish_id)).fetchall()
            return [{key: row[key] for key in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error loading dish transfer events for dish {dish_id}: {e}", exc_info=True)
            return []

    @staticmethod
    def _dish_transgene_source(dish_data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """Determine provenance for dish transgene rows."""
        if dish_data.get("parent_dish_id"):
            return "parent_dish", dish_data.get("parent_dish_id")
        if dish_data.get("cross_id"):
            return "crossing", dish_data.get("cross_id")
        return "manual_genotype", None

    def _save_dish_transgenes(self, cursor, dish_data: Dict[str, Any]):
        """Parse genotype and save normalized transgene rows with spectral data."""
        dish_id = dish_data.get("dish_id")
        genotype = dish_data.get("genotype", "")
        source_type, source_id = self._dish_transgene_source(dish_data)
        cursor.execute("DELETE FROM dish_transgenes WHERE dish_id = ?", (dish_id,))
        transgenes = self.parse_genotype(genotype)
        for tg in transgenes:
            spectra = self.get_fluorophore_spectra(tg.get("fluorophore"))
            catalog_id, match_method = self.resolve_construct_catalog_match(
                tg.get("reporter_raw") or tg.get("reporter")
            )
            cursor.execute("""
                INSERT OR IGNORE INTO dish_transgenes
                (dish_id, construct, modification_type, promoter, reporter, fluorophore,
                 construct_role, sensor_family, sensor_target, effector_family,
                 catalog_id, source_type, source_id, match_method,
                 excitation_nm, emission_nm, fluorophore_color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dish_id,
                tg["construct"],
                tg.get("modification_type"),
                tg["promoter"],
                tg["reporter"],
                tg["fluorophore"],
                tg.get("construct_role"),
                tg.get("sensor_family"),
                tg.get("sensor_target"),
                tg.get("effector_family"),
                catalog_id,
                source_type,
                source_id,
                match_method,
                spectra["ex"] if spectra else None,
                spectra["em"] if spectra else None,
                spectra["color"] if spectra else None,
            ))

    def backfill_dish_transgenes(self):
        """Populate missing or outdated normalized dish transgene rows."""
        if not self.is_initialized:
            return
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                rows = cursor.execute("""
                    SELECT dish_id, genotype, cross_id, parent_dish_id
                    FROM dishes
                    WHERE genotype IS NOT NULL
                """).fetchall()
                filled = 0
                for row in rows:
                    counts = cursor.execute(
                        """
                        SELECT
                            COUNT(*) AS total_count,
                            SUM(
                                CASE
                                    WHEN modification_type IS NOT NULL
                                         AND construct_role IS NOT NULL
                                         AND source_type IS NOT NULL
                                         AND match_method IS NOT NULL
                                    THEN 1 ELSE 0
                                END
                            ) AS normalized_count
                        FROM dish_transgenes
                        WHERE dish_id = ?
                        """,
                        (row["dish_id"],),
                    ).fetchone()
                    if counts["total_count"] and counts["total_count"] == (counts["normalized_count"] or 0):
                        continue
                    self._save_dish_transgenes(cursor, dict(row))
                    if row["genotype"]:
                        filled += 1
                conn.commit()
                if filled:
                    logger.info(f"Backfilled dish_transgenes for {filled} dishes")
        except Exception as e:
            logger.warning(f"dish_transgenes backfill failed (table may not exist yet): {e}")

    def backfill_crossing_indicator_metadata(self):
        """Populate normalized metadata columns for existing crossing indicators."""
        if not self.is_initialized:
            return
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                rows = cursor.execute("""
                    SELECT id, modification_type, promoter_driver, reporter_effector
                    FROM crossing_transgenic_indicators
                """).fetchall()
                updated = 0
                for row in rows:
                    modification_type = row["modification_type"] or "tg"
                    promoter_norm = (row["promoter_driver"] or "").strip().lower() or None
                    reporter_norm = (row["reporter_effector"] or "").strip().lower() or None
                    classified = self.classify_construct(modification_type, promoter_norm, reporter_norm)
                    catalog_id, match_method = self.resolve_construct_catalog_match(
                        row["reporter_effector"] or reporter_norm
                    )
                    cursor.execute("""
                        UPDATE crossing_transgenic_indicators
                        SET promoter_norm = ?,
                            reporter_norm = ?,
                            fluorophore = ?,
                            construct_role = ?,
                            sensor_family = ?,
                            sensor_target = ?,
                            effector_family = ?,
                            catalog_id = ?,
                            match_method = ?
                        WHERE id = ?
                    """, (
                        promoter_norm,
                        reporter_norm,
                        classified.get("fluorophore"),
                        classified.get("construct_role"),
                        classified.get("sensor_family"),
                        classified.get("sensor_target"),
                        classified.get("effector_family"),
                        catalog_id,
                        match_method,
                        row["id"],
                    ))
                    updated += 1
                conn.commit()
                if updated:
                    logger.info(f"Backfilled normalized metadata for {updated} crossing indicators")
        except Exception as e:
            logger.warning(f"crossing indicator metadata backfill failed: {e}")

    def get_dish_transgenes(self, dish_id: str) -> List[Dict[str, Any]]:
        """Get parsed transgenes for a dish with spectral data from the database."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT dt.construct,
                           dt.modification_type,
                           dt.promoter,
                           dt.reporter,
                           dt.fluorophore,
                           dt.construct_role,
                           dt.sensor_family,
                           dt.sensor_target,
                           dt.effector_family,
                           dt.catalog_id,
                           dt.source_type,
                           dt.source_id,
                           dt.match_method,
                           dt.excitation_nm,
                           dt.emission_nm,
                           dt.fluorophore_color,
                           cc.canonical_name AS catalog_name,
                           cc.construct_role AS catalog_construct_role,
                           cc.family AS catalog_family,
                           cc.target AS catalog_target,
                           cc.fluorophore AS catalog_fluorophore,
                           cc.excitation_nm AS catalog_excitation_nm,
                           cc.emission_nm AS catalog_emission_nm,
                           cc.screen_color AS catalog_screen_color,
                           cc.notes AS catalog_notes
                    FROM dish_transgenes dt
                    LEFT JOIN construct_catalog cc ON cc.id = dt.catalog_id
                    WHERE dt.dish_id = ?
                    ORDER BY dt.id ASC
                    """,
                    (dish_id,),
                ).fetchall()
                results = []
                for row in rows:
                    tg = {k: row[k] for k in row.keys()}
                    construct_role = tg.get("catalog_construct_role") or tg.get("construct_role")
                    catalog_family = tg.get("catalog_family")
                    if construct_role == "sensor" and catalog_family and not tg.get("sensor_family"):
                        tg["sensor_family"] = catalog_family
                    if construct_role == "effector" and catalog_family and not tg.get("effector_family"):
                        tg["effector_family"] = catalog_family
                    if construct_role and not tg.get("construct_role"):
                        tg["construct_role"] = construct_role
                    if tg.get("catalog_target") and not tg.get("sensor_target"):
                        tg["sensor_target"] = tg["catalog_target"]
                    if tg.get("catalog_fluorophore") and not tg.get("fluorophore"):
                        tg["fluorophore"] = tg["catalog_fluorophore"]

                    excitation_nm = tg.get("catalog_excitation_nm") or tg.get("excitation_nm")
                    emission_nm = tg.get("catalog_emission_nm") or tg.get("emission_nm")
                    screen_color = tg.get("catalog_screen_color") or tg.get("fluorophore_color")

                    tg["family"] = tg.get("sensor_family") or tg.get("effector_family") or catalog_family
                    tg["target"] = tg.get("sensor_target") or tg.get("catalog_target")
                    tg["screen_color"] = screen_color
                    tg["catalog_notes"] = tg.get("catalog_notes")

                    # Build spectra dict from DB columns (or None if not available)
                    if excitation_nm and emission_nm:
                        tg["spectra"] = {
                            "ex": excitation_nm,
                            "em": emission_nm,
                            "color": screen_color,
                        }
                    else:
                        tg["spectra"] = None
                    results.append(tg)
                return results
        except Exception as e:
            logger.error(f"Error querying dish transgenes: {e}")
            return []

    def get_screening_steps(self, dish_id: str) -> List[Dict[str, Any]]:
        """Get all screening steps for a dish from the normalized table."""
        if not self.is_initialized:
            return []

        try:
            allocations_by_step = self.get_screening_step_allocations(dish_id)
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT screening_datetime, dpf_screened, indicators_screened,
                           pigment_screened, criteria, count_screened_this_step,
                           count_before_step, count_after_step, number_kept,
                           number_removed_pigmented, number_removed_negative, number_removed_other,
                           tricaine_used, notes
                    FROM screening_steps
                    WHERE dish_id = ?
                    ORDER BY screening_datetime ASC
                """, (dish_id,))

                steps = []
                for row in cursor.fetchall():
                    indicators_raw = row['indicators_screened']
                    try:
                        indicators = json.loads(indicators_raw) if indicators_raw else []
                    except (json.JSONDecodeError, TypeError):
                        indicators = [indicators_raw] if indicators_raw else []
                    step = {
                        'screening_datetime': row['screening_datetime'],
                        'dpf_screened': row['dpf_screened'],
                        'indicators_screened': indicators,
                        'pigment_screened': bool(row['pigment_screened']),
                        'criteria': row['criteria'],
                        'count_screened_this_step': row['count_screened_this_step'],
                        'count_before_step': row['count_before_step'],
                        'count_after_step': row['count_after_step'],
                        'number_kept': row['number_kept'],
                        'number_removed_pigmented': row['number_removed_pigmented'],
                        'number_removed_negative': row['number_removed_negative'],
                        'number_removed_other': row['number_removed_other'],
                        'tricaine_used': bool(row['tricaine_used']),
                        'notes': row['notes']
                    }
                    step_allocations = allocations_by_step.get(row['screening_datetime'], [])
                    step['allocations'] = step_allocations or self._legacy_screening_step_allocations(step)
                    steps.append(step)
                return steps

        except Exception as e:
            logger.error(f"Error loading screening steps for dish {dish_id}: {e}")
            return []

    def save_crossing_indicators(self, crossing_id: str, indicators: List[Dict[str, Any]]) -> bool:
        """Save transgenic indicators for a PyRAT crossing.

        Replaces all existing indicators for the given crossing_id.

        Args:
            crossing_id: The PyRAT crossing ID.
            indicators: List of indicator dicts with keys: modification_type,
                        promoter_driver, reporter_effector, color, expected_expression.

        Returns:
            True if saved successfully.
        """
        if not self.is_initialized:
            return False

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("DELETE FROM crossing_transgenic_indicators WHERE crossing_id = ?", (crossing_id,))

                for ind in indicators:
                    modification_type = ind.get('modification_type') or 'tg'
                    promoter_norm = ind.get('promoter_norm') or (ind.get('promoter_driver') or '').strip().lower() or None
                    reporter_norm = ind.get('reporter_norm') or (ind.get('reporter_effector') or '').strip().lower() or None
                    classified = self.classify_construct(modification_type, promoter_norm, reporter_norm)
                    catalog_id, match_method = self.resolve_construct_catalog_match(
                        ind.get('reporter_effector') or reporter_norm
                    )
                    cursor.execute("""
                        INSERT INTO crossing_transgenic_indicators
                        (crossing_id, modification_type, promoter_driver, promoter_norm,
                         reporter_effector, reporter_norm, fluorophore, construct_role,
                         sensor_family, sensor_target, effector_family, catalog_id,
                         match_method, color, expected_expression)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        crossing_id,
                        modification_type,
                        ind.get('promoter_driver'),
                        promoter_norm,
                        ind.get('reporter_effector'),
                        reporter_norm,
                        ind.get('fluorophore') or classified.get('fluorophore'),
                        ind.get('construct_role') or classified.get('construct_role'),
                        ind.get('sensor_family') or classified.get('sensor_family'),
                        ind.get('sensor_target') or classified.get('sensor_target'),
                        ind.get('effector_family') or classified.get('effector_family'),
                        catalog_id,
                        match_method,
                        ind.get('color'),
                        ind.get('expected_expression')
                    ))

                conn.commit()
                logger.info(f"Saved {len(indicators)} indicators for crossing {crossing_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving crossing indicators for {crossing_id}: {e}")
            return False

    def get_crossing_indicators(self, crossing_id: str) -> List[Dict[str, Any]]:
        """Get transgenic indicators for a PyRAT crossing.

        Args:
            crossing_id: The PyRAT crossing ID.

        Returns:
            List of indicator dicts.
        """
        if not self.is_initialized:
            return []

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cti.modification_type,
                           cti.promoter_driver,
                           cti.promoter_norm,
                           cti.reporter_effector,
                           cti.reporter_norm,
                           cti.fluorophore,
                           cti.construct_role,
                           cti.sensor_family,
                           cti.sensor_target,
                           cti.effector_family,
                           cti.catalog_id,
                           cti.match_method,
                           cti.color,
                           cti.expected_expression,
                           cc.canonical_name AS catalog_name,
                           cc.construct_role AS catalog_construct_role,
                           cc.family AS catalog_family,
                           cc.target AS catalog_target,
                           cc.fluorophore AS catalog_fluorophore,
                           cc.excitation_nm AS catalog_excitation_nm,
                           cc.emission_nm AS catalog_emission_nm,
                           cc.screen_color AS catalog_screen_color,
                           cc.notes AS catalog_notes
                    FROM crossing_transgenic_indicators cti
                    LEFT JOIN construct_catalog cc ON cc.id = cti.catalog_id
                    WHERE crossing_id = ?
                    ORDER BY cti.id ASC
                """, (crossing_id,))

                indicators = []
                for row in cursor.fetchall():
                    construct_role = row['catalog_construct_role'] or row['construct_role']
                    sensor_family = row['sensor_family']
                    effector_family = row['effector_family']
                    if construct_role == 'sensor' and row['catalog_family'] and not sensor_family:
                        sensor_family = row['catalog_family']
                    if construct_role == 'effector' and row['catalog_family'] and not effector_family:
                        effector_family = row['catalog_family']
                    indicators.append({
                        'modification_type': row['modification_type'],
                        'promoter_driver': row['promoter_driver'],
                        'promoter_norm': row['promoter_norm'],
                        'reporter_effector': row['reporter_effector'],
                        'reporter_norm': row['reporter_norm'],
                        'fluorophore': row['catalog_fluorophore'] or row['fluorophore'],
                        'construct_role': construct_role,
                        'sensor_family': sensor_family,
                        'sensor_target': row['sensor_target'] or row['catalog_target'],
                        'effector_family': effector_family,
                        'catalog_id': row['catalog_id'],
                        'catalog_name': row['catalog_name'],
                        'catalog_notes': row['catalog_notes'],
                        'match_method': row['match_method'],
                        'spectra': {
                            'ex': row['catalog_excitation_nm'],
                            'em': row['catalog_emission_nm'],
                            'color': row['catalog_screen_color'],
                        } if row['catalog_excitation_nm'] and row['catalog_emission_nm'] else None,
                        'color': row['color'],
                        'expected_expression': row['expected_expression']
                    })
                return indicators

        except Exception as e:
            logger.error(f"Error loading crossing indicators for {crossing_id}: {e}")
            return []

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
                    SELECT dish_id, cross_id, date_created, dof, cross_setup_date, dof_source, genotype, responsible,
                           status, fish_count, current_fish_count, species, sex, parent_dish_id, dish_population_type,
                           source_screening_datetime, source_screening_bucket,
                           notes, room, enclosure_temperature, container_type,
                           enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
                           breeding_parents, screening_final_positive_count, screening_date_finalized,
                           termination_date, termination_reason, data
                    FROM dishes WHERE dish_id = ?
                """, (dish_id,))
                row = cursor.fetchone()

                if row:
                    # Start with JSON data as base (for backward compatibility)
                    dish_data = json.loads(row['data']) if row['data'] else {}

                    incoming_fish_count = self._extra_incoming_allocation_count(
                        conn,
                        dish_id=row['dish_id'],
                        parent_dish_id=row['parent_dish_id'],
                        source_screening_datetime=row['source_screening_datetime'],
                        source_screening_bucket=row['source_screening_bucket'],
                        fish_count=row['fish_count'] or 0,
                    )
                    incoming_transfer_count, outgoing_transfer_count = self._transfer_counts_for_dish(
                        conn,
                        row['dish_id'],
                    )

                    # Override with flattened column values (columns are authoritative)
                    dish_data['dish_id'] = row['dish_id']
                    dish_data['cross_id'] = row['cross_id']
                    dish_data['date_created'] = row['date_created']
                    dish_data['dof'] = row['dof']
                    dish_data['cross_setup_date'] = row['cross_setup_date']
                    dish_data['dof_source'] = row['dof_source']
                    dish_data['genotype'] = row['genotype']
                    dish_data['responsible'] = row['responsible']
                    dish_data['status'] = row['status']
                    dish_data['fish_count'] = row['fish_count']
                    dish_data['incoming_fish_count'] = incoming_fish_count
                    dish_data['incoming_transfer_count'] = incoming_transfer_count
                    dish_data['outgoing_transfer_count'] = outgoing_transfer_count
                    dish_data['current_fish_count'] = row['current_fish_count']
                    dish_data['species'] = row['species'] or 'Danio rerio'
                    dish_data['sex'] = row['sex'] or 'unknown'
                    dish_data['parent_dish_id'] = row['parent_dish_id']
                    dish_data['dish_population_type'] = row['dish_population_type']
                    dish_data['source_screening_datetime'] = row['source_screening_datetime']
                    dish_data['source_screening_bucket'] = row['source_screening_bucket']
                    dish_data['notes'] = row['notes']
                    dish_data['termination_date'] = row['termination_date']
                    dish_data['termination_reason'] = row['termination_reason']

                    # Reconstruct enclosure structure from flattened columns
                    dish_data['enclosure'] = {
                        'temperature': row['enclosure_temperature'],
                        'container_type': row['container_type'] or 'petri_dish',
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
            'poly_l_serine_derivatives', 'fish_dishes',
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
                    SELECT dish_id, cross_id, date_created, dof, cross_setup_date, dof_source, genotype, responsible,
                           status, fish_count, current_fish_count, species, sex, parent_dish_id, dish_population_type,
                           source_screening_datetime, source_screening_bucket,
                           notes, room, enclosure_temperature, container_type,
                           enclosure_vol_water_total, enclosure_light_duration, enclosure_dawn_dusk,
                           breeding_parents, screening_final_positive_count, screening_date_finalized,
                           termination_date, termination_reason
                    FROM dishes
                """)

                dishes = {}
                for row in cursor.fetchall():
                    dish_id = row['dish_id']
                    incoming_fish_count = self._extra_incoming_allocation_count(
                        conn,
                        dish_id=dish_id,
                        parent_dish_id=row['parent_dish_id'],
                        source_screening_datetime=row['source_screening_datetime'],
                        source_screening_bucket=row['source_screening_bucket'],
                        fish_count=row['fish_count'] or 0,
                    )
                    incoming_transfer_count, outgoing_transfer_count = self._transfer_counts_for_dish(
                        conn,
                        dish_id,
                    )

                    # Reconstruct dish data from columns
                    dish_data = {
                        'dish_id': dish_id,
                        'cross_id': row['cross_id'],
                        'date_created': row['date_created'],
                        'dof': row['dof'],
                        'cross_setup_date': row['cross_setup_date'],
                        'dof_source': row['dof_source'],
                        'genotype': row['genotype'],
                        'responsible': row['responsible'],
                        'status': row['status'],
                        'fish_count': row['fish_count'],
                        'incoming_fish_count': incoming_fish_count,
                        'incoming_transfer_count': incoming_transfer_count,
                        'outgoing_transfer_count': outgoing_transfer_count,
                        'current_fish_count': row['current_fish_count'],
                        'species': row['species'] or 'Danio rerio',
                        'sex': row['sex'] or 'unknown',
                        'parent_dish_id': row['parent_dish_id'],
                        'dish_population_type': row['dish_population_type'],
                        'source_screening_datetime': row['source_screening_datetime'],
                        'source_screening_bucket': row['source_screening_bucket'],
                        'notes': row['notes'],
                        'termination_date': row['termination_date'],
                        'termination_reason': row['termination_reason'],
                        'enclosure': {
                            'temperature': row['enclosure_temperature'],
                            'container_type': row['container_type'] or 'petri_dish',
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

    # --- Dish-Level Quality Checks (Web API) ---

    def save_dish_quality_check(self, dish_id: str, check_data: Dict[str, Any]) -> bool:
        """Save a single dish-level quality check."""
        if not self.is_initialized:
            return False
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO quality_checks
                    (dish_id, check_time, fed, feed_type, water_changed,
                     vol_water_changed, num_dead, notes, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dish_id,
                    check_data["check_time"],
                    check_data.get("fed", False),
                    check_data.get("feed_type"),
                    check_data.get("water_changed", False),
                    check_data.get("vol_water_changed"),
                    check_data.get("num_dead", 0),
                    check_data.get("notes"),
                    json.dumps(check_data),
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving quality check for {dish_id}: {e}")
            return False

    def get_dish_quality_checks(self, dish_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent quality checks for a dish."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute("""
                    SELECT check_time, fed, feed_type, water_changed,
                           vol_water_changed, num_dead, notes
                    FROM quality_checks
                    WHERE dish_id = ?
                    ORDER BY check_time DESC
                    LIMIT ?
                """, (dish_id, limit)).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying quality checks for {dish_id}: {e}")
            return []

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

    # --- mapzebrain Atlas Integration ---

    _MAPZEBRAIN_CATALOG_URL = (
        "https://api.mapzebrain.org/media/downloads/Lines/markers_catalog.json"
    )
    _MAPZEBRAIN_IMAGE_BASE = (
        "https://api.mapzebrain.org/media/Lines"
    )
    _mapzebrain_catalog: Optional[List[Dict[str, Any]]] = None

    def fetch_mapzebrain_catalog(self) -> List[Dict[str, Any]]:
        """Fetch and cache the mapzebrain markers catalog.

        On first call per process, prefers a live API refresh and falls back
        to the cached ``config/mapzebrain_catalog.json`` copy on failure.
        Returns an empty list if neither source is available — the external
        dependency must never block screening.
        """
        if self._mapzebrain_catalog is not None:
            return self._mapzebrain_catalog

        cache_path = self.config_dir / "mapzebrain_catalog.json" if self.config_dir else None
        cached_data: Optional[List[Dict[str, Any]]] = None

        # Load disk cache as a fallback candidate.
        if cache_path and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text())
                if isinstance(data, list):
                    cached_data = data
            except Exception as e:
                logger.warning(f"Failed to read mapzebrain cache: {e}")

        # Prefer a live fetch so the catalog stays fresh across restarts.
        try:
            import urllib.request
            req = urllib.request.Request(
                self._MAPZEBRAIN_CATALOG_URL,
                headers={"User-Agent": "MetaZebrobot/0.1"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if isinstance(data, list):
                DataManager._mapzebrain_catalog = data
                logger.info(f"Fetched mapzebrain catalog ({len(data)} markers)")
                # Cache to disk
                if cache_path:
                    try:
                        cache_path.write_text(json.dumps(data))
                    except Exception as e:
                        logger.warning(f"Failed to write mapzebrain cache: {e}")
                return data
        except Exception as e:
            logger.warning(f"Failed to fetch mapzebrain catalog: {e}")

        if cached_data is not None:
            DataManager._mapzebrain_catalog = cached_data
            logger.info(f"Loaded mapzebrain catalog from cache ({len(cached_data)} markers)")
            return cached_data

        DataManager._mapzebrain_catalog = []
        return []

    def lookup_mapzebrain_lines(
        self,
        genotype: Optional[str] = None,
        dish_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Find mapzebrain atlas entries matching a genotype.

        Can use either a raw genotype string (parsed on the fly) or a
        ``dish_id`` (reads pre-parsed transgenes from ``dish_transgenes``).
        If both are provided, ``dish_id`` takes precedence.

        Returns a list of dicts with ``name``, ``folder``, and ``url`` keys.
        """
        catalog = self.fetch_mapzebrain_catalog()
        if not catalog:
            return []

        # Get search terms from transgenes table or by parsing
        if dish_id:
            tgs = self.get_dish_transgenes(dish_id)
            search_terms = [(t["promoter"], t["reporter"] or "") for t in tgs]
        elif genotype:
            search_terms = self._parse_genotype_terms(genotype)
        else:
            return []

        if not search_terms:
            return []

        results = []
        seen_folders = set()
        for term_promoter, term_reporter in search_terms:
            best = self._find_best_catalog_match(catalog, term_promoter, term_reporter)
            if best and best["folder"] not in seen_folders:
                seen_folders.add(best["folder"])
                results.append(best)

        return results

    # Known fluorophore patterns (lowercase) → canonical name
    _FLUOROPHORE_PATTERNS = [
        ("gcamp", "gcamp"),
        ("jrgeco", "jrgeco"),
        ("rgeco", "rgeco"),
        ("campari", "campari"),
        ("mcherry", "mcherry"),
        ("dsred", "dsred"),
        ("tagrfp", "rfp"),
        ("h2brfp", "rfp"),
        ("rfp", "rfp"),
        ("cerulean", "cerulean"),
        ("cer", "cerulean"),
        ("egfp", "gfp"),
        ("gfp", "gfp"),
        ("yfp", "yfp"),
        ("cfp", "cfp"),
        ("bfp", "bfp"),
        ("tdtomato", "tdtomato"),
    ]

    # Excitation/emission wavelengths (nm) for canonical fluorophores
    _FLUOROPHORE_SPECTRA = {
        "gfp":       {"ex": 488, "em": 509, "color": "green"},
        "egfp":      {"ex": 488, "em": 507, "color": "green"},
        "gcamp":     {"ex": 488, "em": 509, "color": "green"},
        "yfp":       {"ex": 514, "em": 527, "color": "yellow"},
        "cfp":       {"ex": 434, "em": 477, "color": "cyan"},
        "bfp":       {"ex": 383, "em": 448, "color": "blue"},
        "cerulean":  {"ex": 433, "em": 475, "color": "cyan"},
        "mcherry":   {"ex": 587, "em": 610, "color": "red"},
        "dsred":     {"ex": 558, "em": 583, "color": "red"},
        "tdtomato":  {"ex": 554, "em": 581, "color": "red"},
        "rfp":       {"ex": 555, "em": 584, "color": "red"},
        "jrgeco":    {"ex": 565, "em": 600, "color": "red"},
        "rgeco":     {"ex": 561, "em": 589, "color": "red"},
        "campari":   {"ex": 488, "em": 513, "color": "green"},  # green form; photoconverts to red
    }

    _EFFECTOR_PATTERNS = [
        ("trpv1", "TRPV1"),
        ("cochr", "CoChR"),
        ("chrimson", "Chrimson"),
        ("reachr", "ReaChR"),
        ("arch", "Arch"),
        ("ntr", "NTR"),
        ("cre", "Cre"),
        ("cas9", "Cas9"),
    ]

    _GRAB_TARGET_PATTERNS = [
        ("5-ht", "serotonin"),
        ("5ht", "serotonin"),
        ("serotonin", "serotonin"),
        ("dopamine", "dopamine"),
        ("da", "dopamine"),
        ("acetylcholine", "acetylcholine"),
        ("ach", "acetylcholine"),
        ("norepinephrine", "norepinephrine"),
        ("ne", "norepinephrine"),
        ("atp", "ATP"),
    ]

    @staticmethod
    def _normalize_construct_name(value: Optional[str]) -> Optional[str]:
        """Normalize construct/reporter names for catalog matching."""
        if not value:
            return None
        normalized = re.sub(r'[^a-z0-9]+', '', value.lower())
        return normalized or None

    def _load_construct_catalog_seed(self) -> List[Dict[str, Any]]:
        """Load bundled construct catalog seed data from config."""
        if not self.config_dir:
            return []
        seed_path = self.config_dir / "construct_catalog.json"
        payload = load_json_file(seed_path)
        if not payload:
            return []
        constructs = payload.get("constructs") if isinstance(payload, dict) else payload
        return constructs if isinstance(constructs, list) else []

    def seed_construct_catalog(self):
        """Upsert bundled starter construct catalog rows and aliases."""
        if not self.is_initialized:
            return

        constructs = self._load_construct_catalog_seed()
        if not constructs:
            return

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for entry in constructs:
                    canonical_name = entry.get("canonical_name")
                    normalized_name = self._normalize_construct_name(
                        entry.get("normalized_name") or canonical_name
                    )
                    if not canonical_name or not normalized_name:
                        continue

                    cursor.execute("""
                        INSERT INTO construct_catalog
                            (canonical_name, normalized_name, construct_role, family, target,
                             fluorophore, excitation_nm, emission_nm, screen_color, notes, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(normalized_name) DO UPDATE SET
                            canonical_name = excluded.canonical_name,
                            construct_role = excluded.construct_role,
                            family = excluded.family,
                            target = excluded.target,
                            fluorophore = excluded.fluorophore,
                            excitation_nm = excluded.excitation_nm,
                            emission_nm = excluded.emission_nm,
                            screen_color = excluded.screen_color,
                            notes = excluded.notes,
                            is_active = excluded.is_active,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        canonical_name,
                        normalized_name,
                        entry.get("construct_role"),
                        entry.get("family"),
                        entry.get("target"),
                        entry.get("fluorophore"),
                        entry.get("excitation_nm"),
                        entry.get("emission_nm"),
                        entry.get("screen_color"),
                        entry.get("notes"),
                        entry.get("is_active", True),
                    ))

                    catalog_row = cursor.execute(
                        "SELECT id FROM construct_catalog WHERE normalized_name = ?",
                        (normalized_name,),
                    ).fetchone()
                    if not catalog_row:
                        continue
                    catalog_id = catalog_row["id"]

                    aliases = set(entry.get("aliases") or [])
                    aliases.add(canonical_name)
                    for alias in aliases:
                        normalized_alias = self._normalize_construct_name(alias)
                        if not alias or not normalized_alias:
                            continue
                        cursor.execute("""
                            INSERT INTO construct_aliases (catalog_id, alias_name, normalized_alias)
                            VALUES (?, ?, ?)
                            ON CONFLICT(normalized_alias) DO UPDATE SET
                                catalog_id = excluded.catalog_id,
                                alias_name = excluded.alias_name
                        """, (catalog_id, alias, normalized_alias))

                conn.commit()
        except Exception as e:
            logger.warning(f"construct catalog seed failed: {e}")

    def resolve_construct_catalog_match(self, reporter: Optional[str]) -> Tuple[Optional[int], str]:
        """Resolve a reporter/effector string to a construct catalog row."""
        normalized = self._normalize_construct_name(reporter)
        if not normalized:
            return None, "unmatched"

        try:
            with self.get_connection() as conn:
                row = conn.execute("""
                    SELECT catalog_id
                    FROM construct_aliases
                    WHERE normalized_alias = ?
                """, (normalized,)).fetchone()
                if row:
                    return row["catalog_id"], "alias_exact"
        except Exception as e:
            logger.warning(f"construct catalog lookup failed for {reporter}: {e}")
        return None, "unmatched"

    @classmethod
    def get_fluorophore_spectra(cls, fluorophore: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return excitation/emission/color for a canonical fluorophore name."""
        if not fluorophore:
            return None
        return cls._FLUOROPHORE_SPECTRA.get(fluorophore)

    @staticmethod
    def _extract_fluorophore(reporter: str) -> Optional[str]:
        """Extract the canonical fluorophore name from a reporter string.

        Best-effort: checks the reporter (lowercase) against known fluorophore
        patterns.  Returns None for unrecognized reporters.
        """
        if not reporter:
            return None
        reporter_lower = reporter.lower()
        for pattern, canonical in DataManager._FLUOROPHORE_PATTERNS:
            if pattern in reporter_lower:
                return canonical
        return None

    @staticmethod
    def _infer_sensor_target(reporter: str, sensor_family: Optional[str]) -> Optional[str]:
        """Infer the sensed biological target for known sensor families."""
        if not reporter or not sensor_family:
            return None

        reporter_lower = reporter.lower()
        if sensor_family in {"GCaMP", "jRGECO", "RGECO"}:
            return "calcium"
        if sensor_family == "CaMPARI":
            return "neural_activity"
        if sensor_family == "GRAB":
            for pattern, target in DataManager._GRAB_TARGET_PATTERNS:
                if pattern in reporter_lower:
                    return target
            return "unknown"
        return None

    @staticmethod
    def _infer_effector_family(reporter: str) -> Optional[str]:
        """Infer a known effector family from reporter text."""
        if not reporter:
            return None

        reporter_lower = reporter.lower()
        for pattern, family in DataManager._EFFECTOR_PATTERNS:
            if pattern in reporter_lower:
                return family
        return None

    @staticmethod
    def classify_construct(
        modification_type: Optional[str],
        promoter: Optional[str],
        reporter: Optional[str],
    ) -> Dict[str, Optional[str]]:
        """Classify a construct into normalized metadata fields."""
        normalized_reporter = (reporter or "").strip().lower()
        fluorophore = DataManager._extract_fluorophore(normalized_reporter)
        sensor_family: Optional[str] = None
        construct_role: Optional[str] = None

        if not normalized_reporter:
            construct_role = "driver"
        elif "grab" in normalized_reporter:
            construct_role = "sensor"
            sensor_family = "GRAB"
        elif "gcamp" in normalized_reporter:
            construct_role = "sensor"
            sensor_family = "GCaMP"
        elif "jrgeco" in normalized_reporter:
            construct_role = "sensor"
            sensor_family = "jRGECO"
        elif "rgeco" in normalized_reporter:
            construct_role = "sensor"
            sensor_family = "RGECO"
        elif "campari" in normalized_reporter:
            construct_role = "sensor"
            sensor_family = "CaMPARI"

        sensor_target = DataManager._infer_sensor_target(normalized_reporter, sensor_family)
        effector_family = None

        if not construct_role:
            effector_family = DataManager._infer_effector_family(normalized_reporter)
            if effector_family:
                construct_role = "effector"
            elif fluorophore:
                construct_role = "fluorescent_reporter"
            elif modification_type == "other" and promoter:
                construct_role = "other"
            else:
                construct_role = "unknown"

        return {
            "fluorophore": fluorophore,
            "construct_role": construct_role,
            "sensor_family": sensor_family,
            "sensor_target": sensor_target,
            "effector_family": effector_family,
        }

    @staticmethod
    def parse_genotype(genotype: str) -> List[Dict[str, Optional[str]]]:
        """Parse a genotype string into structured transgene dicts.

        Extracts parenthesized construct blocks (for example ``Tg(...)`` or
        ``Et(...)``) and returns normalized rows like::

            {"construct": "Tg(elavl3:jRGECO1b)",
             "modification_type": "tg",
             "promoter": "elavl3",
             "reporter": "jrgeco1b",
             "fluorophore": "jrgeco",
             "construct_role": "sensor",
             "sensor_family": "jRGECO",
             "sensor_target": "calcium"}

        Non-transgenic genotypes (e.g. ``"wt"``) return an empty list.
        Parsing is best-effort and never raises.
        """
        results = []
        if not genotype:
            return results

        for match in DataManager._CONSTRUCT_PATTERN.finditer(genotype):
            prefix = match.group(1)
            inner = match.group(2)
            full_match = match.group(0)
            parts = inner.split(":", 1)
            promoter_raw = parts[0].strip() if parts else ""
            reporter_raw = parts[1].strip() if len(parts) > 1 else ""
            promoter = promoter_raw.lower() if promoter_raw else None
            reporter = reporter_raw.lower() if reporter_raw else None

            if not promoter:
                continue

            modification_type = DataManager._PREFIX_TO_TYPE.get((prefix or "tg").lower(), "other")
            classified = DataManager.classify_construct(modification_type, promoter, reporter)
            results.append({
                "construct": full_match,
                "modification_type": modification_type,
                "promoter": promoter,
                "promoter_raw": promoter_raw or None,
                "reporter": reporter,
                "reporter_raw": reporter_raw or None,
                **classified,
            })
        return results

    @staticmethod
    def _parse_genotype_terms(genotype: str) -> List[tuple]:
        """Extract (promoter, reporter) pairs from a genotype string.

        Legacy wrapper around :meth:`parse_genotype` for mapzebrain lookup.
        """
        return [
            (t["promoter"], t["reporter"] or "")
            for t in DataManager.parse_genotype(genotype)
        ]

    def _find_best_catalog_match(
        self,
        catalog: List[Dict[str, Any]],
        promoter: str,
        reporter: str,
    ) -> Optional[Dict[str, str]]:
        """Find the best catalog entry for a promoter+reporter pair."""
        candidates = []
        gene_expression_candidates = []
        normalized_promoter = self._normalize_construct_name(promoter)
        for entry in catalog:
            synonyms = (entry.get("synonyms") or "").lower()
            name = (entry.get("name") or "").lower()
            search_text = f"{name} {synonyms}"

            # Extract folder from stack URL
            stack_url = entry.get("stack", "")
            if "/Lines/" not in stack_url:
                continue
            folder = stack_url.split("/Lines/")[1].split("/")[0]

            category = (entry.get("category") or "").lower()
            normalized_name = self._normalize_construct_name(entry.get("name"))
            if (
                category == "gene expression"
                and normalized_promoter
                and normalized_name == normalized_promoter
            ):
                gene_expression_candidates.append({
                    "name": entry.get("name", ""),
                    "display_name": entry.get("name", "") or promoter,
                    "folder": folder,
                    "url": f"{self._MAPZEBRAIN_IMAGE_BASE}/{folder}/average_data/orthogonal_views/dorsal/180.jpg",
                })
                continue

            if promoter not in search_text:
                continue

            # Require a reporter hit for reporter-bearing genotypes.
            score = 0
            if reporter:
                # Check if reporter terms appear in folder or synonyms
                reporter_parts = re.split(r'[-_]', reporter)
                for part in reporter_parts:
                    if len(part) >= 3 and part in folder.lower():
                        score += 2
                    elif len(part) >= 3 and part in search_text:
                        score += 1
                if score <= 0:
                    continue
            else:
                continue

            candidates.append({
                "name": entry.get("name", ""),
                "display_name": entry.get("name", "") or f"{promoter}:{folder}",
                "folder": folder,
                "url": f"{self._MAPZEBRAIN_IMAGE_BASE}/{folder}/average_data/orthogonal_views/dorsal/180.jpg",
                "_score": score,
            })

        if not candidates:
            return gene_expression_candidates[0] if gene_expression_candidates else None

        # Return highest-scoring match
        candidates.sort(key=lambda c: c["_score"], reverse=True)
        best = candidates[0]
        del best["_score"]
        return best

    # --- Screening Step Images ---

    def save_screening_image(
        self,
        dish_id: str,
        screening_datetime: str,
        image_filename: str,
        image_type: str = "screening",
        caption: Optional[str] = None,
    ) -> bool:
        """Insert a row into screening_step_images linking an image file to a step."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO screening_step_images
                        (dish_id, screening_datetime, image_filename, image_type, caption)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (dish_id, screening_datetime, image_filename, image_type, caption),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving screening image record: {e}")
            return False

    def get_screening_images(
        self,
        dish_id: str,
        screening_datetime: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query images for a dish, optionally filtered to a specific screening step."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                if screening_datetime:
                    rows = conn.execute(
                        """
                        SELECT id, dish_id, screening_datetime, image_filename,
                               image_type, caption, created_at
                        FROM screening_step_images
                        WHERE dish_id = ? AND screening_datetime = ?
                        ORDER BY created_at
                        """,
                        (dish_id, screening_datetime),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, dish_id, screening_datetime, image_filename,
                               image_type, caption, created_at
                        FROM screening_step_images
                        WHERE dish_id = ?
                        ORDER BY screening_datetime, created_at
                        """,
                        (dish_id,),
                    ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying screening images: {e}")
            return []

    # --- Fish Subject Tracking ---

    def create_fish_subject(
        self,
        dish_id: str,
        fish_id: Optional[str] = None,
        subject_label: Optional[str] = None,
        sex: Optional[str] = None,
        genotype: Optional[str] = None,
        species: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new fish subject.

        If fish_id is provided (e.g. minted by Citrus at acquisition time),
        it is used as-is.  Otherwise a new UUID v4 is generated server-side.

        Returns the fish_id on success, None on failure.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None
        fish_id = fish_id or str(uuid.uuid4())
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO fish_subjects
                        (fish_id, dish_id, subject_label, sex, genotype, species, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (fish_id, dish_id, subject_label, sex, genotype, species, notes),
                )
                conn.commit()
                return fish_id
        except Exception as e:
            logger.error(f"Error creating fish subject: {e}")
            return None

    def get_fish_subjects(self, dish_id: str) -> List[Dict[str, Any]]:
        """List all fish subjects for a dish, ordered by created_at."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT fish_id, dish_id, subject_label, sex, genotype,
                           species, created_at, notes, current_unit_id
                    FROM fish_subjects
                    WHERE dish_id = ?
                    ORDER BY created_at
                    """,
                    (dish_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying fish subjects: {e}")
            return []

    def get_crosses_with_fish_counts(self) -> List[Dict[str, Any]]:
        """List all crosses that have at least one registered fish, with counts."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT d.cross_id,
                           COUNT(DISTINCT d.dish_id) AS dish_count,
                           COUNT(f.fish_id) AS fish_count,
                           d.genotype
                    FROM dishes d
                    JOIN fish_subjects f ON f.dish_id = d.dish_id
                    WHERE d.cross_id IS NOT NULL
                    GROUP BY d.cross_id
                    ORDER BY d.cross_id DESC
                    """,
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying crosses with fish counts: {e}")
            return []

    def get_dishes_for_cross(self, cross_id: str) -> List[Dict[str, Any]]:
        """List dishes for a cross with fish counts and parent/child metadata."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT d.dish_id, d.cross_id, d.genotype, d.status,
                           d.parent_dish_id, d.dish_population_type,
                           d.source_screening_datetime, d.source_screening_bucket,
                           COUNT(f.fish_id) AS fish_count
                    FROM dishes d
                    LEFT JOIN fish_subjects f ON f.dish_id = d.dish_id
                    WHERE d.cross_id = ?
                    GROUP BY d.dish_id
                    ORDER BY d.parent_dish_id NULLS FIRST, d.dish_id
                    """,
                    (cross_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying dishes for cross: {e}")
            return []

    def get_fish_subjects_for_cross(self, cross_id: str) -> List[Dict[str, Any]]:
        """List all fish subjects across every dish belonging to a cross."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT f.fish_id, f.dish_id, f.subject_label, f.sex,
                           f.genotype, f.species, f.created_at, f.notes,
                           f.current_unit_id, d.cross_id,
                           d.parent_dish_id, d.dish_population_type
                    FROM fish_subjects f
                    JOIN dishes d ON d.dish_id = f.dish_id
                    WHERE d.cross_id = ?
                    ORDER BY d.parent_dish_id NULLS FIRST, f.dish_id, f.created_at
                    """,
                    (cross_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying fish subjects for cross: {e}")
            return []

    def get_fish_subject(self, fish_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single fish subject by UUID."""
        if not self.is_initialized:
            return None
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT fish_id, dish_id, subject_label, sex, genotype,
                           species, created_at, notes, current_unit_id
                    FROM fish_subjects
                    WHERE fish_id = ?
                    """,
                    (fish_id,),
                ).fetchone()
                if row is None:
                    return None
                return {k: row[k] for k in row.keys()}
        except Exception as e:
            logger.error(f"Error fetching fish subject: {e}")
            return None

    def update_fish_subject(self, fish_id: str, **kwargs) -> bool:
        """Update mutable fields on a fish subject.

        Accepted keyword arguments: subject_label, sex, genotype, species, notes.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        allowed = {"subject_label", "sex", "genotype", "species", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return True  # nothing to do
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        values = list(updates.values()) + [fish_id]
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    f"UPDATE fish_subjects SET {set_clause} WHERE fish_id = ?",
                    values,
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating fish subject: {e}")
            return False

    def delete_fish_subject(self, fish_id: str) -> bool:
        """Delete a fish subject by UUID."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM fish_subjects WHERE fish_id = ?",
                    (fish_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting fish subject: {e}")
            return False

    # --- Housing Unit Management ---

    def create_housing_unit(
        self,
        dish_id: str,
        unit_kind: str = "open",
        position_label: Optional[str] = None,
        capacity: Optional[int] = 1,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        """Create a single housing unit. Returns the generated unit_id."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None
        unit_id = f"{dish_id}:{position_label}" if position_label else f"{dish_id}:open"
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO housing_units
                        (unit_id, dish_id, position_label, unit_kind, capacity, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (unit_id, dish_id, position_label, unit_kind, capacity, notes),
                )
                conn.commit()
                return unit_id
        except Exception as e:
            logger.error(f"Error creating housing unit: {e}")
            return None

    def create_housing_units_for_dish(
        self,
        dish_id: str,
        unit_kind: str,
        count: int,
        label_format: Optional[str] = None,
    ) -> List[str]:
        """Batch-create housing units for a dish.

        label_format controls position labels:
        - None or "numeric": "1", "2", ..., "N"
        - "well_plate": "A1", "A2", ..., row-major for standard plates

        Returns list of created unit_ids.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return []

        labels = []
        if label_format == "well_plate":
            rows = "ABCDEFGH"
            cols_per_row = max(1, (count + 7) // 8) if count > 8 else count
            for r in rows:
                for c in range(1, cols_per_row + 1):
                    labels.append(f"{r}{c}")
                    if len(labels) == count:
                        break
                if len(labels) == count:
                    break
        else:
            labels = [str(i) for i in range(1, count + 1)]

        created = []
        try:
            with self.get_connection() as conn:
                for label in labels:
                    unit_id = f"{dish_id}:{label}"
                    conn.execute(
                        """
                        INSERT INTO housing_units
                            (unit_id, dish_id, position_label, unit_kind, capacity)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (unit_id, dish_id, label, unit_kind, 1),
                    )
                    created.append(unit_id)
                conn.commit()
        except Exception as e:
            logger.error(f"Error batch-creating housing units: {e}")
        return created

    def get_housing_units(self, dish_id: str) -> List[Dict[str, Any]]:
        """List housing units for a dish with current occupancy counts."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT h.unit_id, h.dish_id, h.position_label, h.unit_kind,
                           h.capacity, h.status, h.created_at, h.notes,
                           COUNT(f.fish_id) AS occupant_count
                    FROM housing_units h
                    LEFT JOIN fish_subjects f ON f.current_unit_id = h.unit_id
                    WHERE h.dish_id = ?
                    GROUP BY h.unit_id
                    ORDER BY h.position_label
                    """,
                    (dish_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying housing units: {e}")
            return []

    def get_housing_unit(self, unit_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single housing unit with its current fish."""
        if not self.is_initialized:
            return None
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT unit_id, dish_id, position_label, unit_kind,
                           capacity, status, created_at, notes
                    FROM housing_units WHERE unit_id = ?
                    """,
                    (unit_id,),
                ).fetchone()
                if row is None:
                    return None
                unit = {k: row[k] for k in row.keys()}
                fish_rows = conn.execute(
                    """
                    SELECT fish_id, dish_id, subject_label, sex, genotype,
                           species, created_at, notes
                    FROM fish_subjects WHERE current_unit_id = ?
                    ORDER BY created_at
                    """,
                    (unit_id,),
                ).fetchall()
                unit["fish"] = [{k: r[k] for k in r.keys()} for r in fish_rows]
                return unit
        except Exception as e:
            logger.error(f"Error fetching housing unit: {e}")
            return None

    def get_housing_units_with_fish(self, dish_id: str) -> List[Dict[str, Any]]:
        """Fetch all housing units for a dish with their occupants in a single query.

        Returns a list of unit dicts, each with a nested ``fish`` list containing
        ``fish_id`` and ``subject_label`` for every current occupant.
        """
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT h.unit_id, h.position_label, h.unit_kind, h.status,
                           f.fish_id, f.subject_label
                    FROM housing_units h
                    LEFT JOIN fish_subjects f ON f.current_unit_id = h.unit_id
                    WHERE h.dish_id = ?
                    ORDER BY h.position_label, f.created_at
                    """,
                    (dish_id,),
                ).fetchall()
                # Group rows by unit_id
                units: Dict[str, Dict[str, Any]] = {}
                for row in rows:
                    uid = row["unit_id"]
                    if uid not in units:
                        units[uid] = {
                            "unit_id": uid,
                            "position_label": row["position_label"],
                            "unit_kind": row["unit_kind"],
                            "status": row["status"],
                            "fish": [],
                        }
                    if row["fish_id"] is not None:
                        units[uid]["fish"].append({
                            "fish_id": row["fish_id"],
                            "subject_label": row["subject_label"],
                        })
                return list(units.values())
        except Exception as e:
            logger.error(f"Error querying housing units with fish: {e}")
            return []

    def assign_fish_to_unit(
        self, fish_id: str, unit_id: str, reason: str = "initial",
    ) -> bool:
        """Assign a fish to a housing unit. Updates current_unit_id and creates occupancy record."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE fish_subjects SET current_unit_id = ? WHERE fish_id = ?",
                    (unit_id, fish_id),
                )
                conn.execute(
                    """
                    INSERT INTO housing_unit_occupancy
                        (fish_id, unit_id, moved_in_at, reason)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                    """,
                    (fish_id, unit_id, reason),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error assigning fish to unit: {e}")
            return False

    def move_fish(
        self, fish_id: str, new_unit_id: str, reason: str = "transfer",
    ) -> bool:
        """Move a fish from its current unit to a new one.

        Closes the old occupancy record and opens a new one.
        """
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                # Close current occupancy
                conn.execute(
                    """
                    UPDATE housing_unit_occupancy
                    SET moved_out_at = CURRENT_TIMESTAMP
                    WHERE fish_id = ? AND moved_out_at IS NULL
                    """,
                    (fish_id,),
                )
                # Update current unit
                conn.execute(
                    "UPDATE fish_subjects SET current_unit_id = ? WHERE fish_id = ?",
                    (new_unit_id, fish_id),
                )
                # Open new occupancy
                conn.execute(
                    """
                    INSERT INTO housing_unit_occupancy
                        (fish_id, unit_id, moved_in_at, reason)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                    """,
                    (fish_id, new_unit_id, reason),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error moving fish: {e}")
            return False

    def log_housing_unit_check(
        self,
        unit_id: str,
        check_time: str,
        fed: Optional[bool] = None,
        feed_type: Optional[str] = None,
        water_changed: Optional[bool] = None,
        vol_water_changed: Optional[int] = None,
        num_dead: int = 0,
        notes: Optional[str] = None,
    ) -> bool:
        """Log a maintenance check for a housing unit position."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO housing_unit_checks
                        (unit_id, check_time, fed, feed_type, water_changed,
                         vol_water_changed, num_dead, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (unit_id, check_time, fed, feed_type, water_changed,
                     vol_water_changed, num_dead, notes),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error logging housing unit check: {e}")
            return False

    def get_housing_unit_checks(self, unit_id: str) -> List[Dict[str, Any]]:
        """Maintenance history for a housing unit position."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT id, unit_id, check_time, fed, feed_type, water_changed,
                           vol_water_changed, num_dead, notes, created_at
                    FROM housing_unit_checks
                    WHERE unit_id = ?
                    ORDER BY check_time DESC
                    """,
                    (unit_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying housing unit checks: {e}")
            return []

    def get_fish_occupancy_history(self, fish_id: str) -> List[Dict[str, Any]]:
        """Where has this fish lived — full occupancy history with unit details."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT o.id, o.fish_id, o.unit_id, o.moved_in_at,
                           o.moved_out_at, o.reason,
                           h.dish_id, h.position_label, h.unit_kind
                    FROM housing_unit_occupancy o
                    JOIN housing_units h ON h.unit_id = o.unit_id
                    WHERE o.fish_id = ?
                    ORDER BY o.moved_in_at
                    """,
                    (fish_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying fish occupancy history: {e}")
            return []

    # --- Fish Subject Images ---

    def save_fish_image(
        self,
        fish_id: str,
        image_filename: str,
        image_type: str = "reference",
        caption: Optional[str] = None,
    ) -> bool:
        """Insert a row into fish_subject_images linking an image file to a fish."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO fish_subject_images
                        (fish_id, image_filename, image_type, caption)
                    VALUES (?, ?, ?, ?)
                    """,
                    (fish_id, image_filename, image_type, caption),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving fish image record: {e}")
            return False

    def get_fish_images(self, fish_id: str) -> List[Dict[str, Any]]:
        """Query images for a fish."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT id, fish_id, image_filename, image_type, caption, created_at
                    FROM fish_subject_images
                    WHERE fish_id = ?
                    ORDER BY created_at
                    """,
                    (fish_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying fish images: {e}")
            return []

    # --- Dish-Level Images ---

    def save_dish_image(
        self,
        dish_id: str,
        image_filename: str,
        image_type: str = "reference",
        caption: Optional[str] = None,
    ) -> bool:
        """Insert a row into dish_images linking an image file to a dish."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return False
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO dish_images
                        (dish_id, image_filename, image_type, caption)
                    VALUES (?, ?, ?, ?)
                    """,
                    (dish_id, image_filename, image_type, caption),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving dish image record: {e}")
            return False

    def get_dish_images(self, dish_id: str) -> List[Dict[str, Any]]:
        """Query reference images for a dish."""
        if not self.is_initialized:
            return []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT id, dish_id, image_filename, image_type, caption, created_at
                    FROM dish_images
                    WHERE dish_id = ?
                    ORDER BY created_at
                    """,
                    (dish_id,),
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying dish images: {e}")
            return []

    # --- Genotype Reference Images ---

    @staticmethod
    def genotype_reference_key(genotype: Optional[str]) -> str:
        """Return the conservative exact-match key for a full genotype string."""
        return " ".join((genotype or "").split())

    def save_genotype_reference_image(
        self,
        genotype: str,
        image_filename: str,
        caption: Optional[str] = None,
        display_genotype: Optional[str] = None,
        source_image_id: Optional[int] = None,
        source_dish_id: Optional[str] = None,
        source_fish_id: Optional[str] = None,
        channels_json: Optional[str] = None,
        notes: Optional[str] = None,
        is_active: bool = True,
    ) -> Optional[int]:
        """Insert a curated display image for an exact full-genotype match."""
        if not self.is_initialized:
            logger.error("DataManager not initialized.")
            return None

        genotype_key = self.genotype_reference_key(genotype)
        if not genotype_key:
            logger.error("Cannot save genotype reference image without genotype.")
            return None
        if not image_filename:
            logger.error("Cannot save genotype reference image without image filename.")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO genotype_reference_images
                        (genotype_key, display_genotype, image_filename, caption,
                         source_image_id, source_dish_id, source_fish_id,
                         channels_json, notes, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        genotype_key,
                        display_genotype or genotype_key,
                        image_filename,
                        caption,
                        source_image_id,
                        source_dish_id,
                        source_fish_id,
                        channels_json,
                        notes,
                        1 if is_active else 0,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Error saving genotype reference image record: {e}")
            return None

    def get_genotype_reference_images(
        self,
        genotype: str,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Query curated reference images for an exact full-genotype match."""
        if not self.is_initialized:
            return []

        genotype_key = self.genotype_reference_key(genotype)
        if not genotype_key:
            return []

        try:
            with self.get_connection() as conn:
                params: List[Any] = [genotype_key]
                active_filter = ""
                if active_only:
                    active_filter = "AND is_active = 1"
                rows = conn.execute(
                    f"""
                    SELECT id, genotype_key, display_genotype, image_filename,
                           caption, source_image_id, source_dish_id, source_fish_id,
                           channels_json, notes, is_active, created_at
                    FROM genotype_reference_images
                    WHERE genotype_key = ?
                    {active_filter}
                    ORDER BY created_at DESC, id DESC
                    """,
                    params,
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error querying genotype reference images: {e}")
            return []

    def list_genotype_reference_images(
        self,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List curated full-genotype reference images for library management."""
        if not self.is_initialized:
            return []

        try:
            with self.get_connection() as conn:
                active_filter = "WHERE is_active = 1" if active_only else ""
                rows = conn.execute(
                    f"""
                    SELECT id, genotype_key, display_genotype, image_filename,
                           caption, source_image_id, source_dish_id, source_fish_id,
                           channels_json, notes, is_active, created_at
                    FROM genotype_reference_images
                    {active_filter}
                    ORDER BY display_genotype COLLATE NOCASE, created_at DESC, id DESC
                    """
                ).fetchall()
                return [{k: row[k] for k in row.keys()} for row in rows]
        except Exception as e:
            logger.error(f"Error listing genotype reference images: {e}")
            return []

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
                                    # Handle legacy indicator_screened → indicators_screened
                                    indicators = step.get('indicators_screened', [])
                                    if not indicators and step.get('indicator_screened'):
                                        indicators = [step['indicator_screened']]
                                    indicators_json = json.dumps(indicators)
                                    # Handle legacy number_positive → number_kept
                                    number_kept = step.get('number_kept', step.get('number_positive'))
                                    cursor.execute("""
                                        INSERT OR IGNORE INTO screening_steps
                                        (dish_id, screening_datetime, dpf_screened, indicators_screened,
                                         pigment_screened, criteria, count_screened_this_step, count_before_step, count_after_step, number_kept,
                                         number_removed_pigmented, number_removed_negative, number_removed_other,
                                         tricaine_used, notes)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        dish_id,
                                        step.get('screening_datetime'),
                                        step.get('dpf_screened'),
                                        indicators_json,
                                        step.get('pigment_screened', False),
                                        step.get('criteria'),
                                        step.get('count_screened_this_step'),
                                        step.get('count_before_step'),
                                        step.get('count_after_step'),
                                        number_kept,
                                        step.get('number_removed_pigmented'),
                                        step.get('number_removed_negative'),
                                        step.get('number_removed_other'),
                                        step.get('tricaine_used', False),
                                        step.get('notes')
                                    ))
                                    allocations = step.get('allocations') or self._legacy_screening_step_allocations(step)
                                    for allocation in allocations:
                                        cursor.execute("""
                                            INSERT INTO screening_step_allocations
                                            (dish_id, screening_datetime, bucket, disposition, count, destination_dish_id, derived_dish_id, notes)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            dish_id,
                                            step.get('screening_datetime'),
                                            allocation.get('bucket'),
                                            allocation.get('disposition'),
                                            allocation.get('count'),
                                            allocation.get('destination_dish_id') or allocation.get('derived_dish_id'),
                                            allocation.get('derived_dish_id') or allocation.get('destination_dish_id'),
                                            allocation.get('notes'),
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
                                source_screening_datetime = COALESCE(source_screening_datetime, ?),
                                source_screening_bucket = COALESCE(source_screening_bucket, ?),
                                notes = COALESCE(notes, ?),
                                room = COALESCE(room, ?),
                                enclosure_temperature = COALESCE(enclosure_temperature, ?),
                                container_type = COALESCE(container_type, ?),
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
                            dish_data.get('source_screening_datetime'),
                            dish_data.get('source_screening_bucket'),
                            dish_data.get('notes'),
                            enclosure.get('room'),
                            enclosure.get('temperature'),
                            enclosure.get('container_type', 'petri_dish'),
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



# Create a singleton instance for global access
data_manager = DataManager()
