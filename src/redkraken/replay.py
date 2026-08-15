"""`rk test replay`: perform one Test through the door and record what it settled.

The runtime replaying a Test is not an agent acting, and this file is where that
distinction stops being a word. A browser mission or a subagent's request is
somebody deciding what to send; a replay sends what a Test specification already
said, in the order it said it, and reports which Receipt answered which planned
action. Nothing here chooses a url, a method or a role -- all three come out of
the plan `open_test_replay` hands back, and the only decision this file makes is
what to do when the door says no.

Three things follow from that, and they are the whole of this module.

The Lane is not passed anywhere. `open_test_replay` writes the row that makes
this Tool run a replay before it mints the capability, so every Receipt the door
files for it carries `replay` -- and if this file sent a request under a
capability minted some other way, `record_test_action` would refuse the Receipt
rather than record it under the wrong Lane.

The outcome is not decided here. `close_test_replay` derives it from the
Receipts, so a run that could not reach the target and a run whose assertions
failed are told apart by the database rather than by whatever this process
concluded. What this file contributes to the outcome is only which actions it
managed to record -- and an action it could not record leaves an assertion
unevaluated, which is what makes the run inconclusive.

The cleanup is reported honestly. A Test that created something and could not
remove it has left the target changed, and `skipped` and `failed` are different
facts about that: one means the run never got there, the other means it tried.

Ticket 38 added a second pair of verbs around the same walk, still in the
`replay` Lane and still under the same capability. A Test that states an
impact runs through `open_impact_replay`, which asks for an operator grant and
parks the Task when there is none, and closes through `close_impact_replay`,
which records a demonstration and settles nothing. Which pair of verbs is used
is the only difference: the plan, the door, the walk and the report are the
same, because what a replay does to the target is the same either way and the
difference is entirely in what may be concluded from it.
"""

from __future__ import annotations

import http.client
import json
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import config, migrate, pg, program, proxy, scope, tls
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)


__all__ = ["COMMAND", "DETECTION", "FACTS", "IMPACT", "RUN", "run"]


COMMAND = "test"
RUN = f"{COMMAND} replay"

#: What this command reports on every path, refused, parked or performed, so a
#: caller parses one document whichever happened.
FACTS = ("program_id", "program_slug", "tool_run", "test_run", "decision")

BIND = "SELECT set_config('rk2.program_id', $1, false)"
AGENT_RUN = "SELECT id FROM agent_runs WHERE program_id = $1::uuid AND label = $2"
TEST = "SELECT id FROM tests WHERE program_id = $1::uuid AND label = $2"
RECORD = "SELECT record_test_action($1::uuid, $2::integer, $3)"

#: The three words either close verb admits for what became of the cleanup.
DONE, FAILED, SKIPPED = "done", "failed", "skipped"


@dataclass(frozen=True)
class _Verbs:
    """The pair of verbs one replay is opened and closed by.

    Both pairs answer the same two documents -- a plan to walk and a reading of
    what the walk produced -- so nothing below this declaration asks which one
    it is running. What differs is entirely inside the database: one settles a
    claim, the other proves an impact under a grant and settles nothing.
    """

    open_sql: str
    close_sql: str


