"""`rk tool run`: run one registered offline tool and keep what it printed.

The interesting part of this command is what it does not decide. Which tools
exist, which roles may run them, which arguments they take, what those arguments
may look like, how long a run gets, how much memory, how many processes and how
many bytes of output -- every one of those is a row in the registry, and this
module reads the answer rather than holding an opinion. What is left here is the
half a database cannot do: start a process, hold it to the ceilings the registry
named, and file what it produced.

The order is the whole design, and it is three moments rather than one:

* Open, and commit. `open_offline_tool_run` validates the call and writes the
  `tool_runs` row before anything starts, so a run that never comes back is a
  row an operator can find. Committing it before the container starts is the
  point: a row that only existed inside the transaction that also ran the
  process would vanish exactly when the process was what went wrong.
* Run, bounded. The plan says what argv to run, where each input Artifact's
  bytes appear, whether the tool has a network at all, and the five ceilings.
  `isolation.run_tool` enforces them while the process is still running, because
  a bound applied to output already read is not a bound.
* Store, link and close, in one transaction. Stdout, stderr and every declared
  output become content-addressed Artifacts this Program holds, each linked to
  the run with the byte count the stream actually reached; then the run closes.
  All of it together, so there is no committed state in which a run is closed as
  a success and its output is not there to read.

Two versions are in play and they are not the same claim. The registry says
which versions of a tool it will admit, as a pattern; the image says which one is
actually installed, when this command asks it. What is recorded on the run is
what the image answered -- so `tool_runs.tool_version` is provenance rather than
policy, and a run made before an upgrade still says what produced its bytes.

Nothing here mints a capability or asks the risk gate. An offline tool makes no
request and reaches no target, so there is nothing for the gate to decide; the
one policy that does reach it is the Halt, and `open_offline_tool_run` applies
that itself. A tool whose registry row says it uses the proxy adapter is put on
the Agent's own one-peer boundary and nothing wider, which is the only way this
command can reach a network at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from redkraken import artifact, config, isolation, migrate, pg, program
from redkraken.outcome import (
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    Ledger,
    Report,
    report,
)
from redkraken.store import Corrupt, Missing, Store


__all__ = [
    "COMMAND",
    "FACTS",
    "IMAGE_VARIABLE",
    "RUN",
    "run",
]


COMMAND = "tool"
RUN = f"{COMMAND} run"

#: Where the image holding the registered executables is named. Environment
#: rather than the Program's configuration file, for `RK_AGENT_IMAGE`'s reason:
#: which image this machine has is a property of the machine, and moving to
#: another one must not read as a policy change. A separate variable from the
#: Agent's because they are separate images -- one holds an SDK and a
#: credential, the other holds tools and must hold neither.
IMAGE_VARIABLE = "RK_TOOL_IMAGE"

#: What this command reports on every path, so a caller parses one document
#: whether the run succeeded, failed, timed out or was refused before it started.
FACTS = ("program_id", "program_slug", "tool_run", "outputs")

#: The registry row, through the one lookup that also refuses. Read here because
#: the runtime has to know which executable to ask its version before it can open
#: a run at all; the array crosses as JSON rather than as an array literal, so
#: there is no quoting rule for this module to reimplement.
REGISTERED = (
    "SELECT executable, to_json(version_argv)::text, timeout_seconds, memory_mb,"
    "       cpu_quota, pids_limit, max_output_bytes"
    "  FROM rk2_offline_tool($1)"
)

#: Which Program this connection is, for the session's lifetime. The verbs read
#: it rather than taking a Program, so that a runtime holding one connection open
#: cannot open a run against another Program by passing a different argument.
BIND = "SELECT set_config('rk2.program_id', $1, false)"

#: The agent run this call belongs to, by the label an operator reads. The
#: Program is in the query because a label is only unique within one.
AGENT_RUN = "SELECT id FROM agent_runs WHERE program_id = $1::uuid AND label = $2"

OPEN = "SELECT open_offline_tool_run($1::uuid, $2, $3, $4::jsonb)"
CLOSE = "SELECT close_offline_tool_run($1::uuid, $2, $3::integer, $4)"

#: One stored stream. `produced_bytes` is what the stream reached rather than
#: what was kept, which is what makes a truncated Artifact readable as a prefix
#: of something longer instead of as the whole of something short.
LINK = (
    "INSERT INTO tool_run_artifacts"
    " (program_id, tool_run_id, stream, output_name, sha256, produced_bytes, truncated)"
    " VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::bigint, $7)"
)


def run(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    root: Path,
    image: str,
    agent_run: str,
    offline_tool: str,
    arguments: Mapping[str, str],
    door: isolation.AgentContainer | None = None,
) -> Report:
    """Run one registered offline tool for one agent run, and file its output."""
    ledger = Ledger()
    answers = _Answers(RUN)

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, answers)
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")

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

        try:
            registered = _registered(connection, offline_tool)
            version = _version(container, registered)
        except pg.DatabaseError as error:
            # The registry's own refusal -- an unknown or disabled tool -- in the
            # registry's words. Reported rather than re-derived, because this
            # module is not the thing that decides which tools exist.
            ledger.fail(
                "tool",
                f"the registry refused {offline_tool}: {_said(error)}",
                code=INVALID_CONFIGURATION,
                source="argument:--tool",
            )
            return _report(ledger, answers)
        except isolation.Unavailable as error:
            ledger.fail(
                "image", str(error), code=MISSING_DEPENDENCY, source=f"environment:{IMAGE_VARIABLE}"
            )
            return _report(ledger, answers)
        ledger.hold("tool", f"{offline_tool} reports itself as {version}")

        # Everything that decides whether this call may happen at all happens
        # here, and the row it writes is committed before the process starts.
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                plan = json.loads(
                    str(
                        connection.execute(
                            OPEN, (run_id, offline_tool, version, json.dumps(dict(arguments)))
                        ).scalar()
                    )
                )
        except pg.DatabaseError as error:
            ledger.fail(
                "call",
                f"the registry refused this call: {_said(error)}",
                code=INVALID_CONFIGURATION,
                source="argument:--argument",
            )
            return _report(ledger, answers)

        answers.tool_run = {
            "label": plan["tool_run"],
            "tool": plan["tool"],
            "version": plan["version"],
            "network": plan["network"],
            "argv": plan["argv"],
            "inputs": [item["label"] for item in plan["inputs"]],
            "status": "running",
            "exit_code": None,
            "detail": None,
        }
        ledger.hold(
            "call",
            f"{plan['tool_run']} opened: {plan['tool']} {plan['version']} on "
            f"{len(plan['inputs'])} input(s), {plan['network']} network, "
            f"{plan['timeout_seconds']}s and {plan['max_output_bytes']} byte(s) at most",
        )

        # From here the row is open and committed, so every way out of this
        # block closes it. The two named failures close it and are reported;
        # anything else -- a store that cannot write, a socket that dropped
        # between the run and the transaction that files it -- closes it saying
        # so and then goes on being whatever it was. An open row left behind is
        # the one state `check_offline_tools` cannot tell from a supervisor that
        # died, so this is the difference between a failure and a mystery.
        try:
            answer = _perform(container, keep, plan)
        except (Missing, Corrupt) as error:
            return _abandon(
                ledger, answers, connection, plan, f"an input Artifact cannot be read: {error}",
                name="integrity", code=INTEGRITY_FAILED, source="artifact_store",
            )
        except isolation.Unavailable as error:
            return _abandon(
                ledger, answers, connection, plan, str(error),
                name="run", code=MISSING_DEPENDENCY, source=f"environment:{IMAGE_VARIABLE}",
            )
        except BaseException as error:
            _closing(connection, plan, f"the supervisor could not run the tool: {error!r}")
            raise

        status, detail, stopped = _verdict(answer, plan)
        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
                answers.outputs = [
                    _keep_stream(connection, keep, answers.program_id, plan, stream, name, captured)
                    for stream, name, captured in _streams(answer, plan)
                ]
                closed = json.loads(
                    str(
                        connection.execute(
                            CLOSE, (plan["tool_run_id"], status, answer.exit_code, detail)
                        ).scalar()
                    )
                )
        except BaseException as error:
            _closing(connection, plan, f"the output could not be filed: {error!r}")
            raise

    answers.tool_run.update(status=closed["status"], exit_code=closed["exit_code"], detail=detail)
    kept = sum(item["byte_size"] for item in answers.outputs)
    ledger.hold(
        "output",
        f"{len(answers.outputs)} Artifact(s), {kept} byte(s): "
        + ", ".join(f"{item['stream']} {item['label']}" for item in answers.outputs),
    )
    # A run the supervisor stopped is reported as a fault, because what was kept
    # is a fragment and the ceiling that cut it is the operator's to set. A tool
    # that decided its own exit is not: exiting non-zero on purpose -- no match,
    # nothing to do -- is a tool this command ran correctly, and reported as an
    # exit class it would send an operator to fix a machine that is working. The
    # difference either way is on the run's own row, which every path here gives.
    if stopped:
        ledger.fail(
            "run",
            f"{plan['tool_run']} did not succeed: {detail}",
            code=INVALID_CONFIGURATION,
            source=f"offline_tool:{plan['tool']}",
        )
    else:
        ledger.hold(
            "run",
            f"{plan['tool_run']} exited 0" if status == "success"
            else f"{plan['tool_run']} did not succeed: {detail}",
        )
    return _report(ledger, answers)


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


def _registered(connection: pg.Connection, tool: str) -> dict:
    """The registry row for one enabled tool, or the registry's own refusal."""
    executable, version_argv, timeout, memory, cpu, pids, output = connection.execute(
        REGISTERED, (tool,)
    ).rows[0]
    return {
        "executable": str(executable),
        "version_argv": [str(item) for item in json.loads(str(version_argv))],
        "ceilings": isolation.Ceilings(
            timeout_seconds=float(timeout),
            memory_mb=int(memory),
            cpu_quota=float(cpu),
            pids_limit=int(pids),
            max_output_bytes=int(output),
        ),
    }


