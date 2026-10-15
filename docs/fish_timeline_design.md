---
title: "Fish Timeline and Experiment Usage"
summary: "Proposal: one inspectable timeline per fish, assembled from the records each system owns; MetaZebrobot stores only a link per recording a fish was used in."
owner: metazebrobot
status: current
kind: design
verified_against: c6a88c1
---

# Fish Timeline and Experiment Usage

Status (2026-10-15): steps 1 and 2 built (`data/fish_timeline.py`; `GET /fish/{fish_id}/timeline`
and the page `/fish/{fish_id}/view`, linked from the plate map, fish tables and
cross view). Steps 3 and 4 are proposals.

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

One row per arena per recording. Field choices follow Citrus's review
(2026-10-15):

| Field | Meaning |
|---|---|
| `recording_ref` | The arena-recording's id: Orange's `observation_context_id` (`obsctx_` + 64 hex) for bound sessions; Citrus's `session_uuid` for unbound Citrus-only runs. Unique per arena. |
| `ref_kind` | `observation_context` or `citrus_session`, so the two namespaces never mix |
| `recording_id` | Orange's recording folder name, the grouping people search by (null for unbound runs) |
| `dish_id` | The dish recorded (always set) |
| `fish_id` | The fish, or null for `dish_group` arenas and v3-era runs |
| `fish_revision` | The revision the snapshot sealed |
| `unit_id` | The well the fish was picked from (Citrus's sealed `mzb_fish_unit_id`) |
| `rig_id`, `arena_id` | Where (`rig_id` source to be decided) |
| `started_at`, `ended_at` | RFC 3339 UTC on the wire (`Z`); MZB displays lab time |
| `end_status` | `completed` \| `aborted` \| `interrupted`, so an aborted run isn't read as a normal absence |

Rules:

- **MZB never stores recording content.** No paths, no behaviour results,
  no frames: only the reference and the fields above.
- **Writer (decided 2026-10-15): Citrus only.** `POST` at Start (not arm:
  the context is bound and the fish registration has its answer), and `PATCH`
  `ended_at` / `end_status` at Stop. Both go through Citrus's outbox and never
  block start or stop. The outbox orders them: a link waits behind a queued
  fish registration; if the registration fails terminally, the link is held
  as failed too (never rewritten as dish-only). Palette confirmation can be
  added later without changing what's built.
- **Idempotent, like the v4 create:** keyed on `recording_ref` (with
  `arena_id` checked). An identical replay → 200, a different body → 409. The
  `PATCH` follows the same rule. The row stores its creation values for the
  comparison.
- **Dish-level rows** (decided 2026-10-15): an arena with a dish but no fish
  named (`dish_group`, v3-era runs) still gets a row, with `fish_id` null.
  That makes queries like "recordings of this dish" or "recordings of fish
  never minted" possible. The timeline of every fish in that dish shows
  "possibly used in recording R (fish not recorded)". That's what the 17:20
  recording needs. An arena with no dish declared sends no link.
- **Out of the well, without manual moves** (decided 2026-10-15): a fish
  picked from a well isn't moved in MetaZebrobot. Its link records `unit_id`,
  `started_at`, `ended_at` and `end_status`, so the timeline shows "out of C1
  for recording R, 16:00–16:35" and "which wells were empty at 17:20" is
  answered from the links active then.
- **On the Citrus side** (a v4.x addition): the exact start POST is sealed in
  the snapshot, like `registration_request`; the end PATCH isn't.

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

- **`rig_id`:** Orange's rig id, the hostname, or a configured rig name? Citrus
  seals no rig id today.
