"""The only module in this application that constructs the Agent SDK.

One module, so the startup assertion has one seam. `tests/test_agent.py` walks
the source tree and fails if any other module imports `claude_agent_sdk`: an
SDK constructed somewhere else would be an Agent run started without crossing
`agent_run`, and the assertion would be a check on one launch path out of two.

This runs as a child process -- `python -m redkraken._launch`, one job document
on standard input, inside the container `redkraken.isolation` verifies -- for a
reason that is not stylistic. The assertion has to be made against the
environment and the filesystem the child *actually* got, and the only way to be
sure nothing leaked in is to build them from a list out there and then measure
them here, in the process that will use them. It is also why the launch
directory is created here rather than by the supervisor: the supervisor's
filesystem is not this one, so a directory it made would be a directory this
child could not be given.

The order is the whole point. Facts, then one options value, then the pre-spawn
assertion against that value, then the transport built from the same value,
then the init message, and only then a tool the model can call. Every one of
those steps is a gate on the next; a refusal at any of them leaves the steps
after it un-run rather than undone.

The import below is the application's only third-party one, and it is
deliberately not a declared dependency (see `pyproject.toml` and
`doctor.REQUIRED_DISTRIBUTIONS`). What this runtime requires is not a package
but a *pair* -- an SDK version and the CLI version it bundles, held in
`_startup.KNOWN_RUNTIME` -- and a requirement specifier cannot name the second
half of that. Declaring the first
half would state the same fact twice, in a weaker form that a resolver is free
to satisfy with a pair nothing has measured. So the requirement is enforced
where it is decidable: an SDK that is absent, or present at another version, is
an unmeasured runtime and refuses at the assertion.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

from redkraken import agent, packet, roster


try:
    import claude_agent_sdk
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        ResultMessage,
        SystemMessage,
        create_sdk_mcp_server,
        query,
        tool,
    )
except ImportError:
    # Not an error here. An SDK that is not installed is an unmeasured runtime
    # pair, which is a refusal the assertion already knows how to make -- and
    # making it there rather than raising here keeps one refusal path.
    claude_agent_sdk = None


#: The distribution the runtime pair is measured against.
DISTRIBUTION = "claude-agent-sdk"

#: Where the SDK keeps the CLI it was published with.
BUNDLED = ("_bundled", "claude")

#: The messages that may reach the runtime before init has been corroborated.
#: A positive list, because the pair is pinned: on a measured runtime the set
#: of things the transport can emit is fixed, so anything not named here
#: arriving first is an Agent run that did work before it was assessed.
BEFORE_INIT = ("RateLimitEvent",)

#: How the CLI announces itself, and the subtype the announcement must carry.
INIT = "init"

#: Why an init message was never read: something else was produced first, or
#: the run ended without the CLI ever announcing itself.
PREMATURE = "first_message"
ABSENT = "absent"

#: What the child writes when it refuses, on standard error, as one line.
REFUSAL = "startup_refusal"

#: How much of the final answer crosses back. A bound rather than a budget: the
#: result document travels through a pipe and this is proof the run finished,
#: not a transcript. What is kept of it is Promotion's business, not this pipe's.
ANSWER = 1500


class Closed(RuntimeError):
    """A tool was called while the runtime's tool surface was not open."""


class Surface:
    """The tool surface, and the count that makes `exactly once` checkable.

    A flag would answer "is it open"; the criterion is that it opens once, and
    the difference matters -- a surface reopened by a second init message is a
    child whose authentication was corroborated twice and believed both
    times. So opening increments, and being open means having opened exactly
    once.
    """

    def __init__(self) -> None:
        self.opened = 0
        self.served: list[str] = []

    @property
    def ready(self) -> bool:
        return self.opened == 1

    def open(self) -> None:
        self.opened += 1

    def serve(self, name: str) -> None:
        if not self.ready:
            raise Closed(f"{name} was called before the runtime's tool surface opened")
        self.served.append(name)


def runtime_facts() -> dict[str, str | None]:
    """The SDK version, the CLI it bundles and the executable that would run.

    Resolved rather than configured. Each one is read from the installed
    package, so a launch is measured against what is on this machine and not
    against what a caller says is on it. Anything unreadable stays `None` and
    becomes an unmeasured runtime in the assertion.
    """
    facts: dict[str, str | None] = {"sdk_version": None, "cli_version": None, "cli_path": None}
    if claude_agent_sdk is None:
        return facts
    try:
        facts["sdk_version"] = importlib.metadata.version(DISTRIBUTION)
    except (importlib.metadata.PackageNotFoundError, ValueError):
        pass
    try:
        from claude_agent_sdk import _cli_version

        facts["cli_version"] = _cli_version.__cli_version__
    except (AttributeError, ImportError):
        pass
    package = getattr(claude_agent_sdk, "__file__", None)
    try:
        if package:
            facts["cli_path"] = str(Path(package).resolve().parent.joinpath(*BUNDLED))
    except (OSError, TypeError, ValueError):
        pass
    return facts


