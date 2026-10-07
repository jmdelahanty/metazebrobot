---
title: "Identity and Provenance Contract"
summary: "Which system owns which records across MetaZebrobot, Citrus, Orange and Palette, and how identity flows between them."
owner: metazebrobot
status: current
kind: reference
verified_against: 384a366
---

# Identity and Provenance Contract

Cross-repo data flow between MetaZebrobot (fish identity + housing),
Citrus (acquisition pipeline), and Palette (data processing + analysis).

## Source of Truth Ownership

| Entity | Source of truth | Other system | Sync mechanism |
|--------|----------------|--------------|----------------|
| Crosses | PyRAT (via MetaZebrobot proxy) | Palette: backfilled cache | Citrus H5 snapshot |
| Dishes + screening history | MetaZebrobot | Palette: backfilled cache | Citrus H5 snapshot |
| Fish identity + housing | MetaZebrobot | Palette: `subjects` cache | Citrus H5 snapshot |
| Recordings + sessions | Palette | Not in MetaZebrobot (it does not read Palette) | N/A |
| Behavioral results | Palette | Not in MetaZebrobot | N/A |
| Arena assignments | Palette (`recordings.arena_id`) | Not in MetaZebrobot | N/A |

## Screening Model

Each dish tracks its screening history as a list of `ScreeningStep` records.
A single step captures one screening event where multiple criteria may be
assessed simultaneously:

- **`indicators_screened`** — list of indicators assessed (e.g. `["GFP", "jRGECO"]`),
  empty for pigment-only steps
- **`pigment_screened`** — whether pigmentation was assessed
- **`count_screened_this_step`** — fish screened in this step
- **`allocations`** — where the screened fish went, as a list of
  `{bucket, disposition, count, destination_dish_id}`: `bucket` is
  `remaining_in_parent`, `positive_screened`, `negative_screened`,
  `pigmented_screened`, or `other`; `disposition` is `remain_parent`,
  `derived_dish`, or `discarded`
- **`number_kept`**, **`number_removed_pigmented/negative/other`** — legacy
  compatibility counts; new steps record allocations instead

A `discarded` allocation already records fish that are euthanized or
discarded — no derived dish is needed for fish that won't be tracked further.

### Derived Dishes

When fish are physically moved to a new container, the operator creates a
derived dish from the screening page. The step-linked form,
`POST /screening/{dish_id}/steps/{screening_datetime}/split`, also records a
`derived_dish` allocation on that step; `POST /screening/{dish_id}/split`
creates a derived dish without a step link. Both take form fields:
- **`fish_count`** — how many fish go into the new dish (explicit, not auto-calculated)
- **`container_type`** — what container they go into (petri_dish, beaker,
  well_plate, tank); defaults to the parent's
- **`population_type`** — e.g. positive_screened, negative_screened,
  pigmented_screened, or other

The derived dish inherits cross, genotype, DOF, species, sex, breeding
parents, and enclosure settings from the parent, and records `parent_dish_id`.
Lineage is read from screening allocations and transfer events, with
`parent_dish_id` as a fallback; see `docs/dish_lineage_graph.md`.

### Yield Queries

To answer "for genotype X, what's the expected yield from one cross group?":
- Query all dishes by genotype
- Sum `count_screened_this_step` from first screening steps (initial population)
- Sum `final_positive_count` after all screening (final kept population)
- Yield = final / initial

## Identity Assignment Flow — First Recording

Fish get IDs no later than recording time (not after): pre-registered in
MetaZebrobot, or minted at recording. The flow for a fish's **first**
behavioral session:

1. Citrus checks MetaZebrobot for available fish → `GET /dishes/{dish_id}/fish`
2. If fish don't have IDs yet, Citrus registers them →
   `POST /dishes/{dish_id}/fish` (returns `fish_id` UUID)
3. Citrus writes H5 with fish_id, arena_id, and snapshot in
   `/zebrobot_snapshot/snapshot_json`
4. Session/recording metadata stays in Palette (Citrus creates it in Palette's
   registry, not MetaZebrobot)
5. After recording, fish are assigned to wells with
   `POST /fish/{fish_id}/assign` and a `unit_id` (the web UI has no
   assignment control yet; see `docs/fish_tracking_api.md`)
6. Palette backfills subjects from H5 snapshot (existing path)

### Fish Identity Details

