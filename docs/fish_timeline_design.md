---
title: "Fish Timeline and Experiment Usage"
summary: "Proposal: one inspectable timeline per fish, assembled from the records each system owns; MetaZebrobot stores only a link per recording a fish was used in."
owner: metazebrobot
status: current
kind: design
verified_against: c6a88c1
---

# Fish Timeline and Experiment Usage

Status (2026-10-15): step 1 built (`data/fish_timeline.py`; `GET /fish/{fish_id}/timeline`
and the page `/fish/{fish_id}/view`, linked from the plate map, fish tables and
cross view). Steps 2–4 are proposals.

Goal (Jeremy): follow where an individual fish went, inspectably. For example:
minted during screening or at an experiment, started in parent A, moved to a
well in dish B, used in an experiment on rig Z. Builds on
[fish origin and location](fish_origin_and_location_design.md) and
[inherited screening calls](construct_screening_link_design.md).

## Why now

On 2026-10-09, plate 19234_3 was recorded at 17:20 (Cam2010096). Citrus
sealed no fish for that recording, because the operator's fish pick was
cleared when the 16:00 experiment stopped. MetaZebrobot couldn't identify the
fish afterwards: every fish still showed as sitting in its well, and nothing
recorded taking fish out. The timeline is meant to make that kind of gap
visible when it happens, and the Citrus v4 fish pick is meant to prevent it.

## Ownership (unchanged)

[Identity and provenance](identity_and_provenance_contract.md) assigns
**recordings and sessions to Palette**. MetaZebrobot doesn't store session
data. The `experiment_sessions` and `fish_runs` tables still exist but are
empty and unused. This design keeps that rule: the timeline is **assembled**
from records each system owns. MetaZebrobot stores only a **usage link**,
which says "this fish appears in that recording", with the identifiers
needed to look the recording up in Palette (or in the H5 Citrus wrote).

## The timeline

`GET /fish/{fish_id}/timeline` returns time-ordered entries. Each entry says
where it comes from:

| Entry | Source | Owner | Exists today? |
|---|---|---|---|
| Fertilized; cross, parent tanks | origin dish → cross → `cross_parents` | MZB (PyRAT cache) | yes |
| Screening calls | inherited calls (`/fish/{id}/screening`) | MZB | yes |
| Registered: when, how, by whom | `fish_subjects` + new creation provenance | MZB | partly (no how/by whom) |
| Moves between wells and dishes | `housing_unit_occupancy`, `dish_transfer_events` | MZB | yes |
| Edits (label, notes, ...) | `fish_subject_revisions` | MZB | yes (from 2026-10-14) |
| Used in a recording | **usage links** (new) → Palette / H5 | Palette owns the recording | no |
| Died / ended | fish status event ([#13](https://github.com/jmdelahanty/metazebrobot/issues/13)) | MZB | no |

A fish page in the web UI (`/fish/{fish_id}/`) shows the same entries, each
linking to its source: the dish, the screening step, the plate map, the
recording.

## Usage links

One row per fish per recording:

| Field | Meaning |
|---|---|
| `fish_id` | The fish |
| `recording_ref` | The recording's id in the system that owns it (Palette recording id, or Citrus session/run id + camera) |
| `dish_id` | The dish recorded (always set; the only subject when no fish is named) |
| `unit_id` | The well the fish was picked from (its `current_unit_id` when Citrus picked it), or null |
| `rig_id`, `arena_id` | Where |
| `started_at`, `ended_at` | Lab-local start and end (end filled when the recording stops, or at intake) |
| `fish_revision` | The fish revision the recording sealed |
| `status` | `declared` (Citrus said so at start) or `confirmed` (Palette admitted the recording) |
| `source` | `citrus` or `palette` |

Rules:

- **MZB never stores recording content.** No paths, no behaviour results,
  no frames: only the reference and the fields above.
- **Writers:** Citrus writes `declared` at record start, the same moment it
  registers or verifies the fish (subject identity v4). Palette upgrades a
  link to `confirmed` at intake, or adds it if Citrus couldn't reach MZB.
  Jeremy leaned toward Palette confirming at intake (2026-10-14).
- **Dish-level rows** (decided 2026-10-15): a recording that names no
  individual fish still gets a row, with `fish_id` null and `dish_id` set.
  That makes queries like "recordings of this dish" or "recordings of fish
  never minted" (including v4 `dish_group` subjects) possible. The timeline
  of every fish in that dish shows "possibly used in recording R (fish not
  recorded)". That's what the 17:20 recording needs.
- **Out of the well, without manual moves** (decided 2026-10-15): a fish
  picked from a well for an arena isn't moved in MetaZebrobot. Its link
  records `unit_id`, `started_at` and `ended_at`, so the timeline shows "out
  of C1 for recording R, 16:00–16:35" and "which wells were empty at 17:20"
  is answered from the links active then. The fish's location stays the
  well, where it returns. Nobody has to record moves.
- **Writes are idempotent** on (`fish_id` or `dish_id`, `recording_ref`), like
  the v4 fish create.

## Registration provenance

New fish record how they were created: `created_via` (`web_form` |
`web_batch` | `api` | `citrus_start` | `plate_setup`) and `created_by` (the web
user, or the client name for API calls). The timeline's first entry then says
"minted during screening by Jeremy" or "minted at experiment start by
Citrus".

## Build order

1. **MZB-owned timeline:** `GET /fish/{fish_id}/timeline` from what exists
   today (origin, cross, screening calls, moves, transfers, revisions), plus
   the fish page. No other system involved.
2. **Registration provenance:** `created_via` / `created_by`.
3. **Usage links:** table and endpoints (`POST` idempotent, `GET` by fish or
   dish), agreed with Citrus and Palette as an additive contract change.
4. **Deaths ([#13](https://github.com/jmdelahanty/metazebrobot/issues/13)):**
   status events on the timeline.

## Open questions (Jeremy)

- **Who writes usage links:** Citrus at start (`declared`) and Palette at
  intake (`confirmed`), or only one of them?
