"""The execution slice: what it does in what order, and what it leaves open.

Nothing here talks to a database or starts a container. What is worth testing
without either is the sequence -- which statement happens before which, what a
step does when the one before it failed, and whether the closing runs anyway --
and a suite that needed a live engine to ask those questions would ask them
once a day instead of on every change. `test_database.ExecutionSliceTest` runs
the same sequence against real rows; this one runs it against a recorder that
answers every statement and remembers all of them.
"""

from __future__ import annotations

import contextlib
import json
import unittest
from unittest import mock

from redkraken import agent, execution, isolation, packet, pg, program, proposal, proxy, roster
from redkraken.outcome import Ledger
from tests import fixtures


PROGRAM = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"
TASK = "33333333-3333-4333-8333-333333333333"
TOOL_RUN = "44444444-4444-4444-8444-444444444444"
PROPOSAL = "55555555-5555-4555-8555-555555555555"

CAPABILITY = "c0ffee" * 10 + "cafe"

#: The one described boundary every test here starts a child inside. The engine
#: never runs: `Slice.launch` is replaced, and what is asserted is what the
#: request handed to it says.
BOUNDARY = fixtures.boundary()

#: The agent connection string the packet would be compiled on. Never opened:
#: every test here replaces the compile, and what it is pointed at is only
#: asserted to be carried rather than invented.
STATE = pg.settings_from_url(
    "postgresql://rk2_state:unused@127.0.0.1:5432/rk2", application_name="rk run"
)


def database_error(message: str) -> pg.DatabaseError:
    """One server error, in the field shape the wire protocol delivers them in."""
    return pg.DatabaseError({"C": "23514", "M": message})


def claimed(**overrides) -> execution.Claimed:
    fields = {
        "agent_run_id": RUN,
        "agent_run_label": "AR7",
        "role": "recon",
        "task_id": TASK,
        "task_label": "T3",
        "kind": "recon",
        "attempts": 1,
        "subject_type": "endpoint",
        "subject_label": "GET /login",
        "method": "GET",
        "url": "https://app.example.com/login",
    }
    fields.update(overrides)
    return execution.Claimed(**fields)


def started_row(**overrides) -> tuple:
    """One `STARTED` row, in the column order the query selects them."""
    subject = claimed(**overrides)
    return (
        subject.agent_run_id,
        subject.agent_run_label,
        subject.role,
        subject.task_id,
        subject.task_label,
        subject.kind,
        subject.attempts,
        subject.subject_type,
        subject.subject_label,
        subject.method,
        subject.url,
    )


def result(**overrides) -> agent.AgentRunResult:
    fields = {
        "agent_run_id": RUN,
        "role": "recon",
        "sdk_version": "0.1.0",
        "cli_version": "1.0.0",
        "api_key_source": "none",
        "tool_ready": 1,
        "tools_served": ("mcp__rk2__http_request",),
        "denials": (),
        "answers": 2,
        "stop_reason": "completed",
        "text": "the login form is served over HTTPS",
        "mission_result": {
            "completion": "complete",
            "observations": [
                {
                    "kind": "response",
                    "summary": "the login form is served over HTTPS",
                    "receipt_label": "RC1",
                }
            ],
        },
        "mission_attempts": 1,
    }
    fields.update(overrides)
    return agent.AgentRunResult(**fields)


#: `offer_slate()`'s own columns, as the server names them. Spelled out because
#: the slice reads the answer by name: a recorder that returned bare tuples
#: would let a column order change pass every test in this file.
SLATE_COLUMNS = (
    "ordinal", "task_label", "kind", "subject_label",
    "priority", "factors", "entitled", "expires_at",
)


def slate_row(ordinal: int) -> tuple:
    """One offered entry, in the wire shapes this client actually decodes.

    `priority`, `factors` and `expires_at` stay text on purpose -- numeric,
    jsonb and timestamptz are none of the three types `pg` decodes -- so a slice
    that assumed a parsed value would be assuming it here too.
    """
    return (
        ordinal,
        f"T{ordinal}",
        "recon",
        "EN1",
        "0.500000",
        '{"novelty": 1.0, "cost": 0.3}',
        ordinal == 1,
        "2026-08-13 17:05:00+00",
    )


