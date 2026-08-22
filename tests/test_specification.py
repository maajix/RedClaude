"""Ticket 141: the door a run authors a Test specification through.

Three halves of one claim, which is why they are in one module. The roster half
is what a model is offered and what the gate refuses before a handler sees it;
the launch half is what crosses the pipe and what a run is charged for; the
corpus half is that the verb on the other side of that pipe exists, is granted,
and closes over the same five parts the shape rule reads.

None of it asserts whether a particular specification *should* be stored. That
is `rk2_test_spec_problem`, thirty rules deep, on a document this process never
sees, and a second opinion about it on this side is exactly what the two-step
shape exists to avoid.
"""

import asyncio
import contextlib
import io
import json
import re
import types
import unittest
from unittest import mock

from redkraken import _launch, isolation, packet, roster
from tests import ROOT


MIGRATIONS = ROOT / "src" / "redkraken" / "migrations"

#: The tool as the CLI spells it, and as the bare name the MCP server registers.
TOOL = "mcp__rk2__propose_test"
BARE = "propose_test"

#: One well-formed plan, reused. Three actions because a Test carries all three
#: roles and cannot do that in fewer, and two assertions because the two kinds
#: take different fields -- a status, or a second action to compare against.
PLAN = {
    "hypothesis_label": "H7",
    "preconditions": [
        {"kind": "scope_holds", "detail": "the application is a target of the live scope"}
    ],
    "setup": [],
    "actions": [
        {
            "ordinal": 1,
            "role": "baseline",
            "kind": "request",
            "method": "GET",
            "url": "https://app.example.test/orders/1",
        },
        {
            "ordinal": 2,
            "role": "variant",
            "kind": "request",
            "method": "GET",
            "url": "https://app.example.test/orders/2",
        },
        {
            "ordinal": 3,
            "role": "control",
            "kind": "request",
            "method": "GET",
            "url": "https://app.example.test/orders/9999",
        },
    ],
    "assertions": [
        {"id": "variant-reads", "kind": "status_equals", "action": 2, "status": 200},
        {"id": "control-differs", "kind": "status_differs", "action": 3, "against": 2},
    ],
    "cleanup": [],
}


@contextlib.contextmanager
def packaged():
    """The SDK's two constructors, recorded instead of imported.

    Stands in for `claude_agent_sdk.tool` and `create_sdk_mcp_server` so the
    handlers can be exercised on a checkout with no SDK. What the handler does
    is this application's code -- refuse while the surface is closed, carry the
    arguments it declares, report a refusal as a refusal -- and none of that is
    the pair's.
    """
    served: dict[str, types.SimpleNamespace] = {}

    def stand_in(name: str, description: str, schema: dict):
        def decorator(handler):
            served[name] = types.SimpleNamespace(
                name=name, description=description, input_schema=schema, handler=handler
            )
            return served[name]

        return decorator

    def collect(*, name, version, tools):
        return types.SimpleNamespace(name=name, version=version, tools=tools)

    with (
        mock.patch.object(_launch, "tool", stand_in, create=True),
        mock.patch.object(_launch, "create_sdk_mcp_server", collect, create=True),
    ):
        yield served


class Supervisor:
    """A runtime that answers a script and remembers what it was asked for.

    The side of the pipe that holds a database, which is the whole of what it is
    here: `propose_test` decides out of rows the child cannot see, and what is
    asserted on this side is what was carried, what came back and what the run
    was charged for.
    """

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict]] = []

    def call(self, verb: str, arguments) -> dict:
        self.calls.append((verb, dict(arguments)))
        return self.answers.pop(0) if self.answers else {}


