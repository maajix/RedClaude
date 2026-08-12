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
import contextlib
import http.client
import json
import os
import secrets
import shutil
import socket
import ssl
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from redkraken import (
    _startup,
    agent,
    artifact,
    backup,
    callback,
    config,
    decisions,
    header,
    identity,
    integrity,
    migrate,
    packet,
    pg,
    program,
    proposal,
    proxy,
    scope,
    seal,
    state,
    tls,
)
from redkraken.outcome import (
    AWAITING_DECISION,
    EXIT_AWAITING_DECISION,
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INTEGRITY_FAILED,
    EXIT_INVALID_CONFIGURATION,
    EXIT_OK,
    EXIT_TARGET_UNREACHABLE,
    TARGET_UNREACHABLE,
    Report,
)
from redkraken.store import Store
from tests.fixtures import (
    EXPORTED,
    PINNED,
    ROLE,
    SCOPE_ENTITIES,
    SCOPE_REQUESTS,
    SCOPED,
    VALID,
    WITHDRAWN,
    Target,
    boundary,
    counterparty,
    scratch,
    startup_refusal,
    tls_counterparty,
    unlatched,
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
    #: The operator connection. It owns no tables and changes Halt/decision
    #: state only through SECURITY DEFINER verbs granted to this login.
    human: pg.Settings
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
        human=admin.replace(
            database=DATABASE, user="rk2_human", password=passwords["rk2_human"]
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

    def owner(self, sql: str, parameters: tuple = ()) -> None:
        """One statement as the role that owns the tables, committed.

        Shared rather than each case's own, because what the scheduler writes --
        a claimed Task, a granted Identity Lease -- may be written by neither
        the runtime nor the proxy, so every case that arranges one has to become
        the owner in the same two lines.
        """
        with self.connection.transaction():
            self.connection.execute("SET LOCAL ROLE rk2_owner")
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            self.connection.execute(sql, parameters)

    def owned(self, sql: str, parameters: tuple = ()) -> str:
        """The same as `owner`, for a statement whose one value is needed back."""
        with self.connection.transaction():
            self.connection.execute("SET LOCAL ROLE rk2_owner")
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            return str(self.connection.execute(sql, parameters).scalar())


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

    def test_the_identity_skill_is_registered_for_the_web_hunter(self):
        source = Path(__file__).parents[1] / "skills" / "use-identity" / "SKILL.md"
        row = self.connection.execute(
            "SELECT s.enabled, s.source_sha256, rs.role"
            "  FROM skills s JOIN role_skills rs ON rs.skill_name = s.name"
            " WHERE s.name = 'use-identity'"
        ).rows

        self.assertEqual(
            ((True, artifact.digest(source.read_bytes()), "web_hunter"),), row
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
    families: tuple[str, ...] = integrity.ALL_FAMILIES


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


#: One arrival that got in while the guard was off. Everything before the last
#: statement is the ordinary shape -- a Program, the version it was running, the
#: channel that version declared, a subject and a live correlator -- so the only
#: falsification is the name in that statement, which is a host no channel of
#: this Program admits. It takes the trigger with it because that is the only
#: state this row exists in: a restore, where ORIGIN triggers do not fire and
#: the check is the last thing that would notice.
CALLBACK_CONTROL = (
    "DROP TRIGGER callback_interactions_attribution ON callback_interactions;"
    " DO $ctl$ DECLARE p uuid; e uuid; t uuid;"
    " BEGIN"
    "   PERFORM set_actor('runtime', 'selftest');"
    "   INSERT INTO programs (slug, name) VALUES ('callback-control', 'Self test')"
    "     RETURNING id INTO p;"
    "   INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)"
    "        VALUES (p, 1, '{}'::jsonb, repeat('c', 64));"
    "   INSERT INTO program_callback_channels (program_id, version, ord, name, kind, host)"
    "        VALUES (p, 1, 1, 'oob', 'dns', 'oob.example.test');"
    "   INSERT INTO entities (program_id, type, dedup_key)"
    "        VALUES (p, 'technology', 'tech:callback-control') RETURNING id INTO e;"
    "   INSERT INTO callback_correlators (program_id, scope_version, channel_name,"
    "                                      correlator_sha256, subject_entity_id, expires_at)"
    "        VALUES (p, 1, 'oob', repeat('a', 64), e, now() + interval '1 hour')"
    "     RETURNING id INTO t;"
    "   INSERT INTO artifacts (sha256, byte_size, visibility)"
    "        VALUES (repeat('d', 64), 4, 'agent_visible');"
    "   INSERT INTO callback_interactions (program_id, correlator_id, channel_name, arrival_kind,"
    "                                      observed_host, body_sha256, byte_size)"
    "        VALUES (p, t, 'oob', 'dns', 'elsewhere.test', repeat('d', 64), 4);"
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
    Control(
        # A question every channel has given up on. The fan-out is a trigger, so
        # the notification here is the one the database wrote; what the control
        # does is spend its attempts, which is the state a notifier that never
        # works arrives at on its own. From there nothing will carry the question
        # again and the deadline is the only thing left that happens to it -- so
        # it would be retired as a timeout against a human who was never told
        # there was anything to answer.
        "standing:control_surface",
        "DO $ctl$ DECLARE p uuid; a uuid; t uuid; g jsonb;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('unannounced-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet)"
        "        VALUES (p, 'orchestrator', 'session', 'operator', 'low', '{}'::jsonb)"
        "     RETURNING id INTO a;"
        "   INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport)"
        "        VALUES (p, a, 'mcp__rk2__net_request',"
        "                '{\"url\":\"https://probe.invalid/a\",\"method\":\"POST\"}'::jsonb,"
        "                'running', 'runtime')"
        "     RETURNING id INTO t;"
        "   g := canonical_request('mcp__rk2__net_request',"
        "                          '{\"url\":\"https://probe.invalid/a\",\"method\":\"POST\"}'::jsonb,"
        "                          'probe');"
        "   INSERT INTO pending_decisions"
        "        (program_id, agent_run_id, tool_run_id, tool, risk_class, risk_rule,"
        "         question_code, request_digest, equivalence_key, question, deadline_at)"
        "        VALUES (p, a, t, 'mcp__rk2__net_request', 'approval_required',"
        "                'net_unsafe_method', 'destructive_action', g, equivalence_key(g),"
        "                render_decision_question(g, 'approval_required', 'net_unsafe_method'),"
        "                now() + interval '1 hour');"
        "   UPDATE decision_notifications n SET attempts = c.max_attempts"
        "     FROM notification_channels c"
        "    WHERE c.channel = n.channel AND n.program_id = p;"
        " END $ctl$",
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
    Control(
        # Rule 6: the blocked-receipt writer answering with a row id again. A
        # return type can only be changed by dropping the function, and the drop
        # takes the proxy's grant with it, so a second arm of this same check
        # fires alongside -- which is why a control names the check and not one
        # problem. What it falsifies is that the gate would notice at all: before
        # this arm, a migration re-declaring the writer this way put a name on
        # the wire that `rk state --label` cannot resolve, silently.
        "standing:capability_receipt_fence",
        "DROP FUNCTION write_blocked_receipt(uuid,jsonb,text);"
        " CREATE FUNCTION write_blocked_receipt(uuid,jsonb,text) RETURNS uuid"
        " LANGUAGE sql AS $ctl$ SELECT uuidv7() $ctl$",
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
        "standing:program_halt",
        "GRANT EXECUTE ON FUNCTION halt_program(uuid,text) TO rk2_runtime",
    ),
    Control(
        # Rule 1: the reservation is the door's, and only the door's. A runtime
        # that can reserve can spend a Program's budget without passing the
        # capability check the door does first, and the count stops meaning
        # "requests that reached a target".
        "standing:egress_budget",
        "GRANT EXECUTE ON FUNCTION"
        " reserve_egress_slot(text,text,text,integer,text,text) TO rk2_runtime",
    ),
    Control(
        # Rule 2, and the one the verbs alone do not cover: the counters are
        # ordinary tables, so a role that can UPDATE the bucket refills it
        # without calling anything. The runtime is the role that matters --
        # 0029's default privileges hand it every DML verb on each new table, so
        # this control restores the state the migration's revoke undoes.
        "standing:egress_budget",
        "GRANT UPDATE ON program_egress_budget TO rk2_runtime",
    ),
    Control(
        # Rule 2 again, on the Halt. A DELETE lifts it and the actor-kind guard
        # never sees one: the trigger is BEFORE INSERT OR UPDATE.
        "standing:program_halt",
        "GRANT DELETE ON program_halts TO rk2_runtime",
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
    # --- callback admission --------------------------------------------------
    Control(
        # The verb on the connection the model reads through. A session that can
        # accept an interaction can write itself the evidence it wanted to have
        # observed, which is the one thing an out-of-band Observation is trusted
        # for: that nobody here caused it.
        "standing:callback_admission",
        "GRANT EXECUTE ON FUNCTION record_callback_interaction(text, jsonb, jsonb) TO rk2_state",
    ),
    Control(
        # A correlator whose expiry can be moved is a correlator with no expiry.
        "standing:callback_admission",
        "GRANT UPDATE ON callback_correlators TO rk2_runtime",
    ),
    Control(
        # The digest of a live correlator on the agent read surface. It is not
        # the plaintext, and it is still the join that tells a session which of
        # its own canaries is armed; the name an arrival came in at is worse.
        # `apply_state_grants` turns a row here into a grant, so the row is the
        # falsification rather than any GRANT statement.
        "standing:callback_admission",
        "INSERT INTO state_read_surface (table_name, column_name, added_by)"
        " VALUES ('callback_correlators', 'correlator_sha256', '14-control')",
    ),
    Control(
        # The invariant demoted to an ordinary trigger: still enforced on this
        # connection, and skipped entirely by the one connection that replays
        # rows nobody re-checks.
        "standing:callback_admission",
        "ALTER TABLE callback_interactions DISABLE TRIGGER callback_interactions_attribution",
    ),
    Control(
        # And the stored rows, which is the arm that exists for exactly the
        # state the control above leaves behind.
        "standing:callback_admission",
        CALLBACK_CONTROL,
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
    Control(
        "roles:runtime_role_exists",
        "ALTER ROLE rk2_runtime RENAME TO rk2_absent",
        on="superuser",
        families=(integrity.ROLES_FAMILY,),
    ),
    Control(
        "roles:proxy_role_exists",
        "ALTER ROLE rk2_proxy RENAME TO rk2_absent",
        on="superuser",
        families=(integrity.ROLES_FAMILY,),
    ),
)

#: The four facts fixed by the running binary and installed extension cannot be
#: changed transactionally. They cross the same evaluator the live gate uses,
#: so each negative control supplies one independently bad observation and asks
#: that evaluator for the named failed check. Expected values are literals from
#: the production baseline, not recomputed from the predicate under test.
RUNTIME_CONTROLS = (
    ("baseline:server_major", 170000, "{1}", "0.8.6", True),
    ("baseline:uuidv7_is_builtin", 180000, "{1,20000}", "0.8.6", True),
    ("baseline:pgvector_version", 180000, "{1}", "0.7.9", True),
    ("baseline:hnsw_cosine_opclass", 180000, "{1}", "0.8.6", False),
)


class NegativeControlTest(DatabaseCase):
    """Criterion 5: each check, shown failing when its subject is broken."""

    def run_gate(
        self,
        connection: pg.Connection,
        families: tuple[str, ...] = integrity.ALL_FAMILIES,
    ) -> list[str]:
        return [
            check.source
            for check in integrity.run(connection, self.harness.expected, families=families)
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

    def break_it(self, control: Control) -> list[str]:
        connection = self.connection_for(control.on)
        failed: list[str] = []
        try:
            with connection.transaction():
                if control.on == "owner":
                    connection.execute("SET LOCAL ROLE rk2_owner")
                connection.execute_script(control.sql)
                failed = self.run_gate(connection, control.families)
                raise Rollback
        except Rollback:
            pass
        return failed

    def test_the_gate_holds_before_anything_is_broken(self):
        self.assertEqual([], self.run_gate(self.connection))

    def test_each_check_fails_when_its_subject_is_broken(self):
        for control in CONTROLS:
            with self.subTest(control.check):
                self.assertIn(control.check, self.break_it(control))

    def test_each_fixed_runtime_fact_fails_through_the_gate_evaluator(self):
        for check, version, uuid_oids, vector_version, cosine in RUNTIME_CONTROLS:
            with self.subTest(check):
                failed = self.connection.execute(
                    "SELECT 'baseline:' || check_name"
                    "  FROM evaluate_server_runtime($1::integer, $2::bigint[], $3, $4)"
                    " WHERE NOT ok",
                    (version, uuid_oids, vector_version, cosine),
                ).rows

                self.assertEqual([check], [str(row[0]) for row in failed])

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
        # accounts for is the shape RK-REG-002 produced. `ts_egress` is what
        # makes it that shape rather than a refusal: bytes left this machine and
        # nothing accounts for them. A refusal decided before contact has no
        # tool run either, by construction, and is not this.
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
                    " ts_egress, scope_class, scope_version, host)"
                    " VALUES ($1, 'agent', 'blocked', 'self test', now(), now(),"
                    " 'target', 1, 'example.test')",
                    (program,),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    def test_a_refusal_before_contact_does_not_fail_the_receipt_check(self):
        # The other side of the same arm, and the reason it needed narrowing.
        # The door files a blocked Receipt for every capability it refuses, and
        # a refused capability resolves to no tool run -- that is what refusing
        # it means. Counting those made one fabricated capability fail the
        # standing gate for every Program, for good, and the only way to clear
        # it was to delete the row the refusal existed to leave.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program = self.connection.execute(PROGRAM, ("refusal-selftest",)).scalar()
                self.connection.execute(
                    "INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)"
                    " VALUES ($1, 1, '{}'::jsonb, repeat('c', 64))",
                    (program,),
                )
                self.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason, ts_arrival,"
                    " scope_class, scope_version, host)"
                    " VALUES ($1, 'agent', 'blocked', 'refused before contact', now(),"
                    " 'target', 1, 'example.test')",
                    (program,),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertNotIn("standing:receipt_integrity", failed)

    def test_egress_under_a_verdict_the_gate_refused_fails_the_receipt_check(self):
        # The second arm's own control. What it means is one sentence -- the
        # hook said no and the network happened anyway -- and both halves have
        # to be present for it to be that: a tool run the gate did not allow,
        # and a Receipt carrying `ts_egress`.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program, tool_run = self._refused_tool_run("denied-egress-selftest")
                self.connection.execute(
                    "INSERT INTO receipts (program_id, tool_run_id, lane, decision, reason,"
                    " ts_arrival, ts_egress, scope_class, scope_version, host)"
                    " VALUES ($1, $2, 'agent', 'blocked', 'self test', now(), now(),"
                    " 'target', 1, 'example.test')",
                    (program, tool_run),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    def test_a_budget_refusal_the_door_enforced_does_not_fail_the_receipt_check(self):
        # The shape ticket 13 produced against a live target, which failed this
        # arm five times over and could not be cleared: a Receipt is insert-only
        # evidence. The gate allowed the call, the door refused it before
        # contact, and the runtime closed the run as denied because a refused
        # request must not close as success. Nothing here is a hole -- reading
        # the outcome as the verdict was.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program, tool_run = self._refused_tool_run(
                    "budget-refusal-selftest", decision="allow"
                )
                self.connection.execute(
                    "INSERT INTO receipts (program_id, tool_run_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host)"
                    " VALUES ($1, $2, 'agent', 'blocked', 'rate limited', now(),"
                    " 'target', 1, 'example.test')",
                    (program, tool_run),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertNotIn("standing:receipt_integrity", failed)

    def test_a_target_that_never_answered_closed_as_denied_fails_the_receipt_check(self):
        # Arm (i)'s control, and the pair of the one above it. There, an outcome
        # was read as a verdict; here, a verdict nobody gave is written as an
        # outcome. The gate allowed this run, the name resolved to nothing, and
        # `denied` says the harness refused a request it in fact authorized.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program, tool_run = self._refused_tool_run(
                    "target-fault-selftest", decision="allow"
                )
                self.connection.execute(
                    "INSERT INTO receipts (program_id, tool_run_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host)"
                    " VALUES ($1, $2, 'agent', 'blocked', 'target unresolved', now(),"
                    " 'target', 1, 'example.test')",
                    (program, tool_run),
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    def test_a_run_that_was_also_refused_may_be_closed_as_denied(self):
        # The other half of arm (i), and the reason it reads the Receipts rather
        # than the status alone: one run may make several requests. This one met
        # an unreachable target and was separately refused, so `denied` is a word
        # something under it earned.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                program, tool_run = self._refused_tool_run(
                    "target-fault-and-refusal-selftest", decision="allow"
                )
                for reason in ("target unreachable", "capability refused"):
                    self.connection.execute(
                        "INSERT INTO receipts (program_id, tool_run_id, lane, decision,"
                        " reason, ts_arrival, scope_class, scope_version, host)"
                        " VALUES ($1, $2, 'agent', 'blocked', $3, now(),"
                        " 'target', 1, 'example.test')",
                        (program, tool_run, reason),
                    )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertNotIn("standing:receipt_integrity", failed)

    def test_a_question_for_a_human_closed_as_a_refusal_fails_the_receipt_check(self):
        # Arm (j). `ask` is the one verdict this harness may not act on, and the
        # shape ticket 11 gives it is `parked` naming the decision it opened.
        # A run closed `denied` under it says the harness refused a request
        # nobody had yet ruled on -- and the row is all that is left, because
        # nothing was queued and nobody was asked.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                self._refused_tool_run(
                    "discarded-question-selftest",
                    decision="ask",
                    risk_class="approval_required",
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    def test_a_call_allowed_by_no_answer_fails_the_receipt_check(self):
        # Arm (e), for the one class whose policy is to ask. `approval_required`
        # resolves to `ask`, so an `allow` on it did not come from the policy
        # table; the only thing that can produce one is a live grant, and this
        # run names no decision at all.
        failed: list[str] = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                self._refused_tool_run(
                    "ungranted-allow-selftest",
                    decision="allow",
                    risk_class="approval_required",
                    status="success",
                )
                failed = self.run_gate(self.connection)
                raise Rollback
        except Rollback:
            pass

        self.assertIn("standing:receipt_integrity", failed)

    # Arm (e)'s other half -- a call a human did approve, which departs from its
    # risk class legitimately -- is asserted where the rows are real, in
    # `test_a_call_the_gate_reserves_for_a_human_is_asked_and_not_refused`. It
    # cannot be built here: `actor_kind = 'human'` is refused unless the session
    # is a member of `rk2_human`, which is the whole point of that guard.

    def _refused_tool_run(
        self,
        slug: str,
        decision: str = "deny",
        *,
        risk_class: str | None = None,
        status: str = "denied",
    ) -> tuple[str, str]:
        """A Program with one closed tool run carrying the gate's verdict."""
        program = self.connection.execute(PROGRAM, (slug,)).scalar()
        self.connection.execute(
            "INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)"
            " VALUES ($1, 1, '{}'::jsonb, repeat('d', 64))",
            (program,),
        )
        run = self.connection.execute(
            "INSERT INTO agent_runs (program_id, role, runs_as, model, effort,"
            " mission_packet) VALUES ($1, 'orchestrator', 'session', 'operator',"
            " 'low', '{}'::jsonb) RETURNING id",
            (program,),
        ).scalar()
        tool_run = self.connection.execute(
            "INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport,"
            " risk_class, decision) VALUES ($1, $2, $3, '{}'::jsonb, $4, 'runtime',"
            " $5, $6) RETURNING id",
            (
                program,
                run,
                proxy.TOOL,
                status,
                risk_class or ("forbidden" if decision == "deny" else "constrained"),
                decision,
            ),
        ).scalar()
        return str(program), str(tool_run)

    def test_every_check_the_gate_runs_has_a_control(self):
        # The assertion that keeps the rest of this file honest: a check added
        # without a control fails here, naming itself, instead of joining the
        # gate as one more thing nobody has seen fail.
        covered = {control.check for control in CONTROLS}
        covered |= {check for check, *_ in RUNTIME_CONTROLS}
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

    def test_the_program_projects_only_identity_labels_to_the_agent_read_surface(self):
        slug = f"{RUN_SLUG}-identity"
        source = self.configuration(slug)
        opened = program.run(self.harness.runtime, source)

        visible = state.read(self.harness.runtime, self.harness.state, source)

        self.assertTrue(opened.ok, opened.violations)
        self.assertTrue(visible.ok, visible.violations)
        entity_labels = [
            item["label"]
            for item in visible.facts["state"]["records"]
            if item["kind"] == "entity"
        ]
        full_records = [
            state.read(self.harness.runtime, self.harness.state, source, label=label)
            for label in entity_labels
        ]
        identities = [
            result
            for result in full_records
            if result.facts["record"]["document"]["type"] == "identity"
        ]
        self.assertEqual(1, len(identities))
        [full] = identities
        document = full.facts["record"]["document"]
        self.assertEqual("member", document["descriptor"])
        self.assertEqual("user", document["identity_class"])
        self.assertNotIn("slot://", json.dumps(visible.as_dict()))
        self.assertNotIn("slot://", json.dumps(full.as_dict()))

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

    def test_opening_projects_the_identity_and_resuming_emits_one_more_event(self):
        # The configured Identity is durable Program state now, so opening emits
        # its creation and initial scope projection beside program.configured.
        # Resuming adds only run.resumed because neither projection moved.
        slug = f"{RUN_SLUG}-events"

        opened = self.run_for(slug)
        program_id = opened.facts["program_id"]
        after_open = self.events(program_id)
        self.run_for(slug)
        after_resume = self.events(program_id)

        self.assertEqual(
            [
                ("program.configured", "program_configurations", "runtime"),
                ("entity.created", "entities", "runtime"),
                ("entity.updated", "entities", "runtime"),
            ],
            [event[:3] for event in after_open],
        )
        self.assertEqual(4, len(after_resume))
        self.assertEqual(("run.resumed", None, "runtime"), after_resume[3][:3])
        payload = json.loads(after_resume[3][3])
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
        self.assertEqual(3, len(self.events(program_id)))

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
            [
                "program.configured",
                "entity.created",
                "entity.updated",
                "program.configured",
                "entity.updated",
                "run.resumed",
            ],
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
        self.assertEqual(3, len(self.events(program_id)))

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
        # The second Program holds its configured Identity beside the technology,
        # and the first holds everything else this case wrote. Neither count
        # includes the other Program's colliding labels.
        self.assertEqual(
            [("entity", 2)],
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

#: The two Programs the mission packet is compiled and staged against.
PACKET_SLUG = "selftest-packet"

#: What one seeded Artifact holds, before the Program's own name is appended to
#: it. Short, and text, because what is under test is that a head crosses the
#: boundary at all; how much of it does is `Limits`.
PACKET_BODY = b"the Program stored these bytes: "

#: What the canonical half of the database is, in the terms criterion 4 is
#: about. A Mission result that promoted anything, set a Task's lifecycle, or
#: queued a report or a validation would move one of these numbers.
CANONICAL_SNAPSHOT = """
SELECT (SELECT count(*) FROM entities),
       (SELECT count(*) FROM hypotheses),
       (SELECT count(*) FROM observations),
       (SELECT count(*) FROM hypothesis_evidence),
       (SELECT count(*) FROM findings),
       (SELECT count(*) FROM tasks),
       (SELECT coalesce(md5(string_agg(t.status, '|' ORDER BY t.id)), '') FROM tasks t),
       (SELECT count(*) FROM validation_queue),
       (SELECT count(*) FROM report_queue),
       (SELECT count(*) FROM verdicts)
"""


class MissionPacketTest(DatabaseCase):
    """PH2-19: what one Agent may read about its Program, and what it may write.

    Both halves need a server and neither can be faked. The compile runs on the
    `rk2_state` connection because every bound it honours is a bound row level
    security and the column grants impose -- a packet compiled as the owner
    would return every Program's rows and prove nothing. The staging write runs
    as `rk2_runtime` because that is the role the supervisor holds, and because
    `rk2_runtime` is the only role that can see another Program's Receipt, which
    is what makes `receipt_other_program` provable rather than
    indistinguishable from a Receipt that does not exist.

    Two Programs, seeded alike, so that every refusal here is about which
    Program a label resolves in rather than about a row one of them happens not
    to have. This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.configurations = {}
        cls.identifiers = {}
        for name in ("a", "b"):
            slug = f"{PACKET_SLUG}-{name}"
            path = write(VALID.replace('name = "acme-web"', f'name = "{slug}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]
        cls.seeded = {name: cls._populate(name) for name in ("a", "b")}
        cls.exclusive = cls._exclusive("b")

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            # `hypothesis_evidence` first, and only because of how its two keys
            # differ: the hypothesis side cascades and the observation side does
            # not, so dropping the Program takes the Observation out from under
            # an edge that still cites it. Deliberate in the schema -- an
            # Observation may not be deleted while something rests on it -- and
            # therefore an ordering a purge has to supply.
            cls.connection.execute(
                "DELETE FROM hypothesis_evidence WHERE program_id = ANY($1::uuid[])",
                (pg.quote_array([cls.identifiers[name] for name in ("a", "b")]),),
            )
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{PACKET_SLUG}-%",)
            )
            # `artifacts` is content-addressed across Programs, so deleting the
            # Programs takes the references and leaves the blobs. They are only
            # deletable now that nothing holds them.
            cls.connection.execute(
                "DELETE FROM artifacts WHERE sha256 = ANY($1::text[])",
                (pg.quote_array([cls.seeded[name]["artifact"] for name in ("a", "b")]),),
            )
        super().tearDownClass()

    @classmethod
    def _populate(cls, name: str) -> dict:
        """One of everything an Agent reads, in each Program.

        Each Program gets its own Task, run, Tool Run and Receipts, because the
        interesting refusals are all about a label that resolves in the wrong
        one -- and a label only resolves somewhere if something wrote it there.
        """
        program_id = cls.identifiers[name]
        seeded: dict[str, object] = {"program_id": program_id}
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            seeded["task"] = str(
                cls.connection.execute(
                    "INSERT INTO tasks (program_id, kind, status, claimed_at,"
                    " lease_expires_at) VALUES ($1::uuid, 'recon', 'claimed', now(),"
                    " now() + interval '10 minutes') RETURNING id::text",
                    (program_id,),
                ).scalar()
            )
            # No `kind`: migration 019 derives it from the Task, and stating it
            # here would be a second opinion about what the run is serving.
            seeded["run"] = str(
                cls.connection.execute(
                    "INSERT INTO agent_runs (program_id, task_id, role, runs_as, model,"
                    " effort, mission_packet) VALUES ($1::uuid, $2::uuid, 'recon',"
                    " 'subagent', 'selftest', 'low', '{}'::jsonb) RETURNING id::text",
                    (program_id, seeded["task"]),
                ).scalar()
            )
            seeded["tool_run"] = str(
                cls.connection.execute(
                    "INSERT INTO tool_runs (program_id, agent_run_id, task_id, tool,"
                    " args, status, transport) VALUES ($1::uuid, $2::uuid, $3::uuid,"
                    " 'mcp__rk2__http_request', '{}'::jsonb, 'success', 'runtime')"
                    " RETURNING id::text",
                    (program_id, seeded["run"], seeded["task"]),
                ).scalar()
            )
            # The bytes. The store is one content-addressed namespace shared by
            # every Program, so what makes a blob this Program's is an
            # `artifact_references` row -- and that row is not written here.
            # `hold_receipt_transcripts` writes it from the Receipt below,
            # which is the point of that trigger: holding follows from the
            # record rather than from each writer remembering.
            body = PACKET_BODY + f"{name}\n".encode()
            digest = artifact.digest(body)
            cls.connection.execute(
                "INSERT INTO artifacts (sha256, byte_size, content_type, visibility)"
                " VALUES ($1, $2, 'text/plain', 'agent_visible')",
                (digest, len(body)),
            )
            seeded["artifact"], seeded["body"] = digest, body
            # A refusal, which is the one Receipt shape that needs no live
            # capability behind it: migration 040 requires a running Tool Run,
            # an unexpired egress token and a leased Task before an `allowed`
            # agent-lane Receipt may exist. What is under test here is what a
            # Receipt is readable as, not what earned one.
            seeded["receipt"] = str(
                cls.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host, method, scheme,"
                    " path, request_agent_sha)"
                    " VALUES ($1::uuid, 'agent', 'blocked', 'refused before contact',"
                    " now(), 'target', 1, 'example.test', 'GET', 'https', '/', $2)"
                    " RETURNING label",
                    (program_id, digest),
                ).scalar()
            )
            # The label the Receipt's trigger just minted, which is the only
            # handle a child is ever given for these bytes.
            seeded["artifact_label"] = str(
                cls.connection.execute(
                    "SELECT label FROM artifact_references"
                    " WHERE program_id = $1::uuid AND sha256 = $2",
                    (program_id, digest),
                ).scalar()
            )
            # The proxy's own traffic. Migration 020's restrictive policy hides
            # this lane from `rk2_state`, so it is here to be *absent* from the
            # packet a child is given.
            seeded["internal"] = str(
                cls.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host)"
                    " VALUES ($1::uuid, 'proxy_internal', 'allowed', 'a csrf token',"
                    " now(), 'target', 1, 'example.test') RETURNING label",
                    (program_id,),
                ).scalar()
            )
            subject, subject_label = cls.connection.execute(
                "INSERT INTO entities (program_id, type, dedup_key)"
                " VALUES ($1::uuid, 'technology', $2) RETURNING id::text, label",
                (program_id, f"tech:{PACKET_SLUG}-{name}"),
            ).rows[0]
            seeded["subject"], seeded["subject_label"] = str(subject), str(subject_label)
            hypothesis, hypothesis_label = cls.connection.execute(
                "INSERT INTO hypotheses (program_id, subject_entity_id, property_class,"
                " statement) VALUES ($1::uuid, $2::uuid,"
                " (SELECT id FROM property_classes ORDER BY id LIMIT 1), $3)"
                " RETURNING id::text, label",
                (program_id, subject, f"a self test in {name}"),
            ).rows[0]
            seeded["hypothesis"] = str(hypothesis)
            seeded["hypothesis_label"] = str(hypothesis_label)
            observation, observation_label = cls.connection.execute(
                "INSERT INTO observations (program_id, agent_run_id, subject_entity_id,"
                " kind, summary, provenance_kind, tool_run_id)"
                " VALUES ($1::uuid, $2::uuid, $3::uuid, 'technology_identified', $4,"
                " 'tool_run', $5::uuid) RETURNING id::text, label",
                (
                    program_id,
                    seeded["run"],
                    subject,
                    f"the self test in {name} identified a technology",
                    seeded["tool_run"],
                ),
            ).rows[0]
            seeded["observation"] = str(observation)
            seeded["observation_label"] = str(observation_label)
            # `context`, because migration 018 makes `technology_identified`
            # non-evidential: it populates the surface and settles nothing, and
            # the trigger refuses to let it be cited as a baseline.
            cls.connection.execute(
                "INSERT INTO hypothesis_evidence (hypothesis_id, observation_id,"
                " polarity, role) VALUES ($1::uuid, $2::uuid, 'supports', 'context')",
                (seeded["hypothesis"], seeded["observation"]),
            )
            seeded["tool_run_label"] = str(
                cls.connection.execute(
                    "SELECT label FROM tool_runs WHERE id = $1::uuid",
                    (seeded["tool_run"],),
                ).scalar()
            )
        return seeded

    @classmethod
    def _exclusive(cls, name: str) -> dict:
        """Two labels that resolve in this Program and in no other.

        Labels are per-Program counters -- `next_label` counts within
        `program_id` -- so two Programs seeded alike hold the same labels, and
        "another Program's R1" is also this Program's R1. That collision is
        correct behaviour and it makes the cross-Program refusals untestable
        against the identical halves: a proposal citing R1 from Program a is
        citing a Receipt Program a really has.

        So one Program gets one more of each. The extra Receipt and the extra
        Entity take the next counter values, which the other Program has not
        reached, and citing those from the other Program is the citation the
        refusal is about.
        """
        program_id = cls.identifiers[name]
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            receipt = str(
                cls.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host, method, scheme,"
                    " path) VALUES ($1::uuid, 'agent', 'blocked', 'out of scope',"
                    " now(), 'target', 1, 'only-in-b.test', 'GET', 'https', '/')"
                    " RETURNING label",
                    (program_id,),
                ).scalar()
            )
            subject = str(
                cls.connection.execute(
                    "INSERT INTO entities (program_id, type, dedup_key)"
                    " VALUES ($1::uuid, 'technology', $2) RETURNING label",
                    (program_id, f"tech:{PACKET_SLUG}-{name}-only"),
                ).scalar()
            )
        return {"program": name, "receipt": receipt, "subject_label": subject}

    # -- the two connections -------------------------------------------------

    @classmethod
    @contextlib.contextmanager
    def agent_session(cls, name: str):
        """The connection a child's world is compiled on, bound to one Program.

        The binding is transaction-scoped by design -- `state.bind_agent_session`
        says why -- so it is held open around whatever reads through it. A read
        outside the transaction would be a read of no Program at all.
        """
        with pg.connect(cls.harness.state) as session:
            with session.transaction():
                assert state.bind_agent_session(state.Ledger(), session, cls.identifiers[name])
                yield session

    def compiled(self, name: str, **options) -> packet.Packet:
        with self.agent_session(name) as session:
            return packet.compile(session, **options)

    def staged(self, name: str, result: proposal.Result) -> proposal.Staged:
        """One Mission result, written the way the supervisor writes one."""
        seeded = self.seeded[name]
        with self.connection.transaction():
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            return proposal.stage(
                self.connection,
                result,
                program_id=seeded["program_id"],
                agent_run_id=seeded["run"],
                task_id=seeded["task"],
            )

    def canonical(self) -> tuple:
        return tuple(self.connection.execute(CANONICAL_SNAPSHOT).rows[0])

    # -- what the packet carries ---------------------------------------------

    def test_a_packet_carries_this_programs_rows_and_no_other_programs(self):
        # Criterion 1. Both Programs hold the same shapes and their labels
        # collide, so a compile that leaked would show up as a second
        # descriptor rather than only as a larger count.
        for name in ("a", "b"):
            other = "b" if name == "a" else "a"
            with self.subTest(program=name):
                compiled = self.compiled(name)

                descriptors = {
                    row.record["descriptor"] for row in compiled.section("surface").rows
                }
                self.assertIn(f"tech:{PACKET_SLUG}-{name}", descriptors)
                self.assertNotIn(f"tech:{PACKET_SLUG}-{other}", descriptors)
                expected = {self.seeded[name]["receipt"]}
                if name == self.exclusive["program"]:
                    expected.add(self.exclusive["receipt"])
                self.assertEqual(
                    expected,
                    {row.label for row in compiled.section("receipts").rows},
                )
                self.assertEqual(
                    [self.seeded[name]["artifact_label"]],
                    [row.label for row in compiled.section("artifacts").rows],
                )
                self.assertEqual(
                    [self.seeded[name]["artifact"]],
                    [row.record["sha256"] for row in compiled.section("artifacts").rows],
                )

    def test_every_section_a_read_tool_answers_from_is_compiled(self):
        compiled = self.compiled("a")

        for name in packet.SECTIONS:
            with self.subTest(section=name):
                self.assertTrue(compiled.section(name).rows, name)

    def test_the_proxys_own_traffic_is_not_in_the_packet_at_all(self):
        # Migration 020's restrictive policy, read from the side that matters:
        # the child cannot cite what it was never given.
        compiled = self.compiled("a")

        self.assertNotIn(
            self.seeded["a"]["internal"],
            [row.label for row in compiled.section("receipts").rows],
        )

    def test_every_digest_is_the_one_the_database_computes(self):
        # Criterion 2's other half. A digest an agent cites has to be
        # re-checkable against the database later, so it is the database's
        # digest that is staged -- a second implementation of the hash in
        # Python would be a second answer to that check.
        compiled = self.compiled("a")
        with self.agent_session("a") as session:
            held = {
                str(label): str(digest)
                for label, digest in session.execute(
                    "SELECT label, digest FROM v_records"
                ).rows
            }

        for name in ("surface", "hypotheses", "receipts"):
            for row in compiled.section(name).rows:
                with self.subTest(section=name, label=row.label):
                    self.assertEqual(held[row.label], row.digest)

    def test_the_revision_is_the_programs_own_high_water_mark(self):
        compiled = self.compiled("a")

        self.assertGreater(compiled.revision, 0)
        self.assertGreaterEqual(
            int(self.connection.execute("SELECT max(seq) FROM events").scalar()),
            compiled.revision,
        )

    def test_a_row_limit_leaves_behind_the_count_of_what_it_left_out(self):
        # Criterion 2. The staged rows come from a capped read and the total
        # comes from the database in the same compile, so the marker is the
        # subtraction: a caller is told the size of what it was not shown.
        compiled = self.compiled("a", limits=packet.Limits(rows=1))
        answer = packet.Reader(compiled).attack_surface()

        self.assertEqual(1, answer["counts"]["staged"])
        self.assertGreater(answer["counts"]["total"], 1)
        self.assertEqual(
            answer["counts"]["total"] - answer["counts"]["staged"],
            sum(
                marker["count"]
                for marker in answer["omitted"]
                if marker["reason"] == "packet_bound"
            ),
        )

    def test_a_byte_ceiling_is_honoured_by_the_compiled_document(self):
        compiled = self.compiled("a", limits=packet.Limits(byte_limit=600))

        self.assertLessEqual(compiled.bytes, 600)
        self.assertLess(
            len(compiled.rows()),
            sum(compiled.section(name).total for name in packet.SECTIONS),
        )

    def test_an_artifacts_head_is_staged_only_when_the_runtime_can_load_it(self):
        seeded = self.seeded["a"]
        held = {seeded["artifact"]: seeded["body"]}

        compiled = self.compiled("a", load=held.get)
        answer = packet.Reader(compiled).artifact(
            artifact_label=seeded["artifact_label"], span="0-4"
        )

        self.assertEqual(seeded["body"][:4].decode(), answer["records"][0]["content"])
        self.assertEqual([], answer["omitted"])

    def test_an_artifact_the_runtime_cannot_load_is_metadata_and_says_so(self):
        seeded = self.seeded["a"]

        answer = packet.Reader(self.compiled("a")).artifact(
            artifact_label=seeded["artifact_label"]
        )

        self.assertIsNone(answer["records"][0]["content"])
        self.assertEqual(
            [{"reason": "not_staged", "byte_size": len(seeded["body"])}],
            answer["omitted"],
        )

    def test_an_artifact_is_addressed_by_label_and_its_hash_is_only_reported(self):
        # Ticket 06's rule on `v_artifacts`, from the side that would break it:
        # the store is one content-addressed namespace shared by every Program,
        # so a verb taking a hash is a verb an agent can call for bytes it was
        # never shown. There is no such verb -- the hash comes back in the
        # record, where it is checkable against bytes the caller already holds.
        seeded = self.seeded["a"]

        answer = packet.Reader(self.compiled("a")).artifact(
            artifact_label=seeded["artifact_label"]
        )

        self.assertEqual(seeded["artifact"], answer["records"][0]["record"]["sha256"])
        with self.assertRaises(TypeError):
            packet.Reader(self.compiled("a")).artifact(artifact_hash=seeded["artifact"])

    def test_another_programs_artifact_is_not_reachable_by_its_label(self):
        # The labels of the two Programs collide by construction, so this is
        # the strongest form of the question: Program a asks for the label its
        # own reference happens to share with Program b's, and gets its own
        # bytes rather than a choice of two.
        answer = packet.Reader(self.compiled("a")).artifact(
            artifact_label=self.seeded["b"]["artifact_label"]
        )

        self.assertEqual(
            [self.seeded["a"]["artifact"]],
            [record["record"]["sha256"] for record in answer["records"]],
        )
        self.assertNotIn(
            self.seeded["b"]["artifact"],
            [record["record"]["sha256"] for record in answer["records"]],
        )

    # -- what the Mission result writes --------------------------------------

    def test_a_mission_result_writes_a_staging_row_and_moves_nothing_canonical(self):
        # Criterion 4, measured rather than argued: the canonical half of the
        # database is identical either side of the write, including the Task's
        # lifecycle, the validation queue and the report queue.
        seeded = self.seeded["a"]
        before = self.canonical()

        written = self.staged(
            "a",
            proposal.Result(
                payload={
                    "observations": [
                        {
                            "summary": "the header was absent",
                            "tool_run_label": seeded["tool_run_label"],
                            "subject_label": seeded["subject_label"],
                        }
                    ],
                    "new_entities": [{"type": "endpoint", "value": "/admin"}],
                    "hypotheses": [{"statement": "the endpoint is unauthenticated"}],
                    "evidence": [{"hypothesis": 0, "observation": 0}],
                    "suggested_tasks": [{"kind": "hunt"}],
                    "completion_claim": {"status": "partial"},
                }
            ),
        )

        self.assertEqual(before, self.canonical())
        self.assertEqual("staged", written.status)
        self.assertEqual("partial", written.completion)
        self.assertEqual([], list(written.drops))
        self.assertEqual(
            1,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM proposals WHERE id = $1::uuid",
                    (written.proposal_id,),
                ).scalar()
            ),
        )

    def test_the_staging_row_is_labelled_by_the_database_like_every_other_row(self):
        written = self.staged("a", proposal.Result(payload={"observations": []}))

        self.assertRegex(written.label, r"^PR[0-9]+$")
        self.assertEqual(
            written.label,
            str(
                self.connection.execute(
                    "SELECT label FROM proposals WHERE id = $1::uuid",
                    (written.proposal_id,),
                ).scalar()
            ),
        )

    def test_a_receipt_of_another_program_is_kept_as_a_rejected_element(self):
        # Criterion 5. `rk2_runtime` sees every Program, which is the only way
        # this is `receipt_other_program` rather than `no_such_receipt`. The
        # label has to be one only the other Program reached, per `_exclusive`.
        foreign = self.exclusive["receipt"]
        self.assertNotIn(
            foreign, [row.label for row in self.compiled("a").section("receipts").rows]
        )

        written = self.staged(
            "a",
            proposal.Result(
                payload={"observations": [{"summary": "seen", "receipt_label": foreign}]}
            ),
        )

        self.assertEqual("staged", written.status)
        self.assertEqual(["receipt_other_program"], [drop.reason for drop in written.drops])
        self.assertEqual(
            [("observations[0]", "receipt_other_program", foreign)],
            [
                (str(path), str(reason), str(cited))
                for path, reason, cited in self.connection.execute(
                    "SELECT element_path, reason, cited FROM proposal_drops"
                    " WHERE proposal_id = $1::uuid ORDER BY ordinal",
                    (written.proposal_id,),
                ).rows
            ],
        )

    def test_a_proxy_internal_receipt_cannot_back_an_observation_either(self):
        written = self.staged(
            "a",
            proposal.Result(
                payload={
                    "observations": [
                        {"summary": "seen", "receipt_label": self.seeded["a"]["internal"]}
                    ]
                }
            ),
        )

        self.assertEqual(["receipt_proxy_internal"], [drop.reason for drop in written.drops])

    def test_an_observation_about_another_programs_entity_is_kept_as_rejected(self):
        # The subject, unlike the provenance, is a label of a canonical row the
        # other Program holds and this one does not -- again `_exclusive`, for
        # the same reason.
        written = self.staged(
            "a",
            proposal.Result(
                payload={
                    "observations": [
                        {
                            "summary": "seen",
                            "tool_run_label": self.seeded["a"]["tool_run_label"],
                            "subject_label": self.exclusive["subject_label"],
                        }
                    ]
                }
            ),
        )

        self.assertEqual(["label_other_program"], [drop.reason for drop in written.drops])

    def test_a_receipt_no_program_holds_is_kept_as_a_rejected_element(self):
        written = self.staged(
            "a",
            proposal.Result(
                payload={"observations": [{"summary": "seen", "receipt_label": "R999999"}]}
            ),
        )

        self.assertEqual(["no_such_receipt"], [drop.reason for drop in written.drops])

    def test_the_read_role_cannot_write_a_proposal_or_anything_else(self):
        # The roster refuses a canonical write at compile time and the child has
        # no database at all; this is the third, independent statement of the
        # same thing, made where a bug in either of the other two would still be
        # caught.
        for table in ("proposals", "proposal_drops", "entities", "tasks", "report_queue"):
            with self.subTest(table=table):
                self.assertFalse(
                    self.connection.execute(
                        "SELECT bool_or(has_table_privilege('rk2_state', $1, p))"
                        "  FROM unnest(ARRAY['INSERT','UPDATE','DELETE']) AS p",
                        (table,),
                    ).scalar()
                )


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
        expected_fields = {"id", "kind", "label", "sha256", "created_at", "program_id"}
        self.assertTrue(all(set(item) == expected_fields for item in payloads))
        written = json.dumps(payloads)
        for fragment in ("artifact line 3", "only the first Program"):
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


CALLBACK_SLUG = "selftest-callback"

#: One recorded arrival. Not a DNS message anybody could parse: what is promoted
#: into an Observation is the bytes the listener wrote, and a test whose bytes
#: were well formed would be testing a parser this harness does not have.
ARRIVAL = b"\x00\x01\x81\x80 an out-of-band query for a canary\n"


class CallbackAdmissionTest(DatabaseCase):
    """PH2-14: one interaction at a name this Program published, and nothing else.

    The one Observation the harness does not fetch, which is why every claim
    here is about attribution rather than about a request. A correlator the
    runtime minted goes out in a payload; something the harness never spoke to
    queries a name carrying it; the operator's own listener writes the bytes to
    a file and hands them to `rk callback accept`. What must hold is that the
    arrival is admitted only if it names a channel the live policy declares and
    resolves a correlator of this Program that has not expired -- and that the
    correlator, which is the whole of the binding, never becomes something the
    agent can read.

    Criterion 6 is structural rather than asserted: nothing here opens a socket
    and no callback provider exists in this test. The listener is a file, which
    is exactly what a listener hands over.

    Everything runs as `rk2_runtime` and is read back as `rk2_state`, because a
    claim about what the agent connection cannot reach is worth nothing when it
    is made from the connection that owns the tables. This case commits, and
    purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = scratch() / "artifacts"
        cls.configurations = {}
        cls.identifiers = {}
        cls.opened = {}
        for name in ("a", "b", "c", "d"):
            slug = f"{CALLBACK_SLUG}-{name}"
            path = write(SCOPED.replace('name = "matrix-web"', f'name = "{slug}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (slug, opened.violations)
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]
            cls.opened[name] = opened

        # One subject each, so that an Observation has something to be about.
        # `TEC1` is what the label trigger calls the first technology entity of
        # a Program, and all three hold that label for the reason `StateReadTest`
        # gives: labels are per Program and colliding is the ordinary case.
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            for name in cls.identifiers:
                cls.connection.execute(
                    "INSERT INTO entities (program_id, type, dedup_key)"
                    " VALUES ($1::uuid, 'technology', $2)",
                    (cls.identifiers[name], f"tech:{CALLBACK_SLUG}-{name}"),
                )

        cls.source = scratch() / "arrival.bin"
        cls.source.write_bytes(ARRIVAL)
        cls.minted = callback.provision(
            cls.harness.runtime, cls.configurations["a"], "oob-dns", "TEC1"
        )
        assert cls.minted.ok, cls.minted.violations
        cls.accepted = callback.accept(
            cls.harness.runtime,
            cls.configurations["a"],
            cls.minted.facts["callback"]["address"],
            cls.source,
            root=cls.root,
            peer="resolver",
        )
        assert cls.accepted.ok, cls.accepted.violations

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{CALLBACK_SLUG}-%",)
            )
            cls.connection.execute(
                "DELETE FROM artifacts WHERE sha256 = $1", (artifact.digest(ARRIVAL),)
            )
        super().tearDownClass()

    @property
    def correlator(self) -> str:
        """The plaintext that went out in the payload, which nothing stored."""
        return str(self.minted.facts["callback"]["address"]).partition(".")[0]

    def subject(self, name: str) -> str:
        return str(
            self.connection.execute(
                "SELECT id FROM entities WHERE program_id = $1::uuid AND label = 'TEC1'",
                (self.identifiers[name],),
            ).scalar()
        )

    def mint(self, name: str, *, channel: str = "oob-dns", seconds: float = 3600) -> str:
        """One correlator, minted through the verb rather than through the CLI.

        The CLI refuses a lifetime under a second, which is the right answer for
        an operator and the wrong one for a test about expiry.
        """
        correlator = secrets.token_hex(16)
        with self.connection.transaction():
            self.connection.execute(
                "SELECT set_config('rk2.program_id', $1, true)", (self.identifiers[name],)
            )
            self.connection.execute(
                "SELECT mint_callback_correlator($1, $2, $3::uuid,"
                "        make_interval(secs => $4::double precision))",
                (channel, correlator, self.subject(name), str(seconds)),
            )
        return correlator

    def arrive(self, name: str, host: str, **options: object) -> Report:
        return callback.accept(
            self.harness.runtime,
            self.configurations[name],
            host,
            self.source,
            root=self.root,
            **options,
        )

    def refuse(self, name: str, sql: str, parameters: tuple) -> pg.DatabaseError:
        """One statement, in a transaction of its own, expected to be refused.

        Its own transaction because a refused statement aborts the one it was
        in: a second attempt in the same block is answered `25P02` whatever it
        asked, which would pass an assertion about being refused for a reason
        that has nothing to do with callbacks.

        The actor is declared as well, so that a statement put straight to the
        table is answered by the guard under test rather than by the emitter for
        writing anonymously.
        """
        with self.assertRaises(pg.DatabaseError) as refused:
            with self.connection.transaction():
                self.connection.execute(
                    "SELECT set_config('rk2.program_id', $1, true)",
                    (self.identifiers[name],),
                )
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                self.connection.execute(sql, parameters)
        return refused.exception

    def channels(self, name: str) -> list[tuple[int, str, str, str]]:
        """The channels of the live scope version, joined the way the guard joins."""
        return [
            (int(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in self.connection.execute(
                "SELECT c.ord, c.name, c.kind, c.host"
                "  FROM program_callback_channels c"
                "  JOIN programs p ON p.id = c.program_id AND p.scope_version = c.version"
                " WHERE c.program_id = $1::uuid ORDER BY c.ord",
                (self.identifiers[name],),
            ).rows
        ]

    def bytes_json(self) -> str:
        """The artifact half of an arrival: bytes that are registered already."""
        return json.dumps(
            {"sha256": artifact.digest(ARRIVAL), "byte_size": len(ARRIVAL)}
        )

    def counts(self) -> tuple[int, int]:
        """How many arrivals and callback Observations exist, over every Program."""
        return tuple(
            int(value)
            for value in self.connection.execute(
                "SELECT (SELECT count(*) FROM callback_interactions),"
                "       (SELECT count(*) FROM observations WHERE provenance_kind = 'callback')"
            ).rows[0]
        )

    def test_the_channels_the_policy_declares_are_projected_with_its_version(self):
        # Criterion 1's first half: what may be provisioned at all is what the
        # live scope version says, and the version is what the configuration
        # compiled to rather than anything a caller passed.
        self.assertEqual(
            [
                (1, "oob-dns", "dns", "dns.example.org"),
                (2, "oob-http", "http", "callback.example.org"),
            ],
            self.channels("a"),
        )
        self.assertEqual(2, self.opened["a"].facts["scope"]["callback_channels"])

    def test_a_version_that_carries_no_channel_list_yet_is_given_one(self):
        # The other half of criterion 1, and the case an installation upgraded
        # into this corpus is actually in: a Program live on a scope version
        # compiled before channels existed. Its digest has not changed, so the
        # ordinary reprojection writes nothing at all, and without a backfill
        # the Program would admit no arrival until the operator happened to edit
        # the configuration file. `d` is used here and nowhere else, because
        # this test takes its channels away.
        with self.connection.transaction():
            self.connection.execute("SET LOCAL app.purging = 'on'")
            self.connection.execute(
                "DELETE FROM program_callback_channels WHERE program_id = $1::uuid",
                (self.identifiers["d"],),
            )
        emptied = self.channels("d")

        again = program.run(self.harness.runtime, self.configurations["d"])

        self.assertEqual([], emptied)
        self.assertTrue(again.ok, again.violations)
        # Nothing was recompiled: the rows arrived on the path that recompiles
        # nothing, which is the only path this Program will ever take again.
        self.assertFalse(again.facts["scope"]["compiled"])
        self.assertEqual(
            [
                (1, "oob-dns", "dns", "dns.example.org"),
                (2, "oob-http", "http", "callback.example.org"),
            ],
            self.channels("d"),
        )

    def test_a_correlator_is_an_address_beneath_the_channel_it_names(self):
        # Criterion 2. The address is the whole product of provisioning: an
        # operator who was told a token and not where to send it has nothing to
        # embed.
        minted = self.minted.facts["callback"]

        self.assertEqual(("oob-dns", "dns"), (minted["channel"], minted["kind"]))
        self.assertEqual(f"{self.correlator}.dns.example.org", minted["address"])
        self.assertEqual(callback.CORRELATOR_BYTES * 2, len(self.correlator))
        self.assertEqual("technology", minted["subject_type"])

    def test_the_correlator_reaches_the_database_as_a_digest_and_never_as_itself(self):
        # The other half of criterion 2: it binds without being stored. The row
        # is compared whole rather than column by column, so a later migration
        # that added somewhere to keep the plaintext would fail this.
        row = str(
            self.connection.execute(
                "SELECT to_jsonb(t)::text FROM callback_correlators t WHERE id = $1::uuid",
                (self.minted.facts["callback"]["correlator_id"],),
            ).scalar()
        )

        self.assertNotIn(self.correlator, row)
        self.assertIn(artifact.digest(self.correlator.encode()), row)
        self.assertIn(str(self.identifiers["a"]), row)

    def test_the_exact_inbound_bytes_are_the_artifact_the_observation_cites(self):
        # Criterion 3, end to end: the bytes the listener recorded are in the
        # content-addressed store under their own hash, the arrival names that
        # hash, and the Observation names the arrival.
        accepted = self.accepted.facts["callback"]
        sha256 = artifact.digest(ARRIVAL)

        self.assertEqual(sha256, accepted["sha256"])
        self.assertEqual(len(ARRIVAL), accepted["byte_size"])
        self.assertEqual(ARRIVAL, artifact.path_for(self.root, sha256).read_bytes())

        row = self.connection.execute(
            "SELECT o.kind, o.provenance_kind, o.subject_entity_id::text,"
            "       ci.label, ci.body_sha256, ci.byte_size, ci.peer_class, ci.observed_host,"
            "       ci.channel_name, ci.arrival_kind"
            "  FROM observations o"
            "  JOIN callback_interactions ci ON ci.id = o.callback_interaction_id"
            " WHERE o.label = $1 AND o.program_id = $2::uuid",
            (accepted["observation"], self.identifiers["a"]),
        ).rows[0]

        self.assertEqual("callback_interaction", str(row[0]))
        self.assertEqual("callback", str(row[1]))
        self.assertEqual(self.subject("a"), str(row[2]))
        self.assertEqual(accepted["interaction"], str(row[3]))
        self.assertEqual(sha256, str(row[4]))
        self.assertEqual(len(ARRIVAL), int(row[5]))
        self.assertEqual("resolver", str(row[6]))
        self.assertEqual(self.minted.facts["callback"]["address"], str(row[7]))
        self.assertEqual(("oob-dns", "dns"), (str(row[8]), str(row[9])))

    def test_the_arrival_and_the_observation_it_produced_are_immutable(self):
        # An Observation has no status and an arrival is what happened. Nothing
        # rewrites either from the role that wrote them, which is the only role
        # holding any DML on them at all. The two halves refuse for different
        # reasons and both are worth asserting: the arrival because the verbs
        # were never granted, the Observation because 0013's `ENABLE ALWAYS`
        # trigger refuses it even where they were.
        for sql in (
            "UPDATE callback_interactions SET observed_host = 'elsewhere.test'"
            " WHERE program_id = $1::uuid",
            "DELETE FROM callback_interactions WHERE program_id = $1::uuid",
            "UPDATE callback_correlators SET expires_at = now() + interval '1 year'"
            " WHERE program_id = $1::uuid",
        ):
            with self.subTest(sql[:6]):
                with self.assertRaises(pg.DatabaseError) as refused:
                    self.connection.execute(sql, (self.identifiers["a"],))

                self.assertEqual("42501", refused.exception.sqlstate)

        observation = self.accepted.facts["callback"]["observation"]
        for sql in (
            "UPDATE observations SET summary = 'something else'"
            " WHERE label = $1 AND program_id = $2::uuid",
            "DELETE FROM observations WHERE label = $1 AND program_id = $2::uuid",
        ):
            with self.subTest(f"observation:{sql[:6]}"):
                with self.assertRaises(pg.DatabaseError) as refused:
                    self.connection.execute(sql, (observation, self.identifiers["a"]))

                self.assertIn("immutable", str(refused.exception))

        self.assertEqual(
            1,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM observations"
                    " WHERE label = $1 AND program_id = $2::uuid",
                    (observation, self.identifiers["a"]),
                ).scalar()
            ),
        )

    def test_what_the_observation_says_names_the_channel_and_not_the_canary(self):
        # The Observation is the one part of this record the agent reads, so it
        # carries the channel, the size and the artifact label -- and neither the
        # correlator nor the name it arrived at. Not a secrecy claim about the
        # correlator, which is printed to the operator: a claim that reading the
        # evidence does not hand a session the label another session's canary is
        # armed at.
        summary, metadata = self.connection.execute(
            "SELECT o.summary, o.metadata::text FROM observations o"
            " WHERE o.label = $1 AND o.program_id = $2::uuid",
            (self.accepted.facts["callback"]["observation"], self.identifiers["a"]),
        ).rows[0]

        self.assertIn("oob-dns", str(summary))
        self.assertIn(str(self.accepted.facts["callback"]["artifact"]), str(summary))
        for text in (summary, metadata):
            self.assertNotIn(self.correlator, str(text))
            self.assertNotIn("dns.example.org", str(text))

    def test_the_event_the_arrival_emitted_carries_no_name_and_no_correlator(self):
        # The log is the other copy of everything, and a redacted column is the
        # only reason the name is not in it twice.
        logged = "".join(
            str(row[0])
            for row in self.connection.execute(
                "SELECT to_jsonb(e)::text FROM events e WHERE e.program_id = $1::uuid",
                (self.identifiers["a"],),
            ).rows
        )

        self.assertIn("callback.observed", logged)
        self.assertNotIn(self.correlator, logged)
        self.assertNotIn(self.minted.facts["callback"]["address"], logged)

    def test_the_agent_connection_reaches_the_observation_and_neither_table(self):
        # Criterion 2's last clause. The Observation is evidence and is read;
        # the correlator and the name it arrived at are neither, and the absence
        # of a `state_read_surface` row is what refuses them.
        with pg.connect(self.harness.state) as session:
            session.execute(
                "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers["a"],)
            )
            visible = session.execute(
                "SELECT summary FROM observations WHERE label = $1",
                (self.accepted.facts["callback"]["observation"],),
            ).scalar()

            for sql in (
                "SELECT correlator_sha256 FROM callback_correlators",
                "SELECT observed_host FROM callback_interactions",
                "SELECT host FROM program_callback_channels",
            ):
                with self.subTest(sql[7:20]):
                    with self.assertRaises(pg.DatabaseError) as refused:
                        session.execute(sql)

                    self.assertEqual("42501", refused.exception.sqlstate)

        self.assertIn("oob-dns", str(visible))

    def test_no_correlator_but_a_live_one_of_this_program_confirms_anything(self):
        # Criterion 4, all four ways. Each is an arrival at a name the policy
        # admits -- so nothing is refused for being off-channel -- carrying a
        # correlator that is not one this Program has live.
        expired = self.mint("a", seconds=0.001)
        cleared = self.mint("a")
        with self.connection.transaction():
            self.connection.execute(
                "SELECT set_config('rk2.program_id', $1, true)", (self.identifiers["a"],)
            )
            self.connection.execute(
                "SELECT clear_callback_correlator(id) FROM callback_correlators"
                " WHERE correlator_sha256 = $1",
                (artifact.digest(cleared.encode()),),
            )
        before = self.counts()

        for reason, token in (
            ("fabricated", secrets.token_hex(16)),
            ("expired", expired),
            ("cleared", cleared),
            ("another Program's", self.mint("b")),
        ):
            with self.subTest(reason):
                result = self.arrive("a", f"{token}.dns.example.org")

                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
                self.assertIn("refused", result.violations[0].detail)

        # And the fifth way, which the command cannot express because a name with
        # no label beneath the endpoint is refused before the database is opened:
        # an arrival stating no correlator at all, put straight to the writer.
        for reason, token in (("empty", ""), ("absent", None)):
            with self.subTest(reason):
                refused = self.refuse(
                    "a",
                    "SELECT record_callback_interaction($1, $2::jsonb, $3::jsonb)",
                    (
                        token,
                        json.dumps({"host": "dns.example.org", "arrival_kind": "dns"}),
                        self.bytes_json(),
                    ),
                )

                self.assertEqual("23514", refused.sqlstate)

        self.assertEqual(before, self.counts())

    def test_a_name_no_channel_admits_is_refused_wherever_it_is_asked(self):
        # Criterion 5, from both ends. The command refuses these without opening
        # a connection, so the interesting half is the database's: the same
        # arrival, put straight to the writer, is refused there too.
        live = self.mint("a")
        before = self.counts()

        for host in (
            "oob.example.net",  # a channel, but another Program's configuration
            "dns.example.org.evil.test",  # adjacent infrastructure
            "example.org",  # the parent the channel is beneath
            "dns.example.org",  # the endpoint itself, carrying no correlator
        ):
            with self.subTest(host):
                self.assertEqual(
                    EXIT_INVALID_CONFIGURATION, self.arrive("a", host).exit_code
                )

        for host in ("elsewhere.test", "dns.example.org.evil.test"):
            with self.subTest(f"writer:{host}"):
                refused = self.refuse(
                    "a",
                    "SELECT record_callback_interaction($1, $2::jsonb, $3::jsonb)",
                    (
                        live,
                        json.dumps({"host": host, "arrival_kind": "dns"}),
                        self.bytes_json(),
                    ),
                )

                self.assertEqual("23514", refused.sqlstate)

        self.assertEqual(before, self.counts())

    def test_an_arrival_carries_the_correlator_it_is_filed_under(self):
        # Criterion 2's binding, which the admitted-name arms do not make. Both
        # correlators here are this Program's and both names are admitted by the
        # same channel, so everything else about this arrival is in order: what
        # is wrong is that the name carries one canary and the row is filed under
        # the other. Without this the Observation would be a true fact about the
        # wrong entity.
        mine, other = self.mint("a"), self.mint("a")
        before = self.counts()

        refused = self.refuse(
            "a",
            "SELECT record_callback_interaction($1, $2::jsonb, $3::jsonb)",
            (
                mine,
                json.dumps(
                    {"host": f"{other}.dns.example.org", "arrival_kind": "dns"}
                ),
                self.bytes_json(),
            ),
        )

        self.assertEqual("23514", refused.sqlstate)
        self.assertIn("does not carry the correlator", str(refused))

        # And beneath the writer, which is where a restore or a fixture arrives.
        beneath = self.refuse(
            "a",
            "INSERT INTO callback_interactions"
            "     (program_id, correlator_id, channel_name, arrival_kind,"
            "      observed_host, body_sha256, byte_size)"
            " SELECT $1::uuid, t.id, 'oob-dns', 'dns', $2, $3, $4::bigint"
            "  FROM callback_correlators t WHERE t.correlator_sha256 = $5",
            (
                self.identifiers["a"],
                f"{other}.dns.example.org",
                artifact.digest(ARRIVAL),
                str(len(ARRIVAL)),
                artifact.digest(mine.encode()),
            ),
        )

        self.assertEqual("23514", beneath.sqlstate)
        self.assertIn("does not carry the correlator", str(beneath))
        self.assertEqual(before, self.counts())

    def test_an_arrival_cannot_backdate_itself_into_a_dead_correlator(self):
        # `received_at` is the row's own column, so an expiry arm that read it
        # would be a guard the guarded row answers. This row states a time the
        # correlator was demonstrably listening -- the instant it was minted --
        # and the clock still says the canary is gone.
        dead = self.mint("a", seconds=0.001)
        before = self.counts()

        refused = self.refuse(
            "a",
            "INSERT INTO callback_interactions"
            "     (program_id, correlator_id, channel_name, arrival_kind,"
            "      observed_host, received_at, body_sha256, byte_size)"
            " SELECT $1::uuid, t.id, 'oob-dns', 'dns', $2, t.issued_at, $3, $4::bigint"
            "  FROM callback_correlators t WHERE t.correlator_sha256 = $5",
            (
                self.identifiers["a"],
                f"{dead}.dns.example.org",
                artifact.digest(ARRIVAL),
                str(len(ARRIVAL)),
                artifact.digest(dead.encode()),
            ),
        )

        self.assertEqual("23514", refused.sqlstate)
        self.assertIn("was not live", str(refused))
        self.assertEqual(before, self.counts())

    def test_a_correlator_that_could_never_arrive_is_not_minted(self):
        # A correlator is one DNS label or it is a canary nothing can query, and
        # the admission trigger compares the digest of the label a name carries:
        # a correlator with a dot in it, or a capital, would be minted and then
        # never match anything that arrived.
        live = int(
            self.connection.execute("SELECT count(*) FROM callback_correlators").scalar()
        )

        for reason, correlator in (
            ("a name rather than a label", "abc.def"),
            ("upper case, which a name is not stored in", "ABC123"),
            ("empty", ""),
            ("longer than a label", "a" * 64),
        ):
            with self.subTest(reason):
                refused = self.refuse(
                    "a",
                    "SELECT mint_callback_correlator($1, $2, $3::uuid,"
                    "                                make_interval(secs => 60))",
                    ("oob-dns", correlator, self.subject("a")),
                )

                self.assertEqual("23514", refused.sqlstate)
                self.assertIn("one lower-case DNS label", str(refused))

        self.assertEqual(
            live,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM callback_correlators"
                ).scalar()
            ),
        )

    def test_a_wildcard_is_not_a_channel_and_never_becomes_a_program(self):
        # The rest of criterion 5. A channel is one host: a wildcard would be a
        # standing invitation to attribute an arrival at anything beneath a
        # domain to this Program, which is the shape of the mistake that lets
        # somebody else's infrastructure produce evidence here.
        slug = f"{CALLBACK_SLUG}-wildcard"
        source = write(
            SCOPED.replace('name = "matrix-web"', f'name = "{slug}"').replace(
                'host = "dns.example.org"', 'host = "*.example.org"'
            )
        )

        opened = program.run(self.harness.runtime, source)

        self.assertFalse(opened.ok)
        self.assertEqual(
            0,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM programs WHERE slug = $1", (slug,)
                ).scalar()
            ),
        )

    def test_a_channel_the_live_policy_withdrew_admits_nothing_it_used_to(self):
        # Criterion 1's teeth, and the reason the channel list is projected per
        # version rather than kept once. A correlator minted while the channel
        # was declared stays in the table -- it is a record of what was armed --
        # and stops admitting anything the moment the operator's next revision
        # goes live.
        live = self.mint("c")
        withdrawn = write(
            SCOPED.replace('name = "matrix-web"', f'name = "{CALLBACK_SLUG}-c"').replace(
                '[[callback]]\nname = "oob-dns"\nkind = "dns"\nhost = "dns.example.org"\n',
                "",
            )
        )

        revised = program.run(self.harness.runtime, withdrawn, accept_change=True)

        self.assertTrue(revised.ok, revised.violations)
        self.assertEqual(1, revised.facts["scope"]["callback_channels"])
        arriving = self.refuse(
            "c",
            "SELECT record_callback_interaction($1, $2::jsonb, $3::jsonb)",
            (
                live,
                json.dumps({"host": f"{live}.dns.example.org", "arrival_kind": "dns"}),
                self.bytes_json(),
            ),
        )
        minting = self.refuse(
            "c",
            "SELECT mint_callback_correlator('oob-dns', $1, $2::uuid, interval '1 hour')",
            (secrets.token_hex(16), self.subject("c")),
        )

        self.assertEqual("23514", arriving.sqlstate)
        self.assertEqual("23514", minting.sqlstate)

    def test_the_gate_still_holds_over_the_rows_these_writes_made(self):
        with pg.connect(self.harness.migrate) as connection:
            result = integrity.verify(connection, self.harness.expected)

        self.assertTrue(result.ok, result.violations)


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


class HeldTarget(Target):
    """A counterparty that answers only once the test lets go of it.

    Concurrency is the one limit that cannot be shown against a target which
    answers immediately: two fast requests are two sequential requests, and a
    door that allowed both would be right to. So one request is parked here,
    inside the exchange and holding its slot, while the second is made.

    The gate is a class attribute because the handler is constructed per request
    and there is nothing to hand it one through. It starts set, so a stray
    request never hangs the suite; a test that wants a request parked clears it
    and sets it again.
    """

    answer = ANSWER
    release = threading.Event()
    release.set()

    def do_GET(self) -> None:
        HeldTarget.release.wait(timeout=30)
        super().do_GET()

    do_POST = do_GET
    do_HEAD = do_GET


#: The `[budgets]` block `SCOPED` carries, so that a Program built from it can be
#: given a different one. Matched as the whole block rather than line by line: a
#: partial replacement would leave a document whose limits half agree.
SCOPED_BUDGETS = (
    "requests = 100\ntokens = 10000\nconcurrency = 1\nburst = 100\nwindow_seconds = 60"
)

#: What every Program in the suite below gets unless it is a Program about
#: budgets. Wide on purpose: a limit shared by tests that are not about it is a
#: limit that makes adding an unrelated test break an unrelated assertion, and
#: `SCOPED` is tight enough that the suite would run into its own ceiling.
WIDE_ENOUGH = (
    "requests = 500\ntokens = 10000\nconcurrency = 4\nburst = 500\nwindow_seconds = 3600"
)

#: And the Programs that exist to be stopped, each named for the limit it hits.
#: A window of an hour against a burst of two is a refill of one token every half
#: hour, which is what makes `throttle` a test of the limit rather than of how
#: fast the suite runs.
BUDGETS = {
    "budget": (
        "requests = 2\ntokens = 10000\nconcurrency = 4\nburst = 500\nwindow_seconds = 3600"
    ),
    "throttle": (
        "requests = 500\ntokens = 10000\nconcurrency = 4\nburst = 2\nwindow_seconds = 3600"
    ),
    "concurrent": (
        "requests = 500\ntokens = 10000\nconcurrency = 1\nburst = 500\nwindow_seconds = 3600"
    ),
    "race": (
        "requests = 3\ntokens = 10000\nconcurrency = 8\nburst = 500\nwindow_seconds = 3600"
    ),
    "halted": (
        "requests = 500\ntokens = 10000\nconcurrency = 4\nburst = 500\nwindow_seconds = 3600"
    ),
}


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
        cls.human = pg.connect(cls.harness.human)
        cls.root = scratch() / "proxy-store"

        cls.identifiers = {}
        cls.configurations = {}
        # `shared` is where the exchanges that spend one capability more than once
        # live, kept apart from `a` because those are counted: a suite that
        # asserts "two Receipts and no more" under the Program every other test
        # uses is a suite where adding a test breaks an unrelated one.
        for name in (
            "a",
            "b",
            "retired",
            "shared",
            "credential",
            "lease",
            "other",
            "slot-reference",
            "reused-bytes",
            "sealed-first",
            "identity-audit",
            "identity-revision",
            "mtls",
            # The queue cases park questions and leave some of them open across a
            # sweep, and a sweep is machine-wide. Their own Program keeps that out
            # of the counting assertions the exchanges above make.
            "decision",
            *BUDGETS,
        ):
            source = SCOPED + "\n[[identity]]\nname = \"member\"\nslot_ref = \"slot://identity/member\"\n"
            source = source.replace(SCOPED_BUDGETS, BUDGETS.get(name, WIDE_ENOUGH))
            path = write(source.replace('name = "matrix-web"', f'name = "{PROXY_SLUG}-{name}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]

        cls.target, _ = counterparty(LiveTarget)
        cls.parked, _ = counterparty(HeldTarget)
        cls.secure_target, _, cls.target_ca = tls_counterparty(LiveTarget)
        cls.authority = tls.authority(scratch() / "door-authority")
        # One installation has one root.  The sealed-artifact case later in
        # this module deliberately uses the same material against the key
        # generation this proxy may establish first.
        cls.root_secret = seal.Root(Path("live-proxy-selftest-root"), SECRET)

        # Every configuration above declares `X-Bounty-Id`, and a declared header
        # with no provisioned value is a request the door refuses before it dials.
        # So the value exists here for the same reason the target does: the thing
        # under test is what reaches the wire, and a Program that cannot reach it
        # tests nothing. `bounty-id` is the marker the header assertions look for.
        cls.bounty_id = "rk2-selftest-bounty-9c4e17"
        value = scratch() / "bounty-id.txt"
        value.write_text(cls.bounty_id, encoding="utf-8")
        for name, path in cls.configurations.items():
            sealed = header.provision(
                cls.harness.runtime,
                path,
                "X-Bounty-Id",
                value,
                root_secret=cls.root_secret,
            )
            assert sealed.ok, (name, sealed.violations)

        cls.resolved = []
        cls.dialled = []
        # What `connect` would have read off the socket towards an https target,
        # stated by the fixture because the connection `dial` hands back has not
        # been dialled yet. The values are the shape of a target whose
        # certificate does not chain to a public root -- which is what this
        # machine's target is -- so a Receipt written from them says the door
        # reached it without verifying it, and every field differs from the
        # forged leaf the agent saw on the other side of the tunnel.
        cls.upstream = proxy.Handshake(
            tls_version="TLSv1.3",
            cipher="TLS_AES_128_GCM_SHA256",
            alpn="http/1.1",
            sni="app.example.com",
            cert_sha256="f" * 64,
            cert_issuer=None,
            cert_subject=None,
            cert_not_after=None,
            chain_verified=False,
            hostname_verified=False,
            defect="[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate",
        )
        cls.fence = proxy.Fence(pg.connect(cls.harness.proxy))
        cls.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=cls.fence,
            store=Store(cls.root),
            connector=cls.dial,
            resolver=cls.look_up,
            authority=cls.authority,
            root_secret=cls.root_secret,
        )
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.proxy_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

        # The one exchange every criterion but the fifth is read from. Run once,
        # in setup, because it commits: repeating it per test would multiply the
        # Receipts the counting assertions are about.
        cls.sent = proxy.send(
            cls.harness.runtime, cls.configurations["a"], URL, proxy_url=cls.proxy_url
        )
        # What arrived for that one exchange, held rather than looked up later:
        # the target is shared, so "the last thing it saw" is whatever test ran
        # most recently, and the request this report is about is this one.
        cls.arrived = cls.target.seen[-1]
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
        cls.parked.shutdown()
        cls.parked.server_close()
        cls.secure_target.shutdown()
        cls.secure_target.server_close()
        cls.runtime.close()
        cls.human.close()

        stored = [
            str(row[0])
            for row in cls.connection.execute(
                "SELECT DISTINCT unnest(ARRAY[request_agent_sha, response_agent_sha,"
                "                             request_wire_sha, response_wire_sha])"
                "  FROM receipts r JOIN programs p ON p.id = r.program_id"
                " WHERE p.slug LIKE $1",
                (f"{PROXY_SLUG}-%",),
            ).rows
            if row[0] is not None
        ]
        ciphertexts = [
            str(row[0])
            for row in cls.connection.execute(
                "SELECT s.ciphertext_sha256 FROM artifact_seal s JOIN programs p"
                "    ON p.id = s.scope_id AND s.scope_kind = 'program'"
                " WHERE p.slug LIKE $1",
                (f"{PROXY_SLUG}-%",),
            ).rows
        ]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM secret_access_log WHERE program_id IN"
                " (SELECT id FROM programs WHERE slug LIKE $1)",
                (f"{PROXY_SLUG}-%",),
            )
            cls.connection.execute(
                "DELETE FROM artifact_seal WHERE scope_kind = 'program' AND scope_id IN"
                " (SELECT id FROM programs WHERE slug LIKE $1)",
                (f"{PROXY_SLUG}-%",),
            )
            cls.connection.execute("DELETE FROM programs WHERE slug LIKE $1", (f"{PROXY_SLUG}-%",))
            if stored:
                cls.connection.execute(
                    "DELETE FROM artifacts WHERE sha256 = ANY($1)",
                    ("{" + ",".join(stored) + "}",),
                )
        keep = Store(cls.root)
        for sha256 in (*stored, *ciphertexts):
            keep.discard(sha256)
        super().tearDownClass()

    #: What `look_up` answers. Mutable, because the resolver the server holds was
    #: bound once in setup: a test that needs a different answer changes what the
    #: resolver reads rather than which resolver runs.
    answers = (PINNED,)

    #: Whether http exchanges reach the target that answers or the one that
    #: waits. Read by `dial` for the same reason `answers` is read by `look_up`:
    #: the connector was bound once, in setup.
    holding = False

    @classmethod
    def look_up(cls, host: str, port: int) -> tuple[str, ...]:
        """What the names in this suite resolve to, without asking a real zone.

        A lookup is a packet leaving the machine, so a suite that let this reach
        the operator's resolver would be testing the operator's DNS. What it
        answers is a public address, because the point of the pin is that the
        door refuses anything else.
        """
        cls.resolved.append((host, port))
        return cls.answers

    @classmethod
    def dial(
        cls,
        host: str,
        port: int,
        timeout: float,
        protocol: str,
        address: str,
        client_certificate: identity.ClientCertificate | None,
    ) -> tuple[http.client.HTTPConnection, proxy.Handshake | None]:
        """Every authorised name reaches the one target this machine is running.

        One target per protocol, because the door's outbound side is not the same
        socket for the two: an https target is verified by the door itself, which
        is the half of interception the agent can no longer do for itself.

        The `address` the door pinned is recorded rather than dialled: what it
        proves is that the socket was opened at the address the database decided
        and not at the name, and no test on this machine can route to the real
        one. Everything before this point -- resolution, routability, the second
        decision -- happened for real.
        """
        cls.dialled.append((host, port, protocol, address))
        if protocol == "http" and cls.holding:
            return http.client.HTTPConnection(
                "127.0.0.1", cls.parked.server_address[1], timeout=timeout
            ), None
        if protocol == "https":
            context = ssl.create_default_context(cafile=str(cls.target_ca))
            if client_certificate is not None:
                client_certificate.install(context)
            return http.client.HTTPSConnection(
                "127.0.0.1",
                cls.secure_target.server_address[1],
                timeout=timeout,
                context=context,
            ), cls.upstream
        return http.client.HTTPConnection(
            "127.0.0.1", cls.target.server_address[1], timeout=timeout
        ), None

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

    def answered(
        self,
        capability: str | None,
        program_id: str | None,
        url: str = URL,
        method: str = "GET",
        port: int | None = None,
    ) -> http.client.HTTPResponse:
        """One request at the door, and the whole answer it came back with.

        The `port` is a parameter because a Program's limits are not one door's:
        the arms that prove that send half their requests at a second door with a
        fence of its own, and the only thing that differs between them is this.
        """
        headers = {}
        if capability is not None:
            headers[proxy.AUTHORIZATION] = f"RedKraken {capability}"
        if program_id is not None:
            headers[proxy.PROGRAM] = program_id
        client = http.client.HTTPConnection(
            "127.0.0.1", port or self.server.server_address[1], timeout=proxy.TIMEOUT
        )
        try:
            client.request(method, url, headers=headers)
            answer = client.getresponse()
            answer.read()
            return answer
        finally:
            client.close()

    def attempt(
        self,
        capability: str | None,
        program_id: str | None,
        url: str = URL,
        method: str = "GET",
        port: int | None = None,
    ) -> tuple[int, str | None]:
        """The two fields most arms read out of that answer."""
        answer = self.answered(capability, program_id, url, method, port)
        return answer.status, answer.headers.get(proxy.DECISION)

    def leased(
        self,
        name: str,
        identity_label: str | None = None,
        *,
        approval_ready: bool = False,
    ) -> tuple[str, str, str]:
        """A capability whose run holds a task lease, the way a subagent's does.

        `mint` imitates the operator path, and that path has no task -- nor may
        it: `agent_runs_kind_with_task` and the role roster make the
        orchestrator's lack of one a constraint rather than a habit. The lease is
        the fourth thing a capability hangs from and the only one the rest of
        this suite cannot reach, so getting to it means opening the run the
        scheduler would have opened: a recon subagent under a claimed task.

        The task is written by the owner because granting a lease is the
        scheduler's, and neither the runtime nor the proxy may write one.
        """
        task = self.owned(
            "INSERT INTO tasks (program_id, kind, status, claimed_at, lease_expires_at)"
            " VALUES ($1::uuid, 'recon', 'claimed', now(), now() + interval '10 minutes')"
            " RETURNING id::text",
            (self.identifiers[name],),
        )
        self.runtime.execute(proxy.BIND, (self.identifiers[name],))
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            run = self.runtime.execute(
                "INSERT INTO agent_runs (program_id, task_id, role, kind, runs_as, model,"
                " effort, mission_packet)"
                " VALUES ($1::uuid, $2::uuid, 'recon', 'recon', 'subagent', 'operator',"
                " 'low', $3::jsonb) RETURNING id::text",
                (self.identifiers[name], task, json.dumps({"command": "selftest"})),
            ).scalar()
            opened = self.runtime.execute(
                "INSERT INTO tool_runs (program_id, agent_run_id, task_id, tool, args, status,"
                " transport) VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb, 'running',"
                " 'runtime') RETURNING id::text",
                (
                    self.identifiers[name],
                    str(run),
                    task,
                    proxy.TOOL,
                    json.dumps(
                        {
                            "url": URL,
                            "method": "GET",
                            "identity_slot": identity_label or "",
                        }
                    ),
                ),
            ).scalar()
        if identity_label is not None:
            self.owner(
                "INSERT INTO identity_leases"
                " (program_id, identity_entity_id, holder_agent_run_id, expires_at)"
                " SELECT $1::uuid, i.entity_id, $2::uuid, now() + interval '10 minutes'"
                "   FROM identities i"
                "  WHERE i.program_id = $1::uuid AND i.slot_name = $3"
                "    AND i.invalidated_at IS NULL",
                (self.identifiers[name], str(run), identity_label),
            )
        gate = self.runtime.execute(proxy.AUTHORIZE_TOOL_RUN, (str(opened),)).scalar()
        answer = json.loads(gate) if isinstance(gate, str) else dict(gate)
        capability = answer.get("capability")
        if capability is None and identity_label is not None and not approval_ready:
            self.assertEqual("ask", answer.get("decision"))
            decision = str(
                self.runtime.execute(
                    "SELECT park_for_human($1::uuid, interval '10 minutes')",
                    (str(opened),),
                ).scalar()
            )
            self.human.execute(proxy.BIND, (self.identifiers[name],))
            with self.human.transaction():
                self.human.execute(
                    "SELECT answer_decision($1, 'approved', 'selftest leased Identity',"
                    " interval '10 minutes')",
                    (decision,),
                )
            self.owner(
                "UPDATE tasks SET status = 'abandoned', abandoned_reason = 'answered',"
                " finished_at = now() WHERE id = $1::uuid",
                (task,),
            )
            return self.leased(name, identity_label, approval_ready=True)
        self.assertIsNotNone(capability, f"the gate answered {answer.get('decision')}")
        return str(capability), str(opened), task

    def resolving_to(self, *addresses: str) -> None:
        """Point every name at these addresses, for the length of one test."""
        self.addCleanup(setattr, type(self), "answers", type(self).answers)
        type(self).answers = addresses

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

    def latest(self, name: str) -> tuple[str, str, object]:
        """The newest Receipt a Program has: its verdict, reason and retry time."""
        row = self.connection.execute(
            "SELECT decision, reason, retry_after FROM receipts"
            " WHERE program_id = $1::uuid ORDER BY ts_arrival DESC LIMIT 1",
            (self.identifiers[name],),
        ).rows[0]
        return str(row[0]), str(row[1]), row[2]

    def spent(self, name: str) -> tuple[int, int]:
        """What the Program's own row says it contacted, and was refused after."""
        rows = self.connection.execute(
            "SELECT contacted, exhausted FROM program_egress_spend"
            " WHERE program_id = $1::uuid",
            (self.identifiers[name],),
        ).rows
        return (int(rows[0][0]), int(rows[0][1])) if rows else (0, 0)

    def parking(self) -> None:
        """Send http exchanges to the target that waits, for one test.

        Both halves are undone on the way out, and the gate is set again rather
        than left cleared: a class attribute a failing test leaves behind would
        park every later exchange in the suite for thirty seconds each.
        """
        self.addCleanup(HeldTarget.release.set)
        self.addCleanup(setattr, type(self), "holding", type(self).holding)
        type(self).holding = True
        HeldTarget.release.clear()

    def another_door(self) -> proxy.Server:
        """A second door, on a fence and a database session of its own.

        What makes the aggregate arms mean anything. Two doors that share a
        Program share its budget or they do not, and a suite that only ever ran
        one could not tell a limit from a counter in a process.
        """
        fence = proxy.Fence(pg.connect(self.harness.proxy))
        server = proxy.listen(
            ("127.0.0.1", 0),
            fence=fence,
            store=Store(self.root),
            connector=self.dial,
            resolver=self.look_up,
            authority=self.authority,
            root_secret=self.root_secret,
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(fence.close)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

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

    def test_identity_provisioning_leaves_only_an_encrypted_control_side_slot(self):
        marker = "rk2-provisioned-bearer-6d28ea"
        client_key_marker = "rk2-private-client-key-25b7c4"
        material = scratch() / "identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "https://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {marker}"}
                            ],
                            "cookies": [],
                            "client_certificate": {
                                "certificate_pem": (
                                    "-----BEGIN CERTIFICATE-----\nfixture\n"
                                    "-----END CERTIFICATE-----\n"
                                ),
                                "private_key_pem": (
                                    "-----BEGIN PRIVATE KEY-----\n"
                                    f"{client_key_marker}\n"
                                    "-----END PRIVATE KEY-----\n"
                                ),
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["b"],
            "member",
            material,
            root_secret=self.root_secret,
        )

        self.assertTrue(provisioned.ok, provisioned.violations)
        self.assertEqual(1, provisioned.facts["identity"]["revision"])
        row = self.connection.execute(
            "SELECT s.revision, s.alg, encode(s.envelope, 'hex'), s.byte_size"
            "  FROM identity_slots s JOIN identities i ON i.entity_id = s.identity_entity_id"
            " WHERE s.program_id = $1::uuid AND i.slot_name = 'member'",
            (self.identifiers["b"],),
        ).rows[0]
        self.assertEqual(1, int(row[0]))
        self.assertEqual(seal.ALG, str(row[1]))
        self.assertNotIn(marker.encode().hex(), str(row[2]))
        self.assertNotIn(client_key_marker.encode().hex(), str(row[2]))
        self.assertGreater(int(row[3]), len(marker))
        for secret in (marker, client_key_marker):
            self.assertEqual(
                (),
                self.connection.execute(
                    "SELECT relation, attribute FROM find_in_database($1) WHERE hits > 0",
                    (secret,),
                ).rows,
            )
            self.assertNotIn(secret, json.dumps(provisioned.as_dict()))
        self.assertFalse(
            self.connection.execute(
                "SELECT has_table_privilege('rk2_state', 'identity_slots', 'SELECT')"
            ).scalar()
        )
        self.assertFalse(
            self.connection.execute(
                "SELECT has_function_privilege("
                " 'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')"
            ).scalar()
        )
        for signature in (
            "record_proxy_exchange(text,jsonb,jsonb)",
            "record_proxy_exchange(text,jsonb,jsonb,jsonb)",
        ):
            with self.subTest(signature=signature):
                self.assertFalse(
                    self.connection.execute(
                        "SELECT has_function_privilege('rk2_proxy', $1, 'EXECUTE')",
                        (signature,),
                    ).scalar()
                )

    def test_normalized_identity_state_is_refused_without_crashing_provisioning(self):
        material = scratch() / "oversized-normalized-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "https://app.example.com/",
                            "headers": [],
                            "cookies": [f"cookie{index}=x" for index in range(6_000)],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = identity.provision(
            self.harness.runtime,
            self.configurations["b"],
            "member",
            material,
            root_secret=self.root_secret,
        )

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertIn("slot plaintext exceeds", result.violations[0].detail)

    def test_an_identity_client_certificate_hash_is_persisted_in_its_receipt(self):
        client = tls.authority(scratch() / "persisted-client-identity")
        credential = identity.ClientCertificate(
            client.certificate.read_text(encoding="utf-8"),
            client.key.read_text(encoding="utf-8"),
        )
        material = scratch() / "persisted-client-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "https://app.example.com/",
                            "headers": [],
                            "cookies": [],
                            "client_certificate": {
                                "certificate_pem": credential.certificate_pem,
                                "private_key_pem": credential.private_key_pem,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["mtls"],
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)
        capability, tool_run, _ = self.leased("mtls", "member")
        previous = LiveTarget.response_headers
        LiveTarget.response_headers = (("X-Identity-Fixture", "mtls-evidence"),)
        try:
            status, decision = self.attempt(
                capability, self.identifiers["mtls"], url=SECURE
            )
        finally:
            LiveTarget.response_headers = previous

        self.assertEqual((200, None), (status, decision))
        persisted = self.connection.execute(
            "SELECT identity_tls_cert_sha256 FROM receipts"
            " WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
            (tool_run,),
        ).scalar()
        self.assertEqual(credential.public_sha256(), str(persisted))

    def test_a_configuration_change_invalidates_the_stale_identity_ciphertext(self):
        name = "slot-reference"
        path = self.configurations[name]
        material = scratch() / "slot-reference.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "https://app.example.com/",
                            "headers": [{"name": "X-Api-Key", "value": "stale-secret"}],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            path,
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)

        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "slot://identity/member", "slot://identity/replacement"
            ),
            encoding="utf-8",
        )
        revised = program.run(self.harness.runtime, path, accept_change=True)

        self.assertTrue(revised.ok, revised.violations)
        self.assertEqual(
            1,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM identity_slots WHERE program_id = $1::uuid",
                    (self.identifiers[name],),
                ).scalar()
            ),
        )
        binding, current = self.connection.execute(
            "SELECT s.binding_revision, (e.metadata ->> 'configuration_revision')::bigint"
            "  FROM identity_slots s JOIN entities e ON e.id = s.identity_entity_id"
            " WHERE s.program_id = $1::uuid",
            (self.identifiers[name],),
        ).rows[0]
        self.assertNotEqual(int(binding), int(current))

        capability, _, _ = self.leased(name, "member")
        before = len(self.target.seen)
        attempted = self.attempt(capability, self.identifiers[name])
        reasons = self.connection.execute(
            "SELECT decision, reason FROM receipts WHERE program_id = $1::uuid"
            " ORDER BY ts_arrival DESC LIMIT 3",
            (self.identifiers[name],),
        ).rows
        self.assertEqual(
            (407, proxy.REFUSED), attempted
        )
        self.assertEqual((("blocked", "identity slot refused"),), reasons)
        self.assertEqual(before, len(self.target.seen))

    def test_root_checks_and_failed_identity_opens_are_audited_at_their_real_outcome(self):
        name = "identity-audit"
        path = self.configurations[name]
        material = scratch() / "identity-audit.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [{"name": "Authorization", "value": "Bearer audit"}],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            path,
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)
        wrong = identity.provision(
            self.harness.runtime,
            path,
            "member",
            material,
            root_secret=seal.Root(Path("wrong-identity-root"), b"w" * seal.KEY_BYTES),
        )
        self.assertFalse(wrong.ok)
        rootchecks = [
            (str(row[0]), str(row[1]))
            for row in self.connection.execute(
                "SELECT operation_id, string_agg(outcome, ',' ORDER BY at, id)"
                " FROM secret_access_log"
                " WHERE program_id = $1::uuid AND verb = 'rootcheck'"
                "   AND field = 'identity_slot'"
                " GROUP BY operation_id ORDER BY min(at), operation_id",
                (self.identifiers[name],),
            ).rows
        ]
        self.assertEqual(2, len(rootchecks))
        self.assertEqual(["attempted,ok", "attempted,denied"], [row[1] for row in rootchecks])

        capability, tool_run, _ = self.leased(name, "member")
        previous_root = self.server.root_secret
        before = len(self.target.seen)
        # A wrong root at the door breaks the required header too, and the order
        # is what this asserts: the Identity is opened first, so its refusal is
        # the one that comes back and the header is never reached.
        self.server.root_secret = seal.Root(
            Path("wrong-proxy-identity-root"), b"z" * seal.KEY_BYTES
        )
        try:
            status, decision = self.attempt(capability, self.identifiers[name])
        finally:
            self.server.root_secret = previous_root

        self.assertEqual((502, proxy.REFUSED), (status, decision))
        self.assertEqual(before, len(self.target.seen))
        audit = self.connection.execute(
            "SELECT count(DISTINCT operation_id),"
            "       string_agg(outcome, ',' ORDER BY at, id)"
            "  FROM secret_access_log"
            " WHERE tool_run_id = $1::uuid AND verb = 'open_identity'",
            (tool_run,),
        ).rows[0]
        self.assertEqual(1, int(audit[0]))
        self.assertEqual("attempted,denied", str(audit[1]))

    def test_a_stale_identity_revision_refuses_even_when_no_cookie_changed(self):
        name = "identity-revision"
        path = self.configurations[name]
        material = scratch() / "identity-revision.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [{"name": "Authorization", "value": "Bearer first"}],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        first = identity.provision(
            self.harness.runtime,
            path,
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(first.ok, first.violations)
        capability, _, _ = self.leased(name, "member")
        binding = self.fence.open_identity(
            self.identifiers[name],
            capability,
            str(
                self.connection.execute(
                    "SELECT entity_id::text FROM identities"
                    " WHERE program_id = $1::uuid AND slot_name = 'member'",
                    (self.identifiers[name],),
                ).scalar()
            ),
            "member",
            self.root_secret,
        )
        material.write_text(
            material.read_text(encoding="utf-8").replace("Bearer first", "Bearer second"),
            encoding="utf-8",
        )
        second = identity.provision(
            self.harness.runtime,
            path,
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(second.ok, second.violations)

        with pg.connect(self.harness.proxy) as session:
            session.execute(proxy.BIND, (self.identifiers[name],))
            with self.assertRaises(pg.DatabaseError) as raised:
                session.execute(
                    "SELECT record_identity_proxy_exchange("
                    "$1, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, $2, $3, NULL)",
                    (capability, binding.label, binding.revision),
                )

        self.assertIn("revision changed during exchange", str(raised.exception))

    def test_a_live_identity_lease_injects_and_persists_a_private_session(self):
        credential = "rk2-identity-bearer-f237c9"
        cookie = "rk2-identity-cookie-6b0a41"
        material = scratch() / "leased-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {credential}"}
                            ],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["credential"],
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)

        previous = LiveTarget.response_headers
        LiveTarget.response_headers = (("Set-Cookie", f"session={cookie}; Path=/; HttpOnly"),)
        self.addCleanup(setattr, LiveTarget, "response_headers", previous)
        capability, tool_run, _ = self.leased("credential", "member")
        first_seen = len(self.target.seen)
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=proxy.TIMEOUT
        )
        try:
            client.request(
                "GET",
                URL,
                headers={
                    proxy.AUTHORIZATION: f"RedKraken {capability}",
                    proxy.PROGRAM: self.identifiers["credential"],
                },
            )
            answer = client.getresponse()
            answer.read()
            self.assertEqual(200, answer.status)
            self.assertIsNone(answer.headers.get("Set-Cookie"))
        finally:
            client.close()

        LiveTarget.response_headers = ()
        self.assertEqual(
            (200, None),
            self.attempt(capability, self.identifiers["credential"]),
        )
        first_headers = dict(self.target.seen[first_seen][2])
        second_headers = dict(self.target.seen[first_seen + 1][2])
        self.assertEqual(f"Bearer {credential}", first_headers.get("authorization"))
        self.assertIsNone(first_headers.get("cookie"))
        self.assertEqual(f"Bearer {credential}", second_headers.get("authorization"))
        self.assertIn(f"session={cookie}", second_headers.get("cookie", ""))

        rows = self.connection.execute(
            "SELECT r.identity_entity_id::text, r.request_agent_sha, r.request_wire_sha,"
            "       r.response_agent_sha, r.response_wire_sha,"
            "       s.ciphertext_sha256, s.kek_gen, encode(k.salt, 'hex')"
            "  FROM receipts r"
            "  JOIN artifact_seal s ON s.sha256 = r.request_wire_sha"
            "  JOIN secret_kek k ON k.gen = s.kek_gen"
            " WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'"
            " ORDER BY r.ts_arrival, r.label",
            (tool_run,),
        ).rows
        self.assertEqual(2, len(rows))
        self.assertEqual(1, len({str(row[0]) for row in rows}))
        for row in rows:
            agent_sha, wire_sha, ciphertext_sha = map(str, (row[1], row[2], row[5]))
            self.assertNotEqual(agent_sha, wire_sha)
            visible = Store(self.root).load(agent_sha)
            self.assertNotIn(credential.encode(), visible)
            self.assertNotIn(cookie.encode(), visible)
            envelope = Store(self.root).load(ciphertext_sha)
            generation = int(row[6])
            opened = seal.unseal(
                self.root_secret.program_key(
                    bytes.fromhex(str(row[7])),
                    generation=generation,
                    program_id=self.identifiers["credential"],
                ),
                seal.Sealed.decode(envelope),
                aad=seal.associated_data(
                    program_id=self.identifiers["credential"],
                    sha256=wire_sha,
                    generation=generation,
                ),
            )
            self.assertIn(credential.encode(), opened)

        slot = self.connection.execute(
            "SELECT s.revision, encode(s.envelope, 'hex')"
            "  FROM identity_slots s JOIN identities i ON i.entity_id = s.identity_entity_id"
            " WHERE s.program_id = $1::uuid AND i.slot_name = 'member'",
            (self.identifiers["credential"],),
        ).rows[0]
        self.assertEqual(2, int(slot[0]), "the first response persisted its cookie jar")
        self.assertNotIn(credential.encode().hex(), str(slot[1]))
        self.assertNotIn(cookie.encode().hex(), str(slot[1]))
        for secret in (credential, cookie):
            self.assertFalse(
                self.connection.execute("SELECT * FROM find_in_database($1)", (secret,)).rows
            )

    def test_an_authenticated_fetch_of_bytes_the_agent_already_read_is_recorded(self):
        # The wire view of an authenticated exchange is the target's message
        # unaltered, and that is exactly what an anonymous exchange stores as
        # its Agent artifact. Artifacts are content-addressed and a row is
        # either Agent-visible or credential-bearing, so sealing the same bytes
        # a second time under the other classification has nowhere to go: the
        # exchange happened, the target answered, and the Receipt would not
        # write. Fetching a page anonymously and then with an Identity is
        # ordinary hunting, so this is the ordinary case, not a corner.
        marker = "rk2-reused-bytes-4c81ab"
        material = scratch() / "reused-bytes-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {marker}"}
                            ],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["reused-bytes"],
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)

        previous = LiveTarget.response_headers
        LiveTarget.response_headers = ()
        self.addCleanup(setattr, LiveTarget, "response_headers", previous)
        # `Date` is the one part of this target's answer that changes between two
        # requests, and it changes once a second. Left alone it would make the
        # collision this test is about depend on which side of a second boundary
        # the two exchanges landed, which is a coin flip and not a test.
        steady = mock.patch.object(
            LiveTarget,
            "date_time_string",
            lambda self, timestamp=None: "Tue, 11 Aug 2026 09:00:00 GMT",
        )
        steady.start()
        self.addCleanup(steady.stop)

        anonymous, plain_run, plain_task = self.leased("reused-bytes")
        self.assertEqual(
            (200, None), self.attempt(anonymous, self.identifiers["reused-bytes"])
        )
        # The anonymous read is over, and a Program may hold one live recon task
        # at a time, so it is closed the way the scheduler closes one it has an
        # answer for. The second read is a second task by construction: nothing
        # about this exchange carries over except the bytes.
        self.owner(
            "UPDATE tasks SET status = 'abandoned', abandoned_reason = 'answered',"
            " finished_at = now() WHERE id = $1::uuid",
            (plain_task,),
        )
        plain_sha = str(
            self.connection.execute(
                "SELECT response_agent_sha FROM receipts"
                " WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
                (plain_run,),
            ).scalar()
        )

        capability, tool_run, _ = self.leased("reused-bytes", "member")
        self.assertEqual(
            (200, None), self.attempt(capability, self.identifiers["reused-bytes"])
        )
        self.assertEqual(
            f"Bearer {marker}", dict(self.target.seen[-1][2]).get("authorization")
        )

        rows = self.connection.execute(
            "SELECT r.identity_entity_id IS NOT NULL, r.request_wire_sha IS NOT NULL,"
            "       r.response_agent_sha, r.response_wire_sha"
            "  FROM receipts r"
            " WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'",
            (tool_run,),
        ).rows
        self.assertEqual(1, len(rows))
        authenticated, request_sealed, response_agent_sha, response_wire_sha = rows[0]
        self.assertTrue(authenticated)
        # The request still carries the credential the Agent never sent, so that
        # direction is still transformed and still sealed.
        self.assertTrue(request_sealed)
        # The response direction is not: these bytes came back once already
        # without the credential, so there is nothing in them to withhold and
        # nothing to pair a ciphertext of the Program's own plaintext with.
        self.assertEqual(plain_sha, str(response_agent_sha))
        self.assertIsNone(response_wire_sha)

    def test_an_anonymous_fetch_of_bytes_an_identity_sealed_is_still_recorded(self):
        # The same collision in the order the store cannot answer. The Identity
        # exchange goes first and seals its wire view; the anonymous one then
        # returns those same bytes and has to file them as an Agent artifact,
        # which the row -- classified credential-bearing by the seal -- cannot
        # be. The store holds only the envelope, so nothing on this side of the
        # database could see it coming, and the exchange that could not be
        # recorded is an ordinary unauthenticated GET.
        marker = "rk2-sealed-first-7d2fe0"
        material = scratch() / "sealed-first-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {marker}"}
                            ],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["sealed-first"],
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)

        previous = LiveTarget.response_headers
        LiveTarget.response_headers = ()
        self.addCleanup(setattr, LiveTarget, "response_headers", previous)
        # A date of this case's own, for the reason the other case pins one and
        # so that the two cases cannot reach each other's bytes: this one needs
        # the Identity exchange to seal, which is the opposite of what happens
        # when the same message is already in the store.
        steady = mock.patch.object(
            LiveTarget,
            "date_time_string",
            lambda self, timestamp=None: "Wed, 12 Aug 2026 10:00:00 GMT",
        )
        steady.start()
        self.addCleanup(steady.stop)

        capability, tool_run, task = self.leased("sealed-first", "member")
        self.assertEqual(
            (200, None), self.attempt(capability, self.identifiers["sealed-first"])
        )
        sealed = self.connection.execute(
            "SELECT r.response_wire_sha, a.visibility, a.encrypted"
            "  FROM receipts r JOIN artifacts a ON a.sha256 = r.response_wire_sha"
            " WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'",
            (tool_run,),
        ).rows[0]
        self.assertEqual(("credential_bearing", True), (str(sealed[1]), bool(sealed[2])))
        self.owner(
            "UPDATE tasks SET status = 'abandoned', abandoned_reason = 'answered',"
            " finished_at = now() WHERE id = $1::uuid",
            (task,),
        )

        anonymous, plain_run, _ = self.leased("sealed-first")
        self.assertEqual(
            (200, None), self.attempt(anonymous, self.identifiers["sealed-first"])
        )
        self.assertIsNone(dict(self.target.seen[-1][2]).get("authorization"))

        plain = self.connection.execute(
            "SELECT r.response_agent_sha, r.response_wire_sha, a.visibility, a.encrypted"
            "  FROM receipts r JOIN artifacts a ON a.sha256 = r.response_agent_sha"
            " WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'",
            (plain_run,),
        ).rows[0]
        self.assertEqual(("agent_visible", False), (str(plain[2]), bool(plain[3])))
        self.assertIsNone(plain[1])
        # The two exchanges answered with the same message and are not the same
        # document: the sealed one names the exchange that carried it, so the
        # anonymous read has a hash of its own to be readable under.
        self.assertNotEqual(str(sealed[0]), str(plain[0]))
        self.assertIn(ANSWER, Store(self.root).load(str(plain[0])))

    def test_an_identity_cannot_be_shared_crossed_or_used_after_its_lease_expires(self):
        marker = "rk2-exclusive-identity-91b7fd"
        material = scratch() / "exclusive-identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "http://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {marker}"}
                            ],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        provisioned = identity.provision(
            self.harness.runtime,
            self.configurations["lease"],
            "member",
            material,
            root_secret=self.root_secret,
        )
        self.assertTrue(provisioned.ok, provisioned.violations)
        capability, tool_run, _ = self.leased("lease", "member")

        before = len(self.target.seen)
        self.assertEqual((200, None), self.attempt(capability, self.identifiers["lease"]))
        self.assertEqual(before + 1, len(self.target.seen))
        self.assertEqual(
            f"Bearer {marker}", dict(self.target.seen[-1][2]).get("authorization")
        )

        # The same stable label exists in both Programs. Binding the request to
        # the other Program cannot turn that label into the other Program's row.
        crossed = self.attempt(capability, self.identifiers["other"])
        self.assertEqual((407, proxy.REFUSED), crossed)
        self.assertEqual(before + 1, len(self.target.seen))

        second_holder = self.owned(
            "INSERT INTO agent_runs"
            " (program_id, role, runs_as, model, effort, mission_packet)"
            " VALUES ($1::uuid, 'orchestrator', 'session', 'selftest', 'low', '{}'::jsonb)"
            " RETURNING id::text",
            (self.identifiers["lease"],),
        )
        with self.assertRaises(pg.DatabaseError):
            self.owner(
                "INSERT INTO identity_leases"
                " (program_id, identity_entity_id, holder_agent_run_id, expires_at)"
                " SELECT $1::uuid, i.entity_id, $2::uuid, now() + interval '10 minutes'"
                "   FROM identities i"
                "  WHERE i.program_id = $1::uuid AND i.slot_name = 'member'",
                (self.identifiers["lease"], second_holder),
            )

        self.owner(
            "UPDATE identity_leases SET expires_at = now() - interval '1 minute'"
            " WHERE holder_agent_run_id ="
            "       (SELECT agent_run_id FROM tool_runs WHERE id = $1::uuid)"
            "   AND released_at IS NULL",
            (tool_run,),
        )
        expired = self.attempt(capability, self.identifiers["lease"])
        self.assertEqual((407, proxy.REFUSED), expired)
        self.assertEqual(before + 1, len(self.target.seen))
        still_live = self.connection.execute(
            "SELECT status, egress_token_sha256 IS NOT NULL"
            "  FROM tool_runs WHERE id = $1::uuid",
            (tool_run,),
        ).rows[0]
        self.assertEqual(("running", True), (str(still_live[0]), bool(still_live[1])))

    def test_one_request_is_served_and_one_allowed_receipt_records_it(self):
        # Criteria 2 and 4, from the caller's side. The report names the Receipt
        # the database wrote, not one the runtime chose, and the row is `agent`
        # lane, `allowed`, and attributed to the Tool run that spent it.
        self.assertTrue(self.sent.ok, self.sent.violations)
        self.assertEqual(EXIT_OK, self.sent.exit_code)
        self.assertEqual(200, self.sent.facts["response"]["status"])
        self.assertEqual(len(ANSWER), self.sent.facts["response"]["byte_size"])

        fixture = {
            self.sent.facts["tool_run"]["id"],
            self.secured.facts["tool_run"]["id"],
        }
        served = [row for row in self.receipts("a") if row[1] == "allowed"]
        allowed = [row for row in served if row[3] == self.sent.facts["tool_run"]["id"]]

        # One Receipt for this exchange, and one per exchange: the https run in
        # setup is the other, and a path that recorded twice or not at all is a
        # Receipt count that no longer equals the egress count. Counted over the
        # fixture's two runs, because other tests in this class make their own.
        self.assertEqual(1, len(allowed))
        self.assertEqual(2, len([row for row in served if row[3] in fixture]))
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
        # disk are asked about together. The request claims a wire view and the
        # response does not: this Program requires a header, so what left the
        # door is not what the agent may read, and the target issued no
        # authentication material, so what came back is.
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

        self.assertIsNotNone(row[2])
        self.assertNotEqual(request_sha, str(row[2]))
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

    def test_the_program_holds_both_transcripts_by_a_label_it_can_cite(self):
        # Storing the bytes is not holding them. `v_artifacts` is built from
        # `artifact_references` alone, so a transcript with no reference has no
        # label, and §6's rule that a hash is never an argument then means the
        # agent cannot ask for it at all. Both directions of both exchanges are
        # asked for through an agent session, not through the owner, because the
        # claim is about what the agent surface answers. Named by Tool run rather
        # than swept from the Program: other tests in this class make exchanges
        # of their own, and this one is about the two the fixture made.
        rows = self.connection.execute(
            "SELECT request_agent_sha, response_agent_sha, request_wire_sha, response_wire_sha"
            "  FROM receipts WHERE program_id = $1::uuid AND decision = 'allowed'"
            "   AND tool_run_id IN ($2::uuid, $3::uuid)",
            (
                self.identifiers["a"],
                self.sent.facts["tool_run"]["id"],
                self.secured.facts["tool_run"]["id"],
            ),
        ).rows
        agent = {str(row[column]) for row in rows for column in (0, 1)}
        wire = {str(row[column]) for row in rows for column in (2, 3) if row[column] is not None}

        session = pg.connect(self.harness.state)
        self.addCleanup(session.close)
        session.execute(
            "SELECT set_config('rk2.program_id', $1, false)", (self.identifiers["a"],)
        )
        held = {
            str(row[1]): (str(row[0]), int(row[2]))
            for row in session.execute("SELECT label, sha256, byte_size FROM v_artifacts").rows
        }

        # Two exchanges, two hashes: the http and https runs sent the same bytes
        # and read the same answer, and a content-addressed store holds that
        # once. What matters is that every one of them is citable through the
        # agent surface -- the Program may hold more, because other tests in this
        # class make exchanges of their own -- and that no wire artifact is.
        self.assertEqual(2, len(agent))
        self.assertTrue(wire)
        self.assertLessEqual(agent, set(held))
        self.assertEqual(set(), wire & set(held))
        for sha, (label, byte_size) in held.items():
            with self.subTest(label=label):
                self.assertRegex(label, r"^AF[0-9]+$")
                self.assertEqual(byte_size, len(artifact.path_for(self.root, sha).read_bytes()))

    def test_the_target_saw_the_request_and_none_of_the_control_headers(self):
        # Criterion 3, against a target that actually ran. The request line is
        # origin form -- the target is not a proxy -- and nothing that named the
        # capability or the Program survived the hop.
        method, path, headers = self.arrived
        names = [name for name, _ in headers]

        self.assertEqual(("GET", "/notes"), (method, path))
        self.assertEqual(["app.example.com"], [value for name, value in headers if name == "host"])
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        self.assertEqual([], [name for name in names if name.startswith(proxy.INTERNAL)])
        for _, value in headers:
            self.assertNotIn("RedKraken", value)

    def test_the_required_header_reached_the_target_and_stayed_out_of_the_agent_view(self):
        """Story 8 end to end, over a real fence, a real slot and a real socket.

        The stub in `tests/test_proxy.py` proves the handler puts the value on
        the wire. This proves the value came out of the database, through the
        capability, under the installation root -- and that the record the Agent
        may read does not contain it.
        """
        _, _, headers = self.arrived
        row = self.connection.execute(
            "SELECT request_agent_sha, request_wire_sha FROM receipts"
            " WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
            (self.sent.facts["tool_run"]["id"],),
        ).rows[0]
        visible = Store(self.root).load(str(row[0]))

        self.assertEqual(
            [self.bounty_id], [value for name, value in headers if name == "x-bounty-id"]
        )
        self.assertNotIn(self.bounty_id.encode(), visible)
        self.assertNotIn(b"X-Bounty-Id", visible)
        # And the wire view exists, is not the agent's, and is not on disk in
        # the clear: the door wrote what it sent, sealed, beside what it showed.
        wire_sha = str(row[1])
        self.assertNotEqual(str(row[0]), wire_sha)
        self.assertFalse(artifact.path_for(self.root, wire_sha).exists())
        self.assertFalse(
            self.connection.execute(
                "SELECT * FROM find_in_database($1)", (self.bounty_id,)
            ).rows
        )

    def test_a_header_the_configuration_does_not_declare_is_refused_unsealed(self):
        """The declaration is the authority, and it is checked before the key.

        A value sealed into a slot no policy names is a value the door never
        sends and an operator who believes their traffic carries it.
        """
        value = scratch() / "undeclared-header.txt"
        value.write_text("rk2-undeclared-header-2b71fe", encoding="utf-8")

        refused = header.provision(
            self.harness.runtime,
            self.configurations["b"],
            "X-Not-Declared",
            value,
            root_secret=self.root_secret,
        )

        self.assertFalse(refused.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, refused.exit_code)
        self.assertEqual(
            ["argument:--header"], [item.source for item in refused.violations]
        )
        self.assertIn("X-Bounty-Id", refused.violations[0].detail)
        self.assertEqual(
            0,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM program_header_slots"
                    " WHERE program_id = $1::uuid AND lower(name) = 'x-not-declared'",
                    (self.identifiers["b"],),
                ).scalar()
            ),
        )

    def test_a_replaced_header_value_takes_the_next_revision_and_the_door_sends_it(self):
        """Rotation, which is the operation a bounty identifier actually gets.

        The revision is authenticated as associated data, so a slot rolled back
        to an earlier ciphertext cannot open; asserting it moves is asserting
        that the rollback has something to fail against.
        """
        name = "other"
        first = scratch() / "rotate-first.txt"
        first.write_text("rk2-rotated-first-8f20ac", encoding="utf-8")
        second = scratch() / "rotate-second.txt"
        second.write_text("rk2-rotated-second-3ce914", encoding="utf-8")

        before = header.provision(
            self.harness.runtime,
            self.configurations[name],
            "X-Bounty-Id",
            first,
            root_secret=self.root_secret,
        )
        after = header.provision(
            self.harness.runtime,
            self.configurations[name],
            "x-bounty-id",
            second,
            root_secret=self.root_secret,
        )

        self.assertTrue(before.ok, before.violations)
        self.assertTrue(after.ok, after.violations)
        self.assertEqual(
            before.facts["header"]["revision"] + 1, after.facts["header"]["revision"]
        )
        # One row, in the declaration's spelling rather than the operator's.
        row = self.connection.execute(
            "SELECT count(*), min(name), min(byte_size) FROM program_header_slots"
            " WHERE program_id = $1::uuid",
            (self.identifiers[name],),
        ).rows[0]

        self.assertEqual((1, "X-Bounty-Id", 25), (int(row[0]), str(row[1]), int(row[2])))

        capability, tool_run, _ = self.mint(name)
        status, _ = self.attempt(capability, self.identifiers[name])
        _, _, headers = self.target.seen[-1]

        self.assertEqual(200, status)
        self.assertEqual(
            ["rk2-rotated-second-3ce914"],
            [value for header_name, value in headers if header_name == "x-bounty-id"],
        )

    def test_target_credentials_are_absent_from_the_agent_and_sealed_on_the_wire(self):
        marker = "rk2-live-target-cookie-91ae73"
        previous = LiveTarget.response_headers
        LiveTarget.response_headers = (("Set-Cookie", f"session={marker}; Secure; HttpOnly"),)
        self.addCleanup(setattr, LiveTarget, "response_headers", previous)
        capability, tool_run, _ = self.mint("credential")
        program_id = self.identifiers["credential"]
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=proxy.TIMEOUT
        )
        try:
            client.request(
                "GET",
                URL,
                headers={
                    proxy.AUTHORIZATION: f"RedKraken {capability}",
                    proxy.PROGRAM: program_id,
                },
            )
            answer = client.getresponse()
            body = answer.read()
            self.assertEqual(200, answer.status)
            self.assertIsNone(answer.headers.get("Set-Cookie"))
            self.assertEqual(ANSWER, body)
        finally:
            client.close()

        row = self.connection.execute(
            "SELECT r.response_agent_sha, r.response_wire_sha, s.ciphertext_sha256,"
            "       s.alg, s.nonce, s.kek_gen, encode(k.salt, 'hex')"
            "  FROM receipts r"
            "  JOIN artifact_seal s ON s.sha256 = r.response_wire_sha"
            "  JOIN secret_kek k ON k.gen = s.kek_gen"
            " WHERE r.tool_run_id = $1::uuid AND r.decision = 'allowed'",
            (tool_run,),
        ).rows[0]
        agent_sha, wire_sha, ciphertext_sha = map(str, row[:3])
        visible = Store(self.root).load(agent_sha)
        envelope = Store(self.root).load(ciphertext_sha)
        self.assertNotEqual(agent_sha, wire_sha)
        self.assertNotIn(marker.encode(), visible)
        self.assertNotIn(marker.encode(), envelope)
        self.assertFalse(artifact.path_for(self.root, wire_sha).exists())

        generation = int(row[5])
        key = self.root_secret.program_key(
            bytes.fromhex(str(row[6])), generation=generation, program_id=program_id
        )
        opened = seal.unseal(
            key,
            seal.Sealed.decode(envelope),
            aad=seal.associated_data(
                program_id=program_id, sha256=wire_sha, generation=generation
            ),
        )
        self.assertIn(marker.encode(), opened)
        self.assertFalse(
            self.connection.execute("SELECT * FROM find_in_database($1)", (marker,)).rows
        )
        access = self.connection.execute(
            "SELECT verb, scope_kind, scope_id::text, tool_run_id::text, field, outcome"
            "  FROM secret_access_log WHERE tool_run_id = $1::uuid",
            (tool_run,),
        ).rows
        # Every touch of key material for this one exchange, in the order it
        # happened: the required header opened on the way out, then both
        # directions sealed. The request is sealed too, because the header the
        # door added is not in the agent's copy of it.
        self.assertEqual(
            [
                ("open", "program", program_id, tool_run, "header_slot", "attempted"),
                ("open", "program", program_id, tool_run, "header_slot", "ok"),
                ("seal", "program", program_id, tool_run, "target_request", "ok"),
                ("seal", "program", program_id, tool_run, "target_response", "ok"),
            ],
            [tuple(map(str, item)) for item in access],
        )

    def test_the_receipt_names_the_address_the_door_resolved_and_then_dialled(self):
        # PH2-11, criterion 2. The name was decided, then resolved once by the
        # door itself, then decided again as the literal address, and the socket
        # was opened at that address rather than at the name. A door that handed
        # the name to the socket layer would be letting whoever runs the zone
        # answer twice, and nothing in a Receipt would show it; this row carries
        # the address, so the second answer is a fact somebody can read.
        row = self.connection.execute(
            "SELECT pinned_ips FROM receipts"
            " WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
            (self.sent.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual(PINNED, str(row[0]))
        self.assertIn(("app.example.com", 80), self.resolved)
        self.assertIn(("app.example.com", 80, "http", PINNED), self.dialled)
        self.assertIn(("app.example.com", 443, "https", PINNED), self.dialled)

    def test_an_address_the_program_withdrew_is_refused_with_nothing_dialled(self):
        # The half of criterion 2 a policy written in names cannot answer on its
        # own. The name is in scope and the first decision allows it; what comes
        # back from resolution is an address this Program excluded, and the
        # exchange stops there. What `SCOPED` withdraws is one octet from the
        # address every other test pins, so a rule that matched loosely would
        # make this pass for the wrong reason.
        self.resolving_to(WITHDRAWN)
        capability, tool_run, _ = self.mint("a")
        dialled = len(self.dialled)

        record = self.refused("a", capability, self.identifiers["a"])

        self.assertEqual(("agent", "blocked", "address refused"), record[:3])
        self.assertEqual(tool_run, record[3], "the capability resolved, so its run is named")
        self.assertEqual(dialled, len(self.dialled), "a socket was opened towards the target")

        row = self.connection.execute(
            "SELECT pinned_ips, ts_egress, host FROM receipts"
            " WHERE program_id = $1::uuid ORDER BY ts_arrival DESC, label DESC LIMIT 1",
            (self.identifiers["a"],),
        ).rows[0]

        self.assertEqual(WITHDRAWN, str(row[0]))
        self.assertIsNone(row[1], "a refusal before contact records no moment of egress")
        self.assertEqual("app.example.com", str(row[2]), "the name it asked for is still the row")

    def test_a_name_that_answers_off_the_public_internet_is_refused_by_the_door(self):
        # The other rebinding shape, and the one that needs no policy at all: an
        # address the public internet does not route to is not a bug bounty
        # target under any scope, so the refusal is the door's own and happens
        # before the database is asked a second question. The two answers are the
        # classic pair -- loopback, which reaches this machine, and the link-local
        # address every cloud metadata service listens on.
        for address in ("127.0.0.1", "169.254.169.254"):
            with self.subTest(address=address):
                self.resolving_to(address)
                capability, _, _ = self.mint("a")
                dialled = len(self.dialled)

                record = self.refused("a", capability, self.identifiers["a"])

                self.assertEqual(("agent", "blocked", "address refused"), record[:3])
                self.assertEqual(dialled, len(self.dialled), "a socket was opened")

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
        # And the wire view is claimed on the side that has one. The request left
        # with a header the agent never saw, so the row names a different hash;
        # the response came back with nothing the agent may not read, so the row
        # says so by leaving that hash null rather than by repeating the agent's.
        self.assertIsNotNone(row[9])
        self.assertIsNone(row[10])

    def test_both_sides_of_the_intercepted_handshake_are_on_the_receipt(self):
        # The gap, written down. The agent's TLS stack negotiated with this door
        # and the door negotiated with the target, and until now the row said
        # nothing about either -- so an agent concluding "the target speaks TLS
        # 1.3 under a certificate that verifies" from what it saw had nothing
        # contradicting it. Now the row holds both, and `transport_divergence` is
        # generated from the pair.
        row = self.connection.execute(
            "SELECT agent_tls_version, agent_cipher, agent_alpn, agent_cert_sha256,"
            "       wire_tls_version, wire_cipher, wire_sni, wire_cert_sha256,"
            "       wire_chain_verified, wire_hostname_verified,"
            "       transport_divergence, transport_citable, notes"
            "  FROM receipts WHERE tool_run_id = $1::uuid AND decision = 'allowed'",
            (self.secured.facts["tool_run"]["id"],),
        ).rows[0]

        # The agent side is read off the socket the request arrived on, which
        # inside a tunnel is this door's own TLS.
        self.assertTrue(str(row[0]).startswith("TLSv1."), row[0])
        self.assertIsNotNone(row[1])
        # Null because `_through` -- the runtime's own client, which is what sent
        # this -- proposes no ALPN, and a server negotiates only what the client
        # offered. Recorded as the null it is rather than as the `http/1.1` the
        # door would have accepted: this column is what was negotiated, and the
        # upstream one beside it is `http/1.1` because the door does propose it.
        self.assertIsNone(row[2])
        # And the leaf the door forged stays unwritten: naming it means naming
        # the forging key, and nothing yet writes the `interception_cas` row that
        # `receipts_intercepted_leaf_names_ca` would make it point at.
        self.assertIsNone(row[3])

        self.assertEqual(self.upstream.tls_version, str(row[4]))
        self.assertEqual(self.upstream.cipher, str(row[5]))
        self.assertEqual("app.example.com", str(row[6]))
        self.assertEqual(self.upstream.cert_sha256, str(row[7]))
        # The target's certificate did not verify and the row says so in the two
        # columns `transport_citable` is generated from, which is why an exchange
        # that was served is still not a citable measurement of its transport.
        self.assertFalse(row[8])
        self.assertFalse(row[9])
        self.assertFalse(row[11])
        # Which fields the two sides disagree about, computed by the column and
        # not by the door: the certificate above all, because the agent was shown
        # a forged one, and the cipher because the two handshakes are two.
        self.assertIn("cert_sha256", str(row[10]))
        self.assertIn("cipher", str(row[10]))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", str(row[12]))

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
            "SELECT scheme, host, port, path, ts_egress FROM receipts"
            " WHERE program_id = $1::uuid AND label = $2",
            (self.identifiers["a"], answer.receipt),
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

    def test_a_target_that_did_not_answer_is_neither_a_success_nor_a_refusal(self):
        # A request the gate authorized, the door dialled, and nothing answered,
        # which is the case the runtime has to read correctly twice over. Reading
        # the blocked Receipt as "served" would close the Tool run as success and
        # exit 0, telling an operator scripting this command that the request
        # went out. Reading it as a refusal -- which is what a `denied` close, a
        # 407 and an `invalid_configuration` violation all said -- points every
        # later reader at this harness for a fact about the target: the
        # capability was minted, resolved and spent, and the run's own `decision`
        # column says `allow`.
        #
        # The fault is manufactured by pointing this door's outbound side at a
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
            connector=lambda host, port, timeout, protocol, address, client_certificate: (
                http.client.HTTPConnection("127.0.0.1", closed, timeout=timeout),
                None,
            ),
            resolver=self.look_up,
            authority=self.authority,
            # A door with no root cannot open the header this Program requires,
            # and refuses before it dials. This case is about what happens when
            # it does dial, so it carries the same key the others do.
            root_secret=self.root_secret,
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
        self.assertEqual(EXIT_TARGET_UNREACHABLE, result.exit_code)
        self.assertEqual(502, result.facts["response"]["status"])
        self.assertEqual(
            ["egress"], [item.name for item in result.assertions if not item.ok]
        )
        self.assertEqual(
            [(TARGET_UNREACHABLE, "target:app.example.com")],
            [(item.code, item.source) for item in result.violations],
        )
        # Cited, and closed as what it was: `error` is the outcome word for a run
        # that was authorized and did not complete. The capability is gone either
        # way -- any close that leaves `running` clears the digest.
        self.assertIsNotNone(result.facts["receipt"])
        row = self.connection.execute(
            "SELECT status, egress_token_sha256 FROM tool_runs WHERE id = $1::uuid",
            (result.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual("error", str(row[0]))
        self.assertIsNone(row[1])
        blocked = self.connection.execute(
            "SELECT decision, reason, host, ts_egress FROM receipts"
            " WHERE program_id = $1::uuid AND label = $2",
            (self.identifiers["a"], result.facts["receipt"]),
        ).rows[0]

        self.assertEqual(
            ("blocked", "target unreachable", "app.example.com"),
            (str(blocked[0]), str(blocked[1]), str(blocked[2])),
        )
        self.assertIsNotNone(blocked[3], "the door had already tried the target")

    def test_a_call_the_gate_reserves_for_a_human_is_asked_and_not_refused(self):
        # Ticket 11's whole loop, on the path an operator uses. The verdict is
        # `ask` -- a mutating method, which is the call the risk table reserves
        # for a person -- and what the runtime did with it was report "no
        # capability was minted" and close the run as `denied`: the question was
        # never filed, no human could answer it, and the row read as if this
        # harness had refused a request nobody had ruled on.
        first = proxy.send(
            self.harness.runtime,
            self.configurations["a"],
            SECURE,
            proxy_url=self.proxy_url,
            method="POST",
            ca_file=self.authority.certificate,
        )

        self.assertEqual(EXIT_AWAITING_DECISION, first.exit_code)
        self.assertIsNone(first.facts["response"], "an unanswered question sends nothing")
        label = first.facts["decision"]
        self.assertEqual(
            [(AWAITING_DECISION, f"decision:{label}")],
            [(item.code, item.source) for item in first.violations],
        )

        parked = self.connection.execute(
            "SELECT t.status, t.decision, t.egress_token_sha256, d.label, d.status,"
            "       d.task_id, d.question, a.stop_reason"
            "  FROM tool_runs t"
            "  JOIN pending_decisions d ON d.id = t.pending_decision_id"
            "  JOIN agent_runs a ON a.id = t.agent_run_id"
            " WHERE t.id = $1::uuid",
            (first.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual("parked", str(parked[0]))
        self.assertEqual("deny", str(parked[1]), "a request that stopped at a question")
        self.assertIsNone(parked[2], "nothing to spend while the question is open")
        self.assertEqual(label, str(parked[3]))
        self.assertEqual("pending", str(parked[4]))
        # No task, and the column that used to require one. An operator-initiated
        # call has nothing to resume; the operator repeats the command.
        self.assertIsNone(parked[5])
        self.assertIn("POST", str(parked[6]))
        self.assertEqual("parked", str(parked[7]), "the run ends; the lane slot frees")

        # The answer, given by the one role that may give it, and then the same
        # request again -- which is what resumption is when there is no task.
        self.human.execute(proxy.BIND, (self.identifiers["a"],))
        with self.human.transaction():
            self.human.execute(
                "SELECT answer_decision($1, 'approved', 'selftest operator',"
                " interval '10 minutes')",
                (label,),
            )

        second = proxy.send(
            self.harness.runtime,
            self.configurations["a"],
            SECURE,
            proxy_url=self.proxy_url,
            method="POST",
            ca_file=self.authority.certificate,
        )

        self.assertEqual(EXIT_OK, second.exit_code, second.violations)
        self.assertEqual(200, second.facts["response"]["status"])
        # Named on the row and in the report: rule 5 admitted this call because a
        # human answered, and "which answer" is a question the record has to be
        # able to close. Recomputing it later cannot -- the equivalence key is
        # taken at the scope version the approval was given under.
        self.assertEqual(label, second.facts["decision"])
        allowed = self.connection.execute(
            "SELECT t.decision, t.risk_class, d.label, d.status"
            "  FROM tool_runs t JOIN pending_decisions d ON d.id = t.pending_decision_id"
            " WHERE t.id = $1::uuid",
            (second.facts["tool_run"]["id"],),
        ).rows[0]

        self.assertEqual(("allow", "approval_required"), (str(allowed[0]), str(allowed[1])))
        self.assertEqual((label, "approved"), (str(allowed[2]), str(allowed[3])))
        # And the standing check agrees about both of them. `approval_required`
        # resolves to `ask`, so the parked `deny` and the granted `allow` are
        # each a decision the policy table did not give -- which is exactly what
        # arm (e) counts, unless the row names the decision that authorised it.
        self.assertEqual(
            (),
            self.connection.execute(
                "SELECT detail FROM check_receipt_integrity($1::uuid, interval '1 hour')"
                " WHERE problem IN ('decision_disagrees_with_risk_class',"
                "                   'ask_closed_as_a_verdict')",
                (self.identifiers["a"],),
            ).rows,
        )

    def question(self, ttl: str = "10 minutes") -> tuple[str, str]:
        """One filed question, and the notification the fan-out wrote for it.

        The door parks with the default deadline, which is right for an operator
        and useless for a case about deadlines, so the run is opened here and
        `park_for_human` is called with the interval the case needs. Everything
        before that is the production path: the gate is what answers `ask`, and
        it answers it because the method mutates.

        Cleanup answers the question rather than deleting it. Nothing may delete
        one -- `pending_decisions_no_delete` -- and a question left open would be
        a question the next sweep in this module finds, which is exactly the
        state these cases are about.
        """
        self.runtime.execute(proxy.BIND, (self.identifiers["decision"],))
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            run = self.runtime.execute(
                proxy.OPEN_RUN,
                (self.identifiers["decision"], "operator", json.dumps({"command": "selftest"})),
            ).scalar()
            opened = self.runtime.execute(
                proxy.OPEN_TOOL_RUN,
                (
                    self.identifiers["decision"],
                    str(run),
                    proxy.TOOL,
                    json.dumps({"url": URL, "method": "POST", "identity_slot": ""}),
                ),
            ).rows[0][0]
        label = str(
            self.runtime.execute(
                "SELECT park_for_human($1::uuid, $2::interval)", (str(opened), ttl)
            ).scalar()
        )
        self.addCleanup(self.close_question, label)
        notification = str(
            self.runtime.execute(
                "SELECT n.id::text FROM decision_notifications n"
                "  JOIN pending_decisions d ON d.id = n.pending_decision_id"
                " WHERE d.program_id = $1::uuid AND d.label = $2",
                (self.identifiers["decision"], label),
            ).scalar()
        )
        return label, notification

    def close_question(self, label: str) -> None:
        """Answer it if it is still open, whatever this case did to it."""
        self.human.execute(proxy.BIND, (self.identifiers["decision"],))
        with self.human.transaction():
            self.human.execute(
                "SELECT answer_decision($1, 'denied', 'selftest')"
                "  FROM pending_decisions"
                " WHERE program_id = $2::uuid AND label = $1 AND status = 'pending'",
                (label, self.identifiers["decision"]),
            )

    def surface(self, label: str) -> list[str]:
        """What the standing check says about one question, and only that one."""
        return [
            str(row[0])
            for row in self.connection.execute(
                "SELECT problem FROM check_control_surface() WHERE detail = $1", (label,)
            ).rows
        ]

    def test_the_sweep_carries_a_question_to_its_channel_and_stops_carrying_it(self):
        # Ticket 11's second clock. The database files the question and fans it
        # out; nothing in it can run a command, so a queue nobody tends is a
        # question nobody is told about. What the channel is handed is the label
        # and the rendered question, substituted per argv element -- never a
        # string a shell parses, because the host and the path in it come from
        # the request the agent asked to make.
        label, notification = self.question()
        carried: list[list[str]] = []

        first = decisions.sweep(self.harness.runtime, deliver=self.recorder(carried))

        self.assertTrue(first.ok, first.violations)
        self.assertIn(
            f"{label} was carried to the desktop channel",
            [item.detail for item in first.assertions if item.name == "notification"],
        )
        sent = [command for command in carried if f"redKrakenV2 {label}" in command]
        self.assertEqual(1, len(sent), carried)
        self.assertEqual("notify-send", sent[0][0])
        self.assertIn("POST", sent[0][-1], "the question the human has to answer")
        # Recorded, and gone from the queue: a delivery that is not written down
        # is one the next pass makes again, for ever.
        self.assertEqual((1, True), self.attempted(notification))
        carried.clear()
        second = decisions.sweep(self.harness.runtime, deliver=self.recorder(carried))

        self.assertTrue(second.ok, second.violations)
        self.assertEqual([], [command for command in carried if f"redKrakenV2 {label}" in command])

    def test_a_channel_that_refuses_is_recorded_and_tried_again_later(self):
        # A failed delivery is not a failure of the sweep. The queue exists so
        # that it can be tried again, so the pass says what happened and exits
        # zero -- and the attempt is written down, because a channel that fails
        # for ever has to run out eventually rather than be retried for ever.
        label, notification = self.question()

        result = decisions.sweep(
            self.harness.runtime, deliver=lambda command: (False, "no session bus")
        )

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(
            [f"{label} did not reach the desktop channel and will be retried: no session bus"],
            [
                item.detail
                for item in result.assertions
                if item.name == "notification" and label in item.detail
            ],
        )
        self.assertEqual((1, False), self.attempted(notification))
        self.assertEqual(
            "no session bus",
            str(
                self.connection.execute(
                    "SELECT last_error FROM decision_notifications WHERE id = $1::uuid",
                    (notification,),
                ).scalar()
            ),
        )
        # And it is not due again immediately: the channel's backoff is what
        # stands between "retry" and a loop that hammers a broken notifier.
        self.assertEqual(
            (),
            self.runtime.execute(
                "SELECT notification_id FROM due_notifications() WHERE notification_id = $1::uuid",
                (notification,),
            ).rows,
        )

    def test_a_question_no_channel_will_carry_again_is_a_standing_failure(self):
        # The half of ticket 11 that had no alarm. A notification that spends
        # every attempt leaves the question in the queue, and the only thing that
        # then happens to it is the deadline -- so it is retired as a timeout
        # against a human who was never told there was anything to answer.
        label, notification = self.question()

        self.assertEqual([], self.surface(label), "still being tried")
        self.spend(notification)

        self.assertEqual(["decision_unannounced"], self.surface(label))
        # One delivery anywhere closes it. The rule is about a question nobody
        # was told about, not about a channel that failed.
        self.owner(
            "UPDATE decision_notifications SET delivered_at = now() WHERE id = $1::uuid",
            (notification,),
        )

        self.assertEqual([], self.surface(label))

    def test_a_question_that_dies_unannounced_is_reported_before_it_is_retired(self):
        # The order inside one pass, which is the whole of what the arm is worth.
        # `decision_unannounced` is a rule about a pending question, and this
        # sweep is about to retire this one -- so a sweep that expired first and
        # looked afterwards would find nothing to report, every time, and the
        # question would go to a timeout in silence. It is read first.
        label, notification = self.question(ttl="1 millisecond")
        self.spend(notification)

        result = decisions.sweep(self.harness.runtime, deliver=lambda command: (True, ""))

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertEqual(
            [(False, f"no channel will carry these questions again and no human has been told about them: {label}")],
            [
                (item.ok, item.detail)
                for item in result.assertions
                if item.name == "announcement" and label in item.detail
            ],
        )
        # Retired all the same, by the same pass: the alarm is about the record
        # being honest, not about holding the deadline open.
        self.assertEqual(
            ("expired", "runtime", "deadline passed with no human answer"),
            tuple(
                str(value)
                for value in self.connection.execute(
                    "SELECT status, actor_kind, answer FROM pending_decisions"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (self.identifiers["decision"], label),
                ).rows[0]
            ),
        )

    @staticmethod
    def recorder(carried: list[list[str]]):
        """A channel that always works, and keeps what it was handed.

        Nothing here runs `notify-send`: what the substitution produced is the
        subject, and a suite that put it on a desktop would be a suite whose
        result depends on whether one is there.
        """

        def deliver(command):
            carried.append(list(command))
            return True, ""

        return deliver

    def attempted(self, notification: str) -> tuple[int, bool]:
        """How many times a notification was tried, and whether it landed."""
        row = self.connection.execute(
            "SELECT attempts, delivered_at IS NOT NULL FROM decision_notifications"
            " WHERE id = $1::uuid",
            (notification,),
        ).rows[0]
        return int(row[0]), bool(row[1])

    def spend(self, notification: str) -> None:
        """Burn every attempt this notification's channel allows it."""
        self.owner(
            "UPDATE decision_notifications n SET attempts = c.max_attempts"
            "  FROM notification_channels c"
            " WHERE c.channel = n.channel AND n.id = $1::uuid",
            (notification,),
        )

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

    def test_a_refusal_answers_with_a_label_the_agent_connection_can_open(self):
        # The served path names its Receipt's label and the refused path named
        # the row's uuid, so `rk state --label` -- the only lookup an agent has
        # -- answered "is not a record of this Program" for a record sitting
        # right there, and "refused and filed" read exactly like "refused and
        # lost". This walks the whole way rather than asserting the shape of the
        # header: the name on the wire, the row it belongs to, and the read.
        answer = self.answered("c" * 64, self.identifiers["a"])
        named = answer.headers[proxy.RECEIPT]

        self.assertEqual(407, answer.status)
        self.assertRegex(named, r"^R[0-9]+$")
        row = self.connection.execute(
            "SELECT decision, reason FROM receipts"
            " WHERE program_id = $1::uuid AND label = $2",
            (self.identifiers["a"], named),
        ).rows[0]

        self.assertEqual(("blocked", "capability refused"), (str(row[0]), str(row[1])))
        cited = state.read(
            self.harness.runtime,
            self.harness.state,
            self.configurations["a"],
            label=named,
        )

        self.assertTrue(cited.ok, cited.violations)
        self.assertTrue(cited.facts["record"]["present"], named)
        self.assertEqual("receipt", cited.facts["record"]["kind"])
        self.assertEqual("blocked", cited.facts["record"]["document"]["decision"])

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

    def test_a_subresource_earns_its_own_receipt_under_the_parent_tool_run(self):
        # PH2-11, criterion 4. One capability and four exchanges: the page, the
        # script it pulls, a method the Tool run never declared, and a path this
        # Program withdrew. Nothing is inherited from the exchange before it --
        # each one resolves the capability again, is decided against the current
        # policy, is resolved and pinned again, and is recorded on its own -- so
        # the sharing §7 asks for costs nothing in evidence. Four Receipts under
        # one Tool run, and the two that were refused never reached the target.
        capability, tool_run, _ = self.mint("shared")
        seen = len(self.target.seen)

        page = self.attempt(capability, self.identifiers["shared"], URL)
        script = self.attempt(
            capability, self.identifiers["shared"], "http://app.example.com/static/app.js"
        )
        self.assertEqual((200, None), page)
        self.assertEqual((200, None), script, "a subresource GET was refused")
        self.assertEqual(seen + 2, len(self.target.seen))

        # And the same capability buys nothing the Tool run did not authorise. A
        # shared capability that could be spent on an unsafe method, or on a path
        # the policy withdrew, would make every subresource an opening.
        unsafe = self.attempt(capability, self.identifiers["shared"], URL, "DELETE")
        withdrawn = self.attempt(
            capability, self.identifiers["shared"], "https://app.example.com/internal/secrets"
        )

        self.assertEqual((407, proxy.REFUSED), unsafe)
        self.assertEqual((407, proxy.REFUSED), withdrawn)
        self.assertEqual(seen + 2, len(self.target.seen), "a refused exchange reached the target")

        rows = [
            (str(row[0]), str(row[1]), str(row[2]), row[3] and str(row[3]))
            for row in self.connection.execute(
                "SELECT decision, method, path, pinned_ips FROM receipts"
                " WHERE tool_run_id = $1::uuid ORDER BY ts_arrival, label",
                (tool_run,),
            ).rows
        ]

        self.assertEqual(
            [
                ("allowed", "GET", "/notes", PINNED),
                ("allowed", "GET", "/static/app.js", PINNED),
                # Refused before resolution, so there is no address to name: the
                # exchange stopped at the first decision, not at the second.
                ("blocked", "DELETE", "/notes", None),
                ("blocked", "GET", "/internal/secrets", None),
            ],
            rows,
        )

    def test_a_lease_lost_between_two_requests_stops_the_second_before_contact(self):
        # PH2-11, criterion 5, and the arm 09 could not reach: the capability,
        # the Tool run, the Agent run and the Program are all untouched between
        # the two requests, and what lapses is the task lease the run holds.
        # `resolve_egress_capability` requires it on every exchange rather than
        # at mint time, so the parent is served and the child is stopped with
        # nothing dialled -- which is what makes one capability safe to share
        # across a page and everything the page pulls.
        capability, tool_run, task = self.leased("shared")

        served = self.attempt(capability, self.identifiers["shared"])
        dialled = len(self.dialled)
        self.owner(
            "UPDATE tasks SET lease_expires_at = now() - interval '1 minute'"
            " WHERE id = $1::uuid",
            (task,),
        )
        record = self.refused("shared", capability, self.identifiers["shared"])

        self.assertEqual(200, served[0])
        self.assertEqual(("agent", "blocked", "capability refused"), record[:3])
        self.assertEqual(dialled, len(self.dialled), "a socket was opened without a lease")
        # Nothing about the run itself changed, which is the point: the fence is
        # not reading a revoked capability, it is reading a lease that lapsed.
        row = self.connection.execute(
            "SELECT tr.status, tr.egress_token_sha256 IS NOT NULL, ar.finished_at"
            "  FROM tool_runs tr JOIN agent_runs ar ON ar.id = tr.agent_run_id"
            " WHERE tr.id = $1::uuid",
            (tool_run,),
        ).rows[0]

        self.assertEqual("running", str(row[0]))
        self.assertTrue(row[1], "the capability was still live")
        self.assertIsNone(row[2])

    def test_a_program_halted_between_two_requests_stops_the_second_until_an_operator_clears_it(self):
        # PH2-11, criterion 5's fourth arm. The capability predates the Halt and
        # remains live throughout; what changes is the Program's current
        # operator state. Every exchange resolves that state again, so the
        # parent is served, the child stops before a socket, and remediation
        # allows the same still-live Tool run to continue.
        capability, tool_run, _ = self.mint("shared")
        program_id = self.identifiers["shared"]

        parent = self.attempt(capability, program_id)
        dialled = len(self.dialled)
        halted = self.human.execute(
            "SELECT halt_program($1::uuid, $2)",
            (program_id, "operator containment self-test"),
        ).scalar()
        child = self.refused("shared", capability, program_id)

        self.assertEqual(200, parent[0])
        # Named as the Halt rather than as a lapse. A Halt refuses by making the
        # capability resolve to nothing, which is what an expired token does, so
        # without the writer saying which it was the one refusal an operator
        # caused reads like the one nobody can lift.
        self.assertEqual(("agent", "blocked", "program halted"), child[:3])
        self.assertEqual(dialled, len(self.dialled), "a socket was opened during Halt")
        halt_payload = json.loads(halted) if isinstance(halted, str) else dict(halted)
        self.assertEqual("halted", halt_payload["status"])
        row = self.connection.execute(
            "SELECT tr.status, tr.egress_token_sha256 IS NOT NULL, ar.finished_at"
            "  FROM tool_runs tr JOIN agent_runs ar ON ar.id = tr.agent_run_id"
            " WHERE tr.id = $1::uuid",
            (tool_run,),
        ).rows[0]
        self.assertEqual(("running", True, None), (str(row[0]), bool(row[1]), row[2]))

        with self.assertRaises(pg.DatabaseError):
            self.runtime.execute(
                "SELECT clear_program_halt($1::uuid, $2)",
                (program_id, "runtime must not clear this"),
            )

        cleared = self.human.execute(
            "SELECT clear_program_halt($1::uuid, $2)",
            (program_id, "operator remediation complete"),
        ).scalar()
        resumed = self.attempt(capability, program_id)

        clear_payload = json.loads(cleared) if isinstance(cleared, str) else dict(cleared)
        self.assertEqual("cleared", clear_payload["status"])
        self.assertEqual(200, resumed[0])
        events = self.connection.execute(
            "SELECT type, actor_kind, payload -> 'after' ->> 'status'"
            "  FROM events WHERE subject_table = 'program_halts'"
            "   AND subject_id = (SELECT id FROM program_halts WHERE program_id = $1::uuid)"
            " ORDER BY seq",
            (program_id,),
        ).rows
        self.assertEqual(
            [("program.halted", "human", "halted"),
             ("program.halt_changed", "human", "cleared")],
            [(str(event[0]), str(event[1]), str(event[2])) for event in events],
        )

    def test_clearing_a_halt_revives_neither_an_expired_capability_nor_a_closed_run(self):
        # PH2-13, criterion 5. Clearing is remediation of one thing -- the
        # operator's stop -- and every other reason a capability stopped
        # resolving is still a reason afterwards. The arm that matters is the
        # ordering: both capabilities lapse *during* the Halt, when nothing was
        # being decided about them, so a clear that resumed "everything that was
        # live when I halted" would put both of them back.
        program_id = self.identifiers["halted"]
        expired, expiring_run, _ = self.mint("halted")
        closed, closed_run, _ = self.mint("halted")
        self.human.execute(
            "SELECT halt_program($1::uuid, $2)", (program_id, "operator containment")
        )
        self.owner(
            "UPDATE tool_runs SET egress_token_expires_at = now() - interval '1 minute'"
            " WHERE id = $1::uuid",
            (expiring_run,),
        )
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            self.runtime.execute(proxy.CLOSE_TOOL_RUN, (closed_run, "success"))
        self.human.execute(
            "SELECT clear_program_halt($1::uuid, $2)", (program_id, "remediation done")
        )

        dialled = len(self.dialled)
        lapsed = self.refused("halted", expired, program_id)
        finished = self.refused("halted", closed, program_id)

        self.assertEqual(("agent", "blocked", "capability refused"), lapsed[:3])
        self.assertEqual(("agent", "blocked", "capability refused"), finished[:3])
        self.assertEqual(dialled, len(self.dialled), "a socket was opened after the clear")
        # And the clear did lift the Halt, or the two refusals above would prove
        # nothing: a capability minted after it works.
        live, _, _ = self.mint("halted")
        self.assertEqual(200, self.attempt(live, program_id)[0])

    def test_the_runtime_can_neither_delete_its_halt_nor_refill_its_budget(self):
        # PH2-13, criteria 2 and 3, at the table rather than at the verb. The
        # earlier test proves `clear_program_halt` is out of the runtime's reach;
        # this one proves the row is too, which is a different fact -- the
        # actor-kind guard is a BEFORE INSERT OR UPDATE trigger, so a DELETE
        # passes it untouched, and an absent Halt is a lifted Halt.
        #
        # Same for the three counters. They are ordinary tables created by the
        # owner, and the owner's default privileges standing-grant the runtime
        # every DML verb on those, so the revoke is the only thing between the
        # process the model runs inside and its own budget.
        program_id = self.identifiers["shared"]
        self.human.execute(
            "SELECT halt_program($1::uuid, $2)", (program_id, "privilege self-test")
        )
        self.addCleanup(
            self.human.execute,
            "SELECT clear_program_halt($1::uuid, $2)",
            (program_id, "privilege self-test done"),
        )

        writes = (
            ("DELETE FROM program_halts WHERE program_id = $1::uuid", (program_id,)),
            ("UPDATE program_halts SET status = 'cleared' WHERE program_id = $1::uuid",
             (program_id,)),
            ("UPDATE program_egress_spend SET contacted = 0 WHERE program_id = $1::uuid",
             (program_id,)),
            ("UPDATE program_egress_budget SET tokens = 1000000"
             " WHERE program_id = $1::uuid", (program_id,)),
            ("DELETE FROM egress_reservations WHERE program_id = $1::uuid", (program_id,)),
        )
        for statement, arguments in writes:
            with self.subTest(statement=statement.split(" WHERE")[0]):
                self.runtime.execute(proxy.BIND, (program_id,))
                with self.assertRaises(pg.DatabaseError) as refused:
                    self.runtime.execute(statement, arguments)
                self.assertEqual("42501", refused.exception.sqlstate)

        # And the Halt is still a Halt afterwards, which is the point: a refused
        # write that left the row changed would be a privilege error hiding a
        # successful one.
        self.assertEqual(
            "halted",
            str(self.connection.execute(
                "SELECT status FROM program_halts WHERE program_id = $1::uuid",
                (program_id,),
            ).scalar()),
        )

    def test_an_exhausted_program_budget_stops_a_tool_run_that_never_spent_any(self):
        # PH2-13, criteria 3 and 4. The total is the Program's: two exchanges
        # spend it under one Tool run, and the third is refused under a
        # capability minted afterwards, from a Tool run that had made no request
        # at all. A per-run or per-process counter would have let it through.
        program_id = self.identifiers["budget"]
        first, _, _ = self.mint("budget")
        self.assertEqual(200, self.attempt(first, program_id)[0])
        self.assertEqual(200, self.attempt(first, program_id)[0])

        second, _, _ = self.mint("budget")
        dialled = len(self.dialled)
        seen = len(self.target.seen)
        resolved = len(self.resolved)
        answer = self.answered(second, program_id)

        self.assertEqual(407, answer.status)
        self.assertEqual(proxy.BUDGETED, answer.headers.get(proxy.DECISION))
        self.assertEqual("budget exhausted", answer.headers.get(proxy.DETAIL))
        # Nothing left the machine, and that includes the lookup: the budget is
        # decided before the name is resolved, so an exhausted Program does not
        # keep announcing its targets to a resolver.
        self.assertEqual(resolved, len(self.resolved), "a name was resolved past the budget")
        self.assertEqual(dialled, len(self.dialled), "a socket was opened past the budget")
        self.assertEqual(seen, len(self.target.seen))
        # A typed Receipt, and no retry time on it. Exhaustion is not a wait: the
        # engagement's allowance is gone until an operator decides otherwise, and
        # a time here would be this door promising it comes back on its own.
        self.assertEqual(("blocked", "budget exhausted", None), self.latest("budget"))
        self.assertIsNone(answer.headers.get("Retry-After"))
        self.assertEqual((2, 1), self.spent("budget"))

    def test_a_rate_limited_request_is_refused_with_the_time_it_may_be_retried(self):
        # The other half of criterion 4. `throttle` allows a burst of two per
        # hour, so the third request in a row is refused for its rate -- and
        # unlike exhaustion it is refused *until* a moment, which is on the wire
        # as seconds and in the row as an instant. The row is what makes the
        # retry durable: the answer is read once by a caller that may not
        # outlive it.
        program_id = self.identifiers["throttle"]
        capability, _, _ = self.mint("throttle")
        self.assertEqual(200, self.attempt(capability, program_id)[0])
        self.assertEqual(200, self.attempt(capability, program_id)[0])

        dialled = len(self.dialled)
        answer = self.answered(capability, program_id)

        self.assertEqual(407, answer.status)
        self.assertEqual(proxy.BUDGETED, answer.headers.get(proxy.DECISION))
        self.assertEqual("rate limited", answer.headers.get(proxy.DETAIL))
        self.assertEqual(dialled, len(self.dialled), "a socket was opened past the rate")
        decision, reason, retry_after = self.latest("throttle")
        self.assertEqual(("blocked", "rate limited"), (decision, reason))
        self.assertIsNotNone(retry_after, "a throttle with no time to retry after")
        # Two tokens an hour is one every half hour, so the wait is that and not
        # a round number this test could have got by accident.
        self.assertIn(int(answer.headers["Retry-After"]), range(1750, 1801))

    def test_a_second_request_in_flight_is_refused_by_the_concurrency_limit(self):
        # Criterion 3's concurrency arm, which needs a request that is still
        # happening: `concurrent` allows one at a time, so the second is refused
        # while the first is parked at a target that has not answered yet. Two
        # capabilities from two Tool runs, because the limit is the Program's.
        program_id = self.identifiers["concurrent"]
        first, _, _ = self.mint("concurrent")
        second, _, _ = self.mint("concurrent")
        self.parking()

        held: list[tuple[int, str | None]] = []
        dialled = len(self.dialled)
        running = threading.Thread(
            target=lambda: held.append(self.attempt(first, program_id))
        )
        running.start()
        self.addCleanup(running.join, 30)
        # Wait for the socket rather than for a moment: a sleep long enough to be
        # reliable on a loaded machine is a sleep this suite pays on every run,
        # and the thing the second request has to overlap is an exchange that has
        # started, which is exactly what the dial records.
        deadline = time.monotonic() + 30
        while len(self.dialled) == dialled and time.monotonic() < deadline:
            time.sleep(0.01)

        answer = self.answered(second, program_id)
        HeldTarget.release.set()
        running.join(timeout=30)

        self.assertEqual(407, answer.status)
        self.assertEqual(proxy.BUDGETED, answer.headers.get(proxy.DECISION))
        self.assertEqual("too many concurrent requests", answer.headers.get(proxy.DETAIL))
        self.assertEqual([200], [status for status, _ in held], "the first never finished")
        decision, reason, retry_after = self.latest("concurrent")
        self.assertEqual(("blocked", "too many concurrent requests"), (decision, reason))
        # Told when to come back, and the answer is bounded by the slot's own
        # lifetime rather than open-ended: the request ahead either finishes or
        # its reservation lapses.
        self.assertIsNotNone(retry_after)
        self.assertIn(int(answer.headers["Retry-After"]), range(1, 91))

    def test_a_concurrent_burst_across_two_doors_spends_one_budget(self):
        # PH2-13, criterion 6, and the claim the whole ticket rests on. Eight
        # Tool runs, eight capabilities, two doors on two database sessions, one
        # Program with three requests left -- fired at once off a barrier. Three
        # is what the target may be contacted, and five is what has to be
        # refused, whichever door happened to be quicker.
        program_id = self.identifiers["race"]
        capabilities = [self.mint("race")[0] for _ in range(8)]
        second = self.another_door()
        doors = (self.server.server_address[1], second.server_address[1])

        dialled = len(self.dialled)
        seen = len(self.target.seen)
        answers: list[tuple[int, str | None]] = []
        start = threading.Barrier(len(capabilities), timeout=30)

        def race(index: int) -> None:
            start.wait()
            answers.append(
                self.attempt(capabilities[index], program_id, port=doors[index % 2])
            )

        threads = [
            threading.Thread(target=race, args=(index,))
            for index in range(len(capabilities))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(8, len(answers), "a request never came back")
        self.assertEqual(3, len([1 for status, _ in answers if status == 200]))
        self.assertEqual(
            5, len([1 for _, decision in answers if decision == proxy.BUDGETED])
        )
        # The exact count, which is the part a limit enforced per process would
        # get wrong: eight racing requests, three sockets, three arrivals.
        self.assertEqual(3, len(self.dialled) - dialled, "the target was contacted twice over")
        self.assertEqual(3, len(self.target.seen) - seen)
        self.assertEqual((3, 5), self.spent("race"))
        self.assertEqual(
            [("agent", "allowed"), ("agent", "allowed"), ("agent", "allowed"),
             ("agent", "blocked"), ("agent", "blocked"), ("agent", "blocked"),
             ("agent", "blocked"), ("agent", "blocked")],
            sorted(row[:2] for row in self.receipts("race")),
        )
        # And nothing is still held: every slot the race took was given back, so
        # a Program that ran out of total has not also lost its concurrency.
        self.assertEqual(
            0,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM egress_reservations"
                    " WHERE program_id = $1::uuid AND released_at IS NULL",
                    (program_id,),
                ).scalar()
            ),
        )

    def test_a_name_made_of_hexadecimal_is_a_name_and_not_an_address(self):
        # The address decision refuses a request whose *host* was already an
        # address and whose pinned address is a different one, because a caller
        # that resolved nothing has nothing to disagree about. Which hosts count
        # as addresses is therefore load-bearing: `cafe` is a legal single-label
        # hostname made entirely of hexadecimal digits, and a shape test loose
        # enough to call it an address would refuse it forever, whatever the
        # policy said. `1.2.3` is the same trap from the other side -- `inet`
        # widens it into an address and `scope_normalize_host` does not.
        capability, _, _ = self.mint("a")

        for host in ("cafe", "1.2.3", "app.example.com"):
            with self.subTest(host=host):
                self.fence.authorize_address(
                    self.identifiers["a"],
                    capability,
                    scope.canonical_request(f"http://{host}/notes"),
                    PINNED,
                )

        # And an address literal that disagrees with the pin is still refused,
        # which is the rule the shape test exists to apply. The pinned address
        # here is one no rule mentions, so the only thing left to refuse it is
        # the disagreement itself.
        with self.assertRaises(proxy.Refused) as raised:
            self.fence.authorize_address(
                self.identifiers["a"],
                capability,
                scope.canonical_request(f"http://{PINNED}/notes"),
                "93.184.216.36",
            )

        self.assertEqual("address refused", raised.exception.reason)
        self.assertIn("is not the address", raised.exception.detail)

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


#: The Programs the refusal case opens. Two of them, because one thing a
#: refusal must not be able to do is close a run another Program opened.
REFUSAL_SLUG = "selftest-refusal"


class StartupRefusalTest(DatabaseCase):
    """PH2-17: what a refused Agent run leaves behind, and what it does not.

    The transaction is reached the way the supervisor reaches it --
    `agent.close_refusal`, on a runtime connection bound to the Program -- and
    the run it closes is opened the way the scheduler opens one: a claimed Task
    with an attempt spent, a subagent run under it, the session binding a hook
    resolves a tool call through, and a lease on the Program's one Identity.
    Those four are what a refusal has to undo, and undoing all of them in one
    statement is the difference between a refusal that is durable and one that
    is half-applied.

    Everything here is a question only a server can answer: whether the cleanup
    commits as a whole, whether a repeat of it finds anything left, whether one
    Program can close another's run, what the transaction does with a payload
    that is not a refusal record, and whether the event log still accounts for
    every row afterwards.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)
        cls.identifiers = {}
        # One Program per test, because `tasks_live_dedup_idx` allows a Program
        # one live recon task with no subject, and every test here needs that
        # one. `onlooker` opens nothing: it is the second Program a refusal is
        # tried from, and having written nothing is the whole of its part.
        for name in (
            "closed",
            "recorded",
            "unowned",
            "onlooker",
            "malformed",
            "accounted",
            "launched",
        ):
            source = SCOPED + '\n[[identity]]\nname = "member"\nslot_ref = "slot://identity/member"\n'
            path = write(source.replace('name = "matrix-web"', f'name = "{REFUSAL_SLUG}-{name}"'))
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, opened.violations
            cls.identifiers[name] = opened.facts["program_id"]

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{REFUSAL_SLUG}-%",)
            )
        super().tearDownClass()

    def opened(self, name: str) -> tuple[str, str]:
        """One Agent run the way the scheduler opens one, and the Task under it.

        The Task and the lease are written by the owner because granting either
        is the scheduler's; the run and the session binding by the runtime,
        because opening either is the supervisor's. The Task carries a spent
        attempt and a priority so that giving them back is visible.
        """
        program_id = self.identifiers[name]
        task = self.owned(
            "INSERT INTO tasks (program_id, kind, status, attempts, claimed_at,"
            " lease_expires_at, priority)"
            " VALUES ($1::uuid, 'recon', 'claimed', 1, now(), now() + interval '10 minutes',"
            " 4.5) RETURNING id::text",
            (program_id,),
        )
        self.runtime.execute(agent.BIND, (program_id,))
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            run = str(
                self.runtime.execute(
                    "INSERT INTO agent_runs (program_id, task_id, role, kind, runs_as, model,"
                    " effort, mission_packet)"
                    " VALUES ($1::uuid, $2::uuid, 'recon', 'recon', 'subagent', 'operator',"
                    " 'low', $3::jsonb) RETURNING id::text",
                    (program_id, task, json.dumps({"objective": "Say nothing."})),
                ).scalar()
            )
            self.runtime.execute(
                "INSERT INTO agent_sessions (program_id, session_id, agent_run_id, task_id)"
                " VALUES ($1::uuid, $2, $3::uuid, $4::uuid)",
                (program_id, f"session-{run}", run, task),
            )
        self.owner(
            "INSERT INTO identity_leases"
            " (program_id, identity_entity_id, holder_agent_run_id, expires_at)"
            " SELECT $1::uuid, i.entity_id, $2::uuid, now() + interval '10 minutes'"
            "   FROM identities i"
            "  WHERE i.program_id = $1::uuid AND i.slot_name = 'member'"
            "    AND i.invalidated_at IS NULL",
            (program_id, run),
        )
        return run, task

    def state(self, run: str, task: str) -> dict:
        """The four rows one refusal is about, read back as one answer."""
        columns = (
            "finished",
            "stop_reason",
            "result",
            "status",
            "attempts",
            "claimed_at",
            "lease_expires_at",
            "priority",
            "bound",
            "leased",
        )
        row = self.connection.execute(
            "SELECT r.finished_at IS NOT NULL, r.stop_reason, r.result,"
            "       t.status, t.attempts, t.claimed_at, t.lease_expires_at, t.priority,"
            "       (SELECT count(*) FROM agent_sessions s"
            "         WHERE s.agent_run_id = r.id AND s.unbound_at IS NULL),"
            "       (SELECT count(*) FROM identity_leases l"
            "         WHERE l.holder_agent_run_id = r.id AND l.released_at IS NULL)"
            "  FROM agent_runs r JOIN tasks t ON t.id = r.task_id"
            " WHERE r.id = $1::uuid AND t.id = $2::uuid",
            (run, task),
        ).rows[0]
        return dict(zip(columns, row, strict=True))

    def refusals(self, run: str) -> list[str]:
        """Every `startup.refused` payload written for one run, as text.

        Text rather than parsed, because half of what is asked of it is that a
        string is *not* in it.
        """
        return [
            str(row[0])
            for row in self.connection.execute(
                "SELECT payload::text FROM events"
                " WHERE agent_run_id = $1::uuid AND type = 'startup.refused' ORDER BY seq",
                (run,),
            ).rows
        ]

    def test_one_call_closes_the_run_returns_its_task_and_releases_what_it_held(self):
        run, task = self.opened("closed")
        before = self.state(run, task)

        closed = agent.close_refusal(
            self.runtime, self.identifiers["closed"], run, startup_refusal()
        )

        self.assertEqual(
            ("claimed", 1, 1, 1),
            (before["status"], before["attempts"], before["bound"], before["leased"]),
        )
        self.assertTrue(closed)
        self.assertEqual(
            {
                "finished": True,
                "stop_reason": "refusal",
                "result": None,
                "status": "pending",
                "attempts": 0,
                "claimed_at": None,
                "lease_expires_at": None,
                "priority": None,
                "bound": 0,
                "leased": 0,
            },
            self.state(run, task),
        )

    def test_exactly_one_redacted_event_is_written_and_a_repeat_writes_none(self):
        run, task = self.opened("recorded")
        refusal = startup_refusal()

        first = agent.close_refusal(self.runtime, self.identifiers["recorded"], run, refusal)
        settled = self.state(run, task)
        again = agent.close_refusal(self.runtime, self.identifiers["recorded"], run, refusal)

        self.assertEqual((True, False), (first, again))
        self.assertEqual(settled, self.state(run, task))
        written = self.refusals(run)
        self.assertEqual(1, len(written))
        self.assertEqual(
            {
                "schema_version": 1,
                "phase": "pre_spawn",
                "sdk_version": _startup.KNOWN_RUNTIME[0],
                "cli_version": _startup.KNOWN_RUNTIME[1],
                "violations": [dict(record) for record in refusal.violations],
            },
            json.loads(written[0]),
        )
        self.assertNotIn(EXPORTED, written[0])

    def test_a_run_another_program_opened_is_not_one_this_session_may_close(self):
        run, task = self.opened("unowned")

        closed = agent.close_refusal(
            self.runtime, self.identifiers["onlooker"], run, startup_refusal()
        )

        self.assertFalse(closed)
        self.assertEqual([], self.refusals(run))
        self.assertEqual("claimed", self.state(run, task)["status"])

    def test_a_payload_that_is_not_refusal_records_closes_nothing(self):
        run, task = self.opened("malformed")
        self.runtime.execute(agent.BIND, (self.identifiers["malformed"],))
        records = '[{"code": "c", "vector": "v", "source": "s", "effect": "e"}]'

        for description, phase, violations in (
            ("a phase this runtime has no assertion in", "spawned", records),
            ("a refusal that refused nothing", "pre_spawn", "[]"),
            ("one record short of the shape", "pre_spawn", '[{"code": "c", "vector": "v"}]'),
            (
                "one record carrying the value it found",
                "pre_spawn",
                '[{"code": "c", "vector": "v", "source": "s", "effect": "e",'
                f' "value": "{EXPORTED}"}}]',
            ),
            ("records that are not a list", "pre_spawn", '{"code": "c"}'),
        ):
            with self.subTest(description):
                with self.assertRaises(pg.DatabaseError):
                    self.runtime.execute(
                        agent.CLOSE, (run, phase, *_startup.KNOWN_RUNTIME, violations)
                    )

        self.assertEqual([], self.refusals(run))
        self.assertEqual("claimed", self.state(run, task)["status"])

    def test_the_cleanup_leaves_the_log_accounting_for_every_row_it_touched(self):
        run, _ = self.opened("accounted")

        agent.close_refusal(self.runtime, self.identifiers["accounted"], run, startup_refusal())

        self.assertEqual(
            (),
            self.connection.execute(
                "SELECT problem, detail, count FROM check_event_log_integrity($1::uuid)",
                (self.identifiers["accounted"],),
            ).rows,
        )

    def test_a_refused_launch_is_cleaned_up_before_the_refusal_reaches_its_caller(self):
        run, task = self.opened("launched")
        request = agent.AgentRunRequest(
            agent_run_id=run,
            objective="Say nothing.",
            container=boundary(),
            role=ROLE,
            program_id=self.identifiers["launched"],
        )

        with unlatched():
            with mock.patch.object(agent, "_spawn", side_effect=startup_refusal()):
                with self.assertRaises(agent.StartupRefusal):
                    agent.agent_run(request, self.runtime)

        self.assertEqual("pending", self.state(run, task)["status"])
        self.assertEqual(1, len(self.refusals(run)))


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
