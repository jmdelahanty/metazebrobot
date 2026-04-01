# Individual Fish Tracking Plan

Track individual fish from registration through experiments. A UUID assigned in MetaZebrobot flows through the pipeline: MetaZebrobot → Citrus (acquisition) → Palette (ingestion) → Crimson (analysis).

**Implementation status:** Phases 1, 2, 2b, and 3 are complete — fish subject CRUD, web UI, housing unit management, and reference images are implemented with API endpoints and data manager methods. Phase 4 (experiment session tracking) is planned but not yet implemented.

## Key Constraints

- Fish registration is **optional** — not all dishes use individual tracking
- Works with any dish type (source, derived, well plate, regular dish)
- `fish_id` is UUID v4 (`8-4-4-4-12` hex) per downstream contracts (`~/gitrepos/palette/docs/zebrobot_snapshot.md`)
- UUIDs can be minted by MetaZebrobot (web UI, batch registration) or by Citrus at acquisition time and back-registered later
- Downstream systems consume `fish_id` via H5 `/subject_metadata` block
- One fish can have **multiple recordings** — the `fish_runs` join table links N sessions to 1 fish

## Data Storage Strategy: Snapshot + Registry

The `fish_id` UUID is the bridge between two complementary storage strategies. Both are necessary.

### Snapshot: H5 files as self-contained artifacts

Each recording's H5 file should contain a complete snapshot of the facts that were true **at the time of recording**. This makes the dataset a durable, self-contained artifact — usable without network access, surviving database migrations, and shareable with collaborators who don't have access to the registry.

Snapshot into H5 `/subject_metadata`:

| Field | Source |
|-------|--------|
| `fish_id` | `fish_subjects.fish_id` (the UUID — also the join key back to registry) |
| `subject_count` | Number of fish used in this session |
| `genotype` | `fish_subjects.genotype` (as known at recording time) |
| `species` | `fish_subjects.species` |
| `sex` | `fish_subjects.sex` |
| `dpf_at_run` | Computed from `dishes.dof` + session date |
| `source_dish_id` | The fish's origin dish (walk `parent_dish_id` if needed) |
| `source_cross_id` | `dishes.cross_id` |
| `housing_unit_id` | `housing_units.unit_id` (where the fish lives at recording time) |
| `housing_unit_kind` | `housing_units.unit_kind` (well, lane, chamber, open) |
| `housing_position_label` | `housing_units.position_label` (e.g. "B3") |

Snapshot into H5 `/zebrobot_snapshot` (richer context, already defined in `~/gitrepos/palette/docs/zebrobot_snapshot.md`):

- Full dish metadata from API
- Full cross metadata (line strain, parents)
- Timestamped API context (`queried_at_utc`)

### Registry: MetaZebrobot database for cross-session queries

The live database is the queryable index across all recordings and the full lifecycle of each fish. It holds information that accumulates over time and doesn't belong in a single H5 file.

Registry-only (not snapshotted):

| Data | Why registry-only |
|------|-------------------|
| Full housing history | Still accumulating after recording |
| All experiment sessions for this fish | Grows with each session |
| Screening results | May be amended after recording |
| Maintenance / quality checks | Per-housing-unit log, not per-recording |
| Other fish in the same dish/cross | Useful for population queries, not per-recording |

### Target query

The registry enables the target query:

> "Show me all individual fish that had protocol X performed, with their housing history, screening results, and cross lineage."

```sql
SELECT
    f.fish_id, f.genotype, f.sex,
    s.protocol_name, s.run_at_utc, fr.dpf_at_run,
    d.cross_id, d.dof,
    h.position_label, h.unit_kind,
    ho.moved_in_at, ho.moved_out_at, ho.reason
FROM fish_subjects f
JOIN fish_runs fr ON fr.fish_id = f.fish_id
JOIN experiment_sessions s ON s.session_uuid = fr.session_uuid
JOIN dishes d ON d.dish_id = f.dish_id
LEFT JOIN housing_unit_occupancy ho ON ho.fish_id = f.fish_id
LEFT JOIN housing_units h ON h.unit_id = ho.unit_id
WHERE s.protocol_name = 'DefaultScreen'
ORDER BY f.fish_id, ho.moved_in_at;
```