class SpecificationContractTest(unittest.TestCase):
    """What the model is offered, before any of it has been called."""

    def setUp(self):
        self.contract = roster.CONTRACTS[TOOL]

    def test_the_tool_asks_rather_than_writes_the_table_it_leads_to(self):
        # The rule that decided the shape. `tests` is canonical, so a Contract
        # naming it would not compile; what this one writes is the audit row
        # beside it, and the runtime decides whether a Test comes of the ask.
        self.assertIn("tests", roster.CANONICAL)
        self.assertEqual(("test_proposals",), self.contract.writes)
        self.assertEqual(roster.REQUEST, self.contract.direction)
        for name, contract in roster.CONTRACTS.items():
            with self.subTest(tool=name):
                self.assertNotIn("tests", contract.writes)

    def test_it_sits_beside_the_finding_it_makes_reachable(self):
        # One group, because they are one role's account of one piece of work:
        # the Test that settles the claim and the Finding the settled claim
        # justifies. `_check_authority` keeps that group off the role that
        # schedules, so neither ask reaches the party that hands out the work.
        self.assertEqual("state.propose", self.contract.group)
        self.assertIn(TOOL, roster.TOOL_GROUPS["state.propose"])
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                if TOOL in role.tools:
                    self.assertNotIn("sched.pick", role.tool_groups)

    def test_the_hunting_role_holds_it_and_the_validator_does_not(self):
        # The role that holds a testable claim is the role that authors the plan
        # for it. A validator judges a Finding out of a packet and holds nothing
        # else, so a plan-authoring tool on its surface would be a second thing
        # in a world that is meant to be one packet wide.
        self.assertIn(TOOL, roster.ROLES["web_hunter"].tools)
        self.assertNotIn(TOOL, roster.ROLES["validator"].tools)
        self.assertNotIn(TOOL, roster.ROLES["orchestrator"].tools)

    def test_the_five_parts_are_the_parts_and_the_two_grants_are_not(self):
        # A stored specification may also carry `impact` and `pivot`. Neither is
        # here, because neither is a plan: an impact block is what an operator's
        # grant is measured against and a pivot block claims a capability. A
        # model that could write either would be authorizing its own impact.
        self.assertEqual(
            {"hypothesis_label", *_launch.SPECIFICATION_PARTS},
            set(self.contract.arguments),
        )
        for withheld in ("impact", "pivot"):
            with self.subTest(part=withheld):
                self.assertNotIn(withheld, self.contract.arguments)

    def test_no_argument_of_it_is_unconstrained(self):
        # Including every field of every element. `_check_argument` already
        # refuses a contract that declares an open argument without an
        # `OPEN_ARGUMENTS` entry saying why; this is the same claim read off the
        # contract, and the reason it is worth reading is that the honest way to
        # ship this tool quickly would have been one free-text `spec` object.
        self.assertNotIn(TOOL, roster.OPEN_ARGUMENTS)
        for name, argument in self.contract.arguments.items():
            with self.subTest(argument=name):
                self.assertFalse(argument.free_text)
                self.assertTrue(argument.constrained)
                for field, shape in (argument.element or {}).items():
                    with self.subTest(field=field):
                        self.assertFalse(shape.free_text)
                        self.assertTrue(shape.constrained)

    def test_the_assertion_identifier_is_the_one_a_verdict_can_name(self):
        # A validator reports a failed assertion by this identifier. An
        # identifier a Test could be authored with and a verdict could not name
        # would be a failure nobody can report, so the two patterns are one
        # pattern and this is what says so.
        authored = self.contract.arguments["assertions"].element["id"]
        named = roster.CONTRACTS["mcp__rk2__submit_verdict"].arguments[
            "failed_assertion_ids"
        ]

        self.assertEqual(named.items_pattern, authored.pattern)


class SpecificationGateTest(unittest.TestCase):
    """What the gate refuses, which is the half the CLI checks first.

    Every refusal here is one the model can correct and re-send inside the same
    run, which is the whole reason the closed vocabularies are in the schema and
    the thirty shape rules are not.
    """

    def gate(self) -> roster.Gate:
        gate = roster.Gate("web_hunter")
        gate.bind("agent-1", "web_hunter")
        return gate

    def call(self, **overrides) -> roster.Call:
        return roster.Call(
            tool=TOOL,
            arguments={**PLAN, **overrides},
            agent_id="agent-1",
            agent_type="web_hunter",
        )

    def test_a_well_formed_plan_is_a_call_the_gate_allows(self):
        self.assertIsNone(self.gate().decide(self.call()))

    def test_a_plan_that_leaves_a_part_out_is_still_a_call_the_gate_allows(self):
        # Three of the five parts are optional and an empty one is legitimate,
        # so leaving one out has to reach the runtime rather than being refused
        # here. The handler is what makes the two spellings one document.
        thin = dict(PLAN)
        for part in ("preconditions", "setup", "cleanup"):
            thin.pop(part)

        self.assertIsNone(
            self.gate().decide(
                roster.Call(
                    tool=TOOL, arguments=thin, agent_id="agent-1", agent_type="web_hunter"
                )
            )
        )

    def test_a_word_outside_a_closed_vocabulary_is_refused_by_name(self):
        # `context` is an evidence role and is not an action role, which is the
        # one word `EVIDENCE_ROLES` has and `TEST_ACTION_ROLES` does not.
        strayed = [dict(action) for action in PLAN["actions"]]
        strayed[2]["role"] = "context"

        denial = self.gate().decide(self.call(actions=strayed))

        self.assertIsNotNone(denial)
        self.assertEqual(roster.INVALID_ARGUMENT, denial.rule)
        self.assertIn("baseline, variant, control", denial.reason)

    def test_a_plan_with_too_few_actions_is_refused_by_the_bound(self):
        # The floor follows from the roles rather than standing on its own: a
        # Test carries all three and cannot do that in fewer than three actions.
        denial = self.gate().decide(self.call(actions=PLAN["actions"][:2]))

        self.assertIsNotNone(denial)
        self.assertIn("3-32", denial.reason)

    def test_a_part_this_specification_has_no_room_for_is_refused(self):
        denial = self.gate().decide(self.call(teardown=[]))

        self.assertIsNotNone(denial)
        self.assertIn("teardown", denial.reason)

    def test_a_url_is_bounded_by_its_length_and_not_by_its_shape(self):
        # The decision this contract takes about where a rule lives. A relative
        # url passes here and is refused by `rk2_test_request_problem` with a
        # sentence naming the action it found it in, which is strictly more than
        # a rejected call quoting a regex could have said.
        relative = [dict(action) for action in PLAN["actions"]]
        relative[0]["url"] = "/orders/1"

        self.assertIsNone(self.gate().decide(self.call(actions=relative)))
        self.assertIsNotNone(
            self.gate().decide(
                self.call(
                    actions=[{**PLAN["actions"][0], "url": "h" * 2001}, *PLAN["actions"][1:]]
                )
            )
        )


