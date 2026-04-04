"""
Shared fixtures for fish tracking tests.

Provides a TestClient backed by a temporary SQLite database so tests
run without a live server or production data.
"""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metazebrobot.api_server import create_app
from metazebrobot.data.data_manager import data_manager


@pytest.fixture(scope="session")
def tmp_db_path(tmp_path_factory) -> Path:
    """Create a temporary SQLite database file for the test session."""
    db_file = tmp_path_factory.mktemp("data") / "test_zebrobot.db"
    # Seed the required `dishes` table (the lifespan only creates fish-tracking tables).
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dishes (
            dish_id TEXT PRIMARY KEY,
            data TEXT,
            genotype TEXT,
            species TEXT DEFAULT 'Danio rerio',
            sex TEXT DEFAULT 'unknown',
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            cross_id TEXT,
            dof TEXT,
            fish_count INTEGER,
            responsible TEXT,
            parent_dish_id TEXT,
            dish_population_type TEXT DEFAULT 'primary',
            container_type TEXT DEFAULT 'petri_dish',
            notes TEXT,
            room TEXT,
            enclosure_temperature REAL,
            enclosure_vol_water_total INTEGER,
            enclosure_light_duration TEXT,
            enclosure_dawn_dusk TEXT,
            breeding_parents TEXT,
            screening_final_positive_count INTEGER,
            screening_date_finalized TEXT,
            termination_date TEXT,
            termination_reason TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screening_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id TEXT NOT NULL,
            screening_datetime TEXT NOT NULL,
            dpf_screened INTEGER,
            indicators_screened TEXT,
            pigment_screened BOOLEAN DEFAULT FALSE,
            criteria TEXT,
            count_screened_this_step INTEGER,
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
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_screening_steps_dish_id
        ON screening_steps(dish_id)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dish_transgenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id TEXT NOT NULL,
            construct TEXT NOT NULL,
            promoter TEXT NOT NULL,
            reporter TEXT,
            fluorophore TEXT,
            excitation_nm INTEGER,
            emission_nm INTEGER,
            fluorophore_color TEXT,
            FOREIGN KEY (dish_id) REFERENCES dishes(dish_id),
            UNIQUE(dish_id, construct)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_dish_transgenes_dish_id
        ON dish_transgenes(dish_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_dish_transgenes_promoter
        ON dish_transgenes(promoter)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id TEXT NOT NULL,
            check_time TEXT NOT NULL,
            fed BOOLEAN,
            feed_type TEXT,
            water_changed BOOLEAN,
            vol_water_changed INTEGER,
            num_dead INTEGER DEFAULT 0,
            notes TEXT,
            data TEXT,
            UNIQUE(dish_id, check_time)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            material_type TEXT NOT NULL,
            material_id TEXT NOT NULL,
            data TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_type, material_id)
        )
    """)
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture()
def client(tmp_db_path) -> TestClient:
    """FastAPI TestClient backed by the temp database.

    Each test function gets a fresh client; the lifespan runs on enter
    which creates all fish-tracking tables (CREATE TABLE IF NOT EXISTS).
    """
    app = create_app(str(tmp_db_path))
    with TestClient(app) as tc:
        yield tc


@pytest.fixture()
def seed_dish(client) -> str:
    """Insert a minimal dish row with a unique ID and return its dish_id.

    Each test gets its own dish so housing-unit labels and fish records
    never collide across tests sharing the session-scoped database.
    """
    import uuid as _uuid
    dish_id = f"DISH_{_uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(str(data_manager.database_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO dishes (dish_id, data, genotype, species) VALUES (?, ?, ?, ?)",
        (dish_id, json.dumps({"dish_id": dish_id}), "Tg(elavl3:GCaMP6s)", "Danio rerio"),
    )
    conn.commit()
    conn.close()
    return dish_id


@pytest.fixture()
def seed_full_dish(client) -> str:
    """Insert a dish with all fields required by the FishDish model.

    Unlike seed_dish (minimal row), this goes through save_fish_dish so the
    controller can load it back as a valid FishDish for operations like split.
    """
    import uuid as _uuid
    from metazebrobot.models.fish_dish import FishDish
    dish = FishDish.create_new(
        cross_id=f"CROSS_{_uuid.uuid4().hex[:6]}",
        dish_number=1,
        genotype="Tg(elavl3:GCaMP6s)",
        responsible="test-user",
        fish_count=50,
        dof="20260401",
        container_type="petri_dish",
    )
    data_manager.save_fish_dish(dish.model_dump(mode="json", exclude_none=True))
    return dish.dish_id


@pytest.fixture()
def seed_cross_dishes(client):
    """Insert two dishes sharing the same cross_id. Returns (cross_id, dish_id_1, dish_id_2)."""
    import uuid as _uuid
    cross_id = f"CROSS_{_uuid.uuid4().hex[:6]}"
    dish_a = f"DISH_{_uuid.uuid4().hex[:8]}"
    dish_b = f"DISH_{_uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(str(data_manager.database_path))
    conn.execute("PRAGMA foreign_keys = ON")
    for did in (dish_a, dish_b):
        conn.execute(
            "INSERT INTO dishes (dish_id, data, genotype, species, cross_id) VALUES (?, ?, ?, ?, ?)",
            (did, json.dumps({"dish_id": did}), "Tg(elavl3:GCaMP6s)", "Danio rerio", cross_id),
        )
    conn.commit()
    conn.close()
    return cross_id, dish_a, dish_b
