"""The corpus as a Google Open Knowledge Format v0.2 bundle.

Ticket 101 asks for a knowledge view of the shipped catalogue "without weakening
the closed `bb:` execution schema". Those are two different jobs and this module
is the reason they do not become one. `bb:` is an execution contract: a closed
set of keys, loaded into Postgres by migration, where an unknown value fails at
INSERT. OKF is a portable provenance view: open by design, where a consumer
"MUST NOT reject documents with unrecognized fields". A format that tried to be
both would have to give up the half that makes it useful.

So the bundle is **derived and never authored**. Every concept here is generated
from `playbook.PLAYBOOKS` and `skill.SKILLS`, which are the same compiled
corpora the runtime reads, and `tests/test_okf.py` regenerates it and compares.
A second hand-maintained copy of fifty Playbooks is a copy that is wrong within
a month, and the whole point of a provenance view is that it is not wrong.

What conformance actually requires is short, and section 11 of the specification
says so: every non-reserved `.md` file parses, every one of them carries a
non-empty `type`, and `index.md` and `log.md` are the two reserved names. Every
other constraint is soft guidance a consumer may not reject a bundle over. This
module meets the three and then goes further on the families ticket 101 names --
`sources` with stable ids and matching footnotes, `generated`, `status`,
`stale_after`, the actor spellings -- because a provenance view that carries no
provenance is a directory of prose.

Two absences are decisions rather than omissions.

**No `verified` key anywhere.** OKF derives its trust tier from that key: absent
means `unverified`. Every Playbook in this corpus ships `bb:status: draft`
because no fixture has graded it, so `unverified` is the true tier and writing
the key would be the one lie a provenance format can tell. It appears on the day
ticket 84's grading produces a verdict, with `process:` as the actor.

**No `type: Attested Computation`.** The four offline tools are deterministic and
do return a declared Receipt, so they would qualify -- but the corpus source
policy says the label is used "only where a deterministic executor returns a
declared Receipt and a no-LLM attester can verify it", and nothing in this tree
is an attester yet. Ordinary Playbook prose is not relabelled as an attested
computation to make the bundle look richer.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from pathlib import Path

from . import playbook, skill

#: Where a corpus path is rooted. `Playbook.path` and `Reference.path` are
#: written relative to the installed package -- `playbooks/<name>/playbook.md`
#: -- because that is what the database stores and what a Task records. This
#: module needs both the real file and a repository-relative spelling for the
#: link, so it resolves through here rather than guessing a prefix.
PACKAGE = playbook.CORPUS.parent

#: Where the bundle lands is not this module's business, and `check_baseline`
#: is right that it is not: an installable application may not name a path under
#: the documentation tree. So `build` returns a mapping of bundle-relative name
#: to text, `write` takes the target directory, and the one place the target is
#: written down is `tests/test_okf.py`, which is where it is enforced anyway.

#: How deep a concept sits under the bundle root, so a generated relative link
#: back to an authoritative file resolves. Every concept in this bundle sits in
#: exactly one directory under the root, which is why this is a constant and not
#: a computation: a second level would need a per-concept depth and there is no
#: second level. Three levels is the depth the bundle root sits at; a caller
#: writing it elsewhere gets links that do not resolve, which the freeze test
#: is the guard against.
DEPTH = "../../../"

#: `generated.at`. OKF wants "the ISO 8601 datetime of last meaningful change",
#: and a generator that stamped the clock would rewrite fifty files on every run
#: and make the freeze test meaningless. So it is a constant, bumped by whoever
#: regenerates the bundle after a corpus change, which is what "last meaningful
#: change" actually means.
BUILT_AT = "2026-08-28T00:00:00Z"

#: The actor. `process:` and not `<producer>/<version>`, because section 7's
#: producer form is for an agent or a tool with a model behind it and this is a
#: deterministic function of the corpus. Nothing here was written by a model.
ACTOR = "process:redkraken-okf"

OKF_VERSION = "0.2"

#: The two reserved filenames of section 11. Everything else under the root is a
#: concept document and is held to the `type` rule.
RESERVED = ("index.md", "log.md")

FENCE = "---"

#: A concept's file name, which is also the stem of its stable source id.
STEM = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BundleError(Exception):
    """One reason the bundle cannot be built or does not conform."""


def _instant(day: dt.date) -> str:
    """A `bb:stale_after` date as the absolute instant OKF asks for.

    Section 5.5 wants an instant and not a date, so that "is this stale" is one
    comparison in every timezone rather than a question about which midnight.
    Midnight UTC is the reading that makes a review due on the day the author
    wrote down, and never the day before it.
    """
    return f"{day.isoformat()}T00:00:00Z"


def _front(fields: list[tuple[str, str]]) -> str:
    """A frontmatter block, in the order given.

    Order is the caller's because a generated document is read by people:
    `type` first because it is the one required key, then identity, then the
    trust and lifecycle families, then sources last because they are the
    longest. A sorted block would put `description` above `type`.
    """
    lines = [FENCE]
    for key, value in fields:
        # A block value opens on the next line, so it is joined without the
        # space. `git diff --check` is one of this repository's gates and a
        # `key: ` with nothing after it is trailing whitespace to it.
        if value.startswith("\n"):
            lines.append(f"{key}:{value}")
        else:
            lines.append(f"{key}: {value}" if value else f"{key}:")
    lines.append(FENCE)
    return "\n".join(lines)


def _quote(text: str) -> str:
    """A scalar YAML will read back as the string it was given.

    Everything generated here is a description or a title lifted out of the
    corpus, and those carry colons. A colon followed by a space is a second key
    to a YAML parser, so the whole value is double-quoted and the two characters
    that would end the quote early are escaped.
    """
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _heading(text: str, fallback: str) -> str:
    """A maintainer reference's own title, or its file name.

    Every one of the eighty-four opens with an ATX heading today. `fallback`
    is here for the one that will not, rather than for a bug: a reference is a
    file a maintainer wrote and nothing enforces its first line.
    """
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _reference_id(owner: str, name: str) -> str:
    """The stable source id, which is also the concept's file name."""
    return f"{owner}--{name[:-3] if name.endswith('.md') else name}"


