# Fish Counts & Screening Accuracy

## `fish_count` Is a Best-Effort Estimate

The `fish_count` field on a dish represents the operator's best estimate at the time the dish record is created. It is not validated against downstream screening totals and is not intended to be precise. Operators do their best to count accurately, but some error is expected and acceptable — especially for large groups of larvae.

There is intentionally no validation that prevents a screening step from reporting more kept + removed than the dish's initial `fish_count`. This avoids hard failures caused by minor estimation errors that have no practical impact on the workflow.

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
| `count_screened_this_step` | Fish actually screened in a step | Operator-counted, reliable |
| `number_kept` | Fish kept (passed all criteria) in a step | High confidence |
| `number_removed_*` | Fish removed during screening | Operator-counted, reliable |
| `final_positive_count` | End-of-screening positive total | High confidence |
