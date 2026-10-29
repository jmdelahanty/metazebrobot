---
title: "Dish Photo Capture and Label Reading"
summary: "A Raspberry Pi in the aquatics room photographs dishes and sends them over an SSH tunnel to a capture inbox in MetaZebrobot; label text is read (local OCR or Claude Haiku) into suggestions a person confirms before the photo is attached to a dish. Larva counting comes later, trained on these photos."
owner: metazebrobot
status: current
kind: design
verified_against: 25ad83c
---

# Dish Photo Capture and Label Reading

Status (2026-10-27): design, not built. Stages 1–2 agreed; stage 3 later.

## Goal

Save time when inventorying dishes. Take one photo of a dish in the
aquatics room and get:

1. the photo attached to the right dish (stage 1);
2. the label read, so cross id and crossing tank group are suggested
   rather than typed (stage 2);
3. later, a suggested larva count (stage 3, not designed here).

A person always confirms. Nothing read from a photo is saved as fact without
that.

## Stage 1: capture inbox

### Network

The service stays bound to `127.0.0.1:8000`, because it has no login. The Pi is on
the same network as the workstation and reaches the service the same way
Jeremy does: an SSH local forward.

- A dedicated SSH key for the Pi, in the workstation account's
  `authorized_keys`, restricted to that one forward and nothing else:
  `restrict,port-forwarding,permitopen="127.0.0.1:8000" ssh-ed25519 …`.
  The key can't open a shell or reach any other port.
- On the Pi, a systemd unit keeps the tunnel up (`ssh -N -L
  8000:127.0.0.1:8000 …` with `ServerAliveInterval` and restart on failure).
- The Pi posts to `http://localhost:8000/captures`.

### Pi side (`scripts/pi_capture/`)

- Camera module over a lightbox, at a fixed height in a simple stand, so every
  photo has the same scale and lighting. That matters for both OCR and counting.
- A button (GPIO) or keypress takes a full-resolution photo with picamera2.
- Each photo is written to a local spool first, then uploaded. A failed upload
  stays in the spool and is retried, so a dropped tunnel loses nothing.
- Sent fields: the image, the capture time, and a station name (e.g.
  `aquatics-pi-1`).

### Server side

- `POST /captures` (multipart). It stores the file under a captures directory
  next to the dish images, then records a row in a new table:

  | column | meaning |
  |---|---|
  | `capture_id` | uuid |
  | `filename`, `sha256` | stored file; duplicates by hash are refused |
  | `captured_at`, `station` | from the Pi |
  | `status` | `unassigned` / `assigned` / `discarded` |
  | `dish_id`, `assigned_by`, `assigned_at` | set on confirm |
  | `suggested` | JSON from label reading (stage 2) |
  | `reader`, `reader_text` | which reader ran and its raw output |

- `/captures/` lists unassigned photos, newest first. Each card shows the photo,
  a dish picker (prefilled from suggestions once stage 2 exists) and
  Assign / Discard buttons.
- On assignment, the file is linked as a dish image (new `image_type`
  `capture`), using the existing dish image storage, so it appears in the dish
  gallery.
- Why an inbox rather than choosing the dish on the Pi: the Pi has no screen,
  and the inbox keeps the confirm step in one place.

Limitation: aquatics staff can't open the web app (localhost only), so for now
Jeremy (or anyone with a tunnel) works through the inbox.

## Stage 2: reading the label

The aquatics stickers are printed text, with no barcode.

A small reader interface: `read(image) -> {text, cross_id?, group?, dish_number?,
confidence}`. The reader is chosen in config, and both kinds below can be
added:

- **Local OCR**, on the workstation or the Pi.
  - Tesseract: light and fast, fine for clean printed text with fixed lighting.
  - PaddleOCR: better on small, angled or curved text.
  - Images stay on the network. This kind needs a crop or a fixed label
    position to work well.
