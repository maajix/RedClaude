"""Local runtime readiness: the operation behind `rk doctor`.

`diagnose` answers one question — can this machine be trusted to run a Program
— by asserting the interpreter, the declared runtime requirements and, when the
operator supplies one, a Program configuration. It reads; it never creates
state, contacts a target or starts an Agent run. Every fact it reports is a
name, a version, a count or a digest.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
from dataclasses import dataclass
from pathlib import Path

from redkraken import __version__, config, outcome
from redkraken.outcome import (
    MISSING_DEPENDENCY,
    RESULT_SCHEMA_VERSION,
    UNSUPPORTED_VERSION,
    Assertion,
    Ledger,
    Violation,
)


#: The interpreter range this runtime is exercised against, as an inclusive
#: minimum and an exclusive maximum. `pyproject.toml` declares the same range.
SUPPORTED_PYTHON = ((3, 14), (3, 15))

#: Interpreter modules the runtime needs that a minimal build may omit.
REQUIRED_MODULES = ("ssl", "tomllib")

#: Production dependencies as exact pins, mirroring `pyproject.toml`.
REQUIRED_DISTRIBUTIONS: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Requirements:
    """What a machine must provide before it can run a Program.

    A value rather than a lookup, so a diagnosis can be run against a stated
    requirement table — including one no machine here satisfies — without
    disturbing the interpreter it runs on.
    """

    modules: tuple[str, ...] = REQUIRED_MODULES
    distributions: tuple[tuple[str, str], ...] = REQUIRED_DISTRIBUTIONS


#: The requirements this application declares. Operator commands use these.
REQUIREMENTS = Requirements()


@dataclass(frozen=True)
class Diagnosis:
    """What one `rk doctor` run observed."""

    application_version: str
    python_version: str
    assertions: tuple[Assertion, ...]
    configuration: dict | None
    violations: tuple[Violation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def exit_code(self) -> int:
        return outcome.exit_code(self.violations)

    def as_dict(self) -> dict:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "command": "doctor",
            "ok": self.ok,
            "exit_code": self.exit_code,
            "application_version": self.application_version,
            "python_version": self.python_version,
            "supported_python": supported_python(),
            "assertions": [assertion.as_dict() for assertion in self.assertions],
            "configuration": self.configuration,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def supported_python() -> str:
    """The supported interpreter range in the form `pyproject.toml` declares."""
    minimum, below = SUPPORTED_PYTHON
    return f">={_version(minimum)},<{_version(below)}"


def diagnose(
    configuration_path: Path | None = None,
    *,
    python_version: tuple[int, ...] | None = None,
    requirements: Requirements = REQUIREMENTS,
) -> Diagnosis:
    """Report local readiness, and the supplied configuration when there is one.

    The observed interpreter version and the declared requirements are
    parameters so that the negative outcomes stay reachable from tests without
    corrupting the running interpreter. Operator commands supply neither.
    """
    version = tuple(python_version) if python_version is not None else tuple(sys.version_info[:3])
    ledger = Ledger()

    _assert_python(ledger, version)
    _assert_modules(ledger, requirements.modules)
    _assert_distributions(ledger, requirements.distributions)
    summary = _assert_configuration(ledger, configuration_path)

    return Diagnosis(
        application_version=__version__,
        python_version=_version(version),
        assertions=tuple(ledger.assertions),
        configuration=summary,
        violations=outcome.ordered(ledger.violations),
    )


def _version(parts: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in parts)


def _assert_python(ledger: Ledger, version: tuple[int, ...]) -> None:
    minimum, below = SUPPORTED_PYTHON
    rendered = _version(version)
    if minimum <= tuple(version[:2]) < below:
        ledger.hold("python_version", f"{rendered} within {supported_python()}")
        return
    ledger.fail(
        "python_version",
        f"interpreter {rendered} is outside the supported range {supported_python()}",
        code=UNSUPPORTED_VERSION,
        source="runtime:python",
    )


def _assert_modules(ledger: Ledger, modules: tuple[str, ...]) -> None:
    for name in sorted(modules):
        try:
            importlib.import_module(name)
        except (ImportError, ValueError):
            # ValueError covers an empty or malformed name: a broken
            # requirement table rather than a module this machine lacks.
            # Either way the requirement is not satisfied here.
            ledger.fail(
                f"module:{name}",
                f"required interpreter module {name} cannot be imported",
                code=MISSING_DEPENDENCY,
                source=f"runtime:module:{name}",
            )
        else:
            ledger.hold(f"module:{name}", "importable")


def _assert_distributions(ledger: Ledger, distributions: tuple[tuple[str, str], ...]) -> None:
    for name, pinned in sorted(distributions):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed == pinned:
            ledger.hold(f"distribution:{name}", pinned)
            continue
        ledger.fail(
            f"distribution:{name}",
            f"declared dependency {name}=={pinned} is not installed"
            if installed is None
            else f"declared dependency {name}=={pinned} is installed at {installed}",
            code=MISSING_DEPENDENCY,
            source=f"runtime:distribution:{name}",
        )


def _assert_configuration(ledger: Ledger, path: Path | None) -> dict | None:
    if path is None:
        ledger.hold("configuration", "no configuration supplied")
        return None
    configuration, refusals = config.load(path)
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return None
    ledger.hold("configuration", f"valid at schema version {configuration.schema_version}")
    return configuration.summary()
