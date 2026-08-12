"""Staging a Mission result: what is kept, what is refused, and what is written.

The load-bearing sentence is the Spec's -- a Mission result "is staging data,
not canonical truth" -- and the tests here are about the two halves of making
that structurally true rather than conventionally true.

The first half is the write. `stage` touches `proposals` and `proposal_drops`
and nothing else, and the assertion is on the SQL it emits, so a later edit that
reached for a canonical table would fail here rather than in review. It also
supplies neither `label` nor `status`: the trigger and the column default do,
because a caller that could pass a status could pass `promoted`.

The second half is the refusal. An Observation whose provenance the runtime can
*disprove* is kept as a rejected element with the reason attached, never dropped
silently -- migration 0020 says why: "a silent drop is indistinguishable from a
thing the agent never proposed". Each of the reasons the column accepts gets a
test, including the two that are deliberately not faults: a Receipt with no Tool
Run behind it, and a subject label this Mission is proposing in the same result.

What needs a server -- that these rows land, that no canonical table moved, and
that another Program's Receipt really is visible to `rk2_runtime` and really is
refused -- is in `tests/test_database.py`.
"""

from __future__ import annotations

import contextlib
import json
import re
import unittest

from redkraken import pg, proposal
from tests import ROOT


MINE = "11111111-1111-4111-8111-111111111111"
THEIRS = "22222222-2222-4222-8222-222222222222"
RUN = "33333333-3333-4333-8333-333333333333"
OTHER_RUN = "44444444-4444-4444-8444-444444444444"
TASK = "55555555-5555-4555-8555-555555555555"
PROPOSAL = "66666666-6666-4666-8666-666666666666"

CORPUS = ROOT / "src" / "redkraken" / "migrations" / "0020_state_access.sql"


def observation(**fields) -> dict:
    return {"kind": "response", "summary": "the header was absent", **fields}


def result(*observations, **payload) -> proposal.Result:
    return proposal.Result(payload={"observations": list(observations), **payload})


class Recorder:
    """A connection that answers the three provenance lookups, and remembers all.

    Answers are per statement rather than per fragment: the three lookups differ
    by table, and a caller that matched loosely would answer a Tool Run question
    with a Receipt.
    """

    def __init__(self, *, receipts=None, tool_runs=None, entities=None):
        self.calls: list[tuple[str, tuple]] = []
        self.receipts = receipts or {}
        self.tool_runs = tool_runs or {}
        self.entities = entities or {}

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        return pg.Result(columns=(), rows=tuple(self._answer(sql, parameters)), tag="SELECT")

    @contextlib.contextmanager
    def transaction(self):
        self.calls.append(("BEGIN", ()))
        yield self
        self.calls.append(("COMMIT", ()))

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql == proposal.RECEIPT:
            return list(self.receipts.get(parameters[0], ()))
        if sql == proposal.TOOL_RUN:
            return list(self.tool_runs.get(parameters[0], ()))
        if sql == proposal.ENTITY:
            return list(self.entities.get(parameters[0], ()))
        if sql == proposal.INSERT:
            return [(PROPOSAL, "PR1", proposal.STAGED)]
        if sql == proposal.INSERT_DROP:
            return []
        raise AssertionError(f"an unplanned statement was issued: {sql}")


def receipt(program_id: str = MINE, lane: str = "agent_http", run: str | None = RUN) -> tuple:
    return (program_id, lane, run)


