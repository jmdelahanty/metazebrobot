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

Full snapshot with match details and lab questions:
[construct data inventory, 2026-10-14](construct_data_inventory_2026-10-14.md).

## Proposal

### 1. Curate the catalog

Status: built (2026-10-14). `config/construct_catalog.json` owns the entries.
At startup it loads the `constructs`, `construct_key_aliases` and
`construct_references` tables (the CHECK constraints below) and refreshes every
dish construct's `construct_key`. On prod all 125 dish construct rows match an
entry (68 were unmatched before), and no dish or fish revision changes.
Read-only `GET /constructs` and `GET /constructs/{key}` serve the catalog;
they're not in the pinned consumer slice yet. As built, keys are
`[a-z0-9]` only (`barkd110a`, `jgcamp8ph2b`, `pmca2mcherryzf`). Spectra are
optional, because several sensors have no sourced peaks. `family` is kept as
an optional display field. The legacy `construct_catalog` table is a projection
of the same file for older code paths.

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
| `variant_of` | catalog key: e.g. an inactive control's active parent, or a nuclear version's base sensor | optional |
| `localization` | `cytosolic` \| `nuclear` \| `soma` \| `membrane` \| `synaptic` \| `unknown` | role = sensor (default `cytosolic`) |
| `excitation_nm`, `emission_nm` | integers; null when no source gives them | optional |
| `screen_color` | `green` \| `red` \| `far_red` \| `blue` \| `yellow` \| `photoconvertible` | readout_link ≠ none |
| `notes` | text | optional |

`fusion_terminus` exists so the orientation is answered or explicitly
`unknown`, never inferred from the name: the published CalEx construct is
mCherry-hPMCA2w/b (N-terminal), while the lab's line is named "PMCA2-mCherry".

Proposed values, assembled 2026-10-14 from the lab's plasmid files and from
research whose identifiers were each re-checked against the source (DOIs via
Crossref, Addgene ids via Addgene's pages, ZFIN ids via ZFIN's
`features.txt` download). The biology is Jeremy's to confirm row by row; "?"
marks a value no opened source gave.

| Key | Role | Payload / target | Readout | `readout_link` | Ex/em nm (source) | Open |
|---|---|---|---|---|---|---|
| `bark` | effector | bovine GRK2 (βARK1) RGS fragment; attenuates Gq GPCR signaling | mCherry | co_expressed, P2A; HA-FLAG N-terminal | 587/610 (FPbase mCherry) | |
| `barkd110a` | effector, `variant_of` `bark` | same, D110A (inactive) | mCherry | co_expressed, P2A | 587/610 | |
| `pmca2mcherry` | effector | hPMCA2w/b (ATP2B2); Ca²⁺ extrusion ("CalEx") | mCherry | fusion, `fusion_terminus` ? | 587/610 | orientation (plasmid requested); which PyRAT PMCA2 names are distinct constructs |
| `trpv1t2agfp` | effector | rat TRPV1; capsaicin-gated cation channel | EGFP | co_expressed, T2A | 488/507 (FPbase EGFP) | |
| `cochregfp` | effector | CoChR; blue-light-gated cation channel | EGFP | fusion, C | 488/507 | |
| `jgcamp8f` | sensor | calcium | cpGFP | intrinsic | 492/512 (Helassa et al. 2023, secondary) | |
| `jgcamp8p` (aliases `GCaMP7ff`, `GCaMP7FF`, `GCaMP8p`) | sensor | calcium | cpGFP (GCaMP family; to confirm) | intrinsic | ? | unpublished lab sensor; H2B (nuclear) lines are `variant_of` entries |
| `gcamp6s` | sensor | calcium | cpGFP | intrinsic | 497/515 (secondary, from Chen et al. 2013) | |
| `jrgeco1b` | sensor | calcium | cpmApple | intrinsic | ? | |
| `grab5ht` | sensor | serotonin | cpGFP in 5-HT2C receptor | intrinsic | ? | version (see ZFIN ct876Tg note) |
| `grabatp10` | sensor | extracellular ATP | cpEGFP in P2Y1 receptor | intrinsic | ? | |
| `iglusnfr3` | sensor | glutamate | cp superfolder Venus/GFP | intrinsic | ? | variant (v857 or v82) and membrane anchor |
| `campari` / `campari2` | sensor | Ca²⁺ × light activity integrator | mEos2-derived, photoconvertible | intrinsic | CaMPARI 498/514 → 560/576; CaMPARI2 502/516 → 562/577 (Moeyaert et al. 2018, Table 1) | which one the lab used; two entries |

