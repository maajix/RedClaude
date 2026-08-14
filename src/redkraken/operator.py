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
HALT = "halt"
RESUME = "resume"

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
HALT_PROGRAM = "SELECT halt_program($1::uuid, $2)"
CLEAR_HALT = "SELECT clear_program_halt($1::uuid, $2)"

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
            "operator connection may answer a question or lift a Halt",
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
