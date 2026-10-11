"""Write the GitHub Pages site. Usage: python scripts/build_pages.py --out site"""

import argparse
from pathlib import Path

from flymsg.pages import build


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
