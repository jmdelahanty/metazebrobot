---
title: "Crossing Tank Group on Dishes"
summary: "Enter the crossing tank group written on the aquatics sticker when creating a dish, so screening results can later be read per parent group; the value is as-labelled, not verified."
owner: metazebrobot
status: current
kind: design
verified_against: 81de027
---

# Crossing Tank Group on Dishes

Status (2026-10-27): built (entry and display only).

## Problem

A PyRAT crossing can be set up as several crossing tanks (groups), each with
its own parent fish. Screening crosses for a mixed carrier tank (7472) give
very different positive rates per dish, and the rates only mean something per
group. PyRAT's API, as we use it, reports parent counts per crossing, not per
group, and MetaZebrobot recorded only the parent tanks per dish.

Aquatics writes the group on the dish sticker.

## What is built

- The dish model already had `source_group_id` (set from the old desktop app
  on 32 dishes). The web new-dish form now has a "Crossing tank group" field,
  free text as written on the sticker (e.g. `19445-G2`), optional, trimmed.
- The screening page header shows it, marked "from the sticker".
- Dishes split from a dish (`_pos<n>`) already inherit it.

## Caveat

The sticker may not match what was actually set up; that is still being
checked with aquatics. The value is recorded as labelled, not verified.

## Not built yet

- Editing the group after the dish is created.
- Per-group positive rates on the cross pages.
- A "dim / unsure" screening class (separate decision).
