# Next Steps

## Completed (April 2-4, 2026)

### Screening model redesign
- [x] `indicator_screened` → `indicators_screened` (list) + `pigment_screened` (bool)
- [x] `number_positive` → `number_kept`
- [x] `enclosure_in_beaker` → `container_type` (petri_dish, beaker, well_plate, tank)
- [x] Derived dish splitting with explicit fish count (`POST /screening/{dish_id}/split`)
- [x] Automated tests for split endpoint (success, 404, validation, inheritance, suffix)
- [x] Session/fish_runs tables removed (belongs in Palette)
- [x] DB migration logic for all column renames
- [x] Screening protocol suggestions updated for new model (`pigment_screened` pre-fill, real indicator names)

### Structured transgene data
- [x] `dish_transgenes` table (promoter, reporter, fluorophore, excitation_nm, emission_nm, fluorophore_color)
- [x] `parse_genotype()` extracts structured data from genotype strings
- [x] Fluorophore extraction with spectral wavelength lookup (GFP 488/509nm, jRGECO 565/600nm, etc.)
- [x] Auto-populated on dish save, one-time backfill on startup
- [x] Fuzzy protocol matching (promoter-set comparison when exact string fails)
- [x] `GET /dishes?promoter=elavl3` filter
- [x] Transgene tags displayed on screening, care, and fish pages (promoter:reporter + wavelengths + color border)

### Visual plate map
- [x] CSS grid rendering of well plates on fish list page
- [x] Occupied wells green with fish labels, empty wells gray
- [x] Unassigned fish section below grid
- [x] Simple occupant list for open containers (petri dish, beaker, tank)
- [x] Single JOIN query (`get_housing_units_with_fish`) avoids TOCTOU

### mapzebrain atlas integration
- [x] Fetch + cache markers catalog (738 lines) from mapzebrain API
- [x] Auto-match transgenic lines by genotype promoter/reporter
- [x] Dorsal-view expression pattern images on screening form
- [x] Offline fallback message when catalog unavailable
- [x] Larger atlas-thumb CSS class for brain images
- [x] Full-genotype reference image design documented in `docs/genotype_reference_images_design.md`
- [x] Genotype Reference panel reads curated exact-genotype PNG metadata
- [x] Read-only References page lists curated exact-genotype references
- [x] References page supports manual genotype reference PNG/JPEG upload

### Daily care web form
- [x] `/care/` dish list with red highlight for unchecked dishes
- [x] Adaptive form: dish-level check for simple containers, per-unit grid for well plates
- [x] "Apply to all" convenience toggles for fed/water on per-unit form
- [x] `POST /care/{dish_id}/check` and `POST /care/{dish_id}/unit-checks` endpoints
- [x] HTMX check history partial

### Labels and barcode scanning
- [x] `GET /dishes/{dish_id}/label` — PNG label (62x29mm, 300 DPI) with QR code
- [x] QR encodes dish_id for USB barcode scanner and phone camera
- [x] Scan-to-navigate input on screening and care dish lists (`data-navigate` pattern)
- [x] "Print Label" button on care and screening forms
- [x] `qrcode` dependency added
- [x] Scanner hardware guidance documented in `docs/fish_tracking_api.md`

### Dish creation via web
- [x] `/dishes/new` form with all fields matching desktop app
- [x] PyRAT cross auto-fill via HTMX (genotype, responsible, parents)
- [x] Cross datalist populated from crosses table (active-dish crosses first, new crosses included)
- [x] "Refresh Crosses from PyRAT" button (last 30 days, filtered by user)
- [x] Redirects to screening page on success
- [x] "New Dish" buttons on home, screening, and care pages

### In-browser guided tour
- [x] Driver.js v1.4.0 vendored (MIT, ~7KB gzipped)
- [x] `POST /walkthrough/setup` creates TOUR_ test data (dish, screening, derived dish, fish, wells)
- [x] `POST /walkthrough/cleanup` sweeps all TOUR_ dishes from database
- [x] Multi-page tour via localStorage step tracking
- [x] Click-to-advance steps, optional steps, custom button labels
- [x] Stale data cleanup on page load and tour start (sendBeacon, no beforeunload)
- [x] Atlas `<details>` opens/closes with spotlight via onShow/onLeave
- [x] Dynamic navigation via `getNavigateTo()` (reads dish_id at click time)

### PyRAT browser
- [x] `/pyrat/tanks/` — tank list with age color coding (URGENT >365d, WARNING >315d, OK)
- [x] Summary badges showing urgent/warning/ok counts
- [x] `/pyrat/crossings/` — crossing list with status colors and performance tracking
- [x] Links from crossings to local dishes
- [x] Sortable table columns (click headers, numeric + alpha sort, ▲/▼ indicators)
- [x] Filtered by current user's responsible_id

### User identity
- [x] Cookie-based user switcher in nav bar (30-day expiry)
- [x] User list populated from `~/.pyrat_user_mapping.json`
- [x] `_current_user(request)` replaces all hardcoded username references
- [x] Middleware injects `current_user` and `user_list` into all templates

### Infrastructure and fixes
- [x] Home page at `/` with feature cards and "Start Guided Tour" button
- [x] TemplateResponse deprecation fix (all 25 calls updated to new Starlette signature)
- [x] Removed unused `[project.optional-dependencies] api` from pyproject.toml
- [x] Screening dish list queries DB directly (not through FishDish model)
- [x] Correlated subqueries replaced with LEFT JOIN + GROUP BY in dish lists
- [x] Scan input handler deduplicated (one handler in base.html, `data-navigate` attribute)
- [x] Walkthrough cleanup: TOUR_ prefix guard, screening_images directory sweep
- [x] Reusable `_fetch_pyrat()` helper for PyRAT API calls
- [x] 7 stale docs updated, identity contract and enclosure design docs
- [x] 128 tests passing, zero warnings

## Remaining

### Web UI — next features
- [ ] Material tracking web UI (agarose, fish water, poly-L-serine)
- [ ] Export/survivability reports via web
- [ ] Label printer hardware integration (Brother QL-820NWB)
- [ ] Mobile / single-column layout for care form on phones

### Citrus integration prep
- [ ] Coordinate with Citrus on identity assignment API calls
  (`GET /dishes/{dish_id}/fish`, `POST /dishes/{dish_id}/fish`)
- [ ] Define H5 snapshot schema_version=2 format — needs per-fish metadata
  (fish_id, current housing unit, provenance chain)
- [ ] Verify Palette's `_backfill_subject_dish_cross_entities()` handles
  known fish via `INSERT OR IGNORE` / `ON CONFLICT`

### Future
- [ ] Design `POST /dishes/{dish_id}/fish/place` batch endpoint
  (register N fish + create wells + assign in one call)
- [ ] Optional automatic well creation when splitting into well_plate
  (revisit once workflow is clearer)
- [ ] Palette integration: read-only session count display on fish detail pages
  (optional `--palette-registry` CLI arg on API server)
