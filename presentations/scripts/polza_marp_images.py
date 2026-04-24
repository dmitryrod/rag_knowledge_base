"""Placeholder Polza image generator entrypoint.

Replace this file with the real implementation when the presentation
pipeline starts using AI-generated images.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="generate")
    parser.add_argument("-o", "--output", default="presentations/assets/generated/placeholder.txt")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "Placeholder output from presentations/scripts/polza_marp_images.py\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
