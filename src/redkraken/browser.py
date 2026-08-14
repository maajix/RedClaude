"""`rk browser run`: drive one browser mission through the door and file it.

This is the same three moments `tool.py` has -- open and commit, run bounded,
then store and close in one transaction -- with the two things a browser adds.

The first is a capability. A browser reaches a target, so unlike an offline tool
it needs one, and it is minted by `authorize_tool_run` like every other request
this harness makes: the risk gate decides, the door spends it, and a decision
that is not `allow` closes the mission before a container starts. The capability
is written into the plan the container reads and nowhere else -- not into its
environment, where a page that could read the process table would find it.

The second is that the container cannot be trusted to say where it went. The
driver reports what each step did; it does not report what class of destination
it reached, because a container that could would be a container that could call
an out-of-scope host in-scope. `scope_class` is filled in here, from the Receipt
the door wrote, and a navigation with no Receipt is `denied` -- which is what a
navigation nothing let through actually was.

What names each artifact is here rather than in the driver, for a reason worth
stating: the host has to declare the files it expects out of a container before
the container starts, so the names have to exist on this side already. Composing
them again inside would be two places to change the day a name does.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from redkraken import artifact, config, isolation, migrate, pg, program, proxy, tls
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    Ledger,
    Report,
    report,
)
from redkraken.store import Store


__all__ = [
    "COMMAND",
    "DRIVER",
    "FACTS",
    "IMAGE_VARIABLE",
    "RUN",
    "artifact_names",
    "image_from_environment",
    "run",
]


COMMAND = "browser"
RUN = f"{COMMAND} run"

#: Where the image holding a headless browser is named. Its own variable rather
#: than the tool image's: a browser image carries a browser and its libraries and
#: nothing this harness registers as a tool, and pointing one at the other would
#: start whichever of them happened to answer.
IMAGE_VARIABLE = "RK_BROWSER_IMAGE"

#: What the driver is called inside the container, and what runs it. Copied in as
#: an input rather than baked into the image, so the driver and the runtime that
#: reads its output are one version of one repository.
DRIVER = "/input/browser_driver.py"
PLAN_FILE = "/input/plan.json"
ARGV = ("python3", DRIVER, PLAN_FILE)

#: What this command reports on every path, so a caller parses one document
#: whether the mission ran, was refused or died holding a container.
FACTS = ("program_id", "program_slug", "tool_run", "outputs")

BIND = "SELECT set_config('rk2.program_id', $1, false)"
AGENT_RUN = "SELECT id FROM agent_runs WHERE program_id = $1::uuid AND label = $2"
OPEN = "SELECT open_browser_run($1::uuid, $2::jsonb, $3)"
STEP = "SELECT record_browser_step($1::uuid, $2::integer, $3::jsonb, $4::integer)"
CLOSE = "SELECT close_browser_run($1::uuid, $2, $3)"

#: One stored stream, attributed to the step that produced it. The same table an
#: offline tool run writes to, with the ordinal that says which step saw it.
LINK = (
    "INSERT INTO tool_run_artifacts"
    " (program_id, tool_run_id, stream, output_name, browser_step_ordinal,"
    "  sha256, produced_bytes, truncated)"
    " VALUES ($1::uuid, $2::uuid, $3, $4, $5::integer, $6, $7::bigint, $8)"
)

#: What the door decided about the destination one navigation named. The latest,
#: because a Program's scope version is pinned for the length of a run and two
#: navigations to one URL therefore answer the same; the ordering only matters
#: when a mission navigated somewhere twice and something changed underneath it,
#: and then the last verdict is the one that describes the page it ended on.
CLASSIFIED = (
    "SELECT scope_class FROM receipts"
    " WHERE program_id = $1::uuid AND tool_run_id = $2::uuid"
    "   AND host = $3 AND path = $4"
    " ORDER BY ts_arrival DESC LIMIT 1"
)

#: The one file every mission produces, whatever else it did.
CONSOLE_FILE = "console.jsonl"

#: What each artifact-producing action calls what it kept. A step's ordinal is in
#: the name because two captures of one mission are two files, and the extension
#: is there because an operator who exports one wants it to open.
ARTIFACT_FILES = {
    "capture_dom": "dom-{ordinal}.html",
    "screenshot": "screenshot-{ordinal}.png",
    "probe": "probe-{ordinal}.json",
}

#: The class a navigation is recorded as when the door filed no Receipt for it.
#: Not an omission and not a guess: no Receipt means nothing was let through, and
#: `denied` is the word the scope compiler itself uses for a destination no rule
#: covers.
UNCLASSIFIED = "denied"

#: How much scratch a browser needs. Chromium is told to put its shared memory in
#: TMPDIR by `--disable-dev-shm-usage`, and the few megabytes a command-line tool
#: gets would be a renderer that dies mid-page for reasons no log explains.
SCRATCH_MB = 256


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    root: Path,
    image: str,
    authority: Path,
    agent_run: str,
    steps: Sequence[Mapping[str, object]],
    identity_slot: str | None,
    door: isolation.AgentContainer,
) -> Report:
    """Run one browser mission for one agent run, and file what it saw."""
    ledger = Ledger()
    answers = _Answers(RUN)

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, answers)
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")

    try:
        pin = tls.authority(authority).pin()
    except (tls.Missing, tls.Unusable) as error:
        ledger.fail("authority", str(error), code=MISSING_DEPENDENCY, source="argument:--authority")
        return _report(ledger, answers)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)

    keep = Store(Path(root))
    container = isolation.ToolContainer(image=image, door=door)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        answers.program_id = program.resolve(ledger, connection, answers.slug)
        if answers.program_id is None:
            return _report(ledger, answers)
        connection.execute(BIND, (answers.program_id,))

        rows = connection.execute(AGENT_RUN, (answers.program_id, agent_run)).rows
        if not rows:
            ledger.fail(
                "agent_run",
                f"{agent_run} is not an agent run of this Program",
                code=INVALID_CONFIGURATION,
                source="argument:--agent-run",
            )
            return _report(ledger, answers)
        run_id = str(rows[0][0])

        # Everything that decides whether this mission may happen at all happens
        # in the database, and the rows it writes are committed before anything
        # starts: a mission that never comes back is a plan an operator can read.
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                plan = json.loads(
                    str(
                        connection.execute(
                            OPEN, (run_id, json.dumps(list(steps)), identity_slot)
                        ).scalar()
                    )
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "plan",
                f"the registry refused this mission: {_said(error)}",
                code=INVALID_CONFIGURATION,
                source="argument:--plan",
            )
            return _report(ledger, answers)

        answers.tool_run = {
            "label": plan["tool_run"],
            "plan_sha256": plan["plan_sha256"],
            "identity_slot": plan["identity_slot"],
            "methods": plan["methods"],
            "steps": len(plan["steps"]),
            "status": "running",
            "detail": None,
            "result_digest": None,
        }
        ledger.hold(
            "plan",
            f"{plan['tool_run']} opened: {len(plan['steps'])} step(s), "
            f"{', '.join(plan['methods'])}, {plan['timeout_seconds']}s at most",
        )

        # From here the row is open and committed, so every way out closes it.
        try:
            gate = proxy.as_object(
                _minted(connection, plan["tool_run_id"], f"rk {RUN}")
            )
        except pg.DatabaseError as error:
            return _abandon(
                ledger, answers, connection, plan,
                f"the risk gate refused this mission: {_said(error)}",
                name="capability", source="risk_gate",
            )
        capability = gate.get("capability")
        if not capability:
            return _abandon(
                ledger, answers, connection, plan,
                f"the risk gate answered {gate.get('decision')} rather than allow",
                name="capability", source="risk_gate",
            )
        ledger.hold("capability", f"the risk gate allowed {plan['tool_run']}")

        names = artifact_names(plan)
        try:
            answer = _perform(container, plan, names, str(capability), answers.program_id, pin)
        except isolation.Unavailable as error:
            return _abandon(
                ledger, answers, connection, plan, str(error),
                name="run", source=f"environment:{IMAGE_VARIABLE}",
            )
        except BaseException as error:
            _closing(connection, plan, f"the supervisor could not run the browser: {error!r}")
            raise

        said, status, detail = _read(answer, plan)
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                for recorded in said.get("steps", ()):
                    _record(connection, answers.program_id, plan, recorded)
                answers.outputs = [
                    _keep_stream(connection, keep, answers.program_id, plan, kept, captured)
                    for kept, captured in _streams(said, answer)
                ]
                closed = json.loads(
                    str(connection.execute(CLOSE, (plan["tool_run_id"], status, detail)).scalar())
                )
        except pg.DatabaseError as error:
            # The close refused what the container reported -- an outcome the
            # registry does not admit, or a success that performed half its plan.
            # The mission is closed as the error it is, with the words the
            # database used, rather than left open for a checker to find.
            return _abandon(
                ledger, answers, connection, plan,
                f"what the browser reported was refused: {_said(error)}",
                name="outcome", source="browser_run",
            )
        except BaseException as error:
            _closing(connection, plan, f"the output could not be filed: {error!r}")
            raise

    answers.tool_run.update(
        status=closed["status"], detail=detail, result_digest=closed["result_digest"]
    )
    ledger.hold(
        "output",
        f"{len(answers.outputs)} Artifact(s), "
        f"{sum(item['byte_size'] for item in answers.outputs)} byte(s): "
        + ", ".join(f"{item['stream']} {item['label']}" for item in answers.outputs),
    )
    if status == "success":
        ledger.hold(
            "run",
            f"{plan['tool_run']} performed {closed['recorded']} step(s), "
            f"digest {closed['result_digest'][:12]}",
        )
    else:
        ledger.fail(
            "run",
            f"{plan['tool_run']} did not succeed: {detail}",
            code=INVALID_CONFIGURATION,
            source="browser_run",
        )
    return _report(ledger, answers)


def artifact_names(plan: Mapping[str, object]) -> dict[str, str]:
    """What each producing step's evidence is called, by the ordinal that made it.

    The console is under `browser_driver.CONSOLE` rather than an ordinal because
    it belongs to the mission rather than to a step: a page logs when it likes,
    including while a step that captures nothing is running.
    """
    names = {"console": CONSOLE_FILE}
    for step in plan["steps"]:
        shape = ARTIFACT_FILES.get(str(step["action"]))
        if shape is not None:
            names[str(step["ordinal"])] = shape.format(ordinal=step["ordinal"])
    return names


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    slug: str | None = None
    program_id: str | None = None
    tool_run: dict | None = None
    outputs: list = field(default_factory=list)


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        tool_run=answers.tool_run,
        outputs=answers.outputs,
    )


def _minted(connection: pg.Connection, tool_run_id: str, actor: str) -> str:
    """One capability for this mission, through the gate every request goes through."""
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (actor,))
        return str(connection.execute(proxy.AUTHORIZE_TOOL_RUN, (tool_run_id,)).scalar())


def _perform(
    container: isolation.ToolContainer,
    plan: Mapping[str, object],
    names: Mapping[str, str],
    capability: str,
    program_id: str,
    pin: str,
) -> isolation.ToolProcess:
    """Start the browser, bounded by the ceilings the registry named.

    The three keys added here are the three the database cannot know: which door
    to speak to and with what credentials, which certificate to believe, and what
    to call each file. Nothing else about the plan is touched.
    """
    door = container.door
    address = urlsplit(door.proxy_url)
    carried = dict(plan)
    carried["certificate_pin"] = pin
    carried["program_id"] = program_id
    carried["door"] = {
        "host": address.hostname,
        "port": address.port or 80,
        "headers": {
            proxy.AUTHORIZATION: f"RedKraken {capability}",
            proxy.PROGRAM: program_id,
        },
    }
    carried["console"] = names["console"]
    carried["steps"] = [
        {**step, "artifact": names[str(step["ordinal"])]}
        if str(step["ordinal"]) in names
        else dict(step)
        for step in plan["steps"]
    ]
    return isolation.run_tool(
        container,
        ARGV,
        ceilings=isolation.Ceilings(
            timeout_seconds=float(plan["timeout_seconds"]),
            memory_mb=int(plan["memory_mb"]),
            cpu_quota=float(plan["cpu_quota"]),
            pids_limit=int(plan["pids_limit"]),
            max_output_bytes=int(plan["max_artifact_bytes"]),
        ),
        inputs={
            PLAN_FILE: json.dumps(carried).encode(),
            DRIVER: (Path(__file__).parent / "browser_driver.py").read_bytes(),
        },
        outputs=sorted(set(names.values())),
        network="proxy",
        scratch_mb=SCRATCH_MB,
    )


def _read(
    answer: isolation.ToolProcess, plan: Mapping[str, object]
) -> tuple[dict, str, str | None]:
    """What the container said, and how the mission ended.

    A driver that printed no document at all is a failure whatever it exited
    with: the result document is the only account of what happened inside, and a
    mission closed as a success without one would be a digest over nothing.

    The plan digest is checked because it is cheap and because the one thing it
    catches -- a container that walked a plan other than the one that was
    committed -- is the thing that would make every later comparison a lie.
    """
    printed = answer.stdout.data.decode("utf-8", "replace").strip()
    if answer.timed_out:
        return {}, "error", f"the mission exceeded its {plan['timeout_seconds']}s ceiling"
    if answer.overflowed:
        return {}, "error", f"the mission exceeded its {plan['max_artifact_bytes']} byte bound"
    try:
        said = json.loads(printed) if printed else None
    except ValueError:
        said = None
    if not isinstance(said, dict):
        tail = answer.stderr.data.decode("utf-8", "replace").strip().splitlines()
        return {}, "error", f"the browser reported nothing readable: {tail[-1] if tail else '(silent)'}"
    if said.get("plan_sha256") != plan["plan_sha256"]:
        return said, "error", "the browser walked a plan this mission did not open"
    if said.get("status") == "success":
        return said, "success", None
    return said, "error", str(said.get("detail") or f"the browser exited {answer.exit_code}")


def _record(
    connection: pg.Connection,
    program_id: str,
    plan: Mapping[str, object],
    recorded: Mapping[str, object],
) -> None:
    """One step's outcome, with the part of it the container may not answer for."""
    outcome = dict(recorded["outcome"])
    if recorded["action"] == "navigate":
        outcome["scope_class"] = _classified(connection, program_id, plan, recorded["ordinal"])
    connection.execute(
        STEP,
        (
            plan["tool_run_id"],
            int(recorded["ordinal"]),
            json.dumps(outcome),
            int(recorded.get("network_requests") or 0),
        ),
    )


