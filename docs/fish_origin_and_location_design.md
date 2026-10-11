---
title: "Fish Origin and Location"
summary: "Proposal: give each tracked fish a fixed origin (the dish it came from, whose screening results it inherits) and a changing location (container and well), so mixed plates and post-session isolation keep provenance."
owner: metazebrobot
status: current
kind: design
verified_against: 62b2b9b
---

# Fish Origin and Location

Status (2026-10-11): proposal; nothing below is built. Inputs: the 12-well
plate set up on 2026-10-09 (dish 19234_3) and Citrus's subject identity v4
proposal (citrus repo, `docs/subject_identity_v4_design_2026-10-10.md`).

## The lifecycle this models

For larval zebrafish:

1. Parent tanks are crossed in PyRAT
   ([tank heritage](tank_heritage_design.md)).
2. The cross produces larvae, which go into **primary dishes**.
3. Dishes are **screened**. Each step's allocations either move fish into
   **derived dishes** (e.g. `18300_2_pos1`) or leave them in the parent
   ([counts and screening](fish_count_and_screening_accuracy.md)). Leaving
   negatives in the parent and moving positives out is common.
4. Individual fish are registered from a dish when someone needs to tell them
   apart. They may then be placed in wells, at setup or later by a downstream
   experiment (e.g. isolating a fish after a recording).

Steps 1-3 are about **groups**; step 4 is about **individuals**. Every fish
should still carry its own screening result, inherited from its group.

## Problem

A dish stands for two things at once:

- a **group**: one cross, one fertilization date, one screening history;
- a **container**: the dish or plate the fish physically sit in.

Usually they coincide. The 2026-10-09 plate broke that. Dish 19234_3 is one
container holding 5 mCherry+ fish from 19234_1 and 5 mCherry- fish from 19234_2.
It was recorded as a `manual_transfer` derived from 19234_1 only. All ten fish
have `dish_id = 19234_3`, so the record no longer says which group each fish
belongs to. The source and screen result live only in each fish's `notes`.

Moving a fish is also two unconnected operations today: a dish transfer moves
the count, and `POST /fish/{fish_id}/assign` moves the individual. The assign
doesn't change the fish's `dish_id` or check that the unit belongs to its dish
([#3](https://github.com/jmdelahanty/metazebrobot/issues/3)).

## Proposal

Each tracked fish gets two separate links.

| | Origin | Location |
|---|---|---|
| Meaning | The group the fish came from | Where it is now |
| Stored as | `dish_id` (set at registration, never changed) | `current_unit_id` (exists) and a new `current_dish_id` |
| Example (Z1) | 19234_1 | 19234_3, well A1 |
| Drives | Genotype, cross, age, screening results | Plate map, care, "where do I find it" |

`dish_id` already behaves as an origin for fish that are moved: assign never
changes it. Keeping that meaning and adding a location field is additive for
consumers. The rule that follows: **register a fish under the dish it came
from, then move it.** Don't register it directly in a mixed container.

### Screening results are inherited

A fish's screening result is computed from its origin dish's lineage, not typed
in per fish. Walk from the origin dish up through `parent_dish_id`, collecting
what each step established:

- **Derived dish:** it holds the fish from one bucket of one step
  (`source_screening_datetime`, `source_screening_bucket`). Example:
  `18300_2_pos1` is positive for that step's indicators.
- **Parent dish after a step:** if every fish left in the dish came from one
  classified bucket (e.g. all `remain_parent` allocations are
  `positive_screened`), the dish is known to be that result. Examples: 19234_1
  is mCherry+ and 19234_2 is mCherry-, both from 2026-10-05.
- **Otherwise unknown:** e.g. `remaining_in_parent` (not classified), or more
  than one bucket left in the dish. The fish's result for that indicator is
  unknown until someone records it.

Results accumulate along the lineage, so a fish can be pigment- (an earlier
step) and mCherry+ (a later one). An optional **fish-level observation** (fish,
time, indicator, result, notes) overrides the inherited value, e.g. a fish
re-checked under the scope after isolation. The fish API reports each result
with its source: "inherited from 19234_1, step 2026-10-05T11:18" or "observed
on this fish".

### Moving is one action

Moving a tracked fish to a unit in another dish does three things in one
transaction:

- updates `current_unit_id` and `current_dish_id`, and writes
  `housing_unit_occupancy`;
- records a dish transfer of 1 between the two dishes, so both
  `current_fish_count`s stay right;
- bumps the fish's `revision`.

The origin (`dish_id`) and the UUID never change. Registering a fish changes no
counts, because the fish is already in its dish. A batch form of the move
covers plate setup.

### A plate can be just a container

A plate filled from several dishes has no single group, so its own
`dish_population_type` and screening history don't describe its fish. The plate
map shows each well's inherited results instead. Whether such dishes get an
explicit "container" type is an open question.

## Worked examples

**The 2026-10-09 plate.** Target state after a backfill:

- Z1-Z5: `dish_id` 19234_1, inherited mCherry+;
- Z6-Z10: `dish_id` 19234_2, inherited mCherry-;
- all: `current_dish_id` 19234_3, `current_unit_id` per well.

The existing dish transfers (5 + 5, `well_plate_setup`) already match the
counts. The backfill bumps the ten fish's revisions, so it waits until their
recordings are registered (Citrus and Orange seal revision 3).

**Citrus: record, then isolate.**

1. At session start, Citrus registers a new fish under the batch dish with its
   own UUID (`dish_id` = batch dish, located there, no count change).
2. After the session, the fish is moved to a plate well: the batch dish count
   drops by one and the plate's rises.
3. The fish's origin, inherited screening result and UUID are unchanged.

Citrus seals the origin dish and its revision at start and doesn't read
`dish_id` after a move.

## Contract impact

These would be additive fields on the pinned `GET /fish/{fish_id}` and
`GET /dishes/{dish_id}/fish` responses:

- `current_dish_id`;
- `current_dish_uuid`;
- inherited and observed screening results with their sources.

This is a re-pin through agent-contracts, not a new `schema_version`.
`dish_id`'s meaning is unchanged for moved fish. The doc
[zebrobot_snapshot.md](zebrobot_snapshot.md) would state it explicitly as the
origin. `GET /dishes/{dish_id}/fish` needs a decision: list fish by origin, by
location, or both.

## Builds on this

- Plate setup page: pick source dishes, then place fish in wells. Fish are
  registered under their origin and moved in one batch.
- Citrus v4 create-with-UUID (idempotent `POST /dishes/{dish_id}/fish`) and the
  fish revision history it compares against.
- Recording a fish's death ([#13](https://github.com/jmdelahanty/metazebrobot/issues/13)):
  a location and status change on the fish.

## Open questions

- Should a fish-level observation with a different result from the inherited
  one flag the origin dish's screening as suspect?
- Should `GET /dishes/{dish_id}/fish` list by origin, by location, or both,
  with a parameter?
- Moves between dishes of different crosses: today dish transfers require the
  same cross. Mixed-cross plates need that rule relaxed for single-fish moves,
  or a container type exempt from it.
- Origins other than a dish (an adult from a tank, an import): leave room for
  an origin kind, but build nothing until needed.
