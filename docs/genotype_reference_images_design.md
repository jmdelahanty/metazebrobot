# Genotype Reference Images Design

## Purpose

Screening needs two different kinds of visual context:

- **Atlas reference**: broad promoter/line expectations from mapzebrain or other atlas sources.
- **Genotype reference**: curated lab examples for the exact full genotype being screened.

These should both appear on the screening page when available. The atlas panel answers
"what should this promoter generally label?" while the genotype panel answers "what
have we personally seen for this exact genotype?"

This document describes the genotype reference image layer and how it should coexist
with uploaded screening evidence images.

## Current State

The app already stores screening evidence images on the filesystem and records metadata
in SQLite:

```text
screening_images/
  {dish_id}/
    {screening_datetime}_001.jpg
    {screening_datetime}_002.jpg
```

The `screening_step_images` table links files to `(dish_id, screening_datetime)`.
This is the right pattern for raw evidence images. Full image payloads should not be
stored as SQLite BLOBs.

Observed staging data currently lives under:

```text
/groups/ahrens/ahrenslab/jeremy/screening_staging/
```

Example contents:

```text
17907_1/  PNG exports
17907_2/  OME-TIFF exports
17907_4/  OME-TIFF exports
17907_7/  OME-TIFF exports plus CZI originals
```

The OME-TIFF files inspected were 16-bit, 2464 x 2056, and sometimes two-channel.
This reinforces keeping raw images on disk and storing only metadata, paths, and
provenance in the database.

## Manual Fiji OME-TIFF Review

Until MetaZebrobot has an automated staging importer/preview generator, inspect
raw OME-TIFF screening images manually in Fiji. On Apple Silicon Macs, use the
macOS arm64 Fiji build.

Recommended Fiji import path:

```text
Plugins -> Bio-Formats -> Bio-Formats Importer
```

Recommended import options:

```text
View stack with: Hyperstack
Color mode: Colorized
Autoscale: on
Use virtual stack: on, for large files or network-mounted storage
Display OME-XML metadata: optional, useful for debugging channel metadata
```

The Zeiss Axio Zoom OME-TIFF metadata observed so far includes explicit OME
`Channel Color` values. Example:

```xml
<Channel Color="385810687" Fluor="Calcium Green-1" Name="CaGr1" ...>
<Channel Color="-16187137" Fluor="mCherry" Name="mCher" ...>
```

Those packed RGBA values decode to green for Calcium Green/CaGr1 and red for
mCherry/mCher. In Fiji, `Color mode: Composite` may still display the imported
channels as grayscale, while `Color mode: Colorized` correctly applies the channel
colors for these files.

If Fiji still displays grayscale, manually assign channel lookup tables:

```text
Image -> Color -> Channels Tool...
```

Current manual fallback mapping:

```text
CaGr1 / Calcium Green-1 -> Green
mCher / mCherry -> Red or Magenta
```

For curated MetaZebrobot genotype references, adjust the display in Fiji and export
a display-ready PNG/JPEG. Do not upload raw OME-TIFFs as genotype reference images.

MetaZebrobot can also generate these display-ready PNGs directly from the
Reference Library page. Operators can either choose an OME-TIFF from the browser
or paste a server-visible OME-TIFF path. Browser-selected files are staged in
`genotype_reference_ome_uploads/` next to the database before preview/import.
For server-visible files, the Reference Library also includes a Linux staging file
browser rooted at `/groups/ahrens/ahrenslab/jeremy/screening_staging` by default.
Set `METAZEBROBOT_OME_STAGING_ROOT` to override that root for another deployment.

The narrow first implementation expects a simple OME-TIFF with one Z plane, one T
point, and one plane per channel. It uses embedded OME channel metadata to:

- detect channel index, channel name, fluor/reporter label, and display color;
- suggest channel-to-transgene mappings from the exact genotype;
- generate one composite PNG plus one PNG per channel;
- save structured `genotype_reference_images` rows for the composite and channels.