def _version(container: isolation.ToolContainer, registered: Mapping[str, object]) -> str:
    """Ask the installed tool what it is, in a container with nothing in it.

    The registry says which versions it admits and the image says which one is
    there; neither can answer for the other, so the answer is taken from the
    thing that will actually run. No network and no inputs: a version probe that
    could reach anything would be a way to reach something.

    What comes back is one line and is not interpreted here. `open_offline_tool_run`
    holds it against the registry's pattern, which is where the decision belongs
    -- this is the half that cannot lie about what is installed.
    """
    answer = isolation.run_tool(
        container,
        (str(registered["executable"]), *registered["version_argv"]),
        ceilings=registered["ceilings"],
    )
    reported = answer.stdout.data.decode("utf-8", "replace").strip().splitlines()
    if answer.exit_code != 0 or not reported:
        raise isolation.Unavailable(
            f"the tool image cannot say what version of {registered['executable']} it holds"
        )
    return reported[0].strip()


def _perform(
    container: isolation.ToolContainer, keep: Store, plan: Mapping[str, object]
) -> isolation.ToolProcess:
    """Run the plan the database produced, and nothing this module invented.

    The input bytes are read out of the store by the hash the plan names, so
    `Store.load`'s verification is what puts them in the container: bytes that no
    longer hash to their own name never reach a tool, and the run is abandoned
    instead of being fed something that is not what the Artifact says it is.
    """
    return isolation.run_tool(
        container,
        [str(item) for item in plan["argv"]],
        ceilings=isolation.Ceilings(
            timeout_seconds=float(plan["timeout_seconds"]),
            memory_mb=int(plan["memory_mb"]),
            cpu_quota=float(plan["cpu_quota"]),
            pids_limit=int(plan["pids_limit"]),
            max_output_bytes=int(plan["max_output_bytes"]),
        ),
        inputs={item["path"]: keep.load(item["sha256"]) for item in plan["inputs"]},
        outputs=[item["name"] for item in plan["outputs"]],
        network=str(plan["network"]),
    )


