"""Create or resume a Program: everything answerable without a server.

The decision itself is the seam. `decide` is given what the database currently
holds and what the operator's file currently says, and answers with one of four
words; every other part of the operation is arranging for it to be asked once,
inside the transaction that acts on the answer. Written this way, the rule that
a changed policy is never adopted silently is testable without a database, a
Program or a run.

What needs a server -- that the first run writes one Program, that the second
writes none, that each emits one Event -- is in `tests/test_database.py`.
"""

from __future__ import annotations

import unittest
from unittest import mock

from redkraken import config, pg, program
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INVALID_CONFIGURATION,
)
from tests.fixtures import VALID, write


UNREACHABLE = "postgresql://rk2_runtime@127.0.0.1:1/rk2"


def loaded(text: str = VALID) -> config.Configuration:
    configuration, refusals = config.load(write(text))
    assert configuration is not None, refusals
    return configuration


def revision_for(configuration: config.Configuration) -> program.Revision:
    """The revision a database would hold if this configuration had been written."""
    return program.Revision(
        revision=1,
        schema_version=configuration.schema_version,
        source_sha256=configuration.source_sha256,
        canonical_sha256=configuration.canonical_sha256,
    )


def settings() -> pg.Settings:
    return pg.settings_from_url(UNREACHABLE, application_name="rk run")


class DecisionTest(unittest.TestCase):
    """The four answers, and which fact produces each one."""

    def setUp(self):
        self.configuration = loaded()

    def test_a_program_nobody_has_opened_yet_is_created(self):
        answer = program.decide(None, self.configuration, accept_change=False)

        self.assertEqual(program.CREATE, answer)

    def test_the_same_policy_resumes_what_is_already_there(self):
        current = revision_for(self.configuration)

        answer = program.decide(current, self.configuration, accept_change=False)

        self.assertEqual(program.RESUME, answer)

    def test_a_file_that_changed_without_the_policy_changing_still_resumes(self):
        # The canonical hash is taken over sorted-key compact JSON, so a comment,
        # a reflow or a reordered table is a different file and the same policy.
        # Recording a revision for it would claim a change that did not happen.
        reflowed = loaded(VALID.replace("[program]", "# the target\n[program]"))
        current = revision_for(self.configuration)

        self.assertNotEqual(current.source_sha256, reflowed.source_sha256)
        self.assertEqual(current.canonical_sha256, reflowed.canonical_sha256)
        self.assertEqual(program.RESUME, program.decide(current, reflowed, accept_change=False))

    def test_a_changed_policy_is_refused_rather_than_adopted(self):
        changed = loaded(VALID.replace("requests = 5000", "requests = 50000"))
        current = revision_for(self.configuration)

        answer = program.decide(current, changed, accept_change=False)

        self.assertEqual(program.REFUSE, answer)

    def test_a_changed_policy_the_operator_accepts_becomes_a_revision(self):
        changed = loaded(VALID.replace("requests = 5000", "requests = 50000"))
        current = revision_for(self.configuration)

        answer = program.decide(current, changed, accept_change=True)

        self.assertEqual(program.REVISE, answer)

    def test_accepting_a_change_that_is_not_there_still_resumes(self):
        # Otherwise the flag is a way to write a revision that changes nothing,
        # which is one of the three things `check_program_configuration` refuses.
        current = revision_for(self.configuration)

        answer = program.decide(current, self.configuration, accept_change=True)

        self.assertEqual(program.RESUME, answer)


class LifecycleTest(unittest.TestCase):
    """What the two timestamps on the root row mean, in one word."""

    def test_a_program_with_neither_timestamp_is_open(self):
        self.assertEqual("open", program.lifecycle(None, None))

    def test_a_closed_program_is_closed(self):
        self.assertEqual("closed", program.lifecycle("2026-08-09 12:00:00+00", None))

    def test_a_program_awaiting_purge_is_retired(self):
        # `retire_program()` sets both, and retired is the more specific answer:
        # the rows are scheduled to go, not merely finished with.
        self.assertEqual(
            "retired", program.lifecycle("2026-08-09 12:00:00+00", "2026-11-07 12:00:00+00")
        )


