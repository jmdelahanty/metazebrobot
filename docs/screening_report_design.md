---
title: "Screening Report"
summary: "Proposal: a per-cross screening report (counts, plates, images, corrections) built as one self-contained file to send to the cross's owner, and finalizing with the computed count instead of typing it."
owner: metazebrobot
status: current
kind: design
verified_against: 2bc31ad
---

# Screening Report

Status (2026-11-04): proposal; only finalizing without typing is built.

Goal: when a cross's screening is done, the person who owns the cross gets a
short report of what was screened, what was kept and what it looked like,
without opening MetaZebrobot. The usual case is one lab member screening
another's cross.

## Constraints (checked 2026-11-04)

- **The site isn't reachable by recipients.** It answers on `127.0.0.1` only,
  so the report can't link back to it. It must be one self-contained file:
  HTML with its images inlined.
- **No email addresses.** PyRAT `api/v3/users` refuses `email`/`mail` fields
  (422). Addresses have to live in MetaZebrobot (see
  [`user_scoped_workflow_design.md`](user_scoped_workflow_design.md)).
- **Sending works.** Another lab service sends mail from the same host
  through a lab mail server without logging in. Its settings belong in the
  service environment, not in this repo. Only hhmi.org recipients are
  needed.
- **"Done" is rarely recorded.** Finalize (`POST /screening/{dish}/finalize`)
  asks for the final positive count and the date typed by hand; 9 of 270
  dishes have it.

## Finalizing without typing (do first)

The screening page already knows a dish's positives from its steps'
allocations. The finalize form becomes:

- **Count prefilled** with the computed positive count (positives booked to
  derived dishes and plates plus positives remaining in the dish), shown with
  how it was computed. It stays editable for legacy dishes whose steps don't
  add up.
- **Date prefilled** with today (lab time), as the step form's Date/Time
  already defaults to now.
- One button: "Finalize: N positives".

This is independent of the report and small, so it goes first.

Built (2026-11-04, `FishDish.computed_positive_count`): the form is prefilled
with the count and today's date and says how the count was made. It leaves
the count blank for dishes whose steps have no allocations (legacy or
unscreened) instead of guessing 0. Checked against the dishes already
finalized: every one with allocations matches its recorded count.

## Phase 1: build and download

**One report per cross**, from `GET /crosses/{cross_id}/screening-report`
(preview page), with downloads of the same content.

Contents, in order:

1. **Header:** cross, line, parent tanks (role, tank, strain, generation, born;
   `cross_parents`), set-up date, the request text, the cross's PyRAT
   responsible, and who produced the report and when (see Dependencies).
2. **Summary table, one row per dish:** fish at start, screened, positive,
   negative, pigmented, where they went (derived dishes and plates, discarded,
   remaining), and finalized or not. Counts come from the screening steps and
   their allocations, the same source as the screening page.
3. **Per plate:** the well grid with fish label and current call per well, and
   one small thumbnail per well: the gallery's enhanced (per-image contrast)
   rendering by default, downsized to about 300 px, JPEG.
4. **Notes and flags:**
   - corrections (observations noted "Corrected from ...");
   - dishes of the cross with no screening step, listed as "not screened"
     so the cross's progress is visible;
   - positives from only one dish when the cross's other dishes screened
     negative, which can point to a mix-up worth checking;
   - dishes not finalized, each with "Finalize: N positives".

Downloads:

- **HTML file:** the report as one file (thumbnails as `data:` URIs). Prints
  to PDF from any browser, so no PDF library is needed.
- **Email file (`.eml`):** a draft with subject "Cross <id> screening
  summary", the summary table as the body and the HTML report attached. "To"
  is left for the sender. It opens in Outlook or Apple Mail ready to send.

Size: twelve 300 px JPEG thumbnails are roughly 0.3-0.5 MB per plate, well
within mail limits.

## Saving and sending (agreed 2026-11-04: part of phase 1)

- **Every report is saved** when generated: the HTML and the `.eml`, under the
  service's data directory, with "Generated at <lab date-time> · MetaZebrobot
  <git commit>" in the report and the message.
- **Modes, as in the lab's other service:** `disabled`, `outbox` (save the
  `.eml` only) and `smtp` (save and send). Settings from the service
  environment: mode, host, port (default 25), STARTTLS (default off), From (a
  real hhmi.org mailbox with display name). None are committed.
- **Recipients:** the cross owner's address from the users table (filled in by
  hand), editable before sending.
- **Send log:** cross, recipients, sender, generated-at, commit, report
  checksum, mode and result, so it's clear what was sent to whom.
- **First real send** goes to the person running it, as a test.

## Dependencies

- **Owner, screener and names** come from the users table, `screened_by` and
  `responsible_user` in
  [`user_scoped_workflow_design.md`](user_scoped_workflow_design.md#owners-screeners-and-names-agreed-2026-11-04).

## Open questions

- Also a per-session report ("everything I screened today") for the
  screener?
