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

from . import document, playbook, skill

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
    # Once, here, because this is the only door `_corpus_path` is reached
    # through and `relative_to` is lexical: `Path('.')` names the repository
    # root and is not a prefix of any resolved path under it.
    root = root.resolve()
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
    # Section 9, quoted: "Log files carry no frontmatter." A reserved name is
    # not a concept, and a `type: Log` block here would be a concept wearing
    # one. Section 11's third rule is what makes it a fault rather than a
    # preference: a reserved filename follows the structure of section 8 or 9
    # when it is present, and a frontmatter block is not that structure.
    files["log.md"] = (
        "\n".join(
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


#: The seven shapes `_front` writes, and therefore the only seven a block in
#: this bundle may carry. Measured over `build()` rather than guessed -- every
#: one of the 2136 frontmatter lines it emits falls into them, and none outside:
#:
#:   1046  `key: <plain>`                      `type: Log`
#:    301  `key: [a, b, c]`                    `tags: [injection, read_only]`
#:    281  `key: "..."`                        `okf_version: "0.2"`
#:    252  four spaces, `key: value`           `    resource: /references/x.md`
#:    140  `key: { k: v, k: v }`               `generated: { by: ..., at: ... }`
#:     84  two spaces, `- key: value`          `  - id: agentic-ai--llm`
#:     32  `key:`, which opens a block sequence `sources:`
#:
#: A key is lower case with underscores, optionally namespaced once by a colon,
#: which is what admits the fourteen `bb:` extension keys alongside `okf_version`.
OKF_KEY = re.compile(r"^[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)?$")

#: The escapes YAML defines inside a double-quoted scalar. `_quote` writes two
#: of them; the rest are here because the grammar belongs to the format rather
#: than to today's emitter.
OKF_ESCAPE = re.compile(r'\\(?:[\\"/bfnrt0]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})')


def _plain(value: str) -> str:
    """Why this is not a plain scalar two parsers would read the same way."""
    if not value:
        return "has no value"
    if value[0] in document.INDICATORS:
        return f"opens with {value[0]!r}, which YAML reads as structure"
    if ": " in value or value.endswith(":"):
        return "carries a colon YAML would read as a second key"
    if " #" in value:
        return "carries a comment introducer"
    return ""


def _quoted(value: str) -> str:
    """Why this is not a closed double-quoted scalar."""
    if len(value) < 2 or not value.endswith('"'):
        return "opens a quote it never closes"
    # Every defined escape is removed first, so what is left is what a parser
    # would still have to interpret: a lone backslash, or a quote that ends the
    # scalar in the middle of it.
    body = OKF_ESCAPE.sub("", value[1:-1])
    if "\\" in body:
        return "carries a backslash escape YAML does not define"
    if '"' in body:
        return "closes its quote early"
    return ""


#: The four characters YAML calls flow indicators. Inside a flow collection
#: they end the scalar wherever they stand and not only where it opens, so
#: `[a[b]` and `[a]b]` are both refused by a parser and both waved through by a
#: check that reads the first character. Section 7.3.3 of the YAML spec.
FLOW_INDICATORS = ",[]{}"


def _flow_plain(value: str) -> str:
    """Why this is not a plain scalar a flow collection may hold."""
    fault = _plain(value)
    if fault:
        return fault
    for indicator in FLOW_INDICATORS:
        if indicator in value:
            return f"carries {indicator!r}, which ends a scalar inside a flow collection"
    return ""


def _flow_sequence(value: str) -> str:
    """Why this is not a flow sequence of plain scalars."""
    if not value.endswith("]"):
        return "opens a flow sequence it never closes"
    inner = value[1:-1]
    if not inner.strip():
        return "is an empty flow sequence, which this emitter never writes"
    for position, element in enumerate(inner.split(",")):
        want = element.strip()
        if not want:
            # `[a,,b]` and `[a, b,]` both land here, and both are the reason a
            # comma count is not a substitute for reading the elements.
            return "holds an empty element"
        if element != (want if position == 0 else f" {want}"):
            return "separates its elements by something other than a comma and a space"
        fault = _flow_plain(want)
        if fault:
            return f"holds an element that {fault}"
    return ""


def _flow_mapping(value: str) -> str:
    """Why this is not a flow mapping of `key: value` pairs."""
    if not value.endswith("}"):
        return "opens a flow mapping it never closes"
    inner = value[1:-1].strip()
    if not inner:
        return "is an empty flow mapping, which this emitter never writes"
    for pair in inner.split(", "):
        key, separator, held = pair.partition(": ")
        if not separator:
            return f"holds {pair!r}, which is not a `key: value` pair"
        if not OKF_KEY.match(key):
            return f"holds {key!r}, which is not a key"
        fault = _quoted(held) if held.startswith('"') else _flow_plain(held)
        if fault:
            return f"holds a value that {fault}"
    return ""


def _value(value: str) -> str:
    """Why this value is outside the four shapes a value may take."""
    if value.startswith("["):
        return _flow_sequence(value)
    if value.startswith("{"):
        return _flow_mapping(value)
    if value.startswith('"'):
        return _quoted(value)
    return _plain(value)


def frontmatter_faults(name: str, text: str) -> tuple[str, ...]:
    """Every way this block leaves the sub-grammar above, in line order.

    Section 11 asks whether a concept's frontmatter is parseable YAML, and this
    answers it without a YAML parser, because the runtime carries no
    third-party dependency and this module is not the place to acquire one.
    The repository has paid this wall three times already and decided the same
    way each time: `document.frontmatter`, `check_wiring.frontmatter` -- "No
    YAML: this gate is standard library only" -- and `_frontmatter` below.

    It is a closed sub-grammar and not a list of suspicions. The seven forms
    are admitted and everything else is refused, so a shape nobody anticipated
    is refused rather than waved through; a plausibility check would still pass
    `type: [a,,b]`. Block scalars, anchors, aliases, tags and merge keys need
    no rule of their own: each opens with a character `_plain` already refuses,
    or spells a key `OKF_KEY` already refuses.

    The direction is one way and deliberately so. What passes here is valid
    YAML; valid YAML does not have to pass here. That is the right bias for a
    checker over one generator's output, and the positive corpus in
    `tests/test_okf.py` is what keeps the admitted half honest.

    Key and value split at the first `": "` -- colon *and* space, or a colon
    ending the line -- and never at the first colon. That is YAML's own rule,
    and it is why `bb:category: injection` carries the key `bb:category` and
    why `stale_after: 2027-02-15T00:00:00Z` is one plain scalar. `_frontmatter`
    below splits at the first colon instead and therefore sees a single `bb`
    key. The two views differ on purpose and both are kept.
    """
    if not text.startswith(FENCE + "\n"):
        return (f"{name}: no frontmatter block opens the file",)
    end = text.find(f"\n{FENCE}\n", len(FENCE))
    if end < 0:
        return (f"{name}: the frontmatter block is never closed",)
    block = text[len(FENCE) + 1 : end]
    if not block:
        return (f"{name}: the frontmatter block is empty",)

    faults: list[str] = []
    seen: set[str] = set()
    sequence = ""
    for number, line in enumerate(block.split("\n"), start=2):
        where = f"{name} line {number}"
        if "\t" in line:
            faults.append(f"{where}: a tab is not indentation two parsers agree about")
            continue
        indent = len(line) - len(line.lstrip(" "))
        rest = line[indent:]

        if indent == 0:
            sequence = ""
            key, separator, value = rest.partition(": ")
            if not separator:
                if not rest.endswith(":") or len(rest) < 2:
                    faults.append(f"{where}: is not `key: value`")
                    continue
                key, value = rest[:-1], ""
            if not OKF_KEY.match(key):
                faults.append(f"{where}: {key!r} is not a key")
                continue
            if key in seen:
                # Which of the two a parser keeps is a property of the parser,
                # which is exactly why this refuses. `document.frontmatter`
                # holds the same line for the same reason.
                faults.append(f"{where}: {key} is stated twice")
            seen.add(key)
            if not value:
                sequence = key
                continue
            fault = _value(value)
            if fault:
                faults.append(f"{where}: {key} {fault}")
            continue

        if not sequence:
            faults.append(f"{where}: is indented under no block sequence")
            continue
        if indent == 2:
            if not rest.startswith("- "):
                faults.append(f"{where}: is indented two spaces and opens no sequence entry")
                continue
            rest = rest[2:]
        elif indent != 4:
            faults.append(f"{where}: is indented {indent} spaces, and this bundle uses 0, 2 or 4")
            continue
        elif rest.startswith("- "):
            faults.append(f"{where}: opens a sequence entry four spaces in")
            continue
        key, separator, value = rest.partition(": ")
        if not separator:
            faults.append(f"{where}: is not `key: value`")
            continue
        if not OKF_KEY.match(key):
            faults.append(f"{where}: {key!r} is not a key")
            continue
        fault = _value(value)
        if fault:
            faults.append(f"{where}: {key} {fault}")
    return tuple(faults)


#: Section 9: a log is a flat list of date-grouped entries, newest first, and
#: the date heading is ISO 8601 `YYYY-MM-DD`.
LOG_DATE = re.compile(r"^## (\d{4}-\d{2}-\d{2})$", re.MULTILINE)


def validate(files: Mapping[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What makes this bundle non-conforming, and what only makes it worse.

    Two tuples, because they carry two different powers.

    `faults` is section 11 and nothing else: every non-reserved `.md` holds a
    parseable frontmatter block, every block carries a non-empty `type`, and
    the two reserved names keep the structure of sections 8 and 9. A consumer
    may refuse a bundle over one of those.

    `advisories` is everything else this bundle is held to -- the actor
    spelling, the lifecycle family, the absolute instant, a link that lands, a
    root index at all, `okf_version` on it when it is there, and a footnote and
    its source finding each other. The specification is explicit that a consumer "MUST NOT
    reject documents with unrecognized fields", and the module docstring above
    says the same: every constraint past the three is soft guidance. Returning
    them separately is what stops this gate from refusing a conforming bundle
    over a rule the format never made.

    Soft does not mean unwatched. `tests/test_okf.py` demands both tuples
    empty, because a rule nobody enforces is a rule that rots quietly.
    """
    faults: list[str] = []
    advisories: list[str] = []

    if "index.md" not in files:
        # Section 8 says an index "MAY appear in any directory, including the
        # bundle root". A missing one is a bundle that discloses less, not a
        # bundle that fails.
        advisories.append("the bundle has no root index.md")
    else:
        # Section 12 lists `okf_version` among the fields a root index MAY
        # carry, and section 11's three hard rules do not ask for it. A bundle
        # that omits it is one a consumer cannot version-check, which is worth
        # reporting and is not a conformance failure.
        front = _frontmatter(files["index.md"])
        if front is None or front.get("okf_version") != f'"{OKF_VERSION}"':
            advisories.append(f'root index.md does not declare okf_version: "{OKF_VERSION}"')

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
            # Section 9, quoted: "Log files carry no frontmatter." A block here
            # would be a concept wearing a reserved name.
            if front is not None:
                faults.append(f"{name}: the reserved log carries a frontmatter block")
            dates = LOG_DATE.findall(text)
            if not dates:
                faults.append(f"{name}: the reserved log carries no ISO 8601 date heading")
            elif dates != sorted(dates, reverse=True):
                faults.append(f"{name}: the reserved log is not newest first")
            continue

        if front is None:
            faults.append(f"{name}: no parseable frontmatter block")
            continue
        # Rule one of section 11 in full. `_frontmatter` proves a block is
        # *there*; only the grammar proves it *parses*, and the two are not the
        # same question.
        faults.extend(frontmatter_faults(name, text))
        if not front.get("type"):
            faults.append(f"{name}: no non-empty type, which is the one required key")
            continue

        generated = front.get("generated", "")
        actor = generated.partition("by:")[2].partition(",")[0].strip()
        if not actor:
            advisories.append(f"{name}: generated carries no actor")
        elif not ACTOR_FORM.match(actor):
            advisories.append(f"{name}: {actor!r} is not an OKF actor spelling")

        status = front.get("status", "")
        if status not in ("draft", "stable", "deprecated"):
            advisories.append(f"{name}: status {status!r} is outside the lifecycle family")
        stale = front.get("stale_after", "")
        if not stale.endswith("Z") or "T" not in stale:
            advisories.append(f"{name}: stale_after {stale!r} is not an absolute instant")

        body = text[text.find(f"\n{FENCE}\n", len(FENCE)) + len(FENCE) + 2 :]
        declared = set(SOURCE_ID.findall(text[: text.find(f"\n{FENCE}\n", len(FENCE))]))
        defined = set(FOOTNOTE_DEF.findall(body))
        used = set(FOOTNOTE_USE.findall(body)) - defined
        # Both directions. A footnote with no source is an attribution pointing
        # at nothing; a source no claim cites is a citation nobody made. Both
        # are defects in this bundle and neither is one of section 11's three
        # rules, so they are reported and do not decide conformance -- the
        # repository's own test still holds this list empty.
        for orphan in sorted(used - declared):
            advisories.append(f"{name}: footnote [^{orphan}] matches no sources[].id")
        for unused in sorted(declared - defined):
            advisories.append(f"{name}: source id {unused} is declared and never cited")

        for target in LINK.findall(text):
            if target.lstrip("/") not in files:
                advisories.append(f"{name}: bundle-relative link {target} resolves to nothing")

    return tuple(faults), tuple(advisories)
