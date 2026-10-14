---
title: "Linking Screening Indicators to Constructs"
summary: "Proposal: screening steps point at a dish's transgene constructs instead of free text, the catalog records how each fluorescent readout relates to its transgene, and the API and Citrus snapshot serve the result."
owner: metazebrobot
status: current
kind: design
verified_against: 96f00f5
---

# Linking Screening Indicators to Constructs

Status (2026-10-14): proposal; nothing below is built. Goal: a fish's screening
result should say which transgene it carries, not just which color it
showed. Users get that from the API, and Citrus can show it and seal it at
recording time. Builds on
[fish origin and location](fish_origin_and_location_design.md), which defines
how a fish inherits its origin dish's screening results.

## What exists (checked against prod, 2026-10-14)

- **Parsed constructs per dish.** `dish_transgenes` holds the constructs that
  `parse_genotype` finds in a dish's genotype ([strain parser edge
  cases](strain_parser_edge_cases.md)). Each row has a promoter, reporter,
  fluorophore, excitation/emission, `construct_role`, and an optional
  `catalog_id`. Thirteen distinct constructs occur. Example, dish 18300_2:
  `Tg(her4.1:PMCA2-mCherry)` (mCherry, red) and `Tg(elavl3:jGCaMP8f)` (GCaMP,
  green).
- **A construct catalog.** `construct_catalog` + `construct_aliases` has seven
  entries. 57 dish construct rows match one (`alias_exact`); 65 match none.
  PMCA2-mCherry, jGCaMP8f, GCaMP7ff, b-ARK and iGluSnFR3 are missing. Roles are
  guessed from names: PMCA2-mCherry is classed `fluorescent_reporter` because
  it ends in mCherry, though PMCA2 is an effector (a calcium pump).
- **Free-text screening indicators.** `screening_steps.indicators_screened` is
  a JSON list of strings typed or picked on the form: "mCherry",
  "pmca2-mcherry", "Pigment, elavl3:jRGECO1b" (two indicators in one string),
  "Both/Final Brightness". That's 42 steps on 39 dishes. Nothing ties an
  indicator to a construct.
- **No construct API.** No JSON endpoint returns a dish's constructs, and the
  Citrus snapshot (`GET /dishes/{dish_id}/citrus-snapshot`) has no construct
  or screening fields.
- **Unparsed strains.** A PyRAT strain such as `EXPERIMENTAL` (cross 19234)
  parses to no constructs, so its mCherry screen links to nothing.

## How strongly a readout implies its transgene

Seeing a fluorophore means different things depending on how the construct is
built. The catalog records this as `readout_link`:

| `readout_link` | Construct shape | A positive screen means | Example |
|---|---|---|---|
| `intrinsic` | The transgene product is the fluorescent molecule | Expressed, in the expressing cells | jGCaMP8f, jRGECO1b, GRAB sensors |
| `fusion` | Fluorophore fused to the protein of interest | Expressed, where the fusion localizes | PMCA2-mCherry, CoChR-eGFP |
| `co_expressed` | Same transcript, separate protein (2A, IRES) | Expressed in the same cells | TRPV1-T2A-GFP |
| `cis_marker` | Separate marker cassette on the same construct (e.g. `cmlc2:EGFP`) | Carries the construct; says nothing about target expression | heart or eye markers |
| `none` | No fluorescent readout | Can't be screened by fluorescence | b-ARK (to confirm) |

A construct on a different transgene than its marker has no link at all. The
marker only co-segregates by chance, so it is never recorded as a readout for
that construct.

## Proposal

### 1. Curate the catalog

Add the missing constructs and a `readout_link` column to the catalog. Correct
roles to the set `sensor | effector | reporter | marker`. The biology is
Jeremy's to confirm. Proposed starting values:

| Construct | Role | Readout | `readout_link` | Confirm |
|---|---|---|---|---|
| PMCA2-mCherry | effector | mCherry, red | fusion | |
| jGCaMP8f, GCaMP7ff, GCaMP6s | sensor | green | intrinsic | |
| jRGECO1b | sensor | red | intrinsic | |
| GRAB-5HT, GRABATP1.0 | sensor | green (cpGFP) | intrinsic | |
| iGluSnFR3 | sensor | green | intrinsic | |
| CaMPARI | sensor | green→red | intrinsic | |
| TRPV1-T2A-GFP | effector | GFP, green | co_expressed | |
| CoChR-eGFP | effector | eGFP, green | fusion | |
| b-ARK | effector? | ? | ? | yes: steps screen "b-ark", so it has some readout |

