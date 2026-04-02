#!/usr/bin/env python3
"""
Operator walkthrough — guided exercise of the full fish tracking workflow.

Runs against a live MetaZebrobot API server and real database.  The operator
runs each step, checks the web UI at the printed URLs, and presses Enter to
continue.  All test data is cleaned up at the end (even on Ctrl+C).

Prerequisites
─────────────
  • API server running:
      pixi run python -m metazebrobot.api_server --db-path /path/to/zebrobot.db
  • At least one real cross in the database (from PyRAT sync)

Usage
─────
  # Interactive (pauses at each step so you can check the web UI):
  pixi run python scripts/walkthrough.py --db-path /path/to/zebrobot.db [--port 8002]

  # Automated (runs straight through, no pauses — good for CI / smoke tests):
  pixi run python scripts/walkthrough.py --db-path /path/to/zebrobot.db --non-interactive
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ── Colours for terminal output ─────────────────────────────────────

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"

# ── Helpers ──────────────────────────────────────────────────────────


def banner(text: str) -> None:
    width = max(len(text) + 4, 60)
    print(f"\n{BOLD}{CYAN}{'═' * width}")
    print(f"  {text}")
    print(f"{'═' * width}{RESET}\n")


def step(text: str) -> None:
    print(f"  {GREEN}▶{RESET} {text}")


def info(text: str) -> None:
    print(f"    {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {text}")


def error(text: str) -> None:
    print(f"  {RED}✗{RESET} {text}")


def pause(url: str, interactive: bool = True) -> None:
    """Print URL and optionally wait for operator to press Enter."""
    print(f"\n    {CYAN}→ Check:{RESET} {url}")
    if interactive:
        input(f"    {YELLOW}Press Enter to continue...{RESET}")
    print()


def api(
    method: str,
    path: str,
    base: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    expect: int = 200,
) -> Optional[Dict[str, Any]]:
    """Make an API call, assert status, return parsed JSON (or None for 204)."""
    url = f"{base}{path}"
    resp = requests.request(method, url, json=json_body, data=data, files=files)
    if resp.status_code != expect:
        error(f"{method} {path} → {resp.status_code} (expected {expect})")
        info(f"Response: {resp.text[:500]}")
        raise SystemExit(1)
    step(f"{method} {path} → {resp.status_code}")
    if resp.status_code == 204 or not resp.content:
        return None
    try:
        return resp.json()
    except Exception:
        # HTML responses from HTMX endpoints — that's fine
        return None


def make_test_png(colour: tuple[int, int, int] = (0, 180, 120)) -> bytes:
    """Generate a tiny 4×4 solid-colour PNG in memory (no file needed)."""
    width, height = 4, 4
    r, g, b = colour

    # Build raw pixel rows: filter byte (0) + RGB triples
    raw_data = b""
    for _ in range(height):
        raw_data += b"\x00" + bytes([r, g, b] * width)

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    buf = b"\x89PNG\r\n\x1a\n"  # PNG signature
    buf += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    buf += _chunk(b"IDAT", zlib.compress(raw_data))
    buf += _chunk(b"IEND", b"")
    return buf


# ── Walkthrough phases ───────────────────────────────────────────────

class Walkthrough:
    """Stateful walkthrough runner — tracks created entities for cleanup."""

    def __init__(self, base_url: str, db_path: str, interactive: bool = True):
        self.base = base_url
        self.db_path = db_path
        self.interactive = interactive

        # Entities created during the walkthrough (for cleanup)
        self.cross_id: Optional[str] = None
        self.dish_ids: List[str] = []
        self.fish_ids: List[str] = []

    # ── Phase 1: Dish setup ──────────────────────────────────────

    def phase_1_dish_setup(self) -> str:
        banner("Phase 1: Dish Setup")

        # Pick a real cross from the DB
        step("Fetching dishes to find a real cross_id...")
        resp = api("GET", "/dishes?limit=50", self.base)
        items = resp["items"] if resp else []
        crosses = {d["cross_id"] for d in items if d.get("cross_id")}

        if not crosses:
            error("No dishes with cross_id found in the database.")
            info("Make sure PyRAT sync has run and at least one dish has a cross_id.")
            raise SystemExit(1)

        self.cross_id = sorted(crosses)[0]
        info(f"Using cross: {BOLD}{self.cross_id}{RESET}")

        # Create test dish via direct SQL (no POST /dishes endpoint)
        dish_id = f"E2E_TEST_{self.cross_id}_1"
        step(f"Creating test dish: {dish_id}")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO dishes
               (dish_id, data, genotype, species, cross_id, status,
                dish_population_type, date_created, dof, responsible,
                fish_count, container_type, room)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dish_id,
                json.dumps({"dish_id": dish_id, "fish_count": 20}),
                "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)",
                "Danio rerio",
                self.cross_id,
                "active",
                "primary",
                "20260401",  # date_created
                "20260327",  # dof (April 1 screening = DPF 5)
                "walkthrough",  # responsible
                20,  # fish_count
                "petri_dish",  # container_type
                "2E.282",  # room
            ),
        )
        conn.commit()
        conn.close()
        self.dish_ids.append(dish_id)
        info(f"Dish created: {dish_id}")

        pause(f"{self.base}/screening/", self.interactive)
        return dish_id

    # ── Phase 2: Screening ───────────────────────────────────────

    def phase_2_screening(self, dish_id: str) -> None:
        banner("Phase 2: Screening")

        step("Logging a screening step on the test dish...")
        api(
            "POST",
            f"/screening/{dish_id}/steps",
            self.base,
            data={
                "screening_datetime": "20260401T10:00:00",
                "dpf_screened": 5,
                "indicators_screened": "gfap:TRPV1-T2A-GFP",
                "pigment_screened": False,
                "criteria": "Check pan-glial expression",
                "count_screened_this_step": 20,
                "number_kept": 12,
                "number_removed_negative": 8,
                "tricaine_used": True,
                "notes": "E2E walkthrough: DPF 5 gfap screen per protocol",
            },
        )

        pause(f"{self.base}/screening/{dish_id}", self.interactive)

    # ── Phase 3: Derived dishes ──────────────────────────────────

    def phase_3_derived_dishes(self, parent_dish_id: str) -> tuple[str, str]:
        banner("Phase 3: Derived Dishes (via API split)")

        step("Creating a positive_screened dish (12 kept fish → well plate)...")
        api(
            "POST",
            f"/screening/{parent_dish_id}/split",
            self.base,
            data={
                "fish_count": 12,
                "population_type": "positive_screened",
                "container_type": "well_plate",
                "notes": "E2E walkthrough: kept fish moved to well plate",
            },
        )

        step("Creating a negative_screened dish (8 removed fish → beaker)...")
        api(
            "POST",
            f"/screening/{parent_dish_id}/split",
            self.base,
            data={
                "fish_count": 8,
                "population_type": "negative_screened",
                "container_type": "beaker",
                "notes": "E2E walkthrough: removed fish for observation",
            },
        )

        # Discover the created dish IDs (controller generates them)
        resp = api("GET", f"/dishes?limit=50", self.base)
        items = resp["items"] if resp else []
        neg_id = None
        pos_id = None
        for d in items:
            if d.get("parent_dish_id") == parent_dish_id:
                pop = d.get("dish_population_type", "")
                if "negative" in pop:
                    neg_id = d["dish_id"]
                    self.dish_ids.append(neg_id)
                    info(f"Found negative dish: {neg_id}")
                elif "positive" in pop:
                    pos_id = d["dish_id"]
                    self.dish_ids.append(pos_id)
                    info(f"Found positive dish: {pos_id}")

        if not pos_id or not neg_id:
            warn("Could not find one or both derived dishes — check server logs")
            # Fall back to empty strings so later phases can still attempt
            pos_id = pos_id or ""
            neg_id = neg_id or ""

        pause(f"{self.base}/crosses/{self.cross_id}/fish/", self.interactive)
        return pos_id, neg_id

    # ── Phase 4: Dish-level images ───────────────────────────────

    def phase_4_dish_images(self, dish_id: str) -> None:
        banner("Phase 4: Dish-Level Images")

        step(f"Uploading a sample reference image to {dish_id}...")
        png_bytes = make_test_png(colour=(0, 200, 80))
        api(
            "POST",
            f"/dishes/{dish_id}/images",
            self.base,
            files={"file": ("walkthrough_ref.png", io.BytesIO(png_bytes), "image/png")},
            data={"caption": "E2E walkthrough positive reference"},
        )

        pause(f"{self.base}/dishes/{dish_id}/fish/", self.interactive)

    # ── Phase 5: Individual fish registration ────────────────────

    def phase_5_fish_registration(self, dish_id: str) -> List[str]:
        banner("Phase 5: Individual Fish Registration")

        fish_ids = []
        for i in range(1, 5):
            resp = api(
                "POST",
                f"/dishes/{dish_id}/fish",
                self.base,
                json_body={
                    "subject_label": f"wt-{i:02d}",
                    "sex": "unknown",
                    "genotype": "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)",
                    "species": "Danio rerio",
                    "notes": f"E2E walkthrough fish #{i}",
                },
                expect=201,
            )
            fid = resp["fish_id"]
            fish_ids.append(fid)
            self.fish_ids.append(fid)
            info(f"  → {fid[:8]}… label=wt-{i:02d}")

        pause(f"{self.base}/dishes/{dish_id}/fish/", self.interactive)
        return fish_ids

    # ── Phase 6: Housing units ───────────────────────────────────

    def phase_6_housing_units(self, dish_id: str, fish_ids: List[str]) -> None:
        banner("Phase 6: Housing Units")

        step("Creating a 4-well plate...")
        resp = api(
            "POST",
            f"/dishes/{dish_id}/units",
            self.base,
            json_body={
                "unit_kind": "well",
                "count": 4,
                "label_format": "well_plate",
            },
            expect=201,
        )
        unit_ids = resp["created"]
        info(f"  Created units: {unit_ids}")

        step("Assigning each fish to a well...")
        for fish_id, unit_id in zip(fish_ids, unit_ids):
            api(
                "POST",
                f"/fish/{fish_id}/assign",
                self.base,
                json_body={"unit_id": unit_id, "reason": "initial"},
            )
            info(f"  → {fish_id[:8]}… → {unit_id}")

        pause(f"{self.base}/dishes/{dish_id}/fish/", self.interactive)

    # ── Phase 7: Plate map visualization ─────────────────────────

    def phase_7_plate_map(self, dish_id: str, fish_ids: List[str]) -> None:
        banner("Phase 7: Plate Map Visualization")

        info("The fish list page now shows a visual housing map.")
        info("Occupied wells are green, empty wells are gray.")
        info("Check the plate map, then we'll add an unassigned fish.")
        pause(f"{self.base}/dishes/{dish_id}/plate-map", self.interactive)

        step("Registering one more fish WITHOUT assigning to a well...")
        resp = api(
            "POST",
            f"/dishes/{dish_id}/fish",
            self.base,
            json_body={
                "subject_label": "unplaced-05",
                "genotype": "Tg(gfap:TRPV1-T2A-GFP);Tg(elavl3:jRGECO1b)",
                "notes": "E2E walkthrough: unassigned fish for plate map demo",
            },
            expect=201,
        )
        fid = resp["fish_id"]
        self.fish_ids.append(fid)
        info(f"  → {fid[:8]}… label=unplaced-05 (no well assignment)")
        info("This fish should appear in the 'Unassigned fish' section below the grid.")

        pause(f"{self.base}/dishes/{dish_id}/fish/", self.interactive)

    # ── Phase 8: Cross-level view ────────────────────────────────

    def phase_8_cross_level_view(self) -> None:
        banner("Phase 8: Cross-Level View")

        info("Check the fish index, then drill into the cross to see the full hierarchy.")
        pause(f"{self.base}/fish/", self.interactive)

    # ── Cleanup ──────────────────────────────────────────────────

    def cleanup(self) -> None:
        banner("Cleanup")

        # Delete fish via API (has DELETE endpoint)
        for fish_id in self.fish_ids:
            try:
                resp = requests.delete(f"{self.base}/fish/{fish_id}")
                if resp.status_code in (204, 200):
                    step(f"Deleted fish {fish_id[:8]}…")
                else:
                    warn(f"Could not delete fish {fish_id[:8]}… (status {resp.status_code})")
            except Exception as e:
                warn(f"Error deleting fish {fish_id[:8]}…: {e}")

        # Direct SQL cleanup for entities without DELETE endpoints
        conn = sqlite3.connect(self.db_path)

        # Delete housing units + occupancy for test dishes
        for dish_id in self.dish_ids:
            step(f"Cleaning up housing data for {dish_id} (SQL)")
            conn.execute(
                "DELETE FROM housing_unit_occupancy WHERE unit_id IN "
                "(SELECT unit_id FROM housing_units WHERE dish_id = ?)",
                (dish_id,),
            )
            conn.execute("DELETE FROM housing_unit_checks WHERE unit_id IN "
                "(SELECT unit_id FROM housing_units WHERE dish_id = ?)",
                (dish_id,),
            )
            conn.execute("DELETE FROM housing_units WHERE dish_id = ?", (dish_id,))

        # Delete dish images
        for dish_id in self.dish_ids:
            step(f"Deleting dish images for {dish_id} (SQL)")
            conn.execute("DELETE FROM dish_images WHERE dish_id = ?", (dish_id,))

        # Delete screening data
        for dish_id in self.dish_ids:
            conn.execute("DELETE FROM screening_step_images WHERE dish_id = ?", (dish_id,))
            conn.execute("DELETE FROM screening_steps WHERE dish_id = ?", (dish_id,))

        # Delete test dishes
        for dish_id in self.dish_ids:
            step(f"Deleting test dish: {dish_id} (SQL)")
            conn.execute("DELETE FROM dishes WHERE dish_id = ?", (dish_id,))

        conn.commit()
        conn.close()

        # Remove uploaded test images from disk
        db_dir = Path(self.db_path).parent
        for subdir in ("dish_images", "fish_images"):
            img_dir = db_dir / subdir
            if img_dir.exists():
                for dish_id in self.dish_ids:
                    dish_img_dir = img_dir / dish_id
                    if dish_img_dir.exists():
                        for f in dish_img_dir.iterdir():
                            f.unlink()
                            step(f"Removed image file: {f.name}")
                        dish_img_dir.rmdir()

        step("Cleanup complete!")
        info(f"Verify at: {self.base}/fish/")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Guided walkthrough of the fish tracking workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the SQLite database file (same one the API server uses)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="API server port (default: 8002)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without pauses (for automated smoke tests)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path).resolve()
    if not db_path.exists():
        error(f"Database not found: {db_path}")
        raise SystemExit(1)

    base_url = f"http://localhost:{args.port}"

    # Verify server is reachable
    banner("MetaZebrobot Operator Walkthrough")
    step(f"Checking server at {base_url}...")
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        resp.raise_for_status()
        info(f"Server healthy: {resp.json()}")
    except Exception as e:
        error(f"Cannot reach server at {base_url}: {e}")
        info("Start the server first:")
        info(f"  pixi run python -m metazebrobot.api_server --db-path {db_path}")
        raise SystemExit(1)

    interactive = not args.non_interactive
    wt = Walkthrough(base_url, str(db_path), interactive=interactive)

    try:
        # Phase 1: Dish setup
        dish_id = wt.phase_1_dish_setup()

        # Phase 2: Screening
        wt.phase_2_screening(dish_id)

        # Phase 3: Derived dishes
        pos_dish, neg_dish = wt.phase_3_derived_dishes(dish_id)

        # Phase 4: Dish-level images
        wt.phase_4_dish_images(pos_dish)

        # Phase 5: Individual fish registration
        fish_ids = wt.phase_5_fish_registration(pos_dish)

        # Phase 6: Housing units
        wt.phase_6_housing_units(pos_dish, fish_ids)

        # Phase 7: Plate map visualization
        wt.phase_7_plate_map(pos_dish, fish_ids)

        # Phase 8: Cross-level view
        wt.phase_8_cross_level_view()

        # Done!
        banner("Walkthrough Complete!")
        info("All phases passed. Starting cleanup...")

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Interrupted — running cleanup...{RESET}")
    finally:
        wt.cleanup()


if __name__ == "__main__":
    main()
