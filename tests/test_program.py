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
    Ledger,
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


class WorkableTest(unittest.TestCase):
    """Which durable fact stops a run before it claims anything, and what it says.

    Four facts, four sentences. The scheduler enforces three of them itself and
    would refuse every Task anyway; what this decides is whether the operator
    reads why, or reads an empty slate and guesses.
    """

    def workable(self, **facts) -> tuple[bool, str]:
        ledger = Ledger()
        state = program._State(**{"lifecycle": "open", "pending": [], **facts})
        answer = program._workable(ledger, state)
        return answer, "" if not ledger.assertions else ledger.assertions[-1].detail

    def test_an_open_program_with_nothing_outstanding_is_worked(self):
        answer, said = self.workable()

        self.assertTrue(answer)
        self.assertEqual("", said)

    def test_a_halted_program_is_named_as_halted_rather_than_as_empty(self):
        # Stories 14 and 15. `claimable_for` refuses every Task of a halted
        # Program, so a run that got this far would offer an empty slate and
        # stop with nothing to say. This is the sentence three consoles have
        # always promised: no new work until it is lifted.
        answer, said = self.workable(halted=True)

        self.assertFalse(answer)
        self.assertIn("halted", said)
        self.assertIn("lifts it", said)

    def test_a_halt_is_read_before_the_decisions_it_makes_moot(self):
        # Both are true and only one is actionable: answering the question does
        # not restart the Program, and lifting the Halt does.
        answer, said = self.workable(halted=True, pending=[{"question_code": "scope"}])

        self.assertFalse(answer)
        self.assertIn("halted", said)

    def test_a_question_waiting_on_a_human_stops_the_run(self):
        answer, said = self.workable(pending=[{"question_code": "scope"}])

        self.assertFalse(answer)
        self.assertIn("waiting on a human", said)

    def test_a_closed_program_is_held_rather_than_failed(self):
        answer, said = self.workable(lifecycle="closed")

        self.assertFalse(answer)
        self.assertIn("closed", said)

    def test_a_run_that_already_refused_says_nothing_further(self):
        # The violation is the answer. A second sentence about a Halt or a
        # lifecycle here would be a fact read off state the refusal may have
        # stopped before filling in.
        ledger = Ledger()
        ledger.fail("integrity", "a check failed", code="x", source="database")
        state = program._State(lifecycle="open", pending=[], halted=True)

        self.assertFalse(program._workable(ledger, state))
        self.assertEqual(1, len(ledger.assertions))


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


#: A Program identifier the recorder below never resolves. The projection takes
#: it as text and hands it straight back to the statements, so what it is worth
#: testing about is that every statement gets the same one.
PROGRAM = "0198b0f0-0000-7000-8000-0000000000ab"


class Recorder:
    """A connection that answers the one SELECT and records every write.

    What `_project_known_issues` decides is which statement each entry produces
    against what the table already holds, and that is answerable here: the
    alternative is standing a server up to watch three INSERTs, which is
    `tests/test_database.py`'s to do once the projection is called by a run.
    """

    def __init__(self, held: tuple[tuple[object, ...], ...] = ()) -> None:
        self.held = held
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, statement: str, parameters: tuple = ()) -> pg.Result:
        self.statements.append((" ".join(statement.split()), tuple(parameters)))
        if statement.lstrip().upper().startswith("SELECT"):
            return pg.Result(columns=(), rows=self.held, tag=f"SELECT {len(self.held)}")
        return pg.Result(tag=statement.split()[0].upper() + " 1")

    def issued(self, verb: str) -> list[tuple[str, tuple]]:
        return [item for item in self.statements if item[0].upper().startswith(verb)]


def known_issue(entity_like: str | None, source: str, note: str) -> str:
    """`VALID` with one do-not-send entry, spelled the way an operator would."""
    instance = "" if entity_like is None else f'entity_like = "{entity_like}"\n'
    return (
        VALID
        + f'\n[[known_issue]]\nclass_id = "idor"\n{instance}'
        + f'source = "{source}"\nnote = "{note}"\n'
    )


