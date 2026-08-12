#!/usr/bin/env python3
"""Observe the tool inventory of one SDK/CLI pair and write it down.

The roster is a closed list, and a closed list is only closed against
something. This is that something: the built-in tools the CLI actually serves,
the agent types it will start on its own, what each model alias a role may name
resolves to, and the two vocabularies the SDK accepts for effort and permission
mode. Every one is read off the running pair rather than off documentation,
because what the roster has to be checked against is what a child would
actually be offered.

It runs offline and bills nothing. The model API is `tests.fixtures`'
`ControlUpstream` on loopback -- a real socket the real CLI reaches through
proxy variables and a root it was told to trust -- and the observation is
finished at the init message, before a completion is ever asked for. The
credential in the home it reads is a literal that authenticates nothing.

Run it on a version bump, and write a new file rather than replacing the
previous pair's:

    PYTHONPATH=<sdk> python3 tools/probe_tool_inventory.py \\
      > src/redkraken/measurements/tool-inventory-sdk-NEW-cli-NEW.json

Then update `roster.INVENTORY` and `roster.INVENTORY_SHA256` to name it. The
digest is what makes the file evidence rather than a list somebody edited.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import typing
from pathlib import Path


CHECKOUT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CHECKOUT / "src"), str(CHECKOUT)]

#: The preset that asks the CLI for every built-in tool it has. The inventory
#: has to be the full one: a roster checked against a narrowed list would be a
#: roster that cannot notice the tool it forgot to classify.
PRESET = {"type": "preset", "preset": "claude_code"}

#: How many times the pair is asked. More than one, because a list that is not
#: the same twice is not an inventory, and the probe refuses rather than
#: writing down whichever answer came last.
REPETITIONS = 2

#: The settings document the probe's own child loads, and the fields whose
#: vocabularies are read off the SDK's type declarations rather than a session.
SETTINGS = {"env": {}}
VOCABULARIES = (("effort_levels", "EffortLevel"), ("permission_modes", "PermissionMode"))

#: The model aliases whose resolution is measured. A role names an alias, but
#: what it runs is whatever the pair resolves that alias to, and the two are not
#: the same claim: an alias the pair does not know resolves to something else
#: without saying so. Read off the init frame for the same reason as the tools.
MODEL_ALIASES = ("opus", "sonnet", "haiku")


def observation(root: Path, model: str | None = None) -> dict:
    """One init message from one real child, as the facts it announced."""
    from redkraken import tls
    from tests import fixtures

    authority = tls.authority(root / "authority")
    home = fixtures.subscription(root / "home")
    launch = root / "launch"
    launch.mkdir(exist_ok=True)
    (launch / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")

    upstream = fixtures.ControlUpstream("unused", authority=authority)
    os.environ.update(
        {
            "HOME": str(home),
            "HTTP_PROXY": upstream.url,
            "HTTPS_PROXY": upstream.url,
            "http_proxy": upstream.url,
            "https_proxy": upstream.url,
            "NO_PROXY": "",
            "no_proxy": "",
            "NODE_EXTRA_CA_CERTS": str(authority.certificate),
            "SSL_CERT_FILE": str(authority.certificate),
        }
    )
    try:
        return asyncio.run(_announced(launch, model))
    finally:
        upstream.stop()


async def _announced(launch: Path, model: str | None) -> dict:
    """Start the pair, read its announcement, and stop before it does work."""
    import claude_agent_sdk
    from claude_agent_sdk import ClaudeAgentOptions, SystemMessage, query

    bundled = Path(claude_agent_sdk.__file__).resolve().parent / "_bundled" / "claude"
    options = ClaudeAgentOptions(
        max_turns=1,
        tools=PRESET,
        setting_sources=[],
        permission_mode="bypassPermissions",
        cwd=str(launch),
        env={},
        sandbox=None,
        settings=str(launch / "settings.json"),
        cli_path=str(bundled),
        model=model,
    )
    messages = query(prompt="Say nothing.", options=options)
    try:
        async for message in messages:
            if isinstance(message, SystemMessage) and message.subtype == "init":
                return dict(message.data)
    finally:
        await messages.aclose()
    raise SystemExit("the pair produced no init message")


def vocabularies() -> dict[str, list[str]]:
    """The two closed argument vocabularies, read off the SDK's own aliases."""
    from claude_agent_sdk import types

    return {
        name: sorted(typing.get_args(getattr(types, alias)))
        for name, alias in VOCABULARIES
    }


def agreed(announcements: list[dict], fields: tuple[str, ...]) -> dict:
    """The answer the pair gave every time, or nothing because it varied."""
    first, *rest = (
        {field: announcement[field] for field in fields} for announcement in announcements
    )
    for other in rest:
        if other != first:
            raise SystemExit(f"the pair announced two inventories: {first} then {other}")
    return first


def manifest(announcements: list[dict], models: dict[str, str]) -> dict:
    """One inventory, or nothing, when the pair did not answer the same twice."""
    from claude_agent_sdk import _cli_version

    first = agreed(announcements, ("tools", "agents", "model"))
    return {
        "schema_version": 1,
        "runtime": {
            "sdk_version": importlib.metadata.version("claude-agent-sdk"),
            "bundled_cli_version": _cli_version.__cli_version__,
        },
        "observation": {
            "probe": "tools/probe_tool_inventory.py",
            "tools_preset": PRESET["preset"],
            "repetitions": len(announcements),
            "default_model": first["model"],
        },
        "builtin_tools": sorted(first["tools"]),
        "agent_types": sorted(first["agents"]),
        "models": models,
        **vocabularies(),
    }


def resolutions(root: Path, repetitions: int) -> dict[str, str]:
    """What each measured alias is, once the pair has been asked for it."""
    resolved = {}
    for alias in MODEL_ALIASES:
        announcements = [observation(root, alias) for _ in range(repetitions)]
        resolved[alias] = agreed(announcements, ("model",))["model"]
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=REPETITIONS,
        help="how many times the pair is asked before its answer is written down",
    )
    arguments = parser.parse_args(argv)
    if arguments.repetitions < 2:
        parser.error("an inventory is only an inventory if it was observed twice")

    root = Path(tempfile.mkdtemp(prefix="rk2-inventory-"))
    try:
        announcements = [observation(root) for _ in range(arguments.repetitions)]
        models = resolutions(root, arguments.repetitions)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(json.dumps(manifest(announcements, models), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
