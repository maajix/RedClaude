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
import dataclasses
import hashlib
import json
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from redkraken import (
    agent,
    execution,
    integrity,
    isolation,
    packet,
    pg,
    playbook,
    program,
    proposal,
    proxy,
    replay,
    roster,
    store,
)
from redkraken import _startup, migrate
from redkraken import outcome as outcome_module
from redkraken.outcome import Ledger
from tests import fixtures


PROGRAM = "11111111-1111-4111-8111-111111111111"
RUN = "22222222-2222-4222-8222-222222222222"
TASK = "33333333-3333-4333-8333-333333333333"
TOOL_RUN = "44444444-4444-4444-8444-444444444444"
PROPOSAL = "55555555-5555-4555-8555-555555555555"
SESSION = "66666666-6666-4666-8666-666666666666"
CAMPAIGN = "77777777-7777-4777-8777-777777777777"
SUBJECT = "88888888-8888-4888-8888-888888888888"

#: One Playbook out of the installed corpus, which is what a selection can
#: name: the runtime refuses a row whose digests are not a document it holds.
SELECTED_PLAYBOOK = playbook.PLAYBOOKS["object-ownership"]

#: What `Launcher.picks` means when nobody said, named here for the tests that
#: pass it. The sentinel itself is `fixtures`', because the launcher fixture in
#: `test_database` answers a session with the same walk.
FIRST = fixtures.FIRST

CAPABILITY = "c0ffee" * 10 + "cafe"


def seeded_classes() -> tuple[str, ...]:
    """Every id the migration corpus seeds into `vulnerability_classes`.

    Read out of the corpus rather than written down here, which is the whole
    point of ticket 163: a list of words kept beside the table is a second copy
    that goes stale, and the run this ticket is about was refused by words a
    stale copy would not have carried. A migration that seeds a thirty-eighth
    class puts it in this tuple, and the assertions below then demand it of the
    objective without anybody editing them.
    """
    found: list[str] = []
    for source in sorted(migrate.CORPUS.glob("*.sql")):
        lines = source.read_text(encoding="utf-8").splitlines()
        rows = False
        for line in lines:
            if line.startswith("INSERT INTO vulnerability_classes"):
                rows = True
                continue
            # The statement ends where the indented rows do. Sliced on the
            # indent rather than on the terminating semicolon, because one of
            # the remediation sentences contains a semicolon of its own.
            if rows and (not line.strip() or not line.startswith((" ", "\t"))):
                rows = False
            if not rows:
                continue
            named = re.match(r"\s*\('([a-z0-9_]+)'", line)
            if named:
                found.append(named.group(1))
    assert found, "the corpus seeds no vulnerability class at all"
    return tuple(sorted(found))


#: The vocabulary as the database would answer `CLASSES`, in the same order.
SEEDED_CLASSES = seeded_classes()

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
        "subject_entity_id": SUBJECT,
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
        subject.subject_entity_id,
        subject.subject_type,
        subject.subject_label,
        subject.method,
        subject.url,
        subject.subagent_cap,
        subject.token_cap,
        subject.hypothesis_label,
        subject.test_label,
        subject.identity_slot_name,
        subject.identity_class,
        subject.finding_label,
        subject.impact_class,
        subject.proves_impact,
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
        # Ticket 165. What the provider billed, broken into what it was made of,
        # beside what this harness charged the run for under its own policy. The
        # cache read is most of it, which is the whole finding: the prefix is
        # re-sent every turn and counted at full price.
        "uncached_input_tokens": 200,
        "cache_creation_input_tokens": 100,
        "cache_read_input_tokens": 900,
        "answer_count": 6,
        "budget_tokens": 690,
        "budget_policy": execution.BUDGET_POLICY,
    }
    fields.update(overrides)
    return agent.AgentRunResult(**fields)


#: `offer_slate()`'s own columns, as the server names them. Spelled out in
#: `fixtures` because the slice reads the answer by name -- a recorder that
#: returned bare tuples would let a column order change pass every test in this
#: file -- and asserted against the server itself by `RecordedColumnsTest`,
#: which is what stops the spelling from being a second opinion about what the
#: function returns.
SLATE_COLUMNS = fixtures.SLATE_COLUMNS


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


#: What the capsule's four read statements answer here: one row each, in the
#: `(label, revision, digest, record)` shape every section shares. The records
#: are thin on purpose -- what this file tests is the sequence and what the
#: request carries, and the server is where a record's contents are decided.
CAPSULE_READS = {
    execution.capsule_module.PROGRAM: ("matrix-web", 12, {"kind": "program"}),
    execution.capsule_module.CAMPAIGN: ("OS1", 0, {"kind": "session"}),
    execution.capsule_module.CAPACITY: ("program", 0, {"kind": "capacity"}),
    execution.capsule_module.LANES: ("recon", 0, {"kind": "lane"}),
    execution.capsule_module.WORK: ("T9", 8, {"kind": "work"}),
}

#: The one statement the standing family is read with. Taken from `integrity`
#: rather than written out, so a recorder answering it is answering the statement
#: the capsule actually sends.
STANDING = integrity.STANDING_QUERY

#: The slug the capsule asks the standing checks about, matching the one its
#: `PROGRAM` section reports: a capsule naming one Program in its lifecycle
#: section and asking about another would be two documents.
PROGRAM_SLUG = CAPSULE_READS[execution.capsule_module.PROGRAM][0]


def digested(document: object) -> list[tuple]:
    """The server's own digest answer, for records this process built.

    A real one hashes the canonical text of each element; this hashes the text
    it was sent. The capsule's rule is that the hash comes from SQL, and a fake
    that answered a constant would let a compile that never asked pass.
    """
    return [
        (position, hashlib.sha256(json.dumps(element).encode()).hexdigest())
        for position, element in enumerate(json.loads(str(document)), start=1)
    ]


