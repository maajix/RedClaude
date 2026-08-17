"""`rk import`: read one redacted v1 export without inheriting its conclusions.

043 packs a bundle so that somebody outside this harness can check it. This is
the inverse and is deliberately not symmetric, because the two directions are
not the same problem. An export leaves with everything needed to check it. A v1
export arrives with almost nothing: v1 kept no Receipt for an attempt, no Tool
Run behind an Artifact, no Agent run behind a Playbook choice, and no record of
which of its own words -- `confirmed`, `exploited`, `tested`, `completed` --
were ever produced by running anything. So the question this module answers is
not "is the export intact" but "how much of it can be believed", and the answer
it gives is deliberately small.

Four things cross, and nothing else does.

*The configuration.* Validated against this Program's compiled scope, reported
per entry, and applied to nothing. A v1 engagement's scope is that engagement's
account of what it was allowed to touch; this Program's scope is the operator's
account of what this Program may touch, and only the second one has ever set a
rule. An import that widened scope would be an engagement authorising itself
from a file.

*The Surface.* Domains, hosts and applications, converged on the dedup keys the
runtime already uses. Not endpoints and not parameters: a route recovered from a
v1 database is a claim about a request nothing in the export witnessed, and
criterion 3 says such a row is an unverified proposal rather than Surface.

*The findings.* One hint per subject and Property class family, with a count and
a severity ceiling, and no leaf class, status or title anywhere. That is story
193 exactly -- "used only as prioritization evidence at family granularity, so
that missing Playbook and Skill provenance is not fabricated".

*The artifacts.* Bytes the export retained, filed under their own hash at a
fourth reference kind, and only when the bytes hash to what the export said and
no redaction rule matches them. `imported` is not in `artifact.KINDS`, which is
the vocabulary `rk artifact put` offers: an operator who could mint an imported
reference by hand could make any demoted row look correlated, and the one thing
that turns a proposal into imported Surface here is whether such a reference
exists.

The rest -- Receipts, Tool Runs, attempts, Hypotheses, Findings, Test runs,
pivot stamps -- is not written, is not writable through this path, and is what
`check_v1_import` stands watch over.

Criterion 1 is a property of the arguments. `--from` is required and is a
directory an operator names. Nothing here searches, defaults, globs or reads an
engagement directory it was not handed, and there is no configuration key that
supplies one: an import that could find its own input is an import that can
happen without anybody deciding it should.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from redkraken import artifact, config, evidence, migrate, pg, program, reporting, store, verifier
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


__all__ = [
    "COMMAND",
    "FACTS",
    "KIND",
    "MANIFEST",
    "PAYLOAD",
    "SCHEMA",
    "STATES",
    "Export",
    "Refused",
    "read",
    "run",
]


COMMAND = "import"

#: What an export must declare itself to be. An unknown schema stops the read
#: rather than being interpreted, for the reason `verifier.SCHEMA` gives: a
#: reader that guessed at a layout it did not know would answer confidently
#: about a document it had misread, and here the answer becomes rows.
SCHEMA = "rk2-v1-export/1"

#: The index, which is not one of the files it indexes.
MANIFEST = "manifest.json"

#: Which document carries which list, and the key `record_v1_import` reads it
#: under. One mapping rather than four constants, because the four are read in a
#: loop and a fifth payload is a row here rather than a fifth branch.
PAYLOAD = {
    "scope": "configuration.json",
    "surface": "surface.json",
    "findings": "findings.json",
    "artifacts": "artifacts.json",
}

#: What can be true of the bytes behind one artifact record. Every one of the
#: four is reported and only the first is filed; the other three are the shapes
#: an export can be wrong in that criterion 6 asks for fixtures of.
STATES = ("retained", "redacted", "stale", "absent")

#: The reference kind an import files under. Not `runtime`: this harness did not
#: store these bytes in the course of its own work, and a source analysis tool
#: pointed at `source` must not reach them on the strength of a word.
KIND = "imported"

#: What both halves of the command report, refused or performed.
FACTS = ("program_id", "program_slug", "source", "imported")

RECORD = "SELECT record_v1_import($1::jsonb, $2::jsonb)"


class Refused(Exception):
    """An export this module will not read, with the sentence saying why."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(detail)
        self.path = path
        self.detail = detail


