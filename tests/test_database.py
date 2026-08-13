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
    _launch,
    _startup,
    agent,
    artifact,
    backup,
    callback,
    config,
    decisions,
    execution,
    header,
    identity,
    integrity,
    migrate,
    packet,
    pg,
    program,
    proposal,
    proxy,
    roster,
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
    Ledger,
    Report,
)
from redkraken.store import Store
from tests.fixtures import (
    EXPORTED,
    FIRST,
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
    latched,
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
#:
#: The key generation is written `ON CONFLICT DO NOTHING` because it is not part
#: of the falsification: a seal needs a generation on record, and the first
#: sealed wire artifact of the installation establishes one and commits it. Any
#: suite that reaches a live door before this one runs leaves generation 1
#: behind, and a control that insisted on writing it would fail on the row it
#: only needs to exist.
SEAL_CONTROL = (
    "DO $ctl$ DECLARE p uuid;"
    " BEGIN"
    "   PERFORM set_actor('runtime', 'selftest');"
    "   INSERT INTO programs (slug, name) VALUES ('sealed-selftest', 'Self test')"
    "     RETURNING id INTO p;"
    "   INSERT INTO secret_kek (gen, salt, root_check)"
    "        VALUES (1, decode(repeat('61', 32), 'hex'), decode(repeat('62', 16), 'hex'))"
    "     ON CONFLICT (gen) DO NOTHING;"
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
        # Detached rather than falsified with a row, because the check's first
        # business is structural: the grammar is what keeps an edge with an
        # undefined direction from existing, and a disabled trigger is the state
        # in which the other arms would have something to find.
        "standing:surface_promotion",
        "ALTER TABLE relationships DISABLE TRIGGER relationships_follow_the_grammar",
    ),
    Control(
        # A section registered without the three delta kinds derived from it.
        # Structural for the same reason: a projection section nothing compares
        # is a class of change that stops being detected silently, and every
        # data arm of this check would still read as clean.
        "standing:surface_fingerprint",
        "INSERT INTO surface_projection_sections (section, delta_prefix, note)"
        " VALUES ('selftest_section', 'selftest', 'a section with no delta kinds')",
    ),
    Control(
        # A clock inside the eligibility rule, which is the one thing that
        # would make two passes over the same rows disagree. Structural because
        # that is where determinism lives: no row can be wrong in a way that
        # falsifies it, and the arm reads the function's own text.
        "standing:slate_claim",
        "CREATE OR REPLACE FUNCTION identity_held_for(t tasks) RETURNS boolean"
        " LANGUAGE sql STABLE AS $ctl$ SELECT now() IS NOT NULL $ctl$",
    ),
    Control(
        # The second clock, which is the failure a Lease cannot survive: two
        # halves of one hold written from a timestamp that advances between the
        # two statements do not expire together, and a run whose Task Lease is
        # alive beside a dead Identity Lease is exactly what the glossary
        # forbids. Structural, because no row can be wrong in a way that shows
        # it -- the two expiries would differ by microseconds and look right.
        "standing:lease_liveness",
        "CREATE OR REPLACE FUNCTION heartbeat_leases(p_agent_run uuid) RETURNS jsonb"
        " LANGUAGE sql AS $ctl$ SELECT to_jsonb(clock_timestamp()) $ctl$",
    ),
    Control(
        # A model identifier spelled in SQL. `claude-opus-5` is what one measured
        # SDK/CLI pair resolves the alias `opus` to, and the manifest that records
        # the resolution is bound to that pair; a copy in a function body is a
        # value that goes stale on the day the pair changes, without moving and
        # without anything reading it noticing. Structural for the same reason
        # the slate's is: no row is wrong, the text is.
        "standing:roster_model_and_effort",
        "CREATE FUNCTION selftest_model_for_role() RETURNS text"
        " LANGUAGE sql IMMUTABLE AS $ctl$ SELECT 'claude-opus-5'::text $ctl$",
    ),
    Control(
        # The cross-role subagent cap, counted correctly and bounded by a copy
        # of the number instead of by the row that holds it. Structural for the
        # third time and for the third version of the same reason: with the
        # weights row at 3 this function answers exactly what the scheduler
        # answers, and it starts lying on the day an operator moves the row --
        # which is the day nothing would be watching it.
        "standing:subagent_cap",
        "CREATE FUNCTION selftest_subagent_cap_reached() RETURNS boolean"
        " LANGUAGE sql STABLE AS $ctl$"
        " SELECT (SELECT count(*) FROM tasks c"
        "           JOIN effective_lane_capacity lc"
        "             ON lc.program_id = c.program_id AND lc.kind = c.kind"
        "           JOIN roles r ON r.role = lc.role"
        "          WHERE c.status IN ('claimed','running')"
        "            AND r.runs_as = 'subagent') >= 3 $ctl$",
    ),
    Control(
        # Capacity held out of the pool for a run that has already ended. Written
        # by hand because no call reaches it: the trigger on `finished_at`
        # settles the reservation in the same statement that closes the run, so
        # this is what a restore or a hand-written row leaves behind -- and it is
        # a Program that has silently shrunk, since nothing will ever give the
        # tokens back. The run is inserted already finished for that reason: a
        # closure would have settled it on the way past.
        "standing:budget_reservations",
        "DO $ctl$ DECLARE p uuid; t uuid; r uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('reserved-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO tasks (program_id, kind, status, finished_at)"
        "        VALUES (p, 'recon', 'done', now()) RETURNING id INTO t;"
        "   INSERT INTO agent_runs (program_id, task_id, role, runs_as, model, effort,"
        "                           mission_packet, finished_at, stop_reason)"
        "        VALUES (p, t, 'recon', 'subagent', 'selftest', 'low', '{}'::jsonb,"
        "                now(), 'completed') RETURNING id INTO r;"
        "   INSERT INTO budget_reservations (program_id, agent_run_id, task_id, kind, tokens)"
        "        VALUES (p, r, t, 'recon', 1000);"
        " END $ctl$",
    ),
    Control(
        # An unlock term that pays for every edge pointed at a Task, including
        # the ones a model wrote about itself. The arithmetic is otherwise
        # correct and the result is still bounded, so nothing downstream can
        # tell -- the priority simply becomes a number anyone with INSERT on
        # `task_dependencies` can raise. The basis table is the whole defence,
        # and this is what its absence looks like.
        "standing:task_ranking",
        "CREATE OR REPLACE FUNCTION unlock_for(t tasks, w scheduler_weights)"
        " RETURNS numeric LANGUAGE sql STABLE AS $ctl$"
        " SELECT least(coalesce(sum(value_for(b, w)), 0), 1.0)"
        "   FROM task_dependencies d"
        "   JOIN tasks b ON b.id = d.task_id"
        "  WHERE d.unlocked_by_task_id = t.id"
        "    AND d.program_id = t.program_id"
        "    AND b.status = 'pending' $ctl$",
    ),
    Control(
        # The grant 029's default privileges would have made on their own. It is
        # one statement, it leaves the function working, and it hands the
        # scheduler's weights to the connection a model reaches through.
        "standing:task_ranking",
        "GRANT EXECUTE ON FUNCTION version_scheduler_weights(jsonb) TO rk2_runtime",
    ),
    Control(
        # Dropping the trigger leaves every row, every grant and every other arm
        # of the check exactly as they were, and turns `basis` back into a
        # column anything holding the runtime connection can write
        # `runtime_rule` into. The soundness vocabulary is then a lookup table
        # that agrees with whatever it is told.
        "standing:task_ranking",
        "DROP TRIGGER task_dependencies_sound_basis_is_derived ON task_dependencies",
    ),
    Control(
        # An admission rule that admits everything, which is one way of no
        # longer asking which role may load a Task's Skills. Structural for the
        # reason the slate's clock control is: the failure is in the text, and a
        # rule that stopped asking would leave every row looking exactly as it
        # does now until a child failed at load time inside a started container.
        "standing:orchestrator_dispatch",
        "CREATE OR REPLACE FUNCTION claimable_for(t tasks, w scheduler_weights)"
        " RETURNS text LANGUAGE sql STABLE AS $ctl$ SELECT NULL::text $ctl$",
    ),
    Control(
        # A recorded choice with a sixth word in it. The runtime branches on
        # five, so this is an outcome nothing downstream has an answer for --
        # and it is written by hand because `record_choice` cannot produce it:
        # the point of the arm is the row a restore or a later verb could leave.
        "standing:orchestrator_dispatch",
        "DO $ctl$ DECLARE p uuid; r uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('chose-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet)"
        "        VALUES (p, 'orchestrator', 'session', 'operator', 'low', '{}'::jsonb)"
        "     RETURNING id INTO r;"
        "   INSERT INTO events (program_id, type, actor_kind, agent_run_id, payload)"
        '        VALUES (p, \'scheduler.chose\', \'llm\', r, \'{"outcome": "probably"}\'::jsonb);'
        " END $ctl$",
    ),
    Control(
        # A choice nothing made. An Event naming no session is a decision with
        # no decider: the run that chose is the one thing that says which model,
        # at which effort, under which caps, answered the way it did.
        "standing:orchestrator_dispatch",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('unattributed-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO events (program_id, type, actor_kind, payload)"
        '        VALUES (p, \'scheduler.chose\', \'llm\', \'{"outcome": "chosen"}\'::jsonb);'
        " END $ctl$",
    ),
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
        " VALUES (1, decode(repeat('61', 32), 'hex'), decode(repeat('62', 16), 'hex'))"
        " ON CONFLICT (gen) DO NOTHING;"
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
    # --- the end of one attempt ----------------------------------------------
    Control(
        # The first arm, and the leak criterion 5 names first: a Task closed as
        # done that no promotion accounts for. An INSERT rather than an UPDATE
        # because `tasks_completion_needs_promotion` is BEFORE UPDATE, which is
        # the whole reason the row arm exists beside the trigger -- the trigger
        # closes the path the runtime takes, and the check reads the row however
        # it arrived.
        "standing:execution_closure",
        "DO $ctl$ DECLARE p uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('closed-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO tasks (program_id, kind, status, finished_at)"
        "        VALUES (p, 'recon', 'done', now());"
        " END $ctl$",
    ),
    Control(
        # The arm `finish_task_attempt`'s ordering exists for: the Agent run
        # ended and a Tool run of it is still open. Written by hand because no
        # call produces it -- the closing updates the Tool runs first, so this
        # is the state a crash between the two leaves, and the only one that
        # holds a capability nothing will revoke.
        "standing:execution_closure",
        "DO $ctl$ DECLARE p uuid; r uuid;"
        " BEGIN"
        "   PERFORM set_actor('runtime', 'selftest');"
        "   INSERT INTO programs (slug, name) VALUES ('half-closed-selftest', 'Self test')"
        "     RETURNING id INTO p;"
        "   INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet,"
        "                           finished_at, stop_reason)"
        "        VALUES (p, 'orchestrator', 'session', 'operator', 'low', '{}'::jsonb,"
        "                now(), 'completed')"
        "     RETURNING id INTO r;"
        "   INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport)"
        f"        VALUES (p, r, '{proxy.TOOL}', '{{}}'::jsonb, 'running', 'runtime');"
        " END $ctl$",
    ),
    Control(
        # The structural arm, and the same demotion the callback control makes:
        # the guard still holds on this connection and is skipped by the one
        # connection that replays rows nobody re-checks. A Task that closed
        # during a restore would be indistinguishable from one the runtime
        # accepted a result for.
        "standing:execution_closure",
        "ALTER TABLE tasks DISABLE TRIGGER tasks_completion_needs_promotion",
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

        # By the rows, not by the size on disk. The size is the one column that
        # moves without a write -- autovacuum reached this database mid-test once
        # and grew it by twelve pages while every digest below stayed identical --
        # and it is also the one column that could not have caught the write it
        # would have been catching: a single row does not move a page count.
        self.assertEqual(before[ROWS], after[ROWS])
        self.assertGreaterEqual(after[0], before[0], "reading does not shrink a database")
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

    def test_the_artifact_list_reaches_this_programs_references_and_no_others(self):
        # How a label becomes learnable at all. The Receipt records the child
        # reads carry `request_agent_sha` and `response_agent_sha`, and a hash
        # is not an argument this surface takes -- so listing is the one path
        # from "I am holding a Receipt" to "I may fetch its transcript", and it
        # is a path that stops at this Program's own references.
        answer = packet.Reader(self.compiled("a")).artifact()

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


#: The limits `SCOPED` states, in the order it states them. Written as a table
#: and rendered rather than copied nine times: every fragment below differs from
#: this one in a limit or two, and nine literal numbers per fragment is nine
#: chances for an unrelated ceiling to drift when the loader gains a key.
SCOPED_LIMITS = {
    "requests": 100,
    "tokens": 10000,
    "run_tokens": 2000,
    "run_requests": 10,
    "lane_tokens": 5000,
    "lane_requests": 50,
    "concurrency": 1,
    "burst": 100,
    "window_seconds": 60,
}


def budgets(**overrides: int) -> str:
    """One `[budgets]` block, `SCOPED`'s limits with the named ones moved."""
    limits = SCOPED_LIMITS | overrides
    return "\n".join(f"{limit} = {limits[limit]}" for limit in SCOPED_LIMITS)


#: The `[budgets]` block `SCOPED` carries, so that a Program built from it can be
#: given a different one. Matched as the whole block rather than line by line: a
#: partial replacement would leave a document whose limits half agree.
SCOPED_BUDGETS = budgets()

#: What every Program in the suite below gets unless it is a Program about
#: budgets. Wide on purpose: a limit shared by tests that are not about it is a
#: limit that makes adding an unrelated test break an unrelated assertion, and
#: `SCOPED` is tight enough that the suite would run into its own ceiling. The
#: per-run and per-Lane ceilings are the whole of the aggregate for the same
#: reason: what these Programs are stopped by has to be the limit each is named
#: for, and 25's admission arms are not it.
WIDE_ENOUGH = budgets(
    requests=500, lane_requests=500, concurrency=4, burst=500, window_seconds=3600,
    lane_tokens=10000,
)

#: And the Programs that exist to be stopped, each named for the limit it hits.
#: A window of an hour against a burst of two is a refill of one token every half
#: hour, which is what makes `throttle` a test of the limit rather than of how
#: fast the suite runs.
BUDGETS = {
    "budget": budgets(
        requests=2, run_requests=1, lane_requests=2, concurrency=4, burst=500,
        window_seconds=3600, lane_tokens=10000,
    ),
    "throttle": budgets(
        requests=500, lane_requests=500, concurrency=4, burst=2, window_seconds=3600,
        lane_tokens=10000,
    ),
    "concurrent": budgets(
        requests=500, lane_requests=500, concurrency=1, burst=500, window_seconds=3600,
        lane_tokens=10000,
    ),
    "race": budgets(
        requests=3, run_requests=1, lane_requests=3, concurrency=8, burst=500,
        window_seconds=3600, lane_tokens=10000,
    ),
    "halted": budgets(
        requests=500, lane_requests=500, concurrency=4, burst=500, window_seconds=3600,
        lane_tokens=10000,
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
        # Held for the same reason as `arrived` above, and for a sharper one: the
        # https target is shared with the case that sends a POST through a human
        # decision, and that case sorts first, so "the last thing it saw" is that
        # POST rather than the tunnelled GET this report is about.
        cls.secure_arrived = cls.secure_target.seen[-1]

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
        method, path, headers = self.secure_arrived
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


#: The Programs the execution slice runs in. One per scenario, because the
#: slice claims from a Program's own queue: two scenarios sharing one would be
#: two attempts competing for the same Task, and whichever lost would be a test
#: of the scheduler rather than of the slice.
EXECUTION_SLUG = "selftest-execution"

#: What the child claims to have established. `endpoint_discovered` is the one
#: recon-shaped row of `observation_kinds` a plain http Receipt may back: every
#: evidential kind is a comparison one request cannot make, and
#: `transport_parameters_observed` is admissible only from the measurement lane.
DISCOVERED = "endpoint_discovered"

#: The address the seeded Task is about, as the Program's own rows spell it: an
#: application whose base is the host `SCOPED` includes, and one endpoint under
#: it. Together they have to join to `URL`, because that is the request the
#: matrix already decides and the door already has a target for.
HOST = "app.example.com"
BASE_URL = f"http://{HOST}"
PATH = "/notes"

#: The budget these Programs carry, and its width is not arbitrary.
#: `rank_candidates` calls a Task affordable only where `tokens_left` covers
#: `estimated_cost * cost_reference_tokens`, and a recon Task with no run
#: history to shrink towards costs the 0.30 prior of a 200000-token reference.
#: Under `SCOPED`'s own 10000 no Task in this suite would ever be offered, and
#: that reads as an idle queue rather than as a budget that is too small.
#: The per-run and per-Lane ceilings are wide for the same reason and one more:
#: what a claim reserves is the per-run number, so a Lane ceiling near it would
#: admit one claim and refuse the next -- which is 25's own subject and not the
#: subject of any suite that carries this.
AFFORDABLE = budgets(
    requests=500, tokens=1000000, run_tokens=40000, run_requests=50,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)



class Child:
    """A launcher that spends the capability it was handed, and reports back.

    Not a container, and it makes no claim to be one: what an engine does with
    an image is `redkraken.isolation`'s subject and is asserted there. What this
    stands in for is the one thing the slice needs a child for -- a request made
    with the capability the runtime minted, and a structured result citing what
    that request produced.

    The request goes through `_launch._spend`, which is the function the served
    tool calls inside a real child. A hand-rolled request here would be a second
    client, and the door's answer -- which decides whether the Tool run closes
    as served or as denied -- would be parsed in two places.

    It answers as two children, because one pass starts two: the orchestrator
    session that chooses off the Slate, and the worker that runs what was
    claimed. They are kept in separate lists rather than told apart by index --
    a planning run that stopped happening would otherwise shift every assertion
    about the worker by one and still pass.

    The choice it makes is the first entry it was offered, through the same
    latch a real child picks with. `_launch.Choice` is what refuses an off-Slate
    label and what supersedes an earlier pick, so a fixture that set the field
    directly would be reporting a choice no tool would have accepted.
    """

    def __init__(
        self,
        subject: str,
        *,
        observations: list[dict] | None = None,
        completion: str = "complete",
        picks: object = FIRST,
    ) -> None:
        self.subject = subject
        self.overrides = observations
        self.completion = completion
        self.picks = picks
        self.requests: list[agent.AgentRunRequest] = []
        self.choices: list[agent.AgentRunRequest] = []
        self.answers: list[dict] = []

    def __call__(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        if request.role == roster.ORCHESTRATOR:
            return self.choose(request)
        self.requests.append(request)
        if request.egress is not None:
            self.answers.append(_launch._spend(request.egress, URL, "GET"))
        return agent.AgentRunResult(
            agent_run_id=request.agent_run_id,
            role=request.role,
            sdk_version="selftest",
            cli_version="selftest",
            api_key_source="none",
            tool_ready=1,
            tools_served=agent.SERVED,
            denials=(),
            answers=1,
            stop_reason="completed",
            text="one request, one observation",
            mission_result=self.result(),
            mission_attempts=1,
        )

    def choose(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        """What the orchestrator session answers: one pick, or nothing.

        The pick goes through `fixtures.latched`, which is the latch a served
        `pick_task` writes into, so what comes back is what the tool would have
        returned rather than what this fixture would like it to be.
        """
        self.choices.append(request)
        latch = latched(request.slate, self.picks)
        return agent.AgentRunResult(
            agent_run_id=request.agent_run_id,
            role=request.role,
            sdk_version="selftest",
            cli_version="selftest",
            api_key_source="none",
            tool_ready=1,
            tools_served=agent.SERVED,
            denials=(),
            answers=1,
            stop_reason="completed",
            text=f"{len(latch.entries)} offered",
            choice=latch.task,
            pick_attempts=latch.attempts,
        )

    def result(self) -> dict:
        """What the child submits: one Observation and one completion claim."""
        answer = self.answers[-1] if self.answers else {}
        return {
            "observations": (
                self.overrides
                if self.overrides is not None
                else [
                    {
                        "kind": DISCOVERED,
                        "subject_label": self.subject,
                        "receipt_label": answer.get("receipt"),
                        "summary": f"{URL} answered {answer.get('status')} through the door",
                    }
                ]
            ),
            "completion_claim": {"status": self.completion, "note": "one request, read"},
        }


#: Every row one attempt produced, read from the Receipt outwards. One query
#: rather than six, because what criterion 2 asks is whether they agree, and six
#: queries would each be right about a row while saying nothing about the six.
ATTEMPT = (
    "SELECT r.program_id::text  AS receipt_program,"
    "       tr.program_id::text AS tool_run_program,"
    "       ar.program_id::text AS agent_run_program,"
    "       t.program_id::text  AS task_program,"
    "       pr.program_id::text AS proposal_program,"
    "       tr.agent_run_id::text AS tool_run_of,"
    "       tr.task_id::text      AS tool_run_on,"
    "       ar.id::text           AS agent_run,"
    "       ar.task_id::text      AS agent_run_on,"
    "       t.id::text            AS task,"
    "       pr.agent_run_id::text AS proposal_of,"
    "       pr.task_id::text      AS proposal_on,"
    "       r.lane                AS lane,"
    "       r.decision            AS decision"
    "  FROM receipts r"
    "  JOIN tool_runs tr  ON tr.id = r.tool_run_id"
    "  JOIN agent_runs ar ON ar.id = tr.agent_run_id"
    "  JOIN tasks t       ON t.id = ar.task_id"
    "  JOIN proposals pr  ON pr.task_id = t.id"
    " WHERE r.label = $1 AND r.program_id = $2::uuid"
)

#: The whole of criterion 5 about one finished attempt, as one row. Not a copy
#: of `check_execution_closure()`: that function asks the same questions of the
#: whole installation and is asserted as itself below, and a second copy of its
#: five arms here would be a second statement of the same rule.
SETTLED = (
    "SELECT t.status, t.lease_expires_at, t.finished_at,"
    "       ar.finished_at, ar.stop_reason,"
    "       tr.status, tr.finished_at, tr.egress_token_sha256, tr.egress_token_expires_at,"
    "       (SELECT count(*)::int FROM identity_leases l"
    "         WHERE l.holder_agent_run_id = ar.id AND l.released_at IS NULL),"
    "       (SELECT count(*)::int FROM proposals pr"
    "         WHERE pr.task_id = t.id AND pr.status = 'promoted')"
    "  FROM agent_runs ar"
    "  JOIN tasks t       ON t.id = ar.task_id"
    "  JOIN tool_runs tr  ON tr.agent_run_id = ar.id"
    " WHERE ar.id = $1::uuid"
)

#: The two arms of the standing check that are about the installation rather
#: than about any Program's rows. Asserted machine-wide because that is what
#: they are: a detached completion guard or an `observations` table that stopped
#: emitting Events is wrong everywhere at once.
STRUCTURAL = ("completion_guard_detached", "promotion_writes_no_event")


#: What of one attempt's report is a decision, section by section. Everything
#: left out is either a row identifier or a machine-wide counter, and that is
#: exactly the distinction criterion 6 draws: two Programs seeded alike must
#: reach the same verdicts and hand out the same per-Program labels, and must
#: share no single row identifier while doing it. `None` keeps the whole value.
#:
#: The slate is a list, and every field of an entry is a decision except
#: `expires_at`, which is the one clock reading in it. Naming the rest rather
#: than dropping the section is the point of ticket 23's criterion 1: a rank
#: that differed between two identically seeded Programs would mean the ranking
#: pass read something other than its rows and its weights version.
DECIDED = {
    #: Counts, all of them, and on a seeded Program all of them zero. Kept
    #: whole because a reconciliation that recovered something here would mean
    #: one of the two Programs had a lapsed Lease the other did not.
    "reconciliation": None,
    #: `beats` and the `identities` the last beat saw are how long the child
    #: took divided by the interval, which is this machine's load and not a
    #: decision. `every` is, and so is either way it can stop.
    "heartbeat": ("every", "lapsed", "failure"),
    "slate": ("ordinal", "task", "kind", "subject", "priority", "factors",
              "entitled"),
    #: What one decision came to. The label is kept for the reason the run
    #: labels are: two Programs seeded alike open their sessions in the same
    #: order and must name them the same. `detail` is left out because the one
    #: thing that fills it is a refusal message from the server.
    "choice": ("agent_run", "outcome", "task", "attempts"),
    "task": ("label", "kind", "attempts", "subject", "subject_type"),
    "agent_run": ("label", "role", "stop_reason"),
    "target": None,
    "packet": ("sections",),
    "tool_run": ("label", "decision"),
    "receipt": None,
    "proposal": ("label", "status", "completion", "drops"),
    "promotion": None,
    "fingerprint": None,
    "closure": ("task_status", "accepted", "runs_closed", "tool_runs_closed",
                "leases_released"),
}


def _kept(value: object, fields: tuple[str, ...] | None) -> object:
    """One section of a report, narrowed to the named fields.

    A list is narrowed entry by entry rather than kept whole, because a section
    that is a sequence of rows -- the slate -- is still a sequence of decisions.
    """
    if fields is None or value is None:
        return value
    if isinstance(value, list):
        return [_kept(entry, fields) for entry in value]
    return {name: value[name] for name in fields}


def decided(facts: dict) -> dict:
    """One attempt's verdicts, without the identifiers two attempts must differ in."""
    return {key: _kept(value, DECIDED[key]) for key, value in facts.items()}


class ExecutionSliceTest(DatabaseCase):
    """PH2-20: one seeded Task run to a canonical Observation, and closed.

    The half of ticket 20 only a server can answer. `tests/test_execution.py`
    holds the other half -- what the sequence does with each answer -- against a
    recorder; here the queue is the real scheduler, the capability is minted by
    `authorize_tool_run` and spent through a real door, the Observation is
    promoted by `promote_proposal`, and what closes the attempt is
    `finish_task_attempt`.

    Two things make this the production path rather than a rehearsal of it. The
    request the child makes is `_launch._spend`, which is what the served tool
    calls inside a real container. And the promotion runs on `rk2_runtime`, the
    role an operator actually points at the database, against rows the
    `rk2_state` connection that compiled the packet cannot write.

    What stands in for the container is `Child`. The boundary itself is
    described rather than started, because an engine is not available in the
    assertion suite and because what this case is about is the order of the
    steps either side of the child -- which is exactly the part a launcher seam
    leaves intact.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)
        cls.root = scratch() / "execution-store"

        cls.identifiers = {}
        cls.configurations = {}
        for name in ("grounded", "prose", "twin-a", "twin-b"):
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, AFFORDABLE).replace(
                    'name = "matrix-web"', f'name = "{EXECUTION_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]

        # `SCOPED` declares a required header, and a declared header with no
        # provisioned value is a request the door refuses before it dials. So
        # this exists for the same reason the target does: what is under test is
        # what reaches the wire, and a Program that cannot reach it tests nothing.
        cls.root_secret = seal.Root(Path("live-execution-selftest-root"), SECRET)
        value = scratch() / "execution-bounty-id.txt"
        value.write_text("rk2-selftest-bounty-20", encoding="utf-8")
        for name, path in cls.configurations.items():
            sealed = header.provision(
                cls.harness.runtime, path, "X-Bounty-Id", value, root_secret=cls.root_secret
            )
            assert sealed.ok, (name, sealed.violations)

        cls.target, _ = counterparty(LiveTarget)
        cls.authority = tls.authority(scratch() / "execution-authority")
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
        cls.boundary = boundary(
            proxy_url=f"http://127.0.0.1:{cls.server.server_address[1]}"
        )

        # Every attempt the assertions read, run here because they commit: an
        # attempt repeated per test would be a second attempt on a Task the
        # first one closed, and one run in a test would make the test that
        # reads it depend on which test ran first.
        cls.subject, cls.task = cls.seed("grounded")
        cls.child = Child(cls.subject)
        cls.ledger = Ledger()
        cls.facts = cls.attempt("grounded", cls.child, cls.ledger)

        # Everything about this one is a success except the thing that counts:
        # the child made its request, read the answer and claimed to have
        # finished -- citing a Receipt that does not exist.
        ungrounded, _ = cls.seed("prose")
        cls.prose = cls.attempt(
            "prose",
            Child(
                ungrounded,
                observations=[
                    {
                        "kind": DISCOVERED,
                        "subject_label": ungrounded,
                        "receipt_label": "R404",
                        "summary": "an endpoint I am sure about",
                    }
                ],
            ),
            Ledger(),
        )

        cls.twins = {}
        for name in ("twin-a", "twin-b"):
            twin, _ = cls.seed(name)
            ledger = Ledger()
            cls.twins[name] = cls.attempt(name, Child(twin), ledger)
            assert not list(ledger.violations), (name, ledger.violations)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.fence.close()
        cls.target.shutdown()
        cls.target.server_close()
        cls.runtime.close()

        stored = [
            str(row[0])
            for row in cls.connection.execute(
                "SELECT DISTINCT unnest(ARRAY[request_agent_sha, response_agent_sha,"
                "                             request_wire_sha, response_wire_sha])"
                "  FROM receipts r JOIN programs p ON p.id = r.program_id"
                " WHERE p.slug LIKE $1",
                (f"{EXECUTION_SLUG}-%",),
            ).rows
            if row[0] is not None
        ]
        ciphertexts = [
            str(row[0])
            for row in cls.connection.execute(
                "SELECT s.ciphertext_sha256 FROM artifact_seal s JOIN programs p"
                "    ON p.id = s.scope_id AND s.scope_kind = 'program'"
                " WHERE p.slug LIKE $1",
                (f"{EXECUTION_SLUG}-%",),
            ).rows
        ]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM secret_access_log WHERE program_id IN"
                " (SELECT id FROM programs WHERE slug LIKE $1)",
                (f"{EXECUTION_SLUG}-%",),
            )
            cls.connection.execute(
                "DELETE FROM artifact_seal WHERE scope_kind = 'program' AND scope_id IN"
                " (SELECT id FROM programs WHERE slug LIKE $1)",
                (f"{EXECUTION_SLUG}-%",),
            )
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{EXECUTION_SLUG}-%",)
            )
            if stored:
                cls.connection.execute(
                    "DELETE FROM artifacts WHERE sha256 = ANY($1)",
                    ("{" + ",".join(stored) + "}",),
                )
        keep = Store(cls.root)
        for sha256 in (*stored, *ciphertexts):
            keep.discard(sha256)
        super().tearDownClass()

    @classmethod
    def look_up(cls, host: str, port: int) -> tuple[str, ...]:
        """What the names in this suite resolve to, without asking a real zone."""
        return (PINNED,)

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
        """The one authorised name reaches the one target this machine is running.

        The pinned `address` is not dialled, because no test on this machine can
        route to a public one. Everything before this point -- resolution,
        routability, the door's second decision -- happened for real.
        """
        return http.client.HTTPConnection(
            "127.0.0.1", cls.target.server_address[1], timeout=timeout
        ), None

    @classmethod
    def seed(cls, name: str) -> tuple[str, str]:
        """One in-scope endpoint under one application, and a Task about it.

        Written as the owner and in one transaction, because an endpoint whose
        application did not commit with it is a subject the slice would resolve
        no address for -- which is a different test than this one.

        Both entities are created through `add_entity`, which is the only way an
        in-scope one comes to exist: an entity is born denied and `in_scope` is
        projected from the policy, so a fixture that asserted scope itself would
        be seeding a Task the scheduler would never have offered. The labels are
        left to the database for the same reason -- `assign_entity_label` is what
        a Program's rows are named by, and naming them here would be asserting
        against this file's own spelling.
        """
        program_id = cls.identifiers[name]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            application = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'application', '', 'host', $2, 80, $3)",
                    (program_id, HOST, f"application:{BASE_URL}"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO applications (entity_id, base_url, kind)"
                " VALUES ($1::uuid, $2, 'web')",
                (application, BASE_URL),
            )
            endpoint = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'endpoint', '', 'host', $2, 80, $3)",
                    (program_id, HOST, f"endpoint:GET {PATH}"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO endpoints (entity_id, application_id, method, path_template)"
                " VALUES ($1::uuid, $2::uuid, 'GET', $3)",
                (endpoint, application, PATH),
            )
            cls.connection.execute(
                "INSERT INTO tasks (program_id, kind, status, subject_entity_id)"
                " VALUES ($1::uuid, 'recon', 'pending', $2::uuid)",
                (program_id, endpoint),
            )
            subject = str(
                cls.connection.execute(
                    "SELECT label FROM entities WHERE id = $1::uuid", (endpoint,)
                ).scalar()
            )
        return subject, endpoint

    @classmethod
    def attempt(cls, name: str, child: Child, ledger: Ledger) -> dict:
        """One slice, run against one Program on the runtime's own connection."""
        return execution.Slice(
            boundary=cls.boundary, state=cls.harness.state, launch=child
        ).attempt(ledger, cls.runtime, cls.identifiers[name])

    # -- criterion 1: one Task, one role, one bounded packet, one request ------

    def test_the_slice_claimed_one_task_and_ran_it(self):
        facts = self.facts

        self.assertEqual([], list(self.ledger.violations), self.ledger.violations)
        self.assertEqual(1, len(facts["slate"]))
        self.assertEqual("recon", facts["task"]["kind"])
        self.assertEqual(1, facts["task"]["attempts"])
        self.assertEqual(self.subject, facts["task"]["subject"])
        self.assertEqual("recon", facts["agent_run"]["role"])
        self.assertEqual({"url": URL, "method": "GET"}, facts["target"])

    def test_the_child_was_started_inside_the_boundary_with_one_capability(self):
        self.assertEqual(1, len(self.child.requests))
        started = self.child.requests[0]

        self.assertIs(self.boundary, started.container)
        self.assertEqual("recon", started.role)
        self.assertEqual(self.identifiers["grounded"], started.program_id)
        self.assertEqual(self.facts["agent_run"]["id"], started.agent_run_id)
        self.assertIsNotNone(started.packet)
        self.assertIsNotNone(started.egress)
        self.assertEqual(self.boundary.proxy_url, started.egress.proxy_url)
        # The capability lives about five minutes, and the child is given no
        # longer: turns spent after it lapses cannot reach anything.
        self.assertLessEqual(started.timeout, 300.0)
        self.assertGreater(started.timeout, 0.0)

    def test_the_packet_the_child_read_was_compiled_as_the_agent_role(self):
        # `packet.compile` runs on the state connection and refuses any other,
        # so a packet existing at all is the claim: what the child may read was
        # bounded by row level security rather than by this runtime's own reach.
        # Its surface is what that connection could see of this Program, which
        # is the application and the endpoint and nothing of the other three.
        sections = self.facts["packet"]["sections"]

        self.assertEqual(set(packet.SECTIONS), set(sections))
        self.assertEqual(2, sections["surface"])
        self.assertEqual(0, sections["receipts"])

    def test_the_one_request_was_served_through_the_door(self):
        self.assertEqual(1, len(self.child.answers))
        answer = self.child.answers[0]

        self.assertTrue(answer["served"], answer)
        self.assertEqual(200, answer["status"])
        self.assertIsNone(answer["decision"])
        self.assertEqual(ANSWER.decode(), answer["body"])
        self.assertEqual(answer["receipt"], self.facts["receipt"]["label"])
        self.assertEqual("allowed", self.facts["receipt"]["decision"])

    # -- criterion 2: one Program and one cause across every row --------------

    def test_every_row_of_the_attempt_names_one_program_and_one_cause(self):
        program_id = self.identifiers["grounded"]
        row = self.connection.execute(
            ATTEMPT, (self.facts["receipt"]["label"], program_id)
        ).dicts()[0]

        self.assertEqual(
            {program_id},
            {
                row["receipt_program"],
                row["tool_run_program"],
                row["agent_run_program"],
                row["task_program"],
                row["proposal_program"],
            },
        )
        self.assertEqual(
            {self.facts["agent_run"]["id"]},
            {row["tool_run_of"], row["agent_run"], row["proposal_of"]},
        )
        self.assertEqual(
            {self.facts["task"]["id"]},
            {row["tool_run_on"], row["agent_run_on"], row["task"], row["proposal_on"]},
        )
        self.assertEqual("agent", row["lane"])
        self.assertEqual("allowed", row["decision"])

    def test_the_response_artifact_is_reachable_from_the_receipt(self):
        rows = self.connection.execute(
            "SELECT a.visibility, a.encrypted, a.purged_at"
            "  FROM artifact_refs x JOIN artifacts a ON a.sha256 = x.sha256"
            " WHERE x.program_id = $1::uuid AND x.ref_label = $2"
            "   AND x.ref_kind = 'receipt_response'",
            (self.identifiers["grounded"], self.facts["receipt"]["label"]),
        ).rows

        self.assertEqual(1, len(rows))
        self.assertEqual("agent_visible", str(rows[0][0]))
        self.assertFalse(rows[0][1])
        self.assertIsNone(rows[0][2])

    def test_the_events_of_the_attempt_name_the_run_that_caused_them(self):
        # `set_cause` is what puts them there. Without it every Event of this
        # slice would name a Program and no run, and criterion 2 would be true
        # of the rows and false of the log that accounts for them.
        rows = self.connection.execute(
            "SELECT DISTINCT e.agent_run_id::text, e.task_id::text FROM events e"
            " WHERE e.program_id = $1::uuid AND e.type = 'observation.recorded'",
            (self.identifiers["grounded"],),
        ).rows

        self.assertEqual(
            [(self.facts["agent_run"]["id"], self.facts["task"]["id"])],
            [(str(row[0]), str(row[1])) for row in rows],
        )

    # -- criterion 3: exactly one immutable Observation, with its Event -------

    def test_exactly_one_observation_became_canonical(self):
        rows = self.connection.execute(
            "SELECT o.label, o.kind, o.provenance_kind, o.receipt_id::text,"
            "       o.agent_run_id::text, o.subject_entity_id::text,"
            "       o.metadata ->> 'proposal', o.metadata ->> 'element'"
            "  FROM observations o WHERE o.program_id = $1::uuid",
            (self.identifiers["grounded"],),
        ).rows

        self.assertEqual(1, len(rows))
        label, kind, provenance, receipt, run, subject, proposed, element = rows[0]
        self.assertEqual(self.facts["promotion"]["observations"], [str(label)])
        self.assertEqual(DISCOVERED, str(kind))
        self.assertEqual("receipt", str(provenance))
        self.assertIsNotNone(receipt)
        self.assertEqual(self.facts["agent_run"]["id"], str(run))
        self.assertEqual(self.task, str(subject))
        self.assertEqual(self.facts["proposal"]["label"], str(proposed))
        self.assertEqual("observations[0]", str(element))
        self.assertEqual("promoted", self.facts["promotion"]["status"])
        self.assertEqual(0, self.facts["promotion"]["refused"])

    def test_the_promotion_fingerprinted_the_surface_it_changed(self):
        # 022's "after recon", from this end: the promotion's own transaction
        # is where the fingerprint is taken, so what a later reader compares
        # against is the Surface as this attempt left it.
        rows = self.connection.execute(
            "SELECT count(*) FROM events WHERE program_id = $1::uuid"
            "   AND type = 'surface.fingerprinted'",
            (self.identifiers["grounded"],),
        ).rows

        self.assertEqual(
            self.facts["fingerprint"]["applications"], int(rows[0][0])
        )
        self.assertEqual(
            self.facts["fingerprint"]["applications"],
            int(
                self.connection.execute(
                    "SELECT count(*) FROM surface_fingerprints WHERE program_id = $1::uuid",
                    (self.identifiers["grounded"],),
                ).rows[0][0]
            ),
        )

    def test_the_observation_it_promoted_carries_its_own_event(self):
        rows = self.connection.execute(
            "SELECT e.subject_id::text, e.actor_kind FROM events e"
            "  JOIN observations o ON o.id = e.subject_id"
            " WHERE e.program_id = $1::uuid AND e.subject_table = 'observations'",
            (self.identifiers["grounded"],),
        ).rows

        self.assertEqual(1, len(rows))
        self.assertEqual("runtime", str(rows[0][1]))

    def test_a_canonical_observation_cannot_be_changed_afterwards(self):
        with self.assertRaises(pg.DatabaseError) as raised:
            self.owner(
                "UPDATE observations SET summary = 'edited' WHERE program_id = $1::uuid",
                (self.identifiers["grounded"],),
            )

        self.assertIn("observations rows are immutable", str(raised.exception))

    # -- criterion 4: prose closes nothing ------------------------------------

    def test_a_completion_claim_the_runtime_cannot_ground_closes_nothing(self):
        facts = self.prose

        self.assertEqual("complete", facts["proposal"]["completion"])
        self.assertEqual(
            [{"element": "observations[0]", "reason": "no_such_receipt"}],
            facts["proposal"]["drops"],
        )
        self.assertEqual("rejected", facts["promotion"]["status"])
        self.assertEqual([], facts["promotion"]["observations"])
        self.assertFalse(facts["closure"]["accepted"])
        self.assertEqual("pending", facts["closure"]["task_status"])
        self.assertEqual(
            0,
            self.connection.execute(
                "SELECT count(*)::int FROM observations WHERE program_id = $1::uuid",
                (self.identifiers["prose"],),
            ).scalar(),
        )

    def test_a_task_cannot_be_closed_as_done_without_a_promoted_proposal(self):
        # The structural half of the same claim, asked of the row directly: no
        # writer, however privileged, closes a Task the runtime did not accept.
        with self.assertRaises(pg.DatabaseError) as raised:
            self.owner(
                "UPDATE tasks SET status = 'done' WHERE program_id = $1::uuid",
                (self.identifiers["prose"],),
            )

        self.assertIn("no proposal of it has been promoted", str(raised.exception))

    # -- criterion 5: nothing left open, and closing again changes nothing ----

    def test_the_finished_attempt_left_nothing_open(self):
        row = self.connection.execute(
            SETTLED, (self.facts["agent_run"]["id"],)
        ).rows[0]
        (
            task_status,
            lease_expires_at,
            task_finished_at,
            run_finished_at,
            stop_reason,
            tool_run_status,
            tool_run_finished_at,
            digest,
            expires_at,
            held,
            promoted,
        ) = row

        self.assertEqual("done", str(task_status))
        self.assertIsNone(lease_expires_at)
        self.assertIsNotNone(task_finished_at)
        self.assertIsNotNone(run_finished_at)
        self.assertEqual("completed", str(stop_reason))
        self.assertEqual("success", str(tool_run_status))
        self.assertIsNotNone(tool_run_finished_at)
        self.assertIsNone(digest)
        self.assertIsNone(expires_at)
        self.assertEqual(0, int(held))
        self.assertEqual(1, int(promoted))

    def test_the_installation_wide_structures_the_closing_depends_on_hold(self):
        reported = [
            str(row[0])
            for row in self.connection.execute(
                "SELECT problem FROM check_execution_closure()"
            ).rows
        ]

        self.assertEqual([], [item for item in reported if item in STRUCTURAL])

    def test_closing_the_same_attempt_again_finds_nothing_to_close(self):
        self.runtime.execute(proxy.BIND, (self.identifiers["grounded"],))
        with self.runtime.transaction():
            self.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            again = proxy.as_object(
                self.runtime.execute(
                    "SELECT finish_task_attempt($1::uuid, 'completed')",
                    (self.facts["agent_run"]["id"],),
                ).scalar()
            )

        self.assertEqual(
            {"runs_closed": 0, "tool_runs_closed": 0, "leases_released": 0},
            {key: int(again[key]) for key in ("runs_closed", "tool_runs_closed", "leases_released")},
        )
        self.assertEqual("done", again["task_status"])
        self.assertTrue(again["accepted"])

    def test_a_second_slice_on_the_same_program_claims_nothing(self):
        ledger = Ledger()
        facts = self.attempt("grounded", Child(self.subject), ledger)

        self.assertEqual([], facts["slate"])
        self.assertIsNone(facts["task"])
        self.assertEqual([], list(ledger.violations))
        self.assertIn(
            "no Task is ready", " ".join(item.detail for item in ledger.assertions)
        )

    # -- criterion 6: two identical Programs decide the same way --------------

    def test_two_identically_seeded_programs_reach_the_same_decisions(self):
        first, second = self.twins["twin-a"], self.twins["twin-b"]

        self.assertEqual(decided(first), decided(second))
        self.assertEqual("done", first["closure"]["task_status"])

    def test_the_two_attempts_share_no_row_identifier(self):
        # The other half of criterion 6: the same decisions, and every row
        # identifier its own. Asked of the rows rather than of the report,
        # because two attempts that agreed by sharing a row would agree for the
        # one reason that is not allowed.
        rows = self.connection.execute(
            "SELECT ar.program_id::text, ar.id::text, ar.task_id::text,"
            "       tr.id::text, o.id::text"
            "  FROM agent_runs ar"
            "  JOIN tool_runs tr ON tr.agent_run_id = ar.id"
            "  JOIN observations o ON o.agent_run_id = ar.id"
            " WHERE ar.program_id = ANY($1::uuid[])",
            ("{" + ",".join(self.identifiers[name] for name in ("twin-a", "twin-b")) + "}",),
        ).rows

        self.assertEqual(2, len(rows))
        for column in range(len(rows[0])):
            self.assertNotEqual(rows[0][column], rows[1][column])


#: The Programs the promotion case opens. Two of them, seeded and promoted
#: alike, because "one Program-scoped Entity" is a claim about two Programs
#: finding the same thing and holding two rows for it.
SURFACE_SLUG = "selftest-surface"

#: The one Identity an operator declares, so that a configured origin exists to
#: be told apart from a promoted one. `program.run` is the only writer that
#: makes an Entity without a promotion behind it.
DECLARED = "\n[[identity]]\nname = \"member\"\nslot_ref = \"slot://identity/member\"\n"


class SurfacePromotionTest(DatabaseCase):
    """PH2-21: one recon run's result, promoted into typed Surface.

    Only a server can answer any of this. The canonical form of a URL, the
    scope class of a subject that does not exist yet, a relationship's direction,
    the key two proposals converge on and the compact read an agent gets back
    are five things `promote_proposal` decides in SQL, in one transaction, and
    the Python half of the ticket is a description of arguments rather than a
    second opinion about any of them.

    Everything runs on `rk2_runtime`, the role an operator points at the
    database, and the compact read is taken through `rk2_state` bound to one
    Program -- because a Surface read that only works for the role that wrote
    the rows is not the read the criterion is about.

    Four results are promoted in setup because they commit and because each
    later one is about what the first one left behind: a full recon result, the
    same subjects found again through different evidence, the same result in a
    second Program, and a result in which every element is wrong in a different
    way.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.configurations = {}
        cls.identifiers = {}
        for name in ("recon", "other"):
            slug = f"{SURFACE_SLUG}-{name}"
            path = write(SCOPED.replace('name = "matrix-web"', f'name = "{slug}"') + DECLARED)
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.configurations[name] = path
            cls.identifiers[name] = opened.facts["program_id"]
        cls.seeded = {name: cls._populate(name) for name in ("recon", "other")}

        # The result a recon run actually returns: nine typed subjects across
        # the eight types, three relationships between them and one Observation
        # about a subject that did not exist when the child wrote it.
        cls.found, cls.promoted = cls.promote("recon", cls.recon("recon"))
        # The same two subjects, found again through a Receipt rather than a
        # Tool run. Convergence is measured against this: one Entity, two
        # provenances, and the relationship already there rather than a second.
        cls.again, cls.converged = cls.promote(
            "recon",
            {
                "new_entities": [
                    {
                        "ref": "site",
                        "type": "domain",
                        "fqdn": "www.example.com",
                        "receipt_label": cls.seeded["recon"]["receipt"],
                    },
                    {
                        "ref": "machine",
                        "type": "host",
                        "hostname": "app.example.com",
                        "receipt_label": cls.seeded["recon"]["receipt"],
                    },
                ],
                "relationships": [
                    {
                        "type": "resolves_to",
                        "src_ref": "site",
                        "dst_ref": "machine",
                        "receipt_label": cls.seeded["recon"]["receipt"],
                    }
                ],
            },
        )
        # And the same recon result in the other Program, which has found the
        # same host on the same internet and holds its own row for it.
        cls.elsewhere, cls.parallel = cls.promote("other", cls.recon("other"))
        cls.refusals, cls.refused = cls.promote("recon", cls.wrong())

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{SURFACE_SLUG}-%",)
            )
        super().tearDownClass()

    # -- the fixture ---------------------------------------------------------

    @classmethod
    def _populate(cls, name: str) -> dict:
        """One claimed Task, one run, and the two things evidence can be.

        A Receipt as well as a Tool run because criterion 5 is about origins
        staying distinguishable, and the two provenances of one converged Entity
        are the sharpest form of that: same subject, same Program, two pieces of
        evidence that are not each other.
        """
        program_id = cls.identifiers[name]
        seeded: dict[str, str] = {"program_id": program_id}
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            seeded["task"] = str(
                cls.connection.execute(
                    "INSERT INTO tasks (program_id, kind, status, claimed_at,"
                    " lease_expires_at) VALUES ($1::uuid, 'recon', 'claimed', now(),"
                    " now() + interval '30 minutes') RETURNING id::text",
                    (program_id,),
                ).scalar()
            )
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
                    " RETURNING label",
                    (program_id, seeded["run"], seeded["task"]),
                ).scalar()
            )
            # A refusal, which is the one Receipt shape that needs no live
            # capability behind it, and one with no Tool run of its own so that
            # `receipt_other_run` is not what this fixture is testing.
            seeded["receipt"] = str(
                cls.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host, method, scheme,"
                    " path) VALUES ($1::uuid, 'agent', 'blocked', 'refused before contact',"
                    " now(), 'target', 1, 'app.example.com', 'GET', 'http', '/')"
                    " RETURNING label",
                    (program_id,),
                ).scalar()
            )
        return seeded

    @classmethod
    def recon(cls, name: str) -> dict:
        """What a recon run returns, in the spellings a model writes them in.

        Deliberately not canonical: a trailing dot and mixed case on the name,
        a lowercase method, a trailing slash on the route, an uppercase protocol
        and location. Every one of them is a spelling the schema does not store,
        so a promotion that wrote them through would be visible as a second
        Entity the next time the same subject was found.
        """
        tool_run = cls.seeded[name]["tool_run"]
        return {
            "new_entities": [
                {"ref": "site", "type": "domain", "fqdn": "WWW.Example.COM.",
                 "tool_run_label": tool_run},
                {"ref": "tree", "type": "domain", "fqdn": "example.com",
                 "wildcard": True, "tool_run_label": tool_run},
                {"ref": "machine", "type": "host", "hostname": "app.example.com",
                 "address": PINNED, "tool_run_label": tool_run},
                {"ref": "port", "type": "service", "parent_ref": "machine",
                 "port": 80, "protocol": "TCP", "banner": "nginx",
                 "tool_run_label": tool_run},
                {"ref": "site_app", "type": "application",
                 "base_url": "http://app.example.com/", "kind": "web",
                 "tool_run_label": tool_run},
                {"ref": "route", "type": "endpoint", "parent_ref": "site_app",
                 "method": "get", "path_template": "/notes/", "auth_required": False,
                 "tool_run_label": tool_run},
                {"ref": "field", "type": "parameter", "parent_ref": "route",
                 "name": "q", "location": "QUERY", "reflected": True,
                 "tool_run_label": tool_run},
                {"ref": "stack", "type": "technology", "name": "nginx",
                 "version": "1.24.0", "tool_run_label": tool_run},
                {"ref": "guest", "type": "identity", "slot_name": "anonymous-visitor",
                 "tool_run_label": tool_run},
            ],
            "relationships": [
                {"type": "resolves_to", "src_ref": "site", "dst_ref": "machine",
                 "tool_run_label": tool_run},
                {"type": "serves", "src_ref": "machine", "dst_ref": "site_app",
                 "tool_run_label": tool_run},
                {"type": "runs", "src_ref": "site_app", "dst_ref": "stack",
                 "tool_run_label": tool_run},
            ],
            "observations": [
                {"kind": DISCOVERED, "subject_ref": "route",
                 "summary": "the route answered without a session",
                 "tool_run_label": tool_run},
            ],
            "completion_claim": {"status": "partial"},
        }

    @classmethod
    def wrong(cls) -> dict:
        """One element per way of being wrong, and no two wrong the same way.

        Read as a table: each element's reason is the one thing that element
        gets wrong, and the promotion has to name that reason rather than the
        first refusal the database happened to raise.
        """
        tool_run = cls.seeded["recon"]["tool_run"]
        held = cls.held("recon")
        return {
            "new_entities": [
                {"type": "host", "hostname": "admin.example.com",
                 "tool_run_label": tool_run},
                {"type": "application", "base_url": "http://app.example.com/a/../b",
                 "tool_run_label": tool_run},
                {"type": "service", "parent_label": held["technology"], "port": 443,
                 "tool_run_label": tool_run},
                {"type": "unicorn", "tool_run_label": tool_run},
                {"type": "identity", "slot_name": "root", "class": "privileged",
                 "secret_ref": "slot://identity/root", "tool_run_label": tool_run},
                {"type": "domain", "fqdn": "one.example.com"},
                {"type": "host", "hostname": "two.example.com",
                 "address": "app.example.com", "tool_run_label": tool_run},
            ],
            "relationships": [
                {"type": "serves", "src_label": held["application"],
                 "dst_label": held["host"], "tool_run_label": tool_run},
                {"type": "same_as", "src_label": held["service"],
                 "dst_label": held["host"], "tool_run_label": tool_run},
                {"type": "pwns", "src_label": held["host"],
                 "dst_label": held["application"], "tool_run_label": tool_run},
                {"type": "resolves_to", "src_label": "DOM999",
                 "dst_label": held["host"], "tool_run_label": tool_run},
            ],
        }

    @classmethod
    def promote(cls, name: str, payload: dict) -> tuple[proposal.Staged, dict]:
        """Stage one result and promote it, the way the supervisor does both.

        Two transactions rather than one, because `proposal.stage` opens its own
        and the Program a promotion runs against is transaction-local: bound in
        the transaction the staging insert commits, it would be unbound by the
        time `promote_proposal` asked which Program this is.
        """
        seeded = cls.seeded[name]
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            staged = proposal.stage(
                cls.connection,
                proposal.Result(payload=payload),
                program_id=cls.identifiers[name],
                agent_run_id=seeded["run"],
                task_id=seeded["task"],
            )
        return staged, cls.promoted_now(name, staged.proposal_id)

    @classmethod
    def promoted_now(cls, name: str, proposal_id: str) -> dict:
        with cls.connection.transaction():
            cls.connection.execute(
                "SELECT set_config('rk2.program_id', $1, true)", (cls.identifiers[name],)
            )
            return proxy.as_object(
                cls.connection.execute(
                    "SELECT promote_proposal($1::uuid)", (proposal_id,)
                ).scalar()
            )

    @classmethod
    def held(cls, name: str) -> dict:
        """This Program's Entities, by type, for the types it holds one of.

        A type this Program holds twice is left out rather than resolved by
        order: two Domains are two subjects, and a test that named one of them
        by which label sorted higher would be asserting about the counter.
        """
        return {
            str(row[0]): str(row[1])
            for row in cls.connection.execute(
                "SELECT type, min(label) FROM entities WHERE program_id = $1::uuid"
                " GROUP BY type HAVING count(*) = 1",
                (cls.identifiers[name],),
            ).rows
        }

    @classmethod
    def labels(cls, name: str) -> dict:
        """This Program's Entities by the key they converge on."""
        return {
            str(row[0]): str(row[1])
            for row in cls.connection.execute(
                "SELECT dedup_key, label FROM entities WHERE program_id = $1::uuid",
                (cls.identifiers[name],),
            ).rows
        }

    def rows(self, sql: str, name: str = "recon") -> list:
        return self.connection.execute(sql, (self.identifiers[name],)).rows

    @contextlib.contextmanager
    def agent_session(self, name: str):
        """The connection a child reads through, bound to one Program."""
        with pg.connect(self.harness.state) as session:
            with session.transaction():
                assert state.bind_agent_session(
                    state.Ledger(), session, self.identifiers[name]
                )
                yield session

    def record(self, name: str, label: str) -> dict:
        with self.agent_session(name) as session:
            return proxy.as_object(
                session.execute(
                    "SELECT record FROM v_records WHERE kind = 'entity' AND label = $1",
                    (label,),
                ).scalar()
            )

    # -- criterion 1: eight typed subjects, from one result -------------------

    def test_one_recon_result_became_nine_typed_entities_and_three_relationships(self):
        promoted = self.promoted

        self.assertEqual("promoted", promoted["status"])
        self.assertFalse(promoted["repeated"])
        self.assertEqual(0, promoted["refused"])
        self.assertEqual([], list(self.found.drops))
        self.assertEqual(9, len(promoted["entities"]))
        self.assertEqual(3, len(promoted["relationships"]))
        self.assertEqual(1, len(promoted["observations"]))
        self.assertEqual(
            {"domain": 2, "host": 1, "service": 1, "application": 1, "endpoint": 1,
             "parameter": 1, "technology": 1, "identity": 2},
            {
                str(row[0]): int(row[1])
                for row in self.rows(
                    "SELECT type, count(*) FROM entities WHERE program_id = $1::uuid"
                    " GROUP BY type"
                )
            },
        )

    def test_every_promoted_subject_carries_the_typed_fields_it_was_given(self):
        # The detail row, not the Entity: an `endpoints` row is what makes the
        # subject an Endpoint rather than a label with a type column.
        [row] = self.rows(
            "SELECT e.label, ep.method, ep.path_template, ep.auth_required,"
            "       app.base_url, app.kind, p.name, p.location, p.reflected"
            "  FROM endpoints ep"
            "  JOIN entities e ON e.id = ep.entity_id"
            "  JOIN applications app ON app.entity_id = ep.application_id"
            "  JOIN parameters p ON p.endpoint_id = ep.entity_id"
            " WHERE e.program_id = $1::uuid"
        )

        self.assertRegex(str(row[0]), r"^EP[0-9]+$")
        self.assertEqual(("GET", "/notes", False), (str(row[1]), str(row[2]), bool(row[3])))
        self.assertEqual(("http://app.example.com", "web"), (str(row[4]), str(row[5])))
        self.assertEqual(("q", "query", True), (str(row[6]), str(row[7]), bool(row[8])))

    def test_the_service_and_the_host_it_is_on_are_two_rows_and_one_link(self):
        [row] = self.rows(
            "SELECT s.port, s.protocol, s.banner, h.hostname, host(h.address), e.label"
            "  FROM services s JOIN hosts h ON h.entity_id = s.host_id"
            "  JOIN entities e ON e.id = s.host_id"
            " WHERE e.program_id = $1::uuid"
        )

        self.assertEqual((80, "tcp", "nginx"), (int(row[0]), str(row[1]), str(row[2])))
        self.assertEqual(("app.example.com", PINNED), (str(row[3]), str(row[4])))
        self.assertRegex(str(row[5]), r"^HST[0-9]+$")

    def test_an_observation_may_be_about_a_subject_proposed_beside_it(self):
        # The gap ticket 20 left: an Observation whose subject is proposed in
        # the same result had no label to name, and naming it by `ref` is the
        # only way a child can be about something it just found.
        [row] = self.rows(
            "SELECT o.label, o.kind, e.type, o.metadata ->> 'element'"
            "  FROM observations o JOIN entities e ON e.id = o.subject_entity_id"
            " WHERE o.program_id = $1::uuid"
        )

        self.assertEqual(self.promoted["observations"], [str(row[0])])
        self.assertEqual((DISCOVERED, "endpoint"), (str(row[1]), str(row[2])))
        self.assertEqual("observations[0]", str(row[3]))

    # -- criterion 2: canonical form, and scope, before the row exists --------

    def test_every_subject_was_canonicalized_before_it_was_written(self):
        stored = {
            str(row[0]): str(row[1])
            for row in self.rows(
                "SELECT e.type, e.dedup_key FROM entities e"
                " WHERE e.program_id = $1::uuid AND e.type IN ('domain','endpoint','application')"
                " AND e.dedup_key NOT LIKE '%*%'"
            )
        }

        self.assertEqual("domain:www.example.com", stored["domain"])
        self.assertEqual("application:http://app.example.com", stored["application"])
        self.assertTrue(stored["endpoint"].endswith("|GET|/notes"), stored["endpoint"])

    def test_a_subject_the_program_has_not_authorised_is_refused_before_it_exists(self):
        # `admin.example.com` is excluded by the configuration, and the Spec
        # forbids discovery outside it. So the refusal has to happen before the
        # row: an Entity written and then projected denied is a record of the
        # discovery this rule exists to prevent.
        self.assertIn(("new_entities[0]", "out_of_scope"), self.dropped())
        self.assertEqual(
            0,
            int(
                self.connection.execute(
                    "SELECT count(*) FROM entities WHERE program_id = $1::uuid"
                    "   AND scope_selector = 'admin.example.com'",
                    (self.identifiers["recon"],),
                ).scalar()
            ),
        )

    def test_a_url_the_schema_cannot_spell_is_refused_with_the_reason(self):
        drops = dict(self.dropped())
        cited = {
            str(path): str(reason)
            for path, reason in self.connection.execute(
                "SELECT element_path, cited FROM proposal_drops"
                " WHERE proposal_id = $1::uuid AND element_path = 'new_entities[1]'",
                (self.refusals.proposal_id,),
            ).rows
        }

        self.assertEqual("malformed_field", drops["new_entities[1]"])
        self.assertIn("normal form", cited["new_entities[1]"])

    def test_a_field_the_schema_cannot_hold_refuses_the_element_it_is_on(self):
        # A Host offered with a hostname for an address. Promoting it on the
        # hostname alone would answer "what address is this" with nothing, while
        # the child that sent one has been told the element landed.
        [row] = self.connection.execute(
            "SELECT reason, cited FROM proposal_drops"
            " WHERE proposal_id = $1::uuid AND element_path = 'new_entities[6]'",
            (self.refusals.proposal_id,),
        ).rows

        self.assertEqual("malformed_field", str(row[0]))
        self.assertIn("address is not an IP address", str(row[1]))
        self.assertEqual(
            [],
            list(
                self.rows(
                    "SELECT h.hostname FROM hosts h JOIN entities e ON e.id = h.entity_id"
                    " WHERE e.program_id = $1::uuid AND h.hostname = 'two.example.com'"
                )
            ),
        )

    def test_each_wrong_element_is_refused_for_the_one_thing_it_gets_wrong(self):
        self.assertEqual(
            [
                ("new_entities[0]", "out_of_scope"),
                ("new_entities[1]", "malformed_field"),
                ("new_entities[2]", "no_parent"),
                ("new_entities[3]", "unknown_kind"),
                ("new_entities[4]", "malformed_field"),
                ("new_entities[5]", "no_provenance"),
                ("new_entities[6]", "malformed_field"),
                ("relationships[0]", "invalid_direction"),
                ("relationships[1]", "is_containment"),
                ("relationships[2]", "unknown_kind"),
                ("relationships[3]", "no_subject"),
            ],
            self.dropped(),
        )
        self.assertEqual("rejected", self.refused["status"])
        self.assertEqual(11, self.refused["refused"])
        self.assertEqual([], self.refused["entities"])
        self.assertEqual([], self.refused["relationships"])

    def dropped(self) -> list[tuple[str, str]]:
        return [
            (str(path), str(reason))
            for path, reason in self.connection.execute(
                "SELECT element_path, reason FROM proposal_drops"
                " WHERE proposal_id = $1::uuid ORDER BY ordinal",
                (self.refusals.proposal_id,),
            ).rows
        ]

    # -- criterion 3: containment is not a relationship, and direction is a rule

    def test_the_three_relationships_promoted_are_the_three_allowed(self):
        self.assertEqual(
            sorted(["resolves_to", "serves", "runs"]),
            sorted(
                str(row[0])
                for row in self.rows(
                    "SELECT type FROM relationships WHERE program_id = $1::uuid"
                )
            ),
        )

    def test_a_containment_pair_is_refused_however_it_is_written(self):
        cited = str(
            self.connection.execute(
                "SELECT cited FROM proposal_drops WHERE proposal_id = $1::uuid"
                "   AND element_path = 'relationships[1]'",
                (self.refusals.proposal_id,),
            ).scalar()
        )

        self.assertIn("containment", cited)

    def test_the_grammar_holds_against_a_writer_that_is_not_the_promotion(self):
        # On the table rather than in the promotion, because promotion is one
        # writer: an operator's session and a restore are the others, and a
        # relationship with a direction nothing accepts is as wrong from either.
        held = self.held("recon")
        # As the owner, on its own connection: this case's connection is the
        # runtime's, and the writer being answered here is the one that owns the
        # table and could otherwise write what promotion refuses to.
        with pg.connect(self.harness.superuser) as session, session.transaction():
            session.execute("SET LOCAL ROLE rk2_owner")
            session.execute("SELECT set_actor('runtime', 'selftest')")
            with self.assertRaises(pg.DatabaseError) as refused:
                session.execute(
                    "INSERT INTO relationships (program_id, src_entity_id,"
                    " dst_entity_id, type)"
                    " SELECT $1::uuid, a.id, b.id, 'serves' FROM entities a, entities b"
                    "  WHERE a.program_id = $1::uuid AND b.program_id = $1::uuid"
                    "    AND a.label = $2 AND b.label = $3",
                    (self.identifiers["recon"], held["application"], held["host"]),
                )

        self.assertIn("is not defined from application to host", str(refused.exception))
        self.assertIn("reversed", str(refused.exception))

    def test_the_standing_check_reports_nothing_about_this_installation(self):
        # Through the registry rather than by calling the function, because a
        # check nothing runs is a check that cannot fail: `run_standing_checks`
        # is what the gate reads, and the row is what puts this one in it.
        [row] = self.connection.execute(
            "SELECT problems, detail FROM run_standing_checks()"
            " WHERE name = 'surface_promotion'"
        ).rows

        self.assertEqual((0, ""), (int(row[0]), str(row[1])))

    # -- criterion 4: one subject, one Entity, every provenance ---------------

    def test_the_same_subject_found_twice_is_one_entity_with_two_provenances(self):
        self.assertEqual("promoted", self.converged["status"])
        self.assertEqual(2, len(self.converged["entities"]))
        self.assertEqual(1, len(self.converged["relationships"]))
        self.assertEqual(
            sorted(self.converged["entities"]),
            sorted(
                str(row[0])
                for row in self.rows(
                    "SELECT e.label FROM entities e WHERE e.program_id = $1::uuid"
                    "   AND e.dedup_key IN ('domain:www.example.com','host:app.example.com')"
                )
            ),
        )
        self.assertEqual(
            [2, 2],
            [
                int(row[0])
                for row in self.rows(
                    "SELECT count(*) FROM entity_provenance p"
                    "  JOIN entities e ON e.id = p.entity_id"
                    " WHERE p.program_id = $1::uuid"
                    "   AND e.dedup_key IN ('domain:www.example.com','host:app.example.com')"
                    " GROUP BY e.id ORDER BY count(*)"
                )
            ],
        )

    def test_the_second_sighting_added_a_provenance_rather_than_replacing_one(self):
        rows = self.rows(
            "SELECT p.element_path, p.receipt_id IS NOT NULL, p.tool_run_id IS NOT NULL"
            "  FROM entity_provenance p JOIN entities e ON e.id = p.entity_id"
            " WHERE p.program_id = $1::uuid AND e.dedup_key = 'domain:www.example.com'"
            " ORDER BY p.observed_at"
        )

        self.assertEqual(
            [("new_entities[0]", False, True), ("new_entities[0]", True, False)],
            [(str(row[0]), bool(row[1]), bool(row[2])) for row in rows],
        )

    def test_the_relationship_found_twice_is_one_row_with_two_provenances(self):
        [row] = self.rows(
            "SELECT count(DISTINCT r.id), count(*) FROM relationship_provenance p"
            "  JOIN relationships r ON r.id = p.relationship_id"
            " WHERE p.program_id = $1::uuid AND r.type = 'resolves_to'"
        )

        self.assertEqual((1, 2), (int(row[0]), int(row[1])))

    def test_two_programs_that_found_the_same_host_hold_two_entities(self):
        rows = self.connection.execute(
            "SELECT program_id::text, id::text FROM entities"
            " WHERE dedup_key = 'host:app.example.com' AND program_id = ANY($1::uuid[])",
            ("{" + ",".join(self.identifiers[name] for name in ("recon", "other")) + "}",),
        ).rows

        self.assertEqual(2, len(rows))
        self.assertEqual(2, len({str(row[0]) for row in rows}))
        self.assertEqual(2, len({str(row[1]) for row in rows}))
        self.assertEqual(
            9, len(self.parallel["entities"]), self.parallel
        )

    def test_no_provenance_row_reaches_across_the_program_boundary(self):
        # Structural rather than incidental: every key on the two provenance
        # tables carries `program_id`, so a row citing another Program's
        # evidence is refused by the key. This is the query that would find one.
        self.assertEqual(
            [],
            list(
                self.connection.execute(
                    "SELECT p.id::text FROM entity_provenance p"
                    "  JOIN entities e ON e.id = p.entity_id"
                    " WHERE e.program_id <> p.program_id"
                ).rows
            ),
        )

    # -- criterion 5: where a row came from stays readable --------------------

    def test_a_configured_identity_and_a_promoted_one_are_told_apart(self):
        origins = {
            str(row[0]): str(row[1])
            for row in self.rows(
                "SELECT i.slot_name, e.origin FROM identities i"
                "  JOIN entities e ON e.id = i.entity_id"
                " WHERE e.program_id = $1::uuid"
            )
        }

        self.assertEqual(
            {"member": "configured", "anonymous-visitor": "proposed"}, origins
        )

    def test_an_agent_may_not_propose_an_identity_that_holds_a_secret(self):
        cited = str(
            self.connection.execute(
                "SELECT cited FROM proposal_drops WHERE proposal_id = $1::uuid"
                "   AND element_path = 'new_entities[4]'",
                (self.refusals.proposal_id,),
            ).scalar()
        )

        self.assertIn("only an anonymous identity", cited)
        self.assertEqual(
            [],
            list(
                self.rows(
                    "SELECT i.slot_name FROM identities i"
                    "  JOIN entities e ON e.id = i.entity_id"
                    " WHERE e.program_id = $1::uuid AND i.slot_name = 'root'"
                )
            ),
        )

    def test_the_origin_vocabulary_covers_the_three_the_criterion_names(self):
        self.assertEqual(
            ["configured", "imported", "observed", "proposed"],
            [
                str(row[0])
                for row in self.connection.execute(
                    "SELECT unnest(rk2_origins()) ORDER BY 1"
                ).rows
            ],
        )

    # -- criterion 6: the compact read, without the transcript ----------------

    def test_the_surface_record_names_the_parent_and_the_relationships(self):
        held, labels = self.held("recon"), self.labels("recon")
        endpoint = self.record("recon", held["endpoint"])
        host = self.record("recon", held["host"])

        self.assertEqual(held["application"], endpoint["parent_label"])
        self.assertEqual("proposed", endpoint["origin"])
        self.assertEqual([], endpoint["relationships"])
        self.assertEqual(
            sorted(
                [
                    {"type": "resolves_to", "direction": "in",
                     "label": labels["domain:www.example.com"]},
                    {"type": "serves", "direction": "out", "label": held["application"]},
                ],
                key=repr,
            ),
            sorted(host["relationships"], key=repr),
        )

    def test_the_surface_record_says_who_says_so_without_the_proposal(self):
        domain = self.record("recon", self.labels("recon")["domain:www.example.com"])

        self.assertEqual("proposed", domain["origin"])
        self.assertEqual(["proposed"], domain["origins"])
        self.assertEqual("target", domain["scope_class"])
        self.assertTrue(domain["in_scope"])
        self.assertNotIn(self.found.label, json.dumps(domain))
        self.assertNotIn(self.again.label, json.dumps(domain))

    def test_the_record_says_how_many_relationships_it_cut_the_list_down_from(self):
        # The cap without the count would read as the whole list. `packet` says
        # the same thing about every section it truncates; a record that carries
        # twenty of two hundred and does not say so is the one shape of bounded
        # read an agent cannot tell from a complete one.
        held = self.held("recon")
        host = self.record("recon", held["host"])
        endpoint = self.record("recon", held["endpoint"])

        self.assertEqual(len(host["relationships"]), host["relationship_count"])
        self.assertEqual(2, host["relationship_count"])
        self.assertEqual(0, endpoint["relationship_count"])

    def test_the_record_revision_covers_the_relationships_the_record_carries(self):
        # A Relationship is its own row with its own Events, and joining one
        # changes this record. A revision that only counted `entities` would
        # leave a reader ranking and comparing by a number the change did not
        # move.
        held = self.held("recon")
        [row] = self.connection.execute(
            "SELECT rk2_revision('entities', e.id) FROM entities e"
            " WHERE e.program_id = $1::uuid AND e.label = $2",
            (self.identifiers["recon"], held["host"]),
        ).rows
        with self.agent_session("recon") as session:
            revision = int(
                session.execute(
                    "SELECT revision FROM v_records WHERE kind = 'entity' AND label = $1",
                    (held["host"],),
                ).scalar()
            )

        self.assertGreater(revision, int(row[0]))

    def test_the_read_role_reads_the_origin_of_a_row_and_not_its_evidence(self):
        # 033's registry is the grant, and section 5 names four columns in it.
        # Which kinds of evidence stand behind a row is the agent's question;
        # which Receipt, from which run, is the supervisor's, and answering it
        # to a child would put another Program's label one join away.
        granted = {
            column: bool(
                self.connection.execute(
                    "SELECT has_column_privilege('rk2_state', 'entity_provenance',"
                    " $1, 'SELECT')",
                    (column,),
                ).scalar()
            )
            for column in ("entity_id", "origin", "receipt_id", "agent_run_id")
        }

        self.assertEqual(
            {"entity_id": True, "origin": True,
             "receipt_id": False, "agent_run_id": False},
            granted,
        )

    def test_promoting_the_same_result_again_changes_nothing_and_says_so(self):
        before = self.labels("recon")

        repeated = self.promoted_now("recon", self.found.proposal_id)

        self.assertTrue(repeated["repeated"])
        self.assertEqual("promoted", repeated["status"])
        self.assertEqual(
            sorted(self.promoted["entities"]), sorted(repeated["entities"])
        )
        self.assertEqual(
            sorted(self.promoted["relationships"]), sorted(repeated["relationships"])
        )
        self.assertEqual(before, self.labels("recon"))


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


#: The Program the fingerprint case opens. One Program holding both twins,
#: because two Programs would make "the same surface" a claim about isolation
#: rather than about the projection.
FINGERPRINT_SLUG = "selftest-fingerprint"

#: One small application's observable surface, as a shape rather than as rows.
#: Both twins are built from this and differ only in the three things the
#: projection deliberately does not carry: the Entity labels, the base URL and
#: the per-Program slot name of every Identity. If a fingerprint could see any
#: of them, no two deployments of one application could ever compare equal.
TWIN = {
    "kind": "web",
    "endpoints": [
        {
            "method": "GET",
            "path": "/notes",
            "auth": True,
            "content_type": None,
            "parameters": [
                {"name": "q", "location": "query", "value_class": "text",
                 "reflected": False},
                {"name": "page", "location": "query", "value_class": "number",
                 "reflected": False},
            ],
        },
        {
            "method": "POST",
            "path": "/notes",
            "auth": True,
            "content_type": "application/json",
            "parameters": [
                {"name": "body", "location": "body", "value_class": "text",
                 "reflected": False},
            ],
        },
    ],
    "technologies": [("nginx", "1.24.0"), ("openssl", "3.0.13")],
    "identities": [
        {"ref": "guest", "class": "anonymous", "owns": ["application"]},
        {"ref": "org", "class": "service", "owns": []},
        {"ref": "member", "class": "user", "owns": ["GET /notes"], "member_of": "org"},
    ],
}


class SurfaceFingerprintTest(DatabaseCase):
    """PH2-22: the Surface gets a fingerprint, and its changes get names.

    Everything the ticket asks for is a question about one projection and two
    of them compared, and both are SQL: which rows are in, what they are
    called, what the fingerprint is over, and which of twelve typed things happened
    between two of them.

    Two twins, built from one shape. The secure one is written in the order
    `TWIN` lists and the vulnerable one in the reverse of it, so "identical
    Surface produces the same fingerprint across runs and row insertion order" is
    the same assertion as "these two applications are the same application".
    Then the vulnerable twin gets what makes it vulnerable, and every kind of
    delta the vocabulary has is produced by that one recompute.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "runtime"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        path = write(SCOPED.replace('name = "matrix-web"', f'name = "{FINGERPRINT_SLUG}"'))
        opened = program.run(cls.harness.runtime, path)
        assert opened.ok, opened.violations
        cls.program_id = opened.facts["program_id"]

        cls.secure = cls.build("secure", "http://secure.example.com", TWIN)
        cls.vulnerable = cls.build(
            "vuln", "http://vulnerable.example.com", TWIN, reverse=True
        )

        # The baselines. Neither has a predecessor, so neither produces a
        # delta, and the two fingerprints are the whole of criterion 6's first half.
        cls.first_secure = cls.compute(cls.secure)
        cls.first_vulnerable = cls.compute(cls.vulnerable)
        # Nothing moved in between, which is the run that has to repeat.
        cls.again_secure = cls.compute(cls.secure)

        # One refuted Hypothesis about a route the mutation is about to change,
        # holding the fingerprint it was refuted under. Criterion 5's second half is
        # that recomputing does not touch it.
        cls.refuted = cls.refute(
            cls.route(cls.vulnerable, "GET /notes"), cls.first_vulnerable["fingerprint"]
        )

        cls.mutate()
        cls.changed = cls.compute(cls.vulnerable)

    @classmethod
    def tearDownClass(cls):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug = $1", (FINGERPRINT_SLUG,)
            )
        super().tearDownClass()

    # -- the fixture ---------------------------------------------------------

    @classmethod
    def entity(cls, kind: str, dedup: str, selector: str | None = None) -> str:
        """One Entity, through the corpus's own door.

        `add_entity` rather than an INSERT because 021 made an addressable
        Entity carry the selector its scope is decided from, and a fixture that
        wrote the row itself would be a fixture that had to keep remembering
        that. Origin `observed`: these are the rows an instrument would have
        left, and fingerprinting is downstream of who wrote them.
        """
        return str(
            cls.connection.execute(
                "SELECT add_entity($1::uuid, $2, '', $3, $4, NULL, $5, 'observed')::text",
                (cls.program_id, kind, None if selector is None else "host",
                 selector, dedup),
            ).scalar()
        )

    @classmethod
    def link(cls, kind: str, src: str, dst: str) -> None:
        cls.connection.execute(
            "INSERT INTO relationships (program_id, src_entity_id, dst_entity_id, type)"
            " VALUES ($1::uuid, $2::uuid, $3::uuid, $4)",
            (cls.program_id, src, dst, kind),
        )

    @classmethod
    def build(cls, prefix: str, base_url: str, spec: dict, reverse: bool = False) -> str:
        """One twin's rows, written in the order the caller asks for.

        The reversal is the point rather than decoration: it reverses the
        routes, the parameters under each route, the stack and the Identities,
        so every list the projection sorts was written into the database the
        other way round.
        """
        def ordered(items: list) -> list:
            return list(reversed(items)) if reverse else list(items)

        host = base_url.split("//", 1)[1]
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            application = cls.entity("application", base_url, host)
            cls.connection.execute(
                "INSERT INTO applications (entity_id, base_url, kind)"
                " VALUES ($1::uuid, $2, $3)",
                (application, base_url, spec["kind"]),
            )

            reached = {"application": application}
            for route in ordered(spec["endpoints"]):
                key = f"{route['method']} {route['path']}"
                endpoint = cls.entity("endpoint", f"{base_url}{key}", host)
                cls.connection.execute(
                    "INSERT INTO endpoints (entity_id, application_id, method,"
                    " path_template, auth_required, request_content_type)"
                    " VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)",
                    (endpoint, application, route["method"], route["path"],
                     route["auth"], route["content_type"]),
                )
                reached[key] = endpoint
                for field in ordered(route["parameters"]):
                    parameter = cls.entity(
                        "parameter",
                        f"{base_url}{key}#{field['location']}:{field['name']}",
                        host,
                    )
                    cls.connection.execute(
                        "INSERT INTO parameters (entity_id, endpoint_id, name, location,"
                        " value_class, reflected) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)",
                        (parameter, endpoint, field["name"], field["location"],
                         field["value_class"], field["reflected"]),
                    )

            for name, version in ordered(spec["technologies"]):
                technology = cls.entity("technology", f"{base_url}{name}")
                cls.connection.execute(
                    "INSERT INTO technologies (entity_id, name, version)"
                    " VALUES ($1::uuid, $2, $3)",
                    (technology, name, version),
                )
                cls.link("runs", application, technology)

            held = {}
            for who in ordered(spec["identities"]):
                held[who["ref"]] = cls.identity(prefix, who["ref"], who["class"])
            for who in ordered(spec["identities"]):
                for target in who["owns"]:
                    cls.link("owns", held[who["ref"]], reached[target])
                if who.get("member_of"):
                    cls.link("member_of", held[who["ref"]], held[who["member_of"]])
        return application

    @classmethod
    def identity(cls, prefix: str, ref: str, class_: str) -> str:
        """One Identity, under a slot name no other twin can hold.

        `identities_slot_idx` is unique per Program since 017, so two
        Applications of one Program cannot share a slot -- which is why the
        projection carries the class and not the slot.
        """
        slot = f"{prefix}-{ref}"
        who = cls.entity("identity", slot)
        cls.connection.execute(
            "INSERT INTO identities (entity_id, slot_name, class, secret_ref)"
            " VALUES ($1::uuid, $2, $3, $4)",
            (who, slot, class_,
             None if class_ == "anonymous" else f"slot://identity/{slot}"),
        )
        return who

    @classmethod
    def mutate(cls) -> None:
        """What makes the vulnerable twin vulnerable, in one recompute.

        Deliberately every kind at once: an export route nobody has to
        authenticate for, the write route retired, the read route's session
        requirement dropped, a search term that now comes back in the page, the
        server upgraded, TLS no longer attributed, a framework newly attributed,
        an administrator who holds the new route, and the anonymous holder gone.
        Twelve delta kinds exist and this produces all twelve, because a kind
        nothing can produce is a kind nothing has to be right about.
        """
        application = cls.vulnerable
        host = "vulnerable.example.com"
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            admin = cls.entity(
                "endpoint", "http://vulnerable.example.com/admin/export", host
            )
            cls.connection.execute(
                "INSERT INTO endpoints (entity_id, application_id, method,"
                " path_template, auth_required) VALUES ($1::uuid, $2::uuid,"
                " 'GET', '/admin/export', false)",
                (admin, application),
            )
            leak = cls.entity(
                "parameter",
                "http://vulnerable.example.com/admin/export#query:next",
                host,
            )
            cls.connection.execute(
                "INSERT INTO parameters (entity_id, endpoint_id, name, location,"
                " value_class, reflected) VALUES ($1::uuid, $2::uuid, 'next',"
                " 'query', 'url', true)",
                (leak, admin),
            )
            # The parameter first: 017 gave the containment its composite key
            # and no cascade, so a route cannot be retired out from under its
            # own inputs.
            cls.connection.execute(
                "DELETE FROM entities WHERE id = $1::uuid",
                (cls.route(application, "POST /notes#body:body"),),
            )
            cls.connection.execute(
                "DELETE FROM entities WHERE id = $1::uuid",
                (cls.route(application, "POST /notes"),),
            )
            cls.connection.execute(
                "UPDATE endpoints SET auth_required = false WHERE entity_id = $1::uuid",
                (cls.route(application, "GET /notes"),),
            )
            cls.connection.execute(
                "UPDATE parameters SET reflected = true WHERE entity_id = $1::uuid",
                (cls.route(application, "GET /notes#query:q"),),
            )
            cls.connection.execute(
                "UPDATE technologies SET version = '1.27.0'"
                " WHERE entity_id = $1::uuid",
                (cls.technology(application, "nginx"),),
            )
            cls.connection.execute(
                "DELETE FROM relationships WHERE src_entity_id = $1::uuid"
                "   AND dst_entity_id = $2::uuid AND type = 'runs'",
                (application, cls.technology(application, "openssl")),
            )
            express = cls.entity("technology", "http://vulnerable.example.comexpress")
            cls.connection.execute(
                "INSERT INTO technologies (entity_id, name, version)"
                " VALUES ($1::uuid, 'express', '4.19.2')",
                (express,),
            )
            cls.link("runs", application, express)

            operator = cls.identity("vuln", "operator", "privileged")
            cls.link("owns", operator, admin)
            cls.link("member_of", operator, cls.slot("vuln-org"))
            cls.link("owns", cls.slot("vuln-member"), admin)
            cls.connection.execute(
                "DELETE FROM relationships WHERE src_entity_id = $1::uuid"
                "   AND dst_entity_id = $2::uuid AND type = 'owns'",
                (cls.slot("vuln-guest"), application),
            )

    @classmethod
    def route(cls, application: str, key: str) -> str:
        """The Entity one projection key names, through the corpus's own lookup."""
        return str(
            cls.connection.execute(
                "SELECT entity_id::text FROM rk2_surface_reach($1::uuid) WHERE key = $2",
                (application, key),
            ).scalar()
        )

    @classmethod
    def technology(cls, application: str, name: str) -> str:
        return str(
            cls.connection.execute(
                "SELECT t.entity_id::text FROM technologies t"
                "  JOIN relationships r ON r.dst_entity_id = t.entity_id"
                " WHERE r.src_entity_id = $1::uuid AND r.type = 'runs' AND t.name = $2",
                (application, name),
            ).scalar()
        )

    @classmethod
    def slot(cls, name: str) -> str:
        """One Identity by the slot name this fixture gave it.

        By slot rather than by class, because the slot is what a fixture holds
        and the class is what the projection carries -- and a helper that
        looked one up by the other would be the projection's own rule, restated
        in the test that is supposed to check it.
        """
        return str(
            cls.connection.execute(
                "SELECT entity_id::text FROM identities WHERE slot_name = $1", (name,)
            ).scalar()
        )

    @classmethod
    def refute(cls, subject: str, fingerprint: str) -> str:
        """One refuted Hypothesis, holding the fingerprint it was refuted under."""
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            return str(
                cls.connection.execute(
                    "INSERT INTO hypotheses (program_id, subject_entity_id,"
                    " property_class, statement, status, observed_fingerprint)"
                    " VALUES ($1::uuid, $2::uuid, 'authorization.function_access',"
                    " 'the export route refuses an anonymous caller', 'refuted', $3)"
                    " RETURNING id::text",
                    (cls.program_id, subject, fingerprint),
                ).scalar()
            )

    @classmethod
    def compute(cls, application: str) -> dict:
        with cls.connection.transaction():
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            cls.connection.execute(
                "SELECT set_config('rk2.program_id', $1, true)", (cls.program_id,)
            )
            return proxy.as_object(
                cls.connection.execute(
                    "SELECT compute_surface_fingerprint($1::uuid)", (application,)
                ).scalar()
            )

    def projection(self, application: str) -> dict:
        return proxy.as_object(
            self.connection.execute(
                "SELECT rk2_surface_projection($1::uuid)", (application,)
            ).scalar()
        )

    def deltas(self) -> dict:
        """The last recompute's deltas, by kind, each with its subject key."""
        found: dict[str, list] = {}
        for row in self.connection.execute(
            "SELECT kind, subject_key, subject, property_classes::text"
            "  FROM v_surface_deltas WHERE fingerprint = $1 ORDER BY kind, subject_key",
            (self.changed["fingerprint"],),
        ).rows:
            found.setdefault(str(row[0]), []).append(
                (str(row[1]), None if row[2] is None else str(row[2]),
                 json.loads(str(row[3])))
            )
        return found

    # -- criterion 1: a documented canonical projection -----------------------

    def test_the_projection_is_the_sections_the_registry_names(self):
        registered = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT section FROM surface_projection_sections"
            ).rows
        }
        projection = self.projection(self.secure)

        self.assertEqual(registered | {"application_kind"}, set(projection))
        self.assertEqual("web", projection["application_kind"])
        # And an Application that is not there still carries every section, so
        # the standing check can ask the function what its shape is rather than
        # asking one stored row that may predate the answer.
        empty = self.projection(None)

        self.assertEqual(registered | {"application_kind"}, set(empty))
        self.assertEqual([[] for _ in registered], [empty[s] for s in sorted(registered)])

    def test_the_projection_carries_no_identifier_no_label_and_no_timestamp(self):
        # The three the criterion names, plus the two the twins would differ by.
        written = json.dumps(self.projection(self.vulnerable))
        labels = [
            str(row[0])
            for row in self.connection.execute(
                "SELECT label FROM entities WHERE program_id = $1::uuid",
                (self.program_id,),
            ).rows
        ]

        self.assertNotRegex(written, r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}")
        self.assertNotRegex(written, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
        self.assertNotIn("vulnerable.example.com", written)
        self.assertNotIn("vuln-member", written)
        for label in labels:
            self.assertNotIn(f'"{label}"', written)

    def test_the_projection_says_what_it_carries_rather_than_which_rows(self):
        # Every element is keyed, and the key is what a delta is about. An
        # element without one would be a change nothing could name.
        projection = self.projection(self.secure)

        for section in ("endpoints", "parameters", "technologies",
                        "identity_relationships"):
            keys = [element["key"] for element in projection[section]]
            self.assertEqual(sorted(keys), keys, section)
            self.assertEqual(len(set(keys)), len(keys), section)
        self.assertEqual(
            ["GET /notes", "POST /notes"],
            [element["key"] for element in projection["endpoints"]],
        )
        self.assertEqual(
            ["anonymous|owns", "user|member_of", "user|owns"],
            [element["key"] for element in projection["identity_relationships"]],
        )

    # -- criterion 2: same surface, same fingerprint --------------------------

    def test_two_twins_written_in_opposite_orders_fingerprint_the_same(self):
        self.assertEqual(
            self.first_secure["fingerprint"], self.first_vulnerable["fingerprint"]
        )
        self.assertEqual(
            self.projection(self.secure),
            proxy.as_object(
                self.connection.execute(
                    "SELECT inputs FROM surface_fingerprints WHERE id = $1::uuid",
                    (self.first_vulnerable["fingerprint_id"],),
                ).scalar()
            ),
        )

    def test_recomputing_an_unchanged_surface_repeats_the_fingerprint(self):
        self.assertTrue(self.first_secure["baseline"])
        self.assertFalse(self.again_secure["baseline"])
        self.assertEqual(self.first_secure["fingerprint"], self.again_secure["fingerprint"])
        self.assertFalse(self.again_secure["changed"])
        self.assertEqual(0, self.again_secure["deltas"])

    def test_an_unchanged_recompute_is_still_a_row(self):
        # "We looked and it was the same" is a fact, and a function that only
        # wrote when something moved could not tell it from nobody looking.
        [row] = self.connection.execute(
            "SELECT count(*) FROM surface_fingerprints WHERE application_entity_id = $1::uuid",
            (self.secure,),
        ).rows

        self.assertEqual(2, int(row[0]))

    # -- criterion 3: typed deltas, and a new fingerprint ---------------------

    def test_the_mutation_moved_the_fingerprint(self):
        self.assertTrue(self.changed["changed"])
        self.assertNotEqual(
            self.first_vulnerable["fingerprint"], self.changed["fingerprint"]
        )
        self.assertEqual(
            self.first_vulnerable["fingerprint"], self.changed["previous_fingerprint"]
        )

    def test_every_kind_of_change_the_vocabulary_has_is_reachable(self):
        vocabulary = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT kind FROM surface_delta_kinds"
            ).rows
        }

        self.assertEqual(12, len(vocabulary))
        self.assertEqual(vocabulary, set(self.deltas()))

    def test_the_added_route_and_its_parameter_are_typed_additions(self):
        found = self.deltas()

        self.assertEqual(
            ["GET /admin/export"], [key for key, _, _ in found["endpoint_added"]]
        )
        self.assertEqual(
            ["GET /admin/export#query:next"],
            [key for key, _, _ in found["parameter_added"]],
        )

    def test_a_retired_route_takes_its_parameter_with_it(self):
        found = self.deltas()

        self.assertEqual(
            ["POST /notes"], [key for key, _, _ in found["endpoint_removed"]]
        )
        self.assertEqual(
            ["POST /notes#body:body"],
            [key for key, _, _ in found["parameter_removed"]],
        )

    def test_a_changed_route_is_one_delta_carrying_both_sides(self):
        [row] = self.connection.execute(
            "SELECT before_element, after_element FROM v_surface_deltas"
            " WHERE kind = 'endpoint_changed'"
        ).rows
        before, after = proxy.as_object(row[0]), proxy.as_object(row[1])

        self.assertEqual("GET /notes", after["key"])
        self.assertTrue(before["auth_required"])
        self.assertFalse(after["auth_required"])

    def test_a_parameter_that_started_reflecting_is_a_change_not_a_pair(self):
        found = self.deltas()

        self.assertEqual(
            ["GET /notes#query:q"], [key for key, _, _ in found["parameter_changed"]]
        )
        self.assertNotIn(
            "GET /notes#query:q", [key for key, _, _ in found["parameter_added"]]
        )

    def test_a_version_bump_is_one_technology_change(self):
        found = self.deltas()
        [row] = self.connection.execute(
            "SELECT before_element, after_element FROM v_surface_deltas"
            " WHERE kind = 'technology_changed'"
        ).rows

        self.assertEqual(["nginx"], [key for key, _, _ in found["technology_changed"]])
        self.assertEqual(["1.24.0"], proxy.as_object(row[0])["versions"])
        self.assertEqual(["1.27.0"], proxy.as_object(row[1])["versions"])
        self.assertEqual(["express"], [key for key, _, _ in found["technology_added"]])
        self.assertEqual(["openssl"], [key for key, _, _ in found["technology_removed"]])

    def test_a_new_class_of_holder_and_a_holder_that_gained_a_route(self):
        found = self.deltas()
        [row] = self.connection.execute(
            "SELECT before_element, after_element FROM v_surface_deltas"
            " WHERE kind = 'identity_relationship_changed'"
        ).rows

        self.assertEqual(
            ["privileged|member_of", "privileged|owns"],
            [key for key, _, _ in found["identity_relationship_added"]],
        )
        self.assertEqual(
            ["anonymous|owns"],
            [key for key, _, _ in found["identity_relationship_removed"]],
        )
        self.assertEqual(["user|owns"], [key for key, _, _ in found["identity_relationship_changed"]])
        self.assertEqual(["GET /notes"], proxy.as_object(row[0])["targets"])
        self.assertEqual(
            ["GET /admin/export", "GET /notes"], proxy.as_object(row[1])["targets"]
        )

    # -- criterion 4: an operation, with an Event, never a read ---------------

    def test_every_fingerprint_is_an_event_somebody_caused(self):
        [row] = self.connection.execute(
            "SELECT (SELECT count(*) FROM surface_fingerprints WHERE program_id = $1::uuid),"
            "       (SELECT count(*) FROM events WHERE program_id = $1::uuid"
            "         AND type = 'surface.fingerprinted')",
            (self.program_id,),
        ).rows

        self.assertEqual(4, int(row[0]))
        self.assertEqual(int(row[0]), int(row[1]))

    def test_the_event_says_what_moved_and_by_how_much(self):
        payload = proxy.as_object(
            self.connection.execute(
                "SELECT payload FROM events WHERE type = 'surface.fingerprinted'"
                "   AND payload ->> 'fingerprint_id' = $1"
                " ORDER BY seq DESC LIMIT 1",
                (self.changed["fingerprint_id"],),
            ).scalar()
        )

        self.assertTrue(payload["changed"])
        self.assertFalse(payload["baseline"])
        self.assertEqual(13, payload["deltas"])
        self.assertEqual(2, payload["by_kind"]["identity_relationship_added"])
        # The Event and the caller get the same account of the same act, which
        # is one object in the function rather than two that agree today.
        self.assertEqual(self.changed, payload)

    def test_the_program_wide_verb_is_what_recon_calls(self):
        # "After recon" is the Program rather than one Application: a promotion
        # returns labels, not which Application each one landed under, so the
        # runtime asks for all of them and an untouched one gets the row that
        # says it was untouched. Rolled back, because every other test in this
        # case counts the rows the fixture wrote.
        self.connection.execute("BEGIN")
        try:
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            self.connection.execute(
                "SELECT set_config('rk2.program_id', $1, true)", (self.program_id,)
            )
            swept = proxy.as_object(
                self.connection.execute("SELECT fingerprint_program_surface()").scalar()
            )
            written = self.connection.execute(
                "SELECT count(*) FROM events WHERE program_id = $1::uuid"
                "   AND type = 'surface.fingerprinted'",
                (self.program_id,),
            ).rows[0][0]
        finally:
            self.connection.execute("ROLLBACK")

        self.assertEqual(2, swept["applications"])
        self.assertEqual(0, swept["changed"])
        self.assertEqual(6, int(written))
        self.assertEqual(
            sorted([self.first_secure["fingerprint"], self.changed["fingerprint"]]),
            sorted(one["fingerprint"] for one in swept["fingerprints"]),
        )

    def test_reading_the_surface_recomputes_nothing(self):
        def counted() -> tuple[int, int]:
            [row] = self.connection.execute(
                "SELECT (SELECT count(*) FROM surface_fingerprints WHERE program_id = $1::uuid),"
                "       (SELECT count(*) FROM surface_deltas WHERE program_id = $1::uuid)",
                (self.program_id,),
            ).rows
            return int(row[0]), int(row[1])

        before = counted()
        self.connection.execute("SELECT * FROM v_surface_deltas").rows
        self.connection.execute(
            "SELECT rk2_surface_projection($1::uuid)", (self.vulnerable,)
        ).scalar()
        self.connection.execute(
            "SELECT record FROM v_records WHERE kind = 'entity'"
        ).rows

        self.assertEqual(before, counted())

    def test_nothing_else_in_the_corpus_writes_a_fingerprint(self):
        # The verb is the only writer, so the fingerprint cannot become a function
        # of who looked. A trigger on the table would be the way that stopped
        # being true without anybody deciding it.
        [row] = self.connection.execute(
            "SELECT count(*) FROM pg_trigger t"
            " WHERE t.tgrelid = 'surface_fingerprints'::regclass"
            "   AND NOT t.tgisinternal"
        ).rows
        writers = [
            str(other[0])
            for other in self.connection.execute(
                "SELECT p.proname FROM pg_proc p"
                "  JOIN pg_namespace n ON n.oid = p.pronamespace"
                " WHERE n.nspname = 'public'"
                "   AND p.prosrc ILIKE '%INSERT INTO surface_fingerprints%'"
            ).rows
        ]

        self.assertEqual(0, int(row[0]))
        self.assertEqual(["compute_surface_fingerprint"], writers)

    # -- criterion 5: subjects and classes, as rows ---------------------------

    def test_a_delta_names_the_row_it_is_about(self):
        found = self.deltas()
        [(_, subject, _)] = found["endpoint_added"]
        [(_, gone, _)] = found["endpoint_removed"]

        self.assertEqual(
            subject,
            str(
                self.connection.execute(
                    "SELECT label FROM entities WHERE id = $1::uuid",
                    (self.route(self.vulnerable, "GET /admin/export"),),
                ).scalar()
            ),
        )
        # And a subject that is gone is null rather than a label that no longer
        # resolves: the key still says what changed.
        self.assertIsNone(gone)

    def test_each_delta_carries_the_classes_it_puts_back_in_question(self):
        found = self.deltas()
        [(_, _, added)] = found["endpoint_added"]
        [(_, _, reflected)] = found["parameter_changed"]
        [(_, _, holder)] = found["identity_relationship_changed"]

        self.assertIn("authorization.function_access", added)
        self.assertIn("injection.markup", reflected)
        self.assertIn("authorization.tenant_isolation", holder)
        # And no kind that says something appeared or changed maps to nothing:
        # a delta with an empty class list is one ticket 34 would find and then
        # have no reason to act on.
        silent = self.connection.execute(
            "SELECT k.kind FROM surface_delta_kinds k"
            " WHERE k.change <> 'removed' AND NOT EXISTS ("
            "   SELECT 1 FROM surface_delta_property_classes pc WHERE pc.kind = k.kind)"
        ).rows

        self.assertEqual([], list(silent))

    def test_a_removal_puts_no_class_back_in_question(self):
        # The decision, not an omission: a route that is gone tests nothing,
        # and a refutation about it is not made due by its subject vanishing.
        found = self.deltas()

        for kind, rows in found.items():
            if kind.endswith("_removed"):
                for _, _, classes in rows:
                    self.assertEqual([], classes, kind)

    def test_recomputing_declares_no_previous_refutation_invalid(self):
        [row] = self.connection.execute(
            "SELECT status, observed_fingerprint, superseded_by FROM hypotheses"
            " WHERE id = $1::uuid",
            (self.refuted,),
        ).rows

        self.assertEqual("refuted", str(row[0]))
        self.assertEqual(self.first_vulnerable["fingerprint"], str(row[1]))
        self.assertIsNone(row[2])
        # What makes it retestable is the join a later ticket can make: this
        # subject, this class, and a delta that names both.
        [joined] = self.connection.execute(
            "SELECT count(*) FROM hypotheses h"
            "  JOIN surface_deltas d ON d.subject_entity_id = h.subject_entity_id"
            "  JOIN surface_delta_property_classes pc"
            "    ON pc.kind = d.kind AND pc.property_class_id = h.property_class"
            " WHERE h.id = $1::uuid",
            (self.refuted,),
        ).rows

        self.assertEqual(1, int(joined[0]))

    def test_a_section_with_no_subject_rule_is_a_refusal_and_not_a_null(self):
        # A fifth section registered and not answered would give every one of
        # its deltas a null subject, and criterion 5 would quietly stop being
        # true for a whole section without a single arm noticing.
        with self.assertRaises(pg.DatabaseError) as refused:
            self.connection.execute(
                "SELECT rk2_surface_subject($1::uuid, 'selftest_section', 'x')",
                (self.vulnerable,),
            )

        self.assertIn("no subject rule", str(refused.exception))

    def test_two_methods_that_differ_only_in_case_are_two_keys(self):
        # `endpoints` is unique on (application, method, path) case-sensitively,
        # so a projection that folded the case would give one key to two rows:
        # the comparison would cross-join them and the delta's own unique key
        # would abort the recompute.
        self.connection.execute("BEGIN")
        try:
            self.connection.execute("SELECT set_actor('runtime', 'selftest')")
            lower = self.entity(
                "endpoint", "http://vulnerable.example.com/get /notes",
                "vulnerable.example.com",
            )
            self.connection.execute(
                "INSERT INTO endpoints (entity_id, application_id, method,"
                " path_template, auth_required) VALUES ($1::uuid, $2::uuid,"
                " 'get', '/notes', false)",
                (lower, self.vulnerable),
            )
            keys = [
                str(row[0])
                for row in self.connection.execute(
                    "SELECT key FROM rk2_surface_reach($1::uuid) ORDER BY key",
                    (self.vulnerable,),
                ).rows
            ]
        finally:
            self.connection.execute("ROLLBACK")

        self.assertIn("get /notes", keys)
        self.assertIn("GET /notes", keys)
        self.assertEqual(len(set(keys)), len(keys))

    # -- criterion 6: the twins ----------------------------------------------

    def test_the_twins_differ_by_exactly_what_the_vulnerable_one_gained(self):
        secure = self.projection(self.secure)
        vulnerable = self.projection(self.vulnerable)

        self.assertNotEqual(
            self.fingerprint_of(secure), self.fingerprint_of(vulnerable)
        )
        self.assertEqual(
            {"GET /notes", "POST /notes"},
            {element["key"] for element in secure["endpoints"]},
        )
        self.assertEqual(
            {"GET /notes", "GET /admin/export"},
            {element["key"] for element in vulnerable["endpoints"]},
        )
        # And the secure twin has not moved while the vulnerable one did.
        self.assertEqual(self.first_secure["fingerprint"], self.fingerprint_of(secure))

    def fingerprint_of(self, projection: dict) -> str:
        return str(
            self.connection.execute(
                "SELECT rk2_surface_fingerprint($1::jsonb)", (json.dumps(projection),)
            ).scalar()
        )

    # -- the invariant --------------------------------------------------------

    def test_the_standing_check_is_registered_and_holds(self):
        [registered] = self.connection.execute(
            "SELECT count(*) FROM standing_checks WHERE name = 'surface_fingerprint'"
        ).rows
        problems = self.connection.execute(
            "SELECT problem, subject FROM check_surface_fingerprint()"
        ).rows

        self.assertEqual(1, int(registered[0]))
        self.assertEqual([], list(problems))


#: The Programs the slate case opens. One per scenario, because a slate is a
#: Program's own and claiming off it moves that Program's Lane: two scenarios
#: sharing a Program would be two orchestrators contending for one Lane, which
#: is what only the last of them is about.
SLATE_SLUG = "selftest-slate"

#: A budget wide enough to offer a recon Task and, once spent against, too
#: narrow to claim one. `claimable_for` calls a Task affordable where
#: `tokens_left` covers `estimated_cost * cost_reference_tokens` -- 60000 for a
#: recon Task with no run history to shrink its 0.30 prior -- so 100000 opens
#: and `SLATE_SPEND` closes it while leaving the budget itself unexhausted,
#: which is a refusal with a different name.
SLATE_TIGHT = budgets(
    requests=500, tokens=100000, run_tokens=2000, run_requests=50,
    lane_tokens=100000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: What one Agent run spends to take that Program under the line.
SLATE_SPEND = (40000, 10000)

#: How many orchestrators race for one Lane in the contended Program. Four
#: against a Lane that admits one, so three of them have to come back empty
#: rather than partially claimed.
SLATE_CONTENDERS = 4

#: The bytes the analyze scenario's subject was seen through. Any 64 hex
#: characters do: `artifacts` is content-addressed and nothing on the claim path
#: hashes anything back, so what `ready_for` asks is that the row exists, is
#: agent-visible, is unencrypted and is reachable from an Observation.
ANALYZED_SHA = "7e" * 32

#: What the seeded Findings are findings of. One of 034's seeded classes, chosen
#: because it is the family the seeded Hypotheses' property class belongs to.
FINDING_CLASS = "idor"

#: Every Task kind, in the order the roster scenario seeds and claims them. One
#: Task each, and all five claimed, because a role's model and effort are what
#: the claim is being asked about and each kind reaches a different role.
SLATE_KINDS = ("recon", "hunt", "analyze", "validate", "report")


class SchedulerFixture:
    """The moves every scheduler scenario is built out of, on live rows.

    Seeding a Program, ranking it, offering the slate and claiming off it are
    the same six statements whatever the scenario is about, and the classes
    below are about different things: 23 is about the gap between an offer and
    a claim, 25 about the capacity a claim holds out of the pool. Shared here
    so that a change to how a Task is seeded is one edit rather than one per
    ticket that ever seeded one.

    It assumes what both cases set up: `cls.connection` as the migrate
    connection, `cls.runtime` as a runtime one, and `cls.identifiers` mapping a
    scenario name to a Program.
    """

    @classmethod
    def started(cls, name: str, run: object) -> execution.Claimed:
        """The claimed run as the runtime reads it back, through its own query.

        `execution.STARTED` rather than a statement written here: what is under
        test is that the number the runtime carries to the child is the one the
        claim ran against, and a second query would only prove that the column
        can be selected.
        """
        rows = cls.runtime.execute(
            execution.STARTED, (str(run), cls.identifiers[name])
        ).rows
        return execution.Claimed.from_row(rows[0])

    @classmethod
    def hypothesis(
        cls,
        name: str,
        subject: str,
        worth: str,
        property_class: str = "authorization.object_ownership",
    ) -> str:
        """One testable Hypothesis on the subject.

        The shape a hunt needs under it and the shape a Finding is a finding
        of are the same shape, so both take it from here. `worth` is what
        distinguishes them when a row is read back by hand.

        `property_class` is a parameter because `hypotheses_dedup_idx` is
        unique over `(subject, identity_a, identity_b, property_class)`: two
        Hypotheses about one subject have to disagree about what property is at
        stake, which is the point the index is making.
        """
        return str(
            cls.scalar(
                "INSERT INTO hypotheses (program_id, subject_entity_id,"
                " property_class, statement, status)"
                " VALUES ($1::uuid, $2::uuid, $3, $4, 'testable') RETURNING id::text",
                (
                    cls.identifiers[name],
                    subject,
                    property_class,
                    f"a hypothesis {worth}",
                ),
            )
        )

    # -- what the scenarios are built out of -----------------------------------

    @classmethod
    def seed(cls, name: str, count: int, kind: str = "recon") -> list[str]:
        """`count` endpoints under one application, and one Task about each.

        The Tasks differ only in what they promise -- the i-th is worth 0.1*i in
        both gain and impact -- so the order the ranking should reach is known
        here without this file recomputing the weights it is testing. Written as
        the owner and in one transaction, because an endpoint whose application
        did not commit with it is a Task with no resolvable subject.
        """
        program_id = cls.identifiers[name]
        labels = []
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            application = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'application', '', 'host', $2, 80, $3)",
                    (program_id, HOST, f"application:{BASE_URL}"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO applications (entity_id, base_url, kind)"
                " VALUES ($1::uuid, $2, 'web')",
                (application, BASE_URL),
            )
            for index in range(1, count + 1):
                path = f"{PATH}/{index}"
                endpoint = str(
                    cls.connection.execute(
                        "SELECT add_entity($1::uuid, 'endpoint', '', 'host', $2, 80, $3)",
                        (program_id, HOST, f"endpoint:GET {path}"),
                    ).scalar()
                )
                cls.connection.execute(
                    "INSERT INTO endpoints (entity_id, application_id, method,"
                    " path_template) VALUES ($1::uuid, $2::uuid, 'GET', $3)",
                    (endpoint, application, path),
                )
                labels.append(
                    str(
                        cls.connection.execute(
                            "INSERT INTO tasks (program_id, kind, status,"
                            " subject_entity_id, expected_information_gain,"
                            " potential_impact) VALUES ($1::uuid, $2, 'pending',"
                            " $3::uuid, $4, $4) RETURNING label",
                            (program_id, kind, endpoint, str(round(0.1 * index, 2))),
                        ).scalar()
                    )
                )
        return labels

    @classmethod
    def bind(cls, name: str):
        """Which Program the runtime connection is speaking for from here on."""
        cls.runtime.execute(agent.BIND, (cls.identifiers[name],))

    @classmethod
    def offer(cls) -> tuple[dict[str, object], ...]:
        """One Ranking pass, one Lane quota, and the slate they leave."""
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            cls.runtime.execute("SELECT rank_pass('runtime')")
            cls.runtime.execute("SELECT advance_lane_quota('runtime')")
            return cls.runtime.execute("SELECT * FROM offer_slate()").dicts()

    @classmethod
    def call(cls, sql: str, parameters: tuple = ()) -> object:
        """One statement as the runtime, in its own transaction."""
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            return cls.runtime.execute(sql, parameters).scalar()

    @classmethod
    def refusal(cls, sql: str, parameters: tuple = ()) -> str:
        """What one refused statement raised, insisting that it did."""
        try:
            cls.call(sql, parameters)
        except pg.DatabaseError as refused:
            return str(refused)
        raise AssertionError(f"not refused: {sql} {parameters}")

    @classmethod
    def operator(cls, sql: str, parameters: tuple = ()) -> object:
        """One statement as the operator, on a connection of its own.

        PH2-26 grants the weights verb to `rk2_human` and to nothing else, so a
        test that versioned the weights as the owner would be exercising a path
        no operator has. Opened per call rather than held: the scenarios that
        need it move the weights twice each, and a connection kept open across
        a class that commits is one more thing to close on a failure path.
        """
        connection = pg.connect(cls.harness.human)
        try:
            with connection.transaction():
                return connection.execute(sql, parameters).scalar()
        finally:
            connection.close()

    @classmethod
    def as_owner(cls, sql: str, parameters: tuple = ()):
        """One statement as the role that owns the rows the scheduler reads."""
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            return cls.connection.execute(sql, parameters)

    @classmethod
    def scalar(cls, sql: str, parameters: tuple = ()) -> object:
        """One reading as the owner, which every Program's rows are visible to.

        `DatabaseCase.owned` is the same statement, and this is not it: that one
        stringifies its answer, and half of what is read here is a count or a
        boolean that a string would flatten into something always true.
        """
        return cls.as_owner(sql, parameters).scalar()

    @classmethod
    def claimable(cls, name: str, label: str) -> str | None:
        """Why one Task may not be claimed, in the scheduler's own vocabulary."""
        answer = cls.scalar(
            "SELECT claimable_for(t, w) FROM tasks t CROSS JOIN scheduler_weights w"
            " WHERE w.active AND t.program_id = $1::uuid AND t.label = $2",
            (cls.identifiers[name], label),
        )
        return None if answer is None else str(answer)

    @classmethod
    def claimed_by(cls, name: str, run: object) -> str | None:
        """The Task an Agent run was opened against, by label."""
        claimed = cls.scalar(
            "SELECT t.label FROM agent_runs a JOIN tasks t ON t.id = a.task_id"
            " WHERE a.program_id = $1::uuid AND a.label = $2",
            (cls.identifiers[name], str(run)),
        )
        return None if claimed is None else str(claimed)

    @classmethod
    def counted(cls, name: str) -> tuple[int, int]:
        """How much of a Program has moved: Tasks off pending, and Agent runs."""
        program_id = cls.identifiers[name]
        return (
            int(
                cls.scalar(
                    "SELECT count(*) FROM tasks"
                    " WHERE program_id = $1::uuid AND status <> 'pending'",
                    (program_id,),
                )
            ),
            int(
                cls.scalar(
                    "SELECT count(*) FROM agent_runs WHERE program_id = $1::uuid",
                    (program_id,),
                )
            ),
        )

    @classmethod
    def tokens_left(cls, name: str) -> int:
        return int(
            cls.scalar(
                "SELECT tokens_left FROM program_budget WHERE program_id = $1::uuid",
                (cls.identifiers[name],),
            )
        )

    @classmethod
    def contend(cls, name: str, gate: threading.Barrier, guard: threading.Lock):
        """One orchestrator's whole part in a race, on its own connection.

        A refusal is recorded rather than raised, because most of these are
        supposed to lose and a loser that raised in a thread would fail nothing.
        """
        connection = pg.connect(cls.harness.runtime)
        try:
            connection.execute(agent.BIND, (cls.identifiers[name],))
            gate.wait()
            try:
                with connection.transaction():
                    connection.execute("SELECT set_actor('runtime', 'selftest')")
                    outcome = connection.execute("SELECT claim_task()").scalar()
            except pg.DatabaseError as refused:
                outcome = f"refused: {refused}"
            with guard:
                cls.outcomes.append(None if outcome is None else str(outcome))
        finally:
            connection.close()


class SlateClaimTest(SchedulerFixture, DatabaseCase):
    """PH2-23: a Slate is offered, and exactly one Task is claimed off it.

    Every question here is one only a server can answer, because what ticket 23
    asks about is the gap between two moments -- what the Ranking pass decided
    when it wrote the slate, and what is still true when a claim arrives. A
    recorder cannot have a gap: only real rows can move under an offer.

    The Programs are the scenarios. Each one is opened, seeded, offered a slate
    and then disturbed in exactly one way -- a Task that runs out of attempts, a
    Lane that fills, a budget that gets spent, an Identity that gets leased, a
    slate that ages past its expiry, a choice whose entry is consumed under it,
    a second Program that owns the label being asked for. What the claim then
    does with the disturbance is the whole of the ticket.

    One Program is not disturbed at all: the `roster` one carries a Task of
    every kind, and what it asks is PH2-71's -- that the run each claim opens
    carries the claimed role's own model and effort.

    Everything runs in `setUpClass` because all of it commits: a claim repeated
    per test would be a second claim on a Task the first one took, and the
    refusals only mean anything against the state the steps before them left.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)

        cls.identifiers = {}
        for name, budgets in (
            ("ranked", AFFORDABLE),
            ("fallback", AFFORDABLE),
            ("refused", AFFORDABLE),
            ("onlooker", AFFORDABLE),
            ("picked", AFFORDABLE),
            ("stale", AFFORDABLE),
            ("spent", SLATE_TIGHT),
            ("held", AFFORDABLE),
            ("contended", AFFORDABLE),
            ("roster", AFFORDABLE),
            ("capped", AFFORDABLE),
        ):
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, budgets).replace(
                    'name = "matrix-web"', f'name = "{SLATE_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.identifiers[name] = opened.facts["program_id"]

        cls.arrange_ranked()
        cls.arrange_fallback()
        cls.arrange_refused()
        cls.arrange_picked()
        cls.arrange_stale()
        cls.arrange_spent()
        cls.arrange_held()
        cls.arrange_contended()
        cls.arrange_model_and_effort()
        cls.arrange_subagent_cap()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            # The rollup edge goes first, and this is a workaround rather than
            # tidiness: `finding_hypotheses` cascades from the finding side only
            # (016's `purge_cascade_edges`), while `hypotheses_program_id_fkey`
            # is older than `findings_program_id_fkey` and so cascades first --
            # so the NO ACTION check on the edge fires before the delete that
            # would have removed it, and `DELETE FROM programs` raises. It is a
            # purge that cannot travel its own edge in the order the catalogue
            # happens to hold, which is 031's failure in a place 031 does not
            # repair. Filed as PH2-74; this delete comes out with that ticket.
            cls.connection.execute(
                "DELETE FROM finding_hypotheses WHERE program_id IN"
                " (SELECT id FROM programs WHERE slug LIKE $1)",
                (f"{SLATE_SLUG}-%",),
            )
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{SLATE_SLUG}-%",)
            )
        super().tearDownClass()

    # -- the scenarios ---------------------------------------------------------

    @classmethod
    def arrange_ranked(cls):
        """Two passes over six Tasks nothing disturbs between them."""
        cls.ranked = cls.seed("ranked", 6)
        cls.bind("ranked")
        cls.first = cls.offer()
        cls.again = cls.offer()
        # Whether the one clock reading in the offer is the one the weights
        # declare, asked of the row rather than of the report: an expiry that
        # did not come from `offered_at + slate_ttl` would still look like a
        # timestamp five minutes out to anything comparing it with `now()`.
        cls.expiry_is_the_ttl = cls.scalar(
            "SELECT bool_and(s.offered_at + w.slate_ttl = $2::timestamptz)"
            "  FROM task_slate s CROSS JOIN scheduler_weights w"
            " WHERE w.active AND s.program_id = $1::uuid AND NOT s.consumed",
            (cls.identifiers["ranked"], cls.again[0]["expires_at"]),
        )

    @classmethod
    def arrange_fallback(cls):
        """The top entry stops being claimable after it was offered.

        Nothing re-ranks in between, which is the point: the slate still names
        the Task, and only the claim's own recheck can notice that it has spent
        its last attempt. What the orchestrator asked for is then refused, and
        what it gets by asking for nothing is the next entry that survives.
        """
        cls.seed("fallback", 6)
        cls.bind("fallback")
        cls.offered_fallback = cls.offer()
        cls.top = cls.offered_fallback[0]["task_label"]
        cls.second = cls.offered_fallback[1]["task_label"]
        cls.as_owner(
            "UPDATE tasks SET attempts = 3 WHERE program_id = $1::uuid AND label = $2",
            (cls.identifiers["fallback"], cls.top),
        )
        cls.exhausted = cls.refusal("SELECT claim_task($1)", (cls.top,))
        cls.after_exhausted = cls.counted("fallback")
        cls.fallback_run = cls.call("SELECT claim_task()")
        cls.fallback_task = cls.claimed_by("fallback", cls.fallback_run)
        # One claimed recon Task fills the recon Lane, whose role admits one at
        # a time, so the next pass over the same five survivors offers nothing.
        cls.lane_full = cls.offer()

    @classmethod
    def arrange_refused(cls):
        """Four ways of naming a Task that is not on this Program's slate."""
        cls.elsewhere = cls.seed("onlooker", 6)[5]
        cls.seed("refused", 3)
        cls.bind("refused")
        cls.offered_refused = cls.offer()
        cls.off_slate = cls.refusal("SELECT claim_task($1)", ("T99",))
        cls.cross_program = cls.refusal("SELECT claim_task($1)", (cls.elsewhere,))
        cls.off_slate_pick = cls.refusal("SELECT pick_task($1)", ("T99",))
        cls.as_owner(
            "UPDATE task_slate SET offered_at = now() - interval '10 minutes'"
            " WHERE program_id = $1::uuid AND NOT consumed",
            (cls.identifiers["refused"],),
        )
        cls.expired = cls.refusal("SELECT claim_task()")
        cls.untouched = cls.counted("refused")

    @classmethod
    def arrange_picked(cls):
        """A choice recorded out of band, and honoured by the next claim."""
        cls.seed("picked", 3)
        cls.bind("picked")
        cls.offered_picked = cls.offer()
        cls.chosen = cls.offered_picked[1]["task_label"]
        cls.pick_echo = cls.call("SELECT pick_task($1)", (cls.chosen,))
        cls.picked_task = cls.claimed_by("picked", cls.call("SELECT claim_task()"))
        cls.picks_left = int(
            cls.scalar(
                "SELECT count(*) FROM task_picks"
                " WHERE program_id = $1::uuid AND NOT consumed",
                (cls.identifiers["picked"],),
            )
        )

    @classmethod
    def arrange_stale(cls):
        """A recorded choice whose slate entry is gone by the time it is read.

        The entry is consumed here rather than raced for, and that is a fixture
        decision worth stating. `task_picks` references `tasks` on the Program's
        own key, so recording a pick holds a KEY SHARE lock on the Task row and
        a concurrent `claim_task` blocks on it at `FOR UPDATE` -- the two
        transactions cannot in fact interleave into this state from outside.
        The state itself is reachable, because a claim commits its consumption
        of the slate before the next transaction reads the pick. So what stands
        in for the race is the state the race would leave.
        """
        cls.seed("stale", 3)
        cls.bind("stale")
        offered = cls.offer()
        cls.forgotten = offered[1]["task_label"]
        cls.call("SELECT pick_task($1)", (cls.forgotten,))
        cls.as_owner(
            "UPDATE task_slate s SET consumed = true FROM tasks t"
            " WHERE t.id = s.task_id AND s.program_id = $1::uuid AND t.label = $2",
            (cls.identifiers["stale"], cls.forgotten),
        )
        cls.stale_pick = cls.refusal("SELECT claim_task()")
        cls.stale_counts = cls.counted("stale")

    @classmethod
    def arrange_spent(cls):
        """The budget that made the offer affordable is gone by the claim."""
        cls.seed("spent", 3)
        cls.bind("spent")
        cls.offered_spent = cls.offer()
        cls.needed = int(
            cls.scalar(
                "SELECT max(t.estimated_cost * w.cost_reference_tokens)::bigint"
                "  FROM tasks t CROSS JOIN scheduler_weights w"
                " WHERE w.active AND t.program_id = $1::uuid",
                (cls.identifiers["spent"],),
            )
        )
        cls.left_before = cls.tokens_left("spent")
        # Spent through a run rather than by writing `programs.token_budget`,
        # because the budget is a configured number and the ledger is the only
        # thing entitled to move what is left of it. The role is one that runs
        # no Task, which is what a run with no Task must name.
        cls.as_owner(
            "INSERT INTO agent_runs (program_id, role, model, effort, mission_packet,"
            " input_tokens, output_tokens)"
            " VALUES ($1::uuid, 'orchestrator', 'operator', 'low', '{}', $2, $3)",
            (cls.identifiers["spent"], *SLATE_SPEND),
        )
        cls.left_after = cls.tokens_left("spent")
        cls.unaffordable = cls.refusal(
            "SELECT claim_task($1)", (cls.offered_spent[0]["task_label"],)
        )
        # One Agent run exists here and this fixture opened it, to spend the
        # budget. What a refused claim must not have added is a second.
        cls.after_unaffordable = cls.counted("spent")
        cls.offer_when_poor = cls.offer()

    @classmethod
    def arrange_held(cls):
        """The Identity a hunt needs is leased between the offer and the claim."""
        cls.seed("held", 1, kind="hunt")
        program_id = cls.identifiers["held"]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            cls.identity = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'identity', '', 'host', $2, 80, $3)",
                    (program_id, HOST, "identity:slate-member"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO identities (entity_id, program_id, slot_name, class)"
                " VALUES ($1::uuid, $2::uuid, 'slate-member', 'anonymous')",
                (cls.identity, program_id),
            )
            # A hunt Task is only ready with a testable Hypothesis under it, and
            # a Hypothesis about an Identity is what makes the Task need one.
            hypothesis = str(
                cls.connection.execute(
                    "INSERT INTO hypotheses (program_id, subject_entity_id,"
                    " identity_a_entity_id, property_class, statement, status)"
                    " SELECT $1::uuid, subject_entity_id, $2::uuid,"
                    " 'authorization.object_ownership', 'a slate hypothesis', 'testable'"
                    "   FROM tasks WHERE program_id = $1::uuid AND kind = 'hunt'"
                    " RETURNING id::text",
                    (program_id, cls.identity),
                ).scalar()
            )
            cls.connection.execute(
                "UPDATE tasks SET hypothesis_id = $2::uuid"
                " WHERE program_id = $1::uuid AND kind = 'hunt'",
                (program_id, hypothesis),
            )
        cls.bind("held")
        cls.offered_held = cls.offer()
        holder = str(
            cls.as_owner(
                "INSERT INTO agent_runs (program_id, role, model, effort, mission_packet)"
                " VALUES ($1::uuid, 'orchestrator', 'operator', 'low', '{}')"
                " RETURNING id::text",
                (program_id,),
            ).scalar()
        )
        cls.as_owner(
            "INSERT INTO identity_leases (program_id, identity_entity_id,"
            " holder_agent_run_id, expires_at)"
            " VALUES ($1::uuid, $2::uuid, $3::uuid, now() + interval '10 minutes')",
            (program_id, cls.identity, holder),
        )
        cls.identity_held = cls.refusal(
            "SELECT claim_task($1)", (cls.offered_held[0]["task_label"],)
        )
        # Same reading as the spent Program's: the one run is the lease holder
        # this fixture opened, not a run the refused claim left behind.
        cls.after_identity_held = cls.counted("held")
        cls.offer_while_held = cls.offer()

    @classmethod
    def arrange_contended(cls):
        """Four orchestrators claim off one slate at once."""
        cls.seed("contended", 5)
        cls.bind("contended")
        cls.offer()

        gate = threading.Barrier(SLATE_CONTENDERS)
        guard = threading.Lock()
        cls.outcomes: list[str | None] = []
        contenders = [
            threading.Thread(target=cls.contend, args=("contended", gate, guard))
            for _ in range(SLATE_CONTENDERS)
        ]
        for contender in contenders:
            contender.start()
        for contender in contenders:
            contender.join()
        cls.contended_counts = cls.counted("contended")
        cls.contended_integrity = list(
            cls.connection.execute(
                "SELECT problem, detail, count FROM check_event_log_integrity($1::uuid)",
                (cls.identifiers["contended"],),
            ).rows
        )

    @classmethod
    def arrange_model_and_effort(cls):
        """One Task of every kind, each claimed, each against its roster row.

        PH2-71's criterion 3. `claim_task` used to decide a run's model and
        effort from `runs_as` alone, so three of the five agent roles ran at a
        model and an effort the roster does not give them -- and a fixture that
        claims only recon Tasks cannot see that, because recon is one of the two
        the constant happened to be right about. Every kind is seeded ready
        here, which is also the first time `claimable_for` is asked about all
        five in one Program.

        Each run is closed before the next Task is claimed, and that is not
        tidiness. `global_subagent_cap` counts every claimed or running Task in
        the Program whose lane role runs as a subagent and then refuses the
        claim in front of it, whatever that claim would start: three of the
        five kinds are subagent ones (recon, web_hunter, js_analyst -- the
        validator holds a session and the reporter is a renderer), so with all
        three left open the validate claim is refused for somebody else's
        concurrency. Closing hands the Task back to `pending` with the attempt
        spent, which frees both the lane and the count. That the cap also
        refuses claims which start no subagent at all is real and is PH2-75.
        """
        program_id = cls.identifiers["roster"]
        labels = cls.seed("roster", 5)
        by_kind = dict(zip(SLATE_KINDS, labels, strict=True))
        subjects = {
            kind: str(
                cls.scalar(
                    "SELECT subject_entity_id::text FROM tasks"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (program_id, label),
                )
            )
            for kind, label in by_kind.items()
        }

        # A hunt is ready with a testable Hypothesis under it.
        hypothesis = cls.hypothesis("roster", subjects["hunt"], "worth hunting")
        cls.as_owner(
            "UPDATE tasks SET kind = 'hunt', hypothesis_id = $3::uuid"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, by_kind["hunt"], hypothesis),
        )

        # An analyze is ready with an agent-visible Artifact reachable from an
        # Observation on its subject, which is ticket 12's `artifact_refs`
        # bridge: content-addressed bytes, a Receipt of this Program citing
        # them, and an Observation citing the Receipt.
        cls.as_owner(
            "INSERT INTO artifacts (sha256, byte_size, content_type, visibility)"
            " VALUES ($1, 9, 'text/plain', 'agent_visible')",
            (ANALYZED_SHA,),
        )
        receipt = str(
            cls.scalar(
                # The replay lane, because 040 fences the agent one: an allowed
                # agent receipt has to name a live capability held by a running
                # tool run, which is a whole exchange this fixture does not have
                # and `ready_for` does not ask about. The scope class and the
                # policy version it was classified under are 021's biconditional
                # -- a receipt of the Program's own traffic carries both.
                "INSERT INTO receipts (program_id, lane, decision, reason,"
                " ts_arrival, response_agent_sha, scope_class, scope_version)"
                " VALUES ($1::uuid, 'replay', 'allowed', 'seeded', now(), $2,"
                "         'target', (SELECT max(version) FROM program_scope_versions"
                "                     WHERE program_id = $1::uuid))"
                " RETURNING id::text",
                (program_id, ANALYZED_SHA),
            )
        )
        cls.as_owner(
            "INSERT INTO observations (program_id, subject_entity_id, kind, summary,"
            " provenance_kind, receipt_id)"
            " VALUES ($1::uuid, $2::uuid, 'artifact_captured', 'a body worth reading',"
            " 'receipt', $3::uuid)",
            (program_id, subjects["analyze"], receipt),
        )
        cls.as_owner(
            "UPDATE tasks SET kind = 'analyze'"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, by_kind["analyze"]),
        )

        # A validate is ready with a candidate Finding that has a test spec
        # behind it; a report is ready with a validated Finding anywhere in the
        # Program, and a validated Finding is one the runtime re-ran.
        candidate = cls.finding("roster", subjects["validate"], "candidate")
        cls.as_owner(
            "UPDATE tasks SET kind = 'validate', finding_id = $3::uuid"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, by_kind["validate"], candidate),
        )
        cls.finding("roster", subjects["report"], "validated")
        cls.as_owner(
            "UPDATE tasks SET kind = 'report'"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, by_kind["report"]),
        )

        cls.bind("roster")
        cls.offer()
        cls.claimed_runs = {}
        for kind in SLATE_KINDS:
            run = cls.call("SELECT claim_task($1)", (by_kind[kind],))
            claimed = cls.as_owner(
                "SELECT a.id::text AS id, a.role, a.model, a.effort,"
                "       r.model AS roster_model, r.effort AS roster_effort"
                "  FROM agent_runs a JOIN roles r ON r.role = a.role"
                " WHERE a.program_id = $1::uuid AND a.label = $2",
                (program_id, str(run)),
            ).dicts()[0]
            cls.claimed_runs[kind] = claimed
            cls.call("SELECT finish_task_attempt($1::uuid, 'completed')",
                     (claimed["id"],))

    @classmethod
    def arrange_subagent_cap(cls):
        """The one number moved, and both sides of the runtime seam moving.

        PH2-73's criterion 2. `scheduler_weights.max_concurrent_subagents` is
        what the claim refuses past and what the pre-tool gate refuses past,
        and until this ticket the gate held its own copy of it -- so raising
        the row offered a subagent the gate then denied, and lowering it left
        the gate as code that never fired.

        Both claims are made against one slate, offered before the row is
        touched, because it is the claim that re-reads the weights: the Task
        the Slate offered is refused at a cap of one and taken at a cap of two,
        with nothing about the Task itself different between the two attempts.
        The row is put back at the end, and `cap_after` is what says so -- it
        is a global row, and every scenario after this one would otherwise be
        scheduled under a cap this fixture chose.
        """
        program_id = cls.identifiers["capped"]
        first, second = cls.seed("capped", 2)
        subject = str(
            cls.scalar(
                "SELECT subject_entity_id::text FROM tasks"
                " WHERE program_id = $1::uuid AND label = $2",
                (program_id, second),
            )
        )
        cls.as_owner(
            "UPDATE tasks SET kind = 'hunt', hypothesis_id = $3::uuid"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, second, cls.hypothesis("capped", subject, "worth hunting")),
        )

        cls.bind("capped")
        cls.offer()
        cls.cap_before = cls.cap()

        # `finally`, because the number is global: an arrangement that raised
        # between the two claims would leave every case after it -- in this
        # class and in every other -- scheduled at whatever this one last set,
        # and the test that checks the row was restored would never run.
        try:
            # One subagent Task claimed and running, which is the whole of the
            # Program's count. The recon lane admits one at a time, so what
            # refuses the hunt below cannot be this Task's lane.
            cls.set_cap(1)
            cls.capped_at_one = cls.started(
                "capped", cls.call("SELECT claim_task($1)", (first,))
            )
            cls.capped_refusal = cls.refusal("SELECT claim_task($1)", (second,))

            cls.set_cap(2)
            cls.capped_at_two = cls.started(
                "capped", cls.call("SELECT claim_task($1)", (second,))
            )
        finally:
            cls.set_cap(cls.cap_before)
        cls.cap_after = cls.cap()

    @classmethod
    def cap(cls) -> int:
        """What the active weights row says the cross-role subagent cap is."""
        return int(
            cls.scalar(
                "SELECT max_concurrent_subagents FROM scheduler_weights WHERE active"
            )
        )

    @classmethod
    def set_cap(cls, subagent_cap: int) -> None:
        """The operator's move, which is the only place this number is set.

        A new version rather than an edit, since PH2-26: a weights row is what
        a recorded Ranking pass points at, so the trigger refuses an UPDATE of
        anything but `active`. Everything else about the row is carried over,
        which is what keeps this a change to the cap and not to the formula.
        """
        cls.operator(
            "SELECT version_scheduler_weights("
            " jsonb_build_object('max_concurrent_subagents', $1::smallint))",
            (str(subagent_cap),),
        )

    @classmethod
    def finding(cls, name: str, subject: str, status: str) -> str:
        """One Finding of the given status, with everything that status needs.

        A candidate needs a Hypothesis with a test spec, because that is what
        `validate.no_test_spec` asks for. A validated one needs all of that and
        a run of the spec as well: `findings` refuses `validated` without the
        `test_runs` row, which is Q27 in the schema -- validated means the
        runtime re-ran it.
        """
        program_id = cls.identifiers[name]
        hypothesis = cls.hypothesis(name, subject, "worth judging")
        test = str(
            cls.scalar(
                "INSERT INTO tests (program_id, hypothesis_id, spec, spec_sha256)"
                " VALUES ($1::uuid, $2::uuid, '{}'::jsonb,"
                "         encode(sha256('{}'::bytea), 'hex')) RETURNING id::text",
                (program_id, hypothesis),
            )
        )
        run = None
        if status == "validated":
            run = str(
                cls.scalar(
                    "INSERT INTO test_runs (program_id, test_id, lane, outcome,"
                    " assertion_results)"
                    " VALUES ($1::uuid, $2::uuid, 'replay', 'holds', '[]'::jsonb)"
                    " RETURNING id::text",
                    (program_id, test),
                )
            )
        finding = str(
            cls.scalar(
                "INSERT INTO findings (program_id, subject_entity_id, class_id, title,"
                " severity, status, validated_by_test_run_id)"
                " VALUES ($1::uuid, $2::uuid, $3, 'a seeded finding', 'medium', $4,"
                " $5::uuid) RETURNING id::text",
                (program_id, subject, FINDING_CLASS, status, run),
            )
        )
        cls.as_owner(
            "INSERT INTO finding_hypotheses (finding_id, hypothesis_id)"
            " VALUES ($1::uuid, $2::uuid)",
            (finding, hypothesis),
        )
        return finding

    # -- criterion 1: the same rows and weights reach the same order -----------

    def test_two_passes_over_the_same_rows_offer_the_same_order(self):
        self.assertEqual(
            [(row["ordinal"], row["task_label"]) for row in self.first],
            [(row["ordinal"], row["task_label"]) for row in self.again],
        )

    def test_two_passes_over_the_same_rows_reach_the_same_numbers(self):
        # The order alone would survive a rank that drifted with the clock as
        # long as it drifted monotonically, so the values are compared too.
        self.assertEqual(
            [(row["priority"], row["factors"]) for row in self.first],
            [(row["priority"], row["factors"]) for row in self.again],
        )

    def test_the_only_thing_the_second_pass_moved_is_the_expiry(self):
        # And the expiry is not a rank value: it is when this offer stops being
        # one, which is the single reading of the clock an offer is allowed.
        self.assertNotEqual(
            self.first[0]["expires_at"], self.again[0]["expires_at"]
        )
        self.assertTrue(self.expiry_is_the_ttl)

    # -- criterion 2: what the offered slate contains --------------------------

    def test_the_slate_is_capped_and_ordinal_from_one(self):
        self.assertEqual(5, len(self.first))
        self.assertEqual([1, 2, 3, 4, 5], [row["ordinal"] for row in self.first])

    def test_the_slate_holds_the_five_worth_most_and_drops_the_sixth(self):
        # Seeded ascending, so the offer should be the reverse, less the least.
        self.assertEqual(
            list(reversed(self.ranked))[:5], [row["task_label"] for row in self.first]
        )
        self.assertNotIn(self.ranked[0], [row["task_label"] for row in self.first])

    def test_every_entry_breaks_its_priority_into_factors(self):
        for row in self.first:
            self.assertEqual(
                {
                    "novelty",
                    "confidence",
                    "gain",
                    "impact",
                    "value",
                    "cost",
                    "time",
                    "safety",
                    "unlock",
                    "weights_version",
                },
                set(json.loads(str(row["factors"]))),
            )

    def test_the_whole_slate_shares_one_expiry(self):
        self.assertEqual(1, len({row["expires_at"] for row in self.first}))

    def test_only_what_the_lane_has_room_for_is_entitled(self):
        # The recon Lane's floor is one slot and its role admits one at a time,
        # so exactly the top entry is what the Lane is currently short of.
        self.assertEqual(
            [True, False, False, False, False], [row["entitled"] for row in self.first]
        )

    def test_a_full_lane_offers_nothing(self):
        self.assertEqual((), self.lane_full)

    def test_an_unaffordable_task_is_not_offered(self):
        self.assertEqual(3, len(self.offered_spent))
        self.assertEqual((), self.offer_when_poor)

    def test_a_task_whose_identity_is_held_is_not_offered(self):
        self.assertEqual(1, len(self.offered_held))
        self.assertEqual((), self.offer_while_held)

    # -- criterion 3: the claim rechecks rather than trusting the snapshot -----

    def test_a_task_that_ran_out_of_attempts_is_refused_after_being_offered(self):
        self.assertIn(f"task {self.top} is no longer claimable", self.exhausted)
        self.assertIn("attempts_exhausted", self.exhausted)

    def test_a_task_the_budget_no_longer_covers_is_refused_after_being_offered(self):
        self.assertEqual(60000, self.needed)
        self.assertEqual(100000, self.left_before)
        self.assertEqual(50000, self.left_after)
        self.assertIn("is no longer claimable: unaffordable", self.unaffordable)

    def test_a_task_whose_identity_was_leased_is_refused_after_being_offered(self):
        self.assertIn("is no longer claimable: identity_held", self.identity_held)

    # -- criterion 4: refused whole, or not at all -----------------------------

    def test_a_task_that_was_never_offered_is_refused(self):
        self.assertIn("task T99 is not on the current slate", self.off_slate)
        self.assertIn("task T99 is not on the current slate", self.off_slate_pick)

    def test_another_programs_task_is_refused_even_though_the_label_exists(self):
        # Labels are counted per Program, so `T6` names a live Task of the
        # onlooker and nothing at all in the Program doing the asking. A claim
        # that read labels without their Program would have found one.
        self.assertEqual(
            1,
            int(
                self.scalar(
                    "SELECT count(*) FROM tasks"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (self.identifiers["onlooker"], self.elsewhere),
                )
            ),
        )
        self.assertEqual(
            0,
            int(
                self.scalar(
                    "SELECT count(*) FROM tasks"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (self.identifiers["refused"], self.elsewhere),
                )
            ),
        )
        self.assertIn(
            f"task {self.elsewhere} is not on the current slate", self.cross_program
        )

    def test_an_expired_slate_is_refused_by_its_age_and_not_by_its_contents(self):
        self.assertEqual(3, len(self.offered_refused))
        self.assertIn("expired after 00:05:00", self.expired)

    def test_a_choice_whose_entry_is_gone_is_refused(self):
        self.assertIn(
            "the choice recorded for this program is no longer on the slate",
            self.stale_pick,
        )

    def test_none_of_the_refusals_claimed_anything(self):
        self.assertEqual((0, 0), self.untouched)
        self.assertEqual((0, 0), self.stale_counts)

    def test_a_recheck_that_refuses_leaves_the_task_and_the_run_log_alone(self):
        # The other half of criterion 4, asked of the three refusals that come
        # from the recheck rather than from the slate: a claim refused at the
        # last condition is as whole a refusal as one refused at the first. The
        # run counts are the runs the fixtures opened, not runs a claim left.
        self.assertEqual((0, 0), self.after_exhausted)
        self.assertEqual((0, 1), self.after_unaffordable)
        self.assertEqual((0, 1), self.after_identity_held)

    # -- criterion 5: choosing, and not choosing -------------------------------

    def test_a_recorded_choice_is_the_task_the_claim_takes(self):
        self.assertEqual(self.chosen, self.pick_echo)
        self.assertEqual(self.chosen, self.picked_task)
        self.assertEqual(0, self.picks_left)

    def test_choosing_nothing_falls_through_to_the_first_entry_that_survives(self):
        self.assertEqual(self.second, self.fallback_task)

    # -- criterion 6: one winner, and a complete account of it -----------------

    def test_four_claims_at_once_produce_exactly_one_run(self):
        claimed = [
            outcome
            for outcome in self.outcomes
            if outcome is not None and not outcome.startswith("refused")
        ]

        self.assertEqual(SLATE_CONTENDERS, len(self.outcomes))
        self.assertEqual(1, len(claimed))
        self.assertEqual((1, 1), self.contended_counts)

    def test_the_losers_come_back_empty_rather_than_refused(self):
        # An empty slate is what a Program with a full Lane has, and asking for
        # nothing off one is not an error. A raise here would make three of four
        # orchestrators handle an exception on the ordinary path.
        self.assertEqual(
            [None] * (SLATE_CONTENDERS - 1),
            [outcome for outcome in self.outcomes if outcome is None],
        )

    def test_the_event_log_accounts_for_the_row_the_race_moved(self):
        self.assertEqual([], self.contended_integrity)

    # -- the model and effort the claim opens a run at (PH2-71) ----------------

    def test_every_kind_opens_its_run_at_the_rosters_model_and_effort(self):
        # Criterion 3, and the whole of what the ticket moved: the claim reads
        # the role's model and effort off `roles` instead of deciding them from
        # `runs_as`. Asserted against the roster row rather than against five
        # literals, so a future roster edit the scheduler does not follow fails
        # here without this file being touched. The kinds are asserted first,
        # because two comprehensions over one dict agree with each other however
        # few claims are in it.
        self.assertEqual(set(SLATE_KINDS), set(self.claimed_runs))
        self.assertEqual(
            {kind: (row["roster_model"], row["roster_effort"])
             for kind, row in self.claimed_runs.items()},
            {kind: (row["model"], row["effort"])
             for kind, row in self.claimed_runs.items()},
        )

    def test_the_kinds_do_not_all_run_at_one_effort(self):
        # The guard on the assertion above. Four of the five kinds ran at
        # `high` before this ticket, and a roster that gave every role the same
        # effort would make agreeing with it prove nothing. The literals are
        # deliberate: agreement is what the test above asks, and this one asks
        # what the roster says, which is not something it can read off the row
        # it is checking.
        self.assertEqual(
            {"recon": "medium", "hunt": "high", "analyze": "high",
             "validate": "max", "report": "none"},
            {kind: row["effort"] for kind, row in self.claimed_runs.items()},
        )

    def test_the_run_the_renderer_opens_carries_no_model(self):
        # `agent_runs_renderer_has_no_model` is the column-level half; this is
        # the claim actually satisfying it off a roster row rather than off the
        # branch that used to spell `'none'` here.
        self.assertEqual(
            ("reporter", "none", "none"),
            (self.claimed_runs["report"]["role"],
             self.claimed_runs["report"]["model"],
             self.claimed_runs["report"]["effort"]),
        )

    def test_no_run_was_opened_at_a_resolved_model_identifier(self):
        # The alias is what `_launch.options_for` hands the SDK, so the alias is
        # what the run row records. A resolution -- what one measured SDK/CLI
        # pair turns `opus` into -- belongs to the version-bound manifest, and a
        # copy of it here would go stale without moving.
        self.assertEqual(
            [], [kind for kind, row in self.claimed_runs.items()
                 if str(row["model"]).startswith("claude-")]
        )

    # -- the one cross-role subagent cap (PH2-73) -------------------------------

    def test_the_claim_carries_the_weights_rows_cap_into_the_run(self):
        # Criterion 1, read back through `execution.STARTED`: the number the
        # runtime hands the child is the one the claim ran against, and it
        # moves when the row moves rather than when a constant is edited.
        self.assertEqual(
            (1, 2),
            (self.capped_at_one.subagent_cap, self.capped_at_two.subagent_cap),
        )

    def test_a_lowered_cap_refuses_the_claim_a_raised_one_admits(self):
        # The scheduler half of criterion 2, off one slate: the same Task, the
        # same lane and the same budget, refused and then taken with nothing
        # changed but the weights row. `web_hunter` is a subagent role, so the
        # refusal is the cap and not the lane -- the lane admits two.
        self.assertIn("global_subagent_cap", self.capped_refusal)
        self.assertEqual(
            ("hunt", "web_hunter"), (self.capped_at_two.kind, self.capped_at_two.role)
        )

    def test_the_gate_refuses_at_the_cap_the_claim_was_admitted_under(self):
        # The runtime half of the same criterion, and the seam the ticket
        # closes: the gate is built from what the claim read, so both numbers
        # here came out of one row that this fixture moved once.
        for claimed in (self.capped_at_one, self.capped_at_two):
            with self.subTest(subagent_cap=claimed.subagent_cap):
                gate = roster.Gate("orchestrator", claimed.subagent_cap)
                # Alternating targets, because both roles run two at a time:
                # every delegation here is inside its own role's ceiling, so
                # the session's cap is the only thing that can refuse one.
                delegations = [
                    roster.Call(
                        tool=roster.DELEGATION,
                        arguments={
                            roster.SUBAGENT_TYPE:
                                "web_hunter" if index % 2 == 0 else "js_analyst"
                        },
                        ticket=f"t{index}",
                    )
                    for index in range(claimed.subagent_cap + 1)
                ]

                for admitted in delegations[:-1]:
                    self.assertIsNone(gate.decide(admitted))
                denial = gate.decide(delegations[-1])

                self.assertIsNotNone(denial, "the gate admitted one past its cap")
                self.assertEqual(roster.OVERFLOW, denial.rule)
                self.assertIn("this session", denial.reason)
                self.assertIn(str(claimed.subagent_cap), denial.reason)

    def test_the_weights_row_is_back_where_this_fixture_found_it(self):
        # The active `scheduler_weights` row is global, so a scenario that moved
        # it and did not put it back would schedule every case after this one --
        # in this file and in every other -- under a cap this fixture chose.
        # The version number is not restored and is not meant to be: PH2-26 says
        # a change is a new version, so putting the cap back is one more of them.
        self.assertEqual(self.cap_before, self.cap_after)

    # -- the invariant ---------------------------------------------------------

    def test_the_standing_checks_are_registered_and_hold(self):
        for name in ("slate_claim", "roster_model_and_effort", "subagent_cap"):
            with self.subTest(check=name):
                [registered] = self.connection.execute(
                    "SELECT count(*) FROM standing_checks WHERE name = $1", (name,)
                ).rows
                [[problems, detail]] = self.connection.execute(
                    "SELECT problems, detail FROM run_standing_checks() WHERE name = $1",
                    (name,),
                ).rows

                self.assertEqual(1, int(registered[0]))
                self.assertEqual((0, ""), (int(problems), str(detail)))


