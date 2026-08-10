"""The operator command line.

The CLI is an adapter: it parses arguments, calls one runtime operation and
renders its structured result. It holds no policy of its own, so the local UI
and the CLI can never develop different interpretations of the same state.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from redkraken import (
    __version__,
    artifact,
    backup,
    doctor,
    migrate,
    pg,
    program,
    proxy,
    scope,
    state,
)
from redkraken.outcome import (
    DATABASE_UNREACHABLE,
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)


#: Which environment variable holds the connection string for which command.
#: They are separate variables because they are separate roles: the whole point
#: of the role split is lost if one exported URL can do everything.
SUPERUSER_URL = "RK_SUPERUSER_URL"
MIGRATE_URL = "RK_MIGRATE_URL"
RESTORE_URL = "RK_RESTORE_URL"
DATABASE_URL = "RK_DATABASE_URL"
STATE_URL = "RK_STATE_URL"
#: The egress door's own connection, held as `rk2_proxy`: EXECUTE on two writers
#: and no receipt DML at all. Spelled out rather than folded into
#: `RK_DATABASE_URL` because a fence running as the runtime would be a fence with
#: the privileges of the thing it fences.
PROXY_DATABASE_URL = "RK_PROXY_DATABASE_URL"

DEFAULT_DATABASE = "rk2"

#: Where the door listens when nobody says otherwise. Loopback because a
#: capability is bearer material and the runtime is on this machine; a fixed port
#: because the operator has to be able to name it in `RK_PROXY_URL` before the
#: process that will use it starts.
DEFAULT_PROXY_HOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 8080


@dataclass(frozen=True)
class _Source:
    """Where one input comes from, in the three names it has.

    The flag, the variable and the name a refusal is filed under always travel
    together, and an operator reading a refusal has to be able to act on it: a
    report that named the wrong variable would send them to edit an environment
    the command never read. Which is also why `fact` is the name the operation
    itself files under and not a spelling invented here -- a path resolved as
    `ca_file` and refused as `trust_root` is one input under two names.
    """

    fact: str
    flag: str
    variable: str


SUPERUSER = _Source("connection_string", "--url", SUPERUSER_URL)
MIGRATION = _Source("connection_string", "--url", MIGRATE_URL)
RESTORATION = _Source("connection_string", "--url", RESTORE_URL)
RUNTIME = _Source("connection_string", "--url", DATABASE_URL)
AGENT = _Source("state_connection_string", "--state-url", STATE_URL)
FENCE = _Source("connection_string", "--url", PROXY_DATABASE_URL)

#: Where the door listens, which is neither a role nor a store. The capability
#: is sent to this address and to nothing else, and `proxy.endpoint` refuses any
#: spelling of it that is not plain HTTP on the loopback interface.
PROXY = _Source("proxy_url", "--proxy", proxy.PROXY_URL)

#: The two halves of the trust that lets the door see inside a tunnel. The
#: directory is the door's and holds a signing key; the file is the certificate
#: out of it, and is the only part anything else is given. Two names because an
#: installation that exported one for both would be exporting the key.
AUTHORITY = _Source("authority", "--authority", proxy.AUTHORITY_VARIABLE)
TRUST = _Source("trust_root", "--ca", proxy.CA_VARIABLE)

#: Where the bytes an exchange produced are written, which is a directory and
#: not a row. It has a variable of its own because an operator who moved the
#: database has not thereby moved the bytes.
ARTIFACTS = _Source("artifact_root", "--artifacts", artifact.ROOT_VARIABLE)

#: And the key those bytes are sealed with. Separate from the store for the
#: reason the store is separate from the connection string --
#: an operator who copied the bytes somewhere has not thereby copied the key,
#: and the sealed artifacts are worth exactly as much as that stays true.
KEYS = _Source("artifact_key", "--key", artifact.KEY_VARIABLE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rk",
        description="Operate the RedKraken bug-bounty hunting harness.",
    )
    parser.add_argument("--version", action="version", version=f"rk {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    diagnose = commands.add_parser(
        "doctor",
        help="report local runtime readiness and validate a Program configuration",
    )
    diagnose.add_argument(
        "--config",
        type=Path,
        metavar="path",
        help="a Program configuration file to validate",
    )
    diagnose.set_defaults(run=_doctor)

    runner = commands.add_parser(
        "run",
        help=f"create or resume the Program a configuration names (${DATABASE_URL})",
    )
    _add_url(runner, RUNTIME)
    runner.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the Program configuration to run under",
    )
    runner.add_argument(
        "--accept-change",
        action="store_true",
        help=(
            "record a new configuration revision when the policy has changed; "
            "without it a changed policy is refused rather than adopted"
        ),
    )
    runner.set_defaults(run=_run)

    policy = commands.add_parser(
        "scope",
        help="compile a Program configuration and decide what it authorises",
        description=(
            "Compile the Scope Policy and answer questions about it. Reaches no "
            "database: a verdict is a function of the policy and the request, so "
            "this is the same decision the runtime makes. A denial is an answer "
            "and exits 0; a configuration that will not compile is refused."
        ),
    )
    policy.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the Program configuration to compile",
    )
    policy.add_argument(
        "--url",
        action="append",
        default=[],
        dest="urls",
        metavar="https://...",
        help="decide one request; repeatable",
    )
    policy.add_argument(
        "--host",
        action="append",
        default=[],
        dest="hosts",
        metavar="host[:port][/path]",
        help="decide one host as the projection would; repeatable",
    )
    policy.add_argument(
        "--subtree",
        action="append",
        default=[],
        dest="subtrees",
        metavar="domain",
        help="decide a whole domain as a wildcard seed; repeatable",
    )
    policy.add_argument(
        "--callback",
        action="append",
        default=[],
        dest="callbacks",
        metavar="host",
        help="decide whether an observed interaction arrived on a declared channel",
    )
    policy.add_argument(
        "--action",
        action="append",
        default=[],
        dest="actions",
        metavar="permission",
        help=(
            "ask about one rule of engagement; repeatable, and all five are "
            "reported when none is named"
        ),
    )
    policy.add_argument(
        "--discovery",
        action="append",
        default=[],
        dest="techniques",
        metavar="technique",
        help=(
            "ask about one discovery technique; repeatable, and all five are "
            "reported when none is named"
        ),
    )
    policy.set_defaults(run=_scope)

    inspect = commands.add_parser(
        "state",
        help=(
            "read one Program's records as the agent connection sees them "
            f"(${DATABASE_URL} and ${STATE_URL})"
        ),
    )
    _add_url(inspect, RUNTIME)
    # The second string is added here rather than through `_add_url`: it is the
    # only command with two, and the help has to say which role each one is.
    inspect.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=f"the agent connection string (default: ${AGENT.variable})",
    )
    inspect.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program to read",
    )
    inspect.add_argument(
        "--label",
        metavar="label",
        help="read one full record by its label instead of only the compact index",
    )
    inspect.add_argument(
        "--limit",
        type=int,
        default=state.DEFAULT_RECORDS,
        metavar="n",
        help=f"records per kind in the compact read (default: {state.DEFAULT_RECORDS})",
    )
    inspect.add_argument(
        "--bytes",
        dest="byte_limit",
        type=int,
        default=state.DEFAULT_BYTES,
        metavar="n",
        help=(
            "the size the record index must fit under; a full record asked for "
            f"by --label is returned whole (default: {state.DEFAULT_BYTES})"
        ),
    )
    inspect.set_defaults(run=_state)

    artifacts = commands.add_parser(
        "artifact", help="store, read and verify this Program's content-addressed artifacts"
    )
    verbs = artifacts.add_subparsers(dest="operation", required=True, metavar="operation")

    deposit = verbs.add_parser(
        "put",
        help=(
            "store one file by the hash of its bytes and record that this "
            f"Program holds it (${DATABASE_URL})"
        ),
    )
    _add_url(deposit, RUNTIME)
    _add_root(deposit)
    deposit.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program that will hold it",
    )
    deposit.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="path",
        help="the file whose bytes are stored",
    )
    deposit.add_argument(
        "--kind",
        default="runtime",
        choices=artifact.KINDS,
        help="why this Program holds these bytes (default: runtime)",
    )
    deposit.add_argument(
        "--content-type",
        dest="content_type",
        metavar="type",
        help="what the bytes are, recorded beside them and never inferred from them",
    )
    deposit.set_defaults(run=_artifact_put)

    fetch = verbs.add_parser(
        "get",
        help=(
            "read one artifact by label, bounded, as the agent connection sees "
            f"it (${DATABASE_URL} and ${STATE_URL})"
        ),
    )
    _add_url(fetch, RUNTIME)
    fetch.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=f"the agent connection string (default: ${AGENT.variable})",
    )
    _add_root(fetch)
    fetch.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program to read as",
    )
    fetch.add_argument(
        "--label",
        required=True,
        metavar="label",
        help="the artifact's label; there is no way to ask for one by hash",
    )
    fetch.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="n",
        help="where the returned range starts (default: 0)",
    )
    fetch.add_argument(
        "--bytes",
        dest="byte_limit",
        type=int,
        default=artifact.DEFAULT_BYTES,
        metavar="n",
        help=(
            "how many bytes the range carries; what is left out is reported "
            f"rather than dropped (default: {artifact.DEFAULT_BYTES})"
        ),
    )
    fetch.set_defaults(run=_artifact_get)

    check = verbs.add_parser(
        "audit",
        help=(
            "read every artifact this Program holds and hold its hash against "
            f"its bytes (${DATABASE_URL})"
        ),
    )
    _add_url(check, RUNTIME)
    _add_root(check)
    check.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose holdings are checked",
    )
    check.set_defaults(run=_artifact_audit)

    close = verbs.add_parser(
        "seal",
        help=(
            "store one exchange as a redacted artifact and an encrypted wire "
            f"artifact (${DATABASE_URL})"
        ),
    )
    _add_url(close, RUNTIME)
    _add_root(close)
    _add_key(close)
    close.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program that will hold both views",
    )
    close.add_argument(
        "--wire",
        type=Path,
        required=True,
        metavar="path",
        help="the file whose bytes went over the wire; stored only encrypted",
    )
    close.add_argument(
        "--redacted",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "the file the agent may see; stored as an ordinary artifact and the "
            "only one of the two that gets a label"
        ),
    )
    close.add_argument(
        "--content-type",
        dest="content_type",
        metavar="type",
        help="what the bytes are, recorded beside them and never inferred from them",
    )
    close.set_defaults(run=_artifact_seal)

    release = verbs.add_parser(
        "open",
        help=(
            "decrypt one wire artifact to a file, deliberately and audited "
            f"(${DATABASE_URL})"
        ),
    )
    _add_url(release, RUNTIME)
    _add_root(release)
    _add_key(release)
    release.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose wire artifact is opened",
    )
    release.add_argument(
        "--label",
        required=True,
        metavar="label",
        help=(
            "the agent-visible label of the pair; the wire view has no label of "
            "its own and there is no way to ask for one by hash"
        ),
    )
    release.add_argument(
        "--into",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "where the plaintext is written, created for this user alone; an "
            "existing file is refused rather than overwritten"
        ),
    )
    release.add_argument(
        "--authorize",
        metavar="reason",
        help=(
            "why this is being opened, recorded in the audit log; without it the "
            "command refuses before it reads any key material"
        ),
    )
    release.set_defaults(run=_artifact_open)

    door = commands.add_parser(
        "proxy", help="the egress door: run it, and spend one capability through it"
    )
    operations = door.add_subparsers(dest="operation", required=True, metavar="operation")

    listener = operations.add_parser(
        "serve",
        help=(
            "run the egress fence until it is interrupted, as the proxy role "
            f"(${PROXY_DATABASE_URL})"
        ),
    )
    _add_url(listener, FENCE)
    _add_root(
        listener,
        help=(
            "where the transcripts of each exchange are filed, under the hash of "
            f"their bytes (default: ${ARTIFACTS.variable})"
        ),
    )
    listener.add_argument(
        "--host",
        default=DEFAULT_PROXY_HOST,
        metavar="address",
        help=(
            "which loopback interface to listen on; a capability is bearer "
            "material, so a routable one is refused rather than bound "
            f"(default: {DEFAULT_PROXY_HOST})"
        ),
    )
    listener.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PROXY_PORT,
        metavar="port",
        help=f"the port to listen on (default: {DEFAULT_PROXY_PORT})",
    )
    listener.add_argument(
        AUTHORITY.flag,
        dest="authority",
        type=Path,
        metavar="directory",
        help=(
            "where this run's certificate authority lives, which is what lets "
            "the door read inside a tunnel; without one a CONNECT is refused "
            f"rather than relayed (default: ${AUTHORITY.variable})"
        ),
    )
    listener.set_defaults(run=_proxy_serve)

    spend = operations.add_parser(
        "request",
        help=(
            "open one Tool run, mint its capability and spend it on one request "
            f"through the door (${DATABASE_URL})"
        ),
    )
    _add_url(spend, RUNTIME)
    spend.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose scope decides this request",
    )
    spend.add_argument(
        PROXY.flag,
        dest="proxy_url",
        metavar="http://127.0.0.1:port",
        help=f"where the door is listening (default: ${PROXY.variable})",
    )
    spend.add_argument(
        TRUST.flag,
        dest="ca_file",
        type=Path,
        metavar="path",
        help=(
            "the door's certificate, which an https target is verified against "
            "and nothing else; the door reports it when it starts "
            f"(default: ${TRUST.variable})"
        ),
    )
    spend.add_argument(
        "--method",
        default="GET",
        metavar="verb",
        help="the HTTP method, which the authorized Tool run has to agree with (default: GET)",
    )
    spend.add_argument(
        "target",
        metavar="url",
        help=(
            "the absolute URL to request; decided against the compiled policy "
            "twice, once here and once at the door"
        ),
    )
    spend.set_defaults(run=_proxy_request)

    database = commands.add_parser("db", help="create, migrate, verify and move the database")
    operations = database.add_subparsers(dest="operation", required=True, metavar="operation")

    provision = operations.add_parser(
        "provision",
        help=f"create the roles, the database and the extension (superuser; ${SUPERUSER_URL})",
    )
    _add_url(provision, SUPERUSER)
    provision.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        metavar="name",
        help=f"the database to create (default: {DEFAULT_DATABASE})",
    )
    provision.set_defaults(run=_provision)

    migrate_ = operations.add_parser(
        "migrate", help=f"apply every pending migration, then verify (${MIGRATE_URL})"
    )
    _add_url(migrate_, MIGRATION)
    migrate_.set_defaults(run=_migrate)

    verify = operations.add_parser(
        "verify", help=f"run every registered integrity check (${MIGRATE_URL})"
    )
    _add_url(verify, MIGRATION)
    _add_root(
        verify,
        help=(
            "also hold every recorded artifact against the bytes filed under it; "
            f"no registered check can open a file (default: ${ARTIFACTS.variable})"
        ),
    )
    verify.set_defaults(run=_verify)

    status = operations.add_parser(
        "status", help=f"report what is applied and what is pending (${MIGRATE_URL})"
    )
    _add_url(status, MIGRATION)
    status.set_defaults(run=_status)

    dump = operations.add_parser("dump", help=f"write a full archive (${MIGRATE_URL})")
    _add_url(dump, MIGRATION)
    dump.add_argument("--to", type=Path, required=True, metavar="path", help="where to write it")
    dump.set_defaults(run=_dump)

    restore = operations.add_parser(
        "restore", help=f"restore an archive into an empty database (${RESTORE_URL})"
    )
    _add_url(restore, RESTORATION)
    restore.add_argument("--from", dest="archive", type=Path, required=True, metavar="path")
    restore.set_defaults(run=_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return arguments.run(arguments)


def _add_url(parser: argparse.ArgumentParser, source: _Source) -> None:
    parser.add_argument(
        source.flag,
        metavar="postgresql://...",
        help=f"the connection string (default: ${source.variable})",
    )
    parser.set_defaults(url_source=source)


def _add_root(parser: argparse.ArgumentParser, help: str | None = None) -> None:
    parser.add_argument(
        ARTIFACTS.flag,
        type=Path,
        metavar="dir",
        help=help or f"where the artifact bytes live (default: ${ARTIFACTS.variable})",
    )


def _add_key(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        KEYS.flag,
        dest="key",
        type=Path,
        metavar="path",
        help=(
            "the file holding the root secret, readable by its owner alone and "
            f"kept outside the database (default: ${KEYS.variable})"
        ),
    )


def _doctor(arguments: argparse.Namespace) -> int:
    diagnosis = doctor.diagnose(arguments.config)
    print(json.dumps(diagnosis.as_dict(), indent=2))
    return diagnosis.exit_code


def _scope(arguments: argparse.Namespace) -> int:
    return _render(
        scope.diagnose(
            arguments.config,
            urls=tuple(arguments.urls),
            hosts=tuple(arguments.hosts),
            subtrees=tuple(arguments.subtrees),
            callbacks=tuple(arguments.callbacks),
            actions=tuple(arguments.actions),
            techniques=tuple(arguments.techniques),
        )
    )


def _run(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        program.COMMAND,
        lambda settings: program.run(
            settings, arguments.config, accept_change=arguments.accept_change
        ),
    )


def _state(arguments: argparse.Namespace) -> int:
    """Two connection strings, because the read is about two roles.

    The Program is resolved on the runtime connection and its records are read
    on the agent's, which cannot resolve one. A single URL doing both would be
    a single role doing both, and the isolation this command reports would be
    a description of an arrangement that was not in force while it read.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, state.COMMAND)
    agent = _url(ledger, AGENT, arguments.state_url, state.COMMAND)
    if runtime is None or agent is None:
        return _render(report(state.COMMAND, ledger))
    return _render(
        _guarded(
            state.COMMAND,
            lambda: state.read(
                runtime,
                agent,
                arguments.config,
                label=arguments.label,
                per_kind=arguments.limit,
                byte_limit=arguments.byte_limit,
            ),
        )
    )


