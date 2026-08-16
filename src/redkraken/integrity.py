"""The integrity gate: the operation behind `rk db verify`.

The corpus carries its own checkers — one per invariant, written by the
migration that introduced the invariant — and a registry naming all of them. The
defect that registry exists to prevent is a checker with no caller: nine of the
prototype's twelve had none, and four live defects survived in the gap. So there
is one gate, it runs everything registered, and every command that changes the
database ends by running it.

Three families answer three different questions. The baseline asks whether this
is the right server, running the right corpus, with the right settings. The role
catalogue asks whether the separation between the connections still holds. The
standing checks ask whether the rows themselves still satisfy what the schema
claims about them.

A caller may run fewer than three, because which families a connection is
entitled to run is part of what the role split means. What it may not do is run
fewer and report as though it ran all of them, so the families that ran are a
fact in the report rather than an assumption in the reader.

One invariant has no checker and cannot have one. `artifact_references.sha256`
claims that some bytes on a filesystem hash to it, and no registered check can
open a file. So the gate takes an optional store root and answers that claim the
only way it can be answered: by reading the bytes. Optional because the store is
not part of the database and a caller may not have it -- but a caller who names
one and gets a pass has been told something `run_standing_checks()` alone cannot
say.

Sealed wire artifacts are held against their bytes here too, and the gate holds
no key while it does it. That is a property of how they are filed: the envelope
is stored under the hash of the envelope, so "are these the bytes the row names"
is the same arithmetic for a ciphertext as for anything else. What the gate adds
for a seal is that the algorithm and nonce recorded in the row are the ones in
the envelope's own header -- a row describing a ciphertext other than the one on
disk is a broken record even when both halves are individually intact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from redkraken import pg, seal
from redkraken.outcome import (
    INTEGRITY_FAILED,
    SCHEMA_DRIFT,
    Ledger,
    Report,
    report,
)
from redkraken.store import Corrupt, Missing, Store


#: The registered surface, and what a caller has to supply to run it. The
#: baseline takes the on-disk corpus because the database cannot see the
#: filesystem: set equality both ways is the only way "no pending migrations"
#: can be a fact rather than a hope.
BASELINE = "check_server_baseline"
ROLE_CATALOGUE = "check_role_catalogue"
STANDING = "run_standing_checks"

#: How the standing family is asked, and the one seam that decides how narrow
#: the question is. `$1` names the Programs the Program-scoped checks are about:
#: NULL is every Program, which is what `rk db verify` means, and the empty
#: array is none of them, which is how a caller asks for the corpus-wide
#: invariants alone. `$2` drops the corpus-wide rows entirely, for a caller
#: holding a transaction open over one Program's write -- re-asking a corpus
#: invariant there would judge rows nobody has committed, and one that is
#: momentarily false mid-transaction would roll back a sound write.
#:
#: Which checks the Program list applies to is the registry's answer, not this
#: module's: `standing_checks.program_scoped` carries the flag and the checker
#: itself carries the filter, because only the checker knows which of its
#: columns holds a slug.
STANDING_QUERY = f"SELECT name, problems, detail FROM {STANDING}($1::text[], $2::boolean)"

#: The families by name, and the subset a runtime connection asks for. The role
#: catalogue is the runner's: `0029_roles_and_grants.sql` revokes it from PUBLIC
#: for that reason, and ticket 66 closes the default-privilege grant that
#: currently leaves it executable by `rk2_runtime` regardless. A command that
#: runs as the runtime therefore asks for the other two, so closing 66 narrows
#: the role rather than breaking the command.
BASELINE_FAMILY = "baseline"
ROLES_FAMILY = "roles"
STANDING_FAMILY = "standing"
ALL_FAMILIES = (BASELINE_FAMILY, ROLES_FAMILY, STANDING_FAMILY)
RUNTIME_FAMILIES = (BASELINE_FAMILY, STANDING_FAMILY)

#: The one check a restore is entitled to fail, and the one problem kind that
#: entitlement covers. `check_event_log_integrity()`'s part (d) compares a row's
#: `xmin` -- the transaction that produced the live tuple -- with the transaction
#: id recorded on its event. `pg_restore` rewrites every tuple in the restore's
#: own transaction while the events keep the ids of the writes that really
#: happened, so that comparison is false for every restored row by construction.
#: The evidence was destroyed by machinery outside the schema, which is the same
#: class as the `xmin = 2` exclusion the check already carries for frozen tuples:
#: the row degrades to part (b), an event exists for it at all, and that is said
#: rather than silently passed. Nothing else is tolerated -- a second problem
#: kind in the same check fails a restore exactly as it fails anything else.
RESTORE_ENTITLEMENT = "event_log_integrity"
RESTORED_ROW_PROBLEM = "row_last_write_unaccounted"
EVENT_LOG_PROBLEMS = "SELECT DISTINCT problem FROM check_event_log_integrity()"

#: Every recorded claim about the store, in the order an operator reads them.
#: No Program in the query: this is the gate, which asks whether the record as a
#: whole is still true, not what any one Program may reach.
REFERENCES = "SELECT label, sha256 FROM artifact_references ORDER BY label"

#: The other recorded claim about the store, and the one no reference names. A
#: sealed wire artifact has no label -- a label is an agent-reachable name and
#: that is the point -- so the gate reaches it through the seal itself.
SEALS = (
    "SELECT sha256, ciphertext_sha256, alg, encode(nonce, 'hex')"
    "  FROM artifact_seal ORDER BY sha256"
)


@dataclass(frozen=True)
class Check:
    """One check's answer: which family it came from, and whether it holds."""

    family: str
    name: str
    ok: bool
    detail: str

    @property
    def source(self) -> str:
        return f"{self.family}:{self.name}"


