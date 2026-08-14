"""The half of a source analysis that runs inside the container.

This file is not imported by anything. It is staged into `/input` and run by
the container's own interpreter, for `browser_driver.py`'s reason: the boundary
an offline tool runs behind has no `redkraken` on its path and no index to
install one from. It imports nothing outside the standard library, and the
registry row that names it -- `offline_tools.analyser` -- is what puts it there.

Three questions, one file, because they are three readings of the same tokens:

* `js_parse` says what a source Artifact is made of. Its size and shape, the
  source map it points at, and every path-shaped literal it holds, each marked
  with whether anything actually requests it.
* `js_routes` says what it calls. Only the literals that are an argument of a
  request, each with the call site that grounds it, because a route nothing
  calls is a string and this harness has one word for the difference.
* `js_map` reads a source map, indexes the originals it carries, and recovers
  one of them as a file.

The grounding rule is the whole point of the ticket. A model reading a bundle
sees a fraction of it and a path that sounds right is indistinguishable in
prose from a path that is there, so this file never reports a path because it
looks like one. It reports a path because a call to something that makes
requests was given it as an argument, and it prints the call and the offset so
the claim can be checked against the bytes the run recorded.

What it does not do is parse JavaScript. A tokeniser is enough to answer these
three questions and is the thing that can be got right: it separates code from
strings, comments and regular expressions, which is the distinction every naive
scanner of bundles gets wrong. Two ambiguities are left where the tokeniser
resolves them by the usual heuristic -- a `/` after `)` or `}` is division
rather than a regular expression -- and both are noted where they are decided.

Everything printed on stdout is one JSON document. The input's own hash is in
it, computed here from the bytes this process read, so what the run recorded as
its input and what the analysis was actually of are two statements that can be
held against each other.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass

#: What this program answers to `--version`. The registry pins a pattern
#: against it, so this is the contract of the output below rather than a build
#: number: a change to what these documents mean is a change here. `paths` is
#: part of that contract: an answer that names request paths names them there,
#: and the runtime files them against the run.
VERSION = "rk2-jsscan 1"

#: The one file `js_map` may write, and it is the name the registry declares as
#: a declared output. Bare, because the workspace is where the runtime mounts it
#: and a program that could name a directory could name another one.
RECOVERED = "source.js"

#: Where a `${...}` goes in a route template when the expression is not a plain
#: identifier. `rk2_clean_path` admits braces, so a template survives promotion
#: as the route it describes rather than as a path with a hole in it.
HOLE = "{}"

#: The methods a call site may name. Anything else in a `method:` property or
#: an `open()` first argument is not a method and is left unread rather than
#: guessed at -- a route reported under the wrong verb is a route reported
#: wrongly.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE")

#: Callee names that make a request. The tail of the member chain, so
#: `axios.get`, `client.get` and `get` are one rule; what the call was written
#: as is reported beside every route, because "which of these it was" is the
#: reader's question and not this file's to answer.
REQUESTERS = ("fetch", "request", "ajax", "open", *(name.lower() for name in METHODS))

#: Property names an options object gives a method under. `type` is jQuery's
#: spelling and `method` is everyone else's.
METHOD_KEYS = ("method", "type")

#: Where an options object gives the path.
URL_KEYS = ("url", "uri", "path")

#: A name token, the only thing a member chain is made of.
NAME = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

#: A number, tokenised only so that a `/` after one reads as division.
NUMBER = re.compile(r"(?:0[xXbBoO][0-9a-fA-F_]+|[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][+-]?[0-9]+)?"
                    r"|\.[0-9][0-9_]*(?:[eE][+-]?[0-9]+)?)n?")

#: Keywords after which a `/` opens a regular expression rather than dividing.
#: The list is the operator positions: everything here is followed by an
#: expression, and everything else that is a name is a value.
BEFORE_REGEX = frozenset(
    "return typeof case in of new delete void instanceof do else yield await throw".split()
)

#: What the tokeniser calls the punctuation that can precede a division.
CLOSERS = (")", "]", "}")

#: The two kinds of token that can carry a path. Everything that reads a route
#: out of the stream asks for one of these, and a third kind added here is a
#: third kind every reader gets at once.
LITERALS = ("string", "template")

#: Where a source map says which file it describes.
SOURCE_MAP = re.compile(rb"(?://|/\*)[#@]\s*sourceMappingURL=([^\s*'\"]+)")

#: How long a line has to be before a file is called minified. Bundlers emit
#: one enormous line; hand-written source does not, and the difference decides
#: whether an offset is worth printing as a line number.
MINIFIED_LINE = 500


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical unit, with where it started so a finding can be checked."""

    kind: str
    value: str
    start: int
    #: For a template literal: the static chunks and the expression sources
    #: between them, which is what a route template is built out of.
    parts: list[str] | None = None
    holes: list[str] | None = None