@dataclass(frozen=True)
class Export:
    """One export, read and checked, before anything has been decided about it.

    Frozen and separate from the import itself so that criterion 1 is testable
    without a database: `read` opens a directory, refuses everything it should
    refuse, and reaches no connection, no store and no Program.
    """

    root: Path
    schema: str
    program: str
    exported_at: str
    digest: str
    lists: dict[str, list]
    files: dict[str, dict]

    @property
    def source(self) -> dict:
        """The export's identity, in the three keys `record_v1_import` reads."""
        return {
            "schema": self.schema,
            "source_sha256": self.digest,
            "exported_at": self.exported_at,
        }


def read(source: Path) -> Export:
    """One export directory, held against its own manifest.

    Five refusals, and each one is a way an export can be wrong that would
    otherwise become rows: no manifest, a schema this reader does not know, a
    manifest that is not what it says it is, a named file that is missing or is
    not the bytes named, and a file present that the manifest does not name.

    The last is the one worth stating. A directory somebody added a file to is a
    directory whose provenance is no longer the export's, and every per-file
    check above it passes -- which is exactly `verifier._missing_from_manifest`'s
    argument, made here because an import is a bundle read in the other
    direction.
    """
    source = Path(source)
    try:
        document = json.loads((source / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(MANIFEST, f"there is no {MANIFEST} in {source}") from None
    except (OSError, ValueError) as error:
        raise Refused(MANIFEST, f"{MANIFEST} could not be read: {error}") from None
    if not isinstance(document, dict):
        raise Refused(MANIFEST, f"{MANIFEST} is not an object")

    if document.get("schema") != SCHEMA:
        raise Refused(
            MANIFEST,
            f"the export declares itself {document.get('schema')!r} and this reader "
            f"knows {SCHEMA!r}",
        )
    if document.get("digest") != verifier.manifest_digest(document):
        raise Refused(MANIFEST, "the manifest is not what it says it is")
    for key in ("program", "exported_at"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise Refused(MANIFEST, f"the manifest states no {key}")

    listed = _listed(source, document)
    for path in sorted(listed):
        _bytes(source, path, listed[path])
    for name in sorted(
        item.relative_to(source).as_posix() for item in source.rglob("*") if item.is_file()
    ):
        if name != MANIFEST and name not in listed:
            raise Refused(name, "it is in the export and the manifest does not name it")

    return Export(
        root=source,
        schema=str(document["schema"]),
        program=str(document["program"]).strip(),
        exported_at=str(document["exported_at"]).strip(),
        digest=str(document["digest"]),
        lists={key: _list(source, listed, PAYLOAD[key]) for key in PAYLOAD},
        files=listed,
    )


def _listed(source: Path, document: Mapping) -> dict[str, dict]:
    """The manifest's file entries, keyed by path, with the four documents there.

    A missing payload document is refused rather than read as an empty list. An
    export that omits `findings.json` and one that carries an empty one are
    different claims, and treating them alike would let a truncated export import
    quietly as a small one.
    """
    entries = document.get("files")
    if not isinstance(entries, list):
        raise Refused(MANIFEST, "the manifest names no files")
    listed: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise Refused(MANIFEST, "a file entry names no path")
        listed[entry["path"]] = entry
    missing = sorted(name for name in PAYLOAD.values() if name not in listed)
    if missing:
        raise Refused(MANIFEST, f"the manifest names no {', '.join(missing)}")
    return listed


def _bytes(source: Path, path: str, entry: Mapping) -> bytes:
    """One named file, checked to be the size and the bytes the manifest names."""
    if path.startswith("/") or ".." in Path(path).parts:
        raise Refused(path, "a manifest entry names a path outside the export")
    try:
        data = (source / path).read_bytes()
    except FileNotFoundError:
        raise Refused(path, "the manifest names it and it is not here") from None
    except OSError as error:
        raise Refused(path, f"it could not be read: {error}") from None
    if len(data) != entry.get("bytes"):
        raise Refused(path, f"{entry.get('bytes')} byte(s) recorded, {len(data)} here")
    found = store.digest(data)
    if found != entry.get("sha256"):
        raise Refused(path, f"{entry.get('sha256')} recorded, {found} here")
    return data


def _list(source: Path, listed: Mapping[str, dict], path: str) -> list:
    """One payload document, which is a list of records or is a refusal."""
    try:
        parsed = json.loads(_bytes(source, path, listed[path]).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise Refused(path, f"it is not readable as JSON: {error}") from None
    if not isinstance(parsed, list):
        raise Refused(path, "it is not a list of records")
    for ordinal, record in enumerate(parsed):
        if not isinstance(record, dict) or not str(record.get("ref", "")).strip():
            raise Refused(path, f"record {ordinal} carries no ref")
    return parsed


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    source: Path,
    *,
    root: Path,
) -> Report:
    """Read one operator-named export into one Program, and report every record."""
    ledger = Ledger()
    answers = _Answers(COMMAND, source=str(source))

    try:
        export = read(Path(source))
    except Refused as refusal:
        ledger.fail(
            "export",
            f"{refusal.path}: {refusal.detail}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return _report(ledger, answers)
    answers.digest = export.digest
    ledger.hold(
        "export",
        f"{export.schema} taken at {export.exported_at} under {export.digest[:12]}, "
        f"{len(export.files)} file(s): "
        + ", ".join(f"{len(export.lists[key])} {key}" for key in sorted(export.lists)),
    )

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, answers)
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")

    # Criterion 5's isolation, asked before a connection is opened. An export
    # taken from one engagement and imported into another Program is the whole
    # of the cross-Program failure at the coarse end, and the manifest is where
    # it is cheapest to see. The record-level half is the writer's, because an
    # export whose manifest agrees can still carry one row belonging elsewhere.
    if export.program != answers.slug:
        ledger.fail(
            "export",
            f"the export was taken from program {export.program!r} and this "
            f"configuration names {answers.slug!r}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return _report(ledger, answers)

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
        return _recorded(ledger, answers, connection, export, root=Path(root))


def _recorded(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    export: Export,
    *,
    root: Path,
) -> Report:
    """File what survived and record the whole export, in one transaction.

    One transaction because the two halves are one claim. `record_v1_import`
    decides whether a Surface row is imported or demoted by asking whether this
    Program holds an imported reference to the bytes behind it, and it refuses an
    artifact record whose claimed state and whose reference disagree -- so a
    filing that committed without the recording would leave a reference the audit
    never accounted for, and a recording that committed without the filing would
    be refused by its own check on the way in.

    What a rollback does not undo is the store, because `put` writes a file
    before any row cites it, and a refused import can leave bytes behind that
    nothing references. Stated rather than swept: they are bytes the operator
    already had, in the directory they pointed at, now also under their own hash
    with no row citing them, and every artifact that reached `put` is one no
    redaction rule matched -- `_filed` files nothing a rule touched, so the
    residue of a failure cannot contain a secret. What matters for the audit is
    the other direction, and that holds: no reference outlives the refusal.

    The redaction rules come from `evidence`, which is where `redact` is: the
    three columns are that function's argument and reading them through a second
    query here would be a second opinion about what it takes.
    """
    rules = list(connection.execute(evidence.RULES).dicts())
    keep = store.Store(root)
    try:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {COMMAND}",))
            artifacts, counted = _filed(connection, keep, answers.program_id, export, rules)
            payload = {**export.lists, "artifacts": artifacts}
            answered = connection.execute(
                RECORD, (json.dumps(export.source), json.dumps(payload))
            ).scalar()
    except pg.DatabaseError as error:
        ledger.fail(
            "import",
            f"the export was refused: {_sentence(error)}",
            code=INVALID_CONFIGURATION,
            source="record_v1_import",
        )
        return _report(ledger, answers)
    except OSError as error:
        ledger.fail(
            "artifact",
            f"an artifact this export retained could not be filed: {error}",
            code=INVALID_CONFIGURATION,
            source="artifact_store",
        )
        return _report(ledger, answers)

    recorded = json.loads(str(answered))
    answers.imported = {
        "path": str(export.root),
        "source_sha256": export.digest,
        "exported_at": export.exported_at,
        **recorded,
        "artifacts": counted,
    }
    ledger.hold(
        "artifacts",
        ", ".join(f"{counted[state]} {state}" for state in STATES),
    )
    if recorded.get("repeated"):
        ledger.hold(
            "import",
            f"this export was already imported as {recorded['import']}; "
            f"the report is the one that import gave",
        )
    else:
        ledger.hold(
            "import",
            f"{recorded['records']} record(s) under import {recorded['import']}: "
            + ", ".join(
                f"{count} {word}" for word, count in sorted(recorded["by_disposition"].items())
            ),
        )
    return _report(ledger, answers)


def _filed(
    connection: pg.Connection,
    keep: store.Store,
    program_id: str,
    export: Export,
    rules: Sequence[Mapping[str, str]],
) -> tuple[list[dict], dict[str, int]]:
    """Every artifact the export offers: what became of its bytes, and the count.

    Four outcomes and one of them stores anything.

    `absent` -- the export names bytes it does not carry. v1 pruned its store
    and kept the row, which is most of what a real export looks like.

    `stale` -- the bytes are here and are not the bytes the export says they
    are. The manifest check above cannot see this: the manifest is a claim about
    the file in the directory and this is v1's claim about what it stored, so an
    export repacked around a modified artifact passes one and fails the other.
    That is the whole of why both are checked.

    `redacted` -- a rule in `redaction_rules` matches. The bytes are not filed,
    not hashed into a row and not carried anywhere: an import is the one path by
    which material this harness never chose to collect arrives, and the rules are
    the standing answer to what may not be kept. The count says how many, which
    is the difference between a redaction and a silent drop.

    `retained` -- filed under its own hash at kind `imported`.
    """
    offered: list[dict] = []
    counted = dict.fromkeys(STATES, 0)
    for record in export.lists["artifacts"]:
        ref = str(record["ref"]).strip()
        claimed = str(record.get("sha256", "")).strip()
        state = "absent"
        path = str(record.get("path", "")).strip()
        if path in export.files:
            data = _bytes(export.root, path, export.files[path])
            if store.digest(data) != claimed:
                state = "stale"
            elif evidence.redact(data, rules)[1]:
                state = "redacted"
            else:
                artifact.filed(
                    connection,
                    keep,
                    program_id,
                    data,
                    kind=KIND,
                    content_type=_content_type(record),
                )
                state = "retained"
        counted[state] += 1
        offered.append({"ref": ref, "sha256": claimed, "state": state})
    return offered, counted


def _content_type(record: Mapping) -> str | None:
    """What the export says these bytes are, if it says anything usable."""
    given = str(record.get("content_type", "")).strip()
    return given[:200] or None


def _sentence(error: pg.DatabaseError) -> str:
    """The server's own words, which are the refusal an operator acts on."""
    return str(error).strip().splitlines()[0] if str(error).strip() else repr(error)


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    source: str
    slug: str | None = None
    program_id: str | None = None
    digest: str | None = None
    imported: dict = field(default_factory=dict)


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        source={"path": answers.source, "digest": answers.digest},
        imported=answers.imported or None,
    )
