"""What only a real server can answer.

Everything here needs PostgreSQL 18 with pgvector, so the module skips itself
unless `RK_TEST_SUPERUSER_URL` names one. The server it names is treated as
disposable: this module drops and recreates its two databases and re-provisions
the seven roles with passwords it generates for the run. Point it at a
container, never at anything you would miss.

The four questions asked here are the four a schema can only be wrong about in
production: that the corpus applies to an empty database and stays applied on a
rerun, that a write cannot happen without saying who caused it, that every
registered check runs through one gate, and that each of those checks actually
fails when the thing it describes is broken. The last one is why the negative
controls exist: a check nobody has seen fail is a check nobody knows is wired
up, and a gate of those is a green light with nothing behind it.

`ProgramRunTest` asks a fifth, about an operation rather than about the schema:
that `rk run` opens one Program and afterwards resumes that one. `StateReadTest`
asks a sixth, about the connection the model reads through: that one Program
cannot name, infer or mutate another's rows. `ArtifactStoreTest` asks a seventh,
about the half of the state that is not in the database: that bytes shared by
content hash stay one row and two claims, and that a hash on its own opens
nothing. `SealedWireArtifactTest` asks an eighth, about the half of an exchange
nobody may read: that the wire view is kept whole, kept encrypted under key
material the database never holds, and reachable only through an authorized
operation that is audited whatever becomes of it. All four commit, because what
survives the transaction is their subject.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import secrets
import shutil
import socket
import ssl
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from redkraken import (
    artifact,
    backup,
    config,
    integrity,
    migrate,
    pg,
    program,
    proxy,
    scope,
    seal,
    state,
    tls,
)
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INTEGRITY_FAILED,
    EXIT_INVALID_CONFIGURATION,
    EXIT_OK,
    Report,
)
from redkraken.store import Store
from tests.fixtures import (
    SCOPE_ENTITIES,
    SCOPE_REQUESTS,
    SCOPED,
    VALID,
    Target,
    counterparty,
    scratch,
    tls_counterparty,
    write,
)


SUPERUSER_URL = os.environ.get("RK_TEST_SUPERUSER_URL", "")
DATABASE = os.environ.get("RK_TEST_DATABASE", "rk2_selftest")
RESTORED = f"{DATABASE}_restored"

REASON = "set RK_TEST_SUPERUSER_URL to a disposable PostgreSQL 18 superuser connection string"

#: The Lane check, verbatim, as the server renders it. Pinned rather than
#: derived: the corpus pins the same text in `check_causal_attribution`, and a
#: test that recomputed it from the same source would agree with any answer.
LANE_CHECK = "CHECK ((lane = ANY (ARRAY['agent'::text, 'replay'::text, 'proxy_internal'::text])))"

#: A minimal, self-contained row chain. Every test that needs one writes it
#: inside a transaction it rolls back, so the database the gate and the archive
#: tests see stays empty.
PROGRAM = "INSERT INTO programs (slug, name) VALUES ($1, 'Self test') RETURNING id"
ENTITY = (
    "INSERT INTO entities (program_id, type, label, dedup_key)"
    " VALUES ($1, 'technology', 'selftest-tech', 'tech:selftest') RETURNING id"
)
HYPOTHESIS = (
    "INSERT INTO hypotheses (program_id, subject_entity_id, property_class, statement)"
    " VALUES ($1, $2, (SELECT id FROM property_classes ORDER BY id LIMIT 1), 'a self test')"
    " RETURNING id"
)


@dataclass
class Harness:
    """One migrated database, and the connections that reach it as each role."""

    #: Where the databases are created and dropped from. The URL is expected to
    #: name a maintenance database, because neither `CREATE DATABASE` nor
    #: `DROP DATABASE` can be issued from the database it names.
    admin: pg.Settings
    superuser: pg.Settings
    migrate: pg.Settings
    restore: pg.Settings
    #: What `RK_DATABASE_URL` names in production: no DDL, no ownership, and
    #: row level security in force. `rk run` is tested through this one because
    #: running it as the owner would prove nothing about the connection an
    #: operator actually points at the database.
    runtime: pg.Settings
    #: What `RK_STATE_URL` names: the connection the model's reads run on. It
    #: owns nothing, writes nothing and cannot resolve a Program, so everything
    #: it returns is what row level security left it.
    state: pg.Settings
    #: What `rk proxy serve` holds: EXECUTE on two writers and no DML of its own.
    #: The fence is tested through this one because a proxy tested as the owner
    #: would prove nothing about the role a compromised proxy would be holding.
    proxy: pg.Settings
    passwords: dict[str, str]
    migrations: tuple[migrate.Migration, ...]
    created: object = None
    reapplied: object = None

    @property
    def expected(self) -> list[str]:
        return [item.identity for item in self.migrations]


HARNESS: Harness | None = None


def setUpModule() -> None:
    global HARNESS
    if SUPERUSER_URL:
        HARNESS = _build()


def tearDownModule() -> None:
    if HARNESS is not None:
        for name in (DATABASE, RESTORED):
            _drop(HARNESS.admin, name)


def harness() -> Harness:
    if HARNESS is None:
        raise unittest.SkipTest(REASON)
    return HARNESS


def _build() -> Harness:
    admin = pg.settings_from_url(SUPERUSER_URL, application_name="rk test")
    passwords = {role.name: secrets.token_urlsafe(18) for role in migrate.ROLES if role.login}

    _drop(admin, DATABASE)
    _drop(admin, RESTORED)
    provisioned = migrate.provision(admin, DATABASE, passwords=passwords)
    if not provisioned.ok:
        raise unittest.SkipTest(f"cannot provision {DATABASE}: {provisioned.violations}")

    migrations, refusals = migrate.load()
    assert not refusals, refusals
    built = Harness(
        admin=admin,
        superuser=admin.replace(database=DATABASE),
        migrate=admin.replace(
            database=DATABASE, user="rk2_migrate", password=passwords["rk2_migrate"]
        ),
        restore=admin.replace(
            database=DATABASE, user="rk2_restore", password=passwords["rk2_restore"]
        ),
        runtime=admin.replace(
            database=DATABASE, user="rk2_runtime", password=passwords["rk2_runtime"]
        ),
        state=admin.replace(
            database=DATABASE, user="rk2_state", password=passwords["rk2_state"]
        ),
        proxy=admin.replace(
            database=DATABASE, user="rk2_proxy", password=passwords["rk2_proxy"]
        ),
        passwords=passwords,
        migrations=migrations,
    )
    # Both runs happen once, here, because they are the expensive part and
    # because "safe to rerun" is a claim about the second run seeing the first
    # one's database, not about two independent runs.
    built.created = migrate.migrate(built.migrate)
    built.reapplied = migrate.migrate(built.migrate)
    return built


def _drop(settings: pg.Settings, name: str) -> None:
    with pg.connect(settings) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {pg.quote_identifier(name)} WITH (FORCE)")


class Rollback(Exception):
    """Raised to undo a transaction that was only opened to break something."""


class DatabaseCase(unittest.TestCase):
    """A case with the migrated database under it and a connection to it."""

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        cls.harness = harness()
        cls.connection = pg.connect(getattr(cls.harness, cls.settings_for))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()


class CleanCreationTest(DatabaseCase):
    """Criterion 1: the corpus applies to an empty database, and reruns."""

    def test_the_whole_corpus_is_applied_to_an_empty_database(self):
        created = self.harness.created

        self.assertEqual([], list(created.violations))
        self.assertEqual(EXIT_OK, created.exit_code)
        self.assertEqual(
            [item.identity for item in self.harness.migrations],
            [item["id"] for item in created.facts["applied"]],
        )

    def test_running_it_again_applies_nothing_and_still_holds(self):
        again = self.harness.reapplied

        self.assertEqual([], list(again.violations))
        self.assertEqual([], again.facts["applied"])

    def test_the_database_agrees_with_the_corpus_it_was_built_from(self):
        state = migrate.status(self.harness.migrate)

        self.assertTrue(state.ok, state.violations)
        self.assertEqual(sorted(self.harness.expected), state.facts["applied"])
        self.assertEqual([], state.facts["pending"])
        self.assertTrue(state.facts["server_version"].startswith("18."))

    def test_every_migration_is_recorded_with_the_bytes_that_were_applied(self):
        recorded = dict(
            self.connection.execute(
                "SELECT id, checksum FROM rk2_meta.schema_migrations"
            ).rows
        )

        self.assertEqual(
            {item.identity: item.checksum for item in self.harness.migrations}, recorded
        )

    def test_the_shipped_settings_reach_the_connection_the_gate_runs_on(self):
        # `apply_server_settings` is `ALTER DATABASE ... SET`, which only reaches
        # sessions opened after it. Verifying on the connection that applied it
        # reports the settings the run started with, so the gate opens its own.
        settings = {
            check.name: check.ok
            for check in integrity.run(self.connection, self.harness.expected)
            if check.family == "baseline"
        }

        self.assertTrue(settings["maintenance_work_mem"])
        self.assertTrue(settings["hnsw_iterative_scan"])
        self.assertTrue(settings["hnsw_max_scan_tuples"])

    def test_the_migrate_report_says_how_much_of_the_gate_ran(self):
        # "The gate passed" is worth nothing without the number of checks behind
        # it: a gate that ran none of them passes too.
        created = self.harness.created

        self.assertEqual([], created.facts["failed"])
        self.assertEqual(["baseline", "roles", "standing"], created.facts["families"])
        self.assertEqual(len(integrity.run(self.connection, self.harness.expected)),
                         created.facts["checks"])


class ExclusiveRunTest(DatabaseCase):
    """One runner at a time, from reading the plan to finishing the finalizers.

    Two runners that read an empty `schema_migrations` in the same moment both
    plan every file, so the span that has to be exclusive starts before the plan
    and not at the first `CREATE TABLE`.
    """

    def held(self, connection: pg.Connection) -> bool:
        # `pg_advisory_lock` splits a bigint key across classid and objid.
        return not connection.execute(
            "SELECT pg_try_advisory_lock($1)", (migrate.LOCK_KEY,)
        ).scalar()

    def test_no_second_runner_can_start_while_one_holds_the_corpus(self):
        with migrate.exclusive(self.connection):
            with pg.connect(self.harness.migrate) as other:
                self.assertTrue(self.held(other))

    def test_the_lock_is_given_back_when_the_run_ends(self):
        with migrate.exclusive(self.connection):
            pass

        with pg.connect(self.harness.migrate) as other:
            self.assertFalse(self.held(other))

    def test_a_finished_migration_leaves_no_lock_behind(self):
        # The two runs in `setUpModule` are finished, and their connections are
        # closed; a lock still held here would be one the runner never released.
        outstanding = self.connection.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"
            "   AND ((classid::bigint << 32) | objid::bigint) = $1",
            (migrate.LOCK_KEY,),
        ).scalar()

        self.assertEqual(0, outstanding)


class ConnectionGuardTest(DatabaseCase):
    """Which connection string each database command will not run on.

    A superuser URL is the dangerous one: it succeeds, and leaves every object
    owned by the wrong role, which nothing downstream notices until the runtime
    cannot read its own tables.
    """

    def wrong(self, settings: pg.Settings) -> list[tuple[str, str]]:
        observed = []
        for name, operation in (("status", migrate.status), ("verify", migrate.verify)):
            result = operation(settings)
            self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code, result.facts)
            observed.append((name, result.violations[0].detail))
        return observed

    def test_a_runtime_connection_is_refused_rather_than_run_until_it_breaks(self):
        runtime = self.harness.admin.replace(
            database=DATABASE, user="rk2_runtime", password=self.harness.passwords["rk2_runtime"]
        )

        for name, detail in self.wrong(runtime):
            with self.subTest(name):
                self.assertIn("not a member of rk2_owner", detail)

    def test_a_superuser_connection_is_refused_rather_than_silently_accepted(self):
        for name, detail in self.wrong(self.harness.superuser):
            with self.subTest(name):
                self.assertIn("connected as the superuser", detail)


class LaneVocabularyTest(DatabaseCase):
    """Criterion 2: one Lane vocabulary, and metadata that is not a Lane."""

    def definition(self, name: str) -> str:
        return self.connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = $1", (name,)
        ).scalar()

    def test_lane_is_the_three_causing_parties(self):
        self.assertEqual(LANE_CHECK, self.definition("receipts_lane_check"))

    def test_control_and_transport_are_a_purpose_rather_than_a_lane(self):
        # RK-REG-007: the prototype spent two Lane values on a question Lane does
        # not answer, and a Finding could then rest on a receipt no subagent made.
        purpose = self.definition("receipts_purpose_check")

        self.assertIn("control_plane", purpose)
        self.assertIn("transport_measurement", purpose)
        self.assertNotIn("control_plane", self.definition("receipts_lane_check"))

    def test_no_receipt_can_carry_a_lane_outside_the_three(self):
        for lane in ("control", "transport", "internal"):
            with self.subTest(lane):
                with self.assertRaises(pg.DatabaseError) as refusal:
                    self.write(lane)
                self.assertEqual("23514", refusal.exception.sqlstate)

    def write(self, lane: str) -> None:
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program = self.connection.execute(PROGRAM, ("lane-selftest",)).scalar()
                self.connection.execute(
                    "INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)"
                    " VALUES ($1, 1, '{}'::jsonb, repeat('b', 64))",
                    (program,),
                )
                self.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason, ts_arrival,"
                    " scope_class, scope_version, host)"
                    " VALUES ($1, $2, 'blocked', 'self test', now(), 'target', 1, 'example.test')",
                    (program, lane),
                )
                raise Rollback
        except Rollback:
            pass


class WriteDisciplineTest(DatabaseCase):
    """Criterion 3: who wrote the row, and what the row is not allowed to say."""

    def test_a_row_write_authors_its_own_event(self):
        # ADR 0002: the event is written by the table's trigger, in the writing
        # transaction, so a write path that forgets to log cannot exist.
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program = self.connection.execute(PROGRAM, ("event-selftest",)).scalar()
                entity = self.connection.execute(ENTITY, (program,)).scalar()
                events = self.connection.execute(
                    "SELECT type, subject_table, subject_id::text, actor_kind,"
                    "       xact_id = pg_current_xact_id() FROM events"
                ).rows

                self.assertEqual(
                    [("entity.created", "entities", str(entity), "runtime", True)], list(events)
                )
                raise Rollback
        except Rollback:
            pass

    def test_a_write_without_actor_context_is_refused(self):
        with self.assertRaises(pg.DatabaseError) as refusal:
            self.write(actor=None)

        self.assertIn("app.actor_kind is unset", refusal.exception.primary)

    def test_an_actor_declared_in_an_earlier_transaction_does_not_carry(self):
        # RK-REG-004: the prototype's declaration was session-wide, so one
        # statement at connect time attributed every later transaction on a
        # pooled connection. It has to stop the next write, not decay quietly.
        connection = pg.connect(self.harness.migrate)
        with connection:
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('app.actor_kind', 'runtime', false),"
                    "       set_config('app.actor_id', 'stale', false),"
                    "       set_config('app.actor_xact', pg_current_xact_id()::text, false)"
                )

            with self.assertRaises(pg.DatabaseError) as refusal:
                with connection.transaction():
                    connection.execute("SET LOCAL ROLE rk2_owner")
                    program = connection.execute(PROGRAM, ("stale-selftest",)).scalar()
                    connection.execute(ENTITY, (program,))

        self.assertIn("actor context belongs to transaction", refusal.exception.primary)

    def test_the_status_cache_cannot_be_written_directly(self):
        # `status` is maintained by the transition table, which is what makes an
        # illegal transition unwritable rather than merely undocumented.
        with self.assertRaises(pg.DatabaseError) as refusal:
            self.write(status="refuted")

        self.assertIn("maintained by hypothesis_transitions", refusal.exception.primary)

    def write(self, *, actor: str | None = "runtime", status: str | None = None) -> None:
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                if actor is not None:
                    self.connection.execute("SELECT set_actor($1, 'selftest')", (actor,))
                program = self.connection.execute(PROGRAM, ("write-selftest",)).scalar()
                entity = self.connection.execute(ENTITY, (program,)).scalar()
                if status is not None:
                    hypothesis = self.connection.execute(HYPOTHESIS, (program, entity)).scalar()
                    self.connection.execute(
                        "UPDATE hypotheses SET status = $1 WHERE id = $2", (status, hypothesis)
                    )
                raise Rollback
        except Rollback:
            pass


class GateTest(DatabaseCase):
    """Criterion 4: every registered check, through one command."""

    def test_one_command_runs_every_registered_check(self):
        result = migrate.verify(self.harness.migrate)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual([], result.facts["failed"])
        self.assertEqual(["baseline", "roles", "standing"], result.facts["families"])
        self.assertEqual(
            len(integrity.run(self.connection, self.harness.expected)), result.facts["checks"]
        )

    def test_the_gate_runs_the_registry_the_database_holds(self):
        # Not a number in a test: whatever `standing_checks` says, the gate runs.
        registered = {
            row[0]
            for row in self.connection.execute("SELECT name FROM standing_checks").rows
        }
        ran = {
            check.name
            for check in integrity.run(self.connection, self.harness.expected)
            if check.family == "standing"
        }

        self.assertEqual(registered, ran)

    def test_every_area_the_ticket_names_is_answered_by_a_check(self):
        ran = {check.source for check in integrity.run(self.connection, self.harness.expected)}

        for area, names in {
            "schema": ("baseline:schema_migrations_present", "baseline:migrations_in_declared_order"),
            "event": ("standing:event_log_integrity", "standing:event_coverage"),
            "provenance": ("standing:hook_provenance", "standing:causal_attribution"),
            "receipt": ("standing:receipt_integrity", "standing:capability_receipt_fence"),
            "scope": ("standing:program_isolation", "standing:state_access"),
            "scheduler": ("standing:scheduler_closure", "standing:lane_quota_closure"),
            "catalogue": ("roles:roles_present", "standing:role_catalogue"),
        }.items():
            with self.subTest(area):
                self.assertEqual(set(), set(names) - ran)

    def test_a_database_with_no_schema_in_it_is_drift_rather_than_a_pass(self):
        with pg.connect(self.harness.admin) as connection:
            result = integrity.verify(connection)

        self.assertFalse(result.ok)
        self.assertIn("run `rk db migrate`", result.violations[0].detail)


@dataclass(frozen=True)
class Control:
    """One way to break one check, and the check it has to break."""

    check: str
    sql: str
    #: Which connection can do it. `owner` is the migrate connection with
    #: `SET ROLE rk2_owner`; `superuser` is the only one that can change a role,
    #: which is exactly why a migration cannot.
    on: str = "owner"


def repeat(character: str) -> str:
    """One artifact identifier, written the way the controls above write them."""
    return f"repeat('{character}', 64)"


#: One sealed pair, assembled by hand, with three holes to break it through.
#: `sealed` is the artifact the seal describes, `reference` is whether the
#: Program holds the agent-visible half by name, and `extra` is anything else the
#: control needs. Written once because a seal has four foreign keys behind it --
#: the two artifacts, the algorithm and the key generation -- and repeating that
#: per control would bury which one line is the falsification.
SEAL_CONTROL = (
    "DO $ctl$ DECLARE p uuid;"
    " BEGIN"
    "   PERFORM set_actor('runtime', 'selftest');"
    "   INSERT INTO programs (slug, name) VALUES ('sealed-selftest', 'Self test')"
    "     RETURNING id INTO p;"
    "   INSERT INTO secret_kek (gen, salt, root_check)"
    "        VALUES (1, decode(repeat('61', 32), 'hex'), decode(repeat('62', 16), 'hex'));"
    "   INSERT INTO artifacts (sha256, byte_size, visibility, encrypted)"
    "        VALUES {sealed};"
    "   INSERT INTO artifacts (sha256, byte_size, visibility)"
    "        VALUES (repeat('f', 64), 9, 'agent_visible');"
    "   {reference}"
    "   INSERT INTO artifact_seal (sha256, scope_kind, scope_id, visibility, byte_size,"
    "                              alg, nonce, kek_gen, ciphertext_sha256, agent_sha256)"
    "        VALUES (repeat('e', 64), 'program', p, 'credential_bearing', 9,"
    "                'rk-hkdf-sha256-ctr-hmac-v1', decode(repeat('00', 32), 'hex'), 1,"
    "                repeat('1', 64), repeat('f', 64));"
    "   {extra}"
    " END $ctl$"
)


#: Every check the gate runs, and the edit that makes it fail. Each runs in a
#: transaction that is rolled back, so the database is unchanged afterwards --
#: `test_the_database_is_unchanged_afterwards` is what says so.
CONTROLS = (
    # --- the migration ledger ------------------------------------------------
    Control(
        "baseline:no_unknown_migrations",
        "INSERT INTO rk2_meta.schema_migrations (id, checksum, execution_ms, runner_version)"
        " VALUES ('9999_ghost', 'x', 0, '2')",
    ),
    Control(
        "baseline:no_pending_migrations",
        "DELETE FROM rk2_meta.schema_migrations"
        " WHERE id = (SELECT max(id) FROM rk2_meta.schema_migrations)",
    ),
    Control(
        "baseline:migrations_in_declared_order",
        "INSERT INTO rk2_meta.schema_migrations (id, checksum, execution_ms, runner_version)"
        " VALUES ('0000_ghost', 'x', 0, '2')",
    ),
    Control("baseline:schema_migrations_present", "DROP TABLE rk2_meta.schema_migrations"),
    # --- the settings the schema depends on ----------------------------------
    Control("baseline:maintenance_work_mem", "SET LOCAL maintenance_work_mem = '16MB'"),
    Control("baseline:hnsw_iterative_scan", "SET LOCAL hnsw.iterative_scan = 'off'"),
    Control("baseline:hnsw_max_scan_tuples", "SET LOCAL hnsw.max_scan_tuples = 5000"),
    Control(
        "baseline:default_transaction_isolation",
        "SET LOCAL default_transaction_isolation = 'repeatable read'",
    ),
    Control(
        # The one setting that turns every ALWAYS trigger off, on the one role
        # allowed to set it. From any other connection this statement is refused,
        # which is `roles:only_restore_may_set_replication_role` below.
        "baseline:session_replication_role",
        "SET LOCAL session_replication_role = 'replica'",
        on="restore",
    ),
    # --- the event log -------------------------------------------------------
    Control("baseline:event_coverage", "DROP TRIGGER entities_emit_event ON entities"),
    Control("standing:event_log_integrity", "DROP TRIGGER entities_emit_event ON entities"),
    Control("standing:event_coverage", "DROP TRIGGER entities_emit_event ON entities"),
    Control(
        "standing:control_surface",
        "DROP TRIGGER hypothesis_transitions_actor_kind_guard ON hypothesis_transitions",
    ),
    # --- causal attribution --------------------------------------------------
    Control(
        # RK-REG-007, exactly: the fourth Lane value the prototype allowed.
        "standing:causal_attribution",
        "ALTER TABLE receipts DROP CONSTRAINT receipts_lane_check;"
        " ALTER TABLE receipts ADD CONSTRAINT receipts_lane_check CHECK"
        " (lane = ANY (ARRAY['agent'::text, 'replay'::text, 'proxy_internal'::text, 'control'::text]))",
    ),
    Control(
        # RK-REG-004: a later redefinition that drops the transaction binding.
        "standing:causal_attribution",
        "CREATE OR REPLACE FUNCTION emit_event() RETURNS trigger LANGUAGE plpgsql"
        " AS $fn$ BEGIN RETURN NEW; END $fn$",
    ),
    # --- access control ------------------------------------------------------
    Control("standing:rls_coverage", "ALTER TABLE entities DISABLE ROW LEVEL SECURITY"),
    Control("standing:state_access", "ALTER TABLE entities DISABLE ROW LEVEL SECURITY"),
    Control("standing:state_grants", "GRANT SELECT ON entities TO rk2_state"),
    Control(
        # The registry back on the agent's surface. A role that can enumerate
        # Programs can tell a label nobody holds from a label another Program
        # holds, by asking a second question -- which is the whole of what
        # indistinguishable absence means.
        "standing:state_isolation",
        "GRANT SELECT ON programs TO rk2_state",
    ),
    Control(
        # The hole `state_access` rule 8 has and this one closes: a column grant
        # on a runtime table, which `information_schema.table_privileges` does
        # not list, so the older rule cannot see it.
        "standing:state_isolation",
        "GRANT SELECT (program_id) ON events TO rk2_state",
    ),
    Control(
        # The revision lookup answering with the owner's view of the log rather
        # than the caller's, which is every Program's.
        "standing:state_isolation",
        "ALTER FUNCTION rk2_revision(text, uuid) SECURITY DEFINER",
    ),
    Control(
        # The other half of the same rule: the descriptor is the one definition
        # of what an entity is called, and as a definer function it would name
        # any Program's entity to whoever could name one.
        "standing:state_isolation",
        "ALTER FUNCTION rk2_descriptor(uuid) SECURITY DEFINER",
    ),
    Control("standing:capability_receipt_fence", "GRANT INSERT ON receipts TO rk2_proxy"),
    Control(
        # Rule 4: the writer that checks nothing, reachable again. Every rule
        # `record_proxy_exchange` enforces is optional for a role that can call
        # what it delegates to, so the grant itself is the falsification.
        "standing:capability_receipt_fence",
        "GRANT EXECUTE ON FUNCTION write_allowed_receipt(text, jsonb) TO rk2_proxy",
    ),
    Control(
        # Rule 5: the gap 07's seal rule left for `register_proxy_artifacts`,
        # which this branch dropped. An encrypted artifact with no bytes is no
        # longer a placeholder for bytes somebody else registered; it is
        # credential-bearing material with no seal over it.
        "standing:capability_receipt_fence",
        "INSERT INTO artifacts (sha256, byte_size, visibility, encrypted)"
        " VALUES (" + repeat("a") + ", 0, 'credential_bearing', true)",
    ),
    Control("standing:program_isolation", "CREATE TABLE public.orphan_table (id uuid PRIMARY KEY)"),
    Control(
        # A Program opened by hand around `rk run`, which is what the check is
        # for: the root row is legal on its own, and nothing then records the
        # policy every Finding written under it would claim to have been
        # authorised by.
        "standing:program_configuration",
        "INSERT INTO programs (slug, name) VALUES ('unconfigured-selftest', 'Self test')",
    ),
    Control(
        # The other half of the same check: the Program has a policy on record
        # and is not running it. `programs` emits no event, so an update that
        # moved the budget without a revision behind it would leave the log
        # saying one thing and the scheduler reading another.
        "standing:program_configuration",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name, platform, token_budget)"
        "        VALUES ('misapplied-selftest', 'Self test', 'hackerone', 1000)"
        "     RETURNING id INTO p;"
        "   INSERT INTO program_configurations"
        "        (program_id, revision, schema_version, source_path, source_sha256,"
        "         canonical_sha256, document, platform, token_budget, reason)"
        "        VALUES (p, 1, 1, 'selftest', repeat('a', 64), repeat('b', 64),"
        "                '{}'::jsonb, 'hackerone', 2000, 'a policy the Program does not run');"
        " END $ctl$",
    ),
    Control(
        # A Program that compiled a policy and runs under none. Every entity of
        # it projects to denied, which is safe and is indistinguishable from a
        # policy that lists nothing -- so the operator sees an enforced scope
        # where there is no promoted one. The version is written and
        # `set_scope_version` is never called, which is the one state no honest
        # path produces: `_project_scope` writes and promotes in one transaction.
        "standing:scope_policy",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name, platform, token_budget)"
        "        VALUES ('scopeless-selftest', 'Self test', 'hackerone', 1000)"
        "     RETURNING id INTO p;"
        "   INSERT INTO program_configurations"
        "        (program_id, revision, schema_version, source_path, source_sha256,"
        "         canonical_sha256, document, platform, token_budget, reason)"
        "        VALUES (p, 1, 1, 'selftest', repeat('a', 64), repeat('b', 64),"
        "                '{}'::jsonb, 'hackerone', 1000, 'program opened');"
        "   INSERT INTO program_scope_versions"
        "        (program_id, version, policy, policy_sha256, configuration_revision)"
        "        VALUES (p, 1, jsonb_build_object('configuration_sha256', repeat('b', 64)),"
        "                repeat('c', 64), 1);"
        " END $ctl$",
    ),
    Control(
        # The redaction, which is a grant and not a convention: one row in the
        # registry is the whole edit that would put a runtime-owned secret
        # reference on the agent's read surface.
        "standing:scope_policy",
        "INSERT INTO state_read_surface (table_name, column_name, added_by)"
        " VALUES ('program_required_headers', 'value_ref', 'selftest')",
    ),
    Control(
        # A live version with a header and no body. Deny-by-default makes this
        # silent: the Program looks configured and every request is `unlisted`.
        "standing:scope_policy",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name, platform, token_budget)"
        "        VALUES ('bodyless-selftest', 'Self test', 'hackerone', 1000)"
        "     RETURNING id INTO p;"
        "   INSERT INTO program_configurations"
        "        (program_id, revision, schema_version, source_path, source_sha256,"
        "         canonical_sha256, document, platform, token_budget, reason)"
        "        VALUES (p, 1, 1, 'selftest', repeat('a', 64), repeat('b', 64),"
        "                '{}'::jsonb, 'hackerone', 1000, 'program opened');"
        "   INSERT INTO program_scope_versions"
        "        (program_id, version, policy, policy_sha256, configuration_revision)"
        "        VALUES (p, 1, jsonb_build_object('configuration_sha256', repeat('b', 64)),"
        "                repeat('c', 64), 1);"
        "   PERFORM set_scope_version(p, 1);"
        " END $ctl$",
    ),
    # --- the registry, and the catalogue it describes ------------------------
    Control(
        "standing:check_registration",
        "CREATE FUNCTION check_unregistered() RETURNS TABLE (problem text, subject text, detail text)"
        " LANGUAGE sql STABLE AS $fn$ SELECT 'x', 'y', 'z' WHERE false $fn$",
    ),
    Control(
        "standing:hook_provenance",
        "ALTER TABLE receipts DROP CONSTRAINT receipts_served_agent_needs_tool_run",
    ),
    Control(
        "standing:lane_quota_closure",
        "DELETE FROM lane_quota_profile_slots"
        " WHERE ctid IN (SELECT ctid FROM lane_quota_profile_slots LIMIT 1)",
    ),
    Control("standing:role_kind_mapping", "INSERT INTO task_kinds (kind) VALUES ('selftest_kind')"),
    Control("standing:scheduler_closure", "INSERT INTO task_kinds (kind) VALUES ('selftest_kind')"),
    Control(
        "standing:report_grounding",
        "INSERT INTO report_blocks (id, name, description)"
        " VALUES ('selftest_block', 'Self test', 'a block no template includes')",
    ),
    Control(
        "standing:playbook_integrity",
        "INSERT INTO surface_facts (id, scope, description)"
        " VALUES ('selftest_fact', 'endpoint', 'a fact no view computes')",
    ),
    Control(
        # The FK is what normally makes this unwritable. Dropping it first is the
        # point: the check exists because a migration can drop a constraint in
        # one line, and then only a standing check still says the row is wrong.
        "standing:playbook_tests",
        "ALTER TABLE fixture_classes DROP CONSTRAINT fixture_classes_property_class_fkey;"
        " INSERT INTO fixtures (id, kind, source_sha256)"
        " VALUES ('selftest-fixture', 'own_pair', repeat('a', 64));"
        " INSERT INTO fixture_classes (fixture_id, property_class)"
        " VALUES ('selftest-fixture', 'selftest.unknown_class')",
    ),
    Control("standing:transport_claims", "DROP TRIGGER transport_hypothesis_guard ON hypotheses"),
    Control(
        "standing:purge_reachability",
        "CREATE FUNCTION selftest_block_delete() RETURNS trigger LANGUAGE plpgsql"
        " AS $fn$ BEGIN RETURN OLD; END $fn$;"
        " CREATE TRIGGER entities_selftest_guard BEFORE DELETE ON entities"
        " FOR EACH ROW EXECUTE FUNCTION selftest_block_delete()",
    ),
    Control("standing:role_catalogue", "GRANT TRUNCATE ON entities TO rk2_runtime"),
    # --- artifacts a Program can reach ---------------------------------------
    Control(
        # Rule 1: the bytes go and the label that cites them stays. This is the
        # state the NO ACTION key exists to prevent, so it takes a purge rather
        # than a delete to reach it at all.
        "standing:artifact_reachability",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('dangling-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO artifacts (sha256, byte_size, content_type, visibility)"
        "        VALUES (repeat('c', 64), 3, 'text/plain', 'agent_visible');"
        "   INSERT INTO artifact_references (program_id, sha256, kind)"
        "        VALUES (p, repeat('c', 64), 'runtime');"
        "   UPDATE artifacts SET purged_at = now() WHERE sha256 = repeat('c', 64);"
        " END $ctl$",
    ),
    Control(
        # Rule 2: a label pointing at credential-bearing material. The table
        # already insists such an artifact is encrypted, which is why the check
        # is about the reference rather than about the artifact.
        "standing:artifact_reachability",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('secret-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO artifacts (sha256, byte_size, visibility, encrypted)"
        "        VALUES (repeat('d', 64), 3, 'credential_bearing', true);"
        "   INSERT INTO artifact_references (program_id, sha256, kind)"
        "        VALUES (p, repeat('d', 64), 'runtime');"
        " END $ctl$",
    ),
    Control(
        # Rule 3: one line of a later migration, which is the whole reason the
        # rule is a standing check and not a comment on the constraint.
        "standing:artifact_reachability",
        "ALTER TABLE artifact_references DROP CONSTRAINT artifact_references_sha256_fkey;"
        " ALTER TABLE artifact_references ADD CONSTRAINT artifact_references_sha256_fkey"
        " FOREIGN KEY (sha256) REFERENCES artifacts(sha256) ON DELETE CASCADE",
    ),
    Control(
        # Rule 4: the bridge read as its owner. Every reference of every Program
        # would satisfy the policy on `artifacts` from any session.
        "standing:artifact_reachability",
        "ALTER VIEW artifact_refs SET (security_invoker = false)",
    ),
    # --- wire artifacts, and the key arrangement behind them ------------------
    Control(
        # Rule 2, and the one that matters most: credential-bearing bytes with no
        # seal describing them. This is the state ticket 07 exists to prevent --
        # the artifact store holding a plaintext capability under an ordinary
        # hash, which every later reader treats as ordinary.
        "standing:wire_artifact_secrecy",
        "INSERT INTO artifacts (sha256, byte_size, visibility, encrypted)"
        " VALUES (" + repeat("e") + ", 41, 'credential_bearing', true)",
    ),
    Control(
        # Rule 1 from the other side: a seal over bytes that are not sealed. The
        # row would say the material is protected and the artifact would say
        # anyone may read it.
        "standing:wire_artifact_secrecy",
        SEAL_CONTROL.format(
            sealed=f"({repeat('e')}, 9, 'agent_visible', false)",
            reference=f"INSERT INTO artifact_references (program_id, sha256, kind)"
            f" VALUES (p, {repeat('f')}, 'runtime');",
            extra="",
        ),
    ),
    Control(
        # Rule 5: the redacted view exists and no Program names it. Criterion 4
        # asks for two references describing what each party saw; an agent view
        # nothing can cite is one reference and a file.
        "standing:wire_artifact_secrecy",
        SEAL_CONTROL.format(
            sealed=f"({repeat('e')}, 9, 'credential_bearing', true)",
            reference="",
            extra="",
        ),
    ),
    Control(
        # Rule 6: the envelope registered as an artifact of its own. Nothing in
        # the pair is wrong; what is wrong is the second, unsealed name for the
        # same material, which rule 2 cannot see because a ciphertext row is not
        # marked encrypted.
        "standing:wire_artifact_secrecy",
        SEAL_CONTROL.format(
            sealed=f"({repeat('e')}, 9, 'credential_bearing', true)",
            reference=f"INSERT INTO artifact_references (program_id, sha256, kind)"
            f" VALUES (p, {repeat('f')}, 'runtime');",
            extra="INSERT INTO artifacts (sha256, byte_size, visibility)"
            f" VALUES ({repeat('1')}, 200, 'agent_visible');",
        ),
    ),
    Control(
        # Rule 7: the agent connection reaching the seal record. It carries no
        # key material and it does carry the nonce, the generation and the exact
        # size of every wire message -- and, through `agent_sha256`, a hash the
        # session can join back to its own artifacts.
        "standing:wire_artifact_secrecy",
        "GRANT SELECT (nonce) ON artifact_seal TO rk2_state",
    ),
    Control(
        # Rule 8: a wrapped data key in the database. The prototype's design
        # stored one per scope; this runtime derives the Program's key from a
        # root secret the database never sees, so a row here means something is
        # keeping key material where the dumps go.
        "standing:wire_artifact_secrecy",
        "INSERT INTO secret_kek (gen, salt, root_check)"
        " VALUES (1, decode(repeat('61', 32), 'hex'), decode(repeat('62', 16), 'hex'));"
        " INSERT INTO secret_dek (scope_kind, scope_id, dek_gen, kek_gen, wrapped)"
        " VALUES ('program', '00000000-0000-4000-8000-000000000001'::uuid, 1, 1,"
        "         decode(repeat('63', 60), 'hex'))",
    ),
    # --- the role split ------------------------------------------------------
    Control("roles:runtime_no_truncate_anywhere", "GRANT TRUNCATE ON entities TO rk2_runtime"),
    Control(
        "roles:runtime_readwrite_on_every_managed_table",
        "REVOKE INSERT ON entities FROM rk2_runtime",
    ),
    Control(
        # As the login role, not as the owner: rk2_owner is a member of nothing,
        # so it cannot hand a table to a role it cannot become.
        "roles:owner_owns_every_managed_table",
        "ALTER TABLE entities OWNER TO rk2_migrate",
        on="migrate",
    ),
    Control(
        "roles:runtime_owns_no_managed_table",
        "ALTER TABLE entities OWNER TO rk2_runtime",
        on="superuser",
    ),
    Control(
        "roles:model_reachable_roles_are_not_human",
        "GRANT rk2_human TO rk2_runtime",
        on="superuser",
    ),
    Control(
        "roles:state_cannot_become_runtime_or_owner",
        "GRANT rk2_runtime TO rk2_state",
        on="superuser",
    ),
    Control(
        "roles:no_role_has_createrole_or_bypassrls",
        "ALTER ROLE rk2_human CREATEROLE",
        on="superuser",
    ),
    Control(
        "roles:only_restore_may_set_replication_role",
        "GRANT SET ON PARAMETER session_replication_role TO rk2_runtime",
        on="superuser",
    ),
    Control(
        "roles:runtime_cannot_set_replication_role",
        "GRANT SET ON PARAMETER session_replication_role TO rk2_runtime",
        on="superuser",
    ),
    Control(
        # The catalogue counts six roles by name and `rk2_migrate` is one of
        # them. Renaming it is the falsification that stays answerable: every
        # other check that reads this role reads it through a NULL-safe
        # subquery, so the count comes back 5 of 6 rather than raising.
        "roles:roles_present",
        "ALTER ROLE rk2_migrate RENAME TO rk2_absent",
        on="superuser",
    ),
    Control("roles:migrate_role_is_not_superuser", "ALTER ROLE rk2_migrate SUPERUSER", on="superuser"),
    Control("roles:runtime_not_superuser", "ALTER ROLE rk2_runtime SUPERUSER", on="superuser"),
    Control("roles:runtime_not_bypassrls", "ALTER ROLE rk2_runtime BYPASSRLS", on="superuser"),
    Control("roles:runtime_not_owner", "GRANT rk2_owner TO rk2_runtime", on="superuser"),
    Control("roles:proxy_is_not_owner_or_human", "GRANT rk2_human TO rk2_proxy", on="superuser"),
)

#: Checks whose subject cannot be taken away without a sibling check in the same
#: function raising first, which aborts the whole family before any row is
#: returned. The gate reports that as a refusal rather than as a pass -- the
#: property that actually protects an operator -- but it cannot name the check
#: that was about to fail, so these are counted apart from the controls above
#: rather than quietly folded in with them.
REFUSES = (
    ("ALTER ROLE rk2_proxy RENAME TO rk2_absent", "superuser", ("roles:proxy_role_exists",)),
    ("ALTER ROLE rk2_runtime RENAME TO rk2_gone", "superuser", ("roles:runtime_role_exists",)),
    (
        "DROP EXTENSION vector CASCADE",
        "superuser",
        ("baseline:pgvector_version", "baseline:hnsw_cosine_opclass"),
    ),
)

#: Checks about the server binary itself. Falsifying either means running a
#: different PostgreSQL, which is a property of the container this suite is
#: pointed at rather than something a test can arrange. `uuidv7_is_builtin`
#: belongs here only because it is aggregated: read as a scalar subquery it
#: would raise on a second zero-argument `uuidv7()` instead of reporting.
UNFALSIFIABLE = {"baseline:server_major", "baseline:uuidv7_is_builtin"}


class NegativeControlTest(DatabaseCase):
    """Criterion 5: each check, shown failing when its subject is broken."""

    def run_gate(self, connection: pg.Connection) -> list[str]:
        return [
            check.source
            for check in integrity.run(connection, self.harness.expected)
            if not check.ok
        ]

    def connection_for(self, on: str) -> pg.Connection:
        return {
            "owner": self.connection,
            "migrate": self.connection,
            "superuser": self.superuser,
            "restore": self.restore,
        }[on]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.superuser = pg.connect(cls.harness.superuser)
        cls.restore = pg.connect(cls.harness.restore)

    @classmethod
    def tearDownClass(cls):
        cls.superuser.close()
        cls.restore.close()
        super().tearDownClass()

    def break_it(self, sql: str, on: str) -> list[str]:
        connection = self.connection_for(on)
        failed: list[str] = []
        try:
            with connection.transaction():
                if on == "owner":
                    connection.execute("SET LOCAL ROLE rk2_owner")
                connection.execute_script(sql)
                failed = self.run_gate(connection)
                raise Rollback
        except Rollback:
            pass
        return failed

    def test_the_gate_holds_before_anything_is_broken(self):
        self.assertEqual([], self.run_gate(self.connection))

    def test_each_check_fails_when_its_subject_is_broken(self):
        for control in CONTROLS:
            with self.subTest(control.check):
                self.assertIn(control.check, self.break_it(control.sql, control.on))

    def test_a_check_whose_subject_is_gone_refuses_rather_than_passes(self):
        for sql, on, checks in REFUSES:
            with self.subTest(checks):
                connection = self.connection_for(on)
                try:
                    with connection.transaction():
                        connection.execute_script(sql)
                        result = integrity.verify(connection, self.harness.expected)

                        self.assertFalse(result.ok)
                        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
                        self.assertIn("could not be run", result.violations[0].detail)
                        raise Rollback
                except Rollback:
                    pass

    def test_an_index_the_server_cannot_build_fails_the_headroom_check(self):
        # The one check that needs rows rather than an edit: headroom is the
        # number of vectors an HNSW build fits in maintenance_work_mem, so
        # falsifying it means having more rows than the setting allows.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SET LOCAL maintenance_work_mem = '64kB'")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program = self.connection.execute(PROGRAM, ("headroom-selftest",)).scalar()
                entity = self.connection.execute(ENTITY, (program,)).scalar()
                hypothesis = self.connection.execute(HYPOTHESIS, (program, entity)).scalar()
                self.connection.execute(
                    "INSERT INTO hypothesis_embeddings (hypothesis_id, model, embedding, program_id)"
                    " SELECT $1, 'selftest-' || g, array_fill(0::real, ARRAY[1536])::vector, $2"
                    "   FROM generate_series(1, 12) g",
                    (hypothesis, program),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("baseline:hnsw_headroom", failed)

    def test_an_unattributable_receipt_fails_the_receipt_check(self):
        # Also rows rather than an edit: an agent-lane request that no tool run
        # accounts for is the shape RK-REG-002 produced.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program = self.connection.execute(PROGRAM, ("receipt-selftest",)).scalar()
                self.connection.execute(
                    "INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)"
                    " VALUES ($1, 1, '{}'::jsonb, repeat('b', 64))",
                    (program,),
                )
                self.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason, ts_arrival,"
                    " scope_class, scope_version, host)"
                    " VALUES ($1, 'agent', 'blocked', 'self test', now(), 'target', 1, 'example.test')",
                    (program,),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    def test_every_check_the_gate_runs_has_a_control(self):
        # The assertion that keeps the rest of this file honest: a check added
        # without a control fails here, naming itself, instead of joining the
        # gate as one more thing nobody has seen fail.
        covered = {control.check for control in CONTROLS}
        covered |= {check for _, _, checks in REFUSES for check in checks}
        covered |= UNFALSIFIABLE
        covered |= {"baseline:hnsw_headroom", "standing:receipt_integrity"}
        ran = {check.source for check in integrity.run(self.connection, self.harness.expected)}

        self.assertEqual(set(), ran - covered, "a check with no negative control")
        self.assertEqual(set(), covered - ran, "a control for a check the gate does not run")

    def test_the_database_is_unchanged_afterwards(self):
        # Every control above rolls back. If one did not, the gate says so here.
        self.assertEqual([], self.run_gate(self.connection))


#: What every Program these tests open is called, so the cleanup can find all of
#: them by prefix and each test can still have one nobody else touches.
RUN_SLUG = "selftest-run"


class ProgramRunTest(DatabaseCase):
    """PH2-04: `rk run` opens a Program once and resumes that one afterwards.

    The only tests in this module that commit. Everything else writes inside a
    transaction it rolls back, because the gate and the archive want an empty
    database to look at; this operation's entire subject is what survives the
    transaction, so it cannot be asked that way. The rows go at the end, down
    the path a purge takes.

    They also run as `rk2_runtime` rather than as the owner, which is the point
    of asking a real server at all: row level security is in force, no DDL is
    reachable, and the readiness assertion the command makes about its own
    connection is being made about the connection production uses.
    """

    settings_for = "runtime"

    @classmethod
    def tearDownClass(cls):
        # `DELETE FROM programs` is the purge, and every table cascades from it.
        # `app.purging` is what the immutability triggers read; without it the
        # configuration revisions and the events refuse to go, which is the
        # property they exist for.
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute("DELETE FROM programs WHERE slug LIKE $1", (f"{RUN_SLUG}-%",))
        super().tearDownClass()

    def configuration(self, slug: str, text: str = VALID) -> Path:
        """The fixture, renamed to a Program of this test's own.

        Each call writes into a directory of its own, so a second run of the
        same policy arrives at a different path. That is deliberate: the source
        path is provenance, and resuming has to key on the policy instead.
        """
        return write(text.replace('name = "acme-web"', f'name = "{slug}"'))

    def run_for(self, slug: str, text: str = VALID, **options: object) -> Report:
        return program.run(self.harness.runtime, self.configuration(slug, text), **options)

    def programs(self, slug: str) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM programs WHERE slug = $1", (slug,)
            ).scalar()
        )

    def revisions(self, program_id: str) -> list[tuple]:
        return [
            tuple(row)
            for row in self.connection.execute(
                "SELECT revision, reason, canonical_sha256 FROM program_configurations"
                " WHERE program_id = $1::uuid ORDER BY revision",
                (program_id,),
            ).rows
        ]

    def events(self, program_id: str) -> list[tuple]:
        return [
            tuple(row)
            for row in self.connection.execute(
                "SELECT type, subject_table, actor_kind, payload::text FROM events"
                " WHERE program_id = $1::uuid ORDER BY seq",
                (program_id,),
            ).rows
        ]

    def test_the_first_run_opens_the_program_and_records_its_policy(self):
        # Criterion 1: one Program, one revision, one transaction, one actor.
        slug = f"{RUN_SLUG}-open"

        result = self.run_for(slug)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual(slug, result.facts["program_slug"])
        self.assertEqual("open", result.facts["lifecycle"])
        self.assertEqual(program.STOPPED_NOTHING_TO_EXECUTE, result.facts["stop_reason"])
        self.assertEqual(1, result.facts["configuration"]["revision"])
        # Readiness, as the runtime is entitled to ask it: the role catalogue is
        # the runner's, so this connection never sends that query.
        self.assertEqual(["baseline", "standing"], result.facts["integrity"]["families"])
        self.assertEqual(
            [(result.facts["program_id"], "hackerone", 2000000)],
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT id::text, platform, token_budget FROM programs WHERE slug = $1",
                    (slug,),
                ).rows
            ],
        )
        self.assertEqual(
            [(1, "program opened", result.facts["configuration"]["canonical_sha256"])],
            self.revisions(result.facts["program_id"]),
        )

    def test_the_same_command_resumes_rather_than_opening_a_second_program(self):
        # Criterion 2: the identity is the slug and the policy is the canonical
        # hash, so the second run is the same Program even from a different path.
        slug = f"{RUN_SLUG}-again"

        first = self.run_for(slug)
        second = self.run_for(slug)

        self.assertTrue(second.ok, second.violations)
        self.assertEqual(first.facts["program_id"], second.facts["program_id"])
        self.assertEqual(1, second.facts["configuration"]["revision"])
        self.assertEqual(1, self.programs(slug))
        self.assertEqual([1], [revision for revision, _, _ in self.revisions(first.facts["program_id"])])

    def test_opening_and_resuming_each_emit_exactly_one_event(self):
        # Criterion 4. The first is trigger-authored, from the row write; the
        # second is written by the command, because a sweep that changed nothing
        # is still a fact about the Program and no trigger can observe it.
        slug = f"{RUN_SLUG}-events"

        opened = self.run_for(slug)
        program_id = opened.facts["program_id"]
        after_open = self.events(program_id)
        self.run_for(slug)
        after_resume = self.events(program_id)

        self.assertEqual(
            [("program.configured", "program_configurations", "runtime")],
            [event[:3] for event in after_open],
        )
        self.assertEqual(2, len(after_resume))
        self.assertEqual(("run.resumed", None, "runtime"), after_resume[1][:3])
        payload = json.loads(after_resume[1][3])
        self.assertEqual(1, payload["configuration_revision"])
        self.assertEqual(0, payload["counts"]["tasks_unclaimed"])

    def test_the_event_a_revision_writes_carries_no_value_out_of_the_policy(self):
        # Criterion 4's other half. `events` is read by connections that are not
        # allowed the configuration itself, so the document is redacted and the
        # hashes are what say which policy the event is about.
        slug = f"{RUN_SLUG}-redacted"

        result = self.run_for(slug)

        payload = json.loads(self.events(result.facts["program_id"])[0][3])
        self.assertEqual("[redacted]", payload["after"]["document"])
        self.assertEqual(
            result.facts["configuration"]["canonical_sha256"], payload["after"]["canonical_sha256"]
        )
        # What the revision put on the `programs` row is not redacted: that row
        # emits no event of its own, so this is where the projection is legible.
        self.assertEqual(2000000, payload["after"]["token_budget"])
        self.assertEqual("hackerone", payload["after"]["platform"])
        for value in ("app.example.com", "slot://identity/member", "X-Bounty-Id", "oob.example.net"):
            self.assertNotIn(value, json.dumps(payload))

    def test_a_changed_policy_is_refused_and_leaves_the_program_as_it_was(self):
        # Criterion 3: drift is detected before execution, and the refusal names
        # both policies and the flag that would adopt the new one.
        slug = f"{RUN_SLUG}-drift"
        opened = self.run_for(slug)
        program_id = opened.facts["program_id"]

        changed = self.run_for(slug, VALID.replace("requests = 5000", "requests = 50000"))

        self.assertFalse(changed.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, changed.exit_code)
        self.assertIn("--accept-change", changed.violations[0].detail)
        self.assertEqual(program.STOPPED_REFUSED, changed.facts["stop_reason"])
        self.assertEqual(1, changed.facts["configuration"]["revision"])
        self.assertEqual([1], [revision for revision, _, _ in self.revisions(program_id)])
        self.assertEqual(1, len(self.events(program_id)))

    def test_a_change_the_operator_accepts_becomes_the_next_revision(self):
        # The other side of criterion 3: an explicit revision, never a silent
        # replacement. Revision 1 is still readable and still says what it said.
        slug = f"{RUN_SLUG}-accepted"
        opened = self.run_for(slug)
        program_id = opened.facts["program_id"]

        accepted = self.run_for(
            slug, VALID.replace("tokens = 2000000", "tokens = 3000000"), accept_change=True
        )

        self.assertTrue(accepted.ok, accepted.violations)
        self.assertEqual(program_id, accepted.facts["program_id"])
        self.assertEqual(2, accepted.facts["configuration"]["revision"])
        revisions = self.revisions(program_id)
        self.assertEqual([1, 2], [revision for revision, _, _ in revisions])
        self.assertNotEqual(revisions[0][2], revisions[1][2])
        self.assertEqual(
            3000000,
            self.connection.execute(
                "SELECT token_budget FROM programs WHERE id = $1::uuid", (program_id,)
            ).scalar(),
        )
        # A policy change and a resume both happened, and the log says both.
        events = self.events(program_id)
        self.assertEqual(
            ["program.configured", "program.configured", "run.resumed"],
            [event[0] for event in events],
        )
        # And the budget the Program now runs under is readable as a before and
        # an after, which is the only place it is: the `UPDATE programs` that
        # applied it writes no event.
        self.assertEqual(
            [2000000, 3000000],
            [
                json.loads(event[3])["after"]["token_budget"]
                for event in events
                if event[0] == "program.configured"
            ],
        )

    def test_a_retired_program_is_reported_rather_than_resumed(self):
        # Its rows are the record of work that finished and are scheduled to go;
        # resuming into them would attach new work to a purge already ordered.
        slug = f"{RUN_SLUG}-retired"
        opened = self.run_for(slug)
        program_id = opened.facts["program_id"]
        self.connection.execute("SELECT retire_program($1::uuid)", (program_id,))

        result = self.run_for(slug)

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual("retired", result.facts["lifecycle"])
        self.assertEqual(program_id, result.facts["program_id"])
        self.assertEqual(1, len(self.events(program_id)))

    def test_a_database_that_is_not_ready_is_refused_before_anything_is_written(self):
        # Criterion 5, the first half, at the last point it can still be true:
        # the gate runs on this connection, and a corpus the database has not
        # caught up with is a refusal rather than a Program opened against the
        # wrong schema. It is also what proves the runtime can read the
        # migration ledger at all -- without that grant the whole baseline
        # family raises instead of answering.
        slug = f"{RUN_SLUG}-unready"
        corpus = scratch() / "migrations"
        shutil.copytree(migrate.CORPUS, corpus)
        (corpus / "20991231T235959Z__selftest_pending.sql").write_text(
            "-- a migration this database has never seen\n", encoding="utf-8"
        )

        result = program.run(self.harness.runtime, self.configuration(slug), corpus=corpus)

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertIsNone(result.facts["program_id"])
        self.assertEqual(["baseline:no_pending_migrations"], result.facts["integrity"]["failed"])
        self.assertEqual(0, self.programs(slug))

    def test_a_failure_after_the_commit_still_leaves_a_durable_program(self):
        # Criterion 5, the second half. The read-back is the seam: it happens
        # after the transaction commits, so failing it is the shape of every
        # loss of the connection at the worst moment. The Program exists, the
        # report says which one, and the operator is told where to look.
        slug = f"{RUN_SLUG}-durable"
        execute = pg.Connection.execute

        def fail_on_read_back(self, sql, parameters=()):
            if sql.startswith("SELECT closed_at"):
                raise pg.ConnectionError_("the connection was closed by the server")
            return execute(self, sql, parameters)

        with mock.patch.object(pg.Connection, "execute", fail_on_read_back):
            result = program.run(self.harness.runtime, self.configuration(slug))

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.exit_code)
        self.assertIn("rk db verify", result.violations[0].detail)
        program_id = result.facts["program_id"]
        self.assertIsNotNone(program_id)
        self.assertEqual(1, self.programs(slug))
        self.assertEqual([1], [revision for revision, _, _ in self.revisions(program_id)])

    def test_the_gate_still_holds_over_the_programs_these_tests_opened(self):
        # The rows above are the first this module leaves committed, and the
        # standing check the migration registered is about exactly them.
        #
        # The whole gate, on the runner's connection: `rk run` asks for two of
        # the three families because the role catalogue is not the runtime's to
        # run, and this is where the third one is answered about the same rows.
        self.run_for(f"{RUN_SLUG}-gate")

        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected)

        self.assertTrue(result.ok, result.violations)


#: The Program the scope tests open. Named apart from `RUN_SLUG` so the purge at
#: the end of each class finds only its own rows.
SCOPE_SLUG = "selftest-scope"


class ScopeEvaluatorTest(DatabaseCase):
    """PH2-08: the compiled policy, decided in SQL rather than in Python.

    The fixture matrix is the subject. `tests/test_scope.py` puts it through the
    evaluator and `tests/test_cli.py` puts it through `rk scope`; this puts the
    same rows through `scope_class_of`, and a disagreement between the three is
    the failure the whole ticket is about -- two implementations of one grammar
    that answer differently are two policies.

    Canonicalisation is Python's job in both worlds, so the matrix is read into
    a `Request` here and the host, port and both path spellings are handed to
    SQL. That is exactly what the runtime does: the proxy canonicalises once and
    the database matches what it was given.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.opened = program.run(cls.harness.runtime, cls.written("matrix"))
        assert cls.opened.ok, cls.opened.violations
        cls.program_id = cls.opened.facts["program_id"]
        cls.version = cls.opened.facts["scope"]["version"]
        cls.policy = cls.compiled()

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{SCOPE_SLUG}-%",)
            )
        super().tearDownClass()

    @classmethod
    def written(cls, name: str, text: str = SCOPED) -> Path:
        return write(text.replace('name = "matrix-web"', f'name = "{SCOPE_SLUG}-{name}"'))

    @classmethod
    def compiled(cls, name: str = "matrix", text: str = SCOPED) -> scope.Policy:
        # The name has to be the one the run opened: `Policy.document` carries
        # the Program name, so compiling under a second slug produces a policy
        # whose digest can never equal the digest the run wrote.
        configuration, refusals = config.load(cls.written(name, text))
        assert configuration is not None, refusals
        policy, refused = scope.compile_policy(configuration)
        assert policy is not None, refused
        return policy

    def ask(self, request: scope.Request) -> tuple:
        return tuple(
            self.connection.execute(
                "SELECT scope_class, reason, rule_ord"
                "  FROM scope_class_of($1::uuid, $2, $3, $4, $5, $6, $7, $8)",
                (
                    self.program_id,
                    self.version,
                    request.host,
                    request.port,
                    request.path_raw,
                    request.path_norm,
                    request.protocol,
                    request.question,
                ),
            ).rows[0]
        )

    def project(self, kind: str, selector: str, port: int | None, path: str) -> tuple:
        raw, normalized = scope.path_variants(path)
        return tuple(
            self.connection.execute(
                "SELECT scope_class, reason, rule_ord"
                "  FROM scope_class_of_entity($1::uuid, $2, $3, $4, $5, $6, $7)",
                (self.program_id, self.version, kind, selector, port, raw, normalized),
            ).rows[0]
        )

    def rules(self, version: int) -> int:
        return int(
            self.connection.execute(
                "SELECT count(*) FROM program_scope_rules"
                " WHERE program_id = $1::uuid AND version = $2",
                (self.program_id, version),
            ).scalar()
        )

    def test_the_run_writes_the_policy_it_compiled_and_promotes_it(self):
        # 021 built these tables and left nothing writing them. This is the first
        # test in the suite for which `programs.scope_version` is not NULL.
        facts = self.opened.facts["scope"]

        self.assertEqual(1, facts["version"])
        self.assertEqual(1, facts["configuration_revision"])
        self.assertTrue(facts["compiled"])
        self.assertEqual(len(self.policy.rules), facts["rules"])
        self.assertEqual(self.policy.policy_sha256(), facts["policy_sha256"])
        self.assertEqual(
            [(1, self.policy.policy_sha256(), 1, True)],
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT p.scope_version, sv.policy_sha256, sv.configuration_revision,"
                    "       sv.mutation"
                    "  FROM programs p"
                    "  JOIN program_scope_versions sv"
                    "    ON sv.program_id = p.id AND sv.version = p.scope_version"
                    " WHERE p.id = $1::uuid",
                    (self.program_id,),
                ).rows
            ],
        )
        self.assertEqual(len(self.policy.rules), self.rules(1))

    def test_every_request_in_the_matrix_gets_the_same_verdict_from_sql(self):
        for url, scope_class, reason in SCOPE_REQUESTS:
            with self.subTest(url):
                request = scope.canonical_request(url)
                verdict = scope.decide_request(self.policy, request)

                answered, said, ord_cited = self.ask(request)

                self.assertEqual((scope_class, reason), (answered, said))
                # And the same rule is cited, which is the part a receipt records:
                # agreeing on the verdict while disagreeing on why is a policy an
                # operator cannot audit.
                self.assertEqual(verdict.rule_ord, None if ord_cited is None else int(ord_cited))

    def test_every_entity_in_the_matrix_gets_the_same_verdict_from_sql(self):
        for kind, selector, port, path, scope_class, reason in SCOPE_ENTITIES:
            with self.subTest(f"{kind}:{selector}:{port}:{path}"):
                verdict = scope.decide_entity(
                    self.policy, kind, selector, port=port, path=path
                )

                answered, said, ord_cited = self.project(kind, selector, port, path)

                self.assertEqual((scope_class, reason), (answered, said))
                self.assertEqual(verdict.rule_ord, None if ord_cited is None else int(ord_cited))

    def test_an_entity_with_no_selector_is_not_a_scope_question_in_either_world(self):
        # An identity slot and a technology fingerprint have no address. Denied
        # and not-addressable are both refusals and they are not the same fact.
        answered, said, _ = self.project(None, None, None, "/")

        self.assertEqual(("not_addressable", "not_addressable"), (answered, said))
        self.assertEqual(
            scope.NOT_ADDRESSABLE, scope.decide_entity(self.policy, None, None).scope_class
        )

    def test_a_host_sql_cannot_read_is_refused_for_the_reason_python_gives(self):
        # `scope_normalize_host` returns NULL for "there was no host" and for
        # "the host was malformed" alike, so `scope_host_problem` is what keeps
        # the two reasons apart. Without it the matrix would agree on every
        # verdict and disagree on half the reasons.
        for host, reason in (("", "no_host"), ("app..example.com", "malformed_host")):
            with self.subTest(host):
                answered, said, _ = self.ask(
                    scope.Request(protocol="https", host=host, port=443, path_raw="/", path_norm="/")
                )

                self.assertEqual(("denied", reason), (answered, said))

    def test_the_required_header_name_is_readable_and_its_reference_is_not(self):
        # Criterion 3. The grant is the redaction: `rk2_state` holds no
        # relation-level privilege on this table, so the read surface registry is
        # the grant, and `value_ref` is not in it.
        self.assertEqual(
            [("X-Bounty-Id", True, False)],
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT h.name,"
                    "       has_column_privilege('rk2_state', 'program_required_headers',"
                    "                            'name', 'SELECT'),"
                    "       has_column_privilege('rk2_state', 'program_required_headers',"
                    "                            'value_ref', 'SELECT')"
                    "  FROM program_required_headers h"
                    " WHERE h.program_id = $1::uuid AND h.version = $2"
                    " ORDER BY h.ord",
                    (self.program_id, self.version),
                ).rows
            ],
        )
        self.assertEqual(
            ["name", "ord", "program_id", "version"],
            [
                str(row[0])
                for row in self.connection.execute(
                    "SELECT column_name FROM state_read_surface"
                    " WHERE table_name = 'program_required_headers' ORDER BY column_name"
                ).rows
            ],
        )

    def test_no_event_carries_the_reference_the_runtime_resolves(self):
        # The other half of the same criterion, and why the table emits nothing:
        # a redacted column in an event payload is a rule that has to keep
        # working, and no event at all is a rule that cannot stop working.
        events = [
            (str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT type, payload::text FROM events WHERE program_id = $1::uuid ORDER BY seq",
                (self.program_id,),
            ).rows
        ]

        self.assertEqual(["program.configured"], [name for name, _ in events])
        for name, payload in events:
            with self.subTest(name):
                self.assertNotIn("slot://", payload)

    def test_a_required_header_cannot_be_edited_or_dropped_afterwards(self):
        # Immutable with the version it belongs to. A header whose reference
        # could be repointed would change what every request carries without
        # changing the policy digest that says what the request should carry.
        for statement in (
            "UPDATE program_required_headers SET value_ref = 'slot://header/other'"
            " WHERE program_id = $1::uuid",
            "DELETE FROM program_required_headers WHERE program_id = $1::uuid",
        ):
            with self.subTest(statement.split()[0]), self.assertRaises(pg.DatabaseError) as refused:
                with self.connection.transaction():
                    self.connection.execute(statement, (self.program_id,))

            self.assertIn("immutable", str(refused.exception).lower())

    def test_resuming_the_same_policy_writes_no_second_version(self):
        # Idempotent by digest. Without this every `rk run` would append an
        # identical version, and the version numbers receipts cite would count
        # restarts rather than policy changes.
        resumed = program.run(self.harness.runtime, self.written("matrix"))

        self.assertTrue(resumed.ok, resumed.violations)
        self.assertEqual(self.program_id, resumed.facts["program_id"])
        self.assertEqual(1, resumed.facts["scope"]["version"])
        self.assertFalse(resumed.facts["scope"]["compiled"])
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT count(*) FROM program_scope_versions WHERE program_id = $1::uuid",
                (self.program_id,),
            ).scalar(),
        )

    def test_an_accepted_change_compiles_the_next_version_and_promotes_it(self):
        # A Program of its own, so the matrix above keeps reading version 1.
        changed = SCOPED.replace('host = "api.example.net"', 'host = "api.example.org"')
        opened = program.run(self.harness.runtime, self.written("revised"))
        assert opened.ok, opened.violations
        program_id = opened.facts["program_id"]

        revised = program.run(
            self.harness.runtime, self.written("revised", changed), accept_change=True
        )

        self.assertTrue(revised.ok, revised.violations)
        self.assertEqual(program_id, revised.facts["program_id"])
        self.assertEqual(2, revised.facts["configuration"]["revision"])
        self.assertEqual(2, revised.facts["scope"]["version"])
        self.assertNotEqual(
            opened.facts["scope"]["policy_sha256"], revised.facts["scope"]["policy_sha256"]
        )
        # Version 1 is still there and still says what it said: receipts cite it.
        self.assertEqual(
            [(1, 1), (2, 2)],
            [
                tuple(row)
                for row in self.connection.execute(
                    "SELECT version, configuration_revision FROM program_scope_versions"
                    " WHERE program_id = $1::uuid ORDER BY version",
                    (program_id,),
                ).rows
            ],
        )
        self.assertEqual(
            2,
            self.connection.execute(
                "SELECT scope_version FROM programs WHERE id = $1::uuid", (program_id,)
            ).scalar(),
        )

    def test_the_invariants_this_ticket_added_hold_over_what_the_run_wrote(self):
        # The check the migration registered, over the rows the real path wrote:
        # every Program that stated a policy runs the compiled form of its newest
        # revision, that form names the bytes it came from, and it has rules.
        self.assertEqual([], [tuple(row) for row in self.connection.execute(
            "SELECT * FROM check_scope_policy()"
        ).rows])


