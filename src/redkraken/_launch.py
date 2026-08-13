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
import http.client
import importlib.metadata
import json
import os
import ssl
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

from redkraken import agent, packet, proxy, roster, scope, tls


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

#: Why a request tool call reached no target. Tokens rather than prose, for the
#: same reason the door's decision header is a token: the model reads one of
#: these and the runtime reads the same one out of the transcript, and a reason
#: reworded later would silently change what either concluded.
NO_CAPABILITY = "no_capability"
UNUSABLE_TARGET = "unusable_target"
DOOR_UNREACHABLE = "door_unreachable"


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
    "http_request": (
        "Send one HTTP request to a target through the capability proxy, which "
        "decides it against this Program's scope and writes the Receipt and the "
        "response Artifact. Answers the status, the Receipt label to cite and a "
        "bounded excerpt of the body; a refusal names the door's decision rather "
        "than pretending the request happened."
    ),
    # The element lists stay open -- `roster.OPEN_ARGUMENTS` says why -- so this
    # sentence is the only place a child is told which fields promotion reads
    # out of them. A field name it has to guess is a drop row with
    # `malformed_field` on it and no way for the model to learn the spelling.
    "submit_mission_result": (
        "Submit this run's one result: proposed Entities, Relationships, "
        "Hypotheses, Observations with the Receipt or Tool Run each cites, evidence "
        "edges, suggested Tasks and a completion claim. It is staging data. The "
        "runtime checks provenance and decides what becomes canonical; nothing here "
        "is true because it was submitted.\n\n"
        "Every element cites its evidence with exactly one of receipt_label or "
        "tool_run_label. An entity carries type and the typed fields of that type: "
        "domain fqdn and wildcard; host hostname and address; service parent_ref "
        "with port and protocol; application base_url and kind; endpoint parent_ref "
        "with method and path_template; parameter parent_ref with name and "
        "location; technology name and version; identity slot_name. A service, an "
        "endpoint and a parameter name their containment parent by parent_ref or "
        "parent_label; give an entity a ref of your own and later elements can "
        "point at it by that name before it has a label. A relationship carries "
        "type with src_ref or src_label and dst_ref or dst_label, and containment "
        "is never one of them."
    ),
}