def run(
    connection: pg.Connection,
    expected: list[str] | None = None,
    families: Sequence[str] = ALL_FAMILIES,
    programs: Sequence[str] | None = None,
) -> tuple[Check, ...]:
    """Every registered check in the named families, in the order an operator reads them.

    `programs` narrows the standing family; see `STANDING_QUERY` for what naming
    Programs, or naming none, asks for.
    """
    checks: list[Check] = []

    if BASELINE_FAMILY in families:
        if expected is None:
            baseline = connection.execute(
                f"SELECT check_name, ok, detail FROM {BASELINE}(NULL)"
            )
        else:
            baseline = connection.execute(
                f"SELECT check_name, ok, detail FROM {BASELINE}($1::text[])",
                (pg.quote_array(expected),),
            )
        for name, ok, detail in baseline.rows:
            checks.append(Check(BASELINE_FAMILY, str(name), bool(ok), str(detail)))

    if ROLES_FAMILY in families:
        for name, ok, detail in connection.execute(
            f"SELECT check_name, ok, detail FROM {ROLE_CATALOGUE}()"
        ).rows:
            checks.append(Check(ROLES_FAMILY, str(name), bool(ok), str(detail)))

    if STANDING_FAMILY in families:
        checks.extend(_standing_checks(connection, programs, scoped_only=False))

    return tuple(checks)


def _standing_checks(
    connection: pg.Connection, programs: Sequence[str] | None, *, scoped_only: bool
) -> list[Check]:
    """The standing family, run and read back as Checks. No problems is a pass."""
    rows = connection.execute(
        STANDING_QUERY,
        (None if programs is None else pg.quote_array(list(programs)), scoped_only),
    ).rows
    checks = []
    for name, problems, detail in rows:
        count = int(problems)  # type: ignore[arg-type]
        checks.append(
            Check(
                STANDING_FAMILY,
                str(name),
                count == 0,
                f"{count} problem(s)" + (f": {detail}" if count and detail else ""),
            )
        )
    return checks


def program_checks(connection: pg.Connection, slug: str) -> tuple[Check, ...]:
    """The standing checks that are about one Program, asked about that one.

    Separate from `run` because the caller is: a command holding a transaction
    open over one Program's write, asking whether what it just wrote leaves that
    Program sound. Running the corpus-wide checks there would answer a question
    nobody asked against rows nobody has committed, and a corpus-wide invariant
    that is momentarily false mid-transaction would roll back a sound adoption.
    """
    return tuple(_standing_checks(connection, (slug,), scoped_only=True))


