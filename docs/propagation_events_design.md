---
title: "Propagation Events and Reference Galleries"
summary: "Proposal: record each propagation (fish handed to aquatics to raise a line) as an event with its dish, screen, count and chosen reference images, so a line's propagations can be compared over time and references picked from one gallery."
owner: metazebrobot
status: current
kind: design
verified_against: 6577bdb
---

# Propagation Events and Reference Galleries

Status (2026-10-15): decisions below; being built.

## Problem

Propagation is only a dish termination reason (`propagation`), so nothing
records what was handed over: which line, how many fish, from which screen,
what they looked like, or which PyRAT tank they became. Screening images are
now linked to dishes ([screening images](screening_images_design.md)), but
there's no view across generations of a line. Reference images for screening
(the References page, `genotype_reference_images`) are PNG copies made by
hand, separate from the linked originals.

## Proposal

### Propagation events

| Field | Example | Source |
|---|---|---|
| `event_id` | uuid | minted |
| `dish_ids` | 19327_4_pos1 | the dish(es) propagated |
| `propagated_on`, `recorded_by` | 2026-10-15, Jeremy | form; defaults to the dish's termination date |
| `line_construct` | `Tg(gfap:PMCA2-mCherry-zf)` | the dish's constructs; chosen when several |
| `fish_count` | 20 | dish count at termination |
| `screening_step` | 19327_4, 10-15 12:04, positives | the step the dish was split from |
| `generation` | F3 | the cross's parent generation + 1, editable |
| `pyrat_tank_id` | (later) | entered, or proposed by the nightly sync from new tanks of that strain and birth date |
| `notes` | | free text |

- **Created** when a dish is terminated for propagation (the terminate form
  offers it), or afterwards from the dish page. Existing propagation dishes
  (five today, including 19327_4_pos1) can be backfilled from their
  termination fields.
- **Reference images:** a propagation event picks some of its dish's linked
  images as "what these fish looked like". No copies; the images stay links.

### Views

- **Line history** (`/lines/<construct key>`): every propagation of a line,
  oldest to newest, each with date, generation, count, source cross and its
  reference images side by side. This shows whether positives look consistent
  across generations.
- **Reference gallery** (`/references/`, extended): images marked as
  references, filterable by construct or line. These are linked images
  (propagation references and others flagged as references) alongside today's
  genotype reference PNGs. The screening page's reference strip draws from it,
  so people pick "what a good positive looks like" from real, sourced images.

### Data shape

- `propagation_events` plus `propagation_event_dishes` (an event can combine
  dishes).
- `image_links` gains a reference flag and optional caption, so any linked
  image (from a propagation, a plate or a screen) can be marked as a reference
  for its construct.
- Today's `genotype_reference_images` stay working. New references come from
  linked images, so no more copies.

## Decisions (Jeremy, 2026-10-15)

- **One event, many dishes, possibly several days.** Dishes can't be
  overcrowded, so a propagation's positives often span several dishes, and
  screening can continue the next day. An event groups any number of
  dishes; each keeps its own hand-over date (its termination date) and count.
- **Grouping is explicit.** A Propagation page lists propagation-terminated
  dishes not yet in an event. Selected dishes create a new event, or join an
  existing one. Nothing is grouped automatically. This also covers the five
  existing propagation dishes.
- **Generation is suggested, labelled and editable.** The suggestion is the
  highest parent-tank generation in PyRAT + 1 (e.g. F2 × F1 → F3), recomputed
  as dishes are added. It's stored as `generation` with
  `generation_source = suggested` and its basis text (e.g. "parents: tank
  7472 F2, tank 8131 F1"). An edited value is `generation_source = entered`
  and isn't recomputed. Parents without a generation in PyRAT give no
  suggestion.
- **No automatic PyRAT tank link.** There's no way to tie a set of dishes to
  the tank they became, so `resulting_tank_id` is optional, entered by hand,
  and labelled as such.