def _classified(
    connection: pg.Connection, program_id: str, plan: Mapping[str, object], ordinal: object
) -> str:
    """What the door made of the destination one navigation named."""
    for step in plan["steps"]:
        if step["ordinal"] != ordinal:
            continue
        target = urlsplit(str(step["arguments"]["url"]))
        rows = connection.execute(
            CLASSIFIED,
            (program_id, plan["tool_run_id"], target.hostname, target.path or "/"),
        ).rows
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
    return UNCLASSIFIED


def _streams(said: Mapping[str, object], answer: isolation.ToolProcess):
    """Every artifact the container declared and the supervisor actually found.

    Declared and found rather than either alone: the driver says what a step
    produced and under which stream, and the supervisor says what came out of the
    container and how many bytes it reached. A declared file that is not there is
    skipped rather than invented -- a mission that died mid-capture has one fewer
    Artifact, which is true, instead of an empty one, which is not.
    """
    for declared in said.get("artifacts", ()):
        found = answer.outputs.get(declared["file"])
        if found is not None:
            yield declared, found


def _keep_stream(
    connection: pg.Connection,
    keep: Store,
    program_id: str,
    plan: Mapping[str, object],
    declared: Mapping[str, object],
    captured: isolation.Captured,
) -> dict:
    """File one artifact and link it to the step that produced it."""
    record = artifact.filed(connection, keep, program_id, captured.data, kind="tool_output")
    connection.execute(
        LINK,
        (
            program_id,
            plan["tool_run_id"],
            declared["stream"],
            declared["output_name"],
            declared["ordinal"],
            record["sha256"],
            captured.produced,
            captured.truncated,
        ),
    )
    return {
        "stream": declared["stream"],
        "output_name": declared["output_name"],
        "ordinal": declared["ordinal"],
        "label": record["label"],
        "sha256": record["sha256"],
        "byte_size": record["byte_size"],
        "produced_bytes": captured.produced,
        "truncated": captured.truncated,
    }


