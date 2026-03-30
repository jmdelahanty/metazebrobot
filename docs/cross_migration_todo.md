# Cross → PyRAT Migration: Open Decisions & TODOs

Tracks the remaining items needed before local crosses can be removed in favor of PyRAT-only crossings. See `cross_to_pyrat_migration_risks.md` for full context.

## Already Resolved

- [x] **Genotype/strain**: PyRAT `strain_name` is equivalent to local `line_strain`
- [x] **Responsible person**: PyRAT `responsible_fullname` on crossings is the requestor, same as local `responsible_requestor`

## Open Items

### 1. Aggregate Screening Results

**Problem:** Yield %, total initially produced, and total positive final are currently calculated from dish data and stored on the local Cross object. PyRAT has no aggregation mechanism and cannot store these values.

**Options:**
- A) Compute on demand — query dishes by `cross_id` and calculate whenever the UI needs it
- B) Cache in a standalone `crossing_aggregates` table keyed by `crossing_id`, recalculated when screening data changes

**Decision:** On-demand computation. The number of dishes per cross is small (1-3 typical), so there's no performance concern. No extra table needed.

**Action items:**
- [ ] Extract aggregate calculation logic from `cross_controller.update_aggregate_results()` into a standalone function (e.g., in `fish_dish_controller`) that takes a `cross_id` and computes results from dishes on the fly
- [ ] Update any UI that displays aggregates to call the new function instead of reading from the Cross object
- [ ] Remove aggregate storage fields from the Cross model and `crosses` table when the full migration happens

---

### 2. Structured Transgenic Indicators

**Problem:** Local Cross stores structured `TransgenicIndicator` objects with `modification_type`, `promoter_driver`, `reporter_effector`, `color`, and `expected_expression`. PyRAT only has the `strain_name` string (e.g., `Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)`).

**What can be parsed from `strain_name`:**
- `modification_type` (e.g., `tg` from `Tg(` prefix)
- `promoter_driver` (e.g., `gfap`, `elavl3`)
- `reporter_effector` (e.g., `TRPV1-T2A-GFP`, `jRGECO1b`)

**What cannot be parsed (user annotations):**
- `color` (e.g., Green, Red)
- `expected_expression` (e.g., pan-glial, pan-neuronal)

**Options:**
- A) Parse promoter/reporter from `strain_name` at runtime, keep a slim local `transgenic_annotations` table for `color` and `expected_expression` only
- B) Keep the existing `transgenic_indicators` table as-is, just keyed by `crossing_id` instead of `cross_id`

**Decision:** Keep full local `transgenic_indicators` table (option B), re-keyed to `crossing_id`. Structured columns enable direct queries like "all crossings using UAS promoters" or "all crossings with GFP" without repeated string parsing. The duplication with PyRAT's `strain_name` is a small cost for clean queryability.

**Action items:**
- [ ] Re-key `transgenic_indicators` table from `cross_id` to `crossing_id` when migration happens
- [ ] Decide if indicators should be populated manually (current approach) or seeded by a one-time parse of `strain_name` with manual review
- [ ] Ensure the UI for adding/editing indicators works against PyRAT crossings instead of local crosses

---

### 3. Parent Tank Information

**Problem:** Local Cross stores parent identifiers as human-readable strings (e.g., `#5182_M11>E1`) and optional genotypes per parent. PyRAT's `CrossingTank` model has `tank_id` (numeric), `tank_label`, and `strain_name`, but it's unclear whether these are populated for parent tanks on crossings.

**What needs verification:**
- Does PyRAT populate `strain_name` on parent tanks within a crossing response? (Would cover parent genotypes.)
- Does PyRAT populate `tank_label` on parent tanks? If so, what format? (Would cover parent identifiers.)

**Options (pending verification):**
- A) If PyRAT provides sufficient parent tank detail, use it directly — no local storage needed
- B) If PyRAT data is sparse, keep a local `crossing_parents` supplement table for genotype and human-readable identifier

**Decision:** PyRAT provides sufficient data — no local supplementation needed (option A).

Verified against live API response for crossing 15178. PyRAT parent tanks include:
- `strain_name` → parent genotype (e.g., `WIK Casper_HHMI`, `Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)`)
- `location_rack_name` + `tank_position` → human-readable identifier (e.g., M11 + E1 → `#5182_M11>E1`)
- `number_of_male` / `number_of_female` → sex inference
- `tank_label` is unreliable (sometimes null, sometimes unrelated notes) — do not depend on it

**Action items:**
- [x] Add `location_rack_name`, `location_room_name`, `tank_position` to `CrossingTank` model
- [x] Add these fields to `TANK_KEYS` in `PyRATCrossingsWorker`
- [x] Add a computed property on `CrossingTank` for a human-readable identifier (`location_display`, e.g., `#5182_M11>E1`)
- [x] Update crossing detail view to display parent rack/position and strain
- [ ] Update dish auto-fill to pull parent identifiers from PyRAT parent tanks when migration happens
