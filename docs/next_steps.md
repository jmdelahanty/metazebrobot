# Next Steps

## Near-term

- [ ] Add automated tests for `POST /screening/{dish_id}/split` endpoint
  - Successful split with custom container type
  - Split on nonexistent dish (404)
  - Zero fish count (validation error)
  - Split inherits parent properties correctly

- [ ] Commit current work — screening model redesign, derived dish splitting,
  container_type migration, session/fish_runs removal, identity contract docs

- [ ] Review screening protocol suggestions in web form — the protocol-aware
  hints (pre-filling indicators) reference the old single-indicator format
  and may need updating for `indicators_screened` (list)

## Citrus integration prep

- [ ] Coordinate with Citrus on identity assignment API calls
  (`GET /dishes/{dish_id}/fish`, `POST /dishes/{dish_id}/fish`)

- [ ] Define H5 snapshot schema_version=2 format — needs per-fish metadata
  (fish_id, current housing unit, provenance chain)

- [ ] Verify Palette's `_backfill_subject_dish_cross_entities()` handles
  known fish via `INSERT OR IGNORE` / `ON CONFLICT`

## Future

- [ ] Design `POST /dishes/{dish_id}/fish/place` batch endpoint
  (register N fish + create wells + assign in one call)

- [ ] Optional automatic well creation when splitting into well_plate
  (revisit once workflow is clearer)

- [ ] Palette integration: read-only session count display on fish detail pages
  (optional `--palette-registry` CLI arg on API server)
