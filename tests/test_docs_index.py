"""docs/README.md is generated from doc frontmatter and must not drift.

The generator is agent-contracts docs-contract/docs_index.py at the commit
pinned in scripts/docs_index.py.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docs_index.py"
spec = importlib.util.spec_from_file_location("docs_index", SCRIPT)
docs_index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs_index)


@pytest.fixture(scope="module")
def generator_available():
    try:
        docs_index.pinned_generator()
    except LookupError as exc:
        pytest.skip(str(exc))


def test_every_doc_is_adopted_and_index_is_current(generator_available):
    # --strict: docs without frontmatter are errors; exit 1 = stale, 2 = invalid.
    result = docs_index.run("--check", "--strict")
    assert result.returncode == 0, (
        f"{result.stdout}{result.stderr}\nRun `pixi run python scripts/docs_index.py`")
