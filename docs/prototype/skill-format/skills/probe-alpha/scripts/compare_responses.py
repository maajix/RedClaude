#!/usr/bin/env python3
"""Fixture script. Deterministic, so it is code rather than prose (Q1).

Invoked only through `run_skill_script`, never Bash directly, so the run leaves
a provenance row (Q10).
"""

from __future__ import annotations

import argparse
import json
import sys


def compare(left: str, right: str, ignore_headers: list[str]) -> dict:
    ignored = sorted({h.lower() for h in ignore_headers})
    return {
        "left": left,
        "right": right,
        "ignored_headers": ignored,
        "verdict": "differs" if left != right else "identical",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--ignore-headers", nargs="*", default=[])
    args = parser.parse_args()
    json.dump(compare(args.left, args.right, args.ignore_headers), sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
