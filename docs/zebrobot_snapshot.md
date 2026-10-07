---
title: "MetaZebrobot H5 Snapshot Integration"
summary: "Consumer contract for Citrus, Orange and Palette: snapshot fields, identity, errors, dates and times, stability."
owner: metazebrobot
status: current
kind: reference
verified_against: 384a366
---

# MetaZebrobot H5 Snapshot Integration

This document describes how the acquisition agent should query the
MetaZebrobot read-only API and store a minimal, no-PII snapshot in an H5 file.

## Schema overview

End-to-end pieces. MetaZebrobot owns the API values the snapshot is built
from and the database (item 4). The H5 layout, the stored snapshot object, and
the local registry (items 1-3) are owned by the acquisition system; items 1-3
are MetaZebrobot's recommendation, and Citrus documents what it actually
writes in its own repository (`docs/zebrobot_snapshot.md`,
`docs/Understanding_H5_Log.md`).

1) **H5 subject metadata** (`/subject_metadata`)
   - `zebrobot_schema_version` (int, start at 1)
   - `dish_id`, `cross_id`, `genotype`, `line_strain`
   - `dish_uuid`, `dish_revision`, `dish_updated_at` (from API `schema_version` 2;
     see [Identity and change detection](#identity-and-change-detection))
   - `date_of_fertilization` (YYYYMMDD), `fish_count`, `species`, `sex`
   - `queried_at_utc` (ISO8601)
   - `parents` (JSON string, machine-parseable list of `{identifier, sex}`)
   - `parents_display` (human-readable string)
   - optional: `dpf_at_acquisition` (int; set null + missing if invalid)

2) **Snapshot JSON schema** (logical model used to populate the H5 fields)
   - `schema_version` (version of this stored object, not the API response
     `schema_version`), `queried_at_utc`, `status`, `missing`, `dish_id`
   - `dish` (minimal fields) and `cross` (minimal fields; `null` if missing)
   - optional: `errors[]`, `dpf_at_acquisition`

3) **Local acquisition registry** (staging cache, Citrus-owned)
   - File: `~/.local/share/fisheye/subject_registry.json`
   - Tracks `fish_id` UUIDs for immediate reuse across sessions
   - Prune aggressively; registry is not the source of truth
   - See [Acquisition registry (staging) schema](#acquisition-registry-staging-schema)

4) **Database (individual tracking)**
   - `fish_subjects`, `housing_units`, `housing_unit_occupancy`, `housing_unit_checks`
   - Session/experiment tracking lives in Palette (see `docs/identity_and_provenance_contract.md`)

## API access

- If using the SSH tunnel, the base URL is:
  - `http://127.0.0.1:18000`
- If running on the DB host directly:
  - `http://127.0.0.1:8000`

No auth is required when using the SSH tunnel; the API is bound to localhost on
the DB host.

## Endpoints used

- List active dishes for the acquisition dropdown, with DPF, current fish count,
  registered fish/unit counts, cross background summary, and follow-up links:
  - `GET /acquisition/dishes?status=active&limit=300&offset=0`
- Legacy/general active-dish list:
  - `GET /dishes?status=active&limit=200&offset=0`
- Fetch a specific dish:
  - `GET /dishes/{dish_id}`
  - `GET /dishes/by-uuid/{dish_uuid}` (same payload, looked up by the immutable UUID)
- Fetch the no-PII H5 snapshot payload for a selected dish:
  - `GET /dishes/{dish_id}/citrus-snapshot`
- Fetch registered fish or housing units for a selected dish:
  - `GET /dishes/{dish_id}/fish`
  - `GET /dishes/{dish_id}/units`
- Fetch its cross:
  - `GET /crosses/{cross_id}`
- Fetch cached parent/background provenance:
  - `GET /crosses/{cross_id}/provenance`
- Health check with local DB and PyRAT status split apart:
  - `GET /health?check_db=true&check_pyrat=true`
