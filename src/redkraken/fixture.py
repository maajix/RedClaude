"""The fixture corpus: what a synthetic target contains, declared by whoever built it.

A fixture is the other half of a Playbook evaluation and it is deliberately not
written by the same hand. The Playbook declares what it looks for; the fixture
declares what it holds; and the pairing between them is computed by
`playbook_fixture_binding()` over those two declarations rather than stated by
either side. Ticket 25 gave the reason and ticket 46 keeps it: a Playbook that
could name the fixtures it is graded on is a Playbook whose test is the case it
passes.

Three things travel together in one directory and they are not the same kind of
thing.

* **`fixture.md`** is the ground truth: the Property classes this target
  contains, whether it has a secure twin, what surface it presents. It is a
  claim about the application, and `ground_truth_sha256` is its digest.
* **`app.py`** is the application, served twice from one source under a variant
  flag. `source_sha256` is its digest. This module never imports it -- a corpus
  compile reads and hashes, and the evaluator is the only thing that runs a
  fixture.
* The two digests are separate because they move separately, the same way a
  Playbook's document and projection do. Rewriting the ground truth changes how
  a result is scored without changing what was served; editing the application
  changes what was served without necessarily changing what it contains. A test
  result freezes both, so "was this the same target" and "was it graded the same
  way" are two questions with two answers.

What is *not* here is any statement about which Playbook this fixture tests.
There is no key for it and the parser refuses one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from redkraken import document
from redkraken.document import digest

#: The corpus, inside the package for the reason the Skill and Playbook corpora
#: are: `rk` evaluates what it was installed with.
CORPUS = Path(__file__).resolve().parent / "fixtures"

DOCUMENT = "fixture.md"
APPLICATION = "app.py"

#: What the catalogue calls this fixture, and `fixtures.id`'s pattern from 025.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: `property_classes.id`, restated where the corpus names one. Same pattern and
#: same reason as `playbook.CLASS`.
CLASS = re.compile(r"^[a-z_]+\.[a-z_]+$")

#: `surface_facts.id`, restated the same way.
FACT = re.compile(r"^[a-z][a-z0-9_]*$")

#: An Identity label the fixture issues sessions for. Spelled like a Program's
#: identity names so the evaluation configuration can carry it unchanged.
LABEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: The route the subject entity sits at. An origin-form path and nothing else:
#: a fixture that named a host would be naming where it is served, which is the
#: evaluator's to decide and changes every run.
SUBJECT = re.compile(r"^/[A-Za-z0-9._~/-]{0,255}$")

#: 025's `fixtures.kind`. `own_pair` is one source, one variant flag and two
#: ports; `third_party` has no secure twin and therefore no control.
KINDS = ("own_pair", "third_party")

DESCRIPTION_LIMIT = 1024
PROVENANCE_LIMIT = 1024

REQUIRED_KEYS = (
    "description",
    "bb:kind",
    "bb:classes",
    "bb:subject",
    "bb:facts",
    "bb:identities",
    "bb:provenance",
)

#: The coverage 036 requires of a third-party fixture and refuses on a pair. One
#: key holding both numbers rather than two keys holding one each, for two
#: reasons. The rule is "both or neither" -- a converted count without the list
#: it came from is a statement about our transcription rather than about coverage
#: -- and one key makes that structural instead of a check. And `document.field`
#: reads a bare scalar as text: an integer only arrives as an integer inside JSON,
#: which is how `bb:evidence`'s `min_count` is one.
OPTIONAL_KEYS = ("bb:coverage",)

COVERAGE_KEYS = ("upstream_list_size", "converted")

FORBIDDEN_KEYS: dict[str, str] = {
    "name": "identity is the directory name; a second one is a name that can drift from it",
    "bb:id": "same",
    "bb:version": "the version is a digest, so a declared one can be wrong",
    "bb:playbooks": "the binding is total and derived; a fixture that named its Playbooks would let one side choose the pairing",
    "bb:tests": "same, in the other direction",
    "bb:variants": "the variants are the application's, and `app.py` states them where they are served",
}


class FixtureError(document.DocumentError):
    """One reason the fixture corpus does not compile, by the code a test names."""


@dataclass(frozen=True, slots=True)
class Fixture:
    """One synthetic target: what it contains, what it presents, and its two digests.

    `classes` is the ground truth and it is the only statement anywhere about
    what this target holds. `playbook_fixture_binding()` intersects it with a
    Playbook's declared outputs to decide which side of that Playbook's test
    this fixture is on, so under-declaring here moves a fixture onto the `out`
    side and a Playbook that then fires on it fails -- which is the direction
    the mistake should push.
    """

    name: str
    kind: str
    #: Sorted, distinct Property classes this target contains.
    classes: tuple[str, ...]
    description: str
    #: The route the subject entity sits at, origin-form.
    subject: str
    #: The `surface_facts` the subject carries, which is what makes a Playbook's
    #: trigger stage able to fire on it at all.
    facts: tuple[str, ...]
    #: The Identity labels this fixture issues sessions for. Empty for a target
    #: that has no notion of a caller, which is a fact about it and not a gap.
    identities: tuple[str, ...]
    provenance: str
    upstream_list_size: int | None
    converted: int | None
    #: `app.py`'s bytes and their digest: what was served.
    source: bytes
    source_sha256: str
    #: `fixture.md`'s digest: how a run against it is scored.
    ground_truth_sha256: str

    @property
    def path(self) -> str:
        """`fixtures.path`: where a maintainer finds this fixture."""
        return f"fixtures/{self.name}/{DOCUMENT}"

    @property
    def application_path(self) -> str:
        return f"fixtures/{self.name}/{APPLICATION}"

    @property
    def paired(self) -> bool:
        """Whether a secure twin exists, which is whether a control is evaluable."""
        return self.kind == "own_pair"


def _count(name: str, key: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise FixtureError("value_malformed", name, f"{key} is a non-negative integer, not {value!r}")
    return value


def _labels(name: str, key: str, value: Any, pattern: re.Pattern[str]) -> tuple[str, ...]:
    """`document.strings`, admitting the empty list.

    A fixture with no Identity is not a fixture missing something -- `/search`
    has no caller to be -- so the empty case is a value here rather than a
    refusal. Everything else is the shared rule, and delegating rather than
    restating it is what keeps `[]` the only difference between them.
    """
    if isinstance(value, list) and not value:
        return ()
    return document.strings(FixtureError, name, key, value, pattern)


def _coverage(name: str, kind: str, fields: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """036's two `fixtures` coverage constraints, refused at compile instead.

    The constraints are in the database and this is the same rule read off the
    document, so a fixture that would be refused at INSERT is refused here with a
    message about the line that is wrong rather than about a constraint name.
    """
    declared = fields.get("bb:coverage")
    if kind == "own_pair":
        if declared is not None:
            raise FixtureError(
                "key_forbidden", name,
                "bb:coverage is a third-party coverage fraction; a pair converts nothing",
            )
        return None, None
    if declared is None:
        raise FixtureError(
            "key_missing", name,
            "a third-party fixture states bb:coverage: a converted count without "
            "the list it came from is a statement about our transcription",
        )
    if not isinstance(declared, dict) or sorted(declared) != sorted(COVERAGE_KEYS):
        raise FixtureError(
            "value_malformed", name,
            f"bb:coverage is a JSON object holding exactly {list(COVERAGE_KEYS)}",
        )
    size = _count(name, "bb:coverage.upstream_list_size", declared["upstream_list_size"])
    converted = _count(name, "bb:coverage.converted", declared["converted"])
    if size < 1:
        raise FixtureError("value_malformed", name, "bb:coverage.upstream_list_size is at least 1")
    if converted > size:
        raise FixtureError(
            "value_malformed", name,
            f"bb:coverage.converted is {converted} of an upstream list of {size}",
        )
    return size, converted


def _read(name: str, path: Path, what: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise FixtureError("file_missing", name, f"there is no {what}")
    return path.read_bytes()


def _fixture(directory: Path) -> Fixture:
    name = directory.name
    if not NAME.match(name):
        raise FixtureError("name_invalid", name, "a fixture is named the way its id is spelled")

    source = _read(name, directory / APPLICATION, APPLICATION)
    ground_truth = _read(name, directory / DOCUMENT, DOCUMENT)
    try:
        text = ground_truth.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FixtureError("frontmatter_malformed", name, f"{DOCUMENT} is not UTF-8") from error
    if "\r" in text:
        raise FixtureError("frontmatter_malformed", name, f"{DOCUMENT} carries a carriage return")

    fields, body = document.frontmatter(FixtureError, name, DOCUMENT, text)
    if not body:
        raise FixtureError("body_missing", name, "a fixture whose body is empty explains nothing")
    for key, reason in FORBIDDEN_KEYS.items():
        if key in fields:
            raise FixtureError("key_forbidden", name, f"{key}: {reason}")
    unknown = sorted(set(fields) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise FixtureError("key_unknown", name, f"nothing reads {unknown}")
    missing = sorted(set(REQUIRED_KEYS) - set(fields))
    if missing:
        raise FixtureError("key_missing", name, f"a fixture states {missing}")

    stray = document.strays(directory, (DOCUMENT, APPLICATION))
    if stray:
        raise FixtureError("stray_file", name, f"nothing reads {stray}")

    kind = document.one_of(FixtureError, name, "bb:kind", fields["bb:kind"], KINDS)
    size, converted = _coverage(name, kind, fields)

    return Fixture(
        name=name,
        kind=kind,
        classes=document.strings(FixtureError, name, "bb:classes", fields["bb:classes"], CLASS),
        description=document.line(
            FixtureError, name, "description", fields["description"], DESCRIPTION_LIMIT
        ),
        subject=document.named(FixtureError, name, "bb:subject", fields["bb:subject"], SUBJECT),
        facts=document.strings(FixtureError, name, "bb:facts", fields["bb:facts"], FACT),
        identities=_labels(name, "bb:identities", fields["bb:identities"], LABEL),
        provenance=document.line(
            FixtureError, name, "bb:provenance", fields["bb:provenance"], PROVENANCE_LIMIT
        ),
        upstream_list_size=size,
        converted=converted,
        source=source,
        source_sha256=digest(source),
        ground_truth_sha256=digest(ground_truth),
    )


def compile_corpus(root: Path = CORPUS) -> Mapping[str, Fixture]:
    """Parse every fixture under `root`, or refuse.

    Parameterised on the root so a test can compile a corpus it wrote rather
    than the installed one. Nothing in the running system passes an argument.
    """
    compiled: dict[str, Fixture] = {}
    for entry in document.directories(FixtureError, root, "fixture"):
        one = _fixture(entry)
        compiled[one.name] = one
    return MappingProxyType(compiled)


#: The compiled corpus, read-only, built at import so a bad corpus is never a
#: running one.
FIXTURES: Mapping[str, Fixture] = compile_corpus()
