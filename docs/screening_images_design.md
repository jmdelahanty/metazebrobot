---
title: "Screening Images on Dishes and Fish"
summary: "Link screening and propagation OME-TIFFs on lab storage to dishes and individual fish by reference, with cached previews in the web app; no image data in SQLite."
owner: metazebrobot
status: current
kind: design
verified_against: 52ebae1
---

# Screening Images on Dishes and Fish

Status (2026-10-15): being built.

## Goal

Screening produces OME-TIFF snapshots under the screening staging root
(`/groups/ahrens/ahrenslab/jeremy/screening_staging`, setting
`METAZEBROBOT_OME_STAGING_ROOT`). Folders are named by dish (`19327_6_pos1`),
sometimes by cross (`19327`). Jeremy wants to see them in the web app for a
dish's fish as a group (including propagated dishes, whose fish have no
individual ids) and, where possible, for each individual fish.

## Decisions

- **Links, not copies or blobs** (Jeremy, 2026-10-15). Files stay on lab
  storage, the one owner. SQLite stores a reference per file: its path
  relative to the staging root, size, sha256 (to notice moves or edits), OME
  channel metadata, the dish, and the fish if known. 309 files / 2.8 GB
  already: storing them in the database would bloat it and its backups.
- **Previews are derived and cached:** a composite PNG per image, rendered by
  the existing OME export (`utils/ome_reference_export.py`) on first view,
  into a cache directory (`METAZEBROBOT_IMAGE_CACHE`, default
  `/nvme1/metazebrobot_image_cache`). Deleting the cache only costs
  re-rendering.
- **Linking is an explicit import:** scan a folder, review the proposed
  matches, then link. Unmatched files are shown, not guessed.
  - **Dish:** a folder named like an existing dish proposes that dish. Any
    other folder (e.g. a cross folder) needs a dish chosen once. The `19327`
    folder holds the positives propagated as 19327_4_pos1.
  - **Fish:** a well label at the end of a filename's leading token
    (`…_A1-OME TIFF-Export-01`, `A3-OME TIFF-…`) proposes the fish that was in
    that well, recorded by fish id so later moves don't break the link. The
    match uses the well, not the dish text, so the `19372_6_pos1_A2` typo still
    matches A2.
  - **Kind:** `screening`, `propagation` or `plate`, chosen at import.
- **Scope now:** OME-TIFF only. Older folders with PNG/JPEG exports (e.g.
  `17907_1`) are deferred (Jeremy, 2026-10-15).

## In the app

- Dish fish page: a gallery of the dish's linked images (thumbnails →
  larger preview, file path, channels).
- Fish timeline page: that fish's images; the timeline gets an "imaged" entry.
- JSON: import page `/image-links/import`; `GET /dishes/{dish_id}/image-links`, `GET /fish/{fish_id}/image-links`
  (not in the pinned consumer slice yet).
