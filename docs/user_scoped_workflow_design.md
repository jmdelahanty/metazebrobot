---
title: "User-Scoped Crosses, Dishes, and Fish"
summary: "Proposal to let each lab member find their own PyRAT crosses live and see their own dishes and fish by default, keeping the cross cache for heritage."
owner: metazebrobot
status: current
kind: design
verified_against: fcdba01
---

# User-Scoped Crosses, Dishes, and Fish

Status (2026-10-09): proposal, agreed in direction; nothing below is built.

Goal: other lab members can manage their own crosses, dishes and individually
tracked fish without searching the database by hand.

## Problem

Creating a dish starts from a PyRAT cross. The cross suggestions on
`/dishes/new` come from `_load_new_dish_crosses` in
`src/metazebrobot/api_server.py`: up to 100 cached crosses that have active
dishes or no dishes, across all owners, ordered by active-dish count then
`cross_id` descending. There is no per-user filter. Finding a colleague's cross
(Zhao Peixiong, PyRAT `responsible_id` 135, cross 19234) took a manual DB
search.

Crosses set up after the last cache sync are not suggested. Typing the ID still
works, because `_load_cross_prefill` falls back to a live PyRAT
`tanks/crossings` lookup and caches the result.

## What exists today

- **Cross cache.** The `crosses` table is a local cache (16,621 rows on
  2026-10-09): one historical backfill plus the nightly
  `scripts/sync_cross_cache.py` (`deploy/metazebrobot-cross-sync.timer`, 02:30;
  `--days` default 30; all owners). Why bulk history is cached:
  [`tank_heritage_design.md`](tank_heritage_design.md).
- **User identity.** There is no login. `POST /set-user` stores a username in
  the `metazebrobot_user` cookie; `_current_user` reads it and falls back to the
  first name in `~/.pyrat_user_mapping.json`. `_pyrat_user_id` maps that
  username to a PyRAT user id through the same file (16 users; Zhao is not in
  it). See [`web_pages.md`](web_pages.md), "Global UI".
- **Live, user-scoped PyRAT views already exist.** `/pyrat/crossings/` and
  `/pyrat/tanks/` pass `responsible_id` to PyRAT `api/v3` when the mapping has
  the current user, and the crossings table links each cross to
  `/dishes/new?cross_id=...`. The new-dish "Refresh Crosses" panel syncs the
  current user's last 30 days of crosses into the cache. So filtering
  `tanks/crossings` by `responsible_id` is in use, not a guess.
- **Dish ownership is a name string.** `dishes.responsible` is free text,
  prefilled from PyRAT `responsible_fullname` and editable on the form. Values
  are inconsistent (both "Delahanty Jeremy" and "Jeremy Delahanty" occur).
  Fish (`fish_subjects`) have no owner field; they belong to a dish.

## Principle

Query PyRAT live for small, user-scoped, freshness-sensitive questions ("my
crosses without dishes"). Use the cache for bulk or historical derivation
(heritage, analytics). The gap is scoping, not storage.

## Proposed pieces (incremental)

1. **Complete the user mapping.** Add every lab member who uses the app to the
   username to PyRAT id mapping (Zhao first). Consider moving it from a file in
   the service user's home directory into the database so it can be edited and
   backed up with everything else.
2. **"My crosses" view.** Build on `/pyrat/crossings/` rather than a new page:
   a "without dishes" filter, age in dpf, and the existing one-click link to the
   prefilled `/dishes/new?cross_id=...`.
3. **New-dish suggestions prefer the user's live crosses.** Show the current
   user's recent PyRAT crosses first, then the existing cached list, so a cross
   set up today is suggested without waiting for the nightly sync.
4. **"My dishes and fish."** Dishes, Screening, Care and Fish lists default to
   the current user's dishes, with a whole-lab toggle. Fish are scoped through
   their dish.
5. **Cache unchanged.** The `crosses` table stays the backing store for
   heritage and analytics; nothing here replaces the nightly sync.

## Owners, screeners and names (agreed 2026-11-04)

A cross's owner and the person who screens its fish are often different
people. Agreed design, built in this order:

1. **`users` table, synced from PyRAT `api/v3/users`.** PyRAT user id
   (key), username, first name, last name, PyRAT full name ("Last First"),
   active/inactive, and an email address filled in by hand (PyRAT doesn't
   serve one). Pages show "First Last"; records store the username. It
   replaces `~/.pyrat_user_mapping.json` for the user picker and
   `_pyrat_user_id`. Since 2026-11-04 the service's PyRAT account can list
   every user (153), with `first_name`/`last_name`.
   - Names don't identify people: the same person can have two PyRAT accounts
     with near-identical names. Store the id; when two accounts are one
     person, the lab says which one is current.
   - Built 2026-11-04 (`data/users.py`, `scripts/sync_users.py`):
     `sync_users.py --db-path … --mark-lab <lab-owner-username>` refreshes all
     users and adds the lab owner's active lab members (Responsible for an
     open tank the owner owns) to the picker; it never removes anyone and
     keeps local emails. The picker shows "First Last" and falls back to the
     mapping file while the table is empty. Not yet on the nightly timer.
