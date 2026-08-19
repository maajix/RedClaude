"""The local operator console: `rk ui serve`.

An adapter over the same operations the CLI calls, and nothing else. Every view
on it is one call into `panels`, `state`, `operator` or `reporting`, and every
button is one of the seven typed operator verbs -- so there is no query here, no
connection here, and no second opinion about what a campaign's state means. A
console that computed anything of its own would be a second implementation of
the harness with a nicer font, and the two would disagree on the day one of them
was changed.

Written on `http.server` and `html`, and that is the whole stack. There is no
JavaScript on any page: every control is a link or a form, which is also how the
keyboard access this ticket asks for is achieved -- not by handling key events
but by never taking the browser's own handling away. It follows that a page can
be read with the network off, printed, or driven by a screen reader without any
of that being a feature somebody had to add.

Two things make a local console worth being careful about. It holds the
operator's connection, which is the only role that may lift a Halt or report a
Finding, and it is reachable by any page the operator's browser happens to be
on. So: the Host header must name the address this console was bound to, a POST
must carry the per-process token that is only ever printed into this console's
own forms, and the pages declare a content policy that permits no script and no
outbound request at all.
"""

from __future__ import annotations

import html
import http.server
import json
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from redkraken import config, operator, panels, pg, reporting, state
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


COMMAND = "ui serve"

#: Where the console listens when nobody says otherwise. Loopback, because this
#: process holds `rk2_human` and an address that is not loopback is an address
#: something other than this operator can reach.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

#: How long a page may spend reading before the panels it has not reached are
#: rendered as pending. The console is serial, so this is also the longest one
#: operator waits for another page.
DEFAULT_BUDGET = 5.0

#: How many rows one panel shows on a page of its own. Larger than the overview's
#: default because the operator asked for this one panel, and still bounded:
#: criterion 6's large campaign is bounded here or it is bounded by the browser
#: running out of memory.
PANEL_ROWS = 200

#: The largest form this console will read. A local console has no upload and no
#: long field but a reason, so anything past this is not a form.
MAX_BODY = 64 * 1024

#: How many summaries are kept. A projection is a convenience and the canonical
#: text is always beside it, so the cache is allowed to forget: the oldest entry
#: goes when the next one arrives, and forgetting reads as `unavailable`, which
#: is a state the page already knows how to show.
MAX_SUMMARIES = 512

#: How long a projection is allowed to be. It is one line under a record and not
#: a second copy of it.
SUMMARY_CHARACTERS = 160

#: Criterion 4's seven words, in the order a claim passes through them. A cell
#: under one of these carries the word itself when the rung was reached and a
#: dash when it was not: a tick and a cross are the same shape to somebody
#: having the page read to them, and what the criterion asks is that the seven
#: stay distinct rather than that they be coloured.
RUNGS = (
    "proposed",
    "attempted",
    "observed",
    "supported",
    "validated",
    "demonstrated",
    "reported",
)

#: The three cells that read the opposite way round from the rungs beside them:
#: a Finding that is blocked cannot be sent, a check that does not hold is a
#: Program that is unsound, and a rendering that is stale describes a Finding
#: that has moved. Each is a `(column, value)` pair and not a value, because a
#: `true` is progress under `demonstrated` and a refusal to send under `blocked`,
#: so what makes it a warning is which column it is in.
WARNINGS = {("blocked", "true"), ("holds", "no"), ("freshness", "stale")}

#: How a summary that is not the record's own is shown. Both are warnings and
#: both leave the canonical text exactly where it was: criterion 5's fallback is
#: not a mode this console switches into, it is what the page always shows.
CURRENT = "current"
STALE = "stale"
UNAVAILABLE = "unavailable"

#: What the browser may do with a page from here, which is: render it, using the
#: one stylesheet, and submit a form back to this origin. No script, no image,
#: no font, no frame, no connection. A console that could fetch could exfiltrate
#: what it is showing, and what it is showing is a campaign against somebody
#: else's systems.
POLICY = "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'"

HEADERS = (
    ("Content-Security-Policy", POLICY),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
)


@dataclass(frozen=True)
class Response:
    """One answer, before anything has been written to a socket.

    The whole of what a request produces, so that `respond` can be driven by a
    test with no socket at all: everything below it is a function of a console,
    a method, a path and a form.
    """

    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"

    def encoded(self) -> bytes:
        return self.body.encode("utf-8")


@dataclass(frozen=True)
class Summary:
    """One non-authoritative projection, under the digest it was taken from."""

    digest: str
    text: str


