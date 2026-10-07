---
title: "Dish Lineage Graph"
summary: "Dish lineage as a directed graph built from transfer and screening records."
owner: metazebrobot
status: current
kind: design
verified_against: 384a366
---

# Dish Lineage Graph

Dish lineage is modeled as a directed graph, not a strict tree. A tree is enough
for simple derived dishes, but it cannot represent later merges or partial
transfers where multiple source dishes feed one destination dish.

## Current Read Model

The graph is read from existing records:

- `dishes` creates dish nodes.
- `screening_step_allocations` creates screening-derived edges when an
  allocation has a `destination_dish_id` or legacy `derived_dish_id`.
- `dish_transfer_events` creates transfer edges between dishes, including
  transfers into a new numbered destination dish created by the transfer.
- `dish_count_events` creates node-local count adjustment annotations.
- `parent_dish_id` is used only as a fallback edge for older records that do
  not have a matching screening allocation edge.

The current API endpoints are:

- `GET /crosses/{cross_id}/lineage` for JSON
  `{cross_id, nodes, edges, count_events, graph, summary}`, where `graph` is
  the laid-out node/edge geometry for the SVG view.
- `GET /crosses/{cross_id}/lineage/` for an HTML page with a compact SVG
  lineage graph, a count-adjustments table, a lineage-events table, and a
  dishes table.

## Design Principle

Persist events, render lineage from events. The graph view should be a
projection of recorded actions, not a separate source of truth.

## Future Extensions

- Add fish-level edges once individual fish IDs are routinely assigned before
  well-plate work.
- Extend the compact SVG graph into a richer visualization only after the
  event model is stable.

## Count Adjustment History

Manual count edits currently correct the dish's durable baseline so that the
derived `current_fish_count` reloads correctly. Each edit also writes a
`dish_count_events` row so count corrections answer "why does this dish
currently say N fish?" without overloading movement edges.

Columns:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `dish_id TEXT NOT NULL`
- `cross_id TEXT`
- `event_datetime TEXT NOT NULL`
- `previous_current_fish_count INTEGER`
- `new_current_fish_count INTEGER NOT NULL`
- `previous_fish_count INTEGER`
- `new_fish_count INTEGER NOT NULL`
- `reason TEXT NOT NULL`
- `notes TEXT`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

Reason categories:

- `initial_count_correction` for fixing a dish created with no or wrong count.
- `manual_recount` for later physical recounts.
- `data_cleanup` for administrative correction after reviewing records.

UI behavior:

- The Dishes page **Edit Count** form requires a reason and accepts optional
  notes.
- The entered number is the intended current physical fish count.
- The event records the previous and new baseline values because the
  controller adjusts `fish_count`, not just `current_fish_count`, to preserve
  derived-count semantics (see
  [Fish Counts & Screening Accuracy](fish_count_and_screening_accuracy.md#editing-dish-counts)).

Lineage display:

- `/crosses/{cross_id}/lineage/` shows count-adjustment events as annotations
  attached to dish nodes (latest adjustment on the graph node, plus a Count
  Adjustments table), not arrows between dishes.
- Keep movement provenance separate: screening allocations and transfers are
  edges; count corrections are node-local audit events.