def tokenize(text: str) -> list[Token]:
    """Every token that matters, in order, with comments and regexes kept.

    Kept rather than skipped because they are half the answer: a path inside a
    comment is exactly the decoy this ticket is about, and a regular expression
    read as division is how a scanner ends up reporting the inside of a pattern
    as source.
    """
    out: list[Token] = []
    index, size = 0, len(text)
    while index < size:
        char = text[index]
        if char in " \t\r\n\f\v ﻿":
            index += 1
            continue
        if char == "/" and index + 1 < size and text[index + 1] == "/":
            stop = text.find("\n", index)
            stop = size if stop < 0 else stop
            out.append(Token("comment", text[index + 2 : stop], index))
            index = stop
            continue
        if char == "/" and index + 1 < size and text[index + 1] == "*":
            stop = text.find("*/", index + 2)
            stop = size if stop < 0 else stop + 2
            out.append(Token("comment", text[index + 2 : max(index + 2, stop - 2)], index))
            index = stop
            continue
        if char in "'\"":
            value, stop = _string(text, index, char)
            out.append(Token("string", value, index))
            index = stop
            continue
        if char == "`":
            parts, holes, stop = _template(text, index)
            out.append(Token("template", _written(parts, holes), index, parts, holes))
            index = stop
            continue
        if char == "/" and _opens_regex(out):
            index = _regex(text, index, out)
            continue
        match = NAME.match(text, index)
        if match:
            out.append(Token("name", match.group(), index))
            index = match.end()
            continue
        match = NUMBER.match(text, index)
        if match:
            out.append(Token("number", match.group(), index))
            index = match.end()
            continue
        out.append(Token("punct", char, index))
        index += 1
    return out


def _string(text: str, index: int, quote: str) -> tuple[str, int]:
    """One quoted string, decoded enough to be a path, and where it ended."""
    chunks: list[str] = []
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            chunks.append(_escape(text, index + 1))
            index += 2 + (4 if text[index + 1 : index + 2] == "u" else 0)
            continue
        if char == quote:
            index += 1
            break
        if char == "\n":
            # An unterminated string. Minified code has none, and stopping at
            # the newline keeps one broken literal from swallowing the file.
            break
        chunks.append(char)
        index += 1
    return "".join(chunks), index


def _escape(text: str, index: int) -> str:
    """What one backslash escape stands for, as far as a path needs.

    `\\u` is decoded because bundlers emit `\\u002f` for a slash and a scanner
    that did not decode it would miss the route. Everything else is taken
    literally, which is right for `\\/` and harmless for the rest.
    """
    char = text[index : index + 1]
    if char == "u":
        try:
            return chr(int(text[index + 1 : index + 5], 16))
        except ValueError:
            return char
    return {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "0": "\0"}.get(char, char)


def _template(text: str, index: int) -> tuple[list[str], list[str], int]:
    """One template literal: its static chunks, its expressions, and the end.

    The expressions are kept as source rather than parsed. A route template
    wants to know that there is a hole and, when the hole is one identifier,
    what it is called -- and that is the whole of what a `${}` contributes to a
    path.
    """
    parts: list[str] = []
    holes: list[str] = []
    chunk: list[str] = []
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            chunk.append(_escape(text, index + 1))
            index += 2 + (4 if text[index + 1 : index + 2] == "u" else 0)
            continue
        if char == "`":
            index += 1
            break
        if char == "$" and text[index + 1 : index + 2] == "{":
            parts.append("".join(chunk))
            chunk = []
            source, index = _expression(text, index + 2)
            holes.append(source)
            continue
        chunk.append(char)
        index += 1
    parts.append("".join(chunk))
    return parts, holes, index


def _rejoined(parts: list[str], holes: list[str], render: Callable[[str], str]) -> str:
    """A template literal's chunks and holes back in the order they were in.

    The two callers differ in nothing but how a hole is spelled, so that is the
    argument: putting the pieces back in the wrong order is the mistake worth
    having one place to make.
    """
    pieces = []
    for index, part in enumerate(parts):
        pieces.append(part)
        if index < len(holes):
            pieces.append(render(holes[index]))
    return "".join(pieces)


