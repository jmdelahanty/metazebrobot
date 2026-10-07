---
title: "Fish Tracking API"
summary: "API for individual fish and housing units, and snapshotting fish metadata at acquisition."
owner: metazebrobot
status: current
kind: reference
verified_against: 384a366
---

# Fish Tracking API

This document describes the MetaZebrobot API endpoints for individual fish
tracking and housing unit management, and how fish identity relates to the H5
metadata that acquisition systems write.

The meaning of the identity fields (`dish_uuid`, `revision`, `updated_at`), the
structured error shapes, timestamp conventions, and stability promises for the
consumer endpoints `GET /dishes/{dish_id}/fish` and `GET /fish/{fish_id}` are
owned by [`zebrobot_snapshot.md`](zebrobot_snapshot.md); their response shapes
are pinned in [`api/consumer_openapi.json`](api/consumer_openapi.json). The
other endpoints below are not part of that pinned contract.

## API access

Same as the dish/cross API; see [API access](zebrobot_snapshot.md#api-access).

## Core concepts

- **fish_id** — UUID v4 (`8-4-4-4-12` hex, lowercase). Durable identity for
  one fish. Minted either by MetaZebrobot (web UI / batch registration) or by
  Citrus at acquisition time and back-registered later. MetaZebrobot stores a
  caller-supplied `fish_id` as-is and does not validate its format.
- **housing_unit** — A physical position within a dish: a well, lane, chamber,
  or the entire dish for simple petri dishes. Has its own `unit_id`
  (`{dish_id}:{position_label}`, or `{dish_id}:open` when created without a
  position label).
- **dish_id** — The dish the fish was registered on. Register fish on the dish
  they live in: for derived dishes (well plates, sorted populations), that is
  the derived dish, not the original source. `POST /fish/{fish_id}/assign`
  does not change a fish's `dish_id`, even when the unit belongs to another
  dish; current housing is `current_unit_id`, and that unit carries its own
  `dish_id`.
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
      "dish_uuid": "b833f00a-0e75-42ab-aebf-8a44a852c7f8",
      "subject_label": "A1",
      "sex": "unknown",
      "genotype": "Tg(elavl3:jRGECO1b)",
      "species": "Danio rerio",
      "created_at": "2026-03-31 14:22:01",
      "notes": null,
      "current_unit_id": "17257_1_WP1:A1",
      "revision": 2,
      "updated_at": "2026-03-31 15:02:44"
    }
  ]
}
```

Items are ordered by `created_at`. `current_unit_id` is `null` if the fish has
not been assigned to a housing unit. `dish_uuid` is that of the fish's
`dish_id`; `revision` and `updated_at` belong to the fish record itself (see
[Identity and change detection](zebrobot_snapshot.md#identity-and-change-detection)).
`created_at` and `updated_at` are UTC (see
[Dates and times](zebrobot_snapshot.md#dates-and-times)).

Errors use the structured shape in
[API errors](zebrobot_snapshot.md#api-errors): `404` `dish_not_found` for an
unknown dish, `503` `database_error` on a SQLite failure.

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

Returns `404` if the dish does not exist, with `{"detail": "Dish not found"}`
(a plain string, not the structured shape). Returns `500` if the insert fails,
for example because the `fish_id` is already registered.

#### Fetch a fish by UUID

```
GET /fish/{fish_id}
```

Returns the fish object (same shape as the list items above). Errors use the
structured shape: `404` `fish_not_found`, `503` `database_error` (see
[API errors](zebrobot_snapshot.md#api-errors)).

#### Update a fish

```
PATCH /fish/{fish_id}
Content-Type: application/json

{"subject_label": "B2", "notes": "moved wells"}
```

Accepted fields: `subject_label`, `sex`, `genotype`, `species`, `notes`.
Other fields are ignored.

Returns the updated fish object. `404` if the fish does not exist.

#### Delete a fish

```
DELETE /fish/{fish_id}
```

Returns `204` on success, `404` if not found. The fish's occupancy history and
reference-image records are deleted with it.

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
      "created_at": "2026-03-31 14:00:00",
      "notes": null,
      "occupant_count": 1
    }
  ]
}
```

`occupant_count` is the number of fish whose `current_unit_id` is this unit.
An unknown `dish_id` returns an empty `items` list, not a `404`.

