"""Generate the six static ASCII-eye design review sheets."""

from __future__ import annotations

import argparse
from pathlib import Path

from synapse_pet.ui.ascii_eye_mockups import PALETTES, generate_mockups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "mockups",
        help="directory for the six PNG sheets (default: docs/mockups)",
    )
    parser.add_argument(
        "--palette",
        choices=tuple(PALETTES),
        default="nocturne",
        help="static color palette",
    )
    args = parser.parse_args()
    for path in generate_mockups(args.output, args.palette):
        print(f"{path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