def _corpus_path(root: Path, relative: str) -> tuple[Path, str]:
    """A corpus-relative path as the real file and as a repository-relative link."""
    absolute = PACKAGE / relative
    return absolute, absolute.relative_to(root).as_posix()


def _playbook_concept(one: playbook.Playbook, root: Path) -> str:
    """One Playbook as an OKF concept.

    `resource` points out of the bundle at the authoritative document, which is
    the whole design: this concept describes a Playbook, it is not a second copy
    of one. A consumer that wants the execution contract follows the link and
    reads the `bb:` frontmatter there.
    """
    sources = []
    footnotes = []
    for reference in one.references:
        path, _ = _corpus_path(root, reference.path)
        title = _heading(path.read_text(encoding="utf-8"), reference.name)
        source_id = _reference_id(one.name, reference.name)
        sources.append(
            f"  - id: {source_id}\n"
            f"    resource: /references/{source_id}.md\n"
            f"    title: {_quote(title)}\n"
            f"    author: human:maintainer\n"
        )
        footnotes.append(f"[^{source_id}]: {title}")

    front = [
        ("type", "Playbook"),
        ("title", _quote(one.name)),
        ("description", _quote(one.description)),
        ("resource", f"{DEPTH}{_corpus_path(root, one.path)[1]}"),
        ("tags", "[" + ", ".join([one.category, one.risk, one.effects]) + "]"),
        ("generated", f"{{ by: {ACTOR}, at: {BUILT_AT} }}"),
        ("status", one.status),
        ("stale_after", _instant(one.stale_after)),
        # The `bb:` half, carried verbatim as extension keys. Section 5 of the
        # specification says a consumer "SHOULD preserve unknown keys when
        # round-tripping", so this is the round-trip surface ticket 101 asks a
        # test to exercise -- and it is the honest place for them, because they
        # are this producer's fields and not OKF's.
        ("bb:category", one.category),
        ("bb:outputs", "[" + ", ".join(one.property_classes) + "]"),
        ("bb:triggers_all", "[" + ", ".join(one.triggers_all) + "]"),
    ]
    if one.triggers_any:
        front.append(("bb:triggers_any", "[" + ", ".join(one.triggers_any) + "]"))
    front.extend(
        [
            ("bb:skills", "[" + ", ".join(one.skills) + "]"),
            ("bb:risk", one.risk),
            ("bb:effects", one.effects),
            ("bb:baseline", one.baseline),
            ("bb:version", one.version),
            ("bb:sha256", one.sha256),
        ]
    )
    if sources:
        front.append(("sources", "\n" + "".join(sources).rstrip()))

    body = [
        f"# {one.description}",
        "",
        "## What it concludes about",
        "",
        *(f"- `{klass}`" for klass in one.property_classes),
        "",
        "## When it is selected",
        "",
        "A subject carrying every one of these facts:",
        "",
        *(f"- `{fact}`" for fact in one.triggers_all),
    ]
    if one.triggers_any:
        body.extend(["", "and at least one of:", "", *(f"- `{f}`" for f in one.triggers_any)])
    body.extend(
        [
            "",
            f"Risk `{one.risk}`, effects `{one.effects}`, baseline `{one.baseline}`.",
            "",
            "## Skills it loads",
            "",
            *(f"- [{name}](/skills/{name}.md)" for name in one.skills),
            "",
            "## What it owes before a claim moves",
            "",
        ]
    )
    for expectation in one.evidence:
        polarity = expectation.polarity or "either-way"
        body.append(
            f"- to `{expectation.to_status}`: at least {expectation.min_count} "
            f"{polarity} `{expectation.kind}` observation(s) from a "
            f"`{expectation.role}`"
        )
    body.extend(["", "## Provenance", "", one.provenance])
    if one.references:
        body.extend(["", "## Maintainer references", ""])
        for reference in one.references:
            source_id = _reference_id(one.name, reference.name)
            body.append(f"- [{reference.name}](/references/{source_id}.md)[^{source_id}]")
        body.extend(["", *footnotes])
    body.extend(
        [
            "",
            "## The authoritative document",
            "",
            f"The execution contract is the closed `bb:` frontmatter of "
            f"[`{one.path}`]({DEPTH}{_corpus_path(root, one.path)[1]}). This "
            f"concept describes that document and never replaces it.",
        ]
    )
    return _front(front) + "\n\n" + "\n".join(body).rstrip() + "\n"


