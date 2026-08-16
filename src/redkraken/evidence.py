"""`rk evidence`: one Finding or chain, packed so it can be checked elsewhere.

042 renders a document. A document is a claim, and a triager holding one has no
way to tell a rendered claim from a typed one. This is the difference: the same
bytes, the projection they came from, the exchanges behind them, the Agent view
of what crossed the wire, and a hash of every one of those -- so that a person
with no access to this harness can hold each against the others.

Three rules decide what goes in.

*Nothing that authenticates.* The wire view of every exchange is sealed under a
key this bundle does not carry, and `evidence_artifacts` selects the Agent view
alone. Capabilities, cookies, secret header values and Identity material are in
no column this module reads. What was withheld is counted and named rather than
silently absent, because a reader cannot tell material that was excluded from
material that was never there.

*Nothing about another person.* 034 wrote six redaction patterns and no reader.
This is the reader. Every packaged artifact is scanned against all six and each
match is replaced by a marker carrying the length and the digest of what was
removed, so an excerpt can still be proved against the full artifact later.

*Nothing that has stopped being true.* Export renders through 042, which refuses
an invalidated, duplicate or review-gated Finding, and asks the one question 042
had no reason to ask: whether the last rendering a human read was made from the
source that still holds.

The check travels inside the bundle. `verifier.py` is copied in as `verify.py`,
imports nothing -- not this package, not the standard library beyond four
modules -- and is run here over the finished directory before this command
reports success. An exporter that could write a bundle its own verifier rejects
would be reporting on the wrong thing.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from redkraken import config, migrate, pg, program, reporting, store, verifier
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


__all__ = ["COMMAND", "EXPORT", "FACTS", "VERIFY", "export", "redact", "verify"]


COMMAND = "evidence"
EXPORT = f"{COMMAND} export"
VERIFY = f"{COMMAND} verify"

#: What both operations report on every path, refused or performed.
FACTS = ("program_id", "program_slug", "subject", "label", "template", "bundle")

#: There is no version string of this module in the manifest, and there was one.
#: `verifier.SCHEMA` is the version of what packs a bundle as well as of what
#: reads one, because the verifier ships inside the bundle it verifies: there is
#: no release in which the two can differ, and the second key was the same string
#: under a name that invited a recipient to look for a difference. `renderer` is
#: still there and is a different fact -- 042 renders through a projection this
#: module does not control, so a document can move while the packing does not.

#: Which Receipts a bundle is about, per subject. Composed into the reads below
#: rather than fetched and passed back in: the arrays are gathered, ordered and
#: bound to the Program by the database, and a round trip through this process
#: would put a list this process could edit between the two.
GATHER = {
    "finding": "finding_evidence_receipts($1::uuid)",
    "chain": "chain_evidence_receipts($1::uuid)",
}

#: What would have to be re-run to get the report again, per subject. A Finding
#: has one specification and a chain has one per step; both come from the
#: database rather than one from here and one out of the report source, so that
#: `spec.json` is one document a recipient reads one way.
SPECS = {
    "finding": "SELECT * FROM finding_evidence_specifications($1::uuid)",
    "chain": "SELECT * FROM chain_evidence_specifications($1::uuid)",
}

RECEIPTS = "SELECT * FROM evidence_receipts({gather})"
ARTIFACTS = "SELECT * FROM evidence_artifacts({gather})"
EXCLUSIONS = "SELECT * FROM evidence_exclusions({gather})"
REGISTRY = "SELECT path FROM evidence_bundle_files WHERE subject = $1 ORDER BY path"
RULES = "SELECT id, label, pattern FROM redaction_rules ORDER BY id"
STALE = "SELECT evidence_stale_rendering($1::uuid, $2)"

#: Where the packaged bytes go, under the hash of the Agent view they are the
#: redaction of. A directory rather than a flat name so that the files a bundle
#: always carries stay legible beside however many artifacts one Finding cites.
BYTES = "artifacts"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def redact(data: bytes, rules: Sequence[Mapping[str, str]]) -> tuple[bytes, list[dict]]:
    """One artifact with every rule's matches replaced, and what was replaced.

    Every rule is matched against the *original* text and the splice happens
    once. Applying six substitutions in turn would let the fifth rule match
    inside the marker the second one left -- the markers carry the length of what
    they took, a long body is a long run of digits, and a run of digits is a
    telephone number as far as `phone` is concerned. Combining the six into one
    alternation is not available either: `bearer` carries `(?i)`, and Python
    refuses a global flag that is not at the start of the whole expression.

    Overlaps go to the rule whose match starts first, then to the longer match,
    then to the lower rule identifier -- a total order, so the same bytes redact
    the same way whichever order the rules arrive in.

    latin-1 throughout. It is the one codec that round-trips every byte, which is
    what `proxy.transcript` already relies on; decoding as UTF-8 would put this
    module in the business of guessing an encoding and would make a redaction
    depend on the guess.
    """
    text = data.decode("latin-1")
    spans = [
        (found.start(), found.end(), rule)
        for rule in rules
        for found in re.finditer(rule["pattern"], text)
        if found.end() > found.start()
    ]
    spans.sort(key=lambda span: (span[0], -span[1], span[2]["id"]))

    pieces: list[str] = []
    marks: list[dict] = []
    cursor = 0
    for start, end, rule in spans:
        if start < cursor:
            continue  # inside a range an earlier rule already removed
        removed = text[start:end].encode("latin-1")
        pieces.append(text[cursor:start])
        pieces.append(_marker(str(rule["id"]), removed))
        marks.append(
            {
                "rule": rule["id"],
                "label": rule["label"],
                "offset": start,
                "bytes": len(removed),
            }
        )
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces).encode("latin-1"), marks


def _marker(rule: str, removed: bytes) -> str:
    """What stands where a match was: which rule took it and how much it took.

    Not the digest of what was removed. A telephone number, a national
    identifier or a card number has few enough possible values to walk through
    offline, so a SHA-256 of one is the value with an extra step -- and a bundle
    that published one would be a redaction in name. The range stays answerable
    without it: the manifest carries the unredacted artifact's own digest and
    the mark carries the offset and the length, so a triager holding the full
    artifact can read exactly what this took and see that nothing around it
    moved. That needs the artifact, which is the difference.
    """
    return verifier.MARKER_FORM.format(rule=rule, bytes=len(removed))


# ---------------------------------------------------------------------------
# The export
# ---------------------------------------------------------------------------


def export(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    subject: str,
    label: str,
    template: str,
    out: Path,
    root: Path,
) -> Report:
    """Pack one Finding or chain into a directory that can be checked without this."""
    ledger = Ledger()
    answers = _Answers(EXPORT, subject=subject, label=label, template=template)

    # Asked before anything is read. Every other refusal below costs a database
    # round trip; this one costs a `listdir`, and an operator who named an
    # occupied directory wants to hear about it now rather than after the export
    # has decided what may leave.
    if not _empty(ledger, out):
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
        connection.execute(reporting.BIND, (answers.program_id,))
        return _packed(ledger, answers, connection, out=Path(out), root=Path(root))


def _packed(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    *,
    out: Path,
    root: Path,
) -> Report:
    """Everything that needs the database open, and every way out of it."""
    found = reporting.projected(
        ledger,
        connection,
        program_id=answers.program_id,
        subject=answers.subject,
        label=answers.label,
        template=answers.template,
    )
    if found is None:
        return _report(ledger, answers)
    subject_id, source = found

    # The soundness recheck of criterion 4, and it is 042's rather than a second
    # opinion here: `render` is what reads `report_blockers` and
    # `rk2_chain_unsoundness`, so an invalidated, duplicate, known-issue or
    # review-gated subject raises before anything is written.
    try:
        document = reporting.render(source)
    except reporting.Refused as refusal:
        for reason in refusal.reasons:
            ledger.fail("render", reason, code=INVALID_CONFIGURATION, source=refusal.source)
        return _report(ledger, answers)
    ledger.hold(
        "render",
        f"{len(document.encode('utf-8'))} byte(s) of {answers.template} "
        f"under source digest {str(source.get('digest'))[:12]}",
    )

    if not _current(ledger, answers, connection, subject_id):
        return _report(ledger, answers)

    gathered = _gathered(connection, answers.subject, subject_id)
    ledger.hold(
        "evidence",
        f"{len(gathered.receipts)} exchange(s), {len(gathered.artifacts)} Agent-view "
        f"artifact(s) and {len(gathered.specifications)} specification(s) cited",
    )
    for excluded in gathered.exclusions:
        ledger.hold("excluded", f"{excluded['items']} x {excluded['code']}: {excluded['detail']}")

    return _written(ledger, answers, out, root, document, source, gathered)


def _current(
    ledger: Ledger, answers: _Answers, connection: pg.Connection, subject_id: str
) -> bool:
    """Whether the last document a human read was made from the source that holds.

    The half of criterion 4 that 042 does not answer. A Finding whose rows moved
    after somebody approved a rendering of it would export a fresh document under
    a label an approval was given for a different one, and every hash in the
    bundle would be internally consistent. Re-render, re-read, re-approve: the
    refusal names the digest on both sides so an operator can see which.

    A chain has no rendering row -- an approval is a transition of one Finding --
    and a Finding nobody has filed a rendering for is not stale. Neither is
    refused; there is nothing there to have gone out of date.
    """
    if answers.subject != "finding":
        return True
    answered = connection.execute(STALE, (subject_id, answers.template)).scalar()
    if answered is None:
        ledger.hold("rendering", "no rendering of this Finding has been filed to go stale")
        return True
    filed = json.loads(str(answered))
    if filed["stale"]:
        ledger.fail(
            "rendering",
            f"the rendering filed at {filed['rendered_at']} was made from source "
            f"{str(filed['source_digest'])[:12]} and the source is now "
            f"{str(filed['digest_now'])[:12]}; re-render and have it read again "
            f"before exporting",
            code=INVALID_CONFIGURATION,
            source="report_renderings",
        )
        return False
    ledger.hold(
        "rendering",
        f"the rendering filed at {filed['rendered_at']} is still of this source"
        + (", and is approved" if filed["approved"] else ""),
    )
    return True


def _gathered(connection: pg.Connection, subject: str, subject_id: str) -> _Evidence:
    """The six reads the packing needs, each ordered by the database."""
    gather = GATHER[subject]
    return _Evidence(
        receipts=list(connection.execute(RECEIPTS.format(gather=gather), (subject_id,)).dicts()),
        artifacts=list(connection.execute(ARTIFACTS.format(gather=gather), (subject_id,)).dicts()),
        # `spec` arrives as the text of a jsonb column, and putting that text in
        # `spec.json` would ship a specification a recipient has to parse twice.
        specifications=[
            {**row, "spec": json.loads(str(row["spec"]))}
            for row in connection.execute(SPECS[subject], (subject_id,)).dicts()
        ],
        exclusions=list(connection.execute(EXCLUSIONS.format(gather=gather), (subject_id,)).dicts()),
        rules=list(connection.execute(RULES).dicts()),
        required=[str(row[0]) for row in connection.execute(REGISTRY, (subject,)).rows],
    )


# ---------------------------------------------------------------------------
# The bytes on disk
# ---------------------------------------------------------------------------


def _written(
    ledger: Ledger,
    answers: _Answers,
    out: Path,
    root: Path,
    document: str,
    source: Mapping[str, object],
    gathered: _Evidence,
) -> Report:
    """Write the whole bundle, then hold it against the verifier that ships in it."""
    keep = store.Store(root)
    files: dict[str, bytes] = {
        "report.md": document.encode("utf-8"),
        "source.json": _json(source),
        "spec.json": _json({"specifications": gathered.specifications}),
        "receipts.json": _json(gathered.receipts),
        "verify.py": Path(verifier.__file__).read_bytes(),
    }
    # The one document only one subject has: a chain has no single validating
    # run, so there is nothing for it to have answered. Which subject carries it
    # is the registry's decision rather than a `subject ==` here, so that giving
    # a bundle a file stays a matter of adding a row.
    if "assertions.json" in gathered.required:
        files["assertions.json"] = _json(source.get("run"))

    try:
        packaged, blobs, marks = _artifacts(keep, gathered.artifacts, gathered.rules)
    except (store.Missing, store.Corrupt) as error:
        ledger.fail(
            "artifact",
            f"an artifact this {answers.subject} cites cannot be packaged: {error}",
            code=INVALID_CONFIGURATION,
            source="artifact_store",
        )
        return _report(ledger, answers)
    files["artifacts.json"] = _json(packaged)
    files.update(blobs)

    # Every file the registry says a bundle of this subject carries. Checked
    # here as well as by `check_evidence_export` because the check asks whether
    # the registry is complete and this asks whether this bundle is -- and the
    # way those two diverge is a file registered and never written.
    missing = sorted(set(gathered.required) - set(files))
    if missing:
        ledger.fail(
            "bundle",
            f"the registry says a {answers.subject} bundle carries "
            f"{', '.join(missing)} and this export writes none of them",
            code=INVALID_CONFIGURATION,
            source="evidence_bundle_files",
        )
        return _report(ledger, answers)

    manifest = _manifest(answers, source, gathered, files, marks)
    files[verifier.MANIFEST] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    try:
        for path in sorted(files):
            destination = out / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(files[path])
    except OSError as error:
        ledger.fail(
            "bundle",
            f"{out} could not be written: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--out",
        )
        return _report(ledger, answers)

    answers.bundle = {
        "path": str(out),
        "digest": manifest["digest"],
        "files": len(files),
        "bytes": sum(len(data) for data in files.values()),
        "artifacts": len(packaged),
        "redactions": len(marks),
        "excluded": [item["code"] for item in gathered.exclusions],
    }
    ledger.hold(
        "bundle",
        f"{len(files)} file(s) under {manifest['digest'][:12]}, "
        f"{len(marks)} redaction(s) applied, at {out}",
    )
    return _verified(ledger, answers, out)


def _artifacts(
    keep: store.Store, named: Sequence[Mapping], rules: Sequence[Mapping]
) -> tuple[list[dict], dict[str, bytes], list[dict]]:
    """The cited bytes, redacted once each: what to say about them, and them.

    Keyed by the Agent-view hash rather than by the Receipt: two exchanges that
    carried identical bodies are one artifact in the store and are one file here,
    and packing it twice would put the same bytes in the bundle under two names
    that a reader would have to compare to discover were the same.

    The bytes come back beside the description rather than inside it. A packed
    artifact carried in the structure that becomes `artifacts.json` is one
    forgotten `pop` away from writing the artifact into the index as well as
    beside it -- which is a redaction applied to one copy of something the bundle
    then ships twice.
    """
    packaged: dict[str, dict] = {}
    blobs: dict[str, bytes] = {}
    marks: list[dict] = []
    for row in named:
        sha = str(row["sha256"])
        if sha not in packaged:
            data, found = redact(keep.load(sha), rules)
            blobs[f"{BYTES}/{sha}"] = data
            packaged[sha] = {
                "agent_sha256": sha,
                "path": f"{BYTES}/{sha}",
                "content_type": row["content_type"],
                "agent_bytes": row["byte_size"],
                "bytes": len(data),
                "sha256": verifier.digest(data),
                "redactions": found,
                "cited_by": [],
            }
            marks.extend({"artifact": sha, **mark} for mark in found)
        packaged[sha]["cited_by"].append(f"{row['receipt']}:{row['direction']}")
    return [packaged[sha] for sha in sorted(packaged)], blobs, marks


def _manifest(
    answers: _Answers,
    source: Mapping[str, object],
    gathered: _Evidence,
    files: Mapping[str, bytes],
    marks: Sequence[Mapping],
) -> dict:
    """The index, and the one thing in the bundle that is about the bundle.

    `packaging` holds the wall clock and is the only key outside the digest, so
    criterion 5 -- two exports of unchanged rows agree apart from packaging
    metadata -- is something a recipient can check rather than something this
    docstring asserts.

    The redaction rules travel with it. A verifier that had to be told the
    patterns separately could not rescan, and a verifier that could not rescan
    would be taking the redaction on the same trust as the report.
    """
    document = {
        "schema": verifier.SCHEMA,
        "renderer": reporting.VERSION,
        "subject": answers.subject,
        "label": answers.label,
        "template": answers.template,
        "program": answers.slug,
        "source_digest": source.get("digest"),
        "required": sorted(gathered.required),
        "files": [
            {"path": path, "bytes": len(files[path]), "sha256": verifier.digest(files[path])}
            for path in sorted(files)
        ],
        "excluded": list(gathered.exclusions),
        "redactions": list(marks),
        "redaction_rules": list(gathered.rules),
    }
    return {
        **document,
        "digest": verifier.manifest_digest(document),
        verifier.PACKAGING: {"exported_at": _now()},
    }


def _verified(ledger: Ledger, answers: _Answers, out: Path) -> Report:
    """Run the shipped verifier over what was just written.

    The bundle's own check, on the bundle, before this command says it worked.
    Criterion 6 is an absence, and an absence nobody looked for is a claim: this
    is where the packed bytes are rescanned for anything the redaction should
    have taken out, which is the one failure that leaves a bundle looking exactly
    like a clean one.

    A refused bundle is removed rather than left where it was written. The
    refusal this exists to catch is `redaction_incomplete`, which says a packed
    file still carries something a rule was written to take out -- and a failed
    export that leaves that on disk under a directory named as a bundle has
    produced exactly the thing it refused to produce, with only an exit status
    between it and an operator who attaches it. `_empty` established the
    directory was this command's to fill, which is what makes it this command's
    to remove.
    """
    answered = verifier.verify(out)
    answers.bundle["verified"] = answered["ok"]
    if answered["ok"]:
        ledger.hold(
            "verify", f"the bundle passes the verifier it carries, {answered['files']} file(s)"
        )
        return _report(ledger, answers)

    for problem in answered["problems"]:
        ledger.fail(
            "verify",
            f"{problem['path']}: {problem['code']}, {problem['detail']}",
            code=INVALID_CONFIGURATION,
            source="verifier",
        )
    try:
        shutil.rmtree(out)
    except OSError as error:
        answers.bundle["removed"] = False
        ledger.fail(
            "bundle",
            f"{out} did not pass the verifier and could not be removed ({error}); "
            f"delete it by hand, nothing in it has been cleared to leave this harness",
            code=INVALID_CONFIGURATION,
            source="argument:--out",
        )
    else:
        answers.bundle["removed"] = True
        ledger.hold("bundle", f"{out} was removed; a bundle its own verifier refuses does not stay")
    return _report(ledger, answers)


def _json(value: object) -> bytes:
    """One document, in the one shape two exports of equal rows both produce."""
    return json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _empty(ledger: Ledger, out: Path) -> bool:
    """Whether the destination is somewhere a bundle may be written.

    Refused rather than merged into. A second export over the first would leave
    the artifacts of the first behind, the manifest would not name them, and the
    verifier would report a bundle somebody had added files to -- which is true,
    and is not what happened.
    """
    out = Path(out)
    if not out.exists():
        return True
    if not out.is_dir():
        ledger.fail(
            "bundle", f"{out} is not a directory",
            code=INVALID_CONFIGURATION, source="argument:--out",
        )
        return False
    if any(out.iterdir()):
        ledger.fail(
            "bundle",
            f"{out} is not empty; a bundle is written whole, and merging one into "
            f"another leaves files the manifest does not name",
            code=INVALID_CONFIGURATION,
            source="argument:--out",
        )
        return False
    return True


def _now() -> str:
    """When this export happened, to the second, in UTC.

    The only wall clock in the module, and the only thing in the manifest that
    the digest is not taken over.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The verify command