Screening results join through the dish:

```sql
SELECT f.fish_id, ss.*
FROM fish_subjects f
JOIN dishes d ON d.dish_id = f.dish_id
JOIN screening_steps ss ON ss.dish_id = d.dish_id
WHERE f.fish_id = ?;
```

### The one rule

The `fish_id` UUID is minted once — either in MetaZebrobot (web UI, batch registration) or in Citrus (acquisition time, back-registered later) — written into the H5 at acquisition time, and never changes. It is the join key between the self-contained artifact and the live registry. Every other piece of data flows from having this single stable identifier in both places.

## Existing Infrastructure

| Resource | Location |
|----------|----------|
| `fish_subjects` table definition | `docs/schema.sql:124-134` |
| `experiment_sessions` + `fish_runs` tables | `docs/schema.sql:135-154` |
| Proposed `session_assets` table + `dpf_at_run` | `docs/experimental_data_schema.md` |
| Acquisition registry + import receipts | `docs/zebrobot_snapshot.md:187-347` |
| Snapshot contract with `fish_id` in `subject_metadata` | `~/gitrepos/palette/docs/zebrobot_snapshot.md:61-78` |
| Data manager (needs CRUD methods) | `src/metazebrobot/data/data_manager.py` |
| API server (needs endpoints) | `src/metazebrobot/api_server.py` |
| Screening image infrastructure (reusable for fish images) | `src/metazebrobot/api_server.py`, `data_manager.py` |

---

## Phase 1: Data Layer + API

### Schema

- [x] Add `fish_subjects` table to `data_manager.py` `initialize()`:
  ```sql
  CREATE TABLE IF NOT EXISTS fish_subjects (
      fish_id TEXT PRIMARY KEY,
      dish_id TEXT NOT NULL,
      subject_label TEXT,
      sex TEXT,
      genotype TEXT,
      species TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      notes TEXT,
      current_unit_id TEXT,                              -- added in Phase 2b
      FOREIGN KEY (dish_id) REFERENCES dishes(dish_id),
      FOREIGN KEY (current_unit_id) REFERENCES housing_units(unit_id)
  );
  CREATE INDEX IF NOT EXISTS idx_fish_subjects_dish_id ON fish_subjects(dish_id);
  ```

### Data Manager Methods

- [x] `create_fish_subject(dish_id, fish_id=None, subject_label=None, sex=None, genotype=None, species=None, notes=None)` — accepts optional pre-minted UUID (e.g. from Citrus); generates UUID v4 server-side if not provided; insert row, return `fish_id`
- [x] `get_fish_subjects(dish_id)` — list all fish for a dish, ordered by `created_at`
- [x] `get_fish_subject(fish_id)` — fetch single fish by UUID
- [x] `update_fish_subject(fish_id, **kwargs)` — update mutable fields (`subject_label`, `sex`, `genotype`, `species`, `notes`)
- [x] `delete_fish_subject(fish_id)` — remove fish (cascade handled by FK on `fish_runs`)

### API Endpoints

- [x] `GET /dishes/{dish_id}/fish` — list fish for a dish (JSON array)
- [x] `POST /dishes/{dish_id}/fish` — register a new fish (accepts optional `fish_id` for pre-minted UUIDs, plus `subject_label`, `sex`, `genotype`, `species`, `notes`; returns created fish)
- [x] `GET /fish/{fish_id}` — fetch single fish by UUID
- [x] `PATCH /fish/{fish_id}` — update mutable fields
- [x] `DELETE /fish/{fish_id}` — remove fish

### UUID Generation

- [x] Use `uuid.uuid4()` from stdlib
- [x] Store as lowercase hyphenated string (`8-4-4-4-12` hex) — matches Palette snapshot contract

---

## Phase 2: Web UI for Fish Registration

### Templates

- [x] `templates/fish/fish_list.html` — standalone page listing fish for a dish with registration form
- [x] `templates/fish/_fish_table.html` — HTMX partial: fish table rows (swapped in after registration)

### Page Endpoints

- [x] `GET /dishes/{dish_id}/fish/` — fish management page (HTML)
- [x] `POST /dishes/{dish_id}/fish/register` — single fish registration (HTMX form handler)
- [x] `POST /dishes/{dish_id}/fish/batch` — batch registration (HTMX form handler)
- [x] Link from screening form and dish list page to fish management