@dataclass
class Summaries:
    """Criterion 5, and the whole of what makes a projection safe to show.

    Keyed by the digest as well as by the label, so a projection cannot outlive
    the bytes it was taken from: a record that moved has a new digest, the key
    misses, and the page says `stale` instead of showing last revision's sentence
    under this revision's heading. Nothing here is authority -- the canonical
    text is rendered beside every projection on every page that has one -- which
    is why forgetting an entry is allowed to be the eviction policy.
    """

    entries: dict[str, Summary] = field(default_factory=dict)
    limit: int = MAX_SUMMARIES

    def remember(self, label: str, digest: str, text: str) -> None:
        self.entries.pop(label, None)
        self.entries[label] = Summary(digest=digest, text=text)
        while len(self.entries) > self.limit:
            self.entries.pop(next(iter(self.entries)))

    def lookup(self, label: str, digest: str) -> tuple[str, str]:
        """This record's projection, or the reason there is not one to show."""
        found = self.entries.get(label)
        if found is None:
            return UNAVAILABLE, ""
        if found.digest != digest:
            return STALE, found.text
        return CURRENT, found.text


def summarise(document: object) -> str:
    """One canonical record as one line, which is a convenience and not a fact.

    Deliberately shallow. It reads the record's own top-level scalars in the
    order the record carries them and stops at a length nobody has to scroll --
    a projection that walked the whole document would be a second rendering of
    it, and the first one is already on the page underneath.
    """
    if not isinstance(document, Mapping):
        return _clipped(str(document))
    pairs = [
        f"{name}: {value}"
        for name, value in document.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    ]
    return _clipped(", ".join(pairs)) if pairs else "no scalar field to project"


def _clipped(text: str) -> str:
    flat = " ".join(str(text).split())
    if len(flat) <= SUMMARY_CHARACTERS:
        return flat
    return flat[: SUMMARY_CHARACTERS - 1] + "…"


# ---------------------------------------------------------------------------
# The actions, which are the operator's verbs and nothing else
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """One input on one action's form, in the three shapes a form input has."""

    name: str
    label: str
    required: bool = True
    choices: tuple[str, ...] = ()
    placeholder: str = ""


@dataclass(frozen=True)
class Action:
    """One operator verb as a form, and the call it makes when it is submitted.

    The call is the module-level function the CLI calls, taking the same
    arguments in the same order. That is criterion 3 in one line: a console that
    reimplemented a verb would be a console that could get it wrong, and there
    is no route from here to a statement of its own.
    """

    verb: str
    caption: str
    fields: tuple[Field, ...]
    call: Callable[[Console, Mapping[str, str]], Report]


def _halt(console: Console, form: Mapping[str, str]) -> Report:
    return operator.halt(console.human, console.slug, reason=form["reason"])


def _resume(console: Console, form: Mapping[str, str]) -> Report:
    return operator.resume(console.human, console.slug, reason=form["reason"])


def _answer(console: Console, form: Mapping[str, str]) -> Report:
    return operator.answer(
        console.human,
        console.slug,
        form["label"],
        approve=form["verdict"] == "approve",
        reason=form["reason"],
        grant_hours=_hours(form.get("grant_hours", "")),
    )


def _supersede(console: Console, form: Mapping[str, str]) -> Report:
    return operator.supersede(console.human, console.slug, form["label"], reason=form["reason"])


def _report_finding(console: Console, form: Mapping[str, str]) -> Report:
    return operator.report_finding(
        console.human,
        console.slug,
        form["label"],
        form["rendering"],
        form["content_sha256"],
        reason=form["reason"],
    )


def _clear_gate(console: Console, form: Mapping[str, str]) -> Report:
    return operator.clear_gate(
        console.human, console.slug, form["label"], form["gate"], reason=form["reason"]
    )


class Malformed(Exception):
    """One field of a submitted form that cannot be read as what it asks for.

    Raised where the field is parsed and answered where the form is, so that a
    console reads a value in one place rather than validating it in another.
    """


def _hours(given: str) -> float:
    """The grant a form asked for, defaulting only where the flag defaults.

    An empty field is the default, because the field is optional and the flag it
    stands for has one. A field the operator filled in is not: `rk` exits 2 on
    the same characters, and a console that read "12h" or "twelve" as the
    default would widen the window the operator asked to narrow and would report
    the grant it made as the grant that was requested. The two surfaces answer
    the same input the same way, which is the whole of decision 18's "the same
    operator verbs".
    """
    if not given.strip():
        return operator.DEFAULT_GRANT_HOURS
    try:
        return float(given)
    except ValueError:
        raise Malformed(f"grant, in hours: {given!r} is not a number of hours") from None


REASON = Field("reason", "why", placeholder="the sentence an audit reads afterwards")