class Recorder:
    """A connection that answers every statement the slice issues, and keeps them.

    Answers are keyed on the whole statement rather than on a fragment of it,
    for the reason `test_proposal` keys its own that way: two of these are
    updates to the same table, and a recorder that matched loosely would answer
    a closing with an opening's row.
    """

    def __init__(self, **answers):
        self.calls: list[tuple[str, tuple]] = []
        self.slate = answers.get("slate", 1)
        self.claim = answers.get("claim", "AR7")
        self.started = answers.get("started", (started_row(),))
        self.gate = answers.get(
            "gate",
            {
                "decision": "allow",
                "risk_class": "constrained",
                "rule": "net_get",
                "capability": CAPABILITY,
            },
        )
        self.lifetime = answers.get("lifetime", 300.0)
        self.receipt = answers.get("receipt", ("RC1", "allowed", 200))
        self.promotion = answers.get(
            "promotion",
            {
                "proposal": "PR1",
                "status": "promoted",
                "repeated": False,
                "observations": ["OB1"],
                "refused": 0,
            },
        )
        self.fingerprint = answers.get(
            "fingerprint", {"applications": 1, "changed": 1, "fingerprints": []}
        )
        self.closure = answers.get(
            "closure",
            {
                "agent_run": "AR7",
                "task": "T3",
                "task_status": "done",
                "accepted": True,
                "runs_closed": 1,
                "tool_runs_closed": 0,
                "leases_released": 0,
            },
        )
        self.raises: dict[str, Exception] = answers.get("raises", {})

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        if sql in self.raises:
            raise self.raises[sql]
        columns = SLATE_COLUMNS if sql == execution.OFFER else ()
        return pg.Result(
            columns=columns, rows=tuple(self._answer(sql, parameters)), tag="SELECT"
        )

    @contextlib.contextmanager
    def transaction(self):
        self.calls.append(("BEGIN", ()))
        yield self
        self.calls.append(("COMMIT", ()))

    def __enter__(self):
        return self

    def __exit__(self, *exception) -> bool:
        return False

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def sent(self, statement: str) -> list[tuple]:
        return [parameters for sql, parameters in self.calls if sql == statement]

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql in (execution.RANK, execution.QUOTA):
            return [("{}",)]
        if sql == execution.OFFER:
            return [slate_row(n) for n in range(1, self.slate + 1)]
        if sql == execution.CLAIM:
            return [(self.claim,)]
        if sql == execution.STARTED:
            return list(self.started)
        if sql == execution.OPEN_TOOL_RUN:
            return [(TOOL_RUN, "TR9")]
        if sql == proxy.AUTHORIZE_TOOL_RUN:
            return [(json.dumps(self.gate),)]
        if sql == execution.LIFETIME:
            return [(self.lifetime,)]
        if sql == execution.EXCHANGE:
            return [self.receipt] if self.receipt else []
        if sql == execution.PROMOTE:
            return [(json.dumps(self.promotion),)]
        if sql == execution.FINGERPRINT:
            return [(json.dumps(self.fingerprint),)]
        if sql == execution.FINISH:
            return [(json.dumps(self.closure),)]
        if sql == proxy.PARK_TOOL_RUN:
            return [("PD1",)]
        if sql == proposal.INSERT:
            return [(PROPOSAL, "PR1", proposal.STAGED)]
        if sql in (
            proxy.BIND,
            execution.CAUSE,
            proxy.CLOSE_TOOL_RUN,
            proposal.INSERT_DROP,
            "SELECT set_actor('runtime', $1)",
            "SET TRANSACTION READ ONLY",
        ):
            return []
        if sql in (proposal.RECEIPT, proposal.TOOL_RUN, proposal.ENTITY):
            return self._provenance(sql, parameters)
        raise AssertionError(f"an unplanned statement was issued: {sql}")

    def _provenance(self, sql: str, parameters: tuple) -> list[tuple]:
        """Enough for one cited Receipt to ground: this Program, this run's lane."""
        if sql == proposal.RECEIPT and parameters[0] == "RC1":
            return [(PROGRAM, "agent_http", RUN)]
        return []


