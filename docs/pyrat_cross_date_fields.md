---
title: "PyRAT Crossing Date Fields Investigation"
summary: "Which PyRAT crossing date fields MetaZebrobot uses for dish dates, and why."
owner: metazebrobot
status: current
kind: investigation
verified_against: 384a366
---

# PyRAT Crossing Date Fields Investigation

## Context

Crossing `18178` exposed a mismatch between the date shown in the PyRAT crossing
list UI and the date MetaZebrobot was using to prefill new dish dates.

The PyRAT UI showed:

- `Crossing ID`: `18178`
- `Record date`: `05/11/2026`
- `Responsible`: `Delahanty Jeremy`
- `Performance`: `1 / 2`
- `Line / Strain`: `Tg(elavl3:GRABATP1.0)`

MetaZebrobot had been prefilling from PyRAT `date_of_set_up`, which produced:

- `cross_setup_date`: `20260507`
- `dof`: `20260508`
- `dof_source`: `pyrat_setup_plus_1`

This appeared inconsistent with the visible PyRAT UI date.

## Live PyRAT API observations

Checked on 2026-05-18 against live PyRAT. These are live observations and
cannot be re-checked from the code. (MetaZebrobot's shared `CROSSING_FIELDS`
request list in `api_server.py` does not ask `api/v3` for the detail-only
fields below, consistent with the rejection noted here.)

### `api/v3/tanks/crossings`

Requesting crossing `18178` from the public API returned:

```text
crossing_id: 18178
status: set-up
date_of_record: 2026-05-11T00:00:00
date_of_set_up: 2026-05-07T08:53:04
date_of_raise: null
responsible_fullname: Delahanty Jeremy
strain_name: Tg(elavl3:GRABATP1.0)
description: 2 Groups for propagation please! Hopefully today they produce, good luck fish.
```

The same response included parent tank metadata under `tanks.parents` and no child
tanks under `tanks.children`.

The `api/v3/tanks/crossings` endpoint rejects performance/detail fields such as
`crossing_tanks`, `raised_tanks`, `really_raised_tanks`, and `completed` as
invalid `k` values. Those fields are not available from this endpoint.

### `backend/v1/tanks/crossings/18178/details`

The frontend-backed detail endpoint returned the same date values:

```text
date_of_record: 2026-05-11T00:00:00
date_of_set_up: 2026-05-07T08:53:04
date_of_raise: null
status: set-up
completed: false
crossing_tanks: 2
raised_tanks: 1
really_raised_tanks: 1
```

This matches the PyRAT UI performance value of `1 / 2`, but it preserves the same
`date_of_record` / `date_of_set_up` discrepancy.

## Current interpretation

Based on the observed data:

- `date_of_record` appears to match the PyRAT crossing table's visible `Record date` column.
- `date_of_set_up` is a separate backend workflow timestamp and may not be the same as the date shown in the crossing list UI.
- `date_of_set_up` can apparently be earlier than `date_of_record`, at least for crossing `18178`.
- `date_of_raise` is `null` while `status` is `set-up`, so this crossing has not been marked raised in PyRAT's workflow.
- The API itself does not document why `date_of_set_up` is earlier than `date_of_record` or which field should be treated as the biological setup/fertilization date.

One plausible explanation is that a user action in the PyRAT GUI may have moved
the crossing into `set-up` state earlier, while the requested/visible record date
remained `2026-05-11`. This has not been confirmed.

## MetaZebrobot behavior at time of investigation

This is still the behavior as of commit `384a366`
(`_cross_prefill_from_payload()` in `api_server.py`). MetaZebrobot dish prefill
uses this precedence:

```text
if PyRAT date_of_set_up exists:
    cross_setup_date = date_of_set_up
    dof = date_of_set_up + 1 day
    dof_source = pyrat_setup_plus_1
else:
    dof = date_of_record
    dof_source = pyrat_record_date
```

Only the date part of each PyRAT timestamp is used (no timezone conversion);
the chosen `dof_source` is stored on the dish and shown under the DOF field.

For crossing `18178`, this caused new dishes to prefill from `2026-05-07` rather
than the `2026-05-11` date visible in the PyRAT table.

Where the payload comes from matters for the correction below: the new-dish
prefill reads the locally cached `crosses.data` payload first (filling any gaps
from the most recent existing dish for that cross), and only fetches
`api/v3/tanks/crossings` when the local prefill is incomplete.

As a local operational correction, the cached `crosses.data.date_of_set_up` for
crossing `18178` was patched to `2026-05-11T00:00:00`, and existing dish rows for
that cross were updated to:

```text
cross_setup_date = 20260511
dof = 20260512
```

This was a local cache/data correction only. It does not resolve the upstream
field-semantics question, and the cache patch is not durable: any later fetch
of crossing `18178` (the PyRAT crossings page, the new-dish live fallback, or
`scripts/refresh_cross_cache.py --refetch-cached`) goes through `_cache_cross_rows`, which merges
the fresh PyRAT payload over the cached one, so PyRAT's `2026-05-07` value
returns. Whether the patch is still in place has not been re-checked. The
patched dish rows are not affected by cache refreshes.

## Question for PyRAT/company maintainers

Ask PyRAT maintainers:

```text
For crossing 18178, api/v3 and backend/v1 both return:

date_of_record = 2026-05-11T00:00:00
date_of_set_up = 2026-05-07T08:53:04

The PyRAT UI crossing table displays Record date = 05/11/2026.

What event does date_of_set_up represent, and can it validly be earlier than
date_of_record? Which field should downstream systems use as the biological
crossing/setup/fertilization date?
```

## Possible MetaZebrobot follow-ups

- Prefer `date_of_record` for dish creation if the user-facing PyRAT table date is the intended biological crossing date.
- Preserve raw PyRAT payloads unchanged and add a local per-cross date override table for exceptions.
- Display both `date_of_record` and `date_of_set_up` in the dish creation UI when they differ, requiring user confirmation before prefilling DOF.
