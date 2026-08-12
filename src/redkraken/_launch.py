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

from redkraken import agent


try:
    import claude_agent_sdk
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
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
#: result document travels through a pipe and this is proof the run
#: finished, not a transcript. Ticket 17 owns what is kept durably.
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


def server(surface: Surface):
    """The runtime's MCP server, whose tools refuse until the surface opens.

    One tool, and it answers with nothing but the state of the surface it is
    served from: the point at ticket 16 is that a tool surface exists, opens
    once and opens after init. Ticket 19 replaces it with bounded state reads
    and proposals.
    """

    @tool(agent.READY, "Report that the runtime's tool surface is open.", {})
    async def ready(arguments: dict) -> dict:
        surface.serve(agent.READY)
        return {"content": [{"type": "text", "text": json.dumps({"tool_surface": "open"})}]}

    return create_sdk_mcp_server(name=agent.SERVER, version=agent.SERVER_VERSION, tools=[ready])


def options_for(
    job: Mapping[str, object], runtime: Mapping[str, object], mcp_server, launch: Path
) -> object:
    """The one options value this launch is assessed with and started from.

    Built here and handed on unchanged. `cli_path` is whatever the installed
    SDK resolved to and nothing when it resolved to nothing -- the assertion
    refuses that case rather than this function substituting a name the SDK
    would look for on `PATH`. `settings` is the one document in `launch` for
    the same reason: naming the directory and naming the file in it separately
    would be two answers to which document loaded.
    """
    executable = agent.bundled_executable(runtime)
    return ClaudeAgentOptions(
        model=job.get("model") or None,
        max_turns=int(job.get("max_turns") or agent.MAX_TURNS),
        tools=[],
        mcp_servers={agent.SERVER: mcp_server},
        allowed_tools=[agent.TOOL],
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
    the assertion is made here rather than in the supervisor.
    """
    environment = dict(os.environ) if environment is None else dict(environment)
    runtime = runtime_facts() if runtime is None else dict(runtime)
    launch = agent.launch_directory(str(job["workspace"]), str(job["agent_run_id"]))
    agent.write_settings(launch)
    surface = Surface()
    # Nothing, when there is no SDK to build it from. An options value is a
    # description of what one SDK version would do, so an absent SDK has no
    # description rather than a broken one -- and `assess` refuses the absence
    # as an unmeasured runtime, which is where that refusal already lives.
    options = (
        None if claude_agent_sdk is None else options_for(job, runtime, server(surface), launch)
    )

    violations = agent.assess(options, environment, runtime, launch_dir=launch)
    if violations:
        raise agent.StartupRefusal(
            violations, "pre_spawn", runtime.get("sdk_version"), runtime.get("cli_version")
        )

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
        "sdk_version": runtime.get("sdk_version"),
        "cli_version": runtime.get("cli_version"),
        "api_key_source": api_key_source,
        "tool_ready": surface.opened,
        "tools_served": list(surface.served),
        "answers": answers,
        "stop_reason": stop_reason,
        "text": text,
    }


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
