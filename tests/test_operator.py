"""What the operator console sends, without a database under it.

`tests/test_database.py` holds the half a server has to answer -- that an
approval is revalidated, that a withdrawn question puts its Task back, that the
runtime cannot execute any of it. This module holds the other half: which
statement goes out, in which order, carrying which values, and what an operator
is handed when the database says no.

That half is worth its own file because every command here is one a person runs
about work already stopped. A verb that sent the slug where the identifier
belonged, or dropped the hint out of a refusal, would leave an operator holding
a Program that will not start and no sentence telling them why.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from redkraken import migrate, operator, pg
from redkraken.outcome import EXIT_INVALID_CONFIGURATION, EXIT_OK


ANSWERED = json.dumps(
    {
        "label": "D7",
        "status": "approved",
        "answered_by": "rk2_human",
        "grant_expires_at": "2026-08-15T00:00:00+00:00",
    }
)

QUESTION = (
    "acme-web",
    "D7",
    "approval_required",
    "mcp__rk2__net_request",
    "high",
    "[approval_required] POST app.example.com/x",
    "2026-08-14 00:00:00+00",
    "2026-08-15 00:00:00+00",
    "pending",
    None,
    None,
)

ANSWERED_QUESTION = QUESTION[:8] + ("approved", "rk2_human", "scoped and expected")


class FakeConnection:
    """Answers the statements the console sends, and records that it did."""

    def __init__(self, *, human=True, program="0197-a", answer=ANSWERED, questions=(),
                 installed=True, error=None):
        self.human = human
        self.program = program
        self.answer = answer
        self.questions = questions
        self.installed = installed
        self.error = error
        self.statements: list[str] = []
        self.parameters: list[tuple] = []
        self.closed = False

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.statements.append(" ".join(sql.split()))
        self.parameters.append(tuple(parameters))
        if "to_regprocedure" in sql:
            return pg.Result(columns=("ok",), rows=((self.installed,),))
        if "human_actor_session" in sql:
            return pg.Result(columns=("human", "user"), rows=((self.human, "rk2_human"),))
        if "FROM programs" in sql:
            rows = ((self.program,),) if self.program else ()
            return pg.Result(columns=("id",), rows=rows)
        if "set_config" in sql:
            return pg.Result(columns=("set_config",), rows=(("",),))
        if "v_decision_queue" in sql:
            return pg.Result(
                columns=(
                    "program", "label", "question_code", "tool", "risk_class", "question",
                    "requested_at", "deadline_at", "status", "answered_by", "answer",
                ),
                rows=tuple(self.questions),
            )
        if self.error is not None:
            raise self.error
        return pg.Result(columns=("answer",), rows=((self.answer,),))

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.closed = True


def refused(message: str, *, code: str = "23514", hint: str | None = None) -> pg.DatabaseError:
    fields = {"C": code, "M": message}
    if hint is not None:
        fields["H"] = hint
    return pg.DatabaseError(fields)


class ConsoleCase(unittest.TestCase):
    """A case whose connection is a recording, not a socket."""

    def run_with(self, connection: FakeConnection, call):
        with mock.patch.object(migrate, "open_connection", return_value=connection):
            return call(pg.settings_from_url("postgresql://rk2_human@127.0.0.1/rk2"))


class QueueTest(ConsoleCase):
    """`rk decision list` -- the queue, as the operator alone may read it."""

    def test_the_queue_is_filtered_in_the_database_by_program_and_by_status(self):
        # Both in SQL rather than in Python: the view is the operator's own and
        # a filter applied here would be a second definition of "open".
        connection = FakeConnection(questions=(QUESTION,))

        report = self.run_with(connection, lambda s: operator.queue(s, slug="acme-web"))

        self.assertEqual(EXIT_OK, report.exit_code)
        self.assertIn(("acme-web", False), connection.parameters)
        self.assertEqual(1, report.facts["open"])

    def test_closed_questions_are_asked_for_and_not_filtered_out_afterwards(self):
        connection = FakeConnection(questions=(QUESTION,))

        self.run_with(connection, lambda s: operator.queue(s, closed=True))

        self.assertIn((None, True), connection.parameters)

    def test_a_closed_question_carries_back_the_words_the_operator_answered_it_with(self):
        # The one read of `pending_decisions.answer` anywhere in the harness.
        # Write-only is a claim about the runtime and the models behind it, not
        # about the person who wrote the sentence -- and an operator who cannot
        # read back what they decided is an operator who reaches for `psql`.
        connection = FakeConnection(questions=(ANSWERED_QUESTION,))

        report = self.run_with(connection, lambda s: operator.queue(s, closed=True))

        self.assertEqual("scoped and expected", report.facts["questions"][0]["answer"])
        self.assertEqual(0, report.facts["open"])

    def test_a_question_is_reported_under_the_names_the_view_gives_it(self):
        connection = FakeConnection(questions=(QUESTION,))

        report = self.run_with(connection, lambda s: operator.queue(s))

        question = report.facts["questions"][0]
        self.assertEqual("D7", question["label"])
        self.assertEqual("acme-web", question["program"])
        self.assertEqual("approval_required", question["question_code"])

    def test_a_connection_that_is_not_the_operator_is_refused_before_it_reads(self):
        # The database refuses this too, inside every verb. Asking one step
        # earlier is what turns a permission error into a report.
        connection = FakeConnection(human=False)

        report = self.run_with(connection, lambda s: operator.queue(s))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, report.exit_code)
        self.assertNotIn(operator.QUEUE.split()[1], " ".join(connection.statements))
        self.assertIn("not a member of rk2_human", report.violations[0].detail)

    def test_a_database_with_no_operator_assertion_is_named_as_drift(self):
        connection = FakeConnection(installed=False)

        report = self.run_with(connection, lambda s: operator.queue(s))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, report.exit_code)
        self.assertIn("rk db migrate", report.violations[0].detail)


class AnswerTest(ConsoleCase):
    """`rk decision answer` -- the verdict, the reason and the grant."""

    def test_an_approval_sends_the_verdict_the_database_names_it_by(self):
        connection = FakeConnection()

        report = self.run_with(
            connection,
            lambda s: operator.answer(
                s, "acme-web", "D7", approve=True, reason="scoped and expected"
            ),
        )

        self.assertEqual(EXIT_OK, report.exit_code)
        self.assertIn(("D7", "approved", "scoped and expected", "24.0 hours"), connection.parameters)

    def test_a_denial_is_the_same_verb_with_the_other_verdict(self):
        connection = FakeConnection()

        self.run_with(
            connection,
            lambda s: operator.answer(s, "acme-web", "D7", approve=False, reason="out of scope"),
        )

        self.assertEqual("denied", connection.parameters[-1][1])

    def test_the_grant_the_operator_asked_for_is_sent_as_an_interval(self):
        connection = FakeConnection()

        self.run_with(
            connection,
            lambda s: operator.answer(
                s, "acme-web", "D7", approve=True, reason="once", grant_hours=0.5
            ),
        )

        self.assertEqual("0.5 hours", connection.parameters[-1][3])

    def test_the_program_is_resolved_and_bound_before_the_label_is_named(self):
        # `answer_decision` looks the label up inside the session's Program, so
        # a binding that arrived afterwards would resolve nothing.
        connection = FakeConnection()

        self.run_with(
            connection,
            lambda s: operator.answer(s, "acme-web", "D7", approve=True, reason="yes"),
        )

        sent = connection.statements
        self.assertLess(
            next(i for i, sql in enumerate(sent) if "set_config" in sql),
            next(i for i, sql in enumerate(sent) if "answer_decision" in sql),
        )

    def test_the_verb_answer_is_reported_as_the_document_it_is(self):
        connection = FakeConnection()

        report = self.run_with(
            connection,
            lambda s: operator.answer(s, "acme-web", "D7", approve=True, reason="yes"),
        )

        self.assertEqual("approved", report.facts["result"]["status"])

    def test_a_stale_approval_is_a_refusal_carrying_the_database_hint(self):
        # Criterion 5 lands here for the operator: the refusal has to say what
        # changed and what to do about it, or a person is left with a Task that
        # will not move and a command that exited non-zero.
        connection = FakeConnection(
            error=refused(
                "decision D7 no longer validates against the current configuration: "
                "request_reclassified",
                hint="deny it, or supersede it and let the runtime ask again",
            )
        )

        report = self.run_with(
            connection,
            lambda s: operator.answer(s, "acme-web", "D7", approve=True, reason="yes"),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, report.exit_code)
        self.assertIn("request_reclassified", report.violations[0].detail)
        self.assertIn("supersede it", report.violations[0].detail)
        self.assertIsNone(report.facts["result"])

    def test_a_refusal_with_no_hint_is_still_one_readable_sentence(self):
        connection = FakeConnection(error=refused("no decision D9 in the bound Program"))

        report = self.run_with(
            connection,
            lambda s: operator.answer(s, "acme-web", "D9", approve=False, reason="no"),
        )

        self.assertIn("D9 was not denied: 23514: no decision D9", report.violations[0].detail)

    def test_a_program_nobody_opened_stops_before_the_verb(self):
        connection = FakeConnection(program="")

        report = self.run_with(
            connection,
            lambda s: operator.answer(s, "ghost", "D7", approve=True, reason="yes"),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, report.exit_code)
        self.assertNotIn("answer_decision", " ".join(connection.statements))


class SupersedeTest(ConsoleCase):
    """`rk decision supersede` -- withdrawn, not answered."""

    def test_the_label_and_the_reason_are_all_it_sends(self):
        # No verdict and no grant: a withdrawn question authorises nothing, and
        # a third argument here would be a third thing an operator could get
        # wrong about a question they have decided not to answer.
        connection = FakeConnection(answer=json.dumps({"label": "D7", "status": "superseded"}))

        report = self.run_with(
            connection,
            lambda s: operator.supersede(s, "acme-web", "D7", reason="the policy changed"),
        )

        self.assertEqual(EXIT_OK, report.exit_code)
        self.assertEqual(("D7", "the policy changed"), connection.parameters[-1])
        self.assertEqual("superseded", report.facts["result"]["status"])


class HaltTest(ConsoleCase):
    """`rk halt` and `rk resume` -- the Halt on a whole Program."""

    def test_the_halt_is_aimed_at_the_identifier_the_slug_resolved_to(self):
        # The Halt verbs take the Program as an argument where the decision
        # verbs take it from the binding. Sending the slug would be a Halt on a
        # Program that does not exist -- and `halt_program` would say so, one
        # round trip later, about a name the operator typed correctly.
        connection = FakeConnection(program="0197-a")

        report = self.run_with(connection, lambda s: operator.halt(s, "acme-web", reason="stop"))

        self.assertEqual(EXIT_OK, report.exit_code)
        self.assertEqual(("0197-a", "stop"), connection.parameters[-1])

    def test_resuming_clears_the_halt_and_reaches_no_recovery_verb(self):
        # `resume_program` is the runtime's and stays the runtime's: its first
        # statement declares the runtime as the actor, so an operator calling it
        # would file its rows under a name that did not decide anything.
        connection = FakeConnection()

        self.run_with(connection, lambda s: operator.resume(s, "acme-web", reason="fixed"))

        sent = " ".join(connection.statements)
        self.assertIn("clear_program_halt", sent)
        self.assertNotIn("resume_program", sent)

    def test_a_program_with_no_halt_on_it_is_reported_and_not_raised(self):
        connection = FakeConnection(error=refused("Program 0197-a has no active Halt"))

        report = self.run_with(connection, lambda s: operator.resume(s, "acme-web", reason="x"))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, report.exit_code)
        self.assertIn("no active Halt", report.violations[0].detail)


class DocumentTest(unittest.TestCase):
    """One verb's jsonb answer, on its way into a report."""

    def test_a_json_answer_is_parsed_rather_than_escaped_into_a_string(self):
        self.assertEqual({"label": "D7"}, operator._document('{"label": "D7"}'))

    def test_text_that_is_not_json_is_left_exactly_as_it_arrived(self):
        self.assertEqual("halted", operator._document("halted"))

    def test_a_value_the_client_already_decoded_is_left_alone(self):
        self.assertEqual(7, operator._document(7))


if __name__ == "__main__":
    unittest.main()