DETECTION = _Verbs(
    "SELECT open_test_replay($1::uuid, $2::uuid, $3)",
    "SELECT close_test_replay($1::uuid, $2, $3)",
)
IMPACT = _Verbs(
    "SELECT open_impact_replay($1::uuid, $2::uuid, $3)",
    "SELECT close_impact_replay($1::uuid, $2, $3)",
)


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    agent_run: str,
    test: str,
    identity_slot: str | None,
    proxy_url: str,
    ca_file: Path | None = None,
    verbs: _Verbs = DETECTION,
) -> Report:
    """Perform one Test for one agent run, and file the run it produced."""
    ledger = Ledger()
    answers = _Answers(RUN)

    try:
        listener = proxy.endpoint(proxy_url)
    except proxy.Refused as refusal:
        ledger.fail(
            "proxy_endpoint",
            refusal.detail,
            code=INVALID_CONFIGURATION,
            source=f"environment:{proxy.PROXY_URL}",
        )
        return _report(ledger, answers)
    ledger.hold(
        "proxy_endpoint",
        f"every request this Test makes goes to {listener[0]}:{listener[1]} and nowhere else",
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

        run_id = _id_of(connection, AGENT_RUN, answers.program_id, agent_run)
        if run_id is None:
            ledger.fail(
                "agent_run",
                f"{agent_run} is not an agent run of this Program",
                code=INVALID_CONFIGURATION,
                source="argument:--agent-run",
            )
            return _report(ledger, answers)
        test_id = _id_of(connection, TEST, answers.program_id, test)
        if test_id is None:
            ledger.fail(
                "test",
                f"{test} is not a Test of this Program",
                code=INVALID_CONFIGURATION,
                source="argument:--test",
            )
            return _report(ledger, answers)

        # Everything that decides whether this Test may run at all -- the Halt,
        # the claim's status, the scope of every url it names, the Identity
        # lease, the budget and the risk gate -- happens here, in the database,
        # and commits before a request is sent.
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                plan = json.loads(
                    str(
                        connection.execute(
                            verbs.open_sql, (run_id, test_id, identity_slot)
                        ).scalar()
                    )
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "plan",
                f"the registry refused this replay: {_said(error)}",
                code=INVALID_CONFIGURATION,
                source="argument:--test",
            )
            return _report(ledger, answers)

        # Ticket 38 criterion 2. An impact Test with no live grant parks its
        # Task and opens nothing: there is no Tool run, so there is no
        # capability, so nothing below this line could have reached the target.
        # It is a hold and not a violation -- the harness did the right thing,
        # and what it is waiting for is a person.
        if "tool_run_id" not in plan:
            answers.decision = {
                "label": plan["parked"],
                "question": plan["question"],
                "task": plan["task"],
                "test": plan["test"],
                "finding": plan["finding"],
                "impact_class": plan["impact_class"],
                "risk_class": plan["risk_class"],
            }
            ledger.hold(
                "authorization",
                f"{plan['refusal']}: {plan['task']} is parked as {plan['parked']} "
                f"and nothing was sent",
            )
            return _report(ledger, answers)

        answers.tool_run = {
            "label": plan["tool_run"],
            "test": plan["test"],
            "spec_sha256": plan["spec_sha256"],
            "identity_slot": plan["identity_slot"],
            "methods": plan["methods"],
            "actions": len(plan["actions"]),
            "status": "running",
        }
        ledger.hold(
            "plan",
            f"{plan['tool_run']} opened for {plan['test']}: "
            f"{len(plan['actions'])} action(s), {', '.join(plan['methods'])}",
        )
        for stated in plan["preconditions"]:
            ledger.hold(f"precondition:{stated['kind']}", str(stated["detail"]))

        # From here the row is open and committed, so every way out closes it.
        capability = plan.get("capability")
        if not capability:
            return _abandon(
                ledger, answers, connection, verbs, plan,
                f"the risk gate answered {plan.get('decision')} rather than allow",
                name="capability", cleanup=SKIPPED, source="risk_gate",
            )
        ledger.hold("capability", f"the risk gate allowed {plan['tool_run']}")

        try:
            trust, missing = _trust(plan, ca_file)
        except (OSError, ssl.SSLError) as error:
            return _abandon(
                ledger, answers, connection, verbs, plan,
                f"the door's certificate at {ca_file} cannot be used: {error}",
                name="trust_root", cleanup=SKIPPED, source="argument:--ca",
            )
        if missing is not None:
            return _abandon(
                ledger, answers, connection, verbs, plan, missing,
                name="trust_root", cleanup=SKIPPED, source="argument:--ca",
            )
        if trust is not None:
            ledger.hold(
                "trust_root",
                f"every tunnel is verified against {ca_file} and nothing else",
            )

        # The door's own default. A per-request ceiling would be a number this
        # module chose and the plan did not, and the plan is where everything
        # else about a request comes from.
        door = _Door(listener, str(capability), answers.program_id, proxy.TIMEOUT, trust)
        try:
            performed = _perform(ledger, connection, plan, door)
        except BaseException as error:
            _closing(
                connection, verbs, plan, SKIPPED,
                f"the supervisor could not finish it: {error!r}",
            )
            raise

        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                closed = json.loads(
                    str(
                        connection.execute(
                            verbs.close_sql,
                            (plan["tool_run_id"], performed.cleanup, performed.detail),
                        ).scalar()
                    )
                )
        except pg.DatabaseError as error:
            return _abandon(
                ledger, answers, connection, verbs, plan,
                f"what this replay recorded was refused: {_said(error)}",
                name="outcome", cleanup=performed.cleanup, source="test_run",
            )

    answers.tool_run.update(status=closed["status"], recorded=performed.recorded)
    answers.test_run = {
        "id": closed["test_run_id"],
        "outcome": closed["outcome"],
        "failed": closed["failed"],
        "cleanup": closed["cleanup"],
        "actions": closed["actions"],
        "hypothesis_status": closed["hypothesis_status"],
        "demonstration": closed.get("demonstration"),
    }
    _conclude(ledger, plan, closed)
    return _report(ledger, answers)


@dataclass(frozen=True)
class _Door:
    """Where a request goes and what it carries, for the length of one replay."""

    listener: tuple[str, int]
    capability: str
    program_id: str
    timeout: float
    trust: ssl.SSLContext | None

    def send(self, request: Mapping[str, object]) -> proxy.Answer:
        return proxy.spend(
            self.listener,
            str(request["url"]),
            capability=self.capability,
            program_id=self.program_id,
            method=str(request["method"]),
            timeout=self.timeout,
            trust=self.trust,
        )


@dataclass
class _Performed:
    """What the walk managed to do, in the terms the close is told in."""

    recorded: int = 0
    cleanup: str = SKIPPED
    detail: str | None = None


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    slug: str | None = None
    program_id: str | None = None
    tool_run: dict | None = None
    test_run: dict | None = None
    decision: dict | None = None


def _perform(
    ledger: Ledger,
    connection: pg.Connection,
    plan: Mapping[str, object],
    door: _Door,
) -> _Performed:
    """Setup, then the actions, then the cleanup -- in that order, always.

    The cleanup runs whatever the actions did, including when they refused or
    failed, because a Test that changed something has changed it whether or not
    its assertions could be evaluated. The one case it does not run is a setup
    that did not complete, and then nothing was created for it to undo.
    """
    performed = _Performed()

    refused = _requests(ledger, plan["setup"], door, "setup")
    if refused is not None:
        performed.detail = refused
        return performed

    for action in plan["actions"]:
        answer, problem = _sent(door, action)
        if problem is not None:
            # Recorded as a hold rather than a violation: an action the door
            # refused is a fact about this Test, and the run it produces says so
            # by being inconclusive. Failing the command here as well would
            # report the same thing twice under two different words.
            ledger.hold(
                f"action:{action['ordinal']}",
                f"the {action['role']} action was not performed: {problem}",
            )
            continue
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                connection.execute(
                    RECORD, (plan["tool_run_id"], int(action["ordinal"]), answer.receipt)
                )
        except pg.DatabaseError as error:
            ledger.hold(
                f"action:{action['ordinal']}",
                f"the {action['role']} action was not recorded: {_said(error)}",
            )
            continue
        performed.recorded += 1
        ledger.hold(
            f"action:{action['ordinal']}",
            f"the {action['role']} action answered {answer.status} "
            f"and is on record as {answer.receipt}",
        )

    refused = _requests(ledger, plan["cleanup"], door, "cleanup")
    performed.cleanup = FAILED if refused is not None else DONE
    performed.detail = refused
    return performed


def _requests(
    ledger: Ledger,
    requests: Sequence[Mapping[str, object]],
    door: _Door,
    part: str,
) -> str | None:
    """The setup or the cleanup, and the first thing that went wrong in it.

    Neither part is evidence -- no Receipt of theirs is ever tied to an action --
    so nothing is recorded for them beyond whether they worked. The first failure
    stops the part, because a cleanup whose second step depends on its first has
    nothing to do once the first did not happen.
    """
    for ordinal, request in enumerate(requests, start=1):
        _, problem = _sent(door, request)
        if problem is not None:
            said = f"{part} request {ordinal} did not go through: {problem}"
            ledger.hold(part, said)
            return said
    if requests:
        ledger.hold(part, f"{len(requests)} {part} request(s) went through")
    return None


def _sent(door: _Door, request: Mapping[str, object]) -> tuple[proxy.Answer | None, str | None]:
    """One request at the door, and what stopped it if something did.

    A refusal, an unreachable target and an answer the door filed no Receipt for
    are three different things and all three end the same way here: no Receipt to
    record, so nothing to tie to the plan. Which of them it was goes into the
    ledger, because it is the difference between a Test that was turned down and
    a Test whose target was down.
    """
    try:
        answer = door.send(request)
    except scope.PolicyError as error:
        return None, f"the url is not one this harness sends: {error.detail}"
    except (OSError, http.client.HTTPException) as error:
        return None, f"the door did not answer: {error}"
    if answer.decision is not None:
        return answer, (
            f"the door refused it as {answer.decision}: {answer.detail or 'no reason given'}"
        )
    if answer.receipt is None:
        return answer, f"the door answered {answer.status} without naming a Receipt"
    return answer, None


def _trust(
    plan: Mapping[str, object], ca_file: Path | None
) -> tuple[ssl.SSLContext | None, str | None]:
    """The root an intercepted tunnel is verified against, when one is needed.

    The door presents a certificate for a host it does not own, which is what
    interception is, and believing it on any other ground would make this
    process indifferent to who was on the path. No default and no fallback to
    the system store: a Test that reaches an https url without a root here is
    refused before it sends anything.

    Answers the root and what is missing, and writes to no ledger. The caller is
    the one that has to close the replay this refusal ends, and a refusal filed
    here as well would report one cause under two names.
    """
    if not any(
        str(request["url"]).startswith("https://")
        for part in ("setup", "actions", "cleanup")
        for request in plan[part]
    ):
        return None, None
    if ca_file is None:
        return None, (
            f"this Test reaches an https target: pass --ca or set {proxy.CA_VARIABLE}"
        )
    return tls.trust(ca_file), None


def _conclude(ledger: Ledger, plan: Mapping[str, object], closed: Mapping[str, object]) -> None:
    """What the run settled, as the one line an operator reads.

    A refutation is not a failure of this command. The Test ran, the door let it
    through and the claim is answered -- so `refutes` holds and says which
    assertions did not, while `inconclusive` fails, because a Test that settled
    nothing is a Test somebody has to run again.

    A conclusion the epistemic machine refused is the same fact reached the other
    way: every assertion held and the claim still does not carry the verdict, so
    it fails too, carrying the refusal that says what the Test would need.

    An impact run that held and demonstrated nothing anyway is the third shape
    of the same thing, and it arrives under the other name the two close verbs
    withhold their conclusion under. A held claim on that path is not a result:
    an impact run settles nothing, and the status reported for the claim is the
    one it already had.
    """
    outcome = str(closed["outcome"])
    withheld = closed.get("settle_refused") or closed.get("demonstration_refused")
    said = (
        f"{plan['test']} {outcome} over {closed['actions']} action(s); "
        f"the claim is {closed['hypothesis_status']}"
    )
    if withheld:
        said += f", because {withheld}"
    if closed.get("demonstration"):
        said += f"; the impact is demonstrated by {closed['demonstration']}"
    failed = list(closed["failed"])
    if failed:
        said += f"; failed: {', '.join(failed)}"
    if closed["cleanup"] != DONE:
        said += f"; cleanup {closed['cleanup']}"
    if outcome == "inconclusive" or withheld:
        ledger.fail("run", said, code=INVALID_CONFIGURATION, source="test_run")
    else:
        ledger.hold("run", said)


def _id_of(connection: pg.Connection, sql: str, program_id: str, label: str) -> str | None:
    rows = connection.execute(sql, (program_id, label)).rows
    return str(rows[0][0]) if rows else None


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        tool_run=answers.tool_run,
        test_run=answers.test_run,
        decision=answers.decision,
    )


