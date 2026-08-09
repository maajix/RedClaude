#!/usr/bin/env python3
"""Live probes for the three unverified claims in map ticket 09 (Q16).

  A  Unknown `bb:` frontmatter keys survive the CLI parse and the skill still
     loads. Read off minified CLI 2.1.42; the SDK ships 2.1.224, and the whole
     `bb:` namespace decision dies if that changed.
  B  `AgentDefinition.skills` genuinely restricts the listing a subagent sees.
     Q2 and Q3 both rest on it.
  C  A PreToolUse hook on `Skill` fires and can read the skill name. Q13's
     evidence-profile binding and Q9's use-time content hash both depend on it.

A and B are answered from the initialize handshake, which is local stdio and
needs no network. C needs a real model turn.

Run:  probe_sdk.py [a|b|c|all]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
)

HERE = Path(__file__).resolve().parent
FIXTURE_SKILLS = HERE / "skills"

# Set by the hook so the assertion can read what it saw.
HOOK_SAW: list[dict[str, Any]] = []


def build_project() -> Path:
    """A throwaway project whose only skills are our two fixtures.

    setting_sources is pinned to ["project"] so the operator's own
    ~/.claude/skills cannot leak in and make a filtering result meaningless.
    """
    root = Path(tempfile.mkdtemp(prefix="skillfmt-"))
    target = root / ".claude" / "skills"
    target.parent.mkdir(parents=True)
    shutil.copytree(FIXTURE_SKILLS, target)
    return root


def skill_names(info: dict[str, Any] | None) -> list[str]:
    """Pull whatever the initialize response calls its skill listing."""
    if not info:
        return []
    for key in ("skills", "available_skills", "availableSkills"):
        value = info.get(key)
        if isinstance(value, list):
            return [v if isinstance(v, str) else v.get("name", str(v)) for v in value]
        if isinstance(value, dict):
            return sorted(value)
    # Skills also surface as Skill(name) entries in the command/tool listing.
    found: list[str] = []
    for key in ("commands", "slash_commands", "tools", "output_style"):
        value = info.get(key)
        if isinstance(value, list):
            for item in value:
                text = item if isinstance(item, str) else json.dumps(item)
                if "Skill" in text or "probe-" in text:
                    found.append(text)
    return found


async def probe_a(project: Path) -> bool:
    """A: does a skill carrying `bb:` keys still load on CLI 2.1.224?"""
    options = ClaudeAgentOptions(
        cwd=str(project),
        setting_sources=["project"],
        skills="all",
    )
    async with ClaudeSDKClient(options=options) as client:
        info = await client.get_server_info()
    Path(HERE / "artifacts").mkdir(exist_ok=True)
    (HERE / "artifacts" / "init-all.json").write_text(json.dumps(info, indent=2, default=str))
    listed = skill_names(info)
    print(f"A: initialize keys      = {sorted(info or {})}")
    print(f"A: skills visible       = {listed}")
    alpha_ok = any("probe-alpha" in entry for entry in listed)
    print(f"A: probe-alpha (bb: keys) loaded = {alpha_ok}")
    return alpha_ok


async def probe_b(project: Path) -> bool:
    """B: does restricting the list actually hide the other skill?"""
    options = ClaudeAgentOptions(
        cwd=str(project),
        setting_sources=["project"],
        skills=["probe-alpha"],
        agents={
            "restricted-hunter": AgentDefinition(
                description="Fixture subagent restricted to probe-alpha.",
                prompt="You are a fixture. Do nothing.",
                tools=["Read"],
                skills=["probe-alpha"],
            )
        },
    )
    async with ClaudeSDKClient(options=options) as client:
        info = await client.get_server_info()
    (HERE / "artifacts" / "init-restricted.json").write_text(
        json.dumps(info, indent=2, default=str)
    )
    listed = skill_names(info)
    print(f"B: skills visible       = {listed}")
    alpha = any("probe-alpha" in entry for entry in listed)
    beta = any("probe-beta" in entry for entry in listed)
    print(f"B: probe-alpha visible  = {alpha}")
    print(f"B: probe-beta withheld  = {not beta}")
    return alpha and not beta


async def collect_text(client: ClaudeSDKClient) -> str:
    """Concatenate the assistant text blocks of one response."""
    chunks: list[str] = []
    async for message in client.receive_response():
        for block in getattr(message, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


async def probe_b2(project: Path) -> bool:
    """B2: discriminates a broken filter from a mismeasured surface.

    B read the initialize `commands` array, which is the CLI's own discovery
    listing. The SDK's claim is narrower: unlisted skills are hidden from *the
    model's* listing and rejected by the Skill tool. Only the model can answer
    that, so this costs a real turn.
    """
    options = ClaudeAgentOptions(
        cwd=str(project),
        setting_sources=["project"],
        skills=["probe-alpha"],
        max_turns=3,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "List the exact names of every skill you can invoke, one per line. "
            "No other text."
        )
        listing = await collect_text(client)
        await client.query(
            "Now invoke the skill named probe-beta. If you cannot, say exactly "
            "why in one line."
        )
        attempt = await collect_text(client)

    (HERE / "artifacts").mkdir(exist_ok=True)
    (HERE / "artifacts" / "b2-model-listing.txt").write_text(
        f"--- listing ---\n{listing}\n\n--- probe-beta attempt ---\n{attempt}\n"
    )
    print(f"B2: model listing       = {listing.strip()!r}")
    print(f"B2: probe-beta attempt  = {attempt.strip()[:300]!r}")
    hidden = "probe-beta" not in listing
    alpha_listed = "probe-alpha" in listing
    print(f"B2: probe-alpha listed  = {alpha_listed}")
    print(f"B2: probe-beta hidden   = {hidden}")
    return alpha_listed and hidden


async def record_skill_use(
    input_data: dict[str, Any], tool_use_id: str | None, context: Any
) -> dict[str, Any]:
    """Stand-in for the runtime hook of Q13.

    In the real system this writes the skill name plus the SKILL.md content
    hash onto the current task row, which is what binds the evidence profile
    (Q13) and what makes a finding reproducible across a skill edit (Q9).
    """
    tool_input = input_data.get("tool_input") or {}
    name = tool_input.get("skill") or tool_input.get("name") or tool_input.get("command")
    digest = None
    if name:
        path = Path(input_data.get("cwd", ".")) / ".claude" / "skills" / str(name) / "SKILL.md"
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
    HOOK_SAW.append(
        {"tool_name": input_data.get("tool_name"), "skill": name, "sha256": digest}
    )
    return {}


async def probe_c(project: Path) -> bool:
    """C: does a PreToolUse hook on Skill fire, and can it read the name?"""
    options = ClaudeAgentOptions(
        cwd=str(project),
        setting_sources=["project"],
        skills=["probe-alpha"],
        allowed_tools=["Read"],
        max_turns=4,
        hooks={"PreToolUse": [HookMatcher(matcher="Skill", hooks=[record_skill_use])]},
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            "Invoke the probe-alpha skill using the Skill tool, then reply DONE. "
            "Do not do anything else."
        )
        async for _ in client.receive_response():
            pass
    print(f"C: hook invocations     = {json.dumps(HOOK_SAW)}")
    ok = any(entry.get("skill") for entry in HOOK_SAW)
    print(f"C: hook saw skill name  = {ok}")
    print(f"C: hash captured        = {any(e.get('sha256') for e in HOOK_SAW)}")
    return ok


async def main() -> int:
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    project = build_project()
    print(f"project = {project}\n")
    results: dict[str, bool] = {}
    if which in ("a", "all"):
        results["A bb: keys tolerated"] = await probe_a(project)
    if which in ("b", "all"):
        results["B skills filter (init listing)"] = await probe_b(project)
    if which in ("b2", "all"):
        results["B2 skills filter (model listing)"] = await probe_b2(project)
    if which in ("c", "all"):
        results["C Skill hook fires"] = await probe_c(project)
    print()
    for label, ok in results.items():
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