def _abandon(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    plan: Mapping[str, object],
    detail: str,
    *,
    name: str,
    source: str,
) -> Report:
    """Close a mission that cannot go on, and say why.

    A run opened and left open is the one state `check_browser_runs` reports as a
    fault rather than as history, so the row is closed as an error carrying the
    reason -- which is a true account of what happened to it.
    """
    _closing(connection, plan, detail)
    answers.tool_run.update(status="error", detail=detail)
    ledger.fail(name, detail, code=INVALID_CONFIGURATION, source=source)
    return _report(ledger, answers)


def _closing(connection: pg.Connection, plan: Mapping[str, object], detail: str) -> None:
    """Close an open mission on the way out of a failure, best effort.

    Deliberately silent when it fails: the caller is already carrying a reason
    that says more than this one would, and a connection that has just dropped is
    exactly the case where the close cannot land.
    """
    try:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
            connection.execute(CLOSE, (plan["tool_run_id"], "error", detail))
    except (pg.ConnectionError_, pg.DatabaseError, OSError):
        return


def _said(error: pg.DatabaseError) -> str:
    """What the database refused with, in the sentence it refused in."""
    return error.primary or str(error)


def image_from_environment(given: str | None = None) -> str | None:
    """The browser image, from the argument or from the variable behind it.

    Nothing is defaulted for `execution.boundary`'s reason: an image name guessed
    here would run whatever the guess happened to match.
    """
    return given or os.environ.get(IMAGE_VARIABLE) or None
