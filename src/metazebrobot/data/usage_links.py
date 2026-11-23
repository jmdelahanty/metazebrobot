"""Usage links: which arena recording used which dish (and fish).

A group arena's link can name its members (docs/fish_timeline_design.md,
"Group members on usage links"): ``members`` on the request, stored in
``usage_link_members``. Only the members count as used, never the dish. A
group link created without them can be given its members once, later
(``set_members``), with the same checks; the link records when and by whom.

A link's fish (or a member) can be corrected (docs/fish_timeline_design.md,
"Correcting the fish a recording names"): ``usage_link_corrections`` is
append-only, the newest correction for a link (or a member) is the effective
one, and ``fish_id`` null means "fish unknown". The sealed fields are never
edited, so replays still compare against what was sealed.

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
MEMBER_FIELDS = ("fish_id", "fish_revision")
MAX_MEMBERS = 64
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
MEMBERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_link_members (
    recording_ref TEXT NOT NULL REFERENCES usage_links(recording_ref),
    fish_id TEXT NOT NULL,
    fish_revision INTEGER,
    PRIMARY KEY (recording_ref, fish_id)
)
"""
CORRECTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_link_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_ref TEXT NOT NULL REFERENCES usage_links(recording_ref),
    member_fish_id TEXT,
    fish_id TEXT,
    dish_id TEXT NOT NULL,
    fish_revision INTEGER,
    unit_id TEXT,
    attested_by TEXT NOT NULL,
    evidence TEXT NOT NULL,
    corrected_at TEXT NOT NULL,
    CHECK (fish_revision IS NULL OR fish_id IS NOT NULL),
    CHECK (unit_id IS NULL OR fish_id IS NOT NULL)
)
"""
CORRECTION_FIELDS = ("member_fish_id", "fish_id", "evidence", "attested_by")
MAX_EVIDENCE = 2000
INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_usage_links_fish ON usage_links(fish_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_links_dish ON usage_links(dish_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_links_started ON usage_links(started_norm)",
    "CREATE INDEX IF NOT EXISTS idx_usage_link_members_fish ON usage_link_members(fish_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_link_corrections_ref "
    "ON usage_link_corrections(recording_ref)",
    "CREATE INDEX IF NOT EXISTS idx_usage_link_corrections_fish "
    "ON usage_link_corrections(fish_id)",
)


class UsageLinkError(Exception):
    """A request the contract refuses: HTTP status plus the error detail."""

    def __init__(self, status: int, detail: Dict[str, Any]):
        super().__init__(detail.get("error"))
        self.status = status
        self.detail = detail


_DELIVERED_BY = re.compile(r"^[a-z0-9_-]{1,32}$")


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    conn.execute(MEMBERS_SCHEMA)
    conn.execute(CORRECTIONS_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(usage_links)")}
    for column in ("delivered_by", "members_added_at", "members_added_by"):
        if column not in cols:
            conn.execute(f"ALTER TABLE usage_links ADD COLUMN {column} TEXT")
    for statement in INDEXES:
        conn.execute(statement)


def delivered_by_from_header(value: Optional[str]) -> Optional[str]:
    """``X-Delivered-By`` (e.g. citrus, palette); unusable values are ignored."""
    value = (value or "").strip().lower()
    return value if _DELIVERED_BY.match(value) else None


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
        if key not in CREATE_FIELDS and key != "members":
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
    # Only a body that sends members carries the key, so links stored before
    # members existed still compare equal on replay.
    if "members" in body:
        values["members"] = _validate_members(body["members"], values)
    return values


def _validate_members(members: Any, values: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A group's members, sorted by fish_id so replays compare as a set."""
    if values["fish_id"] is not None:
        raise _invalid("members", "only when fish_id is null (a group arena)")
    if not isinstance(members, list) or not members or len(members) > MAX_MEMBERS:
        raise _invalid("members", f"expected a list of 1 to {MAX_MEMBERS} members")
    clean = []
    for member in members:
        if not isinstance(member, dict) or set(member) - set(MEMBER_FIELDS):
            raise _invalid("members", "each member is {fish_id, fish_revision}")
        fish_id, revision = member.get("fish_id"), member.get("fish_revision")
        if not isinstance(fish_id, str) or not _UUID.match(fish_id):
            raise _invalid("members", "each fish_id is a lowercase UUID")
        if revision is not None and (
                not isinstance(revision, int) or isinstance(revision, bool) or revision < 1):
            raise _invalid("members", "each fish_revision is an integer >= 1")
        clean.append({"fish_id": fish_id, "fish_revision": revision})
    if len({m["fish_id"] for m in clean}) != len(clean):
        raise _invalid("members", "a fish is listed twice")
    if values["subject_count"] != len(clean):
        raise _invalid("members", "the number of members must equal subject_count")
    return sorted(clean, key=lambda m: m["fish_id"])


