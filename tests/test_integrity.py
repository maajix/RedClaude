"""The gate's own logic, without a database under it.

What each check means is the corpus's business and is exercised against a real
server in `test_database`. What is tested here is the thing the gate adds: that
every family is run in one pass, that a caller asking for fewer says which ones
it ran, that a failure is reported as a refusal rather than as a number nobody
reads, and that a database with no checks in it is not mistaken for a database
that passed them.

One thing the gate answers is not a registered check and could not be: an
artifact's hash is a claim about bytes on a filesystem, and no SQL function can
open a file. So the store is verified here too, and the cases are about what it
costs -- a store nobody named must leave the report exactly as it was, and a
store that is named must be able to fail the gate.
"""

import unittest
from pathlib import Path

from redkraken import integrity, pg, seal, store
from redkraken.outcome import EXIT_INTEGRITY_FAILED, EXIT_OK, EXIT_SCHEMA_DRIFT, INTEGRITY_FAILED
from tests.fixtures import scratch


class FakeConnection:
    """Answers the statements the gate sends, and records that it did."""

    def __init__(
        self,
        *,
        baseline=(),
        roles=(),
        standing=(),
        installed=True,
        error=None,
        references=(),
        records_references=True,
        references_error=None,
        seals=(),
        records_seals=True,
    ):
        self.baseline = baseline
        self.roles = roles
        self.standing = standing
        self.installed = installed
        self.error = error
        self.references = references
        self.records_references = records_references
        self.references_error = references_error
        self.seals = seals
        self.records_seals = records_seals
        self.statements: list[str] = []
        self.parameters: list[tuple] = []

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.statements.append(" ".join(sql.split()))
        self.parameters.append(tuple(parameters))
        if "to_regprocedure" in sql:
            return pg.Result(columns=("ok",), rows=((self.installed,),))
        if "artifact_seal" in sql and "to_regclass" in sql:
            return pg.Result(columns=("ok",), rows=((self.records_seals,),))
        if "to_regclass" in sql:
            return pg.Result(columns=("ok",), rows=((self.records_references,),))
        if self.error is not None:
            raise self.error
        if integrity.BASELINE in sql:
            return pg.Result(columns=("check_name", "ok", "detail"), rows=tuple(self.baseline))
        if integrity.ROLE_CATALOGUE in sql:
            return pg.Result(columns=("check_name", "ok", "detail"), rows=tuple(self.roles))
        if integrity.STANDING in sql:
            return pg.Result(columns=("name", "problems", "detail"), rows=tuple(self.standing))
        if "FROM artifact_references" in sql:
            if self.references_error is not None:
                raise self.references_error
            return pg.Result(columns=("label", "sha256"), rows=tuple(self.references))
        if "FROM artifact_seal" in sql:
            if self.references_error is not None:
                raise self.references_error
            return pg.Result(
                columns=("sha256", "ciphertext_sha256", "alg", "nonce"), rows=tuple(self.seals)
            )
        raise AssertionError(f"unexpected statement: {sql}")


def failure(message: str = "42883: function does not exist") -> pg.DatabaseError:
    return pg.DatabaseError({"C": message.split(":")[0], "M": message.split(": ", 1)[1]})


class RunTest(unittest.TestCase):
    def test_every_family_is_run_in_one_pass(self):
        connection = FakeConnection(
            baseline=(("server_major", True, "18.4"),),
            roles=(("role_catalogue", True, "seven roles"),),
            standing=(("causal_attribution", 0, ""),),
        )

        checks = integrity.run(connection, ["0001_first"])

        self.assertEqual(
            [("baseline", "server_major"), ("roles", "role_catalogue"), ("standing", "causal_attribution")],
            [(check.family, check.name) for check in checks],
        )
        self.assertTrue(all(check.ok for check in checks))

    def test_the_expected_corpus_reaches_the_baseline_as_an_array(self):
        connection = FakeConnection()

        integrity.run(connection, ["0001_first", "0002_second"])

        self.assertIn(("{\"0001_first\",\"0002_second\"}",), connection.parameters)

    def test_a_caller_may_run_fewer_families_than_the_gate_holds(self):
        # The role catalogue is the runner's, so a command that connects as the
        # runtime asks for the other two. The point of asserting the statement
        # rather than the answer is that the privilege is only not needed if the
        # query is never sent.
        connection = FakeConnection(
            baseline=(("server_major", True, "18.4"),),
            roles=(("role_catalogue", True, "seven roles"),),
            standing=(("causal_attribution", 0, ""),),
        )

        checks = integrity.run(connection, None, integrity.RUNTIME_FAMILIES)

        self.assertEqual(["baseline", "standing"], [check.family for check in checks])
        self.assertFalse([sql for sql in connection.statements if integrity.ROLE_CATALOGUE in sql])

    def test_a_standing_check_reports_the_rows_it_found(self):
        connection = FakeConnection(standing=(("rls_coverage", 2, "receipts; findings"),))

        check = integrity.run(connection)[0]

        self.assertFalse(check.ok)
        self.assertEqual("standing:rls_coverage", check.source)
        self.assertIn("2 problem(s)", check.detail)
        self.assertIn("receipts; findings", check.detail)


