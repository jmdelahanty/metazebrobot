---
title: "Fish Counts & Screening Accuracy"
summary: "What fish_count and current_fish_count mean, how counts are edited, and screening accuracy expectations."
owner: metazebrobot
status: current
kind: reference
verified_against: null
---

# Fish Counts & Screening Accuracy

## `fish_count` Is a Best-Effort Estimate

The `fish_count` field on a dish represents the operator's best estimate at the time the dish record is created. It is not validated against downstream screening totals and is not intended to be precise. Operators do their best to count accurately, but some error is expected and acceptable — especially for large groups of larvae.

There is intentionally no validation that prevents a screening step from reporting more kept + removed than the dish's initial `fish_count`. This avoids hard failures caused by minor estimation errors that have no practical impact on the workflow.

## Editing Dish Counts

The dishes inventory page exposes an **Edit Count** control for active dishes. The operator-entered value is the intended current physical fish count for the dish.

Internally, MetaZebrobot keeps `current_fish_count` derived from the dish's baseline `fish_count` plus screening, transfer, and care history. To make the correction durable, the edit adjusts the baseline `fish_count` enough that the derived `current_fish_count` reloads to the entered value. For a dish that was accidentally created with no count, this simply fills in the missing opening estimate.

This count correction is inventory context only. It does not rewrite screening-step counts and does not change yield calculations.

If the entered count cannot be represented without changing existing screening or transfer history, the update is rejected instead of silently corrupting provenance.

## Deaths Recorded During Care

The **Found dead** count in a dish health check reduces its current inventory count. Deaths recorded in individual housing-unit checks also reduce the parent dish count. Record each loss once, using the dish check or the corresponding unit check. Counts cannot fall below zero. Saving a check and updating inventory happen in the same transaction.

Submitting another check for the same dish or unit at the same timestamp replaces that observation, so a retry does not deduct the same deaths again. Loading a dish includes all care history, with normalized database records taking precedence over older embedded JSON copies. Deaths before a screening step also update its derived before/after inventory counts; observed screening totals and yield calculations retain their existing meaning.

At startup, inventory is recalculated for dishes with existing care history. For example, a baseline of 31 with 8 recorded deaths becomes a current count of 23. For records created before mortality affected inventory, deaths through the latest recorded manual count correction are treated as already covered by that correction. Later deaths still reduce inventory. This cutoff is stored with the dish so repeated startups cannot deduct historical deaths again. An older count adjustment without a recorded count event cannot be inferred automatically.

After this update, **Edit Count** includes mortality when adjusting the baseline: entering 23 after 8 deaths preserves a baseline of 31 and a current count of 23. Subsequent deaths reduce that corrected current count normally.

## Screening Counts Are the Source of Truth

For aggregate metrics (yield percentage, total initially produced, total positive final), the system uses values from `ScreeningStep` records — specifically `count_screened_this_step` and `number_kept` — rather than the dish-level `fish_count`.

This means:
- **`fish_count`** is useful for at-a-glance context (roughly how many fish are in this dish) but does not feed into yield calculations.
- **`count_screened_this_step`** is the actual number of fish an operator screened during a given step and is what drives aggregate results.
- **`number_kept`** counts from screening steps are generally the most accurate values in the system, as operators are careful and deliberate when identifying which fish to keep.

## Summary

| Field | Purpose | Accuracy expectation |
|---|---|---|
| `fish_count` | Initial estimate when dish is created | Best-effort, may be off |
| `current_fish_count` | Remaining fish after inventory and care events | Derived from recorded events and count corrections |
| `count_screened_this_step` | Fish actually screened in a step | Operator-counted, reliable |
| `number_kept` | Fish kept (passed all criteria) in a step | High confidence |
| `number_removed_*` | Fish removed during screening | Operator-counted, reliable |
| `final_positive_count` | End-of-screening positive total | High confidence |
