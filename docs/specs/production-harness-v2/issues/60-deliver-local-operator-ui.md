# 60 — Deliver the local operator UI

**What to build:** Provide a local dashboard over the same bounded application queries and operator verbs as the CLI, with no independent interpretation of campaign truth.

**Blocked by:** 59 — Deliver the complete operator CLI.

**Status:** resolved

**Reading on criterion 2:** "the same application query as the corresponding CLI read" is
the whole design, and following it honestly turned up the gap it was written to catch.
`rk state`, `rk decision list` and `rk report` already existed and are what the records,
decisions and reports pages call. The Program's lifecycle and integrity, its slates, agent
runs, leases, budgets, findings, chains and filed renderings had no CLI read at all -- 59's
surface reaches every one of them through a verb that writes or through `rk state`, which
is the model's read and not the operator's. So the answer was not to write ten statements
into the renderer: it was `panels.py`, the reads themselves, exposed as `rk ui read` and
consumed by the pages. The console then has no query, and the criterion is structural
rather than a habit -- `tests/test_ui.py::SurfaceTest` reads `ui.py` and fails on a SQL
keyword in it.

**Reading on criterion 5:** the fallback is not an error path, because there is no state of a
record page that shows a summary instead of the record. The canonical text is rendered from
`state.read`'s own bytes every time, and the projection goes beside it. The projection is
keyed by the record's digest as well as its label, so it cannot outlive the bytes it was
taken from: a record that moved has a new digest, the key misses, and the page says the held
summary was taken from other bytes and is not this record, rather than putting last
revision's sentence under this revision's heading. A label with nothing held says so. That
also makes forgetting an entry a legitimate eviction policy, which is what keeps the store
bounded.

**Reading on criterion 6:** the coverage is split by what each half can answer. Everything
answerable without a database is `tests/test_ui.py` -- routing, the CSRF token, escaping,
keyboard access, redaction, the four panel states, the seven rungs, the structural no-SQL
audit, and `Host`, `Origin`, headers and the body limit against a real socket. Everything
that needs a live schema is `OperatorConsoleTest` in `tests/test_database.py`: nine
statements and one function actually running against a hundred and forty tables, the ladder asked of rows
that climbed it, two Programs where isolation is a question about two rather than about one
and an absence, bounded rendering, the deadline, one panel's refusal not taking the page,
read-only enforcement, and all six verbs submitted as forms through `respond`.

- [x] The UI shows Program lifecycle and integrity, Tasks and Slates, Agent and Tool runs, Leases, budgets, pending decisions, Surface, Hypotheses, Tests, Findings, chains and reports by stable label.
- [x] Every view is backed by the same application query as the corresponding CLI read and never accesses Postgres tables directly.
- [x] Halt, clear, pending-decision and human-report actions invoke the same typed operator operations and display their durable Event outcome.
- [x] Proposed, attempted, observed, supported, validated, exploited and reported states remain visually distinct, including unsound and stale warnings.
- [x] Summaries are non-authoritative hash-keyed projections and fall back to canonical text when unavailable or stale.
- [x] Cross-Program isolation, redaction, keyboard access, empty/error/loading states and bounded large-campaign rendering have automated coverage.

## Comments

Implemented on 2026-08-17.

`src/redkraken/panels.py` (the ten reads and `rk ui read`), `src/redkraken/ui.py` (the
console, its router, its forms and its server), the `ui serve`, `ui read` and `ui forms`
subcommands in `src/redkraken/cli.py`, `tests/test_ui.py` and `OperatorConsoleTest` in
`tests/test_database.py`. No migration: this ticket adds no table, no function and no
grant, which is the point of it.

### The ten reads are the ticket's own list

Criterion 1 names fifteen areas. Four of them are already somebody's read and stay that
way: Tasks, Surface, Hypotheses and Tests are `rk state`, which is the model's
compact read of its own records and is shown on the console as what it is; pending decisions
are `rk decision list`. The other ten are the panels -- `program`, `checks`, `slates`,
`agent_runs`, `tool_runs`, `leases`, `budgets`, `findings`, `chains` and `reports`.

Two of the ten are not a table of rows, so a `Read` carries a source -- `sql`, `facts` or
`checks`. `program` is one statement about one Program turned on its side into named pairs,
because a table with one row and twelve columns is a shape nobody can read; its `lifecycle`
pair is `program.lifecycle` rather than a `CASE` expression, since that function already
decides what those two timestamps mean and a second spelling of it would be a second opinion.
`checks` is not a statement at all: it is `integrity.program_checks`, the function `rk run`
asks soundness with, narrowed to this Program -- so a console and a run cannot disagree about
whether a campaign is sound. The corpus-wide families stay off it, because the roles family
reads the role catalogue and the baseline family reads the server, and a console holding the
connection those need would be a console that could migrate.

Each panel is one statement in a transaction of its own, on a read-only connection, bounded
by `LIMIT` and counted by a second statement without one. A transaction each is what makes
one refusal one panel: without it, the first failed statement leaves every later one
reporting an aborted transaction and a single typo takes the whole page.

### What a panel is when it has not answered

A panel is `READY`, `EMPTY`, `PENDING` or `ERROR`, and the four are different answers rather
than three ways of drawing nothing. `EMPTY` is the Program holding no rows of that kind.
`PENDING` is the page's budget running out before the read was asked, which is the loading
state the criterion names and is a real state here rather than a spinner: the reads are
synchronous, so a page that has run out of time says which panels it did not get to instead
of holding the request open. `ERROR` is the statement being refused, and it carries what
Postgres said.

### Three connections, because the console is three roles

`rk ui serve` takes three connection strings. The panels read as the runtime, the record
index reads as the agent because that is whose isolation it describes, and the six verbs run
as the operator. A console handed one string in all three places is the thing worth
refusing, and it is refused by the database rather than by the renderer: it renders every
page and cannot lift a Halt, which `test_a_console_holding_the_runtime_where_the_operator_belongs_cannot_act`
asks as a 400 with `rk2_human` in it.

### The verbs are 29's and 59's, submitted as forms

Six verbs, all reached through `operator`: halt, resume, answer, supersede, report and
clear-gate. The console adds no confirmation of its own and no state machine of its own --
the result page is rendered rather than redirected to, because a resubmitted verb is refused
by the database and not by this process, so showing the outcome stays honest on a reload.
What each verb wrote is its own jsonb answer, printed as the Event it is; a verb the database
refused says so and says it wrote nothing.

### The threat model is the socket, not a login

Loopback by default, one origin settled after the bind so `--port 0` still checks the `Host`
it actually got, a `Host` that is not this console's origin answered 421, a cross-origin
`Origin` answered 403, a body over the limit answered 413, and a token this process alone
holds on every form. There is no login and no account, because there is no remote: the
authority is the operator connection string, and anybody who can reach the socket already
has the machine. What the checks are for is the browser -- a page in another tab that can
reach `127.0.0.1` and would otherwise be able to post a Halt.

Nothing the console renders is trusted with a tag. Every value goes through one escape,
including the ones Postgres wrote, and no page carries a connection string: the two
passwords are asserted absent from every page in `test_no_page_this_console_renders_carries_the_connection_it_holds`.
