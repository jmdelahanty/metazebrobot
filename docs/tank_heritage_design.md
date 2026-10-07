---
title: "Tank Heritage and Background Design"
summary: "Record-derived tank heritage: producing crosses, splits, backgrounds, strain ancestry and renames, plus the heritage view."
owner: metazebrobot
status: current
kind: design
verified_against: a56e219
verified_scope: "whole document"
---

# Tank Heritage and Background Design

Status (2026-10-06): steps 1–4 below are built and deployed; step 5 is not.
The view is at `/tanks/{tank_id}/heritage/` (linked from each parent on a
cross's provenance page). Keeping the cache current: `API_SERVICE_GUIDE.md`,
"Nightly Cross-Cache Sync".

Goal: for any dish, cross, or PyRAT tank, show where its fish came from — the
genetic background (AB, WIK, Casper, ...), whether each generation was an
incross or outcross, and the cohort — derived from PyRAT records, with the
aquatics team's strain labels as a cross-check. Eventually this becomes a
"heritage" view in the web app.

Builds on [`cross_parent_background_design.md`](cross_parent_background_design.md),
which defines the per-parent model (`cross_parents`) and the conservative
background parser (`utils/cross_provenance.py`).

## Findings (read-only investigation, 2026-10-06)

### Why parent background shows blank

The cached-cross page for cross 19220 showed empty backgrounds, generations, and
strains for both parents. PyRAT has the data (parent tank 8130:
`Casper_HHMI [AB-C] DEC25`, F1; tank 6728: `Tg(gfap:b-ARK)`, F3), but the local
cache never received it:

- Only 56 of 567 cached parents (29 of 289 crosses) have `strain_name`.
- Five code paths fetch `api/v3/tanks/crossings` and write the same cache, but
  request different per-tank fields (`tk`):

  | Path | Requests parent `strain_name` / `generation` |
  |---|---|
  | `_load_cross_prefill` (dish form), `get_cross_api` | yes |
  | `refresh_crosses_from_pyrat` | no tank fields at all |
  | `pyrat_crossings_page`, `pyrat_crossings_table` | no (`tank_id`, `tank_label`, `status` only) |

- `_merge_cross_payload` keeps per-tank fields from earlier fetches, so a sparse
  fetch does not erase data, but a cross only ever fetched by the sparse paths
  never gets it.

The parser is not the problem; on real strain names it already extracts the
background, line label, and casper flag (see the label table below).

### Aquatics strain labels

The aquatics team names cohort strains like `Casper_HHMI [AB-C IC] MAR26`
(confirmed with aquatics):

| Part | Meaning |
|---|---|
| `[AB-C]` / `[WIK-C]` | AB-Casper / WIK-Casper background |
| `IC` | Incross |
| `MAR26` | Cohort month |

These labels are a quick-glance convenience so people do not have to navigate
PyRAT. The structured truth is in PyRAT records; the label is a second,
lower-confidence reading.

### Labels checked against records

| Strain | Producing cross(es) | Parents | Derived | Children DOB |
|---|---|---|---|---|
| `Casper_HHMI [AB-C IC] MAR26` (1574) | 17697, 17698 (set up 2026-03-09) | 8129 + 8130, 8131 + 8132, all `Casper_HHMI [AB-C] DEC25` F1 | incross ✅ | 2026-03-10 ✅ |
| `Casper_HHMI [WIK-C IC] MAR26` (1577) | 17755 (set up 2026-03-16) | 8177 + 8178, both `Casper_HHMI [WIK-C] JAN26` F1 | incross ✅ | 2026-03-17 ✅ |

The cohort suffix matched tank date of birth in every case checked (e.g.
`[AB-C] DEC25` tank 8130, DOB 2025-12-23). Cross 19220's female parent (tank
8130) is one of the DEC25 breeders, so its background is AB + Casper.

### Properties of PyRAT data that shape the design

- **No tank → producing-cross link.** A tank's history begins with a
  `ReleaseEvent` that names no crossing. The only link is the other direction:
  a crossing's `tanks.children`. Finding a tank's origin needs a local
  child-tank → cross index.
- **Crossing `strain_name` is unreliable for this.** Breeding crosses are often
  named `TBD`, `SHIPMENT`, or `EXPERIMENTAL`; background and incross status must
  come from the parent tanks' strains.
- **Parentage crosses owners.** The DEC25 breeders belong to another user's
  crosses, so the cache must include crosses beyond the current user.
- **`generation` is counted within a strain.** Breeders and offspring of a new
  cohort strain are both `F1`; generation is not distance from founders.
- **Tank history is husbandry, not parentage.** Later events (moves, separations)
  relate many tanks at once; `scripts/inspect_cross_tank_provenance.py`
  documents this.
- **Strain pedigree is strain-level.** `backend/v1/reports/colony_pedigree`
  (`scripts/inspect_colony_pedigree.py`) returns strain → parent-strain edges
  back to founder backgrounds (e.g. `Tg(gfap:b-ARK)` ← `Casper_HHMI`,
  `Tol2-gfap:b-ARK-B78`, `Casper_HHMI [AB-C] DEC25` ← `AB Casper_HHMI` ←
  `AB`, `Casper_HHMI`). It is a PyRAT frontend internal (no compatibility
  guarantee), contains cycles (`Casper_HHMI` ↔ `AB Casper_HHMI`) and
  placeholder nodes (`SENTINEL`), and some parents have no `parent_name`.