def server(
    surface: Surface,
    reader: packet.Reader,
    submission: Submission,
    door: agent.Egress | None = None,
):
    """The runtime's MCP server: five bounded reads, one request, one proposal.

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
    tools.append(_request(surface, door))
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


def _request(surface: Surface, door: agent.Egress | None):
    """The one call that leaves the boundary, spent through the door or refused.

    Blocking work on a thread, because the request is a socket and the caller is
    an event loop: a synchronous exchange run inline would stall every other
    thing the session has in flight for as long as the target takes to answer.

    Nothing here decides whether the request is allowed. The capability was
    minted against a Tool run by the runtime, the door re-decides the request
    that actually arrives against live policy, and this handler's whole job is
    to carry one to the other and report what came back -- including a refusal,
    which is reported as a refusal rather than as a failure to reach anything.
    """
    name = "http_request"

    @tool(name, DESCRIPTIONS[name], _schema(name))
    async def handler(arguments: dict) -> dict:
        surface.serve(name)
        given = dict(arguments or {})
        if door is None:
            return _content(
                {
                    "served": False,
                    "reason": NO_CAPABILITY,
                    "detail": "this run was started with no capability; no request was sent",
                }
            )
        return _content(
            await asyncio.to_thread(
                _spend, door, str(given.get("url") or ""), str(given.get("method") or "GET")
            )
        )

    return handler


def _spend(door: agent.Egress, url: str, method: str) -> dict:
    """One exchange through the door, as the four facts a model can act on.

    The Receipt label is the first of them and the reason the rest are bounded:
    an Observation the runtime will promote has to cite a Receipt, and the way
    to say more about the body than fits here is to analyse the Artifact the
    door already wrote rather than to read it into this context.
    """
    try:
        listener = proxy.peer(door.proxy_url)
        request = scope.canonical_request(url)
    except (proxy.Refused, scope.PolicyError) as refusal:
        return {"served": False, "reason": UNUSABLE_TARGET, "detail": refusal.detail}

    trust: ssl.SSLContext | None = None
    if request.protocol == "https":
        try:
            trust = tls.trust(Path(door.certificate))
        except (OSError, ssl.SSLError) as error:
            return {"served": False, "reason": UNUSABLE_TARGET, "detail": str(error)}

    try:
        answer = proxy.spend(
            listener,
            url,
            capability=door.capability,
            program_id=door.program_id,
            method=method,
            trust=trust,
        )
    except (OSError, http.client.HTTPException) as error:
        return {"served": False, "reason": DOOR_UNREACHABLE, "detail": str(error)}

    body = answer.body[: packet.DEFAULT_EXCERPT]
    return {
        "served": answer.decision is None,
        "status": answer.status,
        "receipt": answer.receipt,
        "decision": answer.decision,
        "detail": answer.detail,
        "byte_size": len(answer.body),
        "truncated": len(answer.body) > len(body),
        "body": body.decode("utf-8", "replace"),
    }


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
    # Nothing, when the job carried no usable capability block. A run started
    # without one still serves the request tool -- the allowlist is the role's,
    # not the job's -- and the tool answers that it has nothing to spend.
    door = agent.Egress.from_dict(job.get("egress"))
    # Nothing, when there is no SDK to build it from, and nothing when there is
    # no role to build it for. An options value is a description of what one
    # SDK version would do for one role, so an absent SDK and an unknown role
    # both leave it without a description rather than with a broken one --
    # and `assess` already refuses each of them by name.
    gate = _gate(role, job.get("subagent_cap"))
    options = (
        None
        if claude_agent_sdk is None or gate is None
        else options_for(job, runtime, server(surface, reader, submission, door), launch, gate)
    )

    violations = agent.assess(options, environment, runtime, launch_dir=launch, role=role)
    if violations:
        raise agent.StartupRefusal(
            violations, "pre_spawn", runtime.get("sdk_version"), runtime.get("cli_version")
        )
    assert gate is not None

    messages = (transport or query)(prompt=str(job["objective"]), options=options)
    api_key_source = await _corroborate(messages, surface, runtime)

    # What the claim reserved for this run, or nothing when it reserved nothing.
    # Read the same way the cap is: off the job, because this process has no
    # database to ask.
    ceiling = _token_cap(job.get("token_cap"))
    text = ""
    answers = 0
    stop_reason = None
    spent_in = 0
    spent_out = 0
    async for message in messages:
        if isinstance(message, SystemMessage) and getattr(message, "subtype", None) == INIT:
            # A second announcement is a second startup, and the assertion was
            # made against the first. Counted rather than ignored: counting is
            # what closes the surface -- a child that announced itself twice
            # stops being served, and the count crosses back as the evidence.
            surface.open()
        if isinstance(message, AssistantMessage):
            answers += 1
            turn_in, turn_out = _usage(getattr(message, "usage", None))
            spent_in += turn_in
            spent_out += turn_out
            # The ceiling stops the run. Not a warning and not a log line: the
            # tokens past it are ones the Program did not reserve, and a session
            # asked politely to stop is a session that decides whether to.
            if ceiling is not None and spent_in + spent_out > ceiling:
                stop_reason = "budget"
                break
        if isinstance(message, ResultMessage):
            text = str(getattr(message, "result", "") or "")[:ANSWER]
            stop_reason = getattr(message, "stop_reason", None)
            # The session's own totals, which is the number to report when there
            # is one: the per-turn sum is what this loop could see, and a turn
            # the SDK accounted for after the last message it sent is in the
            # result and not in the sum. A result reporting nothing leaves the
            # sum alone rather than overwriting a measurement with a zero.
            result_in, result_out = _usage(getattr(message, "usage", None))
            if result_in or result_out:
                spent_in, spent_out = result_in, result_out
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
        "input_tokens": spent_in,
        "output_tokens": spent_out,
    }


def _usage(stated: object) -> tuple[int, int]:
    """One message's tokens, as the two numbers the run row records.

    Everything the model was charged for reading counts as input, cache included:
    a cached read is cheaper, not free, and a ceiling that ignored the cache
    would be a ceiling a long session walks straight through. A turn's numbers
    are that turn's own request, prefix and all, which is what the Program is
    charged for making it -- so the session's cost is the sum of the turns, and
    the `ResultMessage` total replaces the sum when the SDK reports one.

    Nothing reported is zero: a message carrying no usage block still happened,
    and absent fields inside a block that is there are zero for the same reason.
    A block that is not a mapping raises, for the reason `_token_cap` raises:
    usage this process cannot read is a ceiling it cannot enforce, and a quiet
    zero here is a session running unbounded.
    """
    if stated is None:
        return (0, 0)
    if not isinstance(stated, Mapping):
        raise TypeError(f"usage is {type(stated).__name__}, not a mapping")
    usage = stated
    return (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        int(usage.get("output_tokens") or 0),
    )


def _token_cap(stated: object) -> int | None:
    """The most this run may spend, as the claim reserved it.

    Nothing stated is no ceiling: a Program with no total and no per-run number
    reserved nothing, and this process must not invent a bound the scheduler did
    not admit the Task under. A stated value that is not a number raises, which
    fails the run: unlike an unreadable subagent cap, this one cannot degrade to
    a refusal without also degrading to running unbounded.
    """
    return None if stated is None else int(stated)


def _subagent_cap(stated: object) -> int:
    """How many delegations this session may hold, as the claim read it.

    `scheduler_weights.max_concurrent_subagents` travels on the job because
    this process cannot ask: the container's one network reaches the capability
    proxy and no database. Nothing stated gets the roster's default, which is
    the schema's own -- that is a job written before the number travelled, not
    a value this process may prefer to the one the claim read. Anything else
    is converted and not sanitised: a cap this process cannot read is a job it
    cannot honour, and `_gate` turns that into a refusal rather than a guess.
    """
    return roster.DEFAULT_SUBAGENTS if stated is None else int(stated)


def _gate(role: str, subagent_cap: object) -> roster.Gate | None:
    """The gate for this role and cap, or nothing when neither can be had.

    Nothing rather than an exception, because an unknown role is a refusal the
    assertion makes with every other finding beside it, and a traceback here
    would be one finding reported as a crash. A cap the roster refuses -- below
    the one the schema's own CHECK admits, or not a number at all -- arrives at
    the same answer for the same reason: without a gate there is no options
    value, and a launch that cannot be described is one `assess` refuses field
    by field.
    """
    try:
        return roster.Gate(role, _subagent_cap(subagent_cap))
    except (roster.RosterError, TypeError, ValueError):
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
