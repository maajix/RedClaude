"""Whether what an operator installs is what this repository says it is.

Every other gate in `tools/` reads the checkout. This one builds from it and
then asks the built thing, because the two are not the same claim: a suite that
passes on a developer's machine passes with that machine's environment, that
machine's leftovers and that machine's already-migrated database, and none of
those travel. What travels is a clone, one documented install path, and a
server nobody has touched.

So this exports the commit, installs it the way the README says to install it
offline, starts the supported topology, and then drives a database through its
whole life with the production commands and nothing else -- create, migrate,
verify, open a Program, dump, restore, and continue the same campaign on the
restored copy. The declared runtime privilege surface is asked of both
databases, because hardening that was verified on a database a migration built
and never on one a restore built is hardening verified on the artifact nobody
gets.

**Nothing here reaches a provider, a target or an operator's credentials.** Every
child process is started from an environment this file writes: a PATH, a home
under the run's own directory, a locale, and the connection strings the stage
needs. Not a filtered copy of the caller's environment -- a filter forgets, and
a variable that reaches a child by being forgotten is the failure this is a
gate against. The one thing it is given is a superuser connection string to a
*disposable* server, which it drops and recreates databases on.

**What "clean" means, exactly.** The tree under test is `git archive` of the
commit, so untracked scratch cannot travel by being present. The install is
into a virtual environment that did not exist a moment ago. The databases are
created by this run and dropped at the end unless `--keep` says otherwise.

Run it against a disposable server:

    python3 -m tools.release_gate --superuser-url postgres://postgres:...@127.0.0.1:5432/postgres

One stage at a time while working on one of them:

    python3 -m tools.release_gate --superuser-url ... --stage install --stage database

The last stage is the long one: the offline suite and the composed production
suite, each twice, because a suite that passes once has not shown that it left
the server the way it found it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit

from tools.check_baseline import read_status


CHECKOUT = Path(__file__).resolve().parents[1]

#: The stages, in the order they have to happen. Each one uses what the one
#: before it built, which is why this is a sequence and not a set: there is no
#: installed application to drive a database with until `install` has run.
STAGES = ("export", "install", "database", "topology", "privileges", "suites")

#: The interpreter the installation is built with. The one running this file,
#: because `pyproject.toml` pins a version range and a gate that installed under
#: a different interpreter than it checked would be reporting about neither.
INTERPRETER = sys.executable

#: What the three databases are called. Named rather than generated so that a
#: run interrupted halfway leaves something an operator can find and drop. The
#: third is the composed suite's own, so that the suite's teardown never reaches
#: the two databases this gate built.
MIGRATED_DATABASE = "rk2_release_gate"
RESTORED_DATABASE = "rk2_release_gate_restored"
SUITE_DATABASE = "rk2_gate_suite"

#: Every role `rk db provision` creates. Seven, and the seven are the claim: a
#: provision that made six left something ungranted and one that made eight put
#: a login somewhere the design has none.
PROVISIONED = (
    "rk2_owner",
    "rk2_migrate",
    "rk2_restore",
    "rk2_runtime",
    "rk2_state",
    "rk2_proxy",
    "rk2_human",
)

#: The subset this gate connects as. Not `rk2_owner`, which is NOLOGIN and
#: reached by `SET ROLE`, and not `rk2_human`, which is the operator's own and
#: is nothing a gate should be holding.
CONNECTING = ("rk2_migrate", "rk2_restore", "rk2_runtime", "rk2_state", "rk2_proxy")

#: Path segments that must not appear anywhere in the installed application. The
#: first four are the roots the boundary registry already forbids production
#: code to depend on, read from that registry rather than written down again
#: here: a second copy of the same names is a second copy to keep, and this gate
#: is measuring the tree the registry describes. The rest are the directories a
#: checkout carries and an installation does not.
NOT_INSTALLABLE = tuple(
    root.lstrip("/.") for root in read_status()["forbidden_dependency_roots"]
) + ("tests", "tools", ".git", ".venv")

#: What may be installed into the virtual environment. `pip` because a virtual
#: environment has one, and the application. Anything else is a third-party
#: production dependency, which this project does not have and which
#: `pyproject.toml` says it does not have.
INSTALLABLE = frozenset({"redkraken", "pip"})

#: The Program the database stage opens, dumps, restores and continues. Its own
#: rather than the suite's fixture: what is being measured is a configuration
#: travelling through a dump, so it has to be a file this run wrote and can
#: compare byte for byte on the other side. No identity, header or callback,
#: because provisioning material into slots is a different ticket's proof and
#: an unprovisioned declaration is a refusal this stage would have to work
#: around.
PROGRAM = """schema_version = 1