class Submission:
    """The one result a run may submit, and the count of the tries.

    One, because the Spec says one: "Agents submit one Mission result". A
    second submission is not merged and does not overwrite -- the first is what
    the run proposed, and a later contradiction of it is the run arguing with
    its own output. The attempt is still counted, so a model that tried twice
    is distinguishable from one that submitted once.

    Named for what it holds rather than for the run. `CONTEXT.md` gives
    "Mission" to the packet and tells the rest of us to avoid it -- "a payload,
    not a lifecycle" -- and this is the lifecycle side: one latch and one
    counter. The `mission_result` key it fills keeps the word because the tool
    it comes from is `submit_mission_result` and renaming half of that pair
    would leave a key nothing on the wire is called.
    """

    def __init__(self) -> None:
        self.result: dict | None = None
        self.attempts = 0

    @property
    def submitted(self) -> bool:
        return self.result is not None

    def submit(self, arguments: Mapping[str, object]) -> dict:
        self.attempts += 1
        if self.result is not None:
            return {
                "accepted": False,
                "reason": "already_submitted",
                "attempts": self.attempts,
            }
        self.result = dict(arguments)
        return {
            "accepted": True,
            "attempts": self.attempts,
            # Not "staged". Nothing is staged yet: the row is written by the
            # runtime after this process ends and after its provenance is
            # checked, and telling the model otherwise would be this handler
            # promising something it is not the one to do.
            "note": "received; staging and provenance are the runtime's step",
        }


#: What each served tool tells the model it is for. One sentence each, and each
#: one says the bound out loud: a description that promised the whole Program
#: would be a description of a tool this runtime does not have.
DESCRIPTIONS = {
    "get_attack_surface": (
        "List this Program's known Entities -- hosts, endpoints, parameters and the "
        "rest -- from the bounded packet this run was started with. Returns record "
        "revisions, digests, counts and omission markers."
    ),
    "get_hypotheses": (
        "List this Program's Hypotheses, optionally for one subject Entity or one "
        "status, from the bounded packet this run was started with."
    ),
    "get_evidence": (
        "List the evidence edges tying Observations to one Hypothesis or one Finding, "
        "with each Observation's provenance label."
    ),
    "get_receipts": (
        "With no labels, list the Receipts this run's packet reached. With labels, "
        "fetch those. A label that is not in this run's packet comes back as an "
        "omission marker rather than as an error."
    ),
    "get_artifact": (
        "With no label, list the Artifacts this run's packet reached. With one, fetch "
        "that Artifact -- its metadata and, where its head was staged as text, a byte "
        "range of it. The hash is reported, never asked for. Whole large Artifacts "
        "are analysed by a tool run, not read into this context."
    ),
    "submit_mission_result": (
        "Submit this run's one result: proposed Entities, Relationships, "
        "Hypotheses, Observations with the Receipt or Tool Run each cites, evidence "
        "edges, suggested Tasks and a completion claim. It is staging data. The "
        "runtime checks provenance and decides what becomes canonical; nothing here "
        "is true because it was submitted."
    ),
}


def server(surface: Surface, reader: packet.Reader, submission: Submission):
    """The runtime's MCP server: five bounded reads and one proposal.

    Every handler goes through `surface.serve` first, which refuses while the
    surface is not open. That is ticket 16's property and it is load-bearing
    here for a new reason: a state read answered before init would be a read
    served by a child whose authentication this runtime had not corroborated.

    The schemas come from `roster.CONTRACTS` rather than from here. They are
    closed -- `additionalProperties: false` -- and the CLI validates against
    them before `PreToolUse` runs, so an argument the roster does not declare
    is refused before the gate and long before a handler. The gate checks the
    same properties again afterwards. Two checks of one statement, which is the
    arrangement, rather than two statements.
    """
    reads = {
        "get_attack_surface": reader.attack_surface,
        "get_hypotheses": reader.hypotheses,
        "get_evidence": reader.evidence,
        "get_receipts": reader.receipts,
        "get_artifact": reader.artifact,
    }
    tools = [_read(surface, name, answer) for name, answer in reads.items()]
    tools.append(_propose(surface, submission))
    return create_sdk_mcp_server(name=agent.SERVER, version=agent.SERVER_VERSION, tools=tools)


def _read(surface: Surface, name: str, answer):
    """One state read, wired to the reader method that answers it.

    `range` is the one wire name that is a Python builtin, so it is renamed on
    the way in. Renaming it in the contract instead would have made the roster
    describe a tool by a name the tool is not served under.
    """

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        given = dict(arguments or {})
        if "range" in given:
            given["span"] = given.pop("range")
        return _content(answer(**given))

    return handler


