"""Dump and restore: the operations behind `rk db dump` and `rk db restore`.

The supported archive is a full `pg_dump` custom-format archive, and the reason
is a property of this schema rather than a preference. Every row-level trigger
in the corpus is `ENABLE ALWAYS`, so it fires for a replicating session too — a
data-only restore would re-emit an Event for every row it copied and the Event
log would then describe a restore that no actor performed. A full archive
creates the triggers after the data, so nothing re-emits and no enforcement has
to be turned off to make the restore work.

Two things the archive does not carry, both repaired by the same finalizers a
migration run ends with: `ALTER DATABASE ... SET`, so a restored database has
the shipped settings back at their defaults, and the order foreign keys fire in,
which a restore recreates in dump order rather than in purge order.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
from pathlib import Path

from redkraken import child, migrate, pg
from redkraken.outcome import (
    BACKUP_FAILED,
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    Ledger,
    Report,
    report,
)


DUMP = "pg_dump"
RESTORE = "pg_restore"

#: Extensions `rk db provision` installs and the archive therefore leaves out.
#: `vector` is not a trusted extension, so both `CREATE EXTENSION` and the
#: `COMMENT ON EXTENSION` pg_dump emits alongside it are superuser work — and
#: the restore connection is deliberately not a superuser. Excluding it makes
#: the archive what it should be: application state, restored into a database
#: that provisioning has already prepared, exactly as the roles are.
PROVISIONED_EXTENSIONS = ("vector",)

#: A local dump of this size is minutes, not hours; a run that has stopped
#: answering is a failure to report rather than a command to wait on forever.
DEFAULT_TIMEOUT = 3600.0

#: How much of a failed tool's own words to carry into the violation. Enough to
#: name the object it stopped on, bounded so a refusal stays readable.
STDERR_LIMIT = 2000


def dump(settings: pg.Settings, destination: Path, *, timeout: float = DEFAULT_TIMEOUT) -> Report:
    """Write a full custom-format archive of one database.

    The archive is hashed as it is written, so the thing an operator restores
    later can be shown to be the thing this command produced.
    """
    ledger = Ledger()
    target = Path(destination)
    binary = _binary(ledger, DUMP)
    if binary is None:
        return report("db dump", ledger, target=settings.describe(), archive=str(target))
    ledger.hold(f"dependency:{DUMP}", _version(binary))

    if target.exists():
        ledger.fail(
            "archive",
            f"{target} already exists; an archive is never overwritten",
            code=INVALID_CONFIGURATION,
            source="archive",
        )
        return report("db dump", ledger, target=settings.describe(), archive=str(target))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        ledger.fail(
            "archive",
            f"cannot create {target.parent}: {error.strerror or error}",
            code=INVALID_CONFIGURATION,
            source="archive",
        )
        return report("db dump", ledger, target=settings.describe(), archive=str(target))

    completed = child.run(
        binary,
        [
            "--format=custom",
            "--compress=6",
            "--no-password",
            *[f"--exclude-extension={name}" for name in PROVISIONED_EXTENSIONS],
            f"--file={target}",
            *_connection_arguments(settings),
        ],
        environment=_environment(settings),
        timeout=timeout,
    )
    if isinstance(completed, str):
        _discard(ledger, target)
        ledger.fail("dump", completed, code=BACKUP_FAILED, source="pg_dump")
        return report("db dump", ledger, target=settings.describe(), archive=str(target))
    if completed.returncode != 0:
        _discard(ledger, target)
        ledger.fail(
            "dump",
            f"{DUMP} exited {completed.returncode}: {child.tail(completed.stderr, limit=STDERR_LIMIT)}",
            code=BACKUP_FAILED,
            source="pg_dump",
        )
        return report("db dump", ledger, target=settings.describe(), archive=str(target))

    digest, size = _digest(target)
    ledger.hold("dump", f"{size} byte archive written to {target}")
    return report(
        "db dump",
        ledger,
        target=settings.describe(),
        archive=str(target),
        bytes=size,
        sha256=digest,
    )


def restore(
    settings: pg.Settings,
    archive: Path,
    *,
    corpus: Path = migrate.CORPUS,
    timeout: float = DEFAULT_TIMEOUT,
) -> Report:
    """Restore an archive into an existing empty database, then make it usable.

    Restoring is four steps, and the last three are why this is a command rather
    than an invocation an operator remembers: the target is checked for being
    empty, `pg_restore` brings the objects back, the finalizers repair what the
    archive could not carry, and the integrity gate says whether the result is
    the database the corpus describes.

    That last gate is the one place that knows a restore happened, so it is the
    one place that may spend the tolerance a restore is entitled to: a rewritten
    tuple carries the restore's transaction id rather than the one its event
    recorded. `rk db verify` afterwards stays strict and will keep reporting it,
    which is the honest answer -- the evidence really is gone.
    """
    ledger = Ledger()
    source = Path(archive)
    binary = _binary(ledger, RESTORE)
    if binary is None:
        return report("db restore", ledger, target=settings.describe(), archive=str(source))
    ledger.hold(f"dependency:{RESTORE}", _version(binary))

    if not source.is_file():
        ledger.fail(
            "archive",
            f"{source} is not a readable archive",
            code=INVALID_CONFIGURATION,
            source="archive",
        )
        return report("db restore", ledger, target=settings.describe(), archive=str(source))
    digest, size = _digest(source)
    ledger.hold("archive", f"{size} bytes, sha256 {digest}")

    if not _assert_empty(ledger, settings):
        return report("db restore", ledger, target=settings.describe(), archive=str(source))

    completed = child.run(
        binary,
        [
            # One transaction: either the whole archive is there or the database
            # is untouched. It also implies --exit-on-error, so a restore does
            # not run to the end past the first object it could not create.
            "--single-transaction",
            "--no-password",
            *_connection_arguments(settings),
            str(source),
        ],
        environment=_environment(settings),
        timeout=timeout,
    )
    if isinstance(completed, str):
        ledger.fail("restore", completed, code=BACKUP_FAILED, source="pg_restore")
        return report("db restore", ledger, target=settings.describe(), archive=str(source))
    if completed.returncode != 0:
        ledger.fail(
            "restore",
            f"{RESTORE} exited {completed.returncode}: {child.tail(completed.stderr, limit=STDERR_LIMIT)}",
            code=BACKUP_FAILED,
            source="pg_restore",
        )
        return report("db restore", ledger, target=settings.describe(), archive=str(source))
    ledger.hold("restore", f"{source} restored into {settings.database}")

    migrations, refusals = migrate.load(corpus)
    if refusals:
        ledger.refuse("corpus", f"{len(refusals)} refused migration file(s)", refusals)
        return report("db restore", ledger, target=settings.describe(), archive=str(source))

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        return report("db restore", ledger, target=settings.describe(), archive=str(source))
    facts: dict[str, object] = {}
    with connection:
        # The same lock a migration run holds. The finalizers drop and recreate
        # every event trigger and rebuild the foreign keys, so two of them at
        # once collide on the same tables whichever command started them.
        with migrate.exclusive(connection):
            try:
                finalized = migrate.finalize(connection)
            except pg.DatabaseError as error:
                ledger.fail(
                    "finalize",
                    f"the restored database could not be finalized: {error}",
                    code=BACKUP_FAILED,
                    source="database",
                )
                return report("db restore", ledger, target=settings.describe(), archive=str(source))
            for name, answer in finalized.items():
                ledger.hold(f"finalize:{name}", str(answer))

            facts = migrate.gate_on_a_fresh_connection(ledger, settings, migrations)

    return report(
        "db restore",
        ledger,
        target=settings.describe(),
        archive=str(source),
        bytes=size,
        sha256=digest,
        **facts,
    )


#: What a database `rk db provision` just created holds: whatever the extension
#: brought with it, and nothing else. Relations that an extension owns carry a
#: pg_depend row of type `e`, which is how they are told apart from the ones an
#: archive is about to create.
OCCUPANTS = """
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
   AND n.nspname NOT IN ('pg_catalog', 'information_schema')
   AND n.nspname NOT LIKE 'pg_toast%'
   AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
