"""The operator's half of the human control loop.

Ticket 11 files a question and parks the work behind it. Ticket 13 Halts a whole
Program. Both wrote their verbs into the corpus and neither gave a person any way
to reach them: `rk decision sweep` tends the queue as the runtime -- it retires
deadlines and carries notifications -- and there was no command at all that
answered a question, withdrew one, or lifted a Halt. An operator's only route was
`psql`.

Which is why this module exists and why it is separate from `decisions.py`. The
two are the same queue seen from the two sides the design is built on: the sweep
runs as `rk2_runtime` and may not read a word an operator wrote, this runs as
`rk2_human` and is the only connection that may. One module holding both would be
one connection string holding both, and the separation those two roles buy is the
reason a model's own tool call cannot answer the question it raised.

Every verb here is the database's. Nothing in this file decides whether an answer
is still valid, whether a Task may move or whether a Halt may lift -- it names the
Program, calls the verb and reports what came back. A second opinion in Python
would be a second answer, and the one an operator could reach from a shell.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from redkraken import migrate, pg, program
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report

LIST = "decision list"
ANSWER = "decision answer"
SUPERSEDE = "decision supersede"
GRANT_ROUTE = "decision grant-route"
REVOKE_ROUTE = "decision revoke-route"
HALT = "halt"
RESUME = "resume"
REPORT = "finding report"
CLEAR = "finding clear-gate"

#: Membership of `rk2_human` is the whole authorisation: every operator verb asks
#: `human_actor_session()` for it and refuses without it. Named here so a wrong
#: connection string is one refusal before the verb rather than a permission
#: error out of the middle of one. Spelled with its argument list because
#: `to_regprocedure` wants one.
OPERATOR_ASSERTION = "human_actor_session()"
OPERATOR = "SELECT human_actor_session(), current_user"

#: The queue, filtered in the database. `program` is a slug and `$2` is whether
#: closed questions are wanted: an operator reading yesterday's decisions is
#: reading the same rows through the same view.
#:
#: `answer` is the operator's own free text, and this is the one place it is read
#: back. Write-only means write-only to the runtime and to every model behind it:
#: the column grant refuses it to `rk2_runtime`, the view is `security_invoker`,
#: and this connection is the operator's. A queue that showed a closed question
#: without the sentence its answer turned on would leave the person who wrote
#: that sentence with `psql` as the only way to read what they decided.
QUEUE = (
    "SELECT program, label, question_code, tool, risk_class, question,"
    "       requested_at::text, deadline_at::text, status, answered_by, answer"
    "  FROM v_decision_queue"
    " WHERE ($1::text IS NULL OR program = $1)"
    "   AND ($2::boolean OR status = 'pending')"
    " ORDER BY requested_at, program, label"
)

BIND = "SELECT set_config('rk2.program_id', $1, false)"
ANSWER_DECISION = "SELECT answer_decision($1, $2, $3, $4::interval)"
SUPERSEDE_DECISION = "SELECT supersede_decision($1, $2)"
GRANT_ROUTE_SQL = "SELECT grant_route($1, $2::numeric, $3)"
REVOKE_ROUTE_SQL = "SELECT revoke_route_grant($1, $2)"
HALT_PROGRAM = "SELECT halt_program($1::uuid, $2)"
CLEAR_HALT = "SELECT clear_program_halt($1::uuid, $2)"
REPORT_FINDING = "SELECT report_finding($1, $2::uuid, $3, $4)"
CLEAR_REVIEW_GATE = "SELECT clear_review_gate($1, $2, $3)"

#: How long an approval is good for when the operator does not say. The database
#: defaults to the same 24 hours; it is spelled again here because the flag has
#: to show a value in `--help`, and a help text reading "the database decides"
#: would send an operator off to read a function body.
DEFAULT_GRANT_HOURS = 24.0


def queue(human: pg.Settings | None, *, slug: str | None = None, closed: bool = False) -> Report:
    """What the operator has been asked, and what they have answered.

    Open questions only unless `closed` is set. A queue that showed every
    decision ever made would bury the ones that are stopping work, and stopping
    work is the only reason a question is in it.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"questions": [], "open": 0}
    connection = migrate.open_connection(ledger, human)
    if connection is None:
        return report(LIST, ledger, **facts)
    with connection:
        if not assert_operator_connection(ledger, connection):
            return report(LIST, ledger, **facts)
        questions = [dict(row) for row in connection.execute(QUEUE, (slug, closed)).dicts()]
        facts["questions"] = questions
        facts["open"] = sum(1 for row in questions if row["status"] == "pending")
        ledger.hold(
            "decision_queue",
            f"{facts['open']} question(s) waiting on an operator"
            + (f", of {len(questions)} shown" if closed else ""),
        )
    return report(LIST, ledger, **facts)