#: The Programs the state tests open. Two, because one Program can never
#: demonstrate isolation from itself.
STATE_SLUG = "selftest-state"

#: What the database is, in the terms criterion 6 is about: its size on disk,
#: the log that every revision is read from, and the Leases. A read that changed
#: any of them would move at least one of these numbers.
SNAPSHOT = """
SELECT pg_database_size(current_database()),
       (SELECT count(*) FROM events),
       (SELECT coalesce(max(seq), 0) FROM events),
       (SELECT count(*) FROM identity_leases),
       (SELECT coalesce(md5(string_agg(l::text, '|' ORDER BY l.id)), '')
          FROM identity_leases l),
       (SELECT coalesce(md5(string_agg(e::text, '|' ORDER BY e.id)), '') FROM entities e),
       (SELECT coalesce(md5(string_agg(h::text, '|' ORDER BY h.id)), '') FROM hypotheses h)
"""

#: Everything in `SNAPSHOT` except its first column. The size on disk moves for
#: reasons that are not writes -- a catalogue page dirtied by a GRANT, autovacuum
#: -- so it is compared across one test rather than across a whole class.
ROWS = slice(1, None)


def snapshot(connection: pg.Connection) -> tuple:
    return tuple(connection.execute(SNAPSHOT).rows[0])