Construct identity in the catalog is the reporter or effector. The promoter
stays per dish construct (`Tg(gfap:jRGECO1b)` and `Tg(elavl3:jRGECO1b)` share a
catalog entry but differ in where they express).

### 2. Screening steps point at constructs

A new table, `screening_step_indicators`, records one row per indicator per
step. Each row has:
- the step (`dish_id`, `screening_datetime`);
- `kind`: `construct` | `pigment` | `other`;
- the matched dish construct (`dish_transgenes` row) and `catalog_id`, when
  `kind` is `construct`;
- the original text (`raw_text`), which is always kept.

The screening form offers the dish's constructs, showing each one's color and
`readout_link`, plus pigment. Free text stays possible and lands as `other`,
flagged for review.

**Backfill:** match the 42 existing steps' strings against dish constructs and
aliases. Combined strings are split ("Pigment, elavl3:jRGECO1b" becomes
pigment + jRGECO1b). The result is a review report before anything is written,
because some old strings ("Both/Final Brightness") won't match.

**Ambiguity is explicit.** If a dish carries two constructs with the same
screen color, a step that names only the color (e.g. "red") links to neither
and is flagged. It doesn't guess.

### 3. Results per construct, inherited by fish

With step 2, a dish's screening history becomes a set of calls per construct:
"carries Tg(her4.1:PMCA2-mCherry): positive, 4 dpf, 2026-05-26 (dish
18300_2), via fusion
readout". Fish inherit these from their origin dish
([inheritance rules](fish_origin_and_location_design.md#screening-results-are-inherited)),
so each tracked fish has one call per construct with its source and readout
link. Pigment calls work the same way.

### 4. Unparsed strains get constructs entered once

For crosses whose strain parses to nothing (`EXPERIMENTAL`), constructs and
their readouts are entered once per cross. New dishes from that cross then
carry them. Whether PyRAT's tank or strain records hold transgene data that
could fill this automatically is to check first (deferred item in
[user-scoped workflow](user_scoped_workflow_design.md#deferred)).

### 5. API and Citrus

- `GET /constructs`: the catalog.
- `GET /dishes/{dish_id}` gains `constructs[]` (promoter, reporter, catalog
  entry, color, `readout_link`) and per-construct `screening_calls[]`.
- `GET /fish/{fish_id}` and `GET /dishes/{dish_id}/fish` gain inherited
  `screening_calls[]`, each with its source step and whether it was
  inherited or observed on the fish.
- `GET /dishes/{dish_id}/citrus-snapshot` gains `constructs[]` and
  `screening_calls[]`. Citrus can show them per arena at runtime (e.g. "Z1:
  PMCA2-mCherry +, fusion") and seal them in the recording.

Identifiers and precedence:

- **Catalog key:** each catalog entry is referenced by its `normalized_name`
  (unique today, e.g. `pmca2mcherry`), not the integer `id`, so the key
  survives a rebuilt database.
- **Dish construct key:** a call names its dish construct by the canonical
  construct string (e.g. `Tg(her4.1:PMCA2-mCherry)`), which is unique per dish
  (`dish_transgenes` has `UNIQUE(dish_id, construct)`). The same reporter
  under two promoters stays two constructs.
- **Precedence:** for one fish and one construct, an observed call on the fish
  wins over the inherited one. Both are served, with the observed call marked
  current and the inherited call kept with its source, so a disagreement is
  visible rather than hidden. Dish-level calls are never rewritten by fish
  observations (see open questions).
- **Vocabulary:** `readout_link`, call `result` and `kind` values are closed
  enums pinned with the endpoint version. Consumers such as Citrus seal them
  verbatim.

All of these are additive fields on pinned endpoints: a re-pin through
agent-contracts, coordinated with the Citrus subject identity v4 contract so
the field names land once.

## Order

1. Catalog curation + `readout_link` (Jeremy confirms the table above).
2. `screening_step_indicators`, form change, backfill with review report.
3. Construct and screening fields in the API and snapshot; re-pin.
4. Fish-level inherited calls, after the origin/location work.
5. Per-cross constructs for unparsed strains.

Steps 1-3 don't depend on the origin/location work. Step 4 does.

## Open questions

- Should a negative call on a `cis_marker` construct be reported as "does not
  carry" or only "marker not seen"? Markers can be silenced.
- Screening brightness grades ("Final Brightness"): a per-call grade field, or
  out of scope?
- Do promoters need their own catalog (expected tissue, e.g. her4.1 = radial
  glia), or is the free promoter string enough for now?
