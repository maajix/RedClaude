"""Local runtime readiness: the operation behind `rk doctor`.

`diagnose` answers one question -- can this machine be trusted to run a Program
-- by asserting the interpreter, the declared runtime requirements, the state
this installation depends on and, when the operator supplies one, a Program
configuration. It reads; it never creates state, contacts a target or starts an
Agent run. Every fact it reports is a name, a version, a count or a digest.

Story 12 names five subjects and this asks about all five: runtime versions,
database state, proxy readiness, container isolation and catalogue integrity.
Each of the four beyond the interpreter is asked of something the operator has
described -- a connection string, a trust root, an Agent boundary -- and where
nothing was described the answer is that nothing was, rather than a hold that
reads as readiness. A machine with no database configured is not a machine with
a healthy one.

Nothing here re-implements a check another module owns. The database answer is
the one `rk db status` gives, the boundary answer is the assertion `isolation`
makes before it starts a child, and the catalogue answer is the compilation each
corpus refuses with. What this module adds is the asking.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path

from redkraken import (
    __version__,
    build,
    config,
    document,
    door,
    execution,
    fixture,
    isolation,
    migrate,
    outcome,
    pg,
    playbook,
    proxy,
    skill,
    tls,
)
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    INVALID_CORPUS,
    MISSING_DEPENDENCY,
    RESULT_SCHEMA_VERSION,
    UNSUPPORTED_VERSION,
    Assertion,
    Ledger,
    Report,
    Violation,
)


#: The interpreter range this runtime is exercised against, as an inclusive
#: minimum and an exclusive maximum. `pyproject.toml` declares the same range.
SUPPORTED_PYTHON = ((3, 14), (3, 15))

#: Interpreter modules the runtime needs that a minimal build may omit.
REQUIRED_MODULES = ("ssl", "tomllib")

#: Production dependencies as exact pins, mirroring `pyproject.toml`. Empty,
#: and the Agent SDK is not an omission: it is measured rather than declared
#: (`_launch`), so a machine without it runs every command here and refuses at
#: the one thing it cannot do, which is start an Agent run.
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

#: One corpus: the word an operator reads in the report, and the compilation
#: that either produces documents or refuses. A pair rather than a module
#: reference, because what this asks of a corpus is the one function all three
#: expose and nothing else about them.
Corpus = tuple[str, "Callable[[], Mapping[str, object]]"]

#: The three corpora an installation ships. Compiled from the installed package
#: -- each `compile_corpus` defaults to the directory beside its own module --
#: so what is diagnosed is what this machine would actually read.
CORPORA: tuple[Corpus, ...] = (
    ("playbooks", playbook.compile_corpus),
    ("skills", skill.compile_corpus),
    ("fixtures", fixture.compile_corpus),
)


@dataclass(frozen=True)
class Diagnosis:
    """What one `rk doctor` run observed."""

    application_version: str
    python_version: str
    build: dict
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
            "build": self.build,
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
    build_anchor: Traversable | None = None,
    environment: Mapping[str, str] | None = None,
    database_url: str | None = None,
    corpora: tuple[Corpus, ...] = CORPORA,
) -> Diagnosis:
    """Report local readiness, and the supplied configuration when there is one.

    The observed interpreter version, the declared requirements, the package the
    build assertion reads, the environment the boundary is described in and the
    corpora that are compiled are parameters so that the negative outcomes stay
    reachable from tests without corrupting the running interpreter or the
    installed package.

    An unstated environment describes nothing rather than defaulting to this
    process's own. The two probes that read it can start subprocesses against
    whatever a machine happens to export, and a caller that has not said which
    environment it means has not asked about any machine's containers.
    """
    version = tuple(python_version) if python_version is not None else tuple(sys.version_info[:3])
    described = {} if environment is None else environment
    ledger = Ledger()

    _assert_python(ledger, version)
    # An install with no manifest is running from source; that holds, and reports
    # what the tree hashes to. One that matches holds and reports the revision it
    # was built from. One that does not -- or whose manifest cannot be read -- is
    # a `build_mismatch`, because a harness running code no commit vouches for
    # writes Receipts it cannot stand behind. The door asserts the same thing
    # through the same call, which is why the wording is not written out here.
    installed = build.record(ledger, build_anchor).as_dict()
    _assert_modules(ledger, requirements.modules)
    _assert_distributions(ledger, requirements.distributions)
    _assert_database(ledger, database_url)
    _assert_proxy(ledger, described)
    _assert_isolation(ledger, described)
    _assert_agent_credential(ledger, described)
    _assert_catalogue(ledger, corpora)
    summary = _assert_configuration(ledger, configuration_path)
    _assert_door_program(ledger, described, database_url, summary)

    return Diagnosis(
        application_version=__version__,
        python_version=_version(version),
        build=installed,
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


def _assert_database(ledger: Ledger, url: str | None) -> None:
    """Whether the database this machine points at holds the schema it ships.

    The answer `rk db status` gives, folded in whole rather than derived a
    second time: which migrations are recorded and which the corpus still owes
    is one question, and a second reading of it here could differ from the
    command an operator is told to run.
    """
    if not url:
        ledger.hold("database", "no connection string supplied")
        return
    try:
        settings = pg.settings_from_url(url, application_name="rk doctor")
    except ValueError as error:
        # The parser's own words, which name the unusable parameter and never
        # echo the string back: a connection string carries a password.
        ledger.fail(
            "database",
            f"the connection string cannot be used: {error}",
            code=INVALID_CONFIGURATION,
            source="connection_string",
        )
        return
    answer = migrate.status(settings)
    applied = answer.facts.get("applied") or ()
    pending = answer.facts.get("pending") or ()
    _fold(
        ledger,
        "database",
        answer,
        f"{len(applied)} migration(s) recorded and {len(pending)} pending "
        f"at {answer.facts.get('target', 'the configured database')}",
    )


def _assert_proxy(ledger: Ledger, environment: Mapping[str, str]) -> None:
    """Whether the door could be trusted if a child were started against it now.

    Read-only about material that is otherwise made on demand: `tls.authority`
    mints a root when the directory holds none, and a diagnosis that called it
    would be creating the readiness it reports. So the certificate is asked
    whether it exists and whether it is spent, the directory is asked whether it
    is a directory, and the program that would issue the next one is asked
    whether it is installed at all.
    """
    if shutil.which(tls.OPENSSL) is None:
        ledger.fail(
            "certificate_tool",
            f"{tls.OPENSSL} is not on PATH; it issues the certificate that lets the "
            "door see inside a tunnel",
            code=MISSING_DEPENDENCY,
            source=f"program:{tls.OPENSSL}",
        )
    else:
        ledger.hold("certificate_tool", f"{tls.OPENSSL} is installed")

    directory = environment.get(proxy.AUTHORITY_VARIABLE)
    if not directory:
        ledger.hold("proxy_authority", f"no authority directory described (${proxy.AUTHORITY_VARIABLE})")
    elif not Path(directory).is_dir():
        ledger.fail(
            "proxy_authority",
            f"the authority directory is not a directory: {directory}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.AUTHORITY_VARIABLE}",
        )
    else:
        ledger.hold("proxy_authority", f"{directory} can hold the door's authority")

    _assert_trust_root(ledger, environment.get(proxy.CA_VARIABLE))


def _assert_trust_root(ledger: Ledger, certificate: str | None) -> None:
    """Whether the root a child would be handed is one a child could use."""
    if not certificate:
        ledger.hold("proxy_trust_root", f"no trust root described (${proxy.CA_VARIABLE})")
        return
    path = Path(certificate)
    if not path.is_file():
        ledger.fail(
            "proxy_trust_root",
            f"the trust root is not a readable file: {path}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.CA_VARIABLE}",
        )
        return
    try:
        spent = tls.spent(path)
    except tls.Unusable as error:
        ledger.fail(
            "proxy_trust_root",
            f"the trust root cannot be read: {error}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.CA_VARIABLE}",
        )
        return
    if spent:
        # Not a state the door cannot recover from -- it reissues on its next
        # start -- but a child already holding this one keeps holding it, so an
        # operator opening a long session is told before it expires under them.
        ledger.fail(
            "proxy_trust_root",
            f"the trust root at {path} is at the end of its life and will be reissued",
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.CA_VARIABLE}",
        )
        return
    ledger.hold("proxy_trust_root", f"{path} is current")


def _assert_isolation(ledger: Ledger, environment: Mapping[str, str]) -> None:
    """Whether the Agent boundary this machine describes is the one it claims.

    The assertion `isolation` makes before it starts a child, made here without
    starting one: the network is internal, the door is attached to it, the proxy
    URL names that peer, and nothing else is on the network. A machine that
    describes no boundary describes none, which is `rk run` used the way every
    ticket before the boundary used it rather than a failure.
    """
    if not execution.requested(environment):
        ledger.hold("agent_boundary", "no Agent boundary described")
        return
    container, missing = execution.boundary(environment)
    if container is None:
        ledger.fail(
            "agent_boundary",
            "the Agent boundary is described only in part: "
            + ", ".join(missing)
            + (" is unset" if len(missing) == 1 else " are unset")
            + ", and no child starts without all of them",
            code=INVALID_CONFIGURATION,
            source=f"environment:{missing[0]}",
        )
        return
    try:
        engine = isolation.engine_for(container.engine)
    except isolation.Unavailable as error:
        ledger.fail(
            "agent_boundary", str(error), code=MISSING_DEPENDENCY, source="program:container_engine"
        )
        return
    try:
        isolation.peered(engine, container)
    except isolation.Unavailable as error:
        ledger.fail(
            "agent_boundary",
            str(error),
            code=INVALID_CONFIGURATION,
            source=f"environment:{execution.NETWORK}",
        )
        return
    # Ticket 219's fourth criterion: an operator asking whether a second worker
    # can start should not have to read `isolation.py`. The claim is reported and
    # not refused, because a machine with a hunt on it is a machine working --
    # what the operator is owed is the fact, which is the whole answer to "can I
    # start another one" and the whole reason the third worker died on lap 3.
    taken = isolation.unclaimed(container.network)
    ledger.hold(
        "agent_boundary",
        f"{container.network} is internal and holds {container.proxy_container} alone"
        + (
            ", and a launch on this machine already holds it, so a second"
            " `rk run` against it would be refused"
            if taken
            else ", and no launch holds it, so one child may start on it"
        ),
    )


def _assert_agent_credential(ledger: Ledger, environment: Mapping[str, str]) -> None:
    """Whether a child started now would have anything to authenticate with.

    Ticket 146. The launch already refuses an unusable credential, and that
    refusal arrives after a Task has been claimed: it costs an attempt, and
    three of them abandon the Task. The same predicate is asked here, before a
    run, and the message carries the remedy rather than only the path.

    Asked only of a machine that describes an Agent boundary, for the reason
    `_assert_isolation` is: a machine that starts no children needs no token,
    and refusing one over a file it will never open would withhold the four
    other answers this command has.

    The age is a hold and not a violation. A setup token lasts about a year and
    one that is 340 days old still works; what an operator needs is to be told
    now rather than in the middle of the hunt it expires under.
    """
    if not execution.requested(environment):
        ledger.hold("agent_credential", "no Agent boundary described")
        return
    try:
        token = isolation.oauth_token(environment)
    except isolation.Unavailable as error:
        ledger.fail(
            "agent_credential",
            str(error),
            code=INVALID_CONFIGURATION,
            source=f"environment:{isolation.OAUTH_TOKEN_VARIABLE}",
        )
        return
    path = isolation.oauth_token_file(environment)
    if token is None:
        ledger.fail(
            "agent_credential",
            f"no Claude setup token at {path}, and no child authenticates without one; "
            f"{isolation.OAUTH_TOKEN_REMEDY}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{isolation.OAUTH_TOKEN_VARIABLE}",
        )
        return
    days = isolation.oauth_token_days(environment)
    if days is not None and days >= isolation.OAUTH_TOKEN_DAYS:
        ledger.hold(
            "agent_credential",
            f"the Claude setup token at {path} was installed {days} days ago and a setup "
            f"token lasts about a year; {isolation.OAUTH_TOKEN_REMEDY} again",
        )
        return
    ledger.hold("agent_credential", f"{path} holds a setup token this operator alone can read")


def _assert_door_program(
    ledger: Ledger,
    environment: Mapping[str, str],
    database_url: str | None,
    configuration: Mapping[str, object] | None,
) -> None:
    """Whether a child would reach a Door attached to this Program's database."""
    if not execution.requested(environment):
        ledger.hold("door_preflight", "no Agent boundary described")
        return
    if not database_url:
        ledger.hold("door_preflight", "no database connection string supplied")
        return
    if configuration is None or not configuration.get("program_name"):
        ledger.hold("door_preflight", "no Program configuration supplied")
        return
    container, _ = execution.boundary(environment)
    if container is None:
        return
    try:
        settings = pg.settings_from_url(database_url, application_name="rk doctor door")
        with pg.connect(settings) as connection:
            rows = connection.execute(
                "SELECT id::text FROM programs WHERE slug = $1",
                (str(configuration["program_name"]),),
            ).rows
            if len(rows) != 1:
                raise isolation.Unavailable(
                    f"Program {configuration['program_name']} is not visible on the "
                    "database this diagnosis opened"
                )
            detail = door.preflight(container, connection, str(rows[0][0]))
    except (ValueError, isolation.Unavailable, pg.DatabaseError, pg.ConnectionError_) as error:
        ledger.fail(
            "door_preflight",
            f"the Door, database and Program do not form one runtime: {error}",
            code=INVALID_CONFIGURATION,
            source="door",
        )
        return
    ledger.hold("door_preflight", detail)