class StateReadTest(DatabaseCase):
    """PH2-05: what one Program can read about itself, and what it cannot ask.

    Two Programs, both holding the label `TEC1`, because colliding short labels
    are not an accident to be avoided: labels are per Program and are meant to
    be short, so the collision is the ordinary case and isolation has to hold
    through it rather than around it.

    The reads run as `rk2_state` over a real server for the same reason
    `ProgramRunTest` runs as `rk2_runtime`. Every claim here is about row level
    security and about grants, and neither is in force on a connection that owns
    the tables. This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.configurations = {}
        cls.identifiers = {}
        for name in ("a", "b"):
            slug = f"{STATE_SLUG}-{name}"
            path = write(VALID.replace('name = "acme-web"', f'name = "{slug}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]
        cls._populate()
        # Before any read in this class has run, so that a read which changed
        # something once and then never again is still caught: every later test
        # reads, and criterion 6 is measured against this.
        cls.populated = snapshot(cls.connection)

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{STATE_SLUG}-%",)
            )
        super().tearDownClass()

    @classmethod
    def _populate(cls) -> None:
        """One technology in each Program, and everything else in the first.

        The technology rows are what collide: each Program's own counter hands
        out `TEC1`, so both hold that label and the descriptor is the only thing
        that differs. What only the first Program has -- hypotheses, an identity,
        a Lease -- is what makes an absence testable from the second.
        """
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            for name in ("a", "b"):
                cls.connection.execute(
                    "INSERT INTO entities (program_id, type, dedup_key)"
                    " VALUES ($1::uuid, 'technology', $2)",
                    (cls.identifiers[name], f"tech:{STATE_SLUG}-{name}"),
                )
            first = cls.identifiers["a"]
            subject = cls.connection.execute(
                "SELECT id FROM entities WHERE program_id = $1::uuid AND type = 'technology'",
                (first,),
            ).scalar()
            for number in (1, 2, 3):
                # A different property class each time: the dedup index is over
                # the subject and the property, so three hypotheses about one
                # entity are three properties of it or they are one row.
                cls.connection.execute(
                    "INSERT INTO hypotheses"
                    " (program_id, subject_entity_id, property_class, statement)"
                    " VALUES ($1::uuid, $2,"
                    f" (SELECT id FROM property_classes ORDER BY id OFFSET {number - 1} LIMIT 1),"
                    " $3)",
                    (first, subject, f"a self test, number {number}"),
                )
            identity = cls.connection.execute(
                "INSERT INTO entities (program_id, type, dedup_key)"
                " VALUES ($1::uuid, 'identity', 'identity:selftest-state') RETURNING id",
                (first,),
            ).scalar()
            cls.connection.execute(
                "INSERT INTO identities (entity_id, slot_name, class)"
                " VALUES ($1, 'slot://selftest-state/member', 'anonymous')",
                (identity,),
            )
            # The orchestrator, because it is the one role that holds no task:
            # `executes_tasks` is generated from `task_id` and has to agree with
            # the roster, so any other role here would need a task under it.
            holder = cls.connection.execute(
                "INSERT INTO agent_runs"
                " (program_id, role, runs_as, model, effort, mission_packet)"
                " VALUES ($1::uuid, 'orchestrator', 'session', 'selftest', 'low', '{}'::jsonb)"
                " RETURNING id",
                (first,),
            ).scalar()
            cls.connection.execute(
                "INSERT INTO identity_leases"
                " (program_id, identity_entity_id, holder_agent_run_id, expires_at)"
                " VALUES ($1::uuid, $2, $3, now() + interval '1 hour')",
                (first, identity, holder),
            )

    def read(self, name: str, **options: object) -> Report:
        return state.read(
            self.harness.runtime,
            self.harness.state,
            self.configurations[name],
            **options,
        )

    def labels(self, result: Report) -> dict[str, str]:
        return {item["label"]: item["kind"] for item in result.facts["state"]["records"]}

    def test_two_programs_hold_the_same_label_and_neither_resolves_the_other(self):
        # Criterion 1. Both reads return `TEC1`; the descriptor says they are
        # different rows, and neither read returns the other's.
        first = self.read("a", label="TEC1")
        second = self.read("b", label="TEC1")

        self.assertTrue(first.ok, first.violations)
        self.assertTrue(second.ok, second.violations)
        self.assertIn("TEC1", self.labels(first))
        self.assertIn("TEC1", self.labels(second))
        self.assertEqual(
            [f"tech:{STATE_SLUG}-a", f"tech:{STATE_SLUG}-b"],
            [result.facts["record"]["document"]["descriptor"] for result in (first, second)],
        )
        self.assertNotEqual(
            first.facts["record"]["digest"], second.facts["record"]["digest"]
        )
        # The second Program holds one record of one kind, and the first holds
        # everything else this case wrote. Neither count includes the other.
        self.assertEqual(
            [("entity", 1)],
            [
                (item["kind"], item["count"])
                for item in second.facts["state"]["kinds"]
                if item["count"]
            ],
        )

    def test_the_identifier_crosses_once_into_the_session_and_never_into_a_read(self):
        # Criterion 2, over the wire rather than in a signature. Every statement
        # the read sends is recorded: the Program's identifier is a parameter of
        # exactly one of them, the one that binds the session, and none of the
        # three read statements so much as names a Program.
        sent: list[tuple[str, tuple]] = []
        execute = pg.Connection.execute

        def record(connection, sql, parameters=()):
            sent.append((sql, parameters))
            return execute(connection, sql, parameters)

        with mock.patch.object(pg.Connection, "execute", record):
            result = self.read("a", label="H1")

        self.assertTrue(result.ok, result.violations)
        identifier = self.identifiers["a"]
        self.assertEqual(
            ["SELECT set_config('rk2.program_id', $1, true)"],
            [
                sql
                for sql, parameters in sent
                if identifier in [str(value) for value in parameters]
            ],
        )
        reads = (state.COMPACT, state.COUNTS, state.RECORD)
        self.assertEqual(list(reads), [sql for sql, _ in sent if sql in reads])
        for sql in reads:
            with self.subTest(sql[:30]):
                self.assertNotIn("program", sql.lower())

    def test_a_compact_read_carries_labels_revisions_digests_and_what_it_omitted(self):
        # Criterion 3. One record per kind, against three hypotheses: the read
        # is smaller than the Program, and says by how much.
        result = self.read("a", per_kind=1)

        self.assertTrue(result.ok, result.violations)
        compact = result.facts["state"]
        kinds = {item["kind"]: item for item in compact["kinds"]}
        self.assertEqual(
            {"count": 3, "returned": 1, "omitted": 2, "kind": "hypothesis"},
            kinds["hypothesis"],
        )
        self.assertEqual(list(state.KINDS), [item["kind"] for item in compact["kinds"]])
        for record in compact["records"]:
            with self.subTest(record["label"]):
                self.assertGreaterEqual(record["revision"], 1)
                self.assertEqual(64, len(record["digest"]))
        self.assertEqual(
            compact["bytes"],
            len(json.dumps(compact["records"], separators=(",", ":")).encode("utf-8")),
        )

    def test_a_byte_ceiling_is_honoured_by_the_read_the_command_returns(self):
        # The other half of criterion 3: the limit an operator passes is the
        # limit the report is under, whatever the Program holds.
        result = self.read("a", byte_limit=200)

        self.assertTrue(result.ok, result.violations)
        self.assertLessEqual(result.facts["state"]["bytes"], 200)
        self.assertLess(
            len(result.facts["state"]["records"]),
            sum(item["count"] for item in result.facts["state"]["kinds"]),
        )

    def test_a_label_the_compact_read_exposed_retrieves_the_whole_record(self):
        # Criterion 4: what a compact read names is what a full read resolves,
        # so a model working from labels never has to guess an identifier. Every
        # hypothesis, not one, because resolving the first is also what a read
        # that ignored the label would do.
        compact = self.read("a")
        labels = [
            item["label"]
            for item in compact.facts["state"]["records"]
            if item["kind"] == "hypothesis"
        ]

        self.assertEqual(["H3", "H2", "H1"], labels, "newest revision first")
        for label in labels:
            with self.subTest(label):
                result = self.read("a", label=label)

                self.assertTrue(result.ok, result.violations)
                record = result.facts["record"]
                self.assertTrue(record["present"])
                self.assertEqual("hypothesis", record["kind"])
                self.assertEqual(label, record["document"]["label"])
                self.assertEqual(
                    f"a self test, number {label.removeprefix('H')}",
                    record["document"]["statement"],
                )
                self.assertEqual(
                    [
                        item["digest"]
                        for item in compact.facts["state"]["records"]
                        if item["label"] == label
                    ],
                    [record["digest"]],
                )

    def test_an_unknown_label_and_another_programs_label_are_the_same_answer(self):
        # Criterion 5. `H1` exists and belongs to the first Program; `H404`
        # belongs to nobody. From the second Program the two reports differ only
        # where the label itself appears, so nothing in either says which case
        # it was -- and the exit code says nothing either.
        foreign = self.read("b", label="H1")
        unknown = self.read("b", label="H404")

        self.assertEqual(EXIT_OK, foreign.exit_code)
        self.assertEqual(EXIT_OK, unknown.exit_code)
        self.assertEqual({"label": "H1", "present": False}, foreign.facts["record"])
        self.assertEqual({"label": "H404", "present": False}, unknown.facts["record"])
        self.assertEqual(
            json.dumps(foreign.as_dict()).replace("H1", "L"),
            json.dumps(unknown.as_dict()).replace("H404", "L"),
        )

    def test_the_program_registry_is_not_reachable_from_the_agent_connection(self):
        # What makes the answer above indistinguishable rather than merely
        # identical: from this connection there is no second question to ask.
        # The log is the third one, because a row of it names the Program the
        # change belonged to.
        with pg.connect(self.harness.state) as session:
            for sql in (
                "SELECT count(*) FROM programs",
                "SELECT slug FROM programs LIMIT 1",
                "SELECT program_id FROM events LIMIT 1",
            ):
                with self.subTest(sql):
                    with self.assertRaises(pg.DatabaseError) as refused:
                        session.execute(sql)
                    self.assertEqual("42501", refused.exception.sqlstate)

    def test_the_only_program_identifier_this_connection_can_reach_is_its_own(self):
        # `entities.program_id` is on the read surface and stays there: row level
        # security scopes the rows, so the identifier it yields is the one the
        # session is already bound to and could read back out of the setting.
        # What no query here yields is a *second* identifier -- which is what
        # rebinding this session to another Program would take. The boundary is
        # that nothing reachable from this side names another Program; which
        # process holds the session is ticket 19's question, not this role's.
        with pg.connect(self.harness.state) as session:
            session.execute(
                "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers["a"],)
            )
            reachable = {
                str(row[0])
                for row in session.execute("SELECT DISTINCT program_id FROM entities").rows
            }

        self.assertEqual({self.identifiers["a"]}, reachable)
        self.assertNotIn(self.identifiers["b"], reachable)

    def test_a_column_of_the_registry_is_refused_like_the_whole_table(self):
        # The read asserts its own premise before it reads, and asserts it at
        # column granularity: `has_table_privilege` answers "no" for a role
        # holding `SELECT (slug)`, and one readable column is the whole of what
        # indistinguishable absence has to rule out. Committed, because the
        # premise is checked on a connection this transaction does not own.
        with pg.connect(self.harness.migrate) as owner:
            self._as_owner(owner, "GRANT SELECT (slug) ON programs TO rk2_state")
            try:
                result = self.read("a")

                self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
                self.assertIn("Program registry", result.violations[0].detail)
                self.assertIsNone(result.facts["state"])
            finally:
                self._as_owner(owner, "REVOKE SELECT (slug) ON programs FROM rk2_state")

    @staticmethod
    def _as_owner(connection: pg.Connection, sql: str) -> None:
        with connection.transaction():
            connection.execute("SET LOCAL ROLE rk2_owner")
            connection.execute(sql)

    def test_the_agent_connection_cannot_write_what_it_can_read(self):
        # Criterion 6, before the reads: a repeated read cannot change the
        # database because this connection cannot change it at all.
        with pg.connect(self.harness.state) as session:
            session.execute(
                "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers["a"],)
            )
            for sql in (
                "INSERT INTO entities (program_id, type, dedup_key)"
                " VALUES ($1::uuid, 'technology', 'tech:intruder')",
                "DELETE FROM events",
            ):
                with self.subTest(sql[:20]):
                    with self.assertRaises(pg.DatabaseError) as refused:
                        session.execute(sql, (self.identifiers["a"],) if "$1" in sql else ())
                    self.assertEqual("42501", refused.exception.sqlstate)

    def test_repeating_every_read_leaves_the_database_and_the_leases_alone(self):
        # Criterion 6. The Lease is the one piece of runtime state a read could
        # plausibly touch by being observed -- a scheduler that renewed one on
        # access would move it -- so it is measured by name rather than only as
        # part of the database size, which is page-granular and would not notice
        # a single row.
        before = snapshot(self.connection)

        for name in ("a", "b"):
            self.read(name)
            self.read(name, label="TEC1")
            self.read(name, label="H404", per_kind=1, byte_limit=200)
        after = snapshot(self.connection)

        self.assertEqual(before, after)
        # And against the state as it was written, before any read in this class
        # had run: a read that moved something once would pass the comparison
        # above and fail this one.
        self.assertEqual(self.populated[ROWS], after[ROWS])
        # Anchored, so that a snapshot which had stopped seeing rows would fail
        # here rather than pass as two equal descriptions of nothing.
        self.assertEqual(1, before[3], "the Lease this case wrote")
        self.assertGreater(before[1], 0, "the log every revision is read from")
        self.assertNotIn("", before[4:], "a digest over rows that are there")

    def test_the_same_read_twice_returns_the_same_bytes(self):
        # A digest that moved without the row moving would make every revision
        # and every comparison a model makes from one meaningless.
        first = self.read("a", label="TEC1")
        second = self.read("a", label="TEC1")

        self.assertEqual(first.facts["state"], second.facts["state"])
        self.assertEqual(first.facts["record"], second.facts["record"])

    def test_a_connection_that_is_not_the_agents_is_refused_rather_than_read(self):
        # The whole report describes an isolation that only holds for one role.
        # Read through the runtime it would look identical and mean nothing.
        result = state.read(
            self.harness.runtime, self.harness.runtime, self.configurations["a"]
        )

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertIn("rk2_state", result.violations[0].detail)

    def test_a_configuration_naming_no_program_is_refused_before_the_agent_connects(self):
        path = write(VALID.replace('name = "acme-web"', f'name = "{STATE_SLUG}-absent"'))

        result = state.read(self.harness.runtime, self.harness.state, path)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertIsNone(result.facts["program_id"])
        self.assertIsNone(result.facts["state"])

    def test_the_gate_still_holds_over_the_rows_these_reads_were_made_from(self):
        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected)

        self.assertTrue(result.ok, result.violations)


ARTIFACT_SLUG = "selftest-artifact"

#: The bytes both Programs store. Long enough that a bounded range leaves
#: something out at both ends, and numbered so a range that came back shifted
#: would not match the slice it is compared against.
PLAINTEXT = b"".join(f"artifact line {number}\n".encode() for number in range(32))

#: The bytes only the first Program ever stores, which is what makes an absence
#: testable from the second: there is something there to be denied.
PRIVATE = b"only the first Program ever stored these bytes\n"


class ArtifactStoreTest(DatabaseCase):
    """PH2-06: one artifact, two Programs, and the reference that separates them.

    The store deduplicates by content hash and the reference does not, so the
    interesting case is the one where both Programs put the *same* file: one row
    of bytes, two claims on it, and a label each. Everything here runs through
    the roles an operator actually points at the database -- writes as
    `rk2_runtime`, reads as `rk2_state` -- because a claim about isolation made
    from a connection that owns the tables is a claim about nothing.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = scratch() / "artifacts"
        cls.configurations = {}
        cls.identifiers = {}
        for name in ("a", "b"):
            slug = f"{ARTIFACT_SLUG}-{name}"
            path = write(VALID.replace('name = "acme-web"', f'name = "{slug}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]

        cls.shared = scratch() / "shared.txt"
        cls.shared.write_bytes(PLAINTEXT)
        cls.private = scratch() / "private.txt"
        cls.private.write_bytes(PRIVATE)

        # The order matters for exactly one assertion below: the first put is
        # the one that writes bytes, and the second is the one that finds them
        # already there under the same name.
        cls.stored = {
            "a": cls.store("a", cls.shared, content_type="text/plain"),
            "b": cls.store("b", cls.shared, content_type="text/plain"),
        }
        cls.stored["private"] = cls.store("a", cls.private, kind="tool_output")
        for name, result in cls.stored.items():
            assert result.ok, (name, result.violations)

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{ARTIFACT_SLUG}-%",)
            )
            cls.connection.execute(
                "DELETE FROM artifacts WHERE sha256 = ANY($1)",
                ("{" + ",".join(cls.hashes()) + "}",),
            )
        super().tearDownClass()

    @classmethod
    def hashes(cls) -> tuple[str, ...]:
        return (artifact.digest(PLAINTEXT), artifact.digest(PRIVATE))

    @classmethod
    def store(cls, name: str, source: Path, **options: object) -> Report:
        return artifact.put(
            cls.harness.runtime, cls.configurations[name], source, root=cls.root, **options
        )

    def read(self, name: str, **options: object) -> Report:
        return artifact.get(
            self.harness.runtime,
            self.harness.state,
            self.configurations[name],
            root=self.root,
            **options,
        )

    def bound(self, name: str) -> pg.Connection:
        """An agent session bound to one Program, as `rk artifact get` binds it."""
        session = pg.connect(self.harness.state)
        session.execute(
            "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers[name],)
        )
        return session

    def test_identical_plaintext_is_one_artifact_and_a_reference_each(self):
        # Criterion 1. The second put finds the bytes already filed under their
        # hash and does not write them again; it still makes a reference, and
        # the two Programs both call theirs `AF1` because labels are per Program.
        sha256 = artifact.digest(PLAINTEXT)
        first, second = self.stored["a"].facts["artifact"], self.stored["b"].facts["artifact"]

        self.assertEqual(sha256, first["sha256"])
        self.assertEqual(sha256, second["sha256"])
        self.assertEqual([True, False], [first["stored"], second["stored"]])
        self.assertEqual([True, True], [first["referenced"], second["referenced"]])
        self.assertEqual(["AF1", "AF1"], [first["label"], second["label"]])

        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT count(*) FROM artifacts WHERE sha256 = $1", (sha256,)
            ).scalar(),
        )
        self.assertEqual(
            sorted([self.identifiers["a"], self.identifiers["b"]]),
            sorted(
                str(row[0])
                for row in self.connection.execute(
                    "SELECT program_id FROM artifact_references WHERE sha256 = $1", (sha256,)
                ).rows
            ),
        )
        self.assertEqual(1, len(list(self.root.rglob(sha256))), "one file, under one name")

    def test_storing_the_same_bytes_again_adds_neither_a_row_nor_a_file(self):
        # The other half of criterion 1: within one Program the reference is the
        # claim, and a claim made twice is one claim. The report says so rather
        # than reporting a second label nobody else would ever see again.
        again = self.store("a", self.shared, content_type="text/plain")

        self.assertTrue(again.ok, again.violations)
        self.assertEqual("AF1", again.facts["artifact"]["label"])
        self.assertEqual(False, again.facts["artifact"]["stored"])
        self.assertEqual(False, again.facts["artifact"]["referenced"])
        self.assertEqual(
            2,
            self.connection.execute(
                "SELECT count(*) FROM artifact_references WHERE program_id = $1::uuid",
                (self.identifiers["a"],),
            ).scalar(),
        )

    def test_the_recorded_identifier_is_the_hash_of_the_bytes_on_disk(self):
        # Criterion 2, at the only place the two can disagree: the name the
        # database recorded, and what the file filed under it hashes to now.
        for label, plaintext in (("AF1", PLAINTEXT), ("AF2", PRIVATE)):
            with self.subTest(label):
                recorded = self.connection.execute(
                    "SELECT sha256 FROM artifact_references"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (self.identifiers["a"], label),
                ).scalar()
                path = artifact.path_for(self.root, str(recorded))

                self.assertEqual(artifact.digest(plaintext), str(recorded))
                self.assertEqual(plaintext, path.read_bytes())
                self.assertEqual(str(recorded), artifact.digest(path.read_bytes()))

    def test_the_audit_holds_every_recorded_hash_against_its_bytes(self):
        # And the verb that says so for the whole Program at once, which is the
        # only thing that can: no SQL statement reaches the filesystem.
        result = artifact.audit(self.harness.runtime, self.configurations["a"], root=self.root)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(
            {"sound": True, "verified": 2, "broken": [], "root": str(self.root)},
            result.facts["integrity"],
        )
        self.assertEqual(
            [("AF1", "runtime"), ("AF2", "tool_output")],
            [(item["label"], item["kind"]) for item in result.facts["holdings"]],
        )

    def test_a_bounded_read_returns_one_range_and_names_what_it_left_out(self):
        # Criterion 3. The range is the range that was asked for, and the report
        # accounts for every byte of the artifact that is not in it.
        result = self.read("a", label="AF1", offset=10, limit=20)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(
            {
                "size": len(PLAINTEXT),
                "offset": 10,
                "returned": 20,
                "omitted_before": 10,
                "omitted_after": len(PLAINTEXT) - 30,
                "complete": False,
            },
            result.facts["window"],
        )
        self.assertEqual(
            PLAINTEXT[10:30], base64.b64decode(result.facts["content"]["data"])
        )
        self.assertEqual(len(PLAINTEXT), result.facts["artifact"]["byte_size"])
        self.assertEqual("text/plain", result.facts["artifact"]["content_type"])

    def test_a_read_that_asks_for_everything_says_it_got_everything(self):
        result = self.read("a", label="AF2")

        self.assertTrue(result.ok, result.violations)
        self.assertTrue(result.facts["window"]["complete"])
        self.assertEqual(0, result.facts["window"]["omitted_after"])
        self.assertEqual(PRIVATE, base64.b64decode(result.facts["content"]["data"]))

    def test_a_range_beyond_the_end_is_empty_rather_than_an_error(self):
        result = self.read("a", label="AF2", offset=len(PRIVATE) + 100)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(0, result.facts["window"]["returned"])
        self.assertEqual(b"", base64.b64decode(result.facts["content"]["data"]))

    def test_another_programs_label_and_a_label_nobody_holds_are_one_answer(self):
        # Criterion 4. `AF2` exists and belongs to the first Program; `AF404`
        # belongs to nobody. From the second Program the two reports differ only
        # where the label itself appears, and neither exit code says which case
        # it was.
        foreign = self.read("b", label="AF2")
        unknown = self.read("b", label="AF404")

        self.assertEqual(EXIT_OK, foreign.exit_code)
        self.assertEqual(EXIT_OK, unknown.exit_code)
        self.assertEqual({"label": "AF2", "present": False}, foreign.facts["artifact"])
        self.assertEqual({"label": "AF404", "present": False}, unknown.facts["artifact"])
        self.assertEqual(
            json.dumps(foreign.as_dict()).replace("AF2", "L"),
            json.dumps(unknown.as_dict()).replace("AF404", "L"),
        )

    def test_a_bare_hash_from_another_program_reveals_neither_bytes_nor_existence(self):
        # The heart of criterion 4, and the reason deduplication is safe: the
        # hash is the whole address of the bytes, so a Program that guessed one
        # would hold the store open if reachability were not a row of its own.
        # Asked from the Program that does hold it, the same three queries
        # answer -- otherwise this would pass over a surface that answers
        # nothing to anybody.
        sha256 = artifact.digest(PRIVATE)
        counts = {}
        for name in ("a", "b"):
            with self.bound(name) as session:
                counts[name] = [
                    session.execute(sql, (sha256,)).scalar()
                    for sql in (
                        "SELECT count(*) FROM artifacts WHERE sha256 = $1",
                        "SELECT count(*) FROM artifact_references WHERE sha256 = $1",
                        "SELECT count(*) FROM v_artifacts WHERE sha256 = $1",
                    )
                ]

        self.assertEqual([1, 1, 1], counts["a"])
        self.assertEqual([0, 0, 0], counts["b"])

    def test_the_shared_artifact_is_one_row_to_each_program_and_not_two(self):
        # Deduplicated bytes, un-deduplicated claims: from either session the
        # store holds exactly what that Program put in it, and the row both
        # Programs refer to is not doubled by the other's reference.
        for name in ("a", "b"):
            with self.subTest(name), self.bound(name) as session:
                labels = [
                    str(row[0])
                    for row in session.execute("SELECT label FROM v_artifacts ORDER BY label").rows
                ]

                self.assertEqual({"a": ["AF1", "AF2"], "b": ["AF1"]}[name], labels)

    def test_coming_to_hold_an_artifact_is_audited_and_the_bytes_are_not(self):
        # Criterion 5. One event per reference, carrying the label, the hash and
        # the kind -- identifiers and a digest, which is what §6 lets into the
        # log -- and no fragment of what the artifact says.
        rows = self.connection.execute(
            "SELECT type, payload::text FROM events"
            " WHERE program_id = $1::uuid AND subject_table = 'artifact_references'"
            " ORDER BY seq",
            (self.identifiers["a"],),
        ).rows

        self.assertEqual(["artifact.referenced", "artifact.referenced"], [str(r[0]) for r in rows])
        payloads = [json.loads(str(row[1]))["after"] for row in rows]
        self.assertEqual(["AF1", "AF2"], [item["label"] for item in payloads])
        self.assertEqual([artifact.digest(PLAINTEXT), artifact.digest(PRIVATE)],
                         [item["sha256"] for item in payloads])
        self.assertEqual(["runtime", "tool_output"], [item["kind"] for item in payloads])
        written = json.dumps(payloads)
        for fragment in ("artifact line 3", "only the first Program", "b64", "data"):
            with self.subTest(fragment):
                self.assertNotIn(fragment, written)

    def test_the_content_addressed_store_is_not_an_event_and_says_why(self):
        # The other half of criterion 5. `artifacts` is program-global, so an
        # event about a row of it has no Program to belong to; the exemption is
        # recorded with that reason rather than left as an open question.
        exemption = self.connection.execute(
            "SELECT exempt_kind, owner_ticket, reason FROM event_table_exempt"
            " WHERE table_name = 'artifacts'"
        ).rows[0]

        self.assertEqual(("bookkeeping", "ph2-06"), (str(exemption[0]), str(exemption[1])))
        self.assertIn("without the bytes", str(exemption[2]))

    def test_bytes_missing_from_the_store_fail_closed_on_read_and_on_audit(self):
        # Criterion 6. The database still records the hash, so the artifact is
        # not "gone" from anything that reads SQL alone -- which is exactly why
        # the failure has to be loud on the one path that touches the bytes.
        path = artifact.path_for(self.root, artifact.digest(PRIVATE))
        kept = path.read_bytes()
        path.unlink()
        try:
            read = self.read("a", label="AF2")
            checked = artifact.audit(
                self.harness.runtime, self.configurations["a"], root=self.root
            )
        finally:
            path.write_bytes(kept)

        self.assertEqual(EXIT_INTEGRITY_FAILED, read.exit_code)
        self.assertFalse(read.facts["integrity"]["sound"])
        self.assertIsNone(read.facts["content"], "no partial answer")
        self.assertIn("not in the store", read.facts["integrity"]["broken"][0]["detail"])
        self.assertEqual(EXIT_INTEGRITY_FAILED, checked.exit_code)
        self.assertEqual(1, checked.facts["integrity"]["verified"], "the one that is still there")

    def test_bytes_that_do_not_hash_to_their_name_fail_closed(self):
        # The other corruption: a file is there, is the right length, and is not
        # what it is filed as. A read that returned the range asked for would be
        # returning evidence under a digest that no longer describes it.
        path = artifact.path_for(self.root, artifact.digest(PRIVATE))
        kept = path.read_bytes()
        path.write_bytes(b"x" * len(kept))
        try:
            read = self.read("a", label="AF2", offset=0, limit=4)
        finally:
            path.write_bytes(kept)

        self.assertEqual(EXIT_INTEGRITY_FAILED, read.exit_code)
        self.assertIsNone(read.facts["content"])
        self.assertIn("hashes to", read.facts["integrity"]["broken"][0]["detail"])

    def test_a_connection_that_is_not_the_agents_is_refused_rather_than_read(self):
        result = artifact.get(
            self.harness.runtime,
            self.harness.runtime,
            self.configurations["a"],
            root=self.root,
            label="AF1",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertIn("rk2_state", result.violations[0].detail)

    def test_a_write_through_the_agent_connection_is_refused(self):
        # Reachability is a row, so a session that could write one could grant
        # itself the store. It cannot: the reference table is on the read
        # surface by column, and the surface is read-only.
        with self.bound("b") as session:
            with self.assertRaises(pg.DatabaseError) as refused:
                session.execute(
                    "INSERT INTO artifact_references (program_id, sha256, kind)"
                    " VALUES ($1::uuid, $2, 'runtime')",
                    (self.identifiers["b"], artifact.digest(PRIVATE)),
                )

        self.assertEqual("42501", refused.exception.sqlstate)

    def test_the_gate_still_holds_over_the_rows_these_writes_made(self):
        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected)

        self.assertTrue(result.ok, result.violations)

    def test_the_gate_holds_the_recorded_hashes_against_the_store_when_given_one(self):
        # The rest of criterion 6. `rk artifact audit` is one Program's answer
        # and nothing calls it; the gate is what every command ends by running,
        # so this is the path on which a corrupt store makes the checks that
        # trust these hashes unsound rather than merely unasked.
        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected, store=self.root)

        self.assertTrue(result.ok, result.violations)
        artifacts = result.facts["artifacts"]
        self.assertTrue(artifacts["sound"])
        self.assertEqual(str(self.root), artifacts["root"])
        self.assertGreaterEqual(artifacts["verified"], 3, "both labels of a, and b's")
        self.assertEqual([], artifacts["broken"])

    def test_a_store_the_gate_cannot_verify_fails_the_gate(self):
        # And the negative control for it: the database is untouched and every
        # registered check still passes, so a gate that never opened a file
        # would report this database as holding.
        path = artifact.path_for(self.root, artifact.digest(PRIVATE))
        kept = path.read_bytes()
        path.write_bytes(b"x" * len(kept))
        try:
            with pg.connect(self.harness.migrate) as connection:
                blind = integrity.verify(connection, self.harness.expected)
                seeing = integrity.verify(connection, self.harness.expected, store=self.root)
        finally:
            path.write_bytes(kept)

        self.assertTrue(blind.ok, "no registered check can open a file")
        self.assertEqual(EXIT_INTEGRITY_FAILED, seeing.exit_code)
        self.assertEqual(
            ["artifact_store"], [item.source for item in seeing.violations]
        )
        self.assertIn("hashes to", seeing.violations[0].detail)
        self.assertEqual(blind.facts["checks"], seeing.facts["checks"], "not a registered check")


