"""
Parser for extracting transgenic construct components from strain name strings.

The crossing UI still edits human-readable fields like ``promoter_driver`` and
``reporter_effector``, but this module now seeds those rows from the same
normalized parser used by ``dish_transgenes`` so both pathways share one
classification model.
"""

from typing import List, Dict, Optional

from ..data.data_manager import DataManager


def parse_strain_name(strain_name: str) -> List[Dict[str, Optional[str]]]:
    """
    Parse a strain name string into indicator dicts for crossing review/edit.

    Returns rows compatible with ``crossing_transgenic_indicators`` while also
    carrying normalized metadata derived from the shared construct classifier.
    """
    indicators = []
    for tg in DataManager.parse_genotype(strain_name or ""):
        indicators.append({
            "modification_type": tg.get("modification_type"),
            "promoter_driver": tg.get("promoter_raw") or tg.get("promoter"),
            "promoter_norm": tg.get("promoter"),
            "reporter_effector": tg.get("reporter_raw") or tg.get("reporter"),
            "reporter_norm": tg.get("reporter"),
            "fluorophore": tg.get("fluorophore"),
            "construct_role": tg.get("construct_role"),
            "sensor_family": tg.get("sensor_family"),
            "sensor_target": tg.get("sensor_target"),
            "effector_family": tg.get("effector_family"),
            "color": None,
            "expected_expression": None,
        })
    return indicators
