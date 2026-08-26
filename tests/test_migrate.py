"""The corpus, the rules it has to satisfy, and the plan a run would follow.

Everything here runs without a database. What a migration does to a server is
tested in `test_database`, against a real one; what the runner refuses before it
opens a connection is tested here, because that refusal is the reason a bad
corpus can never leave a database half-applied.
"""

import hashlib
import re
import unittest
from pathlib import Path

from redkraken import migrate
from redkraken.outcome import INVALID_CORPUS, SCHEMA_DRIFT, Ledger
from tests.fixtures import scratch


#: The Lane vocabulary CONTEXT.md closes at three values. The prototype widened
#: it to five, and citability then turned on the wrong question.
LANES = {"agent", "replay", "proxy_internal"}

_LANE_EQUALITY = re.compile(r"\blane\s*(?:=|<>|!=)\s*'([a-z_-]+)'")
_LANE_MEMBERSHIP = re.compile(r"\blane\s+IN\s*\(([^)]*)\)", re.IGNORECASE)


def corpus(*files: tuple[str, str]) -> Path:
    directory = scratch()
    for name, text in files:
        (directory / name).write_text(text, encoding="utf-8")
    return directory


class CorpusTest(unittest.TestCase):
    """The corpus that ships inside the package."""

    @classmethod
    def setUpClass(cls):
        cls.migrations, cls.refusals = migrate.load()

    def test_the_shipped_corpus_satisfies_its_own_rules(self):
        self.assertEqual((), self.refusals)
        self.assertTrue(self.migrations)

    def test_the_corpus_ships_inside_the_package(self):
        self.assertEqual(Path(migrate.__file__).resolve().parent / "migrations", migrate.CORPUS)
        self.assertTrue(all(item.path.parent == migrate.CORPUS for item in self.migrations))

    def test_identity_is_the_filename_and_order_is_that_identity(self):
        identities = [item.identity for item in self.migrations]
        self.assertEqual([item.path.name[: -len(".sql")] for item in self.migrations], identities)
        self.assertEqual(sorted(identities), identities)
        self.assertEqual(len(set(identities)), len(identities))

    def test_the_numbered_corpus_is_contiguous_and_frozen_where_it_says(self):
        numbers = [item.number for item in self.migrations if item.number is not None]
        self.assertEqual(list(range(1, len(numbers) + 1)), numbers)
        self.assertEqual(migrate.FROZEN_NUMBER, max(numbers))

    def test_no_migration_carries_transaction_control_or_role_ddl(self):
        # Both rules are enforced on every file with no exemption, which is only
        # possible because the promotion removed the last guarded CREATE ROLE.
        for item in self.migrations:
            with self.subTest(item.identity):
                self.assertIsNone(migrate.TRANSACTION_CONTROL.search(item.sql))
                self.assertIsNone(migrate.ROLE_DDL.search(item.sql))

    def test_one_lane_vocabulary_of_three_causing_parties(self):
        found = set()
        for item in self.migrations:
            found.update(_LANE_EQUALITY.findall(item.sql))
            for group in _LANE_MEMBERSHIP.findall(item.sql):
                found.update(value.strip().strip("'") for value in group.split(","))
        self.assertTrue(found)
        self.assertEqual(set(), found - LANES, "a Lane value outside the three causing parties")

    def test_control_and_transport_are_a_purpose_rather_than_a_lane(self):
        # RK-REG-007: the prototype spent two Lane values on questions Lane does
        # not answer. They are a separate column now, so the check is that the
        # words appear as a purpose and never as a lane.
        purposes = set()
        for item in self.migrations:
            purposes.update(re.findall(r"\bpurpose\s*=\s*'([a-z_]+)'", item.sql))
        self.assertIn("control_plane", purposes)
        self.assertIn("transport_measurement", purposes)

    def test_only_the_two_self_emitting_verbs_set_their_causing_event_inside_the_database(self):
        # Every other write takes its cause from the connection helper, which
        # sets it once for the transaction. `open_task` is the argued exception:
        # it names an Event it emits itself as the cause of the Task it then
        # opens, and it saves and restores what it found. The exception holds
        # `retire_task` is the same argued shape: it emits task.retired and the
        # Task update names that event. Both save and restore the prior cause;
        # no ordinary writer is allowed to add a third setter.
        #
        # The third file is not a third setter. Ticket 191 gives `open_task` a
        # fifth argument, and `CREATE OR REPLACE` restates the whole body --
        # this line with it. So the number of files carrying the string grew
        # while the number of verbs setting the cause did not. That is the rule
        # the list was always a proxy for, and the loop below is the rule
        # itself: appending a name to the list can no longer buy a third verb.
        setters = [
            item.identity
            for item in self.migrations
            if "set_config('app.caused_by_event_id'" in item.sql
        ]
        self.assertEqual(
            [
                "20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope",
                "20261019T000000Z__an_undispatchable_task_ends_itself",
                "20261120T000000Z__both_states_or_the_measurement_is_half_a_measurement",
            ],
            setters,
        )
        for item in self.migrations:
            for name, body in re.findall(
                r"CREATE OR REPLACE FUNCTION\s+(?:public\.)?(\w+)\s*\(.*?"
                r"\$(?:fn|function)\$(.*?)\$(?:fn|function)\$",
                item.sql,
                re.DOTALL,
            ):
                if "set_config('app.caused_by_event_id'" in body:
                    self.assertIn(
                        name,
                        ("open_task", "retire_task"),
                        f"{item.identity} sets the causing event inside {name}",
                    )

    def test_the_emitter_binds_the_actor_to_the_writing_transaction(self):
        # RK-REG-004: a session-wide actor context outlives the write it
        # describes, so the emitter compares it against the current transaction.
        text = "".join(item.sql for item in self.migrations)
        self.assertIn("app.actor_xact", text)
        self.assertIn("CREATE FUNCTION set_actor(", text)


