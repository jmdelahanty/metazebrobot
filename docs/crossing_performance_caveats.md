# Crossing Performance Metrics — Known Limitations

## How Performance Is Currently Calculated

Performance for a crossing is calculated as:

```
performance = raised_count / requested_groups
```

- **`raised_count`**: The number of child tanks associated with the crossing in PyRAT (i.e., `len(child_tanks)` from the API response).
- **`requested_groups`**: Parsed from the free-text `description` field of the crossing using regex (e.g., "3 groups", "one group").

These values are displayed as a percentage in the UI (e.g., "100%", "50%") and color-coded green/orange/red.

## Why These Numbers May Not Be Accurate

### 1. `raised_count` depends on tanks being explicitly "raised" in PyRAT

A crossing's child tanks are only populated when someone marks tanks as raised from that crossing in PyRAT. If fish are propagated but not formally linked back to the crossing as raised tanks, `raised_count` will undercount. This means:

- Crossings where fish were successfully raised but not recorded as child tanks will show **artificially low performance** (or 0%).
- The "raised" status in PyRAT may not be consistently applied by all users.

### 2. `requested_groups` relies on free-text description parsing

The number of requested groups is extracted from the crossing's description field via pattern matching (e.g., "3 groups", "two additional groups"). This is fragile:

- If the description doesn't follow the expected pattern, `requested_groups` returns `None` and performance shows as "N/A".
- Descriptions may be entered inconsistently across users.
- Edits to descriptions after the fact can change the parsed value.

### 3. Users may not be updating crossing status correctly

The crossing workflow in PyRAT follows: **recorded → set-up → raised** (or **discarded**). If users don't advance crossings through these stages — particularly marking them as "raised" and associating child tanks — the data will not reflect actual outcomes.

## What This Means in Practice

- **Performance values should be treated as estimates, not ground truth.** A crossing showing 0% performance may have successfully produced fish that simply weren't linked in PyRAT.
- **Aggregate statistics (average performance, total raised)** inherit these inaccuracies and may underrepresent actual productivity.
- **"N/A" performance** means the requested group count couldn't be parsed — it does not mean the crossing failed.

## Potential Improvements

- Validate with aquatics staff whether the "raised" workflow is being followed consistently.
- Consider adding a manual override or confirmation field for performance if PyRAT data proves unreliable.
- Track which crossings have been verified vs. inferred.