- **Claude Haiku** (`claude-haiku-5-5`) through the API, with a structured-output
  prompt that returns the fields above.
  - Handles odd layouts, glare and partial occlusion better than classic OCR,
    with no crop tuning. The cost per photo is small.
  - The photo is sent to an outside service. The API key lives on the
    workstation only, never on the Pi.
  - Uses Jeremy's HHMI API account (agreed 2026-10-28). Off by default; turned on
    in config.

### The aquatics sticker (seen 2026-10-28)

A printed table, about 38 × 76 mm (likely 1.5" × 3" stock), on the lid of a
90 mm dish. The cells are labelled and always in the same place:

| Cell | Example | Use |
|---|---|---|
| Crossing | `19445` | cross id |
| # | `1` | crossing tank group, saved as `source_group_id` `19445-G1` |
| Line/Strain | `Tg(gfap:PMCA2-mCherry-zf)` | check against the cross strain |
| Parent #1 / #2 | `#8132 M13 > A4` + strain | parent tank, rack, position |
| Responsible | `Delahanty Jeremy` | not used |
| DOF | `10/23/26` | suggested DOF (MM/DD/YY) |

The suggestions fill the inbox picker; nothing else changes until a person
assigns the photo. If no dish exists yet for that cross and group, the picker
offers "new dish" with the cross id, group and DOF prefilled.

**Parent cross-check.** The parent cells carry the same form MZB already stores
per dish (`#8132_M13>A4`). The reader compares them with the cross's PyRAT
parents and flags a mismatch, such as a tank that isn't on the cross or a
strain that differs. This answers "does the sticker match what was set up?"
without anyone typing it.

**Hard parts.**
- People draw over the cells by hand: boxes around the group digit and a parent
  tank, and words like "SCRN". This can break classic OCR on exactly the group
  digit. Haiku should cope; compare the two on the same photos.
- Condensation drops and lid glare. Light the dish from below through a diffuser
  and angle the camera slightly, or use a polarizer.

Measure before trusting: log each suggestion next to what was confirmed,
and report how often they agree for each reader.

## Later: barcodes on MetaZebrobot labels

MetaZebrobot already prints dish labels (`/dishes/{dish_id}/label`). A small
2D code (Data Matrix stays readable at a few mm) carrying the dish id would
make capture exact: decode, then no OCR. Citrus or a handheld scanner could "scan in"
a dish the same way. Until then, OCR on the aquatics sticker covers the gap.

Space on the lid (measured 2026-10-28): beside the sticker there is a band of
about 21–30 mm on each side at the widest, narrowing toward the rim. A label
about 12–14 mm deep fits there. A 10 mm Data Matrix holding a dish id reads
reliably from a fixed camera.

Printer: see the purchase list. A Brother QL-820NWB (network; `brother_ql` drives
it with no driver) with 29 mm water-resistant film tape (DK-2211), cut about
14 mm long and placed with its 29 mm side along the sticker. The 12 mm QL roll
(DK-22214) is paper, and its water resistance is listed both ways, so it
isn't relied on. The fallback is a Brother P-touch with laminated 12 mm TZe
tape (tougher, but driven from Linux only by community tools).
`label_generator.py` gets a small layout for the chosen tape.

## Stage 3 (later): larva counts

Not designed yet. Stage 1 keeps every full-resolution photo and its confirmed
dish, which becomes the training and test set. Try simple backlit blob
counting first, then YOLO if larvae clump. Results would always be shown as
a suggested count, and corrections logged.

## Open questions

- Camera: Pi Camera Module 3, or one of the lab's Teledyne FLIR USB3 cameras.
  FLIR's Spinnaker SDK supports ARM64 Linux (Ubuntu 20.04/22.04) and FLIR tested
  a Blackfly S on a Pi 4. A Pi 5 isn't named. Fallback: Aravis (open source,
  USB3 Vision).
- Lens and stand height for a field of about 110 × 110 mm; lightbox model.
- Local OCR or Haiku first (or both, compared on the same photos).
