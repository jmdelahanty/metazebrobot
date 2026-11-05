---
title: "Screening Report"
summary: "Proposal: a per-cross screening report (counts, plates, images, corrections) built as one self-contained file to send to the cross's owner, and finalizing with the computed count instead of typing it."
owner: metazebrobot
status: current
kind: design
verified_against: 2bc31ad
---

# Screening Report

Status (2026-11-04): proposal; nothing below is built.

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
- **Sending is possible later.** The service host can reach a lab mail
  server. Its settings belong in service configuration, not in this repo.
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
   one small same-scale thumbnail per well (the gallery's `?scale=dish`
   rendering, downsized to about 300 px, JPEG). The shared range is printed.
4. **Notes and flags:**
   - corrections (observations noted "Corrected from ...");
   - dishes of the cross with no screening step;
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

## Phase 2: send from the app (later)

- Mail server settings from the service environment
  (`METAZEBROBOT_SMTP_HOST`, port, sender address); none committed.
- An email address per user in the users table proposed in
  `user_scoped_workflow_design.md`.
- "Send to <owner>" on the preview; each send logged (cross, recipient,
  sender, time, report checksum) so it's clear what was sent.
- How the service authenticates to the mail server is to be settled with IT.

## Dependencies

- **Who screened:** screening steps don't record a screener yet. Until the
  owner-versus-actor work lands, the report names the user-picker user as the
  person producing it, not as the screener of each step.

## Open questions

- Recipient: the cross's PyRAT responsible by default, or the requester when
  they differ?
- Include dishes of the cross that were never screened, or only screened ones?
- Per-cross only, or also a per-session report ("everything I screened
  today") for the screener?
