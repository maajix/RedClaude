"""The bounded operational reads a console shows and `rk ui read` prints.

`state` is the model's read on the model's connection: eight kinds of labelled
record, bounded, isolated by row level security and by nothing else. This is
the operator's read on the runtime's connection, and what it carries is the
part of a campaign that is not a labelled record -- where the Program is in its
lifecycle, what the scheduler offered, which runs happened, which Identity is
leased to which run, what is left of the budgets, which chains were built and
which documents were filed.

None of that is in `v_records`, and none of it should be. `state_read_surface`
decides what a model may read, so adding Leases and budgets to it in order to
make this console possible would be widening the model's surface to build the
operator's. The two reads stay two, on the two connections they belong to.

Every read here is one statement and a count of what it did not return, so a
console showing twenty rows of a campaign holding twenty thousand says so
rather than implying the campaign is small. Each runs in its own read-only
transaction: a panel whose statement is refused is reported as that panel
failing, and the page it was on still renders, which is only possible if the
failure did not leave a transaction the next panel would inherit.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import config, integrity, migrate, pg, program
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


COMMAND = "ui read"

#: How many rows one panel carries when nobody says otherwise. Small, because
#: the answer to "what is this campaign doing" is the newest rows of each kind
#: and not all of them; the count beside them is what makes that honest.
DEFAULT_ROWS = 20

#: What a panel is, once it has been asked. `pending` is the read that did not
#: happen: a deadline spent before its turn, which is the state a console shows
#: while it is still loading the rest.
READY = "ready"
EMPTY = "empty"
PENDING = "pending"
ERROR = "error"
STATES = (READY, EMPTY, PENDING, ERROR)

#: Where a panel's rows come from. Most are one statement over one Program.
#: `facts` is the read whose subject is single -- a Program is one Program, and
#: a table with one row and twelve columns is a shape nobody can read -- and
#: `checks` is the one whose rows are an answer rather than a row: the standing
#: checks about this Program, asked through the function `rk run` asks them
#: with, so a console and a run cannot disagree about whether it is sound.
SQL = "sql"
FACTS = "facts"
CHECKED = "checks"


@dataclass(frozen=True)
class Read:
    """One panel: what it is called, what it asks, and what it is called back."""

    name: str
    caption: str
    columns: tuple[str, ...]
    rows: str
    total: str
    source: str = SQL


#: The Program itself, as pairs. `lifecycle` is not in the query because
#: `program.lifecycle` already decides what two timestamps mean, and a CASE
#: expression here would be a second opinion about the same two columns.
#: The Halt's reason is not read: it is a person's own words about a Program,
#: and 59 settled that those do not go on a surface reached as the runtime.
PROGRAM = Read(
    name="program",
    caption="the Program, its configuration and its Halt",
    columns=("fact", "value"),
    rows=(
        "SELECT p.slug, p.name, coalesce(p.platform, ''),"
        "       p.opened_at::text, p.closed_at::text, p.purge_after::text,"
        "       coalesce(h.status, 'running'), coalesce(h.changed_at::text, ''),"
        "       coalesce(h.changed_by, ''),"
        "       coalesce(c.revision::text, ''), coalesce(c.schema_version::text, ''),"
        "       coalesce(c.canonical_sha256, '')"
        "  FROM programs p"
        "  LEFT JOIN program_halts h ON h.program_id = p.id"
        "  LEFT JOIN LATERAL ("
        "        SELECT revision, schema_version, canonical_sha256"
        "          FROM program_configurations"
        "         WHERE program_id = p.id"
        "         ORDER BY revision DESC LIMIT 1) c ON true"
        " WHERE p.id = $1"
    ),
    total="",
    source=FACTS,
)

#: Whether the Program is sound, asked with the function `rk run` asks it with
#: and narrowed to this Program. The corpus-wide families are not here: the
#: roles family reads the role catalogue and the baseline family reads the
#: server, and `rk db verify` asks both on a connection that owns the schema.
#: A console holding that connection would be a console that could migrate.
CHECKS = Read(
    name="checks",
    caption="the standing checks about this Program, as a run asks them",
    columns=("check", "holds", "detail"),
    rows="",
    total="",
    source=CHECKED,
)

#: The order the pairs are named in, which is the order the columns come back.
PROGRAM_FACTS = (
    "slug",
    "name",
    "platform",
    "opened",
    "closed",
    "purge after",
    "halt",
    "halt changed",
    "halt changed by",
    "configuration revision",
    "configuration schema",
    "configuration digest",
)

#: Criterion 4's ladder, as rows rather than as a status column, because the
#: seven words are not one machine's vocabulary. `proposed` and `supported`
#: belong to the Hypothesis machine, `validated` and `reported` to the Finding
#: machine, and `attempted`, `observed` and `exploited` are not statuses at all
#: -- they are a Test that ran, an Observation that is cited and a
#: demonstration that holds. Each is asked of the rows that would carry it, so
#: a rung shows because the thing happened and not because a column says so.
FINDINGS = Read(
    name="findings",
    caption="every Finding, and how far the claim behind it got",
    columns=(
        "finding",
        "status",
        "severity",
        "proposed",
        "attempted",
        "observed",
        "supported",
        "validated",
        "exploited",
        "reported",
        "blocked",
    ),
    rows=(
        "SELECT f.label, f.status, f.severity,"
        "       (EXISTS (SELECT 1 FROM finding_hypotheses fh"
        "                 WHERE fh.finding_id = f.id))::text,"
        "       (EXISTS (SELECT 1 FROM finding_hypotheses fh"
        "                  JOIN tests t ON t.hypothesis_id = fh.hypothesis_id"
        "                  JOIN test_runs tr ON tr.test_id = t.id"
        "                 WHERE fh.finding_id = f.id))::text,"
        "       (EXISTS (SELECT 1 FROM finding_evidence fe"
        "                 WHERE fe.finding_id = f.id))::text,"
        "       (EXISTS (SELECT 1 FROM finding_hypotheses fh"
        "                  JOIN hypotheses h ON h.id = fh.hypothesis_id"
        "                 WHERE fh.finding_id = f.id AND h.status = 'supported'))::text,"
        "       (f.validated_by_test_run_id IS NOT NULL)::text,"
        "       (EXISTS (SELECT 1 FROM impact_demonstrations d"
        "                 WHERE d.finding_id = f.id))::text,"
        "       (f.reported_at IS NOT NULL)::text,"
        "       (EXISTS (SELECT 1 FROM report_blockers(f.id) b"
        "                 WHERE b.severity = 'hard'))::text"
        "  FROM findings f"
        " WHERE f.program_id = $1"
        " ORDER BY f.status_changed_at DESC, f.label"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM findings WHERE program_id = $1",
)

CHAINS = Read(
    name="chains",
    caption="the chains that were composed, and what each one starts from",
    columns=("chain", "entry", "steps", "built"),
    rows=(
        "SELECT c.label, array_to_string(c.entry, ', '), count(s.id)::text, c.built_at::text"
        "  FROM chains c"
        "  LEFT JOIN chain_steps s ON s.chain_id = c.id"
        " WHERE c.program_id = $1"
        " GROUP BY c.id, c.label, c.entry, c.built_at"
        " ORDER BY c.built_at DESC"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM chains WHERE program_id = $1",
)

#: What was filed, and whether it still describes its Finding. A rendering is
#: bytes taken at a moment; if the Finding has moved since, the bytes are a
#: projection of a state that is over -- which is the one thing an operator
#: about to approve a document has to be told before they read it.
REPORTS = Read(
    name="reports",
    caption="the renderings on file, and whether each still matches its Finding",
    columns=(
        "finding", "rendering", "status", "template", "digest",
        "rendered", "freshness", "approved",
    ),
    # `rendering` is the row's own id, on the panel because the report verb asks
    # for it by name: an operator reporting a Finding names the bytes they read,
    # and the identifier of those bytes is a thing they have to be able to read
    # off the console rather than go to `rk ui read` for.
    rows=(
        "SELECT f.label, r.id, f.status, r.template_id, r.content_sha256, r.rendered_at::text,"
        "       CASE WHEN r.rendered_at < f.status_changed_at THEN 'stale'"
        "            ELSE 'current' END,"
        "       (EXISTS (SELECT 1 FROM finding_transitions ft"
        "                 WHERE ft.approved_rendering_id = r.id))::text"
        "  FROM report_renderings r"
        "  JOIN findings f ON f.id = r.finding_id"
        " WHERE r.program_id = $1"
        " ORDER BY r.rendered_at DESC"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM report_renderings WHERE program_id = $1",
)

SLATES = Read(
    name="slates",
    caption="what the scheduler offered, and which of it was taken",
    columns=("offered", "rank", "task", "kind", "task status", "consumed"),
    rows=(
        "SELECT s.offered_at::text, s.ordinal::text, t.label, t.kind, t.status,"
        "       s.consumed::text"
        "  FROM task_slate s"
        "  JOIN tasks t ON t.id = s.task_id AND t.program_id = s.program_id"
        " WHERE s.program_id = $1"
        " ORDER BY s.offered_at DESC, s.ordinal"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM task_slate WHERE program_id = $1",
)

#: The runs, without either jsonb column. `mission_packet` is what a run was
#: told and `result` is what it said back, and both are model context measured
#: in kilobytes -- a console that put them in a list would be spending a
#: campaign's whole output on a page nobody scrolls.
AGENT_RUNS = Read(
    name="agent_runs",
    caption="the Agent runs, in the order they started",
    columns=("run", "role", "model", "effort", "task", "stopped", "tokens", "started", "finished"),
    rows=(
        "SELECT a.label, a.role, a.model, a.effort, coalesce(t.label, ''),"
        "       coalesce(a.stop_reason, ''),"
        "       (coalesce(a.input_tokens, 0) + coalesce(a.output_tokens, 0))::text,"
        "       a.started_at::text, coalesce(a.finished_at::text, '')"
        "  FROM agent_runs a"
        "  LEFT JOIN tasks t ON t.id = a.task_id"
        " WHERE a.program_id = $1"
        " ORDER BY a.started_at DESC"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM agent_runs WHERE program_id = $1",
)

#: The Tool runs, without either sha256 blob or the args jsonb. `args` is a
#: tool's own words about a target and `result_sha256` points at bytes measured
#: in kilobytes, so a console that put them in a list would be spending a
#: campaign's output on a page nobody scrolls -- the same reason `agent_runs`
#: leaves out its two jsonb columns. Paired with `agent_runs` because criterion
#: 1 pairs them: a run a model started and a tool that run reached for are two
#: different rows, and showing one without the other would answer half of it.
TOOL_RUNS = Read(
    name="tool_runs",
    caption="the Tool runs, in the order they started",
    columns=("run", "tool", "transport", "status", "run by", "task", "started", "finished"),
    rows=(
        "SELECT tr.label, tr.tool, tr.transport, tr.status, coalesce(a.label, ''),"
        "       coalesce(t.label, ''), tr.started_at::text, coalesce(tr.finished_at::text, '')"
        "  FROM tool_runs tr"
        "  LEFT JOIN agent_runs a ON a.id = tr.agent_run_id"
        "  LEFT JOIN tasks t ON t.id = tr.task_id"
        " WHERE tr.program_id = $1"
        " ORDER BY tr.started_at DESC"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM tool_runs WHERE program_id = $1",
)

#: Which Identity a run is holding, and whether it still is. The Entity is
#: joined for its label and not for its Program: 013 put `program_id` on the
#: Lease itself so that the event trigger would not have to join, and scoping
#: through the Entity instead would be this read deciding a Lease belongs to
#: whichever Program its Identity does.
LEASES = Read(
    name="leases",
    caption="which Identity is held by which run, and until when",
    columns=("identity", "slot", "class", "held by", "acquired", "expires", "released"),
    rows=(
        "SELECT e.label, i.slot_name, i.class, r.label,"
        "       l.acquired_at::text, l.expires_at::text, coalesce(l.released_at::text, '')"
        "  FROM identity_leases l"
        "  JOIN identities i ON i.entity_id = l.identity_entity_id"
        "  JOIN entities e ON e.id = i.entity_id"
        "  JOIN agent_runs r ON r.id = l.holder_agent_run_id"
        " WHERE l.program_id = $1"
        " ORDER BY l.acquired_at DESC"
        " LIMIT $2"
    ),
    total="SELECT count(*) FROM identity_leases WHERE program_id = $1",
)

#: The whole Program's tokens first, then each lane. A null ceiling is spelled
#: rather than blanked: "no ceiling" and "not known" are different answers and
#: an empty cell would be read as either.
BUDGETS = Read(
    name="budgets",
    caption="what each ceiling allows, what has been spent and what is left",
    columns=(
        "scope",
        "token ceiling",
        "tokens spent",
        "tokens left",
        "request ceiling",
        "requests spent",
        "requests left",
    ),
    rows=(
        "SELECT scope, token_ceiling, tokens_spent, tokens_left,"
        "       request_ceiling, requests_spent, requests_left"
        "  FROM ("
        "    SELECT 0 AS ord, 'program' AS scope,"
        "           coalesce(b.token_budget::text, 'no ceiling') AS token_ceiling,"
        "           b.tokens_spent::text AS tokens_spent,"
        "           coalesce(b.tokens_left::text, 'no ceiling') AS tokens_left,"
        "           '' AS request_ceiling, '' AS requests_spent, '' AS requests_left"
        "      FROM program_budget b WHERE b.program_id = $1"
        "    UNION ALL"
        "    SELECT 1, l.kind,"
        "           coalesce(l.token_budget::text, 'no ceiling'),"
        "           (l.tokens_spent + l.tokens_reserved)::text,"
        "           coalesce(l.tokens_free::text, 'no ceiling'),"
        "           coalesce(l.request_budget::text, 'no ceiling'),"
        "           (l.requests_spent + l.requests_reserved)::text,"
        "           coalesce(l.requests_free::text, 'no ceiling')"
        "      FROM lane_budget l WHERE l.program_id = $1"
        "  ) ceilings"
        " ORDER BY ord, scope"
        " LIMIT $2"
    ),
    total=(
        "SELECT (SELECT count(*) FROM program_budget WHERE program_id = $1)"
        "     + (SELECT count(*) FROM lane_budget WHERE program_id = $1)"
    ),
)

READS = (
    PROGRAM, CHECKS, FINDINGS, CHAINS, REPORTS, SLATES, AGENT_RUNS, TOOL_RUNS, LEASES, BUDGETS
)
NAMES = tuple(read.name for read in READS)
BY_NAME = {read.name: read for read in READS}


@dataclass(frozen=True)
class Panel:
    """One read, once it has been asked: what came back and what did not.

    `total` is what the Program holds and `rows` is what fitted, so the
    difference is the omission marker -- computed from the two rather than
    carried beside them, because a marker with its own arithmetic is a second
    opinion about the same subtraction.
    """

    name: str
    caption: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    total: int
    state: str
    detail: str = ""

    @property
    def omitted(self) -> int:
        return max(self.total - len(self.rows), 0)

    def summary(self) -> dict:
        return {
            "panel": self.name,
            "caption": self.caption,
            "state": self.state,
            "detail": self.detail,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "total": self.total,
            "omitted": self.omitted,
        }


def panel(
    connection: pg.Connection, program_id: str, slug: str, read: Read, *, limit: int
) -> Panel:
    """Ask one read, in a transaction that cannot write and does not outlive it."""
    with connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        rows, total = _read(connection, program_id, slug, read, limit=limit)
    return Panel(
        name=read.name,
        caption=read.caption,
        columns=read.columns,
        rows=rows,
        total=total,
        state=READY if rows else EMPTY,
    )


def deferred(read: Read, *, detail: str) -> Panel:
    """A read that has not happened, named so a console can say what is missing."""
    return Panel(
        name=read.name,
        caption=read.caption,
        columns=read.columns,
        rows=(),
        total=0,
        state=PENDING,
        detail=detail,
    )


def read(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    names: Sequence[str] = NAMES,
    limit: int = DEFAULT_ROWS,
    deadline: float | None = None,
) -> Report:
    """Ask the named reads about the Program this configuration names.

    `deadline` is a `time.monotonic` instant and not a duration, because the
    caller is a page with a whole budget rather than a panel with one: the
    reads that fit are read and the rest are reported as pending, which is what
    a console shows while a large campaign is still coming back.
    """
    ledger = Ledger()
    facts: dict[str, object] = {
        "program_id": None,
        "program_slug": None,
        "limits": {"rows_per_panel": limit},
        "panels": [],
    }

    unknown = [name for name in names if name not in BY_NAME]
    if unknown:
        ledger.fail(
            "panels",
            f"no such panel: {', '.join(unknown)}; the panels are {', '.join(NAMES)}",
            code=INVALID_CONFIGURATION,
            source="argument:--panel",
        )
        return report(COMMAND, ledger, **facts)

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return report(COMMAND, ledger, **facts)
    slug = configuration.document["program"]["name"]
    facts["program_slug"] = slug
    ledger.hold("configuration", f"{slug}, schema {configuration.schema_version}")

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(COMMAND, ledger, **facts)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(COMMAND, ledger, **facts)
        program_id = program.resolve(ledger, connection, slug)
        if program_id is None:
            return report(COMMAND, ledger, **facts)
        facts["program_id"] = program_id
        found = collect(
            ledger, connection, program_id, slug, names=names, limit=limit, deadline=deadline
        )
    facts["panels"] = [item.summary() for item in found]
    return report(COMMAND, ledger, **facts)


def collect(
    ledger: Ledger,
    connection: pg.Connection,
    program_id: str,
    slug: str,
    *,
    names: Sequence[str] = NAMES,
    limit: int = DEFAULT_ROWS,
    deadline: float | None = None,
) -> tuple[Panel, ...]:
    """Ask each read in turn, and report the ones that stopped rather than stop.

    A refused statement is this panel's failure and not the page's. Each read
    is its own transaction, so the refusal is rolled back before the next one
    starts -- without that, one unreadable panel would leave every panel after
    it reporting a transaction that was already aborted.
    """
    collected = []
    for name in names:
        wanted = BY_NAME[name]
        if deadline is not None and time.monotonic() >= deadline:
            collected.append(deferred(wanted, detail="not read yet: the page ran out of time"))
            ledger.hold(name, "not read yet: the page ran out of time")
            continue
        try:
            found = panel(connection, program_id, slug, wanted, limit=limit)
        except pg.DatabaseError as error:
            collected.append(
                Panel(
                    name=wanted.name,
                    caption=wanted.caption,
                    columns=wanted.columns,
                    rows=(),
                    total=0,
                    state=ERROR,
                    detail=str(error),
                )
            )
            ledger.fail(
                name,
                f"this panel could not be read: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            continue
        collected.append(found)
        ledger.hold(name, f"{len(found.rows)} of {found.total} row(s)")
    return tuple(collected)


#: The report forms this installation carries. Not a panel: a form belongs to
#: the installation and not to a Program, so there is no `program_id` to scope
#: it by and nothing to omit -- the registry is a short fixed list and a chooser
#: that paginated it would be answering a question nobody has.
FORMS_COMMAND = "ui forms"
FORMS = "SELECT id, platform, name FROM report_templates ORDER BY id"


def forms(runtime: pg.Settings) -> Report:
    """Every form a report may be asked for, so a chooser can offer them.

    A command of its own rather than a panel, and a report rather than a list,
    because the caller is a page that has to render whether or not this read
    worked: a form chooser with nothing in it and the refusal beside it is a
    page an operator can act on, and an exception out of a template is not.

    On the runtime connection, and asserted to be it before a statement runs:
    this is one of the reads the console makes as the runtime, so a URL that
    could also lift a Halt is refused here the same way `read` refuses it.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"forms": []}
    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(FORMS_COMMAND, ledger, **facts)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(FORMS_COMMAND, ledger, **facts)
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            found = [
                [str(identity), str(platform), str(name)]
                for identity, platform, name in connection.execute(FORMS).rows
            ]
    facts["forms"] = found
    ledger.hold("report_templates", f"{len(found)} form(s) are registered")
    return report(FORMS_COMMAND, ledger, **facts)