class ReviewTest(unittest.TestCase):
    """Every reason the column accepts, and the two that are not reasons."""

    def review(self, connection: Recorder, sent: proposal.Result) -> list[proposal.Drop]:
        return proposal.review(connection, sent, program_id=MINE, agent_run_id=RUN)

    def only(self, connection: Recorder, sent: proposal.Result) -> proposal.Drop:
        drops = self.review(connection, sent)
        self.assertEqual(1, len(drops), drops)
        return drops[0]

    def test_an_observation_with_a_receipt_of_this_run_is_kept(self):
        connection = Recorder(receipts={"R9": [receipt()]})

        self.assertEqual([], self.review(connection, result(observation(receipt_label="R9"))))

    def test_a_receipt_no_program_holds_is_refused_as_absent(self):
        drop = self.only(Recorder(), result(observation(receipt_label="R9")))

        self.assertEqual("no_such_receipt", drop.reason)
        self.assertEqual("R9", drop.cited)

    def test_a_receipt_another_program_holds_is_refused_as_another_programs(self):
        # A label is unique per Program and not globally, so the same spelling
        # resolves in both. `rk2_runtime` sees every Program -- which is what
        # makes this provable rather than indistinguishable from absence.
        connection = Recorder(receipts={"R9": [receipt(program_id=THEIRS)]})

        drop = self.only(connection, result(observation(receipt_label="R9")))

        self.assertEqual("receipt_other_program", drop.reason)

    def test_a_proxy_internal_receipt_is_refused_by_the_lane_it_is_in(self):
        connection = Recorder(receipts={"R9": [receipt(lane="proxy_internal")]})

        drop = self.only(connection, result(observation(receipt_label="R9")))

        self.assertEqual("receipt_proxy_internal", drop.reason)

    def test_a_receipt_from_another_run_is_refused_even_in_this_program(self):
        connection = Recorder(receipts={"R9": [receipt(run=OTHER_RUN)]})

        drop = self.only(connection, result(observation(receipt_label="R9")))

        self.assertEqual("receipt_other_run", drop.reason)

    def test_a_receipt_behind_no_tool_run_is_not_claimed_to_belong_to_another(self):
        # `receipt_other_run` is a statement about which run produced the
        # Receipt. Nothing here can produce that statement, and unprovable is
        # not the same as false.
        connection = Recorder(receipts={"R9": [receipt(run=None)]})

        self.assertEqual([], self.review(connection, result(observation(receipt_label="R9"))))

    def test_a_tool_run_of_this_program_is_kept_and_an_unknown_one_is_refused(self):
        held = Recorder(tool_runs={"T1": [(MINE, RUN)]})
        self.assertEqual([], self.review(held, result(observation(tool_run_label="T1"))))

        drop = self.only(Recorder(), result(observation(tool_run_label="T1")))
        self.assertEqual("no_such_tool_run", drop.reason)

    def test_a_tool_run_another_program_holds_is_refused_as_a_foreign_label(self):
        connection = Recorder(tool_runs={"T1": [(THEIRS, OTHER_RUN)]})

        drop = self.only(connection, result(observation(tool_run_label="T1")))

        self.assertEqual("label_other_program", drop.reason)

    def test_an_observation_citing_neither_provenance_is_refused(self):
        drop = self.only(Recorder(), result(observation()))

        self.assertEqual("no_provenance", drop.reason)
        self.assertIsNone(drop.cited)

    def test_an_observation_citing_both_provenances_is_refused_as_neither(self):
        # Not twice as well evidenced: ambiguous about which evidence it means,
        # which is migration 0007's rule for the canonical row too.
        connection = Recorder(
            receipts={"R9": [receipt()]}, tool_runs={"T1": [(MINE, RUN)]}
        )

        drop = self.only(
            connection, result(observation(receipt_label="R9", tool_run_label="T1"))
        )

        self.assertEqual("no_provenance", drop.reason)

    def test_a_blank_provenance_label_is_no_provenance_rather_than_a_lookup(self):
        connection = Recorder()

        drop = self.only(connection, result(observation(receipt_label="   ")))

        self.assertEqual("no_provenance", drop.reason)
        self.assertEqual([], connection.statements)

    def test_a_subject_in_another_program_is_refused_even_with_good_provenance(self):
        # The one way a Program boundary can be crossed by citation rather than
        # by query: the provenance is this Program's and the subject is not.
        connection = Recorder(
            receipts={"R9": [receipt()]}, entities={"EP7": [(THEIRS,)]}
        )

        drop = self.only(
            connection, result(observation(receipt_label="R9", subject_label="EP7"))
        )

        self.assertEqual("label_other_program", drop.reason)
        self.assertEqual("EP7", drop.cited)

    def test_a_subject_this_mission_is_proposing_is_not_yet_a_foreign_label(self):
        # An Entity proposed in the same result has no row to resolve to. An
        # absent subject is the promotion step's problem; refusing it here would
        # refuse exactly the elements a Mission exists to submit.
        connection = Recorder(receipts={"R9": [receipt()]})

        self.assertEqual(
            [],
            self.review(
                connection, result(observation(receipt_label="R9", subject_label="EP99"))
            ),
        )

    def test_each_refused_element_names_where_in_the_submission_it_was(self):
        connection = Recorder(receipts={"R9": [receipt()]})
        sent = result(
            observation(receipt_label="R9"),
            observation(),
            observation(receipt_label="R404"),
        )

        drops = self.review(connection, sent)

        self.assertEqual(
            [("observations[1]", 0), ("observations[2]", 1)],
            [(drop.element_path, drop.ordinal) for drop in drops],
        )

    def test_only_observations_are_checked_against_rows_that_already_exist(self):
        # The other five lists propose things that do not exist yet. Checking
        # them against canonical rows would drop every one of them -- including
        # the Relationship below, whose two endpoints are the Entity proposed
        # beside it and one this Program has never seen.
        connection = Recorder()
        sent = proposal.Result(
            payload={
                "new_entities": [{"type": "endpoint", "value": "/admin"}],
                "relationships": [
                    {"kind": "serves", "from_ordinal": 0, "to_label": "HST99"}
                ],
                "hypotheses": [{"statement": "reflected", "subject_label": "EP99"}],
                "evidence": [{"hypothesis_ordinal": 0, "observation_ordinal": 0}],
                "suggested_tasks": [{"kind": "hunt", "rationale": "the parameter reflects"}],
            }
        )

        self.assertEqual([], self.review(connection, sent))
        self.assertEqual([], connection.statements)

    def test_an_element_that_is_not_an_object_is_left_out_of_the_walk(self):
        connection = Recorder()
        sent = proposal.Result(payload={"observations": ["a header was absent", 7]})

        self.assertEqual([], self.review(connection, sent))

    def test_a_payload_whose_element_list_is_not_a_list_is_not_walked(self):
        for value in ("observations", {"receipt_label": "R9"}, None, 3):
            with self.subTest(value=value):
                sent = proposal.Result(payload={"observations": value})
                self.assertEqual([], self.review(Recorder(), sent))