def answer(
    human: pg.Settings | None,
    slug: str,
    label: str,
    *,
    approve: bool,
    reason: str,
    grant_hours: float = DEFAULT_GRANT_HOURS,
) -> Report:
    """Approve or deny one question, and let the Task move.

    Approval is the direction that can do damage, so approval is the direction
    the database revalidates: an answer given a day after the question was filed
    is an answer about a request whose classification may have changed
    underneath it. That refusal arrives here as a database error and is reported
    as what it is -- a decision this operator can still make, under a
    configuration they now have to look at -- and not as a command that crashed.
    """
    verdict = "approved" if approve else "denied"
    return _verb(
        ANSWER,
        human,
        slug,
        lambda connection, _: connection.execute(
            ANSWER_DECISION, (label, verdict, reason, f"{grant_hours} hours")
        ),
        held=f"{label} was {verdict}",
        refused=f"{label} was not {verdict}",
        label=label,
        verdict=verdict,
    )


def supersede(human: pg.Settings | None, slug: str, label: str, *, reason: str) -> Report:
    """Withdraw one question instead of answering it.

    The verb to reach for after changing the configuration a question was asked
    under: no grant is issued, the Task goes back to pending, and what resolves
    it next is a fresh gate verdict under the policy in force then.
    """
    return _verb(
        SUPERSEDE,
        human,
        slug,
        lambda connection, _: connection.execute(SUPERSEDE_DECISION, (label, reason)),
        held=f"{label} was withdrawn",
        refused=f"{label} was not withdrawn",
        label=label,
    )


def grant_route(
    human: pg.Settings | None,
    slug: str,
    label: str,
    *,
    reason: str,
    hours: float,
) -> Report:
    """Widen one approved decision into a standing grant over its route.

    The verb to reach for when the same question keeps arriving. A call opened
    body-bearing carries a nonce in its digest -- the bytes are chosen after the
    row is written -- so its equivalence key matches nothing and the approval
    given an hour ago cannot answer it. Four approvals went on one OAuth token
    endpoint on `rk2here` in a single day, each one halting the campaign.

    A label rather than a route, and that is the safety property: the route, the
    rule and the identity all come from the digest the runtime built, so an
    operator can widen a question they answered yes to and cannot manufacture
    one they were never asked.
    """
    return _verb(
        GRANT_ROUTE,
        human,
        slug,
        lambda connection, _: connection.execute(
            GRANT_ROUTE_SQL, (label, hours, reason)
        ),
        held=f"{label} was widened into a route grant",
        refused=f"{label} was not widened",
        label=label,
        hours=hours,
    )


def revoke_route(human: pg.Settings | None, slug: str, label: str, *, reason: str) -> Report:
    """Withdraw a standing route grant before it expires.

    The other direction, and the reason a grant may be left standing at all: an
    operator who changes their mind does not have to wait for an expiry.
    """
    return _verb(
        REVOKE_ROUTE,
        human,
        slug,
        lambda connection, _: connection.execute(REVOKE_ROUTE_SQL, (label, reason)),
        held=f"{label} was revoked",
        refused=f"{label} was not revoked",
        label=label,
    )


def halt(human: pg.Settings | None, slug: str, *, reason: str) -> Report:
    """Halt a Program: no egress and no new work until an operator lifts it."""
    return _verb(
        HALT,
        human,
        slug,
        lambda connection, identifier: connection.execute(HALT_PROGRAM, (identifier, reason)),
        held=f"{slug} is halted",
        refused=f"{slug} was not halted",
    )


def resume(human: pg.Settings | None, slug: str, *, reason: str) -> Report:
    """Lift a Halt.

    Lifting it is all this does. What the runtime has to put back afterwards --
    Tasks whose lease died while the Program was Halted, receipts nobody closed
    -- is `resume_program`, which runs at the next `rk run` and runs as the
    runtime, because every row it writes is the runtime's own recovery and not a
    claim about what a person decided.
    """
    return _verb(
        RESUME,
        human,
        slug,
        lambda connection, identifier: connection.execute(CLEAR_HALT, (identifier, reason)),
        held=f"the Halt on {slug} is cleared",
        refused=f"the Halt on {slug} was not cleared",
    )


def report_finding(
    human: pg.Settings | None,
    slug: str,
    label: str,
    rendering: str,
    digest: str,
    *,
    reason: str,
) -> Report:
    """Report one validated Finding, naming the rendering the operator read.

    The last step of the harness, and the one the corpus had no caller for:
    `transition_rules` has reserved `validated -> reported` for a human actor
    since ticket 06 and nothing in the runtime may write that row. What makes
    this an operator verb rather than a convenience is the rendering: the
    approval names exact bytes, so "I approved this report" cannot later mean a
    document the Finding has since been re-rendered into.

    The digest is the confirmation, and it is the one this verb can ask for
    honestly. There is no step after this one -- `reported` is terminal in
    `transition_rules` and a clearance cannot be withdrawn -- so the guard is not
    "are you sure" but "which bytes", and an id pasted out of a script that filed
    a rendering nobody opened does not answer it.

    Every gate stays the database's. This adds none and lifts none -- a Finding
    still blocked by anything `report_blockers` raises is refused here, and the
    sentence it is refused with is the blocker's own.
    """
    return _verb(
        REPORT,
        human,
        slug,
        lambda connection, _: connection.execute(
            REPORT_FINDING, (label, rendering, digest, reason)
        ),
        held=f"{label} was reported",
        refused=f"{label} was not reported",
        label=label,
        rendering=rendering,
    )


