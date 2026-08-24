"""`rk playbook evaluate`: run one Playbook against one fixture and file the repeats.

This is ticket 46 criterion 6, and the criterion is mostly about what this file
does NOT contain. There is no evaluation-mode Program opener, no evaluation Agent
launcher and no evaluation path through the door. A fixture is served on a
loopback port, a Program is opened against that origin by `program.run`, the work
is done by whatever `execute` callable the caller would have used against a real
target, and the result is counted by `record_playbook_test_run`. Every one of
those is the production seam, which is the only way the measurement means
anything: a Playbook graded through a special harness is a Playbook graded
against a system nobody ships.

Four things are worth stating about the shape.

**The application is executed from the bytes the catalogue digested.** Not
imported from disk by path -- `fixtures.source_sha256` is what a test run freezes
and what R5 checks, so the process answering the requests has to be the one those
bytes describe. Compiling `Fixture.source` is how "what was served" and "what was
recorded" stop being two separate claims.

**Each repeat gets fresh Programs.** A repeat that inherited the previous one's
hypotheses would be counting one claim twice and calling it agreement, and the
median over repeats -- which is what 036's sensitivity clause reads -- would be a
median over one measurement copied three times.

**Both halves of a pair are separate Programs.** The secure half is the control,
and a control sharing a Program with the run it controls would put both sets of
observations in one row-level-security scope. `admitted_secure` would then be
counting claims from wherever, which is precisely the number that decides whether
the Playbook read the target or recited its own class.

**The counting is not here.** `record_playbook_test_run` derives every number
from the rows the two Programs produced. This module reports what it ran; the
database reports what happened.

**There are two routes to the fixture**, and which one a run took is a fact in
the report rather than a thing to infer from the shape of the numbers.

*loopback*, when no Agent boundary is passed. The fixture listens on 127.0.0.1
and the caller's `work` talks to it directly. The door has no part in it and
could not have one: it refuses to dial a loopback address -- `scope.address_refusal`
at compile time and `authorize_identity_egress_address` at dial time -- which is
the rule that keeps a Program configuration from pointing the harness at the
machine it runs on. A `work` that goes through the proxy reaches nothing down
this route and files honest zeroes, which is what it did before ticket 78 and
still does on a machine with no container engine.

*door*, when an Agent boundary is passed. The fixture listens on the one address
this machine answers on from inside that boundary -- `isolation.host_route`, the
gateway of the door's own routable network, which is private and is not reachable
from the children's internal network -- and the Program records where it put it
with `open_fixture_address`. The door dials that address for that Program and
files ordinary Receipts against it, so a graded run produces the same evidence a
real engagement produces.

Nothing about what the door will dial was widened to get the second route. The
fixture address is an address substituted for a host the Program's own policy
already classes `target`, offered only for a Program in `evaluation_programs`,
and the
database refuses to record anything that is not one private host. Both refusals
named above are untouched, and both still refuse.
"""

from __future__ import annotations

import contextlib
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from redkraken import config, execution, fixture, isolation, migrate, pg, program, tls
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


__all__ = [
    "COMMAND",
    "COST",
    "COST_FACTS",
    "FACTS",
    "RUN",
    "Route",
    "Served",
    "configuration",
    "cost",
    "evaluate",
    "origin",
    "route",
    "served",
]


COMMAND = "playbook"
RUN = f"{COMMAND} evaluate"
COST = f"{COMMAND} cost"

#: What this command answers on every path, refused or performed.
FACTS = ("playbook", "fixture", "route", "repeats", "runs", "verdict")

#: What `cost` answers, on the same terms.
COST_FACTS = ("route", "repeats", "envelope_tokens", "playbooks", "programs", "tokens")

#: Loopback, which is where a fixture listens when nothing has to reach it from
#: inside a container. A fixture bound to a routable address would be a synthetic
#: target reachable from off this machine, and the first thing an evaluation does
#: is point an autonomous agent at it.
HOST = "127.0.0.1"

#: The two routes, named once. They are the values of the `route` fact and of
#: `playbook_test_runs.route`, and `check_playbook_tests` reads the second one to
#: decide whether a run that filed no tool run is a silent zero or a fault.
LOOPBACK = "loopback"
DOOR = "door"

