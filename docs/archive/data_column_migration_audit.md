# Dishes `data` JSON Column — Migration Audit

## Background

The `dishes` table originally stored all dish metadata as a single JSON blob in
the `data` column. Over time, fields were promoted to dedicated columns so they
could be queried, indexed, and validated at the database level. The JSON blob is
still written on every save for backward compatibility, but flattened columns
are now treated as authoritative on reads.

This document records the current state of the migration and what remains to
finish it.

## Current read/write behaviour

### Writes (`save_fish_dish` in `data_manager.py`)

1. Each flattened column is written individually.
2. The **entire** FishDish model is also serialised to the `data` JSON column.
3. Quality checks are written to the `quality_checks` table.
4. Screening steps are written to the `screening_steps` table.

### Reads (`load_single_dish` in `data_manager.py`)

1. Parse the `data` JSON column as a base dictionary.
2. **Override** with values from flattened columns (columns are authoritative).
3. Reconstruct nested objects (`enclosure`, `breeding`, `screening_results`)
   from their respective columns and tables.

This means the JSON blob is only consulted for fields that have no column yet.

## Field-by-field status

### Fully flattened — column exists and is authoritative

| FishDish field | Column | Type |
|---|---|---|
| `dish_id` | `dish_id` | TEXT PK |
| `cross_id` | `cross_id` | TEXT |
| `date_created` | `date_created` | TEXT |
| `dof` | `dof` | TEXT |
| `genotype` | `genotype` | TEXT |
| `responsible` | `responsible` | TEXT |
| `status` | `status` | TEXT |
| `fish_count` | `fish_count` | INTEGER |
| `species` | `species` | TEXT |
| `sex` | `sex` | TEXT |
| `parent_dish_id` | `parent_dish_id` | TEXT |
| `dish_population_type` | `dish_population_type` | TEXT |
| `notes` | `notes` | TEXT |
| `termination_date` | `termination_date` | TEXT |
| `termination_reason` | `termination_reason` | TEXT |
| `enclosure.temperature` | `enclosure_temperature` | REAL |
| `enclosure.room` | `room` | TEXT |
| `enclosure.container_type` | `container_type` | TEXT |
| `enclosure.vol_water_total` | `enclosure_vol_water_total` | INTEGER |
| `enclosure.light_cycle.light_duration` | `enclosure_light_duration` | TEXT |
| `enclosure.light_cycle.dawn_dusk` | `enclosure_dawn_dusk` | TEXT |
| `breeding.parents` | `breeding_parents` | TEXT (JSON list) |
| `screening_results.final_positive_count` | `screening_final_positive_count` | INTEGER |
| `screening_results.date_finalized` | `screening_date_finalized` | TEXT |

### Normalised to separate tables

| FishDish field | Table | Notes |
|---|---|---|
| `quality_checks` | `quality_checks` | One row per check. Loaded on demand via `include_checks` param. |
| `screening_results.screenings[]` | `screening_steps` | One row per step. Loaded during `load_single_dish`. |

### Gaps — only in JSON, no column

| FishDish field | Type | Description |
|---|---|---|
| `source_group_id` | `Optional[str]` | Aquatics source tank identifier (e.g. "15178-G1") |
| `dish_number` | `Optional[int]` | Optional dish sequence number |

These two fields are the only data that would be lost if the `data` JSON column
were dropped today.

## Other tables with `data` JSON columns

The `dishes` table is not the only one carrying a JSON blob:

| Table | `data` column usage |
|---|---|
| `crosses` | Full crossing JSON — **not yet audited** |
| `quality_checks` | Full check JSON alongside flattened columns |
| `materials` | Full material JSON — primary storage, no flattened columns |

The `quality_checks.data` column duplicates the same fields that already have
dedicated columns (`fed`, `feed_type`, `water_changed`, etc.) and could also be
dropped after the dishes migration is complete.

## `breeding_parents` — denormalised JSON list

The `breeding_parents` column stores a JSON-serialised list (e.g.
`["parent-id-1", "parent-id-2"]`) in a TEXT field. A fully normalised design
would use a `dish_parents` join table, but since:

- the list is always 1–2 items,
- there is no need to query "which dishes share parent X",
- the values are opaque identifiers from PyRAT,

the JSON list is a reasonable trade-off and does not need further normalisation.

## Steps to finish the migration

1. **Add 2 columns** to the `dishes` table:
   - `source_group_id TEXT`
   - `dish_number INTEGER`

2. **Backfill** — copy values from the `data` JSON blob into the new columns
   for every existing row.

3. **Update `save_fish_dish()`** — write `source_group_id` and `dish_number` to
   their columns. Stop writing the `data` JSON column (or write NULL).

4. **Update `load_single_dish()`** — read `source_group_id` and `dish_number`
   from columns. Remove the JSON-parsing fallback path.

5. **Update `get_dish_api()`** — stop returning the parsed `data` blob in API
   responses. Verify the Citrus snapshot contract
   (`~/gitrepos/palette/docs/zebrobot_snapshot.md`) does not depend on the
   `data` field.

6. **Deprecate** — set the `data` column to NULL on all rows (or drop it via
   `ALTER TABLE` if no external readers remain).

## API contract consideration

The `GET /dishes/{dish_id}` endpoint currently returns the parsed JSON blob
under a `data` key in addition to all flattened columns. Citrus snapshots dish
metadata into H5 files. Before dropping the `data` column, confirm that
Citrus reads from the top-level flattened fields (which will remain) and not
from inside the `data` object.
