# Next Steps

## Near-term

- [x] Add automated tests for `POST /screening/{dish_id}/split` endpoint
- [x] Commit screening model redesign, derived dish splitting,
  container_type migration, session/fish_runs removal, identity contract docs
- [x] Visual plate map on fish list page (CSS grid for well plates)
- [x] mapzebrain atlas reference images on screening form
- [x] Normalized `dish_transgenes` table with genotype parser and fuzzy protocol matching
- [x] Daily care web form (`/care/`) with dish-level and per-unit checks
- [x] Dish label generation with QR codes (`GET /dishes/{dish_id}/label`)
- [x] Barcode scan-to-navigate input on dish list pages
- [x] In-browser guided tour with Driver.js (setup/cleanup endpoints)
- [x] Home page at `/`
- [x] Fix TemplateResponse deprecation (all calls updated to new Starlette signature)
- [x] Fix screening dish list to query DB directly (not through FishDish model)
- [x] Update stale docs (7 files updated, removed references to deleted tables)

- [ ] Review screening protocol suggestions in web form — protocol-aware
  hints may need updating for `indicators_screened` (list format)

## Web UI — next features

- [ ] Dish creation via web UI (currently desktop-only)
- [ ] Material tracking web UI (agarose, fish water, poly-L-serine)
- [ ] Export/survivability reports via web
- [ ] PyRAT tank/crossing browser for web
- [ ] Label printer hardware integration (Brother QL-820NWB)
- [ ] Mobile / single-column layout for care form on phones

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
