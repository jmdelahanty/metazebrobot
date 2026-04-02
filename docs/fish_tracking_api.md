# Fish Tracking API

This document describes the MetaZebrobot API endpoints for individual fish
tracking, housing unit management, and how to snapshot fish metadata into H5
files at acquisition time.

## API access

Same as the existing dish/cross API:

- SSH tunnel: `http://127.0.0.1:18000`
- DB host: `http://127.0.0.1:8000`

No auth required via SSH tunnel.

## Core concepts

- **fish_id** — UUID v4 (`8-4-4-4-12` hex, lowercase). Durable identity for
  one fish. Minted either by MetaZebrobot (web UI / batch registration) or by
  Citrus at acquisition time and back-registered later.
- **housing_unit** — A physical position within a dish: a well, lane, chamber,
  or the entire dish for simple petri dishes. Has its own `unit_id`
  (`{dish_id}:{position_label}`).
- **dish_id** — Where the fish currently lives. For derived dishes (well plates,
  sorted populations), `dish_id` points to the derived dish, not the original
  source.
- Fish registration is **optional**. Not all dishes use individual tracking.
- One fish can have **multiple recordings** — session tracking lives in
  Palette (see `docs/identity_and_provenance_contract.md`).

---

## Endpoints

### Fish subjects

#### List fish for a dish

```
GET /dishes/{dish_id}/fish
```

Response:
```json
{
  "items": [
    {
      "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
      "dish_id": "17257_1",
      "subject_label": "A1",
      "sex": "unknown",
      "genotype": "Tg(elavl3:jRGECO1b)",
      "species": "Danio rerio",
      "created_at": "2026-03-31T14:22:01",
      "notes": null,
      "current_unit_id": "17257_1_WP1:A1"
    }
  ]
}
```

`current_unit_id` is `null` if the fish has not been assigned to a housing unit.

#### Register a new fish

```
POST /dishes/{dish_id}/fish
Content-Type: application/json

{
  "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
  "subject_label": "A1",
  "sex": "unknown",
  "genotype": "Tg(elavl3:jRGECO1b)",
  "species": "Danio rerio",
  "notes": null
}
```

All fields are optional:
- If `fish_id` is omitted, a UUID v4 is generated server-side.
- If `fish_id` is provided (e.g. minted by Citrus), it is used as-is.

Returns `201` with the created fish object (same shape as the list items above).

Returns `404` if the dish does not exist.

#### Fetch a fish by UUID

```
GET /fish/{fish_id}
```

Returns the fish object. `404` if not found.

#### Update a fish

```
PATCH /fish/{fish_id}
Content-Type: application/json

{"subject_label": "B2", "notes": "moved wells"}
```

Accepted fields: `subject_label`, `sex`, `genotype`, `species`, `notes`.

Returns the updated fish object.

#### Delete a fish

```
DELETE /fish/{fish_id}
```

Returns `204` on success, `404` if not found.

---

### Housing units

#### List housing units for a dish

```
GET /dishes/{dish_id}/units
```

Response:
```json
{
  "items": [
    {
      "unit_id": "17257_1_WP1:A1",
      "dish_id": "17257_1_WP1",
      "position_label": "A1",
      "unit_kind": "well",
      "capacity": 1,
      "status": "active",
      "created_at": "2026-03-31T14:00:00",
      "notes": null,
      "occupant_count": 1
    }
  ]
}
```

`unit_kind` values: `open` (simple petri dish), `well`, `lane`, `chamber`.

`status` values: `active`, `empty`, `retired`.

#### Create housing units

```
POST /dishes/{dish_id}/units
Content-Type: application/json
```

Single unit:
```json
{
  "unit_kind": "well",
  "position_label": "A1",
  "capacity": 1,
  "notes": null
}
```

Batch (e.g. 6-well plate):
```json
{
  "unit_kind": "well",
  "count": 6,
  "label_format": "well_plate"
}
```