ACTIONS = {
    action.verb: action
    for action in (
        Action(
            verb=operator.HALT,
            caption="halt this Program: no egress and no new work until it is lifted",
            fields=(REASON,),
            call=_halt,
        ),
        Action(
            verb=operator.RESUME,
            caption="lift the Halt on this Program",
            fields=(REASON,),
            call=_resume,
        ),
        Action(
            verb=operator.ANSWER,
            caption="approve or deny one pending decision",
            fields=(
                Field("label", "decision"),
                Field("verdict", "verdict", choices=("approve", "deny")),
                Field("grant_hours", "grant, in hours", required=False),
                REASON,
            ),
            call=_answer,
        ),
        Action(
            verb=operator.SUPERSEDE,
            caption="withdraw one pending decision instead of answering it",
            fields=(Field("label", "decision"), REASON),
            call=_supersede,
        ),
        Action(
            verb=operator.REPORT,
            caption="report one validated Finding, naming the bytes you read",
            fields=(
                Field("label", "finding"),
                Field("rendering", "rendering id"),
                Field("content_sha256", "digest of those bytes"),
                REASON,
            ),
            call=_report_finding,
        ),
        Action(
            verb=operator.CLEAR,
            caption="lift one review gate on one Finding, and nothing else",
            fields=(Field("label", "finding"), Field("gate", "gate"), REASON),
            call=_clear_gate,
        ),
    )
}

#: Which forms belong on the decision queue rather than on the control page.
#: Both pages render them from the same table; the split is about where an
#: operator is standing when they want one.
DECISION_ACTIONS = (operator.ANSWER, operator.SUPERSEDE)
CONTROL_ACTIONS = (operator.HALT, operator.RESUME, operator.REPORT, operator.CLEAR)


# ---------------------------------------------------------------------------
# The console
# ---------------------------------------------------------------------------


@dataclass
class Console:
    """Everything a page needs, and one Program it is all about.

    There is no Program argument anywhere on this surface. The console is opened
    against one configuration, resolves that Program's slug once, and every read
    and every verb below uses it -- so cross-Program isolation here is not a
    check that could be forgotten, it is that there is nothing to pass.
    """

    runtime: pg.Settings
    agent: pg.Settings
    human: pg.Settings
    configuration_path: Path
    slug: str
    origin: str
    limit: int = panels.DEFAULT_ROWS
    budget: float = DEFAULT_BUDGET
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    summaries: Summaries = field(default_factory=Summaries)


