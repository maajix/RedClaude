"""The release audit: every requirement in the Spec, delivered and checked by something that can fail.

The other three gates each read one artifact. `check_baseline` reads the tree,
`check_dispositions` reads the ledger row by row and `check_coverage` reads the
shape of the migration those rows describe. None of them has ever read the Spec,
so the one claim nobody could make from inside this repository is the claim the
release turns on: that the two hundred and thirty numbered stories, the nineteen
Implementation Decisions, the twenty-four Testing Decisions, the nine
Out-of-Scope constraints, the six release conditions under Further Notes and the
seven registered prototype regressions were each built by somebody and are each
checked by something that would go red.

Coverage of a *plan* is what the ticket-coverage audit measures, and it is a
different and much weaker statement: a plan can cover a Spec perfectly and be
built not at all. The two are kept apart on purpose, and this file is the one
that is allowed to say "delivered". What makes that sayable is one table --
`baseline/spec-verification.tsv` -- with one row per requirement, and these
readings over it. It says *verification* rather than evidence because Evidence is
already a noun this domain owns: the role an observation plays for a claim. What
a row names is what would report a broken requirement, which is a different
thing, and the v1 ledger next to it already spells that column the same way:

* every requirement in the Spec has exactly one row -- one, so a requirement
  answered twice cannot hide its weaker answer behind its stronger -- and the row
  is frozen at the digest of the requirement's own text, so a story reworded
  after somebody mapped it stops matching and the release stops;
* every row names tickets that exist and are resolved, and verification that is
  a test this checkout can run or a gate this checkout ships -- there is no third
  kind, which is how "prose-only" is refused rather than warned about, and this
  gate is not allowed to be its own evidence. A case that holds no test is not a
  test this checkout can run: `unittest` loads it to an empty suite, and an empty
  suite passes for the same reason a document does;
* except that a requirement whose work is not finished may say so: `owed:NN`
  names the open ticket that owes the verification, in the same way a resolved
  ticket's unticked box names the open ticket that closes it. An owed row is a
  tracked absence rather than a claim, and the release outcome resolving while
  one is still there is itself a failure;
* every ticket from 01 to 63 is resolved, has no unresolved blocker, and names a
  revision git can resolve: the commit that turned its status into `resolved`;
  and every acceptance box it left unticked says which open ticket closes it, so
  a deferral is a tracked piece of work rather than a box somebody stopped
  looking at;
* the dependency graph is acyclic, every blocker exists, and every resolved
  ticket lies on a path to the release outcome -- a ticket nothing downstream
  names is work the release does not depend on, however green it is;
* and each of the eight areas the release is spoken of in holds requirements and
  reaches its anchors, with the one area that carries a number -- the forty-nine
  in-scope Playbooks -- checked against the catalogue gate that enforces it.

The last reading is the one with a history. Tickets 66 through 83 were raised
after the original plan froze, and each of them arrived as a sink beside ticket
65 rather than as something the release needs; that is the exact shape this
reading refuses, and the graph is now written so it holds.

Three things about what this gate does not do. It does not measure whether the
cited evidence is *good* -- a test that asserts nothing would satisfy it, and
only the code review the next ticket runs can catch that. By default it does not
run anything: the static pass proves the map resolves, and `--run` is what proves
the map passes, running the cited tests and then the cited gates, because a
citation that is skipped for want of a database or a container is not evidence of
anything either and is reported as such. And it is not one of the gates the
release gate runs inside its export: criterion 3 reads this repository's history
for the commit that resolved each ticket, and a tarball committed once as a
checkout would answer that question with one synthetic revision for every ticket
in the plan. This gate reads the tracker where the tracker actually happened.

Run it as a module -- `python3 -m tools.check_audit` -- like the other three, and
for the same reason: it reads the registry through the checker that owns it.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import subprocess
import sys
import unittest
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tools.check_baseline import BASELINE, CHECKOUT, BaselineError, read_status, read_table


#: The evidence map. In `baseline/` with the census and the ledger because it is
#: the same kind of file: a frozen table a repository check reads and no part of
#: the application ever opens.
MAP = BASELINE / "spec-verification.tsv"
FIELDS = ("source", "sha256", "area", "tickets", "verification")

#: The classified tree this Spec lives in. Named by slug and resolved through the
#: status registry rather than spelled as a path, because the registry is what
#: already declares where this specification is and refuses to describe a tree
#: that is not there -- and because production code may not name that root at all.
SPEC_SLUG = "production-harness-v2"
DOCUMENTATION = "documentation"
SPEC_FILE = "spec.md"
ISSUES = "issues"

#: What the Spec is required to hold. Constants rather than counts taken from the
#: file, for the reason the migration's numbers are constants: a total derived
#: from the document it is checking agrees with it however the document changes,
#: and "two hundred and thirty stories" is a decision somebody took.
STORIES = 230
DECISIONS = 19
TESTING = 24
OUT_OF_SCOPE = 9
NOTES = 6

#: Every top-level section the Spec holds. Frozen so that a section added later
#: is a section this audit refuses rather than one it never reads: four of these
#: state requirements, `Further Notes` states release conditions, and the first
#: two are the argument for all of them. A requirement nobody audits because it
#: arrived under a heading nobody parsed is the failure this list exists for.
#:
#: `Verify command` is the one entry that states no requirement. It holds the
#: command every ticket's bar is read against, and it is listed here rather than
#: nested under `Testing Decisions` so that a reader looking for it finds a
#: top-level heading (ticket 197).
SECTIONS = (
    "Problem Statement",
    "Solution",
    "User Stories",
    "Implementation Decisions",
    "Testing Decisions",
    "Verify command",
    "Out of Scope",
    "Further Notes",
)

#: Criterion 3's range, and the ticket every resolved ticket must reach. The
#: ticket that wrote this gate is inside the range rather than beside it: an
#: audit that exempts the work it was delivered by is an audit with one ticket
#: nobody reads, and it is the one whose author had the most reason to.
AUDITED = range(1, 64)
RELEASE_OUTCOME = 65

#: Criterion 6, spelled as the eight subsystems the ticket names. An area is a
#: column in the map, and each of these must hold at least one requirement whose
#: evidence reaches every anchor beside it. Anchors are what stop the column from
#: being a label: "the audit verifies Playbooks" is a sentence anybody can type,
#: and "some row in the playbooks area cites the catalogue gate" is not.
AREAS = {
    "runtime": ("tests.test_database",),
    "agents": ("tests.test_agent", "tests.test_roster"),
    "skills": ("tests.test_skill",),
    "playbooks": ("tests.test_playbook", "gate:tools.check_coverage"),
    "operator": ("tests.test_cli", "tests.test_ui"),
    "v1_import": ("tests.test_legacy", "gate:tools.check_dispositions"),
    "long_session": ("tests.test_capsule", "tests.test_database.CampaignRecoveryTest"),
    "first_hunt": ("gate:tools.release_gate",),
}

#: Criterion 6 names a number as well as a subsystem: "all 49 in-scope
#: Playbooks". The catalogue gate is what holds the forty-nine to their corpus,
#: so this audit names the number itself and refuses if that gate is planning a
#: different one -- read out of its source rather than imported, because
#: importing it would pull the application into a gate that reads files.
PLAYBOOKS = 49
CATALOGUE = "tools.check_coverage"
IN_SCOPE = re.compile(r"^IN_SCOPE_PLAYBOOKS = (\d+)$", re.MULTILINE)

#: The two prefixes a row may write instead of a test name, and the four things
#: one citation can turn out to be. `gate:` is a repository check this checkout
#: ships. `owed:` is the one honest way for a requirement to have no verification
#: yet: it names the open ticket that owes it, exactly as a deferred acceptance
#: box does, and the release outcome cannot be resolved while any row still says
#: it. A prefix is read once, in `citations`, and every reading after that
#: compares a kind rather than the string it was cut from.
GATE = "gate:"
OWED = "owed:"
TEST = "test"
PROSE = "prose"
TESTS = "tests"
TOOLS = "tools"

#: This gate cannot be evidence for a requirement: it is the thing reading the
#: row, and a check that reports its own map as proof of the map is a circle.
SELF = "tools.check_audit"

#: The one cited gate `--run` does not run. The release gate builds an install,
#: provisions two databases and runs the whole suite inside them; a mode meant to
#: prove the citations resolve does not get to take an hour, and the release gate
#: is the one citation whose own report is the release record anyway.
UNRUN = ("tools.release_gate",)

#: The one skip `--run` accepts, keyed on the suite's own words: a test that
#: requires the *absence* of the measured runtime this mode requires the presence
#: of. One interpreter cannot be both, and a suite that checks the unmeasured
#: path is right to say so. Every other stand-down proves nothing and is refused.
#: Matched whole rather than as a substring, because a reason that merely
#: contains this sentence is a reason any test could write to excuse itself.
MEASURED = re.compile(r"\S+ is installed, so this interpreter is a measured runtime")

#: How a ticket file states the two things this gate reads off it. Stricter than
#: `check_dispositions.ticket_status`, which reads the same field leniently for a
#: different question: a file the ledger's reader would accept and this one would
#: not is a file this gate refuses out loud rather than one the two of them
#: quietly disagree about.
STATUS = re.compile(r"^\*\*Status:\*\*\s*(.+?)\s*$", re.MULTILINE)
BLOCKED = re.compile(r"^\*\*Blocked by:\*\*\s*(.+?)\s*$", re.MULTILINE)
CRITERION = re.compile(r"^- \[( |x)\] (.+)$", re.MULTILINE)
RESOLVED = "resolved"

#: How a resolved ticket points an unticked criterion at the work that closes it.
#: Read as a marker rather than as any number in the line, because acceptance
#: criteria count things -- eight hashes, 223 rows, 49 Playbooks -- and a count is
#: not a ticket.
DEFERRAL = re.compile(r"[Tt]icket (\d+)")

#: The line whose appearance in a ticket's history is the revision that resolved
#: it. Searched for as a string rather than reconstructed from a message, because
#: a commit subject is prose and this is the fact the tracker actually records.
RESOLUTION = f"**Status:** {RESOLVED}"


class AuditError(Exception):
    """A Spec that is not delivered, as opposed to a tree that does not close."""


@dataclass(frozen=True)
class Ticket:
    """One issue file, read for the four things the graph and the audit ask of it."""

    number: int
    path: Path
    status: str
    blockers: tuple[int, ...]
    criteria: tuple[tuple[bool, str], ...]

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    @property
    def deferred(self) -> tuple[str, ...]:
        """The criteria this ticket was resolved without ticking."""
        return tuple(text for ticked, text in self.criteria if not ticked)


@dataclass(frozen=True)
class Citation:
    """One thing a row names as checking a requirement, read once.

    A citation is a test this checkout can run, a gate it ships, a ticket that
    owes the verification, or prose -- and prose is the kind that cannot fail,
    which is the whole reason the kind is decided here rather than at five call
    sites each cutting the same prefix off the same string.
    """

    kind: str
    #: What the citation names once its prefix is gone: a module path, a gate
    #: module, or the ticket numbers that owe it.
    name: str
    #: The token as the row wrote it, so a refusal can quote the row.
    text: str


@dataclass(frozen=True)
class Audit:
    """The Spec, the tracker and the map, gathered once and read together.

    One object rather than three arguments threaded through six readings: the
    registry and the tree it classifies travel with the requirements they were
    read out of, and a reading that took them separately could be handed a map
    from one checkout and a tracker from another.
    """

    #: The status registry the Spec and the tracker were read out of.
    status: dict
    #: Every requirement the Spec and the registry state, by key, at its own text.
    requirements: dict[str, str]
    #: Every ticket in the tracker, by number.
    tickets: dict[int, Ticket]
    #: The map's rows, in file order.
    rows: list[dict[str, str]]
    #: Every name this checkout can run, and every gate it ships.
    runnable: frozenset[str]
    gates: frozenset[str]

    def cited(self, source: str) -> tuple[int, ...]:
        """The tickets one row names, in row order."""
        for row in self.rows:
            if row["source"] == source:
                return ticket_numbers(row["tickets"])
        return ()

    @property
    def verification(self) -> list[Citation]:
        """Every citation the map makes, row by row and in the order it makes them."""
        return [citation for row in self.rows for citation in citations(row)]


def citations(row: dict[str, str]) -> list[Citation]:
    """What one row names as checking it, split and classified once."""
    read = []
    for token in (token.strip() for token in row["verification"].split(";")):
        if not token:
            continue
        if token.startswith(GATE):
            read.append(Citation(GATE, token[len(GATE):], token))
        elif token.startswith(OWED):
            read.append(Citation(OWED, token[len(OWED):], token))
        elif token.startswith(f"{TESTS}."):
            read.append(Citation(TEST, token, token))
        else:
            read.append(Citation(PROSE, token, token))
    return read


def spec_root(status: dict) -> Path:
    """The tree the status registry classifies as this Spec's documentation.

    Asked of the registry because the registry is already required to be honest
    about it: `read_status` refuses a classification whose path is not there, so
    a Spec that moved without the registry moving with it fails before this gate
    reads a word of it.
    """
    named = [
        entry["path"]
        for entry in status["classifications"]
        if entry["classification"] == DOCUMENTATION and Path(entry["path"]).name == SPEC_SLUG
    ]
    if len(named) != 1:
        raise AuditError(f"the status registry classifies {len(named)} trees as {SPEC_SLUG}")
    return CHECKOUT / named[0]


def bullets(lines: list[str]) -> list[str]:
    """The top-level bullets of one section, each with its continuation lines joined.

    A bullet is the unit the Spec writes a Testing Decision and an Out-of-Scope
    constraint in, and half of one is not a requirement: the digest has to be
    taken over everything the bullet says, or a constraint could lose its second
    sentence without the map noticing.
    """
    bullets: list[str] = []
    for line in lines:
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        elif bullets and line.startswith("  ") and line.strip():
            bullets[-1] += " " + line.strip()
    return bullets


def sections(text: str) -> dict[str, list[str]]:
    """The Spec's top-level headings, each with the lines under it."""
    found: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            found[current] = []
        elif current:
            found[current].append(line)
    return found


