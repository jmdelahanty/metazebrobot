# Experimental Data Registry Notes

> **Status:** Session and experiment tracking was removed from MetaZebrobot.
> Sessions, runs, and file asset tracking belong in **Palette**, which owns the
> behavioral pipeline. See `docs/identity_and_provenance_contract.md` for the
> cross-repo data flow.

This document preserves the original design notes for reference. The tables and
queries described below do **not** exist in MetaZebrobot's schema.

## Goal
Make it easy to answer queries like:

> "Give me all fish that were 8 dpf and ran protocol X."

This query is answered by **Palette**, which stores experiment sessions, fish
runs, and file assets. MetaZebrobot provides the fish identity registry
(`fish_subjects`) and housing/provenance data that Palette references via the
`fish_id` UUID.

## MetaZebrobot tables (current)

- `fish_subjects`:
  - `fish_id` (PK)
  - `dish_id` (FK -> dishes)
  - `subject_label`, `sex`, `genotype`, `species`, `created_at`, `notes`
  - `current_unit_id` (FK -> housing_units)

## Palette tables (session tracking)

The following tables live in Palette's database, not MetaZebrobot:

- `experiment_sessions` — session_uuid, run_at_utc, rig_id, arena_id, protocol_name, h5_path
- `fish_runs` — fish_id, session_uuid, dpf_at_run (links fish to sessions)
- `session_assets` — per-session file paths (raw, cam, derived, zarr)

## Example query (in Palette)

```sql
SELECT f.fish_id
FROM fish_runs r
JOIN subjects f ON f.fish_id = r.fish_id
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

Populate (in Palette):
- `experiment_sessions`: session_uuid, run_at_utc, arena_id, protocol_name, rig_id, h5_path
- `session_assets`: one row per file with `asset_type` + `path`
- `fish_runs`: one row per fish involved in session (+ `dpf_at_run` if available)

## TODO
- Decide on absolute vs. project-relative `path` storage (Palette).
- Confirm `session_uuid` source (folder name, UUID in metadata, etc.).
- Add indexes in Palette if queries become heavy.
