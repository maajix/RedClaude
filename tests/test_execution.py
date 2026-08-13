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
import time
import unittest
from unittest import mock

from redkraken import (
    _launch,
    agent,
    execution,
    isolation,
    packet,
    pg,
    program,
    proposal,
    proxy,
    roster,
)
from redkraken.outcome import Ledger
from tests import fixtures


PROGRAM = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"
TASK = "33333333-3333-4333-8333-333333333333"
TOOL_RUN = "44444444-4444-4444-8444-444444444444"
PROPOSAL = "55555555-5555-4555-8555-555555555555"
SESSION = "66666666-6666-4666-8666-666666666666"

#: What `Launcher.picks` means when nobody said: the first entry on offer. A
#: sentinel rather than `None`, because `None` is already an answer -- a session
#: that called no tool and chose nothing.
FIRST = object()

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
        # The first entry `slate_row` offers, because that is the one the
        # default launcher picks and the claim honours a pick it can still
        # validate. A fixture that claimed something else would be a fixture
        # about a substituted Task, which is what `_dispatchable` refuses.
        "task_label": "T1",
        "kind": "recon",
        "attempts": 1,
        "subject_type": "endpoint",
        "subject_label": "GET /login",
        "method": "GET",
        "url": "https://app.example.com/login",
        "subagent_cap": roster.DEFAULT_SUBAGENTS,
        "token_cap": 40_000,
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
        subject.subagent_cap,
        subject.token_cap,
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
        "input_tokens": 1200,
        "output_tokens": 300,
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


def slate_entry(ordinal: int) -> dict:
    """The same entry after the slice decoded it, which is what `facts` carries.

    Built from `slate_row` through the slice's own decoder rather than written
    out again, so a slice that renamed a key renames it here too.
    """
    return execution._slate_entry(dict(zip(SLATE_COLUMNS, slate_row(ordinal))))


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
        # The Task-less run one choice is made in, and the two ceilings the
        # child has no database of its own to read.
        self.session = answers.get(
            "session",
            {
                "agent_run": SESSION,
                "label": "AR6",
                "model": "opus",
                "effort": "xhigh",
                "subagent_cap": roster.DEFAULT_SUBAGENTS,
                "token_cap": 40_000,
            },
        )
        # Labels this recorder's `record_choice` says the Slate no longer
        # carries. The downgrade is the server's to make -- the runtime never
        # writes `off_slate` itself -- so it is answered here rather than
        # decided by the slice under test.
        self.off_slate = frozenset(answers.get("off_slate", ()))
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
        # An idle reconciliation: nothing had lapsed, and the one Task this
        # recorder's slate is about is this run's own to claim.
        self.reconciliation = answers.get(
            "reconciliation",
            {
                "tasks_left_to_live_owners": 0,
                "tasks_returned": 0,
                "tasks_retired": 0,
                "runs_aborted": 0,
                "leases_released": 0,
                "hypotheses_returned_to_testable": 0,
            },
        )
        # Half an hour, which is the weights' own TTL, so the interval is ten
        # minutes and no beat fires while a stand-in child returns instantly.
        # A test that wants one shortens it.
        self.lease_ttl = answers.get("lease_ttl", 1800.0)
        beat = answers.get(
            "heartbeat",
            {
                "agent_run": "AR7",
                "beat": True,
                "reason": None,
                "expires_at": "2026-08-13 19:30:00+00",
                "identity_leases": 1,
            },
        )
        self.beats = list(answers.get("heartbeats", [beat]))
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
                "task": "T1",
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

    def finished(self, run_id: str = RUN) -> list[tuple]:
        """The closings of one run. A pass closes two, and only one is a Task.

        `finish_task_attempt` closes the orchestrator session as well as the
        attempt, so a count of the statement counts both. What a test asking
        "was the attempt closed" means is this one.
        """
        return [parameters for parameters in self.sent(execution.FINISH) if parameters[0] == run_id]

    def closing(self, run_id: str = RUN) -> int:
        """Where in the sequence one run was closed, for the same reason."""
        for position, (sql, parameters) in enumerate(self.calls):
            if sql == execution.FINISH and parameters[0] == run_id:
                return position
        raise AssertionError(f"{run_id} was never closed: {self.statements}")

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql in (execution.RANK, execution.QUOTA):
            return [("{}",)]
        if sql == execution.OFFER:
            return [slate_row(n) for n in range(1, self.slate + 1)]
        if sql == execution.CLAIM:
            return [(self.claim,)]
        if sql == execution.OPEN_SESSION:
            return [(json.dumps(self.session),)]
        if sql == execution.CHOICE:
            return [(json.dumps(self._choice(parameters)),)]
        if sql == execution.STARTED:
            return list(self.started)
        if sql == execution.OPEN_TOOL_RUN:
            return [(TOOL_RUN, "TR9")]
        if sql == proxy.AUTHORIZE_TOOL_RUN:
            return [(json.dumps(self.gate),)]
        if sql == execution.LIFETIME:
            return [(self.lifetime,)]
        if sql == execution.RECONCILE:
            return [(json.dumps(self.reconciliation),)]
        if sql == execution.LEASE_TTL:
            return [(self.lease_ttl,)]
        if sql == execution.HEARTBEAT:
            # Answered in order and then repeated, so a test can say what the
            # second beat found without saying it about the first.
            beat = min(len(self.sent(sql)) - 1, len(self.beats) - 1)
            return [(json.dumps(self.beats[beat]),)]
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
            execution.BEAT_TIMEOUT,
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

    def _choice(self, parameters: tuple) -> dict:
        """`record_choice`'s answer: what it was told, and what it made of it.

        The shape matters more than the values. `task` is the pick that was
        written and is present only when one was; `offered_task` is the label
        the session named whether or not it survived, which is what an operator
        reading a refusal needs to see.
        """
        _, outcome, task, detail = parameters
        if outcome == "chosen" and task in self.off_slate:
            outcome = "off_slate"
            detail = f"{task} is not on the current slate"
        return {
            "outcome": outcome,
            "task": task if outcome == "chosen" else None,
            "offered_task": task,
            "agent_run": self.session["label"],
            "detail": detail,
        }

    def _provenance(self, sql: str, parameters: tuple) -> list[tuple]:
        """Enough for one cited Receipt to ground: this Program, this run's lane."""
        if sql == proposal.RECEIPT and parameters[0] == "RC1":
            return [(PROGRAM, "agent_http", RUN)]
        return []


