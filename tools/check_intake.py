"""Validate the intake ledger: one publicly disclosed technique per row.

Disclosed reports are where bypass shapes and parser differentials are written
down years before anybody's methodology catches up, and this corpus was migrated
from one operator's v1 knowledge rather than from the field. Reading them is
worth doing; keeping what was read as prose is not. A technique nobody can grade
is ambient authority wearing a different hat, so the unit of intake here is not
"a trick" but a row that resolves: to a Property class the selector can select
on, to an output that exists in this checkout, or to a stated reason why neither
is possible.

Four things a row can be, and the ledger is written so they read apart at a
glance:

* **produced** -- `fixture:`, `playbook:` or `skill:`, naming something on disk
  and carrying a review date, because knowledge that grades a live technique
  goes stale and the Playbook format already expires.
* **covered by** -- `covered_by:` naming what already grades this shape. A second
  fixture for a claim the corpus can already make adds rows to grade and no new
  question.
* **refused** -- `none:` with one of three reasons. A 2016 technique that every
  framework now blocks is worth a refused row, and that refusal is knowledge the
  next reader does not have to re-derive.
* **ungradeable** -- `ungradeable:` with the reason the harness cannot stage it.
  Filed rather than absorbed, because a technique nobody can grade is exactly
  what this ledger exists to keep out of the corpus.

Retrieval is not here and is not anywhere under `src/`. A maintainer reads a
page, records its digest, and restates the shape in their own words; what ships
is this file and the corpus. Nothing at run time fetches a writeup, so no
retrieval crosses the door, earns a Receipt or is attributed to a Program. The
digest is a record of what was read rather than a promise the page still says
it: a page that changed has a different digest and a row that needs re-reading,
which is what the review date is for.

Resolution reads the corpus and the migration text on disk and never opens a
database, for the reason the disposition checker gives: a ledger that asked a
live database which classes exist would answer differently on two machines.

Run it as a module -- `python3 -m tools.check_intake`.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

from redkraken import fixture, playbook, skill

from tools.check_baseline import BASELINE, CHECKOUT, BaselineError, read_table
from tools.check_dispositions import inserted_ids, schema_text


LEDGER = BASELINE / "technique-intake.tsv"

FIELDS = (
    "technique",
    "source_url",
    "published",
    "retrieved",
    "digest",
    "property_class",
    "produced",
    "review_by",
    "rationale",
)

#: The ticket whose fixtures this ledger accounts for. Named here because the
#: mirror rule needs it: a fixture written from a disclosure has to be claimed by
#: a row, or the corpus has grown by a file nobody can say where it came from.
INTAKE_TICKET = "ticket 79"

#: Where an accepted technique may land, and what resolves the name. The three
#: are the three forms knowledge takes in this repository -- a case that grades
#: it, a step that performs it, a reference an Agent may read -- and nothing else
#: is a landing place, least of all a document in `docs/`.
OUTPUTS = ("fixture", "playbook", "skill")

#: Why a technique produced nothing. `covered_by` is the fourth reason and is
#: spelled as its own namespace because it is the only one that names something:
#: "already covered" without saying by what is an assertion, not a resolution.
REFUSALS = {
    "target_specific": "one deployment's route names rather than a shape; that is recon",
    "unreproducible": "the outcome depends on the machine, so two readings disagree",
    "dead_technique": "the runtime the technique needed is gone; the refusal is the knowledge",
}

#: Why this harness cannot stage a technique at all. Each names a property of the
#: containment rather than an opinion about the technique: what a grade would
#: measure here is the door, the trust store or the harness's own listener.
UNGRADEABLE = {
    "normalised_by_the_door": "every reading crosses the proxy, which rewrites what it needs",
    "harness_owned": "the property belongs to the harness's transport, not to a target",
    "protocol_out_of_reach": "the door forwards nothing that could carry it to a target",
}

TECHNIQUE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,7}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
#: As precise as the source states and no more. An academy page carries no date,
#: an RFC carries a month, an advisory carries a day, and inventing the missing
#: digits would be the one part of the row that nobody could check.
PUBLISHED = re.compile(r"^(?:undated|[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?)$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
PRODUCED = re.compile(r"^([a-z_]+):(\S+)$")

#: What a restatement looks like from the outside. The floor refuses a row whose
#: rationale is a label, and the ceiling refuses one that is turning into a
#: transcript of somebody's report. Neither can tell a restatement from a quote;
#: what they enforce is that the row is the size of a claim, and review does the
#: rest.
RATIONALE = (120, 600)

NO_REVIEW = "-"


class IntakeError(Exception):
    """A ledger that cannot be read at all, as opposed to one that reads wrong."""


class Vocabulary(NamedTuple):
    """Everything a row resolves against, read once from this checkout.

    One value rather than four parameters because they are read together and
    make no sense apart: a row is checked against what the schema declares and
    what the package ships, and a check that had one without the others could
    only ever half-resolve a row.
    """

    classes: frozenset[str]
    events: frozenset[str]
    outputs: dict[str, frozenset[str]]
    makeability: dict[str, str]


class Produced(NamedTuple):
    """A produced value, split once so nobody splits it again by hand."""

    namespace: str
    name: str


def parse_produced(value: str) -> Produced | None:
    match = PRODUCED.match(value)
    return Produced(*match.groups()) if match else None


def read_ledger(path: Path = LEDGER) -> list[dict[str, str]]:
    """The rows, read the way the tables beside them are read, keyed by technique."""
    try:
        return read_table(path, FIELDS, "intake", key="technique")
    except BaselineError as error:
        raise IntakeError(str(error)) from error


def resolvable_names() -> dict[str, frozenset[str]]:
    """Every name an output may point at, read from the installed package.

    The corpus is the compiled one rather than a listing of directories, so a
    fixture that does not compile cannot be cited as one: an output that exists
    has to be an output that works. The same holds for the other two, which the
    package validates as it loads them.
    """
    return {
        "fixture": frozenset(fixture.FIXTURES),
        "playbook": frozenset(playbook.PLAYBOOKS),
        "skill": frozenset(skill.SKILLS),
    }


def makeability(schema: str) -> dict[str, str]:
    """Per Property class, what the transport register says a claim can rest on.

    Read for one rule: a class the schema records as `probe_only` or
    `unmakeable` cannot be graded by a fixture, because what the reading would
    land on is the interception proxy or the authority this harness issued
    rather than anything a target did. The register is the schema's own decision
    and this ledger defers to it instead of holding a second opinion beside it.
    """
    found: dict[str, str] = {}
    for block in re.finditer(
        r"INSERT INTO transport_makeability \([^)]*\) VALUES(.*?);\n", schema, re.DOTALL
    ):
        found.update(re.findall(r"\('([^']+)',\s*'([a-z_]+)'", block.group(1)))
    return found


def vocabulary(checkout: Path) -> Vocabulary:
    """What this checkout declares, as one value the row check reads."""
    schema = schema_text(checkout)
    return Vocabulary(
        classes=frozenset(inserted_ids(schema, "property_classes")),
        events=frozenset(inserted_ids(schema, "event_types")),
        outputs=resolvable_names(),
        makeability=makeability(schema),
    )


def source_error(url: str) -> str:
    """Why a source URL is not material published to be read, or empty.

    Three refusals, and each is one of criterion 4's boundaries made mechanical.
    A scheme that is not `https` is a page nobody can say they read unaltered.
    Userinfo in the authority is a credential this harness would then hold. A
    query string is how a gated resource is spelled -- a signed link, a session
    token, an export from a platform's API called with the operator's identity --
    and a public page that needs one is not the kind of source this ledger takes.
    """
    if not url.startswith("https://"):
        return "a source is retrieved over https"
    authority = url[len("https://"):].split("/", 1)[0]
    if not authority or "@" in authority:
        return "a source URL carries no credentials"
    if "?" in url or "#" in url:
        return "a source URL carries no query or fragment"
    return ""


def row_error(row: dict[str, str], words: Vocabulary) -> tuple[str, str]:
    """The first thing wrong with one row, and its state if nothing is.

    First rather than all, for the reason the disposition checker gives: a row
    whose output is not an output has nothing further that could be said about
    its review date.
    """
    technique = row["technique"]
    if not TECHNIQUE.match(technique):
        return f"{technique}: a technique is named in three to eight lowercase words", ""
    problem = source_error(row["source_url"])
    if problem:
        return f"{technique}: {problem}", ""
    if not PUBLISHED.match(row["published"]):
        return f"{technique}: published is a date as precise as the source states, or undated", ""
    if not DATE.match(row["retrieved"]):
        return f"{technique}: retrieved is an ISO date", ""
    if row["published"] != "undated" and row["published"] > row["retrieved"]:
        return f"{technique}: retrieved before it was published", ""
    if not DIGEST.match(row["digest"]):
        return f"{technique}: digest is sha256:<64 hex> of what was read", ""

    if row["property_class"] in words.events:
        # The two vocabularies look alike from a distance and are not alike at
        # all: an event kind is something the harness recorded happening, and a
        # Property class is something a target can be true of. Filing a technique
        # under the nearest-looking name is the failure this message exists for.
        return f"{technique}: {row['property_class']} is an event kind, not a Property class", ""
    if row["property_class"] not in words.classes:
        return (
            f"{technique}: {row['property_class']} is not a shipped Property class;"
            " a technique that fits none of them proposes a migration"
        ), ""

    produced = parse_produced(row["produced"])
    if not produced:
        return f"{technique}: {row['produced']!r} is not a namespaced outcome", ""
    if produced.namespace == "none":
        if produced.name not in REFUSALS:
            return f"{technique}: {produced.name} is not one of {sorted(REFUSALS)}", ""
        state = "refused"
    elif produced.namespace == "ungradeable":
        if produced.name not in UNGRADEABLE:
            return f"{technique}: {produced.name} is not one of {sorted(UNGRADEABLE)}", ""
        state = "ungradeable"
    else:
        cited = produced
        if produced.namespace == "covered_by":
            cited = parse_produced(produced.name)
            if not cited or cited.namespace not in OUTPUTS:
                return (
                    f"{technique}: covered_by names what covers it,"
                    f" one of {', '.join(OUTPUTS)}"
                ), ""
        elif produced.namespace not in OUTPUTS:
            return f"{technique}: {produced.namespace} is not an outcome namespace", ""
        if cited.name not in words.outputs[cited.namespace]:
            return f"{technique}: there is no {cited.namespace} {cited.name}", ""
        state = "produced" if produced.namespace in OUTPUTS else "covered"
        settled = words.makeability.get(row["property_class"], "")
        if produced.namespace == "fixture" and settled and settled != "agent_ok":
            # The schema settled this before the ledger existed, and it settled
            # it about the containment rather than about the technique. A
            # fixture here would be graded through the thing that makes the
            # claim unmakeable, so the row belongs under `ungradeable:`.
            return (
                f"{technique}: the schema records {row['property_class']} as {settled};"
                " a fixture cannot grade it"
            ), ""

    review = row["review_by"]
    if state == "produced":
        if not DATE.match(review):
            return f"{technique}: what grades a live technique carries a review date", ""
        if review <= row["retrieved"]:
            return f"{technique}: a review date falls after the retrieval", ""
    elif review != NO_REVIEW:
        return f"{technique}: nothing was produced, so there is nothing to review ({NO_REVIEW})", ""

    rationale = row["rationale"].strip()
    floor, ceiling = RATIONALE
    if not (floor <= len(rationale) <= ceiling):
        return (
            f"{technique}: a restatement is between {floor} and {ceiling} characters,"
            f" not {len(rationale)}"
        ), ""
    if "://" in rationale:
        # Provenance is the source column's job. A URL in the restatement is
        # either a second uncited source or somebody's target, and neither
        # belongs in a row that is meant to carry a shape.
        return f"{technique}: a restatement carries no URL; provenance is its own column", ""
    return "", state


def report(rows: list[dict[str, str]], states: dict[str, str]) -> str:
    """The counts, in one fixed order, so two runs of it diff to nothing."""
    counted = Counter(states.values())
    reasons = Counter(
        parse_produced(row["produced"]).name
        for row in rows
        if states.get(row["technique"]) in ("refused", "ungradeable")
    )
    lines = [
        "technique intake",
        f"  {'sources read':<24}{len({row['source_url'] for row in rows}):>4}",
        f"  {'rows':<24}{len(rows):>4}   "
        f"produced {counted['produced']}  covered {counted['covered']}  "
        f"refused {counted['refused']}  ungradeable {counted['ungradeable']}",
    ]
    for reason in sorted(REFUSALS) + sorted(UNGRADEABLE):
        if reasons[reason]:
            lines.append(f"  {reason:<24}{reasons[reason]:>4}")
    return "\n".join(lines)


def check(ledger: Path = LEDGER, checkout: Path = CHECKOUT) -> str:
    """The whole gate. Returns the report, or raises with every reason it failed."""
    rows = read_ledger(ledger)
    words = vocabulary(checkout)

    errors: list[str] = []
    states: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for row in sorted(rows, key=lambda row: row["technique"]):
        error, state = row_error(row, words)
        if error:
            errors.append(error)
            continue
        states[row["technique"]] = state
        if state != "produced":
            continue
        if row["produced"] in claimed:
            errors.append(
                f"{row['technique']}: duplicate coverage,"
                f" {claimed[row['produced']]} already produced {row['produced']}"
            )
        claimed.setdefault(row["produced"], row["technique"])

    # The other direction. A fixture written from a disclosure and not claimed by
    # a row is a file in the corpus with no provenance anybody can check, which
    # is the state this ledger exists to make impossible.
    for name, one in sorted(fixture.FIXTURES.items()):
        if INTAKE_TICKET in one.provenance and f"fixture:{name}" not in claimed:
            errors.append(f"no intake row produced fixture {name}, which cites {INTAKE_TICKET}")

    counted = Counter(states.values())
    if not counted["produced"]:
        errors.append("an intake that produced nothing has read nothing worth keeping")
    if not (counted["refused"] + counted["covered"] + counted["ungradeable"]):
        errors.append("an intake that never refuses anything is an intake that is not reading")
    if errors:
        raise IntakeError("\n".join(errors))
    return report(rows, states)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        print(check())
    except (BaselineError, IntakeError, OSError) as error:
        print(f"intake failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
