"""Match a screening step's free-text indicators to the dish's constructs.

Rules and decisions: docs/construct_screening_link_design.md ("Screening steps
point at constructs", "Decisions"). Pure functions; the caller supplies the
dish's constructs and a catalog alias resolver.
"""

import re
from typing import Any, Callable, Dict, List, Optional

FLUOROPHORE_WORDS = {
    "mcherry", "tdtomato", "dsred", "rfp", "red",
    "gfp", "egfp", "cpgfp", "cpegfp", "green",
    "eyfp", "yfp", "venus", "cfp", "cerulean", "bfp",
}
LEGACY_BOTH_NOTE = (
    "Early screen labelled 'Both/Final Brightness'; read as positive for both "
    "constructs if bright (Jeremy, 2026-10-14, uncertain)."
)


def normalize(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def tokens(indicators: Any) -> List[str]:
    """Split a step's indicators (JSON list or string) into stripped tokens."""
    if isinstance(indicators, str):
        indicators = [indicators]
    out = []
    for item in indicators or []:
        for part in str(item).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _readout_words(construct: Dict[str, Any]) -> set:
    entry = construct.get("catalog_entry") or {}
    words = {normalize(construct.get("fluorophore")), normalize(construct.get("fluorophore_color")),
             normalize(entry.get("readout_fluorophore")), normalize(entry.get("screen_color"))}
    return {w for w in words if w}


def match_step(
    indicators: Any,
    pigment_flag: bool,
    constructs: List[Dict[str, Any]],
    resolve_key: Callable[[str], Optional[str]],
) -> List[Dict[str, Any]]:
    """One row per indicator: kind, dish construct, rule, confidence, note.

    ``constructs`` are the dish's construct rows (construct, promoter,
    reporter, construct_key, fluorophore, fluorophore_color, catalog_entry).
    A step counts as pigment-screened if either its text or its checkbox
    says so (decision 2026-10-14).
    """
    rows: List[Dict[str, Any]] = []
    seen = set()

    def add(raw, kind, construct, rule, confidence, note=None):
        ident = (kind, construct.get("construct") if construct else raw)
        if ident in seen:
            return
        seen.add(ident)
        rows.append({
            "raw_text": raw,
            "kind": kind,
            "dish_construct": construct.get("construct") if construct else None,
            "construct_key": construct.get("construct_key") if construct else None,
            "match_rule": rule,
            "match_confidence": confidence,
            "note": note,
        })

    for raw in tokens(indicators):
        norm = normalize(raw)
        lower = raw.lower()
        if norm == "pigment":
            add(raw, "pigment", None, "pigment_text", "high")
            continue
        if "brightness" in lower or lower.startswith("both"):
            if constructs:
                for c in constructs:
                    add(raw, "construct", c, "legacy_both_brightness", "low", LEGACY_BOTH_NOTE)
            else:
                add(raw, "other", None, "unmatched", "none", "No dish constructs to apply 'Both' to.")
            continue
        candidates: List[Dict[str, Any]] = []
        rule = None
        if ":" in raw:
            promoter, reporter = (normalize(p) for p in raw.split(":", 1))
            key = resolve_key(raw.split(":", 1)[1])
            candidates = [
                c for c in constructs
                if normalize(c.get("promoter")) == promoter
                and (normalize(c.get("reporter")) == reporter
                     or (key and c.get("construct_key") == key))
            ]
            rule = "promoter_reporter"
        if not candidates:
            candidates = [c for c in constructs if normalize(c.get("reporter")) == norm]
            rule = "reporter"
        if not candidates:
            key = resolve_key(raw)
            candidates = [c for c in constructs if key and c.get("construct_key") == key]
            rule = "catalog_alias"
        if len(candidates) == 1:
            add(raw, "construct", candidates[0], rule, "high")
            continue
        if len(candidates) > 1:
            add(raw, "other", None, "ambiguous", "none",
                f"Matches {len(candidates)} dish constructs; not guessed.")
            continue
        if norm in FLUOROPHORE_WORDS:
            by_readout = [c for c in constructs if norm in _readout_words(c)]
            if len(by_readout) == 1:
                add(raw, "construct", by_readout[0], "fluorophore_only", "medium")
            elif by_readout:
                add(raw, "other", None, "ambiguous", "none",
                    f"{len(by_readout)} dish constructs share this readout; not guessed.")
            else:
                add(raw, "other", None, "unmatched", "none", "No dish construct has this readout.")
            continue
        add(raw, "other", None, "unmatched", "none", None)

    if pigment_flag and not any(r["kind"] == "pigment" for r in rows):
        add("(pigment checkbox)", "pigment", None, "pigment_flag", "high")
    return rows
