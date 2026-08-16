#!/usr/bin/env python3
"""Pull the path-shaped string literals out of one stored Artifact.

This is the deterministic half of `analyse-source`. `jq` reads a document that
is JSON, and a minified bundle is not one -- which left the Skill's own step 2
admitting that some extractions are done by eye and are therefore not repeatable
by a second party. This closes that: it reads what `mcp__rk2__run_skill_script`
puts on stdin -- one object with an `artifacts` array, each entry carrying the
Artifact's `sha256` and its agent-view `text` -- and writes one JSON object on
stdout. It takes nothing else: no arguments, no environment, no file beside it.

What it reports is *literals*, and the distance between a literal and a route is
the whole of step 4. A path here is a string the build kept. Whether the
application ever requests it is a call graph this does not read, and whether
anything answers it is an exchange this role cannot make. `scanned_literals` is
the denominator for exactly that reason: it says how many strings were looked
at, so a small `paths` list reads as a small proportion rather than as a
finished inventory.

That denominator is quote pairing and not a parse. Nothing here knows a comment
from code or a regular expression from a string, so an apostrophe in `// it's
fine` pairs with the next quote and the span counted there is not a literal
anybody wrote. It is the right order of magnitude on a bundle and it is not a
count to quote at anyone. A parser per language would be the honest fix and is
nine parsers this Skill does not have; what it would buy is a better
denominator, not different paths, since a path in a comment is still a string
the build kept.
"""

import json
import re
import sys

#: One quoted literal, in the three quotings JavaScript has. The body admits an
#: escaped anything, so a `\"` inside a double-quoted string does not end it,
#: and admits any character that is not the opening quote -- including a newline,
#: because a template literal may hold one. The group is atomic and greedy
#: rather than lazy: `(?!\1)` already stops it at the closing quote, so the two
#: agree on every terminated literal, and on an unterminated one -- which a
#: minified megabyte has several of -- atomic fails at once instead of retrying
#: every split of the rest of the file.
LITERAL = re.compile(r"""(["'`])(?>((?:\\.|(?!\1)[\s\S])*))\1""")

#: A path a request could carry: one leading slash, then what RFC 3986 admits in
#: a path or a query, plus `${...}` where a template literal interpolated
#: something. The interpolation is kept rather than dropped, because
#: `/api/orders/${id}` is a parameterised route and `/api/orders` is a different
#: claim about the surface. `?` is in the class because a query string is the
#: parameter half of what this Skill grounds; `#` is not, because a fragment
#: never leaves the client. A second leading slash is refused: `//cdn.host/x` is
#: protocol-relative, so it names somebody's host, and a host is a scope
#: decision rather than a path this Task found. One character is required after
#: the slash, which drops the bare `/` nobody learns anything from.
PATH = re.compile(r"^/(?!/)(?:[A-Za-z0-9._~%!&'()*+,;=:@/?-]|\$\{[^{}]*\})+$")

#: An absolute URL, which is a different fact about the surface: the literal
#: names a host, and a host is somebody's scope decision rather than this Task's.
URL = re.compile(r"^https?://[^\s\"'`<>]+$")


def extract(text: str) -> dict:
    paths, urls, scanned = set(), set(), 0
    for match in LITERAL.finditer(text):
        value = match.group(2)
        scanned += 1
        if PATH.match(value):
            paths.add(value)
        elif URL.match(value):
            urls.add(value)
    return {
        "paths": sorted(paths),
        "scanned_literals": scanned,
        "urls": sorted(urls),
    }


def main() -> int:
    # The same shape as `compare-responses`'s `main`, and duplicated on purpose:
    # `skill.check` runs a script with an empty working directory and a two-entry
    # `PATH`, so there is nothing beside it to import a shared reader from.
    try:
        artifacts = json.load(sys.stdin)["artifacts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"extract_paths reads one JSON object with an artifacts array: {error}", file=sys.stderr)
        return 2
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        print("extract_paths takes exactly one artifact", file=sys.stderr)
        return 2
    try:
        (text,) = (one["text"] for one in artifacts)
    except (KeyError, TypeError) as error:
        print(f"each artifact carries its text: {error}", file=sys.stderr)
        return 2
    json.dump(extract(text), sys.stdout, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