def clear_gate(human: pg.Settings | None, slug: str, label: str, gate: str, *, reason: str) -> Report:
    """Lift one review gate on one Finding, and do nothing else.

    Separate from `report_finding` because it answers a different question.
    Reporting asks "send this one"; clearing asks "the program's do-not-send
    list does not mean this instance", which is a reading of somebody else's
    words that outlives the Finding it was made on. Two verbs mean the operator
    says both things out loud, and the record carries what each of them was told
    at the time.

    Only the two judgement blockers can be reached this way. The other seven are
    facts the database computed, and the refusal for those names the whole set
    rather than the one that was asked for.
    """
    return _verb(
        CLEAR,
        human,
        slug,
        lambda connection, _: connection.execute(CLEAR_REVIEW_GATE, (label, gate, reason)),
        held=f"the {gate} gate on {label} is lifted",
        refused=f"the {gate} gate on {label} was not lifted",
        label=label,
        gate=gate,
    )


def assert_operator_connection(ledger: Ledger, connection: pg.Connection) -> bool:
    """Refuse anything but the operator's connection, before the verb.

    The database asks this question itself inside every verb, so this is not the
    guard -- it is the same question one step earlier, where the answer can be a
    report an operator acts on instead of a permission error raised out of a
    function they did not know they were calling.
    """
    if not connection.execute(
        "SELECT to_regprocedure($1) IS NOT NULL", (OPERATOR_ASSERTION,)
    ).scalar():
        ledger.fail(
            "operator_connection",
            "this database carries no operator assertion; run `rk db migrate`",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return False
    human, user = connection.execute(OPERATOR).rows[0]
    if not human:
        ledger.fail(
            "operator_connection",
            f"connected as {user}, which is not a member of rk2_human: only the "
            "operator connection may answer a question, lift a Halt or report a Finding",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return False
    ledger.hold("operator_connection", f"connected as {user}")
    return True


def _verb(
    command: str,
    human: pg.Settings | None,
    slug: str,
    call: Callable[[pg.Connection, str], pg.Result],
    *,
    held: str,
    refused: str,
    **facts: object,
) -> Report:
    """Name a Program, run one operator verb against it, report what it said.

    Every verb in this module is this shape: connect as the operator, resolve the
    slug a person typed, bind it, call one function and unpack one jsonb. It is
    written once because the four differ only in which function they call and in
    what a failure of it should be called -- and a refusal that read differently
    depending on which verb produced it would be four documents to learn instead
    of one.

    The Program is both bound and passed. The decision verbs resolve a label
    inside the session's Program because labels are counted per Program, and the
    Halt verbs take the Program as an argument; handing the same identifier to
    both is what keeps those two spellings from ever meaning different Programs.
    """
    ledger = Ledger()
    facts = {"program": slug, **facts, "result": None}
    connection = migrate.open_connection(ledger, human)
    if connection is None:
        return report(command, ledger, **facts)
    with connection:
        if not assert_operator_connection(ledger, connection):
            return report(command, ledger, **facts)
        identifier = program.resolve(ledger, connection, slug)
        if identifier is None:
            return report(command, ledger, **facts)
        connection.execute(BIND, (identifier,))
        name = command.replace(" ", "_")
        try:
            answered = call(connection, identifier)
        except pg.DatabaseError as error:
            ledger.fail(
                name,
                f"{refused}: {_said(error)}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(command, ledger, **facts)
        facts["result"] = _document(answered.scalar())
        ledger.hold(name, held)
    return report(command, ledger, **facts)


def _said(error: pg.DatabaseError) -> str:
    """One database refusal as one sentence, with its hint if it carried one.

    The hint is where the corpus writes the operator's next move -- deny it,
    supersede it, go and look at what changed -- and dropping it would leave a
    person holding a refusal and no way forward.
    """
    hint = error.fields.get("H")
    return f"{error}. {hint}" if hint else str(error)


def _document(value: object) -> object:
    """One verb's `jsonb` answer, as the object it already is.

    `pg` hands back text for everything it does not recognise, and a report is
    rendered with `json.dumps`. Parsing here rather than there is what keeps the
    verb's own answer readable in the output instead of arriving as one escaped
    string an operator has to unescape by eye.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value
