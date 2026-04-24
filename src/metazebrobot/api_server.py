"""
FastAPI service for MetaZebrobot web UI + HTTP API.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .controllers.fish_dish_controller import FishDishController
from .data.data_manager import data_manager
from .models.fish_dish import (
    DISH_TRANSFER_REASON_OPTIONS,
    TERMINATION_REASON_OPTIONS,
    termination_reason_label,
)
from .utils.label_generator import generate_dish_label
from .utils.pyrat_credentials import get_pyrat_api_credentials
from .utils.pyrat_frontend_client import (
    enrich_crossings_with_frontend_details,
    get_pyrat_frontend_credentials,
)

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_BUSY_TIMEOUT_MS = 250
_USER_MAPPING_PATH = os.path.expanduser("~/.pyrat_user_mapping.json")


def _load_user_list() -> List[str]:
    """Load available usernames from the PyRAT user mapping file."""
    try:
        if os.path.exists(_USER_MAPPING_PATH):
            with open(_USER_MAPPING_PATH) as f:
                return sorted(json.load(f).keys())
    except Exception:
        pass
    return []


def _current_user(request: Request) -> str:
    """Read the current username from the metazebrobot_user cookie."""
    cookie_val = request.cookies.get("metazebrobot_user")
    if cookie_val:
        return cookie_val
    # Fall back to first user in mapping, or "unknown"
    users = _load_user_list()
    return users[0] if users else "unknown"


def _pyrat_user_id(username: str) -> Optional[int]:
    """Look up a PyRAT user ID from the mapping file."""
    try:
        if os.path.exists(_USER_MAPPING_PATH):
            with open(_USER_MAPPING_PATH) as f:
                return json.load(f).get(username)
    except Exception:
        pass
    return None


def _fetch_pyrat(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Fetch data from the PyRAT API using configured credentials.

    Args:
        endpoint: API path after ``/api/v3/`` (e.g. ``"tanks"``).
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        HTTPException: If credentials are missing or the API call fails.
    """
    import requests as http_requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    credentials = get_pyrat_api_credentials()
    if not credentials:
        raise HTTPException(status_code=503, detail="PyRAT API credentials not configured")

    url = f"{credentials['base_url']}api/v3/{endpoint}"

    started = perf_counter()
    resp = http_requests.get(
        url,
        auth=(credentials["client_token"], credentials["user_token"]),
        headers={"Accept": "application/json"},
        params=params or {},
        verify=False,
        timeout=15,
    )
    elapsed = perf_counter() - started
    if resp.status_code != 200:
        logger.warning("PyRAT api/v3 %s failed in %.2fs with status %s", endpoint, elapsed, resp.status_code)
        raise HTTPException(status_code=502, detail=f"PyRAT API error: {resp.status_code}")
    payload = resp.json()
    count = len(payload) if isinstance(payload, list) else 1
    logger.info("PyRAT api/v3 %s returned %s item(s) in %.2fs", endpoint, count, elapsed)
    return payload


# ---------------------------------------------------------------------------
# Database helpers (read-only JSON API still uses its own lightweight conn)
# ---------------------------------------------------------------------------

def _resolve_db_path(db_path: Optional[str]) -> Optional[Path]:
    if db_path:
        return Path(db_path)
    env_path = os.getenv("METAZEBROBOT_DB_PATH")
    if env_path:
        return Path(env_path)
    return None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _screening_indicator_suggestions(
    transgenes: List[Dict[str, Any]],
    current_step: Optional[Any] = None,
) -> Tuple[List[Dict[str, str]], str]:
    """Build screening-indicator suggestions from parsed dish constructs."""
    suggestions: List[Dict[str, str]] = []
    seen: set[str] = set()
    current_indicators = list(getattr(current_step, "indicators", []) or [])

    def add_suggestion(value: Optional[str], meta_parts: Optional[List[str]] = None):
        raw = (value or "").strip()
        if not raw:
            return
        key = raw.lower()
        if key in seen:
            return
        seen.add(key)
        suggestions.append({
            "value": raw,
            "meta": " · ".join(part for part in (meta_parts or []) if part),
        })

    for indicator in current_indicators:
        add_suggestion(indicator)

    for tg in transgenes:
        value = (tg.get("catalog_name") or tg.get("reporter") or "").strip()
        if not value:
            continue
        family = tg.get("family") or tg.get("sensor_family") or tg.get("effector_family")
        target = tg.get("target") or tg.get("sensor_target")
        screen_color = tg.get("screen_color") or ((tg.get("spectra") or {}).get("color"))
        meta_parts = [
            tg.get("construct_role"),
            family if family and family.lower() != value.lower() else None,
            target,
            screen_color,
        ]
        add_suggestion(value, meta_parts)

    default_value = ", ".join(current_indicators) if current_indicators else ""
    if not default_value and len(suggestions) == 1:
        default_value = suggestions[0]["value"]

    return suggestions, default_value


