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
from pathlib import Path
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

#: What the interpreter writes beside Python it has compiled. Never part of a
#: corpus, and skipped by `entries` wherever a corpus is enumerated.
BYTECODE_DIR = "__pycache__"

#: A file inside a corpus item: a name and never a path -- no separator, no
#: parent, no leading dot. One pattern for every corpus, because a name that is
#: a path is refused for the same reason wherever it is declared.
FILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


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


def entries(directory: Path) -> list[Path]:
    """What a corpus directory really holds, in name order, minus compiled bytecode.

    Every corpus here refuses a file nothing declares, and the interpreter writes
    one into any directory holding Python it has compiled: installing the package
    byte-compiles the fixture applications and skill scripts it ships. Counting
    that as a stray would mean a corpus that loads from a checkout and refuses
    from an install, which is the one place it has to work.

    A *symlink* wearing the name is not skipped. The rule it would slip past is
    the one that keeps a link into the container's own credentials out of a
    corpus, and nothing needs a symlinked `__pycache__` to install.
    """
    return [
        entry
        for entry in sorted(directory.iterdir())
        if not (entry.name == BYTECODE_DIR and entry.is_dir() and not entry.is_symlink())
    ]


def strays(directory: Path, known: tuple[str, ...]) -> list[str]:
    """The names in `directory` that `known` does not account for, in name order.

    Every corpus asks this question of its own item directories and the names it
    reads are the only difference between the three askings, so the walk, the
    bytecode rule and the ordering live here and the names are the argument. The
    refusal itself stays with the corpus, because the code and the sentence it
    raises are that corpus's own.
    """
    return sorted(entry.name for entry in entries(directory) if entry.name not in known)


def directories(fault: type[DocumentError], root: Path, what: str) -> list[Path]:
    """The corpus directories under `root`, in name order, or the reason there are none.

    Every corpus here is one directory per item and nothing else at the top
    level, so a stray file is refused rather than skipped: a corpus that ignores
    what it does not recognise is a corpus where a misnamed document is missing
    rather than wrong.
    """
    if not root.is_dir():
        raise fault("corpus_missing", str(root), f"the installed package carries no {what}s")
    found = []
    for entry in entries(root):
        if not entry.is_dir() or entry.is_symlink():
            raise fault("stray_file", entry.name, f"the corpus holds {what} directories only")
        found.append(entry)
    if not found:
        raise fault("corpus_missing", str(root), f"a corpus with no {what} in it")
    return found


def resolved(fault: type[DocumentError], name: str, parent: Path, file_name: str) -> Path:
    """One file inside a corpus item, or the reason it is not one.

    Two rules, because they fail differently. The pattern refuses a name that is
    a path -- `../`, an absolute path, a separator -- before anything touches the
    filesystem. Resolution refuses a name that is not a path and reaches outside
    anyway, which on a filesystem means a symbolic link: a corpus file that is a
    link into the container's own credentials would pass every text rule either
    corpus has.
    """
    if not FILE_NAME.match(file_name):
        raise fault("path_escape", name, f"{file_name!r} is not a file name")
    candidate = parent / file_name
    if candidate.is_symlink():
        raise fault("path_escape", name, f"{file_name} is a symbolic link")
    if not candidate.is_file():
        raise fault("file_missing", name, f"{parent.name}/{file_name} is declared and absent")
    found = candidate.resolve()
    if not found.is_relative_to(parent.resolve()):
        raise fault("path_escape", name, f"{file_name} resolves outside {parent.name}/")
    return found


def listing(fault: type[DocumentError], name: str, directory: Path) -> tuple[str, ...]:
    """What a corpus item's file directory really holds, refusing anything odd.

    A directory that is not there is empty rather than wrong: every corpus here
    declares its files and a corpus item that declares none has nothing to hold
    them in. What is refused is a name in it that no declaration could reach --
    a symlink, a nested directory, a name that is a path.
    """
    if not directory.is_dir():
        return ()
    found = []
    for entry in entries(directory):
        if not entry.is_file() or entry.is_symlink():
            raise fault("stray_file", name, f"{directory.name}/{entry.name} is not a file")
        if not FILE_NAME.match(entry.name):
            raise fault("path_escape", name, f"{directory.name}/{entry.name} is not a file name")
        found.append(entry.name)
    return tuple(found)


def text(fault: type[DocumentError], name: str, file_name: str, source: bytes) -> str:
    """The bytes of a corpus document as characters, or why they are not one.

    Both refusals are about the second reader. A document that is not UTF-8 is
    one the CLI's own parse and this one would disagree about, and a carriage
    return is the one character that makes a line here and a line there differ
    without showing it in either.
    """
    try:
        decoded = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise fault("frontmatter_malformed", name, f"{file_name} is not UTF-8") from error
    if "\r" in decoded:
        raise fault("frontmatter_malformed", name, f"{file_name} carries a carriage return")
    return decoded


def line(fault: type[DocumentError], name: str, key: str, value: Any, limit: int) -> str:
    """One bounded line of prose, which is what a description or a provenance is."""
    if not isinstance(value, str) or not value.strip():
        raise fault("value_malformed", name, f"{key} is a non-empty line")
    if len(value) > limit:
        raise fault(
            "value_unbounded", name, f"{key} is {len(value)} characters, which is not one line"
        )
    return value


def one_of(fault: type[DocumentError], name: str, key: str, value: Any,
           allowed: tuple[str, ...]) -> str:
    """One value from a closed vocabulary the corpus states, not the database."""
    if not isinstance(value, str) or value not in allowed:
        raise fault("value_malformed", name, f"{key} is one of {list(allowed)}, not {value!r}")
    return value


def named(fault: type[DocumentError], name: str, key: str, value: Any,
          pattern: re.Pattern[str]) -> str:
    """One name, where the vocabulary it belongs to lives in the database."""
    if not isinstance(value, str) or not pattern.match(value):
        raise fault("value_malformed", name, f"{key} holds {value!r}, which is not a name")
    return value


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
