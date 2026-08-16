#!/usr/bin/env python3
"""Compare two stored Artifacts line by line and answer in one JSON object.

This is the deterministic half of `compare-responses`. It reads what
`mcp__rk2__run_skill_script` puts on stdin -- one object with an `artifacts`
array, each entry carrying the Artifact's `sha256` and its agent-view `text` --
and writes one JSON object on stdout. It takes nothing else: no arguments, no
environment, no file beside it. Two runs over one input produce one answer,
which is why a Finding may cite what it says.

The comparison is over lines as sets. A model asked to describe the difference
between two responses will describe the difference it expected; this describes
the difference that is there, and the two are worth keeping apart.
"""

import json
import sys


def compare(first: str, second: str) -> dict:
    left, right = first.split("\n"), second.split("\n")
    unique_left, unique_right = set(left), set(right)
    return {
        "identical": first == second,
        "lengths": [len(first), len(second)],
        "line_counts": [len(left), len(right)],
        "only_in_first": sorted(unique_left - unique_right),
        "only_in_second": sorted(unique_right - unique_left),
        "shared_lines": len(unique_left & unique_right),
    }


def main() -> int:
    try:
        artifacts = json.load(sys.stdin)["artifacts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"compare reads one JSON object with an artifacts array: {error}", file=sys.stderr)
        return 2
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        print("compare takes exactly two artifacts", file=sys.stderr)
        return 2
    try:
        first, second = (one["text"] for one in artifacts)
    except (KeyError, TypeError) as error:
        print(f"each artifact carries its text: {error}", file=sys.stderr)
        return 2
    json.dump(compare(first, second), sys.stdout, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
