# Migrating From Local Crosses to PyRAT-Only Crossings

## Context

The application currently maintains a local `Cross` model with its own database table, separate from the `PyRATCrossing` model which represents data fetched from the PyRAT API. Both models share some overlapping fields (e.g., `requested_groups`, responsible person), which creates a dual-definition problem. The long-term plan is to stop maintaining local crosses and derive everything from PyRAT.

This document captures what the local Cross model provides that PyRAT does not, and what would need to change.

## Field Comparison

| Feature | Local Cross | PyRAT Crossing | Gap |
|---|---|---|---|
| Cross/crossing ID | `cross_id` (str) | `crossing_id` (int) | Type difference only |
| Responsible person | `responsible_requestor` (who requested) | `responsible_fullname` (who requested) | **Equivalent** — see note below |
| Strain/genotype | `line_strain` (full genotype string) | `strain_name` (full genotype string) | **Equivalent** — see note below |
| Parent identifiers | `parents[].identifier` (e.g., "M11:E5 (5187)") | `parent_tanks[].tank_id` (numeric) | Local is human-readable |
| Parent genotypes | `parents[].genotype` | Not available | No PyRAT equivalent |
| Requested groups | Direct field | Parsed from description text via regex | Fragile on PyRAT side |
| Transgenic indicators | Structured `TransgenicIndicator` objects (promoter, reporter, color, expected expression, computed standard notation) | Not available | No PyRAT equivalent |
| Aggregate screening results | `AggregateResults` (yield %, totals, date) | Not available | No PyRAT equivalent |
| Lifecycle status | Requested → Performed → Screening → Completed → Archived | recorded → set-up → raised / discarded | Different workflow |
| Cross type | Standard / Transgenic / unknown | Not available | No PyRAT equivalent |

## What Would Break

### High Risk — No PyRAT Equivalent

**Transgenic indicator tracking.** The local Cross stores structured `TransgenicIndicator` objects with fields for `modification_type`, `promoter_driver`, `reporter_effector`, `color`, `expected_expression`, and a computed `standard_notation` (e.g., `Tg(gfap:GFP)`). PyRAT has no structured representation of this — at best it lives in a free-text description. This data is displayed in the cross detail view, searched across in cross search, and stored in a normalized `transgenic_indicators` table.

**Aggregate screening results.** Yield percentage, total initially produced, and total positive final are calculated from all dishes linked to a cross and stored on the Cross object. PyRAT has no aggregation mechanism. This calculation logic lives in `cross_controller.update_aggregate_results()` and would need a new home.

**Parent genotypes.** The local `Parent` model stores an optional genotype per parent. PyRAT's `CrossingTank` has no genotype field.

### Resolved — Strain/Genotype Is Equivalent

~~Initially assumed PyRAT's `strain_name` was a simple colony reference (e.g., `Casper_HHMI`).~~ Verified against live PyRAT data that `strain_name` carries the full transgenic notation for transgenic crossings (e.g., `Tg(gfap:TRPV1-T2A-GFP); Tg(elavl3:jRGECO1b)`). For non-transgenic crosses, it carries the stock name (e.g., `Casper_HHMI`). This matches the local `line_strain` values exactly.

**Dish genotype auto-fill can use PyRAT's `strain_name` directly.** No local fallback needed for this field.

### Resolved — Responsible Person Is Equivalent

~~Initially assumed PyRAT's `responsible_fullname` on a crossing referred to who performed the crossing, not who requested it.~~ In practice, the "responsible person" on a PyRAT crossing is the person who requested the cross. This matches the local `responsible_requestor` semantics.

Note: The responsible person on the *crossing* can differ from the responsible person on individual *tanks* — a tank's responsible person may be someone else (e.g., the facility manager or a different lab member). This is a PyRAT-level distinction, not something the local model tracks.

**Dish responsible auto-fill can use PyRAT's `responsible_fullname` directly.**

### Medium Risk — Data Exists but Differs

**Dish form auto-fill (remaining gaps).** When creating a new dish, the fish dish tab auto-fills three fields from the selected local Cross:
- `genotype` ← `cross.line_strain` — **resolved**: PyRAT `strain_name` is equivalent
- `responsible` ← `cross.responsible_requestor` — **resolved**: PyRAT `responsible_fullname` is equivalent
- `parents` ← `cross.parents[].identifier` — PyRAT has `parent_tanks[].tank_id` (numeric) and `parent_tanks[].tank_label`. Parent identifiers would degrade from human-readable locations to numeric tank IDs unless `tank_label` is populated.

**Cross creation UI.** The `AddCrossDialog` is entirely built around the local Cross model, including transgenic indicator entry. It would need redesign or removal.

**Cross browsing and editing.** The `CrossTab` displays, filters, searches, and allows status updates on local crosses. Would need to be reworked to display PyRAT data, losing edit capability for fields PyRAT doesn't support.

### Low Risk — Straightforward Mapping

- Linking dishes to crossings via `cross_id` / `crossing_id`
- Date fields (different formats but convertible)
- Basic status display (terminology changes)
- Network graph export (adapts to new data source)
- API server endpoints (route to PyRAT or remove)

## Files That Would Require Changes

### Heavy Rework
- `views/cross_tab.py` — entire tab built around local Cross model
- `views/dialogs/add_cross_dialog.py` — local Cross creation form
- `controllers/cross_controller.py` — all Cross CRUD and aggregate logic
- `data/data_manager.py` — Cross persistence sections (save, load, tables)

### Medium Rework
- `views/fish_dish_tab.py` — cross dropdown and auto-fill mechanism (lines 46-77, 100-107)
- `controllers/fish_dish_controller.py` — cross_id validation, AggregateResults import
- `models/fish_dish.py` — cross_id field semantics

### Light Touch
- `views/main_window.py` — tab initialization
- `utils/export_module.py` — cross nodes in network graph
- `api_server.py` — cross-related endpoints

## Recommended Migration Path

Rather than a full removal, a hybrid approach would avoid losing data PyRAT can't store:

1. **Make PyRATCrossing the primary source** for cross identity, status, dates, responsible person, and parent tanks.
2. **Keep a slim local supplemental table** for data PyRAT cannot provide:
   - Transgenic indicator metadata
   - Aggregate screening results
   - Optionally: parent genotypes, requestor (if distinct from performer)
3. **Remove the local Cross creation workflow** — crosses originate in PyRAT, and the local supplement is added after.
4. **Update dish auto-fill** to pull genotype directly from PyRAT `strain_name` (confirmed equivalent to local `line_strain`). Responsible person and parent identifiers may still need local supplementation depending on workflow needs.