- **`fish_id`** (UUID) — system-generated primary key, globally unique, follows
  the fish across all systems. Callers may supply a pre-minted UUID on
  `POST /dishes/{dish_id}/fish`.
- **`subject_label`** — optional human-friendly label (e.g. `wt-01`, well
  position). Not unique, not required. For operator convenience at the bench.

### Dish Identity, Versioning, and Recordings Without Citrus

Dishes carry an immutable `dish_uuid` next to the human `dish_id`; dishes and
fish carry a content `revision` and `updated_at`. Consumers record the
identifiers at acquisition and compare `(dish_uuid, revision)` later.
Semantics and stability promises: `docs/zebrobot_snapshot.md` (Identity and
change detection, API errors, Contract and stability). Field-level shapes:
`docs/api/consumer_openapi.json`.

## Multi-Session Fish Lifecycle

A fish may go through multiple experiments across its lifetime:

```
screening → behavior #1 (ID minted) → well plate → behavior #2 → imaging
```

**Behavior #2 with existing fish:** Citrus needs to discover that the fish
already has an ID. It queries MetaZebrobot for fish in the dish/plate being
used, gets back fish_ids and their current housing (well positions), and
links them to the new session. The H5 snapshot for this recording includes
the existing fish_id, its current housing info, and original provenance.

**Microscopy/imaging:** Vendor software cannot call MetaZebrobot's API. The
operator must log the imaging session manually or follow a file naming
convention that Palette can parse during import. MetaZebrobot has no session
logging (sessions belong to Palette), so manual logging would happen in
Palette.

## Open Design Questions (resolve before Citrus implementation)

1. **Fish discovery for re-use:** How does Citrus present available fish to the
   operator for a second recording? Options: query by dish/plate, query by
   well position, scan a barcode. MetaZebrobot API already has the building
   blocks (`GET /dishes/{dish_id}/fish`, `GET /units/{unit_id}`).

2. **Imaging session logging:** Microscopy uses vendor software that can't call
   APIs. Options: operator logs imaging sessions manually (in Palette, which
   owns sessions; MetaZebrobot no longer stores them), or imaging files are
   named/organized by fish_id and Palette parses the association during
   import.

3. **H5 snapshot evolution:** The stored snapshot is currently flat (one dish,
   one cross). With individual fish, it needs to include per-fish metadata
   (fish_id, current housing, previous sessions). This is the stored snapshot
   format, owned by Citrus; it is separate from the API response
   `schema_version` 2 described in `docs/zebrobot_snapshot.md`.

4. **Palette backfill for known fish (Palette-owned):** When Palette processes
   a recording where the fish already exists in its `subjects` table, it
   should update (not duplicate) the subject record. Verify that
   `_backfill_subject_dish_cross_entities()` handles this via
   `INSERT OR IGNORE` / `ON CONFLICT`.

5. **Automatic well plate setup on split:** When splitting fish into a
   well_plate container, should individual fish records and wells be created
   automatically, or should this remain a separate manual step? Currently
   separate — revisit once the workflow is clearer.

## H5 Snapshot Schema (extended)

Proposed fields for the H5 snapshot. The H5 layout is owned by Citrus, which
documents what it writes in its own repository (`docs/zebrobot_snapshot.md`,
`docs/Understanding_H5_Log.md`); this list is MetaZebrobot's request, not a
description of current Citrus output. Current snapshot schema plus new fields:

- `dish_uuid`, `dish_revision`, `dish_updated_at`, `fish_revision` — identity
  and version at acquisition (see `docs/zebrobot_snapshot.md`)
- `fish_id` — individual fish UUID (new for individual tracking)
- `arena_id` — which arena the fish was in (already in Palette's recordings)
- `current_unit_id` — current housing position (new)
- `session_uuid` — already captured

## Palette Contract

This section describes Palette internals as last known to MetaZebrobot;
Palette documents its snapshot import in its own repository
(`docs/zebrobot_snapshot.md`).

Palette's `_backfill_subject_dish_cross_entities()` already reads `fish_id`
from provenance. As long as Citrus writes the fish_id to the H5, the existing
backfill path works. Session/recording metadata stays entirely in Palette —
MetaZebrobot no longer stores it (experiment_sessions and fish_runs tables
were removed; that data belongs in Palette).

The open questions above should be resolved before Citrus implementation
but do not block MetaZebrobot's current changes.