#: The domain a fixture is named under in scope, which is not the address it is
#: bound to. `scope.compile_policy` refuses an inclusion that names a loopback
#: address -- "an inclusion may not name one", because such a rule points the
#: harness at its own infrastructure -- so a Program scoped to `127.0.0.1` is a
#: Program that never opens. RFC 6761 reserves `.localhost` for precisely what
#: is wanted instead: a name that means the loopback the fixture is listening on
#: and can mean nothing else. A resolver that answers it answers 127.0.0.1, and
#: the door then refuses that address for being loopback -- which is the right
#: failure, because an evaluation's bytes are not target egress and must not be
#: able to leave as if they were.
DOMAIN = "localhost"

#: The variants of a pair, in the order they are run. `record_playbook_test_run`
#: takes the vulnerable Program first for the same reason: the secure half is the
#: control for that run, not a run of its own.
PAIR = ("vulnerable", "secure")

OPEN_FIXTURE_ADDRESS = (
    "SELECT open_fixture_address($1::uuid, $2, $3, $4::integer, $5, $6)"
)
PLAYBOOK = "SELECT id::text, source_sha256 FROM playbooks WHERE path = $1"
REPEATS = "SELECT required_repeats FROM playbook_test_policy WHERE id = 1"
MARK = (
    "INSERT INTO evaluation_programs (program_id, playbook_id, fixture_id, variant)"
    " VALUES ($1::uuid, $2::uuid, $3, $4) ON CONFLICT (program_id) DO NOTHING"
)
MARKED = (
    "SELECT playbook_id::text, fixture_id, variant FROM evaluation_programs"
    " WHERE program_id = $1::uuid"
)
RECORD = "SELECT record_playbook_test_run($1::uuid, $2, $3::uuid, $4::uuid)::text"
ENVELOPE = "SELECT cost_reference_tokens FROM scheduler_weights WHERE active"

#: What the corpus still owes, per Playbook, at the text each one ships. The
#: repeat count is a parameter rather than a scalar subquery so that the number
#: the report states and the number the arithmetic used are the same read.
#:
#: A fixture already run more times than the policy asks is owed nothing rather
#: than owed a negative, and a run at an older text counts for nothing at all --
#: `playbook_sha256` is the join, the same way `playbook_test_verdict` reads it.
#:
#: The route is the second parameter, and it is what a filed run has to match to
#: count off. `playbook_test_verdict` counts a repeat whichever route filed it,
#: which is right for a verdict -- a run is a run -- and wrong for this number:
#: the loopback route opens a Program and attempts nothing in it, so a corpus
#: with 16500 loopback rows against it would report a campaign that owes nothing
#: and has measured nothing. What is stated is what the campaign *this machine*
#: would run still has to do.
#:
#: The two Programs an `own_pair` fixture costs per repeat is `Subject.variants`
#: read in SQL: `PAIR` is the vulnerable and secure halves, and a fixture that is
#: not its own pair borrows the other half from a fixture that is.
OWED = (
    "WITH bound AS ("
    "  SELECT p.path, b.kind,"
    "         (SELECT count(*) FROM playbook_test_runs r"
    "           WHERE r.playbook_id = p.id"
    "             AND r.playbook_sha256 = p.source_sha256"
    "             AND r.fixture_id = b.fixture_id"
    "             AND r.route = $2) AS filed"
    "    FROM playbooks p, LATERAL playbook_fixture_binding(p.id) b)"
    " SELECT path, count(*)::bigint,"
    "        sum(least(filed, $1::bigint))::bigint,"
    "        sum(greatest($1::bigint - filed, 0)"
    "            * CASE WHEN kind = 'own_pair' THEN 2 ELSE 1 END)::bigint"
    "   FROM bound GROUP BY path ORDER BY path"
)
VERDICT = "SELECT verdict, reason FROM playbook_test_verdict($1::uuid, NULL)"

#: Budgets a fixture evaluation runs under. Small on purpose and not
#: configurable: a synthetic target on loopback that needs thousands of requests
#: is a run that has stopped measuring the Playbook.
BUDGETS = """
[budgets]
requests = 200
tokens = 400000
run_tokens = 40000
run_requests = 40
lane_tokens = 100000
lane_requests = 100
concurrency = 1
burst = 50
window_seconds = 3600
"""