def _artifact_put(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.PUT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(artifact.PUT, ledger))
    return _render(
        _guarded(
            artifact.PUT,
            lambda: artifact.put(
                runtime,
                arguments.config,
                arguments.source,
                root=root,
                kind=arguments.kind,
                content_type=arguments.content_type,
            ),
        )
    )


def _artifact_get(arguments: argparse.Namespace) -> int:
    """Two connection strings and a directory, because the read is about all three.

    The Program is resolved on the runtime connection and the label on the
    agent's, for the reason `rk state` gives. The bytes are neither connection's:
    the database holds a hash, and whether the hash is still true of what is on
    disk is a question only this process can ask.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.GET)
    agent = _url(ledger, AGENT, arguments.state_url, artifact.GET)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or agent is None or root is None:
        return _render(report(artifact.GET, ledger))
    return _render(
        _guarded(
            artifact.GET,
            lambda: artifact.get(
                runtime,
                agent,
                arguments.config,
                root=root,
                label=arguments.label,
                offset=arguments.offset,
                limit=arguments.byte_limit,
            ),
        )
    )


def _artifact_audit(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.AUDIT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(artifact.AUDIT, ledger))
    return _render(
        _guarded(
            artifact.AUDIT,
            lambda: artifact.audit(runtime, arguments.config, root=root),
        )
    )


def _artifact_seal(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.SEAL)
    root = _root(ledger, arguments.artifacts)
    key = _key(ledger, arguments.key)
    if runtime is None or root is None or key is None:
        return _render(report(artifact.SEAL, ledger))
    return _render(
        _guarded(
            artifact.SEAL,
            lambda: artifact.seal_wire(
                runtime,
                arguments.config,
                arguments.wire,
                arguments.redacted,
                root=root,
                key=key,
                content_type=arguments.content_type,
            ),
        )
    )


def _artifact_open(arguments: argparse.Namespace) -> int:
    """The one adapter that hands a report back without the thing it produced.

    What was decrypted is in the file `--into` names. The report says its path,
    its length and its hash, which is what an operator needs to find it and what
    a log may carry.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.OPEN)
    root = _root(ledger, arguments.artifacts)
    key = _key(ledger, arguments.key)
    if runtime is None or root is None or key is None:
        return _render(report(artifact.OPEN, ledger))
    return _render(
        _guarded(
            artifact.OPEN,
            lambda: artifact.open_wire(
                runtime,
                arguments.config,
                root=root,
                key=key,
                label=arguments.label,
                into=arguments.into,
                authorize=arguments.authorize,
            ),
        )
    )


