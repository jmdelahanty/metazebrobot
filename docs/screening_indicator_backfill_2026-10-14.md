---
title: "Screening Indicator Backfill Review (2026-10-14)"
summary: "Dry-run matches of the 42 existing screening steps' free-text indicators to dish constructs, for review before the backfill is applied."
owner: metazebrobot
status: current
kind: investigation
verified_against: c43a088
---

# Screening Indicator Backfill Review (2026-10-14)

Output of `scripts/backfill_screening_indicators.py --db-path /nvme1/zebrobot.db`
(read-only dry run) for
[linking screening indicators to constructs](construct_screening_link_design.md).
Rules: `utils/indicator_match.py`. Decisions applied: "Both/Final Brightness"
is read as positive for both constructs at low confidence, and a step counts
as pigment-screened if its text or its checkbox says so. Nothing is written
until the backfill is applied with `--apply`.

42 steps on 39 dishes, 71 indicator rows.

| kind | confidence | rows |
|---|---|---|
| construct | high | 45 |
| construct | low | 8 |
| construct | medium | 2 |
| pigment | high | 16 |

| dish | step | dpf | raw indicators | pigment box | → kind | construct | rule | confidence | note |
|---|---|---|---|---|---|---|---|---|---|
| 15062_1 | 20250311T14:51:16 | 4 | `["Her4.1:jRGECO1b"]` | False | construct | Tg(Her4.1:jRGECO1b) | promoter_reporter | high |  |
| 15178_1 | 20250403T15:46:45 | 6 | `["Both/Final Brightness, Pigment"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | construct | Tg(elavl3:jRGECO1b) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | pigment |  | pigment_text | high |  |
| 15178_2 | 20250403T15:53:39 | 6 | `["Both/Final Brightness, Pigment"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | construct | Tg(elavl3:jRGECO1b) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | pigment |  | pigment_text | high |  |
| 15180_1 | 20250331T16:32:06 | 3 | `["Pigment, elavl3:jRGECO1b"]` | False | pigment |  | pigment_text | high |  |
| | | | | | construct | Tg(elavl3:jRGECO1b) | promoter_reporter | high |  |
| 15180_1 | 20250403T16:33:50 | 6 | `["Both/Final Brightness"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | construct | Tg(elavl3:jRGECO1b) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| 15180_2 | 20250331T16:40:17 | 3 | `["Pigment, elavl3:jRGECO1b"]` | False | pigment |  | pigment_text | high |  |
| | | | | | construct | Tg(elavl3:jRGECO1b) | promoter_reporter | high |  |
| 15180_2 | 20250403T16:40:54 | 6 | `["Both/Final Brightness"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| | | | | | construct | Tg(elavl3:jRGECO1b) | legacy_both_brightness | low | Early screen labelled 'Both/Final Brightness'; read as positive for both constructs if bright (Jeremy, 2026-10-14, uncertain). |
| 15180_3 | 20250401T16:43:07 | 4 | `["Pigment, elavl3:jRGECO1b"]` | False | pigment |  | pigment_text | high |  |
| | | | | | construct | Tg(elavl3:jRGECO1b) | promoter_reporter | high |  |
| 15180_3 | 20250402T18:21:42 | 5 | `["gfap:TRPV1-T2A-GFP"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | promoter_reporter | high |  |
| 15180_4 | 20250401T16:51:26 | 4 | `["Pigment, elavl3:jRGECO1b"]` | False | pigment |  | pigment_text | high |  |
| | | | | | construct | Tg(elavl3:jRGECO1b) | promoter_reporter | high |  |
| 15180_5 | 20250401T16:52:52 | 4 | `["Pigment, elavl3:jRGECO1b"]` | False | pigment |  | pigment_text | high |  |
| | | | | | construct | Tg(elavl3:jRGECO1b) | promoter_reporter | high |  |
| 17907_2 | 20260413T16:49:00 | 6 | `["GRAB-5HT"]` | True | construct | Tg(elavl3:GRAB-5HT) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 17990_2 | 20260423T13:54:00 | 7 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 17990_4 | 20260423T15:13:00 | 7 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 17990_5 | 20260422T14:02:00 | 6 | `["jgcamp8f", "pmca2-mcherry"]` | False | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| | | | | | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| 17990_6 | 20260422T12:15:00 | 6 | `["jgcamp8f", "pmca2-mcherry"]` | False | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| | | | | | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| 17990_7 | 20260423T13:44:00 | 7 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 18178_1 | 20260518T20:14:00 | 6 | `["GRABATP1.0"]` | False | construct | Tg(elavl3:GRABATP1.0) | reporter | high |  |
| 18178_2 | 20260518T19:56:00 | 6 | `["GRABATP1.0"]` | False | construct | Tg(elavl3:GRABATP1.0) | reporter | high |  |
| 18178_3 | 20260518T20:05:00 | 6 | `["GRABATP1.0"]` | False | construct | Tg(elavl3:GRABATP1.0) | reporter | high |  |
| 18225_1 | 20260520T22:06:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_2 | 20260520T22:20:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_3 | 20260520T22:30:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_4 | 20260520T22:48:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_5 | 20260520T23:00:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_6 | 20260520T23:13:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_7 | 20260520T23:30:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18225_8 | 20260520T23:38:00 | 6 | `["jRGECO1b"]` | True | construct | Tg(gfap:jRGECO1b) | reporter | high |  |
| | | | | | pigment |  | pigment_flag | high |  |
| 18300_1 | 20260526T18:43:00 | 4 | `["jgcamp8f", "pmca2-mcherry"]` | False | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| | | | | | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| 18300_2 | 20260526T19:19:00 | 4 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 18300_3 | 20260526T20:59:00 | 4 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 18300_4 | 20260526T21:15:00 | 4 | `["pmca2-mcherry", "jgcamp8f"]` | False | construct | Tg(her4.1:PMCA2-mCherry) | reporter | high |  |
| | | | | | construct | Tg(elavl3:jGCaMP8f) | reporter | high |  |
| 19120_1 | 20260915T17:53:00 | 4 | `["CoChR-eGFP"]` | False | construct | Tg(Her4.1:CoChR-eGFP) | reporter | high |  |
| 19120_2 | 20260915T17:58:00 | 4 | `["CoChR-eGFP"]` | False | construct | Tg(Her4.1:CoChR-eGFP) | reporter | high |  |
| 19120_3 | 20260915T18:19:00 | 4 | `["CoChR-eGFP"]` | False | construct | Tg(Her4.1:CoChR-eGFP) | reporter | high |  |
| 19120_4 | 20260915T18:37:00 | 4 | `["CoChR-eGFP"]` | False | construct | Tg(Her4.1:CoChR-eGFP) | reporter | high |  |
| 19219_1 | 20261002T13:50:00 | 4 | `["iglusnfr3"]` | False | construct | Tg(elavl3:iGluSnFR3) | reporter | high |  |
| 19220_1 | 20261002T12:27:00 | 4 | `["b-ark"]` | False | construct | Tg(gfap:b-ARK) | reporter | high |  |
| 19220_2 | 20261002T12:29:00 | 4 | `["b-ark"]` | False | construct | Tg(gfap:b-ARK) | reporter | high |  |
| 19234_1 | 20261005T11:18:00 | 5 | `["mCherry"]` | False | construct | Tg(gfap:PMCA2-mCherry-zf) | fluorophore_only | medium |  |
| 19234_2 | 20261005T11:20:00 | 5 | `["mCherry"]` | False | construct | Tg(gfap:PMCA2-mCherry-zf) | fluorophore_only | medium |  |
| TOUR_14781_1 | 20260817T13:51:36 | 5 | `["gfap:TRPV1-T2A-GFP"]` | False | construct | Tg(gfap:TRPV1-T2A-GFP) | promoter_reporter | high |  |
