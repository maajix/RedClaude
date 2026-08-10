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

from redkraken import __version__, backup, doctor, migrate, pg, program, state
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

DEFAULT_DATABASE = "rk2"


@dataclass(frozen=True)
class _Source:
    """Where one connection string comes from, in the three names it has.

    The flag, the variable and the name a refusal is filed under always travel
    together, and an operator reading a refusal has to be able to act on it: a
    report that named the wrong variable would send them to edit an environment
    the command never read.
    """

    fact: str
    flag: str
    variable: str


SUPERUSER = _Source("connection_string", "--url", SUPERUSER_URL)
MIGRATION = _Source("connection_string", "--url", MIGRATE_URL)
RESTORATION = _Source("connection_string", "--url", RESTORE_URL)
RUNTIME = _Source("connection_string", "--url", DATABASE_URL)
AGENT = _Source("state_connection_string", "--state-url", STATE_URL)


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


def _doctor(arguments: argparse.Namespace) -> int:
    diagnosis = doctor.diagnose(arguments.config)
    print(json.dumps(diagnosis.as_dict(), indent=2))
    return diagnosis.exit_code


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
    return _with_settings(arguments, "db verify", migrate.verify)


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
