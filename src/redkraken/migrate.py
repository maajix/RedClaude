"""The schema corpus and the runner that applies it.

One database is authoritative, so one command has to be able to create it,
bring it forward and say what it holds. `provision` does the three things a
non-superuser cannot do for itself — roles, the database, the extension —
and `migrate` does everything else: lint the corpus, refuse a database that
disagrees with it, apply what is pending, and finish by making the end-of-run
invariants true.

Two rules make the rest of it small. A migration and the row recording it commit
together, so "applied" and "recorded" cannot come apart and there is no repair
state to design. And an invariant that belongs to the end of a run — the event
triggers, the RLS sweep, the grants — is applied by the runner rather than by
whichever migration happened to be last, so a migration written next year gets
it without knowing it exists.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from redkraken import integrity, pg
from redkraken.outcome import (
    DATABASE_UNREACHABLE,
    INVALID_CONFIGURATION,
    INVALID_CORPUS,
    SCHEMA_DRIFT,
    Ledger,
    Report,
    Violation,
    report,
)


#: The corpus ships inside the package, so `rk` applies the schema it was built
#: with rather than whatever happens to be in the working directory.
CORPUS = Path(__file__).resolve().parent / "migrations"

#: Recorded on every row this runner writes. It changes when the way a migration
#: is applied changes, not when a migration is added.
RUNNER_VERSION = "2"

#: Held for the length of each migration's transaction, so two runners started
#: at once apply in sequence instead of racing for the same file.
LOCK_KEY = 8158253941

OWNER_ROLE = "rk2_owner"
META_SCHEMA = "rk2_meta"

#: Identity is the filename minus `.sql`, and order is that identity ascending
#: in C collation — which is what Python's string comparison already is. Two
#: forms are legal: the numbered corpus, frozen at `FROZEN_NUMBER`, and a UTC
#: timestamp for everything authored after it. The timestamp form exists because
#: two authors reaching for "the next number" at the same time produce one
#: identity with two contents, and `0` sorts before `2`, so every numbered file
#: stays ahead of every timestamped one for as long as years have four digits.
NUMBERED = re.compile(r"\A(?P<number>\d{4})_[a-z0-9_]+\.sql\Z")
TIMESTAMPED = re.compile(r"\A\d{8}T\d{6}Z__[a-z0-9_]+\.sql\Z")
FROZEN_NUMBER = 42

#: Anchored, so the same words inside a comment or a plpgsql body do not trip it.
#: A `COMMIT;` inside a file commits the runner's transaction early and leaves
#: the bookkeeping row in a second one, which is the one way this design can
#: produce a migration the database does not remember.
TRANSACTION_CONTROL = re.compile(
    r"^[ \t]*(BEGIN|COMMIT|ROLLBACK|START[ \t]+TRANSACTION)[ \t]*;", re.IGNORECASE | re.MULTILINE
)

#: Roles are cluster-global and creating one needs `CREATEROLE`, which
#: `rk2_migrate` must never hold: a migration able to mint a role could grant
#: itself `rk2_human`, membership of which is the only thing authorising
#: `actor_kind = 'human'`. Role work is provisioning; see `provision`.
ROLE_DDL = re.compile(
    r"^[ \t]*(CREATE|ALTER|DROP|COMMENT[ \t]+ON)[ \t]+ROLE[ \t]", re.IGNORECASE | re.MULTILINE
)


@dataclass(frozen=True)
class Role:
    """One role in the catalogue, and why it is separate from the others."""

    name: str
    login: bool
    member_of: str | None = None
    comment: str = ""


#: The seven roles. Splitting them is the whole access-control design: the
#: connection a model's tool calls run on owns nothing, the connection that
#: applies schema logs in as itself but creates as the owner, and the one role
#: allowed to turn enforcement off never runs anything.
ROLES = (
    Role(
        "rk2_owner",
        login=False,
        comment="owns every object. NOLOGIN: reached by SET ROLE from rk2_migrate, never connected to.",
    ),
    Role(
        "rk2_migrate",
        login=True,
        member_of="rk2_owner",
        comment="RK_MIGRATE_URL. Held by `rk db migrate` and nothing else.",
    ),
    Role(
        "rk2_restore",
        login=True,
        member_of="rk2_owner",
        comment="the restore connection. The only role granted SET on session_replication_role.",
    ),
    Role(
        "rk2_runtime",
        login=True,
        comment="RK_DATABASE_URL. DML plus EXECUTE, no DDL, no ownership, no TRUNCATE, no session_replication_role.",
    ),
    Role(
        "rk2_state",
        login=True,
        comment="the agent-facing read connection. SELECT on an enumerated surface, no write privilege anywhere.",
    ),
    Role(
        "rk2_human",
        login=True,
        comment="the operator console. Not granted to rk2_runtime or rk2_state: those are the connections a model can reach through.",
    ),
    Role(
        "rk2_proxy",
        login=True,
        comment="the egress proxy. EXECUTE on the capability receipt writers, no direct receipt DML.",
    ),
)

RESTORE_ROLE = "rk2_restore"

#: Attributes re-applied on every provision, so a role that was created by hand
#: with the wrong ones is repaired rather than reported.
LOGIN_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
OWNER_ATTRIBUTES = "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"

SCHEMA_MIGRATIONS = f"""
CREATE SCHEMA IF NOT EXISTS {META_SCHEMA};
CREATE TABLE IF NOT EXISTS {META_SCHEMA}.schema_migrations (
    id             text PRIMARY KEY,
    checksum       text        NOT NULL,
    applied_seq    bigint      NOT NULL GENERATED ALWAYS AS IDENTITY,
    applied_at     timestamptz NOT NULL DEFAULT now(),
    applied_by     text        NOT NULL DEFAULT current_user,
    execution_ms   integer     NOT NULL,
    runner_version text        NOT NULL
);
"""

#: What belongs to the end of a run rather than to any migration in it. Order
#: matters once: the triggers are attached before they are upgraded to ALWAYS.
#: `apply_server_settings` is re-applied every run because `pg_dump` does not
#: carry `ALTER DATABASE ... SET`, so a restored database has the defaults back
#: while `schema_migrations` still says the settings migration is applied.
FINALIZERS = (
    "apply_server_settings",
    "attach_event_triggers",
    "enforce_always_triggers",
    "apply_state_rls",
    "apply_state_grants",
    "enforce_fk_fire_order",
)


@dataclass(frozen=True)
class Migration:
    """One file in the corpus: what it is called, and exactly what it says."""

    identity: str
    path: Path
    sql: str
    checksum: str

    @property
    def number(self) -> int | None:
        match = NUMBERED.fullmatch(self.path.name)
        return int(match.group("number")) if match else None


def load(corpus: Path = CORPUS) -> tuple[tuple[Migration, ...], tuple[Violation, ...]]:
    """The corpus in application order, or every reason it is not one.

    Reading and linting are one step because a corpus that fails a rule is not
    half-usable: the runner refuses before it opens a connection, so a bad
    filename can never leave a database half-applied.
    """
    directory = Path(corpus)
    if not directory.is_dir():
        return (), (_corpus_violation(str(directory), "the migration corpus directory is missing"),)

    violations: list[Violation] = []
    migrations: list[Migration] = []
    numbers: dict[int, list[str]] = {}

    for path in sorted(directory.glob("*.sql"), key=lambda item: item.name):
        name = path.name
        numbered = NUMBERED.fullmatch(name)
        if numbered:
            number = int(numbered.group("number"))
            numbers.setdefault(number, []).append(name)
            if number > FROZEN_NUMBER:
                violations.append(
                    _corpus_violation(
                        name,
                        f"numbers are frozen at {FROZEN_NUMBER:04d} and are not assignable; "
                        "a new migration is named YYYYMMDDTHHMMSSZ__slug.sql so that two "
                        "authors cannot claim one identity",
                    )
                )
        elif not TIMESTAMPED.fullmatch(name):
            violations.append(
                _corpus_violation(name, "matches neither NNNN_slug.sql nor YYYYMMDDTHHMMSSZ__slug.sql")
            )

        try:
            data = path.read_bytes()
        except OSError as error:
            violations.append(_corpus_violation(name, f"cannot be read: {error.strerror or error}"))
            continue
        try:
            sql = data.decode("utf-8")
        except UnicodeDecodeError:
            violations.append(_corpus_violation(name, "is not UTF-8 text"))
            continue

        if TRANSACTION_CONTROL.search(sql):
            violations.append(
                _corpus_violation(
                    name,
                    "contains transaction control; the runner already wraps every migration "
                    "in one transaction with its bookkeeping row",
                )
            )
        if ROLE_DDL.search(sql):
            violations.append(
                _corpus_violation(
                    name,
                    "contains role DDL; roles are cluster-global provisioning and rk2_migrate "
                    "holds no CREATEROLE. Add the role to `rk db provision` instead",
                )
            )

        migrations.append(
            Migration(
                identity=name[: -len(".sql")],
                path=path,
                sql=sql,
                checksum=hashlib.sha256(data).hexdigest(),
            )
        )

    # Impossible on one filesystem, but not across a merge, so it is said rather
    # than assumed: two files may claim one number without claiming one identity.
    for number, names in sorted(numbers.items()):
        if len(names) > 1:
            violations.append(
                _corpus_violation(
                    f"{number:04d}", "two files claim one migration number: " + ", ".join(names)
                )
            )

    if violations:
        return (), tuple(violations)
    return tuple(sorted(migrations, key=lambda item: item.identity)), ()


def provision(
    settings: pg.Settings,
    database: str,
    *,
    passwords: dict[str, str] | None = None,
) -> Report:
    """Create the roles, the database and the extension, as a superuser.

    Three things a database owner cannot do for itself: roles are cluster-global,
    `CREATE DATABASE` is superuser work, and `vector` is not a trusted extension
    on the image this runs against. Everything else is a migration. Rerunning is
    safe and repairs attributes, which is why the role loop alters unconditionally
    rather than only on creation.
    """
    ledger = Ledger()
    supplied = dict(passwords or {})
    created: list[str] = []

    connection = open_connection(ledger, settings)
    if connection is None:
        return report("db provision", ledger, target=settings.describe(), database=database)

    with connection:
        try:
            _assert_superuser(ledger, connection)
            if ledger.violations:
                return report("db provision", ledger, target=settings.describe(), database=database)

            for role in ROLES:
                if _provision_role(connection, role, supplied.get(role.name)):
                    created.append(role.name)
                ledger.hold(
                    f"role:{role.name}",
                    ("created" if role.name in created else "present")
                    + (", password set" if supplied.get(role.name) else ""),
                )

            # The one grant that lets enforcement be turned off, on the one role
            # that never runs anything. `GRANT ... ON PARAMETER` is what makes
            # "restore as a role allowed to turn the triggers off" a real
            # sentence rather than "become superuser".
            connection.execute(
                f"GRANT SET ON PARAMETER session_replication_role TO {pg.quote_identifier(RESTORE_ROLE)}"
            )
            others = ", ".join(
                pg.quote_identifier(role.name)
                for role in ROLES
                if role.login and role.name != RESTORE_ROLE
            )
            connection.execute(f"REVOKE SET ON PARAMETER session_replication_role FROM {others}")
            ledger.hold("replication_role_grant", f"SET on session_replication_role held by {RESTORE_ROLE} alone")

            existed = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = $1", (database,)
            ).rows
            if not existed:
                connection.execute(
                    f"CREATE DATABASE {pg.quote_identifier(database)} "
                    f"OWNER {pg.quote_identifier(OWNER_ROLE)}"
                )
            ledger.hold(f"database:{database}", "present" if existed else "created")
        except pg.DatabaseError as error:
            ledger.fail(
                "provision",
                f"the server refused provisioning: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report("db provision", ledger, target=settings.describe(), database=database)

    inside = open_connection(ledger, settings.replace(database=database))
    if inside is None:
        return report("db provision", ledger, target=settings.describe(), database=database)
    with inside:
        try:
            inside.execute("CREATE EXTENSION IF NOT EXISTS vector")
            inside.execute(f"ALTER SCHEMA public OWNER TO {pg.quote_identifier(OWNER_ROLE)}")
            version = inside.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).scalar()
            ledger.hold("extension:vector", f"pgvector {version}")
            ledger.hold("schema:public", f"owned by {OWNER_ROLE}")
        except pg.DatabaseError as error:
            ledger.fail(
                "provision",
                f"the server refused provisioning: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )

    return report(
        "db provision",
        ledger,
        target=settings.describe(),
        database=database,
        roles_created=created,
    )


def migrate(settings: pg.Settings, *, corpus: Path = CORPUS) -> Report:
    """Apply every pending migration, then make the run's invariants true.

    Rerunning is the ordinary case: with nothing pending the finalizers and the
    integrity gate still run, which is what makes a restored database repairable
    by the same command that built it.
    """
    migrations, refusals = load(corpus)
    ledger = Ledger()
    if refusals:
        ledger.refuse("corpus", f"{len(refusals)} refused migration file(s)", refusals)
        return report("db migrate", ledger, target=settings.describe(), corpus=0)
    ledger.hold("corpus", f"{len(migrations)} migration(s) in {corpus}")

    connection = open_connection(ledger, settings)
    if connection is None:
        return report("db migrate", ledger, target=settings.describe(), corpus=len(migrations))

    applied: list[dict] = []
    with connection:
        _assert_migrate_connection(ledger, connection)
        if ledger.violations:
            return report("db migrate", ledger, target=settings.describe(), corpus=len(migrations))

        try:
            _bootstrap(connection)
        except pg.DatabaseError as error:
            ledger.fail(
                "bootstrap",
                f"the version table could not be created: {error}",
                code=SCHEMA_DRIFT,
                source="database",
            )
            return report("db migrate", ledger, target=settings.describe(), corpus=len(migrations))

        recorded = _recorded(connection)
        pending = plan(ledger, migrations, recorded)
        if ledger.violations:
            return report("db migrate", ledger, target=settings.describe(), corpus=len(migrations))
        ledger.hold("plan", f"{len(pending)} pending, {len(recorded)} already applied")

        for migration in pending:
            try:
                elapsed = _apply(connection, migration)
            except pg.DatabaseError as error:
                ledger.fail(
                    f"migration:{migration.identity}",
                    f"refused by the server: {error}",
                    code=SCHEMA_DRIFT,
                    source=f"migration:{migration.identity}",
                )
                return report(
                    "db migrate",
                    ledger,
                    target=settings.describe(),
                    corpus=len(migrations),
                    applied=applied,
                )
            applied.append({"id": migration.identity, "execution_ms": elapsed})
            ledger.hold(f"migration:{migration.identity}", f"applied in {elapsed} ms")

        try:
            finalized = finalize(connection)
        except pg.DatabaseError as error:
            ledger.fail(
                "finalize",
                f"an end-of-run invariant could not be applied: {error}",
                code=SCHEMA_DRIFT,
                source="database",
            )
            return report(
                "db migrate",
                ledger,
                target=settings.describe(),
                corpus=len(migrations),
                applied=applied,
            )
        for name, answer in finalized.items():
            ledger.hold(f"finalize:{name}", str(answer))

    gate_on_a_fresh_connection(ledger, settings, migrations)
    return report(
        "db migrate",
        ledger,
        target=settings.describe(),
        corpus=len(migrations),
        applied=applied,
    )


def status(settings: pg.Settings, *, corpus: Path = CORPUS) -> Report:
    """What the database holds, against what the corpus says it should."""
    migrations, refusals = load(corpus)
    ledger = Ledger()
    if refusals:
        ledger.refuse("corpus", f"{len(refusals)} refused migration file(s)", refusals)
        return report("db status", ledger, target=settings.describe())

    connection = open_connection(ledger, settings)
    if connection is None:
        return report("db status", ledger, target=settings.describe())

    with connection:
        present = connection.execute(
            "SELECT to_regclass($1) IS NOT NULL", (f"{META_SCHEMA}.schema_migrations",)
        ).scalar()
        if not present:
            ledger.fail(
                "schema_migrations",
                "the database has no version table; run `rk db migrate`",
                code=SCHEMA_DRIFT,
                source="database",
            )
            return report("db status", ledger, target=settings.describe(), corpus=len(migrations))
        recorded = _recorded(connection)
        plan(ledger, migrations, recorded)
        pending = [item.identity for item in migrations if item.identity not in recorded]
        ledger.hold("applied", f"{len(recorded)} migration(s) recorded")
        return report(
            "db status",
            ledger,
            target=settings.describe(),
            corpus=len(migrations),
            applied=sorted(recorded),
            pending=pending,
            server_version=connection.server_version,
        )


def verify(settings: pg.Settings, *, corpus: Path = CORPUS) -> Report:
    """Run the integrity gate against a database, on its own.

    `migrate` ends by running this, so an operator only reaches for it to ask a
    database that nobody is changing whether it still holds. The corpus is read
    here rather than in the gate because the expected migration set is a fact
    about the installed package, and the database cannot see the filesystem.
    """
    migrations, refusals = load(corpus)
    ledger = Ledger()
    if refusals:
        ledger.refuse("corpus", f"{len(refusals)} refused migration file(s)", refusals)
        return report("db verify", ledger, target=settings.describe(), checks=0)

    connection = open_connection(ledger, settings)
    if connection is None:
        return report("db verify", ledger, target=settings.describe(), checks=0)
    with connection:
        gate = integrity.verify(connection, expected=[item.identity for item in migrations])
    ledger.assertions.extend(gate.assertions)
    ledger.violations.extend(gate.violations)
    return report("db verify", ledger, target=settings.describe(), **gate.facts)


def gate_on_a_fresh_connection(
    ledger: Ledger, settings: pg.Settings, migrations: tuple[Migration, ...]
) -> None:
    """Run the integrity gate the way the next connection will see the database.

    `apply_server_settings` issues `ALTER DATABASE ... SET`, which reaches
    sessions opened after it and not the one that issued it. Verifying on the
    connection that just finalized would therefore report the settings the run
    started with, so the gate gets a connection of its own.
    """
    connection = open_connection(ledger, settings)
    if connection is None:
        return
    with connection:
        gate = integrity.verify(connection, expected=[item.identity for item in migrations])
    ledger.assertions.extend(gate.assertions)
    ledger.violations.extend(gate.violations)


def finalize(connection: pg.Connection) -> dict[str, object]:
    """Run the end-of-run invariants, in one transaction, as the owner."""
    answers: dict[str, object] = {}
    with connection.transaction():
        connection.execute(f"SET LOCAL ROLE {pg.quote_identifier(OWNER_ROLE)}")
        for name in FINALIZERS:
            answers[name] = connection.execute(f"SELECT {name}()").scalar()
    return answers


def _apply(connection: pg.Connection, migration: Migration) -> int:
    """One migration and its bookkeeping row, in one transaction.

    The actor context is set by the runner rather than by every migration:
    a migration that writes to an emitting table hits `emit_event`, which
    refuses a write it cannot attribute. The migration is a runtime actor —
    there is no model in the loop — and the context is bound to this
    transaction, so it cannot outlive the work it describes.
    """
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock($1)", (LOCK_KEY,))
        # Every object a migration creates is owned by rk2_owner, whichever login
        # applied it: ALTER DEFAULT PRIVILEGES is keyed to the creating role, so
        # without this a second admin account would create tables the runtime
        # silently cannot read. LOCAL, so the role does not outlive the file.
        connection.execute(f"SET LOCAL ROLE {pg.quote_identifier(OWNER_ROLE)}")
        _declare_actor(connection, f"migrate:{migration.identity}")
        started = time.monotonic()
        connection.execute_script(migration.sql)
        elapsed = int((time.monotonic() - started) * 1000)
        connection.execute(
            f"INSERT INTO {META_SCHEMA}.schema_migrations"
            " (id, checksum, execution_ms, runner_version) VALUES ($1, $2, $3, $4)",
            (migration.identity, migration.checksum, elapsed, RUNNER_VERSION),
        )
    return elapsed


#: How the runner asks whether the corpus has reached the migration that
#: creates the one supported way to declare an actor.
SET_ACTOR = "set_actor(text,text)"


def _declare_actor(connection: pg.Connection, actor: str) -> None:
    """Declare who is writing, through `set_actor()` wherever it exists.

    ADR 0002 makes one helper the only supported way to populate the actor
    context, and the runner is not an exception to it. It cannot be the only
    way *here*, though: on an empty database the first twelve migrations run
    before 0013 creates the helper, and one of them writes to a table that
    already emits. So the bootstrap form below is used until the helper exists,
    and never afterwards — a later change to what an actor declaration means
    reaches the runner along with everything else.
    """
    if connection.execute("SELECT to_regprocedure($1) IS NOT NULL", (SET_ACTOR,)).scalar():
        connection.execute("SELECT set_actor('runtime', $1)", (actor,))
        return
    connection.execute(
        "SELECT set_config('app.actor_kind', 'runtime', true),"
        "       set_config('app.actor_id', $1, true),"
        "       set_config('app.actor_xact', pg_current_xact_id()::text, true)",
        (actor,),
    )


def _bootstrap(connection: pg.Connection) -> None:
    """Create the version table, which has to exist before the first migration.

    It does not live in `public`: put there it is the first thing the corpus's
    own program-isolation check trips over, because every corpus-wide invariant
    enumerates that schema and the runner's bookkeeping is not application state.
    """
    with connection.transaction():
        connection.execute(f"SET LOCAL ROLE {pg.quote_identifier(OWNER_ROLE)}")
        connection.execute_script(SCHEMA_MIGRATIONS)


def _recorded(connection: pg.Connection) -> dict[str, str]:
    rows = connection.execute(
        f"SELECT id, checksum FROM {META_SCHEMA}.schema_migrations ORDER BY id"
    ).rows
    return {str(identity): str(checksum) for identity, checksum in rows}


def plan(
    ledger: Ledger, migrations: tuple[Migration, ...], recorded: dict[str, str]
) -> tuple[Migration, ...]:
    """The pending migrations, and the two refusals that matter more.

    Drift is the failure of concurrent authorship: not two files with one name,
    which git shows you, but one name with two contents, merged quietly because
    the hunks did not overlap. Out-of-order arrival is a migration that sorts
    before something already applied — nothing is live yet at that point, so the
    answer is "recreate the database and run from empty", not "apply it anyway".
    """
    on_disk = {migration.identity: migration for migration in migrations}
    for identity, checksum in sorted(recorded.items()):
        migration = on_disk.get(identity)
        if migration is None:
            ledger.fail(
                f"migration:{identity}",
                "is applied but its file is gone",
                code=SCHEMA_DRIFT,
                source=f"migration:{identity}",
            )
        elif migration.checksum != checksum:
            ledger.fail(
                f"migration:{identity}",
                f"changed after it was applied: database {checksum}, file {migration.checksum}",
                code=SCHEMA_DRIFT,
                source=f"migration:{identity}",
            )

    pending = tuple(item for item in migrations if item.identity not in recorded)
    highest = max(recorded, default="")
    for migration in pending:
        if highest and migration.identity < highest:
            ledger.fail(
                f"migration:{migration.identity}",
                f"is pending but sorts before the applied {highest}; recreate the database "
                "and migrate from empty",
                code=SCHEMA_DRIFT,
                source=f"migration:{migration.identity}",
            )
    return pending


def _provision_role(connection: pg.Connection, role: Role, password: str | None) -> bool:
    """Create the role if it is absent, then repair its attributes either way."""
    existed = bool(connection.execute("SELECT 1 FROM pg_roles WHERE rolname = $1", (role.name,)).rows)
    name = pg.quote_identifier(role.name)
    if not existed:
        connection.execute(f"CREATE ROLE {name} {LOGIN_ATTRIBUTES if role.login else OWNER_ATTRIBUTES}")
    else:
        connection.execute(
            f"ALTER ROLE {name} {LOGIN_ATTRIBUTES if role.login else OWNER_ATTRIBUTES}"
        )
    if role.member_of:
        connection.execute(f"GRANT {pg.quote_identifier(role.member_of)} TO {name}")
    if password is not None:
        connection.execute(f"ALTER ROLE {name} PASSWORD {pg.quote_literal(pg.scram_verifier(password))}")
    if role.comment:
        connection.execute(f"COMMENT ON ROLE {name} IS {pg.quote_literal(role.comment)}")
    return not existed


def passwords_from_environment(environment: dict[str, str] | None = None) -> dict[str, str]:
    """Role passwords, from the environment and nowhere else.

    A password on the command line is in the process table and in shell history;
    a password in a configuration file is in git. `RK_PASSWORD_RK2_MIGRATE` names
    the role it belongs to, so provisioning a subset is an ordinary thing to do.
    """
    source = os.environ if environment is None else environment
    found = {}
    for role in ROLES:
        value = source.get(f"RK_PASSWORD_{role.name.upper()}")
        if value:
            found[role.name] = value
    return found


def open_connection(ledger: Ledger, settings: pg.Settings) -> pg.Connection | None:
    try:
        return pg.connect(settings)
    except pg.ConnectionError_ as error:
        ledger.fail(
            "connection",
            f"cannot reach {settings.describe()}: {error}",
            code=DATABASE_UNREACHABLE,
            source="database",
        )
    except pg.DatabaseError as error:
        # A refused login is the operator's connection string, not the server's
        # health: the server answered, and what it said was no.
        ledger.fail(
            "connection",
            f"{settings.describe()} refused the connection: {error}",
            code=INVALID_CONFIGURATION,
            source="database",
        )
    return None


def _assert_superuser(ledger: Ledger, connection: pg.Connection) -> None:
    user, superuser = connection.execute(
        "SELECT current_user, coalesce(rolsuper, false) FROM pg_roles WHERE rolname = current_user"
    ).rows[0]
    if not superuser:
        ledger.fail(
            "superuser_connection",
            f"connected as {user}, which is not a superuser: roles, databases and the vector "
            "extension cannot be created without one",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return
    ledger.hold("superuser_connection", f"connected as {user}")


def _assert_migrate_connection(ledger: Ledger, connection: pg.Connection) -> None:
    """Refuse the wrong connection string before anything is applied.

    A runtime URL would fail eventually with a permission error. A superuser URL
    is worse: it succeeds, and leaves every object owned by the wrong role, which
    nothing downstream notices until the runtime cannot read its own tables.
    """
    user, member, superuser = connection.execute(
        "SELECT current_user, pg_has_role(current_user, $1, 'USAGE'),"
        "       coalesce((SELECT rolsuper FROM pg_roles WHERE rolname = current_user), false)",
        (OWNER_ROLE,),
    ).rows[0]
    if superuser:
        ledger.fail(
            "migrate_connection",
            f"connected as the superuser {user}; migrations run as a member of {OWNER_ROLE} "
            "so that ownership is not an accident",
            code=INVALID_CONFIGURATION,
            source="database",
        )
    elif not member:
        ledger.fail(
            "migrate_connection",
            f"connected as {user}, which is not a member of {OWNER_ROLE}: this is not the "
            "migrate connection string",
            code=INVALID_CONFIGURATION,
            source="database",
        )
    else:
        ledger.hold("migrate_connection", f"connected as {user}, a member of {OWNER_ROLE}")


def _corpus_violation(source: str, detail: str) -> Violation:
    return Violation(code=INVALID_CORPUS, source=f"corpus:{source}", detail=detail)
