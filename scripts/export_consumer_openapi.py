"""Write (or check) the pinned consumer OpenAPI slice.

    pixi run python scripts/export_consumer_openapi.py          # regenerate
    pixi run python scripts/export_consumer_openapi.py --check  # exit 1 on drift

Prints the sha256 of the rendered file, which downstream contracts pin.
"""

import argparse
import sys

from metazebrobot.api_server import create_app
from metazebrobot.consumer_contract import (
    CONSUMER_OPENAPI_PATH,
    consumer_openapi,
    digest,
    render,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the committed file differs from the code.",
    )
    args = parser.parse_args()

    text = render(consumer_openapi(create_app()))
    path = CONSUMER_OPENAPI_PATH

    if args.check:
        current = path.read_text() if path.exists() else None
        if current != text:
            print(f"DRIFT: {path} does not match the code. Re-run without --check.")
            return 1
        print(f"OK {digest(text)}  {path}")
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"{digest(text)}  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