def build(
    ledger: Ledger,
    runtime: pg.Settings,
    agent: pg.Settings,
    human: pg.Settings,
    configuration_path: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    limit: int = panels.DEFAULT_ROWS,
    budget: float = DEFAULT_BUDGET,
) -> Console | None:
    """Open a console against one configuration, or refuse and say why.

    The configuration is read here rather than on the first page, because a file
    that will not load is a console that cannot answer anything -- and finding
    that out as a 500 on a page an operator opened in a browser is finding it out
    in the one place where the reason is hardest to read.
    """
    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return None
    slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{slug}, schema {configuration.schema_version}")
    return Console(
        runtime=runtime,
        agent=agent,
        human=human,
        configuration_path=Path(configuration_path),
        slug=slug,
        origin=f"http://{host}:{port}",
        limit=limit,
        budget=budget,
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

#: The pages, in the order they appear in the navigation. `state` and
#: `decisions` are the two reads that are not panels: one is the model's own
#: view of its records and the other is the operator's queue, and both already
#: have a command behind them.
NAVIGATION = (
    ("/", "overview"),
    ("/records", "records"),
    ("/decisions", "decisions"),
    ("/reports", "reports"),
    ("/control", "control"),
)


def respond(
    console: Console, method: str, path: str, form: Mapping[str, str] | None = None
) -> Response:
    """One request, as a function of the console and what was asked.

    The seam every test drives. Nothing above it decides anything: the handler
    reads a socket, checks the Host header and hands the three strings here.
    """
    split = urlsplit(path)
    route = split.path
    query = {name: values[0] for name, values in parse_qs(split.query).items()}

    if method == "POST":
        if route != "/act":
            return _refused(console, 405, f"{route} takes no form")
        return _acted(console, form or {})
    if method != "GET":
        return _refused(console, 405, f"{method} is not a method this console answers")

    if route == "/style.css":
        return Response(200, STYLESHEET, content_type="text/css; charset=utf-8")
    if route == "/":
        return _overview(console)
    if route == "/records":
        return _records(console)
    if route == "/decisions":
        return _decisions(console)
    if route == "/reports":
        return _reports(console, query)
    if route == "/control":
        return _control(console)
    if route.startswith("/panel/"):
        return _panel(console, unquote(route[len("/panel/") :]))
    if route.startswith("/record/"):
        return _record(console, unquote(route[len("/record/") :]))
    return _refused(console, 404, f"{route} is not a page of this console")


def _refused(console: Console, status: int, detail: str) -> Response:
    body = _section("this console cannot answer that", f"<p class=\"warn\">{_e(detail)}</p>")
    return Response(status, _page(console, "not answered", body))


# ---------------------------------------------------------------------------
# The views
# ---------------------------------------------------------------------------


def _overview(console: Console) -> Response:
    """Every panel at the overview's limit, under one budget.

    One call, because `panels.read` opens one connection and asks each read in
    its own transaction: a page that called it nine times would connect nine
    times and could show nine different instants of the same campaign.
    """
    answer = panels.read(
        console.runtime,
        console.configuration_path,
        limit=console.limit,
        deadline=time.monotonic() + console.budget,
    )
    parts = [_outcome(answer)]
    for shown in answer.facts.get("panels") or ():
        parts.append(_panel_html(shown, linked=True))
    return Response(200, _page(console, "overview", "".join(parts)))


def _panel(console: Console, name: str) -> Response:
    """One panel, at a limit of its own, still bounded and still counted."""
    if name not in panels.BY_NAME:
        return _refused(console, 404, f"{name} is not a panel; the panels are {_panel_names()}")
    answer = panels.read(
        console.runtime,
        console.configuration_path,
        names=(name,),
        limit=PANEL_ROWS,
        deadline=time.monotonic() + console.budget,
    )
    parts = [_outcome(answer)]
    for shown in answer.facts.get("panels") or ():
        parts.append(_panel_html(shown, linked=False))
    return Response(200, _page(console, name, "".join(parts)))


def _records(console: Console) -> Response:
    """The model's own compact read, shown as the model gets it.

    On the agent connection, through `state.read`, which is the same call
    `rk state` makes. A console that read these rows on the runtime connection
    would be showing an operator something no model could see and calling it the
    model's state.
    """
    answer = state.read(console.runtime, console.agent, console.configuration_path)
    compact = answer.facts.get("state") or {}
    rows = []
    for entry in compact.get("records") or ():
        label = str(entry["label"])
        shown, text = console.summaries.lookup(label, str(entry["digest"]))
        rows.append(
            (
                _link(f"/record/{quote(label, safe='')}", label),
                _e(entry["kind"]),
                _e(entry["revision"]),
                _e(str(entry["digest"])[:12]),
                _summary_cell(shown, text),
            )
        )
    counts = tuple(
        (_e(item["kind"]), _e(item["count"]), _e(item["returned"]), _e(item["omitted"]))
        for item in compact.get("kinds") or ()
    )
    body = [
        _outcome(answer),
        _table(
            "the records this Program holds, as the agent connection sees them",
            ("label", "kind", "revision", "digest", "summary"),
            tuple(rows),
            empty="this Program holds no record yet",
        ),
        _table(
            f"what each kind holds, in {compact.get('bytes', 0)} byte(s) returned",
            ("kind", "held", "shown", "omitted"),
            counts,
            empty="nothing has been counted",
        ),
    ]
    return Response(200, _page(console, "records", "".join(body)))


def _record(console: Console, label: str) -> Response:
    """One record whole, with the projection of it refreshed from these bytes.

    The canonical text is rendered whether or not there is a projection and
    whether or not the projection was current, which is criterion 5's fallback:
    there is no state of this page that shows a summary instead of the record.
    """
    answer = state.read(console.runtime, console.agent, console.configuration_path, label=label)
    found = answer.facts.get("record") or {}
    parts = [_outcome(answer)]
    if not found.get("present"):
        parts.append(
            _section(
                _e(label),
                '<p class="warn">no record of this Program carries that label</p>',
            )
        )
        return Response(404, _page(console, "record", "".join(parts)))

    digest = str(found["digest"])
    canonical = json.dumps(found["document"], indent=2, sort_keys=True)
    # The prior projection is read before this page writes its own, so the note
    # beside the record can say whether one was held and whether it was this
    # record's. Then the projection shown is the one taken from these very bytes:
    # it is keyed by this digest, so there is no state of this page on which it
    # is stale, and the canonical text is under it whether or not it is there.
    was, previous = console.summaries.lookup(label, digest)
    projection = summarise(found["document"])
    console.summaries.remember(label, digest, projection)
    parts.append(
        _section(
            f"{_e(found['kind'])} {_e(label)}, revision {_e(found['revision'])}",
            "".join(
                [
                    f"<p>digest <code>{_e(digest)}</code></p>",
                    _summary_note(was, previous),
                    f'<p class="summary">{_e(projection)}</p>',
                    "<h3>the record itself</h3>",
                    f"<pre>{_e(canonical)}</pre>",
                ]
            ),
        )
    )
    return Response(200, _page(console, "record", "".join(parts)))


def _decisions(console: Console) -> Response:
    """The queue, on the operator's own connection, with its two verbs beside it."""
    answer = operator.queue(console.human, slug=console.slug)
    rows = tuple(
        (
            _e(question["label"]),
            _e(question["question_code"]),
            _e(question["tool"]),
            _e(question["risk_class"]),
            _mark("status", str(question["status"])),
            _e(question["deadline_at"]),
            _e(question["answered_by"]),
            _e(question["answer"]),
        )
        for question in answer.facts.get("questions") or ()
    )
    body = [
        _outcome(answer),
        _table(
            f"{answer.facts.get('open', 0)} question(s) waiting on this operator",
            (
                "decision", "code", "tool", "risk", "status",
                "deadline", "answered by", "answer",
            ),
            rows,
            empty="nothing is waiting on an operator",
        ),
        _forms(console, DECISION_ACTIONS),
    ]
    return Response(200, _page(console, "decisions", "".join(body)))


def _reports(console: Console, query: Mapping[str, str]) -> Response:
    """One document, rendered by the same call `rk report` makes.

    The form is a chooser rather than a free field wherever the answer is a
    fixed set: the subjects are the two `reporting.SUBJECTS` carries and the
    forms are the rows `panels.forms` reads, so an operator picks what exists
    instead of guessing an identifier and reading a refusal.
    """
    subject = query.get("subject", "finding")
    label = query.get("label", "")
    template = query.get("template", "")
    registry = panels.forms(console.runtime)
    parts = [_report_form(registry.facts.get("forms") or (), subject, label, template)]
    if not registry.ok:
        parts.append(_outcome(registry))
    if label and template:
        if subject not in reporting.SUBJECTS:
            # A subject the chooser never offered can only be a hand-typed
            # query. It is refused rather than coerced: rendering a `finding`
            # report because a `chain` was asked for would put a document on the
            # page under the wrong heading, which is the one thing an operator
            # about to name bytes for an approval must not be handed.
            parts.append(
                _section(
                    "this console cannot answer that",
                    f'<p class="warn">{_e(subject)} is not a subject this console '
                    f'reports; the subjects are {_e(", ".join(reporting.SUBJECTS))}</p>',
                )
            )
            return Response(400, _page(console, "reports", "".join(parts)))
        answer = reporting.run(
            console.runtime,
            console.configuration_path,
            subject=subject,
            label=label,
            template=template,
        )
        parts.append(_outcome(answer))
        document = answer.facts.get("document") or {}
        if document:
            parts.append(
                _section(
                    "the document, as bytes an approval may name",
                    "".join(
                        [
                            f"<p>{_e(document.get('bytes'))} byte(s) under "
                            f"<code>{_e(document.get('sha256'))}</code>, "
                            f"from source digest <code>{_e(document.get('source_digest'))}</code>"
                            "</p>",
                            '<p class="warn">these bytes are not filed; '
                            "`rk report finding --record` files them</p>",
                        ]
                    ),
                )
            )
    return Response(200, _page(console, "reports", "".join(parts)))


def _control(console: Console) -> Response:
    return Response(200, _page(console, "control", _forms(console, CONTROL_ACTIONS)))


def _acted(console: Console, form: Mapping[str, str]) -> Response:
    """One verb, once the request has been established as this console's own.

    The result page is rendered here rather than redirected to, because a
    resubmitted verb is refused by the database and not by this process:
    `reported` is terminal, a clearance is unique on its Finding and its gate,
    and an answered decision is no longer pending. Showing the outcome is
    therefore honest at any point afterwards, including a reload.
    """
    if not secrets.compare_digest(form.get("token", ""), console.token):
        return _refused(console, 403, "this form did not come from this console")
    verb = form.get("verb", "")
    action = ACTIONS.get(verb)
    if action is None:
        return _refused(console, 404, f"{verb or 'nothing'} is not an operator verb")
    missing = [
        item.label
        for item in action.fields
        if item.required and not form.get(item.name, "").strip()
    ]
    if missing:
        return _refused(console, 400, f"{verb} needs {', '.join(missing)}")

    try:
        answer = action.call(console, form)
    except Malformed as unreadable:
        return _refused(console, 400, f"{verb} was given {unreadable}")
    result = answer.facts.get("result")
    body = [
        _section(
            _e(verb),
            f"<p>{_e(action.caption)}</p>"
            + (
                f"<h3>the Event this wrote</h3><pre>{_e(json.dumps(result, indent=2))}</pre>"
                if result is not None
                else '<p class="warn">this verb wrote no Event</p>'
            ),
        ),
        _outcome(answer),
    ]
    return Response(200 if answer.ok else 400, _page(console, verb, "".join(body)))


# ---------------------------------------------------------------------------
# The rendering
# ---------------------------------------------------------------------------


def _e(value: object) -> str:
    """One value as text a browser renders rather than as markup it obeys.

    Every string that reaches a page goes through here, including ones that came
    out of the database: a label is written by a model and a detail is written
    by Postgres, and neither is a source this console trusts with a tag.

    A null renders as nothing, because a null in a cell is a column that has no
    answer yet -- a question nobody has answered, a run that has not finished --
    and the word `None` in that cell would read as an answer somebody gave.
    """
    return "" if value is None else html.escape(str(value), quote=True)


def _link(href: str, text: object) -> str:
    return f'<a href="{_e(href)}">{_e(text)}</a>'


def _section(heading: str, body: str) -> str:
    return f"<section><h2>{heading}</h2>{body}</section>"


def _panel_names() -> str:
    return ", ".join(panels.NAMES)


def _mark(column: str, value: str) -> str:
    """One cell, marked by what it says rather than only by how it looks.

    Criterion 4 asks that the seven rungs stay distinct, so a rung that was
    reached prints its own word: `observed` under the observed column, and a
    dash where the claim never got there. The warnings are the two answers that
    read the opposite way round from the rest and the two words that are a
    problem, which is why they are a set of pairs and not a set of values -- a
    `true` is progress under `demonstrated` and a refusal to send under `blocked`.
    """
    if column in RUNGS:
        if value == "true":
            return f'<span class="rung held">{_e(column)}</span>'
        if value == "false":
            return '<span class="rung missing">–</span>'
    if (column, value) in WARNINGS:
        return f'<span class="warn">{_e(value)}</span>'
    return _e(value)


def _table(
    caption: str, columns: Sequence[str], rows: Sequence[Sequence[str]], *, empty: str
) -> str:
    """One table, with its own caption and an empty state that is not an empty table.

    The cells arrive escaped -- every caller runs them through `_mark` or `_e` --
    because a cell is sometimes a link and sometimes a marked word, and a table
    that escaped them again would print the markup its callers just built.
    """
    if not rows:
        return (
            f"<table><caption>{_e(caption)}</caption></table>"
            f'<p class="empty">{_e(empty)}</p>'
        )
    head = "".join(f'<th scope="col">{_e(name)}</th>' for name in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f"<table><caption>{_e(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    )


def _panel_html(shown: Mapping[str, object], *, linked: bool) -> str:
    """One panel as `panels` reported it, in the state it came back in.

    Four states and four renderings. `ready` is the table; `empty` says so where
    the rows would be; `pending` says the page ran out of time before it got
    here, which is what a console shows while a large campaign is still coming
    back; and `error` carries the refusal the database gave, so a panel that
    could not be read is one panel that could not be read and not a page that
    did not load.
    """
    name = str(shown["panel"])
    columns = [str(column) for column in shown["columns"] or ()]
    heading = _link(f"/panel/{quote(name, safe='')}", name) if linked else _e(name)
    state_ = str(shown["state"])
    if state_ == panels.PENDING:
        return _section(
            heading,
            f'<p class="pending">{_e(shown["detail"] or "not read yet")}</p>',
        )
    if state_ == panels.REFUSED:
        return _section(
            heading,
            f'<p class="warn">this panel could not be read: {_e(shown["detail"])}</p>',
        )
    rows = tuple(
        tuple(_mark(columns[index], str(cell)) for index, cell in enumerate(row))
        for row in shown["rows"] or ()
    )
    omitted = int(shown["omitted"] or 0)
    table = _table(str(shown["caption"]), columns, rows, empty=f"this Program holds no {name}")
    note = (
        f'<p class="omitted">{omitted} further row(s) are held and not shown</p>'
        if omitted
        else ""
    )
    return _section(heading, table + note)


def _summary_cell(shown: str, text: str) -> str:
    """A projection in a list, where the canonical record is one link away."""
    if shown == CURRENT:
        return f'<span class="summary">{_e(text)}</span>'
    if shown == STALE:
        return f'<span class="warn">{_e(STALE)}</span>'
    return f'<span class="empty">{_e(UNAVAILABLE)}</span>'


def _summary_note(shown: str, previous: str) -> str:
    """What the projection was before this page read the record itself."""
    if shown == CURRENT:
        return ""
    if shown == STALE:
        return (
            f'<p class="warn">the summary held for this label was taken from other bytes '
            f"and is not shown as this record: {_e(_clipped(previous))}</p>"
        )
    return '<p class="empty">no summary was held for this label</p>'


def _outcome(answer: Report) -> str:
    """What the operation said about itself, in the shape the CLI prints.

    Both lists, always. A console that showed only the failures would be a
    console on which a command that held could not be told from a command that
    was never run.
    """
    assertions = tuple(
        (_mark("holds", "yes" if item.ok else "no"), _e(item.name), _e(item.detail))
        for item in answer.assertions
    )
    violations = tuple(
        (_e(item.code), _e(item.source), _e(item.detail)) for item in answer.violations
    )
    verdict = "held" if answer.ok else f"refused, exit {answer.exit_code}"
    return _section(
        f"{_e(answer.command)}: {_e(verdict)}",
        _table("what this read asserted", ("holds", "name", "detail"), assertions,
               empty="this read asserted nothing")
        + (
            _table("what it refused", ("code", "source", "detail"), violations,
                   empty="nothing was refused")
            if violations
            else ""
        ),
    )


def _forms(console: Console, verbs: Sequence[str]) -> str:
    return "".join(_form(console, ACTIONS[verb]) for verb in verbs)


def _form(console: Console, action: Action) -> str:
    """One verb's form: real inputs, real labels, and the token that binds it here.

    Every input is labelled with `for` and every label names the input's id, so
    the browser's own focus and label behaviour works and there is nothing for a
    keyboard to be locked out of. The id is namespaced by the verb because six
    forms on one page would otherwise all call their reason field `reason`.
    """
    inputs = []
    for item in action.fields:
        identifier = f"{action.verb}-{item.name}".replace(" ", "-")
        required = " required" if item.required else ""
        if item.choices:
            options = "".join(
                f'<option value="{_e(choice)}">{_e(choice)}</option>' for choice in item.choices
            )
            control = f'<select id="{_e(identifier)}" name="{_e(item.name)}"{required}>{options}</select>'
        else:
            placeholder = (
                f' placeholder="{_e(item.placeholder)}"' if item.placeholder else ""
            )
            control = (
                f'<input id="{_e(identifier)}" name="{_e(item.name)}" type="text"'
                f"{required}{placeholder}>"
            )
        inputs.append(
            f'<p><label for="{_e(identifier)}">{_e(item.label)}</label>{control}</p>'
        )
    return _section(
        _e(action.verb),
        f'<form method="post" action="/act">'
        f'<p>{_e(action.caption)}</p>'
        f'<input type="hidden" name="verb" value="{_e(action.verb)}">'
        f'<input type="hidden" name="token" value="{_e(console.token)}">'
        + "".join(inputs)
        + f'<p><button type="submit">{_e(action.verb)}</button></p></form>',
    )


def _report_form(
    registry: Sequence[Sequence[str]], subject: str, label: str, template: str
) -> str:
    """The chooser for `rk report`, which is a GET because rendering reads."""
    subjects = "".join(
        f'<option value="{_e(one)}"{" selected" if one == subject else ""}>{_e(one)}</option>'
        for one in sorted(reporting.SUBJECTS)
    )
    options = "".join(
        f'<option value="{_e(identity)}"{" selected" if identity == template else ""}>'
        f"{_e(identity)}: {_e(name)} ({_e(platform)})</option>"
        for identity, platform, name in registry
    )
    return _section(
        "render one document",
        '<form method="get" action="/reports">'
        '<p><label for="report-subject">subject</label>'
        f'<select id="report-subject" name="subject">{subjects}</select></p>'
        '<p><label for="report-label">label</label>'
        f'<input id="report-label" name="label" type="text" value="{_e(label)}" required></p>'
        '<p><label for="report-template">form</label>'
        f'<select id="report-template" name="template" required>{options}</select></p>'
        "<p><button type=\"submit\">render</button></p></form>",
    )


def _page(console: Console, title: str, body: str) -> str:
    """One document, with the navigation and the skip link every page carries.

    The skip link is first in the source and visible on focus, so a keyboard
    reaches the content of a page whose navigation is five links long without
    walking all five -- which is the whole of what "keyboard access" costs when
    nothing on the page is a script pretending to be a control.
    """
    navigation = " ".join(_link(href, name) for href, name in NAVIGATION)
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)} — {_e(console.slug)}</title>"
        '<link rel="stylesheet" href="/style.css">'
        "</head><body>"
        '<a class="skip" href="#content">skip to the content</a>'
        f'<header><p class="program">{_e(console.slug)}</p>'
        f'<nav aria-label="pages">{navigation}</nav></header>'
        f'<main id="content" tabindex="-1"><h1>{_e(title)}</h1>{body}</main>'
        "</body></html>"
    )


