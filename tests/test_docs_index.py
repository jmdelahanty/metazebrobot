"""docs/README.md is generated from doc frontmatter and must not drift."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docs_index.py"
spec = importlib.util.spec_from_file_location("docs_index", SCRIPT)
docs_index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs_index)


def test_every_doc_has_valid_frontmatter():
    docs = docs_index.load_docs()  # raises on any invalid or missing frontmatter
    assert docs
    assert {d["status"] for d in docs} <= set(docs_index.STATUSES)


def test_index_is_current():
    expected = docs_index.render(docs_index.load_docs())
    assert docs_index.INDEX.read_text() == expected, (
        "docs/README.md is stale: run `pixi run python scripts/docs_index.py`")


def test_parse_frontmatter_values():
    meta = docs_index.parse_frontmatter(
        '---\ntitle: "A: B"\nverified_against: null\nkind: plan  # comment\n---\n\n# A\n')
    assert meta == {"title": "A: B", "verified_against": None, "kind": "plan"}


def test_missing_frontmatter_is_an_error():
    with pytest.raises(ValueError):
        docs_index.parse_frontmatter("# No frontmatter\n")
