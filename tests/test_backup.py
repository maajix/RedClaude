"""What `rk db dump` and `rk db restore` do around the client programs.

The programs themselves are exercised in `test_database`, against a real
server. What is tested here is everything the commands promise on either side
of running one: which archive they will and will not write over, what they hand
the child, what they carry beside the archive, and what they leave on disk when
the child fails.
"""

import subprocess
import tarfile
import unittest
from dataclasses import dataclass, field
from unittest import mock

from redkraken import backup, pg
from redkraken.outcome import BACKUP_FAILED, INVALID_CONFIGURATION, Ledger
from tests.fixtures import scratch


@dataclass
class Rows:
    """One statement's answer, in the two shapes a caller here reads it in."""

    rows: list = field(default_factory=list)

    def scalar(self) -> object:
        return self.rows[0][0]


@dataclass
class Answers:
    """A connection answering the only question a dump asks the database.

    `backup` reaches a server for one fact -- which hashes the store has to
    hold -- so a double that answers those two statements is the whole surface,
    and using one keeps every case here runnable with no server at all.
    """

    referenced: tuple[str, ...] = ()
    records: bool = True

    def __enter__(self) -> "Answers":
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, sql: str, parameters: tuple = ()) -> Rows:
        if "to_regclass" in sql:
            return Rows([(self.records,)])
        return Rows([(one,) for one in self.referenced])


def settings(**changes: object) -> pg.Settings:
    base = pg.Settings(host="127.0.0.1", port=5432, database="rk2", user="rk2_migrate", password="pw")
    return base.replace(**changes) if changes else base


def failed(returncode: int = 1, stderr: str = "connection refused") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["pg_dump"], returncode=returncode, stderr=stderr, stdout="")


class ArchiveTest(unittest.TestCase):
    """The destination, which is the one thing a dump can destroy."""

    def setUp(self):
        self.target = scratch() / "rk2.dump"
        self.patched = mock.patch.multiple(backup, _binary=mock.DEFAULT, _version=mock.DEFAULT)
        self.doubles = self.patched.start()
        self.addCleanup(self.patched.stop)
        self.doubles["_binary"].return_value = "/usr/bin/pg_dump"
        self.doubles["_version"].return_value = "pg_dump (PostgreSQL) 18.4"

    def dump(self, outcome, *, store=None, referenced=()):
        def run(binary, arguments, *, environment, timeout, stdin=None):
            # What the real program does before it connects, which is why a
            # failure leaves something at the destination to clean up.
            self.target.write_bytes(b"PGDMP\x00partial")
            return outcome

        # Scoped to the one call rather than to the test case: `child.run` is
        # shared with the vault, and a patch left standing for a whole class is
        # one another module's tests can end up running inside.
        with mock.patch.object(backup.child, "run", side_effect=run):
            with mock.patch.object(
                backup.migrate, "open_connection", return_value=Answers(referenced)
            ):
                return backup.dump(settings(), self.target, store=store)

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