def _written(parts: list[str], holes: list[str]) -> str:
    """A template literal put back together as it was written.

    What a finding quotes as the literal behind it, so a reader looking at the
    file sees the thing this reported. The static chunks alone would be a
    different string -- `/orders//lines` for a template that says `${id}` --
    and quoting that would be quoting something nobody wrote.
    """
    return _rejoined(parts, holes, lambda source: "${%s}" % source)


def _expression(text: str, index: int) -> tuple[str, int]:
    """The source of one `${...}`, up to the brace that closes it.

    Depth-counted, and strings and nested templates are skipped whole: a `}`
    inside a string is not the end of the expression, and a scanner that
    thought it was would rejoin the rest of the file to the template.
    """
    start, depth = index, 1
    while index < len(text):
        char = text[index]
        if char in "'\"":
            _, index = _string(text, index, char)
            continue
        if char == "`":
            _, _, index = _template(text, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    return text[start:index], index


def _opens_regex(out: list[Token]) -> bool:
    """Whether a `/` here starts a regular expression rather than dividing.

    The usual heuristic, and the two cases it gets wrong are named because they
    are the ones a reader will find: `if (x) /re/.test(y)` and a `/` after a
    block's closing brace both read as division here. Both are rare in the
    minified code this runs on, and both fail towards reading a pattern as
    source rather than towards reading source as a pattern -- which is the safe
    direction, because a path invented out of a regular expression's insides
    would still have to survive the grounding rule to be reported.
    """
    if not out:
        return True
    last = out[-1]
    if last.kind == "comment":
        return _opens_regex(out[:-1])
    if last.kind in ("string", "template", "number", "regex"):
        return False
    if last.kind == "name":
        return last.value in BEFORE_REGEX
    return last.value not in CLOSERS


def _regex(text: str, index: int, out: list[Token]) -> int:
    """Consume one regular expression literal, class brackets and all."""
    start, index, inside = index, index + 1, False
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            inside = True
        elif char == "]":
            inside = False
        elif char == "/" and not inside:
            index += 1
            break
        elif char == "\n":
            break
        index += 1
    while index < len(text) and text[index].isalpha():
        index += 1
    out.append(Token("regex", text[start:index], start))
    return index


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def path_of(value: str) -> str | None:
    """The route one string literal describes, or nothing.

    Absolute paths and absolute URLs both answer; everything else does not.
    The query and the fragment are cut because they are not part of a route --
    `rk2_clean_path` refuses a path carrying either, and a tool that emitted
    one would be proposing something the schema will not take.
    """
    if not value or "\n" in value or " " in value:
        return None
    if value.startswith("//"):
        rest = value[2:]
        cut = rest.find("/")
        value = rest[cut:] if cut >= 0 else "/"
    elif "://" in value:
        rest = value.split("://", 1)[1]
        cut = rest.find("/")
        value = rest[cut:] if cut >= 0 else "/"
    if not value.startswith("/"):
        return None
    for mark in ("?", "#"):
        cut = value.find(mark)
        if cut >= 0:
            value = value[:cut]
    return value or "/"


def _named_hole(source: str) -> str:
    """One `${...}` as a path spells it.

    A hole that is one identifier keeps its name, because `/orders/${id}` is a
    route with a parameter called `id` and that is worth carrying. Anything
    else becomes an anonymous hole rather than an invented name.
    """
    source = source.strip()
    return "{%s}" % source if NAME.fullmatch(source) else HOLE


def template_source(token: Token) -> str:
    """One template literal with its holes named, as a path would spell them."""
    return _rejoined(token.parts, token.holes, _named_hole)


def template_of(token: Token) -> str | None:
    """The route one template literal describes, holes and all."""
    return path_of(template_source(token))


def route_of(token: Token) -> str | None:
    """The route this token describes, whichever kind of literal it is."""
    if token.kind == "string":
        return path_of(token.value)
    if token.kind == "template":
        return template_of(token)
    return None


# ---------------------------------------------------------------------------
# Call sites
# ---------------------------------------------------------------------------


def calls(tokens: list[Token]) -> list[dict]:
    """Every request-shaped call, with the route it was given.

    One pass. A `(` is a call when a name precedes it, the callee is the member
    chain that name ends, and the arguments are the top-level comma-separated
    token runs up to the matching `)`. Nothing here follows a variable to its
    definition: a route assigned to a constant and requested through it is not
    reported, because reporting it would mean deciding what the constant held
    at the moment of the call, and that decision is where invented endpoints
    come from.
    """
    found: list[dict] = []
    for index, token in enumerate(tokens):
        if token.kind != "punct" or token.value != "(" or index == 0:
            continue
        chain = _chain(tokens, index - 1)
        if not chain or chain[-1].lower() not in REQUESTERS:
            continue
        arguments = _arguments(tokens, index)
        route = _route_argument(chain, arguments)
        if route is None:
            continue
        found.append(
            {
                "call": ".".join(chain),
                "method": _method(chain, arguments),
                "path": route[0],
                "literal": route[1].value,
                "offset": route[1].start,
            }
        )
    return found


def _chain(tokens: list[Token], index: int) -> list[str]:
    """The member chain ending at this token, as names, or nothing.

    `a.b.c(` gives `['a','b','c']`. A computed member -- `a[k](` -- gives
    nothing, because the name that would decide whether this is a request is
    the one part that is not written down.
    """
    if tokens[index].kind != "name":
        return []
    names = [tokens[index].value]
    index -= 1
    while index >= 1 and tokens[index].kind == "punct" and tokens[index].value == ".":
        if tokens[index - 1].kind != "name":
            break
        names.insert(0, tokens[index - 1].value)
        index -= 2
    return names


def _arguments(tokens: list[Token], index: int) -> list[list[Token]]:
    """The argument list of the call whose `(` is at `index`.

    Split on commas at depth one, so an options object and an array stay whole.
    Runs to the end of the file when the parenthesis never closes, which is a
    truncated Artifact rather than a case worth a second answer.
    """
    groups: list[list[Token]] = [[]]
    depth = 0
    for token in tokens[index:]:
        if token.kind == "punct" and token.value in "([{":
            depth += 1
            if depth == 1:
                continue
        elif token.kind == "punct" and token.value in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif token.kind == "punct" and token.value == "," and depth == 1:
            groups.append([])
            continue
        groups[-1].append(token)
    return [group for group in groups if group]


def _route_argument(chain: list[str], arguments: list[list[Token]]) -> tuple[str, Token] | None:
    """The route this call was given, and the literal that carried it.

    Three shapes, and they are the three ways a request names a path:
    `open(method, url)` puts it second, an options object puts it under a key,
    and everything else puts it first.
    """
    if not arguments:
        return None
    if chain[-1].lower() == "open" and len(arguments) > 1:
        ordered = [arguments[1], arguments[0]]
    else:
        ordered = list(arguments)
    for group in ordered:
        joined = _joined(group)
        if joined is not None:
            return joined
        keyed = _property(group, URL_KEYS)
        if keyed is not None:
            route = route_of(keyed)
            if route is not None:
                return route, keyed
    return None


def _joined(group: list[Token]) -> tuple[str, Token] | None:
    """The route one argument describes, literal or built by `+`.

    `"/api/orders/" + id` is the shape a bundler leaves behind wherever the
    source had a template, and refusing to read it would mean missing most of
    the routes in a minified file. It is still the grounding rule and not a
    relaxation of it: the literal is lexically an argument of the request, and
    the parts that are not literals become holes rather than guesses at what a
    variable held.

    The group has to be nothing but literals, names and `+` for this to apply,
    which is what keeps an options object out: a `"/b"` inside `{body: "/b"}`
    is not this call's route, and the braces are how that is known.
    """
    if not group or group[0].kind not in LITERALS:
        return None
    for index, token in enumerate(group):
        if index % 2 == 0:
            if token.kind not in (*LITERALS, "name", "number"):
                return None
        elif token.kind != "punct" or token.value != "+":
            return None
    if len(group) % 2 == 0:
        return None

    pieces = []
    for index, token in enumerate(group[::2]):
        if token.kind == "string":
            pieces.append(token.value)
        elif token.kind == "template":
            pieces.append(template_source(token))
        else:
            pieces.append("{%s}" % token.value if token.kind == "name" else token.value)
    route = path_of("".join(pieces))
    return None if route is None else (route, group[0])


def _method(chain: list[str], arguments: list[list[Token]]) -> str | None:
    """Which verb this call names, or nothing when it does not name one.

    In verb order: the callee itself, then `open`'s first argument, then a
    `method` or `type` property of any argument. `fetch` with no options is
    left unread rather than defaulted to GET -- the default is the language's
    and not this file's to assert, and an endpoint proposed under a verb
    nothing wrote is exactly the invention the grounding rule exists to stop.
    """
    tail = chain[-1].upper()
    if tail in METHODS:
        return tail
    if chain[-1].lower() == "open" and arguments:
        named = _literal(arguments[0])
        if named is not None and named.value.upper() in METHODS:
            return named.value.upper()
    for group in arguments:
        keyed = _property(group, METHOD_KEYS)
        if keyed is not None and keyed.value.upper() in METHODS:
            return keyed.value.upper()
    return None


def _property(group: list[Token], keys: tuple[str, ...]) -> Token | None:
    """The string a `key: "value"` pair in this token run carries.

    Keys are matched as written, quoted or not, which is the two spellings an
    object literal has. Nothing recurses: a `url` nested two objects deep is
    not this call's url, and treating it as one would attribute a route to a
    request that was not given it.
    """
    for index in range(len(group) - 2):
        name = group[index]
        if name.kind not in ("name", "string") or name.value.lower() not in keys:
            continue
        if group[index + 1].kind != "punct" or group[index + 1].value != ":":
            continue
        if group[index + 2].kind in LITERALS:
            return group[index + 2]
    return None


def _literal(group: list[Token]) -> Token | None:
    return group[0] if len(group) == 1 and group[0].kind == "string" else None


# ---------------------------------------------------------------------------
# The three answers
# ---------------------------------------------------------------------------


class Refused(Exception):
    """The input is not the kind of thing this question can be asked of."""


def lines(text: str) -> list[int]:
    """Where every line starts, for turning an offset into a line number."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def line_of(starts: list[int], offset: int) -> int:
    """Which line an offset falls on, counting from one.

    A binary search rather than a count, because a minified bundle is one line
    and a hand-written file is thousands, and every reported finding asks this
    question again over the same list.
    """
    low, high = 0, len(starts) - 1
    while low < high:
        middle = (low + high + 1) // 2
        if starts[middle] <= offset:
            low = middle
        else:
            high = middle - 1
    return low + 1


def _named_paths(paths: Iterable[str]) -> list[str]:
    """Every request path one answer names, deduplicated and in one order.

    Redundant with the answer it sits beside, and deliberately: it is the one
    key the runtime records against the run, so a proposed route can be held
    against what this analysis actually said. A recorder that read
    `path_literals` from one subcommand and `routes` from another would be a
    second place those shapes live, and the shape is this file's to change.
    """
    return sorted({path for path in paths if path})


def parse(raw: bytes, text: str) -> dict:
    """What this source is made of, and which of its paths anything requests.

    Every path literal is claimed, including the ones nothing requests. What
    this answer says is that the file names them, which is true of a decoy; the
    `requested` flag beside each is what says whether anything asks for it, and
    deciding a decoy is not an endpoint is the analyst's judgement rather than
    a fact about the bytes.
    """
    tokens = tokenize(text)
    starts = lines(text)
    grounded = {call["offset"] for call in calls(tokens)}
    literals = []
    for token in tokens:
        route = route_of(token)
        if route is None:
            continue
        literals.append(
            {
                "value": route,
                "offset": token.start,
                "line": line_of(starts, token.start),
                "kind": token.kind,
                # The whole of criterion 6 in one boolean. A path that is in the
                # file and that nothing requests is reported as exactly that,
                # rather than left out -- an analyst has to be able to see the
                # decoy in order to not propose it.
                "requested": token.start in grounded,
            }
        )
    longest = max((len(line) for line in text.splitlines()), default=0)
    reference = SOURCE_MAP.search(raw)
    return {
        "byte_size": len(raw),
        "lines": len(starts),
        "longest_line": longest,
        "minified": longest > MINIFIED_LINE,
        "source_map": reference.group(1).decode("utf-8", "replace") if reference else None,
        "tokens": len(tokens),
        "strings": sum(1 for token in tokens if token.kind in LITERALS),
        "comments": sum(1 for token in tokens if token.kind == "comment"),
        "path_literals": literals,
        "paths": _named_paths(literal["value"] for literal in literals),
    }


def routes(raw: bytes, text: str) -> dict:
    """Every route this source requests, one entry per method and path.

    Deduplicated across call sites and every site kept, because two calls to
    one route is one endpoint and the second site is what a reader checks when
    the first looks wrong.
    """
    starts = lines(text)
    collected: dict[tuple[str | None, str], dict] = {}
    for call in calls(tokenize(text)):
        key = (call["method"], call["path"])
        entry = collected.setdefault(
            key, {"method": call["method"], "path": call["path"], "sites": []}
        )
        entry["sites"].append(
            {
                "call": call["call"],
                "literal": call["literal"],
                "offset": call["offset"],
                "line": line_of(starts, call["offset"]),
            }
        )
    ordered = sorted(collected.values(), key=lambda entry: (entry["path"], entry["method"] or ""))
    return {
        "byte_size": len(raw),
        "routes": ordered,
        "paths": _named_paths(entry["path"] for entry in ordered),
    }


def sourcemap(raw: bytes, text: str, select: int | None) -> dict:
    """Index one source map, and recover one original out of it.

    The index is what makes the recovery citable: an original is chosen by its
    position in a document this run printed, so the only way to name one is to
    have read the run that listed it.
    """
    try:
        document = json.loads(text)
    except ValueError as error:
        raise Refused(f"the Artifact is not a source map: {error}") from None
    if not isinstance(document, dict) or "sources" not in document:
        raise Refused("the Artifact is JSON and is not a source map")
    names = document.get("sources") or []
    contents = document.get("sourcesContent") or []
    if not isinstance(names, list):
        raise Refused("the source map's sources are not a list")

    index = []
    for position, name in enumerate(names):
        body = contents[position] if position < len(contents) else None
        index.append(
            {
                "index": position,
                "path": name if isinstance(name, str) else None,
                "bytes": len(body.encode()) if isinstance(body, str) else 0,
                "recoverable": isinstance(body, str),
            }
        )

    answer = {
        "byte_size": len(raw),
        "version": document.get("version"),
        "file": document.get("file"),
        "source_root": document.get("sourceRoot"),
        "sources": index,
        "recovered": None,
    }
    if select is None:
        return answer
    if not 0 <= select < len(index) or not index[select]["recoverable"]:
        raise Refused(f"this source map carries no recoverable source at {select}")

    body = contents[select].encode()
    with open(RECOVERED, "wb") as handle:
        handle.write(body)
    answer["recovered"] = {
        "index": select,
        "path": index[select]["path"],
        "byte_size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "output": RECOVERED,
    }
    return answer


#: The three questions, in the spelling the registry gives them. The tool's own
#: name is the subcommand, which is what lets three registry rows share one
#: file without a fourth string per row saying which part of it to run.
ANSWERS = ("js_parse", "js_routes", "js_map")


def answer(question: str, raw: bytes, text: str, rest: list[str]) -> dict:
    """Ask one of the three questions of these bytes.

    One place decides which, and it is the only place that knows an argument
    after the Artifact means anything -- `js_map` takes an index and the other
    two take nothing, and a signature they all shared would be two functions
    carrying a parameter to keep the third company.
    """
    if question == "js_parse":
        return parse(raw, text)
    if question == "js_routes":
        return routes(raw, text)
    if not rest:
        return sourcemap(raw, text, None)
    try:
        return sourcemap(raw, text, int(rest[0]))
    except ValueError:
        raise Refused(f"the source to recover is named by index, not {rest[0]!r}") from None


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--version":
        sys.stdout.write(VERSION + "\n")
        return 0
    if len(argv) < 3 or argv[1] not in ANSWERS:
        sys.stderr.write(f"usage: {os.path.basename(argv[0])} "
                         f"<{'|'.join(ANSWERS)}|--version> <artifact> [index]\n")
        return 2

    question, path = argv[1], argv[2]
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        sys.stderr.write(f"the input could not be read: {error}\n")
        return 2

    # Decoded permissively on purpose. A bundle is not always valid UTF-8 and
    # an analysis that refused one would refuse exactly the minified files this
    # exists to read; the hash below is of the bytes, so what was analysed is
    # still named exactly.
    text = raw.decode("utf-8", "replace")
    try:
        found = answer(question, raw, text, argv[3:])
    except Refused as error:
        sys.stderr.write(f"{error}\n")
        return 3

    json.dump(
        {
            "tool": question,
            "analyser": VERSION,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            **found,
        },
        sys.stdout,
        sort_keys=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