#: The one stylesheet, served from this process so that the content policy can
#: forbid every other source. It carries no image and no font: a console that
#: fetched either would be a console making a request the operator did not make.
STYLESHEET = """
:root { color-scheme: light dark; }
body { font: 15px/1.5 ui-monospace, monospace; margin: 0 auto; max-width: 72rem; padding: 1rem; }
header { border-bottom: 1px solid; display: flex; gap: 1rem; align-items: baseline; }
nav a { margin-right: 0.75rem; }
h1 { font-size: 1.1rem; }
.program { font-weight: 700; }
h2 { font-size: 1rem; margin-top: 2rem; }
h3 { font-size: 0.95rem; }
table { border-collapse: collapse; width: 100%; }
caption { text-align: left; padding: 0.25rem 0; font-style: italic; }
th, td { border: 1px solid; padding: 0.2rem 0.4rem; text-align: left; vertical-align: top; }
th { font-weight: 600; }
pre { overflow-x: auto; padding: 0.5rem; border: 1px solid; }
code { word-break: break-all; }
.skip { position: absolute; left: -100rem; }
.skip:focus { position: static; }
.rung.held { font-weight: 700; text-decoration: underline; }
.rung.missing { opacity: 0.5; }
.warn { font-weight: 700; text-decoration: underline wavy; }
.pending { font-style: italic; }
.empty, .omitted { font-style: italic; opacity: 0.75; }
.summary { font-style: italic; }
label { display: inline-block; min-width: 12rem; }
input, select { min-width: 22rem; }
main:focus { outline: none; }
"""


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