def read_spec(root: Path, status: dict) -> dict[str, str]:
    """Every requirement this release is measured against, by key, at its own text.

    Four of the five kinds are read out of the Spec. The fifth is not in the Spec
    at all: the known prototype regressions are frozen in the status registry,
    with the tickets each one requires, and reading them from there is what makes
    the two files one statement rather than two lists that happen to agree.
    """
    spec = (root / SPEC_FILE).read_text(encoding="utf-8")
    found = sections(spec)
    if set(found) != set(SECTIONS):
        raise AuditError(
            "the spec must hold exactly the audited sections; "
            f"missing {sorted(set(SECTIONS) - set(found))}, "
            f"unread {sorted(set(found) - set(SECTIONS))}"
        )

    requirements: dict[str, str] = {}

    #: A story is its number's line and every line that continues it, for the
    #: reason a bullet is: half a requirement is not one, and a story that grew a
    #: second sentence after somebody mapped it has to stop matching.
    stories: dict[int, list[str]] = {}
    for line in found["User Stories"]:
        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            stories[int(numbered.group(1))] = [numbered.group(2).strip()]
        elif stories and line.strip() and not line.startswith("#"):
            stories[next(reversed(stories))].append(line.strip())
    if list(stories) != list(range(1, STORIES + 1)):
        raise AuditError(f"the spec must hold user stories 1 through {STORIES}, numbered in order")
    requirements.update({f"story:{number:03d}": " ".join(body) for number, body in stories.items()})

    decisions: dict[str, list[str]] = {}
    for line in found["Implementation Decisions"]:
        heading = re.match(r"^###\s+(\d+)\.\s+(.*)$", line)
        if heading:
            decisions[f"decision:{int(heading.group(1)):02d}"] = [heading.group(2).strip()]
        elif decisions and line.strip():
            decisions[next(reversed(decisions))].append(line.strip())
    if len(decisions) != DECISIONS:
        raise AuditError(f"the spec must hold {DECISIONS} implementation decisions")
    requirements.update({key: " ".join(body) for key, body in decisions.items()})

    for section, prefix, expected in (
        ("Testing Decisions", "testing", TESTING),
        ("Out of Scope", "scope", OUT_OF_SCOPE),
        ("Further Notes", "note", NOTES),
    ):
        stated = bullets(found[section])
        if len(stated) != expected:
            raise AuditError(f"the spec must hold {expected} entries under {section}")
        requirements.update({
            f"{prefix}:{number:02d}": text for number, text in enumerate(stated, 1)
        })

    requirements.update({
        f"regression:{entry['id']}": entry["description"] for entry in status["regressions"]
    })
    return requirements


