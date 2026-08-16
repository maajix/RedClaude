"""Validate that every frozen v1 artifact has exactly one resolved v2 outcome.

The census froze *what v1 was*: 223 artifacts, by identity and digest, with no
content. This is the other half -- *what happened to each one* -- and it is a
separate file for the same reason the census is content-free. A census is a
measurement and must not move when an opinion changes; a disposition is an
opinion and moves whenever the production tree does.

Every row resolves, and it resolves one of two ways. A **built** row names
something that exists in this checkout right now and cites the file that proves
it works. A **promised** row names something that does not exist yet and cites
the open migration ticket committed to building it; the moment that ticket is
marked resolved, this check fails until the thing is there. That is what keeps a
ledger from becoming a wish list: the rows come due on their own, without anyone
remembering to look.

What it therefore does not prove: that a cited ticket's own criteria mention the
artifact citing it. It proves the row names one of the registered migration
tickets and that the ticket is still open. Ticket 57 is the closing ticket and
asks for more than this -- that the Playbooks load, validate and have passing
evaluations -- so this is one of that ticket's gates, not a replacement for it.

Resolution reads the corpora and the migration text on disk and never opens a
database. A ledger that asked a live database which Property classes exist would
be grading the engagement it happens to be pointed at rather than the code, and
would answer differently on two machines. For the same reason nothing here
writes: the v1 corpus is an input to the census, and the census is an input to
this, so neither is touched by running it.

Run it as a module -- `python3 -m tools.check_dispositions` -- because it reads
the frozen census through the checker that already owns that format.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

from redkraken import playbook, roster, skill

from tools.check_baseline import (
    BASELINE,
    CHECKOUT,
    EXPECTED_COUNTS,
    BaselineError,
    read_manifest,
    read_table,
)


LEDGER = BASELINE / "v1-dispositions.tsv"
POLICY = BASELINE / "v1-dispositions.json"

#: The policy as a row cites it. A retirement's proof is the registered decision,
#: so it names this and nothing else may: a built row citing the register would
#: be offering the file that records intentions as evidence that something works.
REGISTER = POLICY.relative_to(CHECKOUT)

LEDGER_FIELDS = ("source", "sha256", "disposition", "replacement", "verification", "rationale")

#: What can have happened to a v1 artifact, and nothing else. The four are the
#: four criterion 4 asks the ledger to distinguish, and they are distinguished by
#: what survived rather than by how much work it was: what a thing could do, what
#: it knew, what it enforced, or nothing.
DISPOSITIONS = {
    "rewritten": "what it could do survives, written again as a role, Skill or Playbook",
    "absorbed": "what it knew survives as vocabulary or as a bounded reference",
    "superseded": "what it enforced survives as a runtime control, not as a document",
    "retired": "the scope does not survive, deliberately and reversibly",
}

#: Which dispositions a kind of artifact can honestly have. An operator
#: reference cannot be `rewritten`, because it was never something that ran -- it
#: was text somebody read. A reserved file cannot be `absorbed`, because an index
#: or a log is not knowledge, it is bookkeeping the runtime now does. Refusing
#: the impossible combinations is what stops the ledger from being filled in by
#: whichever word came to hand.
ALLOWED = {
    "agent_definition": ("rewritten", "retired"),
    "skill_directory": ("rewritten", "absorbed", "superseded", "retired"),
    "playbook_topic": ("rewritten", "absorbed", "retired"),
    "operator_reference": ("absorbed", "retired"),
    "sink_pack": ("absorbed", "retired"),
    "reserved": ("superseded", "retired"),
}

#: Which kinds of thing each disposition may point at. The namespace is not
#: decoration: `absorbed` may name vocabulary or a reference and may not name a
#: role, because "absorbed into a role" is how a v1 document quietly becomes an
#: Agent's ambient authority again, which is the shape this migration exists to
#: leave behind. `control` is criterion 2's own word for a runtime replacement.
NAMESPACES = {
    "rewritten": ("role", "skill", "playbook"),
    "absorbed": ("property_class", "vocabulary", "reference"),
    "superseded": ("control",),
    "retired": ("retired",),
}

#: Namespaces where two rows naming one target is duplicate coverage, and so the
#: complete list of what may *not* be shared. A Skill, a Playbook and a reference
#: file each replace one v1 artifact, so a second claim on one of them means a v1
#: artifact is being counted twice.
#:
#: The other five -- `role`, `control`, `property_class`, `vocabulary` and
#: `retired` -- are left out deliberately, because for each of them many-to-one
#: is the migration working rather than an accident. Five v1 web Agent
#: definitions collapse into one `role`; several v1 Skills that each described
#: the same enforcement collapse into the one `control` module that now performs
#: it; several references about one class of defect collapse into the one
#: `property_class` or `vocabulary` entry that names it; and every android
#: artifact shares the one `retired` scope, which is the point of registering a
#: scope at all.
EXCLUSIVE = ("skill", "playbook", "reference")

#: A reference attachment, as a path inside the installed package. Bounded by
#: construction: a reference lives under exactly one Skill or one Playbook, so
#: there is no way to spell "loaded for everybody", which is what v1 did.
REFERENCE = re.compile(r"^(?:skills|playbooks)/[a-z0-9-]+/references/[a-z0-9][a-z0-9.-]*\.md$")

TICKET = re.compile(r"^ticket:([0-9]{2,3})$")
REPLACEMENT = re.compile(r"^([a-z_]+):(\S+)$")


class LedgerError(Exception):
    """A ledger that cannot be read at all, as opposed to one that reads wrong."""


class Replacement(NamedTuple):
    """A replacement identifier, split once so nobody splits it again by hand."""

    namespace: str
    name: str


def parse_replacement(value: str) -> Replacement | None:
    match = REPLACEMENT.match(value)
    return Replacement(*match.groups()) if match else None


def read_policy(path: Path = POLICY) -> dict:
    """The closed vocabularies the rows draw on, and where the tickets live.

    The issue root is data rather than a constant in this file because the
    production boundary check reads every scanned source for references into the
    documentation tree and refuses them -- correctly, since a shipping module may
    not depend on prose. This module is a repository check, not shipped code, but
    it is scanned with the rest, and the registry pattern is the one the boundary
    checker already uses on itself for exactly this reason.
    """
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise LedgerError(f"invalid disposition policy: {error}") from error
    if policy.get("schema") != 1:
        raise LedgerError("disposition policy schema must be 1")

    issues = Path(policy.get("issue_root", ""))
    if not policy.get("issue_root") or issues.is_absolute() or ".." in issues.parts:
        raise LedgerError(f"unsafe issue root: {policy.get('issue_root')!r}")
    if not (CHECKOUT / issues).is_dir():
        raise LedgerError(f"issue root does not exist: {policy['issue_root']}")

    # Registered rather than "any number that is a ticket", so that a row cannot
    # be parked against whichever open issue happened to have a plausible number.
    # The set is the migration's own tickets, and it is small enough to read.
    tickets = policy.get("migration_tickets", [])
    if not tickets or any(not TICKET.match(f"ticket:{number}") for number in tickets):
        raise LedgerError("migration tickets must be present and numeric")

    scopes = policy.get("retirements", [])
    names = [entry.get("scope") for entry in scopes]
    if not names or len(names) != len(set(names)):
        raise LedgerError("retirement scopes must be present and unique")
    for entry in scopes:
        # Reversible means somebody wrote down what would bring it back. A
        # retirement with a reason and no reversal is a deletion with a note on
        # it, and the whole claim of this ledger is that nothing was deleted
        # without a decision anybody can revisit.
        if not entry.get("reason") or not entry.get("reversal"):
            raise LedgerError(f"retirement needs a reason and a reversal: {entry.get('scope')}")
    return policy


def read_ledger(path: Path = LEDGER) -> list[dict[str, str]]:
    """The rows, read the way the census beside them is read, or why they are unreadable."""
    try:
        return read_table(path, LEDGER_FIELDS, "disposition")
    except BaselineError as error:
        raise LedgerError(str(error)) from error


def inserted_ids(text: str, table: str) -> set[str]:
    """The first column of every row of every `INSERT INTO <table> ... VALUES` block.

    A regular expression over SQL rather than a connection to a database, because
    the schema corpus on disk is the definition and a database is only ever a
    copy of it. It is deliberately narrow -- `('` and then a quoted value -- and
    a corpus it stops recognising makes rows fail to resolve, which is a refusal
    somebody reads, not a pass nobody notices.
    """
    found: set[str] = set()
    for block in re.finditer(rf"INSERT INTO {table} \([^)]*\) VALUES(.*?);", text, re.DOTALL):
        found.update(re.findall(r"\('([^']+)'", block.group(1)))
    return found


def schema_text(checkout: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((checkout / "src" / "redkraken" / "migrations").glob("*.sql"))
    )


def resolvable_names(checkout: Path, policy: dict) -> dict[str, frozenset[str]]:
    """Every name a replacement is allowed to point at, read from this checkout.

    `control` is a module of the application, at module granularity, because that
    is the coarsest unit that is still a thing rather than a claim: "the scope
    policy" is `scope`, and either the file is there or the control is not. A
    finer identifier would name a function, and a function is renamed by any
    refactor, which would make the ledger fail for a reason it is not about.
    """
    schema = schema_text(checkout)
    package = checkout / "src" / "redkraken"
    return {
        "role": frozenset(roster.ROLES),
        "skill": frozenset(skill.SKILLS),
        "playbook": frozenset(playbook.PLAYBOOKS),
        "property_class": frozenset(
            inserted_ids(schema, "property_classes")
            | inserted_ids(schema, "property_class_families")
        ),
        # What the schema itself calls reference data, rather than a second list
        # of table names kept here: a vocabulary is exactly a table every Program
        # shares, and the schema registers those in one place already.
        "vocabulary": frozenset(inserted_ids(schema, "program_global_tables")),
        "reference": frozenset(
            path.relative_to(package).as_posix()
            for parent in ("skills", "playbooks")
            for path in (package / parent).glob("*/references/*")
            if path.is_file()
        ),
        "control": frozenset(
            path.stem for path in package.glob("*.py") if not path.stem.startswith("_")
        ),
        "retired": frozenset(entry["scope"] for entry in policy["retirements"]),
    }


def ticket_status(checkout: Path, issue_root: str, number: str) -> str | None:
    """What the tracker says about one ticket, or `None` if there is no such ticket."""
    matches = sorted((checkout / issue_root).glob(f"{number}-*.md"))
    if len(matches) != 1:
        return None
    for line in matches[0].read_text(encoding="utf-8").splitlines():
        stripped = line.strip().replace("**", "")
        if stripped.lower().startswith("status:"):
            return stripped.split(":", 1)[1].strip().lower()
    return ""


def row_error(
    row: dict[str, str],
    kind: str,
    names: dict[str, frozenset[str]],
    checkout: Path,
    policy: dict,
) -> tuple[str, str]:
    """The first thing wrong with one row, and the state it is in if nothing is.

    First rather than all, because the checks are ordered from the coarsest
    outwards: a row whose disposition is not a disposition has nothing further
    that could be said about its replacement, and reporting the rest would be
    reporting consequences of the one fault.
    """
    source = row["source"]
    disposition = row["disposition"]
    if disposition not in DISPOSITIONS:
        return f"{source}: unknown disposition {disposition!r}", ""
    if disposition not in ALLOWED[kind]:
        return f"{source}: a {kind} cannot be {disposition}", ""
    if not row["rationale"].strip():
        return f"{source}: no rationale", ""

    replacement = parse_replacement(row["replacement"])
    if not replacement:
        return f"{source}: {row['replacement']!r} is not a namespaced replacement", ""
    if replacement.namespace not in NAMESPACES[disposition]:
        return (
            f"{source}: {disposition} may name {' or '.join(NAMESPACES[disposition])},"
            f" not {replacement.namespace}"
        ), ""
    if replacement.namespace == "reference" and not REFERENCE.match(replacement.name):
        return f"{source}: {replacement.name!r} is not a bounded reference attachment", ""

    resolved = replacement.name in names[replacement.namespace]
    verification = row["verification"]
    if disposition == "retired":
        # A retirement resolves against the registry or not at all: there is no
        # ticket that will one day build a thing nobody is going to build. Its
        # proof is the registered decision, so it cites the register and nothing
        # else does -- a retirement pointing at a test would be citing something
        # that cannot be evidence for a deliberate absence.
        if not resolved:
            return f"{source}: retirement scope {replacement.name!r} is not registered", ""
        if Path(verification) != REGISTER:
            return f"{source}: a retirement is verified by the register, not {verification}", ""
        return "", "retired"

    ticket = TICKET.match(verification)
    if resolved:
        if ticket:
            return (
                f"{source}: {row['replacement']} exists,"
                f" so cite the proof rather than {verification}"
            ), ""
        if Path(verification) == REGISTER:
            return f"{source}: the register records retirements, it does not prove one exists", ""
        if not (checkout / verification).is_file():
            return f"{source}: verification {verification} is not a file", ""
        return "", "built"

    if not ticket:
        return f"{source}: missing replacement {row['replacement']}", ""
    if ticket.group(1) not in policy["migration_tickets"]:
        return f"{source}: {verification} is not one of the migration tickets", ""
    status = ticket_status(checkout, policy["issue_root"], ticket.group(1))
    if status is None:
        return f"{source}: {verification} is not a ticket", ""
    if not status:
        return f"{source}: {verification} has no status", ""
    if status == "resolved":
        return f"{source}: {verification} is resolved and {row['replacement']} is still missing", ""
    return "", "promised"


def report(rows: list[dict[str, str]], kinds: dict[str, str], states: dict[str, str]) -> str:
    """The counts, in one fixed order, so two runs of it diff to nothing."""
    lines = ["v1 dispositions"]
    for kind in EXPECTED_COUNTS:
        counted = Counter(
            row["disposition"] for row in rows if kinds.get(row["source"]) == kind
        )
        detail = "  ".join(
            f"{disposition} {counted[disposition]}"
            for disposition in DISPOSITIONS
            if counted[disposition]
        )
        lines.append(f"  {kind:<19}{sum(counted.values()):>4}   {detail}")
    totals = Counter(states.values())
    lines.append(
        f"  {'total':<19}{len(rows):>4}   "
        f"built {totals['built']}  promised {totals['promised']}  retired {totals['retired']}"
    )
    return "\n".join(lines)


def check(ledger: Path = LEDGER, policy_path: Path = POLICY) -> str:
    """The whole gate. Returns the report, or raises with every reason it failed.

    The census is not a parameter. It is the fixed point the whole check is
    against, and a run that could be pointed at a different one would be able to
    agree with itself about a v1 that never existed.
    """
    policy = read_policy(policy_path)
    rows = read_ledger(ledger)
    manifest = read_manifest()
    kinds = {row["source"]: row["kind"] for row in manifest}
    digests = {row["source"]: row["sha256"] for row in manifest}

    errors = [
        f"no disposition for v1 artifact: {source}"
        for source in sorted(set(kinds) - {row["source"] for row in rows})
    ]
    errors.extend(
        f"disposition for something the census does not hold: {source}"
        for source in sorted({row["source"] for row in rows} - set(kinds))
    )
    # Every later check indexes the manifest by a row's source, and the counts
    # reconcile because this equality holds and `read_manifest` has already held
    # the census to `EXPECTED_COUNTS`. Continuing past a mismatch would mean
    # reporting a total for a set nobody agrees on.
    if errors:
        raise LedgerError("\n".join(errors))

    names = resolvable_names(CHECKOUT, policy)
    claimed: dict[str, str] = {}
    retired_under: set[str] = set()
    states: dict[str, str] = {}
    for row in sorted(rows, key=lambda row: row["source"]):
        source = row["source"]
        if row["sha256"] != digests[source]:
            # The disposition was decided about a text. A different text is a
            # decision nobody has taken yet, however small the edit was.
            errors.append(f"{source}: disposition was taken against a stale source hash")
            continue
        error, state = row_error(row, kinds[source], names, CHECKOUT, policy)
        if error:
            errors.append(error)
        if not state:
            continue
        states[source] = state
        replacement = parse_replacement(row["replacement"])
        if state == "retired":
            retired_under.add(replacement.name)
        if replacement.namespace in EXCLUSIVE and row["replacement"] in claimed:
            errors.append(
                f"{source}: duplicate coverage, {claimed[row['replacement']]} already claims"
                f" {row['replacement']}"
            )
        claimed.setdefault(row["replacement"], source)

    # A scope nobody retires under is a decision that was taken and then not
    # applied, which reads in review as though something were retired for it.
    unused = sorted(names["retired"] - retired_under)
    if unused:
        errors.append("retirement scope nothing is retired under: " + ", ".join(unused))
    if errors:
        raise LedgerError("\n".join(errors))
    return report(rows, kinds, states)


def main(argv: list[str] | None = None) -> int:
    # A parser with no arguments still earns its place: it is what refuses one,
    # and what answers `--help` with the reasoning at the top of this file.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        print(check())
    except (BaselineError, LedgerError, OSError) as error:
        print(f"dispositions failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