class VerifyTest(unittest.TestCase):
    def test_a_database_that_holds_exits_zero(self):
        connection = FakeConnection(
            baseline=(("server_major", True, "18.4"),), standing=(("check_registration", 0, ""),)
        )

        result = integrity.verify(connection)

        self.assertTrue(result.ok)
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual(2, result.as_dict()["checks"])
        self.assertEqual([], result.as_dict()["failed"])

    def test_a_failing_check_is_a_refusal_naming_itself(self):
        connection = FakeConnection(
            baseline=(("server_major", True, "18.4"), ("event_coverage", False, "3 problem(s)"),)
        )

        result = integrity.verify(connection)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertEqual(
            [(INTEGRITY_FAILED, "baseline:event_coverage", "3 problem(s)")],
            [(v.code, v.source, v.detail) for v in result.violations],
        )
        self.assertEqual(["baseline:event_coverage"], result.as_dict()["failed"])

    def test_a_check_that_holds_is_still_reported(self):
        # A gate that only says what failed cannot be read as evidence that
        # anything was checked at all.
        connection = FakeConnection(baseline=(("server_major", True, "server_version = 18.4"),))

        result = integrity.verify(connection)

        self.assertEqual(
            [("baseline:server_major", True, "server_version = 18.4")],
            [(a.name, a.ok, a.detail) for a in result.assertions],
        )

    def test_the_report_names_the_families_that_ran(self):
        # A subset that reported as though it were the whole gate would be worse
        # than not running: the reader would count an unasked question as
        # answered.
        connection = FakeConnection(
            baseline=(("server_major", True, "18.4"),),
            roles=(("role_catalogue", False, "seven roles"),),
            standing=(("causal_attribution", 0, ""),),
        )

        result = integrity.verify(connection, None, integrity.RUNTIME_FAMILIES)

        self.assertTrue(result.ok)
        self.assertEqual(["baseline", "standing"], result.as_dict()["families"])
        self.assertEqual(2, result.as_dict()["checks"])

    def test_a_database_with_no_gate_is_drift_rather_than_a_pass(self):
        result = integrity.verify(FakeConnection(installed=False))

        self.assertEqual(EXIT_SCHEMA_DRIFT, result.exit_code)
        self.assertIn("run `rk db migrate`", result.violations[0].detail)

    def test_a_check_that_raises_is_a_failure_rather_than_a_pass(self):
        # An unanswered invariant is not a satisfied one.
        connection = FakeConnection(error=failure())

        result = integrity.verify(connection)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertIn("could not be run", result.violations[0].detail)