def _normalize_html_date(date_value: Optional[str]) -> Optional[str]:
    """Convert supported date strings to ``YYYY-MM-DD`` for HTML date inputs."""
    if not date_value:
        return None

    raw = str(date_value).strip()
    if not raw:
        return None

    try:
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _html_date_plus_days(date_value: Optional[str], days: int) -> Optional[str]:
    """Return a normalized HTML date shifted by the given number of days."""
    normalized = _normalize_html_date(date_value)
    if not normalized:
        return None

    return (datetime.strptime(normalized, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _format_parent_locations(parent_tanks: Optional[List[Dict[str, Any]]]) -> str:
    """Build a readable comma-separated parent tank list from PyRAT-like data."""
    if not parent_tanks:
        return ""

    labels: List[str] = []
    for tank in parent_tanks:
        location = tank.get("location_display")
        if not location:
            tank_id = tank.get("tank_id")
            rack = tank.get("location_rack_name")
            pos = tank.get("tank_position")
            if tank_id and rack and pos:
                location = f"#{tank_id}_{rack}>{pos}"
            elif tank.get("tank_label"):
                location = str(tank.get("tank_label"))
            elif tank_id:
                location = f"#{tank_id}"
            else:
                location = ""
        if location:
            labels.append(location)
    return ", ".join(labels)


def _cross_prefill_from_payload(cross: Dict[str, Any]) -> Dict[str, str]:
    """Extract dish-form defaults from a PyRAT or locally cached cross payload."""
    parent_tanks = cross.get("parent_tanks")
    if not parent_tanks:
        parent_tanks = (cross.get("tanks") or {}).get("parents", [])

    setup_date = _normalize_html_date(cross.get("date_of_set_up"))
    if setup_date:
        dof = _html_date_plus_days(setup_date, 1) or ""
        dof_source = "pyrat_setup_plus_1"
    else:
        dof = _normalize_html_date(cross.get("date_of_record")) or ""
        dof_source = "pyrat_record_date" if dof else ""

    return {
        "genotype": cross.get("strain_name") or cross.get("strain_name_with_id") or "",
        "responsible": cross.get("responsible_fullname") or "",
        "parents": _format_parent_locations(parent_tanks),
        "cross_setup_date": setup_date or "",
        "dof": dof,
        "dof_source": dof_source,
    }


def _cross_prefill_complete(prefill: Dict[str, str]) -> bool:
    """Return True when local cross data is sufficient to render the new-dish form."""
    return all([
        prefill.get("genotype"),
        prefill.get("responsible"),
        prefill.get("parents"),
        prefill.get("dof"),
    ])


def _load_local_cross_prefill(conn: sqlite3.Connection, cross_id: str) -> Dict[str, str]:
    """Load cross defaults from locally cached crosses and prior dishes."""
    prefill = {
        "genotype": "",
        "responsible": "",
        "parents": "",
        "cross_setup_date": "",
        "dof": "",
        "dof_source": "",
    }

    try:
        cross_row = conn.execute(
            "SELECT line_strain, data FROM crosses WHERE cross_id = ? LIMIT 1",
            (cross_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        cross_row = None

    if cross_row:
        try:
            cross_data = json.loads(cross_row["data"]) if cross_row["data"] else {}
        except (TypeError, ValueError):
            cross_data = {}
        cached = _cross_prefill_from_payload(cross_data)
        if not cached["genotype"]:
            cached["genotype"] = cross_row["line_strain"] or ""
        prefill.update({k: v for k, v in cached.items() if v})

    dish_row = conn.execute(
        """
        SELECT genotype, responsible, breeding_parents, dof, cross_setup_date, dof_source
        FROM dishes
        WHERE cross_id = ?
        ORDER BY COALESCE(dof, '') DESC, date_created DESC
        LIMIT 1
        """,
        (cross_id,),
    ).fetchone()

    if dish_row:
        if not prefill["genotype"]:
            prefill["genotype"] = dish_row["genotype"] or ""
        if not prefill["responsible"]:
            prefill["responsible"] = dish_row["responsible"] or ""
        if not prefill["dof"]:
            prefill["dof"] = _normalize_html_date(dish_row["dof"]) or ""
        if not prefill["cross_setup_date"]:
            prefill["cross_setup_date"] = _normalize_html_date(dish_row["cross_setup_date"]) or ""
        if not prefill["dof_source"]:
            prefill["dof_source"] = dish_row["dof_source"] or ""
        if not prefill["parents"] and dish_row["breeding_parents"]:
            try:
                parents = json.loads(dish_row["breeding_parents"])
            except (TypeError, ValueError):
                parents = []
            prefill["parents"] = ", ".join(parent for parent in parents if parent)

    return prefill


def _load_new_dish_crosses(conn: sqlite3.Connection) -> List[str]:
    """Load recently active or still-unused crosses for the new-dish datalist."""
    rows = conn.execute(
        """SELECT c.cross_id,
       COUNT(d.dish_id) AS total_dishes,
       COUNT(CASE WHEN d.status = 'active' THEN 1 END) AS active_dishes
FROM crosses c
LEFT JOIN dishes d ON d.cross_id = c.cross_id
GROUP BY c.cross_id
HAVING active_dishes > 0           -- has active dishes (active)
    OR total_dishes = 0             -- new cross, no dishes yet
ORDER BY active_dishes DESC, c.cross_id DESC
LIMIT 100"""
    ).fetchall()
    return [r["cross_id"] for r in rows]


def _next_dish_number_for_cross(conn: sqlite3.Connection, cross_id: Optional[str]) -> int:
    """Return the next primary dish number for a cross."""
    if not cross_id:
        return 1

    try:
        rows = conn.execute(
            "SELECT dish_id FROM dishes WHERE cross_id = ?",
            (cross_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return 1

    prefix = f"{cross_id}_"
    dish_numbers: List[int] = []
    for row in rows:
        dish_id = row["dish_id"] or ""
        if not dish_id.startswith(prefix):
            continue

        suffix = dish_id[len(prefix):]
        if suffix.isdigit():
            dish_numbers.append(int(suffix))

    return max(dish_numbers, default=0) + 1


def _load_cross_dish_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Load active local dish counts keyed by cross id."""
    rows = conn.execute(
        "SELECT cross_id, COUNT(*) AS cnt FROM dishes WHERE status = 'active' GROUP BY cross_id"
    ).fetchall()
    return {r["cross_id"]: r["cnt"] for r in rows}


def _load_destination_dish_options(
    db_path: Path,
    busy_timeout_ms: int,
    source_dish: Any,
) -> List[Dict[str, Any]]:
    """Load active same-cross dishes that can receive screening-step fish."""
    cross_id = getattr(source_dish, "cross_id", None)
    source_dish_id = getattr(source_dish, "dish_id", None)
    if not cross_id or not source_dish_id:
        return []

    with _open_readonly_connection(db_path, busy_timeout_ms) as conn:
        rows = conn.execute("""
            SELECT
                dish_id,
                dish_population_type,
                current_fish_count,
                fish_count,
                genotype
            FROM dishes
            WHERE status = 'active'
              AND cross_id = ?
              AND dish_id != ?
            ORDER BY
                CASE dish_population_type
                    WHEN 'positive_screened' THEN 0
                    WHEN 'negative_screened' THEN 1
                    WHEN 'pigmented_screened' THEN 2
                    WHEN 'other' THEN 3
                    ELSE 4
                END,
                date_created DESC,
                dish_id ASC
        """, (cross_id, source_dish_id)).fetchall()

    options = []
    for row in rows:
        population_type = row["dish_population_type"] or "primary"
        current_count = row["current_fish_count"]
        if current_count is None:
            current_count = row["fish_count"]
        options.append({
            "dish_id": row["dish_id"],
            "population_type": population_type,
            "population_label": population_type.replace("_", " "),
            "current_fish_count": current_count,
            "genotype": row["genotype"],
        })
    return options


def _load_cached_cross_payloads(
    conn: sqlite3.Connection,
    cross_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Load cached cross JSON payloads keyed by cross id."""
    if not cross_ids:
        return {}

    placeholders = ",".join("?" for _ in cross_ids)
    rows = conn.execute(
        f"SELECT cross_id, data FROM crosses WHERE cross_id IN ({placeholders})",
        tuple(cross_ids),
    ).fetchall()
    payloads: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        try:
            payloads[row["cross_id"]] = json.loads(row["data"]) if row["data"] else {}
        except (TypeError, ValueError):
            continue
    return payloads


def _merge_cross_payload(base: Optional[Dict[str, Any]], overlay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a cached and fresh crossing payload while preserving detail-only fields."""
    merged = dict(base or {})
    overlay_data = dict(overlay or {})

    base_tanks = merged.get("tanks")
    overlay_tanks = overlay_data.get("tanks")
    if isinstance(base_tanks, dict) and isinstance(overlay_tanks, dict):
        merged_tanks = _merge_tanks_payload(base_tanks, overlay_tanks)
        overlay_data["tanks"] = merged_tanks

    merged.update(overlay_data)
    return merged


def _merge_tanks_payload(
    base_tanks: Dict[str, Any],
    overlay_tanks: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge PyRAT tank payloads without losing location fields from sparse fetches."""
    merged_tanks = dict(base_tanks)
    for key, value in overlay_tanks.items():
        base_value = merged_tanks.get(key)
        if key in {"parents", "children"} and isinstance(base_value, list) and isinstance(value, list):
            merged_tanks[key] = _merge_tank_lists(base_value, value)
        elif value not in (None, ""):
            merged_tanks[key] = value
        elif key not in merged_tanks:
            merged_tanks[key] = value
    return merged_tanks


def _merge_tank_lists(
    base_tanks: List[Dict[str, Any]],
    overlay_tanks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not overlay_tanks and base_tanks:
        return base_tanks

    base_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    base_order: List[Tuple[str, str]] = []
    for index, tank in enumerate(base_tanks):
        key = _tank_merge_key(tank, index)
        base_by_key[key] = tank
        base_order.append(key)

    merged: List[Dict[str, Any]] = []
    used_keys = set()
    for index, tank in enumerate(overlay_tanks):
        key = _tank_merge_key(tank, index)
        base_tank = base_by_key.get(key)
        merged.append(_merge_tank_row(base_tank, tank) if base_tank else tank)
        used_keys.add(key)

    for key in base_order:
        if key not in used_keys:
            merged.append(base_by_key[key])

    return merged


def _tank_merge_key(tank: Dict[str, Any], index: int) -> Tuple[str, str]:
    tank_id = tank.get("tank_id")
    if tank_id not in (None, ""):
        return ("tank_id", str(tank_id))
    return ("index", str(index))


def _merge_tank_row(
    base_tank: Optional[Dict[str, Any]],
    overlay_tank: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(base_tank or {})
    for key, value in overlay_tank.items():
        if value not in (None, ""):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


def _prepare_crossings_for_display(
    raw_crossings: List[Dict[str, Any]],
    dish_counts: Dict[str, int],
    cached_payloads: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Normalize crossing rows for template rendering, preferring cached detail fields."""
    crossings: List[Dict[str, Any]] = []
    cached_payloads = cached_payloads or {}

    for cross in raw_crossings:
        cid = str(cross.get("crossing_id", ""))
        merged = _merge_cross_payload(cached_payloads.get(cid), cross)

        date_display = (
            merged.get("date_of_raise")
            or merged.get("date_of_set_up")
            or merged.get("date_of_record")
            or ""
        )
        if date_display:
            date_display = str(date_display)[:10]
        merged["date_display"] = date_display

        tanks_data = merged.get("tanks", {})
        children = tanks_data.get("children", []) if isinstance(tanks_data, dict) else []
        if merged.get("raised_tanks") is not None:
            merged["raised_count"] = merged["raised_tanks"]
        elif merged.get("really_raised_tanks") is not None:
            merged["raised_count"] = merged["really_raised_tanks"]
        else:
            merged["raised_count"] = len(children)

        desc = merged.get("description", "") or ""
        match = re.search(r"(\d+)\s*(?:group|grp)", desc, re.IGNORECASE)
        merged["requested_groups"] = int(match.group(1)) if match else None
        merged["performance_target_count"] = merged.get("crossing_tanks") or merged["requested_groups"]

        if merged["performance_target_count"] and merged["performance_target_count"] > 0:
            perf = merged["raised_count"] / merged["performance_target_count"]
            merged["performance_display"] = f"{perf:.0%}"
            merged["performance_ratio_display"] = (
                f"{merged['raised_count']} / {merged['performance_target_count']}"
            )
        else:
            merged["performance_display"] = None
            merged["performance_ratio_display"] = None

        merged["local_dish_count"] = dish_counts.get(cid, 0)
        merged["crossing_id"] = cid
        crossings.append(merged)

    return crossings


def _cache_cross_rows(crossings: List[Dict[str, Any]]) -> None:
    """Persist PyRAT crossing payloads into the local crosses cache."""
    if not crossings:
        return

    try:
        with data_manager.get_connection() as conn:
            for cross in crossings:
                cross_id = cross.get("crossing_id")
                if not cross_id:
                    continue
                existing_row = conn.execute(
                    "SELECT data FROM crosses WHERE cross_id = ? LIMIT 1",
                    (str(cross_id),),
                ).fetchone()
                existing_payload = {}
                if existing_row and existing_row["data"]:
                    try:
                        existing_payload = json.loads(existing_row["data"])
                    except (TypeError, ValueError):
                        existing_payload = {}
                merged = _merge_cross_payload(existing_payload, cross)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO crosses
                    (cross_id, cross_status, line_strain, data, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        str(cross_id),
                        merged.get("status"),
                        merged.get("strain_name") or merged.get("strain_name_with_id"),
                        json.dumps(merged),
                    ),
                )
            conn.commit()
    except Exception as exc:
        logger.warning("Unable to cache %s crossing row(s): %s", len(crossings), exc)


def _load_cross_prefill(
    cross_id: str,
    db_path: Optional[Path] = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> Dict[str, str]:
    """Load dish-form defaults for a cross from local cache, then PyRAT."""
    started = perf_counter()
    prefill = {
        "genotype": "",
        "responsible": "",
        "parents": "",
        "cross_setup_date": "",
        "dof": "",
        "dof_source": "",
        "error": None,
    }

    try:
        if db_path:
            with _open_readonly_connection(db_path, busy_timeout_ms) as conn:
                local_prefill = _load_local_cross_prefill(conn, cross_id)
            for key in ("genotype", "responsible", "parents", "cross_setup_date", "dof", "dof_source"):
                prefill[key] = prefill[key] or local_prefill[key]

            if _cross_prefill_complete(prefill):
                logger.info("Cross prefill %s served from local cache in %.2fs", cross_id, perf_counter() - started)
                return prefill

        try:
            items = _fetch_pyrat(
                "tanks/crossings",
                params={
                    "crossing_id": cross_id,
                    "l": 1,
                    "k": [
                        "crossing_id", "status", "date_of_record", "date_of_set_up",
                        "responsible_fullname", "strain_name", "strain_name_with_id", "tanks",
                    ],
                    "tk": [
                        "tank_id", "tank_label", "status", "strain_name",
                        "number_of_male", "number_of_female", "number_of_unknown",
                        "alive_count", "date_of_birth",
                        "location_rack_name", "location_room_name", "tank_position",
                    ],
                },
            )
        except HTTPException as exc:
            if exc.status_code != 503:
                prefill["error"] = str(exc.detail)
        else:
            if items:
                cross = items[0] if isinstance(items, list) else items
                _cache_cross_rows([cross])
                live_prefill = _cross_prefill_from_payload(cross)
                for key in ("genotype", "responsible", "parents", "cross_setup_date", "dof", "dof_source"):
                    prefill[key] = prefill[key] or live_prefill[key]
    except Exception as exc:
        prefill["error"] = f"Could not fetch cross info: {exc}"

    logger.info(
        "Cross prefill %s resolved in %.2fs (complete=%s, error=%s)",
        cross_id,
        perf_counter() - started,
        _cross_prefill_complete(prefill),
        bool(prefill["error"]),
    )
    return prefill


@contextmanager
def _open_readonly_connection(db_path: Path, busy_timeout_ms: int):
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lifespan — initialise data_manager so controllers work
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = app.state.db_path
    if db_path:
        # Point data_manager at the database.
        data_manager.database_path = db_path
        data_manager.config_dir = _PACKAGE_DIR / "config"
        if not data_manager.ensure_schema():
            raise RuntimeError(f"Failed to initialize database schema for {db_path}")

        # Apply remaining API-server-specific schema updates.
        with data_manager.get_connection() as conn:
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_screening_images_dish_datetime
                ON screening_step_images(dish_id, screening_datetime)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fish_subjects_dish_id
                ON fish_subjects(dish_id)
            """)
            # Add current_unit_id to fish_subjects if not present
            cols = [r[1] for r in conn.execute("PRAGMA table_info(fish_subjects)").fetchall()]
            if 'current_unit_id' not in cols:
                conn.execute(
                    "ALTER TABLE fish_subjects ADD COLUMN current_unit_id TEXT REFERENCES housing_units(unit_id)"
                )
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_housing_units_dish_id
                ON housing_units(dish_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_housing_unit_checks_unit_id
                ON housing_unit_checks(unit_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_housing_occupancy_fish_id
                ON housing_unit_occupancy(fish_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_housing_occupancy_unit_id
                ON housing_unit_occupancy(unit_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fish_subject_images_fish_id
                ON fish_subject_images(fish_id)
            """)
            # Migrate enclosure_in_beaker → container_type
            dish_cols = [r[1] for r in conn.execute("PRAGMA table_info(dishes)").fetchall()]
            if 'container_type' not in dish_cols:
                conn.execute("ALTER TABLE dishes ADD COLUMN container_type TEXT")
                conn.execute("""
                    UPDATE dishes SET container_type = CASE
                        WHEN enclosure_in_beaker = 1 THEN 'beaker'
                        ELSE 'petri_dish'
                    END
                    WHERE container_type IS NULL
                """)
            if 'current_fish_count' not in dish_cols:
                conn.execute("ALTER TABLE dishes ADD COLUMN current_fish_count INTEGER")
                conn.execute("""
                    UPDATE dishes
                    SET current_fish_count = fish_count
                    WHERE current_fish_count IS NULL
                """)
            # Migrate screening_steps: indicator_screened → indicators_screened, number_positive → number_kept
            ss_cols = [r[1] for r in conn.execute("PRAGMA table_info(screening_steps)").fetchall()]
            if ss_cols:  # Table exists
                if 'indicators_screened' not in ss_cols:
                    conn.execute("ALTER TABLE screening_steps ADD COLUMN indicators_screened TEXT")
                    if 'indicator_screened' in ss_cols:
                        conn.execute("""
                            UPDATE screening_steps
                            SET indicators_screened = CASE
                                WHEN indicator_screened IS NOT NULL AND indicator_screened != ''
                                THEN '["' || indicator_screened || '"]'
                                ELSE '[]'
                            END
                            WHERE indicators_screened IS NULL
                        """)
                if 'pigment_screened' not in ss_cols:
                    conn.execute("ALTER TABLE screening_steps ADD COLUMN pigment_screened BOOLEAN DEFAULT FALSE")
                if 'number_kept' not in ss_cols:
                    conn.execute("ALTER TABLE screening_steps ADD COLUMN number_kept INTEGER")
                    if 'number_positive' in ss_cols:
                        conn.execute("""
                            UPDATE screening_steps
                            SET number_kept = number_positive
                            WHERE number_kept IS NULL AND number_positive IS NOT NULL
                        """)
                if 'count_before_step' not in ss_cols:
                    conn.execute("ALTER TABLE screening_steps ADD COLUMN count_before_step INTEGER")
                if 'count_after_step' not in ss_cols:
                    conn.execute("ALTER TABLE screening_steps ADD COLUMN count_after_step INTEGER")
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_dish_step
                ON screening_step_allocations(dish_id, screening_datetime)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_derived_dish
                ON screening_step_allocations(derived_dish_id)
            """)
            allocation_cols = [r[1] for r in conn.execute("PRAGMA table_info(screening_step_allocations)").fetchall()]
            if 'destination_dish_id' not in allocation_cols:
                conn.execute("ALTER TABLE screening_step_allocations ADD COLUMN destination_dish_id TEXT")
            conn.execute("""
                UPDATE screening_step_allocations
                SET destination_dish_id = derived_dish_id
                WHERE destination_dish_id IS NULL
                  AND derived_dish_id IS NOT NULL
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_screening_step_allocations_destination_dish
                ON screening_step_allocations(destination_dish_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_source
                ON dish_transfer_events(source_dish_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_destination
                ON dish_transfer_events(destination_dish_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_cross
                ON dish_transfer_events(cross_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transfer_events_datetime
                ON dish_transfer_events(event_datetime)
            """)
            # Normalized transgenes table
            conn.execute("""
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
            # Migrate dish_transgenes: add normalized metadata columns if missing
            tg_cols = [r[1] for r in conn.execute("PRAGMA table_info(dish_transgenes)").fetchall()]
            if 'modification_type' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN modification_type TEXT")
            if 'construct_role' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN construct_role TEXT")
            if 'sensor_family' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN sensor_family TEXT")
            if 'sensor_target' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN sensor_target TEXT")
            if 'effector_family' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN effector_family TEXT")
            if 'catalog_id' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN catalog_id INTEGER")
            if 'source_type' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN source_type TEXT")
            if 'source_id' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN source_id TEXT")
            if 'match_method' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN match_method TEXT")
            if 'excitation_nm' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN excitation_nm INTEGER")
            if 'emission_nm' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN emission_nm INTEGER")
            if 'fluorophore_color' not in tg_cols:
                conn.execute("ALTER TABLE dish_transgenes ADD COLUMN fluorophore_color TEXT")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transgenes_construct_role
                ON dish_transgenes(construct_role)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transgenes_sensor_family
                ON dish_transgenes(sensor_family)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_transgenes_catalog_id
                ON dish_transgenes(catalog_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dish_images_dish_id
                ON dish_images(dish_id)
            """)
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_genotype_reference_images_key
                ON genotype_reference_images(genotype_key, is_active)
            """)
            conn.commit()

        data_manager.load_all_data()
        logger.info(f"data_manager initialised with {db_path}")

        # Ensure screening images directory exists
        images_dir = db_path.parent / "screening_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        app.state.screening_images_dir = images_dir
        logger.info(f"Screening images directory: {images_dir}")

        # Ensure fish images directory exists
        fish_images_dir = db_path.parent / "fish_images"
        fish_images_dir.mkdir(parents=True, exist_ok=True)
        app.state.fish_images_dir = fish_images_dir
        logger.info(f"Fish images directory: {fish_images_dir}")

        # Ensure dish images directory exists
        dish_images_dir = db_path.parent / "dish_images"
        dish_images_dir.mkdir(parents=True, exist_ok=True)
        app.state.dish_images_dir = dish_images_dir
        logger.info(f"Dish images directory: {dish_images_dir}")

        # Ensure curated genotype reference images directory exists
        genotype_reference_images_dir = db_path.parent / "genotype_reference_images"
        genotype_reference_images_dir.mkdir(parents=True, exist_ok=True)
        app.state.genotype_reference_images_dir = genotype_reference_images_dir
        logger.info(f"Genotype reference images directory: {genotype_reference_images_dir}")

    yield


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(db_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="MetaZebrobot API", lifespan=lifespan)
    app.state.db_path = _resolve_db_path(db_path)
    app.state.busy_timeout_ms = DEFAULT_BUSY_TIMEOUT_MS

    # Jinja2 templates & static files
    templates = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")
    # Serve indicator reference images from config/images/
    _config_images_dir = _PACKAGE_DIR / "config" / "images"
    if _config_images_dir.is_dir():
        app.mount("/images", StaticFiles(directory=str(_config_images_dir)), name="images")
    # Serve uploaded screening images (directory created in lifespan)
    if app.state.db_path:
        _screening_images_dir = app.state.db_path.parent / "screening_images"
        _screening_images_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/screening-images",
            StaticFiles(directory=str(_screening_images_dir)),
            name="screening_images",
        )
        # Serve uploaded fish reference images
        _fish_images_dir = app.state.db_path.parent / "fish_images"
        _fish_images_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/fish-images",
            StaticFiles(directory=str(_fish_images_dir)),
            name="fish_images",
        )
        # Serve uploaded dish reference images
        _dish_images_dir = app.state.db_path.parent / "dish_images"
        _dish_images_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/dish-images",
            StaticFiles(directory=str(_dish_images_dir)),
            name="dish_images",
        )
        # Serve curated full-genotype reference images
        _genotype_reference_images_dir = app.state.db_path.parent / "genotype_reference_images"
        _genotype_reference_images_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/genotype-reference-images",
            StaticFiles(directory=str(_genotype_reference_images_dir)),
            name="genotype_reference_images",
        )

    # Controller instance for write endpoints
    fish_dish_ctrl = FishDishController()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_db_path() -> Path:
        if not app.state.db_path:
            raise HTTPException(
                status_code=500,
                detail="Database path not configured. Set METAZEBROBOT_DB_PATH or pass --db-path.",
            )
        return app.state.db_path

    def _dpf_from_dof(dof_str: str, ref_date: Optional[datetime] = None) -> Optional[int]:
        """Calculate days-post-fertilisation from DOF string (YYYYMMDD).

        If ref_date is not provided, defaults to today.
        """
        try:
            dof = datetime.strptime(dof_str, "%Y%m%d")
            today = ref_date or datetime.now()
            return (today - dof).days
        except (ValueError, TypeError):
            return None

    def _last_screening_date(dish) -> Optional[datetime]:
        """Return the datetime of the most recent screening step, or None."""
        if not dish.screening_results or not dish.screening_results.screenings:
            return None
        last = dish.screening_results.screenings[-1]
        try:
            date_part = last.screening_datetime.split("T")[0]
            return datetime.strptime(date_part, "%Y%m%d")
        except (ValueError, IndexError):
            return None

    def _protocol_for_genotype(genotype: str, dpf: Optional[int]):
        """Return the matching protocol step (if any) for a genotype + DPF.

        Tries exact string match first, then falls back to matching by the
        set of promoters parsed from the genotype.  This makes protocol
        lookup resilient to whitespace, capitalisation, and ordering
        differences in genotype strings.
        """
        protocols = data_manager.get_screening_protocols()

        # 1. Exact match (fast path, backward compatible)
        proto = protocols.get(genotype)

        # 2. Fuzzy match: compare promoter sets
        if not proto:
            dish_promoters = {
                t["promoter"] for t in data_manager.parse_genotype(genotype)
            }
            if dish_promoters:
                for proto_genotype, proto_data in protocols.items():
                    if proto_genotype == "_default":
                        continue
                    proto_promoters = {
                        t["promoter"] for t in data_manager.parse_genotype(proto_genotype)
                    }
                    if proto_promoters == dish_promoters:
                        proto = proto_data
                        break

        # 3. Fall back to default
        if not proto:
            proto = protocols.get("_default")
        if not proto:
            return None, None

        for step in proto.get("steps", []):
            lo, hi = step.get("dpf_range", [0, 999])
            if dpf is not None and lo <= dpf <= hi:
                return proto, step
        return proto, None

    # ------------------------------------------------------------------
    # User switcher
    # ------------------------------------------------------------------

    # Make user info available to all templates via Jinja2 globals
    @app.middleware("http")
    async def inject_user_context(request: Request, call_next):
        """Add current_user and user_list to Jinja2 template globals."""
        templates.env.globals["current_user"] = _current_user(request)
        templates.env.globals["user_list"] = _load_user_list()
        response = await call_next(request)
        return response

    @app.post("/set-user")
    def set_user(request: Request, username: str = Form(...)):
        """Set the active user via cookie and redirect back."""
        referer = request.headers.get("referer", "/")
        response = RedirectResponse(url=referer, status_code=303)
        response.set_cookie(
            "metazebrobot_user", username,
            max_age=30 * 24 * 3600,  # 30 days
            httponly=True,
            samesite="lax",
        )
        return response

    # ------------------------------------------------------------------
    # Home page
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home_page(request: Request):
        """Landing page."""
        return templates.TemplateResponse(request, "home.html", {})

    # ------------------------------------------------------------------
    # Dish creation (web UI)
    # ------------------------------------------------------------------

    @app.get("/dishes/new", response_class=HTMLResponse)
    def new_dish_form(request: Request, cross_id: Optional[str] = Query(default=None)):
        """Dish creation form with optional PyRAT cross auto-fill."""
        # Try to load cross IDs for the datalist
        crosses = []
        next_dish_number = 1
        try:
            db_path = _require_db_path()
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                crosses = _load_new_dish_crosses(conn)
                next_dish_number = _next_dish_number_for_cross(conn, cross_id)
        except Exception:
            pass

        today = datetime.now().strftime("%Y-%m-%d")
        prefill = _load_cross_prefill(cross_id, _require_db_path(), app.state.busy_timeout_ms) if cross_id else {
            "genotype": "",
            "responsible": "",
            "parents": "",
            "cross_setup_date": "",
            "dof": "",
            "dof_source": "",
            "error": None,
        }
        return templates.TemplateResponse(request, "dishes/new_dish.html", {
            "crosses": crosses,
            "today": today,
            "form": {
                "cross_id": cross_id or "",
                "dish_number": next_dish_number,
                "cross_setup_date": prefill["cross_setup_date"] or "",
                "dof": prefill["dof"] or "",
                "dof_source": prefill["dof_source"] or "",
            },
            "genotype": prefill["genotype"],
            "responsible": prefill["responsible"],
            "parents": prefill["parents"],
            "cross_setup_date": prefill["cross_setup_date"],
            "dof": prefill["dof"],
            "dof_source": prefill["dof_source"],
            "error": prefill["error"],
            "include_dof_oob": False,
        })

    @app.get("/dishes/new/cross-info", response_class=HTMLResponse)
    def cross_info_partial(request: Request, cross_id: str = Query(...)):
        """HTMX partial: auto-fill genotype/responsible/parents from PyRAT cross."""
        prefill = _load_cross_prefill(cross_id, _require_db_path(), app.state.busy_timeout_ms)
        next_dish_number = 1
        try:
            db_path = _require_db_path()
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                next_dish_number = _next_dish_number_for_cross(conn, cross_id)
        except Exception:
            pass

        return templates.TemplateResponse(request, "dishes/_cross_info.html", {
            "dish_number": next_dish_number,
            "genotype": prefill["genotype"],
            "responsible": prefill["responsible"],
            "parents": prefill["parents"],
            "cross_setup_date": prefill["cross_setup_date"],
            "dof": prefill["dof"],
            "dof_source": prefill["dof_source"],
            "error": prefill["error"],
            "include_dof_oob": True,
        })

    @app.post("/dishes/new/refresh-crosses", response_class=HTMLResponse)
    def refresh_crosses_from_pyrat(
        request: Request,
        all_crosses: bool = Form(default=False),
    ):
        """Fetch recent crosses from PyRAT and update local crosses table."""
        import requests as http_requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        credentials = get_pyrat_api_credentials()
        if not credentials:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": "PyRAT credentials not configured. Set them via pyrat_credentials_tool.py or the desktop app.",
                "level": "error",
            })

        params = {
            "l": 50 if not all_crosses else 200,
            "s": ["date_of_record:desc"],
            "k": [
                "crossing_id", "status", "date_of_record",
                "responsible_fullname", "strain_name", "strain_name_with_id",
            ],
        }
        # Filter by responsible user (from cookie)
        responsible_id = _pyrat_user_id(_current_user(request))
        if responsible_id:
            params["responsible_id"] = responsible_id

        # Only fetch recent crosses unless "all" is requested
        if not all_crosses:
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            params["date_of_record_from"] = cutoff

        try:
            resp = http_requests.get(
                f"{credentials['base_url']}api/v3/tanks/crossings",
                auth=(credentials["client_token"], credentials["user_token"]),
                headers={"Accept": "application/json"},
                params=params,
                verify=False,
                timeout=10,
            )
            if resp.status_code != 200:
                return templates.TemplateResponse(request, "screening/_flash_message.html", {
                    "message": f"PyRAT returned {resp.status_code}.",
                    "level": "error",
                })

            crossings = resp.json()
            _cache_cross_rows(crossings)

            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": f"Synced {len(crossings)} crosses from PyRAT.",
                "level": "success",
            })
        except Exception as e:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": f"PyRAT sync failed: {e}",
                "level": "error",
            })

    @app.post("/dishes/new", response_class=HTMLResponse)
    def create_dish_web(
        request: Request,
        cross_id: str = Form(...),
        dish_number: int = Form(...),
        genotype: str = Form(...),
        responsible: str = Form(...),
        cross_setup_date: Optional[str] = Form(default=None),
        dof: str = Form(...),
        dof_source: Optional[str] = Form(default=None),
        fish_count: int = Form(default=0),
        species: str = Form(default="Danio rerio"),
        sex: str = Form(default="unknown"),
        parents: str = Form(default=""),
        container_type: str = Form(default="petri_dish"),
        temperature: float = Form(default=28.5),
        room: str = Form(default="2E.282"),
        light_duration: str = Form(default="14:10"),
        dawn_dusk: str = Form(default="8:00"),
        vol_water_total: Optional[int] = Form(default=None),
        notes: Optional[str] = Form(default=None),
    ):
        """Create a new dish from the web form."""
        _require_db_path()

        # Convert date format: YYYY-MM-DD → YYYYMMDD
        dof_formatted = dof.replace("-", "")

        # Parse parents string into list
        parents_list = [p.strip() for p in parents.split(",") if p.strip()] if parents else []

        success, message, dish = fish_dish_ctrl.create_dish(
            cross_id=cross_id,
            dish_number=dish_number,
            genotype=genotype,
            responsible=responsible,
            cross_setup_date=cross_setup_date.replace("-", "") if cross_setup_date else None,
            dof_source=dof_source or None,
            dof=dof_formatted,
            fish_count=fish_count,
            species=species,
            sex=sex,
            parents=parents_list,
            temperature=temperature,
            light_duration=light_duration,
            dawn_dusk=dawn_dusk,
            room=room,
            container_type=container_type,
            vol_water_total=vol_water_total,
            notes=notes or None,
        )

        if success:
            return RedirectResponse(
                url=f"/screening/{message}",  # message is the dish_id on success
                status_code=303,
            )

        # Re-render form with error
        crosses = []
        try:
            db_path = _require_db_path()
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                crosses = _load_new_dish_crosses(conn)
        except Exception:
            pass

        return templates.TemplateResponse(request, "dishes/new_dish.html", {
            "crosses": crosses,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "form": {
                "cross_id": cross_id,
                "dish_number": dish_number,
                "cross_setup_date": cross_setup_date,
                "dof": dof,
                "dof_source": dof_source,
                "fish_count": fish_count,
                "species": species,
                "sex": sex,
                "container_type": container_type,
                "temperature": temperature,
                "room": room,
                "light_duration": light_duration,
                "dawn_dusk": dawn_dusk,
                "vol_water_total": vol_water_total,
                "notes": notes,
            },
            "genotype": genotype,
            "responsible": responsible,
            "parents": parents,
            "flash_message": message,
            "flash_level": "error",
        })

    @app.get("/dishes/", response_class=HTMLResponse)
    def dishes_inventory_page(
        request: Request,
        status: str = Query(default="all"),
        terminated: Optional[str] = Query(default=None),
        transferred: Optional[str] = Query(default=None),
    ):
        """Inventory-style dish index for local MetaZebrobot dishes."""
        db_path = _require_db_path()
        normalized_status = (status or "all").strip().lower()
        if normalized_status not in {"all", "active", "inactive"}:
            normalized_status = "all"

        query = """
            SELECT
                d.dish_id,
                d.cross_id,
                d.genotype,
                d.dof,
                d.fish_count,
                d.current_fish_count,
                d.responsible,
                d.status,
                d.termination_date,
                d.termination_reason,
                d.date_created,
                d.parent_dish_id,
                d.dish_population_type,
                d.screening_final_positive_count,
                COALESCE(ss.step_count, 0) AS step_count,
                qc.last_check,
                COALESCE(fs.registered_fish_count, 0) AS registered_fish_count
            FROM dishes d
            LEFT JOIN (
                SELECT dish_id, COUNT(*) AS step_count
                FROM screening_steps
                GROUP BY dish_id
            ) ss ON ss.dish_id = d.dish_id
            LEFT JOIN (
                SELECT dish_id, MAX(check_time) AS last_check
                FROM quality_checks
                GROUP BY dish_id
            ) qc ON qc.dish_id = d.dish_id
            LEFT JOIN (
                SELECT dish_id, COUNT(*) AS registered_fish_count
                FROM fish_subjects
                GROUP BY dish_id
            ) fs ON fs.dish_id = d.dish_id
            WHERE (? = 'all' OR d.status = ?)
            ORDER BY
                CASE WHEN d.status = 'active' THEN 0 ELSE 1 END,
                d.date_created DESC,
                d.dish_id DESC
        """
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            rows = conn.execute(query, (normalized_status, normalized_status)).fetchall()

        dishes = []
        for row in rows:
            d = _row_to_dict(row)
            dpf = _dpf_from_dof(d.get("dof") or "", None)
            step_count = int(d.get("step_count") or 0)
            if d.get("screening_final_positive_count") is not None:
                screening_status = "Done"
            elif step_count > 0:
                screening_status = "In progress"
            else:
                screening_status = "Not started"

            population_label = (d.get("dish_population_type") or "primary").replace("_", " ")
            search_text = " ".join(
                str(value)
                for value in (
                    d.get("dish_id") or "",
                    d.get("cross_id") or "",
                    d.get("genotype") or "",
                    d.get("responsible") or "",
                    d.get("status") or "",
                    d.get("termination_reason") or "",
                    d.get("dish_population_type") or "",
                    d.get("parent_dish_id") or "",
                )
            ).lower()
            dishes.append({
                "dish_id": d.get("dish_id"),
                "cross_id": d.get("cross_id"),
                "genotype": d.get("genotype"),
                "dof": d.get("dof"),
                "dpf": dpf,
                "fish_count": d.get("fish_count"),
                "current_fish_count": d.get("current_fish_count"),
                "registered_fish_count": d.get("registered_fish_count"),
                "responsible": d.get("responsible"),
                "status": d.get("status"),
                "termination_date": d.get("termination_date"),
                "termination_date_display": _normalize_html_date(d.get("termination_date")),
                "termination_reason": d.get("termination_reason"),
                "termination_reason_display": termination_reason_label(d.get("termination_reason")),
                "date_created": d.get("date_created"),
                "last_check": d.get("last_check"),
                "parent_dish_id": d.get("parent_dish_id"),
                "population_label": population_label,
                "screening_status": screening_status,
                "step_count": step_count,
                "search_text": search_text,
                "transfer_destinations": [],
            })

        active_by_cross: Dict[str, List[Dict[str, Any]]] = {}
        for d in dishes:
            if d["status"] == "active" and d["cross_id"]:
                active_by_cross.setdefault(d["cross_id"], []).append(d)
        for d in dishes:
            if d["status"] == "active" and d["cross_id"]:
                d["transfer_destinations"] = [
                    {
                        "dish_id": candidate["dish_id"],
                        "population_label": candidate["population_label"],
                        "current_fish_count": candidate["current_fish_count"],
                    }
                    for candidate in active_by_cross.get(d["cross_id"], [])
                    if candidate["dish_id"] != d["dish_id"]
                ]

        summary = {
            "total": len(dishes),
            "active": sum(1 for d in dishes if d["status"] == "active"),
            "inactive": sum(1 for d in dishes if d["status"] == "inactive"),
        }
        flash_message = None
        if terminated:
            flash_message = f"Terminated dish {terminated}."
        elif transferred:
            flash_message = f"Transferred fish from dish {transferred}."
        return templates.TemplateResponse(request, "dishes/dish_list.html", {
            "dishes": dishes,
            "summary": summary,
            "status_filter": normalized_status,
            "termination_reason_options": TERMINATION_REASON_OPTIONS,
            "transfer_reason_options": DISH_TRANSFER_REASON_OPTIONS,
            "flash_message": flash_message,
            "flash_level": "success",
        })

    @app.post("/dishes/{dish_id}/terminate", response_class=HTMLResponse)
    def terminate_dish_web(
        dish_id: str,
        termination_reason: Optional[str] = Form(default=None),
        return_status: str = Form(default="all"),
    ):
        """Terminate an active dish from the inventory page."""
        _require_db_path()
        normalized_status = (return_status or "all").strip().lower()
        if normalized_status not in {"all", "active", "inactive"}:
            normalized_status = "all"

        success, message = fish_dish_ctrl.update_dish_status(
            dish_id=dish_id,
            status="inactive",
            termination_reason=termination_reason,
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)

        return RedirectResponse(
            url=f"/dishes/?status={normalized_status}&terminated={dish_id}",
            status_code=303,
        )

    @app.post("/dishes/{source_dish_id}/transfer", response_class=HTMLResponse)
    def transfer_dish_fish_web(
        source_dish_id: str,
        destination_dish_id: str = Form(...),
        count: int = Form(...),
        reason: str = Form(...),
        notes: Optional[str] = Form(default=None),
        return_status: str = Form(default="all"),
    ):
        """Transfer fish from one active dish into another active same-cross dish."""
        _require_db_path()
        normalized_status = (return_status or "all").strip().lower()
        if normalized_status not in {"all", "active", "inactive"}:
            normalized_status = "all"

        success, message, _ = fish_dish_ctrl.transfer_fish_between_dishes(
            source_dish_id=source_dish_id,
            destination_dish_id=destination_dish_id,
            count=count,
            reason=reason,
            notes=notes or None,
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)

        return RedirectResponse(
            url=f"/dishes/?status={normalized_status}&transferred={source_dish_id}",
            status_code=303,
        )

    # ------------------------------------------------------------------
    # JSON API — health + dishes
    # ------------------------------------------------------------------

    @app.get("/health")
    def health(check_db: bool = Query(default=False)) -> Dict[str, Any]:
        if not check_db:
            return {"status": "ok"}
        db_path = _require_db_path()
        try:
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                conn.execute("SELECT 1").fetchone()
            return {"status": "ok", "db": "ok"}
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/dishes")
    def list_dishes_api(
        status: Optional[str] = Query(default=None),
        cross_id: Optional[str] = Query(default=None),
        promoter: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> Dict[str, Any]:
        db_path = _require_db_path()
        query = """
            SELECT dish_id, cross_id, genotype, responsible, fish_count, dof,
                   status, date_created, parent_dish_id, dish_population_type
            FROM dishes
            WHERE 1=1
        """
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if cross_id:
            query += " AND cross_id = ?"
            params.append(cross_id)
        if promoter:
            query += " AND dish_id IN (SELECT dish_id FROM dish_transgenes WHERE promoter = ?)"
            params.append(promoter.lower())
        query += " ORDER BY date_created DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        try:
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                rows = conn.execute(query, params).fetchall()
            return {"items": [_row_to_dict(row) for row in rows]}
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/dishes/{dish_id}")
    def get_dish_api(
        dish_id: str,
        include_checks: bool = Query(default=False),
    ) -> Dict[str, Any]:
        db_path = _require_db_path()
        try:
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                row = conn.execute(
                    "SELECT * FROM dishes WHERE dish_id = ?",
                    (dish_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Dish not found")
                dish = _row_to_dict(row)
                if dish.get("data"):
                    try:
                        dish["data"] = json.loads(dish["data"])
                    except json.JSONDecodeError:
                        dish["data"] = dish["data"]
                if include_checks:
                    checks = conn.execute(
                        """
                        SELECT * FROM quality_checks
                        WHERE dish_id = ?
                        ORDER BY check_time DESC
                        """,
                        (dish_id,),
                    ).fetchall()
                    dish["quality_checks"] = [_row_to_dict(r) for r in checks]
            return dish
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/crosses/{cross_id}")
    def get_cross_api(
        cross_id: str,
        include_dishes: bool = Query(default=False),
    ) -> Dict[str, Any]:
        """Fetch crossing info from PyRAT API.

        Returns a response compatible with the palette zebrobot_snapshot contract:
        cross_id, line_strain, parents, and optionally dishes from the local DB.
        """
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        credentials = get_pyrat_api_credentials()
        if not credentials:
            raise HTTPException(status_code=503, detail="PyRAT API credentials not configured")

        # Fetch crossing from PyRAT (list endpoint with crossing_id filter)
        url = f"{credentials['base_url']}api/v3/tanks/crossings"
        try:
            resp = requests.get(
                url,
                auth=(credentials["client_token"], credentials["user_token"]),
                headers={"Accept": "application/json"},
                params={
                    "crossing_id": cross_id,
                    "l": 1,
                    "k": [
                        "crossing_id", "status", "strain_name", "strain_name_with_id",
                        "responsible_fullname", "tanks",
                    ],
                    "tk": [
                        "tank_id", "tank_label", "strain_name",
                        "number_of_male", "number_of_female",
                        "location_rack_name", "tank_position",
                    ],
                },
                verify=False,
                timeout=10,
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail=f"PyRAT API error: {exc}") from exc

        if resp.status_code != 200:
            raise HTTPException(status_code=503, detail=f"PyRAT API returned {resp.status_code}")

        results = resp.json()
        if not results:
            raise HTTPException(status_code=404, detail="Cross not found in PyRAT")

        data = results[0]

        # Build parents list in the format palette expects
        parents = []
        for tank in (data.get("tanks") or {}).get("parents", []) or []:
            rack = tank.get("location_rack_name", "")
            pos = tank.get("tank_position", "")
            tid = tank.get("tank_id", "")
            identifier = f"{rack}:{pos} ({tid})" if rack and pos else f"#{tid}"
            n_male = tank.get("number_of_male", 0) or 0
            n_female = tank.get("number_of_female", 0) or 0
            if n_male > 0 and n_female == 0:
                sex = "M"
            elif n_female > 0 and n_male == 0:
                sex = "F"
            else:
                sex = "unknown"
            parents.append({"identifier": identifier, "sex": sex})

        result: Dict[str, Any] = {
            "cross_id": str(data.get("crossing_id", cross_id)),
            "line_strain": data.get("strain_name") or data.get("strain_name_with_id") or "",
            "parents": parents,
        }

        if include_dishes:
            db_path = _require_db_path()
            try:
                with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                    dishes = conn.execute(
                        """
                        SELECT dish_id, status, fish_count, dof, date_created
                        FROM dishes WHERE cross_id = ?
                        ORDER BY date_created DESC
                        """,
                        (cross_id,),
                    ).fetchall()
                    result["dishes"] = [_row_to_dict(r) for r in dishes]
            except sqlite3.Error:
                result["dishes"] = []

        return result

    # ------------------------------------------------------------------
    # Screening web UI
    # ------------------------------------------------------------------

    @app.get("/screening/", response_class=HTMLResponse)
    def screening_dish_list(request: Request):
        """Dish picker — show active dishes with screening info."""
        db_path = _require_db_path()
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            rows = conn.execute("""
                SELECT d.dish_id, d.genotype, d.dof, d.fish_count, d.current_fish_count, d.responsible,
                       d.screening_final_positive_count,
                       COUNT(s.id) AS step_count
                FROM dishes d
                LEFT JOIN screening_steps s ON s.dish_id = d.dish_id
                WHERE d.status = 'active'
                GROUP BY d.dish_id
                ORDER BY d.date_created DESC
            """).fetchall()
        dishes = []
        for row in rows:
            d = _row_to_dict(row)
            dpf = _dpf_from_dof(d.get("dof") or "", None)
            dishes.append({
                "dish_id": d["dish_id"],
                "genotype": d.get("genotype"),
                "dof": d.get("dof"),
                "dpf": dpf,
                "fish_count": d.get("fish_count"),
                "current_fish_count": d.get("current_fish_count"),
                "responsible": d.get("responsible"),
                "step_count": d.get("step_count", 0),
                "finalized": d.get("screening_final_positive_count") is not None,
            })
        return templates.TemplateResponse(request, "screening/dish_list.html", {
            "dishes": dishes,
        })

    @app.get("/screening/{dish_id}", response_class=HTMLResponse)
    def screening_form(request: Request, dish_id: str):
        """Main screening page for a single dish."""
        dish = fish_dish_ctrl.get_dish(dish_id)
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        ref_date = _last_screening_date(dish)
        dpf = _dpf_from_dof(dish.dof, ref_date)
        protocol, current_step = _protocol_for_genotype(dish.genotype, dpf)

        steps = dish.screening_results.screenings if dish.screening_results else []
        finalized = dish.screening_results.final_positive_count is not None if dish.screening_results else False
        final_count = dish.screening_results.final_positive_count if dish.screening_results else None

        # Build indicator -> URL mapping for reference images
        raw_images = data_manager.get_indicator_images()
        indicator_images = {
            name: f"/{path}" for name, path in raw_images.items()
        }

        # Gather uploaded images per screening step
        step_images = {}
        for s in steps:
            imgs = data_manager.get_screening_images(dish_id, s.screening_datetime)
            if imgs:
                step_images[s.screening_datetime] = imgs

        transgenes = data_manager.get_dish_transgenes(dish_id)
        indicator_suggestions, default_indicator_value = _screening_indicator_suggestions(
            transgenes, current_step
        )
        destination_dishes = _load_destination_dish_options(
            _require_db_path(),
            app.state.busy_timeout_ms,
            dish,
        )

        return templates.TemplateResponse(request, "screening/screening_form.html", {
            "dish": dish,
            "dpf": dpf,
            "protocol": protocol,
            "current_step": current_step,
            "steps": steps,
            "finalized": finalized,
            "final_count": final_count,
            "indicator_images": indicator_images,
            "step_images": step_images,
            "transgenes": transgenes,
            "indicator_suggestions": indicator_suggestions,
            "default_indicator_value": default_indicator_value,
            "destination_dishes": destination_dishes,
        })

    @app.get("/screening/{dish_id}/atlas", response_class=HTMLResponse)
    def screening_atlas_reference(request: Request, dish_id: str):
        """HTMX partial: mapzebrain atlas matches for a dish."""
        dish = fish_dish_ctrl.get_dish(dish_id)
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        atlas_catalog_available = bool(data_manager.fetch_mapzebrain_catalog())
        atlas_lines = (
            data_manager.lookup_mapzebrain_lines(dish_id=dish_id, genotype=dish.genotype)
            if atlas_catalog_available
            else []
        )

        return templates.TemplateResponse(request, "screening/_atlas_reference.html", {
            "atlas_lines": atlas_lines,
            "atlas_catalog_available": atlas_catalog_available,
        })

    @app.get("/screening/{dish_id}/genotype-reference", response_class=HTMLResponse)
    def screening_genotype_reference(request: Request, dish_id: str):
        """HTMX partial: curated exact-genotype reference image for a dish."""
        dish = fish_dish_ctrl.get_dish(dish_id)
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        references = data_manager.get_genotype_reference_images(dish.genotype)
        for reference in references:
            reference["image_url"] = f"/genotype-reference-images/{reference['image_filename']}"

        return templates.TemplateResponse(request, "screening/_genotype_reference.html", {
            "display_genotype": dish.genotype,
            "references": references,
        })

    @app.get("/screening/{dish_id}/steps-table", response_class=HTMLResponse)
    def screening_steps_table(request: Request, dish_id: str):
        """HTMX partial — just the screening steps table rows."""
        dish = fish_dish_ctrl.get_dish(dish_id)
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")
        steps = dish.screening_results.screenings if dish.screening_results else []
        return templates.TemplateResponse(request, "screening/_steps_table.html", {
            "steps": steps,
            "dish_id": dish_id,
            "destination_dishes": _load_destination_dish_options(
                _require_db_path(),
                app.state.busy_timeout_ms,
                dish,
            ),
        })

    @app.post("/screening/{dish_id}/steps", response_class=HTMLResponse)
    def add_screening_step(
        request: Request,
        dish_id: str,
        screening_datetime: str = Form(...),
        dpf_screened: int = Form(...),
        indicators_screened: str = Form(default=""),
        pigment_screened: bool = Form(default=False),
        criteria: Optional[str] = Form(default=None),
        count_screened_this_step: int = Form(...),
        tricaine_used: bool = Form(default=False),
        notes: Optional[str] = Form(default=None),
    ):
        """Submit a new screening step, return HTMX partial."""
        # Parse comma-separated indicators into a list
        indicators_list = [
            ind.strip() for ind in indicators_screened.split(",") if ind.strip()
        ]
        step_data = {
            "screening_datetime": screening_datetime,
            "dpf_screened": dpf_screened,
            "indicators_screened": indicators_list,
            "pigment_screened": pigment_screened,
            "criteria": criteria or None,
            "count_screened_this_step": count_screened_this_step,
            "allocations": [],
            "tricaine_used": tricaine_used,
            "notes": notes or None,
        }

        success, message, _ = fish_dish_ctrl.add_screening_step(dish_id, step_data)

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        # Return updated steps table + success flash
        dish = fish_dish_ctrl.get_dish(dish_id)
        steps = dish.screening_results.screenings if dish and dish.screening_results else []
        return templates.TemplateResponse(request, "screening/_steps_table.html", {
            "steps": steps,
            "dish_id": dish_id,
            "flash_message": message,
            "flash_level": "success",
            "destination_dishes": _load_destination_dish_options(
                _require_db_path(),
                app.state.busy_timeout_ms,
                dish,
            ) if dish else [],
        })

    @app.post("/screening/{dish_id}/steps/{screening_datetime}/allocations", response_class=HTMLResponse)
    def add_screening_step_allocation(
        request: Request,
        dish_id: str,
        screening_datetime: str,
        bucket: str = Form(...),
        disposition: str = Form(...),
        count: int = Form(...),
        notes: Optional[str] = Form(default=None),
    ):
        """Record a non-derived disposition allocation for a screening step."""
        allocation_data = {
            "bucket": bucket,
            "disposition": disposition,
            "count": count,
            "notes": notes or None,
        }

        success, message, _ = fish_dish_ctrl.add_screening_step_allocation(
            dish_id,
            screening_datetime,
            allocation_data,
        )

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        dish = fish_dish_ctrl.get_dish(dish_id)
        steps = dish.screening_results.screenings if dish and dish.screening_results else []
        return templates.TemplateResponse(request, "screening/_steps_table.html", {
            "steps": steps,
            "dish_id": dish_id,
            "flash_message": message,
            "flash_level": "success",
            "destination_dishes": _load_destination_dish_options(
                _require_db_path(),
                app.state.busy_timeout_ms,
                dish,
            ) if dish else [],
        })

    @app.post("/screening/{dish_id}/steps/{screening_datetime}/destination", response_class=HTMLResponse)
    def allocate_screening_step_to_existing_dish(
        request: Request,
        dish_id: str,
        screening_datetime: str,
        bucket: str = Form(...),
        count: int = Form(...),
        destination_dish_id: str = Form(...),
        notes: Optional[str] = Form(default=None),
    ):
        """Allocate screening-step fish into an existing same-cross destination dish."""
        success, message, _ = fish_dish_ctrl.allocate_screening_step_to_existing_dish(
            source_dish_id=dish_id,
            screening_datetime=screening_datetime,
            bucket=bucket,
            count=count,
            destination_dish_id=destination_dish_id,
            notes=notes or None,
        )

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        dish = fish_dish_ctrl.get_dish(dish_id)
        steps = dish.screening_results.screenings if dish and dish.screening_results else []
        return templates.TemplateResponse(request, "screening/_steps_table.html", {
            "steps": steps,
            "dish_id": dish_id,
            "flash_message": message,
            "flash_level": "success",
            "destination_dishes": _load_destination_dish_options(
                _require_db_path(),
                app.state.busy_timeout_ms,
                dish,
            ) if dish else [],
        })

    @app.post("/screening/{dish_id}/finalize", response_class=HTMLResponse)
    def finalize_screening(
        request: Request,
        dish_id: str,
        final_positive_count: int = Form(...),
        date_finalized: str = Form(...),
    ):
        """Finalize screening — set final positive count."""
        success, message = fish_dish_ctrl.finalize_screening(
            dish_id, final_positive_count, date_finalized,
        )

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        # Redirect to the screening form to show updated state
        return RedirectResponse(
            url=f"/screening/{dish_id}",
            status_code=303,
        )

    @app.post("/screening/{dish_id}/split", response_class=HTMLResponse)
    def split_dish(
        request: Request,
        dish_id: str,
        fish_count: int = Form(...),
        population_type: str = Form(default="positive_screened"),
        container_type: Optional[str] = Form(default=None),
        notes: Optional[str] = Form(default=None),
    ):
        """Create a derived dish from a screening step."""
        success, message, new_dish = fish_dish_ctrl.create_derived_dish(
            parent_dish_id=dish_id,
            population_type=population_type,
            fish_count=fish_count,
            container_type=container_type or None,
            notes=notes or None,
        )

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        # Redirect back to screening page with success
        return RedirectResponse(
            url=f"/screening/{dish_id}",
            status_code=303,
        )

    @app.post("/screening/{dish_id}/steps/{screening_datetime}/split", response_class=HTMLResponse)
    def split_dish_from_screening_step(
        request: Request,
        dish_id: str,
        screening_datetime: str,
        fish_count: int = Form(...),
        population_type: str = Form(...),
        container_type: Optional[str] = Form(default=None),
        notes: Optional[str] = Form(default=None),
    ):
        """Create a derived dish linked to a specific screening step."""
        success, message, new_dish = fish_dish_ctrl.create_derived_dish(
            parent_dish_id=dish_id,
            population_type=population_type,
            fish_count=fish_count,
            container_type=container_type or None,
            notes=notes or None,
            source_screening_datetime=screening_datetime,
            source_screening_bucket=population_type,
        )

        if not success:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": message,
                "level": "error",
            })

        return RedirectResponse(
            url=f"/screening/{dish_id}",
            status_code=303,
        )

    # ------------------------------------------------------------------
    # Daily care (web UI)
    # ------------------------------------------------------------------

    @app.get("/care/", response_class=HTMLResponse)
    def care_dish_list(request: Request):
        """Dish list for daily care logging."""
        db_path = _require_db_path()
        today = datetime.now().strftime("%Y%m%d")
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            rows = conn.execute("""
                SELECT d.dish_id, d.genotype, d.fish_count, d.container_type,
                       MAX(q.check_time) AS last_check
                FROM dishes d
                LEFT JOIN quality_checks q ON q.dish_id = d.dish_id
                WHERE d.status = 'active'
                GROUP BY d.dish_id
                ORDER BY d.date_created DESC
            """).fetchall()
        dishes = []
        for row in rows:
            d = _row_to_dict(row)
            last = d.get("last_check") or ""
            d["checked_today"] = last.startswith(today)
            dishes.append(d)
        return templates.TemplateResponse(request, "care/dish_list.html", {
            "dishes": dishes,
        })

    @app.get("/care/{dish_id}", response_class=HTMLResponse)
    def care_form(request: Request, dish_id: str):
        """Care form page — adapts to dish type."""
        db_path = _require_db_path()
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id, genotype, fish_count, container_type FROM dishes WHERE dish_id = ?",
                (dish_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")
            dish = _row_to_dict(row)
        units = data_manager.get_housing_units_with_fish(dish_id)
        has_units = len(units) > 1 or (len(units) == 1 and units[0]["unit_kind"] != "open")
        now = datetime.now().strftime("%Y%m%dT%H:%M:%S")
        transgenes = data_manager.get_dish_transgenes(dish_id)
        return templates.TemplateResponse(request, "care/care_form.html", {
            "dish_id": dish_id,
            "genotype": dish.get("genotype"),
            "fish_count": dish.get("fish_count"),
            "container_type": dish.get("container_type"),
            "units": units,
            "has_units": has_units,
            "now": now,
            "transgenes": transgenes,
        })

    @app.get("/care/{dish_id}/checks-table", response_class=HTMLResponse)
    def care_checks_table(request: Request, dish_id: str):
        """HTMX partial — recent check history."""
        _require_db_path()
        units = data_manager.get_housing_units_with_fish(dish_id)
        has_units = len(units) > 1 or (len(units) == 1 and units[0]["unit_kind"] != "open")

        if has_units:
            # Gather checks across all units
            checks = []
            for u in units:
                for c in data_manager.get_housing_unit_checks(u["unit_id"]):
                    c["unit_id"] = u["unit_id"]
                    checks.append(c)
            checks.sort(key=lambda c: c.get("check_time", ""), reverse=True)
            checks = checks[:50]
        else:
            checks = data_manager.get_dish_quality_checks(dish_id)

        return templates.TemplateResponse(request, "care/_checks_table.html", {
            "checks": checks,
            "unit_level": has_units,
        })

    @app.post("/care/{dish_id}/check", response_class=HTMLResponse)
    def submit_dish_check(
        request: Request,
        dish_id: str,
        check_time: str = Form(...),
        fed: bool = Form(default=False),
        feed_type: Optional[str] = Form(default=None),
        water_changed: bool = Form(default=False),
        vol_water_changed: Optional[int] = Form(default=None),
        num_dead: int = Form(default=0),
        notes: Optional[str] = Form(default=None),
    ):
        """Submit a dish-level quality check."""
        _require_db_path()
        check_data = {
            "check_time": check_time,
            "fed": fed,
            "feed_type": feed_type or None,
            "water_changed": water_changed,
            "vol_water_changed": vol_water_changed,
            "num_dead": num_dead,
            "notes": notes or None,
        }
        success = data_manager.save_dish_quality_check(dish_id, check_data)
        checks = data_manager.get_dish_quality_checks(dish_id)
        return templates.TemplateResponse(request, "care/_checks_table.html", {
            "checks": checks,
            "unit_level": False,
            "flash_message": "Check saved." if success else "Failed to save check.",
            "flash_level": "success" if success else "error",
        })

    @app.post("/care/{dish_id}/unit-checks", response_class=HTMLResponse)
    async def submit_unit_checks(request: Request, dish_id: str):
        """Submit checks for all housing units at once."""
        _require_db_path()
        form = await request.form()
        check_time = form.get("check_time", datetime.now().strftime("%Y%m%dT%H:%M:%S"))

        units = data_manager.get_housing_units_with_fish(dish_id)
        saved = 0
        for u in units:
            uid = u["unit_id"]
            fed = form.get(f"fed_{uid}") == "on"
            water = form.get(f"water_changed_{uid}") == "on"
            feed_type = form.get(f"feed_type_{uid}") or None
            vol_str = form.get(f"vol_water_changed_{uid}")
            vol = int(vol_str) if vol_str else None
            dead_str = form.get(f"num_dead_{uid}")
            num_dead = int(dead_str) if dead_str else 0
            unit_notes = form.get(f"notes_{uid}") or None

            if fed or water or num_dead > 0 or unit_notes:
                ok = data_manager.log_housing_unit_check(
                    unit_id=uid,
                    check_time=check_time,
                    fed=fed,
                    feed_type=feed_type,
                    water_changed=water,
                    vol_water_changed=vol,
                    num_dead=num_dead,
                    notes=unit_notes,
                )
                if ok:
                    saved += 1

        # Return updated checks
        checks = []
        for u in units:
            for c in data_manager.get_housing_unit_checks(u["unit_id"]):
                c["unit_id"] = u["unit_id"]
                checks.append(c)
        checks.sort(key=lambda c: c.get("check_time", ""), reverse=True)
        checks = checks[:50]

        return templates.TemplateResponse(request, "care/_checks_table.html", {
            "checks": checks,
            "unit_level": True,
            "flash_message": f"Saved {saved} unit checks." if saved else "No checks to save (nothing filled in).",
            "flash_level": "success" if saved else "error",
        })

    # ------------------------------------------------------------------
    # Screening images
    # ------------------------------------------------------------------

    @app.post("/screening/{dish_id}/steps/{screening_datetime}/images", response_class=HTMLResponse)
    async def upload_screening_image(
        request: Request,
        dish_id: str,
        screening_datetime: str,
        file: UploadFile = ...,
        caption: Optional[str] = Form(default=None),
    ):
        """Upload an image for a screening step."""
        # Validate file type
        allowed = {"image/jpeg", "image/png"}
        if file.content_type not in allowed:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": f"Invalid file type: {file.content_type}. Only JPEG and PNG are accepted.",
                "level": "error",
            })

        # Determine save path
        images_dir: Path = app.state.screening_images_dir
        dish_dir = images_dir / dish_id
        dish_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: {screening_datetime}_{sequence}.{ext}
        ext = "jpg" if file.content_type == "image/jpeg" else "png"
        existing = list(dish_dir.glob(f"{screening_datetime}_*"))
        seq = len(existing) + 1
        filename = f"{screening_datetime}_{seq:03d}.{ext}"

        # Save file
        dest = dish_dir / filename
        contents = await file.read()
        dest.write_bytes(contents)

        # Record in database
        data_manager.save_screening_image(
            dish_id=dish_id,
            screening_datetime=screening_datetime,
            image_filename=filename,
            caption=caption,
        )

        # Return updated gallery
        images = data_manager.get_screening_images(dish_id, screening_datetime)
        return templates.TemplateResponse(request, "screening/_image_gallery.html", {
            "dish_id": dish_id,
            "screening_datetime": screening_datetime,
            "images": images,
        })

    @app.get("/screening/{dish_id}/steps/{screening_datetime}/images", response_class=HTMLResponse)
    def screening_image_gallery(
        request: Request,
        dish_id: str,
        screening_datetime: str,
    ):
        """HTMX partial — image gallery for a screening step."""
        images = data_manager.get_screening_images(dish_id, screening_datetime)
        return templates.TemplateResponse(request, "screening/_image_gallery.html", {
            "dish_id": dish_id,
            "screening_datetime": screening_datetime,
            "images": images,
        })

    # ------------------------------------------------------------------
    # Fish subject tracking
    # ------------------------------------------------------------------

    @app.get("/dishes/{dish_id}/fish")
    def list_fish_for_dish(dish_id: str) -> Dict[str, Any]:
        """List all fish subjects registered to a dish."""
        _require_db_path()
        subjects = data_manager.get_fish_subjects(dish_id)
        return {"items": subjects}

    @app.post("/dishes/{dish_id}/fish", status_code=201)
    def create_fish_for_dish(
        dish_id: str,
        body: Dict[str, Any] = {},
    ) -> Dict[str, Any]:
        """Register a new fish subject on a dish. Returns the created fish."""
        db_path = _require_db_path()
        # Verify dish exists
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id FROM dishes WHERE dish_id = ?", (dish_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")

        fish_id = data_manager.create_fish_subject(
            dish_id=dish_id,
            fish_id=body.get("fish_id"),
            subject_label=body.get("subject_label"),
            sex=body.get("sex"),
            genotype=body.get("genotype"),
            species=body.get("species"),
            notes=body.get("notes"),
        )
        if fish_id is None:
            raise HTTPException(status_code=500, detail="Failed to create fish subject")
        fish = data_manager.get_fish_subject(fish_id)
        return fish

    @app.get("/fish/{fish_id}")
    def get_fish(fish_id: str) -> Dict[str, Any]:
        """Fetch a single fish subject by UUID."""
        _require_db_path()
        fish = data_manager.get_fish_subject(fish_id)
        if fish is None:
            raise HTTPException(status_code=404, detail="Fish not found")
        return fish

    @app.patch("/fish/{fish_id}")
    def update_fish(fish_id: str, body: Dict[str, Any] = {}) -> Dict[str, Any]:
        """Update mutable fields on a fish subject."""
        _require_db_path()
        existing = data_manager.get_fish_subject(fish_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Fish not found")
        if not data_manager.update_fish_subject(fish_id, **body):
            raise HTTPException(status_code=500, detail="Failed to update fish subject")
        return data_manager.get_fish_subject(fish_id)

    @app.delete("/fish/{fish_id}", status_code=204)
    def delete_fish(request: Request, fish_id: str):
        """Delete a fish subject. Returns HTMX partial when called from the browser."""
        _require_db_path()
        existing = data_manager.get_fish_subject(fish_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Fish not found")
        dish_id = existing["dish_id"]
        if not data_manager.delete_fish_subject(fish_id):
            raise HTTPException(status_code=500, detail="Failed to delete fish subject")
        # If called via HTMX, return updated fish table partial
        if request.headers.get("HX-Request"):
            fish = data_manager.get_fish_subjects(dish_id)
            return templates.TemplateResponse(request, "fish/_fish_table.html", {
                "fish": fish,
                "flash_message": "Fish removed.",
                "flash_level": "success",
            })

    # ------------------------------------------------------------------
    # Fish tracking web UI
    # ------------------------------------------------------------------

    def _dish_context_for_fish_page(dish_id: str):
        """Fetch dish genotype, species, and cross_id for fish pages."""
        db_path = _require_db_path()
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id, genotype, species, cross_id FROM dishes WHERE dish_id = ?",
                (dish_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")
            return _row_to_dict(row)

    @app.get("/dishes/{dish_id}/fish/", response_class=HTMLResponse)
    def fish_list_page(request: Request, dish_id: str):
        """Fish management page for a dish."""
        dish = _dish_context_for_fish_page(dish_id)
        fish = data_manager.get_fish_subjects(dish_id)
        transgenes = data_manager.get_dish_transgenes(dish_id)
        return templates.TemplateResponse(request, "fish/fish_list.html", {
            "dish_id": dish_id,
            "cross_id": dish.get("cross_id"),
            "genotype": dish.get("genotype"),
            "species": dish.get("species") or "Danio rerio",
            "fish": fish,
            "transgenes": transgenes,
        })

    @app.get("/dishes/{dish_id}/plate-map", response_class=HTMLResponse)
    def plate_map(request: Request, dish_id: str):
        """HTMX partial: visual housing map for a dish."""
        _require_db_path()
        units = data_manager.get_housing_units_with_fish(dish_id)
        unassigned = [
            f for f in data_manager.get_fish_subjects(dish_id)
            if f.get("current_unit_id") is None
        ]
        return templates.TemplateResponse(request, "fish/_plate_map.html", {
            "dish_id": dish_id,
            "units": units,
            "unassigned_fish": unassigned,
        })

    @app.post("/dishes/{dish_id}/fish/register", response_class=HTMLResponse)
    def register_fish_htmx(
        request: Request,
        dish_id: str,
        subject_label: Optional[str] = Form(default=None),
        sex: Optional[str] = Form(default=None),
        genotype: Optional[str] = Form(default=None),
        species: Optional[str] = Form(default=None),
        notes: Optional[str] = Form(default=None),
    ):
        """Register a single fish via the web form, return HTMX partial."""
        _dish_context_for_fish_page(dish_id)  # validates dish exists
        fish_id = data_manager.create_fish_subject(
            dish_id=dish_id,
            subject_label=subject_label or None,
            sex=sex or None,
            genotype=genotype or None,
            species=species or None,
            notes=notes or None,
        )
        if fish_id is None:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": "Failed to register fish.",
                "level": "error",
            })
        fish = data_manager.get_fish_subjects(dish_id)
        return templates.TemplateResponse(request, "fish/_fish_table.html", {
            "fish": fish,
            "flash_message": f"Registered fish {subject_label or fish_id[:8]}.",
            "flash_level": "success",
        })

    @app.post("/dishes/{dish_id}/fish/batch", response_class=HTMLResponse)
    def register_fish_batch_htmx(
        request: Request,
        dish_id: str,
        count: int = Form(...),
        label_prefix: Optional[str] = Form(default=None),
    ):
        """Batch-register multiple fish, return HTMX partial."""
        dish = _dish_context_for_fish_page(dish_id)  # validates dish exists
        if count < 1 or count > 96:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": "Count must be between 1 and 96.",
                "level": "error",
            })
        created = 0
        for i in range(1, count + 1):
            label = f"{label_prefix}-{i}" if label_prefix else None
            fish_id = data_manager.create_fish_subject(
                dish_id=dish_id,
                subject_label=label,
                genotype=dish.get("genotype"),
                species=dish.get("species") or "Danio rerio",
            )
            if fish_id is not None:
                created += 1
        fish = data_manager.get_fish_subjects(dish_id)
        return templates.TemplateResponse(request, "fish/_fish_table.html", {
            "fish": fish,
            "flash_message": f"Registered {created} fish.",
            "flash_level": "success",
        })

    # ------------------------------------------------------------------
    # Fish index and cross-level views
    # ------------------------------------------------------------------

    @app.get("/fish/", response_class=HTMLResponse)
    def fish_index_page(request: Request):
        """Top-level fish index — lists crosses that have registered fish."""
        _require_db_path()
        crosses = data_manager.get_crosses_with_fish_counts()
        return templates.TemplateResponse(request, "fish/fish_index.html", {
            "crosses": crosses,
        })

    @app.get("/crosses/{cross_id}/fish")
    def list_fish_for_cross(cross_id: str) -> Dict[str, Any]:
        """List all fish subjects across every dish belonging to a cross."""
        _require_db_path()
        subjects = data_manager.get_fish_subjects_for_cross(cross_id)
        return {"items": subjects}

    @app.get("/crosses/{cross_id}/fish/", response_class=HTMLResponse)
    def fish_cross_page(request: Request, cross_id: str):
        """Web page showing all fish for a cross, grouped by dish."""
        _require_db_path()
        dish_meta = data_manager.get_dishes_for_cross(cross_id)
        subjects = data_manager.get_fish_subjects_for_cross(cross_id)

        # Build dish info lookup and group fish by dish
        dish_info: Dict[str, Dict[str, Any]] = {d["dish_id"]: d for d in dish_meta}
        fish_by_dish: Dict[str, List[Dict[str, Any]]] = {}
        for fish in subjects:
            fish_by_dish.setdefault(fish["dish_id"], []).append(fish)

        children_of: Dict[str, List[Dict[str, Any]]] = {}
        root_dishes: List[Dict[str, Any]] = []

        for dish in dish_meta:
            parent_id = dish.get("parent_dish_id")
            if parent_id and parent_id in dish_info:
                children_of.setdefault(parent_id, []).append(dish)
            else:
                root_dishes.append(dish)

        def _dish_sort_key(dish: Dict[str, Any]) -> Tuple[int, str, str, str]:
            population = dish.get("dish_population_type") or "primary"
            source_dt = dish.get("source_screening_datetime") or ""
            return (
                0 if population == "primary" else 1,
                source_dt,
                population,
                dish.get("dish_id") or "",
            )

        def _build_dish_node(
            dish_id: str,
            seen: Optional[set[str]] = None,
        ) -> Dict[str, Any]:
            seen = set(seen or set())
            dish = dish_info[dish_id]
            cycle_detected = dish_id in seen
            if cycle_detected:
                return {
                    "dish": dish,
                    "fish": fish_by_dish.get(dish_id, []),
                    "children": [],
                    "cycle_detected": True,
                }

            seen.add(dish_id)
            child_nodes = [
                _build_dish_node(child["dish_id"], seen)
                for child in sorted(children_of.get(dish_id, []), key=_dish_sort_key)
            ]
            return {
                "dish": dish,
                "fish": fish_by_dish.get(dish_id, []),
                "children": child_nodes,
                "cycle_detected": False,
            }

        dish_tree = [
            _build_dish_node(d["dish_id"])
            for d in sorted(root_dishes, key=_dish_sort_key)
        ]

        return templates.TemplateResponse(request, "fish/fish_cross.html", {
            "cross_id": cross_id,
            "dish_tree": dish_tree,
            "total_fish": len(subjects),
            "total_dishes": len(dish_meta),
        })

    # ------------------------------------------------------------------
    # Housing units
    # ------------------------------------------------------------------

    @app.get("/dishes/{dish_id}/units")
    def list_housing_units(dish_id: str) -> Dict[str, Any]:
        """List housing units for a dish with occupancy counts."""
        _require_db_path()
        units = data_manager.get_housing_units(dish_id)
        return {"items": units}

    @app.post("/dishes/{dish_id}/units", status_code=201)
    def create_housing_units(
        dish_id: str,
        body: Dict[str, Any] = {},
    ) -> Dict[str, Any]:
        """Create housing unit(s) for a dish.

        Body accepts:
        - unit_kind: "open", "well", "lane", "chamber" (default "open")
        - count: number of units to create (default 1)
        - label_format: "numeric" or "well_plate" (default "numeric")
        - position_label: for single-unit creation (ignored if count > 1)
        - capacity: per-unit capacity (default 1)
        - notes: optional
        """
        db_path = _require_db_path()
        # Verify dish exists
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id FROM dishes WHERE dish_id = ?", (dish_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")

        unit_kind = body.get("unit_kind", "open")
        count = body.get("count", 1)

        if count > 1:
            label_format = body.get("label_format", "numeric")
            created_ids = data_manager.create_housing_units_for_dish(
                dish_id=dish_id,
                unit_kind=unit_kind,
                count=count,
                label_format=label_format,
            )
            if not created_ids:
                raise HTTPException(status_code=500, detail="Failed to create housing units")
            return {"created": created_ids}
        else:
            unit_id = data_manager.create_housing_unit(
                dish_id=dish_id,
                unit_kind=unit_kind,
                position_label=body.get("position_label"),
                capacity=body.get("capacity", 1),
                notes=body.get("notes"),
            )
            if unit_id is None:
                raise HTTPException(status_code=500, detail="Failed to create housing unit")
            return data_manager.get_housing_unit(unit_id)

    @app.get("/units/{unit_id}")
    def get_unit(unit_id: str) -> Dict[str, Any]:
        """Fetch a housing unit with its current fish list."""
        _require_db_path()
        unit = data_manager.get_housing_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Housing unit not found")
        return unit

    @app.post("/units/{unit_id}/checks", status_code=201)
    def log_unit_check(
        unit_id: str,
        body: Dict[str, Any] = {},
    ) -> Dict[str, str]:
        """Log a maintenance check for a housing unit position."""
        _require_db_path()
        if data_manager.get_housing_unit(unit_id) is None:
            raise HTTPException(status_code=404, detail="Housing unit not found")
        check_time = body.get("check_time")
        if not check_time:
            raise HTTPException(status_code=422, detail="check_time is required")
        success = data_manager.log_housing_unit_check(
            unit_id=unit_id,
            check_time=check_time,
            fed=body.get("fed"),
            feed_type=body.get("feed_type"),
            water_changed=body.get("water_changed"),
            vol_water_changed=body.get("vol_water_changed"),
            num_dead=body.get("num_dead", 0),
            notes=body.get("notes"),
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to log check")
        return {"status": "ok"}

    @app.get("/units/{unit_id}/checks")
    def get_unit_checks(unit_id: str) -> Dict[str, Any]:
        """Maintenance history for a housing unit position."""
        _require_db_path()
        checks = data_manager.get_housing_unit_checks(unit_id)
        return {"items": checks}

    @app.post("/fish/{fish_id}/assign", status_code=200)
    def assign_or_move_fish(
        fish_id: str,
        body: Dict[str, Any] = {},
    ) -> Dict[str, Any]:
        """Assign a fish to a housing unit, or move it if already assigned."""
        _require_db_path()
        fish = data_manager.get_fish_subject(fish_id)
        if fish is None:
            raise HTTPException(status_code=404, detail="Fish not found")
        new_unit_id = body.get("unit_id")
        if not new_unit_id:
            raise HTTPException(status_code=422, detail="unit_id is required")
        if data_manager.get_housing_unit(new_unit_id) is None:
            raise HTTPException(status_code=404, detail="Housing unit not found")
        reason = body.get("reason", "transfer")
        if fish.get("current_unit_id"):
            success = data_manager.move_fish(fish_id, new_unit_id, reason)
        else:
            success = data_manager.assign_fish_to_unit(fish_id, new_unit_id, reason)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to assign fish")
        return data_manager.get_fish_subject(fish_id)

    @app.get("/fish/{fish_id}/history")
    def get_fish_history(fish_id: str) -> Dict[str, Any]:
        """Occupancy history for a fish — where it has lived."""
        _require_db_path()
        if data_manager.get_fish_subject(fish_id) is None:
            raise HTTPException(status_code=404, detail="Fish not found")
        history = data_manager.get_fish_occupancy_history(fish_id)
        return {"items": history}

    # ------------------------------------------------------------------
    # Fish reference images
    # ------------------------------------------------------------------

    @app.post("/fish/{fish_id}/images", response_class=HTMLResponse)
    async def upload_fish_image(
        request: Request,
        fish_id: str,
        file: UploadFile = ...,
        caption: Optional[str] = Form(default=None),
    ):
        """Upload a reference image for a fish."""
        _require_db_path()
        fish = data_manager.get_fish_subject(fish_id)
        if fish is None:
            raise HTTPException(status_code=404, detail="Fish not found")

        allowed = {"image/jpeg", "image/png"}
        if file.content_type not in allowed:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": f"Invalid file type: {file.content_type}. Only JPEG and PNG are accepted.",
                "level": "error",
            })

        fish_images_dir: Path = app.state.fish_images_dir
        fish_dir = fish_images_dir / fish_id
        fish_dir.mkdir(parents=True, exist_ok=True)

        ext = "jpg" if file.content_type == "image/jpeg" else "png"
        existing = list(fish_dir.glob("*"))
        seq = len(existing) + 1
        filename = f"{seq:03d}.{ext}"

        dest = fish_dir / filename
        contents = await file.read()
        dest.write_bytes(contents)

        data_manager.save_fish_image(
            fish_id=fish_id,
            image_filename=filename,
            image_type="reference",
            caption=caption,
        )

        images = data_manager.get_fish_images(fish_id)
        return templates.TemplateResponse(request, "fish/_image_gallery.html", {
            "fish_id": fish_id,
            "images": images,
        })

    @app.get("/fish/{fish_id}/images", response_class=HTMLResponse)
    def fish_image_gallery(
        request: Request,
        fish_id: str,
    ):
        """HTMX partial — image gallery for a fish."""
        _require_db_path()
        images = data_manager.get_fish_images(fish_id)
        return templates.TemplateResponse(request, "fish/_image_gallery.html", {
            "fish_id": fish_id,
            "images": images,
        })

    # ------------------------------------------------------------------
    # In-browser walkthrough setup / cleanup
    # ------------------------------------------------------------------

    @app.post("/walkthrough/setup")
    def walkthrough_setup() -> Dict[str, Any]:
        """Create test data for the in-browser guided tour.

        Creates a dish, screening step, derived dishes, fish, housing units,
        and a care check.  Returns all created IDs for later cleanup.
        """
        db_path = _require_db_path()

        # Find a cross_id to attach to
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT cross_id FROM dishes WHERE cross_id IS NOT NULL LIMIT 1"
            ).fetchone()
        cross_id = row["cross_id"] if row else "TOUR_CROSS"

        dish_id = f"TOUR_{cross_id}_1"

        # 1. Create parent dish
        with data_manager.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dishes
                   (dish_id, data, genotype, species, cross_id, status,
                    dish_population_type, date_created, dof, responsible,
                    fish_count, container_type, room)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dish_id,
                    json.dumps({"dish_id": dish_id, "fish_count": 20}),
                    "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)",
                    "Danio rerio",
                    cross_id,
                    "active",
                    "primary",
                    datetime.now().strftime("%Y%m%d"),
                    (datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                    "tour",
                    20,
                    "petri_dish",
                    "2E.282",
                ),
            )
            conn.commit()

        dish_ids = [dish_id]

        # 2. Screening step
        step_data = {
            "screening_datetime": datetime.now().strftime("%Y%m%dT%H:%M:%S"),
            "dpf_screened": 5,
            "indicators_screened": ["gfap:TRPV1-T2A-GFP"],
            "pigment_screened": False,
            "criteria": "Check pan-glial expression",
            "count_screened_this_step": 20,
            "allocations": [
                {
                    "bucket": "remaining_in_parent",
                    "disposition": "remain_parent",
                    "count": 12,
                    "notes": "Tour: fish retained for follow-up",
                },
                {
                    "bucket": "negative_screened",
                    "disposition": "discarded",
                    "count": 8,
                    "notes": "Tour: negative fish removed",
                },
            ],
            "tricaine_used": True,
            "notes": "Tour: DPF 5 gfap screen",
        }
        fish_dish_ctrl.add_screening_step(dish_id, step_data)

        # 3. Derived dish (positive → well plate)
        success, pos_id_or_msg, _ = fish_dish_ctrl.create_derived_dish(
            parent_dish_id=dish_id,
            population_type="positive_screened",
            fish_count=12,
            container_type="well_plate",
            notes="Tour: kept fish moved to well plate",
        )
        pos_dish = pos_id_or_msg if success else None
        if pos_dish:
            dish_ids.append(pos_dish)

        # 4. Register fish + housing units on derived dish
        fish_ids = []
        if pos_dish:
            for i in range(1, 5):
                fid = data_manager.create_fish_subject(
                    dish_id=pos_dish,
                    subject_label=f"wt-{i:02d}",
                    genotype="Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)",
                    species="Danio rerio",
                )
                if fid:
                    fish_ids.append(fid)

            unit_ids = data_manager.create_housing_units_for_dish(
                dish_id=pos_dish, unit_kind="well", count=4, label_format="well_plate",
            )
            for fid, uid in zip(fish_ids, unit_ids):
                data_manager.assign_fish_to_unit(fid, uid, reason="initial")

        return {
            "dish_ids": dish_ids,
            "fish_ids": fish_ids,
            "pos_dish": pos_dish,
            "parent_dish": dish_id,
        }

    @app.post("/walkthrough/cleanup")
    def walkthrough_cleanup(body: Dict[str, Any] = {}) -> Dict[str, Any]:
        """Remove all test data created by walkthrough/setup."""
        _require_db_path()
        # Only allow deletion of tour-prefixed dishes to prevent misuse
        dish_ids = [d for d in body.get("dish_ids", []) if d.startswith("TOUR_")]
        fish_ids = body.get("fish_ids", [])

        # Also find any other TOUR_ dishes in the database (stale from previous tours)
        with data_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT dish_id FROM dishes WHERE dish_id LIKE 'TOUR_%'"
            ).fetchall()
            for row in rows:
                if row["dish_id"] not in dish_ids:
                    dish_ids.append(row["dish_id"])
            # Find fish belonging to any TOUR_ dishes
            fish_rows = conn.execute(
                "SELECT fish_id FROM fish_subjects WHERE dish_id LIKE 'TOUR_%'"
            ).fetchall()
            for row in fish_rows:
                if row["fish_id"] not in fish_ids:
                    fish_ids.append(row["fish_id"])

        # Delete fish via data_manager (cascades to images, occupancy)
        for fid in fish_ids:
            data_manager.delete_fish_subject(fid)

        # SQL cleanup for remaining data
        with data_manager.get_connection() as conn:
            for did in dish_ids:
                conn.execute(
                    "DELETE FROM housing_unit_occupancy WHERE unit_id IN "
                    "(SELECT unit_id FROM housing_units WHERE dish_id = ?)", (did,))
                conn.execute(
                    "DELETE FROM housing_unit_checks WHERE unit_id IN "
                    "(SELECT unit_id FROM housing_units WHERE dish_id = ?)", (did,))
                conn.execute("DELETE FROM housing_units WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM dish_images WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM quality_checks WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM dish_transgenes WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM screening_step_images WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM screening_steps WHERE dish_id = ?", (did,))
                conn.execute("DELETE FROM dishes WHERE dish_id = ?", (did,))
            conn.commit()

        # Clean up image files
        db_dir = Path(_require_db_path()).parent
        for subdir in ("dish_images", "fish_images", "screening_images"):
            img_dir = db_dir / subdir
            if img_dir.exists():
                for did in dish_ids:
                    d = img_dir / did
                    if d.exists():
                        for f in d.iterdir():
                            f.unlink()
                        d.rmdir()

        return {"status": "ok", "cleaned": len(dish_ids)}

    # ------------------------------------------------------------------
    # PyRAT browser (web UI)
    # ------------------------------------------------------------------

    @app.get("/pyrat/tanks/", response_class=HTMLResponse)
    def pyrat_tanks_page(request: Request):
        """Tank list with age monitoring."""
        tanks = []
        error_msg = None
        try:
            responsible_id = _pyrat_user_id(_current_user(request))
            params = {
                "l": 500,
                "s": ["date_of_birth:asc"],
                "k": [
                    "tank_id", "tank_label", "status",
                    "strain_name_with_id",
                    "number_of_male", "number_of_female", "number_of_unknown",
                    "date_of_birth",
                    "location_rack_name", "tank_position",
                ],
            }
            if responsible_id:
                params["responsible_id"] = responsible_id
            params["status"] = "open"

            raw = _fetch_pyrat("tanks", params)
            now = datetime.now()
            for t in raw:
                total = (t.get("number_of_male") or 0) + (t.get("number_of_female") or 0) + (t.get("number_of_unknown") or 0)
                t["total_fish"] = total

                dob = t.get("date_of_birth")
                if dob:
                    try:
                        born = datetime.strptime(dob[:10], "%Y-%m-%d")
                        age = (now - born).days
                        t["age_days"] = age
                        if age > 365:
                            t["age_status"] = "URGENT"
                        elif age > 315:
                            t["age_status"] = "WARNING"
                        else:
                            t["age_status"] = "OK"
                    except ValueError:
                        t["age_days"] = None
                        t["age_status"] = "UNKNOWN"
                else:
                    t["age_days"] = None
                    t["age_status"] = "UNKNOWN"
                tanks.append(t)
            # Sort: urgent first, then by age descending
            status_order = {"URGENT": 0, "WARNING": 1, "OK": 2, "UNKNOWN": 3}
            tanks.sort(key=lambda x: (status_order.get(x["age_status"], 3), -(x["age_days"] or 0)))
        except HTTPException as e:
            error_msg = e.detail
        except Exception as e:
            error_msg = str(e)

        return templates.TemplateResponse(request, "pyrat/tanks.html", {
            "tanks": tanks,
            "error": error_msg,
        })

    @app.get("/pyrat/crossings/", response_class=HTMLResponse)
    def pyrat_crossings_page(request: Request):
        """Crossing list with performance tracking."""
        crossings = []
        error_msg = None
        details_refresh_enabled = bool(get_pyrat_frontend_credentials())
        try:
            responsible_id = _pyrat_user_id(_current_user(request))
            params = {
                "l": 200,
                "s": ["date_of_record:desc"],
                "k": [
                    "crossing_id", "status", "date_of_record", "date_of_set_up", "date_of_raise",
                    "strain_name", "description", "tanks",
                ],
                "tk": [
                    "tank_id", "tank_label", "status",
                ],
            }
            if responsible_id:
                params["responsible_id"] = responsible_id

            page_started = perf_counter()
            raw = _fetch_pyrat("tanks/crossings", params)
            _cache_cross_rows(raw)

            # Get local dish counts per cross
            db_path = _require_db_path()
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                dish_counts = _load_cross_dish_counts(conn)
                cached_payloads = _load_cached_cross_payloads(
                    conn,
                    [str(item.get("crossing_id", "")) for item in raw if item.get("crossing_id")],
                )

            crossings = _prepare_crossings_for_display(raw, dish_counts, cached_payloads)
            logger.info("PyRAT crossings page built %s row(s) in %.2fs", len(crossings), perf_counter() - page_started)
        except HTTPException as e:
            error_msg = e.detail
        except Exception as e:
            error_msg = str(e)

        return templates.TemplateResponse(request, "pyrat/crossings.html", {
            "crossings": crossings,
            "error": error_msg,
            "details_refresh_enabled": details_refresh_enabled,
        })

    @app.get("/pyrat/crossings/table", response_class=HTMLResponse)
    def pyrat_crossings_table(request: Request):
        """HTMX partial: crossing table with fresh backend/v1 detail enrichment."""
        crossings: List[Dict[str, Any]] = []
        error_msg = None
        try:
            responsible_id = _pyrat_user_id(_current_user(request))
            params = {
                "l": 200,
                "s": ["date_of_record:desc"],
                "k": [
                    "crossing_id", "status", "date_of_record", "date_of_set_up", "date_of_raise",
                    "strain_name", "description", "tanks",
                ],
                "tk": [
                    "tank_id", "tank_label", "status",
                ],
            }
            if responsible_id:
                params["responsible_id"] = responsible_id

            table_started = perf_counter()
            raw = _fetch_pyrat("tanks/crossings", params)
            _cache_cross_rows(raw)

            enrich_started = perf_counter()
            raw = enrich_crossings_with_frontend_details(
                raw,
                get_pyrat_frontend_credentials(),
            )
            logger.info(
                "PyRAT crossings table refresh enriched %s crossing(s) in %.2fs",
                len(raw),
                perf_counter() - enrich_started,
            )
            _cache_cross_rows(raw)

            db_path = _require_db_path()
            with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
                dish_counts = _load_cross_dish_counts(conn)
            crossings = _prepare_crossings_for_display(raw, dish_counts)
            logger.info(
                "PyRAT crossings table refresh rendered %s row(s) in %.2fs",
                len(crossings),
                perf_counter() - table_started,
            )
        except HTTPException as e:
            error_msg = e.detail
        except Exception as e:
            error_msg = str(e)

        return templates.TemplateResponse(request, "pyrat/_crossings_table.html", {
            "crossings": crossings,
            "error": error_msg,
            "details_refresh_enabled": False,
        })

    # ------------------------------------------------------------------
    # Dish labels (QR code + metadata)
    # ------------------------------------------------------------------

    @app.get("/dishes/{dish_id}/label")
    def dish_label(dish_id: str):
        """Generate a printable label PNG with QR code for a dish."""
        db_path = _require_db_path()
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id, genotype, dof, fish_count, container_type FROM dishes WHERE dish_id = ?",
                (dish_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")
            dish = _row_to_dict(row)
        png_bytes = generate_dish_label(
            dish_id=dish["dish_id"],
            genotype=dish.get("genotype"),
            dof=dish.get("dof"),
            fish_count=dish.get("fish_count"),
            container_type=dish.get("container_type"),
        )
        return Response(content=png_bytes, media_type="image/png")

    # ------------------------------------------------------------------
    # Dish-level reference images
    # ------------------------------------------------------------------

    @app.post("/dishes/{dish_id}/images", response_class=HTMLResponse)
    async def upload_dish_image(
        request: Request,
        dish_id: str,
        file: UploadFile = ...,
        caption: Optional[str] = Form(default=None),
    ):
        """Upload a reference image for a dish (for bulk populations without individual fish)."""
        db_path = _require_db_path()
        with _open_readonly_connection(db_path, app.state.busy_timeout_ms) as conn:
            row = conn.execute(
                "SELECT dish_id FROM dishes WHERE dish_id = ?", (dish_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Dish not found")

        allowed = {"image/jpeg", "image/png"}
        if file.content_type not in allowed:
            return templates.TemplateResponse(request, "screening/_flash_message.html", {
                "message": f"Invalid file type: {file.content_type}. Only JPEG and PNG are accepted.",
                "level": "error",
            })

        dish_images_dir: Path = app.state.dish_images_dir
        dish_dir = dish_images_dir / dish_id
        dish_dir.mkdir(parents=True, exist_ok=True)

        ext = "jpg" if file.content_type == "image/jpeg" else "png"
        existing = list(dish_dir.glob("*"))
        seq = len(existing) + 1
        filename = f"{seq:03d}.{ext}"

        dest = dish_dir / filename
        contents = await file.read()
        dest.write_bytes(contents)

        data_manager.save_dish_image(
            dish_id=dish_id,
            image_filename=filename,
            image_type="reference",
            caption=caption,
        )

        images = data_manager.get_dish_images(dish_id)
        return templates.TemplateResponse(request, "fish/_dish_image_gallery.html", {
            "dish_id": dish_id,
            "images": images,
        })

    @app.get("/dishes/{dish_id}/images", response_class=HTMLResponse)
    def dish_image_gallery(
        request: Request,
        dish_id: str,
    ):
        """HTMX partial — reference image gallery for a dish."""
        _require_db_path()
        images = data_manager.get_dish_images(dish_id)
        return templates.TemplateResponse(request, "fish/_dish_image_gallery.html", {
            "dish_id": dish_id,
            "images": images,
        })

    return app


app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MetaZebrobot API server.")
    parser.add_argument("--db-path", help="Path to zebrobot.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--busy-timeout-ms", type=int, default=DEFAULT_BUSY_TIMEOUT_MS)
    parser.add_argument(
        "--lab-network",
        action="store_true",
        help="Bind to 0.0.0.0 so other devices on the LAN can connect",
    )
    args = parser.parse_args()

    resolved_host = "0.0.0.0" if args.lab_network else args.host

    app = create_app(args.db_path)
    app.state.busy_timeout_ms = args.busy_timeout_ms

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "uvicorn is required to run the API. Install with "
            "`pixi run python -m metazebrobot.api_server ...`, "
            "`pip install -e . fastapi uvicorn`, or `pip install uvicorn fastapi`."
        ) from exc

    uvicorn.run(app, host=resolved_host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