def _row(conn, row) -> Dict[str, Any]:
    link = {k: row[k] for k in row.keys()
            if k not in ("started_norm", "ended_norm", "creation_body")}
    effective = effective_corrections(conn, row["recording_ref"])
    link["correction"] = effective.get(None)
    link["members"] = [
        {"fish_id": m["fish_id"], "fish_revision": m["fish_revision"],
         "flag": member_flag(conn, m["fish_id"], row["dish_id"], row["started_norm"]),
         "correction": effective.get(m["fish_id"])}
        for m in conn.execute(
            "SELECT fish_id, fish_revision FROM usage_link_members "
            "WHERE recording_ref = ? ORDER BY fish_id", (row["recording_ref"],))
    ]
    return link


def corrections(conn, recording_ref: str) -> List[Dict[str, Any]]:
    """Every correction of a link, oldest first."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM usage_link_corrections WHERE recording_ref = ? ORDER BY id",
        (recording_ref,))]


def effective_corrections(conn, recording_ref: str) -> Dict[Optional[str], Dict[str, Any]]:
    """The newest correction per corrected place: key None for the link's own
    fish, else the sealed member's fish_id."""
    return {c["member_fish_id"]: c for c in corrections(conn, recording_ref)}


def effective_subjects(conn, row) -> Dict[str, Any]:
    """Who the link names once corrections apply.

    ``fish_id``: the link's effective fish (None for a dish-level link or
    "fish unknown"). ``unknown``: the link's own fish was corrected to
    unknown. ``members``: ``{sealed fish_id: effective fish_id or None}``.
    """
    effective = effective_corrections(conn, row["recording_ref"])
    own = effective.get(None)
    members = {}
    for m in conn.execute("SELECT fish_id FROM usage_link_members WHERE recording_ref = ?",
                          (row["recording_ref"],)):
        c = effective.get(m["fish_id"])
        members[m["fish_id"]] = c["fish_id"] if c else m["fish_id"]
    return {
        "fish_id": own["fish_id"] if own else row["fish_id"],
        "unknown": bool(own) and own["fish_id"] is None,
        "members": members,
        "corrections": effective,
    }


def refs_with_effective_fish(conn, fish_id: str) -> List[str]:
    """Refs of links whose effective fish, or an effective member, is this fish."""
    candidates = set(refs_naming_fish(conn, fish_id))
    found = []
    for ref in sorted(candidates):
        row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?", (ref,)).fetchone()
        subjects = effective_subjects(conn, row)
        if subjects["fish_id"] == fish_id or fish_id in subjects["members"].values():
            found.append(ref)
    return found


def _span(row) -> Tuple[str, str]:
    """A link's time span for the one-fish-one-arena check. An end not yet
    recorded counts as the start, so a missing Stop doesn't block later work."""
    return row["started_norm"], row["ended_norm"] or row["started_norm"]


def _fish_state_at(conn, fish_id: str, started_norm: str) -> Dict[str, Any]:
    """The fish's revision, dish and unit at an instant, from its revisions.

    A fish registered after the start (Citrus's outbox) gets its first
    revision.
    """
    from .fish_timeline import _sqlite_utc_to_norm

    revisions = [dict(r) for r in conn.execute(
        "SELECT revision, recorded_at, dish_id, current_unit_id FROM fish_subject_revisions "
        "WHERE fish_id = ? ORDER BY revision", (fish_id,))]
    before = [r for r in revisions if _sqlite_utc_to_norm(r["recorded_at"]) <= started_norm]
    chosen = before[-1] if before else (revisions[0] if revisions else None)
    if chosen is None:
        fish = conn.execute("SELECT revision, dish_id, current_unit_id FROM fish_subjects "
                            "WHERE fish_id = ?", (fish_id,)).fetchone()
        chosen = dict(fish)
    return {"fish_revision": chosen["revision"], "dish_id": chosen["dish_id"],
            "unit_id": chosen["current_unit_id"]}