class LoadTest(unittest.TestCase):
    """What the runner refuses before it opens a connection."""

    def refusal(self, *files: tuple[str, str]) -> str:
        migrations, refusals = migrate.load(corpus(*files))
        self.assertEqual((), migrations)
        self.assertTrue(refusals)
        self.assertEqual({INVALID_CORPUS}, {item.code for item in refusals})
        return " ".join(item.detail for item in refusals)

    def test_both_filename_forms_are_accepted(self):
        migrations, refusals = migrate.load(
            corpus(("0001_first.sql", "SELECT 1;"), ("20260809T120000Z__second.sql", "SELECT 2;"))
        )

        self.assertEqual((), refusals)
        self.assertEqual(["0001_first", "20260809T120000Z__second"], [i.identity for i in migrations])

    def test_a_filename_matching_neither_form_is_refused(self):
        self.assertIn("matches neither", self.refusal(("fix-the-thing.sql", "SELECT 1;")))

    def test_a_number_above_the_frozen_one_is_refused(self):
        detail = self.refusal((f"{migrate.FROZEN_NUMBER + 1:04d}_next.sql", "SELECT 1;"))

        self.assertIn("frozen", detail)
        self.assertIn("YYYYMMDDTHHMMSSZ", detail)

    def test_two_files_claiming_one_number_are_refused(self):
        # The collision that a merge produces and a directory listing hides: two
        # identities, one number, applied in an order nobody chose.
        detail = self.refusal(("0001_one.sql", "SELECT 1;"), ("0001_other.sql", "SELECT 2;"))

        self.assertIn("two files claim one migration number", detail)

    def test_transaction_control_is_refused(self):
        detail = self.refusal(("0001_first.sql", "BEGIN;\nSELECT 1;\nCOMMIT;\n"))

        self.assertIn("transaction control", detail)

    def test_role_ddl_is_refused(self):
        detail = self.refusal(("0001_first.sql", "CREATE ROLE rk2_extra LOGIN;\n"))

        self.assertIn("role DDL", detail)

    def test_the_words_in_a_plpgsql_body_are_not_transaction_control(self):
        body = (
            "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $$\n"
            "BEGIN\n"
            "    -- COMMIT; in a comment is not a statement either\n"
            "    PERFORM 1;\n"
            "END $$;\n"
        )
        migrations, refusals = migrate.load(corpus(("0001_first.sql", body)))

        self.assertEqual((), refusals)
        self.assertEqual(1, len(migrations))

    def test_a_missing_corpus_is_refused_rather_than_read_as_empty(self):
        migrations, refusals = migrate.load(scratch() / "absent")

        self.assertEqual((), migrations)
        self.assertIn("missing", refusals[0].detail)

    def test_the_checksum_is_over_the_bytes_of_the_file(self):
        migrations, _ = migrate.load(corpus(("0001_first.sql", "SELECT 1;\n")))

        self.assertEqual(hashlib.sha256(b"SELECT 1;\n").hexdigest(), migrations[0].checksum)