References per entry (go into `construct_references`):

| Key | Papers (DOI) | Addgene | ZFIN |
|---|---|---|---|
| `bark`, `barkd110a` | Nagai et al. 2021 Neuron, 10.1016/j.neuron.2021.05.023 | #117691 GfaABC1D BARK p2A mCherry, #117689 CMV; controls #117692, #117690 (D110A), #117688 (R106A) | none (lab plasmids B0078, B0077) |
| `pmca2mcherry` | Yu et al. 2018 Neuron, 10.1016/j.neuron.2018.08.015 (CalEx); Chen, Duque et al. 2025 Science, 10.1126/science.adq5233 (zebrafish `Tg(gfap:hPMCA2-mCherry)`) | #111568 pZac2.1-GfaABC1D-mCherry-hPMCA2w/b ("mCherry tag, N terminal") | none |
| `trpv1t2agfp` | Chen et al. 2015 Nat Methods, 10.1038/nmeth.3691 (tool); Duque, Chen et al. 2025 Neuron, 10.1016/j.neuron.2024.11.011 (line) | none | ZDB-TGCONSTRCT-260122-1 `Tg(gfap:Rno.Trpv1-2A-EGFP)`, allele jf64Tg (ZDB-ALT-260122-1) |
| `cochregfp` | Klapoetke et al. 2014 Nat Methods, 10.1038/nmeth.2836 (tool); Mu et al. 2019 Cell, 10.1016/j.cell.2019.05.050 (line) | #124233 pTol1-UAS:CoChR-tdTomato (zebrafish vector, tdTomato, not an exact match) | ZDB-TGCONSTRCT-200206-4 `Tg(gfap:CoChR-EGFP)`, jf29Tg (ZDB-ALT-200206-8); no her4.1 line |
| `jgcamp8f` | Zhang et al. 2023 Nature, 10.1038/s41586-023-05828-9 | #162373 pGP-CMV-jGCaMP8f, #162376 pGP-AAV-syn-jGCaMP8f-WPRE | ZDB-TGCONSTRCT-260409-6 `Tg(elavl3:GCaMP8f)` (no allele; not in `features.txt`, unverified) |
| `jgcamp8p` | none yet (in preparation) | none | none |
| `gcamp6s` | Chen et al. 2013 Nature, 10.1038/nature12354 | #59531 Tol2-elavl3-GCaMP6s | ZDB-TGCONSTRCT-141023-2 `Tg(elavl3:GCaMP6s)`, jf4Tg (ZDB-ALT-141023-1) |
| `jrgeco1b` | Dana et al. 2016 eLife, 10.7554/eLife.12727 | #100857 pAAV.Syn.NES-jRGECO1b | `Tg(elavl3:jRGECO1b)` jf17Tg (ZDB-ALT-200206-5); `Tg(gfap:jRGECO1b)` jf33Tg (ZDB-ALT-200206-6); no her4.1 line |
| `grab5ht` | Wan et al. 2021 Nat Neurosci, 10.1038/s41593-021-00823-7; Deng et al. 2024 Nat Methods, 10.1038/s41592-024-02188-8 | #140552 GRAB_5-HT1.0, #208717 GRAB_g5-HT3.0 | ZDB-TGCONSTRCT-260211-5 `Tg(elavl3:GRABht-4.0)`, ct876Tg (ZDB-ALT-231109-10); ZFIN notes it was published as "GRAB5-HT2.0" |
| `grabatp10` | Wu et al. 2022 Neuron, 10.1016/j.neuron.2021.11.027 | #167577 pAAV-hsyn-GRAB_ATP1.0 | none neuronal (only liver `Tg(fabp10a:GRABATP,…)`) |
| `iglusnfr3` | Aggarwal et al. 2023 Nat Methods, 10.1038/s41592-023-01863-6 | #175186 pRSET iGluSnFR3 v857, #178329 hSyn v857.PDGFR | none |
| `campari`, `campari2` | Fosque et al. 2015 Science, 10.1126/science.1260922; Moeyaert et al. 2018 Nat Commun, 10.1038/s41467-018-06935-2 | #137185 pTol2-HuC(elavl3)-CaMPARI2 | `Tg(elavl3:CaMPARI)` jf9Tg (ZDB-ALT-150403-1); `Tg(elavl3:CaMPARI2)` jf92Tg (ZDB-ALT-180410-5) |