def _proxy_serve(arguments: argparse.Namespace) -> int:
    """The one command that does not return until an operator stops it.

    Its report is written when the listener closes, which is the only moment it
    has anything final to say. What an operator needs before then is on the
    socket: the door answers every request, refused or served, with a decision
    header and the name of the record it wrote.
    """
    ledger = Ledger()
    settings = _url(ledger, FENCE, arguments.url, proxy.SERVE)
    root = _root(ledger, arguments.artifacts)
    if settings is None or root is None:
        return _render(report(proxy.SERVE, ledger))
    authority = _path(AUTHORITY, arguments.authority)
    return _render(
        _guarded(
            proxy.SERVE,
            lambda: proxy.serve(
                settings,
                root=root,
                host=arguments.host,
                port=arguments.port,
                authority=authority,
            ),
        )
    )


def _proxy_request(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, proxy.REQUEST)
    endpoint = _proxy(ledger, arguments.proxy_url)
    if runtime is None or endpoint is None:
        return _render(report(proxy.REQUEST, ledger))
    ca_file = _path(TRUST, arguments.ca_file)
    return _render(
        _guarded(
            proxy.REQUEST,
            lambda: proxy.send(
                runtime,
                arguments.config,
                arguments.target,
                proxy_url=endpoint,
                method=arguments.method,
                ca_file=ca_file,
            ),
        )
    )