class Handler(http.server.BaseHTTPRequestHandler):
    """The socket, and the two questions that are about the socket.

    Everything else is `respond`. What is decided here is what cannot be decided
    from a method and a path: that the request named the address this console
    was bound to, and that a form is small enough to be a form.
    """

    protocol_version = "HTTP/1.1"
    server_version = "rk-console"
    sys_version = ""

    @property
    def console(self) -> Console:
        return self.server.console

    def do_GET(self) -> None:
        self._answer("GET", None)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            # The body is not drained, so the connection cannot be reused: under
            # HTTP/1.1 the unread bytes would be parsed as the next request line.
            # Close it rather than read a body this console has already refused.
            self.close_connection = True
            self._send(_refused(self.console, 413, "that form is too large to be a form"))
            return
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = {name: values[0] for name, values in parse_qs(raw, keep_blank_values=True).items()}
        self._answer("POST", form)

    def log_message(self, format: str, *args: object) -> None:
        """Nothing, on purpose.

        A request line carries a label and a query string, and a label is a
        model's own words about somebody's system. The console's log would be a
        second copy of the campaign in a file nobody is redacting.
        """

    def _answer(self, method: str, form: Mapping[str, str] | None) -> None:
        console = self.console
        host = self.headers.get("Host", "")
        if host != console.origin.removeprefix("http://"):
            # DNS rebinding: a page on another origin can make the browser
            # resolve a name it controls to 127.0.0.1 and send this console a
            # request that carries the operator's own loopback address. What it
            # cannot do is change the Host header, so a request naming anything
            # but the address this console was bound to is not a request from
            # anybody who knows where this console is.
            self._send(_refused(console, 421, "this console is not reachable under that name"))
            return
        origin = self.headers.get("Origin")
        if method == "POST" and origin is not None and origin != console.origin:
            self._send(_refused(console, 403, "that form was submitted from another origin"))
            return
        self._send(respond(console, method, self.path, form))

    def _send(self, response: Response) -> None:
        body = response.encoded()
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