class RefusalTest(unittest.TestCase):
    """What the command does before it has anything durable to report."""

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        # Criterion 5, the first half, at its earliest point: a refusal the
        # operator's own file produces cannot change a database it never reached.
        source = write(VALID.replace("requests = 5000", "requests = -1"))

        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")) as opened:
            result = program.run(settings(), source)

        opened.assert_not_called()
        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(program.STOPPED_REFUSED, result.facts["stop_reason"])

    def test_a_configuration_file_that_is_not_there_is_the_same_refusal(self):
        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")):
            result = program.run(settings(), write(VALID).parent / "absent.toml")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual([], result.facts["pending_decisions"])
        self.assertIsNone(result.facts["program_id"])

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = program.run(settings(), write(VALID))

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.exit_code)
        self.assertEqual(program.STOPPED_REFUSED, result.facts["stop_reason"])

    def test_every_refusal_reports_the_same_keys_a_run_reports(self):
        # Criterion 6 is a property of the report rather than of the happy path:
        # a caller parses one document whether the run reached a Program or not.
        results = (
            program.run(settings(), write(VALID.replace("requests = 5000", "requests = -1"))),
            program.run(settings(), write(VALID)),
        )

        for result in results:
            with self.subTest(result.violations[0].code):
                self.assertEqual(set(program.FACTS), set(result.facts))

    def test_a_configuration_that_will_not_compile_never_opens_a_connection(self):
        # The configuration is valid TOML the validator accepts, so the earlier
        # refusal cannot catch it: the compiler is the only thing that knows a
        # private address is not a target. It has to run before the connection,
        # because a Program whose policy denies everything is worse than none.
        source = write(VALID.replace('host = "app.example.com"', 'host = "10.0.0.1"'))

        with mock.patch.object(pg, "connect", side_effect=AssertionError("connected")) as opened:
            result = program.run(settings(), source)

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(program.STOPPED_REFUSED, result.facts["stop_reason"])
        self.assertIsNone(result.facts["scope"])
        # The source names the compiler rather than the validator, which is how an
        # operator tells "your file is wrong" from "your file says nothing usable".
        self.assertEqual(
            [("invalid_configuration", True)],
            [
                (violation.code, violation.source.startswith("scope:scope.include["))
                for violation in result.violations
            ],
        )

    def test_the_policy_is_compiled_before_the_corpus_is_read(self):
        # A corpus this run cannot read would be a different refusal, and the
        # scope refusal has to win: reading migrations is work done on behalf of
        # a policy that does not exist.
        source = write(VALID.replace('host = "app.example.com"', 'host = "10.0.0.1"'))

        result = program.run(settings(), source, corpus=write(VALID).parent / "absent")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(
            ["scope_policy"],
            [assertion.name for assertion in result.assertions if not assertion.ok],
        )

    def test_a_configuration_that_compiles_reports_the_policy_it_compiled(self):
        # The hold is what an operator reads when the run stops for any later
        # reason, so it names the shape of the policy rather than merely passing.
        result = program.run(settings(), write(VALID))

        holds = {assertion.name: assertion.detail for assertion in result.assertions}
        self.assertIn("scope_policy", holds)
        self.assertRegex(holds["scope_policy"], r"^\d+ rule\(s\), \d+ channel\(s\), policy [0-9a-f]{12}$")

    def test_the_report_carries_no_value_out_of_the_configuration(self):
        # The document holds hosts, headers and `slot://` references. None of
        # them is a durable identifier, so none of them belongs in the outcome.
        result = program.run(settings(), write(VALID))

        rendered = repr(result.as_dict())
        for secret in ("app.example.com", "slot://identity/member", "X-Bounty-Id", "oob.example.net"):
            self.assertNotIn(secret, rendered)


if __name__ == "__main__":
    unittest.main()
