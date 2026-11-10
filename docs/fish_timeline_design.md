---
title: "Fish Timeline and Experiment Usage"
summary: "Proposal: one inspectable timeline per fish, assembled from the records each system owns; MetaZebrobot stores only a link per recording a fish was used in."
owner: metazebrobot
status: current
kind: design
verified_against: c6a88c1
---

# Fish Timeline and Experiment Usage

Status (2026-10-15): steps 1–3 built (`data/fish_timeline.py`; `GET /fish/{fish_id}/timeline`
and the page `/fish/{fish_id}/view`, linked from the plate map, fish tables and
cross view). Step 3 is `data/usage_links.py` with the endpoints below. Step 4 (deaths) is built: [fish deaths and endings](fish_deaths_design.md).
Proposed (2026-11-09): [correcting the fish a recording names](#correcting-the-fish-a-recording-names-design-2026-11-09).

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
| `rig_id`, `arena_id` | Where: Citrus's configured rig id (the arena's `rig_name`, e.g. `omnifin0`), as written to the H5 root and used in the Orange binding |
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

## Proposed endpoints (for review, 2026-10-15)

Built as proposed, with the refinements below. They're in the pinned consumer
slice.

**`POST /usage-links`**: record that an arena recording used a dish (and
fish), at Start.

```json
{
  "recording_ref": "obsctx_<64 hex>",
  "ref_kind": "observation_context",
  "recording_id": "<Orange recording folder>",
  "dish_id": "19234_3",
  "fish_id": "55f673e1-6e2c-4852-b7f0-fa447ebe292e",
  "fish_revision": 4,
  "unit_id": "19234_3:A1",
  "rig_id": "omnifin0",
  "arena_id": "2",
  "started_at": "2026-10-09T20:00:18Z"
}
```

| Case | Response |
|---|---|
| New `recording_ref` | `201`, the link |
| Same `recording_ref`, identical body | `200`, the current link (may already carry an end) |
| Same `recording_ref`, different body | `409 {"error": "usage_link_conflict", "recording_ref": ...}` |
| New link, unknown dish or fish | `404 dish_not_found` / `fish_not_found` |
| Malformed field (`ref_kind`, timestamp not RFC 3339 UTC `Z`, bad UUID) | `422 {"error": "invalid_usage_link", "field": ...}` |

- An existing `recording_ref` is answered before any dish or fish check,
  like the v4 create, so a late replay never fails because something changed
  since.
- No check that the fish is still in `dish_id`: the link records what Citrus
  sealed at Start.
- `fish_id`, `fish_revision`, `unit_id` and `recording_id` may be null
  (dish-level rows, unbound runs). Inactive dishes are accepted.

**`PATCH /usage-links/{recording_ref}`**: the end, at Stop.

```json
{"ended_at": "2026-10-09T20:35:02Z", "end_status": "completed"}
```

`200` with the link (also for an identical replay). `409 usage_link_end_conflict`
if an end with different values is already recorded. `404 usage_link_not_found`.
`422 invalid_usage_link`.