`label_format` options:
- `"numeric"` (default): labels `1`, `2`, ..., `N`
- `"well_plate"`: row-major labels `A1`, `A2`, ..., `B1`, etc.

Returns `201`. Single creation returns the unit object. Batch returns
`{"created": ["17257_1:A1", "17257_1:A2", ...]}`.

#### Fetch a housing unit

```
GET /units/{unit_id}
```

Returns the unit object plus a `fish` array of current occupants:
```json
{
  "unit_id": "17257_1_WP1:A1",
  "dish_id": "17257_1_WP1",
  "position_label": "A1",
  "unit_kind": "well",
  "capacity": 1,
  "status": "active",
  "created_at": "2026-03-31T14:00:00",
  "notes": null,
  "fish": [
    {
      "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
      "dish_id": "17257_1_WP1",
      "subject_label": "A1",
      "sex": "unknown",
      "genotype": "Tg(elavl3:jRGECO1b)",
      "species": "Danio rerio",
      "created_at": "2026-03-31T14:22:01",
      "notes": null
    }
  ]
}
```

---

### Fish-to-unit assignment

#### Assign or move a fish

```
POST /fish/{fish_id}/assign
Content-Type: application/json

{
  "unit_id": "17257_1_WP1:A1",
  "reason": "initial"
}
```

`reason` values: `initial`, `transfer`, `terminated`, `experiment`.

If the fish already has a `current_unit_id`, this is treated as a move: the old
occupancy record is closed and a new one is opened. If this is the first
assignment, a new occupancy record is created.

Returns the updated fish object.

#### Occupancy history

```
GET /fish/{fish_id}/history
```

Response:
```json
{
  "items": [
    {
      "id": 1,
      "fish_id": "6a1f9b7b-...",
      "unit_id": "17257_1:open",
      "moved_in_at": "2026-03-20T10:00:00",
      "moved_out_at": "2026-03-25T09:00:00",
      "reason": "initial",
      "dish_id": "17257_1",
      "position_label": null,
      "unit_kind": "open"
    },
    {
      "id": 2,
      "fish_id": "6a1f9b7b-...",
      "unit_id": "17257_1_WP1:A1",
      "moved_in_at": "2026-03-25T09:00:00",
      "moved_out_at": null,
      "reason": "transfer",
      "dish_id": "17257_1_WP1",
      "position_label": "A1",
      "unit_kind": "well"
    }
  ]
}
```

Records with `moved_out_at: null` are current.

---

### Housing unit maintenance checks

#### Log a check

```
POST /units/{unit_id}/checks
Content-Type: application/json

{
  "check_time": "20260401T09:30:00",
  "fed": true,
  "feed_type": "paramecia",
  "water_changed": true,
  "vol_water_changed": 5,
  "num_dead": 0,
  "notes": null
}
```

`check_time` is required. All other fields are optional. Returns `201`.

#### Check history

```
GET /units/{unit_id}/checks
```

Returns `{"items": [...]}` ordered by `check_time` descending.

---

### Fish reference images

#### Upload an image

```
POST /fish/{fish_id}/images
Content-Type: multipart/form-data

file: <binary image data>     (required, JPEG or PNG)
caption: "dorsal view, GFP"   (optional)
```

Returns `201` with an HTML partial (image gallery). For programmatic use, call
`GET /fish/{fish_id}/images` after uploading to get the updated list.

Images are stored at `data/fish_images/{fish_id}/001.jpg`, `002.png`, etc.
Served at `/fish-images/{fish_id}/{filename}`.

#### List images

```
GET /fish/{fish_id}/images
```

Returns an HTML partial (image gallery with upload form). For JSON consumers,
query the database directly or use the file paths from the gallery.

---

> **Note:** Experiment session tracking (`POST /sessions`, `GET /sessions/*`,
> `GET /fish/{fish_id}/sessions`) was removed from MetaZebrobot. Session and
> run data belongs in **Palette**. See `docs/identity_and_provenance_contract.md`.

