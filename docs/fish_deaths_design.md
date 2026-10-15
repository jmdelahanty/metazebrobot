---
title: "Fish Deaths and Endings"
summary: "Proposal: record when and how an individually tracked fish's life in MetaZebrobot ends (found dead, euthanized, propagated), from a fish action or from its dish's termination, keeping dish counts right."
owner: metazebrobot
status: current
kind: design
verified_against: ddc44df
---

# Fish Deaths and Endings

Status (2026-10-15): built (`data/fish_endings.py`). Decisions: propagation ends
the record as `propagated`; fish lists hide ended fish by default; inherited
endings stay day-precision. Step 4 of the
[fish timeline](fish_timeline_design.md); resolves
[#13](https://github.com/jmdelahanty/metazebrobot/issues/13).

## Problem

Care checks record deaths as a number per well or dish (`num_dead`). Those
numbers lower the dish's `current_fish_count`, but no fish record changes: a
fish that died still shows as living in its well. Terminating a dish
(`status` inactive, with a `termination_reason` and `termination_date`) also
leaves its fish untouched.

## Proposal

### How a fish's record ends

New fields on `fish_subjects`:

| Field | Values |
|---|---|
| `status` | `alive` (default) \\| `dead` \\| `propagated` |
| `ended_at` | When: UTC timestamp, or a lab date when only the day is known |
| `ended_precision` | `time` \\| `day` |
| `end_reason` | `found_dead` \\| `euthanized` \\| `propagated` \\| `other` |
| `end_source` | `fish` (recorded on the fish) \\| `dish_termination` (inherited from its dish) |
| `end_notes` | free text |

`propagated` means the fish left individual tracking alive (handed to
aquatics). It isn't a death, but its MetaZebrobot record ends there.

Ending a fish closes its open well occupancy (the well is free), bumps its
revision, and adds an "ended" entry to its timeline.

### Two ways a fish ends

1. **On the fish** (`POST /fish/{fish_id}/end`: `reason`, optional `at`,
   `notes`). This is for one fish found dead or euthanized. The dish's count
   drops by one, recorded as a death on the fish's well (or the dish, if it
   has no well) at that time, so the existing count arithmetic stays the
   single place counts come from.
2. **From its dish's termination** (Jeremy, 2026-10-15). When a dish is set
   inactive:

   | `termination_reason` | Fish still alive in that dish become |
   |---|---|
   | `euthanasia` | `dead`, `euthanized`, at the termination date (`day` precision) |
   | `propagation` | `propagated`, at the termination date |
   | `transfer` | unchanged: a dish only ends by transfer once its fish have moved out |

   These carry `end_source = dish_termination`. Setting the dish back to
   active reverses exactly those endings (not ones recorded on the fish).
   Counts aren't touched: the whole dish ended.

### Care page

For a well with one fish, the care page's Dead column becomes "this fish
died" and records the ending on that fish (way 1). It isn't a separate
number, so the same death can't be counted twice. Wells with several fish
keep the numeric column.

### API

- Fish responses gain `status`, `ended_at`, `ended_precision`, `end_reason`.
  These are additive.
- `GET /dishes/{dish_id}/fish` lists only living fish by default;
  `?include_ended=true` adds ended ones (Jeremy, 2026-10-15). This is
  documented for consumers in [zebrobot_snapshot.md](zebrobot_snapshot.md).
- The care page's well list and plate map show only living fish. An ended
  fish keeps `current_unit_id` as its last well; its occupancy is closed.
- The fish timeline adds "died: euthanized (dish 19234_3 terminated)" or
  "found dead in well A1".

## Decisions

- **A first-time fish registration on an inactive dish stays refused**
  (`409 dish_inactive`, Jeremy 2026-10-15). Registering a fish to a dish that
  no longer exists as a living group doesn't make sense. The known cost is a
  narrow race. Citrus mints a fish at Start while MetaZebrobot is unreachable,
  and the dish is terminated before the outbox delivers. That registration
  then fails, the fish never appears in MetaZebrobot, and its usage link is
  held as failed in Citrus's GUI. The recording keeps the fish's UUID and the
  dish. Usage links for fish that already exist are accepted whatever their
  status.

