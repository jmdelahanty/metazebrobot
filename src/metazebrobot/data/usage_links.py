"""Usage links: which arena recording used which dish (and fish).

docs/fish_timeline_design.md ("Usage links", "Proposed endpoints",
"Refinements from Citrus's review"). MetaZebrobot stores only the reference
and these fields; recordings stay owned by Palette and the H5. Citrus POSTs a
link at Start and PATCHes its end at Stop; both are idempotent.

Times are RFC 3339 UTC (``...Z``) on the wire and stored as sent, plus a
normalized copy (``YYYY-MM-DDTHH:MM:SS.ffffffZ``) for time-range queries.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

REF_KINDS = ("observation_context", "citrus_session")
END_STATUSES = ("completed", "aborted", "interrupted")
CREATE_FIELDS = (
    "recording_ref", "ref_kind", "recording_id", "dish_id", "fish_id", "fish_revision",
    "unit_id", "rig_id", "arena_id", "subject_count", "started_at",
)
REQUIRED = ("recording_ref", "ref_kind", "dish_id", "rig_id", "arena_id", "started_at")
MAX_REF_LENGTH = 160

_OBSCTX = re.compile(r"^obsctx_[0-9a-f]{64}$")
_CITRUS_SESSION = re.compile(r"^[\x20-\x2e\x30-\x7e]+$")  # printable ASCII, no "/"
_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_links (
    recording_ref TEXT PRIMARY KEY,
    ref_kind TEXT NOT NULL CHECK (ref_kind IN ('observation_context', 'citrus_session')),
    recording_id TEXT,
    dish_id TEXT NOT NULL,
    fish_id TEXT,
    fish_revision INTEGER,
    unit_id TEXT,
    rig_id TEXT NOT NULL,
    arena_id TEXT NOT NULL,
    subject_count INTEGER CHECK (subject_count IS NULL OR subject_count >= 1),
    started_at TEXT NOT NULL,
    started_norm TEXT NOT NULL,
    ended_at TEXT,
    ended_norm TEXT,
    end_status TEXT CHECK (end_status IN ('completed', 'aborted', 'interrupted')),
    received_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    creation_body TEXT NOT NULL,
    CHECK (fish_revision IS NULL OR fish_id IS NOT NULL),
    CHECK (unit_id IS NULL OR fish_id IS NOT NULL),
    CHECK ((ended_at IS NULL) = (end_status IS NULL))
)
"""
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_usage_links_fish ON usage_links(fish_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_links_dish ON usage_links(dish_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_links_started ON usage_links(started_norm)",
)


class UsageLinkError(Exception):
    """A request the contract refuses: HTTP status plus the error detail."""

    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    for statement in INDEXES:
        conn.execute(statement)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_time(value: Any) -> Optional[str]:
    """RFC 3339 UTC 'Z' string -> fixed-width form, or None if invalid."""
    if not isinstance(value, str) or not _RFC3339_UTC.match(value):
        return None
    try:
        parsed = datetime.strptime(value.replace("Z", "+0000"),
                                   "%Y-%m-%dT%H:%M:%S.%f%z" if "." in value else "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _invalid(field: str, message: str) -> UsageLinkError:
    return UsageLinkError(422, {"error": "invalid_usage_link", "field": field, "message": message})


def valid_ref(ref_kind: Any, ref: Any) -> bool:
    if not isinstance(ref, str) or not ref or len(ref) > MAX_REF_LENGTH:
        return False
    if ref_kind == "observation_context":
        return bool(_OBSCTX.match(ref))
    if ref_kind == "citrus_session":
        return bool(_CITRUS_SESSION.match(ref))
    return False


def validate_create(body: Dict[str, Any]) -> Dict[str, Any]:
    """The canonical creation values, or UsageLinkError(422)."""
    if not isinstance(body, dict):
        raise _invalid("body", "expected a JSON object")
    for key in body:
        if key not in CREATE_FIELDS:
            raise _invalid(key, "unknown field")
    for key in REQUIRED:
        if body.get(key) in (None, ""):
            raise _invalid(key, "required")
    values = {key: body.get(key) for key in CREATE_FIELDS}
    if values["ref_kind"] not in REF_KINDS:
        raise _invalid("ref_kind", f"one of {', '.join(REF_KINDS)}")
    if not valid_ref(values["ref_kind"], values["recording_ref"]):
        raise _invalid("recording_ref", f"doesn't match the {values['ref_kind']} pattern "
                                        f"(at most {MAX_REF_LENGTH} characters)")
    for key in ("recording_id", "dish_id", "unit_id", "rig_id", "arena_id"):
        if values[key] is not None and not isinstance(values[key], str):
            raise _invalid(key, "expected a string")
    if values["fish_id"] is not None and (
            not isinstance(values["fish_id"], str) or not _UUID.match(values["fish_id"])):
        raise _invalid("fish_id", "expected a lowercase UUID")
    for key in ("fish_revision", "subject_count"):
        value = values[key]
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise _invalid(key, "expected an integer >= 1")
    if values["fish_revision"] is not None and values["fish_id"] is None:
        raise _invalid("fish_revision", "only with fish_id")
    if values["unit_id"] is not None and values["fish_id"] is None:
        raise _invalid("unit_id", "only with fish_id")
    if normalize_time(values["started_at"]) is None:
        raise _invalid("started_at", "RFC 3339 UTC ending in Z")
    return values


def _row(row) -> Dict[str, Any]:
    link = {k: row[k] for k in row.keys()
            if k not in ("started_norm", "ended_norm", "creation_body")}
    return link


def get_link(conn, recording_ref: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?", (recording_ref,)).fetchone()
    return _row(row) if row else None


def create_link(conn, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """(201 | 200, link) or UsageLinkError. An existing ref is answered first."""
    values = validate_create(body)
    existing = conn.execute(
        "SELECT creation_body FROM usage_links WHERE recording_ref = ?", (values["recording_ref"],)
    ).fetchone()
    if existing:
        if json.loads(existing["creation_body"]) != values:
            raise UsageLinkError(409, {"error": "usage_link_conflict",
                                       "recording_ref": values["recording_ref"]})
        return 200, get_link(conn, values["recording_ref"])
    if not conn.execute("SELECT 1 FROM dishes WHERE dish_id = ?", (values["dish_id"],)).fetchone():
        raise UsageLinkError(404, {"error": "dish_not_found", "dish_id": values["dish_id"]})
    if values["fish_id"] and not conn.execute(
            "SELECT 1 FROM fish_subjects WHERE fish_id = ?", (values["fish_id"],)).fetchone():
        raise UsageLinkError(404, {"error": "fish_not_found", "fish_id": values["fish_id"]})
    stamp = now_utc()
    conn.execute(
        f"""INSERT INTO usage_links ({', '.join(CREATE_FIELDS)}, started_norm,
                                      received_at, updated_at, creation_body)
            VALUES ({', '.join('?' for _ in CREATE_FIELDS)}, ?, ?, ?, ?)""",
        [values[k] for k in CREATE_FIELDS]
        + [normalize_time(values["started_at"]), stamp, stamp,
           json.dumps(values, sort_keys=True)],
    )
    return 201, get_link(conn, values["recording_ref"])


def end_link(conn, recording_ref: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Record the end; identical replays are 200, a different end is 409."""
    if not isinstance(body, dict) or set(body) - {"ended_at", "end_status"}:
        extra = sorted(set(body) - {"ended_at", "end_status"}) if isinstance(body, dict) else ["body"]
        raise _invalid(extra[0], "unknown field")
    ended_norm = normalize_time(body.get("ended_at"))
    if ended_norm is None:
        raise _invalid("ended_at", "RFC 3339 UTC ending in Z")
    if body.get("end_status") not in END_STATUSES:
        raise _invalid("end_status", f"one of {', '.join(END_STATUSES)}")
    row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?", (recording_ref,)).fetchone()
    if not row:
        raise UsageLinkError(404, {"error": "usage_link_not_found", "recording_ref": recording_ref})
    if row["ended_at"] is not None:
        if (row["ended_at"], row["end_status"]) != (body["ended_at"], body["end_status"]):
            raise UsageLinkError(409, {"error": "usage_link_end_conflict",
                                       "recording_ref": recording_ref})
        return _row(row)
    if ended_norm < row["started_norm"]:
        raise _invalid("ended_at", "earlier than started_at")
    conn.execute(
        """UPDATE usage_links SET ended_at = ?, ended_norm = ?, end_status = ?, updated_at = ?
           WHERE recording_ref = ?""",
        (body["ended_at"], ended_norm, body["end_status"], now_utc(), recording_ref),
    )
    return get_link(conn, recording_ref)


def list_links(conn, fish_id: Optional[str] = None, dish_id: Optional[str] = None,
               active_at: Optional[str] = None) -> List[Dict[str, Any]]:
    """Links filtered by fish, dish and/or the instant they were open at."""
    where, params = [], []
    if fish_id:
        where.append("fish_id = ?")
        params.append(fish_id)
    if dish_id:
        where.append("dish_id = ?")
        params.append(dish_id)
    if active_at:
        instant = normalize_time(active_at)
        if instant is None:
            raise _invalid("active_at", "RFC 3339 UTC ending in Z")
        where.append("started_norm <= ? AND (ended_norm IS NULL OR ended_norm >= ?)")
        params += [instant, instant]
    sql = "SELECT * FROM usage_links" + (" WHERE " + " AND ".join(where) if where else "")
    return [_row(r) for r in conn.execute(sql + " ORDER BY started_norm", params)]
