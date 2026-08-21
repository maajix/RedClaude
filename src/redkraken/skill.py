"""The Skill corpus: instructions that steer, compiled against authority they cannot widen.

A Skill is text a model loads mid-run. That is the whole of what it is, and the
whole of the risk: loading it changes what the model knows and must not change
what the model may do. The SDK offers no containment here -- `AgentDefinition.skills`
is a selection list, the `Skill` tool takes a name, and the instructions that
come back are just tokens. So containment is built on this side, in three
places that are deliberately not one:

* **This module** decides whether the corpus is well-formed. It parses each
  `SKILL.md`, refuses metadata it cannot read, refuses a key that would give
  instructions authority over the frame they load into, hashes every file the
  skill owns, and publishes `SKILLS`. It knows nothing about roles or tools
  beyond their spelling, which is why `roster` can import it.
* **`roster._check_skills`** decides whether the corpus fits the authority the
  roles hold: that every role a skill names exists and can execute a skill at
  all, that every tool group it needs is a group that role already holds, and
  that an `allowed-tools` line only ever narrows. It fills `Role.skills` from
  the corpus, so which role may load which Skill is stated once -- in the
  corpus -- rather than twice with a hope that the two agree.
* **`roster.Gate`** decides, at the call, whether the name in a `Skill` call is
  one the running role holds. That is the only one of the three that runs while
  a model is running, and it is the one that cannot be argued with.

What a skill is *named* is part of the design and not a convention. A skill is a
technique -- enumerating a surface, pairing identities, comparing responses,
taking browser evidence, reading source, handling untrusted content -- and never
a vulnerability family or a workflow. (Not "capability": `CONTEXT.md` reserves
that word for what a run obtains against a target, and a Skill obtains nothing.)
A skill called `injection` is a bucket a
model fills with whatever it already believed; a skill called `compare-responses`
is a thing that either happened or did not, and its output is checkable. The
corpus is the enumeration, so the rule is enforced by there being no such
directory rather than by a check that would have to recognise a family name.

**Version is computed, never declared.** A skill's version is the digest of its
own dependency manifest: every file it owns, its kind, its path and its SHA-256,
in one order. A hand-written `version:` line is a second statement of identity
that drifts from the first the moment somebody edits a script and forgets, and
the thing a Task needs to record is not what the author believed the version was
but what actually ran. `docs/prototype/skill-format/SKILL-FORMAT.md` settled
this in the same words: content hash, no semver, no pinning.

**Determinism lives in scripts, and a script carries its own checks.** A script
takes stored Artifacts and nothing else -- that is the whole of what
`mcp__rk2__run_skill_script` can hand it -- and each one declares cases: the
Artifact text in, the exact JSON out. `check` runs a case twice under a bare
environment and refuses if the two runs disagree, because a script whose output
depends on the run is a script whose evidence is not reproducible.

**A reference is maintainer material, and nothing here can hand it to a model.**
`references/` is the SDK format's progressive-disclosure directory, opened by
the model with a file tool -- and `Read` is forbidden to every role, so in this
system there is no such tool and no such open. What a reference is here is what
a Playbook's reference already is: text a person reads, hashed into the version
manifest so that editing one is visible on every Task recorded afterwards. That
is what made v1's operator references keepable at all. They were loaded into
every Agent's context; here they belong to one technique and reach nobody at
run time. `bb:references` names them, because the manifest has to hash what it
versions, and the *body* never points at them: an instruction to open one would
be an instruction no role can carry out.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from redkraken import document
from redkraken.document import ENTRY, digest

#: The corpus, inside the package rather than beside it. The reason is the one
#: the migration corpus already has: `rk` runs what it was installed with, and a
#: directory at the repository root ships in a checkout and not in a wheel.
CORPUS = Path(__file__).resolve().parent / "skills"

INSTRUCTIONS = "SKILL.md"
SCRIPT_DIR = "scripts"
REFERENCE_DIR = "references"

#: Where one launch keeps the instructions its role was granted, relative to
#: the directory that launch runs in. This is the CLI's own project location:
#: `agent.setting_sources` opens `project` for a role that loads a Skill and
#: opens nothing for one that does not, and this directory is what it is opened
#: for. Relative, because the directory it is under is made per run.
STAGED = Path(".claude") / "skills"

#: The name a skill answers to, which is its directory's. Narrower than the
#: `skills.name` column allows on purpose: this is the pattern
#: `mcp__rk2__run_skill_script.skill_name` accepts, and a skill the tool cannot
#: name is a skill whose scripts cannot be run.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: `evidence_profiles.id` and `offline_tools.tool`, restated where the corpus
#: names them. Both are checked for real against the database by the standing
#: check the migration installs; these only refuse a value that could not be
#: either.
PROFILE = re.compile(r"^[a-z0-9_]+$")
RUNTIME_TOOL = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

#: `roles.role`, restated the same way and for the same reason.
ROLE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

#: `roster.TOOL_GROUPS`' keys and the tool names inside them, as spellings. Which
#: groups exist and which role holds them is `roster._check_skills`' question;
#: this only refuses a string that is not a group name or a tool name at all.
TOOL_GROUP = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

#: A description is one line and it is a selection criterion, so it has a
#: ceiling. What is above the ceiling is not a description, it is the skill.
DESCRIPTION_LIMIT = 1024

#: How long one synthetic check may take. A script that needs longer than this
#: over a synthetic input is not a deterministic transform.
CHECK_TIMEOUT = 30

#: Keys a skill may state. `description` is the SDK's and required; the rest of
#: the SDK's own vocabulary is either forbidden below or absent from this corpus
#: on purpose.
REQUIRED_KEYS = ("description", "bb:roles", "bb:tool_groups", "bb:evidence_profile")
OPTIONAL_KEYS = ("allowed-tools", "bb:scripts", "bb:references", "bb:runtime-tools")

#: Keys no skill may state, each with the reason it may not. The shape is
#: `roster.FORBIDDEN_BUILTINS`' and so is the point: a prohibition that does not
#: say what it is protecting is one nobody can argue with later.
#:
#: All four are ways a loaded instruction would reach past the text it is. The
#: frame -- which model, which agent type, which turn -- is opened by the runtime
#: from the roster before the model has read anything, and a skill that could
#: edit it would be instructions granting themselves authority.
FORBIDDEN_KEYS: dict[str, str] = {
    "name": "identity is the directory name; a second one is a name that can drift from it",
    "model": "which model a role runs is the roster's, decided before any instruction is read",
    "agent": "loading instructions may not introduce an Agent type the roster never compiled",
    "agents": "same",
    "context": "`context: fork` runs the text in a frame the gate did not open",
}

#: What a dependency is, for the manifest the version is taken over.
INSTRUCTION_KIND = "instruction"
SCRIPT_KIND = "script"
REFERENCE_KIND = "reference"
KINDS = (INSTRUCTION_KIND, SCRIPT_KIND, REFERENCE_KIND)


class SkillError(document.DocumentError):
    """One reason the skill corpus does not compile, in the words a test names it by."""


@dataclass(frozen=True, slots=True)
class Dependency:
    """One file a skill owns, as the version manifest records it."""

    kind: str
    path: str
    sha256: str

    def line(self) -> str:
        return f"{self.kind} {self.path} {self.sha256}"


@dataclass(frozen=True, slots=True)
class Case:
    """One synthetic check: these Artifacts in, exactly this JSON out.

    `artifacts` is the text of each input; the runner hashes it rather than
    letting the author state a digest, because a digest an author writes is a
    digest that can be wrong about the bytes beside it.
    """

    artifacts: tuple[str, ...]
    stdout: Any

    def payload(self) -> str:
        """The stdin envelope a checked script reads, defined here and nowhere else.

        `mcp__rk2__run_skill_script` has a contract in `roster` and no handler
        in any launch -- ticket 87 owes that channel -- so this is the only
        executable statement of the shape, which is why the checks run against
        it: whatever serves that tool later has to produce this, and a script
        that reads something else fails here first.
        """
        return json.dumps(
            {
                "artifacts": [
                    {"sha256": digest(text.encode("utf-8")), "text": text}
                    for text in self.artifacts
                ]
            },
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class Script:
    """One checked script, and the cases that say what it does."""

    name: str
    description: str
    cases: tuple[Case, ...]
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class Skill:
    """One compiled skill: the exact text, what it needs, and what it is."""

    name: str
    description: str
    roles: tuple[str, ...]
    tool_groups: tuple[str, ...]
    evidence_profile: str
    allowed_tools: tuple[str, ...]
    runtime_tools: tuple[str, ...]
    scripts: Mapping[str, Script]
    references: tuple[str, ...]
    #: The exact bytes of `SKILL.md`, which is what the PreToolUse hook hashes
    #: and what a Task records. Kept as bytes rather than text so the digest and
    #: the thing digested are one object.
    source: bytes
    sha256: str
    dependencies: tuple[Dependency, ...]

    @property
    def version(self) -> str:
        """The digest of the dependency manifest, which is this skill's identity.

        Every file the skill owns, its kind, its path and its hash, one per
        line in a fixed order. Editing a script moves this and leaves `sha256`
        alone, which is the difference a Task needs to be able to record: the
        instructions a model read, and everything that ran underneath them.
        """
        manifest = "".join(f"{item.line()}\n" for item in self.dependencies)
        return digest(manifest.encode("utf-8"))


def _case(name: str, script: str, entry: Any) -> Case:
    if not isinstance(entry, dict):
        raise SkillError("value_malformed", name, f"{script}: a check case is an object")
    unknown = sorted(set(entry) - {"artifacts", "stdout"})
    if unknown:
        raise SkillError("value_malformed", name, f"{script}: a case does not take {unknown}")
    if "artifacts" not in entry or "stdout" not in entry:
        raise SkillError("value_malformed", name, f"{script}: a case states artifacts and stdout")
    artifacts = entry["artifacts"]
    if not isinstance(artifacts, list) or not all(isinstance(one, str) for one in artifacts):
        raise SkillError("value_malformed", name, f"{script}: a case's artifacts are text")
    return Case(tuple(artifacts), entry["stdout"])


def _script(name: str, directory: Path, entry: Any) -> Script:
    if not isinstance(entry, dict):
        raise SkillError("value_malformed", name, "bb:scripts holds objects")
    unknown = sorted(set(entry) - {"name", "description", "checks"})
    if unknown:
        raise SkillError("value_malformed", name, f"a script does not take {unknown}")
    for required in ("name", "description", "checks"):
        if required not in entry:
            raise SkillError("value_malformed", name, f"a script states {required}")
    script_name = entry["name"]
    if not isinstance(script_name, str):
        raise SkillError("value_malformed", name, f"{script_name!r} is not a script name")
    description = entry["description"]
    if not isinstance(description, str) or not description.strip():
        raise SkillError("value_malformed", name, f"{script_name} has no description")
    checks = entry["checks"]
    if not isinstance(checks, list) or not checks:
        # Criterion 3. A script with no case is deterministic behaviour nobody
        # has run, which is the state this key exists to make impossible.
        raise SkillError("check_missing", name, f"{script_name} declares no check")
    path = document.resolved(SkillError, name, directory / SCRIPT_DIR, script_name)
    return Script(
        name=script_name,
        description=description,
        cases=tuple(_case(name, script_name, case) for case in checks),
        path=path,
        sha256=digest(path.read_bytes()),
    )


def _skill(directory: Path) -> Skill:
    name = directory.name
    if not NAME.match(name):
        raise SkillError("name_invalid", name, "a skill is named the way run_skill_script names it")

    source_path = directory / INSTRUCTIONS
    if not source_path.is_file() or source_path.is_symlink():
        raise SkillError("file_missing", name, f"there is no {INSTRUCTIONS}")
    source = source_path.read_bytes()
    text = document.text(SkillError, name, INSTRUCTIONS, source)

    fields, body = document.frontmatter(SkillError, name, INSTRUCTIONS, text)
    if not body:
        raise SkillError("body_missing", name, "a skill whose body is empty teaches nothing")
    for key, reason in FORBIDDEN_KEYS.items():
        if key in fields:
            raise SkillError("key_forbidden", name, f"{key}: {reason}")
    unknown = sorted(set(fields) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        raise SkillError("key_unknown", name, f"nothing reads {unknown}")
    missing = sorted(set(REQUIRED_KEYS) - set(fields))
    if missing:
        raise SkillError("key_missing", name, f"a skill states {missing}")

    description = fields["description"]
    if not isinstance(description, str) or not description.strip():
        raise SkillError("description_missing", name, "a skill states what it is for")
    if len(description) > DESCRIPTION_LIMIT:
        raise SkillError(
            "description_unbounded", name,
            f"{len(description)} characters is the skill, not a criterion for loading it",
        )

    profile = fields["bb:evidence_profile"]
    if not isinstance(profile, str) or not PROFILE.match(profile):
        raise SkillError("value_malformed", name, f"{profile!r} is not an evidence profile id")

    stray = document.strays(directory, (INSTRUCTIONS, SCRIPT_DIR, REFERENCE_DIR))
    if stray:
        raise SkillError("stray_file", name, f"nothing reads {stray}")

    declared_scripts = fields.get("bb:scripts", [])
    if not isinstance(declared_scripts, list):
        raise SkillError("value_malformed", name, "bb:scripts is a JSON array")
    scripts = tuple(_script(name, directory, entry) for entry in declared_scripts)
    if len({script.name for script in scripts}) != len(scripts):
        raise SkillError("duplicate_entry", name, "two scripts share a name")
    references = (
        document.strings(SkillError, name, "bb:references",
                         fields["bb:references"], ENTRY)
        if "bb:references" in fields else ()
    )
    reference_paths = {
        reference: document.resolved(SkillError, name, directory / REFERENCE_DIR, reference)
        for reference in references
    }

    # Both directions. A declared file that is absent is a skill that breaks
    # when it is used; a present file nothing declares is material inside the
    # mounted corpus that no rule here has looked at, and the version manifest
    # would not cover it.
    for directory_name, declared in (
        (SCRIPT_DIR, {script.name for script in scripts}),
        (REFERENCE_DIR, set(references)),
    ):
        undeclared = sorted(
            set(document.listing(SkillError, name, directory / directory_name)) - declared
        )
        if undeclared:
            raise SkillError("stray_file", name, f"{directory_name}/ carries undeclared {undeclared}")

    dependencies = [Dependency(INSTRUCTION_KIND, INSTRUCTIONS, digest(source))]
    dependencies += [
        Dependency(SCRIPT_KIND, f"{SCRIPT_DIR}/{script.name}", script.sha256) for script in scripts
    ]
    dependencies += [
        Dependency(REFERENCE_KIND, f"{REFERENCE_DIR}/{reference}", digest(path.read_bytes()))
        for reference, path in reference_paths.items()
    ]

    return Skill(
        name=name,
        description=description,
        roles=document.strings(SkillError, name, "bb:roles", fields["bb:roles"], ROLE),
        tool_groups=document.strings(
            SkillError, name, "bb:tool_groups", fields["bb:tool_groups"], TOOL_GROUP),
        evidence_profile=profile,
        allowed_tools=(
            document.strings(SkillError, name, "allowed-tools", fields["allowed-tools"], TOOL)
            if "allowed-tools" in fields else ()
        ),
        runtime_tools=(
            document.strings(
                SkillError, name, "bb:runtime-tools",
                fields["bb:runtime-tools"], RUNTIME_TOOL)
            if "bb:runtime-tools" in fields else ()
        ),
        scripts=MappingProxyType({script.name: script for script in scripts}),
        references=references,
        source=source,
        sha256=digest(source),
        dependencies=tuple(sorted(dependencies, key=lambda one: (one.kind, one.path))),
    )


def check(skill: Skill, script: Script, case: Case) -> None:
    """Run one synthetic case, twice, and refuse anything but the declared answer.

    Twice because the word in the criterion is *deterministic*, and one run
    cannot tell a transform from a coin. Under a bare environment and in an
    empty directory, because a script that reads the ambient environment or a
    file beside it is a script whose output is not a function of its input --
    and `mcp__rk2__run_skill_script` gives it neither.
    """
    with tempfile.TemporaryDirectory() as empty:
        answers = []
        for _ in range(2):
            try:
                completed = subprocess.run(
                    [sys.executable, str(script.path)],
                    input=case.payload(),
                    capture_output=True,
                    text=True,
                    timeout=CHECK_TIMEOUT,
                    cwd=empty,
                    env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0"},
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise SkillError(
                    "check_failed", skill.name, f"{script.name} did not finish in {CHECK_TIMEOUT}s"
                ) from error
            if completed.returncode != 0:
                raise SkillError(
                    "check_failed", skill.name,
                    f"{script.name} exited {completed.returncode}: {completed.stderr.strip()}",
                )
            try:
                answers.append(json.loads(completed.stdout))
            except json.JSONDecodeError as error:
                raise SkillError(
                    "check_failed", skill.name, f"{script.name} did not write JSON: {error}"
                ) from error
    if answers[0] != answers[1]:
        raise SkillError("check_failed", skill.name, f"{script.name} answered twice and differed")
    if answers[0] != case.stdout:
        raise SkillError(
            "check_failed", skill.name,
            f"{script.name} answered {json.dumps(answers[0], sort_keys=True)}",
        )


def check_all(skills: Mapping[str, Skill] | None = None) -> tuple[str, ...]:
    """Every declared case in the corpus, and what was run, so a caller can count."""
    ran = []
    for skill in (skills if skills is not None else SKILLS).values():
        for script in skill.scripts.values():
            for ordinal, case in enumerate(script.cases, start=1):
                check(skill, script, case)
                ran.append(f"{skill.name}/{script.name}#{ordinal}")
    return tuple(ran)


def compile_corpus(root: Path = CORPUS) -> Mapping[str, Skill]:
    """Parse and check every skill under `root`, or refuse.

    Parameterised on the root so a test can compile a corpus it wrote rather
    than the installed one. Nothing in the running system passes an argument.
    """
    # A skill's name is its directory's, so two skills cannot share one: the
    # filesystem already refuses that, and `NAME` admits only lower case, so
    # there is no pair of legal names a case-folding filesystem would merge
    # either. The duplicates this corpus can express are inside a document --
    # two scripts, two list entries, a key stated twice -- and each is refused
    # where it is written.
    compiled: dict[str, Skill] = {}
    for entry in document.directories(SkillError, root, "skill"):
        skill = _skill(entry)
        compiled[skill.name] = skill
    return MappingProxyType(compiled)


def stage(
    launch: Path | str,
    names: Sequence[str],
    corpus: Mapping[str, Skill] | None = None,
) -> tuple[Path, ...]:
    """Write the instructions a role was granted where its child will load them.

    A grant is not yet a skill the model can use. `Gate._skill` admits a call
    by the name the role holds and the CLI answers it by reading a directory,
    so a grant with no directory behind it is a name the gate lets through and
    the model then cannot load. This is the step that puts the two in one
    place, and it writes only the granted names: a child holding the whole
    corpus would be a child one prompt away from instructions no roster row
    gave it.

    `SKILL.md` and nothing else. The instructions are what a model loads;
    `scripts/` is run here, by `check`, and by nothing during a run -- the tool
    that would run one over stored Artifacts is `mcp__rk2__run_skill_script`,
    which ticket 87 owes -- and `references/` is maintainer material this system
    has no tool to open. The module docstring says so, and staging either would
    put files in a child's directory that nothing in its frame can reach.

    The bytes written are the compiled skill's own `source`, which is what
    `sha256` digests and what a Task records, so the text a child reads and the
    digest an installation reports are one object and not two copies.

    `corpus` is a parameter for the reason `compile_corpus`' root is: a test
    can stage a corpus it wrote. Nothing in the running system passes one.
    """
    corpus = SKILLS if corpus is None else corpus
    root = Path(launch) / STAGED
    written = []
    for name in names:
        one = corpus.get(name)
        if one is None:
            raise SkillError("skill_absent", name, "this installation carries no such skill")
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        instructions = directory / INSTRUCTIONS
        instructions.write_bytes(one.source)
        instructions.chmod(0o600)
        written.append(instructions)
    return tuple(written)


#: The compiled corpus, read-only, built at import so a bad corpus is never a
#: running one. `roster` imports it and derives `Role.skills` from it.
SKILLS: Mapping[str, Skill] = compile_corpus()
