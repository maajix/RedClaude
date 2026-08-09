#!/usr/bin/env python3
"""Static validator for the v2 skill format (map ticket 09).

Proves the CI half of Q8: a skill is checked for being *well-formed and wired*,
never for being good. Behaviour is the eval harness's job (ticket 16).

Rules, each tagged with the decision it enforces:

  R1  Q12  directory name is the identity and must be a slug
  R2  Q6   SKILL.md exists and its frontmatter parses
  R3  Q12  `description` is the only required key
  R4  Q12  `name`, `model`, `agent`, `context` are forbidden
  R5  Q7   no unknown top-level keys outside the `bb:` namespace
  R6  Q3   `allowed-tools` narrows, never widens, the roles that may load it
  R7  Q2   a skill no role can load is dead weight
  R8  Q4   `bb:evidence_profile` must name a registered predicate
  R9  Q14  `bb:scripts` entries must exist on disk with a valid JSON Schema
  R10 Q1   `references/` links must resolve
  R11 Q17  `description` is a context pointer: single line, bounded  [warning]
  R12 Q9   playbooks must not reference a skill name that does not exist

Usage:
    validate_skills.py <skills-dir> [--roles roles.yaml]
                                    [--profiles evidence_profiles.yaml]
                                    [--playbooks <dir>]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

# Keys the Claude Code CLI parses out of SKILL.md frontmatter. Read off the
# 2.1.42 bundle; probe_parse.py re-checks tolerance against the CLI the SDK
# actually ships (2.1.224).
CLI_KEYS = {
    "description",
    "allowed-tools",
    "user-invocable",
    "disable-model-invocation",
    "model",
    "context",
    "agent",
    "arguments",
    "argument-hint",
    "name",
}

# Q12: forbidden because each hands a skill file authority that belongs to a
# role (model), the roster (agent), the scheduler (context: fork), or creates a
# second identity that can drift from the directory name (name).
FORBIDDEN_KEYS = {"name", "model", "agent", "context"}

REQUIRED_KEYS = {"description"}

ALLOWED_KEYS = CLI_KEYS - FORBIDDEN_KEYS

# Soft cap only. The CLI's own bound on `description` is not verified against
# 2.1.224, so this is a review prompt, never a hard gate.
MAX_DESCRIPTION = 1024

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, skill: str, rule: str, message: str) -> None:
        self.errors.append(f"{skill}: [{rule}] {message}")

    def warn(self, skill: str, rule: str, message: str) -> None:
        self.warnings.append(f"{skill}: [{rule}] {message}")


def split_frontmatter(text: str) -> tuple[dict, str] | None:
    """Return (frontmatter, body), or None when there is no frontmatter block."""
    match = FRONTMATTER.match(text)
    if match is None:
        return None
    loaded = yaml.safe_load(match.group(1))
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError(f"frontmatter is {type(loaded).__name__}, not a mapping")
    return loaded, text[match.end() :]


def load_yaml_mapping(path: Path | None) -> dict:
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}


def tools_permitted_for(skill: str, roles: dict) -> tuple[set[str], list[str]]:
    """Union of tools across every role whose skill list includes `skill`."""
    tools: set[str] = set()
    holders: list[str] = []
    for role_name, role in roles.items():
        if skill in (role.get("skills") or []):
            holders.append(role_name)
            tools |= set(role.get("tools") or [])
    return tools, holders


def validate_skill(directory: Path, roles: dict, profiles: set[str], report: Report) -> None:
    name = directory.name

    # R1
    if not SLUG.match(name):
        report.error(name, "R1", "directory name is not a lowercase slug")

    skill_md = directory / "SKILL.md"
    if not skill_md.is_file():
        report.error(name, "R2", "no SKILL.md")
        return

    # R2
    try:
        split = split_frontmatter(skill_md.read_text())
    except (yaml.YAMLError, ValueError) as exc:
        report.error(name, "R2", f"frontmatter does not parse: {exc}")
        return
    if split is None:
        report.error(name, "R2", "no frontmatter block")
        return
    front, body = split

    # R3
    for key in sorted(REQUIRED_KEYS - front.keys()):
        report.error(name, "R3", f"missing required key `{key}`")
    if not str(front.get("description") or "").strip():
        report.error(name, "R3", "`description` is empty")

    # R4
    for key in sorted(FORBIDDEN_KEYS & front.keys()):
        detail = ""
        if key == "name" and front[key] != name:
            detail = f" (declares `{front[key]}`, but identity is the directory `{name}`)"
        report.error(name, "R4", f"forbidden key `{key}`{detail}")

    # R5
    for key in sorted(front.keys()):
        if key.startswith("bb:") or key in ALLOWED_KEYS or key in FORBIDDEN_KEYS:
            continue
        report.error(name, "R5", f"unknown key `{key}` outside the `bb:` namespace")

    # R6 / R7
    permitted, holders = tools_permitted_for(name, roles)
    if roles and not holders:
        report.error(name, "R7", "no role lists this skill, so nothing can ever load it")
    declared = front.get("allowed-tools") or []
    if isinstance(declared, str):
        declared = [t.strip() for t in declared.split(",") if t.strip()]
    if holders:
        widened = sorted(set(declared) - permitted)
        if widened:
            report.error(
                name,
                "R6",
                f"`allowed-tools` widens beyond roles {holders}: {widened}. "
                "A skill narrows a role's tools; it never grants any.",
            )

    # R8
    profile = front.get("bb:evidence_profile")
    if profile is not None and profile not in profiles:
        report.error(name, "R8", f"unregistered evidence profile `{profile}`")

    # R9
    scripts = front.get("bb:scripts") or []
    if scripts and not isinstance(scripts, list):
        report.error(name, "R9", "`bb:scripts` must be a list")
        scripts = []
    for index, entry in enumerate(scripts):
        label = f"bb:scripts[{index}]"
        if not isinstance(entry, dict):
            report.error(name, "R9", f"{label} is not a mapping")
            continue
        script_name = entry.get("name")
        if not script_name:
            report.error(name, "R9", f"{label} has no `name`")
            continue
        label = f"bb:scripts[{script_name}]"
        if not str(entry.get("description") or "").strip():
            report.error(name, "R9", f"{label} has no `description`")
        if not (directory / "scripts" / script_name).is_file():
            report.error(name, "R9", f"{label} has no file at scripts/{script_name}")
        args = entry.get("args")
        if args is None:
            report.error(name, "R9", f"{label} declares no `args` schema")
            continue
        try:
            Draft202012Validator.check_schema(args)
        except SchemaError as exc:
            report.error(name, "R9", f"{label} `args` is not a valid JSON Schema: {exc.message}")

    # R10
    for target in MD_LINK.findall(body):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (directory / target.split("#", 1)[0]).exists():
            report.error(name, "R10", f"dangling link `{target}`")

    # R11. Q17: the description is a context pointer, and whether it front-loads
    # a leading word and names distinct branches is a review gate, not a lint.
    # CI checks only the mechanically checkable half.
    description = str(front.get("description", ""))
    if "\n" in description.strip():
        report.warn(name, "R11", "`description` spans multiple lines")
    if len(description) > MAX_DESCRIPTION:
        report.warn(
            name,
            "R11",
            f"`description` is {len(description)} chars (soft cap {MAX_DESCRIPTION}); "
            "a pointer pays its cost on every turn",
        )


def validate_playbooks(playbooks: Path, known: set[str], report: Report) -> None:
    """R12: a playbook may reference a skill by name; the name must exist."""
    for path in sorted(playbooks.rglob("*.md")):
        try:
            split = split_frontmatter(path.read_text())
        except (yaml.YAMLError, ValueError):
            continue
        if split is None:
            continue
        front, _ = split
        referenced = front.get("bb:skills") or front.get("skills") or []
        if isinstance(referenced, str):
            referenced = [referenced]
        for skill in referenced:
            if skill not in known:
                report.error(
                    str(path.relative_to(playbooks)),
                    "R12",
                    f"references unknown skill `{skill}`",
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skills", type=Path)
    parser.add_argument("--roles", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--playbooks", type=Path)
    args = parser.parse_args()

    roles = load_yaml_mapping(args.roles).get("roles", {})
    profiles = set(load_yaml_mapping(args.profiles).get("profiles", {}))

    directories = sorted(p for p in args.skills.iterdir() if p.is_dir())
    report = Report()
    for directory in directories:
        validate_skill(directory, roles, profiles, report)

    if args.playbooks:
        validate_playbooks(args.playbooks, {p.name for p in directories}, report)

    for line in report.warnings:
        print(f"warn  {line}")
    for line in report.errors:
        print(f"ERROR {line}")

    print(
        f"\n{len(directories)} skill(s) checked: "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