For multi-channel positive fish, each imported or manually uploaded reference set
should include one composite and one PNG/JPEG per biologically meaningful channel:

```text
Full genotype:
Tg(elavl3:jGCaMP8f);Tg(her4.1:PMCA2-mCherry)

Composite:
display_role = composite

Green channel:
display_role = channel
transgene = Tg(elavl3:jGCaMP8f)
channel_name = CaGr1 or equivalent acquisition channel name
fluor = jGCaMP8f
color_hex = #16FF00 or the OME/Fiji display color

Red/magenta channel:
display_role = channel
transgene = Tg(her4.1:PMCA2-mCherry)
channel_name = mCher or equivalent acquisition channel name
fluor = mCherry
color_hex = #FF0900 or the OME/Fiji display color
```

The full genotype remains the matching key for the screening page. The transgene
metadata explains what each channel represents and allows future reuse/search.

## Storage Model

Keep three related but distinct concepts:

- **Raw image assets**: original OME-TIFF, CZI, PNG, or other acquisition files.
- **Preview images**: generated web-friendly thumbnails/PNGs for fast display.
- **Curated genotype references**: selected display-ready PNGs tied to exact full
  genotypes, with provenance back to the source image/dish/fish where possible.

Recommended directory layout:

```text
screening_images/
  {dish_id}/
    raw/
    previews/

genotype_reference_images/
  {reference_id}.png
```

The genotype reference directory should store display-ready PNGs, not raw OME-TIFFs.
Raw files remain in staging/archive storage or in `screening_images/{dish_id}/raw/`.

## Future Staging Convention

For future screening acquisitions, use folders named for the derived positive dish
when the images already belong to that derived population:

```text
screening_staging/
  17907_2_pos1/
    Snap-156-OME TIFF-Export-16.ome.tiff
    Snap-157-OME TIFF-Export-17.ome.tiff
```

This creates a simple importer rule:

```text
folder name == dish_id
```

For future well-plate workflows, use well-position subfolders:

```text
screening_staging/
  17907_2_pos1/
    A1/
      image.ome.tiff
    A2/
      image.ome.tiff
```

Then the importer can link the raw image to:

- the positive dish: `17907_2_pos1`
- the housing unit: `17907_2_pos1:A1`
- the fish occupying that well, if a fish assignment exists

## Proposed Schema

Use a general image catalog plus target links. This avoids making every image belong
to exactly one concept.

```sql
CREATE TABLE image_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_uri TEXT NOT NULL,
    original_filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    channel_count INTEGER,
    channels_json TEXT,
    physical_size_x REAL,
    physical_size_y REAL,
    sha256 TEXT,
    ome_metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE image_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    role TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES image_assets(id)
);

CREATE TABLE genotype_reference_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    genotype_key TEXT NOT NULL,
    display_genotype TEXT NOT NULL,
    reference_group_key TEXT,
    reference_group_label TEXT,
    image_filename TEXT NOT NULL,
    caption TEXT,
    display_role TEXT DEFAULT 'reference',
    display_order INTEGER DEFAULT 0,
    transgene_key TEXT,
    display_transgene TEXT,
    channel_index INTEGER,
    channel_name TEXT,
    fluor TEXT,
    color_hex TEXT,
    source_image_id INTEGER,
    source_dish_id TEXT,
    source_fish_id TEXT,
    channels_json TEXT,
    notes TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_image_id) REFERENCES image_assets(id)
);
```

Expected `genotype_reference_images.display_role` values:

```text
composite
channel
brightfield
other
reference
```

`reference_group_key` groups a composite and its single-channel derivatives into one
exact-genotype reference set. If no explicit set label is provided, the group key
falls back to `genotype_key`, so all existing legacy rows remain valid.

Expected `image_links.target_type` values:

```text
screening_step
dish
housing_unit
fish
```