`unit_kind` values in use: `open` (simple petri dish; the default), `well`,
`lane`, `chamber`. The API does not validate the value.

`status` is `active` when a unit is created. No endpoint currently changes it.

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

`unit_kind` defaults to `open` and `capacity` to 1. Without `position_label`
the unit id is `{dish_id}:open`.

Batch (`count` greater than 1):
```json
{
  "unit_kind": "well",
  "count": 6,
  "label_format": "well_plate"
}
```

`label_format` options:
- `"numeric"` (default): labels `1`, `2`, ..., `N`
- `"well_plate"`: row-major labels over rows `A`-`H`. With a `count` of 8 or
  fewer, every unit is in row `A` (6 gives `A1`-`A6`). With a larger count,
  each row gets `ceil(count / 8)` columns (96 gives `A1`-`H12`; 24 gives
  `A1`-`A3`, `B1`-`B3`, ..., `H3`). This does not match the physical layout of
  standard 6-, 12- or 24-well plates.

Batch units always get `capacity` 1; `position_label`, `capacity`, and `notes`
are ignored.

Returns `201`. Single creation returns the unit object. Batch returns
`{"created": ["17257_1:A1", "17257_1:A2", ...]}`. Returns `404` if the dish
does not exist, and `500` if the insert fails (for example, a `unit_id` that
already exists).

#### Fetch a housing unit

```
GET /units/{unit_id}
```

Returns the unit object plus a `fish` array of current occupants (`404` if
the unit does not exist):
```json
{
  "unit_id": "17257_1_WP1:A1",
  "dish_id": "17257_1_WP1",
  "position_label": "A1",
  "unit_kind": "well",
  "capacity": 1,
  "status": "active",
  "created_at": "2026-03-31 14:00:00",
  "notes": null,
  "fish": [
    {
      "fish_id": "6a1f9b7b-3b2a-4d7a-8a73-0b2d7c9e3d1a",
      "dish_id": "17257_1",
      "subject_label": "A1",
      "sex": "unknown",
      "genotype": "Tg(elavl3:jRGECO1b)",
      "species": "Danio rerio",
      "created_at": "2026-03-31 14:22:01",
      "notes": null
    }
  ]
}
```

Occupant entries are a subset of the fish object: they omit `dish_uuid`,
`current_unit_id`, `revision`, and `updated_at`. An occupant's `dish_id` is
the dish it was registered on, which can differ from the unit's `dish_id`.

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

`unit_id` is required (`422` if missing). `reason` is stored as free text and
not validated; the conventional values are `initial`, `transfer`,
`terminated`, `experiment`. It defaults to `transfer` when omitted, including
on a first assignment.

If the fish already has a `current_unit_id`, this is treated as a move: the old
occupancy record is closed and a new one is opened. If this is the first
assignment, a new occupancy record is created. The unit may belong to any
dish; the fish's `dish_id` does not change.

Returns the updated fish object; its `revision` increases because
`current_unit_id` changed. `404` if the fish or the unit does not exist.

There is no web UI control for assignment yet; use this endpoint.

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
      "moved_in_at": "2026-03-20 10:00:00",
      "moved_out_at": "2026-03-25 09:00:00",
      "reason": "initial",
      "dish_id": "17257_1",
      "position_label": null,
      "unit_kind": "open"
    },
    {
      "id": 2,
      "fish_id": "6a1f9b7b-...",
      "unit_id": "17257_1_WP1:A1",
      "moved_in_at": "2026-03-25 09:00:00",
      "moved_out_at": null,
      "reason": "transfer",
      "dish_id": "17257_1_WP1",
      "position_label": "A1",
      "unit_kind": "well"
    }
  ]
}
```

Records with `moved_out_at: null` are current. Records are ordered by
`moved_in_at`; `moved_in_at` and `moved_out_at` are UTC (SQLite
`CURRENT_TIMESTAMP`). `dish_id`, `position_label`, and `unit_kind` describe
the unit. `404` if the fish does not exist.

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

`check_time` is required (`422` if missing); the web UI sends lab-local
`YYYYMMDDTHH:MM:SS`. All other fields are optional. `feed_type` must be one of
`paramecia`, `rotifers`, `brine_shrimp` (display labels such as
`Brine shrimp` are also accepted, case-insensitively); anything else returns
`422` with `{"error": "invalid_feed_type", ...}`. `num_dead` must be
non-negative. Logging a check again for the same unit and `check_time`
replaces the earlier one.

Returns `201` with `{"status": "ok"}`. `404` if the unit does not exist.

#### Check history

```
GET /units/{unit_id}/checks
```

Returns `{"items": [...]}` ordered by `check_time` descending. Each item has
`id`, `unit_id`, `check_time`, `fed`, `feed_type`, `water_changed`,
`vol_water_changed`, `num_dead`, `notes`, `created_at`.

---

### Dish-level daily care checks

The web care page chooses this form when the dish has no housing units or a
single `open` unit (simple containers such as petri dishes, beakers, and
tanks). Dishes with other housing units get the per-unit form instead.

#### Log a dish-level check

```
POST /care/{dish_id}/check
Content-Type: multipart/form-data