[program]
name = "release-gate"
platform = "hackerone"

[rules_of_engagement]
mutation = false

[budgets]
requests = 500
tokens = 200000
run_tokens = 4000
run_requests = 20
lane_tokens = 50000
lane_requests = 100
concurrency = 1
burst = 50
window_seconds = 3600

[[scope.include]]
host = "gate.example.com"
ports = [443]
protocols = ["https"]
paths = ["/api/"]
"""

#: Run as the superuser, before the database stage builds and after it is done
#: with what it built. `WITH (FORCE)` because a stage that failed halfway may
#: have left a connection open, and a gate that could not clear its own
#: leftovers would need a person before it could be run a second time.
DROPPING = """
import sys
from redkraken import pg

connection = pg.connect(pg.settings_from_url(sys.argv[1]))
try:
    connection.execute(
        "DROP DATABASE IF EXISTS " + pg.quote_identifier(sys.argv[2]) + " WITH (FORCE)"
    )
finally:
    connection.close()
"""

#: Asked of both databases. The function is the standing check ticket 66 left
#: behind: it fails on anything `rk2_runtime` holds beyond the declared surface,
#: so an empty answer is the surface holding and a row is the privilege that
#: came back. Read through the installed application's own driver, as the
#: runtime, because that is the connection the claim is about.
SURFACE = """
import json, sys
from redkraken import pg

connection = pg.connect(pg.settings_from_url(sys.argv[1]))
try:
    print(json.dumps({
        "excess": [list(map(str, row))
                   for row in connection.execute("SELECT * FROM check_runtime_privileges()").rows],
        "roles": [str(row[0]) for row in connection.execute(
            "SELECT rolname FROM pg_roles WHERE rolname LIKE 'rk2%'").rows],
    }))
finally:
    connection.close()
