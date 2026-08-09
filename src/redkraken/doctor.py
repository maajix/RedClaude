"""Local runtime readiness: the operation behind `rk doctor`.

`diagnose` answers one question — can this machine be trusted to run a Program
— by checking the interpreter, the declared runtime dependencies and, when the
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
from redkraken.outcome import MISSING_DEPENDENCY, UNSUPPORTED_VERSION, Violation


RESULT_SCHEMA_VERSION = 1

#: The interpreter range this runtime is exercised against, as an inclusive
#: minimum and an exclusive maximum. `pyproject.toml` declares the same range.
SUPPORTED_PYTHON = ((3, 14), (3, 15))

#: Interpreter modules the runtime needs that a minimal build may omit.
REQUIRED_MODULES = ("ssl", "tomllib")

#: Production dependencies as exact pins, mirroring `pyproject.toml`.
REQUIRED_DISTRIBUTIONS: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class Diagnosis:
    """What one `rk doctor` run observed."""

    application_version: str
    python_version: str
    checks: tuple[Check, ...]
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
            "checks": [check.as_dict() for check in self.checks],
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
    modules: tuple[str, ...] = REQUIRED_MODULES,
    distributions: tuple[tuple[str, str], ...] = REQUIRED_DISTRIBUTIONS,
) -> Diagnosis:
    """Report local readiness, and the supplied configuration when there is one.

    The interpreter version and dependency tables are parameters so that the
    negative outcomes stay reachable from tests without corrupting the running
    interpreter. Operator commands always use the declared defaults.
    """
    version = tuple(python_version) if python_version else tuple(sys.version_info[:3])
    checks: list[Check] = []
    violations: list[Violation] = []

    _check_python(version, checks, violations)
    _check_modules(modules, checks, violations)
    _check_distributions(distributions, checks, violations)
    summary = _check_configuration(configuration_path, checks, violations)

    return Diagnosis(
        application_version=__version__,
        python_version=_version(version),
        checks=tuple(checks),
        configuration=summary,
        violations=tuple(sorted(violations)),
    )


def _version(parts: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in parts)


def _check_python(
    version: tuple[int, ...], checks: list[Check], violations: list[Violation]
) -> None:
    minimum, below = SUPPORTED_PYTHON
    ok = minimum <= tuple(version[:2]) < below
    rendered = _version(version)
    checks.append(
        Check(
            name="python_version",
            ok=ok,
            detail=f"{rendered} {'within' if ok else 'outside'} {supported_python()}",
        )
    )
    if not ok:
        violations.append(
            Violation(
                code=UNSUPPORTED_VERSION,
                source="runtime:python",
                detail=f"interpreter {rendered} is outside the supported range {supported_python()}",
            )
        )


def _check_modules(
    modules: tuple[str, ...], checks: list[Check], violations: list[Violation]
) -> None:
    for name in sorted(modules):
        try:
            importlib.import_module(name)
        except ImportError:
            checks.append(Check(name=f"module:{name}", ok=False, detail="cannot be imported"))
            violations.append(
                Violation(
                    code=MISSING_DEPENDENCY,
                    source=f"runtime:module:{name}",
                    detail=f"required interpreter module {name} cannot be imported",
                )
            )
        else:
            checks.append(Check(name=f"module:{name}", ok=True, detail="importable"))


def _check_distributions(
    distributions: tuple[tuple[str, str], ...],
    checks: list[Check],
    violations: list[Violation],
) -> None:
    for name, pinned in sorted(distributions):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed == pinned:
            checks.append(Check(name=f"distribution:{name}", ok=True, detail=pinned))
            continue
        detail = (
            f"declared dependency {name}=={pinned} is not installed"
            if installed is None
            else f"declared dependency {name}=={pinned} is installed at {installed}"
        )
        checks.append(Check(name=f"distribution:{name}", ok=False, detail=detail))
        violations.append(
            Violation(
                code=MISSING_DEPENDENCY, source=f"runtime:distribution:{name}", detail=detail
            )
        )


def _check_configuration(
    path: Path | None, checks: list[Check], violations: list[Violation]
) -> dict | None:
    if path is None:
        checks.append(
            Check(name="configuration", ok=True, detail="no configuration supplied")
        )
        return None
    configuration, refusals = config.load(path)
    violations.extend(refusals)
    if configuration is None:
        checks.append(
            Check(
                name="configuration",
                ok=False,
                detail=f"refused by {len(refusals)} violation(s)",
            )
        )
        return None
    checks.append(
        Check(
            name="configuration",
            ok=True,
            detail=f"valid at schema version {configuration.schema_version}",
        )
    )
    return configuration.summary()
