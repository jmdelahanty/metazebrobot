# Web Screening UI Plan

A lightweight web interface for entering screening data at the microscope workstation, away from the main desktop app. Both share the same SQLite database.

## Architecture

```
Microscope Workstation (browser / phone)
        |
        v
  FastAPI Server (api_server.py)
        |
        v
  SQLite Database (zebrobot.db)  <-- Desktop App (PySide6)
```

## Tech Stack

- **FastAPI** (existing dependency, existing `api_server.py`)
- **Jinja2** (server-rendered HTML templates, already installed as FastAPI transitive dep)
- **HTMX** (single 14KB vendored JS file, no build step)
- **Pico CSS** (classless CSS framework, ~10KB, clean forms/tables with zero config)
- **No npm, no React, no JS build toolchain**

## Image Storage Decision

Microscope photos (1-5 MB each) stored on **filesystem with paths in the database**, not as SQLite BLOBs.

Layout:
```
data/screening_images/
  {dish_id}/
    {screening_datetime}_001.jpg
    {screening_datetime}_002.jpg
```

A `screening_step_images` table links images to steps by `(dish_id, screening_datetime)`, supporting multiple images per step (e.g., brightfield + GFP + RGeCO channels).

## Concurrency: Desktop + Web Coexistence

SQLite in WAL mode allows safe concurrent access. Readers never block writers and vice versa. At a few screening sessions per day, write contention is effectively zero. Both sides need `PRAGMA journal_mode = WAL` and `PRAGMA busy_timeout = 3000`.

---

## Phase 1: Screening Data Entry (no images)

### Server Setup

- [x] Add `PRAGMA journal_mode = WAL` and `PRAGMA busy_timeout = 3000` to `data_manager.get_connection()`
- [x] Initialize `data_manager` in FastAPI lifespan event (currently `api_server.py` uses raw sqlite3 connections; write endpoints need the controller)
- [x] Add Jinja2Templates setup to `create_app()` in `api_server.py`
- [x] Mount `StaticFiles` at `/static` for HTMX and CSS
- [x] Add `--lab-network` flag (or config) to bind `0.0.0.0` instead of `127.0.0.1`

### Static Assets

- [x] Vendor `htmx.min.js` into `src/metazebrobot/static/`
- [x] Vendor `pico.min.css` (or similar classless CSS) into `src/metazebrobot/static/`

### Templates

- [x] `templates/base.html` — layout with HTMX script, Pico CSS, nav bar
- [x] `templates/screening/dish_list.html` — table of active dishes with links to screening form
- [x] `templates/screening/screening_form.html` — main page: protocol display, existing steps table, add-step form, finalize section
- [x] `templates/screening/_steps_table.html` — HTMX partial: just the steps `<table>` rows (swapped in after adding a step)
- [x] `templates/screening/_flash_message.html` — HTMX partial: success/error banner

### API Endpoints

- [x] `GET /screening/` — dish picker page (active dishes only)
- [x] `GET /screening/{dish_id}` — screening form page for a specific dish
- [x] `POST /screening/{dish_id}/steps` — submit new screening step (calls `fish_dish_controller.add_screening_step()`, returns HTMX partial)
- [x] `POST /screening/{dish_id}/finalize` — submit final positive count (calls `fish_dish_controller.finalize_screening()`)
- [x] `GET /screening/{dish_id}/steps-table` — HTMX partial endpoint for refreshing the steps table

### Form Features

- [x] DPF auto-calculated from dish DOF + screening date (server-side on load, client-side on date change with minimal vanilla JS)
- [x] Indicator and criteria pre-filled from `screening_protocols.json` based on genotype and DPF
- [x] Protocol text display at top of form (mirrors desktop ScreeningDialog)
- [x] Reference indicator images displayed alongside protocol
- [x] HTMX: submitting a step updates steps table without full page reload

### Packaging

- [x] Add `jinja2` explicitly to `[project.optional-dependencies] api` in `pyproject.toml`
- [x] Add `templates/` and `static/` to package data

---

## Phase 2: Image Capture and Storage

### Schema Changes

- [x] Add `screening_step_images` table to `data_manager.py` `initialize()`:
  ```sql
  CREATE TABLE IF NOT EXISTS screening_step_images (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      dish_id TEXT NOT NULL,
      screening_datetime TEXT NOT NULL,
      image_filename TEXT NOT NULL,
      image_type TEXT DEFAULT 'screening',
      caption TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
  );
  ```
- [x] Add index on `(dish_id, screening_datetime)`

### Data Manager Methods

- [x] `save_screening_image(dish_id, screening_datetime, image_filename, image_type, caption)` — insert row into `screening_step_images`
- [x] `get_screening_images(dish_id, screening_datetime=None)` — query images for a step or all steps of a dish

### Image Configuration

- [x] Add `SCREENING_IMAGES_DIR` to config (default: `screening_images/` relative to database path)
- [x] Create directory on startup if it doesn't exist

### API Endpoints

- [x] `POST /screening/{dish_id}/steps/{screening_datetime}/images` — upload one or more images (uses FastAPI `UploadFile`)
- [x] `GET /screening/{dish_id}/steps/{screening_datetime}/images` — HTMX partial: image gallery for a step
- [x] Mount `StaticFiles` for serving uploaded images at `/screening-images`

### Upload Handling

- [x] Validate file type (JPEG, PNG only)
- [x] Generate filename: `{screening_datetime}_{sequence}.{ext}`
- [x] Save to `{SCREENING_IMAGES_DIR}/{dish_id}/`
- [x] Insert row into `screening_step_images`
- [x] Return HTMX partial with updated gallery

### Templates

- [x] `templates/screening/_image_gallery.html` — thumbnail grid with upload form
- [x] File input with `capture="environment"` (opens camera on mobile)
- [x] Image upload area appears per screening step (lazy-loaded via HTMX)

---

## Phase 3: Refinements

### Derived Dish Creation

- [ ] `POST /screening/{dish_id}/derive` — create derived dish from last screening step (calls `fish_dish_controller.create_derived_dish()`)
- [ ] `templates/screening/_derive_prompt.html` — confirmation form shown after step if negatives > 0
- [ ] HTMX: derive prompt appears inline after step submission

### Mobile / Microscope UX

- [ ] Single-column layout on narrow screens
- [ ] Touch-friendly input sizes
- [ ] Horizontal scroll for steps table on small screens
- [ ] Prominent camera capture button

### Desktop App Integration (optional, later)

- [ ] Display screening images in desktop ScreeningDialog by querying `screening_step_images` table
- [ ] Periodic cache refresh or notification when web UI writes new data

---

## Files to Create

```
src/metazebrobot/static/
  htmx.min.js
  pico.min.css

src/metazebrobot/templates/
  base.html
  screening/
    dish_list.html
    screening_form.html
    _steps_table.html
    _flash_message.html
    _image_gallery.html      (Phase 2)
    _derive_prompt.html      (Phase 3)
```

## Files to Modify

```
src/metazebrobot/api_server.py    -- Jinja2, static mounts, write endpoints, WAL mode, lifespan init
src/metazebrobot/data/data_manager.py  -- screening_step_images table, image methods, WAL pragma
pyproject.toml                    -- explicit jinja2 dep, package data for templates/static
```
