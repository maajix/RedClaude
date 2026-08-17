"""Close the ledger: every v1 outcome landed, and the catalogue it landed in is whole.

`check_dispositions` asks one question of each of the 223 rows -- does this row
resolve? -- and it asks it row by row, which is why it can say nothing about the
shape of the answer. A ledger where every row resolves can still be a migration
that did not finish: forty-eight Playbooks where the plan said forty-nine, a
reference file sitting in a directory whose Playbook was deleted, a Skill nothing
loads, a catalogue entry whose registered digest is a text that no longer ships.
Each of those is a property of the whole, and none of them is visible from
inside a row.

So this is the second gate and it is deliberately arithmetic. The counts below
are the migration's own plan written down once, and the check is that the tree
agrees with it. They are constants rather than something derived, because a
number derived from the thing it is checking agrees with it by construction:
counting the Playbooks in the corpus and asserting the corpus has that many is
not a test, and "forty-nine" is a decision somebody took in the plan and has to
keep. What keeps the constants themselves honest is that they are spent against
a census frozen by somebody else: 49 rewritten plus 10 retired plus 1 absorbed
is the 60 Playbook topics `check_baseline` holds, and if any of the four numbers
moves alone the arithmetic stops closing.

It runs the row gate first and inherits its refusals, so an operator runs one
command. What it adds on top is six readings, one per closing criterion:

* the plan spends the census exactly, and the ledger covers it kind by kind;
* the in-scope Playbooks exist, are loadable by some role, and are registered in
  the schema at the exact text this checkout ships;
* the retirements split by kind, under a scope somebody registered a reversal
  for and wrote that split against;
* every in-scope reference and sink pack is attached to one document that
  declares it, and nothing sits in a `references/` directory unattached;
* no Skill is dangling and no Playbook is unloadable;
* and drift in any of these names the artifact, not the count.

Like the row gate it never opens a database and never writes. The half of
criterion 2 it therefore cannot answer is the evaluation half -- whether each
exact hash has a passing production evaluation -- which lives in
`playbook_test_verdict` and needs an Agent run against a fixture. That is ticket
78's, and this gate proves the precondition it rests on: the hash the database
grades is the hash of the file in the wheel.

Run it as a module -- `python3 -m tools.check_coverage` -- for the reason the row
gate is run that way: it reads the frozen census through the checker that owns
that format.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from redkraken import playbook, roster, skill

from tools import check_dispositions
from tools.check_baseline import BaselineError, CHECKOUT, EXPECTED_COUNTS, read_manifest
from tools.check_dispositions import LedgerError


#: Criterion 2. The v1 topics that earned a v2 Playbook rather than a retirement
#: or an absorption, and the number the migration tickets were written against.
IN_SCOPE_PLAYBOOKS = 49

#: Criterion 4, in two kinds because the census counts them separately: the
#: operator prose a Skill or Playbook now owns, and the sink packs beside it.
IN_SCOPE_REFERENCES = 73
SINK_PACKS = 9

#: Criterion 3's tail. One v1 topic survives as something to read rather than
#: something to run, so it is `absorbed` into a reference like the prose is.
ABSORBED_TOPICS = 1

#: Criterion 3, by scope and then by census kind. Retirement is per scope and the
#: split is what makes it auditable: "fifty-two artifacts retired" hides which
#: fifty-two, and the register's reversal is written against these four numbers
#: under this one name -- "the one Agent definition, two Skills, ten Playbook
#: topics and thirty-nine references are still in the frozen census". A scope
#: with no entry here retires nothing, however well the register describes it.
RETIRED_BY_SCOPE = {
    "android": {
        "agent_definition": 1,
        "skill_directory": 2,
        "playbook_topic": 10,
        "operator_reference": 39,
    },
}

#: A Playbook's registration in the schema corpus: the path literal and the
#: digest immediately after it, which is the shape every migration writes and the
#: only place the two appear adjacent. Narrow on purpose -- a corpus that stopped
#: matching would report the Playbook as unregistered, which is a refusal
#: somebody reads rather than a pass nobody notices.
REGISTRATION = re.compile(r"\('(playbooks/[a-z0-9-]+/playbook\.md)',\s*'([0-9a-f]{64})'")


class CoverageError(Exception):
    """A tree that does not close, as opposed to a ledger that does not read."""


@dataclass(frozen=True)
class Coverage:
    """Everything the readings need, gathered once.

    One object rather than six parameters threaded through six functions: the
    same six always travel together, and a reading that took a different five
    would be reading a different tree from the one beside it.
    """

    #: The ledger rows, and the census kind each row's source has.
    rows: list[dict[str, str]]
    kinds: dict[str, str]
    #: Every reference the corpus declares, mapped to the document declaring it.
    declared: dict[str, str]
    #: Every file actually sitting in a `references/` directory.
    present: frozenset[str]
    #: Every Playbook path the schema corpus registers, and the digest it froze.
    registered: dict[str, str]
    #: The retirement scopes the register carries, in the order it carries them.
    scopes: tuple[str, ...]

    def replacements(self, kind: str, disposition: str, namespace: str) -> list[str]:
        """The names one kind of artifact hands to one disposition, in row order."""
        return [
            name
            for row in self.rows
            if self.kinds[row["source"]] == kind and row["disposition"] == disposition
            for parsed in [check_dispositions.parse_replacement(row["replacement"])]
            if parsed and parsed.namespace == namespace
            for name in [parsed.name]
        ]

    def retired(self, scope: str) -> Counter[str]:
        """What one scope took, by census kind.

        Per scope rather than over every retirement, because a retirement is only
        as reversible as the scope it was taken under: two scopes sharing a total
        would each be accounted for by the other's reversal.
        """
        return Counter(
            self.kinds[row["source"]]
            for row in self.rows
            if row["disposition"] == "retired" and row["replacement"] == f"retired:{scope}"
        )


def registered_playbooks(schema: str) -> dict[str, str]:
    """Every Playbook the schema corpus registers, and the text it registered.

    Last write wins, because the corpus is concatenated in the order the
    migrations apply and every registration is an upsert. A Playbook re-frozen by
    a later ticket is therefore read at the digest the later ticket set, which is
    what the database would hold after applying both.
    """
    return {match.group(1): match.group(2) for match in REGISTRATION.finditer(schema)}


def declared_references() -> dict[str, str]:
    """Every reference the corpus declares, and the one document that declares it.

    Read from the compiled corpora rather than from the filesystem, which is the
    whole point: a file under `references/` is evidence that a file is there, and
    what criterion 4 asks is whether a document that exists *asks for* it. The
    two agreeing is checked separately and is where a deleted Playbook shows up.
    """
    attached = {
        f"skills/{name}/references/{reference}": f"skill {name}"
        for name, one in skill.SKILLS.items()
        for reference in one.references
    }
    attached.update({
        f"playbooks/{name}/references/{reference.name}": f"playbook {name}"
        for name, one in playbook.PLAYBOOKS.items()
        for reference in one.references
    })
    return attached


def plan_errors() -> list[str]:
    """Criterion 1's arithmetic: the plan spends each frozen kind exactly once.

    The one reading that holds the constants above to something they cannot
    agree with by construction. `EXPECTED_COUNTS` was frozen by the census
    ticket and the four numbers below were decided by the migration tickets, so
    an edit to either side that is not matched by the other stops the sum
    closing. Three kinds rather than six: the plan states a total for these, and
    what became of the eleven Agent definitions and twenty-eight Skill
    directories is a per-row question the ledger answers and no criterion counts.
    """
    taken: Counter[str] = Counter()
    for split in RETIRED_BY_SCOPE.values():
        taken.update(split)
    spent = {
        "playbook_topic": IN_SCOPE_PLAYBOOKS + ABSORBED_TOPICS + taken["playbook_topic"],
        "operator_reference": IN_SCOPE_REFERENCES + taken["operator_reference"],
        "sink_pack": SINK_PACKS + taken["sink_pack"],
    }
    return [
        f"the plan spends {total} of the census's {EXPECTED_COUNTS[kind]} {kind}"
        for kind, total in spent.items()
        if total != EXPECTED_COUNTS[kind]
    ]


def census_errors(coverage: Coverage) -> list[str]:
    """Criterion 1: the ledger covers the frozen census, kind by kind.

    The row gate forces this today -- it refuses a ledger whose sources are not
    the manifest's, in both directions and without duplicates, so the counts per
    kind cannot differ. It is asked again because that is a property of one other
    checker's implementation rather than of the ledger, and a kind going short is
    the failure this whole gate exists to name.
    """
    counted = Counter(coverage.kinds[row["source"]] for row in coverage.rows)
    return [
        f"{kind}: the ledger holds {counted[kind]} of the census's {expected}"
        for kind, expected in EXPECTED_COUNTS.items()
        if counted[kind] != expected
    ]


def catalogue_errors(coverage: Coverage) -> list[str]:
    """Criterion 2: the forty-nine exist, are loadable, and ship the text on record."""
    replaced = coverage.replacements("playbook_topic", "rewritten", "playbook")
    errors = []
    if len(set(replaced)) != IN_SCOPE_PLAYBOOKS:
        errors.append(
            f"the plan is {IN_SCOPE_PLAYBOOKS} in-scope Playbooks"
            f" and the ledger names {len(set(replaced))}"
        )
    errors.extend(
        f"in-scope Playbook {name} is not in the corpus"
        for name in sorted(set(replaced) - set(playbook.PLAYBOOKS))
    )

    # Loadability and registration are asked of the whole corpus rather than of
    # the forty-nine, because criterion 5 asks for zero unloadable stable
    # Playbooks and a v2-authored one is as capable of being unloadable as a
    # migrated one. Membership is asked of the forty-nine by name above, so a
    # replacement that is not there reads as a missing replacement rather than as
    # a corpus that is one short.
    for name, one in sorted(playbook.PLAYBOOKS.items()):
        if not roster.loadable(one):
            errors.append(f"{one.path}: no role loads {list(one.skills)} at once")
        frozen = coverage.registered.get(one.path)
        if frozen is None:
            errors.append(f"{one.path}: the schema corpus registers no such Playbook")
        elif frozen != one.sha256:
            # A registration is what an evaluation is graded against, and the
            # verdict is taken at the registered digest. A registration that has
            # drifted means the database would grade a text nobody ships, and
            # every promotion resting on it would be about the wrong document.
            errors.append(
                f"{one.path}: registered at {frozen[:12]} and ships {one.sha256[:12]}"
            )
    return errors


def retirement_errors(coverage: Coverage) -> list[str]:
    """Criterion 3: the split by kind, under a scope with a reversal on record."""
    errors = []
    for scope, expected_split in RETIRED_BY_SCOPE.items():
        counted = coverage.retired(scope)
        errors.extend(
            f"{scope}: {counted[kind]} of {kind} retired"
            f" where the register accounts for {expected}"
            for kind, expected in expected_split.items()
            if counted[kind] != expected
        )
        errors.extend(
            f"{scope}: {kind} may not be retired: nothing in the register accounts for it"
            for kind in sorted(set(counted) - set(expected_split))
        )

    # The row gate accepts a retirement under any scope the register carries.
    # This is the other half: a scope nobody wrote a split for is a scope whose
    # reversal names no artifacts, so what came back would be somebody's memory.
    planned = {f"retired:{scope}" for scope in RETIRED_BY_SCOPE}
    errors.extend(
        f"{row['source']}: retired under {row['replacement']},"
        " which the plan writes no split for"
        for row in sorted(coverage.rows, key=lambda row: row["source"])
        if row["disposition"] == "retired" and row["replacement"] not in planned
    )

    absorbed = coverage.replacements("playbook_topic", "absorbed", "reference")
    if len(absorbed) != ABSORBED_TOPICS:
        errors.append(
            f"the plan absorbs {ABSORBED_TOPICS} v1 topic as reference material"
            f" and the ledger absorbs {len(absorbed)}"
        )
    return errors


def reference_errors(coverage: Coverage) -> list[str]:
    """Criterion 4: every absorbed page is attached, and nothing is loose."""
    errors = []
    for kind, expected in (("operator_reference", IN_SCOPE_REFERENCES), ("sink_pack", SINK_PACKS)):
        absorbed = coverage.replacements(kind, "absorbed", "reference")
        if len(absorbed) != expected:
            errors.append(
                f"the plan absorbs {expected} of {kind} and the ledger absorbs {len(absorbed)}"
            )

    for row in sorted(coverage.rows, key=lambda row: row["source"]):
        replacement = check_dispositions.parse_replacement(row["replacement"])
        if not replacement or replacement.namespace != "reference":
            continue
        if replacement.name not in coverage.declared:
            # The row gate resolved this against the filesystem, so the file is
            # there. What is missing is a document asking for it, which is how a
            # reference outlives the Playbook it was written for: the directory
            # stays, the page stays, and nothing can reach it any more.
            errors.append(f"{row['source']}: {replacement.name} is attached to no document")

    errors.extend(
        # The other direction, and the one that would be an ambient load if
        # anything could perform one: a page in a `references/` directory that no
        # document declares is a page whose only possible reader is something
        # that opens the directory. The corpora refuse it at compile time; this
        # says so against the tree rather than against the compiler.
        f"{name}: sits in a references directory no document declares it from"
        for name in sorted(coverage.present - set(coverage.declared))
    )
    return errors


def skill_errors(coverage: Coverage) -> list[str]:
    """Criterion 5's remaining half: nothing in the corpus is dangling."""
    named = {name for one in playbook.PLAYBOOKS.values() for name in one.skills}
    granted = {name for role in roster.ROLES.values() for name in role.skills}
    return [
        *(
            f"skill {name}: no Playbook names it, so nothing can ever load it"
            for name in sorted(set(skill.SKILLS) - named)
        ),
        *(
            f"skill {name}: no role holds it"
            for name in sorted(set(skill.SKILLS) - granted)
        ),
    ]