---

## Acquisition workflow

### Path A — fish already registered

Use this when fish were pre-registered via the web UI (e.g. well plate with
batch-registered fish).

1. `GET /dishes/{dish_id}/fish` — list registered fish
2. `GET /dishes/{dish_id}/units` — get housing layout (optional, for UI display)
3. Operator picks a fish → you have the `fish_id`
4. `GET /fish/{fish_id}` — get full context including `current_unit_id` (optional)
5. Snapshot into H5 (see below)

### Path B — fish not yet registered

Use this for anonymous petri dishes where no fish have been pre-registered.

1. Mint `fish_id = uuid4()` locally at acquisition time
2. Write it into the H5 `/subject_metadata` immediately
3. After transfer, the import pipeline calls
   `POST /dishes/{dish_id}/fish` with `{"fish_id": "<the-minted-uuid>"}`
   to back-register it

Both paths produce the same result: the same UUID in both the H5 and the
registry.

### Post-transfer session registration

After the H5 is transferred, the import pipeline registers the session in
**Palette** (not MetaZebrobot). Palette stores experiment sessions, fish runs,
and file assets. MetaZebrobot only handles fish identity and housing. See
`docs/identity_and_provenance_contract.md` for the full data flow.

---

## H5 snapshot contract

At acquisition time, snapshot the following into H5 `/subject_metadata`. These
are the facts that were true **at recording time** and make the H5 a
self-contained artifact.

### Required fields (when fish is individually tracked)

| Field | Source | Notes |
|-------|--------|-------|
| `fish_id` | `fish_subjects.fish_id` | UUID v4, the join key back to registry |
| `subject_count` | Number of fish in the session | Usually 1 for individual tracking |

### Recommended fields

| Field | Source | Notes |
|-------|--------|-------|
| `genotype` | `fish_subjects.genotype` or `dishes.genotype` | As known at recording time |
| `species` | `fish_subjects.species` or `dishes.species` | Usually "Danio rerio" |
| `sex` | `fish_subjects.sex` | |
| `dpf_at_run` | Computed: session date − `dishes.dof` | |
| `source_dish_id` | Origin dish (walk `parent_dish_id` if fish was moved) | Provenance |
| `source_cross_id` | `dishes.cross_id` | Provenance |
| `housing_unit_id` | `fish_subjects.current_unit_id` | Where the fish was at recording |
| `housing_unit_kind` | `housing_units.unit_kind` | `well`, `lane`, `chamber`, `open` |
| `housing_position_label` | `housing_units.position_label` | e.g. "A1", "3", null |

### What NOT to snapshot

These are registry-only — they accumulate over the fish's lifetime and don't
belong in a single recording:

- Full housing history (use `GET /fish/{fish_id}/history`)
- Other experiment sessions
- Screening results
- Maintenance / quality check logs

### Relationship to existing zebrobot_snapshot

The existing `/zebrobot_snapshot` (dish + cross metadata) is unchanged. Fish
tracking fields go into `/subject_metadata`. Both groups should be present in
the H5 when individual fish are tracked.

---

## Naming conventions (metadata cleanup)

Per the metadata cleanup recommendation
(`~/gitrepos/palette/docs/metadata_cleanup_recommendation.md`), use explicit
names to avoid ambiguity:

| Use | Instead of | Why |
|-----|-----------|-----|
| `subject_count` | `fish_count` | `fish_count` is ambiguous (session? dish? housing?) |
| `source_dish_id` | `dish_id` (in H5) | Distinguishes origin from current housing |
| `source_cross_id` | `cross_id` (in H5) | Explicit provenance |
| `housing_unit_id` | — | New field, no legacy alias |
| `fish_id` / `subject_id` | — | `fish_id` in MetaZebrobot, `subject_id` in Palette |

In the MetaZebrobot API itself, `dish_id` and `fish_id` retain their original
names. The renames apply to H5 `/subject_metadata` fields.
