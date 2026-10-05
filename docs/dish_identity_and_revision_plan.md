# Dish Identity and Record Revision Plan

Status: planned, not implemented (2026-10-05).

Goal: give consumers (Citrus, Orange via Palette) an immutable, globally
unique handle for every dish, and a way to detect that a dish or fish record
changed after it was captured in a recording. Related contracts:
`docs/identity_and_provenance_contract.md`, `docs/zebrobot_snapshot.md`.

Scope is four changes, shipped together as one schema migration.

## 1. Replace `INSERT OR REPLACE` with a true upsert

### Problem

`DataManager.save_fish_dish` (`src/metazebrobot/data/data_manager.py:1033`)
writes dishes with `INSERT OR REPLACE`. SQLite implements this as
delete-then-insert, so every column *not* in the insert list is lost or reset
to its default on every save:

- `created_at` is reset to now on every save.
- `enclosure_in_beaker` is dropped to NULL.
- Any new column (e.g. `dish_uuid`, `revision` below) would be reset, which
  would defeat the purpose of items 2 and 3.

### Change

- Rewrite as `INSERT INTO dishes (...) VALUES (...) ON CONFLICT(dish_id) DO
  UPDATE SET <col> = excluded.<col>, ...` listing the same columns as today.
  `dish_id`, `created_at`, `dish_uuid`, and `revision` are never in the
  `SET` list.
- Same treatment for the walkthrough/tour dish insert in
  `src/metazebrobot/api_server.py:5554` and `scripts/walkthrough.py:169`.
- `migrate_to_nosql.py` is legacy; leave as is.

### Tests

- Saving an existing dish twice keeps `created_at`, `dish_uuid`, and
  `enclosure_in_beaker` unchanged.
- Child rows (screening steps, quality checks, fish subjects) survive a re-save.

## 2. Add `dish_uuid`

### Schema

- `ALTER TABLE dishes ADD COLUMN dish_uuid TEXT` (in `ensure_schema`, using the
  existing `PRAGMA table_info` guard pattern at `data_manager.py:~304`).
- Backfill: every row with `dish_uuid IS NULL` gets a UUID4 (Python
  `uuid.uuid4()`, lowercase hyphenated), in one transaction.
- `CREATE UNIQUE INDEX IF NOT EXISTS idx_dishes_dish_uuid ON dishes(dish_uuid)`.
  (SQLite cannot add a `UNIQUE NOT NULL` column via `ALTER TABLE`; the index
  plus app-side generation plus the fallback trigger give the same guarantee.)
- Fallback `AFTER INSERT` trigger: if a row is inserted with `dish_uuid IS
  NULL` (scripts, tour setup), set a SQL-generated UUID4. Normal code paths
  generate the UUID in Python.

### Semantics

- Minted once at dish creation; never changes; never reused, even if the dish
  is deleted and the same `dish_id` is created again.
- `dish_id` (`{cross_id}_{n}`) stays the primary key and the human-facing id.
  It is unique only within this database.
- Consumers should record **both**: `dish_uuid` as the reference, `dish_id`
  for humans and for API lookup.

### API

- `dish_uuid` is added to: `GET /dishes/{dish_id}` (already `SELECT *`),
  `GET /dishes`, `GET /acquisition/dishes` items,
  `GET /dishes/{dish_id}/citrus-snapshot`.
- New lookup: `GET /dishes/by-uuid/{dish_uuid}` returns the same payload as
  `GET /dishes/{dish_id}` (404 `dish_not_found` if unknown).
- `fish_subjects` responses gain `dish_uuid` alongside `dish_id`.

## 3. Add `revision` and reliable `updated_at`

### Problem

There is no version on dish or fish records. `dishes.updated_at` is only set by
the full upsert; at least six partial `UPDATE dishes` paths skip it
(`data_manager.py:313, 597, 602, 1180, 1885, 4007`). `fish_subjects` has no
`updated_at` at all.

### Schema

- `dishes`: `ADD COLUMN revision INTEGER NOT NULL DEFAULT 1`.
- `fish_subjects`: `ADD COLUMN revision INTEGER NOT NULL DEFAULT 1` and
  `ADD COLUMN updated_at TEXT` (backfilled from `created_at`).
- `updated_at` is owned by the trigger; `save_fish_dish` no longer sets it.
- One `AFTER UPDATE` trigger per table, rebuilt from `PRAGMA table_info` on
  every startup (`DataManager.ensure_revision_tracking`), so every write path
  is covered (including raw SQL) and newly added columns are tracked
  automatically:

```sql
CREATE TRIGGER trg_dishes_revision
AFTER UPDATE ON dishes
FOR EACH ROW WHEN NEW."genotype" IS NOT OLD."genotype" OR ...  -- every column
BEGIN
    UPDATE dishes
    SET revision = OLD.revision + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE rowid = NEW.rowid;
END;
```

  Excluded from the comparison: `revision`, `updated_at`, `dish_uuid`.
  An `AFTER INSERT` trigger fills `updated_at` where `ALTER TABLE` could not
  give it a default (`fish_subjects`).

### Semantics

- `revision` increments when any tracked column's value changes, and only
  then. No-op saves and the idempotent startup backfills (termination-reason
  normalization, `current_fish_count` fill-in, mortality inventory) do not
  bump it, so restarts never change revisions.