"""


class ReleaseError(RuntimeError):
    """The release gate did not pass, and this says every reason."""


@dataclass
class Gate:
    """One run: where it built, what it built, and what it has proved so far."""

    superuser: str
    root: Path
    keep: bool = False
    token: str = field(default_factory=lambda: secrets.token_hex(4))
    passwords: dict[str, str] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)

    @property
    def export(self) -> Path:
        return self.root / "checkout"

    @property
    def venv(self) -> Path:
        return self.export / ".venv"

    @property
    def rk(self) -> Path:
        return self.venv / "bin" / "rk"

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def archive(self) -> Path:
        # Named per run rather than per directory: `rk db dump` never
        # overwrites an archive, which is right, and a gate rerun into a kept
        # build directory would otherwise be refused by its own leftovers.
        return self.root / f"release-gate-{self.token}.dump"

    @property
    def configuration(self) -> Path:
        return self.root / "program.toml"

    @property
    def kept(self) -> Path:
        return self.root / "roles.json"

    def secret(self, role: str) -> str:
        """The password this run gave a role, made once and written down.

        Written down because the stages can be selected one at a time: a
        `topology` run against the database an earlier `--keep` run provisioned
        has to reach it as the roles that database actually has, and the only
        record of what those are is the one this leaves behind. The file lives
        inside the build root, which is removed unless the run was kept.
        """
        if not self.passwords and self.kept.exists():
            self.passwords.update(json.loads(self.kept.read_text(encoding="utf-8")))
        if role not in self.passwords:
            self.passwords[role] = secrets.token_urlsafe(24)
            self.kept.touch(mode=0o600, exist_ok=True)
            self.kept.write_text(json.dumps(self.passwords), encoding="utf-8")
        return self.passwords[role]

    def url(self, role: str, database: str, *, host: str | None = None) -> str:
        """One role's connection string, spelled as the process holding it reaches it.

        `host` is what the door needs and nothing else does: a loopback address
        is this machine's from out here and the container's own from inside one,
        so the one connection string that crosses into a container is written
        against the name the engine publishes this machine back under.
        """
        parts = urlsplit(self.superuser)
        return (
            f"postgres://{quote(role)}:{quote(self.secret(role))}"
            f"@{host or parts.hostname or '127.0.0.1'}:{parts.port or 5432}/{quote(database)}"
        )

    def environment(self, **named: str) -> dict[str, str]:
        """The whole environment a child gets: written here, never inherited.

        Four names plus whatever the stage adds. A copy of the caller's
        environment with the dangerous names removed would be a list of the
        dangerous names somebody thought of, and the credential that reaches a
        child is always the one nobody thought of.
        """
        return {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": str(self.home),
            "TMPDIR": str(self.root / "tmp"),
            "LANG": "C.UTF-8",
            **named,
        }

    def says(self, fact: str) -> None:
        self.facts.append(fact)


def ran(
    command: list[str],
    *,
    environment: dict[str, str],
    cwd: Path | None = None,
    timeout: int = 3600,
    expect: int = 0,
) -> subprocess.CompletedProcess[str]:
    """One child, from a written environment, whose exit code is the claim."""
    result = subprocess.run(
        [str(item) for item in command],
        env=environment,
        cwd=None if cwd is None else str(cwd),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != expect:
        raise ReleaseError(
            f"{' '.join(str(item) for item in command[:4])} exited {result.returncode}, "
            f"expected {expect}\n{(result.stderr or result.stdout).strip()[:4000]}"
        )
    return result


def answered(result: subprocess.CompletedProcess[str]) -> dict:
    """What a command reported, as the document every command answers in."""
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ReleaseError(f"a command answered something that is not JSON: {error}") from error


# -- the stages ---------------------------------------------------------------


def export(gate: Gate) -> None:
    """The commit, and nothing that is merely lying next to it.

    `git archive` rather than a copy: a copy carries the virtual environment,
    the caches, the databases somebody dumped into the working tree and every
    other thing that makes a machine's own checkout work. None of it is in the
    clone the next person makes, so none of it may be in what this measures.
    """
    revision = ran(
        ["git", "rev-parse", "HEAD"], environment=gate.environment(), cwd=CHECKOUT
    ).stdout.strip()
    dirty = ran(
        ["git", "status", "--porcelain"], environment=gate.environment(), cwd=CHECKOUT
    ).stdout.strip()

    gate.export.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        env=gate.environment(),
        cwd=str(CHECKOUT),
        capture_output=True,
        check=True,
        timeout=300,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(gate.export)],
        input=archive.stdout,
        env=gate.environment(),
        check=True,
        timeout=300,
    )

    files = sum(1 for path in gate.export.rglob("*") if path.is_file())
    gate.says(f"export: {revision[:12]} {files} files" + (", tree dirty" if dirty else ""))


def install(gate: Gate) -> None:
    """The documented offline install path, and what it may leave behind.

    The README's second install path, verbatim, plus `--no-index`: without
    network access there is nothing to fetch, and saying so is what makes the
    absence of the network part of the claim rather than a property of the
    machine that happened to run this.
    """
    ran(
        [INTERPRETER, "-m", "venv", "--system-site-packages", str(gate.venv)],
        environment=gate.environment(),
        timeout=600,
    )
    ran(
        [
            gate.venv / "bin" / "pip",
            "install",
            "--no-index",
            "--no-build-isolation",
            "--check-build-dependencies",
            ".",
        ],
        environment=gate.environment(),
        cwd=gate.export,
        timeout=1800,
    )

    installed = {
        item["name"]
        for item in json.loads(
            ran(
                [gate.venv / "bin" / "pip", "list", "--local", "--format", "json"],
                environment=gate.environment(),
            ).stdout
        )
    }
    problems = [f"the virtual environment holds {name}" for name in sorted(installed - INSTALLABLE)]

    # `pip list --local` cannot answer this one. The environment is built with
    # `--system-site-packages`, so a third-party requirement the base
    # interpreter happens to satisfy is installed, imported and invisible to
    # that listing. What the artifact declares is a property of the artifact:
    # `pyproject.toml` says this application has no runtime dependency, and the
    # distribution metadata pip wrote is where that survives into the wheel.
    required = json.loads(
        ran(
            [
                gate.python,
                "-c",
                "import json, importlib.metadata as data;"
                " print(json.dumps(data.requires('redkraken') or []))",
            ],
            environment=gate.environment(),
        ).stdout
    )
    problems += [f"the installed distribution requires {name}" for name in required]

    # Where the application actually landed, asked of the interpreter that would
    # import it rather than guessed from a path this file composed.
    package = Path(
        ran(
            [gate.python, "-c", "import redkraken, pathlib; print(pathlib.Path(redkraken.__file__).parent)"],
            environment=gate.environment(),
        ).stdout.strip()
    )
    for path in package.rglob("*"):
        for segment in path.relative_to(package).parts:
            if segment in NOT_INSTALLABLE:
                problems.append(f"the installed application carries {path.relative_to(package)}")

    # And beside it, which is where a packaging regression in a `src` layout
    # actually shows up: a `tests` or `docs` directory declared as a package of
    # its own installs as a sibling of the application, not inside it, and the
    # walk above would never see it.
    for path in package.parent.iterdir():
        if path.name.split(".")[0] in NOT_INSTALLABLE:
            problems.append(f"the environment holds {path.name} beside the application")

    version = ran([gate.rk, "--version"], environment=gate.environment()).stdout.strip()
    stated = answered(ran([gate.rk, "version"], environment=gate.environment()))
    doctor = answered(ran([gate.rk, "doctor"], environment=gate.environment()))
    checked = answered(
        ran(
            [gate.rk, "doctor", "--config", str(gate.configuration)],
            environment=gate.environment(),
        )
    )

    for report in (stated, doctor, checked):
        if not report["ok"]:
            problems.append(f"{report['command']} refused: {report['violations']}")
    # A build the application cannot recognise as its own is an install that
    # was edited after it was built, which is the one thing an operator cannot
    # see by looking at the files.
    if not doctor["build"]["digest"]:
        problems.append("the install carries no build digest")
    if doctor["build"]["dirty"]:
        problems.append("the install reports itself built from a dirty tree")

    if problems:
        raise ReleaseError("\n".join(problems))
    gate.says(
        f"install: {version}, {doctor['build']['modules']} modules, "
        f"schema {stated['schema'][:15]}, corpus {stated['corpus']}"
    )


def topology(gate: Gate) -> None:
    """The supported boundary, started by the command that is allowed to start it.

    Two networks and one door, exactly as the README describes them. What is
    asserted afterwards is the shape rather than the traffic -- the Agent
    network internal with the door as its only peer, the egress network
    routable -- because what crosses it is `BrowserContainerIsolationTest` and
    the door's own suite, and this stage's question is whether the documented
    commands produce that shape on a machine that has never run them.

    A machine without a container engine fails this stage rather than skipping
    it. The criterion is that the supported topology starts, and a run that
    reported `ok` having started nothing would be the gate answering a question
    it never asked -- on the one machine where the answer matters, the release
    manager's.
    """
    if shutil.which("docker") is None:
        raise ReleaseError(
            "no container engine on PATH: the supported topology cannot be started, "
            "and this stage is the claim that it can"
        )
    image = os.environ.get("RK_TEST_AGENT_IMAGE", "python:3.14-slim")
    if subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        check=False,
        timeout=120,
    ).returncode:
        raise ReleaseError(
            f"the Agent image is absent: {image}. Build or pull it, or name another "
            "in RK_TEST_AGENT_IMAGE"
        )

    # The name the engine publishes this machine back under, read from the
    # installation rather than written again here: the door adds the host entry
    # under its own constant, and a gate that spelled it differently would be
    # handing the door a name it cannot resolve.
    gateway = ran(
        [gate.python, "-c", "from redkraken import door; print(door.GATEWAY)"],
        environment=gate.environment(),
    ).stdout.strip()

    suffix = secrets.token_hex(4)
    agent = f"rk2-gate-agent-{suffix}"
    egress = f"rk2-gate-egress-{suffix}"
    door = f"rk2-gate-door-{suffix}"
    authority = gate.root / "authority"
    artifacts = gate.root / "artifacts"
    for directory in (authority, artifacts):
        directory.mkdir(parents=True, exist_ok=True)
        # The door runs as the nameless user with a read-only root, so both
        # directories have to be writable by it. World-writable rather than
        # chowned: this gate does not have the machine's root.
        directory.chmod(0o777)

    environment = gate.environment(
        RK_AGENT_IMAGE=image,
        RK_AGENT_NETWORK=agent,
        RK_AGENT_PROXY_CONTAINER=door,
        RK_AGENT_PROXY_URL=f"http://{door}:18080",
        RK_PROXY_CA_FILE=str(authority / "ca.pem"),
        RK_PROXY_DATABASE_URL=gate.url("rk2_proxy", MIGRATED_DATABASE, host=gateway),
        RK_ARTIFACT_ROOT=str(artifacts),
        RK_PROXY_AUTHORITY=str(authority),
    )
    try:
        ran(["docker", "network", "create", "--internal", agent], environment=environment)
        ran(["docker", "network", "create", egress], environment=environment)
        started = answered(
            ran(
                [gate.rk, "proxy", "door", "--egress", egress, "--timeout", "120"],
                environment=environment,
                timeout=300,
            )
        )
        if not started["ok"]:
            raise ReleaseError(f"the door refused to start: {started['violations']}")

        peers = json.loads(
            ran(
                [
                    "docker",
                    "network",
                    "inspect",
                    agent,
                    "--format",
                    "{{json .Containers}}",
                ],
                environment=environment,
            ).stdout
        )
        names = sorted(item["Name"] for item in peers.values())
        if names != [door]:
            raise ReleaseError(f"the Agent network's peers are {names}, not the door alone")
        gate.says(f"topology: {door} serving, {agent} internal with one peer")
    finally:
        subprocess.run(["docker", "rm", "--force", door], capture_output=True, check=False)
        for network in (agent, egress):
            subprocess.run(
                ["docker", "network", "rm", network], capture_output=True, check=False
            )


def database(gate: Gate) -> None:
    """A database's whole life, through the commands an operator has.

    Create, migrate, verify, open a Program, read it, dump it, restore it into
    a database that has never been migrated, verify that, and open the same
    Program again on the restored copy. The last step is the one that cannot be
    faked: a restore that produced a readable schema and an unusable campaign
    would pass every check before it.
    """
    provisioning = gate.environment(
        RK_SUPERUSER_URL=gate.superuser,
        **{f"RK_PASSWORD_{role.upper()}": gate.secret(role) for role in CONNECTING},
    )
    for name in (MIGRATED_DATABASE, RESTORED_DATABASE):
        drop(gate, name)
        ran(
            [gate.rk, "db", "provision", "--database", name],
            environment=provisioning,
            timeout=600,
        )

    migrating = gate.environment(RK_MIGRATE_URL=gate.url("rk2_migrate", MIGRATED_DATABASE))
    applied = answered(ran([gate.rk, "db", "migrate"], environment=migrating, timeout=3600))
    status = answered(ran([gate.rk, "db", "status"], environment=migrating))
    verified = answered(ran([gate.rk, "db", "verify"], environment=migrating, timeout=1800))
    problems = [
        f"{report['command']} refused: {report['violations']}"
        for report in (applied, status, verified)
        if not report["ok"]
    ]

    if len(applied.get("applied", ())) != applied.get("corpus"):
        problems.append(
            f"the first migrate applied {len(applied.get('applied', ()))} of "
            f"{applied.get('corpus')} migrations, so the database was not built empty"
        )
    if status.get("pending"):
        problems.append(f"the migrated database still has pending migrations: {status['pending']}")

    # The upgrade half of the criterion: a second `migrate` on a database that
    # is already current applies nothing and still verifies. Asserted on what it
    # applied rather than on whether it succeeded, because an installation that
    # reapplied the whole corpus and verified afterwards would report exactly
    # the same `ok` -- and that is the destructive upgrade path this is looking
    # for.
    again = answered(ran([gate.rk, "db", "migrate"], environment=migrating, timeout=1800))
    if not again["ok"]:
        problems.append(f"a second migrate refused: {again['violations']}")
    elif again.get("applied"):
        problems.append(
            f"a second migrate reapplied {len(again['applied'])} migration(s): {again['applied'][:3]}"
        )

    running = gate.environment(
        RK_DATABASE_URL=gate.url("rk2_runtime", MIGRATED_DATABASE),
        RK_STATE_URL=gate.url("rk2_state", MIGRATED_DATABASE),
    )
    opened = answered(
        ran(
            [gate.rk, "run", "--config", str(gate.configuration)],
            environment=running,
            timeout=600,
        )
    )
    if not opened["ok"]:
        problems.append(f"the Program would not open: {opened['violations']}")
    read = answered(
        ran(
            [gate.rk, "state", "--config", str(gate.configuration)],
            environment=running,
            timeout=600,
        )
    )
    if not read["ok"]:
        problems.append(f"the bounded read refused: {read['violations']}")

    dumped = answered(
        ran(
            [gate.rk, "db", "dump", "--to", str(gate.archive)],
            environment=migrating,
            timeout=1800,
        )
    )
    if not dumped["ok"]:
        problems.append(f"the dump refused: {dumped['violations']}")
    if not gate.archive.is_file() or not gate.archive.stat().st_size:
        problems.append("the dump wrote nothing")

    restored = answered(
        ran(
            [gate.rk, "db", "restore", "--from", str(gate.archive)],
            environment=gate.environment(RK_RESTORE_URL=gate.url("rk2_restore", RESTORED_DATABASE)),
            timeout=1800,
        )
    )
    if not restored["ok"]:
        problems.append(f"the restore refused: {restored['violations']}")

    after = gate.environment(RK_MIGRATE_URL=gate.url("rk2_migrate", RESTORED_DATABASE))
    checked = answered(ran([gate.rk, "db", "verify"], environment=after, timeout=1800))
    if not checked["ok"]:
        problems.append(f"the restored database failed verification: {checked['violations']}")
    # The recovered copy's own place on the upgrade path: an archive that
    # carried the rows but not the version table restores into a database that
    # verifies and then wants the whole corpus applied over the top of it.
    recovered = answered(ran([gate.rk, "db", "status"], environment=after, timeout=600))
    if recovered.get("pending"):
        problems.append(
            f"the restored database is behind the corpus: {recovered['pending']}"
        )

    continuing = gate.environment(
        RK_DATABASE_URL=gate.url("rk2_runtime", RESTORED_DATABASE),
        RK_STATE_URL=gate.url("rk2_state", RESTORED_DATABASE),
    )
    resumed = answered(
        ran(
            [gate.rk, "run", "--config", str(gate.configuration)],
            environment=continuing,
            timeout=600,
        )
    )
    if not resumed["ok"]:
        problems.append(f"the campaign would not continue after the restore: {resumed['violations']}")
    elif resumed["program_id"] != opened["program_id"]:
        problems.append(
            "the restored database opened a different Program: "
            f"{resumed['program_id']} is not {opened['program_id']}"
        )
    elif any((resumed.get("first_tasks") or {}).values()):
        # Every count zero, not the key absent: opening a Program reports what
        # it recorded either way, and a resumed campaign is the one that
        # recorded nothing because the Task each subject already carries is the
        # Task being resumed.
        problems.append(
            "the restored database opened first Tasks again, so it resumed nothing: "
            f"{resumed['first_tasks']}"
        )
    if not any((opened.get("first_tasks") or {}).values()):
        problems.append(
            "the first open recorded no subject and opened no Task, so the "
            f"restore had nothing to carry: {opened.get('first_tasks')}"
        )
    continued = answered(
        ran(
            [gate.rk, "state", "--config", str(gate.configuration)],
            environment=continuing,
            timeout=600,
        )
    )
    if not continued["ok"]:
        problems.append(f"the restored bounded read refused: {continued['violations']}")

    if problems:
        raise ReleaseError("\n".join(problems))
    gate.says(
        f"database: {len(applied.get('applied', ()))} migrations applied, verified, "
        f"dumped {gate.archive.stat().st_size // 1024}KB, restored and continued as "
        f"{opened['program_id'][:8]}"
    )


def privileges(gate: Gate) -> None:
    """Ticket 66's surface, on the database a migration built and the one a restore built.

    Two answers rather than one because they are built by different roles
    through different paths: `rk2_migrate` applies a corpus, `rk2_restore`
    replays an archive with `session_replication_role` set. A grant that
    survived the second and not the first is a hole in the artifact an operator
    recovers onto, and nothing before this ticket looked there.
    """
    problems = []
    for name in (MIGRATED_DATABASE, RESTORED_DATABASE):
        answer = json.loads(
            ran(
                [gate.python, "-c", SURFACE, gate.url("rk2_runtime", name)],
                environment=gate.environment(),
                timeout=600,
            ).stdout
        )
        if answer["excess"]:
            problems.append(
                f"{name} grants the runtime more than the surface: {answer['excess']}"
            )
        # Roles are the cluster's, not the database's, so this is one reading
        # about provisioning rather than two about the copies: every role the
        # design has is there. Absent ones are named; other `rk2` roles are not,
        # because a cluster an operator also runs something else on may hold
        # them and this gate is not the owner of that cluster.
        absent = [role for role in PROVISIONED if role not in answer["roles"]]
        if absent:
            problems.append(f"the cluster holding {name} is missing {absent}")
    if problems:
        raise ReleaseError("\n".join(problems))
    gate.says("privileges: the declared runtime surface holds on both databases")


def suites(gate: Gate) -> None:
    """Both suites, twice, from the export rather than from the checkout.

    Twice because once proves the suite passes and twice proves it left the
    server the way it found it: a case that commits a fixture it meant to purge
    passes on the first run and collides with itself on the second, and that is
    the failure a release finds in an operator's hands rather than here.

    The composed production suite is the same modules with a server, a
    container engine and the browser image behind them. It runs on a database
    of its own, provisioned by the suite itself, not on either of the two this
    gate built: a suite that dropped and recreated the database the restore
    produced would be taking away the artifact the stage before it just proved.
    """
    # No PYTHONPATH pointing at the exported sources: `unittest discover` puts
    # the export root on the path, which is what makes `tests` and `tools`
    # importable, and `redkraken` then resolves to the installed distribution.
    # That is the only copy this gate has any claim about.
    committed(gate)
    offline = gate.environment()
    live = dict(
        offline,
        RK_TEST_SUPERUSER_URL=gate.superuser,
        RK_TEST_DATABASE=SUITE_DATABASE,
        RK_TEST_CONTAINERS="1",
        RK_TEST_AGENT_IMAGE=os.environ.get("RK_TEST_AGENT_IMAGE", "python:3.14-slim"),
        RK_TEST_BROWSER_IMAGE=os.environ.get("RK_TEST_BROWSER_IMAGE", "rk2browser:test"),
    )
    problems = []
    ran_and_skipped = {}
    for name, environment in (("offline", offline), ("composed", live)):
        for attempt in (1, 2):
            started = time.monotonic()
            result = ran(
                [gate.python, "-m", "unittest", "discover", "-q"],
                environment=environment,
                cwd=gate.export,
                timeout=7200,
            )
            ran_and_skipped[name, attempt] = counts(result.stderr)
            total, skipped = ran_and_skipped[name, attempt]
            gate.says(
                f"suite {name} {attempt}/2: {total} tests, {skipped} skipped, in "
                f"{time.monotonic() - started:.0f}s"
            )

    # A suite exits zero when it runs nothing and when it skips everything, so
    # the exit code above is not the whole reading. Two more: both runs of a
    # suite selected the same tests, and the composed run skipped fewer of them
    # than the offline run did. The second is the one that makes "composed" mean
    # anything -- without a server and an engine the live cases skip, the suite
    # passes, and the gate would be reporting a second offline run under
    # another name.
    for name in ("offline", "composed"):
        if ran_and_skipped[name, 1][0] != ran_and_skipped[name, 2][0]:
            problems.append(
                f"the two {name} runs selected different tests: "
                f"{ran_and_skipped[name, 1][0]} then {ran_and_skipped[name, 2][0]}"
            )
        if not ran_and_skipped[name, 1][0]:
            problems.append(f"the {name} suite ran no tests")
    if ran_and_skipped["composed", 1][1] >= ran_and_skipped["offline", 1][1]:
        problems.append(
            "the composed suite skipped as much as the offline one "
            f"({ran_and_skipped['composed', 1][1]} against "
            f"{ran_and_skipped['offline', 1][1]}), so nothing live ran"
        )
    if problems:
        raise ReleaseError("\n".join(problems))


# -- what the stages need -----------------------------------------------------


def counts(report: str) -> tuple[int, int]:
    """How many tests a suite selected and how many of them it skipped."""
    total = re.search(r"Ran (\d+) test", report)
    skipped = re.search(r"skipped=(\d+)", report)
    if total is None:
        raise ReleaseError(f"a suite reported no count: {report.strip()[-2000:]}")
    return int(total.group(1)), int(skipped.group(1)) if skipped else 0


def committed(gate: Gate) -> None:
    """Make the export a checkout again, because part of the suite asks git.

    `check_secrets` decides what to scan by asking git which files a clone would
    carry, and a tarball cannot answer. Committing the extracted tree gives back
    exactly the answer the archive was made from -- the tracked files of `HEAD`,
    minus nothing -- without the suite reaching the checkout this gate is
    measuring instead of the export it built.

    The virtual environment the install stage put inside the export is ignored
    by the tree's own `.gitignore`, which is the file being restored here.
    """
    if (gate.export / ".git").exists():
        return
    for command in (
        ["git", "init", "-q", "-b", "release-gate"],
        ["git", "add", "-A"],
        [
            "git",
            "-c", "user.name=release gate",
            "-c", "user.email=gate@localhost",
            "commit", "-q", "-m", "the exported commit, as a checkout",
        ],
    ):
        ran(command, environment=gate.environment(), cwd=gate.export, timeout=300)


def drop(gate: Gate, name: str) -> None:
    """Take a database away if it is there, as the superuser that can.

    Run through the installed application's own driver, like every other reading
    this gate takes: it has no `psql` to rely on, and the one client it knows
    exists is the one it just built.
    """
    ran(
        [gate.python, "-c", DROPPING, gate.superuser, name],
        environment=gate.environment(),
        timeout=300,
    )


def preflight(gate: Gate, stages: tuple[str, ...]) -> list[str]:
    """What a selection of stages needs that is not there, before anything runs.

    Stages are separately selectable so that one of them can be worked on
    against a root an earlier `--keep` run left behind. What that costs is that
    a selection can name a stage whose input nobody built, and the failure then
    arrives an hour later as a missing file from whichever command reached for
    it first. These are the same preconditions, asked at the start and by name.

    Asked of the selection as a set: `--stage` appends in the order it is typed,
    and `--stage install --stage export` is the same selection as the other way
    round because `check` runs stages in `STAGES` order either way.
    """
    if unknown := [stage for stage in stages if stage not in STAGES]:
        return [f"no such stage: {', '.join(unknown)}"]

    wanted = set(stages)
    reasons = []
    for needs, built_by, there, what in (
        ({"install"}, "export", gate.export.is_dir(), f"nothing exported under {gate.export}"),
        (
            {"database", "topology", "privileges", "suites"},
            "install",
            gate.python.exists(),
            f"no installation under {gate.venv}",
        ),
        (
            {"topology", "privileges", "suites"},
            "database",
            gate.kept.exists(),
            f"no provisioned roles recorded in {gate.kept}",
        ),
    ):
        if wanted & needs and built_by not in wanted and not there:
            reasons.append(
                f"{what}: run `--stage {built_by}` too, or point --root at a root "
                "a kept run already built"
            )
    return reasons


def check(
    superuser: str,
    stages: tuple[str, ...] = STAGES,
    root: Path | None = None,
    keep: bool = False,
) -> str:
    """The gate. Returns the report, or raises with every reason it failed."""
    working = (
        Path(root)
        if root is not None
        else Path(tempfile.gettempdir()) / f"rk2-release-{secrets.token_hex(4)}"
    )
    gate = Gate(superuser=superuser, root=working, keep=keep)
    if reasons := preflight(gate, stages):
        raise ReleaseError("\n".join(reasons))

    for directory in (gate.root, gate.home, gate.root / "tmp"):
        directory.mkdir(parents=True, exist_ok=True)
    gate.configuration.write_text(PROGRAM, encoding="utf-8")

    try:
        for stage in STAGES:
            if stage in stages:
                RUNS[stage](gate)
        if not keep:
            leftovers = ((MIGRATED_DATABASE, RESTORED_DATABASE) if "database" in stages else ())
            leftovers += ((SUITE_DATABASE,) if "suites" in stages else ())
            for name in leftovers:
                drop(gate, name)
    finally:
        if not keep:
            shutil.rmtree(gate.root, ignore_errors=True)
    return "release gate ok:\n  " + "\n  ".join(gate.facts)


#: Name to stage, written out rather than looked up in `globals()`: the names
#: are already a constant and a module that finds its own functions by string is
#: a module where a typo in `STAGES` is a `KeyError` an hour into a run.
RUNS = {
    "export": export,
    "install": install,
    "database": database,
    "topology": topology,
    "privileges": privileges,
    "suites": suites,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--superuser-url",
        required=True,
        metavar="postgres://...",
        help="a disposable PostgreSQL 18 superuser connection string. This drops "
        "and creates databases on the server it names.",
    )
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        dest="stages",
        choices=STAGES,
        help="run one stage; repeatable. Every stage runs when none is named.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="where to build. A directory this run creates under TMPDIR by default.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the build directory and both databases behind, for looking at "
        "what a stage produced",
    )
    arguments = parser.parse_args(argv)
    try:
        print(check(
            arguments.superuser_url,
            tuple(arguments.stages) or STAGES,
            arguments.root,
            arguments.keep,
        ))
    except (ReleaseError, OSError, subprocess.SubprocessError) as error:
        print(f"release gate failed:\n{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
