---
title: "Crossing Tank Group on Dishes"
summary: "Enter the crossing tank group written on the aquatics sticker when creating a dish, so screening results can later be read per parent group; the value is as-labelled, not verified."
owner: metazebrobot
status: current
kind: design
verified_against: 81de027
---

# Crossing Tank Group on Dishes

Status (2026-10-28): entry and display built; "Group through lineage" below is
planned, not built.

## Problem

A PyRAT crossing can be set up as several crossing tanks (groups), each with
its own parent fish. Screening crosses for a mixed carrier tank (7472) give
very different positive rates per dish, and the rates only mean something per
group. PyRAT's API, as we use it, reports parent counts per crossing, not per
group, and MetaZebrobot recorded only the parent tanks per dish.

Aquatics writes the group on the dish sticker.

## What is built

- The dish model already had `source_group_id` (set from the old desktop app
  on 32 dishes, as `15178-G1`). The web new-dish form now has a "Group #"
  field. Type the number from the sticker's # box, next to the crossing ID;
  it is saved as `<cross>-G<n>`. `1`, `G1` and `19445-G1` all save as
  `19445-G1`. Anything else is kept as typed. Optional.
- The screening page header shows it as "Group 19445-G3". The page doesn't say
  it is from the sticker; the value is still as labelled (see Caveat).
- A dish split from one dish's screening step inherits it. A mixed well plate
  doesn't, because it can hold fish from several groups.

## Caveat

The sticker may not match what was actually set up; that is still being
checked with aquatics. The value is recorded as labelled, not verified.

## Group through lineage (planned)

### Principle

The group belongs to the sticker dish the fish hatched in, not to the
container a fish is in now. A mixed well plate can hold fish from several
groups, so it has no group. Each fish keeps its own.

The group is looked up, never copied onto fish. A sticker found to be wrong
is corrected once, on its dish, and every fish and propagation follows it.

### Resolving a fish's group

1. Take the fish's `origin_dish_id`. For a mixed plate, that is the dish
   chosen in "Fish comes from". For a split plate's own group, it is the
   plate, which inherits its parent's group.
2. If that dish has a group, use it.
3. Otherwise walk `parent_dish_id` upward until a dish has one.
4. If no dish has one, there is no group (shown as "not recorded").

The result carries where it came from:
`{"source_group_id": "19445-G2", "from_dish_id": "19445_2"}`. That covers the
28 dishes split before 2026-10-28 that never copied the group: they resolve
through their parent.

### Where it shows

- **Fish page and the fish API.** Group and the dish it was read from.
  This is not in the consumer contract: Citrus needs only the fish id and
  can look the rest up, so nothing is re-pinned.
- **Propagation events.** The groups of the event's dishes
  (`propagation_event_dishes`). One group shows as `19445-G2`. Pooled groups
  show as `19445-G1 + G3`, never as a single group. This links an adult tank
  to the parent subset that produced it. Which individual larvae became the
  adults isn't recorded, but the parent subset is the part that answers
  "which males carry", e.g. for 7472.
- **Cross page.** Positive rate per group, from the screening allocations of
  each group's dishes, with dishes that have no group counted separately.

### Storage and edits

- Promote `source_group_id` from the dish JSON to a `dishes` column (backfilled
  from the JSON), so per-group queries are plain SQL. The JSON field stays in
  sync, as other promoted fields do.
- Editing a dish's group: a field on the dish page, saved with who changed it,
  when, the old value and a reason, in a small `dish_group_changes` table.
  It edits only that dish. Its derived dishes that inherited the old value
  are listed so they can be changed too, not changed silently.
- Two special values besides `<cross>-G<n>`: `pooled` (aquatics filled the
  dish from several groups) and `unknown` (the sticker can't be read). Both
  stop the upward walk, so a fish from a pooled dish isn't credited to a
  grandparent's group.

### Build order

1. Column, backfill and resolver, with tests for mixed plates, split plates
   and old suffixed dishes.
2. Fish page and fish API.
3. Group editing with history.
4. Propagation events and per-group rates on the cross page.

## Not built yet

- Everything under "Group through lineage".
- A "dim / unsure" screening class (separate decision).