Expected `image_links.role` values:

```text
raw_screening_capture
positive_screening_reference
well_reference
individual_reference
curation_source
```

## Matching Rules

Atlas and genotype references should use different matching rules.

Atlas reference:

- Match by parsed promoter/construct.
- Allow fallback matching, such as promoter-only mapzebrain matches.
- Use this for broad anatomical expectations.

Genotype reference:

- Match by exact canonical full genotype key.
- Do not fuzzy-match by default.
- Do not show a curated image for related but non-identical genotypes unless an
  explicit alias is added.

The first implementation can canonicalize conservatively by normalizing whitespace
and preserving the full genotype text. A later implementation can introduce a more
structured genotype parser and alias table.

## Screening Page UI

The screening page should show both reference panels independently:

```text
Parsed Constructs

Atlas Reference
  mapzebrain/promoter-based panel

Genotype Reference
  curated full-genotype panel

Screening Protocol
  DPF-specific protocol guidance

Screening Steps
  raw evidence uploads per step
```

If no curated genotype reference exists, the panel can be omitted or show:

```text
No curated genotype reference image for this exact genotype yet.
```

The genotype reference panel should display:

- reference PNG
- caption
- exact genotype string used for matching
- source dish/fish link if known
- source image link if available

## Curation Workflow

Initial workflow:

1. Import raw screening images from staging into the image catalog.
2. Generate preview PNGs for web display.
3. In the screening image gallery, provide a `Mark as genotype reference` action.
4. The action writes a display-ready PNG to `genotype_reference_images/`.
5. The action creates a `genotype_reference_images` row with provenance to the
   source image and current dish/fish when known.

This should be an explicit user action. The importer should not automatically decide
that a raw image is a "good" genotype reference.

## Importer Responsibilities

A future importer should:

- Traverse staging folders using the folder name as `dish_id`.
- Parse OME metadata when present: dimensions, channel count, channel names,
  physical pixel size, and embedded OME XML.
- Record original file size and SHA256 for deduplication/reconciliation.
- Generate a preview PNG/thumbnail for browser display.
- Link images to a dish immediately.
- Link images to a housing unit/fish when folder structure and occupancy data make
  that unambiguous.
- Leave ambiguous images as dish-level or unassigned until manually curated.

## Non-Goals

- Do not store raw image bytes in SQLite.
- Do not make the mapzebrain atlas panel and genotype reference panel mutually
  exclusive.
- Do not fuzzy-match curated genotype reference images by default.
- Do not force every raw image to become a genotype reference.

## Open Questions

- Where should canonical genotype aliases live if exact full-genotype matching is
  too strict for real usage?
- Should source OME-TIFF/CZI files be copied into MetaZebrobot-managed storage or
  referenced in place from group storage?
- What image conversion stack should be used for OME-TIFF and CZI previews?
  Current OME-TIFF reference generation uses Pillow/numpy for simple OME-TIFFs,
  but `tifffile`/`aicsimageio` may be needed for robust multi-channel microscopy
  data and CZI support.
- Should curated genotype references be versioned, or is `is_active` enough for
  the first implementation?

## Suggested Implementation Phases

1. [x] Add `genotype_reference_images` table and managed PNG directory.
2. [x] Add `GET /screening/{dish_id}/genotype-reference` HTMX partial.
3. [x] Add the `Genotype Reference` panel below the existing `Atlas Reference` panel.
4. [x] Add a read-only reference library page for curated genotype references.
5. [x] Add a simple manual upload/admin path for genotype reference PNGs/JPEGs.
6. [x] Add structured reference-set metadata for composite/channel/transgene display.
7. [x] Add narrow OME-TIFF-to-reference PNG generation with reviewed channel mapping.
8. Add image catalog and staging importer for OME-TIFF/PNG files.
9. Add `Mark as genotype reference` from existing screening image galleries.
10. Extend linking to housing units and fish for well-plate workflows.