#: How many passes one graded Program is worked for. `rk run` performs one pass
#: and reports the word a driver loop reads; an engagement is that loop run by an
#: operator, and a Program worked once is a Program stopped after recon. That is
#: not a Playbook grade: the claim recon proposes is `proposed`, the ranking pass
#: is what makes it `testable` and derives the hunt Task, and the Playbook is
#: selected when that Task is dispatched. So the evaluation drives the same loop.
#:
#: A ceiling rather than "until it stops", because `chooser_cut_off` and
#: `task_attempted` are both "there is more to do" and a Program that keeps
#: answering one of them would never return. `[budgets]` above is the real bound
#: -- 400000 tokens and 200 requests per Program -- and this is the bound on the
#: number of times the harness is willing to ask.
PASSES = 12


@dataclass(frozen=True, slots=True)
class Route:
    """How the Playbook's requests are meant to reach the fixture.

    The name and the address travel together because they are one decision: an
    evaluation binds where it binds *because* of who has to reach it, and the
    two halves stored apart is how a run ends up serving on loopback and
    reporting that it went through the door.
    """

    name: str
    host: str


@dataclass(frozen=True, slots=True)
class Served:
    """Where one variant of one fixture is listening.

    It does not carry the fixture: `served()` is a context manager around one,
    so every caller already holds the `Fixture` this is about, and a second
    spelling of the name here would be a second thing to keep in step.

    It does carry the host, because on the door route that is not a constant
    and it is the value the fixture address row is written from. What answered
    and what was recorded have to be one address or the Receipt is fiction.

    It carries the scheme for the same reason and it is stated rather than
    defaulted. Almost every fixture in this corpus is cleartext, so a default
    would be right almost every time -- and the one it would be wrong about is
    the one whose whole ground truth is its handshake, recorded as though there
    had not been one.
    """

    variant: str
    host: str
    port: int
    #: `http` or `https`, decided by whether the fixture's `app.py` configures a
    #: handshake. Nothing else reads it: it is what the scope document and the
    #: fixture address row are written from, and those two have to agree with
    #: what the socket actually did.
    scheme: str
    #: The PEM certificate of the authority this call minted, for an https
    #: fixture, and `None` for every other one. Ticket 93: it is the one anchor
    #: the door verifies this fixture's handshake against, and it is carried on
    #: this record rather than left in the directory because the directory is
    #: deleted when the block ends. It is the certificate alone -- the key stays
    #: where `tls.authority` put it and is handed to nobody.
    trust_anchor: str | None = None


@dataclass(frozen=True, slots=True)
class Repeat:
    """One repeat: the Programs it ran in and the run row it filed."""

    index: int
    programs: Mapping[str, str]
    run_id: str

    def as_dict(self) -> dict:
        return {"index": self.index, "programs": dict(self.programs), "run_id": self.run_id}


@dataclass(frozen=True, slots=True)
class Subject:
    """What is being measured, fixed for the whole evaluation.

    One object rather than six arguments repeated down the call chain, and the
    grouping is not arbitrary: these are close to the values `run_key` is built
    from, so a repeat that differs in any of them is a different measurement
    rather than another sample of this one.
    """

    playbook: str
    playbook_id: str
    playbook_sha256: str
    fixture: fixture.Fixture
    #: What one open Program does, asked for by the configuration it will run
    #: under. Carried here rather than passed per repeat so the evaluator cannot
    #: substitute a different worker between repeats of one measurement.
    #:
    #: A factory rather than a `program.Execute`, because one kind of Task is
    #: performed by the runtime itself: `replay.run` resolves the Program and the
    #: schema revision the Test was authored under out of a Program
    #: configuration, and refuses a `perform` Task on a machine that names none.
    #: An evaluation writes one configuration per repeat and per variant, so the
    #: path is not knowable when the caller builds its worker and is knowable
    #: here.
    work: Callable[[Path], program.Execute]
    corpus: Path
    #: Decided once for the whole evaluation, not per repeat: two repeats that
    #: reached the fixture by different routes are not two samples of one
    #: measurement, whatever the median over them says.
    route: Route

    @property
    def variants(self) -> tuple[str, ...]:
        """The Programs one repeat opens: both halves, or only the target."""
        return PAIR if self.fixture.paired else PAIR[:1]

    def slug(self, variant: str, repeat: int) -> str:
        return f"eval-{self.playbook_sha256[:8]}-{self.fixture.name}-{variant}-{repeat}"