### Form Features

- [x] Register fish with optional `subject_label` (well position, nickname, etc.)
- [x] Auto-populate `genotype` and `species` from parent dish/cross data
- [x] HTMX: submitting registration updates fish table without full page reload
- [x] Batch registration: "Add N fish" with optional label prefix (creates prefix-1, prefix-2, ..., or unlabeled)
- [x] Delete fish with confirmation (HTMX delete returns updated table partial)

---

## Phase 2b: Housing Units

Individual fish need to live somewhere. A housing unit is a single physical position within a dish — a well in a well plate, a lane in a lane system, or the entire dish for a simple petri dish. Housing units exist independently of whether fish occupy them, because empty positions still need water changes and feeding.

### Why a separate table

Three things need to attach to a position, not to a fish or the whole dish:

1. **Maintenance** — water changes and feeding happen per well, not per plate and not per fish
2. **Occupancy** — a well can hold 0, 1, or N fish; that count changes over time
3. **Status** — a position can be active, empty (fish moved/died), or retired (plate discarded)

The existing `quality_checks` table is dish-level. For a 6-well plate, you need 6 independent check logs. Hanging checks off the dish means you can't distinguish "well B3 was fed" from "well C1 was fed."

### Data model

```
dish (the physical plate/container)
  └── housing_unit (each well/lane/position, or one "open" unit for simple dishes)
        ├── fish_subject (0..N fish currently in this unit)
        └── housing_unit_checks (per-position maintenance log)
```

### Empty positions

A housing unit with zero fish is normal. Reasons a position can be empty:

- **Never occupied** — well reserved, control well, or plate not fully stocked
- **Fish moved** — transferred to another unit (fish's `current_unit_id` updated)
- **Fish terminated** — died or euthanized (fish gets termination record)
- **Intentionally vacated** — well retired mid-experiment

Empty units still appear in the maintenance UI. Checks can still be logged against them (you still change the water). The `status` field on the unit tracks whether it's actively in use.

### Occupancy history

When a fish moves between units, we want to know where it was and when. A lightweight `housing_unit_occupancy` table records the history:

```
housing_unit_occupancy
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  fish_id         TEXT NOT NULL       -- FK to fish_subjects
  unit_id         TEXT NOT NULL       -- FK to housing_units
  moved_in_at     TEXT NOT NULL       -- when the fish entered this unit
  moved_out_at    TEXT                -- NULL if still there
  reason          TEXT                -- "initial", "transfer", "terminated", "experiment"
```

`fish_subjects.current_unit_id` is the fast lookup; the occupancy table is the audit trail.

### Schema

- [x] Add `housing_units` table to `data_manager.py` `initialize()`:
  ```sql
  CREATE TABLE IF NOT EXISTS housing_units (
      unit_id TEXT PRIMARY KEY,
      dish_id TEXT NOT NULL,
      position_label TEXT,
      unit_kind TEXT NOT NULL DEFAULT 'open',
      capacity INTEGER DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      notes TEXT,
      FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
  );
  CREATE INDEX IF NOT EXISTS idx_housing_units_dish_id ON housing_units(dish_id);
  ```
  `unit_kind` values: `open` (simple petri dish), `well`, `lane`, `chamber`
  `status` values: `active`, `empty`, `retired`

- [x] Add `housing_unit_checks` table:
  ```sql
  CREATE TABLE IF NOT EXISTS housing_unit_checks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      unit_id TEXT NOT NULL,
      check_time TEXT NOT NULL,
      fed BOOLEAN,
      feed_type TEXT,
      water_changed BOOLEAN,
      vol_water_changed INTEGER,
      num_dead INTEGER DEFAULT 0,
      notes TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (unit_id) REFERENCES housing_units(unit_id)
  );
  CREATE INDEX IF NOT EXISTS idx_housing_unit_checks_unit_id ON housing_unit_checks(unit_id);
  ```

- [x] Add `housing_unit_occupancy` table:
  ```sql
  CREATE TABLE IF NOT EXISTS housing_unit_occupancy (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      fish_id TEXT NOT NULL,
      unit_id TEXT NOT NULL,
      moved_in_at TEXT NOT NULL,
      moved_out_at TEXT,
      reason TEXT,
      FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE,
      FOREIGN KEY (unit_id) REFERENCES housing_units(unit_id)
  );
  CREATE INDEX IF NOT EXISTS idx_housing_occupancy_fish_id ON housing_unit_occupancy(fish_id);
  CREATE INDEX IF NOT EXISTS idx_housing_occupancy_unit_id ON housing_unit_occupancy(unit_id);
  ```

- [x] Add `current_unit_id` column to `fish_subjects`:
  ```sql
  ALTER TABLE fish_subjects ADD COLUMN current_unit_id TEXT REFERENCES housing_units(unit_id);
  ```

### Auto-creation of housing units

When a derived dish is created:
- **Simple petri dish**: one housing unit with `unit_kind = 'open'`, `position_label = NULL`, `capacity = NULL`
- **Well plate (N wells)**: N housing units, `unit_kind = 'well'`, `position_label = 'A1'..'B3'` etc.
- **Lane system**: one unit per lane, `unit_kind = 'lane'`, `position_label = '1'..'N'`

When a fish is registered to a dish without specifying a unit, it goes into the default unit (the single `open` unit for petri dishes, or unassigned).

### Data Manager Methods

- [x] `create_housing_unit(dish_id, unit_kind, position_label, capacity, notes)` — create single unit, `unit_id` = `{dish_id}:{position_label}`
- [x] `create_housing_units_for_dish(dish_id, unit_kind, count, label_format)` — batch-create; `label_format` supports `"numeric"` or `"well_plate"` (row-major A1..H12)
- [x] `get_housing_units(dish_id)` — list units for a dish with current occupancy counts
- [x] `get_housing_unit(unit_id)` — fetch single unit with its current fish
- [x] `assign_fish_to_unit(fish_id, unit_id, reason)` — update `current_unit_id`, insert occupancy record
- [x] `move_fish(fish_id, new_unit_id, reason)` — close old occupancy, open new one, update `current_unit_id`
- [x] `log_housing_unit_check(unit_id, check_time, fed, feed_type, water_changed, ...)` — per-position maintenance
- [x] `get_housing_unit_checks(unit_id)` — maintenance history for a position
- [x] `get_fish_occupancy_history(fish_id)` — where has this fish lived

### API Endpoints

- [x] `GET /dishes/{dish_id}/units` — list housing units for a dish (with occupancy counts)
- [x] `POST /dishes/{dish_id}/units` — create housing unit(s); supports single or batch via `count` + `label_format`
- [x] `GET /units/{unit_id}` — fetch unit detail with current fish list
- [x] `POST /units/{unit_id}/checks` — log a maintenance check for a position
- [x] `GET /units/{unit_id}/checks` — maintenance history
- [x] `POST /fish/{fish_id}/assign` — assign or move a fish to a unit (auto-detects first assignment vs transfer)
- [x] `GET /fish/{fish_id}/history` — occupancy history

### Relationship to existing `quality_checks`

The existing dish-level `quality_checks` table stays as-is for dishes that don't use housing units. For dishes with housing units, use `housing_unit_checks` instead. The two tables serve the same purpose at different granularity levels.

---

## Phase 3: Reference Images

### Schema

- [x] Add `fish_subject_images` table to `data_manager.py` `initialize()`:
  ```sql
  CREATE TABLE IF NOT EXISTS fish_subject_images (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      fish_id TEXT NOT NULL,
      image_filename TEXT NOT NULL,
      image_type TEXT DEFAULT 'reference',
      caption TEXT,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE
  );
  CREATE INDEX IF NOT EXISTS idx_fish_subject_images_fish_id ON fish_subject_images(fish_id);
  ```

### Image Storage

- [x] Reuse screening image infrastructure (filesystem with paths in DB)
- [x] Layout:
  ```
  data/fish_images/
    {fish_id}/
      001.jpg
      002.png
  ```
- [x] Mount `StaticFiles` for serving fish images at `/fish-images`

### Data Manager Methods

- [x] `save_fish_image(fish_id, image_filename, image_type, caption)` — insert row
- [x] `get_fish_images(fish_id)` — list images for a fish

### API Endpoints

- [x] `POST /fish/{fish_id}/images` — upload reference image (HTMX multipart form)
- [x] `GET /fish/{fish_id}/images` — HTMX partial: image gallery for a fish

### Templates

- [x] `templates/fish/_image_gallery.html` — HTMX partial: thumbnail grid with upload form
- [x] Per-fish image galleries on the fish list page (lazy-loaded via HTMX `hx-trigger="revealed"`)
- [x] File input with `capture="environment"` for mobile camera

---

## Phase 4: Experiment Session Tracking

### Schema

- [ ] Add `experiment_sessions` table to `data_manager.py` `initialize()`:
  ```sql
  CREATE TABLE IF NOT EXISTS experiment_sessions (
      session_uuid TEXT PRIMARY KEY,
      run_at_utc TEXT,
      rig_id TEXT,
      arena_id TEXT,
      protocol_name TEXT,
      h5_path TEXT
  );
  ```
- [ ] Add `fish_runs` table:
  ```sql
  CREATE TABLE IF NOT EXISTS fish_runs (
      run_id INTEGER PRIMARY KEY AUTOINCREMENT,
      fish_id TEXT NOT NULL,
      session_uuid TEXT NOT NULL,
      notes TEXT,
      FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE,
      FOREIGN KEY (session_uuid) REFERENCES experiment_sessions(session_uuid) ON DELETE CASCADE,
      UNIQUE (fish_id, session_uuid)
  );
  CREATE INDEX IF NOT EXISTS idx_fish_runs_fish_id ON fish_runs(fish_id);
  CREATE INDEX IF NOT EXISTS idx_fish_runs_session_uuid ON fish_runs(session_uuid);
  ```
- [ ] Consider adding `dpf_at_run INTEGER` column to `fish_runs` (see `docs/experimental_data_schema.md`)
- [ ] Consider adding `session_assets` table for per-session file paths

### Data Manager Methods

- [ ] `create_experiment_session(session_uuid, run_at_utc, rig_id, arena_id, protocol_name, h5_path)` — insert session
- [ ] `get_experiment_session(session_uuid)` — fetch single session
- [ ] `create_fish_run(fish_id, session_uuid, notes=None)` — link fish to session
- [ ] `get_fish_runs(fish_id)` — list all sessions a fish participated in
- [ ] `get_session_fish(session_uuid)` — list all fish in a session

### API Endpoints

- [ ] `POST /sessions` — register an experiment session
- [ ] `GET /sessions/{session_uuid}` — fetch session details
- [ ] `POST /sessions/{session_uuid}/fish` — link a fish to a session (accepts `fish_id`)
- [ ] `GET /sessions/{session_uuid}/fish` — list fish in a session
- [ ] `GET /fish/{fish_id}/sessions` — list sessions for a fish

### Downstream Integration

#### Citrus (acquisition time)

Two registration paths depending on whether the fish already exists in the registry:

**Path A — fish already registered (e.g. well plate, pre-registered batch):**
1. Operator selects a dish → Citrus calls `GET /dishes/{dish_id}/fish` to list registered fish
2. Each fish in the response includes `current_unit_id` (may be `null` if not yet assigned to a housing unit)
3. Citrus optionally calls `GET /dishes/{dish_id}/units` to get the housing layout (well labels, occupancy counts)
4. Operator picks a fish from the list → Citrus has the `fish_id`
5. Citrus optionally calls `GET /fish/{fish_id}` for full context

**Path B — fish not yet registered (e.g. anonymous petri dish, first encounter):**
1. Citrus mints `fish_id = uuid4()` locally at acquisition time
2. Citrus writes it into the H5 immediately (no API call needed yet)
3. After transfer, the import pipeline calls `POST /dishes/{dish_id}/fish` with `{"fish_id": "<the-minted-uuid>"}` to back-register it into MetaZebrobot

Both paths converge: the same UUID ends up in both the H5 and the registry.

**API response shapes (for Citrus integration):**

`GET /dishes/{dish_id}/fish` → `{"items": [<fish>, ...]}`

`GET /fish/{fish_id}` → single fish object:
```json
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
```

`POST /dishes/{dish_id}/fish` — body accepts optional `fish_id` (for Citrus-minted UUIDs), `subject_label`, `sex`, `genotype`, `species`, `notes`. Returns `201` with the created fish object.

`GET /dishes/{dish_id}/units` → `{"items": [<unit>, ...]}` where each unit includes `occupant_count`.

`GET /units/{unit_id}` → unit object with nested `fish` array of current occupants.

`POST /fish/{fish_id}/assign` — body: `{"unit_id": "...", "reason": "initial"}`. Assigns or moves fish.

`GET /fish/{fish_id}/history` → `{"items": [<occupancy_record>, ...]}` with `moved_in_at`, `moved_out_at`, `reason`, plus unit details.

**H5 snapshot (both paths):**

Citrus snapshots into H5 `/subject_metadata`:
- [ ] `fish_id` — the UUID (mandatory for individually tracked fish)
- [ ] `subject_count` — number of fish in this session
- [ ] `genotype`, `species`, `sex` — as known at recording time
- [ ] `dpf_at_run` — computed from dish DOF + session date
- [ ] `source_dish_id` — origin dish (may differ from current dish if fish was moved)
- [ ] `source_cross_id` — cross the fish descends from
- [ ] `housing_unit_id`, `housing_unit_kind`, `housing_position_label` — where the fish physically was at recording time

Citrus snapshots richer dish/cross metadata into H5 `/zebrobot_snapshot` (existing contract).

**Multiple recordings per fish:**

The same fish can appear in multiple recordings. Each recording creates a separate `fish_runs` row linking the `fish_id` to a different `experiment_sessions` entry. Example: fish in a petri dish runs protocol A, then later runs protocol B — two sessions, two `fish_runs` rows, one `fish_id`.

```
fish_subjects      1 ──< N >──  fish_runs  ──< N >── 1  experiment_sessions
(one fish)                      (one per recording)      (one session)
```

#### Palette (ingestion time)

- [ ] Palette reads `/subject_metadata.fish_id` during ingestion and stores it in its own registry
- [ ] Palette maps `fish_id` → `subject_id` per the metadata cleanup recommendation (see `~/gitrepos/palette/docs/metadata_cleanup_recommendation.md`)
- [ ] Palette preserves the full `/subject_metadata` and `/zebrobot_snapshot` blocks in its analysis metadata

#### MetaZebrobot (import pipeline, post-transfer)

- [ ] `POST /sessions` registers the experiment session after H5 files are transferred
- [ ] `POST /sessions/{session_uuid}/fish` links fish to the session (creates `fish_runs` row)
- [ ] Import receipts (see `docs/zebrobot_snapshot.md:243-347`) confirm successful import back to acquisition machine

#### What lives where

| Fact | H5 (snapshot) | MetaZebrobot (registry) | Notes |
|------|:---:|:---:|-------|
| `fish_id` UUID | yes | yes | The join key between both |
| Genotype, species, sex at recording | yes | yes | H5 is point-in-time; registry may be corrected later |
| DPF at run | yes | yes (`fish_runs.dpf_at_run`) | Computed once, stored in both |
| Source dish + cross | yes | yes (via `dishes.parent_dish_id` chain) | H5 has compact summary; registry has full lineage |
| Housing unit at recording time | yes | yes (via `housing_unit_occupancy`) | H5 snapshots current; registry has full history |
| Full housing history | no | yes | Accumulates over fish lifetime |
| All experiment sessions | no | yes | Grows with each session |
| Screening results | no | yes | May be amended; join through dish |
| Maintenance / quality checks | no | yes | Per-housing-unit, not per-recording |
| Zebrobot snapshot (dish + cross detail) | yes | implicit (it's the source) | Rich provenance payload in H5 |

---

## Files Created

```
src/metazebrobot/templates/
  fish/
    fish_list.html          (Phase 2 — done)
    _fish_table.html        (Phase 2 — done)
    _image_gallery.html     (Phase 3 — done)
```

## Files to Modify

```
src/metazebrobot/data/data_manager.py  -- fish_subjects table, housing_units tables, CRUD methods, image methods, session/run methods
src/metazebrobot/api_server.py         -- fish endpoints, housing unit endpoints, session endpoints, static mount for fish images
```