#: The Programs of the reservation case. One per scenario for the reason the
#: slate case has one per scenario: capacity is a Program's own, and two
#: scenarios sharing a Program would be one scenario about whichever ceiling
#: happened to bind first.
BUDGET_SLUG = "selftest-budget"

#: Wide enough that nothing refuses for capacity. `run_tokens` is 60000, which
#: is what a recon Task's 0.30 prior costs against the 200000-token reference:
#: the worst case a claim holds and the estimate that made it affordable are
#: then the same number, so a reservation written at anything other than the
#: configured ceiling is visible as one.
BUDGET_WIDE = budgets(
    requests=500, tokens=2000000, run_tokens=60000, run_requests=10,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: A total that admits exactly one claim: 150000 held out of 200000 leaves
#: 50000, and the next claim would have to promise 150000 again. The total is
#: still over the 60000 a recon estimate needs, so `unaffordable` -- which asks
#: only about what has been spent -- says yes, and what refuses is the arm that
#: counts the claim already in flight.
BUDGET_CAPPED = budgets(
    requests=500, tokens=200000, run_tokens=150000, run_requests=10,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: A Program whose whole engagement is ten requests and whose per-run ceiling
#: is the same ten. Coherent on its own -- one run may spend everything, which
#: is a policy and not a contradiction -- and exhausted the moment one claim
#: promises its worst case, so the second Task is refused for requests nobody
#: has sent yet.
BUDGET_METERED = budgets(
    requests=10, tokens=2000000, run_tokens=60000, run_requests=10,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=5,
    window_seconds=3600,
)

#: A Lane ceiling that admits one claim while the Program's total admits many,
#: so what the second Task of that kind is refused for is the Lane and the
#: Task of another kind beside it stays claimable.
BUDGET_LANED = budgets(
    requests=500, tokens=2000000, run_tokens=60000, run_requests=10,
    lane_tokens=100000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: The race's Program: 400000 total against a 250000 worst case, so a second
#: claim cannot fit however the four interleave. Its Tasks are hunts because
#: the hunt Lane admits two at once and the recon Lane admits one -- a race
#: that concurrency decides would prove nothing about capacity.
BUDGET_TIGHT = budgets(
    requests=500, tokens=400000, run_tokens=250000, run_requests=10,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: One request per run at a door whose rate, concurrency and total are wide, so
#: what refuses the second request is the run's own ceiling and nothing else.
BUDGET_DOOR = budgets(
    requests=500, tokens=2000000, run_tokens=60000, run_requests=1,
    lane_tokens=1000000, lane_requests=500, concurrency=4, burst=500,
    window_seconds=3600,
)

#: How many orchestrators race for a capacity that admits one of them.
BUDGET_CONTENDERS = 4

#: What the happy path's run turns out to have cost, and what its reservation
#: is therefore settled against. Far under the 60000 it promised, which is the
#: point: the difference is what comes back to the pool.
BUDGET_SPENT = (5000, 1000)


class BudgetReservationTest(SchedulerFixture, DatabaseCase):
    """PH2-25: capacity is reserved before a Task runs and reconciled after.

    A budget that is only checked is a budget four simultaneous claims walk
    past, so what this case asks is not "was the ceiling read" but "was it held
    out of the pool while the run that promised it was in flight". Only a server
    can answer that: the question is about two claims that overlap in time and
    about rows that survive the process which wrote them.

    Each Program is one scenario, and each is disturbed in exactly one way -- a
    total that admits one claim, an engagement whose requests are fewer than one
    run may send, a Lane that fills while the Program has room, four
    orchestrators at once, a run that ends five different ways, a door that has
    already sent the one request its run was admitted for.

    Everything runs in `setUpClass` because all of it commits, and because the
    refusals only mean anything against the state the claims before them left.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)
        # The door is the one caller entitled to reserve egress, so the arm
        # that refuses a run past its request ceiling can only be asked as the
        # role that holds it. A runtime session asking would be testing a grant
        # that ticket 13 revoked.
        cls.door_connection = pg.connect(cls.harness.proxy)

        cls.identifiers = {}
        for name, limits in (
            ("reserved", BUDGET_WIDE),
            ("endings", BUDGET_WIDE),
            ("capped", BUDGET_CAPPED),
            ("metered", BUDGET_METERED),
            ("laned", BUDGET_LANED),
            ("contended", BUDGET_TIGHT),
            ("door", BUDGET_DOOR),
        ):
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, limits).replace(
                    'name = "matrix-web"', f'name = "{BUDGET_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.identifiers[name] = opened.facts["program_id"]

        cls.arrange_reserved()
        cls.arrange_endings()
        cls.arrange_capped()
        cls.arrange_metered()
        cls.arrange_laned()
        cls.arrange_contended()
        cls.arrange_door()

    @classmethod
    def tearDownClass(cls):
        cls.door_connection.close()
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{BUDGET_SLUG}-%",)
            )
        super().tearDownClass()

    # -- the scenarios ---------------------------------------------------------

    @classmethod
    def arrange_reserved(cls):
        """One claim holds its worst case; closing gives back what it cost."""
        cls.seed("reserved", 3)
        cls.bind("reserved")
        cls.offer()
        cls.free_before = cls.capacity("reserved")
        cls.reserved_run = str(cls.call("SELECT claim_task()"))
        cls.held = cls.reservation("reserved", cls.reserved_run)
        cls.free_while_held = cls.capacity("reserved")
        cls.lane_while_held = cls.lane("reserved", "recon")
        cls.other_lane_while_held = cls.lane("reserved", "hunt")
        # Read back through the runtime's own query, because what the child is
        # told it may spend has to be the number the claim ran against.
        cls.carried = cls.started("reserved", cls.reserved_run)
        cls.settled = cls.close("reserved", cls.reserved_run, "completed", *BUDGET_SPENT)
        cls.free_after = cls.capacity("reserved")

    @classmethod
    def arrange_endings(cls):
        """Four runs, four ways of ending, and the reservation after each.

        Success is the scenario above. These are the other four the ticket
        names, and the last of them ends without anybody closing it: the lease
        lapses and `resume_program` finds the run, which is what a crash leaves
        behind and the one path no `finish_task_attempt` runs on.
        """
        cls.seed("endings", 4)
        cls.bind("endings")
        cls.offer()
        cls.ended = {}
        for stop in ("refusal", "error", "aborted"):
            label = str(cls.call("SELECT claim_task()"))
            cls.ended[stop] = cls.close("endings", label, stop)

        crashed = str(cls.call("SELECT claim_task()"))
        cls.crash_held = cls.reservation("endings", crashed)
        cls.as_owner(
            "UPDATE tasks SET lease_expires_at = now() - interval '1 hour'"
            " WHERE program_id = $1::uuid AND status IN ('claimed','running')",
            (cls.identifiers["endings"],),
        )
        cls.call("SELECT resume_program($1::uuid)", (cls.identifiers["endings"],))
        cls.ended["crash"] = cls.reservation("endings", crashed)
        cls.endings_capacity = cls.capacity("endings")

    @classmethod
    def arrange_capped(cls):
        """The second claim would promise past the total the first one left."""
        labels = cls.seed("capped", 2)
        cls.bind("capped")
        cls.offer()
        cls.capped_run = str(cls.call("SELECT claim_task()"))
        taken = cls.claimed_by("capped", cls.capped_run)
        [cls.capped_left] = [label for label in labels if label != taken]
        cls.capped_reason = cls.claimable("capped", cls.capped_left)
        # Named rather than left to the walk, so the refusal is about this Task
        # and not about a slate that ran out of entries.
        cls.capped_refusal = cls.refusal("SELECT claim_task($1)", (cls.capped_left,))
        cls.capped_counts = cls.counted("capped")
        cls.capped_capacity = cls.capacity("capped")

    @classmethod
    def arrange_metered(cls):
        """One claim's promise is the whole engagement's requests.

        The request side of `arrange_capped`, and it has to be its own Program
        for the same reason: a total that binds first would refuse this Task
        for tokens and prove nothing about requests.
        """
        labels = cls.seed("metered", 2)
        cls.bind("metered")
        cls.offer()
        cls.metered_run = str(cls.call("SELECT claim_task()"))
        taken = cls.claimed_by("metered", cls.metered_run)
        [cls.metered_left] = [label for label in labels if label != taken]
        cls.metered_reason = cls.claimable("metered", cls.metered_left)
        cls.metered_refusal = cls.refusal("SELECT claim_task($1)", (cls.metered_left,))
        # Re-offered after the claim, because the slate and the claim have to
        # refuse the same Task for the same reason: a Task the slate still
        # offers is one an orchestrator would keep trying.
        cls.metered_slate = cls.offer()
        cls.metered_counts = cls.counted("metered")
        cls.metered_capacity = cls.capacity("metered")

    @classmethod
    def arrange_laned(cls):
        """One Lane fills while the Program it belongs to has room to spare."""
        labels = cls.seed("laned", 3)
        cls.hunts("laned", labels[2:])
        cls.bind("laned")
        cls.offer()
        cls.laned_run = str(cls.call("SELECT claim_task($1)", (labels[0],)))
        cls.laned_reason = cls.claimable("laned", labels[1])
        cls.laned_other_lane = cls.claimable("laned", labels[2])
        cls.laned_recon = cls.lane("laned", "recon")
        cls.laned_hunt = cls.lane("laned", "hunt")
        cls.laned_capacity = cls.capacity("laned")

    @classmethod
    def arrange_contended(cls):
        """Four orchestrators claim at once against room for one of them."""
        cls.hunts("contended", cls.seed("contended", BUDGET_CONTENDERS))
        cls.bind("contended")
        cls.offer()

        gate = threading.Barrier(BUDGET_CONTENDERS)
        guard = threading.Lock()
        cls.outcomes: list[str | None] = []
        contenders = [
            threading.Thread(target=cls.contend, args=("contended", gate, guard))
            for _ in range(BUDGET_CONTENDERS)
        ]
        for contender in contenders:
            contender.start()
        for contender in contenders:
            contender.join()

        cls.contended_capacity = cls.capacity("contended")
        cls.contended_reserved = int(
            cls.scalar(
                "SELECT count(*) FROM budget_reservations"
                " WHERE program_id = $1::uuid AND settled_at IS NULL",
                (cls.identifiers["contended"],),
            )
        )
        cls.contended_counts = cls.counted("contended")
        # The Lane the losers could still have been admitted into. Read after
        # the race, because a headroom of zero would mean concurrency decided
        # this and the capacity arm was never reached.
        cls.contended_headroom = int(
            cls.scalar(
                "SELECT headroom FROM scheduler_lane_state"
                " WHERE program_id = $1::uuid AND kind = 'hunt'",
                (cls.identifiers["contended"],),
            )
        )
        cls.contended_reason = str(
            cls.scalar(
                "SELECT claimable_for(t, w) FROM tasks t CROSS JOIN scheduler_weights w"
                " WHERE w.active AND t.program_id = $1::uuid AND t.status = 'pending'"
                " LIMIT 1",
                (cls.identifiers["contended"],),
            )
        )

    @classmethod
    def arrange_door(cls):
        """A run admitted for one request, at a door it asks twice."""
        cls.seed("door", 1)
        cls.bind("door")
        cls.offer()
        cls.door_run = str(cls.call("SELECT claim_task()"))
        run = cls.run_id("door", cls.door_run)
        task = str(
            cls.scalar(
                "SELECT task_id::text FROM agent_runs WHERE id = $1::uuid", (run,)
            )
        )
        # The Tool run carries the Task the run was claimed against, which is
        # what `authorize_tool_run` requires of a run that has one: a Tool call
        # made under a claimed Task and not naming it is not an active call.
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            tool_run = str(
                cls.runtime.execute(
                    "INSERT INTO tool_runs (program_id, agent_run_id, task_id, tool,"
                    " args, status, transport) VALUES ($1::uuid, $2::uuid, $3::uuid,"
                    " $4, $5::jsonb, 'running', 'runtime') RETURNING id::text",
                    (
                        cls.identifiers["door"],
                        run,
                        task,
                        proxy.TOOL,
                        json.dumps({"url": URL, "method": "GET", "identity_slot": ""}),
                    ),
                ).scalar()
            )
        gate = cls.runtime.execute(proxy.AUTHORIZE_TOOL_RUN, (tool_run,)).scalar()
        answer = proxy.as_object(gate)
        capability = answer.get("capability")
        assert capability, answer

        cls.door_connection.execute(proxy.BIND, (cls.identifiers["door"],))
        cls.first_request = cls.through_the_door(str(capability))
        cls.second_request = cls.through_the_door(str(capability))
        cls.door_event = cls.as_owner(
            "SELECT payload FROM events WHERE program_id = $1::uuid"
            " AND type = 'egress.budget_exhausted' ORDER BY seq DESC LIMIT 1",
            (cls.identifiers["door"],),
        ).dicts()
        # Read with the run still open and one of its requests already sent,
        # which is the only moment the promise and the spend overlap.
        cls.door_capacity = cls.capacity("door")
        cls.door_settled = cls.close("door", cls.door_run, "completed", 100, 20)

    # -- what the scenarios are built out of -----------------------------------

    @classmethod
    def hunts(cls, name: str, labels: list[str]) -> None:
        """Turn seeded Tasks into hunts, each ready with a Hypothesis under it.

        Converted rather than seeded as hunts, because `seed` writes one
        application per call and a Program that seeded twice would write the
        same deduplication cell twice.
        """
        for label in labels:
            subject = str(
                cls.scalar(
                    "SELECT subject_entity_id::text FROM tasks"
                    " WHERE program_id = $1::uuid AND label = $2",
                    (cls.identifiers[name], label),
                )
            )
            cls.as_owner(
                "UPDATE tasks SET kind = 'hunt', hypothesis_id = $3::uuid"
                " WHERE program_id = $1::uuid AND label = $2",
                (
                    cls.identifiers[name],
                    label,
                    cls.hypothesis(name, subject, "worth hunting"),
                ),
            )

    @classmethod
    def capacity(cls, name: str) -> dict[str, object]:
        """What one Program may still promise, as the admission arm reads it."""
        return cls.as_owner(
            "SELECT * FROM program_capacity WHERE program_id = $1::uuid",
            (cls.identifiers[name],),
        ).dicts()[0]

    @classmethod
    def lane(cls, name: str, kind: str) -> dict[str, object]:
        """The same question about one Lane of it."""
        return cls.as_owner(
            "SELECT * FROM lane_budget WHERE program_id = $1::uuid AND kind = $2",
            (cls.identifiers[name], kind),
        ).dicts()[0]

    @classmethod
    def reservation(cls, name: str, label: str) -> dict[str, object] | None:
        """What one Agent run has promised, or None if it never promised."""
        rows = cls.as_owner(
            "SELECT br.* FROM budget_reservations br"
            "  JOIN agent_runs ar ON ar.id = br.agent_run_id"
            " WHERE ar.program_id = $1::uuid AND ar.label = $2",
            (cls.identifiers[name], label),
        ).dicts()
        return rows[0] if rows else None

    @classmethod
    def run_id(cls, name: str, label: str) -> str:
        """The identifier behind a run label, which is what the verbs take."""
        return str(
            cls.scalar(
                "SELECT id::text FROM agent_runs"
                " WHERE program_id = $1::uuid AND label = $2",
                (cls.identifiers[name], label),
            )
        )

    @classmethod
    def close(
        cls,
        name: str,
        label: str,
        stop: str = "completed",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> dict[str, object] | None:
        """End one run the way the runtime ends it, and read what it settled.

        `execution.FINISH` rather than a statement written here: the parameters
        the reconciliation depends on are the ones production sends, and a
        second spelling of them would pass while production's did not.
        """
        cls.bind(name)
        cls.call(execution.FINISH, (cls.run_id(name, label), stop, input_tokens,
                                    output_tokens))
        return cls.reservation(name, label)

    @classmethod
    def through_the_door(cls, capability: str) -> dict[str, object]:
        """One request at the egress door, as the role that holds it."""
        with cls.door_connection.transaction():
            return cls.door_connection.execute(
                "SELECT granted, reason, retry_at FROM"
                " reserve_egress_slot($1, 'http', $2, 80, $3, $3)",
                (capability, HOST, PATH),
            ).dicts()[0]

    # -- criterion 1: the configuration states the ceilings --------------------

    def test_the_program_carries_every_ceiling_its_configuration_stated(self):
        [row] = self.as_owner(
            "SELECT token_budget, run_token_budget, run_request_budget,"
            " lane_token_budget, lane_request_budget FROM programs WHERE id = $1::uuid",
            (self.identifiers["reserved"],),
        ).rows
        self.assertEqual(
            (2000000, 60000, 10, 1000000, 500), tuple(int(value) for value in row)
        )

    def test_the_concurrency_and_request_limits_are_the_compiled_scope_versions(self):
        # The other half of the same sentence, and it lands somewhere else: a
        # request ceiling is per scope version because it is spent against a
        # scope, while a token ceiling is the Program's own.
        [row] = self.as_owner(
            "SELECT sv.budget_requests, sv.budget_concurrency"
            "  FROM program_scope_versions sv JOIN programs p"
            "    ON p.id = sv.program_id AND p.scope_version = sv.version"
            " WHERE p.id = $1::uuid",
            (self.identifiers["reserved"],),
        ).rows
        self.assertEqual((500, 4), tuple(int(value) for value in row))
        self.assertEqual(500, int(self.free_before["request_budget"]))

    def test_no_program_here_disagrees_with_the_document_it_was_opened_from(self):
        # `check_program_configuration` compares every ceiling on the row with
        # the configuration it was written from, so a column this ticket added
        # and forgot to write is a problem here rather than a silent zero.
        problems = self.connection.execute(
            "SELECT problem, object, detail FROM check_program_configuration()"
        ).rows
        self.assertEqual([], [tuple(str(field) for field in row) for row in problems])

    def test_ceilings_that_cannot_all_be_true_are_reported_against_the_program(self):
        # The Control for the assertion above, which would pass just as well
        # against a check that never reports anything. A per-run ceiling over
        # the campaign's total is a Program whose every claim promises more
        # than there is, and it has to be named as a configuration problem
        # rather than left to look like an exhausted budget.
        found = []
        try:
            with self.connection.transaction():
                self.connection.execute("SET LOCAL ROLE rk2_owner")
                self.connection.execute("SELECT set_actor('runtime', 'selftest')")
                self.connection.execute(
                    "UPDATE programs SET run_token_budget = token_budget + 1"
                    " WHERE id = $1::uuid",
                    (self.identifiers["door"],),
                )
                found.extend(
                    self.connection.execute(
                        "SELECT object FROM check_program_configuration()"
                        " WHERE problem = 'configuration_ceilings_disagree'"
                    ).rows
                )
                raise Rollback
        except Rollback:
            pass

        self.assertEqual([f"{BUDGET_SLUG}-door"], [str(row[0]) for row in found])

    # -- criterion 2: the claim reserves the worst case ------------------------

    def test_the_claim_writes_one_reservation_for_the_run_it_opened(self):
        self.assertIsNotNone(self.held)
        self.assertEqual("recon", str(self.held["kind"]))
        self.assertIsNone(self.held["settled_at"])
        self.assertIsNone(self.held["tokens_spent"])
        self.assertEqual(
            self.identifiers["reserved"], str(self.held["program_id"])
        )

    def test_the_reservation_is_the_configured_worst_case_and_not_the_estimate(self):
        self.assertEqual(60000, int(self.held["tokens"]))
        self.assertEqual(10, int(self.held["requests"]))

    def test_the_capacity_the_next_claim_reads_is_short_by_what_this_one_promised(self):
        self.assertEqual(0, int(self.free_before["tokens_reserved"]))
        self.assertEqual(60000, int(self.free_while_held["tokens_reserved"]))
        self.assertEqual(
            int(self.free_before["tokens_free"]) - 60000,
            int(self.free_while_held["tokens_free"]),
        )
        self.assertEqual(10, int(self.free_while_held["requests_reserved"]))

    def test_the_lane_the_task_belongs_to_is_the_only_one_that_moved(self):
        self.assertEqual(60000, int(self.lane_while_held["tokens_reserved"]))
        self.assertEqual(0, int(self.other_lane_while_held["tokens_reserved"]))

    def test_the_runtime_carries_the_reserved_ceiling_into_the_child(self):
        # Read through `execution.STARTED`, so what is asserted is the number
        # the launcher will stop the model at and not a column that exists.
        self.assertEqual(60000, self.carried.token_cap)

    # -- criterion 3: concurrent claims cannot promise past the ceiling --------

    def test_four_claims_at_once_reserve_once_against_room_for_one(self):
        self.assertEqual(BUDGET_CONTENDERS, len(self.outcomes))
        self.assertEqual(1, len([taken for taken in self.outcomes if taken]))
        self.assertEqual(1, self.contended_reserved)
        self.assertEqual((1, 1), self.contended_counts)

    def test_the_race_left_no_more_promised_than_the_program_may_spend(self):
        self.assertEqual(250000, int(self.contended_capacity["tokens_reserved"]))
        self.assertLessEqual(
            int(self.contended_capacity["tokens_reserved"]),
            int(self.contended_capacity["token_budget"]),
        )
        self.assertEqual(150000, int(self.contended_capacity["tokens_free"]))

    def test_the_losers_were_refused_by_capacity_and_not_by_the_lane(self):
        # The hunt Lane admits two at once and one is running, so a claim
        # refused here was refused for what it would have promised.
        self.assertGreater(self.contended_headroom, 0)
        self.assertEqual("program_tokens_reserved", self.contended_reason)

    def test_the_losers_come_back_empty_rather_than_refused(self):
        self.assertEqual(
            [None] * (BUDGET_CONTENDERS - 1),
            [taken for taken in self.outcomes if not taken],
        )

    # -- criterion 4: every ending reconciles what it promised -----------------

    def test_a_run_that_completes_settles_against_what_it_actually_spent(self):
        self.assertIsNotNone(self.settled["settled_at"])
        self.assertEqual(sum(BUDGET_SPENT), int(self.settled["tokens_spent"]))
        self.assertEqual(0, int(self.settled["requests_spent"]))

    def test_what_the_run_did_not_spend_goes_back_to_the_pool(self):
        self.assertEqual(0, int(self.free_after["tokens_reserved"]))
        self.assertEqual(sum(BUDGET_SPENT), int(self.free_after["tokens_spent"]))
        self.assertEqual(
            int(self.free_before["tokens_free"]) - sum(BUDGET_SPENT),
            int(self.free_after["tokens_free"]),
        )

    def test_a_refusal_and_an_error_settle_against_the_nothing_they_spent(self):
        # Both ended with a caller behind them that could say what they cost.
        # A refusal never reached the model and an error is the harness's own,
        # so nothing is what they report and nothing is what they are charged.
        for stop in ("refusal", "error"):
            with self.subTest(stop=stop):
                self.assertIsNotNone(self.ended[stop]["settled_at"])
                self.assertEqual(0, int(self.ended[stop]["tokens_spent"]))

    def test_a_run_that_left_no_account_of_itself_is_charged_what_it_promised(self):
        # The killed child. Its tokens were spent and died with it, and a
        # settlement at zero would give back capacity the model consumed.
        self.assertIsNotNone(self.ended["aborted"]["settled_at"])
        self.assertEqual(60000, int(self.ended["aborted"]["tokens_spent"]))

    def test_a_run_nobody_closed_settles_when_the_crash_is_recovered(self):
        # The one ending with no caller behind it. Its reservation was open
        # while the lease was live, which is what makes this a reconciliation
        # rather than a row that was never written. Charged like the abort
        # above, because it is the same ending arrived at from further away.
        self.assertIsNone(self.crash_held["settled_at"])
        self.assertIsNotNone(self.ended["crash"]["settled_at"])
        self.assertEqual(60000, int(self.ended["crash"]["tokens_spent"]))

    def test_what_an_unmeasured_run_was_charged_leaves_the_program_budget(self):
        # Charging the reservation and not the run would be a number in one
        # table nothing else reads: the Program's own spend has to move, or a
        # Program that loses every child is a Program that never runs out.
        self.assertEqual(120000, int(self.endings_capacity["tokens_spent"]))
        self.assertEqual(
            int(self.endings_capacity["token_budget"]) - 120000,
            int(self.endings_capacity["tokens_free"]),
        )

    def test_nothing_is_still_promised_once_every_run_has_ended(self):
        self.assertEqual(0, int(self.endings_capacity["tokens_reserved"]))
        self.assertEqual(0, int(self.endings_capacity["requests_reserved"]))

    def test_a_proxy_exchange_settles_against_the_requests_it_made(self):
        # The request side of the same reconciliation: the run promised one
        # request, sent one, and the settled row says so.
        self.assertEqual(1, int(self.door_settled["requests_spent"]))
        self.assertEqual(120, int(self.door_settled["tokens_spent"]))

    def test_a_request_in_flight_is_counted_once_and_not_twice(self):
        # The door counts a contact when it makes it, while the promise that
        # covered it is still open. Charging both would refuse the next claim
        # against capacity nobody holds, so what an open promise still holds is
        # what it has not yet sent.
        self.assertEqual(1, int(self.door_capacity["requests_spent"]))
        self.assertEqual(0, int(self.door_capacity["requests_reserved"]))
        self.assertEqual(
            int(self.door_capacity["request_budget"]) - 1,
            int(self.door_capacity["requests_free"]),
        )

    # -- criterion 5: exhausted capacity is a typed refusal --------------------

    def test_a_task_the_reserved_total_no_longer_covers_is_ineligible(self):
        self.assertEqual("program_tokens_reserved", self.capped_reason)
        self.assertIn("program_tokens_reserved", self.capped_refusal)

    def test_a_refused_claim_opened_no_run_and_promised_nothing(self):
        self.assertEqual((1, 1), self.capped_counts)
        self.assertEqual(150000, int(self.capped_capacity["tokens_reserved"]))

    def test_a_task_the_engagement_has_no_requests_left_to_promise_is_ineligible(self):
        self.assertEqual("program_requests_reserved", self.metered_reason)
        self.assertIn("program_requests_reserved", self.metered_refusal)
        self.assertEqual((1, 1), self.metered_counts)
        # And it is ineligible before it is offered, not after it is claimed:
        # the slate filters on the same answer the claim re-asks.
        self.assertEqual((), self.metered_slate)

    def test_the_requests_nobody_has_sent_yet_are_what_refused_it(self):
        # The whole engagement is promised while nothing has been spent, which
        # is the difference between this arm and the one 13 already had.
        self.assertEqual(10, int(self.metered_capacity["requests_reserved"]))
        self.assertEqual(0, int(self.metered_capacity["requests_spent"]))
        self.assertEqual(0, int(self.metered_capacity["requests_free"]))

    def test_a_lane_that_is_full_refuses_its_own_kind_and_no_other(self):
        self.assertEqual("lane_tokens_reserved", self.laned_reason)
        self.assertIsNone(self.laned_other_lane)

    def test_the_lane_that_refused_is_the_one_holding_the_reservation(self):
        self.assertEqual(60000, int(self.laned_recon["tokens_reserved"]))
        self.assertEqual(40000, int(self.laned_recon["tokens_free"]))
        self.assertEqual(100000, int(self.laned_hunt["tokens_free"]))
        # The Program itself has room for many more, which is what makes this
        # refusal the Lane's rather than the total's.
        self.assertGreater(int(self.laned_capacity["tokens_free"]), 60000)

    # -- criterion 6: the door's refusal is durable and bounded ----------------

    def test_the_one_request_the_run_was_admitted_for_is_granted(self):
        self.assertTrue(self.first_request["granted"])
        self.assertEqual("reserved", str(self.first_request["reason"]))

    def test_the_next_request_is_refused_by_the_ceiling_the_claim_reserved(self):
        self.assertFalse(self.second_request["granted"])
        self.assertEqual("run budget exhausted", str(self.second_request["reason"]))

    def test_an_exhausted_run_budget_is_refused_without_a_time_to_retry(self):
        # Exhaustion is not a wait. A retry time here would be this door
        # promising the run gets more, and a caller that read one would come
        # back around a loop it can never leave.
        self.assertIsNone(self.second_request["retry_at"])

    def test_the_refusal_is_recorded_with_the_limit_that_caused_it(self):
        [event] = self.door_event
        payload = json.loads(str(event["payload"]))
        self.assertEqual("run_requests", payload["limit"])
        self.assertEqual(1, int(payload["requests"]))
        self.assertEqual(1, int(payload["contacted"]))

    # -- the invariant ---------------------------------------------------------

    def test_the_standing_check_is_registered_and_holds(self):
        [registered] = self.connection.execute(
            "SELECT count(*) FROM standing_checks WHERE name = $1",
            ("budget_reservations",),
        ).rows
        [[problems, detail]] = self.connection.execute(
            "SELECT problems, detail FROM run_standing_checks() WHERE name = $1",
            ("budget_reservations",),
        ).rows

        self.assertEqual(1, int(registered[0]))
        self.assertEqual((0, ""), (int(problems), str(detail)))


#: The Programs of `TaskRankingTest`, sharing a prefix so one DELETE retires them.
RANK_SLUG = "selftest-rank"

#: What the three analyze Tasks in the unlock scenarios each promise. Low enough
#: that all three together stay under the 1.0 cap: at 0.9 each the sum saturated
#: at two of them, and "unblocks several paths" was indistinguishable from
#: "unblocks one". Still high enough that the three together outweigh the richer
#: recon Task -- 0.1 + 0.5*0.6 against 0.2 -- so the flip is the unlock term's.
UNLOCKED_WORTH = "0.2"

#: One Program per disturbance, so no scenario is read through another's rows.
SCENARIOS = (
    "greedy", "unlock", "tied", "missing", "fresh", "proposed", "reweighted",
    "shared",
)

#: Three property classes, because three Hypotheses about one subject have to
#: disagree about something for `hypotheses_dedup_idx` to admit them.
BLOCKED_CLASSES = (
    "authorization.object_ownership",
    "authorization.function_access",
    "authorization.tenant_isolation",
)


class TaskRankingTest(SchedulerFixture, DatabaseCase):
    """PH2-26: a priority made of components, and only sound edges move it.

    The formula is arithmetic and could be checked anywhere. What cannot is
    everything around it: the components come from this Program's own run
    history, the unlock term comes from edges the pass derives and withdraws
    against live rows, and the weights are a version that a trigger refuses to
    let anyone rewrite. All three are properties of a server.

    Each Program is one scenario, disturbed in exactly one way -- nothing at all
    (greedy), three Tasks waiting on one (unlock), two Tasks that promise the
    same thing (tied), one Task that promises nothing (missing), no history to
    estimate from (fresh), an edge nothing derived (proposed).

    Everything runs in `setUpClass` because all of it commits, and because a
    Ranking pass only means anything against the rows the step before it left.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)

        cls.identifiers = {}
        for name in SCENARIOS:
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, AFFORDABLE).replace(
                    'name = "matrix-web"', f'name = "{RANK_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.identifiers[name] = opened.facts["program_id"]

        cls.arrange_greedy()
        cls.arrange_unlock()
        cls.arrange_tied()
        cls.arrange_missing()
        cls.arrange_fresh()
        cls.arrange_proposed()
        cls.arrange_reweighted()
        cls.arrange_shared()
        cls.arrange_weights()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{RANK_SLUG}-%",)
            )
        super().tearDownClass()

    # -- reading a Program back ------------------------------------------------

    @classmethod
    def components(cls, name: str) -> dict[str, tuple]:
        """Every ranked component of every pending Task, by label."""
        rows = cls.as_owner(
            "SELECT label, priority, direct_value, unlock_value, estimated_cost,"
            "       estimated_time, safety_cost, novelty, confidence_of_execution,"
            "       ranked_weights_version"
            "  FROM tasks WHERE program_id = $1::uuid AND status = 'pending'"
            " ORDER BY priority DESC NULLS LAST, created_at, id",
            (cls.identifiers[name],),
        ).dicts()
        return {str(row["label"]): row for row in rows}

    @classmethod
    def ordering(cls, name: str, kind: str | None = None) -> list[str]:
        """The labels of a Program's pending Tasks in the order the pass left.

        `kind` narrows it, because the unlock scenarios keep two populations in
        one Program: the recon Tasks whose order is the claim, and the blocked
        analyze Tasks that are only there to be waiting. The blocked ones are
        unready and will never be offered, so where they land says nothing about
        the ordering under test.
        """
        return [
            str(row["label"])
            for row in cls.as_owner(
                "SELECT label FROM tasks"
                "  WHERE program_id = $1::uuid AND status = 'pending'"
                "    AND ($2::text IS NULL OR kind = $2::text)"
                " ORDER BY priority DESC NULLS LAST, created_at, id",
                (cls.identifiers[name], kind),
            ).dicts()
        ]

    @classmethod
    def subject_of(cls, name: str, label: str) -> str:
        return str(
            cls.scalar(
                "SELECT subject_entity_id::text FROM tasks"
                "  WHERE program_id = $1::uuid AND label = $2",
                (cls.identifiers[name], label),
            )
        )

    @classmethod
    def blocked_on(cls, name: str, subject: str, count: int) -> None:
        """`count` analyze Tasks about a subject no artifact has been seen on.

        Each gets a Hypothesis of its own, and not because analyze reads one --
        `ready_for` does not. `tasks_live_dedup_idx` is unique over
        `(program, kind, subject, hypothesis, finding)` with NULLs not
        distinct, so three live analyze Tasks about one subject are three rows
        the schema calls one. Distinct Hypotheses are the honest way to have
        several paths waiting on the same reconnaissance.
        """
        for index in range(count):
            cls.as_owner(
                "INSERT INTO tasks (program_id, kind, status, subject_entity_id,"
                " hypothesis_id, expected_information_gain, potential_impact)"
                " VALUES ($1::uuid, 'analyze', 'pending', $2::uuid, $3::uuid, $4, $4)",
                (
                    cls.identifiers[name],
                    subject,
                    cls.hypothesis(
                        name, subject, f"blocking {name} {index}", BLOCKED_CLASSES[index]
                    ),
                    UNLOCKED_WORTH,
                ),
            )

    @classmethod
    def edges(cls, name: str) -> list[tuple[str, str, str, str]]:
        """The dependency edges of a Program, as (blocked, unlocker, basis, why)."""
        return [
            (str(row["blocked"]), str(row["unlocker"]), str(row["basis"]), str(row["predicate"]))
            for row in cls.as_owner(
                "SELECT b.label AS blocked, u.label AS unlocker, d.basis, d.predicate"
                "  FROM task_dependencies d"
                "  JOIN tasks b ON b.id = d.task_id"
                "  JOIN tasks u ON u.id = d.unlocked_by_task_id"
                " WHERE d.program_id = $1::uuid"
                " ORDER BY b.label, u.label",
                (cls.identifiers[name],),
            ).dicts()
        ]

    @classmethod
    def rank(cls, name: str) -> dict:
        """One Ranking pass on one Program, as the runtime, committed."""
        cls.bind(name)
        return json.loads(str(cls.call("SELECT rank_pass('runtime')")))

    # -- the scenarios ---------------------------------------------------------

    @classmethod
    def arrange_greedy(cls):
        """Four Tasks, nothing between them, ranked twice."""
        cls.greedy = cls.seed("greedy", 4)
        cls.rank("greedy")
        cls.greedy_first = cls.components("greedy")
        cls.greedy_events_before = cls.ranked_events("greedy")
        cls.rank("greedy")
        cls.greedy_again = cls.components("greedy")
        cls.greedy_order = cls.ordering("greedy")
        cls.greedy_slate = cls.offer()

    @classmethod
    def arrange_unlock(cls):
        """One cheap Task that three valuable ones are waiting on.

        Ranked three times, because the claim is comparative: the same two recon
        Tasks in the same Program have to change places when the edges appear
        and change back when they are withdrawn. A single ordering would be
        consistent with the unlock term doing nothing at all.
        """
        cls.unlock = cls.seed("unlock", 2)
        cls.rank("unlock")
        cls.unlock_greedy_order = cls.ordering("unlock", "recon")

        # The cheaper of the two -- 0.1 against 0.2 -- is the one the analyze
        # Tasks are made to wait on, so anything that puts it first has to have
        # come from what it unblocks.
        cls.blocked_on("unlock", cls.subject_of("unlock", cls.unlock[0]), 3)
        cls.unlock_pass = cls.rank("unlock")
        cls.unlock_order = cls.ordering("unlock", "recon")
        cls.unlock_components = cls.components("unlock")
        cls.unlock_edges = cls.edges("unlock")

        # Withdrawal, in the shape the pass itself writes: an abandoned Task is
        # not pending, and an edge to it is a priority being paid for work that
        # will never be done.
        cls.as_owner(
            "UPDATE tasks SET status = 'abandoned', abandoned_reason = 'answered',"
            " finished_at = now(), priority = NULL"
            " WHERE program_id = $1::uuid AND kind = 'analyze'",
            (cls.identifiers["unlock"],),
        )
        cls.withdrawn_pass = cls.rank("unlock")
        cls.withdrawn_order = cls.ordering("unlock", "recon")
        cls.withdrawn_components = cls.components("unlock")
        cls.withdrawn_edges = cls.edges("unlock")

    @classmethod
    def arrange_tied(cls):
        """Two Tasks that promise exactly the same thing."""
        cls.tied = cls.seed("tied", 2)
        cls.as_owner(
            "UPDATE tasks SET expected_information_gain = 0.5, potential_impact = 0.5"
            " WHERE program_id = $1::uuid",
            (cls.identifiers["tied"],),
        )
        cls.rank("tied")
        cls.tied_components = cls.components("tied")
        cls.tied_order = cls.ordering("tied")
        # Offered twice, and read through the offer rather than through an
        # ORDER BY of this file's own: a tie broken by a clause the test writes
        # is a claim about Postgres, not about the scheduler. `offer_slate`
        # orders by `rank_candidates`, which is where the tie-break lives, and
        # two identical offers are what "not by chance" means.
        cls.tied_slate = [str(row["task_label"]) for row in cls.offer()]
        cls.tied_slate_again = [str(row["task_label"]) for row in cls.offer()]
        cls.tied_created = [
            str(row["label"])
            for row in cls.as_owner(
                "SELECT label FROM tasks WHERE program_id = $1::uuid"
                " ORDER BY created_at, id",
                (cls.identifiers["tied"],),
            ).dicts()
        ]

    @classmethod
    def arrange_missing(cls):
        """The Task that would have been first, with one estimate taken away."""
        cls.missing = cls.seed("missing", 2)
        cls.as_owner(
            "UPDATE tasks SET expected_information_gain = NULL"
            " WHERE program_id = $1::uuid AND label = $2",
            (cls.identifiers["missing"], cls.missing[-1]),
        )
        cls.rank("missing")
        cls.missing_components = cls.components("missing")
        cls.missing_order = cls.ordering("missing")
        cls.missing_slate = cls.offer()

    @classmethod
    def arrange_fresh(cls):
        """One Task in a Program with no run history behind it."""
        cls.fresh = cls.seed("fresh", 1)
        cls.rank("fresh")
        cls.fresh_components = cls.components("fresh")
        cls.fresh_priors = cls.as_owner(
            "SELECT (w.cost_prior ->> 'recon')::numeric AS cost,"
            "       (w.time_prior ->> 'recon')::numeric AS time,"
            "       w.safety_prior AS safety, w.version"
            "  FROM scheduler_weights w WHERE w.active"
        ).dicts()[0]

    @classmethod
    def arrange_proposed(cls):
        """An edge nobody derived, between two Tasks no rule relates."""
        cls.proposed = cls.seed("proposed", 2)
        cls.rank("proposed")
        cls.proposed_greedy_order = cls.ordering("proposed")
        # recon unblocking recon is a claim no rule in the corpus makes, so this
        # edge cannot be re-derived as sound underneath the assertion.
        cls.as_owner(
            "INSERT INTO task_dependencies (program_id, task_id, unlocked_by_task_id,"
            " basis, predicate)"
            " SELECT $1::uuid, b.id, u.id, 'proposed', 'recon.no_subject'"
            "   FROM tasks b, tasks u"
            "  WHERE b.program_id = $1::uuid AND b.label = $2"
            "    AND u.program_id = $1::uuid AND u.label = $3",
            (cls.identifiers["proposed"], cls.proposed[-1], cls.proposed[0]),
        )
        cls.rank("proposed")
        cls.proposed_order = cls.ordering("proposed")
        cls.proposed_components = cls.components("proposed")

        # The same claim written with the basis that would make it count. The
        # runtime holds INSERT here because the derivation runs as the runtime,
        # and that grant is the whole of criterion 4 unless a sound basis is
        # the derivation's alone to write.
        cls.forged_refusal = cls.refusal(
            "INSERT INTO task_dependencies (program_id, task_id,"
            " unlocked_by_task_id, basis, predicate)"
            " SELECT $1::uuid, b.id, u.id, 'runtime_rule', 'recon.no_subject'"
            "   FROM tasks b, tasks u"
            "  WHERE b.program_id = $1::uuid AND b.label = $2"
            "    AND u.program_id = $1::uuid AND u.label = $3",
            (cls.identifiers["proposed"], cls.proposed[-1], cls.proposed[0]),
        )

    @classmethod
    def arrange_reweighted(cls):
        """The unlock scenario again, left standing for the weights to move.

        Its own Program because the unlock one has had its edges withdrawn, and
        an ordering that flips when `w_unlock` goes to zero proves nothing if
        the term was already zero. Here the edges are live and sound when the
        operator changes the weights, so the only thing that moves the order is
        the weights.
        """
        cls.reweighted = cls.seed("reweighted", 2)
        cls.blocked_on("reweighted", cls.subject_of("reweighted", cls.reweighted[0]), 3)
        cls.rank("reweighted")
        cls.reweighted_order = cls.ordering("reweighted", "recon")
        cls.reweighted_components = cls.components("reweighted")

        # The other half of the same grant: deleting a sound edge suppresses an
        # unlock as surely as forging one invents it, and this Program is where
        # there are live ones to delete.
        cls.unwritten_refusal = cls.refusal(
            "DELETE FROM task_dependencies"
            " WHERE program_id = $1::uuid AND basis = 'runtime_rule'",
            (cls.identifiers["reweighted"],),
        )

    @classmethod
    def arrange_shared(cls):
        """One report Task, and the two validations either of which settles it.

        The unlock term's other shape, and the one the report rule makes
        ordinary: `report.no_validated_finding` is asked of the Program, so
        every pending validate Task unblocks the same report Task. Paying each
        of them the whole of its value would hand that value out twice for work
        one Task does, and would put every validate Task in an engagement ahead
        of everything else on the strength of a report nobody has written.
        """
        cls.shared = cls.seed("shared", 2, kind="validate")
        cls.shared_report = str(
            cls.as_owner(
                "INSERT INTO tasks (program_id, kind, status,"
                " expected_information_gain, potential_impact)"
                " VALUES ($1::uuid, 'report', 'pending', $2, $2) RETURNING label",
                (cls.identifiers["shared"], UNLOCKED_WORTH),
            ).scalar()
        )
        cls.rank("shared")
        cls.shared_components = cls.components("shared")
        cls.shared_edges = cls.edges("shared")

    @classmethod
    def arrange_weights(cls):
        """The operator's move, and what it does not touch.

        Restored in a `finally`, because the active weights row is global: a
        scenario that left this Program's version behind would rank every case
        after it -- in this file and in every other -- under weights this one
        chose.
        """
        cls.weights_before = cls.active_weights()
        cls.rewrite_refusal = cls.owner_refusal(
            "UPDATE scheduler_weights SET w_unlock = 0 WHERE version = $1",
            (str(cls.weights_before["version"]),),
        )
        cls.delete_refusal = cls.owner_refusal(
            "DELETE FROM scheduler_weights WHERE version = $1",
            (str(cls.weights_before["version"]),),
        )
        cls.unknown_key_refusal = cls.operator_refusal(
            "SELECT version_scheduler_weights('{\"w_greed\": 1}'::jsonb)"
        )
        cls.reserved_key_refusal = cls.operator_refusal(
            "SELECT version_scheduler_weights('{\"version\": 99}'::jsonb)"
        )
        cls.runtime_refusal = cls.refusal(
            "SELECT version_scheduler_weights('{\"w_unlock\": 0}'::jsonb)"
        )

        try:
            cls.new_version = int(
                str(
                    cls.operator(
                        "SELECT version_scheduler_weights('{\"w_unlock\": 0}'::jsonb)"
                    )
                )
            )
            cls.weights_after = cls.active_weights()
            cls.superseded = cls.weights_row(cls.weights_before["version"])
            # The same rows, ranked again under the new version: the unlock term
            # is switched off, so the Program that changed places changes back
            # without a single row of its own moving.
            cls.rank("reweighted")
            cls.reranked_order = cls.ordering("reweighted", "recon")
            cls.reranked_components = cls.components("reweighted")
            # A Program the change does not otherwise touch, ranked again while
            # the new version is the active one. Without this the "and a new
            # pass happened" half of criterion 5 is a list of events nothing
            # appended to, and the assertion about it holds vacuously.
            cls.greedy_events_at_change = cls.ranked_events("greedy")
            cls.rank("greedy")
            cls.greedy_events_after = cls.ranked_events("greedy")
        finally:
            cls.operator(
                "SELECT version_scheduler_weights("
                " jsonb_build_object('w_unlock', $1::numeric))",
                (str(cls.weights_before["w_unlock"]),),
            )
        cls.weights_restored = cls.active_weights()

    # -- reading the weights ---------------------------------------------------

    @classmethod
    def active_weights(cls) -> dict:
        return cls.as_owner(
            "SELECT version, w_unlock, w_tokens, w_time, w_safety,"
            "       max_concurrent_subagents, slate_size"
            "  FROM scheduler_weights WHERE active"
        ).dicts()[0]

    @classmethod
    def weights_row(cls, version: object) -> dict:
        return cls.as_owner(
            "SELECT version, active, w_unlock FROM scheduler_weights WHERE version = $1",
            (str(version),),
        ).dicts()[0]

    @classmethod
    def ranked_events(cls, name: str) -> list[tuple[str, str]]:
        """Every Ranking pass this Program has recorded, oldest first."""
        return [
            (int(str(row["seq"])), str(row["weights_version"]))
            for row in cls.as_owner(
                "SELECT e.seq, e.payload ->> 'weights_version' AS weights_version"
                "  FROM events e"
                " WHERE e.program_id = $1::uuid AND e.type = 'scheduler.ranked'"
                " ORDER BY e.seq",
                (cls.identifiers[name],),
            ).dicts()
        ]

    @classmethod
    def owner_refusal(cls, sql: str, parameters: tuple = ()) -> str:
        try:
            cls.as_owner(sql, parameters)
        except pg.DatabaseError as refused:
            return str(refused)
        raise AssertionError(f"not refused: {sql}")

    @classmethod
    def operator_refusal(cls, sql: str, parameters: tuple = ()) -> str:
        try:
            cls.operator(sql, parameters)
        except pg.DatabaseError as refused:
            return str(refused)
        raise AssertionError(f"not refused: {sql}")

    # -- criterion 1: every component is exposed -------------------------------

    def test_every_ranked_task_carries_all_seven_components(self):
        for label, row in self.greedy_first.items():
            with self.subTest(task=label):
                for column in (
                    "novelty",
                    "confidence_of_execution",
                    "direct_value",
                    "estimated_cost",
                    "estimated_time",
                    "safety_cost",
                    "unlock_value",
                    "ranked_weights_version",
                ):
                    self.assertIsNotNone(row[column], column)

    def test_the_offer_reports_the_components_the_row_was_ranked_on(self):
        # Rounded on both sides because the offer rounds: an orchestrator is
        # being shown these, and six places is what `task_rank_factors` decided
        # a reader needs. The claim is that the numbers are the row's, not that
        # they are unrounded.
        for entry in self.greedy_slate:
            factors = json.loads(str(entry["factors"]))
            row = self.greedy_again[str(entry["task_label"])]
            with self.subTest(task=entry["task_label"]):
                self.assertEqual(
                    {
                        name: round(float(str(row[column])), 6)
                        for name, column in (
                            ("value", "direct_value"),
                            ("cost", "estimated_cost"),
                            ("time", "estimated_time"),
                            ("safety", "safety_cost"),
                            ("unlock", "unlock_value"),
                            ("novelty", "novelty"),
                            ("confidence", "confidence_of_execution"),
                        )
                    }
                    | {"weights_version": int(str(row["ranked_weights_version"]))},
                    {
                        name: round(float(factors[name]), 6)
                        for name in ("value", "cost", "time", "safety", "unlock",
                                     "novelty", "confidence")
                    }
                    | {"weights_version": factors["weights_version"]},
                )

    # -- criterion 2: the same rows reach the same numbers ---------------------

    def test_two_passes_over_the_same_rows_reach_the_same_priorities(self):
        self.assertEqual(
            {label: row["priority"] for label, row in self.greedy_first.items()},
            {label: row["priority"] for label, row in self.greedy_again.items()},
        )

    def test_a_program_nothing_unlocks_is_ranked_greedily(self):
        # Seeded ascending in worth, so the order should be the reverse.
        self.assertEqual(list(reversed(self.greedy)), self.greedy_order)

    def test_equal_scores_are_broken_by_age_and_not_by_chance(self):
        [first, second] = self.tied_order
        self.assertEqual(
            self.tied_components[first]["priority"],
            self.tied_components[second]["priority"],
        )
        # The order the runtime offers them in, twice, and it is the order they
        # were created in. Read off the Slate because that is the ordering the
        # system acts on; the two offers are what says it was not a coin toss
        # that happened to land the same way as `created_at`.
        self.assertEqual(self.tied_slate, self.tied_slate_again)
        self.assertEqual(self.tied_created, self.tied_slate)

    # -- criterion 3: what a Task unlocks can outrank what it is worth ---------

    def test_the_cheaper_task_loses_until_it_unblocks_something(self):
        self.assertEqual(list(reversed(self.unlock)), self.unlock_greedy_order)

    def test_a_task_that_unblocks_several_valuable_paths_comes_first(self):
        self.assertEqual(self.unlock[0], self.unlock_order[0])
        self.assertGreater(
            self.unlock_components[self.unlock[0]]["priority"],
            self.unlock_components[self.unlock[1]]["priority"],
        )

    def test_several_is_counted_as_several_and_not_capped_to_one(self):
        # Every waiting Task is in the credit, and the sum is theirs -- not the
        # 1.0 ceiling, which at a high enough worth would saturate at two and
        # make "unblocks three paths" indistinguishable from "unblocks one".
        waiting = [
            float(str(row["direct_value"]))
            for label, row in self.unlock_components.items()
            if label not in self.unlock
        ]
        self.assertEqual(3, len(waiting))
        self.assertAlmostEqual(
            sum(waiting),
            float(str(self.unlock_components[self.unlock[0]]["unlock_value"])),
        )

    def test_only_the_unlocking_task_is_credited(self):
        self.assertGreater(
            float(str(self.unlock_components[self.unlock[0]]["unlock_value"])), 0.0
        )
        self.assertEqual(
            0.0, float(str(self.unlock_components[self.unlock[1]]["unlock_value"]))
        )

    def test_a_dependent_is_paid_for_once_however_many_could_settle_it(self):
        worth = float(str(self.shared_components[self.shared_report]["direct_value"]))
        credited = [
            float(str(self.shared_components[label]["unlock_value"]))
            for label in self.shared
        ]

        self.assertEqual(
            [(self.shared_report, label, "runtime_rule", "report.no_validated_finding")
             for label in sorted(self.shared)],
            sorted(self.shared_edges),
        )
        # Half each, and the two halves are the report Task's value exactly
        # once. Whole-value-each would be two Tasks credited with one report.
        for share in credited:
            self.assertAlmostEqual(worth / 2, share)
        self.assertAlmostEqual(worth, sum(credited))

    def test_the_pass_derives_one_edge_per_blocked_task(self):
        self.assertEqual(3, self.unlock_pass["edges_derived"])
        self.assertEqual(3, len(self.unlock_edges))
        for _, unlocker, basis, predicate in self.unlock_edges:
            self.assertEqual(
                (self.unlock[0], "runtime_rule", "analyze.no_agent_visible_artifact"),
                (unlocker, basis, predicate),
            )

    def test_an_edge_stops_being_paid_for_when_its_task_stops_waiting(self):
        self.assertEqual(3, self.withdrawn_pass["edges_withdrawn"])
        self.assertEqual([], self.withdrawn_edges)
        self.assertEqual(
            0.0, float(str(self.withdrawn_components[self.unlock[0]]["unlock_value"]))
        )
        self.assertEqual(list(reversed(self.unlock)), self.withdrawn_order)

    # -- criterion 4: an edge nothing derived is worth nothing -----------------

    def test_an_unsound_edge_moves_no_priority(self):
        self.assertEqual(self.proposed_greedy_order, self.proposed_order)
        for label in self.proposed:
            with self.subTest(task=label):
                self.assertEqual(
                    0.0, float(str(self.proposed_components[label]["unlock_value"]))
                )

    def test_a_sound_basis_is_the_derivations_to_write(self):
        # The runtime may record a claim and may not dress one as derived, in
        # either direction: minting an edge invents unlock value and deleting
        # one suppresses it, and both are reachable from the grant the
        # derivation needs.
        for refused in (self.forged_refusal, self.unwritten_refusal):
            with self.subTest(refused=refused[:40]):
                self.assertIn("derive_task_dependencies", refused)

    def test_the_unsound_edge_is_still_recorded(self):
        # Zero unlock value is not the same as a claim nobody may make: the row
        # is kept, visible and answerable, and only its arithmetic is refused.
        self.assertEqual(
            [(self.proposed[-1], self.proposed[0], "proposed", "recon.no_subject")],
            self.edges("proposed"),
        )

    # -- criterion 5: weights are versioned, and versions are not rewritten ----

    def test_a_weights_version_cannot_be_edited_or_deleted(self):
        self.assertIn("not rewritten", self.rewrite_refusal)
        self.assertIn("named by every Ranking pass", self.delete_refusal)

    def test_the_operator_verb_supersedes_rather_than_edits(self):
        self.assertEqual(
            self.weights_before["version"] + 1, self.weights_after["version"]
        )
        self.assertEqual(self.new_version, self.weights_after["version"])
        self.assertEqual(0.0, float(str(self.weights_after["w_unlock"])))
        # Everything the operator did not name comes with it.
        for column in ("w_tokens", "w_time", "w_safety", "max_concurrent_subagents",
                       "slate_size"):
            with self.subTest(column=column):
                self.assertEqual(
                    str(self.weights_before[column]), str(self.weights_after[column])
                )

    def test_the_superseded_version_keeps_its_numbers(self):
        self.assertEqual(False, self.superseded["active"])
        self.assertEqual(
            str(self.weights_before["w_unlock"]), str(self.superseded["w_unlock"])
        )

    def test_a_new_version_makes_a_new_pass_and_rewrites_no_old_one(self):
        # Every pass this class ran before the change still names the version it
        # ran under, byte for byte.
        self.assertEqual(
            self.greedy_events_before,
            self.greedy_events_after[: len(self.greedy_events_before)],
        )
        self.assertEqual(
            {str(self.weights_before["version"])},
            {version for _, version in self.greedy_events_before},
        )
        # And the pass that ran after it is a new one, naming the new version.
        # Everything recorded before the change is still there unchanged and one
        # event longer is the whole of it: two passes, two versions, both
        # readable, neither restated as the other.
        self.assertEqual(
            self.greedy_events_at_change, self.greedy_events_after[:-1]
        )
        self.assertEqual(
            len(self.greedy_events_at_change) + 1, len(self.greedy_events_after)
        )
        self.assertEqual(str(self.new_version), self.greedy_events_after[-1][1])

    def test_the_new_weights_change_the_order_without_moving_a_row(self):
        # Under version N the unlocker leads; under N+1, which prices unlocking
        # at zero, the richer Task does. Same rows, same edges, same components
        # -- only the version that combined them differs.
        self.assertEqual(self.reweighted[0], self.reweighted_order[0])
        self.assertEqual(list(reversed(self.reweighted)), self.reranked_order)
        for label in self.reweighted:
            with self.subTest(task=label):
                self.assertEqual(
                    str(self.reweighted_components[label]["unlock_value"]),
                    str(self.reranked_components[label]["unlock_value"]),
                )
        self.assertEqual(
            self.new_version,
            int(str(self.reranked_components[self.reweighted[0]]["ranked_weights_version"])),
        )

    def test_only_the_operator_may_version_the_weights(self):
        self.assertIn("permission denied", self.runtime_refusal)

    def test_a_weight_this_table_does_not_have_is_refused(self):
        self.assertIn("w_greed", self.unknown_key_refusal)
        self.assertIn("version", self.reserved_key_refusal)

    def test_the_weights_row_is_back_where_this_fixture_found_it(self):
        self.assertEqual(
            str(self.weights_before["w_unlock"]), str(self.weights_restored["w_unlock"])
        )

    # -- criterion 6: missing estimates and bounded fallbacks ------------------

    def test_a_task_with_a_missing_estimate_sinks_and_is_offered_last(self):
        unestimated = self.missing[-1]
        self.assertIsNone(self.missing_components[unestimated]["priority"])
        self.assertIsNone(self.missing_components[unestimated]["direct_value"])
        self.assertEqual(unestimated, self.missing_order[-1])
        self.assertEqual(
            unestimated, [row["task_label"] for row in self.missing_slate][-1]
        )

    def test_the_other_components_are_still_measured_for_it(self):
        # Unestimated is not unranked: what the runtime can measure about the
        # Task is measured, and only the model's half is absent.
        row = self.missing_components[self.missing[-1]]
        for column in ("novelty", "estimated_cost", "estimated_time", "safety_cost",
                       "unlock_value", "ranked_weights_version"):
            with self.subTest(column=column):
                self.assertIsNotNone(row[column])

    def test_a_program_with_no_history_falls_back_to_its_priors(self):
        row = self.fresh_components[self.fresh[0]]
        self.assertEqual(
            (
                float(str(self.fresh_priors["cost"])),
                float(str(self.fresh_priors["time"])),
                float(str(self.fresh_priors["safety"])),
            ),
            (
                float(str(row["estimated_cost"])),
                float(str(row["estimated_time"])),
                float(str(row["safety_cost"])),
            ),
        )

    def test_every_fallback_is_inside_its_bound(self):
        for name in SCENARIOS:
            for label, row in self.components(name).items():
                with self.subTest(program=name, task=label):
                    for column in ("estimated_cost", "estimated_time", "safety_cost",
                                   "unlock_value", "direct_value"):
                        if row[column] is None:  # criterion 6's unestimated Task
                            continue
                        value = float(str(row[column]))
                        self.assertGreaterEqual(value, 0.0, column)
                        self.assertLessEqual(value, 1.0, column)

    # -- the invariant ---------------------------------------------------------

    def test_the_standing_check_is_registered_and_holds(self):
        [registered] = self.connection.execute(
            "SELECT count(*) FROM standing_checks WHERE name = $1", ("task_ranking",)
        ).rows
        [[problems, detail]] = self.connection.execute(
            "SELECT problems, detail FROM run_standing_checks() WHERE name = $1",
            ("task_ranking",),
        ).rows

        self.assertEqual(1, int(registered[0]))
        self.assertEqual((0, ""), (int(problems), str(detail)))


#: The Programs of `OrchestratorDispatchTest`, sharing a prefix so one DELETE
#: retires them.
DISPATCH_SLUG = "selftest-dispatch"

#: The one Skill the corpus registers, and the one role it is granted to.
#: Criterion 4 is a claim about that pair: `hunt` reaches `web_hunter`, which
#: holds the grant, and every other kind reaches a role that does not.
IDENTITY_SKILL = "use-identity"

#: One Program per scenario, so no scenario is read through another's rows.
DISPATCH_SCENARIOS = ("chose", "refused", "silent", "skilled")


class OrchestratorDispatchTest(SchedulerFixture, DatabaseCase):
    """PH2-27: one model decides, and the runtime commits it or refuses it.

    The arithmetic of a choice is nothing -- a label comes back and a Task is
    claimed. What only a server can answer is everything around it: that the
    session the choice was made in holds no Task and therefore no lane slot,
    that a label the Slate no longer carries is refused rather than replaced,
    that three different kinds of silence all leave the same walk available,
    and that the admission rule knows which role would have to load the Task's
    Skills.

    Each Program is one scenario. `chose` is the pass that works, and it names
    the second entry so that "the claim honoured the choice" and "the claim
    walked the Slate" cannot be true of the same label. `refused` is every way
    of recording something that is not a choice, plus the two downgrades.
    `silent` is the three answers that are not a choice at all. `skilled` is
    one Skill, the kind whose role holds it, and the kind whose role does not.

    Everything runs in `setUpClass` because all of it commits, and because a
    refusal only means anything against the state the step before it left.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)

        cls.identifiers = {}
        for name in DISPATCH_SCENARIOS:
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, AFFORDABLE).replace(
                    'name = "matrix-web"', f'name = "{DISPATCH_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.identifiers[name] = opened.facts["program_id"]

        cls.arrange_chose()
        cls.arrange_refused()
        cls.arrange_silent()
        cls.arrange_skilled()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{DISPATCH_SLUG}-%",)
            )
        super().tearDownClass()

    # -- the moves a scenario is made of ---------------------------------------

    @classmethod
    def session(cls, name: str) -> dict:
        """One planning session, opened by the statement the runtime sends.

        `execution.OPEN_SESSION` rather than a statement spelled here, for
        `started`'s reason: what is under test is the seam, and a second
        spelling of the call would only prove that the function can be called.
        """
        cls.bind(name)
        return json.loads(str(cls.call(execution.OPEN_SESSION)))

    @classmethod
    def choose(
        cls, run: str, outcome: str, label: str | None = None, detail: str | None = None
    ) -> dict:
        """One recorded answer, through the runtime's own statement."""
        return json.loads(str(cls.call(execution.CHOICE, (run, outcome, label, detail))))

    @classmethod
    def ceilings(cls, name: str) -> tuple[int, int]:
        """The two numbers a session is bounded by, read from their own rows."""
        return (
            int(
                cls.scalar(
                    "SELECT max_concurrent_subagents FROM scheduler_weights"
                    " WHERE active"
                )
            ),
            int(
                cls.scalar(
                    "SELECT run_tokens FROM program_capacity WHERE program_id = $1::uuid",
                    (cls.identifiers[name],),
                )
            ),
        )

    # -- reading a Program back ------------------------------------------------

    @classmethod
    def run_row(cls, name: str, run: object) -> dict:
        """One Agent run, the roster row behind it, and what it promised."""
        return cls.as_owner(
            "SELECT a.role, a.task_id, a.executes_tasks, a.model, a.effort,"
            "       r.model AS roster_model, r.effort AS roster_effort,"
            "       (SELECT count(*) FROM budget_reservations b"
            "         WHERE b.agent_run_id = a.id) AS reservations"
            "  FROM agent_runs a JOIN roles r ON r.role = a.role"
            " WHERE a.program_id = $1::uuid AND a.label = $2",
            (cls.identifiers[name], str(run)),
        ).dicts()[0]

    @classmethod
    def run_id(cls, name: str, run: object) -> str:
        return str(
            cls.scalar(
                "SELECT id::text FROM agent_runs"
                " WHERE program_id = $1::uuid AND label = $2",
                (cls.identifiers[name], str(run)),
            )
        )

    @classmethod
    def dispatched(cls, name: str, run: object) -> dict:
        """What a committed claim leaves for the dispatch to act on.

        The Task, the Lease clock it was taken under and the promise held
        against it, read through the Agent run rather than through the Task:
        criterion 5 is that the run carries the claim's own Task, and a query
        that started from the Task could not tell that apart from a run that
        was pointed at a different one.
        """
        return cls.as_owner(
            "SELECT t.label AS task, t.status,"
            "       t.lease_expires_at IS NOT NULL AS leased,"
            "       b.kind AS reserved_kind, bt.label AS reserved_task,"
            "       b.tokens IS NOT NULL AS reserved_tokens"
            "  FROM agent_runs a"
            "  JOIN tasks t ON t.id = a.task_id"
            "  LEFT JOIN budget_reservations b ON b.agent_run_id = a.id"
            "  LEFT JOIN tasks bt ON bt.id = b.task_id"
            " WHERE a.program_id = $1::uuid AND a.label = $2",
            (cls.identifiers[name], str(run)),
        ).dicts()[0]

    @classmethod
    def choices(cls, name: str) -> list[dict]:
        """Every recorded choice of a Program, oldest first.

        The session is joined back in rather than trusted from the payload, so
        that "names a Task-less orchestrator run" is read off the run itself.
        """
        return [
            {
                "actor": str(row["actor_kind"]),
                "run": None if row["run"] is None else str(row["run"]),
                "role": None if row["role"] is None else str(row["role"]),
                "holds_task": row["holds_task"],
                "payload": json.loads(str(row["payload"])),
            }
            for row in cls.as_owner(
                "SELECT e.actor_kind, e.payload::text AS payload, ar.label AS run,"
                "       ar.role, ar.task_id IS NOT NULL AS holds_task"
                "  FROM events e LEFT JOIN agent_runs ar ON ar.id = e.agent_run_id"
                " WHERE e.program_id = $1::uuid AND e.type = 'scheduler.chose'"
                " ORDER BY e.seq",
                (cls.identifiers[name],),
            ).dicts()
        ]

    @classmethod
    def outstanding_picks(cls, name: str) -> int:
        return int(
            cls.scalar(
                "SELECT count(*) FROM task_picks"
                " WHERE program_id = $1::uuid AND NOT consumed",
                (cls.identifiers[name],),
            )
        )

    # -- the scenarios ---------------------------------------------------------

    @classmethod
    def arrange_chose(cls):
        """A session opens, names an entry that is not the first, and gets it."""
        cls.chose = cls.seed("chose", 3)
        cls.bind("chose")
        cls.chose_slate = cls.offer()
        cls.chose_ceilings = cls.ceilings("chose")
        cls.opened = cls.session("chose")
        cls.opened_row = cls.run_row("chose", cls.opened["label"])

        # The second entry. Choosing the first would be indistinguishable from
        # the runtime's own walk, which is the other thing this file tests.
        cls.wanted = str(cls.chose_slate[1]["task_label"])
        cls.chose_payload = cls.choose(
            cls.opened["agent_run"], "chosen", cls.wanted, "the second entry reads better"
        )
        cls.chose_run = cls.call("SELECT claim_task()")
        cls.chose_claimed = cls.claimed_by("chose", cls.chose_run)
        cls.chose_dispatch = cls.dispatched("chose", cls.chose_run)
        cls.chose_events = cls.choices("chose")

    @classmethod
    def arrange_refused(cls):
        """Five ways of recording something that is not a choice, and two
        downgrades.

        The refusals are raised and the downgrades are not, and that is the
        distinction the scenario exists to draw: a caller contradicting itself
        is a bug in the runtime and stops the statement, while a label the
        Slate has stopped carrying is the ordinary outcome of thinking for a
        while and is recorded as one.
        """
        cls.refused = cls.seed("refused", 3)
        cls.bind("refused")
        cls.refused_slate = cls.offer()
        cls.refused_session = cls.session("refused")
        run = cls.refused_session["agent_run"]

        # A label no Slate ever carried.
        cls.off_slate_payload = cls.choose(run, "chosen", "T99")
        cls.picks_after_off_slate = cls.outstanding_picks("refused")

        cls.unknown_outcome = cls.refusal(
            execution.CHOICE, (run, "probably", None, None)
        )
        cls.chosen_without_label = cls.refusal(
            execution.CHOICE, (run, "chosen", None, None)
        )
        cls.silent_with_label = cls.refusal(
            execution.CHOICE, (run, "no_choice", cls.refused[0], None)
        )
        # `arrange_chose` ran first, so its session is a real run that this
        # Program may not record anything against.
        cls.other_programs_session = cls.refusal(
            execution.CHOICE, (cls.opened["agent_run"], "no_choice", None, None)
        )

        # A run that holds a Task is a worker, and a worker recording a choice
        # would be the thing that was chosen attributing the choice to itself.
        worker = cls.call(
            "SELECT claim_task($1)", (str(cls.refused_slate[0]["task_label"]),)
        )
        cls.worker_session = cls.refusal(
            execution.CHOICE, (cls.run_id("refused", worker), "no_choice", None, None)
        )

        # The list died while the model was reading it. The same downgrade as
        # an unknown label, reached through the other half of `pick_task`.
        cls.as_owner(
            "UPDATE task_slate SET offered_at = now() - interval '10 minutes'"
            " WHERE program_id = $1::uuid AND NOT consumed",
            (cls.identifiers["refused"],),
        )
        cls.expired_payload = cls.choose(
            run, "chosen", str(cls.refused_slate[1]["task_label"])
        )
        # One Task claimed and two runs -- the session and the worker -- is
        # everything this scenario opened on purpose. A refusal that left a
        # third would be one that got half way in.
        cls.refused_counts = cls.counted("refused")
        cls.refused_events = cls.choices("refused")

    @classmethod
    def arrange_silent(cls):
        """The three answers that are not a choice, and the walk after them."""
        cls.silent = cls.seed("silent", 3)
        cls.bind("silent")
        cls.silent_slate = cls.offer()
        cls.silent_session = cls.session("silent")
        run = cls.silent_session["agent_run"]
        # The details are the ones `execution` writes, so that what an operator
        # reads back is the sentence the runtime had at the time rather than a
        # word this file invented.
        cls.silent_payloads = {
            outcome: cls.choose(run, outcome, None, detail)
            for outcome, detail in (
                ("no_choice", None),
                ("malformed", "2 pick(s) carried no task label"),
                ("unavailable", "no session answered"),
            )
        }
        cls.picks_after_silence = cls.outstanding_picks("silent")
        cls.silent_walk = cls.claimed_by("silent", cls.call("SELECT claim_task()"))
        cls.silent_events = cls.choices("silent")

    @classmethod
    def arrange_skilled(cls):
        """One Skill, the kind whose role holds it, and the kind whose does not.

        Two Tasks about one subject in one Program, differing in kind and in
        nothing else that the admission rule reads. The recon Task is seeded
        rich -- 0.9 against the hunt's 0.1 -- so that it would lead the Slate
        on every other measure the scheduler has, and what keeps it off is the
        grant alone.
        """
        program_id = cls.identifiers["skilled"]
        cls.skilled_hunt = cls.seed("skilled", 1, kind="hunt")[0]
        subject = str(
            cls.scalar(
                "SELECT subject_entity_id::text FROM tasks"
                " WHERE program_id = $1::uuid AND label = $2",
                (program_id, cls.skilled_hunt),
            )
        )
        # A hunt is ready with a testable Hypothesis under it, and requires the
        # Skill its role was granted.
        cls.as_owner(
            "UPDATE tasks SET hypothesis_id = $3::uuid, required_skills = ARRAY[$4::text]"
            " WHERE program_id = $1::uuid AND label = $2",
            (
                program_id,
                cls.skilled_hunt,
                cls.hypothesis("skilled", subject, "worth hunting"),
                IDENTITY_SKILL,
            ),
        )
        cls.skilled_recon = str(
            cls.as_owner(
                "INSERT INTO tasks (program_id, kind, status, subject_entity_id,"
                " required_skills, expected_information_gain, potential_impact)"
                " VALUES ($1::uuid, 'recon', 'pending', $2::uuid, ARRAY[$3::text],"
                " 0.9, 0.9) RETURNING label",
                (program_id, subject, IDENTITY_SKILL),
            ).scalar()
        )

        cls.bind("skilled")
        cls.skilled_slate = [str(row["task_label"]) for row in cls.offer()]
        cls.skilled_verdicts = {
            label: cls.claimable("skilled", label)
            for label in (cls.skilled_hunt, cls.skilled_recon)
        }
        cls.skilled_walk = cls.claimed_by("skilled", cls.call("SELECT claim_task()"))

    # -- criterion 1: the session is bounded, and bounded from rows ------------

    def test_a_session_carries_the_two_ceilings_the_child_cannot_read(self):
        subagent_cap, token_cap = self.chose_ceilings
        self.assertEqual(subagent_cap, self.opened["subagent_cap"])
        self.assertEqual(token_cap, self.opened["token_cap"])

    def test_a_session_says_what_it_is_and_nothing_more(self):
        self.assertEqual(
            {"agent_run", "label", "model", "effort", "subagent_cap", "token_cap"},
            set(self.opened),
        )

    # -- criterion 2: what the session may be, and who may open one -----------

    def test_a_planning_session_holds_no_task_and_no_lane_slot(self):
        self.assertEqual("orchestrator", str(self.opened_row["role"]))
        self.assertIsNone(self.opened_row["task_id"])
        self.assertEqual(False, self.opened_row["executes_tasks"])

    def test_it_runs_at_the_model_and_the_effort_the_roster_states(self):
        self.assertEqual(
            (str(self.opened_row["roster_model"]), str(self.opened_row["roster_effort"])),
            (str(self.opened_row["model"]), str(self.opened_row["effort"])),
        )
        self.assertEqual(
            (str(self.opened_row["model"]), str(self.opened_row["effort"])),
            (str(self.opened["model"]), str(self.opened["effort"])),
        )

    def test_a_planning_session_promises_no_budget(self):
        # `budget_reservations.task_id` is NOT NULL and its kind is the lane the
        # promise is held against, and a session has neither. What it spends is
        # still counted against the Program, which is `program_budget`'s sum
        # over every run and not only the ones that held a Task.
        self.assertEqual(0, int(str(self.opened_row["reservations"])))

    def test_no_connection_a_model_reaches_through_can_choose(self):
        # The revoke is the load-bearing half of the grant: `record_choice`
        # writes a pick, and a model that could call it directly would be
        # committing its own choice without the Slate ever being consulted.
        reachable = [
            str(row["proname"])
            for row in self.as_owner(
                "SELECT p.proname FROM pg_proc p"
                " WHERE p.pronamespace = 'public'::regnamespace"
                "   AND p.proname IN ('open_orchestrator_session','record_choice')"
                "   AND has_function_privilege('rk2_state', p.oid, 'EXECUTE')"
            ).dicts()
        ]
        self.assertEqual([], reachable)

    def test_the_runtime_holds_both_verbs(self):
        self.assertEqual(
            2,
            int(
                self.scalar(
                    "SELECT count(*) FROM pg_proc p"
                    " WHERE p.pronamespace = 'public'::regnamespace"
                    "   AND p.proname IN ('open_orchestrator_session','record_choice')"
                    "   AND has_function_privilege('rk2_runtime', p.oid, 'EXECUTE')"
                )
            ),
        )

    # -- criterion 3: the claim, not the answer, decides -----------------------

    def test_a_choice_the_slate_carries_is_the_task_the_claim_takes(self):
        self.assertNotEqual(str(self.chose_slate[0]["task_label"]), self.wanted)
        self.assertEqual(self.wanted, self.chose_claimed)
        self.assertEqual(
            {"outcome": "chosen", "task": self.wanted, "offered_task": self.wanted,
             "agent_run": self.opened["label"],
             "detail": "the second entry reads better"},
            self.chose_payload,
        )

    def test_a_label_the_slate_no_longer_carries_claims_nothing(self):
        # ADR 0003 is explicit that a stale choice is refused and not
        # substituted: falling through to entry one here would be the runtime
        # answering the question it was told the model owns.
        for payload in (self.off_slate_payload, self.expired_payload):
            with self.subTest(detail=str(payload["detail"])[:40]):
                self.assertEqual("off_slate", payload["outcome"])
                self.assertIsNone(payload["task"])
        self.assertEqual(0, self.picks_after_off_slate)
        self.assertIn("is not on the current slate", str(self.off_slate_payload["detail"]))
        self.assertIn("expired after", str(self.expired_payload["detail"]))

    def test_the_three_silences_leave_the_slate_to_the_runtimes_own_walk(self):
        self.assertEqual(0, self.picks_after_silence)
        self.assertEqual(str(self.silent_slate[0]["task_label"]), self.silent_walk)

    # -- criterion 4: the kind selects the role, and the role loads the Skill ---

    def test_a_task_whose_role_cannot_load_its_skill_is_not_claimable(self):
        self.assertEqual(
            {self.skilled_hunt: None, self.skilled_recon: "skill_not_granted_to_role"},
            self.skilled_verdicts,
        )

    def test_the_offer_leaves_it_out_and_the_walk_passes_over_it(self):
        self.assertEqual([self.skilled_hunt], self.skilled_slate)
        self.assertEqual(self.skilled_hunt, self.skilled_walk)

    def test_the_grant_is_read_from_the_role_that_runs_the_kind(self):
        # The rule joins `role_skills` through `role_task_kinds`, so what makes
        # the hunt Task admissible is that the one role running `hunt` holds
        # the Skill -- not that some role somewhere does.
        self.assertEqual(
            [("web_hunter", "hunt")],
            [
                (str(row["role"]), str(row["kind"]))
                for row in self.as_owner(
                    "SELECT rs.role, m.kind FROM role_skills rs"
                    "  JOIN role_task_kinds m ON m.role = rs.role"
                    " WHERE rs.skill_name = $1 ORDER BY rs.role, m.kind",
                    (IDENTITY_SKILL,),
                ).dicts()
            ],
        )

    # -- criterion 5: the dispatch acts on the claim, not on the answer --------

    def test_the_claim_leaves_the_lease_and_the_promise_of_the_task_chosen(self):
        row = self.chose_dispatch
        self.assertEqual(
            (self.wanted, "claimed", self.wanted, "recon"),
            (
                str(row["task"]),
                str(row["status"]),
                str(row["reserved_task"]),
                str(row["reserved_kind"]),
            ),
        )
        self.assertEqual((True, True), (row["leased"], row["reserved_tokens"]))

    def test_a_choice_cannot_be_recorded_against_another_programs_session(self):
        self.assertIn("is not this Program's", self.other_programs_session)

    def test_a_run_that_holds_a_task_is_not_a_session_to_choose_in(self):
        self.assertIn("is not a Task-less orchestrator session", self.worker_session)

    def test_a_refusal_leaves_no_run_and_moves_no_task(self):
        self.assertEqual((1, 2), self.refused_counts)

    # -- criterion 6: deterministic, safe and auditable ------------------------

    def test_an_outcome_the_runtime_has_no_branch_for_is_refused(self):
        self.assertIn(
            "a choice is chosen, no_choice, malformed or unavailable", self.unknown_outcome
        )

    def test_only_a_chosen_outcome_names_a_task(self):
        for refused in (self.chosen_without_label, self.silent_with_label):
            with self.subTest(refused=refused[:40]):
                self.assertIn("only a chosen outcome names a task", refused)

    def test_every_answer_writes_one_choice_naming_its_session(self):
        recorded = self.chose_events + self.refused_events + self.silent_events
        self.assertEqual(
            ["chosen", "off_slate", "off_slate", "no_choice", "malformed", "unavailable"],
            [entry["payload"]["outcome"] for entry in recorded],
        )
        for entry in recorded:
            with self.subTest(outcome=entry["payload"]["outcome"]):
                self.assertEqual("orchestrator", entry["role"])
                self.assertEqual(False, entry["holds_task"])
                self.assertEqual(entry["run"], entry["payload"]["agent_run"])

    def test_the_actor_is_the_model_except_where_no_model_ran(self):
        self.assertEqual(
            {"no_choice": "llm", "malformed": "llm", "unavailable": "runtime"},
            {
                entry["payload"]["outcome"]: entry["actor"]
                for entry in self.silent_events
            },
        )
        self.assertEqual(
            {"llm"}, {entry["actor"] for entry in self.chose_events + self.refused_events}
        )

    def test_a_downgraded_choice_still_says_what_was_asked_for(self):
        # The label is kept in `offered_task` and cleared from `task`, so a run
        # that chose and could not be committed reads back as one that chose.
        self.assertEqual("T99", self.off_slate_payload["offered_task"])
        self.assertIsNone(self.off_slate_payload["task"])

    def test_what_the_silent_answers_recorded_is_what_the_runtime_said(self):
        self.assertEqual(
            {"no_choice": None, "malformed": "2 pick(s) carried no task label",
             "unavailable": "no session answered"},
            {
                outcome: payload["detail"]
                for outcome, payload in self.silent_payloads.items()
            },
        )
        for outcome, payload in self.silent_payloads.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(outcome, payload["outcome"])
                self.assertIsNone(payload["task"])
                self.assertIsNone(payload["offered_task"])

    # -- the invariant ---------------------------------------------------------

    def test_the_standing_check_is_registered_and_holds(self):
        [registered] = self.connection.execute(
            "SELECT count(*) FROM standing_checks WHERE name = $1",
            ("orchestrator_dispatch",),
        ).rows
        [[problems, detail]] = self.connection.execute(
            "SELECT problems, detail FROM run_standing_checks() WHERE name = $1",
            ("orchestrator_dispatch",),
        ).rows

        self.assertEqual(1, int(registered[0]))
        self.assertEqual((0, ""), (int(problems), str(detail)))


#: The Programs of `LeaseTest`, which share a prefix so one DELETE retires them.
LEASE_SLUG = "selftest-lease"


class LeaseTest(DatabaseCase):
    """PH2-24: one Lease, one clock, one heartbeat, and what a crash leaves.

    Every Program here is one hunt Task with one Identity named by its
    Hypothesis, because that is the smallest shape in which both halves of a
    Lease exist. `claim_task` writes an Identity Lease only for a role that
    clamps to one -- `web_hunter` -- and only where the Task's Hypothesis names
    an Identity; a recon Task would give a Task Lease with nothing to disagree
    with it, and disagreement is what this ticket is about.

    The Programs are the scenarios, and each is disturbed in one way after the
    claim. `beating` is renewed and never lapses. `lapsed` has both expiries
    pushed into the past, which is what a process that stopped beating leaves,
    and is then refused a beat. `released` gives both halves back and gives them
    back again. `crashed` and `retired` are reconciled after their owner
    stopped, one with attempts to spare and one without. `alive` is the one
    nothing may take, and it is asked of the reconciler and of the restart path
    in turn -- the second being where a competing claim used to get in.

    Everything runs in `setUpClass` because all of it commits, and because the
    order is the assertion: a beat after a release means nothing unless the
    release happened first.

    This case commits, and purges what it wrote at the end.
    """

    settings_for = "migrate"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runtime = pg.connect(cls.harness.runtime)

        cls.identifiers = {}
        cls.runs: dict[str, tuple[str, str]] = {}
        for name in ("beating", "lapsed", "released", "crashed", "retired", "alive"):
            path = write(
                SCOPED.replace(SCOPED_BUDGETS, AFFORDABLE).replace(
                    'name = "matrix-web"', f'name = "{LEASE_SLUG}-{name}"'
                )
            )
            opened = program.run(cls.harness.runtime, path)
            assert opened.ok, (name, opened.violations)
            cls.identifiers[name] = opened.facts["program_id"]
            cls.seed(name)

        cls.arrange_beating()
        cls.arrange_lapsed()
        cls.arrange_released()
        cls.arrange_crashed()
        cls.arrange_retired()
        cls.arrange_alive()

    @classmethod
    def tearDownClass(cls):
        cls.runtime.close()
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL app.purging = 'on'")
            cls.connection.execute(
                "DELETE FROM programs WHERE slug LIKE $1", (f"{LEASE_SLUG}-%",)
            )
        super().tearDownClass()

    # -- the scenarios ---------------------------------------------------------

    @classmethod
    def arrange_beating(cls):
        """A run that keeps saying it is here, twice, and is believed twice."""
        cls.claim("beating")
        cls.at_claim = cls.lease("beating")
        cls.first_beat = cls.beat("beating")
        cls.after_first = cls.lease("beating")
        cls.beat_moved_it = cls.scalar(
            "SELECT $2::timestamptz > $1::timestamptz",
            (cls.at_claim["task_lease"], cls.after_first["task_lease"]),
        )
        cls.second_beat = cls.beat("beating")
        cls.after_second = cls.lease("beating")
        # Whether the renewal accumulated or was set. Asked as one reading of
        # the server's clock against the row, because two beats that each added
        # a TTL would leave an hour on a thirty-minute Lease and nothing else
        # here would notice.
        cls.beat_is_bounded = cls.scalar(
            "SELECT bool_and(t.lease_expires_at <= now() + w.lease_ttl)"
            "  FROM tasks t CROSS JOIN scheduler_weights w"
            " WHERE w.active AND t.program_id = $1::uuid"
            "   AND t.lease_expires_at IS NOT NULL",
            (cls.identifiers["beating"],),
        )
        # The renewal as a non-event: `identity_leases.expires_at` is ignored
        # like `tasks.lease_expires_at`, so a beat writes a suppressed row and
        # not two Events per minute.
        cls.beat_events = cls.counted_events("beating", "identity_leases")
        cls.beat_suppressed = int(
            cls.scalar(
                "SELECT count(*) FROM suppressed_writes"
                " WHERE program_id = $1::uuid AND table_name = 'identity_leases'",
                (cls.identifiers["beating"],),
            )
        )

    @classmethod
    def arrange_lapsed(cls):
        """The Lease is already gone when the beat arrives."""
        cls.claim("lapsed")
        cls.lapse("lapsed")
        cls.expired_lease = cls.lease("lapsed")
        cls.refused_beat = cls.beat("lapsed")
        cls.after_refused = cls.lease("lapsed")

    @classmethod
    def arrange_released(cls):
        """Both halves given back, and given back again."""
        cls.claim("released")
        cls.released_once = cls.call("SELECT release_leases($1::uuid)", cls.holder("released"))
        cls.after_release = cls.lease("released")
        cls.released_twice = cls.call(
            "SELECT release_leases($1::uuid)", cls.holder("released")
        )
        cls.after_second_release = cls.lease("released")
        cls.release_events = cls.counted_events("released", "identity_leases")
        cls.release_unattributed = int(
            cls.scalar(
                "SELECT count(*) FROM events"
                " WHERE program_id = $1::uuid AND subject_table = 'identity_leases'"
                "   AND actor_kind IS DISTINCT FROM 'runtime'",
                (cls.identifiers["released"],),
            )
        )
        # Settled after the releases, because a Task left `claimed` with no
        # Lease is a row the standing check refuses -- correctly. Releasing is
        # not deciding what the Task becomes, and this is the caller deciding.
        cls.before_closure = cls.high_water("released")
        cls.released_closure = cls.call(
            "SELECT finish_task_attempt($1::uuid, 'error')", cls.holder("released")
        )
        # The other direction of the same question: the closing declares its own
        # cause before it calls the release, and everything the transaction
        # writes after that must still be about the run it named.
        cls.closure_causes = set(
            str(row["agent_run_id"])
            for row in cls.as_owner(
                "SELECT DISTINCT agent_run_id::text AS agent_run_id FROM events"
                " WHERE program_id = $1::uuid AND seq > $2",
                (cls.identifiers["released"], cls.before_closure),
            ).dicts()
        )

    @classmethod
    def arrange_crashed(cls):
        """An owner that stopped beating, and the recovery that finds out."""
        cls.claim("crashed")
        cls.under_test("crashed")
        cls.lapse("crashed")
        cls.before_recovery = cls.high_water("crashed")
        cls.recovered, cls.recovered_again = cls.twice("SELECT reconcile_leases()")
        # What the recovery said it was caused by. `release_leases` used to
        # declare a cause of its own, and a cause is transaction-local: the
        # loop's last dead run then stood as the reason for every Task the
        # sweep settled afterwards.
        cls.recovery_causes = int(
            cls.scalar(
                "SELECT count(*) FROM events"
                " WHERE program_id = $1::uuid AND seq > $2 AND agent_run_id IS NOT NULL",
                (cls.identifiers["crashed"], cls.before_recovery),
            )
        )
        cls.after_recovery = cls.lease("crashed")
        cls.recovered_hypothesis = str(
            cls.scalar(
                "SELECT status FROM hypotheses WHERE program_id = $1::uuid",
                (cls.identifiers["crashed"],),
            )
        )

    @classmethod
    def arrange_retired(cls):
        """The same crash on a Task with no attempts left."""
        cls.claim("retired")
        cls.as_owner(
            "UPDATE tasks SET attempts = (SELECT max_attempts FROM scheduler_weights"
            " WHERE active) WHERE program_id = $1::uuid",
            (cls.identifiers["retired"],),
        )
        cls.lapse("retired")
        cls.retired_by = cls.call("SELECT reconcile_leases()")
        cls.after_retirement = cls.lease("retired")
        # Terminal work stays terminal: a second pass over an abandoned Task
        # must not find it, and a third must not either.
        cls.retired_again = cls.call("SELECT reconcile_leases()")
        cls.after_second_pass = cls.lease("retired")

    @classmethod
    def arrange_alive(cls):
        """The Lease nothing may take, asked of both things that take Leases."""
        cls.claim("alive")
        cls.spared_by_reconcile = cls.call("SELECT reconcile_leases()")
        cls.spared_by_resume = cls.call(
            "SELECT resume_program($1::uuid)", (cls.identifiers["alive"],)
        )
        cls.after_resume = cls.lease("alive")
        # A second Task about the same Hypothesis, and therefore about the same
        # Identity. Without it the competition below proves only that a claimed
        # Task cannot be claimed twice; criterion 3 also says the Identity under
        # it cannot be taken, and that is a different Task being refused.
        # A second endpoint, because `tasks_live_dedup_idx` is what stops two
        # Tasks about the same subject and the same Hypothesis -- the Identity
        # is what these two share, and it has to be the only thing.
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            rival = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'endpoint', '', 'host', $2, 80, $3)",
                    (cls.identifiers["alive"], HOST, "endpoint:GET /rival"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO endpoints (entity_id, application_id, method, path_template)"
                " SELECT $1::uuid, e.application_id, 'GET', '/rival'"
                "   FROM endpoints e JOIN entities x ON x.id = e.entity_id"
                "  WHERE x.program_id = $2::uuid LIMIT 1",
                (rival, cls.identifiers["alive"]),
            )
            cls.connection.execute(
                "INSERT INTO tasks (program_id, kind, status, subject_entity_id,"
                " hypothesis_id, expected_information_gain, potential_impact)"
                " SELECT $1::uuid, 'hunt', 'pending', $2::uuid, h.id, 0.9, 0.9"
                "   FROM hypotheses h WHERE h.program_id = $1::uuid",
                (cls.identifiers["alive"], rival),
            )
        # The competing claim, made the way a second `rk run` makes it: a fresh
        # pass over the Program's own rows, and a claim off whatever it offers.
        cls.bind("alive")
        cls.competing_slate = cls.offer()
        cls.competing_claim = cls.claimed_label("SELECT claim_task()")
        cls.after_competition = cls.lease("alive")
        cls.rival_refusal = str(
            cls.scalar(
                "SELECT claimable_for(t, w) FROM tasks t CROSS JOIN scheduler_weights w"
                " WHERE w.active AND t.program_id = $1::uuid AND t.status = 'pending'",
                (cls.identifiers["alive"],),
            )
        )
        cls.identities_held = int(
            cls.scalar(
                "SELECT count(*) FROM identity_leases"
                " WHERE program_id = $1::uuid AND released_at IS NULL",
                (cls.identifiers["alive"],),
            )
        )

    # -- what the scenarios are built out of -----------------------------------

    @classmethod
    def seed(cls, name: str) -> None:
        """One hunt Task about one endpoint, with one Identity in its Hypothesis.

        One transaction, because a Hypothesis whose Identity did not commit with
        it is a Task whose Lease has nothing to hold.
        """
        program_id = cls.identifiers[name]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            application = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'application', '', 'host', $2, 80, $3)",
                    (program_id, HOST, f"application:{BASE_URL}"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO applications (entity_id, base_url, kind)"
                " VALUES ($1::uuid, $2, 'web')",
                (application, BASE_URL),
            )
            endpoint = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'endpoint', '', 'host', $2, 80, $3)",
                    (program_id, HOST, f"endpoint:GET {PATH}"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO endpoints (entity_id, application_id, method, path_template)"
                " VALUES ($1::uuid, $2::uuid, 'GET', $3)",
                (endpoint, application, PATH),
            )
            identity = str(
                cls.connection.execute(
                    "SELECT add_entity($1::uuid, 'identity', '', 'host', $2, 80, $3)",
                    (program_id, HOST, "identity:lease-holder"),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO identities (entity_id, program_id, slot_name, class)"
                " VALUES ($1::uuid, $2::uuid, 'lease-holder', 'anonymous')",
                (identity, program_id),
            )
            hypothesis = str(
                cls.connection.execute(
                    "INSERT INTO hypotheses (program_id, subject_entity_id,"
                    " identity_a_entity_id, property_class, statement, status)"
                    " VALUES ($1::uuid, $2::uuid, $3::uuid,"
                    " 'authorization.object_ownership', 'a leased hypothesis', 'testable')"
                    " RETURNING id::text",
                    (program_id, endpoint, identity),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO tasks (program_id, kind, status, subject_entity_id,"
                " hypothesis_id, expected_information_gain, potential_impact)"
                " VALUES ($1::uuid, 'hunt', 'pending', $2::uuid, $3::uuid, 0.5, 0.5)",
                (program_id, endpoint, hypothesis),
            )

    @classmethod
    def claim(cls, name: str) -> None:
        """One Task claimed, and the Agent run that now holds its Lease."""
        cls.bind(name)
        offered = cls.offer()
        assert offered, f"{name} offered nothing to claim"
        label = str(cls.claimed_label("SELECT claim_task()"))
        run = cls.scalar(
            "SELECT id::text FROM agent_runs WHERE program_id = $1::uuid AND label = $2",
            (cls.identifiers[name], label),
        )
        cls.runs[name] = (label, str(run))

    @classmethod
    def holder(cls, name: str) -> tuple[str]:
        """The Agent run holding this Program's Lease, as a parameter tuple."""
        return (cls.runs[name][1],)

    @classmethod
    def bind(cls, name: str):
        cls.runtime.execute(agent.BIND, (cls.identifiers[name],))

    @classmethod
    def offer(cls) -> tuple[dict[str, object], ...]:
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            cls.runtime.execute("SELECT rank_pass('runtime')")
            cls.runtime.execute("SELECT advance_lane_quota('runtime')")
            return cls.runtime.execute("SELECT * FROM offer_slate()").dicts()

    @classmethod
    def claimed_label(cls, sql: str, parameters: tuple = ()) -> object:
        """One statement as the runtime, in its own transaction, answer as sent."""
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            return cls.runtime.execute(sql, parameters).scalar()

    @classmethod
    def call(cls, sql: str, parameters: tuple = ()) -> dict:
        """The same, for the verbs that answer with a jsonb report.

        Every verb this ticket adds does, and so do the two it changed: what a
        Lease operation did is a set of counts, and a caller that had to read
        the rows back to find out would be re-deriving what the function knows.
        """
        return json.loads(str(cls.claimed_label(sql, parameters)))

    @classmethod
    def twice(cls, sql: str) -> tuple[object, object]:
        """The same statement twice inside one transaction.

        Which is a question about the reconciler and not about the fixture: the
        sweep this replaced built a `TEMP TABLE ... ON COMMIT DROP`, so a second
        call before the commit raised rather than finding nothing to do.
        """
        with cls.runtime.transaction():
            cls.runtime.execute("SELECT set_actor('runtime', 'selftest')")
            first = cls.runtime.execute(sql).scalar()
            second = cls.runtime.execute(sql).scalar()
        return json.loads(str(first)), json.loads(str(second))

    @classmethod
    def beat(cls, name: str) -> dict:
        return cls.call("SELECT heartbeat_leases($1::uuid)", cls.holder(name))

    @classmethod
    def lapse(cls, name: str):
        """What a process that stopped beating leaves behind.

        Both halves, from one reading of the clock, because that is the state a
        Lease that ran out reaches -- and because a Task Lease pushed back on
        its own would be the disagreement the standing check exists to refuse.
        """
        program_id = cls.identifiers[name]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            cls.connection.execute(
                "UPDATE tasks SET lease_expires_at = now() - interval '1 minute'"
                " WHERE program_id = $1::uuid AND lease_expires_at IS NOT NULL",
                (program_id,),
            )
            cls.connection.execute(
                "UPDATE identity_leases SET expires_at = now() - interval '1 minute'"
                " WHERE program_id = $1::uuid AND released_at IS NULL",
                (program_id,),
            )

    @classmethod
    def under_test(cls, name: str):
        """The Hypothesis moved to `testing`, which only a Receipt may do.

        Needed because recovery has to put it back, and a Hypothesis that never
        entered `testing` would let that arm of the reconciler pass untested.
        """
        program_id = cls.identifiers[name]
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            receipt = str(
                cls.connection.execute(
                    "INSERT INTO receipts (program_id, lane, decision, reason,"
                    " ts_arrival, scope_class, scope_version, host)"
                    " VALUES ($1::uuid, 'agent', 'blocked', 'self test', now(),"
                    " 'target', 1, $2) RETURNING id::text",
                    (program_id, HOST),
                ).scalar()
            )
            cls.connection.execute(
                "INSERT INTO hypothesis_transitions (program_id, hypothesis_id,"
                " from_status, to_status, actor_kind, receipt_id, rationale)"
                " SELECT $1::uuid, id, 'testable', 'testing', 'runtime', $2::uuid,"
                " 'self test' FROM hypotheses WHERE program_id = $1::uuid",
                (program_id, receipt),
            )

    @classmethod
    def high_water(cls, name: str) -> int:
        """The last Event this Program had written, so a later read is a delta."""
        return int(
            str(
                cls.scalar(
                    "SELECT coalesce(max(seq), 0) FROM events WHERE program_id = $1::uuid",
                    (cls.identifiers[name],),
                )
            )
        )

    @classmethod
    def as_owner(cls, sql: str, parameters: tuple = ()):
        with cls.connection.transaction():
            cls.connection.execute("SET LOCAL ROLE rk2_owner")
            cls.connection.execute("SELECT set_actor('runtime', 'selftest')")
            return cls.connection.execute(sql, parameters)

    @classmethod
    def scalar(cls, sql: str, parameters: tuple = ()) -> object:
        return cls.as_owner(sql, parameters).scalar()

    @classmethod
    def lease(cls, name: str) -> dict[str, object]:
        """Both halves of the Lease and the Task under it, in one reading.

        One row and one statement, because the whole question here is whether
        two columns agree, and two statements would be two clocks of this
        test's own.
        """
        [row] = cls.as_owner(
            "SELECT t.status, t.attempts, t.lease_expires_at AS task_lease,"
            "       l.expires_at AS identity_lease, l.released_at,"
            "       a.finished_at, a.stop_reason,"
            "       t.lease_expires_at IS NOT DISTINCT FROM l.expires_at AS agree"
            "  FROM tasks t"
            "  JOIN agent_runs a ON a.id = $2::uuid AND a.task_id = t.id"
            "  LEFT JOIN identity_leases l ON l.holder_agent_run_id = a.id"
            " WHERE t.program_id = $1::uuid",
            (cls.identifiers[name], cls.runs[name][1]),
        ).dicts()
        return dict(row)

    @classmethod
    def counted_events(cls, name: str, table: str) -> dict[str, int]:
        """How many Events of each type this Program's rows of `table` produced."""
        return {
            str(row["type"]): int(str(row["n"]))
            for row in cls.as_owner(
                "SELECT type, count(*) AS n FROM events"
                " WHERE program_id = $1::uuid AND subject_table = $2"
                " GROUP BY type",
                (cls.identifiers[name], table),
            ).dicts()
        }

    # -- criterion 1: one transaction writes all three, against database time --

    def test_the_claim_wrote_both_halves_from_one_reading_of_the_clock(self):
        self.assertEqual(True, self.at_claim["agree"])

    def test_the_claim_leased_the_identity_to_the_run_it_opened(self):
        self.assertEqual(
            (None, None), (self.at_claim["released_at"], self.at_claim["finished_at"])
        )
        self.assertEqual("claimed", self.at_claim["status"])

    def test_the_expiry_is_the_ttl_the_weights_declare(self):
        # Asked of the row rather than of a report, and of the Program nothing
        # renewed: an expiry that did not come from `claimed_at + lease_ttl`
        # would still look like a timestamp half an hour out to anything
        # comparing it with `now()`.
        self.assertEqual(
            True,
            self.scalar(
                "SELECT bool_and(t.claimed_at + w.lease_ttl = t.lease_expires_at)"
                "  FROM tasks t CROSS JOIN scheduler_weights w"
                " WHERE w.active AND t.program_id = $1::uuid",
                (self.identifiers["alive"],),
            ),
        )

    # -- criterion 2: one heartbeat, and no disagreement ----------------------

    def test_one_beat_moves_both_halves_to_the_same_moment(self):
        self.assertEqual(True, self.first_beat["beat"])
        self.assertEqual(1, self.first_beat["identity_leases"])
        self.assertEqual(True, self.after_first["agree"])

    def test_the_beat_moved_the_lease_forward(self):
        self.assertEqual(True, self.beat_moved_it)

    def test_beating_twice_renews_rather_than_accumulates(self):
        self.assertEqual(True, self.second_beat["beat"])
        self.assertEqual(True, self.after_second["agree"])
        self.assertEqual(True, self.beat_is_bounded)

    def test_a_renewal_is_a_non_event_on_both_halves_of_the_lease(self):
        # `tasks.lease_expires_at` has been an ignored column since 014 and
        # `identity_leases.expires_at` is one now, so two beats produce the one
        # Event the claim made and no others. Silence and not absence: the
        # suppressed rows are what let the integrity check tell this from a
        # trigger somebody disabled.
        self.assertEqual({"identity_lease.created": 1}, self.beat_events)
        self.assertEqual(2, self.beat_suppressed)

    def test_a_lapsed_lease_is_reported_rather_than_renewed(self):
        self.assertEqual(False, self.refused_beat["beat"])
        self.assertEqual("the task lease has lapsed", self.refused_beat["reason"])
        self.assertEqual(0, self.refused_beat["identity_leases"])

    def test_a_refused_beat_leaves_the_identity_lease_where_it_was(self):
        # The half that matters: a beat that renewed the Identity under a dead
        # Task Lease is the disagreement CONTEXT.md forbids, and it is the one
        # a caller retrying a failed heartbeat would produce.
        self.assertEqual(
            self.expired_lease["identity_lease"], self.after_refused["identity_lease"]
        )
        self.assertEqual(self.expired_lease["task_lease"], self.after_refused["task_lease"])

    # -- criterion 3: nothing else may take what a live run holds -------------

    def test_the_restart_left_a_live_run_holding_both_halves(self):
        self.assertEqual(1, self.spared_by_resume["tasks_left_to_live_owners"])
        self.assertEqual(0, self.spared_by_resume["tasks_unclaimed"])
        self.assertEqual(0, self.spared_by_resume["agent_runs_aborted"])
        self.assertEqual(0, self.spared_by_resume["leases_released"])
        self.assertEqual("claimed", self.after_resume["status"])
        self.assertEqual(None, self.after_resume["released_at"])

    def test_a_competing_claim_gets_nothing(self):
        # Not a refusal: a Program whose only Task is held offers an empty
        # slate, and asking for nothing off one is the queue being busy rather
        # than an error. What matters is that the claim came back empty on a
        # Program that a second `rk run` used to be able to empty first.
        self.assertEqual((), self.competing_slate)
        self.assertEqual(None, self.competing_claim)

    def test_the_competing_claim_left_the_lease_exactly_as_it_found_it(self):
        self.assertEqual(self.after_resume, self.after_competition)

    def test_the_identity_under_a_live_lease_refuses_a_second_task_too(self):
        # The other half of criterion 3, and the one an empty slate cannot
        # show: a Task nobody has claimed, ready in every other respect, and
        # refused for the Identity its Hypothesis names being held elsewhere.
        self.assertEqual("identity_held", self.rival_refusal)
        self.assertEqual(1, self.identities_held)

    # -- criterion 4: release, twice, and attributed --------------------------

    def test_the_release_gives_both_halves_back(self):
        self.assertEqual(True, self.released_once["task_lease_released"])
        self.assertEqual(1, self.released_once["identity_leases"])
        self.assertEqual(None, self.after_release["task_lease"])
        self.assertNotEqual(None, self.after_release["released_at"])

    def test_a_second_release_releases_nothing_and_says_so(self):
        self.assertEqual(False, self.released_twice["task_lease_released"])
        self.assertEqual(0, self.released_twice["identity_leases"])
        self.assertEqual(self.after_release, self.after_second_release)

    def test_every_lease_event_names_who_wrote_it(self):
        self.assertEqual(
            {"identity_lease.created": 1, "identity_lease.updated": 1},
            self.release_events,
        )
        self.assertEqual(0, self.release_unattributed)

    def test_the_closing_finds_the_leases_already_given_back(self):
        self.assertEqual(0, self.released_closure["leases_released"])
        self.assertEqual("pending", self.released_closure["task_status"])

    def test_the_release_keeps_the_cause_its_caller_declared(self):
        # A shared verb declaring its own cause would overwrite the closing's,
        # and a cause is transaction-local: every row the closing settles after
        # the release would then name whatever the release last said.
        self.assertEqual({self.runs["released"][1]}, self.closure_causes)

    def test_reconciliation_attributes_nothing_to_the_run_it_ended(self):
        self.assertEqual(0, self.recovery_causes)

    # -- criterion 5: reconciliation, and what it declines to touch -----------

    def test_reconciliation_recovers_what_an_expired_owner_left(self):
        self.assertEqual(
            {
                "tasks_left_to_live_owners": 0,
                "tasks_returned": 1,
                "tasks_retired": 0,
                "runs_aborted": 1,
                "leases_released": 1,
                "hypotheses_returned_to_testable": 1,
            },
            self.recovered,
        )

    def test_a_second_reconciliation_in_the_same_transaction_finds_nothing(self):
        self.assertEqual(
            {
                "tasks_left_to_live_owners": 0,
                "tasks_returned": 0,
                "tasks_retired": 0,
                "runs_aborted": 0,
                "leases_released": 0,
                "hypotheses_returned_to_testable": 0,
            },
            self.recovered_again,
        )

    def test_recovery_released_both_halves_and_closed_the_run(self):
        self.assertEqual(None, self.after_recovery["task_lease"])
        self.assertNotEqual(None, self.after_recovery["released_at"])
        self.assertEqual("aborted", self.after_recovery["stop_reason"])

    def test_the_hypothesis_under_a_recovered_task_is_testable_again(self):
        self.assertEqual("testable", self.recovered_hypothesis)

    def test_reconciliation_reports_a_live_owner_rather_than_recovering_it(self):
        self.assertEqual(
            {
                "tasks_left_to_live_owners": 1,
                "tasks_returned": 0,
                "tasks_retired": 0,
                "runs_aborted": 0,
                "leases_released": 0,
                "hypotheses_returned_to_testable": 0,
            },
            self.spared_by_reconcile,
        )

    def test_no_reading_role_can_reach_the_reconciler(self):
        # Criterion 5's second half, as a privilege rather than as a promise.
        # The textual arm of the standing check says no function calls it; this
        # says no role that only reads can.
        self.assertEqual(
            [(False, False, True)],
            [
                (bool(row[0]), bool(row[1]), bool(row[2]))
                for row in self.connection.execute(
                    "SELECT has_function_privilege('rk2_state', $1, 'EXECUTE'),"
                    "       has_function_privilege('rk2_proxy', $1, 'EXECUTE'),"
                    "       has_function_privilege('rk2_runtime', $1, 'EXECUTE')",
                    ("reconcile_leases()",),
                ).rows
            ],
        )

    # -- criterion 6: what comes back, and what stays gone --------------------

    def test_the_recovered_task_is_pending_with_the_attempt_it_spent(self):
        # One attempt, which `claim_task` counted and a child was started
        # against. A recovery that gave it back would loop forever on work that
        # fails the same way each time; one that spent a second would retire a
        # Task for having crashed once.
        self.assertEqual("pending", self.after_recovery["status"])
        self.assertEqual(1, int(str(self.after_recovery["attempts"])))

    def test_a_task_with_no_attempts_left_is_retired_rather_than_returned(self):
        self.assertEqual(1, self.retired_by["tasks_retired"])
        self.assertEqual(0, self.retired_by["tasks_returned"])
        self.assertEqual("abandoned", self.after_retirement["status"])

    def test_terminal_work_stays_terminal(self):
        self.assertEqual(0, self.retired_again["tasks_retired"])
        self.assertEqual(0, self.retired_again["tasks_returned"])
        self.assertEqual(self.after_retirement, self.after_second_pass)

    # -- the invariant ---------------------------------------------------------

    def test_the_standing_check_is_registered_and_holds(self):
        [registered] = self.connection.execute(
            "SELECT count(*) FROM standing_checks WHERE name = 'lease_liveness'"
        ).rows
        [[problems, detail]] = self.connection.execute(
            "SELECT problems, detail FROM run_standing_checks()"
            " WHERE name = 'lease_liveness'"
        ).rows

        self.assertEqual(1, int(registered[0]))
        self.assertEqual((0, ""), (int(problems), str(detail)))


if __name__ == "__main__":
    unittest.main()
