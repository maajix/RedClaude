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
from pathlib import Path

from redkraken import __version__, backup, doctor, migrate, pg
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

DEFAULT_DATABASE = "rk2"


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

    database = commands.add_parser("db", help="create, migrate, verify and move the database")
    operations = database.add_subparsers(dest="operation", required=True, metavar="operation")

    provision = operations.add_parser(
        "provision",
        help=f"create the roles, the database and the extension (superuser; ${SUPERUSER_URL})",
    )
    _add_url(provision, SUPERUSER_URL)
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
    _add_url(migrate_, MIGRATE_URL)
    migrate_.set_defaults(run=_migrate)

    verify = operations.add_parser(
        "verify", help=f"run every registered integrity check (${MIGRATE_URL})"
    )
    _add_url(verify, MIGRATE_URL)
    verify.set_defaults(run=_verify)

    status = operations.add_parser(
        "status", help=f"report what is applied and what is pending (${MIGRATE_URL})"
    )
    _add_url(status, MIGRATE_URL)
    status.set_defaults(run=_status)

    dump = operations.add_parser("dump", help=f"write a full archive (${MIGRATE_URL})")
    _add_url(dump, MIGRATE_URL)
    dump.add_argument("--to", type=Path, required=True, metavar="path", help="where to write it")
    dump.set_defaults(run=_dump)

    restore = operations.add_parser(
        "restore", help=f"restore an archive into an empty database (${RESTORE_URL})"
    )
    _add_url(restore, RESTORE_URL)
    restore.add_argument("--from", dest="archive", type=Path, required=True, metavar="path")
    restore.set_defaults(run=_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return arguments.run(arguments)


def _add_url(parser: argparse.ArgumentParser, variable: str) -> None:
    parser.add_argument(
        "--url",
        metavar="postgresql://...",
        help=f"the connection string (default: ${variable})",
    )
    parser.set_defaults(url_variable=variable)


def _doctor(arguments: argparse.Namespace) -> int:
    diagnosis = doctor.diagnose(arguments.config)
    print(json.dumps(diagnosis.as_dict(), indent=2))
    return diagnosis.exit_code


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

    The same promise covers a database that stops answering part-way. Each
    operation classifies the failures it goes looking for; this is the boundary
    for the ones nobody can enumerate — a backend restart, a pooler dropping an
    idle socket — which arrive at whichever statement happened to be next.
    """
    settings, resolution = _settings(arguments, command)
    if settings is None:
        result = resolution
    else:
        try:
            result = operation(settings)
        except pg.ConnectionError_ as error:
            result = _refusal(command, "connection", str(error), DATABASE_UNREACHABLE)
        except pg.DatabaseError as error:
            result = _refusal(command, "database", str(error), INVALID_CONFIGURATION)
    print(json.dumps(result.as_dict(), indent=2))
    return result.exit_code


def _refusal(command: str, name: str, detail: str, code: str) -> Report:
    ledger = Ledger()
    ledger.fail(name, f"the command stopped part-way: {detail}", code=code, source="database")
    return report(command, ledger)


def _settings(arguments: argparse.Namespace, command: str) -> tuple[pg.Settings | None, Report]:
    variable = arguments.url_variable
    url = arguments.url or os.environ.get(variable)
    ledger = Ledger()
    if not url:
        ledger.fail(
            "connection_string",
            f"no connection string: pass --url or set {variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{variable}",
        )
        return None, report(command, ledger)
    try:
        settings = pg.settings_from_url(url, application_name=f"rk {command}")
    except ValueError as error:
        # The parser's own words, which name the unsupported parameter but never
        # echo the string: a connection string carries a password.
        ledger.fail(
            "connection_string",
            f"the connection string cannot be used: {error}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{variable}" if not arguments.url else "argument:--url",
        )
        return None, report(command, ledger)
    return settings, report(command, ledger)