# ---------------------------------------------------------------------------


def verify(bundle: Path) -> Report:
    """Check one unpacked bundle, with no connection and no configuration.

    The same call a recipient makes by running `verify.py` out of the bundle,
    offered as a subcommand so that an operator who has this repository is not
    made to go and find the copy. It reads nothing but the directory, which is
    what makes the two the same check.
    """
    ledger = Ledger()
    answers = _Answers(VERIFY, subject=None, label=None, template=None)
    answered = verifier.verify(Path(bundle))
    answers.bundle = {
        "path": str(bundle),
        "files": answered["files"],
        "verified": answered["ok"],
        "problems": [problem["code"] for problem in answered["problems"]],
    }
    for problem in answered["problems"]:
        ledger.fail(
            "verify",
            f"{problem['path']}: {problem['code']}, {problem['detail']}",
            code=INVALID_CONFIGURATION,
            source="argument:bundle",
        )
    if answered["ok"]:
        ledger.hold(
            "verify",
            f"{answered['files']} file(s) are the bytes the manifest names, "
            f"nothing else is present, and no redaction rule matches what is left",
        )
    return _report(ledger, answers)


@dataclass(frozen=True)
class _Evidence:
    """What one subject's bundle is packed from, each list ordered by the database.

    Named fields rather than a dictionary of six keys. Everything below reaches
    into this and a misspelt key in any of them is a `KeyError` at export time on
    a machine nobody is watching, or -- for the two lookups that are `in` tests
    -- silently the wrong answer about which files a bundle owes.
    """

    receipts: list[dict]
    artifacts: list[dict]
    specifications: list[dict]
    exclusions: list[dict]
    rules: list[dict]
    required: list[str]


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    subject: str | None
    label: str | None
    template: str | None
    slug: str | None = None
    program_id: str | None = None
    bundle: dict = field(default_factory=dict)


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        subject=answers.subject,
        label=answers.label,
        template=answers.template,
        bundle=answers.bundle or None,
    )