def _read(
    connection: pg.Connection, program_id: str, slug: str, read: Read, *, limit: int
) -> tuple[tuple[tuple[str, ...], ...], int]:
    """One read's rows and the count behind them, by where the read comes from.

    The one place `source` is switched on. `facts` and `checks` are each their
    own rows and are their own count -- a Program is one Program and a check is
    an answer, so there is nothing bounded and nothing to count past what came
    back. A statement is bounded rows beside a second statement that counts
    without the bound, which is what makes the omission marker honest.
    """
    if read.source == FACTS:
        rows = _facts(connection, program_id, read)
        return rows, len(rows)
    if read.source == CHECKED:
        rows = tuple(
            (check.name, _held(check.ok), check.detail)
            for check in integrity.program_checks(connection, slug)
        )
        return rows, len(rows)
    rows = tuple(
        tuple(_text(value) for value in row)
        for row in connection.execute(read.rows, (program_id, limit)).rows
    )
    total = int(connection.execute(read.total, (program_id,)).scalar() or 0)
    return rows, total


def _facts(
    connection: pg.Connection, program_id: str, read: Read
) -> tuple[tuple[str, ...], ...]:
    """One Program's twelve columns, turned on their side into named pairs."""
    found = connection.execute(read.rows, (program_id,)).rows
    if not found:
        return ()
    # The two timestamps go to `program.lifecycle` as they came back, nulls and
    # all: it reads absence, and a null spelled as the empty string would tell
    # it this Program had been closed and retired.
    values = dict(zip(PROGRAM_FACTS, found[0]))
    pairs = [(name, _text(values[name])) for name in PROGRAM_FACTS]
    pairs.append(("lifecycle", program.lifecycle(values["closed"], values["purge after"])))
    return tuple(pairs)


def _held(ok: bool) -> str:
    """A check's answer as a word, because `True` is a Python noun and not an answer."""
    return "yes" if ok else "no"


def _text(value: object) -> str:
    """One column as the console prints it, with null as absence and not as a word."""
    return "" if value is None else str(value)