## Design

### Sources and confidence

Every derived heritage value records where it came from:

| Source | Example | Confidence |
|---|---|---|
| `records` | incross because both parent tanks of the producing cross share a strain | highest |
| `strain_ancestry` | AB + Casper because the strain pedigree reaches `AB` and `Casper_HHMI` | inferred |
| `label` | `IC` / `[AB-C]` / `MAR26` parsed from the strain name | inferred |
| `curated` | set by a person | authoritative |

Records win over ancestry, ancestry over label; a disagreement between
`records` and `label` is surfaced as a flag, never silently resolved.

### Data

1. **Complete crossing fetches.** Every `api/v3/tanks/crossings` request asks for
   parent and child `tank_id`, `strain_name`, `strain_name_with_id`, `strain_id`,
   `generation`, `date_of_birth`, plus crossing `date_of_set_up` / `date_of_raise`.
   One-time refetch of the 289 cached crosses.
2. **All-owner sync.** A periodic sync of crossings for all owners (bounded by
   date window) so producing crosses for parent tanks are local.
3. **Child-tank index.** `cross_children(cross_id, tank_id, date_of_birth,
   strain_id, ...)` populated from `tanks.children`, mirroring `cross_parents`.
4. **Strain ancestry cache.** `strain_ancestry(strain_id, ancestor_id,
   ancestor_name, depth, fetched_at)` from the colony-pedigree report, fetched
   on demand per strain, cycle-safe (visited set), refreshed rarely.
5. **Label parse.** Extend `parse_parent_background` to recognize the
   `[<BG>-C( IC)?] <MONYY>` shorthand into `label_background`,
   `label_incross`, `label_cohort_month`.

### Derived per tank

- `producing_cross_id` (via the child index), `incross` (parents share
  `strain_id`), `cohort_month` (from `date_of_birth`), `backgrounds` and
  `mutant_backgrounds` (from parent strains, then strain ancestry), each with
  its `source`, plus `label_*` values and `label_agrees` (true/false/null).

### Heritage view

A page for a tank, cross, or dish that renders two layers as a Mermaid graph
(same approach as the dish lineage page):

1. **Tank lineage** (public API): tank ← producing cross ← parent tanks,
   recursively to a bounded depth, each node showing strain, DOB, generation,
   incross/outcross, and the label check.
2. **Strain ancestry** (internal report, labelled as such): the strain's
   ancestors back to founder backgrounds.

The cached-cross page and dish pages link to it; the background summary there
uses the derived values instead of parsing names only.

## Build order

1. ✅ Complete crossing fetch fields, refetch cached crosses, add all-owner sync
   and the `cross_children` index. Fixes the blank background page.
2. ✅ Derive incross / cohort / background with sources; parse the label
   shorthand; flag disagreements (2a). Follow splits and search older crosses
   (`tank_origins`, 2b). Strain ancestry as a separate inferred layer (2c).
3. ✅ Tank-lineage heritage view (`utils/heritage_graph.py`, server-side SVG,
   tank on the left and ancestors to the right).
4. ✅ Strain-ancestry cache, refreshed nightly for strains that need it.
5. Manual curation (`cross_parent_background_design.md` step 6).
6. ✅ Strain renames (`utils/strain_registry.py`): `strains` holds each
   strain id's current PyRAT name, `strain_names` every name seen (including
   names in cached crossings). Derivation and display use the current name by
   `strain_id`; cached rows keep the name as fetched and are re-parsed when it
   differs; pages show "formerly ...". Refreshed nightly (~9 requests).
7. Tank strain reassignment (a tank's `strain_id` changes, e.g. after
   genotyping): not yet handled; needs a periodic re-fetch of cached crossings.

## Open questions

- Tank strain reassignment (step 7). PyRAT has no change date on strains or
  tanks, so changes are only visible by re-fetching. Candidate: re-fetch all
  cached crossings weekly (~330 requests) and record per-tank strain changes.

- *Danionella* and bracketed line tags (2026-10-06). `WT D. cerebrum [Utah]`,
  `WT D. translucida`, `WT D. dracula`, and tags such as `[Parisian]` on
  `Tg(HuC:H2B-GCaMP6s) [Parisian]` currently yield no background: the
  vocabulary is zebrafish-only (AB, WIK, casper, ...). What `[Utah]` and
  `[Parisian]` denote is not yet known; until it is, these stay unparsed
  rather than guessed. They are most of the parent tanks left without any
  background after records and strain ancestry.

- Window and frequency for the all-owner crossing sync (PyRAT load vs.
  completeness).
- Whether sibling vs. unrelated incrosses matter (tank lineage can tell; strain
  ancestry cannot).
- Whether to request a supported PyRAT API for strain pedigree instead of the
  frontend report.