def _skill_concept(one: skill.Skill, root: Path) -> str:
    """One Skill as an OKF concept, and the executor half of the graph."""
    sources = []
    footnotes = []
    for name in one.references:
        path, _ = _corpus_path(root, f"skills/{one.name}/references/{name}")
        title = _heading(path.read_text(encoding="utf-8"), name)
        source_id = _reference_id(one.name, name)
        sources.append(
            f"  - id: {source_id}\n"
            f"    resource: /references/{source_id}.md\n"
            f"    title: {_quote(title)}\n"
            f"    author: human:maintainer\n"
        )
        footnotes.append(f"[^{source_id}]: {title}")

    front = [
        ("type", "Skill"),
        ("title", _quote(one.name)),
        ("description", _quote(one.description)),
        ("resource", f"{DEPTH}{_corpus_path(root, f'skills/{one.name}/SKILL.md')[1]}"),
        ("tags", "[skill, " + one.evidence_profile + "]"),
        ("generated", f"{{ by: {ACTOR}, at: {BUILT_AT} }}"),
        # A Skill carries no `bb:status`; it is shipped or it is not. `stable`
        # is OKF's default for an absent key and is stated rather than left out,
        # because the Playbooks beside it all say `draft` and a reader comparing
        # the two should see the difference is meant.
        ("status", "stable"),
        ("stale_after", _instant(dt.date(2027, 8, 28))),
        ("bb:roles", "[" + ", ".join(one.roles) + "]"),
        ("bb:evidence_profile", one.evidence_profile),
        ("bb:version", one.version),
        ("bb:sha256", one.sha256),
    ]
    if sources:
        front.append(("sources", "\n" + "".join(sources).rstrip()))

    body = [
        f"# {one.description}",
        "",
        "## Which roles may load it",
        "",
        *(f"- `{role}`" for role in one.roles),
        "",
        "## What it may call",
        "",
        *(f"- `{tool}`" for tool in one.allowed_tools),
    ]
    if one.runtime_tools:
        body.extend(["", "Runtime tools it reaches through `run_tool`:", ""])
        body.extend(f"- `{tool}`" for tool in one.runtime_tools)
    if one.scripts:
        body.extend(["", "## Scripts it owns", ""])
        body.extend(f"- `{name}`" for name in sorted(one.scripts))
    used_by = sorted(p.name for p in playbook.PLAYBOOKS.values() if one.name in p.skills)
    body.extend(["", "## Playbooks that load it", ""])
    body.extend(f"- [{name}](/playbooks/{name}.md)" for name in used_by)
    if one.references:
        body.extend(["", "## Maintainer references", ""])
        for name in one.references:
            source_id = _reference_id(one.name, name)
            body.append(f"- [{name}](/references/{source_id}.md)[^{source_id}]")
        body.extend(["", *footnotes])
    return _front(front) + "\n\n" + "\n".join(body).rstrip() + "\n"


