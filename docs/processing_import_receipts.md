# Processing Suite: Import Receipt Protocol

This document describes how the processing/import pipeline should signal
successful or discarded imports back to the acquisition machine via receipt
files.

## Purpose

The acquisition machine maintains a local registry of fish IDs so the same
individual can be reused across sessions **before** imports complete. When
an import finishes (or is discarded), the processing suite writes a small JSON
receipt on the DB host so the acquisition registry can update itself.

## Receipt location (DB host)

- Directory: `/nvme1/fisheye_import_receipts/`
- Each receipt is a JSON file named by `session_uuid`:
  - `{session_uuid}.json`
- Write atomically: write a `*.tmp` file then rename.

## Receipt schema

```json
{
  "session_uuid": "2026-01-20T19-35-22Z_arena_1",
  "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
  "status": "complete",
  "imported_at_utc": "2026-01-20T21:10:00Z"
}
```

### Status values

- `complete`: import succeeded and DB records were written
- `discarded`: import intentionally skipped/dropped

## When to emit receipts

- **Success path**: after the session has been committed to the database.
- **Discard path**: after you decide a session will not be imported.
- **Failure path**: do **not** emit a receipt; the registry remains `pending`.

## Minimal Python writer (example)

```python
from pathlib import Path
import json, datetime

def write_receipt(session_uuid: str, fish_id: str, status: str):
    out_dir = Path("/nvme1/fisheye_import_receipts")
    out_dir.mkdir(parents=True, exist_ok=True)

    receipt = {
        "session_uuid": session_uuid,
        "fish_id": fish_id,
        "status": status,  # "complete" or "discarded"
        "imported_at_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }

    tmp_path = out_dir / f"{session_uuid}.json.tmp"
    final_path = out_dir / f"{session_uuid}.json"
    tmp_path.write_text(json.dumps(receipt))
    tmp_path.rename(final_path)
```

## Notes

- The acquisition machine periodically syncs and removes receipts from this
  directory (rsync with `--remove-source-files`).
- Do not store PII in receipts.