def _assert_catalogue(ledger: Ledger, corpora: tuple[Corpus, ...]) -> None:
    """Whether the corpora this installation ships still compile.

    Compiled rather than counted, because a corpus is a set of documents the
    runtime reads at the moment it needs one: an installation whose Playbook
    names a Skill nobody ships refuses at selection time, on the run that needed
    it. This is where an operator finds that out instead.

    Compiled rather than *run*, which is a decision and not an oversight. A
    Skill's scripts declare synthetic cases and `skill.check_all` would execute
    them -- two processes and a temporary directory per case -- and `rk doctor`
    promises neither: `tests/test_cli.py`'s `ContainmentTest` runs the command
    under an audit hook and asserts it raises no subprocess, no network and no
    write event at all. A readiness check an operator cannot run beside a live
    Program is one they will not run. So the declared cases are the gate this
    repo passes before it ships a corpus and never the installation's after.
    `Corpus` is a name and a compile function for the same reason: this loop is
    not allowed to know which of the three is the skills.
    """
    for name, compile_corpus in corpora:
        try:
            compiled = compile_corpus()
        except document.DocumentError as error:
            ledger.fail(
                f"catalogue:{name}",
                f"the installed {name} corpus does not compile: {error}",
                code=INVALID_CORPUS,
                source=f"corpus:{name}",
            )
        else:
            ledger.hold(f"catalogue:{name}", f"{len(compiled)} compiled")


def _fold(ledger: Ledger, name: str, answer: Report, held: str) -> None:
    """Record another command's report as one assertion of this diagnosis.

    The violations cross over whole. A diagnosis that summarised them would be a
    second wording of a refusal the operator can already act on, and the exit
    code this command returns is derived from their codes rather than from any
    sentence written here.
    """
    if answer.violations:
        ledger.refuse(
            name,
            f"`{answer.command}` refused: {len(answer.violations)} violation(s)",
            answer.violations,
        )
        return
    ledger.hold(name, held)


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
