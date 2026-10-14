---
title: "Construct and Screening Data Inventory (2026-10-14)"
summary: "Read-only inventory of unmatched constructs, screening-indicator backfill matches, unparsed strains, and open questions for the lab, taken before the construct catalog work."
owner: metazebrobot
status: current
kind: investigation
verified_against: f4ebc43
---

# Construct and Screening Data Inventory (2026-10-14)

Input to [linking screening indicators to constructs](construct_screening_link_design.md).
Answers to the questions in section 4 go back into that design note and the
catalog; this page stays a dated snapshot.


Source: the production database, opened read-only and queried 2026-10-14. Nothing was written. Snapshot only: the counts and flags below describe that date.
Totals: 219 dishes (4 active), 122 `dish_transgenes` rows on 86 dishes (57 `alias_exact`, 65 `unmatched`),
13 distinct constructs, 7 catalog entries, 42 screening steps on 39 dishes, 58 indicator tokens.

How rows get made (read from `src/metazebrobot/data/data_manager.py`):
- `parse_genotype` regex-extracts `Tg(...)`/`Et(...)` blocks from `dishes.genotype`. `construct` is the raw
  match (case kept). `promoter` and `reporter` are lowercased.
- `classify_construct` sets the role from substrings in the reporter: grab/gcamp/jrgeco/rgeco/campari → sensor,
  then effector patterns, then any fluorophore → `fluorescent_reporter`, otherwise `unknown`.
- `resolve_construct_catalog_match` matches the **reporter only** (promoter ignored), using
  `re.sub('[^a-z0-9]+','',lower)` against `construct_aliases.normalized_alias`. A hit is `alias_exact`; anything else is `unmatched`.
- `_dish_transgene_source`: `parent_dish` if parent_dish_id is set, else `crossing` if cross_id is set. The rows
  always come from the dish's own genotype string, even when source_type is `crossing`.
- `utils/strain_parser.parse_strain_name` wraps the same `parse_genotype`.

## 1. Construct inventory

SQL:
```sql
-- per-construct attributes
SELECT construct, promoter, reporter, fluorophore, fluorophore_color, construct_role, match_method,
       catalog_id, source_type, count(*) n
FROM dish_transgenes GROUP BY 1,2,3,4,5,6,7,8,9 ORDER BY 1;
-- per-construct dish counts, dates (dof, falling back to date_created), crosses
SELECT t.construct, count(DISTINCT t.dish_id) dishes, sum(d.status='active') active,
       min(coalesce(d.dof,d.date_created)) earliest, max(coalesce(d.dof,d.date_created)) latest,
       group_concat(DISTINCT d.cross_id) crosses
FROM dish_transgenes t JOIN dishes d USING(dish_id) GROUP BY t.construct;
-- strain names
SELECT DISTINCT t.construct, c.line_strain, json_extract(c.data,'$.strain_name')
FROM dish_transgenes t JOIN dishes d USING(dish_id) LEFT JOIN crosses c ON c.cross_id=d.cross_id;
```