def gather(ledger: Path, policy: dict) -> Coverage:
    """Read the ledger and the tree once, into the one object the readings share."""
    return Coverage(
        rows=check_dispositions.read_ledger(ledger),
        kinds={row["source"]: row["kind"] for row in read_manifest()},
        declared=declared_references(),
        present=check_dispositions.resolvable_names(CHECKOUT, policy)["reference"],
        registered=registered_playbooks(check_dispositions.schema_text(CHECKOUT)),
        scopes=tuple(entry["scope"] for entry in policy["retirements"]),
    )


def report(coverage: Coverage) -> str:
    """The counts, measured and in one fixed order, so two runs of it diff to nothing.

    Measured rather than printed from the constants above, even though the gate
    raised already if the two disagreed. A line that restates its own expectation
    reads the same whether or not anybody looked.
    """
    named = sorted(set(coverage.replacements("playbook_topic", "rewritten", "playbook")))
    shipped = [playbook.PLAYBOOKS[name] for name in named if name in playbook.PLAYBOOKS]
    attached = {
        kind: sum(
            1
            for name in coverage.replacements(kind, "absorbed", "reference")
            if name in coverage.declared
        )
        for kind in ("operator_reference", "sink_pack", "playbook_topic")
    }
    lines = [
        "v1 coverage",
        f"  {'in-scope playbooks':<22}{len(shipped):>4}"
        f"   loadable {sum(1 for one in shipped if roster.loadable(one))}"
        f"  frozen {sum(1 for one in shipped if coverage.registered.get(one.path) == one.sha256)}",
        f"  {'in-scope references':<22}{IN_SCOPE_REFERENCES:>4}"
        f"   attached {attached['operator_reference']}",
        f"  {'sink packs':<22}{SINK_PACKS:>4}   attached {attached['sink_pack']}",
        f"  {'absorbed topics':<22}{ABSORBED_TOPICS:>4}   attached {attached['playbook_topic']}",
    ]
    for scope in coverage.scopes:
        under = coverage.retired(scope)
        detail = "  ".join(f"{kind} {under[kind]}" for kind in EXPECTED_COUNTS if under[kind])
        lines.append(f"  {'retired: ' + scope:<22}{sum(under.values()):>4}   {detail}")
    lines.append(
        f"  {'catalogue':<22}{len(playbook.PLAYBOOKS):>4}"
        f"   skills {len(skill.SKILLS)}  references {len(coverage.declared)}"
    )
    lines.append(f"  {'census':<22}{len(coverage.rows):>4}   reconciled")
    return "\n".join(lines)


def check(
    ledger: Path = check_dispositions.LEDGER,
    policy_path: Path = check_dispositions.POLICY,
) -> str:
    """The closing gate. Returns the report, or raises with every reason it failed.

    The row gate runs first and its refusals are this gate's refusals, because a
    ledger that does not resolve has no shape worth measuring: a row pointing at
    a Playbook that is not there would be counted here as a Playbook that is.
    """
    check_dispositions.check(ledger=ledger, policy_path=policy_path)

    policy = check_dispositions.read_policy(policy_path)
    coverage = gather(ledger, policy)

    errors = [
        *plan_errors(),
        *census_errors(coverage),
        *catalogue_errors(coverage),
        *retirement_errors(coverage),
        *reference_errors(coverage),
        *skill_errors(coverage),
    ]
    if errors:
        raise CoverageError("\n".join(errors))
    return report(coverage)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        print(check())
    except (BaselineError, LedgerError, CoverageError, OSError) as error:
        print(f"coverage failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