**GCaMP7ff is jGCaMP8p.** It isn't jGCaMP7f, as name-based research had
guessed. The lab asked aquatics in October 2026 to rename "GCaMP7ff" to
jGCaMP8p, the name it will be published under. PyRAT can't rename closed tanks,
so only active tanks changed:

- strain 1485 was renamed in place; MetaZebrobot's `strain_names` recorded
  the old name (last seen 2026-10-08) and the new one (from 2026-10-09);
- tank 8937 moved to a new strain, 1705 `Tg(elavl3:jGCaMP8p)`;
- about ten older strains (68 `Tg(elavl3:GCaMP7ff)`, nuclear `H2B-` lines,
  `gfap:` and `tph2:` lines) and dishes 18055_* keep "GCaMP7ff" permanently.

The old spellings stay as catalog aliases for good. This is the general rule:
an alias is how a historical name keeps resolving after a rename, not a typo
to clean up.

Lines in the lab without a ZFIN record (her4.1 jRGECO1b and CoChR, any
PMCA2, b-ARK, elavl3 GRAB-ATP, iGluSnFR3) are presumably unpublished lab
lines. A ZFIN id on a catalog entry describes the published line of that
construct, not necessarily the lab's tank; matching a tank to an allele is a
separate, per-strain fact.

FPbase has no entries for these sensors, so sensor spectra come from papers.
Unknown values stay null rather than being filled from a sibling variant.

An inactive control such as `barkd110a` screens exactly like its active
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
- **Plasmids:** Addgene ids, or an internal plasmid id for lab-made
  constructs. Take ids from Addgene's own pages, not from papers: Nagai et al.
  2021's methods list #117688 as active iβARK, but Addgene's #117688 is the
  R106A control. The active plasmids are #117689 (CMV) and #117691 (GfaABC1D,
  astrocyte promoter); D110A controls are #117690 and #117692.
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

Status: built (2026-10-14). As built, the table is `screening_step_indicators`
with `match_rule`, `match_confidence` (`high` | `medium` | `low` | `none`) and
`note`. Rows are derived on every dish save from the step's text, the dish
constructs and the catalog, so the raw text stays the record. Matching rules
are in `utils/indicator_match.py`. Existing steps are matched by
`scripts/backfill_screening_indicators.py` (dry run by default). The review
report is [screening indicator backfill](screening_indicator_backfill_2026-10-14.md):
all 42 steps match, with no unmatched or ambiguous tokens. The form still takes
text and offers the dish's constructs as suggestions.

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

Status: built (2026-10-15, `data/screening_calls.py`). `GET /fish/{fish_id}/screening`
and `GET /dishes/{dish_id}/screening-calls` serve the calls; they're not in
the pinned consumer slice yet. As built:

- **What establishes a call:**
  - a step's construct indicators, with the remainder all in one classified
    bucket (`remained_in_dish_as_…`);
  - a dish split from its parent's step (`moved_out_of_parent_as_…`),
    including `pigmented` for `_pig` dishes;
  - legacy steps with no allocations but a `number_kept` > 0
    (`legacy_number_kept`, capped at medium).
- **Unknown, never guessed:** an unclassified remainder (`remaining_in_parent`)
  and steps with neither allocations nor a kept count.
- **Confidence:** a call's confidence is its indicator match confidence, so
  "mCherry" matched by readout colour is medium. A later step confirming the
  same result keeps the stronger confidence; a different result replaces it.
