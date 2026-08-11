"""The outcome vocabulary shared by every operator command.

A command reports what it observed as an ordered tuple of violations. The
process exit code is derived from the codes present, so a caller can act on the
outcome class without parsing prose.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


#: The shape of a rendered command result. Every command prints this version,
#: so a caller parsing one command's output can parse them all.
RESULT_SCHEMA_VERSION = 1

INVALID_CONFIGURATION = "invalid_configuration"
MISSING_DEPENDENCY = "missing_dependency"
UNSUPPORTED_VERSION = "unsupported_version"
DATABASE_UNREACHABLE = "database_unreachable"
INVALID_CORPUS = "invalid_corpus"
SCHEMA_DRIFT = "schema_drift"
INTEGRITY_FAILED = "integrity_failed"
BACKUP_FAILED = "backup_failed"
#: A target this harness was authorised to reach did not answer: the name
#: resolved to nothing, the socket would not open, the TLS layer would not come
#: up. Its own class because it is the one outcome here that says nothing is
#: wrong with this machine -- the configuration is valid, the capability was
#: minted and spent, and what failed is outside it. Reported as an invalid
#: configuration it would send an operator to fix a file that is correct.
TARGET_UNREACHABLE = "target_unreachable"

EXIT_OK = 0
EXIT_UNCLASSIFIED = 1
EXIT_USAGE = 2
EXIT_INVALID_CONFIGURATION = 3
EXIT_UNSUPPORTED_VERSION = 4
EXIT_MISSING_DEPENDENCY = 5
EXIT_DATABASE_UNREACHABLE = 6
EXIT_INVALID_CORPUS = 7
EXIT_SCHEMA_DRIFT = 8
EXIT_INTEGRITY_FAILED = 9
EXIT_BACKUP_FAILED = 10
EXIT_TARGET_UNREACHABLE = 11

#: Reported and exited first-to-last when several classes are observed at once.
#: An unsupported runtime outranks a missing dependency, which outranks operator
#: configuration, because the earlier fact explains the later ones. The database
#: classes continue the same order: a connection string that was refused
#: explains a database nobody reached, an unusable corpus explains a schema that
#: does not match it, and a schema that does not match explains an invariant
#: that no longer holds. An archive that was never produced is last because it
#: is reported by a command that stops before the gate, so it never competes
#: with an integrity failure for the same exit. A target nobody reached sorts
#: after all of them: every class above it is a statement about this machine, and
#: any one of them explains a request that did not complete better than the
#: outside world does.
PRECEDENCE = (
    (UNSUPPORTED_VERSION, EXIT_UNSUPPORTED_VERSION),
    (MISSING_DEPENDENCY, EXIT_MISSING_DEPENDENCY),
    (INVALID_CONFIGURATION, EXIT_INVALID_CONFIGURATION),
    (DATABASE_UNREACHABLE, EXIT_DATABASE_UNREACHABLE),
    (INVALID_CORPUS, EXIT_INVALID_CORPUS),
    (SCHEMA_DRIFT, EXIT_SCHEMA_DRIFT),
    (INTEGRITY_FAILED, EXIT_INTEGRITY_FAILED),
    (BACKUP_FAILED, EXIT_BACKUP_FAILED),
    (TARGET_UNREACHABLE, EXIT_TARGET_UNREACHABLE),
)


@dataclass(frozen=True, order=True)
class Violation:
    """One refused fact: its class, where it was observed and what is wrong."""

    code: str
    source: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "source": self.source, "detail": self.detail}


@dataclass(frozen=True)
class Assertion:
    """One statement a command made and whether it holds."""

    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class Ledger:
    """Collects every assertion, and a violation for each one that fails.

    Recording both together is what keeps a refusal explicable: an operator
    reading the result can always find the assertion behind a violation. Shared
    by every operator command so that a readiness refusal, a schema refusal and
    an integrity refusal are the same shape.
    """

    assertions: list[Assertion] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    def hold(self, name: str, detail: str) -> None:
        self.assertions.append(Assertion(name=name, ok=True, detail=detail))

    def fail(self, name: str, detail: str, *, code: str, source: str) -> None:
        self.assertions.append(Assertion(name=name, ok=False, detail=detail))
        self.violations.append(Violation(code=code, source=source, detail=detail))

    def refuse(self, name: str, detail: str, refusals: Iterable[Violation]) -> None:
        """Record an assertion refused by violations raised elsewhere."""
        self.assertions.append(Assertion(name=name, ok=False, detail=detail))
        self.violations.extend(refusals)


@dataclass(frozen=True)
class Report:
    """What one operator command observed.

    The same shape for every command that talks to a database, so an operator
    scripting `rk db migrate` and `rk db verify` parses one document, not two.
    `facts` are the command's own answers — how many migrations were applied,
    which checks ran — and are rendered beside the fixed keys rather than under
    them, because that is where an operator reading the output looks for them.
    """

    command: str
    assertions: tuple[Assertion, ...] = ()
    violations: tuple[Violation, ...] = ()
    facts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def exit_code(self) -> int:
        return exit_code(self.violations)

    def as_dict(self) -> dict:
        return {
            **self.facts,
            "schema_version": RESULT_SCHEMA_VERSION,
            "command": self.command,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "assertions": [assertion.as_dict() for assertion in self.assertions],
            "violations": [violation.as_dict() for violation in self.violations],
        }


def report(command: str, ledger: Ledger, **facts: object) -> Report:
    """The report one command's ledger and answers make."""
    return Report(
        command=command,
        assertions=tuple(ledger.assertions),
        violations=ordered(ledger.violations),
        facts=dict(facts),
    )


def exit_code(violations: tuple[Violation, ...]) -> int:
    """The status a caller acts on: the most fundamental class observed.

    A violation whose class this table does not know still exits non-zero. The
    alternative — reporting a refusal and exiting `0` — would let a caller read
    a refused configuration as a ready one, which is the one failure this
    function exists to prevent.
    """
    if not violations:
        return EXIT_OK
    codes = {violation.code for violation in violations}
    for code, status in PRECEDENCE:
        if code in codes:
            return status
    return EXIT_UNCLASSIFIED


def ordered(violations: Iterable[Violation]) -> tuple[Violation, ...]:
    """Violations in precedence order, then by where they were observed."""
    ranks = {code: rank for rank, (code, _) in enumerate(PRECEDENCE)}
    return tuple(
        sorted(violations, key=lambda item: (ranks.get(item.code, len(ranks)), item.source, item.detail))
    )
