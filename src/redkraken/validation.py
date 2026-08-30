"""`rk finding validate`: reproduce one candidate Finding and have it judged blind.

Three things happen here and the order between them is the whole point.

The claim is reopened and the Test is replayed. The run the Finding was born
from is the run its hunter produced, and a validator shown that run is being
asked whether the hunter's own evidence supports the hunter's own claim. So the
packet is built around a second run of the same Test, performed now, through the
same door, under the same Lane -- and if it does not hold, there is no packet to
serve. That is criterion 6's missing holding replay, and nothing in this file
decides it: `rk2_validation_refusal` reads the run and answers.

The session is opened with nothing in it. A validator gets one document and two
tools, and this module never assembles the document: `rk2_validation_packet`
builds it from a column allowlist, `open_validation_session` records the digest
of what it served, and what travels from here to the child is that jsonb
unchanged. There is no state packet, no egress and no capsule on the request --
not because a validator would misuse them, but because a field this module could
fill is a field a later edit could fill with a hunter's sentence.

The answer is filed as input. `record_verdict` decides what the Finding becomes
by rebuilding the packet and comparing digests, and this module reports what it
said. A child that answered nothing leaves `abandon_validation` to give the
Finding back to the candidates, because a Finding left `validating` by a crashed
session is a Finding that can never be validated again.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from redkraken import (
    agent,
    config,
    execution,
    isolation,
    migrate,
    pg,
    program,
    proxy,
    replay,
    roster,
)
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)


__all__ = ["COMMAND", "FACTS", "RUN", "run"]


COMMAND = "finding"
RUN = f"{COMMAND} validate"

#: What this command reports on every path, refused or performed.
FACTS = ("program_id", "program_slug", "finding", "reproduction", "validation")

BIND = "SELECT set_config('rk2.program_id', $1, false)"
FINDING = "SELECT id FROM findings WHERE program_id = $1::uuid AND label = $2"
REQUEST = "SELECT request_validation($1::uuid, $2::uuid)"
#: Read only where the request was refused, to tell "somebody else is holding
#: this Finding" from "this same ask is still open". Ticket 222.
QUEUED = (
    "SELECT state FROM validation_queue"
    " WHERE program_id = $1::uuid AND finding_id = $2::uuid"
)
REOPEN = "SELECT reopen_for_reproduction($1::uuid, $2::uuid)"
OPEN = "SELECT open_validation_session($1::uuid, $2::uuid, $3::uuid)"
RECORD = "SELECT record_verdict($1::uuid, $2::uuid, $3, $4::text[])"
ABANDON = "SELECT abandon_validation($1::uuid, $2::uuid, $3)"

#: The run the reproducing replay is performed under, opened here because on a
#: stopped Program nothing else can open one. Ticket 222: `open_test_replay`
#: refuses a run that has ended (`20260815T000000Z:1165-1168`), a run is open
#: only while a child is running, and a running child is the peer `one_peer`
#: refuses a second of -- so an operator naming a run names a finished one and
#: an operator running a hunt to get an open one cannot also start a validator.
#:
#: `proxy.py:3867-3870` in the same shape and for the same reason: an
#: operator-driven runtime action gets a run of its own, `orchestrator` is the
#: one role the roster lets execute no Task (`roles.executes_tasks` is false for
#: it, which is what lets `task_id` stay NULL), and `operator` is the model
#: because no model ran. Not a SQL verb: the guard a verb would add -- that the
#: Finding was asked about -- is the `request_validation` two statements above,
#: and a second copy of it is a second place the rule lives.
OPEN_REPRODUCTION = (
    "INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet)"
    " VALUES ($1::uuid, 'orchestrator', 'session', 'operator', 'low', $2::jsonb)"
    " RETURNING id::text, label"
)
#: Closed with what it spent, which is nothing: the replay's own requests are
#: charged to the Tool runs it opened, and a run left open is a run the next
#: pass's `reconcile_leases` closes as `error` -- so this closing is what keeps
#: the reproduction out of the next hunt's reconciliation report.
CLOSE_REPRODUCTION = (
    "UPDATE agent_runs SET finished_at = now(), stop_reason = $2,"
    " input_tokens = 0, output_tokens = 0"
    " WHERE id = $1::uuid AND finished_at IS NULL"
)

#: What the session is told to do, and the whole of it. Every noun in it is a
#: key of the packet, so a validator that read the objective and nothing else
#: would still not know what was claimed, by whom, or why anybody thought so.
#:
#: The label is the one thing it says that the packet also says. Both tools
#: require it and the roster closes their arguments, so a session that was not
#: told it could not make its first call at all -- and a label is an identifier
#: this runtime issued, not something anybody wrote to persuade a reader.
OBJECTIVE = (
    "You are given one document describing one attempted reproduction of {finding}, "
    "one web finding: what was requested, what came back, and which assertions the "
    "run evaluated. Read it with get_validation_packet, naming {finding}. Decide whether the "
    "document, on its own, demonstrates the behaviour its assertions describe. "
    "Answer once with submit_verdict: confirmed if the reproduction shows it, "
    "refuted if the reproduction shows it does not hold, insufficient if the "
    "document cannot settle it either way. Name in failed_assertion_ids every "
    "assertion identifier the document shows did not hold. You have no other "
    "tools, no network and no way to ask anyone; a document that does not "
    "settle the question is insufficient, not a reason to look further."
)


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    finding: str,
    agent_run: str | None = None,
    environment: Mapping[str, str],
    identity_slot: str | None = None,
    launch: Callable[[agent.AgentRunRequest], agent.AgentRunResult] = agent.agent_run,
    timeout: float = agent.TIMEOUT,
) -> Report:
    """Reproduce one candidate Finding, serve the packet, and file the answer."""
    ledger = Ledger()
    answers = _Answers(RUN)

    container, missing = execution.boundary(environment)
    if container is None:
        ledger.fail(
            "boundary",
            "a validator is a session in the Agent boundary and "
            f"{', '.join(missing)} describe(s) none",
            code=INVALID_CONFIGURATION,
            source=f"environment:{missing[0]}",
        )
        return _report(ledger, answers)
    ledger.hold(
        "boundary",
        f"the session runs in {container.image} on {container.network}, "
        f"whose one peer is {container.proxy_container}",
    )

    # Two addresses for one door, and this command needs both. Ticket 222:
    # `container.proxy_url` is `$RK_AGENT_PROXY_URL`, the name the door answers
    # to on the internal network, and it is what the validator's child is given.
    # The reproducing replay runs in this process, on the host, and the address
    # it may spend a capability at is `$RK_PROXY_URL` -- `execution.py:2460-2462`
    # states the same pair for the hunt's own replays. Handing the child's
    # address to the replay is what produced "rk2here-door is not a loopback
    # address; the capability is sent to this machine only".
    door = environment.get(proxy.PROXY_URL)
    if not door:
        ledger.fail(
            "door",
            "the reproducing replay runs on this machine and "
            f"${proxy.PROXY_URL} names no door for it; "
            f"${execution.PROXY_URL} is the address a child is given, not this one",
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.PROXY_URL}",
        )
        return _report(ledger, answers)
    ledger.hold("door", f"the reproduction spends its capability at {door}")

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, answers)
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        answers.program_id = program.resolve(ledger, connection, answers.slug)
        if answers.program_id is None:
            return _report(ledger, answers)
        connection.execute(BIND, (answers.program_id,))

        rows = connection.execute(FINDING, (answers.program_id, finding)).rows
        if not rows:
            ledger.fail(
                "finding",
                f"{finding} is not a Finding of this Program",
                code=INVALID_CONFIGURATION,
                source="argument:--finding",
            )
            return _report(ledger, answers)
        answers.finding = finding
        finding_id = str(rows[0][0])

        return _validate(
            ledger,
            answers,
            connection,
            runtime,
            configuration_path,
            container,
            finding_id=finding_id,
            agent_run=agent_run,
            identity_slot=identity_slot,
            door=door,
            launch=launch,
            timeout=timeout,
        )


def _validate(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    runtime: pg.Settings,
    configuration_path: Path,
    container: isolation.AgentContainer,
    *,
    finding_id: str,
    agent_run: str | None,
    identity_slot: str | None,
    door: str,
    launch: Callable[[agent.AgentRunRequest], agent.AgentRunResult],
    timeout: float,
) -> Report:
    """The three steps, once the Program and the Finding are known."""
    program_id = str(answers.program_id)

    # 011 built the queue as the ask and every verb below refuses a Finding
    # nobody asked about. Running this command is the ask: an operator naming
    # one Finding on the command line has said exactly what the queue records,
    # and the row is what makes the request visible to a second process and
    # refuses a second reproduction while this one is in flight.
    asked = _called(connection, REQUEST, (program_id, finding_id))
    if asked["outcome"] != "queued":
        # Ticket 222, criterion 4. `request_validation` writes a state and not a
        # log -- "011 made the row unique per Finding, so the queue is a state
        # and not a log" -- and `queued` is that state's word for asked and not
        # yet served. So a Finding already `queued` is this same ask, left by a
        # run of this command that did not reach a verdict, and re-running the
        # command continues it rather than making a second one. `running` still
        # refuses: that is a session holding the Finding, and `open_validation`
        # is what set it.
        state = connection.execute(QUEUED, (program_id, finding_id)).scalar()
        if str(state) != "queued":
            return _refused(ledger, answers, "request", str(asked["refusal"]))
        ledger.hold(
            "request",
            f"{answers.finding} was already queued for validation and this run continues it",
        )
    else:
        ledger.hold("request", f"{asked['finding']} is queued for validation")

    # The run before the claim, and that order is the whole of ticket 222's
    # second half. `reopen_for_reproduction` moves the claim out of `supported`
    # and there is no verb that moves it back without a Receipt, so anything
    # that can refuse has to refuse before it runs. Opening the run is the one
    # step left that can.
    run_id, run_label, opening = _reproduction_run(connection, program_id, agent_run)
    if run_id is None:
        return _refused(ledger, answers, "reproduction", opening)
    ledger.hold("reproduction", opening)

    reopened = _called(connection, REOPEN, (program_id, finding_id))
    if reopened["outcome"] != "reopened":
        if agent_run is None:
            _close_reproduction(connection, run_id, "refusal")
        return _refused(ledger, answers, "reproduction", str(reopened["refusal"]))
    ledger.hold(
        "reproduction",
        f"{reopened['hypothesis']} is {reopened['hypothesis_status']}, "
        f"so {reopened['test']} can be performed again",
    )

    stop = "aborted"
    try:
        performed = replay.run(
            runtime,
            configuration_path,
            agent_run=run_label,
            test=str(reopened["test"]),
            identity_slot=identity_slot,
            proxy_url=door,
            ca_file=container.certificate,
        )
        stop = "completed" if performed.ok else "error"
    finally:
        # Closed whatever the replay did, because the run exists to hold one
        # replay and a run left open is one the next pass reconciles as `error`.
        # Only where this command opened it: a run the operator named belongs to
        # whatever opened it, and ending it here would end that too.
        if agent_run is None:
            _close_reproduction(connection, run_id, stop)
    answers.reproduction = {
        "test": reopened["test"],
        "agent_run": run_label,
        **{key: performed.facts.get(key) for key in ("tool_run", "test_run")},
    }
    test_run = performed.facts.get("test_run")
    if not performed.ok or not isinstance(test_run, dict):
        # Ticket 222, criterion 3. The consequence is this command's to state --
        # no second run, no packet, a Finding that stays a candidate -- but the
        # reason is the replay's, and a report that gave only the consequence
        # sent an operator to a second ledger to find out what stopped it. The
        # replay's own violations are carried, not restated, so the sentence an
        # operator reads is the one the verb that refused actually wrote.
        said = f"{reopened['test']} was not reproduced, so there is nothing to judge"
        if performed.violations:
            ledger.refuse("reproduction", said, performed.violations)
        else:
            # `Report.ok` is `not violations`, so a replay that answered ok and
            # still produced no run has none to carry: without this the command
            # would record a failed assertion and exit 0.
            ledger.fail(
                "reproduction", said, code=INVALID_CONFIGURATION, source="test_run"
            )
        return _report(ledger, answers)

    opened = _called(connection, OPEN, (program_id, finding_id, test_run["id"]))
    if opened["outcome"] != "opened":
        return _refused(ledger, answers, "validation", str(opened["refusal"]))
    answers.validation = {
        "attempt": opened["attempt"],
        "agent_run": opened["agent_run"],
        "task": opened["task"],
        "packet_sha256": opened["packet_sha256"],
        "verdict": None,
        "failed": [],
        "outcome": "open",
    }
    ledger.hold(
        "validation",
        f"{opened['agent_run']} was served {opened['packet_sha256'][:12]}, "
        f"which is {_size(opened['packet'])} value(s) and nothing else",
    )

    return _judged(
        ledger,
        answers,
        connection,
        container,
        finding_id=finding_id,
        opened=opened,
        launch=launch,
        timeout=timeout,
    )


def _judged(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    container: isolation.AgentContainer,
    *,
    finding_id: str,
    opened: Mapping[str, object],
    launch: Callable[[agent.AgentRunRequest], agent.AgentRunResult],
    timeout: float,
) -> Report:
    """The session, and every way out of it.

    Written as one `try` with a `finally` for the reason `execution.Slice` has
    one: from the moment `open_validation_session` committed there is a Task
    claimed, a run open and a Finding saying it is being judged, and each of
    those is a row that outlives this process if nothing closes it.
    """
    program_id = str(answers.program_id)
    run_id = str(opened["agent_run_id"])
    result: agent.AgentRunResult | None = None
    filed = False
    try:
        result = _child(ledger, container, opened, run_id, program_id, launch, timeout)
        if result is not None and result.verdict is not None:
            filed = _file(
                ledger, answers, connection, program_id, finding_id, result.verdict
            )
    finally:
        _close(
            ledger, answers, connection, program_id, finding_id, run_id, result, filed
        )
    return _report(ledger, answers)


def _child(
    ledger: Ledger,
    container: isolation.AgentContainer,
    opened: Mapping[str, object],
    run_id: str,
    program_id: str,
    launch: Callable[[agent.AgentRunRequest], agent.AgentRunResult],
    timeout: float,
) -> agent.AgentRunResult | None:
    """One top-level session, holding the packet and nothing else."""
    cap = opened.get("token_cap")
    request = agent.AgentRunRequest(
        agent_run_id=run_id,
        objective=OBJECTIVE.format(finding=opened["finding"]),
        container=container,
        role=roster.VALIDATOR,
        program_id=program_id,
        judgement=opened["packet"],
        # The number the open reserved, not a second reading of the Program's
        # capacity: 026 reserves the worst case before the session starts, and a
        # child running under a ceiling the reservation does not know about is
        # the one case the reservation was supposed to make impossible.
        token_cap=None if cap is None else int(str(cap)),
        timeout=timeout,
    )
    try:
        result = launch(request)
    except agent.StartupRefusal as refusal:
        ledger.refuse(
            "session",
            f"the validator was refused in {refusal.phase} by "
            f"{len(refusal.violations)} vector(s)",
            agent.diagnostics(refusal).violations,
        )
        return None
    except isolation.Unavailable as error:
        ledger.fail(
            "session",
            f"the Agent boundary could not be provided: {error}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{execution.IMAGE}",
        )
        return None
    ledger.hold(
        "session",
        f"{opened['agent_run']} stopped as {execution.stopped_as(result.stop_reason)} "
        f"after {result.verdict_attempts} answer(s)",
    )
    return result


def _file(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    program_id: str,
    finding_id: str,
    verdict: Mapping[str, object],
) -> bool:
    """Hand the answer to the rules, and report what they made of it.

    Answers whether the rules took it, because that is what decides whether
    there is still an attempt open: `record_verdict` closes the attempt on the
    one path where it accepts the answer, and on every other path the Finding is
    still under judgement and `_close` has to give it back.
    """
    failed = [str(named) for named in verdict.get("failed_assertion_ids") or ()]
    answers.validation.update(verdict=verdict["verdict"], failed=failed)
    try:
        recorded = _called(
            connection,
            RECORD,
            (program_id, finding_id, str(verdict["verdict"]), pg.quote_array(failed)),
        )
    except pg.DatabaseError as error:
        # `record_verdict` answers a bad verdict with a sentence rather than an
        # exception, so arriving here means a rule below it raised. Caught
        # because the alternative is this process leaving with a Finding under
        # judgement: the raise took down the transaction that would have closed
        # the attempt, and `_close` is what gets it back.
        ledger.fail(
            "verdict",
            f"the verdict was refused by a rule: {error}",
            code=INVALID_CONFIGURATION,
            source="verdicts",
        )
        return False
    answers.validation["outcome"] = recorded["outcome"]
    if recorded["outcome"] == "answered":
        answers.validation["status"] = recorded["status"]
        ledger.hold(
            "verdict",
            f"{recorded['finding']} was judged {recorded['verdict']} "
            f"and is {recorded['status']}",
        )
        return True
    if recorded["outcome"] == "stale":
        ledger.fail(
            "verdict",
            f"{recorded['finding']} was judged on a packet that has changed "
            f"since; the word is kept on the attempt and nothing was done "
            f"with it",
            code=INVALID_CONFIGURATION,
            source="validation_attempts.packet_sha256",
        )
        return False
    ledger.fail(
        "verdict",
        f"the verdict was not recorded: {recorded['refusal']}",
        code=INVALID_CONFIGURATION,
        source="validation_attempts",
    )
    return False


def _close(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    program_id: str,
    finding_id: str,
    run_id: str,
    result: agent.AgentRunResult | None,
    filed: bool,
) -> None:
    """Give back the Finding, the run and the Task, on every path out.

    Best effort and silent about its own failures for `replay._closing`'s
    reason: whatever brought the caller here says more than a second refusal
    about the cleanup would, and a dropped connection is exactly the case where
    the cleanup cannot land either.

    Asked on every path but the filed one, because an answer the rules turned
    down leaves exactly what a crashed validator leaves: an open attempt, and a
    Finding that `open_validation` will not let anyone judge again.
    `abandon_validation` answers `nothing_open` where there is nothing to give
    back, so the paths that already closed themselves cost one statement.
    """
    answered = result is not None and result.verdict is not None
    try:
        if not filed:
            said = (
                "the validator was not started"
                if result is None
                else "the validator answered and the answer was not accepted"
                if answered
                else "the validator stopped as "
                f"{execution.stopped_as(result.stop_reason)} without answering"
            )
            given = _called(connection, ABANDON, (program_id, finding_id, said))
            # Only where nothing else has spoken for this Finding: when the
            # child did answer, `_file` reported what the rules made of it, and
            # a second violation about the same event would be counted twice.
            if given["outcome"] == "unanswered" and not answered:
                answers.validation.update(outcome="unanswered", refusal=said)
                ledger.fail(
                    "verdict",
                    said,
                    code=INVALID_CONFIGURATION,
                    source="validation_attempts",
                )
        usage = execution.spent(result)
        finished = _called(
            connection,
            # `execution.FINISH` rather than a second spelling here: this closing
            # settles the same columns the dispatch closing does, and a statement
            # written twice is eight columns that stay NULL for half the runs.
            execution.FINISH,
            (
                run_id,
                # `aborted` rather than a word for how it stopped, because a run
                # that never started did not stop: 019 keeps that word for a
                # supervisor that ended a session, which is what happened.
                "aborted" if result is None else execution.stopped_as(result.stop_reason),
                None if result is None else result.input_tokens,
                None if result is None else result.output_tokens,
                *execution.charged(usage),
                # A validation run is not a dispatch this runtime repeats, so it
                # has no attempt profile: ticket 165 counts budget ends on one
                # Task under one unchanged dispatch instruction.
                None,
            ),
        )
        answers.validation["task_status"] = finished["task_status"]
    except (pg.ConnectionError_, pg.DatabaseError, OSError) as error:
        ledger.fail(
            "cleanup",
            f"the validation could not be closed: {error}",
            code=INVALID_CONFIGURATION,
            source="validation_attempts",
        )


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    slug: str | None = None
    program_id: str | None = None
    finding: str | None = None
    reproduction: dict | None = None
    validation: dict = field(default_factory=dict)


def _reproduction_run(
    connection: pg.Connection, program_id: str, named: str | None
) -> tuple[str | None, str, str]:
    """The run the replay is performed under: the operator's, or a fresh one.

    Answers `(id, label, sentence)`, and a null id is a refusal in the sentence.

    A named run is still accepted, because the hunt does have open runs and an
    operator validating beside one is naming something real. It is checked here
    rather than left to `open_test_replay`, so that a run that has ended is
    refused before `reopen_for_reproduction` has moved the claim.
    """
    if named is not None:
        rows = connection.execute(
            "SELECT id::text, label, finished_at IS NULL FROM agent_runs"
            " WHERE program_id = $1::uuid AND label = $2",
            (program_id, named),
        ).rows
        if not rows:
            return None, "", f"{named} is not an agent run of this Program"
        if not rows[0][2]:
            return None, "", f"agent run {named} has already ended"
        return str(rows[0][0]), str(rows[0][1]), f"the replay is performed under {named}"
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
        rows = connection.execute(
            OPEN_REPRODUCTION, (program_id, json.dumps({"command": RUN}))
        ).rows
    label = str(rows[0][1])
    return (
        str(rows[0][0]),
        label,
        f"{label} was opened for the reproduction, which is what it holds",
    )


def _close_reproduction(connection: pg.Connection, run_id: str, stop: str) -> None:
    """End the run the replay was performed under, on every path out.

    Silent about its own failure for `_close`'s reason: whatever brought the
    caller here says more than a second refusal about the cleanup would. A run
    this misses is closed by the next pass's `reconcile_leases` as `error`,
    which is worse reporting and not a lost row.
    """
    try:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
            connection.execute(CLOSE_REPRODUCTION, (run_id, stop))
    except (pg.ConnectionError_, pg.DatabaseError, OSError):
        return


def _called(connection: pg.Connection, sql: str, parameters: tuple) -> dict:
    """One verb, in its own transaction, under the runtime's name."""
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
        answered = connection.execute(sql, parameters).scalar()
    return json.loads(str(answered))


def _size(packet: object) -> int:
    """How many leaves the served document has, for the ledger to state."""
    if isinstance(packet, Mapping):
        return sum(_size(value) for value in packet.values())
    if isinstance(packet, list):
        return sum(_size(value) for value in packet)
    return 1


def _refused(ledger: Ledger, answers: _Answers, name: str, refusal: str) -> Report:
    """A refusal the database filed, reported in the sentence it filed it in."""
    ledger.fail(name, refusal, code=INVALID_CONFIGURATION, source="argument:--finding")
    return _report(ledger, answers)


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        finding=answers.finding,
        reproduction=answers.reproduction,
        validation=answers.validation or None,
    )