class KnownIssueProjectionTest(unittest.TestCase):
    """The do-not-send list, projected into the table `report_blockers` joins.

    `0034_reports.sql:1073` registered `program_known_issues` as the program's
    published list "entered by the operator through the control surface", and
    ticket 125 settled that the surface it meant is the configuration document.
    Three answers per entry -- insert what is new, update what changed, delete
    what the document stopped naming -- on the pattern `_project_identities`
    already sets.
    """

    def project(self, text: str, held: tuple = ()) -> Recorder:
        recorder = Recorder(held=held)
        program._project_known_issues(recorder, loaded(text), PROGRAM)
        return recorder

    def test_an_entry_the_table_does_not_hold_is_inserted(self):
        recorder = self.project(known_issue("%/tickets/%", "program_policy", "known and wontfix"))

        self.assertEqual(
            [(PROGRAM, "idor", "%/tickets/%", "program_policy", "known and wontfix")],
            [parameters for _, parameters in recorder.issued("INSERT")],
        )
        self.assertEqual([], recorder.issued("UPDATE") + recorder.issued("DELETE"))

    def test_an_entry_that_names_no_instance_is_written_as_the_null_that_means_the_class(self):
        # `entity_like` NULL is the whole program, so the absent key has to
        # reach the column as NULL rather than as a pattern matching nothing.
        recorder = self.project(known_issue(None, "operator", "the staging tier is open"))

        self.assertEqual(
            [(PROGRAM, "idor", None, "operator", "the staging tier is open")],
            [parameters for _, parameters in recorder.issued("INSERT")],
        )

    def test_a_row_the_document_still_declares_unchanged_is_left_alone(self):
        # A resume is the ordinary case, and one that rewrote every row would
        # make an unchanged document look like a policy change to anything
        # reading the table's history.
        held = (("row-1", "idor", "%/tickets/%", "program_policy", "known and wontfix"),)

        recorder = self.project(
            known_issue("%/tickets/%", "program_policy", "known and wontfix"), held=held
        )

        self.assertEqual([], recorder.statements[1:])

    def test_a_changed_note_is_an_update_of_the_row_that_holds_it(self):
        # Not a delete and a re-insert: the row's identity is the rule, and
        # replacing it would give the same rule a new `id` every time the
        # operator reworded the sentence a refusal quotes.
        held = (("row-1", "idor", "%/tickets/%", "operator", "the old wording"),)

        recorder = self.project(
            known_issue("%/tickets/%", "program_policy", "the new wording"), held=held
        )

        self.assertEqual(
            [("row-1", "program_policy", "the new wording")],
            [parameters for _, parameters in recorder.issued("UPDATE")],
        )
        self.assertEqual([], recorder.issued("INSERT") + recorder.issued("DELETE"))

    def test_an_entry_the_document_stopped_naming_is_deleted(self):
        # Deleted rather than invalidated, which is where this parts company
        # with `_project_identities`: nothing cites one of these rows, so there
        # is no row whose meaning a deletion would change, and one kept past the
        # document that declared it would go on refusing reports about something
        # the Program no longer says it does not want.
        held = (
            ("row-1", "idor", "%/tickets/%", "operator", "still declared"),
            ("row-2", "idor", "%/orders/%", "operator", "withdrawn"),
        )

        recorder = self.project(known_issue("%/tickets/%", "operator", "still declared"), held=held)

        self.assertEqual(
            [("row-2",)], [parameters for _, parameters in recorder.issued("DELETE")]
        )
        self.assertEqual([], recorder.issued("INSERT") + recorder.issued("UPDATE"))

    def test_a_document_that_declares_nothing_withdraws_the_whole_list(self):
        held = (("row-1", "idor", None, "program_policy", "was published"),)

        recorder = self.project(VALID, held=held)

        self.assertEqual(
            [("row-1",)], [parameters for _, parameters in recorder.issued("DELETE")]
        )

    def test_the_harnesss_own_record_of_what_it_sent_is_never_read(self):
        # `prior_submission` is the third origin the CHECK admits and the only
        # one this document cannot state, so a row carrying it is not the
        # document's to keep or to withdraw. The exclusion is in the SELECT
        # rather than in a filter afterwards, because a row this function never
        # sees is a row it cannot delete by forgetting to check.
        recorder = self.project(known_issue("%/tickets/%", "operator", "declared"))

        statement, parameters = recorder.statements[0]
        self.assertIn("FROM program_known_issues", statement)
        self.assertIn("source <> 'prior_submission'", statement)
        self.assertEqual((PROGRAM,), parameters)

    def test_every_statement_is_scoped_to_the_program_or_to_one_of_its_rows(self):
        # The table is program-scoped and the delete arm addresses rows by `id`.
        # An `id` is only ever reached through the program-scoped read above, so
        # the pair is what keeps one Program's list off another's.
        held = (("row-1", "idor", "%/orders/%", "operator", "withdrawn"),)

        recorder = self.project(known_issue("%/tickets/%", "operator", "declared"), held=held)

        self.assertEqual(
            [(PROGRAM,), (PROGRAM, "idor", "%/tickets/%", "operator", "declared"), ("row-1",)],
            [parameters for _, parameters in recorder.statements],
        )