def _reference_concept(owner: str, owner_kind: str, name: str, path: Path) -> str:
    """One maintainer reference as a concept.

    The body is a pointer and a sentence, never a copy. A reference is a file a
    maintainer wrote and it stays the one authority on its own contents; a
    second copy in the bundle is a second thing to keep in step.
    """
    text = path.read_text(encoding="utf-8")
    title = _heading(text, name)
    source_id = _reference_id(owner, name)
    relative = path.as_posix()
    front = [
        ("type", "Reference"),
        ("title", _quote(title)),
        (
            "description",
            _quote(f"Maintainer reference held by the {owner_kind} {owner}."),
        ),
        ("resource", f"{DEPTH}{relative}"),
        ("tags", f"[reference, {owner_kind}]"),
        ("generated", f"{{ by: {ACTOR}, at: {BUILT_AT} }}"),
        ("status", "stable"),
        ("stale_after", _instant(dt.date(2027, 8, 28))),
        ("bb:owner", owner),
        ("bb:owner_kind", owner_kind),
    ]
    owner_link = f"/{'playbooks' if owner_kind == 'playbook' else 'skills'}/{owner.rstrip()}.md"
    body = [
        f"# {title}",
        "",
        f"Maintainer material. Nothing here reaches a model: the runtime stages "
        f"`SKILL.md` and a Playbook projection, and neither carries a "
        f"`references/` directory.",
        "",
        f"Held by [{owner}]({owner_link}).",
        "",
        f"The file itself is [`{relative}`]({DEPTH}{relative}).",
        "",
        f"Source id `{source_id}`, which is what the owning concept's "
        f"`sources` entry and its footnote both key on.",
    ]
    return _front(front) + "\n\n" + "\n".join(body).rstrip() + "\n"


def _index(title: str, description: str, entries: list[tuple[str, str]]) -> str:
    """A section index. Frontmatter is permitted only at the root, so it carries none."""
    lines = [f"# {title}", "", description, ""]
    lines.extend(f"* [{name}]({link}) - {note}" for name, link, note in entries)
    return "\n".join(lines).rstrip() + "\n"