class Launcher:
    """A stand-in for `agent.agent_run` that records the request it was given.

    One pass starts two children -- the orchestrator session that chooses off
    the Slate, and the worker that runs what was claimed -- and this keeps them
    in separate lists rather than telling them apart by index. A test that said
    `requests[1]` would be a test that silently moved to the planning run the
    day the choice stopped happening.

    `answer` and `error` are the worker's, because that is what every test that
    passes them is about. What the session answers is `picks`, and `planning` is
    the one exception it raises instead.
    """

    def __init__(
        self,
        answer=None,
        error: Exception | None = None,
        picks: object = FIRST,
        planning: Exception | None = None,
    ):
        self.requests: list[agent.AgentRunRequest] = []
        self.choices: list[agent.AgentRunRequest] = []
        self.answer = answer
        self.error = error
        self.picks = picks
        self.planning = planning

    def __call__(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        if request.role == roster.ORCHESTRATOR:
            return self.choose(request)
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.answer if self.answer is not None else result()

    def choose(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        """One session's answer, made through the latch a real child picks with.

        `picks` is what it calls `mcp__rk2__pick_task` with: `FIRST` for the
        first entry it was offered, a label for one it names itself, `""` for a
        call that carried no label at all, and `None` for a session that calls
        nothing. `_launch.Choice` is what a served tool would have answered
        with, so a fixture that set `choice` directly would be reporting a pick
        no tool accepted.
        """
        self.choices.append(request)
        if self.planning is not None:
            raise self.planning
        latch = _launch.Choice(request.slate)
        wanted = self.picks
        if wanted is FIRST:
            wanted = latch.offered[0] if latch.offered else None
        if wanted is not None:
            latch.pick({"task_label": wanted})
        return result(
            agent_run_id=request.agent_run_id,
            role=request.role,
            text=f"{len(latch.entries)} offered",
            mission_result=None,
            choice=latch.task,
            pick_attempts=latch.attempts,
        )

    @property
    def only(self) -> agent.AgentRunRequest:
        assert len(self.requests) == 1, self.requests
        return self.requests[0]

    @property
    def planned(self) -> agent.AgentRunRequest:
        assert len(self.choices) == 1, self.choices
        return self.choices[0]


class Waiting(Launcher):
    """A child that does not return until the run's Lease has been renewed.

    Deterministic where a sleep would not be. What these tests want to observe
    is a beat, so the child ends when one has been issued rather than after a
    duration guessed to be long enough -- and it gives up rather than hanging if
    none arrives, because a heartbeat that never beats is the failure under
    test and not a reason for the suite to stop.
    """

    def __init__(self, connection: Recorder, beats: int = 1, **answers):
        super().__init__(**answers)
        self.connection = connection
        self.beats = beats

    def __call__(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        # The session that chooses runs before anything is claimed, and nothing
        # beats for a run holding no Lease. Waiting for one here would wait out
        # the whole deadline before the Task this is about was even claimed.
        if request.role == roster.ORCHESTRATOR:
            return self.choose(request)
        deadline = time.monotonic() + 5.0
        while len(self.connection.sent(execution.HEARTBEAT)) < self.beats:
            if time.monotonic() > deadline:
                raise AssertionError(f"no heartbeat arrived within 5s for {request.role}")
            time.sleep(0.005)
        return super().__call__(request)


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
        with compiled():
            _, facts = attempt(connection)

        self.assertEqual([1, 2, 3], [entry["ordinal"] for entry in facts["slate"]])
        self.assertEqual(["T1", "T2", "T3"], [entry["task"] for entry in facts["slate"]])
        self.assertEqual([True, False, False], [e["entitled"] for e in facts["slate"]])
        self.assertEqual({"novelty": 1.0, "cost": 0.3}, facts["slate"][0]["factors"])
        self.assertEqual("2026-08-13 17:05:00+00", facts["slate"][0]["expires_at"])

    def test_a_slate_nothing_could_be_claimed_off_is_held_not_failed(self):
        connection = Recorder(claim=None)
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([], ledger.violations)
        self.assertIsNone(facts["task"])
        # The session that chose is closed; no attempt was opened to close.
        self.assertEqual([], connection.finished())

    def test_a_scheduler_that_refuses_the_claim_is_a_violation_not_a_retry(self):
        connection = Recorder(raises={execution.CLAIM: database_error("lane_full")})
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual(1, len(ledger.violations))
        self.assertIsNone(facts["task"])
        self.assertEqual(1, connection.statements.count(execution.CLAIM))

    def test_a_scheduler_with_no_active_weights_row_is_named_not_misreported(self):
        # PH2-73. The cap is read as a scalar subquery, so a scheduler with no
        # active weights row answers the run and a NULL rather than no row at
        # all -- and the refusal is the configuration it is, not a claimed run
        # that cannot be read back. `claim_task` cannot say this itself: it
        # reads the row into an all-NULL record and compares against nothing.
        connection = Recorder(started=(started_row(subagent_cap=None),))
        launcher = Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)

        self.assertEqual(1, len(ledger.violations))
        self.assertEqual(execution.INVALID_CONFIGURATION, ledger.violations[0].code)
        self.assertIn("scheduler_weights", ledger.violations[0].detail)
        self.assertIsNone(facts["task"])
        self.assertEqual([], launcher.requests)

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
        with compiled():
            attempt(connection)

        self.assertEqual([("AR7", PROGRAM)], connection.sent(execution.STARTED))


class ChoiceTest(unittest.TestCase):
    """The decision between the offer and the claim, in all four of its answers.

    What is asserted here is the property PH2-27 is about: the choice is an
    input to the claim and never a precondition for it. A session that answered
    a label, a session that answered nothing, a session that could not be
    opened and a session whose child never started all leave a defined outcome
    -- and only one of them changes which Task runs.
    """

    def choice(self, connection: Recorder, launcher: Launcher | None = None) -> dict:
        launcher = launcher or Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.ledger, self.launcher = ledger, launcher
        return facts

    def test_the_session_is_opened_after_the_offer_and_closed_before_the_claim(self):
        # The order is the whole mechanism: a session opened before the offer
        # would be choosing off a Slate nobody had computed, and a claim made
        # before the choice was recorded would be a claim with nothing to honour.
        connection = Recorder()
        self.choice(connection)
        order = connection.statements

        self.assertLess(order.index(execution.OFFER), order.index(execution.OPEN_SESSION))
        self.assertLess(order.index(execution.OPEN_SESSION), order.index(execution.CHOICE))
        self.assertLess(order.index(execution.CHOICE), order.index(execution.CLAIM))

    def test_the_choosing_child_is_given_the_slate_and_nothing_to_reach_with(self):
        # Criteria 1 and 2. The entries are the compact Slate rows and not the
        # Tasks behind them, and `egress` is None because the roster serves this
        # role no request tool: planning that reached a target would be testing
        # nobody scheduled.
        connection = Recorder(slate=3)
        self.choice(connection)
        planning = self.launcher.planned

        self.assertEqual(roster.ORCHESTRATOR, planning.role)
        self.assertIsNone(planning.egress)
        self.assertEqual(SESSION, planning.agent_run_id)
        self.assertEqual(["T1", "T2", "T3"], [entry["task"] for entry in planning.slate])
        self.assertIn("3 Task(s) on offer", planning.objective)
        self.assertEqual(roster.DEFAULT_SUBAGENTS, planning.subagent_cap)
        self.assertEqual(40_000, planning.token_cap)

    def test_the_role_that_chooses_may_read_and_pick_and_call_no_target(self):
        # The other half of criterion 2, asked of the roster rather than of the
        # request: a surface that carried the request tool would make the
        # `egress` above a courtesy rather than a bound.
        served = roster.ROLES[roster.ORCHESTRATOR].allowed_tools(agent.SERVED)

        self.assertIn("mcp__rk2__get_slate", served)
        self.assertIn("mcp__rk2__pick_task", served)
        self.assertNotIn("mcp__rk2__net_request", served)

    def test_a_named_task_is_recorded_as_the_choice_and_then_claimed(self):
        connection = Recorder()
        facts = self.choice(connection)

        self.assertEqual((SESSION, "chosen", "T1", None), connection.sent(execution.CHOICE)[0])
        self.assertEqual("chosen", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["choice"]["task"])
        self.assertEqual(1, facts["choice"]["attempts"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual([], self.ledger.violations)

    def test_a_label_this_slate_no_longer_carries_claims_nothing_at_all(self):
        # ADR 0003: an off-Slate choice is refused and not substituted. The
        # runtime's own walk is the answer to "nobody chose", and claiming here
        # would make it the answer to "the choice was refused" as well.
        connection = Recorder(off_slate={"T1"})
        facts = self.choice(connection)

        self.assertEqual("off_slate", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["choice"]["task"])
        self.assertIsNone(facts["task"])
        self.assertNotIn(execution.CLAIM, connection.statements)
        self.assertEqual([], self.launcher.requests)
        self.assertEqual([], self.ledger.violations)

    def test_the_runtime_never_decides_off_slate_for_itself(self):
        # The label is offered to the database even though this runtime holds a
        # copy of the Slate it could have checked it against. The copy has no
        # lock on it: `record_choice` asks `pick_task`, which is the same
        # function the claim re-validates through.
        connection = Recorder(slate=1)
        facts = self.choice(connection, Launcher(picks="T9"))

        self.assertEqual((SESSION, "chosen", "T9", None), connection.sent(execution.CHOICE)[0])
        self.assertEqual("chosen", facts["choice"]["outcome"])

    def test_a_session_that_chose_nothing_leaves_the_walk_to_the_runtime(self):
        connection = Recorder()
        facts = self.choice(connection, Launcher(picks=None))

        self.assertEqual((SESSION, "no_choice", None, None), connection.sent(execution.CHOICE)[0])
        self.assertEqual("no_choice", facts["choice"]["outcome"])
        self.assertIsNone(facts["choice"]["task"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual([], self.ledger.violations)

    def test_a_pick_that_carried_no_label_is_malformed_and_not_a_choice(self):
        connection = Recorder()
        facts = self.choice(connection, Launcher(picks=""))
        run_id, outcome, task, detail = connection.sent(execution.CHOICE)[0]

        self.assertEqual((SESSION, "malformed", None), (run_id, outcome, task))
        self.assertIn("1 pick(s) carried no task label", detail)
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual([], self.ledger.violations)

    def test_a_child_that_never_started_is_unavailable_and_stops_nothing(self):
        connection = Recorder()
        facts = self.choice(
            connection, Launcher(planning=isolation.Unavailable("no such image"))
        )

        self.assertEqual(
            (SESSION, "unavailable", None, "no session answered"),
            connection.sent(execution.CHOICE)[0],
        )
        self.assertEqual("unavailable", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual(1, len(self.ledger.violations))

    def test_a_session_that_could_not_be_opened_still_claims_a_task(self):
        connection = Recorder(
            raises={execution.OPEN_SESSION: database_error("no orchestrator role")}
        )
        facts = self.choice(connection)

        self.assertIsNone(facts["choice"])
        self.assertNotIn(execution.CHOICE, connection.statements)
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual([], self.launcher.choices)
        self.assertEqual(execution.INVALID_CONFIGURATION, self.ledger.violations[0].code)

    def test_the_session_is_closed_whatever_it_answered(self):
        connection = Recorder()
        self.choice(connection)

        self.assertEqual([(SESSION, "completed", 1200, 300)], connection.finished(SESSION))
        self.assertLess(connection.closing(SESSION), connection.statements.index(execution.CLAIM))

    def test_a_session_whose_child_never_answered_is_closed_as_aborted(self):
        connection = Recorder()
        self.choice(connection, Launcher(planning=isolation.Unavailable("no such image")))

        self.assertEqual([(SESSION, "aborted", None, None)], connection.finished(SESSION))

    def test_a_choice_that_could_not_be_recorded_is_closed_and_reported(self):
        connection = Recorder(raises={execution.CHOICE: database_error("gone")})
        facts = self.choice(connection)

        self.assertIsNone(facts["choice"])
        self.assertEqual([(SESSION, "completed", 1200, 300)], connection.finished(SESSION))
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual(execution.INTEGRITY_FAILED, self.ledger.violations[0].code)

    def test_nothing_is_dispatched_against_a_task_the_choice_did_not_commit(self):
        # Criterion 5, and an invariant `claim_task` already holds: it prefers
        # the outstanding pick and refuses it when it has gone stale, so a
        # committed choice and a differently claimed Task is a claim that
        # honoured neither. The Task is given back rather than run.
        connection = Recorder(slate=2, started=(started_row(task_label="T2"),))
        facts = self.choice(connection)

        self.assertEqual("T1", facts["choice"]["task"])
        self.assertEqual([], self.launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.assertEqual(1, len(connection.finished()))
        self.assertEqual(execution.INTEGRITY_FAILED, self.ledger.violations[0].code)

    def test_a_kind_claimed_as_a_role_the_roster_does_not_give_it_is_refused(self):
        # Criterion 4's role half. `role_task_kinds` is unique on kind, so this
        # is the database disagreeing with the roster -- which is exactly the
        # disagreement that must not reach a started child.
        connection = Recorder(started=(started_row(kind="analyze"),))
        self.choice(connection)

        self.assertEqual([], self.launcher.requests)
        self.assertEqual(["roster"], [item.source for item in self.ledger.violations])
        self.assertIn("js_analyst", self.ledger.violations[0].detail)
        self.assertEqual(1, len(connection.finished()))

    def test_every_kind_the_scheduler_can_claim_has_exactly_one_role(self):
        # The map `_dispatchable` checks against, asserted to be total: a kind
        # missing from it would refuse every Task of that kind at dispatch.
        self.assertEqual(
            sorted(roster.TASK_KINDS), sorted(roster.ROLE_FOR_KIND), roster.ROLE_FOR_KIND
        )


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

    def test_the_child_is_capped_at_the_concurrency_the_claim_read(self):
        # PH2-73. `max_concurrent_subagents` comes back with the claim and goes
        # out with the child, so the gate inside refuses at the number the
        # Slate was offered and the Task was claimed under. A default in the
        # child would be a second statement of a weight an operator versions
        # for the whole scheduler -- offered at four and denied at three, with
        # the Task claimed and no child ever started.
        launcher = Launcher()
        with compiled():
            attempt(Recorder(started=(started_row(subagent_cap=4),)), launcher)

        self.assertEqual(4, launcher.only.subagent_cap)

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
        self.assertLess(order.index(proxy.CLOSE_TOOL_RUN), connection.closing())
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
        self.assertEqual(1, len(connection.finished()))

    def test_the_task_status_reported_is_the_one_the_database_decided(self):
        connection = Recorder(
            closure={
                "agent_run": "AR7",
                "task": "T1",
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
        self.assertEqual([(RUN, "completed", 1200, 300)], connection.finished())


class RefusalTest(unittest.TestCase):
    """Every way the attempt stops, and the closing that runs regardless."""

    def closed(self, connection: Recorder) -> None:
        self.assertEqual(1, len(connection.finished()), connection.statements)

    def test_a_subject_with_no_address_is_refused_and_the_task_returned(self):
        connection = Recorder(started=(started_row(subject_type="hypothesis", url=None),))
        launcher = Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertEqual(1, len(ledger.violations))
        self.assertIsNone(facts["target"])
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.closed(connection)

    def test_a_role_this_runtime_cannot_start_is_refused_before_the_packet(self):
        # A `report` Task claimed as the role the roster gives that kind: the
        # refusal under test is about what this runtime can start, not about a
        # role and a kind that do not go together.
        connection = Recorder(started=(started_row(role="reporter", kind="report"),))
        launcher = Launcher()
        with compiled():
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
        connection = Recorder(started=(started_row(role="js_analyst", kind="analyze"),))
        launcher = Launcher()
        with compiled():
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
        self.assertEqual([(RUN, "refusal", None, None)], connection.finished())

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
            self.stopped({"slate": [slate_entry(1)], "task": {"label": "T3"}}),
        )

    def test_execution_is_one_of_the_facts_a_run_always_answers_with(self):
        self.assertIn("execution", program.FACTS)

    def stopped(self, execution_facts: dict) -> str:
        state = program._State(program_id=PROGRAM, execution=execution_facts)
        return str(program._report(Ledger(), state).facts["stop_reason"])


class HeartbeatTest(unittest.TestCase):
    """PH2-24: the run says it is still here for as long as its child runs.

    A sixtieth of the weights' TTL everywhere below, so the beating this slice
    would do over half an hour happens inside a test. The interval is the only
    thing shortened: what is asserted is that a beat is issued at all, that it
    names the run the claim opened, that a refusal stops it rather than being
    retried, and that nothing beats after the child is gone.
    """

    #: A TTL whose third is twenty milliseconds.
    QUICK = 0.06

    def test_the_run_renews_what_it_holds_while_its_child_runs(self):
        connection = Recorder(lease_ttl=self.QUICK)
        with compiled():
            ledger, facts = attempt(connection, Waiting(connection))
        self.assertEqual([(RUN,)], connection.sent(execution.HEARTBEAT)[:1])
        self.assertLessEqual(1, facts["heartbeat"]["beats"])
        self.assertEqual(
            (None, None),
            (facts["heartbeat"]["lapsed"], facts["heartbeat"]["failure"]),
        )
        self.assertEqual([], [step.name for step in ledger.assertions if not step.ok])

    def test_nothing_beats_after_the_child_is_gone(self):
        # The one ordering that matters: the closing releases the Lease, and a
        # beat arriving after it would be this process renewing a hold it had
        # just given back.
        connection = Recorder(lease_ttl=self.QUICK)
        with compiled():
            attempt(connection, Waiting(connection))
        statements = connection.statements
        self.assertLess(
            max(n for n, sql in enumerate(statements) if sql == execution.HEARTBEAT),
            connection.closing(),
        )

    def test_a_lapsed_lease_is_reported_and_not_beaten_harder(self):
        # `beat: false` means some reconciliation is entitled to this run's
        # work and may already have taken it. One attempt, then silence.
        connection = Recorder(
            lease_ttl=self.QUICK,
            heartbeat={
                "agent_run": "AR7",
                "beat": False,
                "reason": "the task lease has lapsed",
                "expires_at": None,
                "identity_leases": 0,
            },
        )
        with compiled():
            ledger, facts = attempt(connection, Waiting(connection))
        self.assertEqual(1, len(connection.sent(execution.HEARTBEAT)))
        self.assertEqual(0, facts["heartbeat"]["beats"])
        self.assertEqual("the task lease has lapsed", facts["heartbeat"]["lapsed"])
        self.assertEqual(
            ["heartbeat"], [step.name for step in ledger.assertions if not step.ok]
        )

    def test_a_heartbeat_that_cannot_reach_the_database_stops_and_says_so(self):
        connection = Recorder(
            lease_ttl=self.QUICK,
            raises={execution.HEARTBEAT: database_error("the server went away")},
        )
        with compiled():
            ledger, facts = attempt(connection, Waiting(connection))
        self.assertEqual(1, len(connection.sent(execution.HEARTBEAT)))
        self.assertIn("the server went away", str(facts["heartbeat"]["failure"]))
        # Reported, and the attempt still finished: what a failed beat costs is
        # the Lease, which expires on its own, and the child was still running.
        self.assertIn(execution.FINISH, connection.statements)

    def test_a_ttl_the_runtime_cannot_read_starts_no_beating_at_all(self):
        connection = Recorder(
            raises={execution.LEASE_TTL: database_error("no active weights row")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([], connection.sent(execution.HEARTBEAT))
        self.assertEqual(0, facts["heartbeat"]["every"])
        self.assertEqual(
            ["heartbeat"], [step.name for step in ledger.assertions if not step.ok]
        )
        # One assertion under that name and not two: a run that never beat must
        # not also be told its Leases were held through nothing.
        self.assertEqual(
            1, len([step for step in ledger.assertions if step.name == "heartbeat"])
        )

    def test_a_ttl_of_zero_is_a_configuration_this_runtime_refuses_to_beat_on(self):
        # Read, and unusable: an interval of zero beats is not a shorter Lease,
        # it is a Lease nothing renews, and reporting it as a read TTL would
        # hide the one thing about it that matters.
        connection = Recorder(lease_ttl=0.0)
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([], connection.sent(execution.HEARTBEAT))
        self.assertEqual(
            ["heartbeat"], [step.name for step in ledger.assertions if not step.ok]
        )

    def test_the_identity_half_going_missing_stops_the_beating(self):
        # The Task lease renewed and the Identity leases did not come with it.
        # Half a hold is the disagreement the Lease exists to prevent, so it is
        # reported the way a lapse is and the beating stops.
        held = {
            "agent_run": "AR7", "beat": True, "reason": None,
            "expires_at": "2026-08-13 19:30:00+00", "identity_leases": 2,
        }
        connection = Recorder(
            lease_ttl=self.QUICK, heartbeats=[held, {**held, "identity_leases": 0}]
        )
        with compiled():
            ledger, facts = attempt(connection, Waiting(connection, beats=2))
        self.assertEqual(1, facts["heartbeat"]["beats"])
        self.assertIn("Identity half", str(facts["heartbeat"]["lapsed"]))
        self.assertEqual(
            ["heartbeat"], [step.name for step in ledger.assertions if not step.ok]
        )


class ReconciliationTest(unittest.TestCase):
    """PH2-24: what a sibling that stopped beating left, before anything is offered.

    The pass this slice makes is the first reader that would otherwise walk past
    a crashed run's Tasks, so it asks first. What is asserted here is the order,
    the report, and that a reconciliation this runtime cannot make does not stop
    it from doing its own work.
    """

    def test_reconciliation_happens_before_the_slate_is_offered(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        statements = connection.statements
        self.assertLess(
            statements.index(execution.RECONCILE), statements.index(execution.RANK)
        )

    def test_what_was_recovered_and_what_was_left_alone_are_both_reported(self):
        connection = Recorder(
            reconciliation={
                "tasks_left_to_live_owners": 2,
                "tasks_returned": 1,
                "tasks_retired": 1,
                "runs_aborted": 2,
                "leases_released": 3,
                "hypotheses_returned_to_testable": 1,
            }
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual(2, facts["reconciliation"]["tasks_left_to_live_owners"])
        held = [step for step in ledger.assertions if step.name == "reconciliation"]
        self.assertEqual(1, len(held))
        self.assertIn("2 Task(s) recovered", held[0].detail)
        self.assertIn("2 left to the runs", held[0].detail)

    def test_a_reconciliation_that_fails_does_not_stop_the_pass(self):
        connection = Recorder(
            raises={execution.RECONCILE: database_error("deadlock detected")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["reconciliation"])
        self.assertEqual(
            ["reconciliation"], [step.name for step in ledger.assertions if not step.ok]
        )
        # The claim still happened: recovering somebody else's work and doing
        # this run's own are two things, and only one of them failed.
        self.assertIn(execution.CLAIM, connection.statements)


if __name__ == "__main__":
    unittest.main()
