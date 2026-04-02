# Identity and Provenance Contract

Cross-repo data flow between MetaZebrobot (fish identity + housing),
Citrus (acquisition pipeline), and Palette (data processing + analysis).

## Source of Truth Ownership

| Entity | Source of truth | Other system | Sync mechanism |
|--------|----------------|--------------|----------------|
| Crosses | PyRAT (via MetaZebrobot proxy) | Palette: backfilled cache | Citrus H5 snapshot |
| Dishes + screening history | MetaZebrobot | Palette: backfilled cache | Citrus H5 snapshot |
| Fish identity + housing | MetaZebrobot | Palette: `subjects` cache | Citrus H5 snapshot |
| Recordings + sessions | Palette | MetaZebrobot: read-only link | MetaZebrobot reads Palette DB |
| Behavioral results | Palette | Not in MetaZebrobot | N/A |
| Arena assignments | Palette (`recordings.arena_id`) | Not in MetaZebrobot | N/A |

## Screening Model

Each dish tracks its screening history as a list of `ScreeningStep` records.
A single step captures one screening event where multiple criteria may be
assessed simultaneously:

- **`indicators_screened`** — list of indicators assessed (e.g. `["GFP", "jRGECO"]`),
  empty for pigment-only steps
- **`pigment_screened`** — whether pigmentation was assessed
- **`number_kept`** — fish that passed all criteria and remain in the dish
- **`number_removed_pigmented/negative/other`** — fish removed, broken out by reason

The removal counts already record fish that are euthanized or discarded — no
derived dish is needed for fish that won't be tracked further.

### Derived Dishes

When kept or removed fish are physically moved to a new container, the operator
creates a derived dish via `POST /screening/{dish_id}/split` with:
- **`fish_count`** — how many fish go into the new dish (explicit, not auto-calculated)
- **`container_type`** — what container they go into (petri_dish, beaker, well_plate, tank)
- **`population_type`** — positive_screened, negative_screened, or other

The derived dish inherits cross, genotype, DOF, and enclosure settings from the
parent. The `parent_dish_id` chain preserves full lineage.

### Yield Queries

To answer "for genotype X, what's the expected yield from one cross group?":
- Query all dishes by genotype
- Sum `count_screened_this_step` from first screening steps (initial population)
- Sum `final_positive_count` after all screening (final kept population)
- Yield = final / initial

## Identity Assignment Flow — First Recording

Fish always get IDs at recording time (not after). The flow for a fish's
**first** behavioral session:

1. Citrus checks MetaZebrobot for available fish → `GET /dishes/{dish_id}/fish`
2. If fish don't have IDs yet, Citrus registers them →
   `POST /dishes/{dish_id}/fish` (returns `fish_id` UUID)
3. Citrus writes H5 with fish_id, arena_id, and snapshot in
   `/zebrobot_snapshot/snapshot_json`
4. Session/recording metadata stays in Palette (Citrus creates it in Palette's
   registry, not MetaZebrobot)
5. After recording, operator assigns fish to wells in MetaZebrobot web UI —
   `POST /fish/{fish_id}/assign` with `unit_id`
6. Palette backfills subjects from H5 snapshot (existing path)

### Fish Identity Details

- **`fish_id`** (UUID) — system-generated primary key, globally unique, follows
  the fish across all systems
- **`subject_label`** — optional human-friendly label (e.g. `wt-01`, well
  position). Not unique, not required. For operator convenience at the bench.

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
operator must log the imaging session manually — either through MetaZebrobot's
web UI or by following a file naming convention that Palette can parse during
import.

## Open Design Questions (resolve before Citrus implementation)

1. **Fish discovery for re-use:** How does Citrus present available fish to the
   operator for a second recording? Options: query by dish/plate, query by
   well position, scan a barcode. MetaZebrobot API already has the building
   blocks (`GET /dishes/{dish_id}/fish`, `GET /units/{unit_id}`).

2. **Imaging session logging:** Microscopy uses vendor software that can't call
   APIs. Options: operator logs imaging sessions manually in MetaZebrobot web
   UI, or imaging files are named/organized by fish_id and Palette parses the
   association during import.

3. **H5 snapshot evolution:** The snapshot is currently flat (one dish, one
   cross). With individual fish, it needs to include per-fish metadata
   (fish_id, current housing, previous sessions). Define the schema_version=2
   format.

4. **Palette backfill for known fish:** When Palette processes a recording
   where the fish already exists in its `subjects` table, it should update
   (not duplicate) the subject record. Verify that
   `_backfill_subject_dish_cross_entities()` handles this via
   `INSERT OR IGNORE` / `ON CONFLICT`.

5. **Automatic well plate setup on split:** When splitting fish into a
   well_plate container, should individual fish records and wells be created
   automatically, or should this remain a separate manual step? Currently
   separate — revisit once the workflow is clearer.

## H5 Snapshot Schema (extended)

Current snapshot schema plus new fields:

- `fish_id` — individual fish UUID (new for individual tracking)
- `arena_id` — which arena the fish was in (already in Palette's recordings)
- `current_unit_id` — current housing position (new)
- `session_uuid` — already captured

## Palette Contract

Palette's `_backfill_subject_dish_cross_entities()` already reads `fish_id`
from provenance. As long as Citrus writes the fish_id to the H5, the existing
backfill path works. Session/recording metadata stays entirely in Palette —
MetaZebrobot no longer stores it (experiment_sessions and fish_runs tables
were removed; that data belongs in Palette).

The open questions above should be resolved before Citrus implementation
but do not block MetaZebrobot's current changes.