class Launcher:
    """A stand-in for `agent.agent_run` that records the request it was given."""

    def __init__(self, answer=None, error: Exception | None = None):
        self.requests: list[agent.AgentRunRequest] = []
        self.answer = answer
        self.error = error

    def __call__(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.answer if self.answer is not None else result()

    @property
    def only(self) -> agent.AgentRunRequest:
        assert len(self.requests) == 1, self.requests
        return self.requests[0]


@contextlib.contextmanager
def compiled(mission: packet.Packet | None = None):
    """The agent connection the Mission packet is compiled on, stood in for.

    The compile is a second connection as a second role, which is the whole
    point of it and is exactly what a suite with no database cannot open. What
    is under test either side of it is unaffected by which rows came back.
    """
    session = Recorder()
    with (
        mock.patch.object(execution.migrate, "open_connection", return_value=session),
        mock.patch.object(
            execution.state_module, "assert_agent_connection", return_value=True
        ),
        mock.patch.object(execution.state_module, "bind_agent_session", return_value=True),
        mock.patch.object(
            execution.packet_module, "compile", return_value=mission or packet.Packet()
        ),
    ):
        yield session


def attempt(connection: Recorder, launcher: Launcher | None = None, **overrides):
    """One attempt, with the ledger and facts it produced."""
    ledger = Ledger()
    runner = execution.Slice(
        boundary=BOUNDARY, state=STATE, launch=launcher or Launcher(), **overrides
    )
    facts = runner.attempt(ledger, connection, PROGRAM)
    return ledger, facts


class BoundaryTest(unittest.TestCase):
    """What a described boundary is, and what a half-described one is not."""

    environment = {
        execution.IMAGE: "rk2-agent:1",
        execution.NETWORK: "rk2-agent-network",
        execution.PROXY_CONTAINER: "rk2-proxy",
        execution.PROXY_URL: "http://rk2-proxy:18080",
        execution.CERTIFICATE: "/run/root.pem",
    }

    def test_an_empty_environment_asks_for_no_execution_at_all(self):
        self.assertFalse(execution.requested({}))
        self.assertFalse(execution.requested({"PATH": "/usr/bin"}))

    def test_one_named_variable_is_a_machine_asking_for_execution(self):
        for name in execution.CLAIMED:
            with self.subTest(name=name):
                self.assertTrue(execution.requested({name: "something"}))

    def test_the_certificate_alone_is_not_a_machine_asking_for_anything(self):
        # It is the door's name as well -- `rk send --ca` falls back to it -- so
        # an operator who exported it to talk to the fence by hand has said
        # nothing about running children, and a run that read it as a
        # half-described boundary would refuse yesterday's working command.
        self.assertNotIn(execution.CERTIFICATE, execution.CLAIMED)
        self.assertFalse(execution.requested({execution.CERTIFICATE: "/run/root.pem"}))

    def test_every_required_name_is_reported_when_it_is_missing(self):
        for name in execution.REQUIRED:
            with self.subTest(name=name):
                partial = {key: value for key, value in self.environment.items() if key != name}
                container, missing = execution.boundary(partial)
                self.assertIsNone(container)
                self.assertEqual((name,), missing)

    def test_a_described_boundary_mounts_only_what_was_named(self):
        container, missing = execution.boundary(self.environment)
        self.assertEqual((), missing)
        assert container is not None
        self.assertEqual("rk2-agent:1", container.image)
        self.assertEqual("http://rk2-proxy:18080", container.proxy_url)
        # The three directories are absent, which is the contained value: no
        # home mounted is no credential at all rather than the operator's.
        self.assertIsNone(container.application)
        self.assertIsNone(container.sdk)
        self.assertIsNone(container.home)

    def test_the_three_directories_arrive_as_paths_when_they_are_named(self):
        container, _ = execution.boundary(
            {**self.environment, execution.SDK: "/opt/sdk", execution.HOME: "/run/home"}
        )
        assert container is not None
        self.assertEqual(isolation.Path("/opt/sdk"), container.sdk)
        self.assertEqual(isolation.Path("/run/home"), container.home)
        self.assertIsNone(container.application)

    def test_the_certificate_is_the_door_variable_the_proxy_already_owns(self):
        self.assertEqual(proxy.CA_VARIABLE, execution.CERTIFICATE)


class StopReasonTest(unittest.TestCase):
    """The two vocabularies for how a child stopped, and the word between them."""

    def test_the_sdks_own_words_arrive_as_the_columns_own_words(self):
        for reported, recorded in execution.STOP_REASONS.items():
            with self.subTest(reported=reported):
                self.assertEqual(recorded, execution.stopped_as(reported))

    def test_every_word_this_translates_into_is_one_the_column_accepts(self):
        # The check constraint 0006 wrote and 0012 extended. A word outside it
        # does not fail the statement that writes it -- it fails the whole
        # closing transaction, which is the one that had to run.
        self.assertEqual(
            set(),
            set(execution.STOP_REASONS.values()) - set(execution.ACCEPTED_STOPS),
        )

    def test_a_child_that_reported_nothing_ended_its_turn(self):
        self.assertEqual("completed", execution.stopped_as(None))

    def test_a_word_the_column_already_speaks_is_passed_through_untouched(self):
        for accepted in execution.ACCEPTED_STOPS:
            with self.subTest(accepted=accepted):
                self.assertEqual(accepted, execution.stopped_as(accepted))

    def test_a_word_from_neither_vocabulary_is_recorded_as_an_error(self):
        # `tool_use` is a real `ResultMessage.stop_reason`, and the honest
        # reading of it here is that the child stopped mid-tool: not an ending
        # this runtime asked for, and not one the column has a word for.
        self.assertEqual("error", execution.stopped_as("tool_use"))
        self.assertEqual("error", execution.stopped_as("a word from a later SDK"))


class ObjectiveTest(unittest.TestCase):
    """What the child is told, which is the only thing it is told."""

    def test_the_objective_names_the_target_the_packet_cannot_hold(self):
        text = claimed().objective()
        self.assertIn("GET https://app.example.com/login", text)
        self.assertIn("the endpoint GET /login", text)

    def test_the_objective_states_the_rule_promotion_will_apply(self):
        text = claimed().objective()
        self.assertIn("mcp__rk2__http_request", text)
        self.assertIn("mcp__rk2__submit_mission_result", text)
        self.assertIn("Receipt", text)

    def test_a_kind_nobody_wrote_prose_for_is_described_rather_than_refused(self):
        self.assertIn("Carry out this exotic Task", claimed(kind="exotic").objective())

    def test_every_kind_the_roster_dispatches_has_its_own_sentence(self):
        dispatched = {kind for role in roster.ROLES.values() for kind in role.task_kinds}
        self.assertEqual(set(), dispatched - set(execution.MISSIONS))


class SlateTest(unittest.TestCase):
    """The two ways an attempt ends before anything is claimed."""

    def test_an_empty_slate_claims_nothing_and_starts_nothing(self):
        connection = Recorder(slate=0)
        launcher = Launcher()
        ledger, facts = attempt(connection, launcher)
        self.assertEqual([], ledger.violations)
        self.assertEqual([], facts["slate"])
        self.assertIsNone(facts["task"])
        self.assertNotIn(execution.CLAIM, connection.statements)
        self.assertEqual([], launcher.requests)

    def test_the_offered_slate_is_carried_out_of_the_attempt_entry_by_entry(self):
        # A slate reduced to a count is a slate nobody was offered. The
        # orchestrator chooses from these entries, so the factors it would
        # choose on and the expiry it would race have to survive the call.
        connection = Recorder(slate=3)
        _, facts = attempt(connection)

        self.assertEqual([1, 2, 3], [entry["ordinal"] for entry in facts["slate"]])
        self.assertEqual(["T1", "T2", "T3"], [entry["task"] for entry in facts["slate"]])
        self.assertEqual([True, False, False], [e["entitled"] for e in facts["slate"]])
        self.assertEqual({"novelty": 1.0, "cost": 0.3}, facts["slate"][0]["factors"])
        self.assertEqual("2026-08-13 17:05:00+00", facts["slate"][0]["expires_at"])

    def test_a_slate_nothing_could_be_claimed_off_is_held_not_failed(self):
        connection = Recorder(claim=None)
        ledger, facts = attempt(connection)
        self.assertEqual([], ledger.violations)
        self.assertIsNone(facts["task"])
        self.assertNotIn(execution.FINISH, connection.statements)

    def test_a_scheduler_that_refuses_the_claim_is_a_violation_not_a_retry(self):
        connection = Recorder(raises={execution.CLAIM: database_error("lane_full")})
        ledger, facts = attempt(connection)
        self.assertEqual(1, len(ledger.violations))
        self.assertIsNone(facts["task"])
        self.assertEqual(1, connection.statements.count(execution.CLAIM))

    def test_the_session_is_bound_to_the_program_before_the_scheduler_is_asked(self):
        connection = Recorder(slate=0)
        attempt(connection)
        self.assertEqual(proxy.BIND, connection.statements[0])
        self.assertEqual((PROGRAM,), connection.sent(proxy.BIND)[0])

    def test_the_slate_is_ranked_and_the_quota_advanced_before_it_is_offered(self):
        # An offer on its own offers nothing: `rank_candidates` compares a
        # Task's `estimated_cost` against the budget, that column is NULL until
        # a ranking writes it, and the comparison then fails silently. A slice
        # that only offered would find an empty slate for every Task it had just
        # created and report an idle queue.
        connection = Recorder(slate=0)
        attempt(connection)
        issued = connection.statements

        self.assertLess(issued.index(execution.RANK), issued.index(execution.QUOTA))
        self.assertLess(issued.index(execution.QUOTA), issued.index(execution.OFFER))

    def test_the_claimed_run_is_read_back_under_the_program_that_claimed_it(self):
        # `claim_task` answers with a label, and every Program's first Agent run
        # is `AR1`. The runtime's connection sees them all, so a lookup that
        # named only the label would open the attempt against whichever Program
        # the planner reached first.
        connection = Recorder()
        attempt(connection)

        self.assertEqual([("AR7", PROGRAM)], connection.sent(execution.STARTED))


class AttemptTest(unittest.TestCase):
    """One claimed Task, from the capability to the closing."""

    def test_the_capability_is_minted_against_a_tool_run_naming_the_task(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        program_id, run_id, task_id, tool, args = connection.sent(execution.OPEN_TOOL_RUN)[0]
        self.assertEqual(PROGRAM, program_id)
        self.assertEqual(RUN, run_id)
        self.assertEqual(TASK, task_id)
        # The name the risk rules and the egress authorisation key on, not the
        # name the roster shows the model.
        self.assertEqual(proxy.TOOL, tool)
        self.assertEqual(
            {"url": "https://app.example.com/login", "method": "GET", "identity_slot": ""},
            json.loads(args),
        )

    def test_the_child_is_handed_the_capability_and_cannot_mint_one(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(), launcher)
        door = launcher.only.egress
        assert door is not None
        self.assertEqual(CAPABILITY, door.capability)
        self.assertEqual(PROGRAM, door.program_id)
        self.assertEqual(BOUNDARY.proxy_url, door.proxy_url)
        self.assertEqual(isolation.CA_FILE, door.certificate)

    def test_the_child_runs_as_the_role_the_scheduler_chose(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(), launcher)
        self.assertEqual("recon", launcher.only.role)
        self.assertEqual(RUN, launcher.only.agent_run_id)
        self.assertEqual(PROGRAM, launcher.only.program_id)
        self.assertIs(BOUNDARY, launcher.only.container)

    def test_the_child_gets_no_longer_than_its_capability_has_left(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(lifetime=42.0), launcher)
        self.assertEqual(42.0, launcher.only.timeout)

    def test_a_capability_outlasting_the_ceiling_does_not_raise_the_ceiling(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(lifetime=99999.0), launcher, timeout=60.0)
        self.assertEqual(60.0, launcher.only.timeout)

    def test_the_tool_run_closes_as_success_before_the_attempt_is_closed(self):
        connection = Recorder()
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([], ledger.violations)
        self.assertEqual([(TOOL_RUN, "success")], connection.sent(proxy.CLOSE_TOOL_RUN))
        order = connection.statements
        self.assertLess(order.index(proxy.CLOSE_TOOL_RUN), order.index(execution.FINISH))
        self.assertEqual({"label": "RC1", "decision": "allowed", "status_code": 200}, facts["receipt"])

    def test_a_blocked_receipt_closes_the_tool_run_as_denied_and_says_so(self):
        connection = Recorder(receipt=("RC1", "blocked", None))
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([(TOOL_RUN, "denied")], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertEqual(["proxy"], [item.source for item in ledger.violations])
        self.assertEqual("blocked", facts["receipt"]["decision"])

    def test_a_capability_that_was_never_spent_closes_the_tool_run_as_error(self):
        connection = Recorder(receipt=None)
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([(TOOL_RUN, "error")], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertIsNone(facts["receipt"])
        self.assertEqual([], ledger.violations)

    def test_what_the_child_submitted_is_staged_and_then_promoted(self):
        connection = Recorder()
        with compiled():
            _, facts = attempt(connection)
        self.assertEqual("PR1", facts["proposal"]["label"])
        self.assertEqual([], facts["proposal"]["drops"])
        self.assertEqual(["OB1"], facts["promotion"]["observations"])
        self.assertEqual([(PROPOSAL,)], connection.sent(execution.PROMOTE))
        # And the Surface it just changed is fingerprinted before the promotion
        # commits, which is 022's "after recon" from the caller's side.
        self.assertEqual([()], connection.sent(execution.FINGERPRINT))
        self.assertEqual({"applications": 1, "changed": 1}, facts["fingerprint"])

    def test_a_child_that_submitted_nothing_stages_nothing_and_still_closes(self):
        connection = Recorder()
        launcher = Launcher(answer=result(mission_result=None, mission_attempts=0))
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertIsNone(facts["proposal"])
        self.assertNotIn(execution.PROMOTE, connection.statements)
        self.assertEqual([], ledger.violations)
        self.assertEqual(1, len(connection.sent(execution.FINISH)))

    def test_the_task_status_reported_is_the_one_the_database_decided(self):
        connection = Recorder(
            closure={
                "agent_run": "AR7",
                "task": "T3",
                "task_status": "pending",
                "accepted": False,
                "runs_closed": 1,
                "tool_runs_closed": 0,
                "leases_released": 1,
            }
        )
        with compiled():
            _, facts = attempt(connection)
        self.assertEqual("pending", facts["closure"]["task_status"])

    def test_the_causal_identifiers_are_set_before_every_write_on_the_run(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertTrue(connection.sent(execution.CAUSE))
        for run_id, task_id in connection.sent(execution.CAUSE):
            self.assertEqual((RUN, TASK), (run_id, task_id))

    def test_the_revocation_is_attributed_inside_the_transaction_that_makes_it(self):
        # Closing a Tool run is what revokes its capability, and 038's guard
        # turns that update into an Event. The cause is transaction-local, so
        # naming it in an earlier transaction names it for nobody: it has to be
        # set between this write's own BEGIN and the write.
        connection = Recorder()
        with compiled():
            attempt(connection)
        order = connection.statements
        write = order.index(proxy.CLOSE_TOOL_RUN)
        opened = write - order[write::-1].index("BEGIN")
        self.assertIn(execution.CAUSE, order[opened:write])

    def test_the_sdks_word_for_stopping_is_translated_before_it_is_recorded(self):
        # `end_turn` is what the SDK reports for the ordinary ending, and it is
        # not a word `agent_runs.stop_reason` accepts.
        connection = Recorder()
        with compiled():
            _, facts = attempt(connection, Launcher(answer=result(stop_reason="end_turn")))
        self.assertEqual("completed", facts["agent_run"]["stop_reason"])
        self.assertEqual([(RUN, "completed")], connection.sent(execution.FINISH))


class RefusalTest(unittest.TestCase):
    """Every way the attempt stops, and the closing that runs regardless."""

    def closed(self, connection: Recorder) -> None:
        self.assertEqual(1, len(connection.sent(execution.FINISH)), connection.statements)

    def test_a_subject_with_no_address_is_refused_and_the_task_returned(self):
        connection = Recorder(started=(started_row(subject_type="hypothesis", url=None),))
        launcher = Launcher()
        ledger, facts = attempt(connection, launcher)
        self.assertEqual(1, len(ledger.violations))
        self.assertIsNone(facts["target"])
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.closed(connection)

    def test_a_role_this_runtime_cannot_start_is_refused_before_the_packet(self):
        connection = Recorder(started=(started_row(role="reporter"),))
        launcher = Launcher()
        ledger, _ = attempt(connection, launcher)
        self.assertEqual(1, len(ledger.violations))
        self.assertEqual([], launcher.requests)
        self.closed(connection)

    def test_a_role_that_may_not_make_the_request_is_refused_before_minting_one(self):
        # `js_analyst` is startable and holds no `net.request`, deliberately.
        # This slice mints one capability per attempt and hands it to the child,
        # so a role that may not spend it would be handed a capability nothing
        # it is allowed to call could use -- and the gate would have minted it.
        self.assertNotIn(execution.NET, roster.ROLES["js_analyst"].tool_groups)
        connection = Recorder(started=(started_row(role="js_analyst"),))
        launcher = Launcher()
        ledger, _ = attempt(connection, launcher)
        self.assertEqual(["roster"], [item.source for item in ledger.violations])
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.closed(connection)

    def test_a_packet_that_cannot_be_compiled_starts_no_child(self):
        connection = Recorder()
        launcher = Launcher()
        with mock.patch.object(execution.migrate, "open_connection", return_value=None):
            ledger, facts = attempt(connection, launcher)
        self.assertIsNone(facts["packet"])
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.closed(connection)

    def test_a_gate_that_mints_nothing_closes_the_tool_run_and_starts_nothing(self):
        connection = Recorder(
            gate={"decision": "deny", "risk_class": "constrained", "rule": "net_post"}
        )
        launcher = Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertEqual(1, len(ledger.violations))
        self.assertEqual([], launcher.requests)
        self.assertEqual([(TOOL_RUN, "denied")], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertEqual("deny", facts["tool_run"]["decision"])
        self.closed(connection)

    def test_a_gate_that_asks_files_the_question_rather_than_answering_it(self):
        connection = Recorder(
            gate={"decision": "ask", "risk_class": "dangerous", "rule": "net_delete"}
        )
        launcher = Launcher()
        with compiled():
            ledger, _ = attempt(connection, launcher)
        self.assertEqual([(TOOL_RUN,)], connection.sent(proxy.PARK_TOOL_RUN))
        # Parked, not closed: `park_for_human` ends the run with words this
        # runtime does not have, and a close here would erase them.
        self.assertEqual([], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertEqual(1, len(ledger.violations))
        self.assertEqual([], launcher.requests)
        self.closed(connection)

    def test_a_refused_child_is_reported_as_a_refusal_and_closed_as_one(self):
        connection = Recorder()
        with fixtures.unlatched():
            refusal = fixtures.startup_refusal()
        launcher = Launcher(error=refusal)
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertTrue(ledger.violations)
        self.assertEqual("refusal", facts["agent_run"]["stop_reason"])
        self.assertEqual([(RUN, "refusal")], connection.sent(execution.FINISH))

    def test_an_unavailable_boundary_is_a_violation_and_not_a_traceback(self):
        connection = Recorder()
        launcher = Launcher(error=isolation.Unavailable("no such image"))
        with compiled():
            ledger, _ = attempt(connection, launcher)
        self.assertEqual(1, len(ledger.violations))
        self.assertEqual("no such image", ledger.violations[0].detail.split(": ")[-1])
        self.closed(connection)

    def test_a_promotion_that_raises_still_closes_the_attempt(self):
        connection = Recorder(raises={execution.PROMOTE: database_error("deadlock")})
        with compiled():
            ledger, facts = attempt(connection)
        self.assertTrue(ledger.violations)
        self.assertIsNone(facts["promotion"])
        self.closed(connection)

    def test_a_closing_that_raises_is_reported_rather_than_swallowed(self):
        connection = Recorder(raises={execution.FINISH: database_error("gone")})
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["closure"])
        self.assertTrue(any("could not be closed" in item.detail for item in ledger.violations))


class ProgramHookTest(unittest.TestCase):
    """What `rk run` does with the callback, and when it declines to call it."""

    def test_the_stop_reason_says_an_attempt_was_made_only_when_one_was(self):
        self.assertEqual(
            program.STOPPED_NOTHING_TO_EXECUTE, self.stopped({"slate": [], "task": None})
        )
        self.assertEqual(
            program.STOPPED_TASK_ATTEMPTED,
            self.stopped({"slate": [slate_row(1)], "task": {"label": "T3"}}),
        )

    def test_execution_is_one_of_the_facts_a_run_always_answers_with(self):
        self.assertIn("execution", program.FACTS)

    def stopped(self, execution_facts: dict) -> str:
        state = program._State(program_id=PROGRAM, execution=execution_facts)
        return str(program._report(Ledger(), state).facts["stop_reason"])


if __name__ == "__main__":
    unittest.main()