def _application(one: fixture.Fixture) -> Mapping[str, object]:
    """Execute the fixture's `app.py` from the bytes the catalogue digested.

    `exec` on package bytes, which is what an import of the same file would do
    with the one difference that matters here: these are the bytes `fixture.py`
    hashed into `source_sha256`, so a file edited between the compile and the
    serve cannot be what answered the requests. Nothing outside the corpus
    reaches this -- `compile_corpus` is what produced the argument.
    """
    namespace: dict[str, object] = {
        "__name__": f"redkraken.fixtures.{one.name.replace('-', '_')}",
        "__file__": one.application_path,
    }
    exec(compile(one.source, one.application_path, "exec"), namespace)  # noqa: S102 -- corpus bytes
    return namespace


def origin(one: fixture.Fixture) -> str:
    """The host this fixture is scoped to.

    Derived from the fixture's own name so that two fixtures served at once are
    two origins, and a Receipt or a scope refusal names which target it was
    about rather than the port it happened to get.
    """
    return f"{one.name}.{DOMAIN}"


@contextlib.contextmanager
def served(one: fixture.Fixture, variant: str, host: str = HOST) -> Iterator[Served]:
    """Serve one variant of one fixture on an ephemeral port of one address.

    The address defaults to loopback and is widened by exactly one caller: the
    door route, which binds on the gateway this machine answers at inside the
    Agent network so the proxy can dial it. That address is a host address, so
    what the narrowing buys is bounded: children of the internal network have no
    route to it, which is the property the door route rests on and what
    `test_isolation.py` proves. It is one address rather than `0.0.0.0` so that
    the fixture is not also on every other interface this machine has.

    What is yielded takes the address from the socket rather than from the
    argument, because a bind that answered somewhere else has to be visible: the
    fixture address recorded for the door is this address, and the Receipt is
    pinned to it.

    A fixture whose `app.py` also defines `tls(variant, context)` is served over
    TLS instead, and that second entry point exists because one class cannot be
    graded without it. 025 records `transport.tls_configuration` as `probe_only`
    over `tls_version`, `cipher` and `alpn`; not one of the three is a thing a
    request handler can write, so a corpus of handlers behind cleartext is a
    corpus that can never hold a positive for it.

    The certificate is minted here rather than by the fixture, and the split is
    the same one the fixture format already makes between ground truth and
    application. Who the target *is* changes every run -- a fresh authority in a
    directory that dies with the context manager, a leaf naming the origin this
    evaluator chose -- and is nobody's business but the evaluator's. What the
    target *negotiates* is the fixture's whole subject, so the context is handed
    over to be configured before a byte crosses it.

    The authority is this run's, and its certificate is yielded with the address
    because ticket 93 needs one party to have it: the door, measuring this one
    fixture, for this one Program. `open_fixture_address` stores it beside the
    address, `authorize_fixture_address` hands it back for that Program's own
    host and port, and it is purged with the evaluation. Nobody else is given
    it, and nobody at all is given the key -- so a client that reaches this
    fixture without going through that row still cannot verify the chain, which
    is what `tests/test_fixture.py` reads it as.
    """
    namespace = _application(one)
    handler = namespace.get("handler")
    if not callable(handler):
        raise fixture.FixtureError(
            "value_malformed", one.name, "app.py does not define handler(variant)"
        )
    configure = namespace.get("tls")
    if configure is not None and not callable(configure):
        raise fixture.FixtureError(
            "value_malformed", one.name, "app.py defines tls as something other than a function"
        )
    server = ThreadingHTTPServer((host, 0), handler(variant))
    with contextlib.ExitStack() as stack:
        scheme = "http"
        anchor: str | None = None
        if configure is not None:
            directory = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="rk2-fixture-tls-")
            )
            # The listening socket, wrapped after the bind, so the address the
            # caller is told about is the one the kernel already gave out. The
            # handshake then happens inside `accept`, which is where a fixture
            # that refuses a client's protocol floor refuses it -- and refusing
            # there is the point of this pair rather than a fault in it.
            minted = tls.authority(Path(directory))
            context = minted.context(origin(one))
            configure(variant, context)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            scheme = "https"
            # Read here rather than pointed at, because the directory above is
            # deleted when this block ends and a path that outlives the file it
            # names is worse than no answer.
            anchor = minted.certificate.read_text()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            bound = server.server_address
            yield Served(
                variant=variant,
                host=str(bound[0]),
                port=int(bound[1]),
                scheme=scheme,
                trust_anchor=anchor,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def configuration(directory: Path, slug: str, one: fixture.Fixture, where: Served) -> Path:
    """Write the Program configuration this variant is evaluated under.

    The scope is the one origin the fixture is listening on and nothing else. A
    wildcard here would authorise an agent that guessed a hostname to reach
    something that is not the fixture, and the claim this module makes is that
    the requests went to the target being graded.

    That origin is `origin(one)` at the port `served` bound, rather than the
    loopback address itself, for the reason `DOMAIN` gives: the production scope
    compiler refuses an inclusion naming a loopback address, and this document
    goes through the production compiler.

    Written as text rather than through a TOML writer because there is no writer
    in the standard library and this package has no dependencies. Every value
    interpolated below was validated before it got here -- the slug against
    `config.SLUG`, the host and the Identity labels against the corpus patterns,
    the port by the socket -- and `config.load` is what reads the result back, so
    a document this produced wrongly is a refusal rather than a running Program.
    """
    identities = "".join(
        f'\n[[identity]]\nname = "{name}"\nslot_ref = "slot://identity/{name}"\n'
        for name in one.identities
    )
    path = directory / f"{slug}.toml"
    path.write_text(
        "schema_version = 1\n\n"
        "[program]\n"
        f'name = "{slug}"\n'
        'platform = "self"\n\n'
        "[rules_of_engagement]\n"
        "mutation = false\n"
        f"{BUDGETS}\n"
        "[[scope.include]]\n"
        f'host = "{origin(one)}"\n'
        f"ports = [{where.port}]\n"
        f'protocols = ["{where.scheme}"]\n'
        'paths = ["/"]\n'
        f"{identities}",
        encoding="utf-8",
    )
    return path


def route(ledger: Ledger, boundary: isolation.AgentContainer | None) -> Route | None:
    """Which route this evaluation takes, and the address it binds the fixture on.

    No boundary is the loopback route and needs nothing of the machine. A
    boundary is the door route, and the address is asked of the engine rather
    than configured: the one thing that must be true of it is that the door can
    reach it, and the door's own network attachment is the only place that fact
    lives.

    A boundary that is described but cannot be read is a failure, not a quiet
    fall back to loopback. An operator who described one asked for a run graded
    through the door, and a loopback run under that name files zeroes that read
    exactly like a Playbook which found nothing.
    """
    if boundary is None:
        return Route(name=LOOPBACK, host=HOST)
    try:
        host = isolation.host_route(
            isolation.engine_for(boundary.engine), boundary.proxy_container
        )
    except isolation.Unavailable as unavailable:
        ledger.fail(
            "route",
            f"an Agent boundary is described, so the fixture has to be served where "
            f"the door can dial it, and {unavailable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{execution.PROXY_CONTAINER}",
        )
        return None
    return Route(name=DOOR, host=host)


def _graded_work(
    subject: Subject, variant: str, where: Served, path: Path
) -> program.Execute:
    """`subject.work`, with the Program prepared to be graded before it runs.

    Two preparations, both inside the wrapper: the Program is marked as an
    evaluation, and on the door route the address its fixture is listening at is
    recorded. Neither can follow the work.

    Wrapping rather than marking afterwards, and the order is the whole reason:
    the marker is what excludes this Program from `playbook_promotion_evidence`,
    so a Program that ran first and was marked second would spend the interval as
    ordinary runtime evidence. A crash in between would leave it that way for
    good, which is criterion 4's last clause arriving by accident.

    The fixture address is written in the same wrapper and for the same reason
    one step on: on the door route the work's first request is what has to find
    the fixture, so the address has to be recorded before the work starts. It is
    written after the marker rather than before it because the database will
    only accept it for a Program that is already an evaluation.

    Both preparations happen on the first pass and no other. `_repeat` works one
    Program until its Slate is empty, so this callable is invoked once per pass;
    `open_fixture_address` writes a row and does not merge one, and a second
    write of the same address would refuse the pass over a fact that has not
    changed since the first.
    """
    prepared = False
    work = subject.work(path)

    def execute(ledger: Ledger, connection: pg.Connection, program_id: str) -> dict:
        nonlocal prepared
        if prepared:
            return work(ledger, connection, program_id)
        connection.execute(MARK, (program_id, subject.playbook_id, subject.fixture.name, variant))
        marked = tuple(connection.execute(MARKED, (program_id,)).rows[0])
        if marked != (subject.playbook_id, subject.fixture.name, variant):
            # `ON CONFLICT DO NOTHING` above leaves a resumed Program that
            # already grades something else alone rather than re-pointing it,
            # and nothing is attempted in it: its rows are counted elsewhere.
            ledger.fail(
                "evaluation_program",
                f"program {program_id} already grades {marked[1]} ({marked[2]}); "
                f"it cannot also be the {variant} evaluation of {subject.fixture.name}",
                code=INVALID_CONFIGURATION,
                source="argument:--fixture",
            )
            return {}
        ledger.hold(
            "evaluation_program",
            f"{program_id} grades {subject.fixture.name} ({variant}) and "
            "contributes no promotion evidence",
        )
        if subject.route.name == DOOR:
            try:
                connection.execute(
                    OPEN_FIXTURE_ADDRESS,
                    (
                        program_id,
                        where.scheme,
                        origin(subject.fixture),
                        where.port,
                        where.host,
                        where.trust_anchor,
                    ),
                )
            except pg.DatabaseError as error:
                # The database holds every rule about what a fixture address
                # may be -- one private host, a Program that is an evaluation,
                # a host and port this Program's own policy already classes
                # `target`. Its refusal is the message worth reporting; a
                # second opinion here would be a second place for the rule to
                # drift.
                ledger.fail(
                    "fixture_address",
                    f"the fixture for {subject.fixture.name} ({variant}) is served at "
                    f"{where.host}:{where.port} and the database would not record it: {error}",
                    code=INVALID_CONFIGURATION,
                    source="function:open_fixture_address",
                )
                return {}
            ledger.hold(
                "fixture_address",
                f"{origin(subject.fixture)}:{where.port} is dialled at {where.host} "
                f"for {program_id}",
            )
        prepared = True
        return work(ledger, connection, program_id)

    return execute


def evaluate(
    settings: pg.Settings,
    workspace: Path,
    *,
    playbook: str,
    fixture_name: str,
    work: Callable[[Path], program.Execute],
    corpus: Path = migrate.CORPUS,
    fixtures: Mapping[str, fixture.Fixture] | None = None,
    boundary: isolation.AgentContainer | None = None,
) -> Report:
    """Run one Playbook against one fixture for the configured repeats, and file each.

    Returns after reading the verdict back, which is deliberately not the same as
    promoting: promotion is `playbooks.promoted_at`, guarded by 035 and 036, and
    this command has no business setting it. What it produces is the evidence
    those guards read.
    """
    ledger = Ledger()
    answers: dict[str, object] = {
        "playbook": playbook,
        "fixture": fixture_name,
        "route": None,
        "repeats": 0,
        "runs": [],
        "verdict": None,
    }

    catalogue = fixture.FIXTURES if fixtures is None else fixtures
    one = catalogue.get(fixture_name)
    if one is None:
        ledger.fail(
            "fixture",
            f"{fixture_name} is not in the fixture corpus ({len(catalogue)} fixture(s))",
            code=INVALID_CONFIGURATION,
            source="argument:--fixture",
        )
        return report(RUN, ledger, **answers)
    ledger.hold(
        "fixture",
        f"{one.name} ({one.kind}) contains {', '.join(one.classes)} at {one.subject}, "
        f"ground truth {one.ground_truth_sha256[:12]}",
    )

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        return report(RUN, ledger, **answers)

    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(RUN, ledger, **answers)

        taken = route(ledger, boundary)
        if taken is None:
            return report(RUN, ledger, **answers)
        answers["route"] = taken.name
        ledger.hold(
            "route",
            f"the fixture is served at {taken.host} and reached over the {taken.name} route",
        )

        rows = connection.execute(PLAYBOOK, (playbook,)).rows
        if not rows:
            ledger.fail(
                "playbook",
                f"{playbook} is not a Playbook this database carries",
                code=INVALID_CONFIGURATION,
                source="argument:--playbook",
            )
            return report(RUN, ledger, **answers)
        subject = Subject(
            playbook=playbook,
            playbook_id=str(rows[0][0]),
            playbook_sha256=str(rows[0][1]),
            fixture=one,
            work=work,
            corpus=corpus,
            route=taken,
        )

        repeats = int(str(connection.execute(REPEATS).scalar()))
        answers["repeats"] = repeats
        ledger.hold(
            "policy",
            f"{repeats} repeat(s) of {len(subject.variants)} Program(s) at text "
            f"{subject.playbook_sha256[:12]}, from playbook_test_policy",
        )
        if not _nameable(ledger, subject, repeats):
            return report(RUN, ledger, **answers)

        filed: list[Repeat] = []
        for index in range(repeats):
            one_repeat = _repeat(ledger, connection, settings, workspace, subject, index)
            if one_repeat is None:
                break
            filed.append(one_repeat)
            answers["runs"] = [item.as_dict() for item in filed]

        verdict = connection.execute(VERDICT, (subject.playbook_id,)).rows
        if verdict:
            answers["verdict"] = {"verdict": str(verdict[0][0]), "reason": str(verdict[0][1])}
            ledger.hold("verdict", f"{verdict[0][0]}: {verdict[0][1]}")

    return report(RUN, ledger, **answers)


def cost(
    settings: pg.Settings,
    *,
    boundary: isolation.AgentContainer | None = None,
) -> Report:
    """What grading the whole shipped corpus would cost, before any of it runs.

    Ticket 84 asks for the cost stated before the campaign starts, and the
    reason it asks is that every repeat is a real Agent run: the number here is
    not how long a query takes, it is how many autonomous sessions an operator
    is about to pay for. So it is counted off the two things the verdict counts
    off -- `playbook_fixture_binding` and `playbook_test_policy` -- and it
    discounts what is already filed at the text each Playbook ships, because a
    corpus half graded owes half a campaign.

    The unit is tokens, which is what this harness reserves in: 023 says the
    scarce resource is rate-limit budget rather than dollars, and
    `scheduler_weights.cost_reference_tokens` is the envelope one Agent run is
    ranked against. What is reported is therefore the reservation the campaign
    implies rather than a bill, and no price is invented to make it one.

    The route is stated with the number because it decides whether the campaign
    measures anything: `rk playbook evaluate` on a machine that describes no
    Agent boundary opens each Program and attempts nothing inside it, so a
    corpus graded that way costs nothing and files zeroes. It is also what a
    filed run has to match to be counted off -- runs from the other route are
    rows about a different campaign, and discounting them would state a corpus
    as half graded on the strength of repeats that reached nothing.
    """
    ledger = Ledger()
    answers: dict[str, object] = {
        "route": None,
        "repeats": 0,
        "envelope_tokens": None,
        "playbooks": [],
        "programs": 0,
        "tokens": 0,
    }

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        return report(COST, ledger, **answers)

    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(COST, ledger, **answers)

        taken = route(ledger, boundary)
        if taken is None:
            return report(COST, ledger, **answers)
        answers["route"] = taken.name
        ledger.hold(
            "route",
            f"the campaign would run over the {taken.name} route"
            + (
                f", dialling each fixture at {taken.host} through the door"
                if taken.name == DOOR
                else ", where a Program is opened and nothing is attempted in it, "
                "so what it would file is zeroes"
            ),
        )

        repeats = int(str(connection.execute(REPEATS).scalar()))
        answers["repeats"] = repeats
        ledger.hold(
            "policy",
            f"{repeats} repeat(s) of every fixture in a Playbook's binding, "
            "from playbook_test_policy",
        )

        envelope = connection.execute(ENVELOPE).scalar()
        if envelope is None:
            ledger.fail(
                "envelope",
                "no scheduler_weights row is active, so there is no envelope an "
                "Agent run reserves and no cost this campaign can be stated in",
                code=INVALID_CONFIGURATION,
                source="table:scheduler_weights",
            )
            return report(COST, ledger, **answers)
        answers["envelope_tokens"] = int(str(envelope))

        owed = [
            {
                "playbook": str(path),
                "fixtures": int(str(fixtures)),
                "repeats_filed": int(str(filed)),
                "programs": int(str(programs)),
            }
            for path, fixtures, filed, programs in connection.execute(
                OWED, (repeats, taken.name)
            ).rows
        ]
        answers["playbooks"] = owed
        answers["programs"] = sum(int(one["programs"]) for one in owed)
        answers["tokens"] = int(answers["programs"]) * int(answers["envelope_tokens"])

        ledger.hold(
            "corpus",
            f"{len(owed)} Playbook(s) against "
            f"{max((int(one['fixtures']) for one in owed), default=0)} bound fixture(s) each, "
            f"{sum(int(one['repeats_filed']) for one in owed)} of the required repeat(s) "
            f"already filed on the {taken.name} route at the text they ship",
        )
        ledger.hold(
            "cost",
            f"{answers['programs']} Agent run(s) still owed, reserving "
            f"{answers['tokens']} token(s) against the {answers['envelope_tokens']}-token "
            "envelope one run is ranked against",
        )

    return report(COST, ledger, **answers)


def _nameable(ledger: Ledger, subject: Subject, repeats: int) -> bool:
    """Whether every Program this evaluation opens can be named.

    Checked once and up front, against the configuration reader's own pattern
    rather than a restated length: a slug refused halfway through would leave a
    Playbook with some of its repeats filed, and 036's median would then be a
    median over the repeats that happened to fit.
    """
    unnameable = sorted(
        slug
        for variant in subject.variants
        for index in range(repeats)
        if not config.SLUG.fullmatch(slug := subject.slug(variant, index))
    )
    if unnameable:
        ledger.fail(
            "program_slug",
            f"{unnameable[0]} is not a Program name a configuration admits "
            f"({len(unnameable)} of this evaluation's slugs are not); the fixture "
            "directory name is what has to shrink",
            code=INVALID_CONFIGURATION,
            source="argument:--fixture",
        )
        return False
    return True


def _repeat(
    ledger: Ledger,
    connection: pg.Connection,
    settings: pg.Settings,
    workspace: Path,
    subject: Subject,
    index: int,
) -> Repeat | None:
    """One repeat: every variant opened and worked to an empty Slate, then counted."""
    programs: dict[str, str] = {}
    for variant in subject.variants:
        try:
            with served(subject.fixture, variant, subject.route.host) as where:
                path = configuration(
                    workspace, subject.slug(variant, index), subject.fixture, where
                )
                # Inside the `served` block, and one `_graded_work` for all of
                # the passes: the fixture has to stay on the port the Program
                # recorded, and the address is recorded once.
                graded = _graded_work(subject, variant, where, path)
                passes = 0
                while True:
                    result = program.run(
                        settings, path, corpus=subject.corpus, execute=graded
                    )
                    passes += 1
                    stopped = result.facts.get("stop_reason")
                    if result.violations or passes >= PASSES:
                        break
                    if stopped in (
                        program.STOPPED_NOTHING_TO_EXECUTE,
                        program.STOPPED_AWAITING_DECISION,
                    ):
                        break
                ledger.hold(
                    "passes",
                    f"repeat {index} of {subject.fixture.name} ({variant}) was worked "
                    f"{passes} pass(es) and stopped on {stopped}",
                )
        except tls.Unusable as unusable:
            # A fixture that configures its own handshake needs an authority to
            # configure, and `tls.authority` is the same call `proxy`, `browser`
            # and `doctor` each translate into a refusal of their own. This is
            # this module's translation: a machine with no `openssl` cannot bind
            # this fixture, and saying so once is worth more than a traceback
            # from inside a context manager three frames down.
            ledger.fail(
                "repeat",
                f"repeat {index} of {subject.fixture.name} ({variant}) serves its own "
                f"handshake, so it needs certificate material, and {unusable}",
                code=INVALID_CONFIGURATION,
                source=f"fixture:{subject.fixture.name}",
            )
            return None
        ledger.assertions.extend(result.assertions)
        if result.violations or not result.facts.get("program_id"):
            ledger.refuse(
                "repeat",
                f"repeat {index} of {subject.fixture.name} ({variant}) did not complete; "
                "nothing was filed for it",
                result.violations,
            )
            return None
        programs[variant] = str(result.facts["program_id"])

    try:
        run_id = str(
            connection.execute(
                RECORD,
                (
                    subject.playbook_id,
                    subject.fixture.name,
                    programs[PAIR[0]],
                    programs.get(PAIR[1]),
                ),
            ).scalar()
        )
    except pg.DatabaseError as error:
        # The counting function holds every rule about what a countable run is,
        # so its refusal is the message worth reporting; restating it here would
        # be this module keeping a second opinion about the same rule.
        ledger.fail(
            "repeat",
            f"repeat {index} of {subject.fixture.name} was refused when filed: {error}",
            code=INVALID_CONFIGURATION,
            source="function:record_playbook_test_run",
        )
        return None

    ledger.hold(
        "repeat",
        f"repeat {index} of {subject.fixture.name} filed as {run_id} "
        f"from {len(programs)} Program(s)",
    )
    return Repeat(index=index, programs=programs, run_id=run_id)
