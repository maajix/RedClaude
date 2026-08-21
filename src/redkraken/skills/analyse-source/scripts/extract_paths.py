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

`paths` and `literals` are two answers rather than one, and which is which
matters. `paths` is what the runtime files against the run in `tool_run_paths`,
and `rk2_source_citation` cleans a proposed route and a stored one through
`rk2_clean_path` before comparing them -- so a path in there that the schema
refuses matches nobody, and the analyst who proposes the route this very run
found is dropped `path_not_in_output` by the run that found it. `groundable` is
that acceptor restated here. `literals` is the other half of the same fact: the
string as the build actually wrote it, query string and method and all, because
the parameter half of a surface is real and this Skill was right to want it.

`redkraken/jsscan.py` decides the same question for the analyser, carries the
same `METHODS`, `VERB` and `groundable`, and cannot be imported from here --
`skill.check` runs this with an empty working directory and a two-entry `PATH`.
`tests/test_jsscan.py` feeds one corpus to both and holds them in step.
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

#: The methods a literal may name in front of its own path. `jsscan.METHODS`,
#: kept in step by the test named above.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE")

#: One literal that names its own method and then its own path:
#: `"GET /orgs/{org}"`, which is how a generated API client writes a whole
#: surface down. The methods are named rather than matched and the space is
#: exactly one, so prose holding a slash does not walk in behind them.
VERB = re.compile(r"^(%s) (/.*)\Z" % "|".join(METHODS))

#: A path a request could carry: one leading slash, then what RFC 3986 admits in
#: a path or a query, plus a `{...}` or `${...}` where the source left a hole.
#: The class is that RFC's `query = *( pchar / "/" / "?" )` written out, because
#: a query admits everything a path does and one thing more. Copied from the
#: ABNF rather than from memory: `unreserved = ALPHA / DIGIT / "-" / "." / "_"
#: / "~"`, `pct-encoded` is the `%`, `sub-delims = "!" / "$" / "&" / "'" / "("
#: / ")" / "*" / "+" / "," / ";" / "="`, and `pchar` adds `":"` and `"@"`. The
#: `$` was missing before ticket 92 and is a sub-delim like any other. `{` and
#: `}` are in neither production and are here only as the template extension.
#: The hole is kept rather than dropped, because `/api/orders/{id}` is a
#: parameterised route and `/api/orders` is a different claim about the surface;
#: both spellings appear in the wild and `jsscan._named_hole` emits the braced
#: one, so refusing it would be refusing what this harness itself writes. `?` is
#: in the class because a query string is the parameter half of what this Skill
#: grounds -- `path_of` cuts it back off for `paths` and `literals` keeps it.
#: `#` is not, because a fragment never leaves the client. A second leading
#: slash is refused: `//cdn.host/x` is protocol-relative, so it names somebody's
#: host, and a host is a scope decision rather than a path this Task found. One
#: character is required after the slash, which drops the bare `/` nobody learns
#: anything from.
PATH = re.compile(r"^/(?!/)(?:[A-Za-z0-9._~%!$&'()*+,;=:@/?-]|\$?\{[^{}\s]*\})+\Z")

#: The RFC 6570 operators that open something which is not part of the path.
#: `jsscan.CUTS`, kept in step by the test named at the end of the docstring.
CUTS = ("?", "&", "#")

#: An absolute URL, which is a different fact about the surface: the literal
#: names a host, and a host is somebody's scope decision rather than this Task's.
URL = re.compile(r"^https?://[^\s\"'`<>]+$")


def groundable(path: str) -> bool:
    """Whether `rk2_clean_path` would take this, which is whether it can ground.

    The acceptor lives in
    `migrations/20260813T090000Z__a_recon_run_becomes_typed_surface.sql`. It is
    restated rather than queried because this program runs in a container with
    no database, and it is the gate on `paths` rather than on the reading: a
    literal the schema refuses is still a fact about the file and is reported in
    `literals`.
    """
    if not path or not path.startswith("/") or "//" in path:
        return False
    if any(mark in path for mark in "?#%") or any(char.isspace() for char in path):
        return False
    return not ("/./" in path or "/../" in path or path.endswith(("/.", "/..")))


def path_half(value: str) -> str:
    """The path half of one literal: everything before its query starts.

    Depth-aware, because a URI template writes its query expansion inside the
    braces. `/packages/{name}/restore{?token}` is RFC 6570 for a route that
    takes a `token` parameter, and cutting at the bare `?` would leave
    `/packages/{name}/restore{`, which is not a path anybody wrote and is the
    shape a naive cut produces on every generated client.

    The operator only opens a query where the template is not already inside
    one, so the cut is made at depth zero and nowhere else: `/x/{a{?b}}` cut on
    the inner brace would leave `/x/{a`, dangling, which `PATH` refuses and
    `groundable` does not.

    Three of that RFC's operators open something that is not the path, and they
    are `CUTS`: `?` and `&` are its form-style query, `#` its fragment. The
    others -- `+` from `op-level2`, and `.`, `/` and `;` from `op-level3` --
    expand inside the path and are kept, and `op-reserve` is left undefined by
    the RFC and is not guessed at here. A `?` or a `#` outside braces opens a
    query or a fragment the ordinary way.
    """
    depth = 0
    for index, char in enumerate(value):
        if char == "{":
            if depth == 0 and value[index + 1:index + 2] in CUTS:
                return value[:index]
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        elif depth == 0 and char in "?#":
            return value[:index]
    return value


def verb_of(value: str) -> str | None:
    """The method one literal names in front of its own path, if it names one.

    Not called by `extract`, and here on purpose: the method reaches the analyst
    inside `literals`, which carries the string as the build wrote it. This is
    the other half of `jsscan.method_of`, which does report it as its own key,
    and the test named in the module docstring holds the two answers equal.
    """
    match = VERB.match(value)
    return match.group(1) if match is not None and path_of(value) is not None else None


def path_of(value: str) -> str | None:
    """The route one literal describes, or nothing.

    The method in front of the path is cut because the schema stores a route
    rather than a sentence, and `verb_of` is where the method is kept. The query
    is cut for the same reason and `literals` is where it is kept.
    """
    match = VERB.match(value)
    if match is not None:
        value = match.group(2)
    if not PATH.match(value):
        return None
    cut = path_half(value)
    # The bare root again, arrived at from the other side: `"/?next=x"` cuts to
    # `/`, and a bundle that told an analyst only that it has a root has told
    # them nothing.
    return cut if len(cut) > 1 else None


def extract(text: str) -> dict:
    paths, literals, urls, scanned = set(), set(), set(), 0
    for match in LITERAL.finditer(text):
        value = match.group(2)
        scanned += 1
        found = path_of(value)
        if found is not None:
            literals.add(value)
            if groundable(found):
                paths.add(found)
        elif URL.match(value):
            urls.add(value)
    return {
        "literals": sorted(literals),
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
