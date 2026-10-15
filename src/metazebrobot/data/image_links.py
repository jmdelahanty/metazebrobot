"""Screening images linked to dishes and fish by reference (docs/screening_images_design.md).

Files stay on lab storage under the screening staging root; this stores one
row per (file, dish) with its relative path, size, sha256 and OME channel
metadata, and the fish when the filename names its well. Previews are
rendered on demand into a cache directory.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.lab_time import LAB_TIMEZONE

IMAGE_SUFFIXES = (".ome.tif", ".ome.tiff")
KINDS = ("screening", "propagation", "plate")
_WELL = re.compile(r"^[A-Ha-h](1[0-2]|[1-9])$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS image_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path TEXT NOT NULL,
    dish_id TEXT NOT NULL,
    fish_id TEXT,
    well_label TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('screening', 'propagation', 'plate')),
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    file_mtime TEXT NOT NULL,
    channels TEXT,
    size_x INTEGER,
    size_y INTEGER,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    linked_by TEXT,
    UNIQUE (rel_path, dish_id)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_links_dish ON image_links(dish_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_image_links_fish ON image_links(fish_id)")


def resolve_under(root: Path, rel_path: str) -> Path:
    """The absolute path of ``rel_path`` inside ``root``; ValueError if it escapes."""
    root = Path(root).resolve()
    path = (root / rel_path).resolve()
    if root != path and root not in path.parents:
        raise ValueError(f"{rel_path} is outside the screening staging root")
    return path


def is_image(path: Path) -> bool:
    return path.is_file() and path.name.lower().endswith(IMAGE_SUFFIXES)


def well_from_filename(name: str) -> Optional[str]:
    """'19327_6_pos1_A1-OME TIFF-Export-01.ome.tiff' -> 'A1'; 'A3-OME…' -> 'A3'."""
    lead = re.split(r"-OME|-Image| ", name, maxsplit=1)[0]
    token = lead.split("_")[-1]
    return token.upper() if _WELL.match(token) else None


def list_folders(root: Path) -> List[str]:
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and any(is_image(f) for f in p.iterdir()))


def _utc_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fish_in_well(conn, dish_id: str, well: str, at_utc: Optional[str]) -> Optional[Dict[str, Any]]:
    """The fish in ``dish_id``'s well at ``at_utc`` (else its current occupant)."""
    unit_id = f"{dish_id}:{well}"
    if at_utc:
        row = conn.execute(
            """SELECT f.fish_id, f.subject_label FROM housing_unit_occupancy o
               JOIN fish_subjects f ON f.fish_id = o.fish_id
               WHERE o.unit_id = ? AND o.moved_in_at <= ?
                 AND (o.moved_out_at IS NULL OR o.moved_out_at > ?)
               ORDER BY o.moved_in_at DESC LIMIT 1""",
            (unit_id, at_utc, at_utc),
        ).fetchone()
        if row:
            return dict(row)
    row = conn.execute(
        "SELECT fish_id, subject_label FROM fish_subjects WHERE current_unit_id = ? "
        "ORDER BY created_at DESC LIMIT 1", (unit_id,)).fetchone()
    return dict(row) if row else None


def scan(conn, root: Path, folder: str, dish_id: Optional[str]) -> Dict[str, Any]:
    """Proposed links for a folder: dish, and per file its well and fish."""
    folder_path = resolve_under(root, folder)
    proposed_dish = dish_id or (folder if conn.execute(
        "SELECT 1 FROM dishes WHERE dish_id = ?", (folder,)).fetchone() else None)
    files = []
    for path in sorted(p for p in folder_path.iterdir() if is_image(p)):
        rel = path.relative_to(Path(root).resolve()).as_posix()
        well = well_from_filename(path.name)
        fish = (fish_in_well(conn, proposed_dish, well, _utc_mtime(path))
                if proposed_dish and well else None)
        linked = conn.execute(
            "SELECT id FROM image_links WHERE rel_path = ? AND dish_id = ?",
            (rel, proposed_dish)).fetchone() if proposed_dish else None
        files.append({"rel_path": rel, "name": path.name, "size_bytes": path.stat().st_size,
                      "well": well, "fish": fish, "already_linked": bool(linked)})
    return {"folder": folder, "dish_id": proposed_dish, "files": files}


def link(conn, root: Path, rel_path: str, dish_id: str, kind: str,
         fish_id: Optional[str] = None, linked_by: Optional[str] = None,
         read_metadata=None) -> int:
    """Create (or keep) the link for one file; returns its id."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    path = resolve_under(root, rel_path)
    if not is_image(path):
        raise ValueError(f"{rel_path} is not an OME-TIFF file")
    existing = conn.execute("SELECT id FROM image_links WHERE rel_path = ? AND dish_id = ?",
                            (rel_path, dish_id)).fetchone()
    if existing:
        if fish_id:
            conn.execute("UPDATE image_links SET fish_id = ? WHERE id = ?", (fish_id, existing["id"]))
        return existing["id"]
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    meta = {}
    if read_metadata is not None:
        try:
            meta = read_metadata(path)
        except Exception:  # an unreadable header still gets linked, without metadata
            meta = {}
    channels = [{"name": c.get("name"), "fluor": c.get("fluor"), "color_hex": c.get("color_hex")}
                for c in meta.get("channels") or []]
    cursor = conn.execute(
        """INSERT INTO image_links (rel_path, dish_id, fish_id, well_label, kind, size_bytes,
               sha256, file_mtime, channels, size_x, size_y, linked_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (rel_path, dish_id, fish_id, well_from_filename(path.name), kind, path.stat().st_size,
         digest.hexdigest(), _utc_mtime(path), json.dumps(channels) if channels else None,
         meta.get("size_x"), meta.get("size_y"), linked_by),
    )
    return cursor.lastrowid


def _row(row) -> Dict[str, Any]:
    item = {k: row[k] for k in row.keys()}
    item["channels"] = json.loads(item["channels"]) if item.get("channels") else []
    item["name"] = Path(item["rel_path"]).name
    instant = datetime.strptime(item["file_mtime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    item["taken_at_lab"] = instant.astimezone(LAB_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    return item


def for_dish(conn, dish_id: str) -> List[Dict[str, Any]]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM image_links WHERE dish_id = ? ORDER BY well_label, rel_path", (dish_id,))]


def for_fish(conn, fish_id: str) -> List[Dict[str, Any]]:
    return [_row(r) for r in conn.execute(
        "SELECT * FROM image_links WHERE fish_id = ? ORDER BY file_mtime", (fish_id,))]


def get(conn, link_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM image_links WHERE id = ?", (link_id,)).fetchone()
    return _row(row) if row else None


def preview_path(root: Path, cache_dir: Path, link: Dict[str, Any], render) -> Path:
    """The cached composite PNG for a link, rendered on first use."""
    target = Path(cache_dir) / f"link{link['id']}_{link['sha256'][:12]}_composite.png"
    if not target.exists():
        source = resolve_under(root, link["rel_path"])
        outputs = render(source, Path(cache_dir), f"link{link['id']}_{link['sha256'][:12]}")
        composite = next(o for o in outputs if o["display_role"] == "composite")
        produced = Path(cache_dir) / composite["image_filename"]
        if produced != target:
            produced.rename(target)
    return target
