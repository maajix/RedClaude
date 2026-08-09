"""The gate's own logic, without a database under it.

What each check means is the corpus's business and is exercised against a real
server in `test_database`. What is tested here is the thing the gate adds: that
every family is run in one pass, that a failure is reported as a refusal rather
than as a number nobody reads, and that a database with no checks in it is not
mistaken for a database that passed them.
"""

import unittest

from redkraken import integrity, pg
from redkraken.outcome import EXIT_INTEGRITY_FAILED, EXIT_OK, EXIT_SCHEMA_DRIFT, INTEGRITY_FAILED


class FakeConnection:
    """Answers the four statements the gate sends, and records that it did."""

    def __init__(self, *, baseline=(), roles=(), standing=(), installed=True, error=None):
        self.baseline = baseline
        self.roles = roles
        self.standing = standing
        self.installed = installed
        self.error = error
        self.statements: list[str] = []
        self.parameters: list[tuple] = []

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.statements.append(" ".join(sql.split()))
        self.parameters.append(tuple(parameters))
        if "to_regprocedure" in sql:
            return pg.Result(columns=("ok",), rows=((self.installed,),))
        if self.error is not None:
            raise self.error
        if integrity.BASELINE in sql:
            return pg.Result(columns=("check_name", "ok", "detail"), rows=tuple(self.baseline))
        if integrity.ROLE_CATALOGUE in sql:
            return pg.Result(columns=("check_name", "ok", "detail"), rows=tuple(self.roles))
        if integrity.STANDING in sql:
            return pg.Result(columns=("name", "problems", "detail"), rows=tuple(self.standing))
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


if __name__ == "__main__":
    unittest.main()