class SpecificationAskTest(unittest.TestCase):
    """The launch half: what crosses, what comes back and what it costs."""

    def authoring(self, stack, *answers):
        surface = _launch.Surface()
        supervisor = Supervisor(*answers)
        specification = _launch.Specification(supervisor)
        offered = stack.enter_context(packaged())
        _launch.server(
            surface,
            packet.Reader(packet.Packet()),
            _launch.Submission(),
            specification=specification,
        )
        surface.open()
        return offered[BARE], specification, supervisor

    def answer(self, packaged_tool, arguments: dict) -> dict:
        wire = asyncio.run(packaged_tool.handler(arguments))
        return json.loads(wire["content"][0]["text"])

    def test_the_plan_crosses_as_one_frame_carrying_what_it_declares(self):
        # And nothing beside it. Which Program and which Agent run this belongs
        # to are settled on the other side of the pipe, and the digest that will
        # be this Test's identity is the database's.
        out = io.StringIO()
        answered = json.dumps(
            {isolation.ANSWER: {"outcome": "created", "test": "TST1"}, "id": 1}
        )
        channel = _launch.Channel(out, io.StringIO(answered + "\n"))

        served = _launch.Specification(channel).ask(PLAN)

        self.assertEqual({"outcome": "created", "test": "TST1"}, served)
        self.assertEqual(
            {**PLAN, "verb": TOOL}, json.loads(out.getvalue())[isolation.CALL]
        )

    def test_a_part_left_out_crosses_as_an_empty_part(self):
        # `tests` is immutable and its identity is the digest of the stored
        # document, so a missing key and an empty array have to reach
        # `rk2_test_spec_digest` as one document. Two spellings would author two
        # Tests for one plan, and the second would not be a correction of the
        # first -- it would be a second Test.
        supervisor = Supervisor({"outcome": "created", "test": "TST1"})
        thin = {name: PLAN[name] for name in ("hypothesis_label", "actions", "assertions")}

        _launch.Specification(supervisor).ask(thin)

        verb, carried = supervisor.calls[0]
        self.assertEqual(TOOL, verb)
        self.assertEqual({"hypothesis_label", *_launch.SPECIFICATION_PARTS}, set(carried))
        for part in ("preconditions", "setup", "cleanup"):
            with self.subTest(part=part):
                self.assertEqual([], carried[part])

    def test_what_the_runtime_answered_is_what_the_model_reads(self):
        # The document `propose_test` returns, carried through unchanged. A
        # handler that summarised it would be deciding which of the facts the
        # database stated the model may act on -- and the digest is one of them.
        authored = {
            "outcome": "created",
            "test": "TST3",
            "hypothesis": "H7",
            "spec_sha256": "9f61fcc1d056225f3bd3774b62bb19a197087c43ff31c80595257425354024cf",
            "actions": 3,
            "assertions": 2,
        }
        with contextlib.ExitStack() as stack:
            offering, _, _ = self.authoring(stack, authored)

            self.assertEqual(authored, self.answer(offering, PLAN))

    def test_a_refusal_names_the_rule_and_is_not_raised(self):
        # Ticket 35 made `rk2_test_spec_problem` a function rather than a CHECK
        # so that the sentence naming the broken rule could be carried back to
        # whoever wrote the plan. This is the last link in that carry, and an
        # exception here would deliver the failure without the sentence.
        refusal = {
            "outcome": "refused",
            "refusal": "action 1 states no absolute http or https url in canonical form",
        }
        with contextlib.ExitStack() as stack:
            offering, _, _ = self.authoring(stack, refusal)

            self.assertEqual(refusal, self.answer(offering, PLAN))

    def test_a_refused_plan_is_charged_and_a_created_or_existing_one_is_not(self):
        # What the ceiling bounds is a run filling `test_proposals` with plans
        # nobody wanted. An `existing` outcome is the opposite of that: a run
        # that reached the plan another run had already reached, which is two
        # independent answers to one question and not a mistake.
        with contextlib.ExitStack() as stack:
            offering, specification, _ = self.authoring(
                stack,
                {"outcome": "refused", "refusal": "a Test performs at least one control action"},
                {"outcome": "created", "test": "TST1"},
                {"outcome": "existing", "test": "TST1"},
            )

            for _ in range(3):
                self.answer(offering, PLAN)

        self.assertEqual(3, specification.attempts)
        self.assertEqual(1, specification.refused)

    def test_the_ceiling_answers_a_token_and_carries_nothing(self):
        # Not a raise and not a silence. The model is told what it spent and
        # that this one was not asked, which is the only answer it can act on;
        # the supervisor is never asked at all, which is the point of a ceiling
        # on this side rather than on the other one.
        refused = {"outcome": "refused", "refusal": "no"}
        with contextlib.ExitStack() as stack:
            offering, specification, supervisor = self.authoring(
                stack, *[refused] * _launch.REFUSED_SPECIFICATIONS
            )

            for _ in range(_launch.REFUSED_SPECIFICATIONS):
                self.answer(offering, PLAN)
            stopped = self.answer(offering, PLAN)

        self.assertEqual(_launch.REFUSED_SPECIFICATIONS, len(supervisor.calls))
        self.assertFalse(stopped["served"])
        self.assertEqual(_launch.SPENT_SPECIFICATIONS, stopped["reason"])
        self.assertEqual(_launch.REFUSED_SPECIFICATIONS, stopped["refused"])
        self.assertEqual(_launch.REFUSED_SPECIFICATIONS + 1, stopped["attempts"])
        self.assertEqual(_launch.REFUSED_SPECIFICATIONS, specification.refused)

    def test_the_ceiling_is_wider_than_the_finding_proposals_ceiling(self):
        # And the reason is the refusal rather than taste. `rk2_finding_refusal`
        # is eight arms of which two are correctable, so three attempts is one
        # more than the correctable mistakes. `rk2_test_spec_problem` answers
        # with the *first* problem it finds, walking five parts in a fixed
        # order, so a converging run learns at most one thing per part -- and a
        # ceiling at three would cut off a run that was still being told
        # something new.
        self.assertGreater(_launch.REFUSED_SPECIFICATIONS, _launch.REFUSED_PROPOSALS)
        self.assertEqual(len(_launch.SPECIFICATION_PARTS) + 1, _launch.REFUSED_SPECIFICATIONS)

    def test_the_ceiling_is_this_runs_and_not_this_processs(self):
        # One Agent run, one count. A second run starting with the refusals of
        # the run before it would be a ceiling on the harness rather than on the
        # loop it exists to stop.
        spent = _launch.Specification(Supervisor())
        spent.refused = _launch.REFUSED_SPECIFICATIONS

        self.assertEqual(_launch.SPENT_SPECIFICATIONS, spent.ask(PLAN)["reason"])
        self.assertEqual(0, _launch.Specification(Supervisor()).refused)

    def test_a_supervisor_that_could_not_be_reached_charges_nothing(self):
        # Only the database's own word counts. A pipe that answered nothing has
        # not refused a specification, because nobody read one, and charging the
        # run for that would spend a ceiling on the runtime's own trouble.
        specification = _launch.Specification(Supervisor({"served": False, "reason": "x"}))

        specification.ask(PLAN)

        self.assertEqual(1, specification.attempts)
        self.assertEqual(0, specification.refused)

    def test_a_run_with_no_supervisor_says_so_and_authors_nothing(self):
        # The allowlist is the role's and not the job's, so the tool is built
        # for every run -- and a run whose installation described no store and
        # no connection answers that rather than writing into a pipe nobody is
        # reading.
        surface = _launch.Surface()
        with packaged() as offered:
            _launch.server(surface, packet.Reader(packet.Packet()), _launch.Submission())
        surface.open()

        served = self.answer(offered[BARE], PLAN)

        self.assertFalse(served["served"])
        self.assertEqual(_launch.NO_TOOLING, served["reason"])

    def test_the_tool_refuses_while_the_surface_is_closed(self):
        surface = _launch.Surface()
        with packaged() as offered:
            _launch.server(
                surface,
                packet.Reader(packet.Packet()),
                _launch.Submission(),
                specification=_launch.Specification(Supervisor()),
            )

        with self.assertRaises(_launch.Closed):
            asyncio.run(offered[BARE].handler(PLAN))


