---
title: "Dish Photo Capture and Label Reading"
summary: "A Raspberry Pi in the aquatics room photographs dishes and sends them over an SSH tunnel to a capture inbox in MetaZebrobot; label text is read (local OCR or Claude Haiku) into suggestions a person confirms before the photo is attached to a dish. Larva counting comes later, trained on these photos."
owner: metazebrobot
status: current
kind: design
verified_against: b37bbdf
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
  - Needs Jeremy's OK before it is switched on.

Parsing the fields from the text depends on the sticker layout, which is
still to see (photo coming 2026-10-28). The cross id is matched against known
crosses, and the group is matched to the `source_group_id` format (see
`dish_source_group_design.md`). The suggestions fill the inbox picker;
nothing else changes until a person assigns the photo.

Measure before trusting: log each suggestion next to what was confirmed,
and report how often they agree for each reader.

## Later: barcodes on MetaZebrobot labels

MetaZebrobot already prints dish labels (`/dishes/{dish_id}/label`). A small
2D code (Data Matrix stays readable at a few mm) carrying the dish id would
make capture exact: decode, then no OCR. Citrus or a handheld scanner could "scan in"
a dish the same way. This needs a small label printer, chosen later. Until
then, OCR on the aquatics sticker covers the gap.

## Stage 3 (later): larva counts

Not designed yet. Stage 1 keeps every full-resolution photo and its confirmed
dish, which becomes the training and test set. Try simple backlit blob
counting first, then YOLO if larvae clump. Results would always be shown as
a suggested count, and corrections logged.

## Open questions

- Sticker photo and layout (2026-10-28).
- Camera module, lens and stand height; lightbox model.
- Local OCR or Haiku first (or both, compared on the same photos).