def _provision(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        "db provision",
        lambda settings: migrate.provision(
            settings,
            arguments.database,
            passwords=migrate.passwords_from_environment(),
        ),
    )


def _migrate(arguments: argparse.Namespace) -> int:
    return _with_settings(arguments, "db migrate", migrate.migrate)


def _verify(arguments: argparse.Namespace) -> int:
    # Not refused when absent, unlike `rk artifact`: the gate has an answer
    # either way, and which one it gave is in the report. Refusing here would
    # make an operator who has no store unable to run the gate at all.
    store = artifact.root_from_environment(arguments.artifacts)
    return _with_settings(
        arguments, "db verify", lambda settings: migrate.verify(settings, store=store)
    )


def _status(arguments: argparse.Namespace) -> int:
    return _with_settings(arguments, "db status", migrate.status)


def _dump(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments, "db dump", lambda settings: backup.dump(settings, arguments.to)
    )


def _restore(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments, "db restore", lambda settings: backup.restore(settings, arguments.archive)
    )


def _with_settings(
    arguments: argparse.Namespace,
    command: str,
    operation: Callable[[pg.Settings], Report],
) -> int:
    """Resolve the connection string, run one operation and render its report.

    A connection string that cannot be read is reported in the same shape as
    everything else rather than as a traceback: an operator scripting these
    commands parses one document whether the run reached the database or not.
    """
    ledger = Ledger()
    settings = _url(ledger, arguments.url_source, arguments.url, command)
    if settings is None:
        return _render(report(command, ledger))
    return _render(_guarded(command, lambda: operation(settings)))


