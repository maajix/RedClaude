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
REOPEN = "SELECT reopen_for_reproduction($1::uuid, $2::uuid)"
OPEN = "SELECT open_validation_session($1::uuid, $2::uuid, $3::uuid)"
RECORD = "SELECT record_verdict($1::uuid, $2::uuid, $3, $4::text[])"
ABANDON = "SELECT abandon_validation($1::uuid, $2::uuid, $3)"

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
    agent_run: str,
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
    agent_run: str,
    identity_slot: str | None,
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
        return _refused(ledger, answers, "request", str(asked["refusal"]))
    ledger.hold("request", f"{asked['finding']} is queued for validation")

    reopened = _called(connection, REOPEN, (program_id, finding_id))
    if reopened["outcome"] != "reopened":
        return _refused(ledger, answers, "reproduction", str(reopened["refusal"]))
    ledger.hold(
        "reproduction",
        f"{reopened['hypothesis']} is {reopened['hypothesis_status']}, "
        f"so {reopened['test']} can be performed again",
    )

    performed = replay.run(
        runtime,
        configuration_path,
        agent_run=agent_run,
        test=str(reopened["test"]),
        identity_slot=identity_slot,
        proxy_url=container.proxy_url,
        ca_file=container.certificate,
    )
    answers.reproduction = {
        "test": reopened["test"],
        "agent_run": agent_run,
        **{key: performed.facts.get(key) for key in ("tool_run", "test_run")},
    }
    test_run = performed.facts.get("test_run")
    if not performed.ok or not isinstance(test_run, dict):
        # The replay reported why on its own ledger and that report is not this
        # one's to restate. What is said here is the consequence: no second run,
        # no packet, and a Finding that stays a candidate.
        ledger.fail(
            "reproduction",
            f"{reopened['test']} was not reproduced, so there is nothing to judge",
            code=INVALID_CONFIGURATION,
            source="test_run",
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