def _abandon(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    verbs: _Verbs,
    plan: Mapping[str, object],
    detail: str,
    *,
    name: str,
    cleanup: str,
    source: str,
) -> Report:
    """Close a replay that cannot go on, and say why.

    An open replay whose Tool run ended is the one state `check_test_replays`
    reports as a fault rather than as history, so the row is closed carrying its
    reason. It closes as inconclusive by derivation rather than by assertion: a
    replay that got this far recorded no action, so there is nothing for
    `evaluate_test_assertions` to read and nothing it could conclude.
    """
    answers.tool_run.update(
        status=_closing(connection, verbs, plan, cleanup, detail), detail=detail
    )
    ledger.fail(name, detail, code=INVALID_CONFIGURATION, source=source)
    return _report(ledger, answers)


def _closing(
    connection: pg.Connection,
    verbs: _Verbs,
    plan: Mapping[str, object],
    cleanup: str,
    detail: str,
) -> str:
    """Close an open replay on the way out of a failure, best effort.

    Answers with the status the Tool run ended on, which is the row's own word
    and not this module's: a report that said `abandoned` would be naming a
    state no `tool_runs` row can be in. `running` is the honest answer when the
    close did not land, because that is what the row still says.

    Deliberately silent when it fails: the caller is already carrying a reason
    that says more than this one would, and a connection that has just dropped is
    exactly the case where the close cannot land.
    """
    try:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
            closed = connection.execute(
                verbs.close_sql, (plan["tool_run_id"], cleanup, detail)
            ).scalar()
    except (pg.ConnectionError_, pg.DatabaseError, OSError):
        return "running"
    return str(json.loads(str(closed))["status"])


def _said(error: pg.DatabaseError) -> str:
    """What the database refused with, in the sentence it refused in."""
    return error.primary or str(error)
