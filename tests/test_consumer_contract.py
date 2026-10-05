"""The pinned consumer OpenAPI slice must match the code.

If the comparison test fails after an intentional, additive change, regenerate:

    pixi run python scripts/export_consumer_openapi.py

The explicit field tests below are the promises Citrus, Orange, and Palette
rely on; they must keep passing even after a regeneration. Removing or
renaming one of these fields requires a new response schema_version.
"""

import pytest

from metazebrobot.api_server import DishDetailResponse, create_app
from metazebrobot.consumer_contract import (
    CONSUMER_ENDPOINTS,
    CONSUMER_OPENAPI_PATH,
    consumer_openapi,
    render,
)


@pytest.fixture(scope="module")
def schema():
    return consumer_openapi(create_app())


def _properties(schema, name):
    return schema["components"]["schemas"][name]["properties"]


def test_committed_slice_matches_code(schema):
    committed = CONSUMER_OPENAPI_PATH.read_text()
    assert committed == render(schema), (
        f"{CONSUMER_OPENAPI_PATH} is out of date with the API code. If the "
        "change is intentional and additive, run "
        "`pixi run python scripts/export_consumer_openapi.py` and commit it."
    )


def test_snapshot_identity_fields(schema):
    props = _properties(schema, "CitrusSnapshotResponse")
    assert props["schema_version"]["default"] == 2
    for field in ("dish_id", "dish_uuid", "revision", "updated_at"):
        assert field in props


def test_acquisition_identity_fields(schema):
    assert _properties(schema, "AcquisitionDishesResponse")["schema_version"]["default"] == 2
    item = _properties(schema, "AcquisitionDishItem")
    for field in ("dish_id", "dish_uuid", "revision", "updated_at", "links"):
        assert field in item
    assert set(_properties(schema, "AcquisitionLinks")) >= {
        "dish", "fish", "units", "cross_provenance",
    }


def test_fish_identity_fields(schema):
    props = _properties(schema, "FishSubjectResponse")
    for field in ("fish_id", "dish_id", "dish_uuid", "subject_label",
                  "current_unit_id", "revision", "updated_at"):
        assert field in props
    list_ref = schema["paths"]["/dishes/{dish_id}/fish"]["get"]["responses"]["200"]
    assert list_ref["content"]["application/json"]["schema"]["$ref"].endswith(
        "/FishListResponse"
    )


def test_dish_detail_identity_fields(schema):
    props = _properties(schema, "DishDetailResponse")
    for field in ("dish_id", "dish_uuid", "revision", "updated_at"):
        assert field in props


def test_dish_detail_passes_other_columns_through():
    dumped = DishDetailResponse(
        dish_id="1_1", dish_uuid="u", revision=1, genotype="Tg(x)", data={"a": 1}
    ).model_dump()
    assert dumped["genotype"] == "Tg(x)"
    assert dumped["data"] == {"a": 1}


LOOKUP_ENDPOINTS = [e for e in CONSUMER_ENDPOINTS if e[1] != "/version"]


def test_version_fields(schema):
    props = _properties(schema, "VersionResponse")
    for field in ("service_commit", "service_commit_dirty",
                  "consumer_schema_sha256", "api_schema_version", "started_at_utc"):
        assert field in props
    assert props["api_schema_version"]["default"] == 2


@pytest.mark.parametrize("method,path", LOOKUP_ENDPOINTS)
def test_lookup_errors_are_declared(schema, method, path):
    responses = schema["paths"][path][method]["responses"]
    assert responses["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ApiErrorResponse"
    )
    if path != "/acquisition/dishes":
        assert "404" in responses


def test_error_detail_shape(schema):
    detail = schema["components"]["schemas"]["ApiErrorDetail"]
    assert detail["required"] == ["error"]
    assert detail.get("additionalProperties") is True
