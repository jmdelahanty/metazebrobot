---
title: "Fish Deaths and Endings"
summary: "Proposal: record when and how an individually tracked fish's life in MetaZebrobot ends (found dead, euthanized, propagated), from a fish action or from its dish's termination, keeping dish counts right."
owner: metazebrobot
status: current
kind: design
verified_against: ddc44df
---

# Fish Deaths and Endings

Status (2026-10-15): proposal; nothing below is built. Step 4 of the
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
- `GET /dishes/{dish_id}/fish` question (Jeremy): list only living fish by
  default (`?include_ended=true` for history), or all fish with `status`? See
  open questions.
- The fish timeline adds "died: euthanized (dish 19234_3 terminated)" or
  "found dead in well A1".

## Open questions (Jeremy)

- **`propagation`:** record the fish as `propagated` (alive, left tracking),
  or as an ending at all?
- **Fish lists:** should `GET /dishes/{dish_id}/fish` hide ended fish by
  default? Hiding them keeps a dead fish out of Citrus's pick list and fits
  "fish in this dish now". It's a meaning change for that endpoint again
  (Orange seals the list), so it would be stated in the re-pin like the last
  one. Showing all with `status` keeps history visible, but Citrus would have
  to filter.
- **Termination time:** dish termination stores only a date, so inherited
  endings are day-precision. Add a time to dish termination going forward?