def _guarded(command: str, operation: Callable[[], Report]) -> Report:
    """Run one operation, reporting a database that stops answering part-way.

    Each operation classifies the failures it goes looking for; this is the
    boundary for the ones nobody can enumerate — a backend restart, a pooler
    dropping an idle socket — which arrive at whichever statement happened to be
    next.
    """
    try:
        return operation()
    except pg.ConnectionError_ as error:
        return _refusal(command, "connection", str(error), DATABASE_UNREACHABLE)
    except pg.DatabaseError as error:
        return _refusal(command, "database", str(error), INVALID_CONFIGURATION)


def _render(result: Report) -> int:
    print(json.dumps(result.as_dict(), indent=2))
    return result.exit_code


def _refusal(command: str, name: str, detail: str, code: str) -> Report:
    ledger = Ledger()
    ledger.fail(name, f"the command stopped part-way: {detail}", code=code, source="database")
    return report(command, ledger)


def _root(ledger: Ledger, given: Path | None) -> Path | None:
    """The artifact store, from the argument or from the variable behind it.

    Refused rather than defaulted. A default would file bytes somewhere nobody
    chose, and the next run with a different working directory would report a
    store that had lost every artifact in it.
    """
    root = artifact.root_from_environment(given)
    if root is None:
        ledger.fail(
            ARTIFACTS.fact,
            f"no artifact store: pass {ARTIFACTS.flag} or set {ARTIFACTS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ARTIFACTS.variable}",
        )
    return root