SEAL_SLUG = "selftest-sealed"

#: A credential that never existed, so that finding it anywhere is unambiguous.
#: Distinctive enough that no column, index or serialisation could hold it by
#: coincidence, and synthetic so that the search itself is safe to run.
MARKER = "rk2-selftest-credential-8f3a1c7d"

#: The exchange, in the two views the two parties saw. Byte-for-byte identical
#: apart from the one header, which is the case that matters: a redaction that
#: rewrote more than the credential would make the pair prove less than it says.
WIRE = (
    "GET /admin/export HTTP/1.1\r\n"
    "Host: target.example\r\n"
    f"Authorization: Bearer {MARKER}\r\n"
    "Accept: application/json\r\n"
    "\r\n"
).encode()
REDACTED = (
    "GET /admin/export HTTP/1.1\r\n"
    "Host: target.example\r\n"
    "Authorization: Bearer [redacted]\r\n"
    "Accept: application/json\r\n"
    "\r\n"
).encode()

#: The root secret for this run, and one that is not it. Fixed rather than
#: random so a failure is reproducible; never written anywhere but the key file.
SECRET = bytes(range(32, 64))
OTHER_SECRET = bytes(range(64, 96))


class SealedWireArtifactTest(DatabaseCase):
    """PH2-07: the wire view kept whole, kept encrypted, and kept out of reach.

    One exchange, stored twice: the redacted view as an ordinary agent-visible
    artifact with a label, and the wire view sealed under a key derived from a
    file this process holds and the database does not. Everything runs through
    the roles an operator points at the database, because the claim being made
    is about what each connection can reach.

    The absence in criterion 3 is asked of the database directly, through
    `find_in_database`, rather than by grepping an archive: `rk db dump` writes
    a compressed custom-format file, so a grep over one would pass whether the
    marker were in it or not. A value in no column of any table is a value in no
    serialisation of them, and this asks that question about every column there
    is.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = scratch() / "sealed"
        cls.key = cls.keyfile("root.key", SECRET)
        cls.wrong = cls.keyfile("other.key", OTHER_SECRET)

        cls.configurations = {}
        cls.identifiers = {}
        for name in ("a", "b"):
            slug = f"{SEAL_SLUG}-{name}"
            path = write(VALID.replace('name = "acme-web"', f'name = "{slug}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]

        cls.wire = scratch() / "exchange.wire"
        cls.wire.write_bytes(WIRE)
        cls.redacted = scratch() / "exchange.redacted"
        cls.redacted.write_bytes(REDACTED)

        cls.sealed = cls.sealing("a", content_type="message/http")
        assert cls.sealed.ok, cls.sealed.violations
        cls.ciphertext = cls.sealed.facts["seals"][0]["ciphertext_sha256"]

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{SEAL_SLUG}-%",)
            )
            cls.connection.execute(
                "DELETE FROM artifact_seal WHERE sha256 = $1", (artifact.digest(WIRE),)
            )
            cls.connection.execute(
                "DELETE FROM artifacts WHERE sha256 = ANY($1)",
                ("{" + ",".join((artifact.digest(WIRE), artifact.digest(REDACTED))) + "}",),
            )
            cls.connection.execute("DELETE FROM secret_access_log")
            cls.connection.execute("DELETE FROM secret_kek")
        super().tearDownClass()

    @classmethod
    def keyfile(cls, name: str, secret: bytes) -> Path:
        """Key material as `seal.load_root` insists on holding it: a file, owner-only."""
        path = scratch() / name
        path.write_bytes(secret)
        path.chmod(0o600)
        return path

    @classmethod
    def sealing(cls, name: str, **options: object) -> Report:
        return artifact.seal_wire(
            cls.harness.runtime,
            cls.configurations[name],
            cls.wire,
            cls.redacted,
            root=cls.root,
            key=cls.key,
            **options,
        )

    def opening(self, name: str, into: str, **options: object) -> tuple[Report, Path]:
        target = scratch() / into
        return (
            artifact.open_wire(
                self.harness.runtime,
                self.configurations[name],
                root=self.root,
                key=self.key,
                into=target,
                **options,
            ),
            target,
        )

    def trail(self, **columns: object) -> list[tuple]:
        """The audit rows matching an exact set of column values, oldest first."""
        where = " AND ".join(f"{name} = ${number}" for number, name in enumerate(columns, 1))
        return [
            (str(row[0]), str(row[1]), row[2], row[3], str(row[4]))
            for row in self.connection.execute(
                "SELECT verb, outcome, value_len, encode(value_fpr, 'hex'), detail"
                "  FROM secret_access_log"
                f" WHERE {where} ORDER BY at, id",
                tuple(columns.values()),
            ).rows
        ]

    def bound(self, name: str) -> pg.Connection:
        """An agent session bound to one Program, as `rk artifact get` binds it."""
        session = pg.connect(self.harness.state)
        session.execute(
            "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers[name],)
        )
        return session

    def stored(self) -> set[Path]:
        """Every file the store holds, so a refusal can be held against it."""
        return {path for path in self.root.rglob("*") if path.is_file()}

    def test_the_store_holds_a_ciphertext_and_never_the_wire_plaintext(self):
        # Criterion 1. The wire artifact has an identifier in the database and no
        # file under it: what is on disk is the envelope, filed under its own
        # hash, which is what lets the gate check it while holding no key.
        wire_sha = artifact.digest(WIRE)
        envelope = artifact.path_for(self.root, self.ciphertext)

        self.assertFalse(artifact.path_for(self.root, wire_sha).exists())
        self.assertTrue(envelope.exists())
        self.assertEqual(self.ciphertext, artifact.digest(envelope.read_bytes()))
        self.assertNotIn(MARKER.encode(), envelope.read_bytes())
        self.assertEqual(REDACTED, artifact.path_for(self.root, artifact.digest(REDACTED)).read_bytes())

    def test_the_database_holds_a_salt_and_a_check_and_no_key(self):
        # The other half of criterion 1. Keys are derived from the file, every
        # time, so there is nothing wrapped to steal: the two values beside the
        # generation are a random salt and 16 bytes of an HMAC output, and
        # neither is the secret they were derived with.
        row = self.connection.execute(
            "SELECT encode(salt, 'hex'), encode(root_check, 'hex') FROM secret_kek WHERE gen = 1"
        ).rows[0]
        salt, check = (bytes.fromhex(str(value)) for value in row)

        self.assertEqual((32, 16), (len(salt), len(check)))
        self.assertNotIn(salt, SECRET)
        self.assertNotIn(check, SECRET)
        self.assertEqual(0, self.connection.execute("SELECT count(*) FROM secret_dek").scalar())

    def test_the_key_is_named_by_the_operator_and_not_by_the_configuration(self):
        # And the rest of it: "outside Agent-visible configuration" means the
        # file the model can read does not say where the key is, let alone what
        # it is. The key reaches the command through its own argument.
        configuration = self.configurations["a"].read_text()

        self.assertNotIn(str(self.key), configuration)
        self.assertNotIn(artifact.KEY_VARIABLE, configuration)
        self.assertNotIn("key", configuration.lower())

    def test_the_seal_records_the_algorithm_the_nonce_and_the_plaintext_hash(self):
        # Criterion 2, read back from the row rather than from the report that
        # wrote it. Every field needed to open the envelope is here except the
        # one that must not be: the key.
        row = self.connection.execute(
            "SELECT alg, octet_length(nonce), encode(nonce, 'hex'), kek_gen,"
            "       ciphertext_sha256, agent_sha256, byte_size, visibility"
            "  FROM artifact_seal WHERE sha256 = $1",
            (artifact.digest(WIRE),),
        ).rows[0]
        alg, nonce_size, nonce, generation, ciphertext, agent, byte_size, visibility = row

        self.assertEqual(seal.ALG, str(alg))
        self.assertEqual(seal.NONCE_BYTES, int(nonce_size))
        self.assertEqual(1, int(generation))
        self.assertEqual(self.ciphertext, str(ciphertext))
        self.assertEqual(artifact.digest(REDACTED), str(agent))
        self.assertEqual(len(WIRE), int(byte_size))
        self.assertEqual("credential_bearing", str(visibility))
        self.assertEqual(
            seal.Sealed.decode(artifact.path_for(self.root, self.ciphertext).read_bytes()).nonce.hex(),
            str(nonce),
            "the recorded nonce is the one the envelope carries",
        )

    def test_the_wire_artifact_row_says_credential_bearing_and_encrypted(self):
        # The wire view is an artifact like any other, and the two columns that
        # make it unlike any other are stated rather than defaulted.
        row = self.connection.execute(
            "SELECT visibility, encrypted, byte_size, content_type FROM artifacts WHERE sha256 = $1",
            (artifact.digest(WIRE),),
        ).rows[0]

        self.assertEqual(("credential_bearing", True), (str(row[0]), bool(row[1])))
        self.assertEqual((len(WIRE), "message/http"), (int(row[2]), str(row[3])))

    def test_the_marker_is_in_no_column_of_any_table(self):
        # Criterion 3, asked of every column of every table at once -- rows,
        # Events, the audit trail and the diagnostics registry included, because
        # all of them are tables. The positive control is the point: the same
        # question about a value that *is* in the database answers, so the
        # absence is an answer rather than a query that matches nothing.
        found = self.connection.execute(
            "SELECT relation, attribute FROM find_in_database($1)", (MARKER,)
        ).rows
        control = self.connection.execute(
            "SELECT relation, attribute FROM find_in_database($1)", (f"{SEAL_SLUG}-a",)
        ).rows

        self.assertEqual([], [(str(row[0]), str(row[1])) for row in found])
        self.assertIn(("programs", "slug"), [(str(row[0]), str(row[1])) for row in control])

    def test_the_marker_is_in_no_byte_of_the_store(self):
        # The half of criterion 3 that no SQL statement can answer.
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                with self.subTest(path.name):
                    self.assertNotIn(MARKER.encode(), path.read_bytes())

    def test_the_marker_is_in_neither_the_report_nor_what_the_agent_reads(self):
        # And the two surfaces an operator and a model actually look at. The
        # agent read returns the redacted view because that is the only view it
        # has a label for.
        read = artifact.get(
            self.harness.runtime,
            self.harness.state,
            self.configurations["a"],
            root=self.root,
            label="AF1",
        )

        self.assertTrue(read.ok, read.violations)
        self.assertEqual(REDACTED, base64.b64decode(read.facts["content"]["data"]))
        for name, rendered in (
            ("seal", json.dumps(self.sealed.as_dict())),
            ("get", json.dumps(read.as_dict())),
        ):
            with self.subTest(name):
                self.assertNotIn(MARKER, rendered)
                self.assertNotIn("Bearer sk", rendered)

    def test_two_views_are_two_artifacts_and_only_one_has_a_label(self):
        # Criterion 4. Both hashes describe exactly the bytes their party saw,
        # and the wire view deliberately has no reference: a label is the name a
        # Program reads an artifact by, so giving the wire view one would undo
        # everything the seal is for.
        agent_sha, wire_sha = artifact.digest(REDACTED), artifact.digest(WIRE)
        labelled = self.connection.execute(
            "SELECT label, sha256 FROM artifact_references WHERE program_id = $1::uuid ORDER BY label",
            (self.identifiers["a"],),
        ).rows

        self.assertNotEqual(agent_sha, wire_sha)
        self.assertEqual([("AF1", agent_sha)], [(str(row[0]), str(row[1])) for row in labelled])
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT count(*) FROM artifact_references WHERE sha256 = ANY($1)",
                ("{" + ",".join((wire_sha, self.ciphertext)) + "}",),
            ).scalar(),
        )
        self.assertEqual(
            2,
            self.connection.execute(
                "SELECT count(*) FROM artifacts WHERE sha256 = ANY($1)",
                ("{" + ",".join((agent_sha, wire_sha)) + "}",),
            ).scalar(),
        )

    def test_neither_the_seal_nor_the_reference_can_be_edited_afterwards(self):
        # The immutability half of criterion 4, from the connection that wrote
        # them. A seal whose nonce could be edited would describe a ciphertext it
        # no longer opens.
        for table, statement in (
            ("artifact_seal", "UPDATE artifact_seal SET kek_gen = 1 WHERE sha256 = $1"),
            (
                "artifact_references",
                "UPDATE artifact_references SET label = 'AF9' WHERE sha256 = $1",
            ),
        ):
            with self.subTest(table), self.assertRaises(pg.DatabaseError) as refused:
                with self.connection.transaction():
                    self.connection.execute(
                        statement,
                        (artifact.digest(WIRE if table == "artifact_seal" else REDACTED),),
                    )

            self.assertIn("immutable", str(refused.exception).lower())

    def test_opening_without_authorization_is_refused_and_recorded(self):
        # Criterion 5. The refusal happens before the lookup, so it is also the
        # answer for a label that has no seal -- and it is in the trail, because
        # an audit that only records the opens cannot answer who tried.
        result, target = self.opening("a", "unauthorized.txt", label="AF1")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(["argument:--authorize"], [item.source for item in result.violations])
        self.assertFalse(target.exists())
        self.assertIsNone(result.facts["released"])
        self.assertEqual(
            [("open", "denied", None, None, "no authorization given for AF1")],
            self.trail(scope_id=self.identifiers["a"], outcome="denied", verb="open"),
        )

    def test_a_release_that_cannot_land_is_still_on_the_record(self):
        # The ordering half of criterion 5. The audit row goes down before the
        # bytes do, so the one state that cannot arise is plaintext on disk that
        # the trail does not account for; the other one can, and this is it. An
        # `--into` that already exists is refused rather than obeyed -- clobbering
        # it would destroy evidence -- and what the operator reads afterwards is
        # an open that was authorized and a release that did not land.
        target = scratch() / "occupied.wire"
        target.write_bytes(b"an earlier release nobody may overwrite")

        result = artifact.open_wire(
            self.harness.runtime,
            self.configurations["a"],
            root=self.root,
            key=self.key,
            label="AF1",
            into=target,
            authorize="checking the release path",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(["argument:--into"], [item.source for item in result.violations])
        self.assertEqual(b"an earlier release nobody may overwrite", target.read_bytes())
        self.assertIsNone(result.facts["released"])
        self.assertNotIn(MARKER, json.dumps(result.as_dict()))

        opened, refused = self.trail(scope_id=self.identifiers["a"], verb="open")[-2:]
        self.assertEqual(("ok", "error"), (opened[1], refused[1]))
        self.assertEqual(len(WIRE), int(opened[2]))
        self.assertIn("checking the release path", opened[4])
        self.assertIn("could not be written out", refused[4])

    def test_an_authorized_open_writes_the_bytes_to_a_file_and_audits_it(self):
        # The rest of criterion 5. The plaintext leaves through the file and
        # never through the report, the file is readable by nobody else, and the
        # trail carries a length and a keyed fingerprint in place of the value.
        result, target = self.opening(
            "a", "opened.wire", label="AF1", authorize="incident review 2026-08-10"
        )

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(WIRE, target.read_bytes())
        self.assertEqual(0o600, target.stat().st_mode & 0o777)
        self.assertEqual(str(target), result.facts["released"]["path"])
        self.assertEqual(artifact.digest(WIRE), result.facts["released"]["sha256"])
        self.assertNotIn(MARKER, json.dumps(result.as_dict()))

        # By the reason, because it is the operator's own words and no other
        # open in this case carries them: authorized opens accumulate in the
        # trail, which is the point of keeping one.
        recorded = [
            row
            for row in self.trail(scope_id=self.identifiers["a"], outcome="ok", verb="open")
            if "incident review 2026-08-10" in row[4]
        ]
        self.assertEqual(1, len(recorded))
        verb, outcome, length, fingerprint, detail = recorded[0]
        self.assertEqual(len(WIRE), int(length))
        self.assertEqual(4, len(bytes.fromhex(str(fingerprint))))
        self.assertIn("incident review 2026-08-10", detail)
        self.assertNotIn(MARKER, detail)

    def test_the_agent_connection_reaches_neither_the_seal_nor_the_trail(self):
        # Which is what makes the audit trail an audit trail: a surface the
        # subject of the audit could read is a surface it could learn from.
        for statement in (
            "SELECT count(*) FROM artifact_seal",
            "SELECT count(*) FROM secret_kek",
            "SELECT count(*) FROM secret_access_log",
            "SELECT count(*) FROM find_in_database('x')",
        ):
            with self.subTest(statement), self.bound("a") as session:
                with self.assertRaises(pg.DatabaseError) as refused:
                    session.execute(statement)

                self.assertEqual("42501", refused.exception.sqlstate)

    def test_a_ciphertext_that_was_edited_fails_closed(self):
        # Criterion 6. The store files the envelope under its own hash, so an
        # edited ciphertext is caught before any key material is used at all --
        # and nothing partial is written out on the way to saying so.
        path = artifact.path_for(self.root, self.ciphertext)
        kept = path.read_bytes()
        path.write_bytes(kept[:-1] + bytes([kept[-1] ^ 0xFF]))
        try:
            result, target = self.opening(
                "a", "tampered.wire", label="AF1", authorize="checking the tamper path"
            )
        finally:
            path.write_bytes(kept)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertFalse(target.exists())
        self.assertIsNone(result.facts["released"])
        self.assertFalse(result.facts["integrity"]["sound"])
        self.assertIn(
            "the sealed bytes cannot be read",
            [row[4] for row in self.trail(scope_id=self.identifiers["a"], outcome="error")][0],
        )

    def test_the_wrong_key_file_is_refused_before_anything_is_decrypted(self):
        # The second way it fails closed, and the one that reads as what it is.
        # The check value exists so that a wrong key file is a configuration
        # problem here rather than an authentication failure that looks like
        # corruption three steps later.
        result = artifact.open_wire(
            self.harness.runtime,
            self.configurations["a"],
            root=self.root,
            key=self.wrong,
            label="AF1",
            into=scratch() / "wrong-key.wire",
            authorize="checking the wrong-key path",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(["argument:--key"], [item.source for item in result.violations])
        self.assertFalse((scratch() / "wrong-key.wire").exists())
        self.assertIsNone(result.facts["released"])
        self.assertIn(
            "key material does not match",
            " ".join(row[4] for row in self.trail(scope_id=self.identifiers["a"], outcome="error")),
        )

    def test_another_programs_label_opens_nothing_and_says_nothing(self):
        # The third: the seal is scoped, the query says so twice, and the answer
        # from the Program that does not hold it is the answer for a label that
        # does not exist. The attempt is still recorded, against the Program that
        # made it.
        result, target = self.opening(
            "b", "cross-program.wire", label="AF1", authorize="reaching for another Program"
        )

        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual({"label": "AF1", "present": False}, result.facts["artifact"])
        self.assertFalse(target.exists())
        self.assertIsNone(result.facts["released"])
        self.assertEqual(
            [("open", "denied", None, None, "AF1 names no sealed artifact of this Program")],
            self.trail(scope_id=self.identifiers["b"], verb="open"),
        )

    def test_sealing_the_same_wire_bytes_twice_is_refused(self):
        # A seal is immutable and a second one would carry a fresh nonce, so the
        # row would describe a ciphertext that is not the one on disk. Refused on
        # the way in, from either Program, and recorded -- and the envelope the
        # refused attempt had already written is taken back up again, because a
        # fresh nonce puts its hash beyond every other writer's reach and no row
        # will ever name it.
        held = self.stored()

        result = self.sealing("b")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(["argument:--wire"], [item.source for item in result.violations])
        self.assertEqual(held, self.stored())
        self.assertEqual(
            1,
            self.connection.execute(
                "SELECT count(*) FROM artifact_seal WHERE sha256 = $1", (artifact.digest(WIRE),)
            ).scalar(),
        )
        self.assertIn(
            "already carries a seal",
            " ".join(
                row[4] for row in self.trail(scope_id=self.identifiers["b"], verb="seal")
            ),
        )

    def test_the_audit_names_the_seal_without_opening_it(self):
        # `rk artifact audit` is the operator's view of the pair: the label, the
        # algorithm, the generation, and both hashes. It holds the envelope
        # against its bytes and never decrypts it, so it needs no key.
        result = artifact.audit(self.harness.runtime, self.configurations["a"], root=self.root)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(
            [
                {
                    "label": "AF1",
                    "sha256": artifact.digest(WIRE),
                    "alg": seal.ALG,
                    "kek_gen": 1,
                    "ciphertext_sha256": self.ciphertext,
                    "byte_size": len(WIRE),
                }
            ],
            result.facts["seals"],
        )
        self.assertEqual(2, result.facts["integrity"]["verified"], "the label, and the envelope")
        self.assertNotIn(MARKER, json.dumps(result.as_dict()))

    def test_the_gate_holds_the_sealed_store_while_holding_no_key(self):
        # And the check every command ends by running. A sealed artifact is
        # reachable through no reference, so a gate that only followed labels
        # would pass a database whose ciphertext was gone.
        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected, store=self.root)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual([], result.facts["artifacts"]["broken"])
        self.assertTrue(result.facts["artifacts"]["sound"])
        self.assertGreaterEqual(result.facts["artifacts"]["verified"], 2)

    def test_a_missing_envelope_fails_the_gate_that_holds_no_key(self):
        # The negative control for it, and the reason the seal is verified at
        # all: every registered check still passes with the ciphertext gone,
        # because no statement in the database can open a file.
        path = artifact.path_for(self.root, self.ciphertext)
        kept = path.read_bytes()
        path.unlink()
        try:
            with pg.connect(self.harness.migrate) as connection:
                blind = integrity.verify(connection, self.harness.expected)
                seeing = integrity.verify(connection, self.harness.expected, store=self.root)
        finally:
            path.write_bytes(kept)

        self.assertTrue(blind.ok, "no registered check can open a file")
        self.assertEqual(EXIT_INTEGRITY_FAILED, seeing.exit_code)
        self.assertEqual(["artifact_store"], [item.source for item in seeing.violations])
        self.assertIn("not in the store", seeing.violations[0].detail)


#: The Programs the proxy tests open. Three: the one that makes the request, one
#: it is not, and one that is retired while its capability is still live.
PROXY_SLUG = "selftest-proxy"

#: What the target answers. Distinctive so that finding it in a transcript is
#: unambiguous, and long enough that a byte count is a real measurement.
ANSWER = b'{"note":"the target answered the proxy","items":[1,2,3,4,5,6,7,8]}'

#: The request the matrix already decides: `http://app.example.com/` is `target`
#: under `SCOPED`, on port 80, over http. Loopback can never be a scope
#: inclusion, so this is the name the proxy asks about and `connector` is where
#: the socket actually goes.
URL = "http://app.example.com/notes"

#: The same name over the protocol the door has to open a tunnel for. In scope
#: under `SCOPED` on 443 as well, so what differs between this and the row above
#: is the transport and nothing about the decision.
SECURE = "https://app.example.com/notes"


class LiveTarget(Target):
    """The shared recording counterparty, answering this suite's own body."""

    answer = ANSWER


