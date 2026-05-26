# MetaZebrobot H5 Snapshot Integration

This document describes how the acquisition agent should query the
MetaZebrobot read-only API and store a minimal, no-PII snapshot in an H5 file.

## Schema overview

End-to-end pieces:

1) **H5 subject metadata** (`/subject_metadata`)
   - `zebrobot_schema_version` (int, start at 1)
   - `dish_id`, `cross_id`, `genotype`, `line_strain`
   - `date_of_fertilization` (YYYYMMDD), `fish_count`, `species`, `sex`
   - `queried_at_utc` (ISO8601)
   - `parents` (JSON string, machine-parseable list of `{identifier, sex}`)
   - `parents_display` (human-readable string)
   - optional: `dpf_at_acquisition` (int; set null + missing if invalid)

2) **Snapshot JSON schema** (logical model used to populate the H5 fields)
   - `schema_version`, `queried_at_utc`, `status`, `missing`, `dish_id`
   - `dish` (minimal fields) and `cross` (minimal fields; `null` if missing)
   - optional: `errors[]`, `dpf_at_acquisition`

3) **Local acquisition registry** (staging cache)
   - File: `~/.local/share/fisheye/subject_registry.json`
   - Tracks `fish_id` UUIDs for immediate reuse across sessions
   - Prune aggressively; registry is not the source of truth

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

Note: `GET /crosses/{cross_id}` returns `parents` as a JSON array. Older
snapshots may have stored this field as a JSON-encoded string.

If `GET /acquisition/dishes?status=active...` returns an empty `items` list,
MetaZebrobot has no currently active dishes matching the filter. Create or
reactivate an acquisition-ready dish in MetaZebrobot rather than changing the
status value in Citrus.

## Snapshot JSON schema (required fields)

Store a single JSON object with the following fields:

```json
{
  "schema_version": 1,
  "queried_at_utc": "2026-01-16T23:45:12Z",
  "status": "complete",
  "missing": [],
  "dish_id": "15238_1",
  "dish": {
    "dish_id": "15238_1",
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
  - Compute as: `session_start_utc.date() - dof_date` (UTC dates).
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
  { "source": "cross", "message": "not found" }
]
```

## H5 storage layout

Store a flattened snapshot under:

- Group: `/subject_metadata`

Recommended fields:

- `zebrobot_schema_version` (integer, start at 1)
- `dish_id`
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

- Parse `cross.parents` from JSON string to a list of objects.
  - If parsing fails, set `parents=[]` and add an error if desired.
- `species` and `sex` are only available from `GET /dishes/{dish_id}`.
- `dish_id` is provided by the acquisition UI dropdown (populated from active
  dishes).

## C++ client notes (DearImGui)

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
