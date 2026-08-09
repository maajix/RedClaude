"""What `rk db dump` and `rk db restore` do around the client programs.

The programs themselves are exercised in `test_database`, against a real
server. What is tested here is everything the commands promise on either side
of running one: which archive they will and will not write over, what they hand
the child, and what they leave on disk when the child fails.
"""

import subprocess
import unittest
from unittest import mock

from redkraken import backup, pg
from redkraken.outcome import BACKUP_FAILED, INVALID_CONFIGURATION
from tests.fixtures import scratch


def settings(**changes: object) -> pg.Settings:
    base = pg.Settings(host="127.0.0.1", port=5432, database="rk2", user="rk2_migrate", password="pw")
    return base.replace(**changes) if changes else base


def failed(returncode: int = 1, stderr: str = "connection refused") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["pg_dump"], returncode=returncode, stderr=stderr, stdout="")


class ArchiveTest(unittest.TestCase):
    """The destination, which is the one thing a dump can destroy."""

    def setUp(self):
        self.target = scratch() / "rk2.dump"
        self.patched = mock.patch.multiple(
            backup, _binary=mock.DEFAULT, _version=mock.DEFAULT, _run=mock.DEFAULT
        )
        self.doubles = self.patched.start()
        self.addCleanup(self.patched.stop)
        self.doubles["_binary"].return_value = "/usr/bin/pg_dump"
        self.doubles["_version"].return_value = "pg_dump (PostgreSQL) 18.4"

    def dump(self, outcome):
        def run(binary, arguments, target, timeout):
            # What the real program does before it connects, which is why a
            # failure leaves something at the destination to clean up.
            self.target.write_bytes(b"PGDMP\x00partial")
            return outcome

        self.doubles["_run"].side_effect = run
        return backup.dump(settings(), self.target)

    def test_an_archive_that_was_written_is_reported_with_its_digest(self):
        report = self.dump(subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout=""))

        self.assertTrue(report.ok, report.violations)
        self.assertEqual(len(b"PGDMP\x00partial"), report.facts["bytes"])
        self.assertEqual(64, len(report.facts["sha256"]))

    def test_a_failed_dump_leaves_nothing_at_the_destination(self):
        # Otherwise the retry meets "already exists" and stops with a
        # configuration error, naming the wrong problem for good.
        report = self.dump(failed())

        self.assertEqual([BACKUP_FAILED], [item.code for item in report.violations])
        self.assertFalse(self.target.exists())

    def test_a_dump_that_could_not_be_run_leaves_nothing_either(self):
        report = self.dump("pg_dump did not finish within 3600 seconds")

        self.assertEqual([BACKUP_FAILED], [item.code for item in report.violations])
        self.assertFalse(self.target.exists())

    def test_the_same_destination_can_be_dumped_to_after_a_failure(self):
        self.dump(failed())

        report = self.dump(subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout=""))

        self.assertTrue(report.ok, report.violations)

    def test_an_archive_that_exists_is_never_written_over(self):
        self.target.write_bytes(b"an earlier archive")

        report = self.dump(subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout=""))

        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in report.violations])
        self.assertEqual(b"an earlier archive", self.target.read_bytes())


class ChildTest(unittest.TestCase):
    """What the client program is told, and how."""

    def test_the_credential_travels_in_the_environment_and_not_the_arguments(self):
        # An argument vector is world-readable in /proc for as long as the
        # process lives; the environment of a child is not.
        arguments = backup._connection_arguments(settings())
        environment = backup._environment(settings())

        self.assertNotIn("pw", " ".join(arguments))
        self.assertEqual("pw", environment["PGPASSWORD"])
        self.assertEqual(
            ["--host=127.0.0.1", "--port=5432", "--username=rk2_migrate", "--dbname=rk2"], arguments
        )

    def test_a_target_with_no_password_carries_none(self):
        self.assertNotIn("PGPASSWORD", backup._environment(settings(password=None)))

    def test_a_sub_second_budget_does_not_become_no_budget(self):
        # libpq reads PGCONNECT_TIMEOUT=0 as "wait indefinitely", so a truncated
        # half-second budget would be the opposite of what was asked for.
        self.assertEqual("1", backup._environment(settings(connect_timeout=0.5))["PGCONNECT_TIMEOUT"])
        self.assertEqual("10", backup._environment(settings(connect_timeout=10.0))["PGCONNECT_TIMEOUT"])

    def test_the_extension_provisioning_installs_is_left_out_of_the_archive(self):
        # `vector` is not a trusted extension, so restoring it is superuser work
        # and the restore connection is deliberately not one.
        self.assertEqual(("vector",), backup.PROVISIONED_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