class SpecificationCorpusTest(unittest.TestCase):
    """The other side of the pipe, read out of the migrations that create it.

    Read as text and not through a connection, for `RelationAgreementTest`'s
    reason: the corpus is where the grants, the tables and the function bodies
    are written, and a check that needs PostgreSQL is a check that is skipped in
    the loop where this Contract is actually edited.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(MIGRATIONS.glob("*.sql"))
        }
        cls.sql = "\n".join(cls.corpus.values())

    def body(self, function: str) -> str:
        """One `CREATE FUNCTION` body, from the signature to the closing tag."""
        opened = re.search(rf"CREATE FUNCTION {function}\(", self.sql)
        self.assertIsNotNone(opened, f"the corpus creates no {function}")
        return self.sql[opened.end() : self.sql.index("$fn$;", opened.end())]

    def test_the_declared_write_target_is_a_table_the_corpus_creates(self):
        for relation in roster.CONTRACTS[TOOL].writes:
            with self.subTest(relation=relation):
                self.assertIn(f"CREATE TABLE {relation} (", self.sql)

    def test_the_verb_behind_it_writes_both_tables_and_is_granted_to_the_runtime(self):
        # The two-step, read off the one function that performs it: the audit row
        # for every attempt, and the canonical row for the ones that were not
        # refused. Before this verb the corpus's only writers of `tests` took a
        # Finding or seeded a fixture, so a hunt could not reach either.
        authored = self.body("propose_test")

        self.assertIn("INSERT INTO test_proposals", authored)
        self.assertIn("INSERT INTO tests (", authored)
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION propose_test(text, jsonb, uuid) TO rk2_runtime",
            self.sql,
        )
        self.assertIn("'propose_test(text, jsonb, uuid)'", self.sql)

    def test_a_refusal_is_the_shape_rules_own_sentence(self):
        # Criterion 4. The rule is a function so that its answer can be written
        # down and carried back; a caller that let the CHECK raise instead would
        # hand the model a constraint name and hand nobody the reason.
        authored = self.body("propose_test")

        self.assertIn("rk2_test_spec_problem(", authored)
        self.assertIn("'refused', v_refusal", authored)
        self.assertIn("CREATE FUNCTION rk2_test_spec_problem(p_spec jsonb) RETURNS text", self.sql)

    def test_the_parts_the_contract_serves_are_the_parts_the_rule_reads(self):
        # The drift that would matter most and would be silent: a part the
        # schema offers and the rule has no room for is refused by name after
        # the model has already been told the key exists, and a part the rule
        # requires and the schema does not offer cannot be sent at all.
        declared = self.body("rk2_test_spec_problem")
        opened = declared.index("v_parts")
        listed = declared.index("ARRAY[", opened)
        parts = tuple(
            re.findall(r"'([^']*)'", declared[listed : declared.index("]", listed)])
        )

        self.assertEqual(set(parts), set(_launch.SPECIFICATION_PARTS))
        self.assertEqual(
            set(parts), set(roster.CONTRACTS[TOOL].arguments) - {"hypothesis_label"}
        )

    def test_the_audit_row_survives_a_proposal_that_named_no_claim(self):
        # The one refusal that is filed before anything about the specification
        # has been looked at. A NOT NULL claim on the proposal table would turn
        # that refusal into a raise, and the record of the attempt would be the
        # one an operator most wants and the only one missing.
        created = self.sql.index("CREATE TABLE test_proposals (")
        columns = self.sql[created : self.sql.index(");", created)]

        self.assertRegex(columns, r"hypothesis_id\s+uuid,")
        self.assertIn("outcome IN ('created', 'existing', 'refused')", columns)


if __name__ == "__main__":
    unittest.main()
