"""The grammar a Skill and a Playbook share: a fenced block, and nothing richer.

Both corpora are markdown with metadata fenced on top, and both are read twice --
once by the CLI, which treats the block as YAML, and once here, line by line. Two
parsers over one document is a document that can mean two things, so the grammar
admits only values where the two cannot disagree: no leading indicator character,
no `key: value` inside a value, no comment introducer. Anything richer is written
as JSON, which is a subset of YAML and so parses the same both ways.

It lives here rather than in `skill` because `playbook` needs the same grammar and
a second copy is the one place the two corpora could start meaning different
things by the same syntax. What it does *not* hold is what either corpus means:
which keys exist, which are required, what a value has to be -- those are
per-corpus and stay where the corpus is compiled.

`fault` is threaded through every function so each corpus keeps raising its own
error type with its own codes. The alternative -- one exception class for both --
would make `except SkillError` catch a playbook's parse failure.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

#: The fence, which is the same three characters both parsers look for.
FENCE = "---"

#: A frontmatter key. `bb:` is a namespace and not a special case -- the probe in
#: `docs/prototype/skill-format/README.md` measured exactly this prefix surviving
#: the CLI's own parse on 2.1.224, so it is the one extension point either corpus
#: is allowed to have evidence for.
KEY = re.compile(r"^[a-z][a-z0-9_]*(?:[-:][a-z0-9_]+)*$")

#: What a list entry has to be before anything more specific is asked of it: a
#: non-empty string that neither begins nor is made of whitespace.
ENTRY = re.compile(r"^\S.*$")


class DocumentError(Exception):
    """One reason a document does not compile, in the words a test names it by.

    `code` exists so a negative test asserts the rule that fired rather than the
    sentence it fired with: the sentence is for the operator reading the refusal
    and is free to improve, the code is what the suite pins.
    """

    def __init__(self, code: str, subject: str, detail: str) -> None:
        super().__init__(f"{code}: {subject}: {detail}")
        self.code = code
        self.subject = subject
        self.detail = detail


def digest(data: bytes) -> str:
    """SHA-256, hex, lower case -- the one spelling every hash in this system has."""
    return hashlib.sha256(data).hexdigest()


def scalar(fault: type[DocumentError], name: str, key: str, raw: str) -> str:
    """A plain value, restricted to what YAML and this parser must agree about."""
    if not raw:
        raise fault("frontmatter_malformed", name, f"{key} has no value")
    if raw[0] in "-?:,[]{}#&*!|>'\"%@`":
        raise fault(
            "frontmatter_malformed", name,
            f"{key} starts with {raw[0]!r}, which YAML reads as structure; quote it as JSON",
        )
    if ": " in raw or raw.endswith(":"):
        raise fault(
            "frontmatter_malformed", name, f"{key} carries a colon YAML would read as a second key"
        )
    if " #" in raw:
        raise fault("frontmatter_malformed", name, f"{key} carries a comment introducer")
    return raw


def field(fault: type[DocumentError], name: str, number: int, line: str) -> tuple[str, Any]:
    """One `key: value` line, with JSON read as JSON and everything else as text."""
    if line != line.strip():
        raise fault("frontmatter_malformed", name, f"line {number} is indented or padded")
    key, colon, raw = line.partition(": ")
    if not colon:
        raise fault("frontmatter_malformed", name, f"line {number} is not `key: value`")
    if not KEY.match(key):
        raise fault("frontmatter_malformed", name, f"line {number}: {key!r} is not a key")
    if raw.startswith(("[", "{", '"')):
        try:
            return key, json.loads(raw)
        except json.JSONDecodeError as error:
            raise fault("frontmatter_malformed", name, f"{key}: {error}") from error
    return key, scalar(fault, name, key, raw)


def frontmatter(
    fault: type[DocumentError], name: str, document: str, text: str
) -> tuple[dict[str, Any], str]:
    """The fenced block and the body under it, or the reason there is neither."""
    lines = text.split("\n")
    if not lines or lines[0] != FENCE:
        raise fault("frontmatter_malformed", name, f"{document} does not open with {FENCE}")
    try:
        end = lines.index(FENCE, 1)
    except ValueError:
        raise fault("frontmatter_malformed", name, "the frontmatter is never closed") from None
    if end == 1:
        raise fault("frontmatter_malformed", name, "the frontmatter is empty")
    fields: dict[str, Any] = {}
    for number, line in enumerate(lines[1:end], start=2):
        key, value = field(fault, name, number, line)
        if key in fields:
            # A duplicate key is not a malformed line: every line parsed, and the
            # file still says two things. Which one a parser keeps is a property
            # of the parser, which is exactly why this refuses.
            raise fault("duplicate_key", name, f"{key} is stated twice")
        fields[key] = value
    return fields, "\n".join(lines[end + 1:]).strip()


def strings(
    fault: type[DocumentError], name: str, key: str, value: Any, pattern: re.Pattern[str]
) -> tuple[str, ...]:
    """A non-empty JSON array of distinct names in sorted order, or a refusal."""
    if not isinstance(value, list) or not value:
        raise fault("value_malformed", name, f"{key} is a non-empty JSON array")
    for item in value:
        if not isinstance(item, str) or not pattern.match(item):
            raise fault("value_malformed", name, f"{key} holds {item!r}, which is not a name")
    if len(set(value)) != len(value):
        raise fault("duplicate_entry", name, f"{key} names something twice")
    if list(value) != sorted(value):
        # Sorted, because a corpus is compared against database rows and against
        # itself. An unordered list is a diff that moves for no reason.
        raise fault("value_malformed", name, f"{key} is not in sorted order")
    return tuple(value)
