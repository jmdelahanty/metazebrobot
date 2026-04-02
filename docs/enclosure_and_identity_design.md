# Enclosure Rework & Identity Assignment Design

## 1. Container type replaces `in_beaker` — DONE

### Problem

The original enclosure model had `in_beaker: bool`, a binary flag that didn't
capture the range of containers used in the lab.

### Solution

Replaced `in_beaker` with `container_type` on the dish:

```python
container_type: Literal["petri_dish", "beaker", "well_plate", "tank"]
```

Using a `Literal` (fixed set of allowed values) rather than a free string
to catch typos and enforce consistency. New types can be added to the Literal
as needed.

### Relationship to housing unit `unit_kind`

`container_type` describes the physical vessel. `unit_kind` describes
subdivisions within it:

| Container type | unit_kind | Example |
|---|---|---|
| `petri_dish` | `open` | Single shared space |
| `beaker` | `open` | Single shared space |
| `well_plate` | `well` | 6, 24, or 96 individual wells |
| `tank` | `open` | Aquatics system tank |

### Migration

Automatic migration at startup:
- Added `container_type TEXT` column to `dishes` table
- Backfilled: `in_beaker = True` → `"beaker"`, `False` → `"petri_dish"`
- Removed `in_beaker` from the Pydantic model
- Desktop UI checkbox replaced with dropdown

---

## 2. Screening model redesign — DONE

### Problem

The original screening model assumed one indicator per step (`indicator_screened: str`)
and tracked `number_positive` — which didn't capture multi-indicator screens,
pigment-only removals, or the actual disposition of fish.

### Solution

`ScreeningStep` now models one screening event where multiple criteria are
assessed simultaneously:

```python
class ScreeningStep(BaseModel):
    screening_datetime: str           # YYYYMMDDTHH:MM:SS
    dpf_screened: int
    indicators_screened: list[str]    # ["GFP", "jRGECO"], empty for pigment-only
    pigment_screened: bool            # whether pigmentation was assessed
    criteria: Optional[str]           # free-text: "fluorescence", "brightest"
    count_screened_this_step: int     # total fish examined
    number_kept: int                  # fish that passed all criteria
    number_removed_pigmented: Optional[int]
    number_removed_negative: Optional[int]
    number_removed_other: Optional[int]
    tricaine_used: bool
    notes: Optional[str]
```

Key design decisions:
- **`number_kept`** replaces `number_positive` — it's the actual count of fish
  remaining, regardless of which criteria they passed
- **Removal counts are the record** for euthanized fish — no derived dish is
  created for fish that won't be tracked further
- **Derived dishes** are created explicitly by the operator when fish are
  physically moved to a new container, with explicit fish count and container type

### Migration

Automatic migration at startup:
- `indicator_screened` (string) → `indicators_screened` (JSON array)
- `number_positive` → `number_kept`
- Added `pigment_screened` column

---

## 3. Derived dish creation — DONE

### Problem

Derived dishes were auto-calculated from screening step counts and only
supported positive/negative splits. Negative fish that would be immediately
euthanized still got a dish record.

### Solution

`POST /screening/{dish_id}/split` accepts explicit parameters:
- **`fish_count`** — operator enters the actual number (not auto-calculated)
- **`container_type`** — what container the fish go into
- **`population_type`** — positive_screened, negative_screened, or other
- **`notes`** — optional context

Fish that are removed and euthanized don't need a derived dish — the
`number_removed_*` fields on the screening step are the record.

---

## 4. Session/experiment tracking — REMOVED from MetaZebrobot

The `experiment_sessions` and `fish_runs` tables were removed. Session and
recording data belongs in Palette, which owns the behavioral pipeline.
MetaZebrobot can optionally read Palette's registry DB (read-only) to display
session counts on fish detail pages.

See `docs/identity_and_provenance_contract.md` for the full cross-repo
data flow.

---

## 5. Identity assignment workflow

### Two entry points for identity

**Path A — ID at screening:**

```
parent dish (bulk)
  → screen
    → derived dish (positive_screened, bulk)
      → register individual fish
        → assign to wells
          → (optional) behavioral session later
```

**Path B — ID at first behavioral session:**

```
parent dish (bulk)
  → screen
    → derived dish (positive_screened, bulk)
      → behavioral session (Citrus assigns ID here)
        → (optional) assign to wells afterward
```

### Core principle

**A fish gets an ID the first time it needs to be individually tracked.** The
system does not care which path triggered it. Once a fish has a `fish_id` UUID,
it carries forward through all subsequent operations.

The `subject_label` is an optional human-friendly name (e.g. `wt-01`, well
position) for bench use — the UUID is the real identity.

---

## 6. Remaining work

### Near-term

- [ ] Add automated tests for `POST /screening/{dish_id}/split`
- [ ] Coordinate with Citrus on identity assignment API calls
- [ ] Define H5 snapshot schema_version=2 format (per-fish metadata)

### Future

- [ ] Design `POST /dishes/{dish_id}/fish/place` batch endpoint
  (register N fish + create wells + assign in one call)
- [ ] Optional automatic well creation when splitting into well_plate
- [ ] Palette integration: read-only session count display on fish pages
