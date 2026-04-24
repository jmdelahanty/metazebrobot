# Agent Notes

## FastAPI TestClient in the Codex sandbox

FastAPI/Starlette `TestClient` can hang inside the Codex filesystem/network
sandbox in this repository. The hang is environment-level, not specific to the
MetaZebrobot app: a minimal `FastAPI()` app also blocks when entering or using
`TestClient` from inside the sandbox.

When verifying tests that use `fastapi.testclient.TestClient`, run the focused
pytest command outside the sandbox with an explicit timeout. Example:

```bash
timeout 120s .pixi/envs/default/bin/python -m pytest tests/test_fish_api.py::TestDishInventory -q
```

Use this only for TestClient-backed tests. Non-TestClient checks such as
`py_compile`, `git diff --check`, and helper-only unit tests can run normally
inside the sandbox.

Avoid leaving hung pytest processes around. If a TestClient run is accidentally
started inside the sandbox and becomes silent, check for and stop only the
focused hung pytest command before rerunning verification.

## Runtime artifacts

Do not commit local runtime artifacts such as `.codex`, `zebrobot.db-shm`, or
`zebrobot.db-wal`.
