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

The corpus ledger beside it is graded by the same run. It is the other half of
the same idea at a different scale: one record per technique a Playbook step
performs, written from what the operator already had rather than from a
disclosure, and its sources in their own table because a record cites one page
many times and a digest recorded once per citation is a digest that disagrees
with itself.

Run it as a module -- `python3 -m tools.check_intake`.
"""

from __future__ import annotations

import argparse
import json
import re
import hashlib
import sys
from datetime import date, datetime
from collections import Counter
from pathlib import Path
from typing import NamedTuple

from redkraken import fixture, playbook, roster, skill

from tools.check_baseline import BASELINE, CHECKOUT, BaselineError, read_table
from tools.check_dispositions import (
    inserted_ids,
    inserted_pairs,
    parse_replacement,
    schema_text,
)


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
CITES = re.compile(rf"\b{INTAKE_TICKET}\b")

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
#: The digest of the bytes the source served, exactly as they arrived and before
#: anything rendered them, so a second reader can recompute it from one fetch.
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
#: As precise as the source states and no more. An academy page carries no date,
#: an RFC carries a month, an advisory carries a day, and inventing the missing
#: digits would be the one part of the row that nobody could check.
PUBLISHED = re.compile(r"^(?:undated|[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?)$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
#: What a restatement looks like from the outside. The floor refuses a row whose
#: rationale is a label, and the ceiling refuses one that is turning into a
#: transcript of somebody's report. Neither can tell a restatement from a quote;
#: what they enforce is that the row is the size of a claim, and review does the
#: rest.
RATIONALE = (120, 600)

NO_REVIEW = "-"

TECHNIQUES = BASELINE / "technique-ledger.jsonl"
SOURCES = BASELINE / "technique-sources.tsv"

#: What every record carries. `id` first because it is what the sources table
#: points at; the rest in the order the mining stage wrote them, so a record
#: reads down the page the way it was filled in.
RECORD_FIELDS = (
    "id",
    "playbook",
    "technique",
    "local_sources",
    "external_sources",
    "preconditions",
    "baseline",
    "variant",
    "control",
    "payload_family",
    "required_skill",
    "runtime_writer",
    "supported_evidence",
    "refuted_evidence",
    "stop_conditions",
    "capability_state",
    "owner_ticket",
    "okf_concept",
    "okf_source_ids",
    "okf_trust_tier",
    "okf_stale_after",
    "mined_from",
    "notes",
    "finding_path",
)

#: The twenty-fifth field, on the records whose finding path needed saying in
#: prose. Absent rather than empty on the rest, because a key that is not there
#: reads as not asked and a key that is empty reads as asked and answered with
#: nothing.
RECORD_NOTE = "finding_path_note"

SOURCE_FIELDS = (
    "id",
    "ledger_id",
    "kind",
    "url",
    "title",
    "version_note",
    "retrieved",
    "digest",
    "note",
)

#: The four fields a record holds as a list. Everything else it carries is a
#: string, and the only two that may be empty are the two that mean something
#: by being empty: a technique the shipped Skills do not cover, and a record
#: no ticket has claimed.
RECORD_LISTS = ("local_sources", "external_sources", "mined_from", "okf_source_ids")

#: What a record keeps about an external source, beside the address. The sources
#: table holds the same three, and the join below checks all three rather than
#: only the address: two files that carry one fact and are never compared are
#: two facts waiting to disagree.
EXTERNAL_PARTS = ("url", "title", "date_or_version")
MAY_BE_EMPTY = ("required_skill", "owner_ticket")

#: A page anybody can fetch, a file one operator had, or a shape the mining
#: stage went looking for and found nobody had published. The third is a kind
#: rather than an external source with an empty address, because "nobody has
#: written this down" is a reading and an unfetchable address is a fault; the
#: gate has to be able to tell them apart.
ABSENT = "absent"
SOURCE_KINDS = ("local", "external", ABSENT)

#: Where a technique's evidence lands, and what the harness can therefore do
#: with it. The two are one statement read from opposite ends -- what this
#: reading reached, and what the harness can reach -- so a record whose halves
#: disagree has been edited on one side only.
CAPABILITY = {
    "reaches": "reachable",
    "observation_only": "reachable",
    "blocked": "blocked",
    "refused": "refused",
    "out_of_scope": "out_of_scope",
}
FINDING_PATHS = tuple(CAPABILITY)

#: `<playbook>/<NN>`, numbered within the playbook. An ordinal rather than a
#: slug off the technique, because the technique is a sentence this corpus
#: rewrites, and an identifier that moved when a sentence was reworded would not
#: be an identifier.
RECORD_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[0-9]{2}\Z")
SOURCE_ID = re.compile(r"^S[0-9]{4}\Z")

#: How many records the reviewed corpus holds. Pinned because the run of
#: ordinals cannot see a tail cut -- a file with the last record of every
#: Playbook removed is still numbered from one with no gap -- and because
#: coverage cannot either: one record per Playbook still covers all fifty-one.
RECORDS = 382

#: The floor under a field that is meant to be a restatement. It is far below
#: what the corpus actually holds -- the shortest technique is fifty-six
#: characters and the shortest arm thirty-two -- because what it is for is the
#: placeholder, not the terse entry: `x`, `TBD` and `-` are what a half-written
#: record looks like, and each of them is a field that reads as filled in.
PROSE = 24

#: The floor under a field that is only ever a phrase: a payload family, a trust
#: tier, the writer that records the result. Lower than `PROSE` because these
#: are names rather than restatements -- `unverified` is ten characters -- and a
#: field saying there is nothing to name is allowed to be shorter still, which
#: is what `UNRUNNABLE` is for.
PHRASE = 10
PHRASED = (
    "preconditions",
    "payload_family",
    "runtime_writer",
    "supported_evidence",
    "refuted_evidence",
    "stop_conditions",
    "okf_concept",
    "okf_trust_tier",
    "notes",
)

#: What a record calls the concept it was filed under while it was being mined.
#: Its own namespace and not a key into the sources table: `wstg-idnt-04` is a
#: name OWASP gave a test, and the row this corpus holds for the page that
#: describes it is a different thing with a different id.
CONCEPT = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*(?:--[a-z0-9]+(?:[-.][a-z0-9]+)*)*\Z")

#: What an arm says when there was nothing to run. Allowed on a record the
#: harness cannot take to a Finding, and refused on one that reaches: three arms
#: are what make a reading a Test rather than one send and an opinion, and a
#: two-armed form cannot tell the target's behaviour from the reading's own.
UNRUNNABLE = re.compile(
    r"(?i)^(?:none|n/?a|null|not (?:applicable|runnable|executed|expressible|sendable))\b"
)

#: One operator's account, wherever it was written from. The check is a whole
#: list rather than one prefix because a corpus mined on a second machine would
#: leak a different one, and a rule that only knew this machine's would pass it.
HOME = re.compile(r"/home/|/Users/|/root/|[A-Za-z]:\\Users\\")

#: The tool a halt tells the operator through, and the words it may file that
#: halt under. Read off the served enum rather than restated here, so that a
#: record is graded against the vocabulary the model is actually offered:
#: `park_task_for_human` refuses a code that is not a row, and a record naming
#: one the enum lost would be a step no run can perform.
PARK = roster.PARK_FOR_HUMAN
QUESTION_CODES = (
    roster.CONTRACTS[PARK].arguments["question_code"].enum
)


class IntakeError(Exception):
    """A ledger that cannot be read at all, as opposed to one that reads wrong."""


class Vocabulary(NamedTuple):
    """Everything a row resolves against, read once.

    One value rather than four parameters because they are read together and
    make no sense apart: a row is checked against what the schema declares and
    what the package ships, and a check that had one without the others could
    only ever half-resolve a row. The first three come off the schema corpus on
    disk; `outputs` comes off the installed package, because an output that
    exists has to be one that loads.
    """

    classes: frozenset[str]
    events: frozenset[str]
    outputs: dict[str, frozenset[str]]
    makeability: dict[str, str]


def read_ledger(path: Path = LEDGER) -> list[dict[str, str]]:
    """The rows, read the way the tables beside them are read, keyed by technique."""
    try:
        return read_table(path, FIELDS, "intake", key="technique")
    except BaselineError as error:
        raise IntakeError(str(error)) from error


def outputs_on_disk() -> dict[str, frozenset[str]]:
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


def vocabulary(checkout: Path) -> Vocabulary:
    """What this checkout declares, as one value the row check reads.

    `makeability` is the transport register, read for one rule: a class the
    schema records as `probe_only` or `unmakeable` cannot be graded by a fixture,
    because what the reading would land on is the interception proxy or the
    authority this harness issued rather than anything a target did. The register
    is the schema's own decision and this ledger defers to it instead of holding
    a second opinion beside it.
    """
    schema = schema_text(checkout)
    return Vocabulary(
        classes=frozenset(inserted_ids(schema, "property_classes")),
        events=frozenset(inserted_ids(schema, "event_types")),
        outputs=outputs_on_disk(),
        makeability=inserted_pairs(schema, "transport_makeability"),
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

    produced = parse_replacement(row["produced"])
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
            cited = parse_replacement(produced.name)
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
        if cited.namespace == "fixture" and settled and settled != "agent_ok":
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
        parse_replacement(row["produced"]).name
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
        if CITES.search(one.provenance) and f"fixture:{name}" not in claimed:
            errors.append(f"no intake row produced fixture {name}, which cites {INTAKE_TICKET}")

    counted = Counter(states.values())
    if not counted["produced"]:
        errors.append("an intake that produced nothing has read nothing worth keeping")
    if not counted["refused"]:
        # `covered` and `ungradeable` are resolutions rather than refusals: one
        # says the corpus already grades the shape and the other says the
        # containment settles it. Neither is the judgement this rule is about,
        # which is a technique read and found not worth keeping.
        errors.append("an intake that never refuses anything is an intake that is not reading")
    if errors:
        raise IntakeError("\n".join(errors))
    return report(rows, states)


def read_records(path: Path = TECHNIQUES) -> list[dict]:
    """The corpus ledger, one record per line.

    JSON Lines rather than a table because six of the fields are lists and one
    is a list of objects, and a table that carried those would have to encode
    them -- at which point the file is JSON with extra steps and a reader that
    can get the escaping wrong.
    """
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            record = json.loads(line)
        except ValueError as error:
            raise IntakeError(f"{path.name} line {number}: {error}") from error
        if not isinstance(record, dict):
            raise IntakeError(f"{path.name} line {number}: not one record")
        records.append(record)
    return records


def read_sources(path: Path = SOURCES) -> list[dict[str, str]]:
    """The sources, read the way the tables beside them are read, keyed by id."""
    try:
        return read_table(path, SOURCE_FIELDS, "technique sources", key="id")
    except BaselineError as error:
        raise IntakeError(str(error)) from error


def record_error(record: dict, books: frozenset[str], skills: frozenset[str]) -> str:
    """Why one ledger record does not resolve, or empty."""
    named = record.get("id", "?")
    missing = [field for field in RECORD_FIELDS if field not in record]
    if missing:
        return f"{named}: missing {', '.join(missing)}"
    unknown = sorted(set(record) - set(RECORD_FIELDS) - {RECORD_NOTE})
    if unknown:
        return f"{named}: unknown field {', '.join(unknown)}"
    for field in RECORD_FIELDS:
        wanted = list if field in RECORD_LISTS else str
        if not isinstance(record[field], wanted):
            return f"{named}: {field} is not {'a list' if wanted is list else 'text'}"
        if wanted is str and field not in MAY_BE_EMPTY and not record[field].strip():
            return f"{named}: {field} is empty"
    if RECORD_NOTE in record and not str(record[RECORD_NOTE]).strip():
        # The field is absent on the two hundred and seventy-six records that
        # did not need it. Present and empty is a third state, and it would
        # count towards the report's tally while saying nothing.
        return f"{named}: {RECORD_NOTE} is present and says nothing"
    # One operator's home directory, written into a file the whole repository
    # ships. It is a leak, and it is also a join that only holds on the machine
    # that built the corpus: the sources table spells the same file with `~`.
    if HOME.search(json.dumps(record)):
        return f"{named}: a path under a home directory was written into a shipped file"
    if not RECORD_ID.match(record["id"]):
        return f"{named}: id is not <playbook>/<NN>"
    if record["playbook"] not in books:
        return f"{named}: no playbook named {record['playbook']}"
    if not record["id"].startswith(f"{record['playbook']}/"):
        return f"{named}: id names a playbook the record does not"
    if record["finding_path"] not in FINDING_PATHS:
        return (
            f"{named}: finding path {record['finding_path']!r} is not one of"
            f" {', '.join(FINDING_PATHS)}"
        )
    for field in ("technique", RECORD_NOTE):
        if thin(str(record.get(field, "x" * PROSE)), PROSE):
            return f"{named}: {field} is too short to be a restatement"
    for field in PHRASED:
        if thin(record[field], PHRASE) and not UNRUNNABLE.match(record[field].strip()):
            return f"{named}: {field} is too short to name anything"
    # Ticket 216. A halt that names who is told and not what it is filed under
    # is a step an Agent cannot perform: the tool takes a `question_code` and
    # refuses the call without one. The rule is here and not in the corpus gate
    # because the ledger is where the halt is written down first.
    if PARK in record["stop_conditions"] and not any(
        code in record["stop_conditions"] for code in QUESTION_CODES
    ):
        return f"{named}: a halt told through {PARK} names the question code it parks under"
    if record["capability_state"] != CAPABILITY[record["finding_path"]]:
        return (
            f"{named}: {record['finding_path']} means the harness is"
            f" {CAPABILITY[record['finding_path']]}, and the record says"
            f" {record['capability_state']}"
        )
    # Empty is a resolution here rather than a gap: a technique the shipped
    # Skills do not cover is a technique a step performs directly, and the three
    # spellings the mining stage used for that were folded to one.
    if record["required_skill"] and record["required_skill"] not in skills:
        return f"{named}: no skill named {record['required_skill']}"
    if not record["local_sources"] and not record["external_sources"]:
        return f"{named}: a record written from nothing is not a reading"
    if not record["okf_source_ids"]:
        return f"{named}: a record filed under no concept cannot be found again"
    for field in ("local_sources", "mined_from"):
        for one in record[field]:
            if not isinstance(one, str) or not one.strip():
                return f"{named}: {field} holds something that is not a name"
    for one in record["local_sources"]:
        if one.startswith("~"):
            continue
        # A path this checkout can resolve, and only inside itself. `..` and an
        # absolute path both resolve to a file that exists, so `exists()` alone
        # would let a citation point anywhere on the machine running the gate.
        if one.startswith("/") or ".." in one.split("/"):
            return f"{named}: {one} walks out of this checkout"
        if not (CHECKOUT / one).exists():
            return f"{named}: no file at {one}"
    for one in record["external_sources"]:
        if not isinstance(one, dict) or set(one) != set(EXTERNAL_PARTS):
            return f"{named}: an external source is not {', '.join(EXTERNAL_PARTS)}"
        if not all(isinstance(one[part], str) for part in EXTERNAL_PARTS):
            return f"{named}: an external source is not {', '.join(EXTERNAL_PARTS)}"
        # Empty is the one address an external source may not have, and it is
        # what `absent` means: the mining stage looked for a published source of
        # some shape and found none. Everything else is held to the rule the
        # ledger next door uses, minus the fragment -- a fragment never leaves
        # the client, so it cannot be how a gated resource is spelled.
        if one["url"] and (error := source_error(one["url"].split("#", 1)[0])):
            return f"{named}: {error}"
    for one in record["okf_source_ids"]:
        if not isinstance(one, str) or not CONCEPT.match(one):
            return f"{named}: {one!r} is not a concept the mining stage filed under"
    try:
        datetime.fromisoformat(record["okf_stale_after"])
    except (TypeError, ValueError):
        return f"{named}: okf_stale_after {record['okf_stale_after']!r} is not a time"
    for field in ("baseline", "variant", "control"):
        arm = record[field].strip()
        if CAPABILITY[record["finding_path"]] == "reachable":
            if UNRUNNABLE.match(arm) or thin(arm, PROSE):
                return f"{named}: {record['finding_path']} with no {field} arm to run"
        elif not UNRUNNABLE.match(arm) and thin(arm, PROSE):
            # Off a reachable path an arm may say there was nothing to run, and
            # that is the whole of what it may say short: anything else is a
            # step, and a step is written out.
            return f"{named}: {field} neither runs nor says why not"
    return ""


def thin(value: str, floor: int) -> bool:
    """Whether a field is too short to be what it claims to be.

    Length, and then one letter somewhere in it: a zero-width space is neither
    whitespace to `strip` nor a letter to a reader, so a field padded with forty
    of them is a field that says nothing at a length that says otherwise.
    """
    said = value.strip()
    return len(said) < floor or not re.search(r"\w", said)


def addressed(record: dict) -> dict[str, list[tuple[str, ...]]]:
    """Every source a record names, keyed by the kind its address makes it.

    Derived rather than declared, because the address is what decides: a record
    cannot claim a page is fetchable by filing it under `external`, and the
    sources table cannot quietly refile one it failed to fetch.
    """
    found: dict[str, list[tuple[str, ...]]] = {kind: [] for kind in SOURCE_KINDS}
    found["local"] = [(one, "", "") for one in record["local_sources"]]
    for one in record["external_sources"]:
        url = one["url"]
        found["external" if url.startswith("https://") else ABSENT].append(
            tuple(one[part] for part in EXTERNAL_PARTS)
        )
    return {kind: sorted(rows) for kind, rows in found.items()}


def source_row_error(row: dict[str, str], records: frozenset[str]) -> str:
    """Why one source row does not resolve, or empty."""
    named = row["id"]
    if not SOURCE_ID.match(named):
        return f"{row['id']!r} is not a source id"
    if row["kind"] not in SOURCE_KINDS:
        return f"{named}: kind {row['kind']!r} is not one of {', '.join(SOURCE_KINDS)}"
    if row["ledger_id"] not in records:
        return f"{named}: no ledger record {row['ledger_id']}"
    try:
        # Both, because they refuse different things: the pattern is the sibling
        # table's own spelling rule, and the parse is what refuses `0000-00-00`,
        # which is a date the pattern is happy with.
        if not DATE.match(row["retrieved"]):
            raise ValueError
        date.fromisoformat(row["retrieved"])
    except ValueError:
        return f"{named}: retrieved {row['retrieved']!r} is not a date"
    # Every column, rather than the address alone: a home directory is as much
    # of a leak in a title or a note as it is in a path.
    if any(HOME.search(value) for value in row.values()):
        return f"{named}: a path under a home directory was written into a shipped file"
    if row["kind"] == "local":
        if not row["url"].strip():
            return f"{named}: a local source with no path is not a source"
        # The record names the path and nothing else, so these two are the
        # table's own and have nothing to be compared against. Pinning them is
        # what keeps them from becoming a second, unchecked place to write.
        if row["title"] != row["url"].rsplit("/", 1)[-1]:
            return f"{named}: a local source is titled by its file name"
        if row["version_note"].strip():
            return f"{named}: a file on disk carries no version note"
        # The hundred and eighty-six sources inside this checkout are the ones
        # a second reader can recompute, so the gate recomputes them. A digest
        # nobody checks is a record of what was read only until the file moves
        # underneath it.
        if not row["url"].startswith("~"):
            whole = (CHECKOUT / row["url"]).read_bytes()
            if row["digest"] != "sha256:" + hashlib.sha256(whole).hexdigest():
                return f"{named}: {row['url']} no longer hashes to what was read"
    if row["kind"] == "external" and (
        error := source_error(row["url"].split("#", 1)[0])
    ):
        return f"{named}: {error}"
    if row["kind"] == ABSENT:
        if row["url"]:
            return f"{named}: an address was found, so it is not absent"
        if not row["title"].strip() and not row["note"].strip():
            return f"{named}: nothing was found, and nothing says what was looked for"
    if row["digest"] and not DIGEST.match(row["digest"]):
        return f"{named}: digest is not sha256 and sixty-four hex digits"
    if row["kind"] == ABSENT and row["digest"]:
        return f"{named}: nothing was found here, so nothing was read"
    if not row["digest"] and row["kind"] != ABSENT:
        # A source with no digest is a source nobody has read, and the row stays
        # rather than being dropped so that the record's own list still resolves.
        # What it may not do is stay silent about why.
        if row["kind"] == "local":
            return f"{named}: a local file was named and never read"
        if not row["note"]:
            return f"{named}: no digest, and no note saying what happened"
    return ""


def link_errors(records: list[dict], sources: list[dict[str, str]]) -> list[str]:
    """The join, on what the two files say rather than on how many rows there are.

    Counting would pass a table whose rows point at pages the record never
    named, which is the failure worth catching: a digest is only evidence of
    what was read if the thing it was taken from is the thing the record cites.
    The address, the title and the version note are all compared, because the
    record keeps its own copy of those three and only the digest was moved out.

    The other direction is `source_row_error`, which refuses a row pointing at
    no record. Together they are the rule: every source a record names has a row
    of its own, and every row belongs to a record.
    """
    held: dict[tuple[str, str], list[tuple[str, ...]]] = {}
    for row in sources:
        held.setdefault((row["ledger_id"], row["kind"]), []).append(
            (row["url"], "", "")
            if row["kind"] == "local"
            else (row["url"], row["title"], row["version_note"])
        )
    errors = []
    for record in records:
        for kind, named in addressed(record).items():
            found = sorted(held.get((record["id"], kind), []))
            if found != named:
                missing = sorted(set(named) - set(found))
                extra = sorted(set(found) - set(named))
                errors.append(
                    f"{record['id']}: {kind} sources:"
                    f" {len(named)} named, {len(found)} in the table"
                    + (f", missing {missing[0][0]!r}" if missing else "")
                    + (f", unnamed {extra[0][0]!r}" if extra else "")
                )
    return errors


def techniques_report(records: list[dict], sources: list[dict[str, str]]) -> str:
    """The counts, in one fixed order, so two runs of it diff to nothing.

    All five finding paths are listed even when one has no records, because a
    path that fell to zero is the change worth seeing: it means a rewrite moved
    every reading of some shape, and a report that only listed what was there
    would show that as nothing at all.
    """
    paths = Counter(record["finding_path"] for record in records)
    kinds = Counter(row["kind"] for row in sources)
    skills = {record["required_skill"] for record in records if record["required_skill"]}
    lines = [
        "technique ledger",
        f"  {'records':<24}{len(records):>4}   "
        f"playbooks {len({record['playbook'] for record in records})}  "
        f"skills {len(skills)}  "
        f"path notes {sum(1 for record in records if RECORD_NOTE in record)}",
        f"  {'sources':<24}{len(sources):>4}   "
        f"local {kinds['local']}  external {kinds['external']}  "
        f"absent {kinds[ABSENT]}  digested {sum(1 for row in sources if row['digest'])}",
    ]
    lines += [f"  {path:<24}{paths[path]:>4}" for path in FINDING_PATHS]
    return "\n".join(lines)


def check_techniques(
    records_path: Path = TECHNIQUES, sources_path: Path = SOURCES
) -> str:
    """The corpus gate. Returns the report, or raises with every reason it failed."""
    records = read_records(records_path)
    sources = read_sources(sources_path)
    books = frozenset(playbook.PLAYBOOKS)
    skills = frozenset(skill.SKILLS)

    errors: list[str] = []
    sound: list[dict] = []
    for record in records:
        error = record_error(record, books, skills)
        if error:
            errors.append(error)
        else:
            sound.append(record)

    # `read_table` refuses a repeated key for the sources; JSON Lines has no
    # reader to do the same, and an id claimed twice would make the join below
    # agree with itself while pointing at two different records.
    for named, count in sorted(Counter(record["id"] for record in sound).items()):
        if count > 1:
            errors.append(f"{named}: {count} records share one id")

    # Every shipped Playbook is written from these records, so a corpus missing
    # one is a Playbook with nothing behind it. This is also what refuses a
    # truncated file: a gate that only read what it was given would call an
    # empty ledger consistent.
    for book in sorted(books - {record["playbook"] for record in sound}):
        errors.append(f"no ledger record is about playbook {book}")

    # Every record that parsed rather than only the sound ones, so that one bad
    # record does not also report each of its source rows as pointing at
    # nothing. Only the ones whose id is text: the rest are already reported,
    # and a list cannot go in a set.
    named = frozenset(
        record["id"] for record in records if isinstance(record.get("id"), str)
    )

    # A record numbered 02 with no 01 is a corpus that lost a reading between
    # the mining stage and here, and the count alone cannot see it: a file cut
    # to its first record per Playbook still covers every Playbook.
    ordinals: dict[str, list[int]] = {}
    for record in sound:
        book, _, number = record["id"].partition("/")
        ordinals.setdefault(book, []).append(int(number))
    for book, found in sorted(ordinals.items()):
        wanted = list(range(1, len(found) + 1))
        if sorted(found) != wanted:
            gap = next(number for number in wanted if number not in found)
            errors.append(f"playbook {book}: {len(found)} records and no {book}/{gap:02d}")

    # What the sources table is for, checked rather than asserted in a comment.
    # One page is cited by four records on average, and a digest recorded once
    # per citation is a digest that can disagree with itself.
    if len(records) != RECORDS:
        errors.append(
            f"the reviewed corpus holds {RECORDS} records,"
            f" and this one holds {len(records)}"
        )

    read: dict[str, str] = {}
    for row in sources:
        if row["digest"] and read.setdefault(row["url"], row["digest"]) != row["digest"]:
            errors.append(f"{row['id']}: {row['url']} was read twice, and the two disagree")
    if not sources:
        errors.append("a corpus whose sources table is empty cites nothing")
    errors += [error for row in sources if (error := source_row_error(row, named))]
    errors += link_errors(sound, sources)
    if errors:
        raise IntakeError("\n".join(errors))
    return techniques_report(sound, sources)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    # Both gates run even when the first fails, because they read two different
    # files and an operator fixing one should not have to run again to find out
    # whether the other is also broken.
    reports, failures = [], []
    for gate in (check, check_techniques):
        try:
            reports.append(gate())
        except (BaselineError, IntakeError, OSError) as error:
            failures.append(str(error))
    if reports:
        print("\n".join(reports))
    if failures:
        print("intake failed: " + "\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