class PlanTest(unittest.TestCase):
    """What a run would do, and the two things it refuses to do."""

    def setUp(self):
        self.migrations, _ = migrate.load(
            corpus(
                ("0001_first.sql", "SELECT 1;\n"),
                ("0002_second.sql", "SELECT 2;\n"),
                ("0003_third.sql", "SELECT 3;\n"),
            )
        )
        self.checksums = {item.identity: item.checksum for item in self.migrations}
        self.ledger = Ledger()

    def test_an_empty_database_has_everything_pending(self):
        pending = migrate.plan(self.ledger, self.migrations, {})

        self.assertEqual([], self.ledger.violations)
        self.assertEqual(["0001_first", "0002_second", "0003_third"], [i.identity for i in pending])

    def test_an_applied_migration_is_not_reapplied(self):
        recorded = {"0001_first": self.checksums["0001_first"]}

        pending = migrate.plan(self.ledger, self.migrations, recorded)

        self.assertEqual([], self.ledger.violations)
        self.assertEqual(["0002_second", "0003_third"], [i.identity for i in pending])

    def test_a_migration_whose_bytes_changed_after_it_was_applied_is_refused(self):
        recorded = {"0001_first": "0" * 64}

        migrate.plan(self.ledger, self.migrations, recorded)

        self.assertEqual([SCHEMA_DRIFT], [item.code for item in self.ledger.violations])
        self.assertIn("changed after it was applied", self.ledger.violations[0].detail)

    def test_an_applied_migration_whose_file_is_gone_is_refused(self):
        recorded = {"0000_removed": "0" * 64}

        migrate.plan(self.ledger, self.migrations, recorded)

        self.assertIn("its file is gone", self.ledger.violations[0].detail)

    def test_a_pending_migration_that_sorts_too_early_is_refused(self):
        # Out-of-order arrival: a migration merged from a branch authored in
        # parallel. Nothing is live yet, so the answer is to start from empty.
        recorded = {
            "0001_first": self.checksums["0001_first"],
            "0003_third": self.checksums["0003_third"],
        }

        migrate.plan(self.ledger, self.migrations, recorded)

        self.assertEqual([SCHEMA_DRIFT], [item.code for item in self.ledger.violations])
        self.assertIn("sorts before the applied 0003_third", self.ledger.violations[0].detail)


class PasswordTest(unittest.TestCase):
    def test_a_role_password_comes_from_the_environment_and_nowhere_else(self):
        found = migrate.passwords_from_environment(
            {"RK_PASSWORD_RK2_MIGRATE": "one", "RK_PASSWORD_RK2_RUNTIME": "two", "PGPASSWORD": "no"}
        )

        self.assertEqual({"rk2_migrate": "one", "rk2_runtime": "two"}, found)

    def test_an_empty_value_is_not_a_password(self):
        self.assertEqual({}, migrate.passwords_from_environment({"RK_PASSWORD_RK2_MIGRATE": ""}))

    def test_every_role_can_be_given_one(self):
        environment = {f"RK_PASSWORD_{role.name.upper()}": role.name for role in migrate.ROLES}

        found = migrate.passwords_from_environment(environment)

        self.assertEqual({role.name for role in migrate.ROLES}, set(found))


class RoleTest(unittest.TestCase):
    def test_the_catalogue_is_the_seven_the_schema_asserts(self):
        self.assertEqual(
            [
                "rk2_owner",
                "rk2_migrate",
                "rk2_restore",
                "rk2_runtime",
                "rk2_state",
                "rk2_human",
                "rk2_proxy",
            ],
            [role.name for role in migrate.ROLES],
        )

    def test_the_owner_is_the_one_role_that_cannot_be_connected_to(self):
        owners = [role for role in migrate.ROLES if not role.login]

        self.assertEqual([migrate.OWNER_ROLE], [role.name for role in owners])

    def test_only_the_two_schema_roles_are_members_of_the_owner(self):
        members = {role.name for role in migrate.ROLES if role.member_of == migrate.OWNER_ROLE}

        self.assertEqual({"rk2_migrate", "rk2_restore"}, members)

    def test_no_login_role_may_create_a_role(self):
        # A migration able to mint a role could grant itself rk2_human, and
        # membership of rk2_human is the only thing authorising a human actor.
        self.assertIn("NOCREATEROLE", migrate.LOGIN_ATTRIBUTES)
        self.assertIn("NOSUPERUSER", migrate.LOGIN_ATTRIBUTES)
        self.assertIn("NOBYPASSRLS", migrate.LOGIN_ATTRIBUTES)


if __name__ == "__main__":
    unittest.main()
