---
title: "Cross Parent Strain and Background Design"
summary: "Per-parent strain and background model for PyRAT crosses (cross_parents, background parser)."
owner: metazebrobot
status: current
kind: design
verified_against: 384a366
---

# Cross Parent Strain and Background Design

Status (2026-10-07): steps 1–5 of the implementation sequence are built; step
6 is not, and step 7 is partly built (see below). Missing parent strain data
and tank-level heritage (incross, cohort, producing cross, background from
records and strain ancestry) are owned by
[`tank_heritage_design.md`](tank_heritage_design.md).

## Motivation

MetaZebrobot can now create local dishes from PyRAT crosses that are not
managed by the current MetaZebrobot user. That workflow is valid: a dish's
`cross_id` identifies the PyRAT cross of origin, while `dishes.responsible`
identifies the local person managing that dish day to day.

Those imported crosses expose a second provenance problem. A PyRAT cross may
combine a transgenic parent with another parent that carries an important
wild-type, mutant, or lab background label, for example `WIK Casper_HHMI`.
For downstream analytics, the parent background can matter independently of
the transgene. The system should preserve that information before reducing it
to a single dish `genotype` string.

## Biological Rationale

Zebrafish background is not just display text. Common laboratory strains and
transparent mutant backgrounds can differ in ways that affect interpretation:

- Common wild-type lines such as `AB`, `TU`, and `WIK` have documented genetic
  variation, including SNP/CNV differences.
- Strain differences have been reported for gene expression, locomotion,
  behavior, stress/fear responses, growth, and related phenotypes.
- Transparent backgrounds such as `casper` are not neutral labels. `casper`
  combines pigment mutants, including `nacre/mitfa` and `roy orbison/mpv17`,
  and may need to be treated separately from wild-type background.

Therefore, analytics should be able to ask questions like:

- Are screen-positive rates different when one parent background includes WIK?
- Do pigment mutant backgrounds such as `casper` or `nacre` affect assay yield?
- Are outcomes different for AB x AB versus AB x WIK crosses?
- Does a transgene behave differently depending on the parent background?

## Model Before This Design

Fields that existed before `cross_parents` (all still present):

- `crosses.cross_id`: local cache key for the PyRAT crossing ID.
- `crosses.data`: raw PyRAT crossing payload JSON.
- `crosses.parents`: older/freeform parent metadata column.
- `dishes.cross_id`: the source PyRAT cross for the dish.
- `dishes.genotype`: current dish-level genotype/strain display string.
- `dishes.breeding_parents`: freeform parent location labels captured during
  dish creation.
- `dish_transgenes`: normalized dish-level transgene constructs parsed from
  genotype strings.
- `crossing_transgenic_indicators`: older cross-level transgene indicator
  table.

This was enough to link a dish to a PyRAT cross, but it does not cleanly model
the two parents as structured entities. It also risked mixing distinct concepts:
transgenes, mutant alleles, wild-type strain background, lab line labels, and
parent tank identity.

## Design Principle

Keep these concepts separate:

| Concept | Examples | Notes |
|---|---|---|
| Parent identity | tank ID, tank label, PyRAT parent payload | The raw source record should be preserved. |
| Wild-type/lab background | `AB`, `WIK`, `TU`, `TL`, `EK` | Useful as analytical covariates. |
| Lab/composite line label | `Casper_HHMI`, `WIK Casper_HHMI` | May include background plus facility-specific label. |
| Transgene/construct | `Tg(elavl3:jRGECO1b)` | Already partly handled by strain parser logic. |
| Mutant allele/background | `nacre/mitfa`, `roy/mpv17`, `casper` | Often phenotypically relevant but not a transgene. |
| Dish ownership | `dishes.responsible` | Local manager, not necessarily PyRAT cross owner. |

Do not force a dish to have one exact "strain" when the real provenance is a
parent pair. A dish from `AB transgene x WIK Casper_HHMI` is best represented
as progeny of those parent backgrounds, with a derived summary for filtering.

## Schema (as built)

Created at startup by `_ensure_cross_parent_provenance_schema` in
`api_server.py` (mirrored in `DataManager`), and backfilled from cached
`crosses.data`. One structured parent row per cross parent:

```sql
CREATE TABLE cross_parents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cross_id TEXT NOT NULL,
    parent_index INTEGER NOT NULL,
    role TEXT,                         -- male, female, mixed, unknown (from sex counts)
    tank_id TEXT,
    tank_label TEXT,
    location_display TEXT,
    raw_strain_name TEXT,
    generation TEXT,
    parsed_background_strains TEXT,    -- JSON array: ["WIK"]
    parsed_line_labels TEXT,           -- JSON array: ["Casper_HHMI"]
    parsed_transgenes TEXT,            -- JSON array
    parsed_mutant_alleles TEXT,        -- JSON array: ["casper"]
    source TEXT DEFAULT 'pyrat',
    confidence TEXT DEFAULT 'raw',     -- raw, or inferred when anything parsed
    raw_payload TEXT,                  -- JSON source parent payload
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cross_id) REFERENCES crosses(cross_id),
    UNIQUE(cross_id, parent_index)
);
```

