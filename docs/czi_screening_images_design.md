---
title: "CZI Screening Images"
summary: "Link Zeiss .czi files as screening images: the acquisition settings ZEN's OME-TIFF export drops (filter cube, exposure, lamp, binning, zoom) are read from the CZI and shown with each image, and a cached OME-TIFF conversion feeds the existing preview and viewer."
owner: metazebrobot
status: current
kind: design
verified_against: 22bdd19
---

# CZI Screening Images

Status (2026-10-29): built.

## Why

Linked screening images are OME-TIFF exports from ZEN
([screening images](screening_images_design.md)). The export keeps the
channel (name, fluor, nominal 587/610 nm) but drops which filter cube was
in, the exposure time and the lamp intensity. In the October exports even
the filter pass bands were blank. So when a cross gave no positives, there
was no record of what the earlier positive screens had used.

The `.czi` original keeps all of it. Checked on two test snaps
(2026-10-29):

| Field | Where in the CZI metadata | Example |
|---|---|---|
| filter cube | `Information/Image/Dimensions/Channels/Channel/Reflector` | `63 HE mRFP` |
| exposure | `…/Channel/ExposureTime` (ns) | 150 ms |
| lamp, intensity | `Information/Instrument/LightSources/LightSource@Name`, `…/Channel/LightSourcesSettings/LightSourceSettings/Intensity` | X-Cite Xylis II, 99 % |
| camera, binning | `Scaling/AutoScaling/CameraName`, `…/Channel/DetectorSettings/Binning` | Axiocam 305, 1×1 |
| objective, zoom | `Scaling/AutoScaling/ObjectiveName`, `Information/Image/MicroscopeSettings/ZoomSettings/Magnification` | PlanNeoFluar Z 1.0x, 4.51× |
| pixel size | `Scaling/Items/Distance[@Id=X]/Value` (m) | 0.765 µm |
| acquired | `Information/Image/AcquisitionDateAndTime` (UTC) | 2026-10-29T16:40:13Z |
| channel | `…/Channel@Name`, `Fluor`, `Color` (#AARRGGBB), `Excitation/EmissionWavelength` | mCher, mCherry, red |

From now on the `.czi` is what gets saved to the staging folder.

## Design

- **Linking.** The import page lists `.czi` files alongside OME-TIFFs. On
  linking, the CZI metadata above is read once and stored on the link as
  `acquisition` (JSON), with the channels and image size as for OME-TIFFs.
- **Display.** The browser viewer (Avivator) and the PNG preview read
  OME-TIFF. For a `.czi`, the server converts it on first use to an
  OME-TIFF in the image cache (channel names, colours and pixel size
  carried over) and serves that at the existing
  `/image-links/{id}/image.ome.tiff`. The preview renders from the same
  file. Only the first plane of any Z, T or scene axis is used; screening
  snaps are single planes.
- **Download** (`/image-links/{id}/file`) still gives the original file.
- **Gallery.** Each image shows its cube, exposure, lamp intensity, binning
  and zoom, so a negative screen can be compared with a positive one.
- **Libraries.** `czifile` reads CZI (with `imagecodecs` for compressed
  files); `tifffile` writes the cached OME-TIFF. Both from conda-forge.
- Existing OME-TIFF links are unchanged.

## Not built

- Reading settings for OME-TIFF-only screens (October). They stay unknown.
- A filter cube and exposure field on the screening step itself, for screens
  without photos.