def _streams(answer: isolation.ToolProcess, plan: Mapping[str, object]):
    """Every stream worth keeping, in the vocabulary the link table has.

    Stdout and stderr are always kept, empty or not. An empty stream is a fact
    about the run -- it is how "printed nothing" is told from "nobody looked" --
    and it is what lets a run that failed silently still close with its output
    recorded rather than as a success that stored nothing.
    """
    yield "stdout", None, answer.stdout
    yield "stderr", None, answer.stderr
    for declared in plan["outputs"]:
        found = answer.outputs.get(declared["name"])
        if found is not None:
            yield "output", declared["name"], found


def _keep_stream(
    connection: pg.Connection,
    keep: Store,
    program_id: str,
    plan: Mapping[str, object],
    stream: str,
    name: str | None,
    captured: isolation.Captured,
) -> dict:
    """File one stream as an Artifact and link it to the run that produced it."""
    record = artifact.filed(connection, keep, program_id, captured.data, kind="tool_output")
    connection.execute(
        LINK,
        (
            program_id,
            plan["tool_run_id"],
            stream,
            name,
            record["sha256"],
            captured.produced,
            captured.truncated,
        ),
    )
    return {
        "stream": stream,
        "output_name": name,
        "label": record["label"],
        "sha256": record["sha256"],
        "byte_size": record["byte_size"],
        "produced_bytes": captured.produced,
        "truncated": captured.truncated,
    }


