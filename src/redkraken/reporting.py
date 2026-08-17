"""`rk report`: the document a human reads, as a projection of what holds.

Named for the activity rather than for the command, because every module in
this package imports `outcome.report` and a module called `report` would make
one of the two something a reader has to disambiguate at every call site.

034 built the Finding side of a report and stopped one file short of a reader.
It has the block registry, the platform forms, the source bundle, the blockers,
the digest and an immutable row for the bytes -- and nothing in the tree ever
produced a byte. This is that file, and 042's schema half is
`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql`.

`render` is the whole reporter and its signature is the criterion: a mapping in,
a string out. No connection, no settings, no model, no clock, no environment. It
cannot reach a target because it is not given anything that could, and it cannot
mutate state because it is not given anything that holds any. Everything below
it is a function of its argument, so two callers with equal bundles get equal
bytes and there is no third thing to keep in step.

What the command around it does is fetch one bundle, hand it here, and put the
bytes where they were asked for. `--record` files them through
`record_rendering`, which recomputes the source digest itself: 034's approval
gate names a rendering row and compares digests, and a digest this process
supplied would be a comparison against this process's own claim.

The narrative is off unless a file is named, and what it may say is bounded by
what the bundle already says. A block's prose is checked token by token against
the bundle's own scalars, so a sentence can rephrase the projection and cannot
add an endpoint, a status, a version or a count that the projection does not
carry. Prose that is not a factual claim -- ordinary words -- passes untouched.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from redkraken import config, migrate, pg, program
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


__all__ = ["COMMAND", "FACTS", "RUN", "Refused", "VERSION", "projected", "render", "run"]


COMMAND = "report"
RUN = COMMAND

#: What this command reports on every path, refused or performed.
FACTS = ("program_id", "program_slug", "subject", "label", "template", "document")

#: Recorded on every rendering row, so a document filed by one version can be
#: told from a document filed by another. Bumped when the bytes this module
#: produces from an unchanged bundle change -- which is the only thing an
#: approval could be surprised by.
VERSION = "rk2-report/1"

BIND = "SELECT set_config('rk2.program_id', $1, false)"
SUBJECTS = {
    "finding": (
        "SELECT id FROM findings WHERE program_id = $1::uuid AND label = $2",
        "SELECT read_finding_report($1::uuid, $2)",
    ),
    "chain": (
        "SELECT id FROM chains WHERE program_id = $1::uuid AND label = $2",
        "SELECT read_chain_report($1::uuid, $2)",
    ),
}
RECORD = "SELECT record_rendering($1::uuid, $2, $3, $4)"

#: Which bundle key holds the thing the document is about. A finding bundle
#: carries `chain` as its list of mechanism steps, so the two subjects cannot
#: share one key and the choice has to be made from `kind`.
_TITLE = {"finding": "finding_label", "chain": "chain"}

#: The blocks a narrative may add a sentence to: the three that argue rather
#: than record. A narrative under `evidence_manifest` or `repro_steps` would be
#: prose beside a list of hashes and a list of requests, where the only thing it
#: could add is emphasis.
#:
#: `chain_composition` is deliberately not among them. It is the whole of
#: criterion 4, and the distinction it draws -- composed from separate
#: demonstrations, or walked end to end by one run -- is made of ordinary words.
#: `_claims` only asks about identifier- and digit-shaped tokens, so a paragraph
#: there could assert the opposite of the sentence above it and pass every check
#: this module makes.
NARRATABLE = frozenset({"impact_sentence", "limitations", "remediation"})

#: Marked in the document rather than blended into it. A triager who wants only
#: what the harness established can find where that stops.
NARRATIVE_MARK = "Narrative (authored; every fact in it appears above):"


class Refused(Exception):
    """A bundle this renderer will not turn into bytes, and why.

    Carries every reason rather than the first. A Finding is usually blocked
    several times over, and an operator told one reason fixes it and meets the
    next -- which is the shape 034's blocker list already has.
    """

    def __init__(self, source: str, reasons: Sequence[str]) -> None:
        super().__init__("; ".join(reasons))
        self.source = source
        self.reasons = tuple(reasons)


# ---------------------------------------------------------------------------
# The renderer
# ---------------------------------------------------------------------------


def render(bundle: Mapping[str, object], *, narrative: Mapping[str, str] | None = None) -> str:
    """One source bundle as the document, or a refusal saying why not.

    Pure, and the signature is where that is enforced: there is nothing here to
    read from or write to. Equal bundles render equal bytes, which is criterion
    5 -- every list in the bundle arrives ordered by the database and nothing
    below re-sorts, re-groups by a dictionary, or asks the clock.
    """
    kind = bundle.get("kind")
    if kind not in _TITLE:
        raise Refused("bundle", [f"a bundle of kind {kind!r} is not a report source"])
    _gate(bundle, kind)
    blocks = _blocks(bundle)
    prose = _narrative(bundle, blocks, narrative)

    lines = [f"# {bundle[_TITLE[kind]]}", ""]
    for block in blocks:
        body = _BLOCKS[block["id"]](bundle)
        lines.append(f"## {block['name']}")
        lines.append("")
        lines.extend(body)
        if block["id"] in prose:
            lines.extend(["", NARRATIVE_MARK, "", prose[block["id"]]])
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _gate(bundle: Mapping[str, object], kind: str) -> None:
    """Criterion 2, and the whole of what this module decides about it.

    Neither answer is computed here. A Finding renders when 034's blockers are
    all soft, and a chain renders when 040 says it is sound -- and 040's own
    soundness already asks the two review gates that hold a member, so a chain
    that renders is a chain whose members are review-cleared.
    """
    if kind == "chain":
        if not bundle.get("sound"):
            raise Refused("chains", [str(bundle.get("unsound") or "the chain is not sound")])
        return
    hard = [
        f"{item['code']}: {item['detail']}"
        for item in bundle.get("blockers") or ()
        if item.get("severity") != "soft"
    ]
    if hard:
        raise Refused("report_blockers", hard)


def _blocks(bundle: Mapping[str, object]) -> list[Mapping[str, str]]:
    """The form's sections, refusing a form this renderer cannot honour.

    A block registered in the database with no function here would render as a
    heading over nothing, which is a report that silently omits a section
    somebody put in the form on purpose.
    """
    blocks = list(bundle.get("blocks") or ())
    if not blocks:
        raise Refused("report_template_blocks", [f"{bundle['template']} states no blocks"])
    unknown = sorted({str(block["id"]) for block in blocks} - set(_BLOCKS))
    if unknown:
        raise Refused(
            "report_blocks",
            [f"{VERSION} cannot render block(s) {', '.join(unknown)}"],
        )
    return blocks


def _provenance_header(bundle: Mapping) -> list[str]:
    origin = bundle["provenance"]
    return [
        f"- Finding: {bundle['finding_label']}",
        f"- Form: {bundle['template']}",
        f"- Source digest: {bundle['digest']}",
        f"- Evidence lane: {origin['lane'] or 'none cited'}",
        f"- First cited exchange: {origin['at'] or 'none cited'} UTC",
    ]


def _scope_block(bundle: Mapping) -> list[str]:
    scope = bundle["scope"]
    lines = [
        f"- Program: {scope['program']}",
        f"- Scope document version: {scope['version']}",
        f"- Scope document digest: {scope['policy_sha256'] or 'none recorded'}",
    ]
    if "subject_class" in scope:
        lines.append(f"- Subject scope class: {scope['subject_class']}")
        lines.append(f"- Subject in scope: {_yes(scope['subject_in_scope'])}")
    return lines


def _impact_sentence(bundle: Mapping) -> list[str]:
    """Criterion 3's impact, under the two words 038 separates it into.

    An effect is what an observation witnessed; a demonstration is what an
    impact run proved, with an after-state Receipt and a performed cleanup
    behind it. Printing them under one heading would make the section read as
    though the weaker of the two had the stronger one's evidence.
    """
    klass = bundle["class"]
    lines = [f"{klass['name']} ({klass['cwe']}) on the subject named below."]
    effects = bundle["effects"]
    if not effects:
        lines.extend(["", "No effect is recorded against this Finding."])
    else:
        lines.extend(["", "Witnessed effects:", *(f"- {item['phrase']}" for item in effects)])
    demonstrated = bundle["demonstrations"]
    if not demonstrated:
        return [*lines, "", "No impact run has demonstrated one of these effects."]
    return [
        *lines,
        "",
        "Demonstrated impact:",
        *(
            f"- {item['class']}: {item['description']} "
            f"(after-state {item['after_state']}, {item['receipts']} exchange(s), "
            f"{item['cleanup_receipts']} undone)"
            for item in demonstrated
        ),
    ]


def _affected_assets(bundle: Mapping) -> list[str]:
    subject = bundle["subject"]
    lines = [f"- Subject: {subject['dedup_key']}", f"- Kind: {subject['type']}"]
    if subject["base_url"]:
        lines.append(f"- Application: {subject['base_url']}")
    if subject["method"]:
        lines.append(f"- Request: {subject['method']} {subject['path']}")
    return lines


def _attack_chain(bundle: Mapping) -> list[str]:
    steps = bundle["chain"]
    if not steps:
        return ["No mechanism is recorded against this Finding."]
    return [
        f"{step['ordinal']}. {_filled(step['template'], step['params'])} "
        f"[{', '.join(step['citations']) or 'no citation'}]"
        for step in steps
    ]


def _by_role(bundle: Mapping, role: str) -> list[Mapping]:
    """The validating Test's actions written under one role, in run order.

    The specification carries every action with the role it was written for and
    the bundle does not group them, so both sections that want a role ask here.
    """
    return [item for item in bundle["spec"]["actions"] if item["role"] == role]


def _poc_payload(bundle: Mapping) -> list[str]:
    variant = _by_role(bundle, "variant")
    if not variant:
        return ["The validating Test performs no variant action."]
    return [
        "The request(s) that differ from the baseline:",
        *(f"{item['ordinal']}. {item['method']} {item['url']}" for item in variant),
    ]


def _repro_steps(bundle: Mapping) -> list[str]:
    spec = bundle["spec"]
    lines = [f"Specification digest: {bundle['spec_sha256']}", ""]
    for item in spec["preconditions"]:
        lines.append(f"- Precondition ({item['kind']}): {item['detail']}")
    for item in spec["setup"]:
        lines.append(f"- Setup: {item['method']} {item['url']}")
    if lines[-1] != "":
        lines.append("")
    lines.append("Actions, in the order the run performs them:")
    lines.extend(
        f"{item['ordinal']}. [{item['role']}] {item['method']} {item['url']}"
        for item in spec["actions"]
    )
    lines.extend(["", "Assertions:"])
    lines.extend(f"- {_assertion(item)}" for item in spec["assertions"])
    if spec["cleanup"]:
        lines.extend(["", "Cleanup:"])
        lines.extend(f"- {item['method']} {item['url']}" for item in spec["cleanup"])
    return lines


def _controls(bundle: Mapping) -> list[str]:
    """Criterion 3's baseline, variant and controls, and what came of them.

    Grouped here rather than in the bundle. The specification already carries
    every action under the role it was written for, and a second grouped copy
    beside it would be the same three lists twice.
    """
    validation = bundle["run"]
    lines = []
    for role in ("baseline", "variant", "control"):
        lines.append(f"{role.capitalize()}:")
        lines.extend(
            f"- {item['ordinal']}. {item['method']} {item['url']}"
            for item in _by_role(bundle, role)
        )
        lines.append("")
    lines.append(f"The validating run {validation['outcome']} on the {validation['lane']} lane, "
                 f"and its cleanup is {validation['cleanup']}.")
    lines.append("")
    lines.append("Assertion verdicts:")
    lines.extend(f"- {item['id']}: {_held(item['held'])}" for item in validation["assertions"])
    return lines


def _evidence_manifest(bundle: Mapping) -> list[str]:
    evidence = bundle["evidence"]
    if not evidence:
        return ["No exchange is cited by this Finding."]
    lines = []
    for item in evidence:
        lines.append(f"- {item['receipt']}: {item['method']} {item['path']} -> {item['status']}")
        lines.append(f"  request sha256 {item['request_sha']}")
        lines.append(f"  response sha256 {item['response_sha']} ({item['visibility']})")
    return lines


def _severity_block(bundle: Mapping) -> list[str]:
    severity = bundle["severity"]
    if not severity["vector"]:
        return ["No CVSS vector has been computed for this Finding."]
    return [
        f"- Vector: {severity['vector']}",
        f"- Base score: {severity['score']} ({severity['band']})",
        f"- Origin: {severity['origin']}",
    ]


def _limitations(bundle: Mapping) -> list[str]:
    stated = bundle["limitations"]
    if not stated:
        return ["Nothing further is known to limit what is stated above."]
    return [f"- {item['code']}: {item['detail']}" for item in stated]


def _remediation(bundle: Mapping) -> list[str]:
    lines = [str(bundle["class"]["remediation"])]
    if bundle["technology"]:
        lines.extend(["", f"The subject was identified as {bundle['technology']}."])
    return lines


def _chain_header(bundle: Mapping) -> list[str]:
    return [
        f"- Chain: {bundle['chain']}",
        f"- Form: {bundle['template']}",
        f"- Source digest: {bundle['digest']}",
        f"- Composed from: {bundle['source_sha256']}",
        f"- Entry capabilities: {', '.join(bundle['entry']) or 'none'}",
        f"- Steps: {len(bundle['steps'])}",
    ]


def _chain_composition(bundle: Mapping) -> list[str]:
    """Criterion 4, which is one word and the sentence that stops it inflating.

    The distinction is the whole of the criterion, so the report states which of
    the two this is in terms a triager reads once, rather than leaving it to be
    inferred from whether the transitions happen to share a run identifier.
    """
    if bundle["execution"] == "executed":
        return [
            "One run walked this chain end to end: a single Tool run's stamps "
            "cover a whole path from an entry step to a terminal one, so the "
            "composition below was performed and not only assembled.",
        ]
    return [
        "Each transition below was demonstrated separately and the chain is "
        "composed from those demonstrations. No single run has yet walked it "
        "end to end, so what is established is that each step holds and that "
        "each one's result satisfies what the next one requires.",
    ]


def _chain_transitions(bundle: Mapping) -> list[str]:
    lines = []
    for step in bundle["steps"]:
        lines.append(f"{step['depth']}. {step['stamp']} ({step['member']}, {step['class']})")
        lines.append(f"   subject {step['subject']} as {step['identity']}")
        lines.append(f"   requires {', '.join(step['requires']) or 'nothing'}")
        lines.append(f"   provides {step['provides']} by {step['transition']}")
        lines.append(f"   conditions {json.dumps(step['conditions'], sort_keys=True)}")
    if not bundle["edges"]:
        return [*lines, "", "The chain states no capability edge between these steps."]
    return [
        *lines,
        "",
        "Capability edges:",
        *(f"- {edge['from']} -> {edge['to']} ({edge['capability']})" for edge in bundle["edges"]),
    ]


def _chain_evidence(bundle: Mapping) -> list[str]:
    evidence = bundle["evidence"]
    if not evidence:
        return ["No transition of this chain cites an exchange."]
    lines = []
    for item in evidence:
        lines.append(
            f"- {item['stamp']}: {item['method']} {item['path']} -> {item['status']} "
            f"({item['receipt']})"
        )
        lines.append(f"  specification sha256 {item['spec_sha256']}")
    return lines


#: Block id to the function that renders its body. Registered here and in
#: `report_blocks`, and `_blocks` refuses a form naming an id this table does
#: not carry, so the two cannot quietly disagree.
_BLOCKS: dict[str, Callable[[Mapping], list[str]]] = {
    "provenance_header": _provenance_header,
    "scope_block": _scope_block,
    "impact_sentence": _impact_sentence,
    "affected_assets": _affected_assets,
    "attack_chain": _attack_chain,
    "poc_payload": _poc_payload,
    "repro_steps": _repro_steps,
    "controls": _controls,
    "evidence_manifest": _evidence_manifest,
    "severity_block": _severity_block,
    "limitations": _limitations,
    "remediation": _remediation,
    "chain_header": _chain_header,
    "chain_composition": _chain_composition,
    "chain_transitions": _chain_transitions,
    "chain_evidence": _chain_evidence,
}


_SLOT = re.compile(r"\{([a-z_]+)\}")


def _filled(template: str, params: Mapping[str, object]) -> str:
    """A mechanism sentence with its slots filled from the step's parameters.

    Substituted rather than formatted. `str.format` would read a brace in a
    parameter value as a second slot, and a parameter value is a token taken
    from a target's own response.
    """
    return _SLOT.sub(lambda match: str(params.get(match.group(1), match.group(0))), template)


def _assertion(item: Mapping) -> str:
    if item["kind"] == "status_equals":
        return f"{item['id']}: action {item['action']} returns {item['status']} ({item['kind']})"
    return (f"{item['id']}: action {item['action']} against action {item['against']} "
            f"({item['kind']})")


def _held(verdict: object) -> str:
    if verdict is None:
        return "could not be evaluated"
    return "held" if verdict else "did not hold"


def _yes(value: object) -> str:
    return "yes" if value else "no"


# ---------------------------------------------------------------------------
# Criterion 6: what a narrative may say
# ---------------------------------------------------------------------------

#: Punctuation a writer puts around a token rather than in it. Stripped before
#: the token is looked for, so `` `/admin`, `` is asked as `/admin`.
_EDGES = " \t\"'`()[]{}<>,.;:!?*_"

#: What makes a word a claim rather than prose. A digit, a character that only
#: appears in an identifier, or an interior dot -- which is `example.com` and
#: `1.4` after the sentence's own full stop has been stripped.
_MARKS = frozenset("/:@=?&%#")


def _narrative(
    bundle: Mapping[str, object],
    blocks: Sequence[Mapping[str, str]],
    narrative: Mapping[str, str] | None,
) -> dict[str, str]:
    """Criterion 6: off by default, and adding no fact when it is on.

    Every factual-looking token has to be something the projection already
    carries. That is a blunt test and deliberately so: the alternative is a
    judgement about which claims matter, made by the same kind of process that
    wrote the sentence.
    """
    if not narrative:
        return {}
    rendered = {str(block["id"]) for block in blocks}
    known = _permitted(bundle)
    reasons = []
    prose = {}
    for block, text in sorted(narrative.items()):
        if block not in NARRATABLE:
            reasons.append(f"{block} takes no narrative; {', '.join(sorted(NARRATABLE))} do")
            continue
        if block not in rendered:
            reasons.append(f"{block} is not a section of {bundle['template']}")
            continue
        introduced = sorted(
            {
                token
                for token in (word.strip(_EDGES) for word in str(text).split())
                if token and _claims(token) and token not in known
            }
        )
        if introduced:
            reasons.append(
                f"the {block} narrative states {', '.join(introduced)}, "
                f"which the projection does not"
            )
            continue
        prose[block] = str(text).strip()
    if reasons:
        raise Refused("argument:--narrative", reasons)
    return prose


def _claims(token: str) -> bool:
    return any(char.isdigit() for char in token) or not _MARKS.isdisjoint(token) or "." in token


def _permitted(bundle: Mapping[str, object]) -> frozenset[str]:
    """Every token the projection carries, as a set.

    The projection and not the document: a short form omits blocks, and the
    scalars under an omitted block stay admissible. Criterion 6's bound is "the
    deterministic projection", which is the bundle, and the alternative would
    make what a sentence may say depend on which form was asked for.

    Whole scalars and their words both, because the document prints both: a
    bundle carrying `GET /admin/users` prints that line, so a sentence saying
    `/admin/users` introduces nothing. What it does not admit is a token that
    only appears as part of a longer one -- a status hiding inside a hash.
    """
    tokens = set()
    for scalar in _scalars(bundle):
        tokens.add(scalar)
        tokens.update(word.strip(_EDGES) for word in scalar.split())
    tokens.discard("")
    return frozenset(tokens)


def _scalars(value: object) -> Iterator[str]:
    """Every leaf of the bundle as text, keys excluded.

    Keys are the projection's own vocabulary rather than anything it observed,
    and admitting them would let a sentence assert `policy_sha256` as a fact.
    The same split 034's `jsonb_scalars` makes, for the same reason.
    """
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _scalars(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _scalars(item)
    elif isinstance(value, bool):
        yield "true" if value else "false"
    elif value is not None:
        yield str(value)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    subject: str,
    label: str,
    template: str,
    narrative_path: Path | None = None,
    out: Path | None = None,
    record: bool = False,
) -> Report:
    """Read one bundle, render it, and put the bytes where they were asked for."""
    ledger = Ledger()
    answers = _Answers(RUN, subject=subject, label=label, template=template)

    # Asked before anything is read, because the answer does not depend on
    # anything that would be: `report_renderings.finding_id` is not nullable and
    # an approval is a transition of one Finding, so there is no row a chain
    # report could be filed as. Refusing here rather than after the render means
    # an operator is not told about it by a command that has already written the
    # document they asked to file.
    if record and subject != "finding":
        ledger.fail(
            "record",
            "a chain report is not a rendering anybody approves; "
            "an approval is a transition of one Finding",
            code=INVALID_CONFIGURATION,
            source="argument:--record",
        )
        return _report(ledger, answers)

    prose = _read_narrative(ledger, narrative_path)
    if ledger.violations:
        return _report(ledger, answers)

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, answers)
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        answers.program_id = program.resolve(ledger, connection, answers.slug)
        if answers.program_id is None:
            return _report(ledger, answers)
        connection.execute(BIND, (answers.program_id,))
        return _rendered(ledger, answers, connection, prose, out=out, record=record)


def projected(
    ledger: Ledger,
    connection: pg.Connection,
    *,
    program_id: str,
    subject: str,
    label: str,
    template: str,
) -> tuple[str, dict] | None:
    """Which row a label names, and the projection of that row onto one form.

    `None` when either question has no answer, with the reason already in the
    ledger; the two refusals are the same two whichever command asked, and they
    name the argument that was wrong rather than the query that returned nothing.

    Shared rather than written twice because the second reader arrived with 043.
    Rendering a document and packing one are the same two reads, and a bundle
    whose `source.json` came from a different projection than its `report.md` is
    a bundle where every hash agrees and the document is about something else.
    """
    identify, read = SUBJECTS[subject]
    rows = connection.execute(identify, (program_id, label)).rows
    if not rows:
        ledger.fail(
            "subject",
            f"{label} is not a {subject} of this Program",
            code=INVALID_CONFIGURATION,
            source="argument:--label",
        )
        return None
    subject_id = str(rows[0][0])

    answered = connection.execute(read, (subject_id, template)).scalar()
    if answered is None:
        ledger.fail(
            "source",
            f"{template} is not a form for a {subject}",
            code=INVALID_CONFIGURATION,
            source="argument:--template",
        )
        return None
    return subject_id, json.loads(str(answered))


def _rendered(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    prose: Mapping[str, str] | None,
    *,
    out: Path | None,
    record: bool,
) -> Report:
    """The three steps that need the database open, and every way out of them."""
    found = projected(
        ledger,
        connection,
        program_id=answers.program_id,
        subject=answers.subject,
        label=answers.label,
        template=answers.template,
    )
    if found is None:
        return _report(ledger, answers)
    subject_id, bundle = found
    ledger.hold(
        "source",
        f"{answers.label} projects onto {len(bundle.get('blocks') or ())} section(s) "
        f"of {answers.template}, under {str(bundle.get('digest'))[:12]}",
    )

    try:
        content = render(bundle, narrative=prose)
    except Refused as refusal:
        for reason in refusal.reasons:
            ledger.fail("render", reason, code=INVALID_CONFIGURATION, source=refusal.source)
        return _report(ledger, answers)
    answers.document = {
        "bytes": len(content.encode("utf-8")),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "source_digest": bundle.get("digest"),
        "blocks": len(bundle.get("blocks") or ()),
        "narrative": sorted(prose or ()),
        "path": None,
    }
    ledger.hold(
        "render",
        f"{answers.document['bytes']} byte(s) under "
        f"{answers.document['sha256'][:12]}, by {VERSION}",
    )

    if out is not None and not _written(ledger, answers, content, out):
        return _report(ledger, answers)
    if record:
        _recorded(ledger, answers, connection, subject_id, content)
    return _report(ledger, answers)


def _written(ledger: Ledger, answers: _Answers, content: str, out: Path) -> bool:
    """The operator's copy.

    Written over without asking, unlike `rk db dump`'s archive. A rendering is a
    pure function of a bundle and a form, so the file this replaces is either
    these same bytes or a projection of a source that has since changed -- and
    in the second case the stale copy is the thing worth losing.
    """
    try:
        Path(out).write_text(content, encoding="utf-8")
    except OSError as error:
        ledger.fail(
            "document",
            f"{out} could not be written: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--out",
        )
        return False
    answers.document["path"] = str(out)
    ledger.hold("document", f"the document is at {out}")
    return True


def _recorded(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    subject_id: str,
    content: str,
) -> None:
    """File the exact bytes, so that 034's approval has a row to name.

    Finding-side only, which `run` established before it read anything. What is
    left here is the write, and the digest it is filed under is recomputed by
    `record_rendering` rather than sent from this process.
    """
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
        answered = connection.execute(
            RECORD, (subject_id, answers.template, content, VERSION)
        ).scalar()
    filed = json.loads(str(answered))
    if filed["outcome"] != "recorded":
        ledger.fail(
            "record",
            f"the rendering was not filed: {filed['refusal']}",
            code=INVALID_CONFIGURATION,
            source="report_renderings",
        )
        return
    # Both, because an approval names both: `rk finding report` takes the id and
    # the digest of the bytes, so that what is approved is a document somebody
    # opened rather than a row somebody's script filed. Printed here because this
    # is where they are true together -- the digest is over the content this call
    # just wrote, and reading it back out of the table later is reading whatever
    # is there now.
    answers.document["rendering"] = filed["rendering"]
    answers.document["content_sha256"] = filed["content_sha256"]
    ledger.hold(
        "record",
        f"the bytes are filed as {filed['rendering']} "
        f"({filed['content_sha256']}), which an approval of {answers.label} may name",
    )


def _read_narrative(ledger: Ledger, path: Path | None) -> dict[str, str] | None:
    """The operator's prose, as a document rather than as a shape.

    Whether a sentence may be said is `_narrative`'s question and is asked
    against the bundle. What is decided here is only that a file was named, is
    readable, and holds an object of strings -- because the alternative is that
    question answered with a type error.
    """
    if path is None:
        return None
    try:
        document = json.loads(Path(path).read_bytes())
    except OSError as error:
        ledger.fail(
            "narrative", f"{path} cannot be read: {error}",
            code=INVALID_CONFIGURATION, source="argument:--narrative",
        )
        return None
    except ValueError as error:
        ledger.fail(
            "narrative", f"{path} is not readable JSON: {error}",
            code=INVALID_CONFIGURATION, source="argument:--narrative",
        )
        return None
    if not isinstance(document, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in document.items()
    ):
        ledger.fail(
            "narrative", f"{path} holds no object of block name to sentence",
            code=INVALID_CONFIGURATION, source="argument:--narrative",
        )
        return None
    ledger.hold("narrative", f"{len(document)} authored section(s) offered from {path}")
    return document


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    subject: str
    label: str
    template: str
    slug: str | None = None
    program_id: str | None = None
    document: dict = field(default_factory=dict)


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        subject=answers.subject,
        label=answers.label,
        template=answers.template,
        document=answers.document or None,
    )