class StoreVerificationTest(unittest.TestCase):
    """The half of the record no registered check can reach.

    `artifact_references.sha256` says some bytes hash to it. Nothing in SQL can
    open the file, so a gate that never reads one passes over a store that has
    been emptied -- which is the shape of unsoundness criterion 6 names, because
    every later check that trusts a recorded hash is then trusting nothing.
    """

    def keep(self, plaintexts: dict[str, bytes]) -> tuple[Path, list[tuple[str, str]]]:
        """A store holding these bytes, and the rows a database would record."""
        root = scratch() / "artifacts"
        deposit = store.Store(root)
        return root, [(label, deposit.put(data)[0]) for label, data in plaintexts.items()]

    def gate(self, **arguments) -> FakeConnection:
        return FakeConnection(
            baseline=(("server_major", True, "18.4"),),
            standing=(("artifact_reachability", 0, ""),),
            **arguments,
        )

    def test_a_store_nobody_named_is_not_asked_about_and_not_reported(self):
        # The gate has to stay runnable by an operator who has no store on this
        # machine, and a report that gained a null key would be a report every
        # existing reader has to be taught about for no answer.
        connection = self.gate()

        result = integrity.verify(connection)

        self.assertTrue(result.ok)
        self.assertNotIn("artifacts", result.as_dict())
        self.assertFalse([sql for sql in connection.statements if "artifact_references" in sql])

    def test_a_named_store_holds_every_recorded_artifact_against_its_bytes(self):
        root, rows = self.keep({"AF1": b"first artifact\n", "AF2": b"second artifact\n"})

        result = integrity.verify(self.gate(references=rows), store=root)

        self.assertTrue(result.ok)
        self.assertEqual(EXIT_OK, result.exit_code)
        self.assertEqual(
            {"sound": True, "verified": 2, "broken": [], "root": str(root)},
            result.as_dict()["artifacts"],
        )

    def test_the_store_is_reported_beside_the_checks_and_not_counted_as_one(self):
        # `checks` is how many registered checkers ran. Counting this one would
        # make the number disagree with `standing_checks` and would put a
        # filesystem answer in a family that is about the database.
        root, rows = self.keep({"AF1": b"first artifact\n"})

        result = integrity.verify(self.gate(references=rows), store=root)

        self.assertEqual(2, result.as_dict()["checks"])
        self.assertEqual(["baseline", "standing"], result.as_dict()["families"])
        self.assertEqual(
            ["artifact_store"],
            [item.name for item in result.assertions if item.name == "artifact_store"],
        )

    def test_bytes_that_are_gone_fail_the_gate_and_name_the_label(self):
        root, rows = self.keep({"AF1": b"first artifact\n", "AF2": b"second artifact\n"})
        store.path_for(root, rows[1][1]).unlink()

        result = integrity.verify(self.gate(references=rows), store=root)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertEqual(
            [(INTEGRITY_FAILED, "artifact_store")],
            [(item.code, item.source) for item in result.violations],
        )
        self.assertIn("AF2", result.violations[0].detail)
        artifacts = result.as_dict()["artifacts"]
        self.assertFalse(artifacts["sound"])
        self.assertEqual(1, artifacts["verified"])
        self.assertEqual(["AF2"], [item["label"] for item in artifacts["broken"]])

    def test_bytes_that_changed_under_their_own_hash_fail_the_gate(self):
        root, rows = self.keep({"AF1": b"first artifact\n"})
        store.path_for(root, rows[0][1]).write_bytes(b"tampered\n")

        result = integrity.verify(self.gate(references=rows), store=root)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertIn("hashes to", result.violations[0].detail)

    def test_a_database_that_records_no_references_is_drift_rather_than_a_pass(self):
        # An empty answer and a missing table read the same from a report that
        # only counts rows, and they mean opposite things about the store.
        root, _ = self.keep({"AF1": b"first artifact\n"})

        result = integrity.verify(self.gate(records_references=False), store=root)

        self.assertEqual(EXIT_SCHEMA_DRIFT, result.exit_code)
        self.assertIn("run `rk db migrate`", result.violations[0].detail)

    def test_references_that_cannot_be_read_are_a_failure_rather_than_an_empty_store(self):
        # A connection refused the rows and a store with nothing recorded in it
        # produce the same list. Only one of them means the record still holds.
        root, _ = self.keep({"AF1": b"first artifact\n"})
        connection = self.gate(references_error=failure("42501: permission denied"))

        result = integrity.verify(connection, store=root)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertEqual(
            [(INTEGRITY_FAILED, "database")],
            [(item.code, item.source) for item in result.violations],
        )
        self.assertFalse(result.as_dict()["artifacts"]["sound"])