- Identify the running service and its consumer schema digest:
  - `GET /version` (see [Which MetaZebrobot am I talking to?](#which-metazebrobot-am-i-talking-to))

Note: `GET /crosses/{cross_id}` returns `parents` as a JSON array. Older
snapshots may have stored this field as a JSON-encoded string.

If `GET /acquisition/dishes?status=active...` returns an empty `items` list,
MetaZebrobot has no currently active dishes matching the filter. Create or
reactivate an acquisition-ready dish in MetaZebrobot rather than changing the
status value in Citrus.

## Identity and change detection

`GET /dishes/{dish_id}/citrus-snapshot` and `GET /acquisition/dishes` return
`schema_version: 2`. Version 2 is additive: every v1 field is unchanged, and
each dish also carries:

| Field | Meaning |
|-------|---------|
| `dish_uuid` | Immutable UUID4, minted when the dish is created and never reused. Record it alongside `dish_id`. |
| `revision` | Integer, starts at 1. Increments whenever any value in the dish row changes, and only then. |
| `updated_at` | UTC timestamp (`YYYY-MM-DD HH:MM:SS`) of the last content change. |

Fish responses (`GET /fish/{fish_id}`, `GET /dishes/{dish_id}/fish`) carry
`dish_uuid`, `revision`, and `updated_at` the same way.

- `dish_id` (`{cross_id}_{n}`) stays the human-facing id and the lookup key,
  but it is only unique within this database and could be reused after a
  delete. `dish_uuid` is the durable reference.
- An unchanged `(dish_uuid, revision)` pair means the dish row is unchanged.
  Always compare the pair: a re-created `dish_id` restarts at revision 1 under
  a new `dish_uuid`.
- Only "changed / not changed" is meaningful. One save can raise `revision`
  by more than 1.
- `revision` covers the dish row only. `parents` and `line_strain` come from
  the cached PyRAT cross (watch `cross.cache_updated_at` in
  `/acquisition/dishes`), and `dpf` is computed from `dof` at request time.
- There is no "read as of time T"; the API always returns the current record.
  Store the snapshot you fetched.

## API errors

JSON read endpoints return structured errors in FastAPI's `detail` field:

| Status | Body | When |
|--------|------|------|
| 404 | `{"detail": {"error": "dish_not_found", "dish_id": "..."}}` | Unknown `dish_id` (also `/dishes/{dish_id}/fish`) |
| 404 | `{"detail": {"error": "dish_not_found", "dish_uuid": "..."}}` | Unknown `dish_uuid` |
| 404 | `{"detail": {"error": "fish_not_found", "fish_id": "..."}}` | Unknown `fish_id` |
| 503 | `{"detail": {"error": "database_error", "message": "..."}}` | SQLite failure (e.g. locked) |
| 422 | `{"detail": [...]}` | Invalid query parameters |

A 404 means the record does not exist; a 503 means the lookup failed and
should be retried. A connection failure (service down or tunnel closed) has
no HTTP status. When recording a failed lookup, keep the HTTP status and
`detail.error` (if present) in the snapshot `errors[]` entry.

## Dates and times

The lab and the MetaZebrobot server are on the US East Coast:
**America/New_York** (EST/EDT). Two conventions are in use, so read each field
by its kind:

| Kind | Fields | Timezone | Format |
|------|--------|----------|--------|
| Calendar days | `dof`, `date_created`, `cross_setup_date`, `termination_date`, `screening_date_finalized` | Lab-local (America/New_York) | `YYYYMMDD`, no time or offset |
| PyRAT datetimes | `date_of_set_up`, `date_of_record`, `date_of_birth`, ... (passed through from PyRAT) | Facility-local (America/New_York), observed rather than documented by PyRAT | `YYYY-MM-DDTHH:MM:SS`, no offset |
| Record timestamps | `updated_at`, `created_at`, `cross.cache_updated_at` | **UTC** (SQLite `CURRENT_TIMESTAMP`) | `YYYY-MM-DD HH:MM:SS`, no offset |
| Explicit UTC | `started_at_utc` (`/version`), consumers' `*_utc` fields | UTC | ISO 8601 with `Z` |

- `dof` is PyRAT `date_of_set_up` + 1 day (`dof_source = pyrat_setup_plus_1`),
  PyRAT `date_of_record`, or entered by hand: always a lab wall-clock day.
- The served `dpf` is the lab's (America/New_York) calendar date at request
  time minus `dof`, fixed in code (`LAB_TIMEZONE`) rather than taken from the
  host's timezone, so it changes at New York midnight. It is the dish's age at
  request time, not at a recording; compute `dpf_at_acquisition` yourself
  (above), or store the served value when querying at record start.
- `updated_at` looks like local time but is UTC: `2026-10-02 16:28:20` is
  12:28 EDT. Parse it as UTC.
- To get a lab-local calendar day from a UTC instant, convert to
  `America/New_York` first (Python: `instant.astimezone(ZoneInfo("America/New_York")).date()`).

## Contract and stability

This document is the single source for what the consumer-facing fields mean.
Field-level shapes are generated from the code, not written by hand:

- `docs/api/consumer_openapi.json`: the OpenAPI slice for
  `/dishes/{dish_id}/citrus-snapshot`, `/acquisition/dishes`,
  `/dishes/{dish_id}`, `/dishes/by-uuid/{dish_uuid}`,
  `/dishes/{dish_id}/fish`, `/fish/{fish_id}`, and `/version`, including
  their 404/503 error models.
- `tests/test_consumer_contract.py` fails if the code and that file
  disagree, and asserts the identity fields explicitly.
- `pixi run python scripts/export_consumer_openapi.py --check` verifies it
  and prints its sha256. Downstream contracts pin a MetaZebrobot commit plus
  this digest instead of copying field lists.

### Which MetaZebrobot am I talking to?

`GET /version` returns:

| Field | Meaning |
|-------|---------|
| `service_commit` | Git SHA of the code the running process loaded (`null` if unknown). |
| `service_commit_dirty` | `true` if that checkout had uncommitted changes to tracked files. |
| `consumer_schema_sha256` | sha256 of the consumer OpenAPI slice, computed from the running app (not read from the file). Equals the pinned digest exactly when the process serves the pinned schema. |
| `api_schema_version` | Response schema version of the consumer endpoints (2). |
| `started_at_utc` | When the process started (`YYYY-MM-DDTHH:MM:SSZ`). |

Consumers read it once per session (e.g. at record start) and store
`service_commit` and `consumer_schema_sha256` as provenance.

Stability promise for response `schema_version` 2:

- Changes are additive only (new optional fields).
- Removing, renaming, or changing the meaning or type of an existing field,
  or changing the error shape, ships as a new `schema_version`, never as an
  edit to v2.
- `dish_uuid` and `fish_id` never change for a given record.

## Snapshot JSON schema (required fields)

Store a single JSON object with the following fields. The top-level
`schema_version` is the version of this stored object (Citrus writes 1), not
the API response `schema_version` (2); `queried_at_utc`, `status`, and
`missing` are filled in by the consumer.

```json
{
  "schema_version": 1,
  "queried_at_utc": "2026-01-16T23:45:12Z",
  "status": "complete",
  "missing": [],
  "dish_id": "15238_1",
  "dish": {
    "dish_id": "15238_1",
    "dish_uuid": "b833f00a-0e75-42ab-aebf-8a44a852c7f8",
    "revision": 3,
    "updated_at": "2026-01-15 18:02:41",
    "cross_id": "15238",
    "genotype": "Tg(gfap:TRPV1-T2A-GFP)",
    "dof": "20250106",
    "fish_count": 25,
    "species": "Danio rerio",
    "sex": "unknown"
  },
  "cross": {
    "cross_id": "15238",
    "line_strain": "Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)",
    "parents": [
      { "identifier": "M11:E5 (5187)", "sex": "M" },
      { "identifier": "M11:E6 (5188)", "sex": "F" }
    ]
  }
}
```

## Derived fields (optional, recommended)

These values are computed at acquisition time and are not fetched from the API:

- `dpf_at_acquisition` (int)
  - Compute as: (the session start instant converted to **America/New_York**,
    then its calendar date) − `dof`. Do **not** take the date from the UTC
    instant: a session started after 20:00 EDT (00:00 UTC) would come out one
    day too old. See [Dates and times](#dates-and-times).
  - If `dof` is missing or invalid, set `dpf_at_acquisition=null` and add `"dpf"` to `missing`.
  - If the computed value is negative, set `dpf_at_acquisition=null` and add an error entry.

If present, include `dpf_at_acquisition` at the top level of the snapshot JSON.

## Partial snapshot rules

Partial snapshots must not block acquisition. Use:

- `status="partial"`
- `missing` list with one or more of: `"dish"`, `"cross"`, `"dpf"`
- `cross=null` if the cross fetch fails or is missing
- `dish_id` is always recorded at the root if known

Optional provenance:

```json
"errors": [
  { "source": "dish", "status": 404, "error": "dish_not_found", "message": "..." }
]
```

## H5 storage layout

The H5 layout is owned by the acquisition system. Citrus documents its own
layout in its repository (`docs/zebrobot_snapshot.md`, H5 storage layout, and
`docs/Understanding_H5_Log.md`, Session Metadata Groups), including the
`/zebrobot_snapshot/snapshot_json` dataset. The recommendation below is
MetaZebrobot's.

Store a flattened snapshot under:

- Group: `/subject_metadata`

Recommended fields:

- `zebrobot_schema_version` (integer, start at 1)
- `dish_id`
- `dish_uuid`
- `dish_revision`
- `dish_updated_at`
- `cross_id`
- `genotype`
- `line_strain`
- `date_of_fertilization`
- `fish_count`
- `species`
- `sex`
- `queried_at_utc`
- `parents` (machine-parseable JSON string)
- `parents_display` (readable string)

Example:

```
parents = [{"identifier":"6489_M12_D9","sex":"unknown"},{"identifier":"6490_M12_D9","sex":"unknown"}]
parents_display = 6489_M12_D9 [unknown]; 6490_M12_D9 [unknown]
```

## PII rules (do not store)

Do not store the following fields:

- `responsible`, `responsible_requestor`
- `notes`, `termination_reason`
- `quality_checks` (including any `notes`)
- full `data` JSON from endpoints

Keep only the explicit fields listed in the snapshot schema above.

## Implementation notes

- The API returns `parents` as a JSON array of `{identifier, sex}` objects
  (`GET /dishes/{dish_id}/citrus-snapshot` and `GET /crosses/{cross_id}`).
  Only older stored snapshots may hold a JSON-encoded string; if parsing one
  fails, set `parents=[]` and add an error if desired.
- `GET /dishes/{dish_id}/citrus-snapshot` already returns `species`, `sex`,
  `dish_uuid`, `revision`, `updated_at`, `line_strain`, and `parents`; no
  second dish or cross call is needed. If the cross is not cached locally,
  `line_strain` is `null`; if the cached cross has no parents (or is not
  cached), `parents` falls back to the dish's breeding parents with `sex`
  `"unknown"`.
- `fish_count` in `citrus-snapshot` is the dish's current count (falling back
  to the initial count). In `GET /dishes/{dish_id}`, `fish_count` is the
  initial count and the current count is `current_fish_count`.
- `dish_id` is provided by the acquisition UI dropdown (populated from active
  dishes).

## C++ client notes (DearImGui)

Historical guidance for the Citrus client, which Citrus now owns (its
`docs/zebrobot_snapshot.md` carries the same notes). The pattern below
predates the current API: it only handles `parents` as a JSON-encoded string,
but `GET /crosses/{cross_id}` now returns an array, so a client should accept
an array (and a string only for older data). `GET /dishes/{dish_id}/citrus-snapshot`
returns dish and cross fields in one call.

- Avoid shelling out to `curl` in the app. Use an in-process HTTP client.
- Suggested client: `cpp-httplib` (single header) or `libcurl`.
- Use timeouts and handle non-200 responses gracefully.

Minimal pattern (with `cpp-httplib` + `nlohmann::json`):

```cpp
httplib::Client cli("http://127.0.0.1:18000");
cli.set_read_timeout(5, 0);
auto res = cli.Get("/dishes/17257_1");
if (!res || res->status != 200) { /* mark missing dish */ }
auto dish_full = nlohmann::json::parse(res->body);

auto cross_id = dish_full.value("cross_id", "");
auto res_cross = cli.Get("/crosses/" + cross_id);
auto cross_full = nlohmann::json::parse(res_cross->body);

nlohmann::json parents = nlohmann::json::array();
if (cross_full.contains("parents") && cross_full["parents"].is_string()) {
    parents = nlohmann::json::parse(cross_full["parents"].get<std::string>(), nullptr, false);
    if (parents.is_discarded()) parents = nlohmann::json::array();
}
```

## Acquisition registry (staging) schema

Historical, consumer-owned. The registry lives on the acquisition machine and
is implemented by Citrus (`src/utils/subject_registry.cpp` in the Citrus
repository), which documents it in its `docs/zebrobot_snapshot.md`
(Acquisition registry). MetaZebrobot does not read or write it; the text below
is the original proposal and may not match the current implementation.

Use a lightweight local registry so fish IDs can be reused immediately even
before H5 files are transferred/processed. This registry is **not** the source
of truth and may be pruned aggressively.

Suggested file: `~/.local/share/fisheye/subject_registry.json`

Example:

```json
{
  "schema_version": 1,
  "updated_at_utc": "2026-01-20T19:35:22Z",
  "entries": [
    {
      "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
      "dish_id": "17257_1",
      "last_seen_utc": "2026-01-20T19:35:22Z",
      "status": "pending",
      "sessions": [
        {
          "session_uuid": "2026-01-20T19-35-22Z_arena_1",
          "created_at_utc": "2026-01-20T19:35:22Z",
          "status": "pending"
        }
      ]
    }
  ],
  "by_dish": {
    "17257_1": [
      "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a"
    ]
  }
}
```

### Dish-scoped selection (recommended)

When a dish is selected in the UI, filter the registry by `dish_id` and show
only fish IDs whose status is not `discarded` or `stale`. A simple optional
index (`by_dish`) can speed this up; rebuild it whenever the registry is saved.

### Registry status rules

- `pending`: recorded at acquisition, not yet imported
- `complete`: imported successfully
- `discarded`: intentionally dropped
- `stale`: auto-marked if too old

### Pruning policy (recommended)

- If `pending` and `last_seen_utc` older than **7 days**, mark `stale`
- If `stale` older than **30 days**, delete the entry
- Optional cap: keep at most **200** entries (drop oldest)

## Import receipt sync (DB host -> acquisition machine)

Historical, consumer-owned. Receipts pass between the processing/import
pipeline and the acquisition machine; MetaZebrobot does not write or read
them. The protocol is archived in
[`archive/processing_import_receipts.md`](archive/processing_import_receipts.md);
no current consumer document for it was found. The text below is the original
proposal and may not match what is deployed.

Use a lightweight receipt queue on the DB host to mark sessions as imported
without tight coupling between machines.

### Receipt location (DB host)

- Directory: `/nvme1/fisheye_import_receipts/`
- Each receipt is a small JSON file named by `session_uuid`, written atomically.

Example receipt:

```json
{
  "session_uuid": "2026-01-20T19-35-22Z_arena_1",
  "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
  "status": "complete",
  "imported_at_utc": "2026-01-20T21:10:00Z"
}
```

### DB host: receipt writer snippet (Python)

```python
from pathlib import Path
import json, datetime, uuid

out_dir = Path("/nvme1/fisheye_import_receipts")
out_dir.mkdir(parents=True, exist_ok=True)

receipt = {
    "session_uuid": session_uuid,
    "fish_id": fish_id,
    "status": "complete",  # or "discarded"
    "imported_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
}

tmp_path = out_dir / f"{session_uuid}.json.tmp"
final_path = out_dir / f"{session_uuid}.json"
tmp_path.write_text(json.dumps(receipt))
tmp_path.rename(final_path)
```

### Acquisition machine: sync script

Save as `~/.local/bin/sync_fisheye_receipts.sh` and `chmod +x`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REMOTE="delahantyj@delahantyj-ws1.hhmi.org"
REMOTE_DIR="/nvme1/fisheye_import_receipts/"
LOCAL_DIR="${HOME}/.local/share/fisheye/import_receipts"

mkdir -p "${LOCAL_DIR}"

rsync -av --remove-source-files \
  "${REMOTE}:${REMOTE_DIR}" \
  "${LOCAL_DIR}/"
```

### Acquisition machine: systemd user timer

Service file: `~/.config/systemd/user/fisheye-receipts-sync.service`

```ini
[Unit]
Description=Sync fisheye import receipts

[Service]
Type=oneshot
ExecStart=%h/.local/bin/sync_fisheye_receipts.sh
```

Timer file: `~/.config/systemd/user/fisheye-receipts-sync.timer`

```ini
[Unit]
Description=Run fisheye receipt sync every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer:

```bash
systemctl --user daemon-reload
systemctl --user enable --now fisheye-receipts-sync.timer
```

### Registry update behavior

When a new receipt is seen:

- Update matching `session_uuid` in the local registry.
- If all sessions for a fish are `complete` or `discarded`, the fish entry can be
  removed (or left until next prune pass).
