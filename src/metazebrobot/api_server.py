"""
FastAPI service for MetaZebrobot — read-only JSON API + web screening UI.
"""

import argparse
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .controllers.fish_dish_controller import FishDishController
from .data.data_manager import data_manager

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
            conn.commit()

        data_manager.load_all_data()
        logger.info(f"data_manager initialised with {db_path}")

        # Ensure screening images directory exists
        images_dir = db_path.parent / "screening_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        app.state.screening_images_dir = images_dir
        logger.info(f"Screening images directory: {images_dir}")
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
        """Return the matching protocol step (if any) for a genotype + DPF."""
        protocols = data_manager.get_screening_protocols()
        proto = protocols.get(genotype) or protocols.get("_default")
        if not proto:
            return None, None
        for step in proto.get("steps", []):
            lo, hi = step.get("dpf_range", [0, 999])
            if dpf is not None and lo <= dpf <= hi:
                return proto, step
        return proto, None

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
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> Dict[str, Any]:
        db_path = _require_db_path()
        query = """
            SELECT dish_id, cross_id, genotype, responsible, fish_count, dof,
                   status, date_created
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
        all_dishes = fish_dish_ctrl.get_all_dishes(include_inactive=False)
        dishes = []
        for dish_id, dish in sorted(all_dishes.items()):
            ref_date = _last_screening_date(dish)
            dpf = _dpf_from_dof(dish.dof, ref_date)
            step_count = len(dish.screening_results.screenings) if dish.screening_results else 0
            finalized = dish.screening_results.final_positive_count is not None if dish.screening_results else False
            dishes.append({
                "dish_id": dish_id,
                "genotype": dish.genotype,
                "dof": dish.dof,
                "dpf": dpf,
                "fish_count": dish.fish_count,
                "responsible": dish.responsible,
                "step_count": step_count,
                "finalized": finalized,
            })
        return templates.TemplateResponse("screening/dish_list.html", {
            "request": request,
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

        return templates.TemplateResponse("screening/screening_form.html", {
            "request": request,
            "dish": dish,
            "dpf": dpf,
            "protocol": protocol,
            "current_step": current_step,
            "steps": steps,
            "finalized": finalized,
            "final_count": final_count,
            "indicator_images": indicator_images,
            "step_images": step_images,
        })

    @app.get("/screening/{dish_id}/steps-table", response_class=HTMLResponse)
    def screening_steps_table(request: Request, dish_id: str):
        """HTMX partial — just the screening steps table rows."""
        dish = fish_dish_ctrl.get_dish(dish_id)
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")
        steps = dish.screening_results.screenings if dish.screening_results else []
        return templates.TemplateResponse("screening/_steps_table.html", {
            "request": request,
            "steps": steps,
        })

    @app.post("/screening/{dish_id}/steps", response_class=HTMLResponse)
    def add_screening_step(
        request: Request,
        dish_id: str,
        screening_datetime: str = Form(...),
        dpf_screened: int = Form(...),
        indicator_screened: str = Form(...),
        criteria: str = Form(...),
        count_screened_this_step: int = Form(...),
        number_positive: int = Form(...),
        number_removed_pigmented: Optional[int] = Form(default=None),
        number_removed_negative: Optional[int] = Form(default=None),
        number_removed_other: Optional[int] = Form(default=None),
        tricaine_used: bool = Form(default=False),
        notes: Optional[str] = Form(default=None),
    ):
        """Submit a new screening step, return HTMX partial."""
        step_data = {
            "screening_datetime": screening_datetime,
            "dpf_screened": dpf_screened,
            "indicator_screened": indicator_screened,
            "criteria": criteria,
            "count_screened_this_step": count_screened_this_step,
            "number_positive": number_positive,
            "number_removed_pigmented": number_removed_pigmented,
            "number_removed_negative": number_removed_negative,
            "number_removed_other": number_removed_other,
            "tricaine_used": tricaine_used,
            "notes": notes or None,
        }

        success, message, _ = fish_dish_ctrl.add_screening_step(dish_id, step_data)

        if not success:
            return templates.TemplateResponse("screening/_flash_message.html", {
                "request": request,
                "message": message,
                "level": "error",
            })

        # Return updated steps table + success flash
        dish = fish_dish_ctrl.get_dish(dish_id)
        steps = dish.screening_results.screenings if dish and dish.screening_results else []
        return templates.TemplateResponse("screening/_steps_table.html", {
            "request": request,
            "steps": steps,
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
            return templates.TemplateResponse("screening/_flash_message.html", {
                "request": request,
                "message": message,
                "level": "error",
            })

        # Redirect to the screening form to show updated state
        return RedirectResponse(
            url=f"/screening/{dish_id}",
            status_code=303,
        )

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
            return templates.TemplateResponse("screening/_flash_message.html", {
                "request": request,
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
        return templates.TemplateResponse("screening/_image_gallery.html", {
            "request": request,
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
        return templates.TemplateResponse("screening/_image_gallery.html", {
            "request": request,
            "dish_id": dish_id,
            "screening_datetime": screening_datetime,
            "images": images,
        })

    return app


app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MetaZebrobot API server.")
    parser.add_argument("--db-path", help="Path to zebrobot.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
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
