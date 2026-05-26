#!/usr/bin/env python
"""Inspect PyRAT's internal colony-pedigree report payload.

This exploratory script logs into the PyRAT frontend, calls the same
``backend/v1/reports/colony_pedigree`` endpoint used by the web client, and
prints a compact summary of the returned graph-like data. It is read-only and
does not write anything to the MetaZebrobot database.

The backend/v1 report endpoints are PyRAT frontend internals. They are useful
for inspection, but their query parameters and response shape may change
without the compatibility guarantees of the public api/v3 endpoints.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from metazebrobot.utils.pyrat_credentials import get_pyrat_frontend_credentials, normalize_base_url  # noqa: E402
from metazebrobot.utils.pyrat_frontend_client import login_pyrat_frontend  # noqa: E402


REPORT_ENDPOINT = "backend/v1/reports/colony_pedigree"
DEFAULT_KIND = "strain_pedigree"
DEFAULT_LABEL = "84"


def compact_scalar(value: Any, max_length: int = 120) -> Any:
    if isinstance(value, str) and len(value) > max_length:
        return value[: max_length - 3] + "..."
    return value


def json_preview(value: Any, max_chars: int = 1000) -> str:
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def frontend_report_url(base_url: str, session_id: str) -> str:
    return urljoin(
        normalize_base_url(base_url),
        f"frontend/reports/colony_pedigree?sessionid={session_id}",
    )


def extract_balanced_json(text: str, start_index: int) -> Any:
    """Parse the first balanced JSON array/object beginning at start_index."""
    opener = text[start_index]
    closer = {"[": "]", "{": "}"}[opener]
    stack = [closer]
    in_string = False
    escape = False

    for index in range(start_index + 1, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "[{":
            stack.append({pat: close for pat, close in (("[", "]"), ("{", "}"))}[char])
            continue
        if char in "]}":
            if not stack or char != stack[-1]:
                raise ValueError("Unbalanced JSON-like payload in frontend HTML")
            stack.pop()
            if not stack:
                return json.loads(text[start_index : index + 1])

    raise ValueError("Could not find the end of the frontend init payload")


def fetch_frontend_init_config(
    session: requests.Session,
    base_url: str,
    session_id: str,
    verify_ssl: bool,
) -> Dict[str, Any]:
    response = session.get(
        frontend_report_url(base_url, session_id),
        verify=verify_ssl,
        timeout=30,
    )
    response.raise_for_status()
    marker = "initColonyPedigree.apply(undefined,"
    marker_index = response.text.find(marker)
    if marker_index < 0:
        raise RuntimeError("Could not find initColonyPedigree payload in frontend HTML")
    array_start = response.text.find("[", marker_index)
    if array_start < 0:
        raise RuntimeError("Could not find initColonyPedigree argument array")
    payload = extract_balanced_json(response.text, array_start)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError("Unexpected initColonyPedigree payload shape")
    return payload[0]


def candidate_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values() if item is not None)
    return str(value)


def print_autocomplete_matches(config: Dict[str, Any], query: str, limit: int) -> None:
    normalized_query = query.lower()
    autocomplete_keys = [
        key for key, value in config.items()
        if key.endswith("_autocomplete") and isinstance(value, list)
    ]
    if not autocomplete_keys:
        print("No autocomplete lists were found in the frontend init payload.")
        return

    print("Autocomplete matches:")
    for key in sorted(autocomplete_keys):
        values = config.get(key) or []
        matches = [
            item for item in values
            if not normalized_query or normalized_query in candidate_text(item).lower()
        ]
        print(f"- {key}: {len(matches)} match(es) out of {len(values)}")
        for item in matches[:limit]:
            print(f"  {json_preview(item, max_chars=500)}")


def response_as_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        text = response.text.strip()
        if len(text) > 1000:
            text = text[:997] + "..."
        raise RuntimeError(
            f"Expected JSON but received {response.status_code} {response.headers.get('content-type')}: {text}"
        ) from exc


def collection_summary(name: str, value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, list):
        return None
    sample = next((item for item in value if isinstance(item, dict)), None)
    summary: Dict[str, Any] = {"name": name, "count": len(value)}
    if sample is not None:
        summary["sample_keys"] = sorted(sample.keys())
        summary["sample"] = {
            key: compact_scalar(sample.get(key))
            for key in sorted(sample.keys())[:12]
            if not isinstance(sample.get(key), (dict, list))
        }
    elif value:
        summary["sample"] = compact_scalar(value[0])
    return summary


def walk_collections(value: Any, path: str = "$") -> List[Dict[str, Any]]:
    collections: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            summary = collection_summary(child_path, child)
            if summary is not None:
                collections.append(summary)
            collections.extend(walk_collections(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value[:5]):
            collections.extend(walk_collections(child, f"{path}[{index}]"))
    return collections


def likely_graph_counts(payload: Any) -> Dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    counts: Dict[str, int] = {}
    for key in ("nodes", "edges", "links", "vertices"):
        value = payload.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
    for wrapper_key in ("data", "graph", "result", "payload"):
        nested = payload.get(wrapper_key)
        if isinstance(nested, dict):
            for key, value in likely_graph_counts(nested).items():
                counts[f"{wrapper_key}.{key}"] = value
    return counts


def print_payload_summary(payload: Any) -> None:
    print("Response summary:")
    print(f"- payload_type: {type(payload).__name__}")
    if isinstance(payload, dict):
        print(f"- top_level_keys: {sorted(payload.keys())}")
        graph_counts = likely_graph_counts(payload)
        if graph_counts:
            print(f"- graph_counts: {graph_counts}")
    collections = walk_collections(payload)
    if collections:
        print()
        print("Collections:")
        for summary in collections[:12]:
            print(f"- {summary['name']}: {summary['count']}")
            if summary.get("sample_keys"):
                print(f"  sample_keys: {summary['sample_keys']}")
            if summary.get("sample"):
                print(f"  sample: {json_preview(summary['sample'], max_chars=400)}")
    else:
        print()
        print("Payload preview:")
        print(json_preview(payload))


def base_params(kind: str, label: str, generations: int) -> Dict[str, str]:
    return {
        "kind": kind,
        "label": label,
        "generations": str(generations),
    }


def parameter_variants(kind: str, label: str, generations: int) -> Iterable[Tuple[str, Dict[str, str]]]:
    """Yield conservative query variants for PyRAT frontend-internal probing."""
    yield "kind-label-generations", base_params(kind, label, generations)
    yield "kind-subject-generations", {
        "kind": kind,
        "subject": label,
        "generations": str(generations),
    }
    yield "pedigree_type-label-generations", {
        "pedigree_type": kind,
        "label": label,
        "generations": str(generations),
    }
    yield "type-label-generations", {
        "type": kind,
        "label": label,
        "generations": str(generations),
    }


def fetch_report(
    session: requests.Session,
    base_url: str,
    session_id: str,
    params: Dict[str, str],
    verify_ssl: bool,
) -> requests.Response:
    report_url = urljoin(normalize_base_url(base_url), REPORT_ENDPOINT)
    return session.get(
        report_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {session_id}",
            "Referer": frontend_report_url(base_url, session_id),
        },
        params=params,
        verify=verify_ssl,
        timeout=30,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", default=DEFAULT_KIND)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--raw", action="store_true", help="Print the full JSON payload.")
    parser.add_argument("--output", type=Path, help="Write the full JSON payload to a file.")
    parser.add_argument(
        "--list-label-matches",
        metavar="QUERY",
        help=(
            "Fetch the frontend report page and print autocomplete entries matching QUERY. "
            "Use this to find PyRAT's exact authorized label value."
        ),
    )
    parser.add_argument("--match-limit", type=int, default=10)
    parser.add_argument(
        "--probe-variants",
        action="store_true",
        help="Try a few plausible query parameter spellings until one returns JSON successfully.",
    )
    parser.add_argument("--verify-ssl", action="store_true")
    args = parser.parse_args()

    credentials = get_pyrat_frontend_credentials()
    if not credentials:
        raise SystemExit(
            "PyRAT frontend credentials are not configured. Run "
            "pixi run python pyrat_credentials_tool.py --setup-credentials first."
        )

    debug_info: Dict[str, Any] = {}
    session, session_id = login_pyrat_frontend(
        credentials["base_url"],
        credentials["username"],
        credentials["password"],
        verify_ssl=args.verify_ssl,
        debug_info=debug_info,
    )

    if args.list_label_matches is not None:
        config = fetch_frontend_init_config(
            session,
            credentials["base_url"],
            session_id,
            verify_ssl=args.verify_ssl,
        )
        print(f"Frontend init keys: {sorted(config.keys())}")
        print_autocomplete_matches(
            config,
            args.list_label_matches,
            limit=max(args.match_limit, 1),
        )
        return 0

    variants = (
        list(parameter_variants(args.kind, args.label, args.generations))
        if args.probe_variants
        else [("kind-label-generations", base_params(args.kind, args.label, args.generations))]
    )

    last_error: Optional[str] = None
    for variant_name, params in variants:
        response = fetch_report(
            session,
            credentials["base_url"],
            session_id,
            params,
            verify_ssl=args.verify_ssl,
        )
        print(f"Request variant: {variant_name}")
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")

        if response.status_code >= 400:
            text = response.text.strip()
            if len(text) > 1000:
                text = text[:997] + "..."
            last_error = text
            print(f"Error body: {text}")
            print()
            continue

        payload = response_as_json(response)
        if args.output:
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
            print(f"Wrote raw payload to {args.output}")
        if args.raw:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        else:
            print_payload_summary(payload)
        return 0

    raise SystemExit(f"No report parameter variant succeeded. Last error: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