class Server(http.server.HTTPServer):
    """One console on one socket, answering one request at a time.

    Serial rather than threaded, and that is a decision rather than an omission.
    Every read below opens its own connection and every page is bounded by its
    own deadline, so the cost of answering serially is that a second tab waits;
    the cost of answering in threads would be a shared summary cache and a
    shared operator connection reached from several requests at once, for a
    console one person is looking at.
    """

    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], console: Console) -> None:
        super().__init__(address, Handler)
        self.console = console


def server(console: Console, *, host: str, port: int) -> Server:
    return Server((host, port), console)


def serve(
    runtime: pg.Settings,
    agent: pg.Settings,
    human: pg.Settings,
    configuration_path: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    limit: int = panels.DEFAULT_ROWS,
    budget: float = DEFAULT_BUDGET,
) -> Report:
    """Open the console and answer requests until the operator stops it.

    Reports in the same shape every other command reports in, because the two
    things that can go wrong before a page is ever rendered -- a configuration
    that will not load and an address already in use -- are the two things an
    operator has to be told about in a terminal rather than in a browser.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_slug": None, "address": None, "requests": None}
    console = build(
        ledger, runtime, agent, human, configuration_path,
        host=host, port=port, limit=limit, budget=budget,
    )
    if console is None:
        return report(COMMAND, ledger, **facts)
    facts["program_slug"] = console.slug

    try:
        listening = server(console, host=host, port=port)
    except OSError as error:
        ledger.fail(
            "address",
            f"the console cannot listen on {host}:{port}: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--port",
        )
        return report(COMMAND, ledger, **facts)

    # The port the socket got, under the name the operator gave. `--port 0` is a
    # port the kernel picks, so the origin the Host header is checked against
    # cannot be settled before the bind; the host is not re-read from the socket
    # because `--host localhost` is a name a browser will send back as it was
    # written and the socket would answer with the address it resolved to.
    console.origin = f"http://{host}:{listening.server_address[1]}"
    facts["address"] = console.origin
    ledger.hold("address", f"the console is at {facts['address']}")
    ledger.hold("token", "every form on it carries a token this process alone holds")
    with listening:
        try:
            listening.serve_forever()
        except KeyboardInterrupt:
            ledger.hold("stopped", "the operator stopped the console")
    return report(COMMAND, ledger, **facts)