class SealedStoreVerificationTest(unittest.TestCase):
    """PH2-07: the gate checks sealed wire artifacts, and holds no key while it does.

    A sealed artifact has no reference -- that is the whole point of it -- so the
    query that finds every reference finds none of them. Left there, the store
    would have a half nothing ever reads, which is the same unsoundness ticket 06
    named and worse: the bytes nobody checks are the ones nobody may look at.
    """

    ROOT = bytes(range(32))
    PROGRAM = "3f4c9c62-6f3b-4f0e-9b60-5a8a7d5b2e11"
    WIRE = b"Authorization: Bearer sk-live-do-not-log\r\n\r\n{}\n"

    def keep(self, plaintext: bytes = WIRE) -> tuple[Path, list[tuple[str, str, str, str]]]:
        """A store holding one envelope, and the row `artifact_seal` would carry."""
        root = scratch() / "sealed"
        deposit = store.Store(root)
        sha256 = store.digest(plaintext)
        sealed = seal.seal(
            self.ROOT,
            plaintext,
            aad=seal.associated_data(program_id=self.PROGRAM, sha256=sha256, generation=1),
        )
        ciphertext_sha256 = deposit.put(sealed.encode())[0]
        return root, [(sha256, ciphertext_sha256, sealed.alg, sealed.nonce.hex())]

    def gate(self, **arguments) -> FakeConnection:
        return FakeConnection(
            baseline=(("server_major", True, "18.4"),),
            standing=(("wire_artifact_secrecy", 0, ""),),
            **arguments,
        )

    def test_a_sealed_artifact_is_verified_without_the_key_that_opens_it(self):
        # The envelope is filed under the hash of the envelope, so this is the
        # same arithmetic as any other artifact. Nothing here has the root
        # secret, and the sealed bytes are still held against the record.
        root, seals = self.keep()

        result = integrity.verify(self.gate(seals=seals), store=root)

        self.assertTrue(result.ok, result.violations)
        self.assertEqual(
            {"sound": True, "verified": 1, "broken": [], "root": str(root)},
            result.as_dict()["artifacts"],
        )
        self.assertIn("1 of them sealed", result.assertions[-1].detail)

    def test_a_sealed_artifact_whose_bytes_are_gone_fails_the_gate(self):
        root, seals = self.keep()
        store.path_for(root, seals[0][1]).unlink()

        result = integrity.verify(self.gate(seals=seals), store=root)

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertEqual(
            [f"seal {seals[0][0][:12]}"],
            [item["label"] for item in result.as_dict()["artifacts"]["broken"]],
        )
        self.assertNotIn("Bearer", result.violations[0].detail)

    def test_a_record_describing_a_different_ciphertext_fails_the_gate(self):
        # Both halves intact and disagreeing: the file is the file it is filed
        # as, and the row says it was sealed under a nonce it was not. One of the
        # two has been swapped, and neither is trustworthy afterwards.
        root, seals = self.keep()
        sha256, ciphertext_sha256, alg, _ = seals[0]

        result = integrity.verify(
            self.gate(seals=[(sha256, ciphertext_sha256, alg, "00" * seal.NONCE_BYTES)]),
            store=root,
        )

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        broken = result.as_dict()["artifacts"]["broken"]
        self.assertEqual([f"seal {sha256[:12]}"], [item["label"] for item in broken])
        self.assertIn("recorded as", broken[0]["detail"])
        self.assertEqual(0, result.as_dict()["artifacts"]["verified"])

    def test_bytes_that_are_not_an_envelope_at_all_fail_the_gate(self):
        root, seals = self.keep()
        sha256 = store.digest(b"not an envelope\n")
        store.Store(root).put(b"not an envelope\n")

        result = integrity.verify(
            self.gate(seals=[(seals[0][0], sha256, seals[0][2], seals[0][3])]), store=root
        )

        self.assertEqual(EXIT_INTEGRITY_FAILED, result.exit_code)
        self.assertIn("unreadable", result.as_dict()["artifacts"]["broken"][0]["detail"])

    def test_missing_bytes_are_reported_once_rather_than_as_two_faults(self):
        # The hash check and the header check both fail on a file that is gone.
        # Reporting both would make one missing file look like two problems and
        # would count the same artifact twice in what was verified.
        root, seals = self.keep()
        store.path_for(root, seals[0][1]).unlink()

        result = integrity.verify(self.gate(seals=seals), store=root)

        self.assertEqual(1, len(result.as_dict()["artifacts"]["broken"]))
        self.assertEqual(0, result.as_dict()["artifacts"]["verified"])

    def test_a_corpus_without_the_sealing_migration_is_not_asked_about_seals(self):
        # The gate runs against a database that is mid-corpus, which the baseline
        # reports as drift. Asking a table that does not exist yet would turn
        # that into an error from the store instead.
        root, _ = self.keep()

        connection = self.gate(references=(), records_seals=False)
        result = integrity.verify(connection, store=root)

        self.assertTrue(result.ok, result.violations)
        self.assertFalse([sql for sql in connection.statements if "FROM artifact_seal" in sql])


if __name__ == "__main__":
    unittest.main()