- Same `(dish_uuid, revision)` means the `dishes` row content is unchanged.
  Compare the pair: a deleted and re-created `dish_id` restarts at
  `revision = 1` under a new `dish_uuid`.
- A single save may bump `revision` by more than 1 (e.g. the upsert and the
  screening-finalize update in the same transaction). Only "changed / not
  changed" is meaningful, not the size of the step.
- Coverage is the `dishes` / `fish_subjects` row only. Screening steps, quality
  checks, and cross cache refreshes do not bump the dish revision. The cross
  cache already exposes its own `cache_updated_at`. `dpf` is computed from
  `dof` at request time and changes daily without a revision bump.
- There is still no "read as of time T". Point-in-time reconstruction is out of
  scope (possible later via an append-only `dish_revisions` table). Fish count
  history remains available via `dish_count_events`.

### API

- `revision` and `updated_at` added to `GET /dishes/{dish_id}`, `GET /dishes`,
  `GET /acquisition/dishes`, `GET /dishes/{dish_id}/citrus-snapshot`,
  `GET /fish/{fish_id}`, `GET /dishes/{dish_id}/fish`.
- `citrus-snapshot` and `acquisition/dishes` bump `schema_version` from 1 to 2.
  The change is additive (old fields unchanged), so v1 readers keep working;
  `schema_version >= 2` tells consumers `dish_uuid` / `revision` are present.

### Tests

Implemented in `tests/test_data.py::TestDishRevision` / `TestFishRevision`
and `tests/test_api.py::TestRevisionEndpoints`:

- Generic: a raw `UPDATE` of every tracked `dishes` column (read from
  `PRAGMA table_info`) bumps `revision` by exactly 1. This covers every
  partial-update path by construction.
- Named paths: `save_fish_dish` change, screening finalize, inventory refresh
  after a care check with deaths, startup backfills (bump once when they
  change data, then stable).
- No bump: no-op `UPDATE`, `updated_at`-only write, repeated identical save,
  and `ensure_schema` re-run over all dishes.
- Fish: create starts at 1; `update_fish_subject` and `assign_fish_to_unit`
  bump; an unchanged update does not.
- Existing rows start at `revision = 1` (verified on a copy of the
  production DB: 81 dishes, restart-stable).

## 4. Structured error bodies

Make all JSON read endpoints return the same error shape as
`/citrus-snapshot` already does:

| Case | Status | Body |
|------|--------|------|
| Dish not found | 404 | `{"detail": {"error": "dish_not_found", "dish_id": "..."}}` |
| Dish UUID not found | 404 | `{"detail": {"error": "dish_not_found", "dish_uuid": "..."}}` |
| Fish not found | 404 | `{"detail": {"error": "fish_not_found", "fish_id": "..."}}` |
| SQLite failure | 503 | `{"detail": {"error": "database_error", "message": "..."}}` |

Endpoints: `GET /dishes/{dish_id}`, `GET /dishes/by-uuid/{dish_uuid}`,
`GET /dishes`, `GET /fish/{fish_id}`, `GET /dishes/{dish_id}/fish`.
No existing test or template matches on the old `"Dish not found"` /
`"Fish not found"` strings. Citrus keys off the status code only.

Also fixed while doing this:

- `GET /fish/{fish_id}` used to report a database failure as 404 (the data
  layer swallowed the error and returned `None`). It now returns 503
  `database_error`, so a lookup failure is never recorded as "does not exist".
- `GET /dishes/{dish_id}/fish` used to return `200 {"items": []}` for an
  unknown dish; it now returns 404 `dish_not_found`.

HTML/HTMX routes and write endpoints keep their existing error responses.

## Rollout

1. Back up `zebrobot.db` (`sqlite3 zebrobot.db ".backup zebrobot.db.backup.pre_dish_uuid_<date>"`).
2. Implement items 1 to 4 on a branch; tests per section; run TestClient tests
   outside the sandbox per `AGENTS.md`.
3. Stop `metazebrobot-api.service`; migration runs idempotently in
   `ensure_schema` on startup; restart; verify:
   - `SELECT COUNT(*) FROM dishes WHERE dish_uuid IS NULL` = 0
   - `/dishes/{id}/citrus-snapshot` returns `schema_version: 2`, `dish_uuid`, `revision`.
4. Update `docs/zebrobot_snapshot.md`, `docs/identity_and_provenance_contract.md`,
   and `API_SERVICE_GUIDE.md`.
5. Notify Palette and Citrus that the API is live.

## Consumer changes (after rollout)

**Citrus (acquisition):**

- Read `dish_uuid`, `revision`, `updated_at` from `/citrus-snapshot`.
- Write them into `/metadata/subject` and the Zebrobot snapshot JSON (`dish`
  object).
- Record `fish_id` and its `revision` when an individual fish is recorded.
- Optionally parse structured `detail.error` into snapshot `errors[]`.

**Palette / Orange-without-Citrus:**

- Orange records `dish_uuid` and `dish_id` (plus `fish_id` when applicable) at
  record start.
- At intake, Palette fetches by `dish_id` (or `/dishes/by-uuid/{uuid}`),
  verifies `dish_uuid` matches, and stores the snapshot with `revision`.
- `revision` differing from the one captured at record time means the record
  was written since; compare content to decide whether it matters.
- `lookup_failed` records the HTTP status plus `detail.error`.

## Out of scope

- Read authentication / network exposure for cluster access (separate decision).
- Point-in-time reads / full edit history.
