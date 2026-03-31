# Cross → PyRAT Migration: Complete

Migration from local crosses to PyRAT-only crossings is complete.

## What was done

- **Genotype/strain**: PyRAT `strain_name` replaces local `line_strain`
- **Responsible person**: PyRAT `responsible_fullname` replaces local `responsible_requestor`
- **Aggregate screening results**: Computed on demand via `fish_dish_controller.compute_aggregate_results()` — no stored aggregates
- **Transgenic indicators**: `crossing_transgenic_indicators` table keyed by PyRAT `crossing_id`, seeded from strain parser, editable via `TransgenicIndicatorDialog`
- **Parent tank info**: PyRAT provides `location_rack_name` + `tank_position` + `strain_name` — no local supplementation needed
- **Dish auto-fill**: Uses `pyrat_tanks_controller.cached_crossings` for dropdown and form fields

## What was removed

- `models/cross.py` — `AggregateResults` moved to `fish_dish_controller.py`
- `controllers/cross_controller.py`
- `views/cross_tab.py`
- `views/dialogs/add_cross_dialog.py`
- `views/dialogs/update_cross_status_dialog.py`
- `data_manager.py` — removed `save_cross`, `load_single_cross`, `get_crosses`, `_load_crosses_to_cache`, `_save_transgenic_indicators`, `get_transgenic_indicators`, `migrate_transgenic_data_to_normalized_table`, `migrate_crosses_to_flattened_columns`
- Old `transgenic_indicators` table creation (replaced by `crossing_transgenic_indicators`)
- Aggregate columns (`agg_*`) on `crosses` table
- Crosses indexes from schema updates
- `export_module.py` — `cross_controller` replaced with `pyrat_tanks_controller`

## Note on the `crosses` table

The `crosses` table still exists in the SQLite database for historical data. It is no longer read or written by the application. It can be dropped manually if desired, or kept as an archive.