def _propose(surface: Surface, submission: Submission):
    name = "submit_mission_result"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        return _content(submission.submit(dict(arguments or {})))

    return handler


def _schema(name: str) -> dict:
    return roster.CONTRACTS[f"mcp__{agent.SERVER}__{name}"].schema()


def _content(answer: Mapping[str, object]) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(answer, separators=(",", ":"))}]}


def gate_hooks(gate: roster.Gate) -> dict:
    """The roster's decision, wired to the four events that make it one.

    `PreToolUse` is the decision and the other three are what let it be taken
    honestly. `SubagentStart` records what a delegated agent was started as, so
    a later call carrying that identity is checked against a record rather than
    believed; the two completions give an admitted delegation back, so the
    concurrency ceiling is a ceiling on what is running rather than on what has
    ever run.

    None of the matchers narrows by tool name. A matcher is a filter on which
    calls reach the gate, and a gate that some calls do not reach is not one.
    """

    async def before(payload, tool_use_id, context) -> dict:
        call = roster.Call(
            tool=str(payload.get("tool_name") or ""),
            arguments=payload.get("tool_input") or {},
            agent_id=payload.get("agent_id"),
            agent_type=payload.get("agent_type"),
            ticket=payload.get("tool_use_id") or tool_use_id,
        )
        denial = gate.decide(call)
        if denial is None:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": str(denial),
            }
        }

    async def started(payload, tool_use_id, context) -> dict:
        gate.bind(str(payload.get("agent_id") or ""), str(payload.get("agent_type") or ""))
        return {}

    async def finished(payload, tool_use_id, context) -> dict:
        ticket = payload.get("tool_use_id") or tool_use_id
        if ticket is not None:
            gate.release(str(ticket))
        return {}

    callbacks = {
        "PreToolUse": before,
        "SubagentStart": started,
        "PostToolUse": finished,
        "PostToolUseFailure": finished,
    }
    return {
        event: [HookMatcher(matcher=None, hooks=[callbacks[event]])]
        for event in agent.GATE_EVENTS
    }


def options_for(
    job: Mapping[str, object],
    runtime: Mapping[str, object],
    mcp_server,
    launch: Path,
    gate: roster.Gate,
) -> object:
    """The one options value this launch is assessed with and started from.

    Built here and handed on unchanged. `cli_path` is whatever the installed
    SDK resolved to and nothing when it resolved to nothing -- the assertion
    refuses that case rather than this function substituting a name the SDK
    would look for on `PATH`. `settings` is the one document in `launch` for
    the same reason: naming the directory and naming the file in it separately
    would be two answers to which document loaded.

    Everything that varies between one role and another is read off `gate.role`
    rather than off the job. A job that could name a model or a turn ceiling
    would be a caller deciding what the roster is for, and the assertion
    checks these fields against the same row this reads them from, so a launch
    that disagreed with the roster would not start.
    """
    executable = agent.bundled_executable(runtime)
    role = gate.role
    return ClaudeAgentOptions(
        model=role.model,
        effort=role.effort,
        max_turns=role.max_turns,
        tools=role.visible_tools,
        mcp_servers={agent.SERVER: mcp_server},
        allowed_tools=role.allowed_tools(agent.SERVED),
        hooks=gate_hooks(gate),
        setting_sources=[],
        permission_mode=agent.PERMISSION_MODE,
        cwd=str(launch),
        env={},
        sandbox=None,
        settings=str(launch / agent.SETTINGS),
        cli_path=None if executable is None else str(executable),
    )


