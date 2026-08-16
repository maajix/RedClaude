"""The Playbook corpus: an investigation strategy, and the projection a model gets.

A Playbook is knowledge -- how to ask one question about one kind of subject --
and a Skill is a technique the asking uses. The distinction is load-bearing here
because the two are versioned differently and the runtime does different things
with them: a Skill is compiled into the roster's authority and a Playbook is
*selected*, per subject, out of a catalogue nobody loads whole.

Three things are separate on purpose:

* **This module** decides whether a Playbook document is well-formed. It parses
  the frontmatter with the grammar in `document`, refuses metadata it cannot
  read, refuses a Playbook with no trigger, and builds the projection. It knows
  the spelling of a role and of a Skill and nothing else about either, which is
  why `roster` can import it.
* **`roster._check_playbooks`** decides whether the corpus fits the world the
  roles live in: every Skill a Playbook needs is a Skill that exists, and some
  role can load all of them at once. A Playbook no role can run is dead corpus,
  and dead corpus is worse than an absent Playbook because it looks like cover.
* **The database** decides which Playbook a given subject gets. Selection is
  `select_playbooks()` and it is SQL for the reason ticket 10 gave: the trigger
  stage is set containment over one view, and a per-row interpreter written in
  Python would be the same query with a network round trip in the middle.

**The projection is what the model receives, and it is not the document.** The
document carries provenance, a review date, a status and a list of maintainer
references; none of that helps a model hunt, and the references are written for
a person deciding whether the Playbook is still right. So `Projection` holds the
instructions, the classes the Playbook may claim, the Skills it needs and the
evidence it owes -- and there is no field on it that reference material could
occupy. That is the whole mechanism: not a filter that could be forgotten, but a
shape with nowhere to put the text.

**Two digests, because two things can change independently.** `sha256` is the
document, which is what `playbook_selections.playbook_sha256` freezes and what
ticket 25's test guard compares. `version` is the digest of the projection, which
is what the model actually read. Editing a maintainer reference moves neither;
editing the review date moves the first and not the second; editing the body
moves both. A Task records the pair, so "did the Agent see different text" has an
answer that is not "the file changed at some point".
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from redkraken import document, skill
from redkraken.document import ENTRY, digest

#: The corpus, inside the package for the reason the Skill corpus is: `rk` runs
#: what it was installed with, and a directory at the repository root ships in a
#: checkout and not in a wheel.
CORPUS = Path(__file__).resolve().parent / "playbooks"

DOCUMENT = "playbook.md"
REFERENCE_DIR = "references"

#: What the catalogue calls this Playbook. Every path this module records is
#: `PREFIX/<name>/...`, and `playbooks.path` refuses anything else.
PREFIX = "playbooks"

#: A Playbook's name, which is its directory's. Lower case with hyphens, so the
#: recorded path satisfies `playbooks.path`'s pattern without escaping.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: A file inside a Playbook: a name, never a path. Same rule and same reason as
#: the Skill corpus -- no separator, no parent, no leading dot.
FILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

#: `property_class_families.id` and `property_classes.id`, restated where the
#: corpus names them. Which families and classes exist is the database's
#: question and the foreign keys are what answer it; these refuse a string that
#: could not be either. 018 spells the class `^[a-z_]+\.[a-z_]+$` and this
#: matches it exactly: a looser pattern would accept a `bb:outputs` line the
#: catalogue then refuses, which moves a compile-time refusal to apply time.
FAMILY = re.compile(r"^[a-z_]+$")
CLASS = re.compile(r"^[a-z_]+\.[a-z_]+$")

#: `surface_facts.id` and `observation_kinds.id`, restated the same way.
FACT = re.compile(r"^[a-z][a-z0-9_]*$")
OBSERVATION_KIND = re.compile(r"^[a-z][a-z0-9_]*$")

#: `skills.name`, which is `skill.NAME`: a Playbook names a Skill the way the
#: Skill corpus does or it names nothing.
SKILL_NAME = skill.NAME

#: The four closed vocabularies `playbooks` carries as CHECK constraints, and
#: the two `playbook_evidence` does. Restated rather than imported because there
#: is nothing to import from: they are constraint text in a migration, and a
#: value outside them is a document that would fail at INSERT with a message
#: about a constraint instead of one about the line that is wrong.
RISKS = ("autonomous", "constrained", "approval_required", "forbidden")
EFFECTS = ("read_only", "mutates_session", "mutates_object", "mutates_account")
BASELINES = ("none", "stable_session", "pristine_surface")
STATUSES = ("draft", "stable", "deprecated")
TO_STATUSES = ("supported", "refuted", "inconclusive")
EVIDENCE_ROLES = ("baseline", "variant", "control", "context")
POLARITIES = ("supports", "refutes")

#: `playbooks_risk_matches_effects`, in the words the constraint uses. `bb:risk`
#: is a floor -- the least supervision this class of work can be run under --
#: and ticket 28 may raise it per call. What it may never be is lower than what
#: the Playbook admits it does, which is what this maps.
RISK_FLOOR: dict[str, tuple[str, ...]] = {
    "read_only": RISKS,
    "mutates_session": ("constrained", "approval_required", "forbidden"),
    "mutates_object": ("constrained", "approval_required", "forbidden"),
    "mutates_account": ("approval_required", "forbidden"),
}

#: A description is one line and it is a selection criterion, so it has a
#: ceiling. What is above the ceiling is not a description, it is the Playbook.
DESCRIPTION_LIMIT = 1024

#: Provenance is one line too, and for the opposite reason: it is not a citation
#: format, it is where a maintainer starts looking. The argument belongs in a
#: reference file, which is what those are for.
PROVENANCE_LIMIT = 1024

REQUIRED_KEYS = (
    "description",
    "bb:category",
    "bb:outputs",
    "bb:triggers_all",
    "bb:skills",
    "bb:risk",
    "bb:effects",
    "bb:baseline",
    "bb:status",
    "bb:stale_after",
    "bb:provenance",
    "bb:evidence",
)
OPTIONAL_KEYS = ("bb:triggers_any", "bb:references")

#: Keys no Playbook may state, each with the reason. Two of them are the
#: mistake ticket 10 removed from the Skill format and one is ticket 25's.
FORBIDDEN_KEYS: dict[str, str] = {
    "name": "identity is the directory name; a second one is a name that can drift from it",
    "bb:id": "same, and 12 of v1's 27 skills had already drifted on exactly this",
    "bb:version": "the version is the digest of the projection, so a declared one can be wrong",
    "bb:conflicts": "conflict is derived from baseline and effects; a declared list is O(n^2) and rots",
    "bb:composes_with": "same, in the other direction: composition is emergent and only conflict is computed",
    "bb:tested_against": "the fixture binding is total and derived, so an author cannot pick their own graders",
    "bb:promoted_at": "promotion is ticket 25's guard reading a test verdict, not a line in a document",
}


class PlaybookError(document.DocumentError):
    """One reason the Playbook corpus does not compile, by the code a test names."""


@dataclass(frozen=True, slots=True)
class Expectation:
    """One evidence row: what the runtime must already hold before a transition.

    Stricter than `transition_rules` and never looser -- the two are a
    conjunction, and there is no syntax here for declaring zero.
    """

    to_status: str
    role: str
    kind: str
    polarity: str | None
    min_count: int

    def row(self) -> dict[str, Any]:
        return {
            "to_status": self.to_status,
            "role": self.role,
            "kind": self.kind,
            "polarity": self.polarity,
            "min_count": self.min_count,
        }


@dataclass(frozen=True, slots=True)
class Reference:
    """One maintainer-only file: hashed so it can be found, never projected."""

    name: str
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Projection:
    """What a selected Playbook hands the model, and the whole of it.

    Every field is something a running Agent has to act on. What is missing is
    the point: no provenance, no review date, no status, no trigger facts, and
    no reference material. The runtime already decided this Playbook applies;
    handing over the reasons invites a model to relitigate them, and handing
    over the maintainer notes spends context on an argument aimed at a person.
    """

    path: str
    description: str
    property_classes: tuple[str, ...]
    skills: tuple[str, ...]
    risk: str
    effects: str
    baseline: str
    evidence: tuple[Expectation, ...]
    instructions: str

    def canonical(self) -> str:
        """One byte sequence per projection, so the digest is a fact about it."""
        return json.dumps(
            {
                "path": self.path,
                "description": self.description,
                "property_classes": list(self.property_classes),
                "skills": list(self.skills),
                "risk": self.risk,
                "effects": self.effects,
                "baseline": self.baseline,
                "evidence": [item.row() for item in self.evidence],
                "instructions": self.instructions,
            },
            sort_keys=True,
        )

    @property
    def sha256(self) -> str:
        return digest(self.canonical().encode("utf-8"))


@dataclass(frozen=True, slots=True)
class Playbook:
    """One compiled Playbook: the document, what selects it, and what it projects.

    The fields here are the ones the projection deliberately does not carry --
    what selects a Playbook, and what a maintainer reads. Everything the model
    is handed is read back through `projection`, so there is one copy of each
    value and no way for the two to disagree about what was compiled.
    """

    name: str
    category: str
    triggers_all: tuple[str, ...]
    triggers_any: tuple[str, ...]
    status: str
    stale_after: dt.date
    provenance: str
    references: tuple[Reference, ...]
    projection: Projection
    #: The exact bytes of `playbook.md`, kept as bytes so the digest and the
    #: thing digested are one object.
    source: bytes
    sha256: str

    @property
    def path(self) -> str:
        return self.projection.path

    @property
    def description(self) -> str:
        return self.projection.description

    @property
    def property_classes(self) -> tuple[str, ...]:
        """`playbook_outputs.property_class`: what this Playbook can conclude about."""
        return self.projection.property_classes

    @property
    def skills(self) -> tuple[str, ...]:
        return self.projection.skills

    @property
    def risk(self) -> str:
        return self.projection.risk

    @property
    def effects(self) -> str:
        return self.projection.effects

    @property
    def baseline(self) -> str:
        return self.projection.baseline

    @property
    def evidence(self) -> tuple[Expectation, ...]:
        return self.projection.evidence

    @property
    def version(self) -> str:
        """The digest of the projection, which is what the model actually read."""
        return self.projection.sha256

    @property
    def specificity(self) -> int:
        """`playbooks.specificity`: how many facts the subject must carry.

        The tie-break in `select_playbooks`, and derived rather than declared
        for the reason the version is: a number an author maintains is a number
        that stops matching the list beside it.
        """
        return len(self.triggers_all)


def _date(name: str, key: str, value: Any) -> dt.date:
    """A review date, as a date and not as a string that looks like one."""
    if not isinstance(value, str):
        raise PlaybookError("value_malformed", name, f"{key} is an ISO date")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise PlaybookError("value_malformed", name, f"{key}: {error}") from error


def _expectation(name: str, entry: Any) -> Expectation:
    if not isinstance(entry, dict):
        raise PlaybookError("value_malformed", name, "bb:evidence holds objects")
    unknown = sorted(set(entry) - {"to_status", "role", "kind", "polarity", "min_count"})
    if unknown:
        raise PlaybookError("value_malformed", name, f"an evidence row does not take {unknown}")
    for required in ("to_status", "role", "kind", "min_count"):
        if required not in entry:
            raise PlaybookError("value_malformed", name, f"an evidence row states {required}")
    kind = document.named(PlaybookError, name, "kind", entry["kind"], OBSERVATION_KIND)
    count = entry["min_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        # No syntax for zero, deliberately: `playbook_evidence` is a conjunction
        # with `transition_rules`, so a zero would read as permission to lower
        # the base minimum and would in fact do nothing at all.
        raise PlaybookError("value_malformed", name, f"min_count is a positive integer, not {count!r}")
    polarity = entry.get("polarity")
    if polarity is not None and (not isinstance(polarity, str) or polarity not in POLARITIES):
        raise PlaybookError("value_malformed", name, f"polarity is one of {list(POLARITIES)} or absent")
    return Expectation(
        to_status=document.one_of(PlaybookError, name, "to_status", entry["to_status"], TO_STATUSES),
        role=document.one_of(PlaybookError, name, "role", entry["role"], EVIDENCE_ROLES),
        kind=kind,
        polarity=polarity,
        min_count=count,
    )


def _evidence(name: str, value: Any) -> tuple[Expectation, ...]:
    if not isinstance(value, list) or not value:
        raise PlaybookError("value_malformed", name, "bb:evidence is a non-empty JSON array")
    rows = tuple(_expectation(name, entry) for entry in value)
    keys = [(row.to_status, row.role, row.kind) for row in rows]
    if len(set(keys)) != len(keys):
        # `playbook_evidence`'s primary key. Two rows on one key is a document
        # that states two minimums for one requirement, and which one survives
        # would be decided by insertion order.
        raise PlaybookError("duplicate_entry", name, "two evidence rows share (to_status, role, kind)")
    if keys != sorted(keys):
        raise PlaybookError("value_malformed", name, "bb:evidence is not in sorted order")
    # A Playbook that declares nothing for `supported` cannot make the claim it
    # exists to make, and `enforce_playbook_evidence` would have nothing to
    # enforce -- the criterion would then be met by a document that says less.
    if not any(row.to_status == "supported" for row in rows):
        raise PlaybookError(
            "evidence_missing", name, "bb:evidence states nothing for the supported transition"
        )
    return rows


def _resolved(name: str, parent: Path, file_name: str) -> Path:
    """One file inside a Playbook, or the reason it is not one.

    Two rules, because they fail differently. The pattern refuses a name that is
    a path before anything touches the filesystem; resolution refuses a name that
    is not a path and reaches outside anyway, which on a filesystem means a
    symbolic link.
    """
    if not FILE_NAME.match(file_name):
        raise PlaybookError("path_escape", name, f"{file_name!r} is not a file name")
    candidate = parent / file_name
    if candidate.is_symlink():
        raise PlaybookError("path_escape", name, f"{file_name} is a symbolic link")
    if not candidate.is_file():
        raise PlaybookError("file_missing", name, f"{parent.name}/{file_name} is declared and absent")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise PlaybookError("path_escape", name, f"{file_name} resolves outside {parent.name}/")
    return resolved


def _listing(name: str, directory: Path) -> tuple[str, ...]:
    """What is actually in `references/`, refusing anything odd."""
    if not directory.is_dir():
        return ()
    found = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or entry.is_symlink():
            raise PlaybookError("stray_file", name, f"{directory.name}/{entry.name} is not a file")
        if not FILE_NAME.match(entry.name):
            raise PlaybookError("path_escape", name, f"{directory.name}/{entry.name} is not a file name")
        found.append(entry.name)
    return tuple(found)


def _playbook(directory: Path) -> Playbook:
    name = directory.name
    if not NAME.match(name):
        raise PlaybookError("name_invalid", name, "a Playbook is named the way its path is spelled")

    source_path = directory / DOCUMENT
    if not source_path.is_file() or source_path.is_symlink():
        raise PlaybookError("file_missing", name, f"there is no {DOCUMENT}")
    source = source_path.read_bytes()
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PlaybookError("frontmatter_malformed", name, f"{DOCUMENT} is not UTF-8") from error
    if "\r" in text:
        raise PlaybookError("frontmatter_malformed", name, f"{DOCUMENT} carries a carriage return")

    fields, body = document.frontmatter(PlaybookError, name, DOCUMENT, text)
    if not body:
        raise PlaybookError("body_missing", name, "a Playbook whose body is empty asks nothing")
    for key, reason in FORBIDDEN_KEYS.items():
        if key in fields:
            raise PlaybookError("key_forbidden", name, f"{key}: {reason}")
    unknown = sorted(set(fields) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise PlaybookError("key_unknown", name, f"nothing reads {unknown}")
    missing = sorted(set(REQUIRED_KEYS) - set(fields))
    if missing:
        raise PlaybookError("key_missing", name, f"a Playbook states {missing}")

    stray = sorted(
        entry.name for entry in directory.iterdir() if entry.name not in (DOCUMENT, REFERENCE_DIR)
    )
    if stray:
        raise PlaybookError("stray_file", name, f"nothing reads {stray}")

    category = document.named(PlaybookError, name, "bb:category", fields["bb:category"], FAMILY)
    outputs = document.strings(PlaybookError, name, "bb:outputs", fields["bb:outputs"], CLASS)
    outside = sorted(one for one in outputs if not one.startswith(f"{category}."))
    if outside:
        # `check_playbook_integrity` reports this as corpus rot for a row written
        # by hand. A document that says it is about one family and claims classes
        # from another is refused outright: the category is what a reader filters
        # the catalogue by, and one that lies is worse than one that is absent.
        raise PlaybookError("category_mismatch", name, f"{outside} is not in the {category} family")

    triggers_all = document.strings(
        PlaybookError, name, "bb:triggers_all", fields["bb:triggers_all"], FACT
    )
    triggers_any = (
        document.strings(PlaybookError, name, "bb:triggers_any", fields["bb:triggers_any"], FACT)
        if "bb:triggers_any" in fields else ()
    )
    overlap = sorted(set(triggers_all) & set(triggers_any))
    if overlap:
        # An `any` fact that is already required is not a disjunction, it is a
        # second copy of a requirement -- and it makes the `any` arm of
        # `playbooks_by_trigger` unable to exclude anything.
        raise PlaybookError("duplicate_entry", name, f"{overlap} is required and also optional")

    risk = document.one_of(PlaybookError, name, "bb:risk", fields["bb:risk"], RISKS)
    effects = document.one_of(PlaybookError, name, "bb:effects", fields["bb:effects"], EFFECTS)
    if risk not in RISK_FLOOR[effects]:
        raise PlaybookError(
            "risk_understates_effects", name,
            f"a Playbook whose effects are {effects} cannot be run {risk}",
        )

    references = tuple(
        Reference(
            name=file_name,
            path=f"{PREFIX}/{name}/{REFERENCE_DIR}/{file_name}",
            sha256=digest(_resolved(name, directory / REFERENCE_DIR, file_name).read_bytes()),
        )
        for file_name in (
            document.strings(PlaybookError, name, "bb:references", fields["bb:references"], ENTRY)
            if "bb:references" in fields else ()
        )
    )
    undeclared = sorted(
        set(_listing(name, directory / REFERENCE_DIR)) - {one.name for one in references}
    )
    if undeclared:
        # Both directions, as the Skill corpus does. A declared file that is
        # absent is a link a maintainer cannot follow; a present file nothing
        # declares is material in the shipped package that no rule has read.
        raise PlaybookError("stray_file", name, f"{REFERENCE_DIR}/ carries undeclared {undeclared}")

    projection = Projection(
        path=f"{PREFIX}/{name}/{DOCUMENT}",
        description=document.line(
            PlaybookError, name, "description", fields["description"], DESCRIPTION_LIMIT
        ),
        property_classes=outputs,
        skills=document.strings(PlaybookError, name, "bb:skills", fields["bb:skills"], SKILL_NAME),
        risk=risk,
        effects=effects,
        baseline=document.one_of(PlaybookError, name, "bb:baseline", fields["bb:baseline"], BASELINES),
        evidence=_evidence(name, fields["bb:evidence"]),
        instructions=body,
    )

    return Playbook(
        name=name,
        category=category,
        triggers_all=triggers_all,
        triggers_any=triggers_any,
        status=document.one_of(PlaybookError, name, "bb:status", fields["bb:status"], STATUSES),
        stale_after=_date(name, "bb:stale_after", fields["bb:stale_after"]),
        provenance=document.line(
            PlaybookError, name, "bb:provenance", fields["bb:provenance"], PROVENANCE_LIMIT
        ),
        references=references,
        projection=projection,
        source=source,
        sha256=digest(source),
    )


def compile_corpus(root: Path = CORPUS) -> Mapping[str, Playbook]:
    """Parse every Playbook under `root`, or refuse.

    Parameterised on the root so a test can compile a corpus it wrote rather
    than the installed one. Nothing in the running system passes an argument.
    """
    compiled: dict[str, Playbook] = {}
    for entry in document.directories(PlaybookError, root, "Playbook"):
        one = _playbook(entry)
        compiled[one.name] = one
    return MappingProxyType(compiled)


#: The compiled corpus, read-only, built at import so a bad corpus is never a
#: running one. `roster._check_playbooks` is what holds it to the roster.
PLAYBOOKS: Mapping[str, Playbook] = compile_corpus()
