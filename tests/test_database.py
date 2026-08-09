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
that `rk run` opens one Program and afterwards resumes that one. It is the only
case here that commits, because what survives the transaction is its subject.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from redkraken import backup, integrity, migrate, pg, program
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INTEGRITY_FAILED,
    EXIT_INVALID_CONFIGURATION,
    EXIT_OK,
    Report,
)
from tests.fixtures import VALID, scratch, write


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
    Control("standing:capability_receipt_fence", "GRANT INSERT ON receipts TO rk2_proxy"),
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
