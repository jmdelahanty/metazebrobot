---
title: "Hand-Entered Cross Parents"
summary: "Record a cross parent PyRAT doesn't list (e.g. an IVF sperm donor named only in the crossing description) as a labelled, hand-entered parent, so the cross's dishes get its constructs; PyRAT refreshes keep it."
owner: metazebrobot
status: current
kind: design
verified_against: 139f76b
---

# Hand-Entered Cross Parents

Status (2026-10-22): built.

## Problem

Cross 19299 is an IVF: PyRAT lists only the egg donor, tank 9243
`Tg(elavl3:GAL4FF; myl7:mTagBFP2)`. The sperm donor, TID 5342
(`UAS:ReaChR-TagRFPt`), is only in the crossing's free-text description. Dishes
whose genotype doesn't parse take their constructs from the cross's parents,
so 19299's dishes miss ReaChR and screening can't name it. Aquatics is
looking at fixing the PyRAT record; until then (and for crosses PyRAT can't
represent) MetaZebrobot needs the parent.

## Decisions (Jeremy, 2026-10-22)

- **Hand-entered parents, labelled as such.** A parent row in
  `cross_parents` with `source = 'manual'`, `confidence = 'entered'`, and in
  `raw_payload` who entered it, when, and why (required). Pages show it as
  "entered by hand", never as PyRAT data. Fields: strain or genotype
  (parsed like a PyRAT strain name; a bare `UAS:ReaChR-TagRFPt` is read as
  `Tg(UAS:ReaChR-TagRFPt)`), optional tank id, role (dam / sire / unknown),
  optional generation.
- **PyRAT stays the source of truth for its own parents.** A PyRAT refresh
  replaces only `source = 'pyrat'` rows; hand-entered rows survive.
  Hand-entered rows use `parent_index` 101+, clear of PyRAT's. If PyRAT later
  lists the same parent, remove the hand-entered one.
- **Dishes follow.** Adding or removing a parent re-derives the constructs
  and screening-step indicators of the cross's dishes. Only dishes whose
  genotype doesn't parse use parent constructs (unchanged rule).

## In the app

`/crosses/{cross_id}/parents`: the cross's parents (PyRAT and hand-entered),
an "Add a parent PyRAT doesn't list" form, and remove for hand-entered rows.
Linked from the new-dish form's Parent Provenance. HTML only; nothing in the
pinned consumer slice.

## Parents on the screening page (2026-10-30)

The screening page (`/screening/{dish_id}`) lists the dish's cross parents
under the parsed constructs: role, tank and rack position, strain,
generation and date of birth, with hand-entered parents marked, and the
PyRAT crossing request text. It reads `cross_parents` and the cached
crossing; nothing is fetched from PyRAT. Prompted by 19445, where checking
which tanks went into a cross meant leaving the screening page.