class CompletionTest(unittest.TestCase):
    """The claim, clamped to a word the column accepts."""

    def test_each_word_the_column_accepts_survives_the_clamp(self):
        for stated in proposal.COMPLETIONS:
            with self.subTest(status=stated):
                sent = result(completion_claim={"status": stated, "why": "measured"})
                self.assertEqual(stated, sent.completion)

    def test_anything_else_is_the_absence_of_a_claim_rather_than_a_partial_one(self):
        # "The agent said nothing legible about whether it finished" and "the
        # agent said it half finished" are different claims, and only one of
        # them was made.
        for claim in ({"status": "mostly"}, {"status": None}, {}, "done", None, []):
            with self.subTest(claim=claim):
                self.assertEqual(
                    proposal.UNCLAIMED, result(completion_claim=claim).completion
                )

    def test_a_result_with_no_claim_at_all_is_unproven(self):
        self.assertEqual(proposal.UNCLAIMED, proposal.Result().completion)


class StageTest(unittest.TestCase):
    """The whole write an executing role can cause, and its edges."""

    def stage(self, connection: Recorder, sent: proposal.Result) -> proposal.Staged:
        return proposal.stage(
            connection, sent, program_id=MINE, agent_run_id=RUN, task_id=TASK
        )

    def test_the_only_tables_written_are_the_two_staging_ones(self):
        connection = Recorder(receipts={"R9": [receipt()]})

        self.stage(connection, result(observation(receipt_label="R9"), observation()))

        written = [
            sql for sql in connection.statements if sql.lstrip().upper().startswith("INSERT")
        ]
        self.assertEqual([proposal.INSERT, proposal.INSERT_DROP], written)
        for sql in written:
            with self.subTest(sql=sql[:40]):
                self.assertRegex(sql, r"INSERT INTO (proposals|proposal_drops)\b")

    def test_neither_the_label_nor_the_status_is_supplied_by_the_caller(self):
        # A caller that could pass either could pass `promoted`.
        self.assertNotIn("label", proposal.INSERT.split("VALUES")[0])
        self.assertNotIn("status", proposal.INSERT.split("VALUES")[0])

        staged = self.stage(Recorder(), proposal.Result())

        self.assertEqual("PR1", staged.label)
        self.assertEqual(proposal.STAGED, staged.status)

    def test_the_payload_is_stored_as_it_arrived(self):
        # Storing the walk instead of the submission would make the row a
        # summary of what the runtime understood rather than what was sent.
        connection = Recorder()
        sent = proposal.Result(payload={"observations": ["shapeless"], "notes": "hello"})

        self.stage(connection, sent)

        parameters = next(p for sql, p in connection.calls if sql == proposal.INSERT)
        self.assertEqual({"observations": ["shapeless"], "notes": "hello"},
                         json.loads(parameters[3]))
        self.assertEqual(proposal.UNCLAIMED, parameters[4])

    def test_the_drops_commit_with_the_proposal_they_belong_to(self):
        # A proposal whose drops did not commit with it would read as a
        # proposal that passed provenance.
        connection = Recorder()

        self.stage(connection, result(observation()))

        order = connection.statements
        self.assertLess(order.index("BEGIN"), order.index(proposal.INSERT))
        self.assertLess(order.index(proposal.INSERT_DROP), order.index("COMMIT"))

    def test_a_refused_element_is_staged_with_the_proposal_rather_than_dropped(self):
        connection = Recorder()

        staged = self.stage(connection, result(observation(), observation()))

        self.assertEqual(proposal.STAGED, staged.status)
        self.assertEqual(2, len(staged.drops))
        self.assertEqual(
            {"no_provenance"}, {drop.reason for drop in staged.drops}
        )

    def test_the_staged_row_reports_itself_as_the_wire_answer_it_becomes(self):
        connection = Recorder()

        staged = self.stage(connection, result(observation()))

        self.assertEqual(
            {
                "proposal_id": PROPOSAL,
                "label": "PR1",
                "status": proposal.STAGED,
                "completion": proposal.UNCLAIMED,
                "drops": [
                    {
                        "ordinal": 0,
                        "element_path": "observations[0]",
                        "reason": "no_provenance",
                        "cited": None,
                    }
                ],
            },
            staged.as_dict(),
        )

    def test_every_drop_of_one_proposal_has_its_own_ordinal(self):
        # `proposal_drops` is keyed on (proposal_id, ordinal), so two drops
        # sharing one would be one drop and a constraint violation.
        connection = Recorder()

        staged = self.stage(connection, result(observation(), observation(), observation()))

        self.assertEqual([0, 1, 2], [drop.ordinal for drop in staged.drops])


