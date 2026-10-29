---
title: "Derived Dish Numbering"
summary: "Dishes and well plates made from another dish take the cross's next dish number (19445_7) instead of a suffix like _pos1 or _plate1; the container, parent dish and result are fields on the dish and are shown in the dish list."
owner: metazebrobot
status: current
kind: design
verified_against: 53e6bbc
---

# Derived Dish Numbering

Status (2026-10-28): built.

## Why

Derived dishes used to be named after their parent with a suffix for their
result or container: `19445_1_pos1`, `19329_2_neg1`, `19445_1_plate1`. The
names got long and confusing, and they could be wrong. A plate called
`_plate1` of dish 1 may hold fish from dishes 1, 2 and 3, and a `_pos` name
says nothing once a fish is re-checked.

The dish already records everything the suffix encoded:

| Field | Example |
|---|---|
| `container_type` | `well_plate`, `petri_dish` |
| `parent_dish_id` | `19445_1` |
| `dish_population_type` / `source_screening_bucket` | `positive_screened`, `manual_transfer` |
| `source_screening_datetime` | the step it was split from |
| per-fish origin and screening calls | each fish on a plate |

## Rule

Any dish made from another dish ("Create Derived Dish", or "New well plate
from this dish") is the cross's next dish number: one more than the highest
plain number `<cross>_<n>` the cross has. Gaps are left alone. Old suffixed
dishes don't count toward the numbering and keep their names.

The workflow this supports: first create all the cross's dishes from the
stickers with their counts (`19445_1`…`19445_4`), then derived dishes and
plates continue the numbering (`19445_5`, …).

A dish with no cross falls back to `<parent>_derived<n>`.

## Groups

A dish split from one screening step inherits the parent's `source_group_id`
(crossing tank group). A mixed plate (`manual_transfer`) doesn't, because it
can take fish from any active dish of the cross.

## Display

The screening dish list shows each dish's container and, for a derived dish,
"from <parent>", since the name no longer says so.

## Not changed

- Existing dishes keep their names. Renaming would break fish ids' dish
  references, image folders and anything Citrus or Palette stored.
- Mixed plates still take fish only from dishes of the same cross.
