# Web Page Capabilities

This is the current operator-facing page map for the FastAPI web UI.

## Global UI

- Top navigation links to Dishes, Screening, Care, Fish, References, PyRAT
  Tanks, PyRAT Crossings, and the guided tour.
- The user selector stores `metazebrobot_user` in a cookie and scopes PyRAT
  browsing to that user when `~/.pyrat_user_mapping.json` contains a matching
  PyRAT user ID.
- Scan boxes on dish-list pages use QR/barcode label input to navigate directly
  to the appropriate dish workflow.

## Home: `/`

- Landing page with links into the major workflows.
- Starts the guided walkthrough with sample `TOUR_` data.
- Links to new dish creation.

## Dishes: `/dishes/`

- Browse local dish inventory by active/inactive status.
- Start new-dish creation, dish count edits, transfers, and terminations.
- Transfer fish into an existing compatible dish or create a new derived dish
  that inherits cross, provenance, husbandry metadata, and parent lineage.
- Print dish labels with QR codes.
- Follow links to screening, care, fish registration, lineage, and provenance.

## New Dish: `/dishes/new`

- Create local dishes from a PyRAT crossing or manual fields.
- Exact PyRAT cross lookup fills genotype, responsible person, parent tanks,
  cross setup/record dates, and parent/background provenance when available.
- The Refresh Crosses panel syncs recent PyRAT crosses into the local cache.

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
- Care images are stored under `care_images/{dish_id}/`, linked from the
  `quality_checks.image_filename` field, and displayed as thumbnails in recent
  check history.
- Well plates and other multi-unit dishes use a per-unit grid with batch
  controls for feeding and water changes.
- The current image upload is dish-level only; per-unit batch checks do not yet
  attach images.

## Fish: `/fish/`, `/dishes/{dish_id}/fish/`

- Browse registered fish and open dish-level fish registration pages.
- Register individual fish, batch-register fish, assign fish to housing units,
  and view the current plate map.
- Upload JPEG/PNG fish reference images, stored under `fish_images/{fish_id}/`
  and served at `/fish-images/...`.

## References: `/references/`

- Manage curated exact-genotype reference images for screening.
- Upload manual PNG/JPEG reference images.
- Browse server-side OME-TIFF staging paths, preview reviewed OME-TIFF metadata,
  and generate composite/channel PNG reference images.
- Deactivate individual reference images or whole reference sets without
  deleting the underlying records.

## PyRAT Tanks: `/pyrat/tanks/`

- Fetch open PyRAT tanks through the configured PyRAT API credentials.
- Filter to the current user's `responsible_id` when the local user mapping is
  available.
- Show tank age status with color coding: urgent, warning, ok, or unknown.

## PyRAT Crossings: `/pyrat/crossings/`

- Fetch PyRAT crossings through the configured PyRAT API credentials.
- Filter to the current user's `responsible_id` when available.
- Show status, strain, local dish links, crossing-tank count, raised count, and
  performance.
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
- `POST /walkthrough/cleanup` removes the tour rows and uploaded tour image
  files from local storage.