def entitled_by_a_restore(connection: pg.Connection, check: Check) -> Check:
    """The one failure a restored database may carry, held rather than failed.

    The problem kinds are asked of the checker itself rather than read out of the
    standing check's detail string, because what is tolerated is a kind and the
    kinds are a column. Only a restore may ask: `rk db verify` stays strict, so a
    database that fails this way without anyone restoring it is still a database
    whose emitter was switched off for a write.
    """
    if check.ok or check.family != STANDING_FAMILY or check.name != RESTORE_ENTITLEMENT:
        return check
    kinds = {str(problem) for (problem,) in connection.execute(EVENT_LOG_PROBLEMS).rows}
    if kinds - {RESTORED_ROW_PROBLEM}:
        return check
    return replace(
        check,
        ok=True,
        detail=f"{check.detail}: xmin evidence lost to the restore, rows otherwise accounted for",
    )


def verify(
    connection: pg.Connection,
    expected: list[str] | None = None,
    families: Sequence[str] = ALL_FAMILIES,
    store: Path | None = None,
    programs: Sequence[str] | None = None,
    *,
    restored: bool = False,
) -> Report:
    """Run the gate and report it.

    A database that has no gate to run is reported as drift rather than as an
    integrity failure: the checks did not fail, they were not there, and the
    thing to do about it is to migrate.

    A store root, when one is given, is verified alongside the registered checks
    and lands in the report as its own fact. It is not counted as a check,
    because `checks` is how many registered checkers ran and this is not one of
    them -- but it fails the gate exactly as they do, which is what makes a
    corrupt artifact something `rk db verify` refuses over rather than a thing
    only `rk artifact audit` ever notices.

    `programs` is passed through to `run`. A caller that names Programs is asking
    a narrower question than `rk db verify` asks and gets a narrower answer; the
    report does not pretend otherwise, because the families that ran are already
    a fact in it and this only changes what the standing family was asked about.
    `rk db verify` itself never names any, so the gate is as strict as it was.

    `restored` is the caller saying it has just loaded an archive, and it buys
    exactly one named tolerance -- see `RESTORE_ENTITLEMENT`. It is a parameter
    rather than something the gate works out for itself because no database can
    tell "these tuples were rewritten by a restore" from "these rows were written
    with the emitter switched off"; only the command that ran `pg_restore` knows.
    """
    ledger = Ledger()
    if not _installed(connection):
        ledger.fail(
            "integrity_gate",
            "this database carries no integrity checks; run `rk db migrate`",
            code=SCHEMA_DRIFT,
            source="database",
        )
        return report("db verify", ledger, checks=0)

    try:
        checks = run(connection, expected, families, programs)
        if restored:
            checks = tuple(entitled_by_a_restore(connection, check) for check in checks)
    except pg.DatabaseError as error:
        # A registered check that raises is itself a failure of the gate: the
        # invariant it names is unanswered, which is not the same as satisfied.
        ledger.fail(
            "integrity_gate",
            f"a registered check could not be run: {error}",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return report("db verify", ledger, checks=0)

    for check in checks:
        if check.ok:
            ledger.hold(check.source, check.detail)
        else:
            ledger.fail(
                check.source, check.detail, code=INTEGRITY_FAILED, source=check.source
            )

    failed = [check.source for check in checks if not check.ok]
    facts: dict[str, object] = {
        "checks": len(checks),
        "failed": failed,
        "families": sorted({check.family for check in checks}),
    }
    if store is not None:
        facts["artifacts"] = artifacts(ledger, connection, Path(store))
    return report("db verify", ledger, **facts)


def artifacts(ledger: Ledger, connection: pg.Connection, root: Path) -> dict:
    """Hold every recorded artifact against the bytes filed under its identifier.

    Every reference, not one Program's: a hash that names nothing is a broken
    record whoever recorded it, and a gate that only checked the Program in front
    of it would pass a database whose other half is gone.
    """
    if not connection.execute("SELECT to_regclass('artifact_references') IS NOT NULL").scalar():
        ledger.fail(
            "artifact_store",
            "this database records no artifact references; run `rk db migrate`",
            code=SCHEMA_DRIFT,
            source="database",
        )
        return {"sound": False, "verified": 0, "broken": [], "root": str(root)}

    try:
        rows = connection.execute(REFERENCES).rows
        sealed = connection.execute(SEALS).rows if _records_seals(connection) else []
    except pg.DatabaseError as error:
        ledger.fail(
            "artifact_store",
            f"the recorded artifacts could not be read: {error}",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return {"sound": False, "verified": 0, "broken": [], "root": str(root)}

    named = [{"label": str(label), "sha256": str(sha256)} for label, sha256 in rows]
    named += [
        {"label": f"seal {str(plaintext_sha)[:12]}", "sha256": str(ciphertext_sha)}
        for plaintext_sha, ciphertext_sha, _, _ in sealed
    ]
    keep = Store(root)
    answer = keep.verify(named)
    broken = answer["broken"]
    broken.extend(_headers(keep, sealed, {item["label"] for item in broken}))
    answer["verified"] = len(named) - len(broken)
    answer["sound"] = not broken
    if broken:
        ledger.fail(
            "artifact_store",
            f"{len(broken)} of {len(named)} recorded artifact(s) cannot be verified: "
            + "; ".join(f"{item['label']} ({item['detail']})" for item in broken),
            code=INTEGRITY_FAILED,
            source="artifact_store",
        )
    else:
        ledger.hold(
            "artifact_store",
            f"{len(named)} recorded artifact(s) hash to the identifier recorded for them"
            + (f", {len(sealed)} of them sealed" if sealed else ""),
        )
    return answer


def _records_seals(connection: pg.Connection) -> bool:
    """Whether this database has reached the migration that seals wire artifacts.

    Asked rather than assumed, because the gate has to run against a database
    mid-way through a corpus it is about to be told is out of date. The other
    families report that as drift; this one would report it as a missing table.
    """
    return bool(
        connection.execute(
            "SELECT to_regclass('artifact_seal') IS NOT NULL"
            "   AND EXISTS (SELECT 1 FROM information_schema.columns"
            "                WHERE table_schema = 'public' AND table_name = 'artifact_seal'"
            "                  AND column_name = 'ciphertext_sha256')"
        ).scalar()
    )


def _headers(keep: Store, sealed: Sequence[Sequence[object]], already: set[str]) -> list[dict]:
    """Hold each seal's recorded description against the envelope's own header.

    Key-free, and deliberately so: this asks whether the row and the file agree
    about which ciphertext this is, not whether the ciphertext still decrypts.
    The second question needs the root secret, and a gate that needed the root
    secret would be a gate an operator could only run while holding it.
    """
    broken = []
    for plaintext_sha, ciphertext_sha, alg, nonce in sealed:
        label = f"seal {str(plaintext_sha)[:12]}"
        if label in already:
            # The bytes are already reported missing or misfiled. A second
            # complaint about their header would be the same fault twice.
            continue
        try:
            envelope = seal.Sealed.decode(keep.load(str(ciphertext_sha)))
        except (Missing, Corrupt, seal.Tampered) as error:
            broken.append({"label": label, "detail": f"the sealed bytes are unreadable: {error}"})
            continue
        if not envelope.describes(alg, nonce):
            broken.append(
                {
                    "label": label,
                    "detail": (
                        f"recorded as {alg} under nonce {str(nonce)[:16]} and sealed as "
                        f"{envelope.alg} under nonce {envelope.nonce.hex()[:16]}"
                    ),
                }
            )
    return broken


def _installed(connection: pg.Connection) -> bool:
    """Whether this database has the gate at all.

    The standing runner is probed at the arity this module calls it with, not at
    the one every other caller uses: a database migrated to before ticket 81 has
    the no-argument form and would pass a laxer probe, then fail inside `run`
    with an undefined function rather than being reported as drift.
    """
    return bool(
        connection.execute(
            "SELECT to_regprocedure($1) IS NOT NULL AND to_regprocedure($2) IS NOT NULL"
            "   AND to_regprocedure($3) IS NOT NULL",
            (f"{BASELINE}(text[])", f"{ROLE_CATALOGUE}()", f"{STANDING}(text[],boolean)"),
        ).scalar()
    )
