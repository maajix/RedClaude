"""Run one trusted host program and read what it said.

Two places in this runtime shell out to a program installed on the operator's
own machine rather than into a container: `rk db dump` reaching `pg_dump`, and
the vault reaching `op`. Neither is isolation -- an isolated child is
`isolation.run_tool`, and it exists because the thing being run is not trusted.
These two are trusted, and what they need instead is the same three things:
a curated environment rather than an inherited one, a timeout so an unattended
campaign fails rather than hangs, and a bounded piece of the child's own words
to put in a refusal.

Those three lived twice and had already drifted apart in the bound, which is
the usual way a second copy announces itself. They live here once.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping


def run(
    binary: str,
    arguments: list[str],
    *,
    environment: Mapping[str, str],
    timeout: float,
    stdin: int | None = subprocess.DEVNULL,
) -> subprocess.CompletedProcess | str:
    """Run the program once, or say in one sentence why it could not run.

    A string back is "it never ran, or never finished"; a `CompletedProcess` is
    "it ran, and its status is now the caller's question". The two are different
    enough that a caller which forgot to separate them fails at the first
    attribute rather than misreading a failure as an answer.

    `stdin` is closed by default. A program that prompts -- for a password, for
    a biometric unlock -- is one an unattended campaign otherwise waits on until
    the timeout instead of refusing.
    """
    try:
        return subprocess.run(
            [binary, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(environment),
            stdin=stdin,
        )
    except subprocess.TimeoutExpired:
        return f"{binary} did not finish within {timeout:g} seconds"
    except OSError as error:
        return f"{binary} could not be run: {error.strerror or error}"


def collapse(stderr: str) -> str:
    """Everything the child said, on one line.

    Whole rather than bounded, because this is what a caller reads to decide
    *which* failure it was. A bound belongs on what is put in front of a person,
    not on what is matched against, or a message recognised today stops being
    recognised the day the program before it becomes chattier.
    """
    return " ".join(stderr.split())


def tail(stderr: str, *, limit: int) -> str:
    """The end of what the child said, on one line and no longer than `limit`.

    The end rather than the beginning, because a program that failed says why
    last. A child that said nothing still produces a sentence rather than a
    blank.

    `limit` is the caller's, because how much of a child's words are safe to
    carry is a question about that child: `pg_dump` names the object it stopped
    on and is worth quoting at length, while a program that was handling a
    secret is worth quoting as little of as still diagnoses the failure.
    """
    text = collapse(stderr)
    return text[-limit:] if len(text) > limit else text or "no output"