class ProxyEgressTest(DatabaseCase):
    """PH2-09 and PH2-10: two requests through the door, and ten that fail at it.

    The half of tickets 09 and 10 only a server can answer. `tests/test_proxy.py`
    holds the other half -- what the door does with the bytes -- against a stub;
    here the fence is `rk2_proxy` on a real connection, the capability is minted
    by `authorize_tool_run`, and every refusal is a row somebody can read
    afterwards.

    The two exchanges differ only in protocol, and that is the claim ticket 10
    makes: the https one opens a tunnel this door terminates, and everything
    after the handshake -- the authorization, the writer, the row -- is the code
    the http one ran.

    Three things make this a test of the production path rather than of a
    rehearsal of it. The runtime half is `proxy.send`, the same function
    `rk proxy request` calls. The fence holds the proxy role, so anything it
    manages to write is something a compromised proxy could write. And the
    target is reached through the `connector` seam rather than through DNS,
    because `127.0.0.1` can never be in a Program's scope -- what is faked is
    the address, and nothing about the decision that authorised it.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)
        cls.root = scratch() / "proxy-store"

        cls.identifiers = {}
        cls.configurations = {}
        for name in ("a", "b", "retired"):
            path = write(SCOPED.replace('name = "matrix-web"', f'name = "{PROXY_SLUG}-{name}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]

        cls.target, _ = counterparty(LiveTarget)
        cls.secure_target, _, cls.target_ca = tls_counterparty(LiveTarget)
        cls.authority = tls.authority(scratch() / "door-authority")

        cls.fence = proxy.Fence(pg.connect(cls.harness.proxy))
        cls.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=cls.fence,
            store=Store(cls.root),
            connector=cls.dial,
            authority=cls.authority,
        )
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.proxy_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

        # The one exchange every criterion but the fifth is read from. Run once,
        # in setup, because it commits: repeating it per test would multiply the
        # Receipts the counting assertions are about.
        cls.sent = proxy.send(
            cls.harness.runtime, cls.configurations["a"], URL, proxy_url=cls.proxy_url
        )
        # And the same request over the other protocol, through a tunnel this
        # door terminates. Its Receipt is read beside the one above: two rows
        # from one path is the claim ticket 10 makes.
        cls.secured = proxy.send(
            cls.harness.runtime,
            cls.configurations["a"],
            SECURE,
            proxy_url=cls.proxy_url,
            ca_file=cls.authority.certificate,
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.fence.close()
        cls.target.shutdown()
        cls.target.server_close()
        cls.secure_target.shutdown()
        cls.secure_target.server_close()
        cls.runtime.close()

        stored = [
            str(row[0])
            for row in cls.connection.execute(
                "SELECT DISTINCT unnest(ARRAY[request_agent_sha, response_agent_sha])"
                "  FROM receipts r JOIN programs p ON p.id = r.program_id"
                " WHERE p.slug LIKE $1",
                (f"{PROXY_SLUG}-%",),
            ).rows
            if row[0] is not None
        ]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute("DELETE FROM programs WHERE slug LIKE $1", (f"{PROXY_SLUG}-%",))
            if stored:
                cls.connection.execute(
                    "DELETE FROM artifacts WHERE sha256 = ANY($1)",
                    ("{" + ",".join(stored) + "}",),
                )
        super().tearDownClass()

    @classmethod
    def dial(
        cls, host: str, port: int, timeout: float, protocol: str
    ) -> http.client.HTTPConnection:
        """Every authorised name reaches the one target this machine is running.

        One target per protocol, because the door's outbound side is not the same
        socket for the two: an https target is verified by the door itself, which
        is the half of interception the agent can no longer do for itself.
        """
        if protocol == "https":
            return http.client.HTTPSConnection(
                "127.0.0.1",
                cls.secure_target.server_address[1],
                timeout=timeout,
                context=ssl.create_default_context(cafile=str(cls.target_ca)),
            )
        return http.client.HTTPConnection(
            "127.0.0.1", cls.target.server_address[1], timeout=timeout
        )

    # -- the arms of criterion 5, each of which needs a capability of its own ---

    def mint(self, name: str) -> tuple[str, str, str]:
        """One Agent run, one Tool run and one live capability, committed.

        Committed because the fence resolves it on a session of its own, which is
        the arrangement production has and the reason these arms cannot be asked
        inside a transaction that rolls back.
        """
        self.runtime.execute(proxy.BIND, (self.identifiers[name],))
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            run = self.runtime.execute(
                proxy.OPEN_RUN,
                (self.identifiers[name], "operator", json.dumps({"command": "selftest"})),
            ).scalar()
            opened = self.runtime.execute(
                proxy.OPEN_TOOL_RUN,
                (
                    self.identifiers[name],
                    str(run),
                    proxy.TOOL,
                    json.dumps({"url": URL, "method": "GET", "identity_slot": ""}),
                ),
            ).rows[0]
        gate = self.runtime.execute(proxy.AUTHORIZE_TOOL_RUN, (str(opened[0]),)).scalar()
        answer = json.loads(gate) if isinstance(gate, str) else dict(gate)
        capability = answer.get("capability")
        self.assertIsNotNone(capability, f"the gate answered {answer.get('decision')}")
        return str(capability), str(opened[0]), str(run)

    def attempt(self, capability: str | None, program_id: str | None) -> tuple[int, str | None]:
        """One request at the door, with whatever control headers it was given."""
        headers = {}
        if capability is not None:
            headers[proxy.AUTHORIZATION] = f"RedKraken {capability}"
        if program_id is not None:
            headers[proxy.PROGRAM] = program_id
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=proxy.TIMEOUT
        )
        try:
            client.request("GET", URL, headers=headers)
            answer = client.getresponse()
            answer.read()
            return answer.status, answer.headers.get(proxy.DECISION)
        finally:
            client.close()

    def owner(self, sql: str, parameters: tuple = ()) -> None:
        """One statement as the role that owns the tables, committed."""
        with self.connection.transaction():
            self.connection.execute("SET LOCAL ROLE rk2_owner")
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            self.connection.execute(sql, parameters)

    def version(self, name: str) -> int:
        """The scope version the Program is on, which the Receipt cites by name."""
        return int(
            self.connection.execute(
                "SELECT scope_version FROM programs WHERE id = $1::uuid",
                (self.identifiers[name],),
            ).scalar()
        )

    def receipts(self, name: str) -> list[tuple]:
        return [
            (str(row[0]), str(row[1]), str(row[2]), row[3], str(row[4]))
            for row in self.connection.execute(
                "SELECT lane, decision, reason, tool_run_id::text, coalesce(scope_class, '')"
                "  FROM receipts WHERE program_id = $1::uuid ORDER BY ts_arrival, label",
                (self.identifiers[name],),
            ).rows
        ]

    def refused(self, name: str, capability: str | None, program_id: str | None) -> tuple:
        """One blocked arm: the answer, and the single record it left behind."""
        before = len(self.receipts(name))
        seen = len(self.target.seen)

        status, decision = self.attempt(capability, program_id)
        after = self.receipts(name)

        self.assertEqual(407, status)
        self.assertEqual(proxy.REFUSED, decision)
        self.assertEqual(seen, len(self.target.seen), "the target was contacted")
        self.assertEqual(before + 1, len(after), "a refusal wrote something other than one record")
        return after[-1]

    def test_the_capability_is_minted_by_the_database_and_stored_as_a_digest(self):
        # Criterion 1. The plaintext is 32 random bytes in hex, it is never a
        # column, and what the row holds is its SHA-256 and an expiry the caller
        # did not choose. `authorize_tool_run` is the only minter: the guard
        # trigger refuses the columns to anyone below the owner.
        capability, tool_run, _ = self.mint("a")
        row = self.connection.execute(
            "SELECT egress_token_sha256, encode(digest($2, 'sha256'), 'hex'),"
            "       egress_token_expires_at > now() + interval '4 minutes',"
            "       egress_token_expires_at < now() + interval '6 minutes'"
            "  FROM tool_runs WHERE id = $1::uuid",
            (tool_run, capability),
        ).rows[0]

        self.assertEqual(64, len(capability))
        self.assertRegex(capability, "^[0-9a-f]{64}$")
        self.assertEqual(str(row[1]), str(row[0]))
        self.assertNotEqual(capability, str(row[0]))
        self.assertEqual([True, True], [bool(row[2]), bool(row[3])])
        self.assertEqual(
            0,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM tool_runs WHERE egress_token_sha256 = $1", (capability,)
                ).scalar()
            ),
        )

    def test_one_request_is_served_and_one_allowed_receipt_records_it(self):
        # Criteria 2 and 4, from the caller's side. The report names the Receipt
        # the database wrote, not one the runtime chose, and the row is `agent`
        # lane, `allowed`, and attributed to the Tool run that spent it.
        self.assertTrue(self.sent.ok, self.sent.violations)
        self.assertEqual(EXIT_OK, self.sent.exit_code)
        self.assertEqual(200, self.sent.facts["response"]["status"])
        self.assertEqual(len(ANSWER), self.sent.facts["response"]["byte_size"])

        served = [row for row in self.receipts("a") if row[1] == "allowed"]
        allowed = [row for row in served if row[3] == self.sent.facts["tool_run"]["id"]]

        # One Receipt for this exchange, and one per exchange: the https run in
        # setup is the other, and a path that recorded twice or not at all is a
        # Receipt count that no longer equals the egress count.
        self.assertEqual(1, len(allowed))
        self.assertEqual(2, len(served))
        # The lane is `agent` because a capability is the only thing that mints
        # one: 038's writer derives it rather than accepting it, the same way
        # 040 derives a blocked Receipt's lane from its purpose. A replay or a
        # proxy-internal request reaches a different writer.
        self.assertEqual("agent", allowed[0][0])
        self.assertEqual(
            f"allowed as target under scope version {self.version('a')}", allowed[0][2]
        )
        self.assertEqual(self.sent.facts["tool_run"]["id"], allowed[0][3])
        self.assertEqual("target", allowed[0][4])
        self.assertEqual(
            self.sent.facts["receipt"],
            str(
                self.connection.execute(
                    "SELECT label FROM receipts WHERE tool_run_id = $1::uuid AND decision='allowed'",
                    (self.sent.facts["tool_run"]["id"],),
                ).scalar()
            ),
        )

    def test_the_receipt_names_the_bytes_of_both_directions_and_they_are_stored(self):
        # The other half of criterion 4: a Receipt that names a hash nothing
        # registered proves nothing, so the row, the artifact and the file on
        # disk are asked about together. No wire view is claimed -- ticket 12
        # injects and seals; this exchange sent what the agent may read.
        row = self.connection.execute(
            "SELECT r.request_agent_sha, r.response_agent_sha, r.request_wire_sha,"
            "       r.response_wire_sha, r.status_code, r.method, r.host, r.port, r.path"
            "  FROM receipts r WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'",
            (self.sent.facts["tool_run"]["id"],),
        ).rows[0]
        request_sha, response_sha = str(row[0]), str(row[1])
        stored = {
            str(item[0]): (int(item[1]), str(item[2]), str(item[3]), bool(item[4]))
            for item in self.connection.execute(
                "SELECT sha256, byte_size, content_type, visibility, encrypted FROM artifacts"
                " WHERE sha256 = ANY($1)",
                ("{" + request_sha + "," + response_sha + "}",),
            ).rows
        }

        self.assertIsNone(row[2])
        self.assertIsNone(row[3])
        self.assertEqual((200, "GET", "app.example.com", 80, "/notes"), tuple(row[4:9]))
        self.assertEqual({request_sha, response_sha}, set(stored))
        for sha, (byte_size, content_type, visibility, encrypted) in stored.items():
            with self.subTest(sha=sha):
                blob = artifact.path_for(self.root, sha).read_bytes()
                self.assertEqual(byte_size, len(blob))
                self.assertEqual(sha, artifact.digest(blob))
                self.assertEqual(proxy.TRANSCRIPT, content_type)
                self.assertEqual(("agent_visible", False), (visibility, encrypted))
        self.assertIn(ANSWER, artifact.path_for(self.root, response_sha).read_bytes())

    def test_the_target_saw_the_request_and_none_of_the_control_headers(self):
        # Criterion 3, against a target that actually ran. The request line is
        # origin form -- the target is not a proxy -- and nothing that named the
        # capability or the Program survived the hop.
        method, path, headers = self.target.seen[-1]
        names = [name for name, _ in headers]

        self.assertEqual(("GET", "/notes"), (method, path))
        self.assertEqual(["app.example.com"], [value for name, value in headers if name == "host"])
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        self.assertEqual([], [name for name in names if name.startswith(proxy.INTERNAL)])
        for _, value in headers:
            self.assertNotIn("RedKraken", value)

    def test_the_capability_no_longer_resolves_once_the_tool_run_is_closed(self):
        # Criterion 2's "current lifecycle", read as a fact about the row: the
        # Tool run `send` closed carries no digest at all, so the capability it
        # spent cannot be spent again by anyone who kept it.
        row = self.connection.execute(
            "SELECT status, egress_token_sha256, egress_token_expires_at"
            "  FROM tool_runs WHERE id = $1::uuid",
            (self.sent.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual("success", str(row[0]))
        self.assertIsNone(row[1])
        self.assertIsNone(row[2])

    def test_the_same_request_over_https_crosses_the_same_capability_path(self):
        # PH2-10, criterion 2. The door terminated a tunnel, the request inside
        # it was decided by `authorize_egress_request` on the proxy's own session,
        # and the row that resulted is the row an http request leaves with `https`
        # in it. Nothing about this path is a second implementation: it is the
        # same `send`, the same fence and the same writer.
        self.assertTrue(self.secured.ok, self.secured.violations)
        self.assertEqual(EXIT_OK, self.secured.exit_code)
        self.assertEqual(200, self.secured.facts["response"]["status"])
        self.assertEqual(len(ANSWER), self.secured.facts["response"]["byte_size"])

        row = self.connection.execute(
            "SELECT lane, decision, scheme, host, port, path, status_code, intercepted,"
            "       label, request_wire_sha, response_wire_sha, scope_class"
            "  FROM receipts WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
            (self.secured.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual(("agent", "allowed", "https"), (str(row[0]), str(row[1]), str(row[2])))
        self.assertEqual(
            ("app.example.com", 443, "/notes", 200),
            (str(row[3]), int(row[4]), str(row[5]), int(row[6])),
        )
        self.assertEqual("target", str(row[11]))
        self.assertTrue(row[7], "a terminated tunnel is an intercepted exchange")
        self.assertEqual(self.secured.facts["receipt"], str(row[8]))
        # And no wire view is claimed. What the door saw of the target's own
        # connection is not what the agent read, and the row says so by leaving
        # the two wire hashes null rather than by repeating the agent's.
        self.assertIsNone(row[9])
        self.assertIsNone(row[10])

    def test_the_tunnelled_request_reached_the_target_with_no_control_header(self):
        # PH2-10, criterion 5, against a target that actually ran behind TLS. The
        # capability crossed on the CONNECT this time -- a hop `forwardable` never
        # sees -- so this is not the http case restated.
        method, path, headers = self.secure_target.seen[-1]
        names = [name for name, _ in headers]

        self.assertEqual(("GET", "/notes"), (method, path))
        self.assertEqual(["app.example.com"], [value for name, value in headers if name == "host"])
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        self.assertEqual([], [name for name in names if name.startswith(proxy.INTERNAL)])
        for _, value in headers:
            self.assertNotIn("RedKraken", value)

    def test_an_out_of_scope_https_target_is_refused_before_the_target_is_contacted(self):
        # PH2-10, criterion 4. The capability is real and the tunnel opens --
        # refusing the CONNECT would answer "is this host in scope" without
        # spending anything -- and the request inside it is decided against the
        # current policy, which excludes `admin.example.com`. No socket towards
        # the target is opened, and the identifier the caller is handed is the
        # blocked row itself.
        capability, _, _ = self.mint("a")
        denied = "https://admin.example.com/notes"
        seen = len(self.secure_target.seen)
        before = len(self.receipts("a"))

        answer = proxy._through(
            self.server.server_address,
            denied,
            "GET",
            capability,
            self.identifiers["a"],
            proxy.TIMEOUT,
            scope.canonical_request(denied),
            tls.trust(self.authority.certificate),
        )
        after = self.receipts("a")

        self.assertEqual(407, answer.status)
        self.assertEqual(b"", answer.body)
        self.assertEqual(seen, len(self.secure_target.seen), "the target was contacted")
        self.assertEqual(before + 1, len(after))
        self.assertEqual(("agent", "blocked", "capability refused"), after[-1][:3])

        row = self.connection.execute(
            "SELECT scheme, host, port, path, ts_egress FROM receipts WHERE id = $1::uuid",
            (answer.receipt,),
        ).rows[0]

        self.assertEqual(
            ("https", "admin.example.com", 443, "/notes"),
            (str(row[0]), str(row[1]), int(row[2]), str(row[3])),
        )
        self.assertIsNone(row[4], "a refusal before contact records no moment of egress")

    def test_an_out_of_scope_https_request_never_mints_a_capability_at_all(self):
        # The whole command rather than `_through`, and the refusal lands one
        # step earlier than the one above: the gate authorizes a Tool run against
        # its own arguments, so a request nobody may make never gets a capability
        # to make it with. The door refusing the same URL is the second fence,
        # not the first, and both are asserted because either one alone is a
        # single point of failure.
        denied = "https://admin.example.com/notes"
        seen = len(self.secure_target.seen)

        result = proxy.send(
            self.harness.runtime,
            self.configurations["a"],
            denied,
            proxy_url=self.proxy_url,
            ca_file=self.authority.certificate,
        )

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertIsNone(result.facts["response"], "a denied Tool run sent nothing")
        self.assertIsNone(result.facts["receipt"])
        self.assertEqual(seen, len(self.secure_target.seen), "the target was contacted")

        row = self.connection.execute(
            "SELECT status, egress_token_sha256 FROM tool_runs WHERE id = $1::uuid",
            (result.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual("denied", str(row[0]))
        self.assertIsNone(row[1], "a denied Tool run holds no capability to spend")

    def test_a_refusal_at_the_door_is_reported_as_a_refusal_and_not_as_a_success(self):
        # A door that refuses a request the gate authorized, which is the case
        # the runtime has to read correctly: the Receipt it is handed is a
        # blocked one. Naming it is what makes the refusal auditable, and reading
        # that name as "served" would close the Tool run as success, exit 0, and
        # tell an operator scripting this command that the request went out.
        #
        # The refusal is manufactured by pointing this door's outbound side at a
        # port nothing listens on, because the two fences agree about everything
        # else: an out-of-scope URL is stopped by the gate above before the door
        # ever sees it.
        with socket.socket() as spare:
            spare.bind(("127.0.0.1", 0))
            closed = spare.getsockname()[1]

        fence = proxy.Fence(pg.connect(self.harness.proxy))
        self.addCleanup(fence.close)
        door = proxy.listen(
            ("127.0.0.1", 0),
            fence=fence,
            store=Store(self.root),
            connector=lambda host, port, timeout, protocol: http.client.HTTPConnection(
                "127.0.0.1", closed, timeout=timeout
            ),
            authority=self.authority,
        )
        thread = threading.Thread(target=door.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(door.server_close)
        self.addCleanup(door.shutdown)

        result = proxy.send(
            self.harness.runtime,
            self.configurations["a"],
            SECURE,
            proxy_url=f"http://127.0.0.1:{door.server_address[1]}",
            ca_file=self.authority.certificate,
        )

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(407, result.facts["response"]["status"])
        self.assertEqual(
            ["egress"], [item.name for item in result.assertions if not item.ok]
        )
        # Cited, and closed as what it was. The capability is gone either way:
        # the same close that says `denied` clears the digest.
        self.assertIsNotNone(result.facts["receipt"])
        row = self.connection.execute(
            "SELECT status, egress_token_sha256 FROM tool_runs WHERE id = $1::uuid",
            (result.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual("denied", str(row[0]))
        self.assertIsNone(row[1])
        blocked = self.connection.execute(
            "SELECT decision, reason, host, ts_egress FROM receipts WHERE id = $1::uuid",
            (result.facts["receipt"],),
        ).rows[0]

        self.assertEqual(
            ("blocked", "target unreachable", "app.example.com"),
            (str(blocked[0]), str(blocked[1]), str(blocked[2])),
        )
        self.assertIsNotNone(blocked[3], "the door had already tried the target")

    def test_a_missing_capability_is_blocked_and_recorded_under_its_program(self):
        # Criterion 5, first arm. A Program is named and nothing else, so there
        # is somewhere to file the refusal -- and it is filed with no Tool run,
        # because no capability resolved one.
        record = self.refused("a", None, self.identifiers["a"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])
        self.assertIsNone(record[3])

    def test_a_fabricated_capability_is_blocked_before_the_target_is_contacted(self):
        # Second arm. Well-formed, right length, never minted.
        record = self.refused("a", "c" * 64, self.identifiers["a"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])

    def test_a_capability_offered_twice_is_refused_and_the_database_holds_the_row(self):
        # A caller who sent one header twice used to get a refusal that left no
        # row at all, which made duplicating your own capability the quietest way
        # to probe this fence. The Program was never the ambiguous part: it is
        # named once, it is a real Program, and the attempt belongs in its audit.
        before = len(self.receipts("a"))
        seen = len(self.target.seen)
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=proxy.TIMEOUT
        )
        try:
            client.putrequest("GET", URL)
            client.putheader(proxy.AUTHORIZATION, "RedKraken " + "c" * 64)
            client.putheader(proxy.AUTHORIZATION, "RedKraken " + "d" * 64)
            client.putheader(proxy.PROGRAM, self.identifiers["a"])
            client.endheaders()
            answer = client.getresponse()
            answer.read()
            status, decision = answer.status, answer.headers.get(proxy.DECISION)
        finally:
            client.close()
        after = self.receipts("a")

        self.assertEqual(407, status)
        self.assertEqual(proxy.AMBIGUOUS, decision)
        self.assertEqual(seen, len(self.target.seen), "the target was contacted")
        self.assertEqual(before + 1, len(after))
        self.assertEqual(("agent", "blocked", "ambiguous control headers"), after[-1][:3])
        self.assertIsNone(after[-1][3], "no capability resolved, so no Tool run is named")

    def test_a_capability_offered_under_another_program_resolves_to_nothing(self):
        # Third arm, and the one the header cannot decide: the Program header is
        # the caller's word, and `resolve_egress_capability` requires the Tool
        # run to belong to the bound Program. A real capability under the wrong
        # Program is filed against the Program that was claimed.
        capability, _, _ = self.mint("a")

        record = self.refused("b", capability, self.identifiers["b"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])
        self.assertIsNone(record[3])

    def test_an_expired_capability_is_blocked_although_its_tool_run_still_runs(self):
        # Fourth arm. The Tool run is untouched -- still running, still allowed,
        # still holding its digest -- and only the clock has moved past it.
        capability, tool_run, _ = self.mint("a")
        self.owner(
            "UPDATE tool_runs SET egress_token_expires_at = now() - interval '1 minute'"
            " WHERE id = $1::uuid",
            (tool_run,),
        )

        record = self.refused("a", capability, self.identifiers["a"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])
        self.assertEqual(
            "running",
            str(
                self.connection.execute(
                    "SELECT status FROM tool_runs WHERE id = $1::uuid", (tool_run,)
                ).scalar()
            ),
        )

    def test_a_cleared_capability_is_blocked_because_closing_the_run_revoked_it(self):
        # Fifth arm, and the structural one: nothing revokes the capability, the
        # Tool run simply stops running and the guard trigger clears the digest.
        capability, tool_run, _ = self.mint("a")
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            self.runtime.execute(proxy.CLOSE_TOOL_RUN, (tool_run, "success"))

        record = self.refused("a", capability, self.identifiers["a"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])
        self.assertIsNone(
            self.connection.execute(
                "SELECT egress_token_sha256 FROM tool_runs WHERE id = $1::uuid", (tool_run,)
            ).scalar()
        )

    def test_a_capability_does_not_outlive_the_program_it_was_minted_under(self):
        # The sixth arm, which 038 did not have: a Program can be retired with
        # its runs still running, and a capability minted a minute earlier would
        # otherwise stay live for its full five against withdrawn authority.
        capability, _, _ = self.mint("retired")
        self.owner("SELECT retire_program($1::uuid)", (self.identifiers["retired"],))

        record = self.refused("retired", capability, self.identifiers["retired"])

        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])

    def test_another_programs_request_between_the_decision_and_the_write_records_anyway(self):
        # The fence holds one connection for every handler thread, the Program is
        # a session setting, and the target exchange happens outside the lock --
        # so a second Program's request has the whole round trip in which to
        # rebind the session out from under this one. Interleaved by hand here,
        # because a race left to the scheduler is a test that passes for the
        # wrong reason more often than it fails for the right one.
        capability, tool_run, _ = self.mint("b")
        decided = self.fence.authorize(
            self.identifiers["b"], capability, "GET", scope.canonical_request(URL)
        )
        with self.assertRaises(proxy.Refused):
            self.fence.authorize(
                self.identifiers["a"], "e" * 64, "GET", scope.canonical_request(URL)
            )

        store = Store(self.root)
        sent = b"GET /notes HTTP/1.1\r\nHost: app.example.com\r\n\r\n"
        received = b"HTTP/1.1 200 OK\r\n\r\n" + ANSWER + b"\n"
        request_sha, _ = store.put(sent)
        response_sha, _ = store.put(received)
        written = self.fence.allowed_receipt(
            self.identifiers["b"],
            capability,
            {
                "reason": f"allowed as {decided.scope_class}",
                "method": "GET",
                "scheme": "http",
                "host": "app.example.com",
                "port": 80,
                "path": "/notes",
                "status_code": 200,
                "request_agent_sha": request_sha,
                "response_agent_sha": response_sha,
                "scope_class": decided.scope_class,
            },
            [
                {"sha256": request_sha, "byte_size": len(sent), "content_type": proxy.TRANSCRIPT},
                {
                    "sha256": response_sha,
                    "byte_size": len(received),
                    "content_type": proxy.TRANSCRIPT,
                },
            ],
        )

        self.assertEqual(
            (self.identifiers["b"], tool_run, "allowed"),
            tuple(
                str(value)
                for value in self.connection.execute(
                    "SELECT program_id, tool_run_id, decision FROM receipts WHERE id = $1::uuid",
                    (str(written["receipt_id"]),),
                ).rows[0]
            ),
        )

    def test_the_proxy_role_cannot_write_a_receipt_by_any_route_it_holds(self):
        # Criterion 6, for the role the door actually runs as. Direct DML is
        # revoked, and the writer that would have let it choose the decision is
        # no longer granted: `record_proxy_exchange` is the one door left, and
        # that one forces `allowed` only after the bytes agree.
        with pg.connect(self.harness.proxy) as session:
            session.execute(proxy.BIND, (self.identifiers["a"],))
            for statement, parameters in (
                (
                    "INSERT INTO receipts (program_id, lane, decision, reason, ts_arrival)"
                    " VALUES ($1::uuid, 'agent', 'allowed', 'by hand', now())",
                    (self.identifiers["a"],),
                ),
                (
                    "SELECT write_allowed_receipt($1, '{}'::jsonb)",
                    ("d" * 64,),
                ),
                ("UPDATE receipts SET decision = 'allowed'", ()),
                ("SELECT id FROM receipts", ()),
            ):
                with self.subTest(statement=statement[:40]):
                    with self.assertRaises(pg.DatabaseError) as raised:
                        session.execute(statement, parameters)
                    self.assertIn("permission denied", str(raised.exception).lower())

    def test_an_owner_level_insert_cannot_forge_an_allowed_receipt_either(self):
        # The rest of criterion 6, and the reason the rule is a trigger rather
        # than a grant. `rk2_owner` is above every privilege the fence uses, the
        # trigger is ENABLE ALWAYS, and a Receipt whose Tool run is closed, whose
        # Program is retired, or which names no Tool run at all is refused all
        # the same. The last row is the control: the same INSERT against a live
        # capability succeeds, so what fails above is the invariant and not the
        # statement.
        closed = self.sent.facts["tool_run"]["id"]
        live_capability, live_tool_run, _ = self.mint("a")
        insert = (
            "INSERT INTO receipts (program_id, tool_run_id, lane, decision, reason,"
            " ts_arrival, scope_class, scope_version, host)"
            " VALUES ($1::uuid, $2::uuid, 'agent', 'allowed', 'forged', now(),"
            " 'target', 1, 'app.example.com')"
        )
        for description, program_id, tool_run in (
            ("no tool run at all", self.identifiers["a"], None),
            ("a tool run that has closed", self.identifiers["a"], closed),
            ("another program's tool run", self.identifiers["b"], live_tool_run),
        ):
            with self.subTest(description):
                with self.assertRaises(pg.DatabaseError) as raised:
                    self.owner(insert, (program_id, tool_run))
                self.assertIn("live authorized capability", str(raised.exception))

        with self.assertRaises(Rollback):
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                self.connection.execute(insert, (self.identifiers["a"], live_tool_run))
                raise Rollback
        self.assertIsNotNone(live_capability)


class ArchiveTest(DatabaseCase):
    """Criterion 6: dump, restore, and a restored database that still holds."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        provisioned = migrate.provision(
            cls.harness.admin, RESTORED, passwords=cls.harness.passwords
        )
        assert provisioned.ok, provisioned.violations
        cls.target = cls.harness.restore.replace(database=RESTORED)
        cls.archive = scratch() / "rk2.dump"
        cls.written = backup.dump(cls.harness.migrate, cls.archive)
        cls.read = backup.restore(cls.target, cls.archive)

    def test_the_archive_is_written_and_identified_by_its_bytes(self):
        self.assertTrue(self.written.ok, self.written.violations)
        self.assertEqual(EXIT_OK, self.written.exit_code)
        self.assertEqual(self.archive.stat().st_size, self.written.facts["bytes"])
        self.assertEqual(64, len(self.written.facts["sha256"]))

    def test_an_existing_archive_is_never_overwritten(self):
        again = backup.dump(self.harness.migrate, self.archive)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, again.exit_code)
        self.assertIn("already exists", again.violations[0].detail)

    def test_a_target_that_already_holds_something_is_refused(self):
        # Refused before `pg_restore` runs, so what the operator reads is which
        # database was not empty rather than whichever object collided first.
        again = backup.restore(self.target, self.archive)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, again.exit_code)
        self.assertIn("already holds", again.violations[0].detail)

    def test_the_restore_reports_the_archive_it_read(self):
        self.assertTrue(self.read.ok, self.read.violations)
        self.assertEqual(self.written.facts["sha256"], self.read.facts["sha256"])

    def test_the_restore_repairs_what_the_archive_could_not_carry(self):
        # pg_dump carries neither `ALTER DATABASE ... SET` nor the order foreign
        # keys fire in, so a restore that only ran pg_restore would be a database
        # whose settings and purge order silently differ from the migrated one.
        repaired = {
            assertion.name: assertion.detail
            for assertion in self.read.assertions
            if assertion.name.startswith("finalize:")
        }

        self.assertIn("finalize:apply_server_settings", repaired)
        self.assertGreater(int(repaired["finalize:enforce_fk_fire_order"]), 0)

        # Read back from the catalogue `ALTER DATABASE ... SET` writes into,
        # rather than from `current_setting`, which cannot tell a setting this
        # database carries from a server default that happens to match. Compared
        # against the migrated database rather than a pinned list, because the
        # claim is that the two are the same database.
        self.assertNotEqual("", self.carried(DATABASE))
        self.assertEqual(self.carried(DATABASE), self.carried(RESTORED))

    def carried(self, database: str) -> str:
        return self.connection.execute(
            "SELECT coalesce(array_to_string(s.setconfig, '|'), '') FROM pg_database d"
            " LEFT JOIN pg_db_role_setting s ON s.setdatabase = d.oid AND s.setrole = 0"
            " WHERE d.datname = $1",
            (database,),
        ).scalar()

    def test_the_restored_database_holds_on_its_own(self):
        result = migrate.verify(self.target)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual([], result.facts["failed"])

    def test_the_restore_report_says_how_much_of_the_gate_ran(self):
        # A restore reports its own gate for the same reason a migration does:
        # an operator reading "ok" needs the count that makes it mean something.
        self.assertEqual([], self.read.facts["failed"])
        self.assertEqual(["baseline", "roles", "standing"], self.read.facts["families"])
        self.assertEqual(
            migrate.verify(self.target).facts["checks"], self.read.facts["checks"]
        )

    def test_the_restored_database_carries_the_same_corpus(self):
        state = migrate.status(self.target)

        self.assertEqual(self.harness.expected, state.facts["applied"])
        self.assertEqual([], state.facts["pending"])

    def test_the_restored_database_still_authors_its_own_events(self):
        # The archive creates the triggers after the data, so nothing re-emits
        # during the copy. Asked by writing a row rather than by counting
        # triggers: a trigger that exists and a trigger that fires are different
        # claims, and only the second one is what the restored database is for.
        with pg.connect(self.target) as connection:
            try:
                with connection.transaction():
                    connection.execute("SET LOCAL ROLE rk2_owner")
                    connection.execute("SELECT set_actor('runtime', 'selftest')")
                    program = connection.execute(PROGRAM, ("restored-selftest",)).scalar()
                    entity = connection.execute(ENTITY, (program,)).scalar()
                    events = connection.execute(
                        "SELECT type, subject_table, subject_id::text, actor_kind FROM events"
                    ).rows

                    self.assertEqual(
                        [("entity.created", "entities", str(entity), "runtime")], list(events)
                    )
                    raise Rollback
            except Rollback:
                pass

    def test_the_restored_database_refuses_a_write_that_says_nobody_wrote_it(self):
        # The guard travels with the schema, so it is on the restored database
        # too: an archive that carried the tables but not their discipline would
        # be a database that accepts anonymous rows.
        with pg.connect(self.target) as connection:
            with self.assertRaises(pg.DatabaseError) as refusal:
                with connection.transaction():
                    connection.execute("SET LOCAL ROLE rk2_owner")
                    program = connection.execute(PROGRAM, ("anonymous-selftest",)).scalar()
                    connection.execute(ENTITY, (program,))

        self.assertIn("app.actor_kind is unset", refusal.exception.primary)


if __name__ == "__main__":
    unittest.main()
