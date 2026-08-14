"""The process that tends the queue the human control loop leaves behind.

Ticket 11 splits one decision across two clocks. The gate answers `ask`, the
door files the question and stops; from there on the question has a deadline it
will pass on its own and a notification that has to be carried to a human by
something outside the database. The corpus provides all three verbs for that --
`expire_due_decisions`, `due_notifications`, `record_notification_attempt` --
and until this module nothing called any of them, which left both clocks
stopped: an unanswered question sat pending for ever, and the notification sat
in its queue undelivered.

Both failures are already invariants. `check_control_surface` makes a decision
past its deadline that nothing swept a standing failure, and makes an open
question that no channel will ever try again one too. So this command is not
where either rule is written -- it is the thing that keeps them true, and it
asks the database itself whether it succeeded rather than forming its own
opinion.

It runs as the runtime. `rk2_runtime` is the role the corpus granted the queue
to; the door holds `rk2_proxy`, which can reach none of it, and that separation
is deliberate enough that this sweep gets its own process rather than a thread
inside the fence.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from redkraken import migrate, pg, program
from redkraken.outcome import INTEGRITY_FAILED, Ledger, Report, report

COMMAND = "decision sweep"

#: Retire the questions whose deadline passed. Program-wide by argument and
#: machine-wide here: the check this satisfies is machine-wide too, and a sweep
#: that ran for one Program would leave the gate failing for the others.
EXPIRE = "SELECT expire_due_decisions()"
DUE = (
    "SELECT notification_id::text, label, body, channel, to_json(argv)::text"
    " FROM due_notifications()"
)
RECORD = "SELECT record_notification_attempt($1::uuid, $2::boolean, $3::text)"
#: Asked of the database rather than derived here. The predicate for "nobody
#: will ever be told about this question" is policy, it lives in the standing
#: check, and a second copy in Python would be a second answer.
UNANNOUNCED = (
    "SELECT detail FROM check_control_surface() WHERE problem = 'decision_unannounced'"
)

#: What a channel gets substituted into its argv, and the only two things it
#: gets. A channel that wanted the digest would be a channel handed the shape of
#: a request that has not been approved yet.
LABEL = "{label}"
BODY = "{body}"

#: How long one channel has to deliver one question. A channel that hangs holds
#: up every question behind it, and the queue's own answer to a channel that did
#: not work is to try it again later.
DELIVERY_SECONDS = 10
#: How much of a rendered question a channel is handed, and how much of its
#: complaint is kept. Both are bounded because both end up somewhere an operator
#: reads, and neither is worth an unbounded argument list or an unbounded column.
BODY_BYTES = 400
ERROR_BYTES = 200


def _clipped(text: str, limit: int) -> str:
    """`text`, cut to `limit` bytes without splitting a character.

    Bytes rather than code points, because both bounds above are named in bytes
    and both are spent in bytes: an argument vector is measured by the kernel in
    bytes and a column is stored in them. A slice of the string would bound four
    times as much as the name promises the moment a target's own text is not
    ASCII, and a target's text is exactly what ends up here.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    # `ignore` drops the partial sequence the cut may leave at the end, which is
    # the one thing a byte-wise cut of UTF-8 can produce that is not text.
    return encoded[:limit].decode("utf-8", "ignore")


@dataclass
class _Tally:
    """What one run of the sweep did, across however many passes it made."""

    expired: int = 0
    delivered: int = 0
    failed: int = 0
    passes: int = 0
    #: Every question seen beyond the reach of its channels, gathered across
    #: passes rather than reported per pass: a sweeper left running would
    #: otherwise refuse once per pass for the same question.
    stranded: set[str] = field(default_factory=set)


def sweep(
    runtime: pg.Settings,
    *,
    every: float | None = None,
    deliver: Callable[[Sequence[str]], tuple[bool, str]] | None = None,
) -> Report:
    """Retire the questions whose deadline passed and deliver the ones that are due.

    One pass by default, which is the shape a timer wants. With `every` it keeps
    going until it is interrupted, which is the shape a machine with no timer
    wants; either way the report is written when it stops, because a pass that
    delivered nothing and a pass that was never made are the same document
    otherwise.
    """
    ledger = Ledger()
    tally = _Tally()
    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, tally)

    run = deliver or _run_channel
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, tally)
        try:
            while True:
                _one_pass(ledger, connection, tally, run)
                if every is None:
                    break
                time.sleep(every)
        except KeyboardInterrupt:
            ledger.hold("shutdown", "interrupted by the operator")
        except pg.DatabaseError as error:
            ledger.fail(
                "decision_queue",
                f"the queue could not be tended: {error}",
                code=INTEGRITY_FAILED,
                source="database",
            )
            return _report(ledger, tally)
        _assert_announced(ledger, tally)
    return _report(ledger, tally)


