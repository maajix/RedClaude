"""One ready Task, run from the queue to a canonical Observation.

This is the slice `rk run` was missing. Everything either side of it already
existed and was tested on its own: the scheduler decides what is worth doing,
the isolation boundary decides what a child can reach, the capability proxy
decides what one request may do, and the promotion function decides what
becomes canonical. What was absent was the thing that runs them in one order,
once, and leaves nothing open behind it.

Four properties are what the order is for, and each of them is a property of
the sequence rather than of any step in it:

* Nothing is claimed that cannot be run. The boundary is resolved before the
  claim, because a Task claimed by a runtime with no container to start is a
  Task holding a lease for nothing.
* The capability is minted against a Tool run that names the Task, and it is
  handed to the child rather than mintable by it. A child that could mint one
  would be a child deciding what it may call.
* The child's structured result is staged and promoted on the runtime's own
  connection, against canonical rows the child cannot see, let alone write.
  Its prose closes nothing: `tasks_completion_needs_promotion` is what refuses
  that, and this module never tries.
* The attempt is closed in a `finally`, by the one database call that closes
  Tool runs, the Agent run, the Leases and the Task together. Whatever went
  wrong above it, the rows do not stay open.

The module imports `program` and is never imported by it. `rk run` reaches the
slice through a callback it is given, because `proxy` imports `program` and a
`program` that imported this module would close that loop.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from redkraken import agent, isolation, migrate, packet as packet_module, pg
from redkraken import program, proposal, proxy, roster, state as state_module
from redkraken.outcome import INTEGRITY_FAILED, INVALID_CONFIGURATION, Ledger


__all__ = [
    "APPLICATION",
    "CERTIFICATE",
    "Claimed",
    "HOME",
    "IMAGE",
    "NETWORK",
    "OPTIONAL",
    "PROXY_CONTAINER",
    "PROXY_URL",
    "REQUIRED",
    "SDK",
    "Slice",
    "boundary",
    "requested",
]


#: Where the Agent boundary is described. Environment rather than the Program's
#: configuration file, for the reason the configuration file is hashed: the
#: image, the network and the proxy container are properties of the machine the
#: harness runs on, not of the Program, and moving to another machine must not
#: read as a policy change that every earlier Finding has to be reconciled with.
IMAGE = "RK_AGENT_IMAGE"
NETWORK = "RK_AGENT_NETWORK"
PROXY_CONTAINER = "RK_AGENT_PROXY_CONTAINER"
PROXY_URL = "RK_AGENT_PROXY_URL"
APPLICATION = "RK_AGENT_APPLICATION"
SDK = "RK_AGENT_SDK"
HOME = "RK_AGENT_HOME"

#: The one the door already owns a name for. A second variable for the same
#: certificate would be a second answer the day one of them is set.
CERTIFICATE = proxy.CA_VARIABLE

#: The five without which there is no boundary, and the three directories that
#: are absent by default because absent is the contained value.
REQUIRED = (IMAGE, NETWORK, PROXY_CONTAINER, PROXY_URL, CERTIFICATE)
OPTIONAL = ((APPLICATION, "application"), (SDK, "sdk"), (HOME, "home"))

#: What it takes for this machine to be claiming a boundary at all. Every
#: variable above except the certificate, because the certificate is the door's
#: name as well: `rk send --ca` falls back to it, so an operator who exports it
#: to talk to the fence by hand has said nothing about running children -- and
#: a `rk run` that read it as a half-described boundary would refuse the command
#: that worked yesterday.
CLAIMED = tuple(name for name in REQUIRED if name != CERTIFICATE) + tuple(
    name for name, _ in OPTIONAL
)

#: What the child is told the Task is, in one sentence per kind. A kind with no
#: sentence here is not refused: the fallback names the kind and the subject,
#: which is the honest description of a Task nobody has written prose for yet.
MISSIONS = {
    "recon": "Map what this target exposes.",
    "hunt": "Look for one exploitable weakness in this target.",
    "analyze": "Read what this target returned and say what it implies.",
    "validate": "Decide whether what was claimed about this target holds.",
    "report": "Write up what has been established about this target.",
}

#: How a child stopped, in the words `agent_runs.stop_reason` accepts. Two
#: vocabularies because they have two authors: the column's is 0006's, extended
#: by 0012, and the word the launcher reads off a `ResultMessage` is the API's
#: -- `end_turn`, `max_tokens`, `tool_use`, `stop_sequence`, `pause_turn`,
#: `refusal`, of which only the last is in both.
#:
#: Writing an unmapped word is not a cosmetic error. `finish_task_attempt` sets
#: the column inside the transaction that also closes the Tool runs, releases
#: the Leases and settles the Task, so the check violation would roll all four
#: back and leave a finished child's attempt open -- exactly the state criterion
#: 5 says a success must not leave.
STOP_REASONS = {
    "end_turn": "completed",
    "stop_sequence": "stop_condition",
    "max_tokens": "budget",
    "pause_turn": "aborted",
    "refusal": "refusal",
}

#: The other side of the same column: what it already accepts. Kept beside the
#: mapping because a launcher answering in the database's own vocabulary is
#: answering correctly, and mapping that answer to `error` would report a
#: finished run as a broken one.
ACCEPTED_STOPS = (
    "completed", "stop_condition", "budget", "refusal", "error", "aborted", "parked",
)

#: One scheduler pass, in the three steps the corpus states it in. All three,
#: because `offer_slate` on its own offers nothing: `rank_candidates` filters on
#: `t.estimated_cost`, which is NULL until a ranking writes it, and NULL fails
#: the affordability comparison silently. A runtime that only offered would find
#: an empty slate for every Task it had just created and report an idle queue.
#:
#: `advance_lane_quota` sits between them because 0037 says it does: the quota
#: is an input to the entitlement sort and to nothing in the priority formula,
#: so running it after the ranking cannot invalidate the numbers just written.
#:
#: `offer_slate` consumes the outstanding slate and writes a new one, so calling
#: it is not a peek: it is the offer, and the claim takes from it.
#:
#: Every column of it, not a count. A slate the runtime reduced to a number is a
#: slate nobody was offered -- ticket 23's Slate is what the orchestrator chooses
#: from, and a choice needs the entries, their factors and when the offer stops
#: being good. `claim_task()` still takes no argument here: this loop is the
#: runtime's own path, and decision 3 says the runtime takes the first entry.
RANK = "SELECT rank_pass('runtime')"
QUOTA = "SELECT advance_lane_quota('runtime')"
OFFER = "SELECT * FROM offer_slate()"
CLAIM = "SELECT claim_task()"

#: What was claimed, read back through the Agent run the claim created rather
#: than assembled from what this process asked for. The claim is the database's
#: decision -- which Task, which role, which model -- and a runtime that
#: described the run from its own request would be describing a different run
#: the moment the two disagreed.
#:
#: The target is built here rather than in Python for the same reason: an
#: endpoint's URL is its application's base joined to its template, and the
#: join is one expression over two rows this query already has.
#:
#: The Program is a predicate and not a convenience. `claim_task` answers with
#: an Agent run *label*, and a label is a per-Program counter: every Program's
#: first run is `AR1`. This connection is the runtime's, which sees every
#: Program, so a lookup on the label alone reads back whichever `AR1` the
#: planner reached first -- and the attempt would then be opened against another
#: Program's run.
#:
#: The cross-role subagent cap comes back with the run for the same reason the
#: Lease TTL is read rather than assumed: it is a weights column an operator
#: sets per Program, and the gate inside the child has to refuse at the number
#: the scheduler offered and claimed under. Read here rather than in a second
#: statement so that it is the row this claim ran against -- a weights version
#: activated between the claim and the launch would otherwise start a child
#: under a cap no part of this attempt was scheduled by.
STARTED = (
    "SELECT ar.id::text, ar.label, ar.role,"
    " t.id::text, t.label, t.kind, t.attempts,"
    " e.type, e.label,"
    " coalesce(ep.method, 'GET'),"
    " CASE"
    "   WHEN ep.entity_id IS NOT NULL THEN rtrim(pa.base_url, '/')"
    "     || CASE WHEN left(ep.path_template, 1) = '/' THEN ep.path_template"
    "             ELSE '/' || ep.path_template END"
    "   WHEN ap.entity_id IS NOT NULL THEN ap.base_url"
    " END,"
    " w.max_concurrent_subagents"
    " FROM agent_runs ar"
    " JOIN tasks t ON t.id = ar.task_id"
    " JOIN entities e ON e.id = t.subject_entity_id"
    " JOIN scheduler_weights w ON w.active"
    " LEFT JOIN endpoints ep ON ep.entity_id = e.id"
    " LEFT JOIN applications pa ON pa.entity_id = ep.application_id"
    " LEFT JOIN applications ap ON ap.entity_id = e.id"
    " WHERE ar.label = $1 AND ar.program_id = $2::uuid"
)

#: The Tool run the capability is minted against. `proxy.OPEN_TOOL_RUN` cannot
#: be reused: `authorize_tool_run` requires a Tool run's Task to match its Agent
#: run's, and the proxy's own row carries no Task because the command that opens
#: it has none. Everything else about the row is the same, including the tool
#: name -- `proxy.TOOL` is what `canonical_request`, the `net_*` risk rules and
#: the egress authorisation all key on, and a second spelling would be a row no
#: rule matches.
OPEN_TOOL_RUN = (
    "INSERT INTO tool_runs (program_id, agent_run_id, task_id, tool, args, status, transport)"
    " VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5::jsonb, 'running', 'runtime')"
    " RETURNING id::text, label"
)

#: How long the capability has left, asked of the database that set it rather
#: than parsed out of the verdict. The child is given no longer than this: a
#: run still going when its capability lapses is a run whose remaining turns
#: cannot reach anything, and the honest thing to do with them is not spend them.
LIFETIME = (
    "SELECT greatest(0, extract(epoch FROM (egress_token_expires_at - clock_timestamp())))"
    " FROM tool_runs WHERE id = $1::uuid"
)

#: What the door recorded for this Tool run, which is how the runtime learns
#: what the child's one request actually did. The child reports too, and its
#: report is not evidence: the Receipt is written by the fence, on the fence's
#: own connection, and is the row a promoted Observation has to cite.
EXCHANGE = (
    "SELECT label, decision, status_code FROM receipts"
    " WHERE program_id = $1::uuid AND tool_run_id = $2::uuid"
    " ORDER BY ts_arrival DESC LIMIT 1"
)

CAUSE = "SELECT set_cause($1::uuid, $2::uuid)"
PROMOTE = "SELECT promote_proposal($1::uuid)"
FINGERPRINT = "SELECT fingerprint_program_surface()"
FINISH = "SELECT finish_task_attempt($1::uuid, $2)"

#: The Lease this run was given, and the one call that moves both halves of it.
#: The TTL is read rather than assumed: it is a weights column, so a harness
#: that shortened it would shorten what a crash costs, and a runtime carrying
#: its own copy would keep beating on the old one.
LEASE_TTL = "SELECT extract(epoch FROM lease_ttl) FROM scheduler_weights WHERE active"
HEARTBEAT = "SELECT heartbeat_leases($1::uuid)"

#: What a beat may not outlast. This connection has no timeout of its own -- no
#: statement in this module does -- so a server that stops answering blocks the
#: caller forever, and for every other statement here that is the caller's own
#: thread and its own problem. For a beat it is a second thread the closing has
#: to join before it may use the connection again, so the beat is the one
#: statement that says how long it is willing to wait.
BEAT_TIMEOUT = "SET LOCAL statement_timeout = '20s'"

#: Recovery for what an owner that stopped beating left in flight, asked once
#: per pass and before anything is offered. A crashed sibling's Tasks are not
#: this run's to wait for, and the offer that follows is the first reader that
#: would otherwise skip them.
RECONCILE = "SELECT reconcile_leases()"

#: How many beats fit in one TTL. Three, so two may be lost -- to a slow
#: statement, a paused container, a machine that swapped -- before the Lease
#: lapses and this run's work becomes something another one may take. One would
#: make every missed beat fatal; ten would spend the log on saying nothing.
BEATS_PER_TTL = 3

#: The three answers the gate can give, and the two this runtime may act on.
ALLOW = "allow"
ASK = "ask"

#: The roster group holding the one tool this slice's whole attempt is about.
NET = "net.request"


def requested(environment: Mapping[str, str]) -> bool:
    """Whether this machine was configured to run anything at all.

    A blank environment is not a misconfiguration: it is `rk run` used the way
    every earlier ticket used it, to open a Program and report it. Only a
    half-described boundary is an error, and telling the two apart is what this
    predicate is for.
    """
    return any(environment.get(name) for name in CLAIMED)


def boundary(
    environment: Mapping[str, str],
) -> tuple[isolation.AgentContainer | None, tuple[str, ...]]:
    """The described boundary, or nothing and the names that were missing.

    Nothing is defaulted. An image name guessed here would start a child in
    whatever the guess happened to match, and a proxy URL guessed here would
    point a child's only route at whatever answers on that port -- both of them
    the sort of mistake that looks like a working run.
    """
    missing = tuple(name for name in REQUIRED if not environment.get(name))
    if missing:
        return None, missing
    supplied = {
        field: Path(environment[name])
        for name, field in OPTIONAL
        if environment.get(name)
    }
    container = isolation.AgentContainer(
        image=environment[IMAGE],
        network=environment[NETWORK],
        proxy_container=environment[PROXY_CONTAINER],
        proxy_url=environment[PROXY_URL],
        certificate=Path(environment[CERTIFICATE]),
        **supplied,
    )
    return container, ()


def stopped_as(reported: str | None) -> str:
    """One word for how a child stopped, in the vocabulary the column has.

    Nothing reported is `completed`: a session that ran to the end of its own
    accord is reported with no reason at all, and it did stop. A word neither
    vocabulary has is `error` rather than `completed`, because a run that ended
    for a reason this harness cannot name is not a run it can call finished.
    """
    if reported is None:
        return "completed"
    if reported in ACCEPTED_STOPS:
        return reported
    return STOP_REASONS.get(reported, "error")


@dataclass(frozen=True, slots=True)
class Claimed:
    """One claimed Task and the run the database opened for it.

    A single value rather than twelve passed around together, because every
    step below the claim needs some of them and no step needs a different
    twelve. `url` is the one that can be absent: a subject that is neither an
    application nor an endpoint has no address to send a request to, and that
    is a refusal with a reason rather than a missing field to work around.

    `subagent_cap` is the odd one: it describes the weights row rather than the
    Task, and it is here because it has to travel with the claim. The scheduler
    ranked and claimed under it, and the gate in the child refuses under it, so
    a copy carried anywhere else would be a second statement of the one number
    ticket 73 exists to have only one of.
    """

    agent_run_id: str
    agent_run_label: str
    role: str
    task_id: str
    task_label: str
    kind: str
    attempts: int
    subject_type: str
    subject_label: str
    method: str
    url: str | None
    subagent_cap: int

    @classmethod
    def from_row(cls, row) -> Claimed:
        return cls(
            agent_run_id=str(row[0]),
            agent_run_label=str(row[1]),
            role=str(row[2]),
            task_id=str(row[3]),
            task_label=str(row[4]),
            kind=str(row[5]),
            attempts=int(row[6]),
            subject_type=str(row[7]),
            subject_label=str(row[8]),
            method=str(row[9]),
            url=None if row[10] is None else str(row[10]),
            subagent_cap=int(row[11]),
        )

    def objective(self) -> str:
        """The whole of what the child is told, and the shape of what it owes back.

        The target is named because the child cannot look it up: its packet
        holds what the Program knows, not what this attempt is for. The citation
        rule is stated because it is the rule promotion applies -- an
        Observation citing no Receipt is dropped, and a child that learns that
        from the drop has already spent the attempt.
        """
        mission = MISSIONS.get(self.kind, f"Carry out this {self.kind} Task.")
        return (
            f"{mission}\n\n"
            f"Subject: the {self.subject_type} {self.subject_label}.\n"
            f"Target: {self.method} {self.url}\n\n"
            "Send that one request with mcp__rk2__http_request and read the answer. "
            "Then call mcp__rk2__submit_mission_result once, with one observation per "
            "thing you actually established, each citing the Receipt the request "
            "answered with. Nothing you write becomes canonical until the runtime "
            "promotes it, and it promotes only what cites a Receipt from this run."
        )

    def facts(self) -> dict:
        return {
            "task": {
                "id": self.task_id,
                "label": self.task_label,
                "kind": self.kind,
                "attempts": self.attempts,
                "subject": self.subject_label,
                "subject_type": self.subject_type,
            },
            "agent_run": {
                "id": self.agent_run_id,
                "label": self.agent_run_label,
                "role": self.role,
                "stop_reason": None,
            },
        }


class Heartbeat:
    """One run saying it is still here, for as long as its child runs.

    A thread, because what this has to outlast is a blocking wait on a
    subprocess and there is nothing else in that window to hang a timer on. It
    shares the runtime's connection rather than opening one, and that is safe
    for one reason worth stating: the main thread is inside `_child` for the
    whole life of this thread and touches nothing until `__exit__` has joined
    it. Overlap is not avoided by a lock here, it is not possible.

    That join is unbounded, and `BEAT_TIMEOUT` is why it can be. Bounding the
    join instead would trade a wait for two threads on one stream, which is the
    one thing the paragraph above rules out; bounding the statement leaves the
    beat to fail like any other, and a thread with an error to report stops on
    its own.

    A beat that comes back refused stops the beating and is not retried. The
    database answers `beat: false` when the Task Lease has already lapsed, and
    at that point some reconciliation is entitled to this run's work -- may have
    taken it already. Beating harder at that would be this process arguing with
    the only clock either half of the Lease has.

    A beat that raises stops it too, and stops it quietly. The child is still
    running and the attempt is still worth finishing; what a failed heartbeat
    costs is the Lease, which lapses on its own, and the closing reports it.
    """

    def __init__(
        self,
        connection: pg.Connection,
        ledger: Ledger,
        claimed: Claimed,
        facts: dict,
        every: float,
    ):
        self.connection = connection
        self.ledger = ledger
        self.claimed = claimed
        self.facts = facts
        self.every = every
        self.beats = 0
        self.identities: int | None = None
        self.lapsed: str | None = None
        self.failure: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._beat, name=f"heartbeat-{claimed.agent_run_label}", daemon=True
        )
        self._started = False

    def __enter__(self) -> Heartbeat:
        if self.every > 0:
            self._thread.start()
            self._started = True
        return self

    def __exit__(self, *exception) -> bool:
        self._stop.set()
        if self._started:
            self._thread.join()
        self.facts["heartbeat"] = {
            "every": self.every,
            "beats": self.beats,
            "identities": self.identities,
            "lapsed": self.lapsed,
            "failure": self.failure,
        }
        self._report()
        return False

    def _beat(self) -> None:
        # `wait` and not `sleep`: the child usually ends between two beats, and
        # a sleeping thread would hold the attempt open for the rest of an
        # interval that no longer has anything to keep alive.
        while not self._stop.wait(self.every):
            try:
                with self.connection.transaction():
                    self.connection.execute(BEAT_TIMEOUT)
                    _actor(self.connection)
                    answer = proxy.as_object(
                        self.connection.execute(
                            HEARTBEAT, (self.claimed.agent_run_id,)
                        ).scalar()
                    )
            except (pg.DatabaseError, pg.ConnectionError_) as error:
                # Both, because they are siblings rather than one deriving from
                # the other: the server refusing is a `DatabaseError` and the
                # stream going away is a `ConnectionError_`, and a thread that
                # caught only the first would die with its exception unread,
                # leaving the closing to report a Lease it did not renew.
                self.failure = str(error)
                return
            if not answer.get("beat"):
                self.lapsed = str(answer.get("reason"))
                return
            held = int(answer.get("identity_leases") or 0)
            if self.identities is not None and held < self.identities:
                # The Task half renewed and the Identity half did not come with
                # it. Nothing in this corpus should be able to do that, which is
                # exactly why it is worth saying: what a run holds is one hold,
                # and half of one is the disagreement the Lease exists to
                # prevent. Stopping is the same answer as a lapse, for the same
                # reason -- this process no longer holds what it claimed as.
                self.lapsed = (
                    f"the Identity half of the Lease went from {self.identities} "
                    f"hold(s) to {held}"
                )
                return
            self.identities = held
            self.beats += 1

    def _report(self) -> None:
        if self.failure is not None:
            self.ledger.fail(
                "heartbeat",
                f"{self.claimed.agent_run_label} stopped renewing its Lease after "
                f"{self.beats} beat(s): {self.failure}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        if self.lapsed is not None:
            self.ledger.fail(
                "heartbeat",
                f"{self.claimed.agent_run_label} no longer holds what it claimed after "
                f"{self.beats} beat(s): {self.lapsed}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        if not self._started:
            # Nothing beat and nothing was going to: `_heartbeat` already failed
            # the same assertion saying why. A hold here would be a second
            # assertion under the same name contradicting the first.
            return
        self.ledger.hold(
            "heartbeat",
            f"{self.claimed.task_label} and the {self.identities or 0} Identity Lease(s) "
            f"taken with it were held through {self.beats} beat(s), "
            f"one every {self.every:.0f}s",
        )


@dataclass(frozen=True)
class Slice:
    """One attempt at one Task, and everything an attempt needs to be made.

    `launch` and `state` are the two seams. The first is how a test runs the
    sequence without an engine: the launcher is a callable of the same shape as
    `agent.agent_run`, and everything either side of it is the part worth
    testing. The second is a second connection string, because the Mission
    packet is compiled as the agent role -- what a child may read is decided by
    row level security on that role, and a packet compiled on the runtime's own
    connection would be a packet whose bounds nothing enforced.
    """

    boundary: isolation.AgentContainer
    state: pg.Settings
    launch: Callable[..., agent.AgentRunResult] = agent.agent_run
    timeout: float = agent.TIMEOUT

    def attempt(self, ledger: Ledger, connection: pg.Connection, program_id: str) -> dict:
        """Reconcile, offer, claim, run, promote, close. Once, and closed either way.

        The session is bound to the Program first and stays bound: every
        scheduler function refuses an unbound session, and binding per statement
        would be four chances to bind the wrong one.
        """
        facts = {
            "reconciliation": None,
            "slate": [],
            "task": None,
            "agent_run": None,
            "target": None,
            "packet": None,
            "heartbeat": None,
            "tool_run": None,
            "receipt": None,
            "proposal": None,
            "promotion": None,
            "closure": None,
        }
        connection.execute(proxy.BIND, (program_id,))
        facts["reconciliation"] = self._reconcile(ledger, connection)

        offered = self._offer(ledger, connection)
        if offered is None:
            return facts
        facts["slate"] = offered
        if not offered:
            ledger.hold("slate", "no Task is ready; nothing was claimed")
            return facts

        claimed = self._claim(ledger, connection, program_id, len(offered))
        if claimed is None:
            return facts
        facts.update(claimed.facts())
        ledger.hold(
            "claim",
            f"{claimed.task_label} ({claimed.kind}) claimed as {claimed.agent_run_label}, "
            f"attempt {claimed.attempts}",
        )

        try:
            self._run(ledger, connection, program_id, claimed, facts)
        finally:
            facts["closure"] = self._finish(ledger, connection, claimed, facts)
        return facts

    # -- the queue ---------------------------------------------------------

    def _reconcile(self, ledger: Ledger, connection: pg.Connection) -> dict | None:
        """What an owner that stopped beating left behind, before anything is offered.

        Here rather than in the restart sweep, and explicitly rather than inside
        a read. `resume_program` runs once per `rk run` and answers the question
        for what was in flight when this process started; a sibling that dies
        while this one is working is nobody's restart, and the pass that is
        about to ask what is ready is the first thing that would otherwise walk
        past its Tasks. It reports what it declined to touch as well as what it
        recovered -- a live owner is an answer, not an absence.

        A failure is reported and does not stop the pass. Reconciliation is
        recovery of somebody else's work; this run can still do its own.
        """
        with connection.transaction():
            _actor(connection)
            try:
                answer = proxy.as_object(connection.execute(RECONCILE).scalar())
            except pg.DatabaseError as error:
                ledger.fail(
                    "reconciliation",
                    f"expired Leases could not be reconciled: {error}",
                    code=INTEGRITY_FAILED,
                    source="database",
                )
                return None
        recovered = int(answer.get("tasks_returned") or 0) + int(
            answer.get("tasks_retired") or 0
        )
        ledger.hold(
            "reconciliation",
            f"{recovered} Task(s) recovered from lapsed Leases, "
            f"{answer.get('tasks_left_to_live_owners')} left to the runs still holding them",
        )
        return answer

    def _offer(self, ledger: Ledger, connection: pg.Connection) -> list[dict] | None:
        """One scheduler pass: rank, advance the quota, offer.

        One transaction, because the three are one pass. A ranking that
        committed and an offer that did not would leave priorities computed
        against a slate nobody was given, and the next pass would rank them
        again from the same rows.

        The entries come back as the database named them. `None` is the pass
        failing, which an empty slate is not.
        """
        with connection.transaction():
            _actor(connection)
            try:
                connection.execute(RANK)
                connection.execute(QUOTA)
                return [_slate_entry(row) for row in connection.execute(OFFER).dicts()]
            except pg.DatabaseError as error:
                ledger.fail(
                    "slate",
                    f"the scheduler could not offer a slate: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return None

    def _claim(
        self, ledger: Ledger, connection: pg.Connection, program_id: str, offered: int
    ) -> Claimed | None:
        """One Task off the slate, described by the run the claim opened.

        A refused claim is reported and not retried, because the walk down the
        slate belongs to `claim_task` and has already happened. Called with no
        argument it takes the first entry that is still claimable when the
        claim's own transaction rechecks it, so a NULL here means every entry
        was rechecked and every one had gone -- and a raise here means the pass
        itself is unusable, which retrying would not mend.
        """
        with connection.transaction():
            _actor(connection)
            try:
                label = connection.execute(CLAIM).scalar()
            except pg.DatabaseError as error:
                ledger.fail(
                    "claim",
                    f"the claim against a {offered}-Task slate failed: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return None
            if label is None:
                ledger.hold(
                    "claim", f"{offered} Task(s) offered and none of them was claimable"
                )
                return None
            rows = connection.execute(STARTED, (str(label), program_id)).rows
        if not rows:
            ledger.fail(
                "claim",
                f"{label} was claimed and no run of that name can be read back",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        return Claimed.from_row(rows[0])

    # -- the attempt -------------------------------------------------------

    def _run(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        facts: dict,
    ) -> None:
        """Everything between the claim and the closing, in the one order.

        Nothing here raises past `attempt`: each step that cannot continue says
        why and returns, and the `finally` above closes what was opened. A step
        that threw instead would still be closed -- but the report would carry
        a traceback where it should carry the reason.
        """
        if claimed.url is None:
            ledger.fail(
                "target",
                f"the {claimed.subject_type} {claimed.subject_label} carries no address "
                "to send a request to; only applications and endpoints do",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return
        facts["target"] = {"url": claimed.url, "method": claimed.method}

        role = roster.ROLES.get(claimed.role)
        if role is None or not role.allowed_tools(agent.SERVED):
            # The launcher's own rule, asked here rather than found out there.
            # `agent.assess` refuses a renderer and refuses a role whose served
            # surface is empty -- `validator` holds only `validate.judge`, which
            # nothing serves yet -- and asking after the capability was minted
            # would spend an authorisation on a child that was never going to
            # start.
            ledger.fail(
                "role",
                f"{claimed.agent_run_label} is a {claimed.role} run, which this runtime "
                "cannot start as an isolated child",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return
        if NET not in role.tool_groups:
            # A capability is minted per attempt and this one could not be
            # spent: the roster withholds the request tool from this role on
            # purpose -- an analyst that fetches is a hunter with the wrong
            # quota -- so a Tool run opened for it would be an authorisation
            # nobody may use, sitting live until the closing swept it.
            ledger.fail(
                "role",
                f"a {claimed.role} run holds no {NET}; this slice serves one "
                f"target request and {claimed.task_label} needs a role that may make it",
                code=INVALID_CONFIGURATION,
                source="roster",
            )
            return

        mission = self._packet(ledger, program_id)
        if mission is None:
            return
        facts["packet"] = {
            "revision": mission.revision,
            "sections": {
                name: len(section.rows) for name, section in mission.sections.items()
            },
        }

        opened = self._authorize(ledger, connection, program_id, claimed, facts)
        if opened is None:
            return
        tool_run_id, door, lifetime = opened

        outcome = "error"
        try:
            # The beating stops before anything else in this transaction's
            # sequence resumes, which is what makes sharing the connection with
            # it safe -- and before the closing releases the Lease, which is the
            # one thing a late beat could contradict.
            with self._heartbeat(ledger, connection, claimed, facts):
                result = self._child(ledger, claimed, mission, door, lifetime, program_id)
            if result is None:
                facts["agent_run"]["stop_reason"] = "refusal"
                return
            facts["agent_run"]["stop_reason"] = stopped_as(result.stop_reason)
            outcome = self._exchange(ledger, connection, program_id, tool_run_id, facts)
            self._promote(ledger, connection, program_id, claimed, result, facts)
        finally:
            # Before the closing call sweeps it. That call closes whatever is
            # still running as `error`, which is the right word for a row nobody
            # accounted for and the wrong one for this row: this runtime knows
            # what the request did, and the Receipt above is what it knows it
            # from.
            self._close(ledger, connection, claimed, facts["tool_run"], outcome)

    def _heartbeat(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed, facts: dict
    ) -> Heartbeat:
        """How often this run says it is here, from the TTL it was given.

        A TTL this runtime cannot read leaves the interval at zero, which starts
        no thread at all. That is the honest degradation: the Lease still
        expires on its own, the run still finishes, and the report says nothing
        beat rather than claiming a renewal that never happened.
        """
        try:
            ttl = float(str(connection.execute(LEASE_TTL).scalar()))
            if ttl <= 0:
                raise ValueError(f"the active weights declare a TTL of {ttl}s")
        except (pg.DatabaseError, pg.ConnectionError_, TypeError, ValueError) as error:
            ledger.fail(
                "heartbeat",
                f"the Lease TTL could not be read, so {claimed.agent_run_label} will "
                f"not renew what it holds: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            ttl = 0.0
        return Heartbeat(connection, ledger, claimed, facts, ttl / BEATS_PER_TTL)

    def _close(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        tool_run: dict,
        outcome: str,
    ) -> None:
        """One Tool run closed as what it did, which is what revokes it.

        The cause is set beside the close and not once at the top of the
        attempt: `set_cause` is transaction-local by construction, so every
        transaction that emits an Event has to say again which run it was
        caused by. Without it this row's settling Event names a Program and no
        run, and criterion 2 asks the rows and the log to name the same one.

        A failure is reported rather than raised. This is called from a
        `finally`, and an exception here would replace the reason the attempt
        ended with the reason the cleanup did.
        """
        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                connection.execute(proxy.CLOSE_TOOL_RUN, (tool_run["id"], outcome))
        except pg.DatabaseError as error:
            ledger.fail(
                "revocation",
                f"{tool_run['label']} could not be closed as {outcome}: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        ledger.hold(
            "revocation",
            f"{tool_run['label']} closed as {outcome}; its capability no longer resolves",
        )

    def _packet(self, ledger: Ledger, program_id: str) -> packet_module.Packet | None:
        """What the child may read, compiled as the role whose reads are bounded."""
        session = migrate.open_connection(ledger, self.state)
        if session is None:
            return None
        with session:
            if not state_module.assert_agent_connection(ledger, session):
                return None
            with session.transaction():
                session.execute("SET TRANSACTION READ ONLY")
                if not state_module.bind_agent_session(ledger, session, program_id):
                    return None
                return packet_module.compile(session)

    def _authorize(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        facts: dict,
    ) -> tuple[str, agent.Egress, float] | None:
        """One Tool run naming the Task, one verdict, one capability with a clock.

        Committed before the verdict is asked for, because the gate resolves the
        row on a session of its own and cannot see an uncommitted one -- and
        asked for before the child starts, because a child handed no capability
        is a child that can do nothing with the turns it would spend finding out.

        Every statement is inside the guard, including the two reads. A verdict
        this runtime could not obtain is a reason to report and close the
        attempt, and a traceback out of here would leave `rk run` answering with
        one where it owes a Ledger.
        """
        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                opened = connection.execute(
                    OPEN_TOOL_RUN,
                    (
                        program_id,
                        claimed.agent_run_id,
                        claimed.task_id,
                        proxy.TOOL,
                        json.dumps(
                            {
                                "url": claimed.url,
                                "method": claimed.method,
                                "identity_slot": "",
                            }
                        ),
                    ),
                ).rows[0]
            tool_run_id, label = str(opened[0]), str(opened[1])
            facts["tool_run"] = {"id": tool_run_id, "label": label, "decision": None}

            gate = proxy.as_object(
                connection.execute(proxy.AUTHORIZE_TOOL_RUN, (tool_run_id,)).scalar()
            )
            decision = str(gate.get("decision") or "")
            facts["tool_run"]["decision"] = decision
            capability = gate.get("capability")
            lifetime = (
                0.0
                if not capability
                else float(connection.execute(LIFETIME, (tool_run_id,)).scalar() or 0.0)
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "authorization",
                f"no capability could be minted for {claimed.task_label}: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None

        if not capability:
            self._unauthorized(ledger, connection, claimed, facts["tool_run"], gate, decision)
            return None
        ledger.hold(
            "authorization",
            f"{label} is {gate.get('risk_class')}/{decision} by {gate.get('rule')}",
        )
        door = agent.Egress(
            capability=str(capability),
            program_id=program_id,
            proxy_url=self.boundary.proxy_url,
        )
        return tool_run_id, door, lifetime

    def _unauthorized(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        claimed: Claimed,
        tool_run: dict,
        gate: dict,
        decision: str,
    ) -> None:
        """A verdict that minted nothing, closed as what it was.

        `ask` is filed rather than treated as a refusal, by the same call the
        proxy uses: the answer is that a person decides this one, and a runtime
        that closed it as denied would have decided it -- in the direction that
        leaves no question behind.
        """
        label = tool_run["label"]
        if decision == ASK:
            try:
                with connection.transaction():
                    _actor(connection)
                    connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                    pending = str(
                        connection.execute(proxy.PARK_TOOL_RUN, (tool_run["id"],)).scalar()
                    )
            except pg.DatabaseError as error:
                ledger.fail(
                    "authorization",
                    f"the gate answered ask for {label} and the question could not "
                    f"be filed: {error}",
                    code=INTEGRITY_FAILED,
                    source="database",
                )
                return
            ledger.fail(
                "authorization",
                f"{label} is {gate.get('risk_class')}/ask by {gate.get('rule')}: "
                f"filed as {pending} for a human to answer",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return
        self._close(ledger, connection, claimed, tool_run, "denied")
        ledger.fail(
            "authorization",
            f"the gate answered {decision or 'nothing'} for {label}: "
            "no capability was minted and no child was started",
            code=INVALID_CONFIGURATION,
            source="database",
        )

    def _child(
        self,
        ledger: Ledger,
        claimed: Claimed,
        mission: packet_module.Packet,
        door: agent.Egress,
        lifetime: float,
        program_id: str,
    ) -> agent.AgentRunResult | None:
        """The one child, started inside the boundary with the one capability.

        No connection is passed to the launcher. It takes one only to record a
        startup refusal, and this caller records the whole attempt itself: a
        refusal here returns the Task through `finish_task_attempt` in the
        `finally` above, which is the same cleanup by a different name, and
        letting both run would be two closings racing over one row.
        """
        timeout = min(self.timeout, lifetime) if lifetime > 0 else self.timeout
        request = agent.AgentRunRequest(
            agent_run_id=claimed.agent_run_id,
            objective=claimed.objective(),
            container=self.boundary,
            role=claimed.role,
            program_id=program_id,
            packet=mission,
            egress=door,
            timeout=timeout,
            subagent_cap=claimed.subagent_cap,
        )
        try:
            result = self.launch(request)
        except agent.StartupRefusal as refusal:
            ledger.refuse(
                "startup_assertion",
                f"the child was refused in {refusal.phase} by "
                f"{len(refusal.violations)} vector(s)",
                agent.diagnostics(refusal).violations,
            )
            return None
        except isolation.Unavailable as error:
            ledger.fail(
                "boundary",
                f"the Agent boundary could not be provided: {error}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{IMAGE}",
            )
            return None
        ledger.hold(
            "agent_run",
            f"{claimed.agent_run_label} stopped as {stopped_as(result.stop_reason)} "
            f"after {result.answers} answer(s), {result.mission_attempts} submission(s)",
        )
        return result

    # -- what it produced --------------------------------------------------

    def _exchange(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        tool_run_id: str,
        facts: dict,
    ) -> str:
        """What the door recorded, and therefore how the Tool run closes."""
        rows = connection.execute(EXCHANGE, (program_id, tool_run_id)).rows
        if not rows:
            ledger.hold(
                "egress", "the capability was never spent; the door wrote no Receipt"
            )
            return "error"
        label, decision, status = str(rows[0][0]), str(rows[0][1]), rows[0][2]
        facts["receipt"] = {
            "label": label,
            "decision": decision,
            "status_code": None if status is None else int(status),
        }
        if decision != "allowed":
            ledger.fail(
                "egress",
                f"the door refused the child's request: {label} is {decision}",
                code=INVALID_CONFIGURATION,
                source="proxy",
            )
            return "denied"
        ledger.hold("egress", f"{label} records a {status} answer through the door")
        return "success"

    def _promote(
        self,
        ledger: Ledger,
        connection: pg.Connection,
        program_id: str,
        claimed: Claimed,
        result: agent.AgentRunResult,
        facts: dict,
    ) -> None:
        """Stage what the child submitted, then promote what grounds.

        Two calls and not one, because they answer different questions and both
        answers are worth keeping: staging records what was claimed and why each
        element was dropped, and promotion records what of the rest became
        canonical. A child that submitted nothing is not a failure to report
        here -- the Task simply does not close, which `finish_task_attempt`
        decides from the absence of a promoted proposal.

        Staging is given no cause and needs none: 0030 files `proposals` as an
        audit table -- "the commit it becomes is what emits" -- so the write
        emits no Event for a cause to name. `promote_proposal` sets its own,
        inside the transaction that writes the Observations, which is the only
        place one would survive to be read.

        The fingerprint is the third call and shares the second one's
        transaction: 022 asks for one after recon, and a promotion that
        committed without one would leave the Surface changed and nothing
        recording that it had.
        """
        if result.mission_result is None:
            ledger.hold(
                "proposal",
                f"{claimed.agent_run_label} submitted no result; nothing was staged",
            )
            return
        try:
            staged = proposal.stage(
                connection,
                proposal.Result(payload=dict(result.mission_result)),
                program_id=program_id,
                agent_run_id=claimed.agent_run_id,
                task_id=claimed.task_id,
            )
        except (pg.DatabaseError, ValueError, KeyError) as error:
            ledger.fail(
                "proposal",
                f"the submitted result could not be staged: {error}",
                code=INVALID_CONFIGURATION,
                source="agent",
            )
            return
        facts["proposal"] = {
            "id": staged.proposal_id,
            "label": staged.label,
            "status": staged.status,
            "completion": staged.completion,
            "drops": [
                {"element": drop.element_path, "reason": drop.reason}
                for drop in staged.drops
            ],
        }
        ledger.hold(
            "proposal",
            f"{staged.label} staged as {staged.completion} with {len(staged.drops)} drop(s)",
        )

        try:
            with connection.transaction():
                _actor(connection)
                connection.execute(CAUSE, (claimed.agent_run_id, claimed.task_id))
                promotion = proxy.as_object(
                    connection.execute(PROMOTE, (staged.proposal_id,)).scalar()
                )
                # In the same transaction, because "after recon" means after
                # the rows exist and before anything reads them: a fingerprint
                # taken in a later transaction would be a fingerprint of
                # whatever else had happened by then. 022 makes it one Event per
                # Application rather than a side effect of the promotion.
                swept = proxy.as_object(
                    connection.execute(FINGERPRINT).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "promotion",
                f"{staged.label} could not be promoted: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return
        observations = list(promotion.get("observations") or ())
        facts["promotion"] = {
            "status": promotion.get("status"),
            "repeated": bool(promotion.get("repeated")),
            "observations": observations,
            "refused": int(promotion.get("refused") or 0),
        }
        facts["fingerprint"] = {
            "applications": int(swept.get("applications") or 0),
            "changed": int(swept.get("changed") or 0),
        }
        ledger.hold(
            "promotion",
            f"{staged.label} is {promotion.get('status')}: {len(observations)} "
            f"Observation(s) canonical, {promotion.get('refused')} refused",
        )
        ledger.hold(
            "fingerprint",
            f"{facts['fingerprint']['applications']} Application(s) fingerprinted, "
            f"{facts['fingerprint']['changed']} changed",
        )

    def _finish(
        self, ledger: Ledger, connection: pg.Connection, claimed: Claimed, facts: dict
    ) -> dict | None:
        """The one call that ends the attempt, whatever happened above it.

        Its answer is the report's, not this runtime's opinion: the Task's
        status comes from whether a proposal was promoted, and a runtime that
        reported what it hoped for would be reporting the one thing the trigger
        exists to stop it deciding.
        """
        stop_reason = (facts.get("agent_run") or {}).get("stop_reason") or "error"
        try:
            with connection.transaction():
                _actor(connection)
                closure = proxy.as_object(
                    connection.execute(
                        FINISH, (claimed.agent_run_id, stop_reason)
                    ).scalar()
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "closure",
                f"the attempt on {claimed.task_label} could not be closed: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return None
        ledger.hold(
            "closure",
            f"{claimed.task_label} is {closure.get('task_status')}; "
            f"{closure.get('runs_closed')} run(s), {closure.get('tool_runs_closed')} "
            f"tool run(s) and {closure.get('leases_released')} lease(s) closed",
        )
        return closure


def _actor(connection: pg.Connection) -> None:
    """Who the database records as writing. Transaction-local by construction."""
    connection.execute("SELECT set_actor('runtime', $1)", (program.ACTOR,))


def _slate_entry(row: Mapping[str, object]) -> dict:
    """One entry of the offered Slate, renamed for whoever is choosing.

    `factors` arrives as the text of a jsonb value -- this client decodes
    booleans, integers and floats and leaves everything else exactly as the
    server sent it -- so it is parsed here rather than handed on as a string a
    reader would have to parse a second time. Everything else is passed through:
    a numeric that keeps its own digits is more faithful than a float that
    rounds them, and the expiry is already the timestamp the server rendered.
    """
    return {
        "ordinal": row["ordinal"],
        "task": row["task_label"],
        "kind": row["kind"],
        "subject": row["subject_label"],
        "priority": row["priority"],
        "factors": json.loads(str(row["factors"])),
        "entitled": row["entitled"],
        "expires_at": row["expires_at"],
    }