def _bad_correction(field: str, message: str) -> UsageLinkError:
    return UsageLinkError(422, {"error": "invalid_correction", "field": field, "message": message})


def add_correction(conn, recording_ref: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Record which fish was really in the arena: the link, or UsageLinkError.

    Body ``{member_fish_id?, fish_id, evidence, attested_by}``. ``fish_id``
    null is "fish unknown". ``member_fish_id`` names the sealed member being
    corrected and is required for a link with members. The fish's dish,
    revision and unit at ``started_at`` are filled from its history.
    """
    if not isinstance(body, dict):
        raise _bad_correction("body", "expected a JSON object")
    for key in body:
        if key not in CORRECTION_FIELDS:
            raise _bad_correction(key, "unknown field")
    if "fish_id" not in body:
        raise _bad_correction("fish_id", "required (null for fish unknown)")
    fish_id, member = body.get("fish_id"), body.get("member_fish_id")
    for key, value in (("fish_id", fish_id), ("member_fish_id", member)):
        if value is not None and (not isinstance(value, str) or not _UUID.match(value)):
            raise _bad_correction(key, "expected a lowercase UUID")
    evidence = body.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > MAX_EVIDENCE:
        raise _bad_correction("evidence", f"required text, at most {MAX_EVIDENCE} characters")
    attested_by = body.get("attested_by")
    if not isinstance(attested_by, str) or not conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (attested_by,)).fetchone():
        raise _bad_correction("attested_by", "a known username")

    row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?",
                       (recording_ref,)).fetchone()
    if not row:
        raise UsageLinkError(404, {"error": "usage_link_not_found", "recording_ref": recording_ref})
    subjects = effective_subjects(conn, row)
    if subjects["members"]:
        if member not in subjects["members"]:
            raise _bad_correction("member_fish_id", "required: one of the link's sealed members")
        current = subjects["members"][member]
    else:
        if member is not None:
            raise _bad_correction("member_fish_id", "only for a link with members")
        if row["fish_id"] is None and (row["subject_count"] or 1) > 1:
            raise _bad_correction("fish_id", "a dish-level link of several fish gets members "
                                             "(PUT /usage-links/{recording_ref}/members), "
                                             "not a correction")
        current = subjects["fish_id"]
    # A plain dish-level link already names no fish, so "unknown" there is
    # unchanged too.
    if fish_id == current:
        raise UsageLinkError(409, {"error": "correction_unchanged", "recording_ref": recording_ref})

    state = {"fish_revision": None, "dish_id": row["dish_id"], "unit_id": None}
    if fish_id is not None:
        if not conn.execute("SELECT 1 FROM fish_subjects WHERE fish_id = ?", (fish_id,)).fetchone():
            raise UsageLinkError(404, {"error": "fish_not_found", "fish_id": fish_id})
        # One fish, one arena: not another place in this link, nor another
        # link whose time overlaps.
        if fish_id in [v for k, v in subjects["members"].items() if k != member]:
            raise UsageLinkError(409, {"error": "fish_in_another_arena", "fish_id": fish_id,
                                       "recording_ref": recording_ref})
        start, end = _span(row)
        for other_ref in refs_with_effective_fish(conn, fish_id):
            if other_ref == recording_ref:
                continue
            other = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?",
                                 (other_ref,)).fetchone()
            other_start, other_end = _span(other)
            if other_start <= end and start <= other_end:
                raise UsageLinkError(409, {"error": "fish_in_another_arena", "fish_id": fish_id,
                                           "recording_ref": other_ref})
        state = _fish_state_at(conn, fish_id, row["started_norm"])
    stamp = now_utc()
    conn.execute(
        """INSERT INTO usage_link_corrections (recording_ref, member_fish_id, fish_id, dish_id,
               fish_revision, unit_id, attested_by, evidence, corrected_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (recording_ref, member, fish_id, state["dish_id"], state["fish_revision"],
         state["unit_id"], attested_by, evidence.strip(), stamp))
    conn.execute("UPDATE usage_links SET updated_at = ? WHERE recording_ref = ?",
                 (stamp, recording_ref))
    return get_link(conn, recording_ref)


def member_flag(conn, fish_id: str, dish_id: str, started_norm: str) -> Optional[str]:
    """Why a member needs review, judged at the link's start; None when fine.

    ``dead_at_start``: the fish had already ended before the recording
    started. ``not_in_dish_at_start``: it was in another dish then. Judged
    from history, so a member moved or euthanized after the recording (the
    normal case) isn't flagged, however late the link arrives.
    """
    from .fish_timeline import _dish_at, _sqlite_utc_to_norm, _rfc3339_to_lab_iso

    fish = conn.execute(
        "SELECT dish_id, created_at, status, ended_at, ended_precision "
        "FROM fish_subjects WHERE fish_id = ?", (fish_id,)).fetchone()
    if fish is None:
        return "not_in_dish_at_start"
    if fish["status"] != "alive" and fish["ended_at"]:
        if fish["ended_precision"] == "day":
            # A day-precision end only counts when it was an earlier lab day.
            start_day = (_rfc3339_to_lab_iso(started_norm) or "")[:10]
            if fish["ended_at"][:10] < start_day:
                return "dead_at_start"
        elif _sqlite_utc_to_norm(fish["ended_at"]) < started_norm:
            return "dead_at_start"
    revisions = [dict(r) for r in conn.execute(
        "SELECT dish_id, recorded_at FROM fish_subject_revisions WHERE fish_id = ? "
        "ORDER BY revision", (fish_id,))]
    created_norm = _sqlite_utc_to_norm(fish["created_at"])
    dish_then = _dish_at(revisions, created_norm, started_norm)
    if dish_then is None:
        # Registered after the start (Citrus's outbox): its first dish counts.
        dish_then = revisions[0]["dish_id"] if revisions else fish["dish_id"]
    return None if dish_then == dish_id else "not_in_dish_at_start"


def refs_naming_fish(conn, fish_id: str) -> List[str]:
    """Recording refs of links that name this fish, as subject or group member,
    sealed or by a correction."""
    return [r[0] for r in conn.execute(
        "SELECT recording_ref FROM usage_links WHERE fish_id = ? "
        "UNION SELECT recording_ref FROM usage_link_members WHERE fish_id = ? "
        "UNION SELECT recording_ref FROM usage_link_corrections WHERE fish_id = ? "
        "ORDER BY 1", (fish_id, fish_id, fish_id))]


def get_link(conn, recording_ref: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?", (recording_ref,)).fetchone()
    return _row(conn, row) if row else None


def create_link(conn, body: Dict[str, Any],
                delivered_by: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """(201 | 200, link) or UsageLinkError. An existing ref is answered first.

    ``delivered_by`` (from the ``X-Delivered-By`` header) is recorded on first
    creation only and isn't part of the idempotency comparison, so a backup
    delivery by Palette of Citrus's sealed request is still a 200 replay.
    """
    values = validate_create(body)
    existing = conn.execute(
        "SELECT creation_body FROM usage_links WHERE recording_ref = ?", (values["recording_ref"],)
    ).fetchone()
    if existing:
        # Compared with the body as created, so members given later
        # (set_members) don't turn a replay of the original into a 409.
        if json.loads(existing["creation_body"]) != values:
            raise UsageLinkError(409, {"error": "usage_link_conflict",
                                       "recording_ref": values["recording_ref"]})
        return 200, get_link(conn, values["recording_ref"])
    if not conn.execute("SELECT 1 FROM dishes WHERE dish_id = ?", (values["dish_id"],)).fetchone():
        raise UsageLinkError(404, {"error": "dish_not_found", "dish_id": values["dish_id"]})
    named = ([values["fish_id"]] if values["fish_id"] else []) + [
        m["fish_id"] for m in values.get("members", [])]
    for fish_id in named:
        if not conn.execute("SELECT 1 FROM fish_subjects WHERE fish_id = ?", (fish_id,)).fetchone():
            raise UsageLinkError(404, {"error": "fish_not_found", "fish_id": fish_id})
    stamp = now_utc()
    conn.execute(
        f"""INSERT INTO usage_links ({', '.join(CREATE_FIELDS)}, started_norm,
                                      received_at, updated_at, creation_body, delivered_by)
            VALUES ({', '.join('?' for _ in CREATE_FIELDS)}, ?, ?, ?, ?, ?)""",
        [values[k] for k in CREATE_FIELDS]
        + [normalize_time(values["started_at"]), stamp, stamp,
           json.dumps(values, sort_keys=True), delivered_by],
    )
    conn.executemany(
        "INSERT INTO usage_link_members (recording_ref, fish_id, fish_revision) VALUES (?, ?, ?)",
        [(values["recording_ref"], m["fish_id"], m["fish_revision"])
         for m in values.get("members", [])],
    )
    return 201, get_link(conn, values["recording_ref"])


def set_members(conn, recording_ref: str, body: Dict[str, Any],
                delivered_by: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Give a group link its members once: (201 | 200, link) or UsageLinkError.

    For a link created without ``members``. Same checks as at creation
    (``fish_id`` null, as many as ``subject_count``, each fish exists, flags
    judged at ``started_at``). The same set again is 200; a different set
    once members exist is 409 ``usage_link_members_conflict``.
    """
    if not isinstance(body, dict) or set(body) != {"members"}:
        extra = sorted(set(body) - {"members"}) if isinstance(body, dict) else ["body"]
        raise _invalid(extra[0] if extra else "members", "unknown field" if extra else "required")
    row = conn.execute("SELECT * FROM usage_links WHERE recording_ref = ?", (recording_ref,)).fetchone()
    if not row:
        raise UsageLinkError(404, {"error": "usage_link_not_found", "recording_ref": recording_ref})
    added = _apply_members(conn, row, body["members"], delivered_by)
    return (201 if added else 200), get_link(conn, recording_ref)


def _apply_members(conn, row, members: Any, delivered_by: Optional[str]) -> bool:
    """Store a link's members if it has none; True when they were added."""
    clean = _validate_members(members, {"fish_id": row["fish_id"],
                                        "subject_count": row["subject_count"]})
    ref = row["recording_ref"]
    current = [dict(m) for m in conn.execute(
        "SELECT fish_id, fish_revision FROM usage_link_members "
        "WHERE recording_ref = ? ORDER BY fish_id", (ref,))]
    if current:
        if current != clean:
            raise UsageLinkError(409, {"error": "usage_link_members_conflict",
                                       "recording_ref": ref})
        return False
    for member in clean:
        if not conn.execute("SELECT 1 FROM fish_subjects WHERE fish_id = ?",
                            (member["fish_id"],)).fetchone():
            raise UsageLinkError(404, {"error": "fish_not_found", "fish_id": member["fish_id"]})
    conn.executemany(
        "INSERT INTO usage_link_members (recording_ref, fish_id, fish_revision) VALUES (?, ?, ?)",
        [(ref, m["fish_id"], m["fish_revision"]) for m in clean])
    stamp = now_utc()
    conn.execute("UPDATE usage_links SET members_added_at = ?, members_added_by = ?, "
                 "updated_at = ? WHERE recording_ref = ?", (stamp, delivered_by, stamp, ref))
    return True


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
        # Compare instants, not strings: two writers (Citrus at Stop, Palette at
        # intake) may format the same end with or without fractional seconds.
        if (row["ended_norm"], row["end_status"]) != (ended_norm, body["end_status"]):
            raise UsageLinkError(409, {"error": "usage_link_end_conflict",
                                       "recording_ref": recording_ref})
        return _row(conn, row)
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
    """Links filtered by fish (the link's effective fish or an effective
    member, once corrections apply), dish and/or the instant they were open at."""
    where, params = [], []
    if fish_id:
        refs = refs_with_effective_fish(conn, fish_id)
        where.append(f"recording_ref IN ({', '.join('?' for _ in refs) or 'NULL'})")
        params += refs
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
    return [_row(conn, r) for r in conn.execute(sql + " ORDER BY started_norm", params)]