class CorpusTest(unittest.TestCase):
    """The words this module writes, against the words the column accepts."""

    def test_every_reason_is_one_the_check_constraint_admits(self):
        text = CORPUS.read_text(encoding="utf-8")
        constraint = re.search(r"reason\s+text NOT NULL\s+CHECK \(reason IN \((.*?)\)\)",
                               text, re.S)
        self.assertIsNotNone(constraint)
        admitted = set(re.findall(r"'([a-z_]+)'", constraint.group(1)))

        self.assertEqual(admitted, set(proposal.REASONS))

    def test_every_completion_is_one_the_check_constraint_admits(self):
        text = CORPUS.read_text(encoding="utf-8")
        constraint = re.search(r"completion\s+text NOT NULL\s+CHECK \(completion IN \((.*?)\)\)",
                               text, re.S)
        self.assertIsNotNone(constraint)
        admitted = set(re.findall(r"'([a-z_]+)'", constraint.group(1)))

        self.assertEqual(admitted, set(proposal.COMPLETIONS))
        self.assertIn(proposal.UNCLAIMED, admitted)

    def test_the_status_this_module_writes_is_the_column_default(self):
        text = CORPUS.read_text(encoding="utf-8")

        self.assertIn(f"status       text NOT NULL DEFAULT '{proposal.STAGED}'", text)


if __name__ == "__main__":
    unittest.main()
