---
title: "Linking Screening Indicators to Constructs"
summary: "Proposal: screening steps point at a dish's transgene constructs instead of free text, the catalog records how each fluorescent readout relates to its transgene, and the API and Citrus snapshot serve the result."
owner: metazebrobot
status: current
kind: design
verified_against: 64f4a6c
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
| `co_expressed` | Same transcript, separate protein (2A, IRES) | Expressed in the same cells | TRPV1-T2A-GFP, iβARK-p2A-mCherry |
| `cis_marker` | Separate marker cassette on the same construct (e.g. `cmlc2:EGFP`) | Carries the construct; says nothing about target expression | heart or eye markers |
| `none` | No fluorescent readout | Can't be screened by fluorescence | none in use today |

A construct on a different transgene than its marker has no link at all. The
marker only co-segregates by chance, so it is never recorded as a readout for
that construct.

## Proposal

### 1. Curate the catalog

Replace `construct_catalog` with a table whose fields are exact: closed value
sets enforced by `CHECK` constraints, and fields required by role and readout.
SQLite can't add constraints to an existing table, so this is a new table
migrated from the current seven entries. Aliases (`construct_aliases`) carry
over. The same value sets are `Literal` types in the API models, so they appear
in the pinned OpenAPI schema and change only by a deliberate re-pin.

| Field | Type / values | Required when |
|---|---|---|
| `key` | text, unique: today's `normalized_name` (e.g. `bark`) | always |
| `canonical_name` | text (e.g. `iβARK-P2A-mCherry`) | always |
| `role` | `sensor` \| `effector` \| `reporter` \| `marker` | always |
| `payload` | text: the protein of interest (e.g. `GRK2 RGS fragment`, `hPMCA2w/b`) | role ≠ reporter |
| `sensor_target` | text (e.g. `calcium`, `serotonin`, `ATP`) | role = sensor |
| `mechanism` | short text: what an effector does | optional for effectors |
| `readout_fluorophore` | text: the fluorescent protein (e.g. `mCherry`, `cpGFP`) | readout_link ≠ none |
| `readout_link` | `intrinsic` \| `fusion` \| `co_expressed` \| `cis_marker` \| `none` | always |
| `linker` | `P2A` \| `T2A` \| `E2A` \| `F2A` \| `IRES` | readout_link = co_expressed (null otherwise) |
| `fusion_terminus` | `N` \| `C` \| `unknown`: which end of the payload carries the fluorophore | readout_link = fusion (null otherwise) |
| `marker_promoter` | text (e.g. `cmlc2`) | readout_link = cis_marker (null otherwise) |
| `variant_of` | catalog key: e.g. an inactive control's active parent | optional |
| `excitation_nm`, `emission_nm` | integers | readout_link ≠ none |
| `screen_color` | `green` \| `red` \| `far_red` \| `blue` \| `yellow` \| `photoconvertible` | readout_link ≠ none |
| `notes` | text | optional |

`fusion_terminus` exists so the orientation is answered or explicitly
`unknown`, never inferred from the name: the published CalEx construct is
mCherry-hPMCA2w/b (N-terminal), while the lab's line is named "PMCA2-mCherry".

Proposed values; the biology is Jeremy's to confirm. External ids (DOIs,
Addgene, ZFIN, FPbase) go in `construct_references` (next section).

| Key | Role | Payload / target | Readout | `readout_link` | Detail | Status |
|---|---|---|---|---|---|---|
| `bark` | effector | GRK2 (βARK1) RGS fragment; attenuates Gq GPCR signaling | mCherry, red | co_expressed | `linker` P2A; HA-FLAG N-terminal tags | **confirmed from plasmid B0078** (Tol2, zebrafish gfap promoter) and Nagai et al. 2021 |
| `bark_d110a` | effector (inactive control) | as above, D→A at RGS-fragment codon 66 (consistent with D110A) | mCherry, red | co_expressed | `linker` P2A; `variant_of` `bark` | **confirmed from plasmid B0077**: one base differs from B0078 |
| `pmca2mcherry` | effector | hPMCA2w/b; Ca²⁺ extrusion ("CalEx") | mCherry, red | fusion | `fusion_terminus` to determine | published CalEx is N-terminal; lab line orientation unknown |
| `jgcamp8f`, `gcamp7ff`, `gcamp6s` | sensor | calcium | green | intrinsic | | to confirm ("GCaMP7ff" naming to check) |
| `jrgeco1b` | sensor | calcium | red | intrinsic | | to confirm |
| `grab5ht`, `grabatp10` | sensor | serotonin, ATP | green (cpGFP) | intrinsic | | to confirm |
| `iglusnfr3` | sensor | glutamate | green | intrinsic | | to confirm |
| `campari` | sensor | activity integrator | green→red | intrinsic | `screen_color` photoconvertible | to confirm |
| `trpv1t2agfp` | effector | TRPV1; capsaicin-gated cation channel | GFP, green | co_expressed | `linker` T2A | to confirm |
| `cochregfp` | effector | CoChR; blue-light-gated cation channel | eGFP, green | fusion | `fusion_terminus` C (from name; to confirm) | to confirm |

An inactive control such as `bark_d110a` screens exactly like its active
parent, so screening can't tell them apart. Only line identity (strain or
plasmid records) can, which is why it's a separate catalog entry.

Construct identity in the catalog is the reporter or effector. The promoter
stays per dish construct (`Tg(gfap:jRGECO1b)` and `Tg(elavl3:jRGECO1b)` share a
catalog entry but differ in where they express).

### References and external identifiers

Each catalog entry can carry where its facts come from, owned elsewhere and
linked here (one owner per fact):

- **Papers:** DOIs (e.g. iβARK: `10.1016/j.neuron.2021.05.023`, Nagai et al.
  2021, *Neuron* 109:2256). The DOI is the stable key. A lab Zotero group
  library can own the bibliography, and the catalog stores the DOI plus the
  Zotero item key so the app can link to it. Zotero items can be tagged with
  the catalog key so the link works both ways.
- **Plasmids:** Addgene ids (iβARK-p2A-mCherry: #117688), or an internal
  plasmid id for lab-made constructs.
- **Zebrafish constructs and lines:** ZFIN is the authority for zebrafish
  transgene nomenclature and records transgenic constructs and lines with
  stable ids (`ZDB-TGCONSTRCT-…`, `ZDB-ALT-…`). Lab-made lines often aren't in
  ZFIN; the field stays empty rather than guessed.
- **Fluorophores:** FPbase for spectra, which could fill
  `excitation_nm`/`emission_nm` instead of hand entry.

Stored as a small `construct_references` table (catalog key, kind: `doi` |
`zotero` | `addgene` | `zfin` | `fpbase` | `internal`, value, note), served
with the catalog. Lookups start manual. Assisted matching against ZFIN or
FPbase (both offer public data) is a later step, and results stay proposals
for review.

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