def build(
    root: Path,
    playbooks: Mapping[str, playbook.Playbook] | None = None,
    skills: Mapping[str, skill.Skill] | None = None,
) -> dict[str, str]:
    """The whole bundle as bundle-relative path -> text.

    A mapping and not a directory write, so the freeze test compares strings and
    the failure names the file rather than a diff of a tree. `write` is the
    thin half that puts it on disk.
    """
    playbooks = playbook.PLAYBOOKS if playbooks is None else playbooks
    skills = skill.SKILLS if skills is None else skills
    files: dict[str, str] = {}

    references: dict[str, tuple[str, str, Path]] = {}
    for one in playbooks.values():
        for reference in one.references:
            source_id = _reference_id(one.name, reference.name)
            if source_id in references:
                raise BundleError(f"two references claim the source id {source_id}")
            references[source_id] = (
                one.name,
                "playbook",
                _corpus_path(root, reference.path)[0],
            )
    for one in skills.values():
        for name in one.references:
            source_id = _reference_id(one.name, name)
            if source_id in references:
                raise BundleError(f"two references claim the source id {source_id}")
            references[source_id] = (
                one.name,
                "skill",
                _corpus_path(root, f"skills/{one.name}/references/{name}")[0],
            )

    for name, one in sorted(playbooks.items()):
        files[f"playbooks/{name}.md"] = _playbook_concept(one, root)
    for name, one in sorted(skills.items()):
        files[f"skills/{name}.md"] = _skill_concept(one, root)
    for source_id, (owner, owner_kind, path) in sorted(references.items()):
        files[f"references/{source_id}.md"] = _reference_concept(
            owner, owner_kind, path.name, path.relative_to(root)
        )

    files["playbooks/index.md"] = _index(
        "Playbooks",
        "One concept per shipped Playbook. Each links to the Skills it loads and "
        "to the maintainer references it declares, and points at the "
        "authoritative document whose closed `bb:` frontmatter is the execution "
        "contract.",
        [
            (name, f"{name}.md", one.description)
            for name, one in sorted(playbooks.items())
        ],
    )
    files["skills/index.md"] = _index(
        "Skills",
        "The six shipped Skills. A Playbook names one or more of these and the "
        "runtime stages only the ones the role was granted.",
        [(name, f"{name}.md", one.description) for name, one in sorted(skills.items())],
    )
    files["references/index.md"] = _index(
        "References",
        "Maintainer material held by a Playbook or a Skill. None of it reaches a "
        "model. Each concept is a pointer at the file, never a copy of it.",
        [
            (source_id, f"{source_id}.md", f"held by the {kind} {owner}")
            for source_id, (owner, kind, _) in sorted(references.items())
        ],
    )

    files["index.md"] = (
        _front([("okf_version", f'"{OKF_VERSION}"')])
        + "\n\n"
        + _index(
            "redKraken hunting corpus",
            "The shipped Playbook, Skill and maintainer-reference catalogue as a "
            "Google Open Knowledge Format v0.2 bundle. Every concept here is "
            "derived from the same compiled corpora the runtime reads and is "
            "regenerated by `redkraken.okf.build`; nothing in this directory is "
            "authored by hand, and nothing in it is loaded by the runtime.",
            [
                (
                    "playbooks",
                    "playbooks/index.md",
                    f"{len(playbooks)} Playbooks: what each concludes about, what "
                    "selects it, and what it owes before a claim moves.",
                ),
                (
                    "skills",
                    "skills/index.md",
                    f"{len(skills)} Skills: the executor half of the graph.",
                ),
                (
                    "references",
                    "references/index.md",
                    f"{len(references)} maintainer references, one concept each.",
                ),
            ],
        )
    )
    files["log.md"] = (
        _front([("type", "Log"), ("title", _quote("redKraken corpus bundle history"))])
        + "\n\n"
        + "\n".join(
            [
                "# Bundle history",
                "",
                "## 2026-08-28",
                "",
                "- **Bootstrapped** by `process:redkraken-okf` from the compiled "
                "Playbook and Skill corpora for ticket 101. Initial trust tier: "
                "`unverified` across the board, which is the true tier -- no "
                "`verified` key is written anywhere, because every Playbook "
                "still ships `bb:status: draft` and no fixture has graded one.",
            ]
        )
        + "\n"
    )
    return files


def write(root: Path, target: Path) -> tuple[Path, ...]:
    """Put the bundle on disk under `target`, replacing what is there.

    `root` is the repository root the corpus is read against; `target` is where
    the bundle is written. Two arguments and not one because they answer two
    questions, and because the second is a path this module may not name.
    """
    written = []
    for relative, text in sorted(build(root).items()):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return tuple(written)


def _frontmatter(text: str) -> dict[str, str] | None:
    """The block, flattened to one string per key, or None if there is none.

    Deliberately not a YAML parser and deliberately not `document.frontmatter`:
    that one enforces the `bb:` document's rules, and an OKF block is a
    different shape -- nested mappings, block sequences, quoted scalars. What
    the checks below need is which keys are present and what their first line
    says, and that is what this returns.
    """
    if not text.startswith(FENCE + "\n"):
        return None
    end = text.find(f"\n{FENCE}\n", len(FENCE))
    if end < 0:
        return None
    fields: dict[str, str] = {}
    key = ""
    for line in text[len(FENCE) + 1 : end].splitlines():
        if line[:1].isalpha() and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        elif key and line.strip():
            fields[key] += " " + line.strip()
    return fields


