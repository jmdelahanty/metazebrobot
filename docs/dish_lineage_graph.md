# Dish Lineage Graph

Dish lineage is modeled as a directed graph, not a strict tree. A tree is enough
for simple derived dishes, but it cannot represent later merges or partial
transfers where multiple source dishes feed one destination dish.

## Current Read Model

The graph is read from existing records:

- `dishes` creates dish nodes.
- `screening_step_allocations` creates screening-derived edges when an
  allocation has a `destination_dish_id` or legacy `derived_dish_id`.
- `dish_transfer_events` creates transfer edges between existing dishes.
- `parent_dish_id` is used only as a fallback edge for older records that do
  not have a matching screening allocation edge.

The current API endpoints are:

- `GET /crosses/{cross_id}/lineage` for JSON `{nodes, edges, summary}`.
- `GET /crosses/{cross_id}/lineage/` for a compact HTML event table.

## Design Principle

Persist events, render lineage from events. The graph view should be a
projection of recorded actions, not a separate source of truth.

## Future Extensions

- Add count-adjustment events so manual count edits become traceable.
- Add fish-level edges once individual fish IDs are routinely assigned before
  well-plate work.
- Add a richer visualization only after the event model is stable.
