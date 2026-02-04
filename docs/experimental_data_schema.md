# Experimental Data Registry Notes

This document describes how to store experimental session metadata and file paths
so dataset builders can query runs by fish and experimental context.

## Goal
Make it easy to answer queries like:

> "Give me all fish that were 8 dpf and ran protocol X."

We already have `fish_subjects`, `experiment_sessions`, and `fish_runs` in the
SQLite schema. The missing piece is a consistent way to store per-session file
paths and (optionally) a precomputed `dpf_at_run`.

## Current tables (already present in schema.sql)

- `fish_subjects`:
  - `fish_id` (PK)
  - `dish_id` (FK -> dishes)
  - `subject_label`, `sex`, `genotype`, `species`, `created_at`, `notes`

- `experiment_sessions`:
  - `session_uuid` (PK)
  - `run_at_utc`, `rig_id`, `arena_id`, `protocol_name`, `h5_path`

- `fish_runs`:
  - `run_id` (PK)
  - `fish_id` (FK -> fish_subjects)
  - `session_uuid` (FK -> experiment_sessions)
  - `notes`
  - unique `(fish_id, session_uuid)`

## Proposed additions

### 1) Store file paths in a flexible assets table
The recordings you generate have multiple files per session (raw, cam, derived,
zarr). A normalized table keeps this queryable.

Suggested table:

```
session_assets
  - asset_id INTEGER PRIMARY KEY AUTOINCREMENT
  - session_uuid TEXT NOT NULL (FK -> experiment_sessions)
  - asset_type TEXT NOT NULL           # raw_h5, raw_mp4, cam_mp4, cam_meta, zarr, derived_png, etc.
  - path TEXT NOT NULL                 # absolute path or project-relative
  - camera_id TEXT                     # optional
  - notes TEXT
  - created_at TEXT DEFAULT CURRENT_TIMESTAMP
```

### 2) Store dpf at runtime (optional but convenient)
If you already compute `dpf` at experimental runtime, persist it on `fish_runs`.
This makes the target query trivial and indexable.

Suggested column:

```
fish_runs.dpf_at_run INTEGER
```

Alternatively, if you prefer not to store it, it can be derived using dish `dof`
and session `run_at_utc`, but SQLite date math is more awkward.

## Example query (with dpf_at_run)

```
SELECT f.fish_id
FROM fish_runs r
JOIN fish_subjects f ON f.fish_id = r.fish_id
JOIN experiment_sessions s ON s.session_uuid = r.session_uuid
WHERE r.dpf_at_run = 8
  AND s.protocol_name = 'DefaultScreen';
```

## Ingestion mapping (example)

Given a session folder like:

```
2026-01-28T19-22-28Z_arena_1_DefaultScreen/
  raw/2026-01-28T19-22-28Z_arena_1_DefaultScreen.h5
  raw/2026-01-28T19-22-28Z_arena_1_DefaultScreen.mp4
  cams/Cam2010093.mp4
  cams/Cam2010093_meta.csv
  zarr/...
  derived/extracted_2010096_homography_image.png
```

Populate:
- `experiment_sessions`:
  - `session_uuid`: derived from folder name or metadata
  - `run_at_utc`, `arena_id`, `protocol_name`, `rig_id`, `h5_path`
- `session_assets`: one row per file with `asset_type` + `path`
- `fish_runs`: one row per fish involved in session (+ `dpf_at_run` if available)

## TODO
- Decide on absolute vs. project-relative `path` storage.
- Confirm `session_uuid` source (folder name, UUID in metadata, etc.).
- Add indexes if queries become heavy:
  - `session_assets(session_uuid)`
  - `fish_runs(dpf_at_run)`
  - `experiment_sessions(protocol_name)`
