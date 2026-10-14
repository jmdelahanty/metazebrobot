"""Screening indicator matching (docs/construct_screening_link_design.md)."""

import uuid

from metazebrobot.data.data_manager import data_manager
from metazebrobot.utils.indicator_match import match_step

GFAP_TRPV1 = {"construct": "Tg(gfap:TRPV1-T2A-GFP)", "promoter": "gfap",
              "reporter": "trpv1-t2a-gfp", "construct_key": "trpv1t2agfp",
              "fluorophore": "gfp", "fluorophore_color": "green"}
ELAVL3_RGECO = {"construct": "Tg(elavl3:jRGECO1b)", "promoter": "elavl3",
                "reporter": "jrgeco1b", "construct_key": "jrgeco1b",
                "fluorophore": "jrgeco", "fluorophore_color": "red"}
PMCA2_ZF = {"construct": "Tg(gfap:PMCA2-mCherry-zf)", "promoter": "gfap",
            "reporter": "pmca2-mcherry-zf", "construct_key": "pmca2mcherryzf",
            "fluorophore": "mcherry", "fluorophore_color": "red"}


def no_alias(_):
    return None


def summary(rows):
    return [(r["kind"], r["dish_construct"], r["match_rule"], r["match_confidence"]) for r in rows]


def test_pigment_and_promoter_reporter_split_from_one_string():
    rows = match_step(["Pigment, elavl3:jRGECO1b"], False, [GFAP_TRPV1, ELAVL3_RGECO], no_alias)
    assert summary(rows) == [
        ("pigment", None, "pigment_text", "high"),
        ("construct", "Tg(elavl3:jRGECO1b)", "promoter_reporter", "high"),
    ]


def test_pigment_checkbox_alone_counts():
    rows = match_step(["jRGECO1b"], True, [ELAVL3_RGECO], no_alias)
    assert ("pigment", None, "pigment_flag", "high") in summary(rows)


def test_legacy_both_is_low_confidence_positive_for_every_construct():
    rows = match_step(["Both/Final Brightness"], False, [GFAP_TRPV1, ELAVL3_RGECO], no_alias)
    assert {r["dish_construct"] for r in rows} == {GFAP_TRPV1["construct"], ELAVL3_RGECO["construct"]}
    assert {r["match_confidence"] for r in rows} == {"low"}
    assert all("uncertain" in r["note"] for r in rows)


def test_color_word_matches_unique_readout_as_medium():
    rows = match_step(["mCherry"], False, [PMCA2_ZF], no_alias)
    assert summary(rows) == [("construct", PMCA2_ZF["construct"], "fluorophore_only", "medium")]


def test_color_word_shared_by_two_constructs_is_not_guessed():
    rows = match_step(["red"], False, [PMCA2_ZF, ELAVL3_RGECO], no_alias)
    assert summary(rows) == [("other", None, "ambiguous", "none")]


def test_catalog_alias_matches_by_key():
    jgcamp8p = {"construct": "Tg(elavl3:GCaMP7ff)", "promoter": "elavl3",
                "reporter": "gcamp7ff", "construct_key": "jgcamp8p"}
    rows = match_step(["jGCaMP8p"], False, [jgcamp8p],
                      lambda text: "jgcamp8p" if "8p" in text.lower() else None)
    assert summary(rows) == [("construct", "Tg(elavl3:GCaMP7ff)", "catalog_alias", "high")]


def test_unknown_text_is_kept_as_unmatched():
    rows = match_step(["sparkly"], False, [ELAVL3_RGECO], no_alias)
    assert summary(rows) == [("other", None, "unmatched", "none")]
    assert rows[0]["raw_text"] == "sparkly"


def test_saving_a_dish_derives_indicator_rows(client):
    dish_id = f"DISH_{uuid.uuid4().hex[:8]}"
    assert data_manager.save_fish_dish({
        "dish_id": dish_id, "cross_id": "18178", "date_created": "20260512",
        "dof": "20260512", "genotype": "Tg(elavl3:GRABATP1.0)",
        "responsible": "test-user", "fish_count": 10, "species": "Danio rerio",
        "sex": "unknown", "status": "active",
        "screening_results": {"screenings": [{
            "screening_datetime": "20260518T20:14:00", "dpf_screened": 6,
            "indicators_screened": ["GRABATP1.0"], "pigment_screened": True,
            "count_screened_this_step": 10, "allocations": [],
        }]},
    })
    with data_manager.get_connection() as conn:
        rows = conn.execute(
            "SELECT kind, dish_construct, construct_key, match_rule FROM screening_step_indicators "
            "WHERE dish_id = ? ORDER BY kind", (dish_id,)
        ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("construct", "Tg(elavl3:GRABATP1.0)", "grabatp10", "reporter"),
        ("pigment", None, None, "pigment_flag"),
    ]