def _one_pass(
    ledger: Ledger,
    connection: pg.Connection,
    tally: _Tally,
    run: Callable[[Sequence[str]], tuple[bool, str]],
) -> None:
    """Look, retire, deliver -- in that order, and the order is the point.

    A question beyond the reach of its channels is read first, because the sweep
    is about to retire the ones whose deadline passed and a question that dies
    unannounced would otherwise be gone before anything noticed it was never
    asked. Delivery comes last so that nothing is carried to a human about a
    question this pass has already retired.
    """
    tally.passes += 1
    tally.stranded.update(str(row[0]) for row in connection.execute(UNANNOUNCED).rows)

    expired = int(connection.execute(EXPIRE).scalar() or 0)
    tally.expired += expired
    if expired:
        ledger.hold(
            "deadline",
            f"{expired} question(s) passed their deadline with no human answer",
        )

    for row in connection.execute(DUE).rows:
        notification, label, body, channel, argv = (str(item) for item in row)
        command = _command(json.loads(argv), label, body)
        if not command:
            ok, detail = False, f"the {channel} channel has an empty argv"
        else:
            ok, detail = run(command)
        connection.execute(RECORD, (notification, ok, detail or None))
        if ok:
            tally.delivered += 1
            ledger.hold("notification", f"{label} was carried to the {channel} channel")
        else:
            tally.failed += 1
            ledger.hold(
                "notification",
                f"{label} did not reach the {channel} channel and will be retried: {detail}",
            )


def _assert_announced(ledger: Ledger, tally: _Tally) -> None:
    """Fail if a question was one nobody would ever be told about.

    A delivery that failed is not a failure of this command -- the queue exists
    precisely so that it can be tried again. A question whose every channel is
    spent is different: nothing will carry it now, and the only thing left that
    will happen to it is a deadline it passes in silence. This process saw that,
    so this process says so rather than leaving it for the next `rk db verify`.

    Past tense throughout, and deliberately: what is reported is what the passes
    saw, not what is true at the end. A question can be stranded and then swept
    by the very next step of the same pass, and that one is exactly the one worth
    reporting -- it is about to be retired as a timeout against a human who was
    never told there was anything to answer.
    """
    if tally.stranded:
        ledger.fail(
            "announcement",
            "no channel will carry these questions again and no human has been "
            f"told about them: {', '.join(sorted(tally.stranded))}",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return
    ledger.hold("announcement", "every open question reached a human or is still being tried")


def _command(argv: Sequence[str], label: str, body: str) -> list[str]:
    """One channel's argv with the question written into it.

    The substitution is per element and the result is executed as a list, so the
    question never becomes a string a shell parses. That matters more here than
    it looks: the body is rendered from the request the agent asked to make, so
    its host and its path are text a target -- or the model -- had a hand in. An
    operator who puts a placeholder inside `sh -c` puts that text back in front
    of a parser, and this substitution cannot stop them; what it can do is never
    be the one that does it.
    """
    printable = "".join(character if character.isprintable() else " " for character in body)
    return [
        part.replace(LABEL, label).replace(BODY, _clipped(printable, BODY_BYTES))
        for part in argv
    ]


def _run_channel(command: Sequence[str]) -> tuple[bool, str]:
    """Run one channel once, and say whether it carried the question.

    No shell, a timeout, and every failure answered the same way: with `False`
    and a sentence. A channel is operator-supplied, so it can be missing, hang,
    or exit non-zero, and none of those is this process's to resolve -- they are
    facts to record against the attempt so the queue can decide when to stop.
    """
    try:
        done = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=DELIVERY_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, _clipped(f"{type(error).__name__}: {error}", ERROR_BYTES)
    if done.returncode == 0:
        return True, ""
    said = (done.stderr or done.stdout or "").strip()
    return False, _clipped(f"exit {done.returncode}: {said}", ERROR_BYTES)


def _report(ledger: Ledger, tally: _Tally) -> Report:
    return report(
        COMMAND,
        ledger,
        passes=tally.passes,
        expired=tally.expired,
        delivered=tally.delivered,
        failed=tally.failed,
    )