def ticket_numbers(value: str) -> tuple[int, ...]:
    """The ticket numbers one line names, in the order it names them.

    Leading numbers only, and per clause: a blocker line spells each edge as
    "NN -- title", and a title is free to hold a number of its own that means
    something else entirely.
    """
    numbers = []
    for clause in value.replace(";", ",").split(","):
        match = re.match(r"^\s*(\d+)\b", clause)
        if match:
            numbers.append(int(match.group(1)))
    return tuple(numbers)


def read_tickets(root: Path) -> dict[int, Ticket]:
    """Every issue file in the tracker, by number."""
    tickets: dict[int, Ticket] = {}
    for path in sorted((root / ISSUES).glob("*.md")):
        match = re.match(r"^(\d+)-", path.name)
        if not match:
            raise AuditError(f"a ticket file must start with its number: {path.name}")
        number = int(match.group(1))
        if number in tickets:
            raise AuditError(f"two ticket files are numbered {number:02d}")
        text = path.read_text(encoding="utf-8")
        status = STATUS.search(text)
        blocked = BLOCKED.search(text)
        if not status or not blocked:
            raise AuditError(f"ticket {number:02d} states no status or no blockers")
        tickets[number] = Ticket(
            number=number,
            path=path,
            status=status.group(1).strip(),
            blockers=ticket_numbers(blocked.group(1)),
            criteria=tuple(
                (match.group(1) == "x", match.group(2).strip())
                for match in CRITERION.finditer(text)
            ),
        )
    return tickets


