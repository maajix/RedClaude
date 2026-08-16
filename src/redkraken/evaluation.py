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

One seam is short of production and it is named rather than hidden: the door.
The fixture listens on loopback, and the door refuses to dial a loopback address
-- `scope.address_refusal` at compile time and `authorize_identity_egress_address`
at dial time -- which is the rule that keeps a Program configuration from
pointing the harness at the machine it runs on. So an evaluation whose `work`
needs the proxy has no route to the fixture today, and one whose `work` does not
runs end to end and files honest zeroes. Ticket 78 is where that route is
decided; nothing here should widen what the door will dial in the meantime.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

from redkraken import config, fixture, migrate, pg, program
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


__all__ = ["COMMAND", "FACTS", "RUN", "Served", "configuration", "evaluate", "origin", "served"]


COMMAND = "playbook"
RUN = f"{COMMAND} evaluate"

#: What this command answers on every path, refused or performed.
FACTS = ("playbook", "fixture", "repeats", "runs", "verdict")

#: Loopback and nothing else. A fixture bound to a routable address would be a
#: synthetic target reachable from off this machine, and the first thing an
#: evaluation does is point an autonomous agent at it.
HOST = "127.0.0.1"

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


@dataclass(frozen=True, slots=True)
class Served:
    """Where one variant of one fixture is listening.

    It does not carry the fixture: `served()` is a context manager around one,
    so every caller already holds the `Fixture` this is about, and a second
    spelling of the name here would be a second thing to keep in step.
    """

    variant: str
    port: int


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
    #: `program.Execute`: what one open Program does. Carried here rather than
    #: passed per repeat so the evaluator cannot substitute a different worker
    #: between repeats of one measurement.
    work: program.Execute
    corpus: Path

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
def served(one: fixture.Fixture, variant: str) -> Iterator[Served]:
    """Serve one variant of one fixture on an ephemeral loopback port."""
    handler = _application(one).get("handler")
    if not callable(handler):
        raise fixture.FixtureError(
            "value_malformed", one.name, "app.py does not define handler(variant)"
        )
    server = ThreadingHTTPServer((HOST, 0), handler(variant))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Served(variant=variant, port=server.server_address[1])
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
        'protocols = ["http"]\n'
        'paths = ["/"]\n'
        f"{identities}",
        encoding="utf-8",
    )
    return path


def _marking(subject: Subject, variant: str) -> program.Execute:
    """`subject.work`, with the Program marked as an evaluation before it runs.

    Wrapping rather than marking afterwards, and the order is the whole reason:
    the marker is what excludes this Program from `playbook_promotion_evidence`,
    so a Program that ran first and was marked second would spend the interval as
    ordinary runtime evidence. A crash in between would leave it that way for
    good, which is criterion 4's last clause arriving by accident.
    """

    def execute(ledger: Ledger, connection: pg.Connection, program_id: str) -> dict:
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
        return subject.work(ledger, connection, program_id)

    return execute


def evaluate(
    settings: pg.Settings,
    workspace: Path,
    *,
    playbook: str,
    fixture_name: str,
    work: program.Execute,
    corpus: Path = migrate.CORPUS,
    fixtures: Mapping[str, fixture.Fixture] | None = None,
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
    """One repeat: every variant opened and worked, then counted."""
    programs: dict[str, str] = {}
    for variant in subject.variants:
        with served(subject.fixture, variant) as where:
            path = configuration(workspace, subject.slug(variant, index), subject.fixture, where)
            result = program.run(
                settings, path, corpus=subject.corpus, execute=_marking(subject, variant)
            )
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
