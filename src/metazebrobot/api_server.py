"""
FastAPI service for MetaZebrobot — read-only JSON API + web screening UI.
"""

import argparse
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .controllers.fish_dish_controller import FishDishController
from .data.data_manager import data_manager
from .utils.label_generator import generate_dish_label

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_BUSY_TIMEOUT_MS = 250


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
        # We can't call data_manager.initialize() directly because it
        # reads database_path from the desktop app's config which isn't
        # available in the API server context.
        data_manager.database_path = db_path
        data_manager._is_initialized = True
        data_manager.config_dir = _PACKAGE_DIR / "config"

        # Ensure schema is up to date (screening_step_images table etc.)
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
            # Normalized transgenes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dish_transgenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dish_id TEXT NOT NULL,
                    construct TEXT NOT NULL,
                    promoter TEXT NOT NULL,
                    reporter TEXT,
                    fluorophore TEXT,
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
            conn.commit()

        data_manager.load_all_data()
        logger.info(f"data_manager initialised with {db_path}")

        # Backfill dish_transgenes for existing dishes (one-time migration)
        data_manager.backfill_dish_transgenes()

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

        # Pre-fetch mapzebrain atlas catalog (non-blocking — logs warning on failure)
        data_manager.fetch_mapzebrain_catalog()
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
    # Home page
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home_page(request: Request):
        """Landing page."""
        return templates.TemplateResponse(request, "home.html", {})

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
        import keyring
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Get PyRAT credentials
        base_url = keyring.get_password("pyrat-api", "base_url")
        client_token = keyring.get_password("pyrat-api", "client_token")
        user_token = keyring.get_password("pyrat-api", "user_token")
        if not all([base_url, client_token, user_token]):
            raise HTTPException(status_code=503, detail="PyRAT API credentials not configured")

        # Fetch crossing from PyRAT (list endpoint with crossing_id filter)
        if not base_url.endswith("/"):
            base_url += "/"
        url = f"{base_url}api/v3/tanks/crossings"
        try:
            resp = requests.get(
                url,
                auth=(client_token, user_token),
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
                SELECT d.dish_id, d.genotype, d.dof, d.fish_count, d.responsible,
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

        # mapzebrain atlas expression pattern images
        atlas_catalog_available = bool(data_manager.fetch_mapzebrain_catalog())
        atlas_lines = data_manager.lookup_mapzebrain_lines(
            dish_id=dish_id, genotype=dish.genotype
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
            "atlas_lines": atlas_lines,
            "atlas_catalog_available": atlas_catalog_available,
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
        number_kept: int = Form(...),
        number_removed_pigmented: Optional[int] = Form(default=None),
        number_removed_negative: Optional[int] = Form(default=None),
        number_removed_other: Optional[int] = Form(default=None),
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
            "number_kept": number_kept,
            "number_removed_pigmented": number_removed_pigmented,
            "number_removed_negative": number_removed_negative,
            "number_removed_other": number_removed_other,
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
        return templates.TemplateResponse(request, "care/care_form.html", {
            "dish_id": dish_id,
            "genotype": dish.get("genotype"),
            "fish_count": dish.get("fish_count"),
            "container_type": dish.get("container_type"),
            "units": units,
            "has_units": has_units,
            "now": now,
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
        return templates.TemplateResponse(request, "fish/fish_list.html", {
            "dish_id": dish_id,
            "cross_id": dish.get("cross_id"),
            "genotype": dish.get("genotype"),
            "species": dish.get("species") or "Danio rerio",
            "fish": fish,
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
        dish_info: Dict[str, Dict[str, Any]] = {}
        for d in dish_meta:
            dish_info[d["dish_id"]] = d

        fish_by_dish: Dict[str, List[Dict[str, Any]]] = {}
        for fish in subjects:
            fish_by_dish.setdefault(fish["dish_id"], []).append(fish)

        # Separate primary dishes (no parent) from derived dishes
        primary_dishes = [d for d in dish_meta if not d.get("parent_dish_id")]
        derived_dishes = [d for d in dish_meta if d.get("parent_dish_id")]

        # Map parent_dish_id → list of child dishes
        children_of: Dict[str, List[Dict[str, Any]]] = {}
        for d in derived_dishes:
            children_of.setdefault(d["parent_dish_id"], []).append(d)

        return templates.TemplateResponse(request, "fish/fish_cross.html", {
            "cross_id": cross_id,
            "primary_dishes": primary_dishes,
            "children_of": children_of,
            "fish_by_dish": fish_by_dish,
            "dish_info": dish_info,
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
            "number_kept": 12,
            "number_removed_negative": 8,
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
            "`pip install .[api]` or `pip install uvicorn fastapi`."
        ) from exc

    uvicorn.run(app, host=resolved_host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
