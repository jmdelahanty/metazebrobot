# Crossing Performance Metrics — Known Limitations

## How MetaZebrobot Currently Calculates Performance

Performance for a crossing is calculated as:

```
performance = raised_count / requested_groups
```

- **`raised_count`**: The number of child tanks associated with the crossing in PyRAT (i.e., `len(child_tanks)` from the API response).
- **`requested_groups`**: Parsed from the free-text `description` field of the crossing using regex (e.g., "3 groups", "one group").

These values are displayed as a percentage in the UI (e.g., "100%", "50%") and color-coded green/orange/red.

## Verified UI/API Mismatch On April 9, 2026

Crossing `17907` was checked against both the live PyRAT HTML page and the live
`api/v3/tanks/crossings` response on April 9, 2026. A later check of the newer
PyRAT `backend/v1/tanks/crossings/17907/details` response on the same date
showed additional fields not present in the older crossing API.

Observed facts:

- The PyRAT crossings page rendered performance as `2 / 2`.
- The same HTML row rendered an empty `children_tanks` column.
- The performance numerator in the HTML had CSS class `overwritten`.
- The live crossing API response for `17907` returned `status = "set-up"`,
  `date_of_raise = null`, and `tanks.children = []`.
- The same API response included description text
  `"2 Groups for propagation please"`.
- The newer crossing detail response returned `raised_tanks = 2`,
  `really_raised_tanks = 2`, `crossing_tanks = 2`, and still
  `tanks.children = []`.

Implications:

- PyRAT's browser UI is not simply rendering `len(tanks.children)` for the
  performance numerator.
- The numerator shown in the PyRAT UI appears to come from `raised_tanks` or a
  related internal count, not from the visible `children` list.
- The denominator shown in the PyRAT UI appears to come from `crossing_tanks`,
  which is exposed on the newer detail endpoint but not on
  `api/v3/tanks/crossings`.
- The older public crossing API and the newer authenticated detail endpoint do
  not expose the same information.

Conclusion:

- MetaZebrobot's current `raised_count / requested_groups` calculation is only a
  local approximation of PyRAT performance.
- It should not be treated as a faithful reproduction of the PyRAT UI metric.
- If MetaZebrobot needs closer parity with PyRAT, it should prefer the newer
  authenticated crossing-detail endpoint over `api/v3/tanks/crossings`.

## Recommended Mapping To Match PyRAT

Based on live checks from April 9, 2026, MetaZebrobot should treat the PyRAT
crossing-detail payload as the authoritative source for performance-like values.

Recommended mapping:

- **Performance denominator**: `crossing_tanks`
- **Preferred performance numerator**: `raised_tanks`
- **Fallback numerator**: `really_raised_tanks`
- **Last-resort fallback numerator**: `len(tanks.children)`
- **Last-resort fallback denominator**: parsed `requested_groups`

Recommended precedence:

1. `raised_tanks / crossing_tanks`
2. `really_raised_tanks / crossing_tanks`
3. `len(child_tanks) / requested_groups`
4. No performance value if none of the above are available

Interpretation:

- `crossing_tanks` behaves like the expected number of crossing groups/tanks and
  matches the PyRAT denominator.
- `raised_tanks` behaves like the visible PyRAT numerator and matches observed
  `0 / N`, `1 / N`, and `2 / N` style outcomes.
- `really_raised_tanks` appears to be a closely related internal count on the
  numerator side, not a denominator.
- `status` and `completed` should be displayed as workflow metadata only, not as
  performance inputs.

Observed examples:

- Crossing `17907`: `raised_tanks = 2`, `really_raised_tanks = 2`,
  `crossing_tanks = 2`, UI displayed `2 / 2`
- Crossing `14783`: `raised_tanks = 1`, `really_raised_tanks = 1`,
  `crossing_tanks = 2`, UI-consistent result is `1 / 2`

## Why These Numbers May Not Be Accurate

### 1. `raised_count` from the older crossing API does not match the PyRAT UI in all cases

MetaZebrobot currently derives `raised_count` from `tanks.children`, but live
verification on crossing `17907` showed that PyRAT can display a non-zero
performance numerator even when `tanks.children` is empty. This means:

- Crossings where fish were successfully raised but not reflected in
  `tanks.children` will show **artificially low performance** (or 0%) in
  MetaZebrobot.
- PyRAT has additional state for "raised tanks" beyond the `children` list
  exposed by `api/v3/tanks/crossings`.
- The newer `backend/v1/tanks/crossings/{crossing_id}/details` endpoint exposes
  `raised_tanks` and `really_raised_tanks`, which are better candidates for the
  PyRAT numerator than `len(tanks.children)`.

### 2. `requested_groups` relies on free-text description parsing

The number of requested groups is extracted from the crossing's description field via pattern matching (e.g., "3 groups", "two additional groups"). This is fragile:

- If the description doesn't follow the expected pattern, `requested_groups` returns `None` and performance shows as "N/A".
- Descriptions may be entered inconsistently across users.
- Edits to descriptions after the fact can change the parsed value.
- It should now be treated as a fallback only when `crossing_tanks` is not
  available.

### 3. Crossing status does not guarantee metric parity

The crossing workflow in PyRAT follows: **recorded → set-up → raised** (or **discarded**). If users don't advance crossings through these stages — particularly marking them as "raised" and associating child tanks — the data will not reflect actual outcomes.

However, the `17907` check showed a `set-up` crossing with `date_of_raise = null`
while the PyRAT UI still displayed performance `2 / 2`. So even the visible
status progression is not enough to infer how the UI produced that metric.

Exploratory checks in both the production and test PyRAT UIs on April 9, 2026
also suggested that crossings can be effectively "done" from a workflow point of
view without their status string being updated to `raised`. In other words:

- `status`
- `completed`
- `raised_tanks` / `really_raised_tanks`

should be treated as related but independent signals, not as a single reliable
state machine.

### 4. The PyRAT UI and PyRAT APIs are not a single source

For crossing `17907`, the PyRAT HTML page and the authenticated
`backend/v1/tanks/crossings/17907/details` response agreed on `2 / 2`, while the
older `api/v3/tanks/crossings` response omitted those counts and only exposed an
empty `children` list. Any integration that mixes these endpoints needs to be
explicit about which one is authoritative for performance-like metrics.

## What This Means in Practice

- **Performance values from the older crossing API should be treated as
  estimates, not ground truth.** A crossing showing 0% performance may have
  successfully produced fish that PyRAT's older API does not expose via
  `tanks.children`.
- **Performance values from the authenticated crossing-detail endpoint are much
  closer to PyRAT ground truth.** They should be preferred whenever available.
- **Aggregate statistics (average performance, total raised)** will remain
  inaccurate as long as they are based on `len(child_tanks)` and parsed
  description text.
- **"N/A" performance** should mean neither the authoritative counts nor the
  fallback requested-group parsing were available. It does not mean the crossing
  failed.

## Potential Improvements

- Validate with aquatics staff whether the "raised" workflow is being followed consistently.
- Prefer the authenticated crossing-detail endpoint if the goal is to mirror the
  PyRAT UI's raised/crossing counts.
- Consider adding a manual override or confirmation field for performance if the
  PyRAT UI metric remains unavailable via API.
- Track which crossings have been verified vs. inferred.
