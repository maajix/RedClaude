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
"""

from __future__ import annotations

from dataclasses import dataclass

from redkraken import pg
from redkraken.outcome import (
    INTEGRITY_FAILED,
    SCHEMA_DRIFT,
    Ledger,
    Report,
    report,
)


#: The registered surface, and what a caller has to supply to run it. The
#: baseline takes the on-disk corpus because the database cannot see the
#: filesystem: set equality both ways is the only way "no pending migrations"
#: can be a fact rather than a hope.
BASELINE = "check_server_baseline"
ROLE_CATALOGUE = "check_role_catalogue"
STANDING = "run_standing_checks"


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


def run(connection: pg.Connection, expected: list[str] | None = None) -> tuple[Check, ...]:
    """Every registered check, in one pass, in the order an operator reads them."""
    checks: list[Check] = []

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
        checks.append(Check("baseline", str(name), bool(ok), str(detail)))

    for name, ok, detail in connection.execute(
        f"SELECT check_name, ok, detail FROM {ROLE_CATALOGUE}()"
    ).rows:
        checks.append(Check("roles", str(name), bool(ok), str(detail)))

    for name, problems, detail in connection.execute(
        f"SELECT name, problems, detail FROM {STANDING}()"
    ).rows:
        count = int(problems)
        checks.append(
            Check(
                "standing",
                str(name),
                count == 0,
                f"{count} problem(s)" + (f": {detail}" if count and detail else ""),
            )
        )

    return tuple(checks)


def verify(connection: pg.Connection, expected: list[str] | None = None) -> Report:
    """Run the gate and report it.

    A database that has no gate to run is reported as drift rather than as an
    integrity failure: the checks did not fail, they were not there, and the
    thing to do about it is to migrate.
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
        checks = run(connection, expected)
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
    return report(
        "db verify",
        ledger,
        checks=len(checks),
        failed=failed,
        families=sorted({check.family for check in checks}),
    )


def _installed(connection: pg.Connection) -> bool:
    """Whether this database has the gate at all."""
    return bool(
        connection.execute(
            "SELECT to_regprocedure($1) IS NOT NULL AND to_regprocedure($2) IS NOT NULL"
            "   AND to_regprocedure($3) IS NOT NULL",
            (f"{BASELINE}(text[])", f"{ROLE_CATALOGUE}()", f"{STANDING}()"),
        ).scalar()
    )