- **Transfers in:** a dish that received fish from other dishes keeps only
  the calls every contributor agrees on (status `partial_mixed_sources` if any
  were dropped). The 19234_3 plate therefore has no dish-level call.
- **Fish:** a fish inherits its origin dish's calls from steps before it left
  that dish (its first unit outside the origin; occupancy UTC times are
  converted to lab time). Example: Z1 is `Tg(gfap:PMCA2-mCherry-zf)` positive
  (medium, 2026-10-05, 19234_1); Z10 is negative.
- **Fish-level observations** (built 2026-10-15, `data/fish_observations.py`):
  a result recorded on one fish (`POST /fish/{fish_id}/observations`, or by
  choosing a result when placing a fish in a plate) replaces the inherited
  call for that construct. These calls have `source: observed`, confidence
  high and basis `observed_on_fish`. The latest observation per construct
  wins, and all of them appear on the timeline.
- **Mixed plates:** "New well plate from this dish" on the screening page
  creates an empty plate (`<dish>_plate<n>`, population `manual_transfer`).
  Each placed fish names its source dish and an optional result. With a
  result, the fish is booked into the source's latest screening step (as an
  allocation to the plate) and the result is recorded on the fish. Without a
  result it moves by a one-fish transfer. Its origin is the source dish.
- **Not built:** pigment results for fish that stayed after a pigment step.

With step 2, a dish's screening history becomes a set of calls per construct:
"carries Tg(her4.1:PMCA2-mCherry): positive, 4 dpf, 2026-05-26 (dish
18300_2), via fusion
readout". Fish inherit these from their origin dish
([inheritance rules](fish_origin_and_location_design.md#screening-results-are-inherited)),
so each tracked fish has one call per construct with its source and readout
link. Pigment calls work the same way.

### 4. Unparsed strains take constructs from the parent tanks

Status: built (2026-10-14, `DataManager._parent_tank_transgenes`). Applied at
service start to dishes with no construct rows; on prod that is the three
19234 dishes.

When a cross's own strain parses to no constructs (PyRAT's `EXPERIMENTAL`,
strain 564), a dish's candidate constructs come from its **parent tanks'
strains** instead. `cross_parents.parsed_transgenes` already holds them.
Example, cross 19234:

- the female parent is tank 7472, `Tg(gfap:PMCA2-mCherry-zf)`, F2;
- the male parent is tank 8130, `Casper_HHMI [AB-C] DEC25`, with no transgenes;
- so the dishes' candidate construct is `Tg(gfap:PMCA2-mCherry-zf)`.

These rows are stored with `source_type = parent_tank` and the tank id, so
they're distinguishable from constructs parsed from the cross's own strain.

Parent-derived constructs mean "may carry", not "carries". A cross of a
transgenic carrier with a non-transgenic partner yields a mix, which is what
the screen sorts out. So they become the dish's **screenable** constructs: they
appear on the screening form, and a dish's calls for them come only from its
screening steps. In the 19234 example, 19234_1 is PMCA2-mCherry positive and
19234_2 negative, both from 2026-10-05.

Manual entry per cross stays as the fallback for cases the parent strains
don't cover: a parent strain that is itself unparsed, or a construct that isn't
named in any strain.

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
5. Parent-tank constructs for unparsed strains (manual entry as fallback).

Steps 1-3 don't depend on the origin/location work. Step 4 does.

## Decisions

- **Legacy "Both/Final Brightness"** (2026-10-14, Jeremy): the four steps on
  15178_1/2 and 15180_1/2 (2025, inactive dishes) are read as positive for
  both dish constructs if bright. Each backfilled call carries
  `match_confidence = low` and a note saying it's an interpretation of an
  early, unclear label. It isn't a recorded call.
- **No brightness grade:** brightness was never labelled meaningfully, so
  screening records positive/negative per construct only.

## Open questions

- Should a negative call on a `cis_marker` construct be reported as "does not
  carry" or only "marker not seen"? Markers can be silenced.
- Do promoters need their own catalog (expected tissue, e.g. her4.1 = radial
  glia), or is the free promoter string enough for now?