2. **`screened_by` on each screening step:** one username, set from the user
   picker when the step is created (screening form, or a step started from
   the plate page), editable in the steps table. A session is almost always
   one person.
   - **`recorded_by` on each allocation,** set automatically. If someone
     else books part of a step, it shows ("started by A; B recorded 6 of
     18") without a handover action. No handover button for now.
   - Backfill only from evidence: a step whose fish observations all name
     one observer gets that observer; others stay blank.
   - Built 2026-11-04: the web layer names the picker user as the request's
     actor (`utils/actor.py`); `FishDish.add_screening_step` and
     `add_screening_step_allocation` stamp it on new steps and allocations
     only, so loading and re-saving never attributes old records. Stored in
     `screening_steps.screened_by` and `screening_step_allocations.recorded_by`
     (dishes load steps from these tables). The steps table shows "Screened
     by" and "recorded by …" on allocations booked by someone else.
     `scripts/backfill_screened_by.py` does the evidence-only backfill.
3. **Dish owner from PyRAT, not free text.** New `responsible_user` on dishes,
   defaulting to the cross's PyRAT `responsible_id` (every cached cross of
   the 270 dishes on 2026-11-04 has one). It can be changed to another user,
   because the dish owner can differ from the cross owner: 16 dishes were on
   another member's crosses but raised and used by someone else, and their
   owner is the person who used the fish. The free-text `responsible` stays
   as the legacy display value.
   - Backfill: dishes whose `responsible` text names the cross owner get the
     cross owner; the rest are listed for review, not changed automatically.
4. **Screening report** ([`screening_report_design.md`](screening_report_design.md))
   uses all three: "Cross 19498 (PyRAT responsible: <First Last>), screened by
   <First Last> on 11-04".

## Open questions

- Users without PyRAT accounts (no `responsible_id`): show whole-lab views, or
  scope by dish `responsible` name only?
- Shared or co-owned crosses: PyRAT has one responsible per cross; how does a
  second person see it as theirs?
- Dishes whose responsible differs from the cross owner: scope "my dishes" by
  dish `responsible`, not by cross.
- Matching dishes to users: `dishes.responsible` is a name string in varying
  order. Store a normalized user key or PyRAT id on new dishes, and backfill
  existing rows by matching names to the mapping?

## Deferred

- **Screening indicators for unparsed genotypes.** The screening form suggests
  indicators from the dish's parsed transgene constructs
  (`_screening_indicator_suggestions` in `api_server.py`). A PyRAT strain named
  `EXPERIMENTAL` parses to no constructs, so cross 19234's mCherry screen had to be typed by hand. Possible
  sources: PyRAT's transgene records for the parent tanks or strain, or a
  per-cross indicator entered once. Jeremy to check what PyRAT records for
  these crosses first.
- **Name format for `responsible`.** Default to PyRAT's own form
  (`responsible_fullname`, "Last First", e.g. "Zhao Peixiong") when normalizing;
  Jeremy to confirm against PyRAT before any backfill.