"""


def _assert_empty(ledger: Ledger, settings: pg.Settings) -> bool:
    """Whether the target is a provisioned database with nothing in it yet.

    Asked before `pg_restore` runs rather than discovered from its stderr: an
    archive restored over a database that already holds rows is the one mistake
    in this command that is expensive to undo, and `--single-transaction` means
    the operator would otherwise learn about it from whichever object happened
    to collide first.
    """
    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        return False
    with connection:
        occupants = int(connection.execute(OCCUPANTS).scalar())
    if occupants:
        ledger.fail(
            "target",
            f"{settings.database} already holds {occupants} relation(s); restore into a "
            "database that `rk db provision` has just created",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return False
    ledger.hold("target", f"{settings.database} is provisioned and empty")
    return True


def _discard(ledger: Ledger, target: Path) -> None:
    """Take back the file a failed dump left behind.

    `pg_dump` creates its output before it connects, so a run that fails for any
    reason still leaves something at the destination. Nothing above will
    overwrite an archive, so leaving the remains in place would refuse every
    later dump to that path with "already exists" -- naming the wrong problem
    forever after one transient failure.

    A removal that itself fails is recorded as a failure. `hold` writes an
    assertion that held, and "could not be removed" is not one -- an operator
    reading a green line whose own text says the file is still there is being
    told the opposite of what happened, and the file is exactly what will refuse
    their next dump.
    """
    try:
        target.unlink(missing_ok=True)
    except OSError as error:
        ledger.fail(
            "archive",
            f"{target} could not be removed: {error.strerror or error}",
            code=BACKUP_FAILED,
            source="argument:--to",
        )


def _binary(ledger: Ledger, name: str) -> str | None:
    found = shutil.which(name)
    if found is None:
        ledger.fail(
            f"dependency:{name}",
            f"{name} is not on PATH; it ships with the PostgreSQL client package",
            code=MISSING_DEPENDENCY,
            source=f"runtime:program:{name}",
        )
    return found


def _version(binary: str) -> str:
    try:
        completed = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"{binary} (version unreadable: {error})"
    return completed.stdout.strip() or completed.stderr.strip() or binary


def _connection_arguments(settings: pg.Settings) -> list[str]:
    """Where to connect, as flags. The credential never appears here.

    An argument vector is world-readable in `/proc` for as long as the process
    lives, so the password travels in the environment of the child instead —
    which is the channel `libpq` reads it from anyway.
    """
    return [
        f"--host={settings.host}",
        f"--port={settings.port}",
        f"--username={settings.user}",
        f"--dbname={settings.database}",
    ]


def _environment(settings: pg.Settings) -> dict[str, str]:
    environment = dict(os.environ)
    if settings.password:
        environment["PGPASSWORD"] = settings.password
    else:
        environment.pop("PGPASSWORD", None)
    environment["PGSSLMODE"] = settings.sslmode
    # Rounded up, never down: libpq reads `PGCONNECT_TIMEOUT=0` as "wait forever",
    # so truncating a sub-second budget would invert it into no budget at all.
    environment["PGCONNECT_TIMEOUT"] = str(math.ceil(settings.connect_timeout))
    environment["PGAPPNAME"] = settings.application_name
    return environment


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as archive:
        while chunk := archive.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size