async def run(
    job: Mapping[str, object],
    *,
    environment: Mapping[str, str] | None = None,
    runtime: Mapping[str, object] | None = None,
    transport=None,
) -> dict:
    """Make the launch directory, assert against it, start, corroborate, serve.

    The directory and its settings document come first because they are part of
    what is asserted: the assertion's questions are "is the working directory
    the runtime's own" and "what will the CLI load from it", and neither can be
    asked about a directory that does not exist yet. So a refused launch leaves
    a directory behind and nothing else -- no transport, no session, no turn.
    Everything after the assertion is a gate on the step after it.

    `environment`, `runtime` and `transport` are parameters so that a refusal
    can be provoked without provoking the machine that would have to be broken
    to cause it -- an exported key, a downgraded SDK, a transport that answers
    wrongly. A child supplies none of them: it reads its own environment, its
    own runtime facts and the SDK's own transport, which is the whole reason
    the assertion is made here rather than in the supervisor. The settings
    locations are not one of those seams and are not passed on: `assess` reads
    `agent.MANAGED_SETTINGS` in the process doing the asserting, which is this
    one, and a caller naming them would be a caller choosing what it sees.
    """
    environment = dict(os.environ) if environment is None else dict(environment)
    runtime = runtime_facts() if runtime is None else dict(runtime)
    launch = agent.launch_directory(str(job["workspace"]), str(job["agent_run_id"]))
    agent.write_settings(launch)
    surface = Surface()
    reader = packet.Reader(packet.Packet.from_dict(dict(job.get("packet") or {})))
    submission = Submission()
    role = str(job.get("role") or "")
    # Nothing, when there is no SDK to build it from, and nothing when there is
    # no role to build it for. An options value is a description of what one
    # SDK version would do for one role, so an absent SDK and an unknown role
    # both leave it without a description rather than with a broken one --
    # and `assess` already refuses each of them by name.
    gate = _gate(role)
    options = (
        None
        if claude_agent_sdk is None or gate is None
        else options_for(job, runtime, server(surface, reader, submission), launch, gate)
    )

    violations = agent.assess(options, environment, runtime, launch_dir=launch, role=role)
    if violations:
        raise agent.StartupRefusal(
            violations, "pre_spawn", runtime.get("sdk_version"), runtime.get("cli_version")
        )
    assert gate is not None

    messages = (transport or query)(prompt=str(job["objective"]), options=options)
    api_key_source = await _corroborate(messages, surface, runtime)

    text = ""
    answers = 0
    stop_reason = None
    async for message in messages:
        if isinstance(message, SystemMessage) and getattr(message, "subtype", None) == INIT:
            # A second announcement is a second startup, and the assertion was
            # made against the first. Counted rather than ignored: counting is
            # what closes the surface -- a child that announced itself twice
            # stops being served, and the count crosses back as the evidence.
            surface.open()
        if isinstance(message, AssistantMessage):
            answers += 1
        if isinstance(message, ResultMessage):
            text = str(getattr(message, "result", "") or "")[:ANSWER]
            stop_reason = getattr(message, "stop_reason", None)
    return {
        "role": gate.role.name,
        "sdk_version": runtime.get("sdk_version"),
        "cli_version": runtime.get("cli_version"),
        "api_key_source": api_key_source,
        "tool_ready": surface.opened,
        "tools_served": list(surface.served),
        "denials": [denial.as_dict() for denial in gate.denials],
        "answers": answers,
        "stop_reason": stop_reason,
        "text": text,
        "mission_result": submission.result,
        "mission_attempts": submission.attempts,
    }


def _gate(role: str) -> roster.Gate | None:
    """The gate for this role, or nothing when the roster has no such role.

    Nothing rather than an exception, because an unknown role is a refusal the
    assertion makes with every other finding beside it, and a traceback here
    would be one finding reported as a crash.
    """
    try:
        return roster.Gate(role)
    except roster.RosterError:
        return None


async def _corroborate(messages, surface: Surface, runtime: Mapping[str, object]) -> str:
    """Read up to the init message and open the tool surface, or refuse.

    Returns the credential source the CLI reported rather than the one this
    runtime required. They are equal by the time it returns -- that is the
    whole check -- but a run that reports what it read is carrying evidence,
    and one that reports its own expectation is carrying an assumption.

    The transport is closed on refusal rather than left to be collected. A
    child whose authentication this runtime could not corroborate is one that
    must not still be running while the refusal is written.
    """
    while True:
        message = await anext(messages, None)
        if message is None:
            await _refuse(messages, agent.uncorroborated(ABSENT), runtime)
        if isinstance(message, SystemMessage) and getattr(message, "subtype", None) == INIT:
            source = (getattr(message, "data", None) or {}).get("apiKeySource")
            violations = agent.corroboration(source)
            if violations:
                await _refuse(messages, violations, runtime)
            surface.open()
            return str(source)
        if type(message).__name__ not in BEFORE_INIT:
            await _refuse(messages, agent.uncorroborated(PREMATURE), runtime)


async def _refuse(messages, violations, runtime: Mapping[str, object]) -> NoReturn:
    """Close the run down, then raise the refusal that closed it."""
    await _close(messages)
    raise agent.StartupRefusal(
        violations, "init", runtime.get("sdk_version"), runtime.get("cli_version")
    )


async def _close(messages) -> None:
    close = getattr(messages, "aclose", None)
    if close is not None:
        await close()


def main(stream=None) -> int:
    """The child entry point: one job in, one result or one refusal out."""
    job = json.loads((stream or sys.stdin).read())
    runtime = runtime_facts()
    try:
        result = asyncio.run(run(job, runtime=runtime))
    except agent.StartupRefusal as refusal:
        print(json.dumps({REFUSAL: refusal.as_dict()}), file=sys.stderr, flush=True)
        return agent.REFUSED
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
