"""The outcome vocabulary shared by every operator command.

A command reports what it observed as an ordered tuple of violations. The
process exit code is derived from the codes present, so a caller can act on the
outcome class without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass


INVALID_CONFIGURATION = "invalid_configuration"
MISSING_DEPENDENCY = "missing_dependency"
UNSUPPORTED_VERSION = "unsupported_version"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INVALID_CONFIGURATION = 3
EXIT_UNSUPPORTED_VERSION = 4
EXIT_MISSING_DEPENDENCY = 5

#: Reported first-to-last when several classes are observed at once. An
#: unsupported runtime outranks a missing dependency, which outranks operator
#: configuration, because the earlier fact explains the later ones.
PRECEDENCE = (
    (UNSUPPORTED_VERSION, EXIT_UNSUPPORTED_VERSION),
    (MISSING_DEPENDENCY, EXIT_MISSING_DEPENDENCY),
    (INVALID_CONFIGURATION, EXIT_INVALID_CONFIGURATION),
)


@dataclass(frozen=True, order=True)
class Violation:
    """One refused fact: its class, where it was observed and what is wrong."""

    code: str
    source: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "source": self.source, "detail": self.detail}


def exit_code(violations: tuple[Violation, ...]) -> int:
    codes = {violation.code for violation in violations}
    for code, status in PRECEDENCE:
        if code in codes:
            return status
    return EXIT_OK