**Reads**:
- `GET /usage-links/{recording_ref}`;
- `GET /usage-links?fish_id=...`, `?dish_id=...` (includes dish-level rows),
  `?active_at=<RFC 3339>` (which links were open at an instant: "which
  wells were empty at 17:20").
- The fish timeline adds "used in recording", "out of well" and "possibly
  used (fish not recorded)" entries from these.

**Response** (`UsageLinkResponse`): the POST fields, plus `ended_at`,
`end_status`, `received_at` (server UTC) and `updated_at`. Times stay RFC
3339 UTC on the wire.

### Refinements from Citrus's review (2026-10-15)

- **`recording_ref` validation:** closed pattern per `ref_kind`, at most 160
  characters:
  - `observation_context`: `obsctx_` + 64 lowercase hex;
  - `citrus_session`: printable ASCII with no `/` and no control characters
    (an ISO 8601 UTC time, `_`, and the arena config name).

  In `PATCH /usage-links/{recording_ref}`, the client percent-encodes the
  path segment (`:` and spaces in unbound session ids). Otherwise
  `422 invalid_usage_link` with `field: recording_ref`.
- **`arena_id`** is a string: the arena's config name, the same value as the
  Orange binding's `target.arena_id`.
- **Nullability rules** (`422 invalid_usage_link`):
  - `fish_revision` only with `fish_id`;
  - `unit_id` only with `fish_id`;
  - `ended_at` ≥ `started_at`.

  `fish_revision` may be null with a `fish_id` (an unverified pick, or a
  minted fish still queued). `unit_id` is null for a fish minted from a batch
  dish.
- **`subject_count`** (optional, integer ≥ 1): 1 for a fish row, ≥ 2 for a
  dish-group row, so a dish-only row says how many fish were out.
- **A PATCH before its POST gets `404`** and creates nothing. Citrus only sends
  a PATCH after its POST succeeded, so a 404 means the link was lost; Citrus
  treats it as terminal and shows it.
- **`end_status` from Citrus:**
  - `completed`: normal stop;
  - `aborted`: operator abort, or a refused start that had already linked;
  - `interrupted`: crash, power loss or GUI closed mid-session. This one is
    sent at the next Citrus start, possibly hours later, with `ended_at` =
    the last flushed frame time, not the arrival time.
- **Only Citrus records the end** (agent-contracts #112, 934811d): the file
  seals no normal-stop vs abort signal, so Palette never PATCHes the end. A
  link whose end never arrives stays open: the timeline says "end not
  recorded yet", and `GET /usage-links?active_at=` includes it for every later
  instant. Read `ended_at: null` in that query as "end unknown", not "still
  running".
- **`X-Delivered-By`** (Palette, 2026-10-15): an optional request header
  (`palette` on Palette's intake replays; Citrus sends none). It's recorded on
  first creation as `delivered_by` and never part of the idempotency
  comparison, so a replay of the sealed request stays a 200.
- **Stable request bytes:** Citrus seals the exact start POST (method, path,
  body) in snapshot v4.x, so the request carries no server-filled fields.

## Correcting the fish a recording names (design, 2026-11-09)

Status: proposal; decisions of 2026-11-09 below. Nothing is built.

### The problem

The Citrus picker can seal the wrong fish for an arena. Nothing in any
system can correct that afterwards: the H5 is sealed, MetaZebrobot's usage
link is idempotent on its creation body, and Palette's planned manual link
(palette#402, design only) covers unconfirmed fish, not a `registered` fish
that is the wrong one. Palette's intake has no cross-arena check either, so
these recordings are admitted silently.

Usage links with one fish in two arenas at overlapping times, as of
2026-11-09:

| Recording | Arenas | Sealed fish | Actually there (operator's account) |
|---|---|---|---|
| `2026_11_06_15_48_57` | arena_2, arena_3 | `5a50397a` (19498_4 Z5, C1) | arena_3 was Z6 (`a21ac2c1`, C2) |
| `2026_11_06_17_16_17` | arena_3, arena_4 | `f3fce668` (19498_4 Z9, A4) | arena_3 was Z10 (`efb06650`, B3) |
| `2026_10_17_15_57_07` | arena_1, arena_3 | `784c1937` (19329_1_pos1, B1) | misclick; which fish were there can't be known |
| `2026_10_16_17_28_25` | arena_3, arena_4 | `5870527e` (19329_3, no well) | misclick; which fish were there can't be known |

In both checked cases one misclick copied the neighbouring arena's fish; the
other arenas were right. A wrong pick doesn't have to duplicate a fish,
though: an arena can name a real, distinct, wrong fish, which only a person
can catch.

### Principles

- **The sealed record is never edited.** The H5, the snapshot and the usage
  link's creation values stay as recorded. A replay of the sealed request
  keeps getting 200.
- **A correction is its own record** that outranks the sealed value, and
  says who attested it, on what evidence, and when.
- **Corrections are append-only.** The newest correction for an arena is the
  effective one. Undoing a correction is a new correction back to the sealed
  fish, with its own evidence.
- **Readers see both.** Every view that shows the effective fish can show
  that it was corrected and what was sealed.

### MetaZebrobot: `usage_link_corrections`

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `recording_ref` | The corrected link (references `usage_links`) |
| `fish_id` | The fish that was actually in the arena |
| `dish_id` | That fish's dish at `started_at`; usually the link's dish |
| `fish_revision`, `unit_id` | Filled by MetaZebrobot from the fish's revisions at the link's `started_at`, not typed |
| `attested_by` | The username who made the correction (the viewer picker for the web; required) |
| `evidence` | Free text, required (e.g. "bench notes: arena 3 held Z6") |
| `corrected_at` | Server UTC |

Rules:

- The corrected fish must exist, and differ from the link's current
  effective fish.
- **One fish, one arena:** a correction is refused (409
  `fish_in_another_arena`) if the corrected fish is the effective fish of
  another link whose time overlaps. Correct that arena first, so the
  recording never ends up claiming one fish twice.
- A dish-level link (no `fish_id`) can be corrected to name a fish.
- **"Fish unknown"** (decided 2026-11-09): a correction may set `fish_id`
  null when nobody can tell which fish was in the arena. The link then reads
  as a dish-level row ("possibly used, fish not recorded") for every fish in
  the dish, `fish_revision` and `unit_id` are null, and the one-fish-one-arena
  check doesn't apply.
- When a duplicate can't be resolved, neither arena can be trusted: both
  links get "fish unknown", because nothing says which arena held the sealed
  fish.

### What changes for readers

- `UsageLinkResponse` gains an optional `correction`: the effective
  correction (fields above plus `id`), or null. The top-level fields stay as
  sealed, so the idempotency comparison and anything reading them unchanged
  keep working. This is additive; `api_schema_version` stays 2.
- `GET /usage-links?fish_id=` matches the **effective** fish. A fish that was
  sealed but corrected away gets a timeline entry instead: "recording R,
  arena 3 named this fish; corrected to Z6 by <user> on <date>: <evidence>".
- The fish timeline and "out of well" entries use the effective fish and
  well, so Z6's timeline shows it out of C2, and Z5's shows it out of C1 for
  arena_2 only.
- Overlap flag: a link whose fish has another overlapping link is marked
  "one fish in two arenas" on the timeline and on a needs-review list, until
  a correction resolves it. New links are still accepted as sent (recording
  never waits on MetaZebrobot); the flag is only shown.

### Endpoints (proposed)

- `POST /usage-links/{recording_ref}/corrections` with
  `{fish_id, dish_id?, evidence}`. Returns 201 and the link with its new
  `correction`. Errors: 404 `usage_link_not_found` / `fish_not_found`, 409
  `fish_in_another_arena` / `correction_unchanged`, 422
  `invalid_correction`.
- `GET /usage-links/{recording_ref}/corrections`: every correction, oldest
  first.
- Web: a "Wrong fish?" action on the fish timeline's recording entry and on
  the needs-review list, like the plate map's "Wrong result?".

Who may write: the web UI only at first. Citrus and Palette don't send
corrections.

### Across systems (needs an agent-contracts amendment)

- **One owner for the correction** (decided 2026-11-09): MetaZebrobot owns it, because
  it owns fish identity, and people already correct fish there. Palette's
  intake already replays the sealed usage link; its 200 carries the
  `correction`, so Palette records "corrected per MetaZebrobot correction
  <id>" in its registry above the sealed value, keeping the sealed value as
  recorded. Palette needs `correction` in its consumer pin. The alternative,
  Palette owning a separate correction (keyed on session id + file sha256),
  gives two attestations that can disagree.
- **Citrus:** refuse a Start that seals one fish in two arenas, and show each
  arena's Z label and well in the start summary. That prevents the checked
  cases; only a person catches a distinct wrong fish.
- Orange: no change. The receipt and declaration stay as sealed.

### Build order

1. MetaZebrobot: table, endpoints, `correction` on responses, timeline and
   overlap flag, needs-review list, "Wrong fish?" action.
2. agent-contracts amendment: `UsageLinkResponse.correction`; Palette and
   Citrus review; merges on the operator's word; re-pin.
3. Apply the data (after a database backup): the two 2026-11-06
   corrections (arena_3 → Z6 and arena_3 → Z10), and "fish unknown" for
   both arenas of each October duplicate (misclicks; the fish can't be
   known).
4. Palette: read `correction` at intake and on reconcile.
5. Citrus: the one-fish-one-arena start check.

### Decisions (2026-11-09)

1. MetaZebrobot is the single owner of corrections; Palette reads them.
2. A correction can say "fish unknown".
3. The October cases were misclicks, and which fish were in those arenas
   can't be known: both arenas of each become "fish unknown".