| construct | promoter | reporter | fluorophore / color | role | match | catalog | dishes (active) | earliest–latest dof | crosses | PyRAT strain(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| Tg(Her4.1:CoChR-eGFP) | her4.1 | cochr-egfp | gfp / green | effector | alias_exact | 6 CoChR-eGFP | 5 (0) | 20260911 | 19120 | Tg(Her4.1:CoChR-eGFP) [85] |
| Tg(Her4.1:jRGECO1b) | her4.1 | jrgeco1b | jrgeco / red | sensor | alias_exact | 3 jRGECO1b | 4 (0) | 20250307–20250314 | 15062, 15090 | Tg(gfap:TRPV1-T2A-GFP); Tg(Her4.1:jRGECO1b) [1074] |
| Tg(elavl3:GCaMP7ff) | elavl3 | gcamp7ff | gcamp / green | sensor | **unmatched** | – | 8 (0) | 20260506 | 18055 | Tg(elavl3:GCaMP7ff) [68] |
| Tg(elavl3:GRAB-5HT) | elavl3 | grab-5ht | **NULL / NULL** | sensor | alias_exact | 1 GRAB-5HT | 2 (0) | 20260407 | 17907 | Tg(elavl3:GRAB-5HT) [984] |
| Tg(elavl3:GRABATP1.0) | elavl3 | grabatp1.0 | **NULL / NULL** | sensor | alias_exact | 3200 GRABATP1.0 | 6 (0) | 20260512 | 18178 | "Tg(elavl3:GRABATP1.0) " [366] (trailing space) |
| Tg(elavl3:iGluSnFR3) | elavl3 | iglusnfr3 | **NULL / NULL** | **unknown** | **unmatched** | – | 4 (0) | 20260928 | 19219 | Tg(elavl3:iGluSnFR3) [1016] |
| Tg(elavl3:jGCaMP8f) | elavl3 | jgcamp8f | gcamp / green | sensor | **unmatched** | – | 22 (0) | 20260416–20260522 | 17990, 18300 | Tg(elavl3:jGCaMP8f); Tg(her4.1:PMCA2-mCherry) [1227] |
| Tg(elavl3:jRGECO1b) | elavl3 | jrgeco1b | jrgeco / red | sensor | alias_exact | 3 jRGECO1b | 10 (0) | 20250328–20260812 | 15178, 15180, 17313, 14781 (TOUR) | ...TRPV1...; Tg(elavl3:jRGECO1b) [1107]; Tg(elavl3:jRGECO1b); Tg(gfap:CoChR-eGFP) [799]; **Casper_HHMI** (14781, TOUR dish) |
| Tg(gfap:CoChR-eGFP) | gfap | cochr-egfp | gfp / green | effector | alias_exact | 6 CoChR-eGFP | 1 (0) | 20260116 | 17313 | [799] |
| Tg(gfap:TRPV1-T2A-GFP) | gfap | trpv1-t2a-gfp | gfp / green | effector | alias_exact | 5 TRPV1-T2A-GFP | 13 (0) | 20250307–20260812 | 15062, 15090, 15178, 15180, 14781 (TOUR) | [1074], [1107], **Casper_HHMI** (TOUR) |
| Tg(gfap:b-ARK) | gfap | b-ark | **NULL / NULL** | **unknown** | **unmatched** | – | 9 (**1**: 19220_1) | 20260928 | 19220 | Tg(gfap:b-ARK) [786] |
| Tg(gfap:jRGECO1b) | gfap | jrgeco1b | jrgeco / red | sensor | alias_exact | 3 jRGECO1b | 16 (0) | 20260514 | 18225 | Tg(gfap:jRGECO1b) [97] |
| Tg(her4.1:PMCA2-mCherry) | her4.1 | pmca2-mcherry | mcherry / red | **fluorescent_reporter** | **unmatched** | – | 22 (0) | 20260416–20260522 | 17990, 18300 | [1227] |

Unmatched by construct: jGCaMP8f 22, PMCA2-mCherry 22, b-ARK 9, GCaMP7ff 8, iGluSnFR3 4 = 65 rows.

### Inconsistencies found
1. **Case variants of the promoter in `construct`.** `Tg(Her4.1:...)` (CoChR-eGFP, jRGECO1b) vs `Tg(her4.1:PMCA2-mCherry)`.
   The `promoter` column is lowercased (`her4.1`) in every case, so a promoter query works. But `construct` and
   `UNIQUE(dish_id, construct)` are case-sensitive, so a join on `construct` treats Her4.1 and her4.1 as different.
   The case comes straight from the PyRAT strain names. The screening token `Her4.1:jRGECO1b` (step 1) has the same variant.
2. **Role misclassification.**
   - PMCA2-mCherry is `fluorescent_reporter` (rule: ends in mCherry). It is an effector (CalEx Ca²⁺ pump), per the design note.
   - b-ARK is `unknown` with a NULL fluorophore. Per the design note it is iβARK-P2A-mCherry: an effector with a red, co-expressed readout.
   - iGluSnFR3 is `unknown` with a NULL fluorophore. It should be a sensor (glutamate, green).
3. **Missing fluorophore/spectra on catalog-matched sensors.** GRAB-5HT and GRABATP1.0 have `fluorophore`,
   `excitation_nm`, `emission_nm` and `fluorophore_color` all NULL in `dish_transgenes`, although catalog rows 1 and 3200
   give green / 488 / 509–520. The parser doesn't read spectra from the catalog, and "grab" isn't in the fluorophore patterns.
4. **`fluorophore` holds sensor family names, not proteins.** `jrgeco` and `gcamp` are stored where values like
   `mcherry`/`gfp` are expected. This is harmless for color (red/green are right) but mixes two vocabularies.
5. **GCaMP7ff naming.** PyRAT strain 68 says `GCaMP7ff`. The standard name is jGCaMP7f (also 7b/7c/7s). It may be a typo or lab shorthand.
6. **Catalog gaps.** No alias for jgcamp8f, gcamp7ff, pmca2mcherry, bark or iglusnfr3. The `gcamp` alias maps to GCaMP6s,
   but matching is exact on the whole normalized reporter, so jGCaMP8f doesn't fall through to it (which is correct).
7. **Provenance mislabel on the TOUR dishes.** `TOUR_14781_1` and `TOUR_14781_1_pos1` have genotype
   `Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)`, `source_type=crossing`, and `source_id=14781`. Cross 14781 is
   `Casper_HHMI` (parents 6192/6310 Casper_HHMI F2, "1 Group for Robot Avoidance Assay"), so the constructs did not come
   from that cross. The genotype was typed for a demo/tour. These dishes inflate the jRGECO1b and TRPV1 dish counts and dates (20260812).
8. **Pigment-removed child dishes inherit constructs.** `18225_*_pig1` (8 dishes) get `Tg(gfap:jRGECO1b)` from their
   parent dish. Those fish were moved out under the `pigmented_screened` bucket and their fluorescence wasn't called,
   so dish-level construct presence there is "inherited genotype", not "screened positive".
9. **Legacy `transgenic_indicators` (10 rows, crosses 15062–17313).** It has typos `elavle3` and `CoChr-eGFP`, an empty
   color for 17313 jRGECO1b, and Her4.1:jRGECO1b `expected_expression` set to `pan-glial` on 15062 but `pan-neuronal` on 15090.
   `crossing_transgenic_indicators` is empty (0 rows).
10. Minor issues: the genotype for dish 17257 is `AB_Casper_HHMI` but the cross strain is `AB Casper_HHMI`, and the separator is
    sometimes `;` and sometimes `; ` (no effect on parsing).

### PyRAT strain variants not yet in any dish (they will hit the parser and catalog)
From `strains` (SQL: `SELECT * FROM strains WHERE name LIKE '%PMCA%' OR name LIKE '%ARK%' OR name LIKE '%EXPERIMENT%'`):
- PMCA2 has 8 spellings: `Tg(her4.1:PMCA2-mCherry)` 1172, `Tg(her4.1:PMCA2-mCherry-zf)` 1085, `Tg(her4.1:PMCA2-mCherry_J05)` 1109,
  `Tg(gfap:PMCA2-mCherry)` 1240, `Tg(gfap:PMCA2-mCherry-zf)` 1231, `Tg(gfap:PMCA2-mCherry-zf_J00)` 1120,
  `Tg(gfap:PMCA2-mCherry_J04)` 1099, and **`Tg(gfap:PMCA2-P2A-mCherry-zf_J00)` 1077 (a P2A co-expressed line, not a fusion)**.
  Also `Tg(gfap:mCherry-PMCA2wb)` 121 and `Tg(gfap(ATT):mCherry_hPMCA2wb)` 999 (official name `Tol2_gfap(ATT):mCherry_hPMCA2wb_B61`).
  The suffixes `-zf`, `_J00` and `_J04` would land in `reporter` and defeat exact alias matching.
- b-ARK: `Tg(gfap(ATT):b-ARK-D110)` 826 and `..._B77` 720 (the inactive control), `Tol2-gfap:b-ARK-B78` 708 (no `Tg(` prefix,
  so `parse_genotype` finds nothing), plus combinations with `Tg(dbh:KalTA4); (UAS:CoChR-eGFP)` 974/1058/1093. The bare
  `(UAS:CoChR-eGFP)` has no prefix and `jRGECO1a` appears there.

## 2. Screening-indicator backfill proposal

SQL: `SELECT id, dish_id, screening_datetime, dpf_screened, indicators_screened, pigment_screened, criteria FROM screening_steps ORDER BY dish_id, screening_datetime;`
joined in Python to `SELECT dish_id, construct, promoter, reporter, fluorophore, fluorophore_color, catalog_id FROM dish_transgenes`
and `SELECT normalized_alias, catalog_id FROM construct_aliases`. Matching was done by a one-off read-only script, not kept; the rules are below.

Tokenizing: each JSON list element is split on `,` and stripped. `/` is not split, so "Both/Final Brightness" stays one token.
Rules, applied in order, with norm = lowercase and strip non-alphanumerics:
1. norm == `pigment` → **pigment** (high).
2. Contains "brightness" or starts with "both" → all dish constructs, **ambiguous** (low).
3. Contains `:` → promoter and reporter both normalized-equal to one dish construct (high).
4. norm(token) == norm(reporter) of exactly one dish construct (high).
5. norm(token) is a catalog alias whose catalog_id is on exactly one dish construct (high). No tokens needed this rule.
6. Fluorophore-only token (mCherry/GFP/...) → the unique dish construct with that fluorophore (medium). If several
   match, it is ambiguous; if the dish has no constructs, it is unmatched.

Result: 58 tokens. 52 high, 4 low (ambiguous), 2 none (unmatched).

| step | dish | dpf | raw | token | proposed match | rule | conf | flag |
|---|---|---|---|---|---|---|---|---|
| 1 | 15062_1 | 4 | ["Her4.1:jRGECO1b"] | Her4.1:jRGECO1b | Tg(Her4.1:jRGECO1b) | 3 | high | criteria says "…, Pigmentation" but there's no Pigment token and pigment_screened=0 |
| 2 | 15178_1 | 6 | ["Both/Final Brightness, Pigment"] | Both/Final Brightness | TRPV1-T2A-GFP + elavl3:jRGECO1b | 2 | low | AMBIGUOUS |
| 2 | 15178_1 | 6 | 〃 | Pigment | pigment | 1 | high | pigment_screened=0 |
| 3 | 15178_2 | 6 | ["Both/Final Brightness, Pigment"] | Both/Final Brightness | both constructs | 2 | low | AMBIGUOUS |
| 3 | 15178_2 | 6 | 〃 | Pigment | pigment | 1 | high | pigment_screened=0 |
| 4,6,8,10,11 | 15180_1..5 | 3–4 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | 1 | high | pigment_screened=0 (all 5) |
| 4,6,8,10,11 | 15180_1..5 | 3–4 | 〃 | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | 3 | high | |
| 5, 7 | 15180_1, 15180_2 | 6 | ["Both/Final Brightness"] | Both/Final Brightness | both constructs | 2 | low | AMBIGUOUS |
| 9 | 15180_3 | 5 | ["gfap:TRPV1-T2A-GFP"] | gfap:TRPV1-T2A-GFP | Tg(gfap:TRPV1-T2A-GFP) | 3 | high | |
| 73 | 17907_2 | 6 | ["GRAB-5HT"] | GRAB-5HT | Tg(elavl3:GRAB-5HT) | 4 | high | |
| 68–72 | 17990_2,_4,_5,_6,_7 | 6–7 | ["pmca2-mcherry","jgcamp8f"] (either order) | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | 4 | high | |
| 68–72 | 〃 | | 〃 | jgcamp8f | Tg(elavl3:jGCaMP8f) | 4 | high | |
| 65–67 | 18178_1..3 | 6 | ["GRABATP1.0"] | GRABATP1.0 | Tg(elavl3:GRABATP1.0) | 4 | high | |
| 63, 85–91 | 18225_1..8 | 6 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | 4 | high | pigment_screened=1 but there's no Pigment token (the inverse of the legacy rows) |
| 92–95 | 18300_1..4 | 4 | ["jgcamp8f","pmca2-mcherry"] | jgcamp8f / pmca2-mcherry | Tg(elavl3:jGCaMP8f) / Tg(her4.1:PMCA2-mCherry) | 4 | high | |
| 110–113 | 19120_1..4 | 4 | ["CoChR-eGFP"] | CoChR-eGFP | Tg(Her4.1:CoChR-eGFP) | 4 | high | |
| 122 | 19219_1 | 4 | ["iglusnfr3"] | iglusnfr3 | Tg(elavl3:iGluSnFR3) | 4 | high | |
| 116, 119 | 19220_1, 19220_2 | 4 | ["b-ark"] | b-ark | Tg(gfap:b-ARK) | 4 | high | the readout seen was mCherry (P2A), per the design note |
| 131 | 19234_1 | 5 | ["mCherry"] | mCherry | **unmatched** | 6 | none | the dish has 0 constructs (EXPERIMENTAL). Candidate: Tg(gfap:PMCA2-mCherry-zf) from parent tank 7472 → medium once the genotype is fixed |
| 132 | 19234_2 | 5 | ["mCherry"] | mCherry | **unmatched** | 6 | none | same as 19234_1 |
| 96 | TOUR_14781_1 | 5 | ["gfap:TRPV1-T2A-GFP"] | gfap:TRPV1-T2A-GFP | Tg(gfap:TRPV1-T2A-GFP) | 3 | high | the dish genotype is not from its cross (see §1 #7) |

The full per-token table (58 rows) is in the appendix.

Ambiguous or problem cases:
- **"Both/Final Brightness"** (steps 2, 3, 5, 7 on 15178_1/2 and 15180_1/2). This is a brightness ranking across both
  constructs at 6 dpf ("Screen brightest in correct regions"), not a per-construct +/- call. Options: link it to both
  constructs with a `brightness_rank` criterion, or link it to neither.
- **The pigment flag disagrees with the tokens.** All 7 legacy steps that have a Pigment token have `pigment_screened=0`.
  All 8 steps on 18225 and 17907_2 have `pigment_screened=1` with no Pigment token. For backfill, the token or the flag
  can each imply pigment, but one rule has to be chosen.
- No color-only token is ambiguous today. The only color-only token is mCherry, on 19234, which has no constructs.
  Possible future clashes: on 17990/18300, a "green" token would be unique (jGCaMP8f) and a "red" token unique
  (PMCA2-mCherry). On 15062/15090/15178/15180 the green and red constructs are distinct. No dish currently carries
  two constructs of the same color.
- **19234 count fields.** `count_screened_this_step` is 7 and 11, but `count_before_step` and `count_after_step` are
  2 and 6, which are the counts left after the 10/09 well-plate transfer. They were probably recorded or backfilled after the transfer.

## 3. Dishes and crosses that parse to zero constructs

SQL:
```sql
SELECT d.genotype, count(*) dishes, sum(d.status='active') active, group_concat(DISTINCT d.cross_id)
FROM dishes d WHERE d.dish_id NOT IN (SELECT dish_id FROM dish_transgenes) GROUP BY d.genotype;
SELECT c.cross_id, c.line_strain, json_extract(c.data,'$.strain_id'),
       (SELECT group_concat(json_extract(p.value,'$.tank_id')||':'||json_extract(p.value,'$.strain_name')||'('||json_extract(p.value,'$.generation')||')',' + ')
          FROM json_each(c.data,'$.tanks.parents') p),
       json_extract(c.data,'$.description')
FROM crosses c WHERE c.cross_id IN (SELECT DISTINCT cross_id FROM dishes);
SELECT * FROM cross_parents WHERE cross_id IN ('19234','18418');
```

133 of 219 dishes have zero constructs. 127 of them are background or wild-type strains, which is expected:
Casper_HHMI 61 dishes, AB [AB IC] SEPT25 46, AB_Casper_HHMI 12, Casper_HHMI [AB-C] DEC25 8, all inactive.
Their parent tanks are all background strains, so nothing is missing.

**The 6 `EXPERIMENTAL` dishes (PyRAT strain_id 564) are the real gap:**

| cross | dishes (status) | strain | PyRAT description | parent tanks (from crosses.data.tanks and cross_parents) | construct hint |
|---|---|---|---|---|---|
| 18418 | 18418_1, _2, _3 (all inactive, euthanized 20260614) | EXPERIMENTAL | "1 group for experiments please" | 6482 AB Casper_HHMI F1 (0M/0F/5U), the only parent | **none**. The only parent is a background tank, so these are probably AB Casper (no transgene). No screening steps. |
| 19234 | 19234_1, _2, _3 (**all active**) | EXPERIMENTAL | "Screening cross for 7472, 5 groups, 1 TID 7472 male paired with 2 females" | 8130 Casper_HHMI [AB-C] DEC25 F1 (5M/0F, cross_parents role=male); **7472 `Tg(gfap:PMCA2-mCherry-zf)` F2** (strain 1231, 0M/10F/5U, role=female) | **Tg(gfap:PMCA2-mCherry-zf)**. `cross_parents.parsed_transgenes` already holds it (role fluorescent_reporter, reporter `pmca2-mcherry-zf`). It is a screening cross, so offspring are expected to be hemizygous or negative. |

**Active dishes affected: 3 of 4.** The 4 active dishes are 19234_1 (2 fish), 19234_2 (6), 19234_3 (10, a 12-well
plate), and 19220_1. 19220_1 has a construct but it is catalog-unmatched (b-ARK), so all 4 active dishes have unknown or unmatched construct data.

Notes on 19234:
- **19234_3 is a mixed population.** It holds 5 mCherry+ fish from 19234_1 (wells A1, A2, B1, B2, C1) and 5 mCherry−
  fish from 19234_2 (A3, A4, B3, B4, C4), per `dish_transfer_events` 21/22. Its `parent_dish_id` is 19234_1 only.
  A dish-level construct assignment would be wrong for half the plate, so these fish need fish- or well-level status.
- 19234_1 was recorded as all positive (7 → remain_parent). 19234_2 was recorded as all negative (11).
- The description says a 7472 **male**, but PyRAT lists 7472 as 0 males / 10 females / 5 unknown, and 8130 as males only.
  The sex roles in the description and in the tank records disagree.
- The promoter is **gfap**, not her4.1 like the 17990/18300 PMCA2 line, and the name has a `-zf` suffix. It is a different line from strain 1227.

## 4. Questions for the lab

1. **19234 (active):** Is the transgene `Tg(gfap:PMCA2-mCherry-zf)` from tank 7472? Should the dish genotype record it
   (as hemizygous, from one Tg parent)? Was the 7472 parent the male (as the description says) or the females (as PyRAT tank sex says)?
2. **19234_3 well plate:** Should screening status be per well/fish (A1/A2/B1/B2/C1 = mCherry+, A3/A4/B3/B4/C4 = mCherry−)
   instead of per dish? This is the first mixed dish.
3. **18418:** Was this plain AB Casper_HHMI (only tank 6482 listed), or did an unlisted Tg parent take part?
4. **PMCA2 lines:** For `her4.1:PMCA2-mCherry` (1227/1172), `-zf`, `_J0x` and `gfap:PMCA2-mCherry-zf` (1231): is mCherry
   fused, and at which end? Is `gfap:PMCA2-P2A-mCherry-zf_J00` (1077) the only P2A line? Do `-zf`
   (codon-optimized?) and `_J00`/`_J04`/`_J05` (founder/plasmid ids?) mark separate catalog entries, or variants of one?
5. **GCaMP7ff (strain 68, cross 18055):** Is this jGCaMP7f, or a real "7ff" variant?
6. **"Both/Final Brightness" (15178, 15180 at 6 dpf):** Was this a joint red+green brightness ranking, where kept fish were
   brightest in both? Should it link to both constructs, or be recorded as a brightness criterion with no +/- call?
7. **Pigment:** In the 2025 steps, `pigment_screened=0` although the indicator says "Pigment". In 18225/17907,
   `pigment_screened=1` with no Pigment token. Were pigmented fish actually removed in each case? Is
   `pigmented_screened` → `_pig1` the only reliable signal?
8. **18225 `_pig1` dishes:** Were the pigmented fish ever checked for gfap:jRGECO1b, or should their construct status be "unscreened"?
9. **TOUR_14781_1:** Is this a demo dish whose genotype was typed by hand? Should it be excluded from construct inventories,
   or re-pointed away from cross 14781 (Casper_HHMI)?
10. **Her4.1:jRGECO1b expected expression:** The 2025 legacy indicators say pan-glial on 15062 and pan-neuronal on 15090.
    Which is right? her4.1 is usually radial glia / progenitor.
11. **b-ARK D110 control lines (826/720):** If these are ever crossed, will the strain name always carry "D110"? Screening can't tell the control from the active line.

## Appendix: per-token backfill table

| step id | dish | datetime | dpf | pigment_screened | raw indicators_screened | token | proposed match | rule | confidence | flag | #constructs on dish |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15062_1 | 20250311T14:51:16 | 4 | 0 | ["Her4.1:jRGECO1b"] | Her4.1:jRGECO1b | Tg(Her4.1:jRGECO1b) | promoter:reporter exact (case-insensitive) | high | case variant of promoter | 2 |
| 2 | 15178_1 | 20250403T15:46:45 | 6 | 0 | ["Both/Final Brightness, Pigment"] | Both/Final Brightness | Tg(gfap:TRPV1-T2A-GFP) + Tg(elavl3:jRGECO1b) | "Both" = all dish constructs | low | AMBIGUOUS: brightness ranking, not a per-construct +/- call | 2 |
| 2 | 15178_1 | 20250403T15:46:45 | 6 | 0 | ["Both/Final Brightness, Pigment"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 3 | 15178_2 | 20250403T15:53:39 | 6 | 0 | ["Both/Final Brightness, Pigment"] | Both/Final Brightness | Tg(gfap:TRPV1-T2A-GFP) + Tg(elavl3:jRGECO1b) | "Both" = all dish constructs | low | AMBIGUOUS: brightness ranking, not a per-construct +/- call | 2 |
| 3 | 15178_2 | 20250403T15:53:39 | 6 | 0 | ["Both/Final Brightness, Pigment"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 4 | 15180_1 | 20250331T16:32:06 | 3 | 0 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 4 | 15180_1 | 20250331T16:32:06 | 3 | 0 | ["Pigment, elavl3:jRGECO1b"] | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 5 | 15180_1 | 20250403T16:33:50 | 6 | 0 | ["Both/Final Brightness"] | Both/Final Brightness | Tg(gfap:TRPV1-T2A-GFP) + Tg(elavl3:jRGECO1b) | "Both" = all dish constructs | low | AMBIGUOUS: brightness ranking, not a per-construct +/- call | 2 |
| 6 | 15180_2 | 20250331T16:40:17 | 3 | 0 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 6 | 15180_2 | 20250331T16:40:17 | 3 | 0 | ["Pigment, elavl3:jRGECO1b"] | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 7 | 15180_2 | 20250403T16:40:54 | 6 | 0 | ["Both/Final Brightness"] | Both/Final Brightness | Tg(gfap:TRPV1-T2A-GFP) + Tg(elavl3:jRGECO1b) | "Both" = all dish constructs | low | AMBIGUOUS: brightness ranking, not a per-construct +/- call | 2 |
| 8 | 15180_3 | 20250401T16:43:07 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 8 | 15180_3 | 20250401T16:43:07 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 9 | 15180_3 | 20250402T18:21:42 | 5 | 0 | ["gfap:TRPV1-T2A-GFP"] | gfap:TRPV1-T2A-GFP | Tg(gfap:TRPV1-T2A-GFP) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 10 | 15180_4 | 20250401T16:51:26 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 10 | 15180_4 | 20250401T16:51:26 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 11 | 15180_5 | 20250401T16:52:52 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | Pigment | pigment | literal "pigment" | high | pigment_screened=0 but token says Pigment | 2 |
| 11 | 15180_5 | 20250401T16:52:52 | 4 | 0 | ["Pigment, elavl3:jRGECO1b"] | elavl3:jRGECO1b | Tg(elavl3:jRGECO1b) | promoter:reporter exact (case-insensitive) | high |  | 2 |
| 73 | 17907_2 | 20260413T16:49:00 | 6 | 1 | ["GRAB-5HT"] | GRAB-5HT | Tg(elavl3:GRAB-5HT) | reporter exact (normalized) | high |  | 1 |
| 72 | 17990_2 | 20260423T13:54:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 72 | 17990_2 | 20260423T13:54:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 71 | 17990_4 | 20260423T15:13:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 71 | 17990_4 | 20260423T15:13:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 70 | 17990_5 | 20260422T14:02:00 | 6 | 0 | ["jgcamp8f", "pmca2-mcherry"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 70 | 17990_5 | 20260422T14:02:00 | 6 | 0 | ["jgcamp8f", "pmca2-mcherry"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 69 | 17990_6 | 20260422T12:15:00 | 6 | 0 | ["jgcamp8f", "pmca2-mcherry"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 69 | 17990_6 | 20260422T12:15:00 | 6 | 0 | ["jgcamp8f", "pmca2-mcherry"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 68 | 17990_7 | 20260423T13:44:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 68 | 17990_7 | 20260423T13:44:00 | 7 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 65 | 18178_1 | 20260518T20:14:00 | 6 | 0 | ["GRABATP1.0"] | GRABATP1.0 | Tg(elavl3:GRABATP1.0) | reporter exact (normalized) | high |  | 1 |
| 66 | 18178_2 | 20260518T19:56:00 | 6 | 0 | ["GRABATP1.0"] | GRABATP1.0 | Tg(elavl3:GRABATP1.0) | reporter exact (normalized) | high |  | 1 |
| 67 | 18178_3 | 20260518T20:05:00 | 6 | 0 | ["GRABATP1.0"] | GRABATP1.0 | Tg(elavl3:GRABATP1.0) | reporter exact (normalized) | high |  | 1 |
| 85 | 18225_1 | 20260520T22:06:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 86 | 18225_2 | 20260520T22:20:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 87 | 18225_3 | 20260520T22:30:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 88 | 18225_4 | 20260520T22:48:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 89 | 18225_5 | 20260520T23:00:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 90 | 18225_6 | 20260520T23:13:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 91 | 18225_7 | 20260520T23:30:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 63 | 18225_8 | 20260520T23:38:00 | 6 | 1 | ["jRGECO1b"] | jRGECO1b | Tg(gfap:jRGECO1b) | reporter exact (normalized) | high |  | 1 |
| 92 | 18300_1 | 20260526T18:43:00 | 4 | 0 | ["jgcamp8f", "pmca2-mcherry"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 92 | 18300_1 | 20260526T18:43:00 | 4 | 0 | ["jgcamp8f", "pmca2-mcherry"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 93 | 18300_2 | 20260526T19:19:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 93 | 18300_2 | 20260526T19:19:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 94 | 18300_3 | 20260526T20:59:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 94 | 18300_3 | 20260526T20:59:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 95 | 18300_4 | 20260526T21:15:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | pmca2-mcherry | Tg(her4.1:PMCA2-mCherry) | reporter exact (normalized) | high |  | 2 |
| 95 | 18300_4 | 20260526T21:15:00 | 4 | 0 | ["pmca2-mcherry", "jgcamp8f"] | jgcamp8f | Tg(elavl3:jGCaMP8f) | reporter exact (normalized) | high |  | 2 |
| 113 | 19120_1 | 20260915T17:53:00 | 4 | 0 | ["CoChR-eGFP"] | CoChR-eGFP | Tg(Her4.1:CoChR-eGFP) | reporter exact (normalized) | high |  | 1 |
| 112 | 19120_2 | 20260915T17:58:00 | 4 | 0 | ["CoChR-eGFP"] | CoChR-eGFP | Tg(Her4.1:CoChR-eGFP) | reporter exact (normalized) | high |  | 1 |
| 111 | 19120_3 | 20260915T18:19:00 | 4 | 0 | ["CoChR-eGFP"] | CoChR-eGFP | Tg(Her4.1:CoChR-eGFP) | reporter exact (normalized) | high |  | 1 |
| 110 | 19120_4 | 20260915T18:37:00 | 4 | 0 | ["CoChR-eGFP"] | CoChR-eGFP | Tg(Her4.1:CoChR-eGFP) | reporter exact (normalized) | high |  | 1 |
| 122 | 19219_1 | 20261002T13:50:00 | 4 | 0 | ["iglusnfr3"] | iglusnfr3 | Tg(elavl3:iGluSnFR3) | reporter exact (normalized) | high |  | 1 |
| 116 | 19220_1 | 20261002T12:27:00 | 4 | 0 | ["b-ark"] | b-ark | Tg(gfap:b-ARK) | reporter exact (normalized) | high |  | 1 |
| 119 | 19220_2 | 20261002T12:29:00 | 4 | 0 | ["b-ark"] | b-ark | Tg(gfap:b-ARK) | reporter exact (normalized) | high |  | 1 |
| 131 | 19234_1 | 20261005T11:18:00 | 5 | 0 | ["mCherry"] | mCherry | unmatched | fluorophore token, dish has no constructs | none |  | 0 |
| 132 | 19234_2 | 20261005T11:20:00 | 5 | 0 | ["mCherry"] | mCherry | unmatched | fluorophore token, dish has no constructs | none |  | 0 |
| 96 | TOUR_14781_1 | 20260817T13:51:36 | 5 | 0 | ["gfap:TRPV1-T2A-GFP"] | gfap:TRPV1-T2A-GFP | Tg(gfap:TRPV1-T2A-GFP) | promoter:reporter exact (case-insensitive) | high |  | 2 |

Counter({'high': 52, 'low': 4, 'none': 2})
58 tokens from 42 steps on 39 dishes