check_time: "20260401T09:30:00"   (required)
fed: true                         (optional, default false)
feed_type: "paramecia"            (optional)
water_changed: true               (optional, default false)
vol_water_changed: 50             (optional)
num_dead: 0                       (optional)
notes: "dirty dish"               (optional)
care_image: <binary image data>   (optional, JPEG or PNG)
```

Returns an HTML partial containing the recent check table; an unknown
`feed_type` or image type returns the same partial with an error message. If
`care_image` is provided, the file is stored under `care_images/{dish_id}/`
next to the database as `{check_time}_{NNN}.jpg` or `.png` (characters that
are unsafe in file names replaced with `_`), served at
`/care-images/{dish_id}/{filename}`, and linked from
`quality_checks.image_filename`.

#### Recent dish-level checks

```
GET /care/{dish_id}/checks-table
```

Returns an HTML partial. Dish-level rows include an image thumbnail when a
care image is attached. For well plates or other multi-unit dishes, the same
partial shows per-unit check history; per-unit batch checks do not currently
attach images.

---

### Fish reference images

#### Upload an image

```
POST /fish/{fish_id}/images
Content-Type: multipart/form-data

file: <binary image data>     (required, JPEG or PNG)
caption: "dorsal view, GFP"   (optional)
```

Returns `200` with an HTML partial (image gallery); a file that is not JPEG or
PNG returns `200` with an error-message partial. `404` if the fish does not
exist.

Images are stored in `fish_images/{fish_id}/` next to the database, numbered
in upload order (`001.jpg`, `002.png`, etc.), and served at
`/fish-images/{fish_id}/{filename}`.

#### List images

```
GET /fish/{fish_id}/images
```

Returns an HTML partial (image gallery with upload form). There is no JSON
endpoint for fish images.

---

> **Note:** Experiment session tracking (`POST /sessions`, `GET /sessions/*`,
> `GET /fish/{fish_id}/sessions`) was removed from MetaZebrobot. Session and
> run data belongs in **Palette**. See `docs/identity_and_provenance_contract.md`.

---

### Plate map visualization

```
GET /dishes/{dish_id}/plate-map
```

HTMX partial. For well plates, renders a CSS grid with occupied wells (green)
and fish labels. For open containers, renders a simple occupant list.
Includes an "Unassigned fish" section for fish not assigned to any unit.

---

### Dish labels (QR code)

```
GET /dishes/{dish_id}/label
```

Returns a PNG image (62x29mm at 300 DPI) with dish ID, genotype, DOF, current
fish count (falling back to the initial `fish_count`), container type, and a
QR code encoding the dish_id. Designed for label printers (Brother QL series)
or browser printing. `404` if the dish does not exist.

#### Scanner hardware notes

The labels intentionally encode only the `dish_id`, so a scanner can behave
like a keyboard: scan the QR code into a focused scan box, emit Enter, and the
web UI navigates to the relevant dish workflow.

Recommended scanner requirements:

- Use a **corded 2D imager**, not a 1D-only laser scanner. The current labels
  are QR codes.
- Confirm support for **USB HID / keyboard wedge / keyboard emulation** mode.
- Configure the scanner to append **Enter/CR** after each scan.
- Test by opening a text editor: scanning a label should type a value like
  `17990_7_pos1` and then submit a newline.
- Prefer corded USB for the lab workstation first; it avoids Bluetooth pairing,
  battery, and reconnect issues.

Manufacturer-validated examples:

- [Zebra DS2208](https://www.zebra.com/us/en/products/scanners/general-purpose-handheld-scanners/ds2200-series/ds2208.html):
  corded handheld scanner; Zebra lists 1D/2D scan support. The
  [DS2200 Series spec sheet](https://www.zebra.com/us/en/products/spec-sheets/scanners/general-purpose-scanners/handheld/ds2200-series.html)
  lists USB and Keyboard Wedge host interfaces.
- [Honeywell Voyager XP 1470g](https://automation.honeywell.com/us/en/products/productivity-solutions/barcode-scanners/general-purpose-handheld/voyager-xp-1470g-general-duty-scanner):
  corded 2D engine; Honeywell lists 1D/2D decode capability and USB/KBW host
  interfaces.
- [Datalogic QuickScan 2500 Series](https://www.datalogic.com/eng/retail-manufacturing-healthcare/handheld-scanners/quickscan-2500-series-pd-898.html):
  entry-level corded 2D handheld imager; Datalogic describes the QD2500 as a
  corded scanner that reads 1D and 2D barcodes.

Approximate US street pricing checked 2026-04-24:

- Datalogic QuickScan QD2500 / QD2590-BKK1 USB kit: about **$117-$123**.
- Zebra DS2208 USB kit / DS2208-SR7U2100SGW: about **$193-$208**.
- Honeywell Voyager XP 1470g USB kit: about **$180-$234** depending on kit.

For first lab validation, the Datalogic QD2590-BKK1 is the lowest-cost
reasonable test unit. The Zebra DS2208 USB kit is a conservative institutional
choice if purchasing prefers Zebra hardware. When comparing prices, verify that
the listing includes the scanner, USB cable, and preferably a stand; scanner-only
listings often look cheaper but require extra accessories.

---

### Transgene data

The `dish_transgenes` table stores parsed promoter/reporter/fluorophore
data for each dish. Auto-populated when a dish is saved.

Filter dishes by promoter (exact match on the parsed promoter; the query value
is lowercased):

```
GET /dishes?promoter=elavl3
```

---

## Acquisition workflow

The API calls below are MetaZebrobot's. What the acquisition system writes into
its H5 file is owned by that system (see
[H5 snapshot contract](#h5-snapshot-contract)).

### Path A — fish already registered

Use this when fish were pre-registered via the web UI (e.g. well plate with
batch-registered fish). The web UI registers fish only; housing units are
created and fish assigned through `POST /dishes/{dish_id}/units` and
`POST /fish/{fish_id}/assign`.

1. `GET /dishes/{dish_id}/fish` — list registered fish
2. `GET /dishes/{dish_id}/units` — get housing layout (optional, for UI display)
3. Operator picks a fish → you have the `fish_id`
4. `GET /fish/{fish_id}` — get full context including `current_unit_id`,
   `dish_uuid`, and `revision` (optional)
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

> **Consumer-owned.** The H5 layout is owned by the system that writes it.
> Citrus documents its `/subject_metadata` group in its repository's
> `docs/Understanding_H5_Log.md` (Session Metadata Groups) and its subject
> fields in `docs/subject_identity_and_selection.md`. The tables below are
> MetaZebrobot's original recommendation of what to record and where each
> value comes from in MetaZebrobot; they do not describe what Citrus writes
> today.

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
| `dpf_at_run` | Computed: session date − `dishes.dof` | Use the lab-local session date, as for [`dpf_at_acquisition`](zebrobot_snapshot.md#derived-fields-optional-recommended) |
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

Per Citrus's metadata cleanup recommendation (`docs/metadata_cleanup_recommendation.md`
in the Citrus repository), use explicit names to avoid ambiguity:

| Use | Instead of | Why |
|-----|-----------|-----|
| `subject_count` | `fish_count` | `fish_count` is ambiguous (session? dish? housing?) |
| `source_dish_id` | `dish_id` (in H5) | Distinguishes origin from current housing |
| `source_cross_id` | `cross_id` (in H5) | Explicit provenance |
| `housing_unit_id` | — | New field, no legacy alias |
| `fish_id` / `subject_id` | — | `fish_id` in MetaZebrobot, `subject_id` in Palette |

In the MetaZebrobot API itself, `dish_id` and `fish_id` retain their original
names. The renames apply to H5 `/subject_metadata` fields.