def _verdict(
    answer: isolation.ToolProcess, plan: Mapping[str, object]
) -> tuple[str, str | None, bool]:
    """How the run ended: the two words the column has, one sentence, and who ended it.

    A timeout and an overrun are errors rather than successes with a note. Both
    mean the same thing about the output -- what was kept is a fragment of a run
    that was taken away -- and a reader deciding whether to cite it needs that in
    the status rather than in the detail. Both are also the supervisor's doing
    rather than the tool's, which is the third answer: it separates a ceiling
    somebody has to raise from a tool that ran and said no.
    """
    if answer.timed_out:
        return (
            "error",
            f"the run exceeded its {plan['timeout_seconds']}s ceiling and was stopped",
            True,
        )
    if answer.overflowed:
        return "error", f"the run exceeded its {plan['max_output_bytes']} byte output bound", True
    if answer.exit_code != 0:
        return "error", f"the tool exited {answer.exit_code}", False
    return "success", None, False


def _abandon(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    plan: Mapping[str, object],
    detail: str,
    *,
    name: str,
    code: str,
    source: str,
) -> Report:
    """Close a run that never got as far as producing output, and say why.

    A run opened and then left open would be indistinguishable from a supervisor
    that died holding one, which is the one state `check_offline_tools` reports
    as a fault rather than as history. So the row is closed as an error carrying
    the reason, which is a true account of what happened to it.
    """
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
        connection.execute(CLOSE, (plan["tool_run_id"], "error", None, detail))
    answers.tool_run.update(status="error", detail=detail)
    ledger.fail(name, detail, code=code, source=source)
    return _report(ledger, answers)


def _closing(connection: pg.Connection, plan: Mapping[str, object], detail: str) -> None:
    """Close an open run on the way out of a failure this command did not name.

    Best effort, and deliberately silent when it fails: the caller is already
    carrying an exception that says more than this one would, and a connection
    that has just dropped is exactly the case where the close cannot land. What
    it buys when it does land is the same thing `_abandon` buys -- a row that
    reads as a run that failed rather than as a supervisor that disappeared.
    """
    try:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {RUN}",))
            connection.execute(CLOSE, (plan["tool_run_id"], "error", None, detail))
    except (pg.ConnectionError_, pg.DatabaseError, OSError):
        return


def _said(error: pg.DatabaseError) -> str:
    """What the database refused with, in the sentence it refused in.

    The primary message rather than the whole rendering: the detail and the
    context line say where in a PL/pgSQL body it happened, which is a fact about
    this corpus and not an answer to the operator who typed the command.
    """
    return error.primary or str(error)


def image_from_environment(given: str | None = None) -> str | None:
    """The tool image, from the argument or from the variable behind it.

    Nothing is defaulted for `execution.boundary`'s reason: an image name guessed
    here would run whatever the guess happened to match, which is the sort of
    mistake that looks like a working run.
    """
    return given or os.environ.get(IMAGE_VARIABLE) or None
