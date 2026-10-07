---
title: "Web Page Capabilities"
summary: "Page-by-page map of the operator web UI."
owner: metazebrobot
status: current
kind: reference
verified_against: 384a366
---

# Web Page Capabilities

This is the current operator-facing page map for the FastAPI web UI.

## Global UI

- Top navigation links to Dishes, Screening, Care, Fish, References, PyRAT
  Tanks, PyRAT Crossings, and the guided tour.
- The user selector stores `metazebrobot_user` in a cookie and scopes PyRAT
  browsing to that user when `~/.pyrat_user_mapping.json` contains a matching
  PyRAT user ID.
- Scan boxes on the Screening and Care dish lists use QR/barcode label input
  to navigate directly to that dish's workflow.

## Home: `/`

- Landing page with links into the major workflows.
- Starts the guided walkthrough with sample `TOUR_` data.
- Links to new dish creation.

## Dishes: `/dishes/`

- Browse local dish inventory (all, active, or inactive) with a text filter on
  dish ID, cross ID, genotype, or responsible person.
- Start new-dish creation, dish count edits, transfers, terminations, batch
  termination of selected active dishes, and termination edits.
- Transfer fish into an existing compatible dish or create a new derived dish
  that inherits cross, provenance, husbandry metadata, and parent lineage. New
  transfer destinations use the next cross-level numeric dish ID.
- Print dish labels with QR codes.
- Follow links to screening, care, fish registration, cross lineage, and cross
  provenance.

## New Dish: `/dishes/new`

- Create local dishes from a PyRAT crossing or manual fields.
- Exact PyRAT cross lookup fills genotype, responsible person, parent tanks,
  cross setup/record dates, and parent/background provenance when available.
- A Parent Provenance table shows each parent's tank, strain, generation, and
  parsed background.
- The Refresh Crosses panel syncs the current user's PyRAT crosses from the
  last 30 days, or all visible crosses, into the local cache.

## Screening: `/screening/` and `/screening/{dish_id}`

- Browse active dishes and open a screening workflow.
- Log screening steps with DPF, indicators, pigment screening, tricaine, counts,
  notes, and allocation outcomes.
- Create derived dishes from screening allocations.
- Finalize aggregate screening count information.
- Display parsed transgene tags, mapzebrain atlas matches, and curated
  exact-genotype reference images.
- Upload JPEG/PNG evidence images per screening step; files are stored under
  `screening_images/{dish_id}/` and served at `/screening-images/...`.

## Daily Care: `/care/` and `/care/{dish_id}`

- Browse active dishes and see which have been checked today.
- Simple containers use a dish-level check form for feeding, feed type, water
  change, water volume changed, mortality, notes, and an optional JPEG/PNG care
  image.
- Feed type is a fixed choice: paramecia, rotifers, or brine shrimp (stored as
  `paramecia`, `rotifers`, `brine_shrimp`; defined in `models/fish_dish.py`).
  Other values are rejected by the form, the per-unit grid, and the
  `POST /units/{unit_id}/checks` API.
- Care images are stored under `care_images/{dish_id}/`, linked from the
  `quality_checks.image_filename` field, and displayed as thumbnails in recent
  check history.
- Well plates and other multi-unit dishes use a per-unit grid with batch
  controls for feeding and water changes.
- The current image upload is dish-level only; per-unit batch checks do not yet
  attach images.

## Fish: `/fish/`, `/dishes/{dish_id}/fish/`

- `/fish/` lists crosses that have registered fish, linking to each cross's
  fish page.
- The dish fish page registers individual fish, batch-registers fish, removes
  fish, and shows the current housing map. Assigning fish to housing units is
  API-only (`POST /fish/{fish_id}/assign`).
- Upload JPEG/PNG dish reference images (for bulk populations), stored under
  `dish_images/{dish_id}/` and served at `/dish-images/...`.
- Upload JPEG/PNG fish reference images, stored under `fish_images/{fish_id}/`
  and served at `/fish-images/...`.

## Cross Fish: `/crosses/{cross_id}/fish/`

- All registered fish for a cross, grouped by dish and nested by parent dish.
- Links to the cross lineage and provenance pages and to each dish's fish page.

## Cross Lineage: `/crosses/{cross_id}/lineage/`

- Graph of the cross's local dishes with screening-allocation and transfer
  edges (merges show as several edges into one dish); nodes open the dish's
  screening page.
- Tables of count adjustments, lineage events, and dishes.
- JSON form: `GET /crosses/{cross_id}/lineage`.

## Cross Provenance: `/crosses/{cross_id}/provenance/`

- Read-only view of the cached PyRAT cross (status, strain, responsible,
  setup/record dates, cache time).
- Parent background summary: background from parentage, inferred background,
  and the strain-name parse (backgrounds, line labels, mutant backgrounds,
  mixed background).
- Per-parent table: role, tank (with a Heritage link), strain (with former
  names), generation, birth date, producing cross, background, and label check.
- Local dishes for the cross, linking to their screening pages.
- JSON form: `GET /crosses/{cross_id}/provenance`.

## Tank Heritage: `/tanks/{tank_id}/heritage/`

- For a tank in cached PyRAT records: producing cross (and splits), cohort,
  backgrounds from records and inferred ones, and the label check.
- Lineage graph of tanks and crosses back 3 generations by default
  (`?generations=` up to 6); nodes open the tank's heritage or the cross's
  provenance page.
- A tank with no cached records gets a 404 page explaining how to resolve it.
- JSON form: `GET /tanks/{tank_id}/heritage`. Derivation rules:
  [`tank_heritage_design.md`](tank_heritage_design.md).

## References: `/references/`

- Manage curated exact-genotype reference images for screening.
- Upload manual PNG/JPEG reference images.
- Upload an OME-TIFF from the browser or use a server-side path (with a
  staging-file browser), preview its channel mapping, and generate
  composite/channel PNG reference images.
- Deactivate individual reference images or whole reference sets without
  deleting the underlying records.

## PyRAT Tanks: `/pyrat/tanks/`

- Fetch open PyRAT tanks through the configured PyRAT API credentials.
- Filter to the current user's `responsible_id` when the local user mapping is
  available.
- Show tank age status with color coding: urgent (over 365 days), warning
  (over 315 days), ok, or unknown.
- A Heritage column links each tank to `/tanks/{tank_id}/heritage/`.

## PyRAT Crossings: `/pyrat/crossings/`

- Fetch PyRAT crossings through the configured PyRAT API credentials.
- Filter to the current user's `responsible_id` when available.
- Show status, strain, crossing-tank count, raised count, performance, local
  dish count, and links to the cross's lineage, provenance, and new-dish pages.
- If PyRAT frontend credentials are configured, the table enriches rows from
  `backend/v1/tanks/crossings/{crossing_id}/details`.
- The detail table refreshes immediately on load and then every 5 minutes.
  If backend/v1 detail fetches return `401` or `403`, MetaZebrobot logs into
  the PyRAT frontend again once and retries the detail request.

## Labels: `/dishes/{dish_id}/label`

- Generate a 62x29mm, 300 DPI PNG label with dish metadata and a QR code.
- The QR code encodes the `dish_id` for USB scanner or phone-camera workflows.

## Guided Tour

- `POST /walkthrough/setup` creates temporary `TOUR_` data.
- `POST /walkthrough/cleanup` removes the tour rows and the tour dishes'
  `dish_images/` and `screening_images/` folders. It does not remove care
  images or per-fish image folders uploaded during a tour.