class StoreTest(unittest.TestCase):
    """The half of a backup that is not in the database.

    An archive of the rows alone restores evidence references that name files
    nobody has, which is the failure these cases are about: a dump either
    carries the bytes or says which ones it would have left behind.
    """

    def setUp(self):
        self.target = scratch() / "rk2.dump"
        self.root = scratch() / "store"
        self.root.mkdir()
        self.patched = mock.patch.multiple(backup, _binary=mock.DEFAULT, _version=mock.DEFAULT)
        self.doubles = self.patched.start()
        self.addCleanup(self.patched.stop)
        self.doubles["_binary"].return_value = "/usr/bin/pg_dump"
        self.doubles["_version"].return_value = "pg_dump (PostgreSQL) 18.4"

    def file(self, data: bytes) -> str:
        """One artifact, filed the way the store files one: under its hash."""
        sha256 = backup.hashlib.sha256(data).hexdigest()
        path = self.root / sha256[:2] / sha256
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return sha256

    def dump(self, *, store=None, referenced=()):
        def run(binary, arguments, *, environment, timeout, stdin=None):
            self.target.write_bytes(b"PGDMP\x00archive")
            return subprocess.CompletedProcess(args=[], returncode=0, stderr="", stdout="")

        with mock.patch.object(backup.child, "run", side_effect=run):
            with mock.patch.object(
                backup.migrate, "open_connection", return_value=Answers(referenced)
            ):
                return backup.dump(settings(), self.target, store=store)

    def test_the_store_travels_beside_the_archive_under_its_name(self):
        sha256 = self.file(b"the bytes a restored row points at")

        report = self.dump(store=self.root, referenced=(sha256,))

        self.assertTrue(report.ok, report.violations)
        self.assertEqual(str(backup.beside(self.target)), report.facts["store"])
        self.assertEqual(1, report.facts["stored"])
        self.assertEqual(64, len(report.facts["store_sha256"]))
        with tarfile.open(backup.beside(self.target)) as bundle:
            self.assertEqual([f"{sha256[:2]}/{sha256}"], bundle.getnames())

    def test_a_database_that_references_bytes_and_a_dump_with_no_store_is_refused(self):
        # The finding this pair of files is about: the archive alone restores
        # rows whose every evidence reference names a file that is not there.
        report = self.dump(referenced=("a" * 64,))

        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in report.violations])
        self.assertIn("references 1 artifact(s)", report.violations[0].detail)
        self.assertFalse(self.target.exists())

    def test_a_database_that_references_nothing_is_a_whole_backup_without_one(self):
        report = self.dump()

        self.assertTrue(report.ok, report.violations)
        self.assertEqual(0, report.facts["stored"])
        self.assertFalse(backup.beside(self.target).exists())

    def test_a_referenced_artifact_the_store_does_not_hold_stops_the_dump(self):
        # Learning it here costs one dump. Learning it at the restore costs the
        # backup, because by then the database it was taken from is why anyone
        # is restoring.
        report = self.dump(store=self.root, referenced=("b" * 64,))

        self.assertEqual([BACKUP_FAILED], [item.code for item in report.violations])
        self.assertIn("bbbbbbbbbbbb", report.violations[0].detail)
        self.assertFalse(self.target.exists())
        self.assertFalse(backup.beside(self.target).exists())

    def test_bytes_a_put_never_finished_writing_are_not_carried(self):
        # `Store.put` writes under a leading dot and renames, so a dotted name
        # is bytes no hash names -- and a restore that received them would file
        # a name the store answers `holds` for and `load` cannot verify.
        sha256 = self.file(b"complete")
        (self.root / sha256[:2] / f".{sha256}.4242").write_bytes(b"half")

        report = self.dump(store=self.root, referenced=(sha256,))

        self.assertEqual(1, report.facts["stored"])

    def test_a_store_archive_that_exists_is_never_written_over(self):
        backup.beside(self.target).write_bytes(b"an earlier store")

        report = self.dump(store=self.root)

        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in report.violations])
        self.assertEqual(b"an earlier store", backup.beside(self.target).read_bytes())

    def test_a_store_that_is_not_there_is_refused_rather_than_packed_empty(self):
        report = self.dump(store=self.root / "moved", referenced=())

        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in report.violations])
        self.assertIn("not a readable artifact store", report.violations[0].detail)

    def test_what_was_packed_comes_back_where_the_restore_was_pointed(self):
        sha256 = self.file(b"the bytes a restored row points at")
        self.dump(store=self.root, referenced=(sha256,))
        restored = scratch() / "restored"

        ledger = Ledger()
        answer = backup._unpack(ledger, self.target, restored)

        self.assertEqual({}, answer)
        self.assertEqual([], ledger.violations)
        self.assertEqual(
            b"the bytes a restored row points at", (restored / sha256[:2] / sha256).read_bytes()
        )

    def test_a_restore_with_no_store_half_says_so_and_leaves_it_to_the_gate(self):
        # Not a failure here. Whether the bytes were needed is the gate's
        # question a moment later, and it is the one that can answer it.
        ledger = Ledger()

        answer = backup._unpack(ledger, self.target, scratch() / "restored")

        self.assertEqual({}, answer)
        self.assertEqual([], ledger.violations)
        self.assertIn("does not exist", ledger.assertions[0].detail)


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
