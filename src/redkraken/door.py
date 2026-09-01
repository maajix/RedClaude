"""The egress door, run as the Agent network's one peer.

`isolation` holds every child to one topology: an internal network whose only
other peer is the proxy.  Nothing shipped could put a proxy there.  The door was
`rk proxy serve` on the operator's loopback interface, which is the one address
an internal network has no route to, so the boundary the runtime verifies could
only be satisfied by a container somebody stood up by hand.

This module is the other end of that assertion.  `main` is the door itself,
inside the container: it binds wide, which `proxy.serve` otherwise refuses,
because on an internal network with one peer the whole of what can reach the
port is the child the capability was minted for.  `start` is the half that runs
on this machine and decides whether that sentence is true -- the network is
internal and empty before anything is started, the door is its only peer
afterwards, and the name the children's proxy URL resolves to is the door and
not something that answered on the port.

The door is on two networks and the difference between them is the point.  The
Agent network carries no route anywhere: no database, no internet, no host.  The
second attachment carries both, and nothing but the door is on it -- which is
asserted rather than assumed, because the door binds every interface it has and
a peer on the egress network would be a peer that can reach the fence too.  So a
child reaches the internet only by asking the door to go, which is the same
thing as saying the fence sees every request.

Two things deliberately do not cross into the container.  The operator's home,
because a credential the door could read is a credential a compromised door
could spend; and a secret reference to the artifact key, because resolving one
inside the container would mean a service-account token inside the container.
The key crosses as a file or not at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

from redkraken import execution, isolation, migrate, pg, proxy, seal, store, tls
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    INVALID_CORPUS,
    Ledger,
    Report,
    render,
    report,
)


COMMAND = f"{proxy.COMMAND} door"

#: How `start` runs the other half of this file.  A module rather than a script
#: string: what runs in the container is code a reviewer can read, and a `-c`
#: argument is code that only exists in a process listing.
MODULE = f"{__package__}.door"

#: Printed by `main` once the door is listening *and* its fence is attached, and
#: what `start` waits for.  A marker rather than a sleep; `proxy.serve` says why
#: it is printed where it is.
READY = "rk2-door listening on "

#: What the door names after its endpoint: the database it opened. Ticket 149 --
#: `RK_PROXY_DATABASE_URL` is read once, when the container starts, and the door
#: outlives the command that started it by design (ticket 82). A run against a
#: second database therefore reaches a door that cannot see its Program, and it
#: cannot even file the blocked Receipt that would say so, because the label
#: counter it needs is keyed on a Program row that is not there. The door is the
#: only thing that knows which database it opened, so it is the thing that says.
#:
#: The name and not the host and port: a door on the Agent network and a runtime
#: on this machine reach one database by two addresses, and comparing those
#: would refuse the arrangement that is working.
SERVING = " serving "
IDENTITY = " identity "
CORPUS = " corpus "

PROGRAM_VISIBLE = "SELECT EXISTS (SELECT 1 FROM programs WHERE id = $1::uuid)"
NEWEST_APPLIED = f"""
SELECT id
FROM {migrate.META_SCHEMA}.schema_migrations
ORDER BY applied_seq DESC
LIMIT 1
"""

#: Where `start` puts what the door needs, inside the container.  Fixed paths for
#: the reason `isolation` gives for its own: a path that means one thing inside
#: and another outside is a path somebody will eventually read as the wrong one.
PACKAGE = "/opt/rk2-door"
STORE = "/var/lib/rk2-artifacts"
AUTHORITY = "/var/lib/rk2-authority"
KEY_FILE = "/opt/rk2-door-key"

#: This installation, as the door imports it.  Derived rather than configured:
#: the door has to run the code that started it, and an operator who could name
#: a different tree could be running a different fence than the one they read.
INSTALLATION = Path(__file__).resolve().parent.parent

#: The door's second attachment, over which it reaches the database and the
#: internet.  A network of the door's own, which the operator creates and this
#: command then refuses to use if anything else is on it -- not the engine's
#: default bridge, where every container on the machine is a peer and the door
#: binds a port all of them could reach.  A name rather than nothing, so the
#: README can spell one `docker network create` and every installation ends up
#: with the same one.
EGRESS = "rk2-egress"

#: The name this machine has from inside a container.  Added so an operator whose
#: Postgres listens on the host can name it in the fence URL at all -- without it
#: there is no spelling of "this machine" that resolves.
GATEWAY = "host.docker.internal"

#: The interface the listener is published on, and the only one.  Ticket 153:
#: a child reaches the door by container name over the Agent network and this
#: machine cannot, so every host-side verb that spends a capability -- `rk proxy
#: request`, `rk test replay`, and the `perform` lane that dispatches a replay --
#: had no address to name.  `proxy.endpoint` sends a capability to a loopback
#: address and nothing else, which is what decides this value: the one hop the
#: capability rides in the clear is defended by that hop staying on this machine,
#: and a listener published on every interface would be one reachable from the
#: egress network the door's second attachment is on.
PUBLISHED = "127.0.0.1"

#: How long a door gets to bind and reach its database before it is given up on,
#: and how often that is asked.  Generous because the first start of an authority
#: forks `openssl` twice on a cold page cache.
START_TIMEOUT = 60.0
POLL = 0.25


def main() -> int:
    """The door, inside the container `start` put it in.

    Reads its coordinates from the environment because that is what a container
    is given, and takes its port from the same variable the children's proxy URL
    is read from: a door listening on a port that URL does not name is a boundary
    that verifies and then answers nothing.

    Not an operator surface.  `rk proxy serve` is the door an operator runs, on
    loopback, and the difference between the two is exactly the bind this one is
    allowed and that one is not.

    What this half cannot do is check the sentence that licenses that bind.  A
    process inside a container has no engine to ask and no way to enumerate the
    peers of the networks it is on; it can see that it is contained, which is all
    `proxy._unbindable` asks of it, and no more.  So the topology is asserted by
    `start`, out where an engine exists, and running this module by hand in some
    other container gets a wide bind on a network nobody vouched for.  That is
    the boundary of the assertion, stated rather than hidden: the door is only
    the door when the command that starts it is the one that put it there.
    """
    ledger = Ledger()
    environment = os.environ
    missing = [
        name
        for name in (execution.PROXY_URL, proxy.DATABASE_VARIABLE, store.ROOT_VARIABLE)
        if not environment.get(name)
    ]
    if missing:
        ledger.fail(
            "boundary",
            "the door was started without " + ", ".join(f"${name}" for name in missing),
            code=INVALID_CONFIGURATION,
            source="environment",
        )
        return render(report(COMMAND, ledger))
    try:
        _, port = isolation.proxy_peer(environment[execution.PROXY_URL])
        settings = pg.settings_from_url(environment[proxy.DATABASE_VARIABLE])
    except (isolation.Unavailable, ValueError) as error:
        ledger.fail("boundary", str(error), code=INVALID_CONFIGURATION, source="environment")
        return render(report(COMMAND, ledger))

    migrations, refusals = migrate.load()
    if refusals:
        ledger.refuse(
            "migration_corpus",
            "the Door cannot name a version from a migration corpus that does not compile",
            refusals,
        )
        return render(report(COMMAND, ledger))
    if not migrations:
        ledger.fail(
            "migration_corpus",
            "the Door cannot name a version because its migration corpus is empty",
            code=INVALID_CORPUS,
            source=str(migrate.CORPUS),
        )
        return render(report(COMMAND, ledger))
    corpus_version = migrations[-1].identity

    authority = environment.get(proxy.AUTHORITY_VARIABLE)
    key = environment.get(seal.KEY_VARIABLE)
    return render(
        proxy.serve(
            settings,
            root=Path(environment[store.ROOT_VARIABLE]),
            # Wide, which is the whole reason this module exists. What may reach
            # the port is what `start` proved is on the network, and nothing on
            # that network has a route to anywhere else.
            host="0.0.0.0",
            port=port,
            authority=Path(authority) if authority else None,
            key=Path(key) if key else None,
            contained=True,
            announce_identity=lambda endpoint, identity: print(
                f"{READY}{endpoint}{SERVING}{settings.database}{IDENTITY}{identity}"
                f"{CORPUS}{corpus_version}",
                flush=True,
            ),
        )
    )


def start(
    environment: Mapping[str, str],
    *,
    egress: str = EGRESS,
    timeout: float = START_TIMEOUT,
) -> Report:
    """Put the door on the Agent network, as the only thing on it.

    Everything decidable without starting anything is decided first -- the
    boundary is described, the two directories the door writes are writable by
    the user it runs as, the key is a file and not a reference, the certificate
    children are handed is the one the door will sign with, and both networks are
    what they claim: the Agent's internal and empty, the egress one routable and
    empty.  Then the door is started on its egress attachment alone, so it has a
    database to reach before it is anywhere a child could see it, and joined to
    the Agent network only once it says it is serving.

    The last assertion is the one `isolation.run` makes before every child.
    Asked here so an operator learns the topology is wrong from the command that
    built it, rather than from the first run that used it.
    """
    ledger = Ledger()
    container, absent = execution.boundary(environment)
    if container is None:
        ledger.fail(
            "boundary",
            "no Agent boundary is described: " + ", ".join(f"${name}" for name in absent),
            code=INVALID_CONFIGURATION,
            source="environment",
        )
        return report(COMMAND, ledger)
    ledger.hold(
        "boundary", f"{container.image} on {container.network} as {container.proxy_container}"
    )

    try:
        engine = isolation.engine_for(container.engine)
        proxy_host, _ = isolation.proxy_peer(container.proxy_url)
        root = _writable(environment, store.ROOT_VARIABLE, "store")
        authority = _writable(environment, proxy.AUTHORITY_VARIABLE, "authority")
        key = _key(environment)
        certificate = _unmistaken(container, authority)
        _vacant(engine, container.proxy_container)
        isolation.empty_network(engine, container.network)
        _outward(engine, egress, container.network)
    except _Refused as refusal:
        ledger.fail(refusal.name, str(refusal), code=refusal.code, source=refusal.source)
        return report(COMMAND, ledger)
    except isolation.Unavailable as refusal:
        ledger.fail("topology", str(refusal), code=INVALID_CONFIGURATION, source="environment")
        return report(COMMAND, ledger)
    ledger.hold("store", f"exchanges are filed under {root}")
    ledger.hold("authority", f"{authority} holds the run's signing material")
    ledger.hold(
        "artifact_key",
        f"{key} is opened inside the door"
        if key
        else f"no key material (${seal.KEY_VARIABLE}); sealed responses are refused",
    )

    host_environment = {"PATH": os.environ.get("PATH", "")}
    try:
        _run(
            engine,
            container,
            egress=egress,
            root=root,
            authority=authority,
            key=key,
            fence=environment.get(proxy.DATABASE_VARIABLE, ""),
            host_environment=host_environment,
        )
        bound, serving, served_identity, served_corpus = _listening(
            engine, container.proxy_container, host_environment, timeout
        )
        wanted = pg.settings_from_url(environment[proxy.DATABASE_VARIABLE]).database
        if serving != wanted or not served_identity:
            raise isolation.Unavailable(
                f"the door serves {serving or 'a database it did not name'} and this "
                f"runtime serves {wanted}; the door's exact database identity is "
                f"{'stated' if served_identity else 'missing'}. The door "
                "reads its connection string once "
                "at startup and outlives the command that started it, so it is still "
                "the one a previous engagement began. Remove it and start it again."
            )
        if not served_corpus:
            raise isolation.Unavailable(
                "the Door announced no migration corpus version. Remove it and start it again."
            )
        isolation.join(
            engine, container.network, container.proxy_container, proxy_host, host_environment
        )
        if not certificate.is_file():
            raise isolation.Unavailable(
                f"the door is serving but wrote no certificate to {certificate}"
            )
    except isolation.Unavailable as refusal:
        isolation.remove(engine, container.proxy_container, host_environment)
        ledger.fail("listener", str(refusal), code=INVALID_CONFIGURATION, source="environment")
        return report(COMMAND, ledger)

    ledger.hold(
        "listener",
        f"bound {bound}; children reach it at {container.proxy_url}; corpus {served_corpus}",
    )
    ledger.hold(
        "topology",
        f"{container.network} is internal and its only peer is {proxy_host}; "
        f"the database and the internet are reached over {egress}",
    )
    ledger.hold("certificate", f"children verify targets against {certificate}")
    return report(
        COMMAND,
        ledger,
        container=container.proxy_container,
        endpoint=container.proxy_url,
        bound=bound,
        corpus=served_corpus,
        certificate=str(certificate),
        networks=[container.network, egress],
    )


class _Refused(Exception):
    """One start-time refusal, carried out to where the ledger is.

    Carried rather than reported where it is found, because every one of them is
    found before anything has been started and the caller is the only thing that
    knows that -- a helper that wrote to the ledger itself would be a helper each
    of whose callers has to remember to stop.
    """

    def __init__(self, name: str, detail: str, *, code: str, source: str) -> None:
        super().__init__(detail)
        self.name = name
        self.code = code
        self.source = source


def _writable(environment: Mapping[str, str], variable: str, fact: str) -> Path:
    """One directory the door writes, checked for the user the door runs as.

    Asked of the supervisor's environment and answered about the container's
    user, which is the whole difficulty: `os.access` here would answer for
    whoever ran the command, and the door runs as nobody.

    Not created if it is absent.  A directory this command made would be owned by
    the operator, which is exactly the state the next line refuses, so making one
    would only mean refusing something this command had just built.
    """
    given = environment.get(variable)
    if not given:
        raise _Refused(
            fact,
            f"the door needs somewhere to write: set ${variable}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    directory = Path(given).resolve()
    if not directory.is_dir():
        raise _Refused(
            fact,
            f"${variable} is not a directory: {directory}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    if not isolation.writable_by_the_child(directory):
        raise _Refused(
            fact,
            f"${variable} is not writable by {isolation.UID}:{isolation.GID}, who the "
            f"door runs as: chown {isolation.UID}:{isolation.GID} {directory}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    return directory


def _key(environment: Mapping[str, str]) -> Path | None:
    """Where the root secret is, if it is somewhere the door can be given.

    A secret reference is refused rather than resolved.  Resolving one inside the
    container needs a service-account token inside the container, and resolving
    it out here and passing the material in would put key material in an
    environment `docker inspect` prints.  So the contained door takes a file, and
    an installation keeping its key in a vault gives the door a file written out
    of that vault.
    """
    given = environment.get(seal.KEY_VARIABLE)
    if not given:
        return None
    location = seal.key_from_environment(given)
    if not isinstance(location, Path):
        raise _Refused(
            "artifact_key",
            f"a contained door cannot resolve a secret reference: give "
            f"${seal.KEY_VARIABLE} a file instead of {location}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    resolved = location.resolve()
    if not resolved.is_file():
        raise _Refused(
            "artifact_key",
            f"${seal.KEY_VARIABLE} is not a readable file: {resolved}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    return resolved


def _unmistaken(container: isolation.AgentContainer, authority: Path) -> Path:
    """The certificate children are handed, once it is the one the door signs with.

    Two variables name one file from opposite sides -- the door mints its
    authority into `$RK_PROXY_AUTHORITY`, and every child is handed
    `$RK_PROXY_CA_FILE` and verifies every target against it and nothing else.
    An installation where they disagree is one where every tunnelled request
    fails verification, discovered an hour into a run.
    """
    expected = authority / tls.CERTIFICATE_NAME
    certificate = Path(container.certificate).resolve()
    if certificate != expected:
        raise _Refused(
            "certificate",
            f"${proxy.CA_VARIABLE} does not name the authority this door signs with: "
            f"expected {expected}, not {certificate}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    return certificate


def _vacant(engine: str, name: str) -> None:
    """Refuse if something already holds the door's name.

    Not removed.  A container under this name is either the door already running,
    which this command must not take away from the runs using it, or the corpse
    of one that failed, which is the only remaining account of why.
    """
    if _ask(engine, ("container", "inspect", name)).returncode == 0:
        raise _Refused(
            "container",
            f"a container named {name} already exists; it is either the door or why "
            f"the last one stopped, so take it away yourself: {engine} rm --force {name}",
            code=INVALID_CONFIGURATION,
            source="environment",
        )


def _outward(engine: str, egress: str, network: str) -> None:
    """Refuse unless the second attachment is a way out that only the door is on.

    The door binds every interface it has, so the sentence that lets it bind wide
    -- the whole of what can reach the port is what `empty_network` proved was on
    the Agent network -- is only true if the other network it is on is empty as
    well.  A peer there is a peer that can reach the fence without a capability
    ever having been minted for it, which is the hole the internal network exists
    to close.  Held here rather than inside the container for the reason `main`
    gives.

    And it has to be a way out.  An egress attachment that is itself `--internal`
    carries no route to the database or the internet, so a door on one would come
    up, bind, and answer every request with a target nobody could reach.
    """
    if egress == network:
        raise _Refused(
            "egress",
            f"the egress network cannot be the Agent network: {egress} carries no route "
            f"out, and a door reached over it is a door reachable from it",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    internal, attached = isolation.peers(engine, egress)
    if internal:
        raise _Refused(
            "egress",
            f"the egress network {egress} was created --internal, so the door would "
            f"have no route to the database or the internet",
            code=INVALID_CONFIGURATION,
            source="environment",
        )
    if attached:
        raise _Refused(
            "egress",
            f"the egress network {egress} already has peers, and the door binds every "
            "interface it has: " + ", ".join(sorted(attached.values())),
            code=INVALID_CONFIGURATION,
            source="environment",
        )


def _run(
    engine: str,
    container: isolation.AgentContainer,
    *,
    egress: str,
    root: Path,
    authority: Path,
    key: Path | None,
    fence: str,
    host_environment: Mapping[str, str],
) -> None:
    """Start the door on its egress attachment, denied what every child is denied.

    Not `--rm`: the door outlives the command that starts it, and one that
    vanished when it failed would take the only account of why with it.  The
    environment is a positive list for the reason `isolation.container_environment`
    gives -- a variable absent from here cannot reach the door by being
    forgotten, only by being added on purpose.
    """
    inside = {
        "HOME": "/",
        "TMPDIR": isolation.TMPDIR,
        "LC_ALL": "C.UTF-8",
        isolation.IMPORT_PATH: PACKAGE,
        # Buffered output is a readiness marker that arrives after the thing
        # waiting for it has given up.
        "PYTHONUNBUFFERED": "1",
        execution.PROXY_URL: container.proxy_url,
        proxy.DATABASE_VARIABLE: fence,
        store.ROOT_VARIABLE: STORE,
        proxy.AUTHORITY_VARIABLE: AUTHORITY,
    }
    mounts = [
        f"type=bind,src={INSTALLATION},dst={PACKAGE},readonly",
        f"type=bind,src={root},dst={STORE}",
        f"type=bind,src={authority},dst={AUTHORITY}",
    ]
    if key is not None:
        inside[seal.KEY_VARIABLE] = KEY_FILE
        mounts.append(f"type=bind,src={key},dst={KEY_FILE},readonly")

    listening = proxy.peer(container.proxy_url)[1]
    arguments = [
        *isolation.hardened(container.proxy_container, ephemeral=False),
        "--detach",
        "--network",
        egress,
        "--add-host",
        f"{GATEWAY}:host-gateway",
        "--publish",
        f"{PUBLISHED}:{listening}:{listening}",
        "--tmpfs",
        f"{isolation.TMPDIR}:rw,nosuid,nodev,noexec,size=64m,mode=1777",
    ]
    for mount in mounts:
        arguments.extend(("--mount", mount))
    for name, value in sorted(inside.items()):
        arguments.extend(("--env", f"{name}={value}"))
    arguments.extend((container.image, isolation.INTERPRETER, "-m", MODULE))

    isolation.engine_command(
        engine,
        arguments,
        host_environment,
        f"the door container cannot be started: {container.proxy_container}",
    )


def _listening(
    engine: str, name: str, host_environment: Mapping[str, str], timeout: float
) -> tuple[str, str, str, str]:
    """Wait for the door to say it is serving, or say what it said instead.

    Answers where it is bound, which database it opened, its exact database
    identity and the newest migration in the corpus it loaded at startup. The
    refusal carries the door's own last line rather than a bare timeout, because
    the usual reason a door never listens is a fence URL it could not open, and
    that sentence is already written in the report it printed.

    A door that announces no database is one from a build before ticket 149, and
    empty names are returned rather than guessed at: the caller refuses them,
    and a door too old to say is exactly the stale door this question is asked
    about.
    """
    deadline = time.monotonic() + timeout
    while True:
        logs = _ask(engine, ("logs", name), host_environment)
        written = logs.stdout + logs.stderr
        for line in written.splitlines():
            if line.startswith(READY):
                said = line[len(READY) :].strip()
                bound, _, served = said.partition(SERVING.strip())
                serving, _, identified = served.partition(IDENTITY.strip())
                identity, _, corpus = identified.partition(CORPUS.strip())
                return bound.strip(), serving.strip(), identity.strip(), corpus.strip()
        if time.monotonic() >= deadline:
            said = written.strip().splitlines()
            raise isolation.Unavailable(
                f"the door did not serve within {timeout:g}s: "
                + (said[-1] if said else "it said nothing at all")
            )
        time.sleep(POLL)


def preflight(
    container: isolation.AgentContainer,
    connection: pg.Connection,
    program_id: str,
) -> str:
    """Prove the runtime and the already-running Door see this Program together."""
    if not connection.execute(PROGRAM_VISIBLE, (program_id,)).scalar():
        raise isolation.Unavailable(
            f"Program {program_id} is not visible on the runtime database"
        )
    expected = pg.database_identity(connection)
    engine = isolation.engine_for(container.engine)
    isolation.peered(engine, container)
    _, serving, actual, door_version = _listening(
        engine,
        container.proxy_container,
        {"PATH": os.environ.get("PATH", "")},
        0.0,
    )
    wanted = connection.settings.database
    if serving != wanted or actual != expected:
        raise isolation.Unavailable(
            f"the Door serves {serving or 'an unnamed database'} but the runtime "
            f"serves {wanted}; their exact database identities do not match. "
            "Restart the Door against this Program's database before starting a child."
        )
    applied_version = connection.execute(NEWEST_APPLIED).scalar()
    if not applied_version:
        raise isolation.Unavailable(
            "the runtime database has no applied migration version to compare with the Door"
        )
    if not door_version:
        raise isolation.Unavailable(
            f"Door {container.proxy_container} announces no migration corpus version; "
            "restart the Door before starting a child"
        )
    if door_version < applied_version:
        raise isolation.Unavailable(
            f"Door {container.proxy_container} runs corpus {door_version}, older than newest "
            f"applied migration {applied_version}; restart the Door before starting a child"
        )
    if door_version > applied_version:
        raise isolation.Unavailable(
            f"Door {container.proxy_container} runs corpus {door_version}, newer than newest "
            f"applied migration {applied_version}; run `rk db migrate` before starting a child"
        )
    return (
        f"{container.proxy_container} and the runtime both serve {wanted} and Program "
        f"{program_id}; Door and database version {applied_version}"
    )


def _ask(
    engine: str, arguments: tuple[str, ...], host_environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """One engine command whose answer is read rather than acted on."""
    return subprocess.run(
        [engine, *arguments],
        env=dict(host_environment or {"PATH": os.environ.get("PATH", "")}),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


if __name__ == "__main__":
    sys.exit(main())
