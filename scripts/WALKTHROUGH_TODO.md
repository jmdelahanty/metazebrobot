# Operator Walkthrough Script — TODO

## What this is

A guided, interactive script (`scripts/walkthrough.py`) that exercises the full fish tracking workflow against a live MetaZebrobot API server and real database. The operator runs each step, checks the web UI, and presses Enter to continue. Test data is cleaned up at the end.

## Prerequisites

- API server running: `pixi run python -m metazebrobot.api_server --db-path /path/to/zebrobot.db`
- At least one real cross in the database (from PyRAT sync)

## Steps the walkthrough covers

### Phase 1: Dish setup
- [ ] Pick a real cross_id from the live DB (GET /crosses)
- [ ] Create a test dish (`E2E_TEST_{cross_id}_1`) linked to that cross
- [ ] **Pause** — check `/screening/` to see the dish appear

### Phase 2: Screening
- [ ] Log a screening step on the test dish (POST screening step)
- [ ] **Pause** — check `/screening/{dish_id}` to see the step

### Phase 3: Derived dishes
- [ ] Create a "positive_screened" derived dish (`E2E_TEST_{cross_id}_pos`) with `parent_dish_id` pointing to the primary
- [ ] Create a "negative_screened" derived dish (`E2E_TEST_{cross_id}_neg`)
- [ ] **Pause** — check `/crosses/{cross_id}/fish/` to see parent/child hierarchy

### Phase 4: Dish-level images
- [ ] Upload a sample reference image to the positive derived dish (POST /dishes/{dish_id}/images)
- [ ] **Pause** — check `/dishes/{dish_id}/fish/` to see the dish image gallery

### Phase 5: Individual fish registration
- [ ] Register 4 individual fish on the positive dish (POST /dishes/{dish_id}/fish)
- [ ] **Pause** — check the fish table on the dish page

### Phase 6: Housing units
- [ ] Create a 4-well plate on the positive dish (POST /dishes/{dish_id}/units)
- [ ] Assign each fish to a well (POST /fish/{fish_id}/assign)
- [ ] **Pause** — check `/dishes/{dish_id}/fish/` to see unit assignments

### Phase 7: Plate map visualization
- [ ] **Pause** — check `/dishes/{dish_id}/plate-map` to see the well plate grid (4 occupied wells, green)
- [ ] Register one more fish WITHOUT assigning to a well
- [ ] **Pause** — check `/dishes/{dish_id}/fish/` to see the plate map with the "Unassigned fish" section

### Phase 8: Cross-level view
- [ ] **Pause** — check `/fish/` index, then drill into the cross to see the full hierarchy

### Cleanup
- [ ] Delete all fish subjects created (DELETE /fish/{fish_id})
- [ ] Delete test dishes from the database (direct SQL — no DELETE /dishes endpoint exists)
- [ ] Remove uploaded test images from disk
- [ ] Confirm cleanup — check `/fish/` index, test data should be gone

## Implementation notes

- Use `requests` library (already a dependency)
- Port defaults to 8002, configurable via `--port` arg
- All test data uses `E2E_TEST_` prefix for easy identification
- Wrap in try/finally so cleanup runs even on Ctrl+C
- Each pause prints the URL to check and waits for `input("Press Enter to continue...")`
- For image upload, generate a small solid-color PNG in memory (no test fixture files needed)
- Direct SQL cleanup for entities without DELETE endpoints — connect to the DB path passed via `--db-path` arg