class StopReasonTest(unittest.TestCase):
    """The one word a driver loop reads, and the order it is decided in.

    Ticket 161. `hunt.sh` stops on `nothing_to_execute` and has to keep doing
    so, which makes that word a statement about the Program and not about the
    pass: it may only be said when there was nothing to attempt. A chooser that
    spent a ceiling before it named a Task attempted nothing either, and saying
    the same word for both ended `rk2hunt17` six laps early.
    """

    def stopped(self, ledger: Ledger | None = None, **state) -> str:
        return program._report(ledger or Ledger(), program._State(**state)).facts["stop_reason"]

    def test_a_pass_that_attempted_nothing_at_all_is_the_empty_slate(self):
        self.assertEqual(program.STOPPED_NOTHING_TO_EXECUTE, self.stopped())

    def test_a_chooser_that_ran_out_of_room_is_not_the_empty_slate(self):
        self.assertEqual(
            program.STOPPED_CHOOSER_CUT_OFF,
            self.stopped(execution={"choice": {"cut_off": "budget"}, "task": None}),
        )

    def test_a_chooser_that_declined_the_slate_leaves_the_empty_slate_word(self):
        self.assertEqual(
            program.STOPPED_NOTHING_TO_EXECUTE,
            self.stopped(execution={"choice": {"cut_off": None}, "task": None}),
        )

    def test_an_attempt_that_was_made_outranks_how_the_chooser_stopped(self):
        # The cut-off word is about a pass that did no work. A ceilinged chooser
        # whose Task the runtime's own walk claimed anyway did work, and an
        # operator reading `chooser_cut_off` there would read it as idle.
        self.assertEqual(
            program.STOPPED_TASK_ATTEMPTED,
            self.stopped(execution={"choice": {"cut_off": "budget"}, "task": {"label": "T1"}}),
        )

    def test_a_refusal_and_a_pending_decision_both_outrank_it(self):
        refused = Ledger()
        refused.fail("integrity", "a check failed", code="x", source="database")
        cut_off = {"choice": {"cut_off": "budget"}, "task": None}

        self.assertEqual(program.STOPPED_REFUSED, self.stopped(refused, execution=cut_off))
        self.assertEqual(
            program.STOPPED_AWAITING_DECISION,
            self.stopped(pending=[{"task": "T1"}], execution=cut_off),
        )


if __name__ == "__main__":
    unittest.main()
