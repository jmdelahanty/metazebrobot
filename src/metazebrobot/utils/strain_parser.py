"""
Parser for extracting transgenic indicator components from strain name strings.

Parses notation like:
  - Tg(gfap:TRPV1-T2A-GFP)
  - Et(1121A:GAL4FF)
  - (UAS:jRGECO1b)
  - Tg(elavl3:jRGECO1b); Tg(gfap:CoChR-eGFP)

Returns structured indicator dicts that can seed TransgenicIndicator records.
Color and expected_expression cannot be derived and are left as None for
the user to fill in during review.
"""

import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Pattern matches: optional prefix like Tg/Et/TgBAC, then (content)
# Captures: prefix group (Tg, Et, TgBAC, etc.) and parenthesized content
_CONSTRUCT_PATTERN = re.compile(
    r'(?:(\w+)\s*)?'   # Optional prefix (Tg, Et, TgBAC, etc.)
    r'\('               # Opening paren
    r'([^)]+)'          # Content inside parens
    r'\)'               # Closing paren
)

# Known modification type prefixes
_PREFIX_TO_TYPE = {
    "tg": "tg",
    "tgbac": "tg",
    "et": "other",  # Enhancer trap
}


def parse_strain_name(strain_name: str) -> List[Dict[str, Optional[str]]]:
    """
    Parse a strain name string into a list of indicator component dicts.

    Each dict contains:
      - modification_type: "tg", "other", or None
      - promoter_driver: str or None
      - reporter_effector: str
      - color: None (requires user input)
      - expected_expression: None (requires user input)

    Args:
        strain_name: The strain name string from PyRAT.

    Returns:
        List of indicator dicts. Empty list if no constructs found
        (e.g., for non-transgenic strains like "Casper_HHMI").
    """
    if not strain_name:
        return []

    indicators = []

    for match in _CONSTRUCT_PATTERN.finditer(strain_name):
        prefix = match.group(1)  # e.g., "Tg", "Et", "TgBAC", or None
        content = match.group(2)  # e.g., "gfap:TRPV1-T2A-GFP"

        # Determine modification type from prefix
        mod_type = None
        if prefix:
            mod_type = _PREFIX_TO_TYPE.get(prefix.lower(), "other")

        # Split content on first colon to get promoter:reporter
        if ":" in content:
            promoter, reporter = content.split(":", 1)
            promoter = promoter.strip()
            reporter = reporter.strip()
        else:
            # No colon — entire content is the reporter/effector
            promoter = None
            reporter = content.strip()

        indicators.append({
            "modification_type": mod_type,
            "promoter_driver": promoter,
            "reporter_effector": reporter,
            "color": None,
            "expected_expression": None,
        })

    return indicators