class Recorder:
    """A connection that answers every statement the slice issues, and keeps them.

    Answers are keyed on the whole statement rather than on a fragment of it,
    for the reason `test_proposal` keys its own that way: two of these are
    updates to the same table, and a recorder that matched loosely would answer
    a closing with an opening's row.
    """

    def __init__(self, **answers):
        self.calls: list[tuple[str, tuple]] = []
        # A real connection always has these, and the slice now reads them on
        # every attempt rather than only where a tool image was described: the
        # supervisor answers `propose_test` and `propose_finding`, which need a
        # database whether or not this machine can start a tool container.
        self.settings = pg.settings_from_url("postgres://rk2_runtime@127.0.0.1:1/rk2")
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
                # The campaign this turn belongs to, and what its capsule may
                # cost. A first generation with nothing rotated, which is the
                # answer for a Program whose first pass this is.
                "session": CAMPAIGN,
                "session_label": "OS1",
                "generation": 1,
                "capsule_bytes": packet.DEFAULT_BYTES,
                "capsule_tokens": packet.DEFAULT_TOKENS,
                "rotated": None,
            },
        )
        # What the capsule reads around the choice: the Program's high-water
        # Event sequence, how many Tasks are already running, and the standing
        # checks as `run_standing_checks` answers them -- name, problems,
        # detail. One sound check by default, because a capsule compiled over a
        # broken Program is a case a test says it is about.
        self.revision = answers.get("revision", 12)
        self.working = answers.get("working", 1)
        self.standing = answers.get("standing", [("orchestrator_rotation", 0, "")])
        # What the end-of-pass rotation answers. `None` is the ordinary pass:
        # the campaign has not reached a ceiling, so nothing was closed.
        self.closed = answers.get("closed", None)
        # The Task revisions the capsule's Slate section cites, keyed by label.
        self.task_revisions = answers.get("task_revisions", {})
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
        # What the selection decided, as `SELECTED` reads it back. A real
        # Playbook out of the installed corpus, because the runtime checks the
        # digests it is handed against the documents it carries -- a made-up
        # path here would exercise the refusal and nothing else. `recorded` is
        # how many rows the Task already has, which is what tells a first
        # attempt from a retry.
        self.recorded = answers.get("recorded", 0)
        # How many stable Playbooks the demotion took back to draft on the way
        # in. Zero is the ordinary pass; a case says otherwise to see the pass
        # report a catalogue that moved under it.
        self.demoted = answers.get("demoted", 0)
        self.selections = list(
            answers.get("selections", [(SELECTED_PLAYBOOK.path, SELECTED_PLAYBOOK.sha256,
                                        SELECTED_PLAYBOOK.version)])
        )
        # Ticket 164. What the corpus nearly matched, asked only when the
        # selection kept nothing. Empty is the honest default: a case with a
        # kept Playbook never reaches the question, and a case with none is
        # asking what a subject with no strategy at all reads like.
        self.near_misses = list(answers.get("near_misses", []))
        # Ticket 163. The vocabulary a `conclude` child is shown, as the seeded
        # table holds it. A test that wants the table empty or short says so.
        self.classes = list(answers.get("classes", SEEDED_CLASSES))
        # Ticket 165. How often this Task has already ended on its ceiling under
        # the dispatch this pass is about to repeat. Zero is a first attempt,
        # which is what most cases here are about.
        self.budget_ends = answers.get("budget_ends", 0)
        # How many live selections the sweep found their Playbook had expired
        # under. Zero is the ordinary pass; a catalogue that moved under a
        # running mission is what a case says otherwise to see.
        self.marked = answers.get("marked", 0)
        # What `settle_playbook_selections` made of the Task once it was
        # closed. The default agrees with `closure`: a Task that reached `done`
        # under one kept Playbook, and that Playbook produced. `settled` false
        # is the other real answer -- a Task on its way back onto the Slate --
        # and it is the recorder's business to say which, because the verb
        # reads the Task's own status rather than anything the runtime sends.
        self.settlement = answers.get(
            "settlement",
            {
                "task": "T1",
                "task_status": "done",
                "settled": True,
                "produced": 1,
                "exhausted": 0,
            },
        )
        # What the retest lane found. The default is the quiet answer a Program
        # gives on most passes: every settled claim is already watched, nothing
        # was armed, and the Surface has not moved since, so no refutation
        # became due. A test that wants the lane to have done something says so.
        self.arming = answers.get(
            "arming", {"armed": 0, "watching": 2, "unwatched": 0}
        )
        self.refreshed = answers.get(
            "refreshed",
            {
                "due": 0,
                "by_reason": {},
                "reopened": 0,
                "watches_fired": 0,
                "watches_unwatchable": 0,
            },
        )
        # The two view reads, as rows in the column order the statements ask
        # for. Empty by default for the same reason the two answers above are
        # zero: a lane that made nothing due has nothing to show.
        self.due_retests = list(answers.get("due_retests", ()))
        self.surface_moves = list(answers.get("surface_moves", ()))
        # An idle reconciliation: nothing had lapsed, and the one Task this
        # recorder's slate is about is this run's own to claim.
        self.reconciliation = answers.get(
            "reconciliation",
            {
                "tasks_left_to_live_owners": 0,
                "tasks_returned": 0,
                "tasks_retired": 0,
                "tasks_settled_done": 0,
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
        #: `(label, decision, status_code, reason)`, or a list of them where a
        #: test needs one Tool run to have made several requests.
        self.receipt = answers.get("receipt", ("RC1", "allowed", 200, None))
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
        self.topology = answers.get(
            "topology", {"hosts": 1, "resolves_to": 1, "serves": 1}
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
        # Ticket 143. What `retire_task` answers: the status the Task ended at.
        self.retired = answers.get("retired", "abandoned")
        # Ticket 208. Empty by default: a fake whose Slate is empty and
        # whose queue is empty is the ordinary "nothing left to do", and
        # a case about a wall the pass hit says which wall.
        self.unready = answers.get("unready", ())
        # What the weights row says one Mission packet may cost. An empty list
        # is a scheduler with no active row, which is a real state and the one
        # the module answers with its own defaults.
        self.packet_limits = list(answers.get("packet_limits", [(65536, 8192)]))
        # Whether `close_startup_refusal` found an open run to close. False is
        # a run something else already ended, which is not this pass's to close.
        self.refusal_closed = answers.get("refusal_closed", True)
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
        # Rolls back on any exception, because `pg.Connection.transaction` does:
        # a recorder that committed whatever happened would let a slice that
        # raised mid-transaction record a COMMIT it never issued, which is the
        # one thing these tests read the call list to find out.
        self.calls.append(("BEGIN", ()))
        try:
            yield self
        except BaseException:
            self.calls.append(("ROLLBACK", ()))
            raise
        self.calls.append(("COMMIT", ()))

    def __enter__(self):
        return self

    def __exit__(self, *exception) -> bool:
        return False

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def position(self, statement: str) -> int:
        """Where in the sequence one statement was issued, first time only."""
        for at, (sql, _) in enumerate(self.calls):
            if sql == statement:
                return at
        raise AssertionError(f"{statement} was never issued: {self.statements}")

    def sent(self, statement: str) -> list[tuple]:
        return [parameters for sql, parameters in self.calls if sql == statement]

    def finished(self, run_id: str = RUN) -> list[tuple]:
        """The closings of one run. A pass closes two, and only one is a Task.

        `finish_task_attempt` closes the orchestrator session as well as the
        attempt, so a count of the statement counts both. What a test asking
        "was the attempt closed" means is this one.

        The four the closing has always carried: the run, how it stopped and the
        two totals. Ticket 165's columns travel in the same call and are read
        with `spend` below, so a case about how a run ended is not a case that
        has to spell eight NULLs to say it.
        """
        return [
            parameters[:4]
            for parameters in self.sent(execution.FINISH)
            if parameters[0] == run_id
        ]

    def spend(self, run_id: str = RUN) -> dict:
        """What one closing said the run cost, keyed as `finish_task_attempt` is.

        Ticket 165. The profile is in here too: it is written by the same call
        and is the one value in it that describes the dispatch rather than the
        run.
        """
        closing = [one for one in self.sent(execution.FINISH) if one[0] == run_id]
        assert len(closing) == 1, closing
        return {
            **dict(zip(execution.SPEND, closing[0][4:])),
            "attempt_profile_sha256": closing[0][-1],
        }

    def closing(self, run_id: str = RUN) -> int:
        """Where in the sequence one run was closed, for the same reason."""
        for position, (sql, parameters) in enumerate(self.calls):
            if sql == execution.FINISH and parameters[0] == run_id:
                return position
        raise AssertionError(f"{run_id} was never closed: {self.statements}")

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql in CAPSULE_READS:
            label, revision, record = CAPSULE_READS[sql]
            return [(label, revision, f"{label}-digest", json.dumps(record))]
        if sql == execution.capsule_module.REVISION:
            return [(self.revision,)]
        if sql == execution.capsule_module.WORK_COUNT:
            return [(self.working,)]
        if sql == execution.capsule_module.DIGESTS:
            return digested(parameters[0])
        if sql == execution.capsule_module.SLUG:
            return [(PROGRAM_SLUG,)]
        if sql == STANDING:
            return list(self.standing)
        if sql in (execution.RANK, execution.QUOTA):
            return [("{}",)]
        if sql == execution.OFFER:
            return [slate_row(n) for n in range(1, self.slate + 1)]
        if sql == execution.CLAIM:
            return [(self.claim,)]
        if sql == execution.OPEN_SESSION:
            return [(json.dumps(self.session),)]
        if sql == execution.ROTATE:
            return [(None if self.closed is None else json.dumps(self.closed),)]
        if sql == execution.capsule_module.SLATE_REVISIONS:
            return [
                (label, self.task_revisions[label])
                for label in json.loads(parameters[1])
                if label in self.task_revisions
            ]
        if sql == execution.CHOICE:
            return [(json.dumps(self._choice(parameters)),)]
        if sql == execution.STARTED:
            return list(self.started)
        if sql == execution.RECORDED:
            return [(self.recorded,)]
        if sql == execution.DEMOTE:
            return [(self.demoted,)]
        if sql == execution.RECORD_SELECTION:
            return [(len(self.selections),)]
        if sql == execution.SELECTED:
            return list(self.selections)
        if sql == execution.NEAR_MISSES:
            return list(self.near_misses)
        if sql == execution.CLASSES:
            return [(one,) for one in self.classes]
        if sql == execution.BUDGET_ENDS:
            return [(self.budget_ends,)]
        if sql == execution.SWEEP_STALE:
            return [(self.marked,)]
        if sql == execution.ARM_WATCHES:
            return [(json.dumps(self.arming),)]
        if sql == execution.REFRESH_NEGATIVES:
            return [(json.dumps(self.refreshed),)]
        if sql == execution.DUE_RETESTS:
            return list(self.due_retests)
        if sql == execution.SURFACE_MOVES:
            return list(self.surface_moves)
        if sql == execution.SETTLE_SELECTION:
            return [(json.dumps(self.settlement),)]
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
        if sql == execution.PACKET_LIMITS:
            return list(self.packet_limits)
        if sql == execution.HEARTBEAT:
            # Answered in order and then repeated, so a test can say what the
            # second beat found without saying it about the first.
            beat = min(len(self.sent(sql)) - 1, len(self.beats) - 1)
            return [(json.dumps(self.beats[beat]),)]
        if sql == execution.EXCHANGE:
            if not self.receipt:
                return []
            return list(self.receipt) if isinstance(self.receipt, list) else [self.receipt]
        if sql == execution.PROMOTE:
            return [(json.dumps(self.promotion),)]
        if sql == execution.FINGERPRINT:
            return [(json.dumps(self.fingerprint),)]
        if sql == execution.TOPOLOGY:
            return [(json.dumps(self.topology),)]
        if sql == execution.FINISH:
            return [(json.dumps(self.closure),)]
        # Ticket 143. One column, one row: the status the Task ended at.
        if sql == execution.RETIRE:
            return [(self.retired,)]
        if sql == execution.agent.CLOSE:
            return [(self.refusal_closed,)]
        if sql == proxy.PARK_TOOL_RUN:
            return [("PD1",)]
        # Ticket 208: asked only when the Slate came back empty, and answered
        # with the shape rather than with a scenario. A fake that answered rows
        # here would be inventing a reason the scheduler never gave.
        if sql == execution.UNREADY:
            return list(self.unready)
        if sql == proposal.INSERT:
            return [(PROPOSAL, "PR1", proposal.STAGED)]
        # Two writers put rows in `proposal_drops`: the staging trigger, before
        # this side reads anything, and this side afterwards. The fake has no
        # trigger, so the first answer is nothing and the second is whatever the
        # runtime just wrote -- which is what `stage` reports back.
        if sql == proposal.NEXT_DROP:
            return [(0,)]
        if sql == proposal.DROPS:
            # The last four of the six: the ordinal this side chose, and the
            # three columns it wrote there.
            return [tuple(written[2:]) for written in self.sent(proposal.INSERT_DROP)]
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
        planning_stop: str | None = None,
    ):
        self.requests: list[agent.AgentRunRequest] = []
        self.choices: list[agent.AgentRunRequest] = []
        self.answer = answer
        self.error = error
        self.picks = picks
        self.planning = planning
        # How the session ended, in the SDK's own word. `None` is a session that
        # ran to the end of its own accord; ticket 161 is about the ones that
        # did not, and a stop reason is the only thing that tells them apart.
        self.planning_stop = planning_stop

    def __call__(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        if request.role == roster.ORCHESTRATOR:
            return self.choose(request)
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.answer if self.answer is not None else result()

    def choose(self, request: agent.AgentRunRequest) -> agent.AgentRunResult:
        """One session's answer, made through the latch a real child picks with.

        `planning` is the one thing this adds to the shared walk: a child that
        died before it could pick anything, which is a different case from one
        that picked nothing.
        """
        self.choices.append(request)
        if self.planning is not None:
            raise self.planning
        latch = fixtures.latched(
            () if request.capsule is None else request.capsule.slate(), self.picks
        )
        return result(
            agent_run_id=request.agent_run_id,
            role=request.role,
            text=f"{len(latch.entries)} offered",
            mission_result=None,
            choice=latch.task,
            pick_attempts=latch.attempts,
            **({} if self.planning_stop is None else {"stop_reason": self.planning_stop}),
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


class PacketLimitsTest(unittest.TestCase):
    """Decision 11's word "configured": which numbers a packet is fitted to.

    The capsule beside it has been configured since ticket 28, and the packet
    was fitted to whatever constants `packet.py` held -- so an operator who
    lowered the one ceiling they could set bounded one of the two documents a
    child reads. What is asserted here is the read: that the ceiling comes off
    the weights row, on the connection that can see it.
    """

    def fitted(self, **answers) -> packet.Limits:
        """The limits one compile was handed, from a weights row that says so."""
        with compiled():
            with mock.patch.object(
                execution.packet_module, "compile", return_value=packet.Packet()
            ) as compile:
                execution.Slice(boundary=BOUNDARY, state=STATE)._packet(
                    Ledger(), Recorder(**answers), PROGRAM, packet.Bounds()
                )
        return compile.call_args.kwargs["limits"]

    def test_the_packet_is_fitted_to_the_ceiling_the_weights_row_states(self):
        # Numbers that are not the module's defaults, because a test that used
        # the defaults would pass against a runtime that read nothing at all.
        self.assertEqual(
            packet.Limits(byte_limit=4096, token_limit=512),
            self.fitted(packet_limits=[(4096, 512)]),
        )

    def test_the_ceiling_is_read_as_the_runtime_and_not_as_the_agent(self):
        # `rk2_state` cannot see `scheduler_weights` and should not: what every
        # pass may spend is not a fact about the one Program a packet is of.
        runtime = Recorder()
        with compiled() as session:
            with mock.patch.object(
                execution.packet_module, "compile", return_value=packet.Packet()
            ):
                execution.Slice(boundary=BOUNDARY, state=STATE)._packet(
                    Ledger(), runtime, PROGRAM, packet.Bounds()
                )

        self.assertIn(execution.PACKET_LIMITS, runtime.statements)
        self.assertNotIn(execution.PACKET_LIMITS, session.statements)

    def test_a_scheduler_with_no_active_row_is_the_modules_own_numbers(self):
        # Both callers refuse a pass with no active weights row well before
        # this, and the columns default to these very numbers, so an empty
        # answer is a shape to have rather than a second setting to keep in step.
        self.assertEqual(packet.Limits(), self.fitted(packet_limits=[]))


def attempt(connection: Recorder, launcher: Launcher | None = None, **overrides):
    """One attempt, with the ledger and facts it produced."""
    ledger = Ledger()
    runner = execution.Slice(
        boundary=BOUNDARY, state=STATE, launch=launcher or Launcher(), **overrides
    )
    facts = runner.attempt(ledger, connection, PROGRAM)
    return ledger, facts


class DoorPreflightTest(unittest.TestCase):
    def test_a_mismatch_starts_no_agent_and_claims_no_task(self):
        launcher = Launcher()

        def refused(*_):
            raise isolation.Unavailable("the Door serves another database")

        ledger, facts = attempt(Recorder(), launcher, preflight=refused)

        self.assertEqual([], launcher.requests)
        self.assertIsNone(facts["task"])
        self.assertEqual(["door"], [item.source for item in ledger.violations])

    def test_the_door_is_checked_before_the_chooser_and_again_before_the_worker(self):
        checked = []

        def ready(*_):
            checked.append("ready")
            return "matched"

        with compiled():
            ledger, facts = attempt(Recorder(), preflight=ready)

        self.assertEqual([], list(ledger.violations))
        self.assertIsNotNone(facts["task"])
        self.assertEqual(["ready", "ready"], checked)


class ExcerptLoaderTest(unittest.TestCase):
    """The one thing the packet cannot compile for itself: Artifact bytes.

    The child has no route to the store, so the readable head of an Artifact
    reaches it inside the packet or not at all. Ticket 19's first criterion
    offers "reachable Artifacts under explicit bounds" and the served tool text
    offers a byte range, and both of those are promises about a loader the one
    production caller has to hand over.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rk2-excerpts-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.keep = store.Store(self.root)

    def test_the_compile_is_given_a_loader_when_the_machine_names_a_store(self):
        with compiled():
            with mock.patch.object(
                execution.packet_module, "compile", return_value=packet.Packet()
            ) as compile:
                execution.Slice(
                    boundary=BOUNDARY, state=STATE, artifacts=self.root
                )._packet(Ledger(), Recorder(), PROGRAM, packet.Bounds())

        self.assertIsNotNone(compile.call_args.kwargs["load"])

    def test_a_machine_that_names_no_store_says_so_rather_than_inventing_one(self):
        with compiled():
            with mock.patch.object(
                execution.packet_module, "compile", return_value=packet.Packet()
            ) as compile:
                execution.Slice(boundary=BOUNDARY, state=STATE)._packet(
                    Ledger(), Recorder(), PROGRAM, packet.Bounds()
                )
        self.assertIsNone(compile.call_args.kwargs["load"])

    def test_the_loader_reads_what_the_store_holds(self):
        sha256, _ = self.keep.put(b"<html>a page the hunter filed</html>")
        load = execution.Slice(
            boundary=BOUNDARY, state=STATE, artifacts=self.root
        )._excerpt_loader()

        self.assertEqual(b"<html>a page the hunter filed</html>", load(sha256))

    def test_an_artifact_the_store_lost_is_a_head_that_is_not_here(self):
        """Not an exception. A packet is not worth losing over one missing file,
        and `_excerpts` already has a word for an Artifact it cannot quote."""
        sha256, _ = self.keep.put(b"the bytes that were filed")
        load = execution.Slice(
            boundary=BOUNDARY, state=STATE, artifacts=self.root
        )._excerpt_loader()
        store.path_for(self.root, sha256).write_bytes(b"not what it is named after")

        self.assertIsNone(load(sha256))
        self.assertIsNone(load("0" * 64))


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
        text = claimed().objective(())
        self.assertIn("GET https://app.example.com/login", text)
        self.assertIn("the endpoint GET /login", text)

    def test_the_objective_states_the_rule_promotion_will_apply(self):
        text = claimed().objective(())
        self.assertIn("mcp__rk2__http_request", text)
        self.assertIn("mcp__rk2__submit_mission_result", text)
        self.assertIn("Receipt", text)

    def test_the_objective_asks_for_the_claim_the_run_is_entitled_to_file(self):
        """Six hunts filed no Hypothesis because nothing asked for one."""
        text = claimed().objective(())
        self.assertIn("Hypothesis", text)
        self.assertIn("property_class", text)
        for answered in ("mechanism", "expectation", "falsifier"):
            self.assertIn(answered, text)
        self.assertIn("evidence edge", text)

    def test_the_objective_bounds_the_claim_it_asks_for(self):
        """Asking without bounding buys claims the one answer cannot carry."""
        text = claimed().objective(())
        self.assertIn("file none", text)
        self.assertIn("rolled back", text)
        self.assertIn("Do not say what state a claim is in", text)

    def test_the_claim_is_asked_for_after_what_the_run_owes_back(self):
        text = claimed().objective(())
        self.assertLess(
            text.index("mcp__rk2__submit_mission_result"), text.index("A Hypothesis is")
        )

    def test_a_hunt_is_told_which_claim_it_was_minted_to_settle(self):
        """Two hunts ran in `rk2hunt7` and filed no Test, because nothing asked.

        The tool was served -- `web_hunter` holds `state.propose` -- and the
        claim was in the packet. What was missing was the sentence naming it.
        """
        text = claimed(kind="hunt", hypothesis_label="H1").objective(())
        self.assertIn("H1", text)
        self.assertIn("mcp__rk2__propose_test", text)
        for part in ("baseline", "variant", "control"):
            self.assertIn(part, text)

    def test_the_test_is_asked_for_before_the_ending_that_files_everything(self):
        """`rk2hunt8`'s hunt was told to file a Test and submitted instead.

        `MISSION_STOPS` tells every child that submitting the mission result is
        the only ending that files anything, so a run that submits first never
        reaches the call. Naming the tool was not enough; the order is the
        instruction.
        """
        text = claimed(kind="hunt", hypothesis_label="H1").objective(())
        self.assertIn(
            "mcp__rk2__propose_test before mcp__rk2__submit_mission_result", text
        )

    def test_a_hunt_that_names_no_claim_is_told_nothing_about_one(self):
        """A Task minted by something other than the derivation carries no id."""
        text = claimed(kind="hunt").objective(())
        self.assertNotIn("mcp__rk2__propose_test", text)

    def test_only_a_hunt_is_asked_for_the_test(self):
        """A recon Task with a claim attached is still not the run that settles it."""
        text = claimed(hypothesis_label="H1").objective(())
        self.assertNotIn("mcp__rk2__propose_test", text)

    def test_a_kind_nobody_wrote_prose_for_is_described_rather_than_refused(self):
        self.assertIn("Carry out this exotic Task", claimed(kind="exotic").objective(()))

    def test_every_kind_the_roster_dispatches_has_its_own_sentence(self):
        dispatched = {kind for role in roster.ROLES.values() for kind in role.task_kinds}
        self.assertEqual(set(), dispatched - set(execution.MISSIONS))

    def test_a_selected_playbook_is_carried_into_what_the_child_is_told(self):
        """The whole projection, because a summary is not what was selected."""
        projection = SELECTED_PLAYBOOK.projection
        text = claimed().objective((projection,))
        self.assertIn(projection.text(), text)
        self.assertIn("selected 1 Playbook(s)", text)

    def test_the_playbooks_do_not_displace_what_the_run_owes_back(self):
        text = claimed().objective((SELECTED_PLAYBOOK.projection,))
        self.assertIn("mcp__rk2__submit_mission_result", text)
        self.assertLess(
            text.index("mcp__rk2__submit_mission_result"),
            text.index(SELECTED_PLAYBOOK.projection.text()),
        )

    def test_a_subject_nothing_was_selected_for_is_told_no_more_than_before(self):
        """Not a sentence about an empty list: an empty list is not a Playbook."""
        self.assertNotIn("Playbook", claimed().objective(()))


class FindingVocabularyTest(unittest.TestCase):
    """Ticket 163. The words a `conclude` child has to name one of.

    `rk2hunt17` reached `conclude` twice, spent six runs and eighteen proposals
    on synonyms of a class the vocabulary has no word for, and filed no Finding:
    the objective said "a vulnerability class from this harness's vocabulary"
    and the vocabulary was in a table the child has no route to. What is
    asserted here is that the list travels with the objective and comes from
    the table, so that seeding a thirty-eighth class cannot leave the prompt
    describing thirty-seven.
    """

    def concluding(self, **overrides) -> str:
        subject = claimed(
            kind="conclude", role="web_hunter", hypothesis_label="H1", **overrides
        )
        return subject.objective((), SEEDED_CLASSES)

    def dispatched(self, **answers) -> tuple[Recorder, Launcher]:
        connection = Recorder(
            started=(started_row(kind="conclude", role="web_hunter", hypothesis_label="H1"),),
            **answers,
        )
        launcher = Launcher()
        with compiled():
            self.ledger, _ = attempt(connection, launcher)
        return connection, launcher

    def test_a_conclude_objective_carries_every_class_the_corpus_seeds(self):
        text = self.concluding()
        for one in SEEDED_CLASSES:
            with self.subTest(one):
                self.assertIn(one, text)

    def test_the_vocabulary_the_child_reads_is_the_one_the_table_answered(self):
        # The list is not built here: the pass asks `vulnerability_classes` for
        # it and hands over what came back, which is what makes a class seeded
        # by a later migration reach the prompt without anybody editing it.
        connection, launcher = self.dispatched()

        self.assertIn(execution.CLASSES, connection.statements)
        for one in SEEDED_CLASSES:
            with self.subTest(one):
                self.assertIn(one, launcher.only.objective)
        self.assertEqual([], self.ledger.violations)

    def test_a_word_this_table_does_not_hold_is_offered_to_nobody(self):
        # The class `rk2hunt17` kept reaching for, which is not in the table and
        # must not be in the prompt either: the ticket is about showing the
        # vocabulary, not about widening it.
        self.assertNotIn("missing_security_headers", self.concluding())
        self.assertNotIn("missing_security_headers", SEEDED_CLASSES)

    def test_the_objective_says_what_to_do_when_no_word_on_the_list_fits(self):
        # Six runs ended on three refusals each because the only move the prompt
        # described was proposing again. A child that cannot name the weakness
        # has an answer to give, and this is where it is told what it is.
        text = self.concluding()

        self.assertIn("do not reach for the nearest synonym", text)
        self.assertIn("without a Finding", text)

    def test_a_kind_that_proposes_no_finding_is_told_none_of_this(self):
        # The list is 37 words in every objective that would never use them.
        # A recon child reads what it needs and pays for what it reads.
        connection = Recorder()
        launcher = Launcher()
        with compiled():
            attempt(connection, launcher)

        self.assertNotIn(execution.CLASSES, connection.statements)
        self.assertNotIn("cleartext_transmission", launcher.only.objective)

    def test_a_vocabulary_that_could_not_be_read_starts_no_child(self):
        # A `conclude` child dispatched without it is the run this ticket is
        # about: it calls the one tool the Task was opened for, is refused for a
        # word nobody showed it, and leaves the Task exactly where it was.
        connection, launcher = self.dispatched(classes=[])

        self.assertEqual([], launcher.requests)
        self.assertEqual(
            [execution.INTEGRITY_FAILED], [one.code for one in self.ledger.violations]
        )


class BandingObjectiveTest(unittest.TestCase):
    """Ticket 221. The second shape of `conclude`, and what tells it from the first.

    `F9` on `rk2here` was the first Finding this harness reached `validated` and
    it sat at `info` afterwards, because nothing put a run in front of a
    validated Finding. The kind that holds `state_severity` is this one, and the
    column that says which of its two jobs a Task is is `tasks.finding_id`.

    So what is asserted here is the dispatch and not the prose: a Task carrying
    a Finding is told to band it, a Task carrying none is told to name one, and
    neither objective leaks into the other.
    """

    def banding(self, **overrides) -> str:
        subject = claimed(
            kind="conclude",
            role="web_hunter",
            hypothesis_label="H165",
            finding_label="F9",
            **overrides,
        )
        return subject.objective((), SEEDED_CLASSES)

    def naming(self) -> str:
        subject = claimed(kind="conclude", role="web_hunter", hypothesis_label="H165")
        return subject.objective((), SEEDED_CLASSES)

    def test_a_task_that_names_a_finding_is_asked_for_the_band_and_not_the_class(self):
        text = self.banding()

        self.assertIn(execution.BANDING, text)
        self.assertIn("The Finding F9 is validated", text)
        self.assertIn("mcp__rk2__state_severity", text)
        self.assertNotIn("mcp__rk2__propose_finding", text)

    def test_a_task_that_names_none_keeps_the_objective_ticket_156_wrote(self):
        # The other half of the dispatch, asserted because one kind now has two
        # objectives and the failure that costs a run is the wrong one arriving.
        text = self.naming()

        self.assertIn("mcp__rk2__propose_finding", text)
        self.assertNotIn("mcp__rk2__state_severity", text)
        self.assertNotIn(execution.BANDING, text)

    def test_the_vocabulary_is_not_spent_on_a_child_that_chooses_no_class(self):
        # 37 words the banding child would never use. The class was chosen when
        # the Finding was created and this run is not choosing it again.
        text = self.banding()
        for word in ("error_disclosure", "cleartext_transmission"):
            with self.subTest(word):
                self.assertNotIn(word, text)

    def test_each_basis_is_named_with_the_refusal_that_waits_behind_it(self):
        # Ticket 163's lesson over a second vocabulary: `state_severity` refuses
        # each of the three for its own reason, and a child that learns those
        # from three refusals has spent the attempt learning them.
        text = self.banding()

        self.assertIn("demonstrated_impact", text)
        self.assertIn("constrained_inference", text)
        self.assertIn("program_context", text)
        self.assertIn("cannot carry high or critical", text)

    def test_the_child_is_told_it_may_state_no_band_at_all(self):
        # There are four bands and none of them means `nothing`, so a run that
        # judges the Finding worthless has no word to say it in. Reaching for
        # `low` to have said something is the failure this paragraph prevents.
        text = self.banding()

        self.assertIn("There is no band for `nothing`", text)
        self.assertIn("Do not reach for low to have said something", text)

    def test_the_finding_reaches_the_objective_through_the_row_the_query_returns(self):
        # The dispatch is worth nothing if the column never arrives. This is the
        # `STARTED` row read the way `from_row` reads it, one column longer than
        # it was before this ticket.
        subject = execution.Claimed.from_row(
            started_row(kind="conclude", hypothesis_label="H165", finding_label="F9")
        )

        self.assertEqual("F9", subject.finding_label)
        self.assertIn("The Finding F9 is validated", subject.objective(()))

    def test_a_row_from_before_this_column_reads_as_a_task_naming_no_finding(self):
        # Every kind but one shape of one carries no Finding, and a fixture one
        # column short is describing exactly that rather than a broken row.
        short = started_row(kind="conclude", hypothesis_label="H165")[:18]

        self.assertIsNone(execution.Claimed.from_row(short).finding_label)


class ImpactObjectiveTest(unittest.TestCase):
    """Ticket 226 wall 1. The third shape of `conclude`, and what tells it apart.

    `grep -n "open_impact_task" execution.py` returned nothing before this
    ticket. The verb is granted through `state.conclude`, wrapped by ticket 103
    and described in the roster, and no objective ever asked for it -- so no
    impact Test was ever written, so the lane wall 2 built had nothing to run,
    so `pivot_stamps` and `chains` held zero rows after 197 laps.

    What says which of the kind's three jobs a Task is is not a column on the
    Task. It is `rk2_task_proves_impact`, which asks whether the Task was opened
    after the band was stated -- `rk2_severity_frontier` cannot open a band Task
    once a statement exists, so the two never overlap. So what is asserted here
    is that reading and the dispatch it drives.
    """

    def proving(self, **overrides) -> str:
        subject = claimed(
            kind="conclude",
            role="web_hunter",
            hypothesis_label="H165",
            finding_label="F9",
            proves_impact=True,
            **overrides,
        )
        return subject.objective((), SEEDED_CLASSES)

    def banding(self) -> str:
        subject = claimed(
            kind="conclude", role="web_hunter", hypothesis_label="H165",
            finding_label="F9",
        )
        return subject.objective((), SEEDED_CLASSES)

    def test_a_banded_finding_is_asked_for_the_impact_and_not_the_band_again(self):
        text = self.proving()

        self.assertIn(execution.PROVING, text)
        self.assertIn("mcp__rk2__open_impact_task", text)
        self.assertNotIn(execution.BANDING, text)
        self.assertNotIn("mcp__rk2__propose_finding", text)

    def test_a_finding_nobody_has_banded_keeps_the_objective_221_wrote(self):
        # The half of the dispatch that must not move. The band comes first
        # because `rk2_severity_frontier` refuses a Finding any `conclude` Task
        # already names, so a run sent to prove impact before the band was
        # stated would be the row that closes ticket 221's lane.
        text = self.banding()

        self.assertIn(execution.BANDING, text)
        self.assertIn("mcp__rk2__state_severity", text)
        self.assertNotIn(execution.PROVING, text)
        self.assertNotIn("mcp__rk2__open_impact_task", text)

    def test_only_the_classes_an_operator_may_authorize_are_offered(self):
        # Ticket 163's lesson over a third vocabulary, and the extra rule this
        # one carries: three of the six impact classes are `forbidden`, and
        # `rk2_refuse_forbidden_impact` refuses them inside `open_impact_task`.
        # A word shown here and refused there is the exact shape 163 measured.
        text = self.proving()

        for word in roster.IMPACT_CLASSES:
            with self.subTest(word):
                self.assertIn(word, text)
        for word in ("degrade_availability", "pivot_out_of_scope", "reach_third_party"):
            with self.subTest(word):
                self.assertNotIn(word, text)

    def test_the_child_is_told_not_to_run_what_it_writes(self):
        # The one paragraph this objective could not do without. An impact run
        # writes to a live system and `open_impact_replay` parks the Task and
        # asks an operator before it happens; a child that demonstrated it
        # itself would have performed the unauthorized half of the procedure
        # this harness exists to ask permission for.
        text = self.proving()

        self.assertIn("YOU DO NOT RUN THIS TEST", text)
        self.assertIn("Write the plan and stop", text)

    def test_the_objective_says_what_to_do_when_no_class_fits(self):
        # `_conclusion`'s rule over a third vocabulary. A child that cannot name
        # the impact has an answer to give, and a specification written for a
        # class the weakness does not have is a run against a live target for
        # nothing.
        text = self.proving()

        self.assertIn("do not reach for the nearest one", text)
        self.assertIn("no specification", text)

    def test_the_basis_reaches_the_objective_through_the_row_the_query_returns(self):
        # The dispatch is worth nothing if the column never arrives. This is the
        # `STARTED` row read the way `from_row` reads it, one column longer than
        # wall 2 left it.
        subject = execution.Claimed.from_row(
            started_row(kind="conclude", hypothesis_label="H165", finding_label="F9",
                        proves_impact=True)
        )

        self.assertTrue(subject.proves_impact)
        self.assertIn("mcp__rk2__open_impact_task", subject.objective(()))

    def test_a_row_from_before_this_column_reads_as_a_finding_nobody_banded(self):
        # A fixture one column short describes every `conclude` Task this
        # harness derived before wall 1, which is the band and not the proof.
        short = started_row(kind="conclude", hypothesis_label="H165",
                            finding_label="F9")[:20]
        subject = execution.Claimed.from_row(short)

        self.assertFalse(subject.proves_impact)
        self.assertIn(execution.BANDING, subject.objective(()))


class ImpactReplayTest(unittest.TestCase):
    """Ticket 226. Which replay a `perform` Task runs, and what decides it.

    `replay.IMPACT` is the only verb set that calls `issue_pivot_stamp` and
    `build_kill_chain`, and until this ticket it was selected in one place:
    `rk test replay --impact`, an operator command. The runtime took the
    `DETECTION` default on every Task it ever performed, which is why
    `pivot_stamps` held zero rows on a Program that had run 197 laps.

    What is asserted is the dispatch and the column that carries it, not the
    replay itself -- `replay.run` has its own case, and a test that walked one
    here would be testing the performer through the caller.
    """

    def test_a_task_whose_test_states_an_impact_carries_the_impact_class(self):
        subject = claimed(kind="perform", test_label="TS3",
                          impact_class="read_another_tenants_record")

        self.assertIsNotNone(subject.impact_class)

    def test_a_task_whose_test_states_none_is_a_detection_task(self):
        # The other half of the dispatch. Every Test written before this ticket
        # is this shape, so the default is the one that must not move.
        self.assertIsNone(claimed(kind="perform", test_label="TS3").impact_class)

    def test_the_class_reaches_the_claim_through_the_row_the_query_returns(self):
        # The dispatch is worth nothing if the column never arrives. This is the
        # `STARTED` row read the way `from_row` reads it, one column longer than
        # ticket 221 left it.
        subject = execution.Claimed.from_row(
            started_row(kind="perform", test_label="TS3",
                        impact_class="read_another_tenants_record")
        )

        self.assertEqual("read_another_tenants_record", subject.impact_class)

    def test_a_row_from_before_this_column_reads_as_a_detection_task(self):
        short = started_row(kind="perform", test_label="TS3")[:19]

        self.assertIsNone(execution.Claimed.from_row(short).impact_class)

    def test_the_two_verb_sets_are_not_the_same_object(self):
        # The assertion the dispatch rests on, stated once here rather than
        # implied at four call sites: `IMPACT` carries the two verbs that stamp
        # a pivot and compose a chain, and `DETECTION` carries neither.
        self.assertTrue(replay.IMPACT.stamp_sql)
        self.assertTrue(replay.IMPACT.chain_sql)
        self.assertFalse(replay.DETECTION.stamp_sql)
        self.assertFalse(replay.DETECTION.chain_sql)

    def replay_called(self, **overrides) -> mock.Mock:
        """One `perform` attempt, and the `replay.run` the runtime called.

        The whole harness for it is `PerformTest.performing`, 1600 lines below,
        and what is needed here is its mock rather than its five return values.
        `PerformTest.SETTLED` and `PerformTest.DOOR` are referenced instead of
        respelled: the first is what a settled replay answers with, and the
        second is the runtime's own address for the door, which `_replay`
        refuses to run without.
        """
        connection = Recorder(
            started=(
                started_row(
                    kind="perform", role="performer", test_label="TS3", **overrides
                ),
            )
        )
        performed = outcome_module.Report(
            "test replay", facts=dict(PerformTest.SETTLED)
        )
        with compiled():
            with mock.patch.object(
                execution.replay_module, "run", return_value=performed
            ) as run:
                attempt(
                    connection,
                    configuration=Path("/tmp/program.toml"),
                    proxy_url=PerformTest.DOOR,
                )
        return run

    def test_the_runtime_hands_the_performer_the_impact_verbs(self):
        # Ticket 226 cycle 1's finding, and the one thing the four tests above
        # do not reach: `Claimed.impact_class` arriving is worth nothing unless
        # `_replay` spends it, and nothing read the call it makes. Narrowing
        # `execution.py`'s selection to a flat `DETECTION` left the whole tree
        # green; it turns this test red.
        run = self.replay_called(impact_class="read_another_tenants_record")

        self.assertIs(replay.IMPACT, run.call_args.kwargs["verbs"])

    def test_a_task_whose_test_states_no_impact_is_handed_the_detection_verbs(self):
        # The other half, at the same seam. Every Test written before this
        # ticket is this shape, so a selection that sent `IMPACT` to all of them
        # would stamp a pivot off runs that claim none.
        run = self.replay_called()

        self.assertIs(replay.DETECTION, run.call_args.kwargs["verbs"])


class AttemptProfileTest(unittest.TestCase):
    """Ticket 165. What makes two attempts the same attempt, and what follows.

    `rk2hunt20`'s T6 ran twice at the full ceiling, ended on `budget` both
    times, closed nothing and was still at the top of the ranking for a third
    identical run. The scheduler ranks a Task and not a Task-and-how-it-was-
    sent, so this is the sentence that lets a pass tell a repeat from a retry.
    """

    def profile(self, mission=None, role: str = "recon", **overrides) -> str:
        return execution.attempt_profile(
            claimed(**overrides), mission or packet.Packet(), roster.ROLES[role]
        )

    def test_the_same_dispatch_twice_is_the_same_profile(self):
        self.assertEqual(self.profile(), self.profile())

    def test_every_part_of_the_dispatch_moves_the_profile(self):
        first = self.profile()
        moved = {
            "another Task": self.profile(task_id=SUBJECT),
            "another packet": self.profile(packet.Packet(revision=99)),
            "another role": execution.attempt_profile(
                claimed(role="web_hunter"), packet.Packet(), roster.ROLES["web_hunter"]
            ),
            "another ceiling": self.profile(token_cap=20_000),
        }

        for what, digest in moved.items():
            with self.subTest(what):
                self.assertNotEqual(first, digest)

    def test_the_model_the_build_and_the_bundled_pair_are_in_it_too(self):
        # A build that changed is a dispatch that changed: the objective, the
        # ceiling arithmetic and the tool surface all live in these modules, so
        # a Task refused a third attempt under one build is owed a first one
        # under the next. The same argument covers the model and the SDK/CLI
        # pair the child runs against.
        first = self.profile()
        another = dataclasses.replace(roster.ROLES["recon"], model="another-model")
        moved = {}
        with mock.patch.object(execution, "_tree_digest", return_value="0" * 64):
            moved["another build"] = self.profile()
        with mock.patch.object(_startup, "KNOWN_RUNTIME", ("9.9.9", "9.9.9")):
            moved["another SDK and CLI"] = self.profile()
        moved["another model"] = execution.attempt_profile(
            claimed(), packet.Packet(), another
        )

        for what, digest in moved.items():
            with self.subTest(what):
                self.assertNotEqual(first, digest)

    def test_the_hint_the_repeat_produces_is_not_part_of_what_repeated(self):
        # The narrowed instruction is what this runtime says *because* the
        # profile repeated. A profile that carried it would differ on the retry
        # it is the consequence of, and the second budget end would look like a
        # first one forever.
        first = Recorder()
        second = Recorder(budget_ends=1)
        with compiled():
            attempt(first)
            attempt(second)

        self.assertEqual(
            first.spend()["attempt_profile_sha256"],
            second.spend()["attempt_profile_sha256"],
        )
        self.assertNotEqual(
            first.sent(execution.BUDGET_ENDS), []
        )

    def test_the_profile_is_written_with_the_closing_that_charges_the_run(self):
        connection = Recorder()
        with compiled():
            _, facts = attempt(connection)

        self.assertEqual(
            facts["agent_run"]["attempt_profile"],
            connection.spend()["attempt_profile_sha256"],
        )

    def test_a_second_attempt_is_told_to_finish_rather_than_to_look(self):
        # The ceiling buys turns and not tokens, so the same instruction buys
        # the same turns and spends them the same way. The retry is a narrower
        # job rather than a wider budget.
        launcher = Launcher()
        with compiled():
            ledger, _ = attempt(Recorder(budget_ends=1), launcher)
        text = launcher.only.objective

        self.assertIn("already run out of tokens once", text)
        self.assertIn("Mission packet you were given", text)
        self.assertIn("Do not explore", text)
        self.assertEqual([], ledger.violations)

    def test_a_first_attempt_is_told_none_of_that(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(), launcher)

        self.assertNotIn("already run out of tokens once", launcher.only.objective)

    def test_a_third_identical_attempt_is_not_made_at_all(self):
        launcher = Launcher()
        connection = Recorder(budget_ends=2)
        with compiled():
            ledger, facts = attempt(connection, launcher)
        (task, detail), = connection.sent(execution.RETIRE)

        self.assertEqual([], launcher.requests)
        self.assertEqual(TASK, task)
        self.assertIn("budget_exhausted_twice", detail)
        self.assertEqual([], ledger.violations)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)

    def test_the_count_is_asked_of_this_profile_and_not_of_the_task_alone(self):
        # "If the packet, the build or the policy change, a first retry is
        # allowed again" is this parameter and nothing else: the count is keyed
        # on the profile, so a dispatch that moved counts nothing against it.
        connection = Recorder(budget_ends=2)
        with compiled():
            _, facts = attempt(connection)

        self.assertEqual(
            [(TASK, facts["agent_run"]["attempt_profile"])],
            connection.sent(execution.BUDGET_ENDS),
        )

    def test_a_count_that_could_not_be_read_starts_no_child(self):
        launcher = Launcher()
        connection = Recorder(raises={execution.BUDGET_ENDS: database_error("gone")})
        with compiled():
            ledger, _ = attempt(connection, launcher)

        self.assertEqual([], launcher.requests)
        self.assertEqual(
            [execution.INTEGRITY_FAILED], [one.code for one in ledger.violations]
        )


class SpendTest(unittest.TestCase):
    """What a run cost, in the numbers the ceiling was actually made of.

    Ticket 165's first item. `input_tokens` is the provider's sum of every
    turn's whole request, prefix and all, so a 250 000 ceiling bought a
    `web_hunter` six turns; the turn count was arithmetic on this side and the
    cache split was thrown away. Both now travel from the child to the row.
    """

    def test_the_closing_carries_what_the_child_measured(self):
        connection = Recorder()
        with compiled():
            attempt(connection)

        self.assertEqual(
            {
                "uncached_input_tokens": 200,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 900,
                "answer_count": 6,
                "budget_tokens": 690,
                "budget_policy": execution.BUDGET_POLICY,
                "error_detail": None,
            },
            {name: connection.spend()[name] for name in execution.SPEND},
        )

    def test_the_pass_reports_them_beside_the_two_totals(self):
        with compiled():
            _, facts = attempt(Recorder())
        run = facts["agent_run"]

        self.assertEqual(1200, run["input_tokens"])
        self.assertEqual(6, run["answer_count"])
        self.assertEqual(900, run["cache_read_input_tokens"])
        self.assertEqual(execution.BUDGET_POLICY, run["budget_policy"])

    def test_a_child_that_never_answered_leaves_them_alone(self):
        # Nothing rather than zero, for the reason the two totals already give:
        # a run whose child never reported spent an amount nobody measured, and
        # a zero written here would be settled against.
        connection = Recorder()
        launcher = Launcher(error=RuntimeError("the child died"))
        with compiled():
            attempt(connection, launcher)

        expected = dict.fromkeys(execution.SPEND)
        expected["error_detail"] = "the child died"
        self.assertEqual(
            expected, {name: connection.spend()[name] for name in execution.SPEND}
        )

    def test_the_session_that_chose_is_charged_the_same_way(self):
        # The one closing verb, for the one reason: a second place the tokens
        # are settled is a second answer to what a Program has spent.
        connection = Recorder()
        with compiled():
            attempt(connection)

        self.assertEqual(690, connection.spend(SESSION)["budget_tokens"])
        self.assertIsNone(connection.spend(SESSION)["attempt_profile_sha256"])

    def test_what_the_child_said_went_wrong_reaches_the_row(self):
        connection = Recorder()
        launcher = Launcher(
            answer=result(stop_reason="error", error_detail="the SDK closed the stream")
        )
        with compiled():
            attempt(connection, launcher)

        self.assertEqual(
            "the SDK closed the stream", connection.spend()["error_detail"]
        )


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

    def slate_sentence(self, **answers) -> str:
        connection = Recorder(slate=0, **answers)
        ledger, _ = attempt(connection, Launcher())
        return [one.detail for one in ledger.assertions if one.name == "slate"][-1]

    def test_an_empty_slate_says_which_wall_the_pass_hit(self):
        # Ticket 208. `rk2here` held 685 pending Tasks whose two working lanes
        # had each spent all but one run's worth of their token ceiling, and the
        # pass said "no Task is ready" -- which reads as a campaign that
        # finished. `claimable_for` is the predicate the offer filters on, so
        # the reason was there to be asked for the whole time.
        said = self.slate_sentence(
            unready=[("lane_tokens_reserved", 653), ("hunt.no_address", 6)]
        )

        self.assertIn("no Task is ready", said)
        self.assertIn("653 lane_tokens_reserved", said)
        self.assertIn("6 hunt.no_address", said)

    def test_a_program_with_nothing_pending_says_that_instead(self):
        # The other empty Slate, and the one the sentence used to mean: there is
        # no wall, there is no Task. An operator reading this one has a campaign
        # that is actually done.
        said = self.slate_sentence()

        self.assertIn("no Task is ready", said)
        self.assertIn("no Task is pending", said)

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
        self.assertEqual(
            ["T1", "T2", "T3"], [entry["task"] for entry in planning.capsule.slate()]
        )
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

    def test_a_chooser_the_ceiling_cut_off_is_not_a_slate_nobody_wanted(self):
        # Ticket 161, and the shape `rk2hunt17` lap 6 had: Tasks on the Slate,
        # a session that spent its token ceiling before it picked one, and a
        # claim that answered nothing because the walk found the Slate held
        # only what the choice would have named. The database still hears
        # `no_choice` -- that vocabulary is closed by a migration -- but the
        # pass now carries the word for why, and the detail says it too.
        connection = Recorder(claim=None)
        facts = self.choice(connection, Launcher(picks=None, planning_stop="budget"))
        _, outcome, _, detail = connection.sent(execution.CHOICE)[0]

        self.assertEqual("no_choice", outcome)
        self.assertIn("stopped as budget", detail)
        self.assertEqual("budget", facts["choice"]["cut_off"])
        self.assertIsNone(facts["task"])
        self.assertNotEqual(
            program.STOPPED_NOTHING_TO_EXECUTE,
            program._report(self.ledger, program._State(execution=facts)).facts["stop_reason"],
        )

    def test_a_chooser_that_read_the_slate_and_declined_it_was_cut_off_by_nothing(self):
        # The other half: `nothing_to_execute` has to keep meaning something, so
        # a session that ran to the end of its own accord and named no Task
        # carries no cut-off word however empty its answer was.
        connection = Recorder(claim=None)
        facts = self.choice(connection, Launcher(picks=None))

        self.assertEqual("no_choice", facts["choice"]["outcome"])
        self.assertIsNone(facts["choice"]["cut_off"])
        self.assertEqual(
            program.STOPPED_NOTHING_TO_EXECUTE,
            program._report(self.ledger, program._State(execution=facts)).facts["stop_reason"],
        )

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

    def test_a_choice_that_could_not_be_recorded_claims_nothing_in_its_place(self):
        # ADR 0003 refuses a choice it cannot honour rather than replacing it,
        # and a failed write is one it cannot honour: nothing is outstanding, so
        # the fallback walk would take entry one on behalf of a session that
        # named a Task. The session is still closed and the failure reported.
        connection = Recorder(raises={execution.CHOICE: database_error("gone")})
        facts = self.choice(connection)

        self.assertEqual(
            (execution.UNRECORDED, "T1"),
            (facts["choice"]["outcome"], facts["choice"]["task"]),
        )
        self.assertIsNone(facts["task"])
        self.assertNotIn(execution.CLAIM, connection.statements)
        self.assertEqual([(SESSION, "completed", 1200, 300)], connection.finished(SESSION))
        self.assertEqual(execution.INTEGRITY_FAILED, self.ledger.violations[0].code)

    def test_a_silent_session_whose_record_failed_still_falls_back(self):
        # The other half of the same rule: a session that named nothing has
        # nothing to refuse, so a write that failed leaves the pass exactly
        # where a session that answered `no_choice` would have.
        connection = Recorder(raises={execution.CHOICE: database_error("gone")})
        facts = self.choice(connection, Launcher(picks=None))

        self.assertIsNone(facts["choice"])
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


class CapsuleTest(unittest.TestCase):
    """PH2-28 at the seam: what a turn of a campaign is started with.

    The rotation itself is the database's -- `open_orchestrator_session` closes
    a spent campaign before it opens a turn -- so what is asserted here is what
    this runtime does with the answer: it says so, it compiles the capsule under
    the ceilings the campaign was opened with, and it treats a capsule it could
    not build as one more way of nobody being asked.
    """

    def choice(self, connection: Recorder, launcher: Launcher | None = None) -> dict:
        launcher = launcher or Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.ledger, self.launcher = ledger, launcher
        return facts

    def stated(self, name: str) -> list:
        """Every assertion one step of the pass made, in order."""
        return [
            assertion for assertion in self.ledger.assertions if assertion.name == name
        ]

    def rotated(self, **overrides) -> dict:
        """A session row that says the campaign before it reached a ceiling.

        `rotated` is the `scheduler.rotated` payload, because that is what
        `open_orchestrator_session` returns under that key -- an object, not a
        label. A fixture that put a label there would let a runtime that prints
        the whole payload pass.
        """
        return dict(
            Recorder().session,
            session_label="OS4",
            generation=4,
            rotated={
                "session": "OS3",
                "generation": 3,
                "reason": "turns",
                "usage": {"turns": 100, "tokens": 4096, "decisions": 12},
                "ceilings": {"turns": 100, "tokens": 1000000, "decisions": 80},
            },
            **overrides,
        )

    def test_the_capsule_carries_the_five_sections_a_session_resumes_from(self):
        # Criterion 3. Compiled rather than remembered: the previous session's
        # turns are rows, and this process holds nothing of them.
        connection = Recorder(slate=3)
        self.choice(connection)
        resumed = self.launcher.planned.capsule

        self.assertEqual(
            ["lifecycle", "budget", "integrity", "work", "slate"],
            list(resumed.as_dict()["sections"]),
        )
        self.assertEqual("OS1", resumed.session)
        self.assertEqual(12, resumed.revision)
        self.assertEqual(
            ["matrix-web", "OS1"],
            [row.label for row in resumed.section("lifecycle").rows],
        )
        self.assertEqual(["T1", "T2", "T3"], [e["task"] for e in resumed.slate()])

    def test_every_row_carries_the_revision_and_the_digest_the_server_gave_it(self):
        # The Spec's "revisions, digests and omission markers", and the rule
        # that comes with them: a digest this process computed would be a second
        # answer to a question the database already answers.
        connection = Recorder()
        self.choice(connection)
        resumed = self.launcher.planned.capsule
        program_row = resumed.section("lifecycle").rows[0]
        checked = resumed.section("integrity").rows[0]

        self.assertEqual(12, program_row.revision)
        self.assertEqual("matrix-web-digest", program_row.digest)
        self.assertEqual(
            digested(json.dumps([dict(checked.record)]))[0][1], checked.digest
        )
        self.assertEqual(0, checked.revision)
        self.assertEqual(
            0, self.launcher.planned.capsule.as_dict()["sections"]["work"]["omitted"]
        )

    def test_a_standing_check_that_failed_is_the_first_row_of_its_section(self):
        # Ordered so that a section cut down to its last rows keeps the ones
        # that say something is wrong: `fit` drops from the tail.
        connection = Recorder(
            standing=[("event_coverage", 0, ""), ("lease_discipline", 2, "two open")]
        )
        self.choice(connection)
        rows = self.launcher.planned.capsule.section("integrity").rows

        self.assertEqual(["standing:lease_discipline", "standing:event_coverage"],
                         [row.label for row in rows])
        self.assertEqual(False, rows[0].record["ok"])
        self.assertIn("two open", rows[0].record["detail"])

    def test_the_objective_states_the_campaign_and_leaves_the_slate_to_the_tool(self):
        # Criterion 3 says the replacement *receives* the capsule, so it is in
        # the prompt rather than behind a call it may never make. The Slate is
        # not, because `get_slate` already serves it from the same document.
        connection = Recorder(slate=3, session=self.rotated())
        self.choice(connection)
        objective = self.launcher.planned.objective

        self.assertIn("You are OS4, generation 4", objective)
        self.assertIn('"lifecycle"', objective)
        self.assertIn('"integrity"', objective)
        self.assertNotIn('"slate"', objective)
        self.assertNotIn("T2", objective)

    def test_a_closed_campaign_is_reported_by_the_pass_that_replaced_it(self):
        # The one thing about a rotation an operator cannot read anywhere else
        # in the Ledger: the Events are the database's and the pass looks
        # otherwise identical to any other.
        connection = Recorder(session=self.rotated())
        self.choice(connection)
        holds = self.stated("rotation")

        self.assertEqual([], self.ledger.violations)
        self.assertEqual(1, len(holds))
        self.assertIn("OS3 reached its turns ceiling and was closed", holds[0].detail)
        self.assertIn("OS4 continues it at generation 4", holds[0].detail)

    def test_a_first_generation_campaign_reports_no_rotation(self):
        connection = Recorder()
        self.choice(connection)

        self.assertEqual([], self.stated("rotation"))
        self.assertIn(
            f"OS1 resumes at generation 1 from "
            f"{len(self.launcher.planned.capsule.rows())} row(s)",
            self.stated("capsule")[0].detail,
        )

    def test_the_capsule_is_compiled_under_the_ceilings_the_campaign_opened_with(self):
        # Criterion 6's configuration half: the numbers are columns on the
        # weights row the campaign was opened under, not constants here.
        connection = Recorder(
            session=dict(Recorder().session, capsule_bytes=4096, capsule_tokens=512)
        )
        self.choice(connection)
        limits = self.launcher.planned.capsule.limits

        self.assertEqual((4096, 512), (limits.byte_limit, limits.token_limit))
        self.assertLessEqual(
            self.launcher.planned.capsule.document_bytes, limits.byte_ceiling
        )

    def test_a_capsule_that_cannot_fit_its_ceiling_is_refused_and_not_sent(self):
        # The other half: refused, and the pass carries on without a choice --
        # which is the same place every other failure on this path leaves it.
        connection = Recorder(
            session=dict(Recorder().session, capsule_bytes=64, capsule_tokens=16)
        )
        facts = self.choice(connection)

        self.assertEqual([], self.launcher.choices)
        self.assertEqual("unavailable", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual(execution.INVALID_CONFIGURATION, self.ledger.violations[0].code)
        self.assertIn("could not be given what it inherits", self.ledger.violations[0].detail)

    def test_a_capsule_the_database_refused_leaves_the_pass_where_it_was(self):
        connection = Recorder(
            raises={execution.capsule_module.WORK: database_error("permission denied")}
        )
        facts = self.choice(connection)

        self.assertEqual([], self.launcher.choices)
        self.assertEqual("unavailable", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual(1, len(self.ledger.violations))

    def test_the_objective_promises_the_number_of_entries_the_tool_can_serve(self):
        # `get_slate` is served from the capsule's slate section, and the fit
        # may have dropped entries from it. An objective counting the offer
        # would promise a model Tasks it is then not shown.
        connection = Recorder(
            slate=12,
            session=dict(Recorder().session, capsule_bytes=2600, capsule_tokens=650),
        )
        self.choice(connection)
        served = self.launcher.planned.capsule.slate()

        self.assertLess(len(served), 12)
        self.assertIn(f"get_slate for the {len(served)} Task(s)",
                      self.launcher.planned.objective)

    def test_a_capsule_left_with_no_entry_to_choose_from_is_refused(self):
        # The quiet way to lose a choice: a capsule that fits its ceiling by
        # dropping the whole Slate, and a session asked to pick from a list it
        # cannot be shown. The runtime's own walk claims instead.
        connection = Recorder(
            slate=3,
            session=dict(Recorder().session, capsule_bytes=900, capsule_tokens=225),
        )
        facts = self.choice(connection)

        self.assertEqual([], self.launcher.choices)
        self.assertEqual("unavailable", facts["choice"]["outcome"])
        self.assertEqual("T1", facts["task"]["label"])
        self.assertIn("was left no Slate entry", self.ledger.violations[0].detail)

    def test_a_pass_that_spent_the_campaign_closes_it_before_it_ends(self):
        # Criterion 2 does not say "at the start of the next pass". A session
        # that reached a ceiling on the last pass a supervisor ever runs would
        # otherwise stay open with no Event saying it ended.
        connection = Recorder(
            closed={"session": "OS1", "generation": 1, "reason": "turns"}
        )
        self.choice(connection)
        holds = self.stated("rotation")

        self.assertEqual([(),], [parameters for parameters in connection.sent(execution.ROTATE)])
        self.assertEqual(1, len(holds))
        self.assertIn("OS1 reached its turns ceiling", holds[0].detail)

    def test_a_spent_campaign_says_where_its_successor_comes_from(self):
        # Ticket 161's fourth criterion, which is a question rather than a bug:
        # a session closed on `tokens` rotates on the next pass, not inside the
        # one that closed it and not when an operator says so. `rk2hunt17` has
        # one row at generation 1 with `rotated_from` null because `hunt.sh`
        # stopped on `nothing_to_execute` and never ran that next pass, which is
        # the stop reason's fault and not the rotation's.
        connection = Recorder(
            closed={"session": "OS1", "generation": 1, "reason": "tokens"}
        )
        self.choice(connection)

        self.assertIn(
            "the next pass opens the successor", self.stated("rotation")[0].detail
        )

    def test_a_rotation_that_could_not_be_written_does_not_fail_the_pass(self):
        # The pass is over and everything it did is committed. The next pass's
        # open asks the same question, so the answer is reported and dropped.
        connection = Recorder(
            raises={execution.ROTATE: database_error("permission denied")}
        )
        facts = self.choice(connection)

        self.assertEqual("T1", facts["task"]["label"])
        self.assertEqual([False], [stated.ok for stated in self.stated("rotation")])
        self.assertIn("could not be rotated", self.ledger.violations[0].detail)


class PlaybookSelectionTest(unittest.TestCase):
    """The Playbooks an attempt runs under: chosen, recorded, and handed over.

    Stories 173-175 and Decision 15. `select_playbooks` and
    `record_playbook_selection` were built for this and had no caller, so a
    Task ran under nothing and every verdict `rk playbook evaluate` keyed on
    `playbook_sha256` was a verdict about the harness.
    """

    def test_the_selection_is_recorded_against_the_task_and_its_subject(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertEqual([(TASK, SUBJECT)], connection.sent(execution.RECORD_SELECTION))

    def test_a_stale_stable_playbook_is_demoted_before_the_selection_reads_it(self):
        # Story 182. `demote_playbooks` had no caller, so a Playbook whose own
        # test had started failing stayed `stable` and stayed selectable: the
        # status is the whole of what says the catalogue stands behind it.
        # Running it in the same transaction as the selection is what makes the
        # two agree -- a demotion that committed after the pick would have
        # picked what it then withdrew.
        connection = Recorder(demoted=2)
        with compiled():
            ledger, _ = attempt(connection)

        self.assertLess(
            connection.statements.index(execution.DEMOTE),
            connection.statements.index(execution.RECORD_SELECTION),
        )
        self.assertIn(
            "2 stable Playbook(s) were demoted",
            " ".join(item.detail for item in ledger.assertions),
        )

    def test_a_retry_does_not_demote_again_because_it_selects_nothing(self):
        # The selection is recorded once per Task. A retry reads the rows the
        # first attempt froze, so there is no pick for a demotion to precede.
        connection = Recorder(recorded=1)
        with compiled():
            attempt(connection)

        self.assertEqual([], connection.sent(execution.DEMOTE))

    def test_a_subject_the_corpus_missed_by_one_fact_is_named_in_the_ledger(self):
        # Ticket 164. "Nothing in the corpus is about this subject" was true of
        # a Drupal login page and a catalogue holding a CMS Playbook, and an
        # operator could not tell that from a catalogue that really had nothing
        # to say. The near miss is what tells them apart.
        connection = Recorder(
            selections=[],
            near_misses=[("playbooks/cms/playbook.md", "authenticated_endpoint")],
        )
        with compiled():
            ledger, _ = attempt(connection)

        said = " ".join(item.detail for item in ledger.assertions)
        self.assertIn("nothing in the corpus is about this subject", said)
        self.assertIn(
            "one fact short: playbooks/cms/playbook.md wants authenticated_endpoint",
            said,
        )

    def test_a_subject_the_corpus_really_has_nothing_for_says_only_that(self):
        # The other half, and the reason the near miss is a suffix rather than
        # a replacement: a subject nothing is one fact away from gets the
        # sentence it always got, with nothing appended to read into.
        connection = Recorder(selections=[])
        with compiled():
            ledger, _ = attempt(connection)

        said = [
            item.detail for item in ledger.assertions if "runs under" in item.detail
        ]
        self.assertEqual(
            ["T1 runs under no Playbook: nothing in the corpus is about this subject"],
            said,
        )

    def test_the_near_miss_is_not_asked_for_when_a_playbook_was_kept(self):
        # It is a diagnostic for the empty answer. A run with a strategy has
        # its strategy in the ledger already, and asking anyway would put a
        # list of what it nearly ran beside what it is running.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertEqual([], connection.sent(execution.NEAR_MISSES))

    def test_the_choice_is_made_before_the_capability_the_child_would_spend(self):
        # The migration's own title: a Playbook is chosen before the model
        # reads it. Choosing after the Tool run is open would be an
        # authorisation minted for a run whose strategy was not yet decided.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertLess(
            connection.statements.index(execution.RECORD_SELECTION),
            connection.statements.index(execution.OPEN_TOOL_RUN),
        )

    def test_the_child_is_handed_the_projection_of_what_was_kept(self):
        launcher = Launcher()
        with compiled():
            attempt(Recorder(), launcher)
        self.assertIn(SELECTED_PLAYBOOK.projection.text(), launcher.only.objective)

    def test_what_was_kept_is_reported_with_the_digests_it_was_frozen_at(self):
        with compiled():
            _, facts = attempt(Recorder())
        self.assertEqual(
            [
                {
                    "path": SELECTED_PLAYBOOK.path,
                    "sha256": SELECTED_PLAYBOOK.sha256,
                    "version": SELECTED_PLAYBOOK.version,
                }
            ],
            facts["playbooks"],
        )

    def test_a_retry_runs_under_what_the_first_attempt_was_given(self):
        # `playbook_selections` is unique on (task_id, playbook_id), so a
        # second record would be refused by the constraint. The rows are read
        # back either way: what the first attempt froze is what this one runs
        # under, whatever the catalogue has done since.
        launcher = Launcher()
        connection = Recorder(recorded=3)
        with compiled():
            attempt(connection, launcher)
        self.assertNotIn(execution.RECORD_SELECTION, connection.statements)
        self.assertIn(SELECTED_PLAYBOOK.projection.text(), launcher.only.objective)

    def test_a_subject_no_playbook_is_about_still_gets_its_attempt(self):
        # Keeping nothing is an answer. The corpus has no strategy for this
        # subject, which is a hunt under the Task's own instructions and not a
        # failure to report.
        launcher = Launcher()
        connection = Recorder(selections=[])
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertEqual([], ledger.violations)
        self.assertEqual([], facts["playbooks"])
        self.assertNotIn("Playbook", launcher.only.objective)

    def test_a_playbook_this_installation_does_not_carry_stops_the_attempt(self):
        launcher = Launcher()
        connection = Recorder(
            selections=[("playbooks/nowhere/playbook.md", "0" * 64, "1" * 64)]
        )
        with compiled():
            ledger, _ = attempt(connection, launcher)
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.assertEqual(execution.INTEGRITY_FAILED, ledger.violations[0].code)
        self.assertEqual("corpus", ledger.violations[0].source)

    def test_a_document_that_moved_past_the_digest_it_froze_stops_the_attempt(self):
        # The path is one this installation carries and the bytes behind it are
        # not the bytes the selection recorded. Handing the current text over
        # would make `playbook_sha256` name a document the model never read.
        connection = Recorder(
            selections=[(SELECTED_PLAYBOOK.path, "0" * 64, SELECTED_PLAYBOOK.version)]
        )
        with compiled():
            ledger, _ = attempt(connection)
        self.assertEqual(execution.INTEGRITY_FAILED, ledger.violations[0].code)

    def test_a_projection_that_moved_past_its_version_stops_the_attempt(self):
        # The other digest, and the one that decides what was read: the
        # document can be identical and the projection different only if the
        # two are computed from different bytes, which is corpus rot.
        connection = Recorder(
            selections=[(SELECTED_PLAYBOOK.path, SELECTED_PLAYBOOK.sha256, "1" * 64)]
        )
        with compiled():
            ledger, _ = attempt(connection)
        self.assertEqual(execution.INTEGRITY_FAILED, ledger.violations[0].code)

    def test_a_selection_the_database_refused_stops_the_attempt(self):
        connection = Recorder(
            raises={execution.RECORD_SELECTION: database_error("no role executes that kind")}
        )
        with compiled():
            ledger, _ = attempt(connection)
        self.assertEqual(execution.INVALID_CONFIGURATION, ledger.violations[0].code)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)


class PlaybookOutcomeTest(unittest.TestCase):
    """The far end of the funnel: what a selection turned out to have been worth.

    Ticket 121. `playbook_selections.outcome` has had three values and a default
    of `running` since 027 and no writer at all, so `exhausted` -- the only
    memory the selection has, and the reason `playbook_candidates` drops a
    Playbook it has already run against a subject -- was a word the schema could
    describe and nothing could reach. `mark_stale_selections` was in the same
    state one column over: the sweep existed and nobody ran it.
    """

    def details(self, ledger: Ledger) -> str:
        return " ".join(item.detail for item in ledger.assertions)

    def test_the_staleness_sweep_runs_before_anything_is_offered(self):
        # 027 evaluates staleness at selection and never again inside a run, so
        # the sweep has to have happened by the time this pass picks: a stamp
        # written afterwards would describe a Playbook this pass had just
        # chosen under.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertLess(
            connection.position(execution.SWEEP_STALE),
            connection.position(execution.OFFER),
        )

    def test_a_pass_that_claims_nothing_still_sweeps(self):
        # The sweep is over what other passes left in flight, so it is not the
        # claim's to depend on. A machine whose slate is empty is exactly the
        # one with nothing else to do about a catalogue that moved.
        connection = Recorder(slate=0)
        with compiled():
            _, facts = attempt(connection)
        self.assertEqual({"marked": 0}, facts["staleness"])
        self.assertNotIn(execution.CLAIM, connection.statements)

    def test_a_playbook_that_expired_under_a_live_mission_is_said_out_loud(self):
        connection = Recorder(marked=2)
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual({"marked": 2}, facts["staleness"])
        self.assertIn(
            "2 live selection(s) had their Playbook expire under them",
            self.details(ledger),
        )

    def test_a_sweep_the_database_refused_does_not_stop_the_pass(self):
        # Housekeeping over somebody else's rows, like the reconciliation above
        # it: nothing downstream acts on `went_stale_at`, so a sweep that could
        # not be written is a report an operator loses and not work this pass
        # has to abandon.
        connection = Recorder(
            raises={execution.SWEEP_STALE: database_error("could not update")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["staleness"])
        self.assertEqual(execution.INTEGRITY_FAILED, ledger.violations[0].code)
        self.assertIn(execution.RECORD_SELECTION, connection.statements)

    def test_the_selection_is_settled_after_the_attempt_has_been_closed(self):
        # `finish_task_attempt` is what decides whether the Task is done,
        # abandoned or back on the Slate, and the settlement turns on that word.
        # Asking before it, or inside its transaction, would be asking a
        # question whose answer was still being written.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertLess(
            connection.closing(), connection.position(execution.SETTLE_SELECTION)
        )

    def test_the_settlement_is_told_the_task_and_nothing_else(self):
        # The Program, the subject and the Playbook's classes are all on rows
        # the Task already names. A caller that could name them could settle a
        # selection belonging to a run it was not closing.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertEqual([(TASK,)], connection.sent(execution.SETTLE_SELECTION))

    def test_what_is_exhausted_on_this_subject_is_reported(self):
        connection = Recorder(
            settlement={
                "task": "T1",
                "task_status": "abandoned",
                "settled": True,
                "produced": 0,
                "exhausted": 3,
            }
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual(3, facts["selections"]["exhausted"])
        self.assertIn(
            "0 Playbook(s) produced and 3 are exhausted on this subject",
            self.details(ledger),
        )

    def test_a_task_going_back_onto_the_slate_leaves_its_selection_open(self):
        # The retry runs under the rows this attempt recorded -- the selection
        # is unique on (task, playbook), so there is no second set to record --
        # and a Playbook retired here would be retired in front of the run that
        # was about to use it properly.
        connection = Recorder(
            settlement={
                "task": "T1",
                "task_status": "pending",
                "settled": False,
                "produced": 0,
                "exhausted": 0,
            }
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIs(False, facts["selections"]["settled"])
        self.assertIn("may be run again", self.details(ledger))

    def test_an_attempt_that_never_started_still_settles_what_it_held(self):
        # In the closing `finally` beside the attempt's own, because the
        # outcome is a fact about the Task rather than about how far this
        # runtime got with it. The verb declines to write for a Task still on
        # the Slate, which is what this one will be.
        connection = Recorder(started=(started_row(subject_type="hypothesis", url=None),))
        with compiled():
            attempt(connection)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)
        self.assertEqual([(TASK,)], connection.sent(execution.SETTLE_SELECTION))

    def test_a_settlement_the_database_refused_leaves_the_closing_alone(self):
        # Its own transaction, after the closing, for exactly this: a
        # settlement that could not be written must not roll back the one call
        # that closed the runs, released the Leases and settled the Task.
        connection = Recorder(
            raises={execution.SETTLE_SELECTION: database_error("no such task")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["selections"])
        self.assertEqual(1, len(connection.finished()))
        self.assertEqual(execution.INTEGRITY_FAILED, ledger.violations[0].code)
        self.assertEqual("database", ledger.violations[0].source)


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
            {
                "url": "https://app.example.com/login",
                "method": "GET",
                "identity_slot": "",
                # A body is request framing rather than a mutating effect. The
                # selected Playbook is read-only but may still need one for a
                # reading such as a JSON filter or GraphQL selection.
                "body_allowed": True,
            },
            json.loads(args),
        )

    def test_the_tool_run_carries_the_identity_the_task_selected(self):
        """Ticket 131, on the wire.

        The Task's selection is what the door is told the run acts as, and the
        door keys everything on it: `resolve_egress_identity` refuses a named
        slot with no live Lease, and `net_borrowed_identity` escalates any
        non-empty one. So a selection that never reached the args would be a
        run acting as one Identity and declaring another.
        """
        connection = Recorder(
            started=(started_row(identity_slot_name="tenant-a", identity_class="user"),)
        )
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]
        self.assertEqual("tenant-a", json.loads(args)["identity_slot"])

    def test_an_anonymous_selection_reaches_the_door_as_no_identity_at_all(self):
        # `_anonymous` is a row, not a slot the door can open: naming it here
        # would send every unauthenticated hunt through the borrowed-account
        # escalation and leave it waiting for an approval nobody owes.
        connection = Recorder(
            started=(
                started_row(identity_slot_name="_anonymous", identity_class="anonymous"),
            )
        )
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]
        self.assertEqual("", json.loads(args)["identity_slot"])

    def test_an_attempt_is_opened_body_bearing_when_a_playbook_mutates(self):
        """Ticket 96's first rule, at the moment it is decided.

        Permission for a body is not a property of the call, which arrives after
        this row is written and is chosen by a model. It is a property of the
        work the Task was planned as, and the only statement of that in this
        system is `bb:effects` on the Playbooks selected for it. So it is
        computed here, written beside the url and the method, and read back by
        the authorizer the door calls and by the digest a human answers.
        """
        mutating = playbook.PLAYBOOKS["file-upload"]
        connection = Recorder(
            selections=[(mutating.path, mutating.sha256, mutating.version)]
        )
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]

        self.assertEqual("mutates_object", mutating.effects)
        self.assertIs(True, json.loads(args)["body_allowed"])

    def test_a_read_only_playbook_may_send_a_reading_with_a_body(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]

        self.assertEqual("read_only", SELECTED_PLAYBOOK.effects)
        self.assertIs(True, json.loads(args)["body_allowed"])

    def test_one_mutating_playbook_among_readings_opens_the_attempt_for_a_body(self):
        # The maximum and not the minimum. A Task is one attempt with one
        # capability, and a selection that contains any writing is a Task the
        # child may write on: a body refused because a reading was selected
        # alongside would refuse work the plan already approved.
        mutating = playbook.PLAYBOOKS["authentication"]
        connection = Recorder(
            selections=[
                (SELECTED_PLAYBOOK.path, SELECTED_PLAYBOOK.sha256, SELECTED_PLAYBOOK.version),
                (mutating.path, mutating.sha256, mutating.version),
            ]
        )
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]

        self.assertEqual("read_only", SELECTED_PLAYBOOK.effects)
        self.assertEqual("mutates_account", mutating.effects)
        self.assertIs(True, json.loads(args)["body_allowed"])

    def test_an_attempt_with_no_playbook_at_all_is_not_opened_for_a_body(self):
        # Silence on a permission is not a grant. A Task that selected nothing is
        # a Task nothing said may write, and the honest reading of that is no.
        connection = Recorder(selections=[])
        with compiled():
            attempt(connection)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]

        self.assertIs(False, json.loads(args)["body_allowed"])

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
        # Ticket 136: and who it is spending as, which is the Task's own
        # selection rather than a second decision taken here. Empty is the
        # anonymous run this fixture describes.
        self.assertEqual("", door.identity)

    def test_the_child_is_told_which_identity_its_capability_is_spent_as(self):
        # The other half of the same value: what the Tool run's args say and
        # what the block hands the child are one selection read once, so an
        # answer naming an Identity and a door injecting another is not a state
        # this runtime can produce.
        launcher = Launcher()
        connection = Recorder(
            started=(started_row(identity_slot_name="tenant-a", identity_class="user"),)
        )
        with compiled():
            attempt(connection, launcher)
        *_, args = connection.sent(execution.OPEN_TOOL_RUN)[0]
        door = launcher.only.egress
        assert door is not None

        self.assertEqual("tenant-a", door.identity)
        self.assertEqual("tenant-a", json.loads(args)["identity_slot"])

    def test_a_machine_naming_a_tool_image_and_a_store_can_answer_a_tool_call(self):
        # PH2-87. Both parts, because a run whose output could not be filed is a
        # run that leaves no evidence -- and the settings rather than this
        # connection, because the heartbeat is beating on this one.
        connection = Recorder()
        connection.settings = STATE
        image = isolation.ToolContainer(image="rk2-tool")
        launcher = Launcher()
        with compiled():
            attempt(connection, launcher, tools=image, artifacts=Path("/store"))

        tooling = launcher.only.tooling
        assert tooling is not None
        self.assertIs(image, tooling.container)
        self.assertEqual(Path("/store"), tooling.root)
        self.assertIs(STATE, tooling.runtime)

    def test_a_machine_naming_only_one_of_them_still_reaches_the_runtime(self):
        """The channel is the database, not the image.

        Until 2026-08-22 a machine naming no tool image was given no `Tooling`
        at all, so `propose_test`, `propose_finding` and `mint_callback` were
        answered `no_tooling` by a supervisor that was never built. Four live
        hunts filed no Test for that reason and nothing recorded it.
        """
        launcher = Launcher()
        with compiled():
            attempt(Recorder(), launcher, artifacts=Path("/store"))

        tooling = launcher.only.tooling
        assert tooling is not None
        self.assertIsNone(tooling.container)
        self.assertIsNotNone(tooling.runtime)

    def test_a_supervisor_with_no_image_refuses_the_two_verbs_that_need_one(self):
        """And only those two: the other three write rows."""
        tools = agent._Tools(
            agent.Tooling(runtime=STATE), PROGRAM, RUN
        )
        for verb in (roster.RUN_TOOL, roster.RUN_SKILL_SCRIPT):
            with self.subTest(verb=verb):
                answered = tools({"verb": verb})
                self.assertFalse(answered["served"])
                self.assertEqual(agent.NO_TOOL_IMAGE, answered["reason"])

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
        # Ticket 177. Recorded, and not a violation. A child reaching for a verb
        # its Tool run does not carry is the boundary working; calling it an
        # invalid configuration ended the pass, and `evaluation._repeat` then
        # threw away the whole repeat -- including the variant that had already
        # finished. A lane whose door mints no capability at all still fails, one
        # call earlier, in `_authorize`.
        connection = Recorder(receipt=("RC1", "blocked", None, "required header missing"))
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([(TOOL_RUN, "denied")], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertEqual([], ledger.violations)
        self.assertEqual("blocked", facts["receipt"]["decision"])
        self.assertIn(
            "the door refused the child's request: RC1 is blocked",
            [item.detail for item in ledger.assertions if item.ok],
        )

    def test_a_target_that_did_not_answer_closes_the_tool_run_as_error(self):
        # `denied` is the word for a request the door turned away. A run whose
        # every block is a target fault claims a refusal nobody made, which is
        # what arm (i) of `check_receipt_integrity` refuses -- and that gate runs
        # in `rk run` before anything is written, so one unreachable host stopped
        # every later run of the campaign. Measured on the here engagement:
        # TR25 and TR26, both `GET https://spot.account.here.com/`.
        for reason in ("target unreachable", "target unresolved"):
            with self.subTest(reason=reason):
                connection = Recorder(receipt=[("RC1", "blocked", None, reason)])
                with compiled():
                    ledger, facts = attempt(connection)
                self.assertEqual(
                    [(TOOL_RUN, "error")], connection.sent(proxy.CLOSE_TOOL_RUN)
                )
                self.assertEqual([], ledger.violations)
                self.assertEqual("blocked", facts["receipt"]["decision"])
                self.assertIn(
                    f"the target did not answer: RC1 is blocked for {reason}",
                    [item.detail for item in ledger.assertions if item.ok],
                )

    def test_a_refusal_under_a_target_fault_still_closes_the_tool_run_as_denied(self):
        # The case arm (i)'s own comment preserves: one run may make several
        # requests, and a run that really was refused and separately met an
        # unreachable target closed as denied for a reason that is on the record.
        # Newest first, so the run ended on the fault and was refused before it.
        connection = Recorder(
            receipt=[
                ("RC2", "blocked", None, "target unreachable"),
                ("RC1", "blocked", None, "required header missing"),
            ]
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertEqual([(TOOL_RUN, "denied")], connection.sent(proxy.CLOSE_TOOL_RUN))
        self.assertEqual([], ledger.violations)
        self.assertEqual("RC2", facts["receipt"]["label"])

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

    def test_the_verbs_the_child_reached_for_are_recorded_beside_its_tokens(self):
        """`AgentRunResult.as_dict` has no caller, so nothing read either list.

        A run served a tool and never calling it looked identical to a run
        calling it and being denied. Two live hunts were spent telling those
        apart by hand.
        """
        connection = Recorder()
        answer = result(
            tools_served=("mcp__rk2__http_request", "mcp__rk2__http_request"),
            denials=({"tool": "mcp__rk2__propose_test", "reason": "not served"},),
        )
        with compiled():
            _, facts = attempt(connection, Launcher(answer=answer))
        self.assertEqual(["mcp__rk2__http_request"], facts["agent_run"]["tools_called"])
        self.assertEqual(
            [{"tool": "mcp__rk2__propose_test", "reason": "not served"}],
            facts["agent_run"]["denials"],
        )


class PerformTest(unittest.TestCase):
    """Ticket 152: the one kind the runtime walks itself.

    A `perform` Task carries a Test that a hunt authored in an earlier pass.
    Nothing about it is a dispatch: there is no packet, no Playbook, no
    capability minted by this module and no child, because `replay.run` mints
    its own inside the transaction that opens the Tool run. What this case
    fixes is the seam -- that the claim reaches the performer at all, that it
    reaches it with the right two names, and that what comes back settles the
    attempt the way the Test run says it should.

    `replay.run` itself is not under test here. It has been the performer since
    ticket 35 and `tests.test_database` covers the verbs it calls; the defect
    ticket 152 names is that nothing ever called it.
    """

    #: What a replay that reached a verdict answers with. `test_run` present is
    #: the whole of the question this module asks of it: the row is written by
    #: `close_test_replay` inside the transaction that settles the claim, so a
    #: replay that opened and died has a Tool run and no Test run.
    SETTLED = {"test_run": {"label": "TR1", "outcome": "supports"}}

    #: The door as the runtime sees it, which is not how a child sees it.
    #: Ticket 153: `BOUNDARY.proxy_url` is a container name on the Agent network
    #: and this process is not on that network, so the two are different strings
    #: for one door and the performer is given this one.
    DOOR = "http://127.0.0.1:18080"

    def performing(self, answer=None, **overrides):
        """One attempt on a `perform` Task, with the replay stubbed out."""
        connection = Recorder(
            started=(
                started_row(
                    kind="perform",
                    role="performer",
                    test_label="TST1",
                    hypothesis_label="H1",
                    **overrides,
                ),
            )
        )
        launcher = Launcher()
        performed = outcome_module.Report(
            "test replay", facts=dict(self.SETTLED if answer is None else answer)
        )
        with compiled():
            with mock.patch.object(
                execution.replay_module, "run", return_value=performed
            ) as run:
                ledger, facts = attempt(
                    connection,
                    launcher,
                    configuration=Path("/tmp/program.toml"),
                    proxy_url=self.DOOR,
                )
        return connection, launcher, ledger, facts, run

    def test_the_runtime_performs_it_and_starts_no_child(self):
        connection, launcher, ledger, facts, run = self.performing()

        self.assertEqual(1, run.call_count)
        self.assertEqual([], launcher.requests)
        self.assertEqual([], ledger.violations)
        # No capability either. The replay opens its own Tool run and mints its
        # own, so one minted here would be an authorisation nobody spends.
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)

    def test_the_performer_is_given_the_run_it_is_attributed_to_and_the_test(self):
        # The two names ticket 152 exists to supply. The Agent run is the one
        # the claim just opened and has not ended, which is the condition
        # `rk2_replay_subject` refuses an operator's replay for.
        _, _, _, _, run = self.performing()
        _, configuration = run.call_args.args

        self.assertEqual(Path("/tmp/program.toml"), configuration)
        self.assertEqual("AR7", run.call_args.kwargs["agent_run"])
        self.assertEqual("TST1", run.call_args.kwargs["test"])

    def test_a_replay_that_filed_a_test_run_closes_the_attempt_as_completed(self):
        connection, _, _, facts, _ = self.performing()

        self.assertEqual("completed", facts["agent_run"]["stop_reason"])
        self.assertEqual(1, len(connection.finished()))

    def test_a_replay_that_filed_nothing_closes_the_attempt_as_error(self):
        # The Tool run exists and the Test run does not, which is a replay that
        # opened and died. The attempt is spent and the Task is not done.
        _, _, _, facts, _ = self.performing(answer={"test_run": None})

        self.assertEqual("error", facts["agent_run"]["stop_reason"])

    def test_what_the_replay_reported_is_carried_into_the_pass(self):
        _, _, _, facts, _ = self.performing()

        self.assertEqual("TR1", facts["replay"]["test_run"]["label"])

    def test_a_refused_replay_carries_its_violations_into_the_pass(self):
        connection = Recorder(
            started=(started_row(kind="perform", role="performer", test_label="TST1"),)
        )
        refused = outcome_module.Report(
            "test replay",
            violations=(
                outcome_module.Violation(
                    code="invalid_configuration",
                    source="argument:--test",
                    detail="the registry refused this replay",
                ),
            ),
            facts={"test_run": None},
        )
        with compiled():
            with mock.patch.object(
                execution.replay_module, "run", return_value=refused
            ):
                ledger, facts = attempt(
                    connection,
                    Launcher(),
                    configuration=Path("/tmp/program.toml"),
                    proxy_url=self.DOOR,
                )

        self.assertEqual(
            ["the registry refused this replay"],
            [violation.detail for violation in ledger.violations],
        )
        self.assertEqual("error", facts["agent_run"]["stop_reason"])

    #: What `_conclude` writes for a Test that ran and could not reach its
    #: conclusion: the failed `run` assertion and the violation behind it, both
    #: carrying one sentence. Quoted from canary nine, `attack-surface` against
    #: `artifact-exposure-pair` in `rk2grade9` on 2026-08-25.
    WITHHELD = (
        "TST1 holds over 3 action(s); the claim is inconclusive, because playbook "
        "playbooks/attack-surface/playbook.md requires 1 x "
        "(role=control, kind=response_differential) for supported, found 0"
    )

    def withholding(self, test_run):
        """One attempt whose replay reported the verdict `_conclude` fails on."""
        connection = Recorder(
            started=(started_row(kind="perform", role="performer", test_label="TST1"),)
        )
        withheld = outcome_module.Report(
            "test replay",
            assertions=(
                outcome_module.Assertion(name="run", ok=False, detail=self.WITHHELD),
            ),
            violations=(
                outcome_module.Violation(
                    code="invalid_configuration",
                    source="test_run",
                    detail=self.WITHHELD,
                ),
            ),
            facts={"test_run": test_run},
        )
        with compiled():
            with mock.patch.object(
                execution.replay_module, "run", return_value=withheld
            ):
                return attempt(
                    connection,
                    Launcher(),
                    configuration=Path("/tmp/program.toml"),
                    proxy_url=self.DOOR,
                )

    def test_a_settled_test_that_reached_no_conclusion_does_not_refuse_the_pass(self):
        """Ticket 183, measured on canary nine.

        `_conclude` spends `INVALID_CONFIGURATION` on a Test that settled
        `inconclusive` and on a conclusion the epistemic machine withheld, which
        is what `rk test replay` owes an operator who has to run it again. Here
        the Test run is the Task's ending, so the same sentence is a
        measurement. Carried as a violation it ends the pass loop and
        `evaluation._repeat` discards the whole repeat, every variant of it --
        ticket 177's fault, one layer up.
        """
        ledger, facts = self.withholding({"label": "TR1", "outcome": "holds"})

        self.assertEqual([], ledger.violations)
        self.assertEqual("completed", facts["agent_run"]["stop_reason"])

    def test_the_verdict_it_could_not_reach_is_still_in_the_pass(self):
        # Demoted, not dropped. The sentence naming what the Test would have
        # needed is the one document worth keeping, so it is held under the name
        # `_conclude` gave it and stays whole on `facts["replay"]`, where the
        # replay's own report keeps it as the violation it is.
        ledger, facts = self.withholding({"label": "TR1", "outcome": "holds"})
        held = [item for item in ledger.assertions if item.name == "run"]

        self.assertEqual([True], [item.ok for item in held])
        self.assertEqual([self.WITHHELD], [item.detail for item in held])
        self.assertEqual(
            [self.WITHHELD],
            [violation["detail"] for violation in facts["replay"]["violations"]],
        )

    def test_a_replay_that_died_before_settling_keeps_every_refusal_it_raised(self):
        # The other writer of a `test_run` violation is `_abandon`, reached when
        # `close_test_replay` was itself refused -- and that transaction rolls
        # back, so there is no Test run. Nothing about that is a measurement.
        ledger, facts = self.withholding(None)

        self.assertEqual(
            [self.WITHHELD], [violation.detail for violation in ledger.violations]
        )
        self.assertEqual("error", facts["agent_run"]["stop_reason"])

    def test_the_capability_is_sent_to_this_machine_and_not_to_the_agent_network(self):
        """Ticket 153, measured live before it was fixed.

        The first lap that ever claimed a `perform` Task chose T6, opened AR10
        and refused at the replay's first statement: `rk2hunt-door is not a
        loopback address`. `proxy.endpoint` was right -- the capability rides
        one hop in the clear -- and the boundary's URL is the child's, a
        container name on a network the runtime is not attached to.
        """
        _, _, _, _, run = self.performing()

        self.assertEqual(self.DOOR, run.call_args.kwargs["proxy_url"])
        self.assertNotEqual(BOUNDARY.proxy_url, run.call_args.kwargs["proxy_url"])

    def test_a_machine_naming_no_door_of_its_own_refuses_by_name(self):
        # The second input the performer needs that a dispatch does not. A
        # dispatch hands the child's URL to the child and never spends a
        # capability itself, so a machine can run every other kind without this.
        connection = Recorder(
            started=(started_row(kind="perform", role="performer", test_label="TST1"),)
        )
        with compiled():
            with mock.patch.object(execution.replay_module, "run") as run:
                ledger, facts = attempt(
                    connection, Launcher(), configuration=Path("/tmp/program.toml")
                )

        self.assertEqual(0, run.call_count)
        self.assertEqual(
            ["environment:RK_PROXY_URL"], [one.source for one in ledger.violations]
        )
        self.assertEqual("error", facts["agent_run"]["stop_reason"])
        self.assertEqual(1, len(connection.finished()))

    def test_a_machine_naming_no_configuration_refuses_by_name(self):
        # The one input the performer needs that a dispatch does not, so the
        # refusal says which: a machine that offers, claims and runs every other
        # kind cannot resolve a Program from a file it was never given.
        connection = Recorder(
            started=(started_row(kind="perform", role="performer", test_label="TST1"),)
        )
        with compiled():
            with mock.patch.object(execution.replay_module, "run") as run:
                ledger, facts = attempt(connection, Launcher())

        self.assertEqual(0, run.call_count)
        self.assertEqual(["argument:--config"], [one.source for one in ledger.violations])
        self.assertEqual(1, len(connection.finished()))

    def test_a_perform_task_naming_no_test_refuses_by_name(self):
        connection = Recorder(
            started=(started_row(kind="perform", role="performer", test_label=None),)
        )
        with compiled():
            with mock.patch.object(execution.replay_module, "run") as run:
                ledger, _ = attempt(
                    connection, Launcher(), configuration=Path("/tmp/program.toml")
                )

        self.assertEqual(0, run.call_count)
        self.assertEqual(["database"], [one.source for one in ledger.violations])

    def test_the_kind_is_the_one_the_roster_gives_the_performer(self):
        # Two statements of one word, held equal: the branch keys on it and the
        # roster maps it, and a rename in one is a Task dispatched to a child.
        self.assertEqual("performer", roster.ROLE_FOR_KIND[execution.PERFORM])
        self.assertTrue(roster.ROLES["performer"].rendered)


class RefusalTest(unittest.TestCase):
    """Every way the attempt stops, and the closing that runs regardless."""

    def closed(self, connection: Recorder) -> None:
        self.assertEqual(1, len(connection.finished()), connection.statements)

    def retired(self, connection: Recorder, ledger) -> str:
        """Ticket 143. The Task ended and the pass did not, said as one check.

        Three refusals share this: the runtime cannot dispatch the Task, so it
        ends that Task rather than the pass. No violation, because nothing went
        wrong that an operator can mend -- the pass goes on to the next Task,
        and this one is gone from the ranking instead of sitting at the top of
        it refusing every later pass in the same words.
        """
        self.assertEqual([], ledger.violations)
        [sent] = connection.sent(execution.RETIRE)
        self.assertEqual(TASK, sent[0])
        self.closed(connection)
        return sent[1]

    def test_a_subject_with_no_address_ends_that_task_and_not_the_pass(self):
        connection = Recorder(started=(started_row(subject_type="hypothesis", url=None),))
        launcher = Launcher()
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertIn("carries no address", self.retired(connection, ledger))
        self.assertIsNone(facts["target"])
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)

    def test_a_task_that_cannot_be_retired_is_the_one_refusal_left(self):
        # The only way this slice still fails on an undispatchable Task: the
        # end could not be written either, which is a database this pass cannot
        # trust for the next Task either.
        connection = Recorder(
            started=(started_row(subject_type="hypothesis", url=None),),
            raises={execution.RETIRE: database_error("gone")},
        )
        with compiled():
            ledger, _ = attempt(connection, Launcher())
        [violation] = ledger.violations
        self.assertEqual("database", violation.source)
        self.assertIn("could not be retired", violation.detail)
        self.closed(connection)

    def test_a_role_this_runtime_cannot_start_ends_the_task_before_the_packet(self):
        # A `report` Task claimed as the role the roster gives that kind: the
        # refusal under test is about what this runtime can start, not about a
        # role and a kind that do not go together.
        connection = Recorder(started=(started_row(role="reporter", kind="report"),))
        launcher = Launcher()
        with compiled():
            ledger, _ = attempt(connection, launcher)
        self.assertIn("cannot start as an isolated child", self.retired(connection, ledger))
        self.assertEqual([], launcher.requests)

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
        self.assertIn("holds no net.request", self.retired(connection, ledger))
        self.assertEqual([], launcher.requests)
        self.assertNotIn(execution.OPEN_TOOL_RUN, connection.statements)

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
        # Ticket 206: recorded, and not as a violation. A pass that filed a
        # question did what the gate told it to, so a refused pass here made
        # `rk run` exit 3 for a working harness -- and a driver loop counting
        # exits stopped the campaign after three of them.
        self.assertEqual([], ledger.violations)
        self.assertIn(
            "for a human to answer",
            [one.detail for one in ledger.assertions if one.name == "authorization"][-1],
        )
        self.assertEqual([], launcher.requests)
        self.closed(connection)

    def refusal(self) -> agent.StartupRefusal:
        with fixtures.unlatched():
            return fixtures.startup_refusal()

    def test_a_refused_child_is_reported_as_a_refusal_and_closed_as_one(self):
        connection = Recorder()
        refusal = self.refusal()
        launcher = Launcher(error=refusal)
        with compiled():
            ledger, facts = attempt(connection, launcher)
        self.assertTrue(ledger.violations)
        self.assertEqual("refusal", facts["agent_run"]["stop_reason"])
        # Through `close_startup_refusal` and not `finish_task_attempt`: the
        # phase, both runtime versions and the vectors, none of which the
        # ordinary closing has anywhere to put.
        run, phase, sdk, cli, violations = connection.sent(execution.agent.CLOSE)[0]
        self.assertEqual((RUN, "pre_spawn"), (run, phase))
        self.assertEqual(refusal.sdk_version, sdk)
        self.assertEqual(len(refusal.violations), len(json.loads(violations)))
        self.assertEqual(refusal.cli_version, cli)

    def test_a_refusal_does_not_spend_the_attempt_it_never_made(self):
        # Story 55. Three of these on one machine would otherwise abandon a
        # Task as `attempts_exhausted` that nothing had yet attempted: what was
        # refused is this host, and the Task is as ready as it was.
        connection = Recorder()
        with compiled():
            ledger, facts = attempt(connection, Launcher(error=self.refusal()))

        self.assertEqual([], connection.finished())
        self.assertEqual("pending", facts["closure"]["task_status"])
        self.assertTrue(
            any("did not spend" in item.detail for item in ledger.assertions)
        )

    def test_the_refusal_is_recorded_after_the_heartbeat_has_stopped_beating(self):
        # The thread shares this connection, and the whole reason that is safe
        # is that nothing else touches it until the thread is joined. A refusal
        # written from inside the launcher would be the exception.
        connection = Recorder()
        with compiled():
            attempt(connection, Launcher(error=self.refusal()))

        self.assertLess(
            connection.position(execution.LEASE_TTL),
            connection.position(execution.agent.CLOSE),
        )
        self.assertLess(
            connection.position(execution.agent.CLOSE),
            connection.position(proxy.CLOSE_TOOL_RUN),
        )
        self.assertEqual([(TOOL_RUN, "error")], connection.sent(proxy.CLOSE_TOOL_RUN))

    def test_a_refusal_that_could_not_be_recorded_falls_back_to_the_closing(self):
        # A Task left claimed by a machine that refused it is worse than one
        # charged an attempt it did not make: the Lease is what would have to
        # lapse before anything else could try.
        connection = Recorder(raises={execution.agent.CLOSE: database_error("gone")})
        with compiled():
            ledger, facts = attempt(connection, Launcher(error=self.refusal()))

        self.assertEqual([(RUN, "refusal", None, None)], connection.finished())
        self.assertTrue(
            any("could not be returned" in item.detail for item in ledger.violations)
        )
        self.assertEqual("done", facts["closure"]["task_status"])

    def test_a_run_something_else_already_closed_is_left_to_the_closing(self):
        # `close_startup_refusal` answers false when there is nothing open
        # left, which is what a reconciliation that already took this run looks
        # like from here. Reporting a refunded attempt then would be reporting
        # an arithmetic nobody performed.
        connection = Recorder(refusal_closed=False)
        with compiled():
            ledger, facts = attempt(connection, Launcher(error=self.refusal()))

        self.assertEqual([(RUN, "refusal", None, None)], connection.finished())
        self.assertEqual("done", facts["closure"]["task_status"])
        self.assertTrue(
            any("already closed" in item.detail for item in ledger.assertions)
        )

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
                "tasks_settled_done": 0,
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


class RetestLaneTest(unittest.TestCase):
    """Ticket 114: the lane that notices the ground moved, and says so.

    Three connections were missing and this is the runtime end of all three: the
    watch rows nothing had ever written, the refresh that turns a moved Surface
    into work, and the read of the two views that had a grant and no reader. The
    order is what most of this asserts, because every one of those three is only
    correct in front of something else.
    """

    #: One refutation the lane made due and one delta that did it, in the
    #: column order the two statements ask for. The jsonb columns arrive as the
    #: text the server sent, which is what the module parses.
    DUE = (
        "HY4",
        "testable",
        "EN9",
        "injection.query_operator",
        "EN1",
        "the control was refused",
        json.dumps({"reason": "surface_delta", "delta_kind": "parameter_added",
                    "subject_key": "GET /notes#query:sort", "reopened": True,
                    "became_due_at": "2026-08-22T06:00:00Z"}),
    )
    MOVED = (
        "EN1",
        "parameter_added",
        "EN9",
        "GET /notes#query:sort",
        json.dumps(["injection.query_field", "injection.query_operator"]),
        "2026-08-22 06:00:00+00",
    )

    def test_the_lane_runs_before_the_slate_is_ranked(self):
        # A claim this lane reopens is a Task `cancel_reason_for` stops
        # abandoning and `novelty_for` stops scoring at zero. Behind the ranking
        # it would be a whole pass late, every pass.
        connection = Recorder()
        with compiled():
            attempt(connection)
        statements = connection.statements
        self.assertLess(
            statements.index(execution.ARM_WATCHES), statements.index(execution.RANK)
        )
        self.assertLess(
            statements.index(execution.REFRESH_NEGATIVES),
            statements.index(execution.RANK),
        )

    def test_a_watch_is_armed_before_the_refresh_that_would_fire_it(self):
        # And in the same transaction, which is the other half of the same
        # decision: the arming stamps the fingerprint the refresh compares
        # against, so a watch armed on this pass compares equal and waits for
        # the Surface to move rather than firing on the pass that created it.
        connection = Recorder()
        with compiled():
            attempt(connection)
        statements = connection.statements
        armed = statements.index(execution.ARM_WATCHES)
        refreshed = statements.index(execution.REFRESH_NEGATIVES)
        self.assertLess(armed, refreshed)
        self.assertEqual("BEGIN", statements[armed - 2])
        self.assertNotIn("COMMIT", statements[armed:refreshed])

    def test_both_views_are_read_for_the_program_this_pass_is_bound_to(self):
        # `rk2_runtime` reads every Program on the machine -- the policy on
        # every table under these two views is `USING (true)` -- so the Program
        # is the statement's to say. Neither view carries an identifier, so it
        # is said the way a `v_` read says everything: by the slug.
        connection = Recorder()
        with compiled():
            attempt(connection)
        self.assertEqual(
            [(PROGRAM, execution.RETEST_ROWS)], connection.sent(execution.DUE_RETESTS)
        )
        self.assertEqual(
            [(PROGRAM, execution.RETEST_ROWS)], connection.sent(execution.SURFACE_MOVES)
        )

    def test_the_read_is_of_what_the_two_writes_just_did(self):
        connection = Recorder()
        with compiled():
            attempt(connection)
        statements = connection.statements
        self.assertLess(
            statements.index(execution.REFRESH_NEGATIVES),
            statements.index(execution.DUE_RETESTS),
        )
        self.assertNotIn(
            "COMMIT",
            statements[
                statements.index(execution.ARM_WATCHES) : statements.index(
                    execution.SURFACE_MOVES
                )
            ],
        )

    def test_what_became_due_and_what_moved_are_both_reported(self):
        connection = Recorder(
            arming={"armed": 2, "watching": 5, "unwatched": 1},
            refreshed={
                "due": 1,
                "by_reason": {"surface_delta": 1},
                "reopened": 1,
                "watches_fired": 0,
                "watches_unwatchable": 1,
            },
            due_retests=[self.DUE],
            surface_moves=[self.MOVED],
        )
        with compiled():
            ledger, facts = attempt(connection)

        lane = facts["retests"]
        self.assertEqual((2, 5, 1), (lane["armed"], lane["watching"], lane["unwatched"]))
        self.assertEqual({"surface_delta": 1}, lane["by_reason"])
        [due] = lane["negative_knowledge"]
        self.assertEqual("HY4", due["hypothesis"])
        self.assertEqual("injection.query_operator", due["property_class"])
        # Parsed, not handed on as the server's text: a reader that had to
        # parse it a second time is a reader deciding what it means.
        self.assertEqual("parameter_added", due["retest"]["delta_kind"])
        [moved] = lane["surface_deltas"]
        self.assertEqual(
            ["injection.query_field", "injection.query_operator"],
            moved["property_classes"],
        )
        held = [step for step in ledger.assertions if step.name == "retests"]
        self.assertEqual(1, len(held))
        self.assertIn("2 claim(s) newly watched", held[0].detail)
        self.assertIn("1 refutation(s) became due", held[0].detail)

    def test_a_delta_whose_key_names_no_row_keeps_its_null_subject(self):
        # 022 records a removal with its key and no subject on purpose, and
        # filling one in here would be this module guessing what vanished.
        connection = Recorder(surface_moves=[("EN1", "endpoint_removed", None,
                                              "DELETE /notes", "[]",
                                              "2026-08-22 06:00:00+00")])
        with compiled():
            _, facts = attempt(connection)
        [moved] = facts["retests"]["surface_deltas"]
        self.assertIsNone(moved["subject"])
        self.assertEqual([], moved["property_classes"])

    def test_the_lane_runs_on_a_pass_that_has_nothing_to_offer(self):
        # It is a sweep over what earlier passes settled, not a step of running
        # a Task. A Program with an empty Slate is exactly the Program whose
        # claims have all come to rest, which is the one with most to re-ask.
        connection = Recorder(slate=0)
        with compiled():
            _, facts = attempt(connection)
        self.assertNotIn(execution.CLAIM, connection.statements)
        self.assertEqual(0, facts["retests"]["due"])

    def test_a_lane_that_fails_does_not_stop_the_pass(self):
        connection = Recorder(
            raises={execution.ARM_WATCHES: database_error("deadlock detected")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["retests"])
        self.assertEqual(
            ["retests"], [step.name for step in ledger.assertions if not step.ok]
        )
        # Repeating work already done is expensive and is not a reason to
        # refuse to do any.
        self.assertIn(execution.CLAIM, connection.statements)

    def test_a_read_that_fails_leaves_the_writes_it_would_have_reported(self):
        # One transaction, so a view that will not answer rolls the arming back
        # with it. The next pass arms again -- the verb is idempotent -- and the
        # alternative is a report that says a claim was watched when the rows
        # saying so were never committed.
        connection = Recorder(
            raises={execution.DUE_RETESTS: database_error("permission denied")}
        )
        with compiled():
            ledger, facts = attempt(connection)
        self.assertIsNone(facts["retests"])
        self.assertIn("ROLLBACK", connection.statements)
        self.assertEqual(
            ["retests"], [step.name for step in ledger.assertions if not step.ok]
        )


class VocabularyTest(unittest.TestCase):
    """The words CONTEXT.md's Slate entry asks this module not to use.

    Read out of the document rather than copied here, because a list written
    twice is a list that can disagree with itself: the vocabulary of record is
    CONTEXT.md and this case is only the place where `execution` is held to it.

    `execution` and not every module, because this is where the Slate is walked,
    offered, chosen from and claimed. A word for it that the vocabulary of
    record avoids is a second name for the one thing an operator, an ADR and a
    ledger row all have to be talking about at once.
    """

    def test_the_module_that_walks_the_slate_never_calls_it_a_queue(self):
        root = Path(execution.__file__).resolve().parents[2]
        entry = (root / "CONTEXT.md").read_text().split("**Slate**:", 1)[1]
        avoided = [
            word.strip().lower()
            for word in entry.split("_Avoid_:", 1)[1].splitlines()[0].split(",")
        ]
        self.assertEqual(["queue", "candidates", "shortlist", "options"], avoided)
        source = Path(execution.__file__).read_text().lower()
        for word in avoided:
            with self.subTest(word):
                self.assertNotRegex(source, rf"\b{re.escape(word)}\b")


if __name__ == "__main__":
    unittest.main()