#: `<producer>/<version>`, `human:<id>` or `process:<id>` -- section 7, all three.
ACTOR_FORM = re.compile(r"^(human:[^\s]+|process:[^\s]+|[^\s:]+/[^\s:]+)$")
LINK = re.compile(r"\]\((/[^)]+)\)")
FOOTNOTE_USE = re.compile(r"\[\^([^\]]+)\]")
FOOTNOTE_DEF = re.compile(r"^\[\^([^\]]+)\]:", re.MULTILINE)
SOURCE_ID = re.compile(r"^\s+- id:\s*(\S+)\s*$", re.MULTILINE)


def validate(files: Mapping[str, str]) -> tuple[str, ...]:
    """Every way this bundle fails v0.2, or an empty tuple.

    The first three checks are section 11's conformance rules, which are the
    only hard ones. Everything after them is a rule ticket 101 asked for by
    name, checked here rather than left as a claim in a document: a bundle that
    says it carries provenance and does not is worse than one that says nothing.
    """
    faults: list[str] = []

    if "index.md" not in files:
        faults.append("the bundle has no root index.md")
    else:
        front = _frontmatter(files["index.md"])
        if front is None or front.get("okf_version") != f'"{OKF_VERSION}"':
            faults.append(f'root index.md does not declare okf_version: "{OKF_VERSION}"')

    for name, text in sorted(files.items()):
        base = name.rsplit("/", 1)[-1]
        front = _frontmatter(text)

        if base == "index.md":
            # Section 8: frontmatter is permitted in the root index and nowhere
            # else, and a section index is a body of links for progressive
            # disclosure. Both halves are checked, because an index with no
            # links is a directory listing wearing an index's name.
            if name != "index.md" and front is not None:
                faults.append(f"{name}: only the root index.md may carry frontmatter")
            if "](" not in text:
                faults.append(f"{name}: an index with no links discloses nothing")
            continue
        if base == "log.md":
            if front is None or front.get("type") != "Log":
                faults.append(f"{name}: the reserved log carries no type: Log")
            continue

        if front is None:
            faults.append(f"{name}: no parseable frontmatter block")
            continue
        if not front.get("type"):
            faults.append(f"{name}: no non-empty type, which is the one required key")
            continue

        generated = front.get("generated", "")
        actor = generated.partition("by:")[2].partition(",")[0].strip()
        if not actor:
            faults.append(f"{name}: generated carries no actor")
        elif not ACTOR_FORM.match(actor):
            faults.append(f"{name}: {actor!r} is not an OKF actor spelling")

        status = front.get("status", "")
        if status not in ("draft", "stable", "deprecated"):
            faults.append(f"{name}: status {status!r} is outside the lifecycle family")
        stale = front.get("stale_after", "")
        if not stale.endswith("Z") or "T" not in stale:
            faults.append(f"{name}: stale_after {stale!r} is not an absolute instant")

        body = text[text.find(f"\n{FENCE}\n", len(FENCE)) + len(FENCE) + 2 :]
        declared = set(SOURCE_ID.findall(text[: text.find(f"\n{FENCE}\n", len(FENCE))]))
        defined = set(FOOTNOTE_DEF.findall(body))
        used = set(FOOTNOTE_USE.findall(body)) - defined
        # Both directions. A footnote with no source is an attribution pointing
        # at nothing; a source no claim cites is a citation nobody made.
        for orphan in sorted(used - declared):
            faults.append(f"{name}: footnote [^{orphan}] matches no sources[].id")
        for unused in sorted(declared - defined):
            faults.append(f"{name}: source id {unused} is declared and never cited")

        for target in LINK.findall(text):
            if target.lstrip("/") not in files:
                faults.append(f"{name}: bundle-relative link {target} resolves to nothing")

    return tuple(faults)