def _proxy(ledger: Ledger, given: str | None) -> str | None:
    """Where the capability is allowed to go, from the argument or the variable.

    Refused rather than defaulted, for the same reason as the store and a sharper
    one: a default would be an address this installation did not choose, and the
    thing that would be sent to it is bearer material. Whether the address is one
    a capability may travel to at all is `proxy.endpoint`'s question, asked by the
    operation before it opens anything.
    """
    url = given or os.environ.get(PROXY.variable)
    if not url:
        ledger.fail(
            PROXY.fact,
            f"no proxy endpoint: pass {PROXY.flag} or set {PROXY.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{PROXY.variable}",
        )
        return None
    return url


def _path(source: _Source, given: Path | None) -> Path | None:
    """One optional path, from the argument or from the variable behind it.

    No ledger, because absence is not a refusal here: a door with no authority
    refuses tunnels and says so, and a request that needs a trust root and has
    none is refused by the operation that knows it needs one. Failing in this
    function instead would make an operator name a certificate to send one plain
    HTTP request.
    """
    value = given or os.environ.get(source.variable)
    return Path(value) if value else None


def _key(ledger: Ledger, given: Path | None) -> Path | None:
    """The key file, from the argument or from the variable behind it.

    Refused rather than defaulted, and for a sharper version of the store's
    reason: a default would be a key material path this installation did not
    choose, which either does not exist or belongs to something else. Whether the
    file is one this process will use is `seal.load_root`'s question; this only
    establishes that an operator named one.
    """
    key = artifact.key_from_environment(given)
    if key is None:
        ledger.fail(
            KEYS.fact,
            f"no key material: pass {KEYS.flag} or set {KEYS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{KEYS.variable}",
        )
    return key


def _url(
    ledger: Ledger, source: _Source, given: str | None, command: str
) -> pg.Settings | None:
    """One connection string, from the argument or from the variable behind it."""
    url = given or os.environ.get(source.variable)
    if not url:
        ledger.fail(
            source.fact,
            f"no connection string: pass {source.flag} or set {source.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{source.variable}",
        )
        return None
    try:
        return pg.settings_from_url(url, application_name=f"rk {command}")
    except ValueError as error:
        # The parser's own words, which name the unsupported parameter but never
        # echo the string: a connection string carries a password.
        ledger.fail(
            source.fact,
            f"the connection string cannot be used: {error}",
            code=INVALID_CONFIGURATION,
            source=(
                f"argument:{source.flag}" if given else f"environment:{source.variable}"
            ),
        )
        return None