def runnable_names(root: Path) -> frozenset[str]:
    """Every module, case and method under `tests/` that a citation may name.

    Read with `ast` rather than by importing, because a citation has to be
    resolvable without a database, a container or a network: importing the suite
    to find out whether a name exists would make the static half of this gate
    need the world the run half is careful to ask for explicitly.
    """
    names: set[str] = set()
    for path in sorted(root.glob("test_*.py")):
        module = f"{TESTS}.{path.stem}"
        names.add(module)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeError) as error:
            raise AuditError(f"cannot inspect the suite: {path.name}: {error}") from error
        cases = {
            node.name: {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name.startswith("test")
            }
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        bases = {
            node.name: [base.id for base in node.bases if isinstance(base, ast.Name)]
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        for name, tests in cases.items():
            # A class that holds no test, directly or from a base in its own
            # module, runs nothing: citing it would name something `unittest`
            # loads to an empty suite, which is a citation that cannot fail.
            inherited, seen = list(bases[name]), set()
            while inherited and not tests:
                base = inherited.pop()
                if base in seen or base not in cases:
                    continue
                seen.add(base)
                tests = cases[base]
                inherited.extend(bases[base])
            if not tests:
                continue
            names.add(f"{module}.{name}")
            names.update(f"{module}.{name}.{test}" for test in cases[name])
    return frozenset(names)


def gate_names(root: Path) -> frozenset[str]:
    """Every repository check a citation may name, by module."""
    return frozenset(
        f"{root.name}.{path.stem}"
        for path in sorted(root.glob("*.py"))
        if "def main(" in path.read_text(encoding="utf-8")
    )


def resolution(ticket: Ticket) -> str:
    """The revision that resolved one ticket, or the empty string if none did.

    The commit that added the resolved status line to that file, which is the
    thing the tracker actually records; a commit subject naming a ticket is prose
    and two of them can name the same one. `-S` reports every commit where the
    count of that string changed, and the first line of the log is the newest,
    which is the revision the current status came from.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(CHECKOUT),
            "log",
            "--format=%H",
            f"-S{RESOLUTION}",
            "--",
            str(ticket.path.relative_to(CHECKOUT)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AuditError(f"the tracker is not a readable git worktree: {result.stderr.strip()}")
    revisions = result.stdout.split()
    return revisions[0] if revisions else ""


def map_errors(audit: Audit) -> list[str]:
    """Criterion 1: one row per requirement, at the words the requirement states.

    Correspondence and nothing else. What a row cites is the next reading's
    business; this one answers whether the row is about a requirement the Spec
    still states, in the form it states it.
    """
    keys = [row["source"] for row in audit.rows]
    errors = [
        f"{key}: the spec states it and the map does not"
        for key in sorted(set(audit.requirements) - set(keys))
    ]
    errors.extend(
        f"{key}: the map claims a requirement the spec does not state"
        for key in sorted(set(keys) - set(audit.requirements))
    )
    # Criterion 5 names duplication release-blocking, and two rows for one
    # requirement is the shape it takes here: the second row is a second answer
    # to a question that has one, and whichever answer is weaker is invisible.
    errors.extend(
        f"{key}: the map states it {count} times"
        for key, count in sorted(Counter(keys).items())
        if count > 1
    )

    for row in audit.rows:
        source = row["source"]
        text = audit.requirements.get(source)
        if text is None:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if row["sha256"] != digest:
            # The requirement was edited after somebody mapped it. Whatever the
            # citation proves, it was chosen against different words.
            errors.append(
                f"{source}: mapped at {row['sha256'][:12]} and the spec now states {digest[:12]}"
            )
        if row["area"] not in AREAS:
            errors.append(f"{source}: {row['area']} is not one of the audited areas")
    return errors


def citation_errors(audit: Audit) -> list[str]:
    """Criteria 2 and 5: the tickets that built a requirement, and what checks it.

    One reading rather than two, because `owed:` couples them: a requirement
    whose verification is owed is a requirement whose work is unfinished, so the
    open ticket that owes it is exactly the ticket allowed to be named as
    implementing it. Split apart, each half would refuse what the other excuses.
    """
    errors: list[str] = []
    for row in audit.rows:
        source = row["source"]
        cited = citations(row)
        if not cited:
            # Criterion 5's testless requirement: something somebody believes is
            # built, with nothing that could report otherwise.
            errors.append(f"{source}: no test or gate checks it")

        owing = {
            number
            for citation in cited
            if citation.kind == OWED
            for number in ticket_numbers(citation.name)
        }
        built_by = ticket_numbers(row["tickets"])
        if not built_by:
            errors.append(f"{source}: no ticket implements it")
        errors.extend(
            f"{source}: names ticket {number:02d}, which the tracker does not hold"
            for number in built_by
            if number not in audit.tickets
        )
        errors.extend(
            f"{source}: ticket {number:02d} is {audit.tickets[number].status}, not {RESOLVED}"
            for number in built_by
            if number in audit.tickets and not audit.tickets[number].resolved
            and number not in owing
        )

        for citation in cited:
            if citation.kind == OWED:
                owed = ticket_numbers(citation.name)
                if not owed:
                    errors.append(f"{source}: {citation.text} names no ticket that owes it")
                errors.extend(
                    f"{source}: {citation.text} names a ticket the tracker does not hold"
                    for number in owed
                    if number not in audit.tickets
                )
                # The mirror of the deferral rule: work that is finished cannot
                # owe anything, so a resolved ticket here is a row whose evidence
                # somebody stopped looking for.
                errors.extend(
                    f"{source}: {citation.text} is owed by a ticket that is already {RESOLVED}"
                    for number in owed
                    if number in audit.tickets and audit.tickets[number].resolved
                )
            elif citation.kind == GATE:
                if citation.name == SELF:
                    errors.append(f"{source}: {citation.text} cannot be its own evidence")
                elif citation.name not in audit.gates:
                    errors.append(
                        f"{source}: {citation.text} is not a gate this checkout ships"
                    )
            elif citation.kind == TEST:
                if citation.name not in audit.runnable:
                    errors.append(
                        f"{source}: {citation.text} is not a test this checkout can run"
                    )
            else:
                # Criterion 5's prose-only requirement. A document, a heading or a
                # sentence cannot fail, so it cannot be evidence.
                errors.append(f"{source}: {citation.text} is neither a test nor a gate")
    return errors


def ticket_errors(audit: Audit) -> list[str]:
    """Criterion 3: every ticket in the audited range is done, and the revision says when."""
    errors = []
    for number in AUDITED:
        ticket = audit.tickets.get(number)
        if ticket is None:
            errors.append(f"ticket {number:02d}: the tracker holds no such ticket")
            continue
        if not ticket.resolved:
            errors.append(f"ticket {number:02d}: {ticket.status}, not {RESOLVED}")
            continue
        if not ticket.criteria:
            errors.append(f"ticket {number:02d}: resolved with no acceptance criteria")
        for criterion in ticket.deferred:
            # An unticked box on a resolved ticket is either an honest deferral or
            # an abandoned one, and the difference is whether somebody still owes
            # the work. A ticket that has itself been resolved cannot owe it.
            owed = [
                other
                for other in (int(found) for found in DEFERRAL.findall(criterion))
                if other in audit.tickets and not audit.tickets[other].resolved
            ]
            if not owed:
                errors.append(
                    f"ticket {number:02d}: unticked criterion names no open ticket:"
                    f" {criterion[:72]}"
                )
        errors.extend(
            f"ticket {number:02d}: blocked by {blocker:02d}, which is"
            f" {audit.tickets[blocker].status}"
            for blocker in ticket.blockers
            if blocker in audit.tickets and not audit.tickets[blocker].resolved
        )
        if not resolution(ticket):
            errors.append(f"ticket {number:02d}: no revision resolved it")
    return errors


def graph_errors(audit: Audit) -> list[str]:
    """Criterion 4: the blockers exist, the graph is acyclic, and the work ends somewhere."""
    errors = [
        f"ticket {ticket.number:02d}: blocked by {blocker:02d}, which does not exist"
        for ticket in audit.tickets.values()
        for blocker in ticket.blockers
        if blocker not in audit.tickets
    ]

    #: Depth-first, three-coloured, so the cycle is named rather than counted.
    state: dict[int, int] = {}
    cycles: list[str] = []

    def walk(number: int, path: list[int]) -> None:
        state[number] = 1
        for blocker in audit.tickets[number].blockers:
            if blocker not in audit.tickets:
                continue
            if state.get(blocker) == 1:
                cycle = path[path.index(blocker):] if blocker in path else [number]
                cycles.append(" -> ".join(f"{step:02d}" for step in [*cycle, blocker]))
            elif blocker not in state:
                walk(blocker, [*path, blocker])
        state[number] = 2

    for number in sorted(audit.tickets):
        if number not in state:
            walk(number, [number])
    errors.extend(f"the dependency graph holds a cycle: {cycle}" for cycle in sorted(set(cycles)))

    if RELEASE_OUTCOME not in audit.tickets:
        errors.append(f"the tracker holds no release outcome: ticket {RELEASE_OUTCOME}")
        return errors

    # Everything the release outcome rests on, transitively. Anything resolved
    # and outside it is finished work nothing downstream asks for, which is the
    # one way a green ticket can still not be part of a release.
    needed = {RELEASE_OUTCOME}
    frontier = [RELEASE_OUTCOME]
    while frontier:
        for blocker in audit.tickets[frontier.pop()].blockers:
            if blocker in audit.tickets and blocker not in needed:
                needed.add(blocker)
                frontier.append(blocker)
    errors.extend(
        f"ticket {ticket.number:02d}: resolved, and no path reaches"
        f" ticket {RELEASE_OUTCOME} from it"
        for ticket in sorted(audit.tickets.values(), key=lambda one: one.number)
        if ticket.resolved and ticket.number not in needed
    )
    return errors


def area_errors(audit: Audit) -> list[str]:
    """Criterion 6: each named subsystem holds requirements, and its anchors are cited."""
    errors = []
    by_area: dict[str, list[Citation]] = {area: [] for area in AREAS}
    for row in audit.rows:
        if row["area"] in by_area:
            by_area[row["area"]].extend(citations(row))
    for area, anchors in AREAS.items():
        if not by_area[area]:
            errors.append(f"{area}: the map covers no requirement in this area")
            continue
        errors.extend(
            f"{area}: no requirement in this area is checked by {anchor}"
            for anchor in anchors
            if not any(
                citation.text == anchor or citation.text.startswith(f"{anchor}.")
                for citation in by_area[area]
            )
        )
    return errors


def playbook_errors() -> list[str]:
    """Criterion 6's number: the catalogue gate still plans the forty-nine.

    The audit does not hold the corpus and is not going to import it. What it
    holds is the count the ticket names, against the gate that enforces it: a
    catalogue gate quietly re-planned to forty-eight would still pass every
    reading here, and the requirement that all forty-nine ship would have moved
    without this file noticing.
    """
    source = (CHECKOUT / f"{CATALOGUE.replace('.', '/')}.py").read_text(encoding="utf-8")
    planned = IN_SCOPE.search(source)
    if planned is None:
        return [f"{CATALOGUE} no longer states how many in-scope Playbooks it plans"]
    if int(planned.group(1)) != PLAYBOOKS:
        return [
            f"{CATALOGUE} plans {planned.group(1)} in-scope Playbooks"
            f" and this audit was written against {PLAYBOOKS}"
        ]
    return []


def release_errors(audit: Audit) -> list[str]:
    """Criterion 5's last word: nothing is still owed once the release is declared.

    An owed row is a requirement with no evidence and a ticket that says so. That
    is an honest state for a repository mid-plan and a dishonest one for a
    release, so the two are separated by the only event that means the release
    happened: ticket 65 resolving.
    """
    outcome = audit.tickets.get(RELEASE_OUTCOME)
    if outcome is None or not outcome.resolved:
        return []
    return [
        f"{row['source']}: still owed, and ticket {RELEASE_OUTCOME} is {RESOLVED}"
        for row in audit.rows
        if any(citation.kind == OWED for citation in citations(row))
    ]


def regression_errors(audit: Audit) -> list[str]:
    """Criterion 2's registered half: each regression is mapped to the tickets it requires."""
    errors = []
    for entry in audit.status["regressions"]:
        cited = set(audit.cited(f"regression:{entry['id']}"))
        absent = sorted(set(entry["required_tickets"]) - cited)
        errors.extend(
            f"regression:{entry['id']}: the registry requires ticket {number:02d}"
            f" and the map does not name it"
            for number in absent
        )
    return errors


def cited_tests(rows: list[dict[str, str]]) -> list[str]:
    """The cited tests, deduplicated and shortened to the broadest citation of each.

    A method cited beside its own case is the case, twice: `unittest` would load
    and run it under both names, and a suite that reports a test twice cannot be
    compared with the count of what was asked for.
    """
    names = {
        citation.name
        for row in rows
        for citation in citations(row)
        if citation.kind == TEST
    }
    return sorted(
        name
        for name in names
        if not any(other != name and name.startswith(f"{other}.") for other in names)
    )


def run_errors(names: list[str], stream=sys.stderr) -> tuple[list[str], str]:
    """Criterion 1's other half: the cited evidence is run, and it holds.

    A skip is a refusal here rather than a pass. Most of this suite's live arms
    stand down without a database or a container, and a citation that stood down
    proves exactly nothing about the requirement that cites it -- which is the
    difference between this and running the suite for a green exit code. The one
    exception is the inverse case, and it is the suite's own words that identify
    it: a test which requires the runtime to be absent cannot run in the
    interpreter this mode requires it to be present in.
    """
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=0, stream=stream).run(suite)
    inverted = [case for case, reason in result.skipped if MEASURED.fullmatch(reason)]
    errors = [f"{case}: failed" for case, _ in result.failures]
    errors.extend(f"{case}: errored" for case, _ in result.errors)
    errors.extend(
        f"{case}: skipped, so it proves nothing"
        for case, reason in result.skipped
        if not MEASURED.fullmatch(reason)
    )
    report = (
        f"  {'cited tests':<22}{len(names):>4}"
        f"   ran {result.testsRun}  failed {len(result.failures) + len(result.errors)}"
        f"  skipped {len(result.skipped) - len(inverted)}  unmeasurable {len(inverted)}"
    )
    return errors, report


def gate_errors(cited: list[Citation], stream=sys.stderr) -> tuple[list[str], str]:
    """The other half of what the map cites: the gates, run as the modules they are.

    As subprocesses, like an operator would, rather than by importing them: two
    of them import the application, one of them scans the tree, and none of them
    was written to be a library this gate calls. What they print is theirs; what
    this reads is the exit code.
    """
    modules = sorted({citation.name for citation in cited if citation.kind == GATE})
    run = [module for module in modules if module not in UNRUN]
    errors = []
    for module in run:
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=str(CHECKOUT),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(result.stdout + result.stderr, file=stream)
            errors.append(f"{GATE}{module}: exited {result.returncode}")
    report = (
        f"  {'cited gates':<22}{len(modules):>4}"
        f"   ran {len(run)}  failed {len(errors)}"
        f"  deferred {len(modules) - len(run)}"
    )
    return errors, report


def report(audit: Audit) -> str:
    """The counts, measured and in one fixed order, so two runs of it diff to nothing."""
    kinds = Counter(row["source"].split(":")[0] for row in audit.rows)
    areas = Counter(row["area"] for row in audit.rows)
    tests = {citation.name for citation in audit.verification if citation.kind == TEST}
    gates = {citation.name for citation in audit.verification if citation.kind == GATE}
    owed = {row["source"] for row in audit.rows
            if any(citation.kind == OWED for citation in citations(row))}
    resolved = sum(1 for ticket in audit.tickets.values() if ticket.resolved)
    deferred = sum(
        len(audit.tickets[number].deferred) for number in AUDITED if number in audit.tickets
    )
    lines = [
        "spec coverage",
        f"  {'stories':<22}{kinds['story']:>4}   decisions {kinds['decision']}"
        f"  testing {kinds['testing']}  scope {kinds['scope']}"
        f"  notes {kinds['note']}  regressions {kinds['regression']}",
        f"  {'verification':<22}{len(tests) + len(gates):>4}"
        f"   tests {len(tests)}  gates {len(gates)}  owed {len(owed)}",
        f"  {'tickets':<22}{len(audit.tickets):>4}"
        f"   resolved {resolved}  audited {len(AUDITED)}  deferred criteria {deferred}",
    ]
    lines.extend(
        f"  {'area: ' + area:<22}{areas[area]:>4}   anchors {len(AREAS[area])}"
        for area in AREAS
    )
    return "\n".join(lines)


def gather() -> Audit:
    """Read the registry, the Spec, the tracker and the map once."""
    status = read_status()
    root = spec_root(status)
    return Audit(
        status=status,
        requirements=read_spec(root, status),
        tickets=read_tickets(root),
        rows=read_table(MAP, FIELDS, "verification map"),
        runnable=runnable_names(CHECKOUT / TESTS),
        gates=gate_names(CHECKOUT / TOOLS),
    )


def check(run: bool = False) -> str:
    """The release audit. Returns the report, or raises with every reason it failed."""
    audit = gather()
    errors = [
        *map_errors(audit),
        *citation_errors(audit),
        *ticket_errors(audit),
        *graph_errors(audit),
        *area_errors(audit),
        *playbook_errors(),
        *release_errors(audit),
        *regression_errors(audit),
    ]
    lines = [report(audit)]
    if run and not errors:
        # After the static pass and only after it: names that do not resolve are
        # names `unittest` refuses to load, and the refusal it raises would be
        # this gate reporting an import error where it has a list of them.
        failures, measured = run_errors(cited_tests(audit.rows))
        errors.extend(failures)
        lines.append(measured)
        failures, measured = gate_errors(audit.verification)
        errors.extend(failures)
        lines.append(measured)
    if errors:
        raise AuditError("\n".join(errors))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="run every cited test and gate, refusing a failure, an error or a skip",
    )
    arguments = parser.parse_args(argv)
    try:
        print(check(run=arguments.run))
    except (AuditError, BaselineError, OSError) as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
