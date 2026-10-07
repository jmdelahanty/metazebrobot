---
title: "Crossing Performance Metrics — Known Limitations"
summary: "How crossing performance (raised / requested) is calculated and where it misleads."
owner: metazebrobot
status: current
kind: reference
verified_against: 384a366
---

# Crossing Performance Metrics — Known Limitations

## How MetaZebrobot Currently Calculates Performance

Performance for a crossing is calculated as:

```
performance = raised_count / performance_target_count
```

- **`raised_count`** (numerator): `raised_tanks`, else `really_raised_tanks`,
  else `len(tanks.children)`.
- **`performance_target_count`** (denominator): `crossing_tanks` when it is
  present and non-zero, else `requested_groups`.
- **`requested_groups`**: Parsed from the free-text `description` field of the
  crossing using regex (e.g., "3 groups").

`raised_tanks`, `really_raised_tanks`, and `crossing_tanks` only exist on the
authenticated `backend/v1/tanks/crossings/{crossing_id}/details` response, so
they are only available when PyRAT frontend credentials are configured and
`enrich_crossings_with_frontend_details()` (`utils/pyrat_frontend_client.py`)
has run. Numerator and denominator fall back independently, so a row can mix an
authoritative count with a fallback one (for example `raised_tanks /
requested_groups`).

The logic lives in two places that must be kept in step:

- Desktop: computed properties on `PyRATCrossing` (`models/pyrat_crossing.py`).
  The crossings tab enriches from `backend/v1` when frontend credentials are
  configured. The detail panel color-codes performance green (>= 100%), orange
  (>= 50%), or red; "N/A" when there is no denominator.
- Web (`/pyrat/crossings/`): `_prepare_crossings_for_display()` in
  `api_server.py`. The first page load uses `api/v3/tanks/crossings` merged
  with detail fields previously cached in the local `crosses` table by
  `_cache_cross_rows`, so counts can be stale. The HTMX table partial
  (`/pyrat/crossings/table`) then re-enriches from `backend/v1` on load and
  every 5 minutes when frontend credentials are configured. Rows without a
  denominator show "-" (no color coding).

The two `requested_groups` parsers differ: the desktop model accepts spelled-out
numbers and intervening words ("one group", "2 additional groups"), while the
web helper only matches a digit directly before "group"/"grp" ("3 groups").

## Verified UI/API Mismatch On April 9, 2026

These are live PyRAT observations; they cannot be re-checked from the code.

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

- A `len(tanks.children) / requested_groups` calculation from the older API is
  only a local approximation of PyRAT performance.
- It should not be treated as a faithful reproduction of the PyRAT UI metric.
- For closer parity with PyRAT, MetaZebrobot prefers the newer authenticated
  crossing-detail endpoint over `api/v3/tanks/crossings` (implemented; see the
  mapping below).

## Recommended Mapping To Match PyRAT

Based on live checks from April 9, 2026, MetaZebrobot treats the PyRAT
crossing-detail payload as the authoritative source for performance-like values.
This mapping is implemented (see "How MetaZebrobot Currently Calculates
Performance" above, where numerator and denominator fall back independently
rather than as the paired steps listed here).

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

When no `backend/v1` detail counts are available (no frontend credentials, a
failed detail fetch, or a crossing never enriched and cached), MetaZebrobot
falls back to deriving `raised_count` from `tanks.children`, but live
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

- If the description doesn't follow the expected pattern, `requested_groups` returns `None` and, without `crossing_tanks`, performance shows as "N/A" (desktop) or "-" (web).
- The desktop and web parsers accept different phrasings (see above), so the same description can yield a value in one and `None` in the other.
- Descriptions may be entered inconsistently across users.
- Edits to descriptions after the fact can change the parsed value.
- It is used only as a fallback when `crossing_tanks` is not available.

### 3. Crossing status does not guarantee metric parity

The crossing workflow in PyRAT follows: **recorded → set-up → raised** (or **discarded**). If users don't advance crossings through these stages — particularly marking them as "raised" and associating child tanks — the data will not reflect actual outcomes.

However, the `17907` check (observed live) showed a `set-up` crossing with `date_of_raise = null`
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
  closer to PyRAT ground truth.** They are preferred whenever available.
- **Aggregate statistics (average performance, total raised)** in the desktop
  crossings tab use the same per-crossing fallbacks, so they are only as
  accurate as the mix of detail counts versus `len(child_tanks)` and parsed
  description text behind them.
- **"N/A" performance** should mean neither the authoritative counts nor the
  fallback requested-group parsing were available. It does not mean the crossing
  failed.

## Potential Improvements

- Validate with aquatics staff whether the "raised" workflow is being followed consistently.
- Make sure frontend credentials are configured wherever crossings are viewed,
  so the authenticated crossing-detail counts are used rather than fallbacks.
- Share one `requested_groups` parser between the desktop model and the web
  helper.
- Consider adding a manual override or confirmation field for performance if the
  PyRAT UI metric remains unavailable via API.
- Track which crossings have been verified vs. inferred.
