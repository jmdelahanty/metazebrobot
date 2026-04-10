from types import SimpleNamespace

from metazebrobot.api_server import _screening_indicator_suggestions


class TestScreeningIndicatorSuggestions:
    def test_single_catalog_backed_construct_prefills_field(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            }
        ]

        suggestions, default_value = _screening_indicator_suggestions(transgenes)

        assert default_value == "GRAB-5HT"
        assert suggestions == [
            {
                "value": "GRAB-5HT",
                "meta": "sensor · GRAB · serotonin · green",
            }
        ]

    def test_current_protocol_step_overrides_default_value(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            }
        ]
        current_step = SimpleNamespace(indicators=["GFP", "GRAB-5HT"])

        suggestions, default_value = _screening_indicator_suggestions(transgenes, current_step)

        assert default_value == "GFP, GRAB-5HT"
        assert [entry["value"] for entry in suggestions] == ["GFP", "GRAB-5HT"]

    def test_multiple_constructs_do_not_autofill(self):
        transgenes = [
            {
                "catalog_name": "GRAB-5HT",
                "reporter": "grab-5ht",
                "construct_role": "sensor",
                "family": "GRAB",
                "target": "serotonin",
                "screen_color": "green",
            },
            {
                "catalog_name": "jRGECO1b",
                "reporter": "jrgeco1b",
                "construct_role": "sensor",
                "family": "jRGECO",
                "target": "calcium",
                "screen_color": "red",
            },
        ]

        suggestions, default_value = _screening_indicator_suggestions(transgenes)

        assert default_value == ""
        assert [entry["value"] for entry in suggestions] == ["GRAB-5HT", "jRGECO1b"]