A derived per-cross summary for fast filtering:

```sql
CREATE TABLE cross_background_summaries (
    cross_id TEXT PRIMARY KEY,
    background_summary TEXT,           -- e.g. "WIK + Casper_HHMI + casper"
    background_strains TEXT,           -- JSON array: ["AB", "WIK"]
    line_labels TEXT,                  -- JSON array: ["Casper_HHMI"]
    mutant_backgrounds TEXT,           -- JSON array: ["casper", "nacre"]
    transgenes TEXT,                   -- JSON array of parsed constructs
    has_mixed_background INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cross_id) REFERENCES crosses(cross_id)
);
```

`has_mixed_background` means more than one wild-type background across the
parents (e.g. AB x WIK); a pigment mutant such as casper on one background is
not a mix. Startup backfill corrects rows summarized under the older rule.

The summary table is derived/cache data. The source of truth is the per-parent
records plus the raw PyRAT payload. The same migration also creates
`cross_children` and the heritage tables, which belong to
[`tank_heritage_design.md`](tank_heritage_design.md). The proposed `curated`
flag on summaries was not built; it waits on step 6.

## Parsing and Curation

Parsing is conservative (`parse_parent_background` in
`utils/cross_provenance.py`):

- Preserve `raw_strain_name` exactly.
- Parse clear tokens such as `AB`, `WIK`, `TU`, `TL`, `EK`, `casper`, `nacre`
  (`mitfa`), `roy` (`mpv17`).
- Do not discard facility suffixes such as `_HHMI`.
- Any parsed result is stored as `confidence = 'inferred'`; nothing parsed
  stays `raw`.
- Manual correction to `confidence = 'curated'` is planned (step 6), not built.

Examples:

| Raw parent strain | Parsed background | Parsed line label | Mutant/background flags |
|---|---|---|---|
| `WIK Casper_HHMI` | `WIK` | `Casper_HHMI` | `casper` |
| `Casper_HHMI` | empty/unknown | `Casper_HHMI` | `casper` |
| `AB` | `AB` | empty | empty |
| `Tg(elavl3:jRGECO1b)` | unknown | empty | transgene parsed separately |
| `Tg(gfap:TRPV1-T2A-GFP); WIK` | `WIK` | empty | transgene parsed separately |

The existing strain parser should continue focusing on transgenic constructs.
Background parsing should be a related but separate layer so that `Casper_HHMI`
is not incorrectly treated as a transgene.

## UI Implications

Proposed compact parent block for dish creation from a PyRAT cross:

```text
Cross 18055
Parent 1: Tg(...)                         tank #...
Parent 2: WIK Casper_HHMI                 tank #...
Derived background: WIK + casper background
```

Built: the new-dish form shows a Parent Provenance table (tank, strain,
generation, parsed background per parent), and `/crosses/{cross_id}/provenance/`
shows the per-parent rows and background summary (see
[`web_pages.md`](web_pages.md)). The operator should also be able to:

- Accept raw PyRAT parent metadata as-is.
- Correct parsed background/line labels when the parser is wrong (not built).
- Add parent metadata manually if PyRAT access is incomplete (not built).
- Keep local dish `responsible` separate from PyRAT cross `responsible_fullname`.

## Analytics Implications

Analysis code should prefer structured parent/background fields over parsing
`dishes.genotype` repeatedly. Useful derived features include:

- `has_background_wik`
- `has_background_ab`
- `has_casper_background`
- `has_nacre_or_mitfa_background`
- `has_mixed_background`
- `parent_background_pair`
- `transgene_constructs`

These should be derived from `cross_parents` rather than hand-entered per
dish. Today `GET /acquisition/dishes` exposes the cross summary fields
(`background_summary`, `background_strains`, `line_labels`,
`mutant_backgrounds`, `has_mixed_background`) per dish; the per-feature flags
above are not materialized.

## Implementation Sequence

1. ✅ Preserve raw parent payloads from PyRAT crossings more deliberately in
   `crosses.data`.
2. ✅ Add `cross_parents` with startup migration and backfill from cached
   `crosses.data`.
3. ✅ Add conservative background parser tests for known local strings such as
   `WIK Casper_HHMI`.
4. ✅ Populate `cross_parents` during exact cross lookup and PyRAT crossing sync.
   Some sync paths don't request parent strain fields, so most cached parents
   have no strain; fixed by step 1 of `tank_heritage_design.md`.
5. ✅ Display parent background on the new-dish form and the cross
   provenance page.
6. Add manual curation UI only after the raw/parsed model is stable.
7. Add analytics/export fields derived from `cross_parents`. Partly built:
   `GET /acquisition/dishes` carries the cross summary fields.

## Open Questions

- Does PyRAT reliably identify parent sex/role, or only a parent tank list?
- Are facility labels like `Casper_HHMI` stable enough to treat as controlled
  vocabulary, or should they remain free text with aliases?
- Should cross-level background summaries be manually curated once per cross,
  or should each dish be allowed to override inherited background context?
- How should derived dishes from mixed parent crosses display background:
  parent-pair summary, inferred offspring background, or both?
