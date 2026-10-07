#!/usr/bin/env python
"""Generate or check docs/README.md with the shared docs-contract generator.

The frontmatter schema and the generator live in agent-contracts
(docs-contract/README.md, docs-contract/docs_index.py); this repo doesn't keep
its own copy. This wrapper runs the generator at a pinned agent-contracts
commit, read from a local checkout with ``git show`` so the checkout's own
state doesn't matter. Re-pin by changing DOCS_CONTRACT_COMMIT.

The checkout is found via $AGENT_CONTRACTS_DIR, else a sibling directory named
agent-contracts or contracts.

    pixi run python scripts/docs_index.py          # rewrite docs/README.md
    pixi run python scripts/docs_index.py --check  # exit 1 if stale, 2 if invalid

Other arguments (e.g. --list-unadopted) pass through to the generator.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
REPO_NAME = "MetaZebrobot"
DOCS_CONTRACT_COMMIT = "46a2c5e2b0df3283d74b2ca72514bbc48c7e61f9"
GENERATOR_PATH = "docs-contract/docs_index.py"


def find_agent_contracts() -> Optional[Path]:
    candidates = [os.environ.get("AGENT_CONTRACTS_DIR")]
    candidates += [str(REPO_ROOT.parent / name) for name in ("agent-contracts", "contracts")]
    for candidate in candidates:
        if candidate and (Path(candidate) / ".git").exists():
            return Path(candidate)
    return None


def pinned_generator() -> str:
    """Source of the shared generator at the pinned commit; raises LookupError."""
    checkout = find_agent_contracts()
    if checkout is None:
        raise LookupError("no agent-contracts checkout: set AGENT_CONTRACTS_DIR or clone it next to this repo")
    result = subprocess.run(
        ["git", "-C", str(checkout), "show", f"{DOCS_CONTRACT_COMMIT}:{GENERATOR_PATH}"],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise LookupError(f"{checkout} lacks agent-contracts {DOCS_CONTRACT_COMMIT[:7]}; "
                          f"run `git -C {checkout} fetch origin`")
    return result.stdout


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-", "--docs-dir", str(DOCS), "--repo", REPO_NAME, *args],
        input=pinned_generator(), capture_output=True, text=True)


def main() -> int:
    try:
        result = run(*sys.argv[1:])
    except LookupError as exc:
        print(f"docs_index: {exc}", file=sys.stderr)
        return 3
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
