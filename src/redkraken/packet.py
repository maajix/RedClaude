"""The bounded Program-scoped packet an Agent child reads its world from.

Spec section 11: a mission packet is "compiled from canonical rows for one
Task", carries "revisions, digests and omission markers", and obeys "a
configured serialized byte and estimated-token ceiling". This module is both
halves of that sentence -- the compile that runs on the runtime's `rk2_state`
connection, and the reader the child answers its five state tools from.

It is two halves because the boundary makes it two. `isolation.py` gives the
child one internal network whose only peer is the capability proxy, so there is
no route to PostgreSQL and no route to the Artifact store: a handler inside the
container cannot query anything. What crosses is one JSON document on stdin,
compiled before the container starts. Migration 0020 says the same thing from
the other side -- "the runtime compiles the packet and the runtime writes the
staging rows" -- and this module is where that sentence becomes code.

So the bounds are compile-time facts, not handler-time promises. A row that did
not fit is a row the child cannot serve however it is asked, which is the point:
truncation that the model could argue its way past would not be a bound. What
the model gets instead is the subtraction, stated -- how many rows the Program
holds, how many were staged, how many matched, how many came back.

Digests come from SQL, never from Python. `v_records` already defines a record's
digest as `sha256(record::text)` and an agent that cites one has to be able to
have it re-checked against the database later; a second implementation of the
same hash in Python would be a second answer to that check.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from . import pg

#: The sections a packet carries, in the order a reader meets them. One per
#: state read tool except `get_artifact`, which reads the same `artifacts`
#: section `get_receipts` cites into.
SECTIONS = ("surface", "hypotheses", "evidence", "receipts", "artifacts")

#: The three sections that are a projection of `v_records`, and the kind each
#: one selects. The other two are shapes no single kind has: an evidence edge is
#: an edge rather than a record, and an Artifact is a reference to bytes the
#: store holds under a hash rather than a canonical row.
RECORD_KINDS = {"surface": "entity", "hypotheses": "hypothesis", "receipts": "receipt"}

#: How many bytes of a serialized packet one token is worth. Four is the usual
#: English-text approximation and it is an approximation here too: the ceiling
#: this feeds is a guard against a packet that would crowd out the objective,
#: not an accounting of what the provider will bill.
BYTES_PER_TOKEN = 4

DEFAULT_ROWS = 50
DEFAULT_BYTES = 65536
DEFAULT_TOKENS = 8192
DEFAULT_EXCERPT = 4096
DEFAULT_PAGE = 25

#: Content types whose bytes are worth putting in a context window at all. An
#: Artifact outside this set is staged as metadata and the child is told the
#: bytes were not staged, rather than being handed a screenful of replacement
#: characters that reads like a truncated document.
TEXTUAL = (
    "text/",
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/x-www-form-urlencoded",
)


class PacketError(ValueError):
    """A packet document that is not one. Raised at the boundary, not below it."""


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Limits:
    """What a compile is allowed to spend, from the caller rather than from here.

    Two ceilings because the Spec names two, and they are not the same ceiling:
    bytes bound what crosses the process boundary, tokens bound what crowds the
    objective out of the child's first turn. Whichever is smaller is the one
    that binds, which is what `byte_ceiling` is for -- a compile that honoured
    only the larger would satisfy the configuration and not the sentence.
    """

    rows: int = DEFAULT_ROWS
    byte_limit: int = DEFAULT_BYTES
    token_limit: int = DEFAULT_TOKENS
    excerpt: int = DEFAULT_EXCERPT

    @property
    def byte_ceiling(self) -> int:
        return min(self.byte_limit, self.token_limit * BYTES_PER_TOKEN)

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "bytes": self.byte_limit,
            "tokens": self.token_limit,
            "excerpt": self.excerpt,
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> Limits:
        return cls(
            rows=int(document.get("rows", DEFAULT_ROWS)),
            byte_limit=int(document.get("bytes", DEFAULT_BYTES)),
            token_limit=int(document.get("tokens", DEFAULT_TOKENS)),
            excerpt=int(document.get("excerpt", DEFAULT_EXCERPT)),
        )


@dataclass(frozen=True, slots=True)
class Row:
    """One staged row: what it is called, whether it moved, and what it says.

    `revision` is `rk2_revision()`, the highest Event sequence touching the row,
    and it is 0 for the two shapes that have none of their own -- an evidence
    edge, and an Artifact reference, which is written once and never edited.
    Zero rather than absent, because a reader comparing revisions should not
    have to branch on a missing key.
    """

    section: str
    label: str
    revision: int
    digest: str
    record: Mapping[str, Any]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "revision": self.revision,
            "digest": self.digest,
            "record": dict(self.record),
        }

    @classmethod
    def from_dict(cls, section: str, document: Mapping[str, Any]) -> Row:
        return cls(
            section=section,
            label=str(document["label"]),
            revision=int(document["revision"]),
            digest=str(document["digest"]),
            record=dict(document["record"]),
        )


@dataclass(frozen=True, slots=True)
class Section:
    """One section, and the count it was cut down from.

    `total` is what the Program holds, measured on the same connection in the
    same compile. It is the only number here the packet cannot recompute, and
    it is the number every omission marker is a subtraction from.
    """

    name: str
    total: int
    rows: tuple[Row, ...] = ()

    def as_dict(self) -> dict:
        return {"total": self.total, "rows": [row.as_dict() for row in self.rows]}

    @classmethod
    def from_dict(cls, name: str, document: Mapping[str, Any]) -> Section:
        return cls(
            name=name,
            total=int(document["total"]),
            rows=tuple(Row.from_dict(name, row) for row in document["rows"]),
        )


@dataclass(frozen=True, slots=True)
class Packet:
    """Everything one Agent child may read, as one document.

    `revision` is the Program's high-water Event sequence at compile time. It
    is on every response the child gives, so a promotion step reading a claim
    the child made can ask whether the state it was made against still holds.
    """

    revision: int = 0
    limits: Limits = field(default_factory=Limits)
    sections: Mapping[str, Section] = field(default_factory=dict)
    excerpts: Mapping[str, str] = field(default_factory=dict)

    def section(self, name: str) -> Section:
        return self.sections.get(name) or Section(name=name, total=0)

    @property
    def bytes(self) -> int:
        return _size(self.rows())

    def rows(self) -> list[Row]:
        return [row for name in SECTIONS for row in self.section(name).rows]

    def as_dict(self) -> dict:
        return {
            "revision": self.revision,
            "limits": self.limits.as_dict(),
            "sections": {
                name: self.section(name).as_dict()
                for name in SECTIONS
                if name in self.sections
            },
            "excerpts": dict(self.excerpts),
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> Packet:
        """Rebuild a packet inside the child, refusing anything that is not one.

        The child is the side that cannot check anything else: it has no
        database to compare against and no second copy to diff. So the one
        thing it does check is that the document has the shape it will index
        into, and a malformed packet is a startup refusal rather than a
        `KeyError` in the middle of the model's third turn.
        """
        try:
            sections = {
                name: Section.from_dict(name, body)
                for name, body in dict(document.get("sections", {})).items()
                if name in SECTIONS
            }
            return cls(
                revision=int(document.get("revision", 0)),
                limits=Limits.from_dict(dict(document.get("limits", {}))),
                sections=sections,
                excerpts={
                    str(key): str(value)
                    for key, value in dict(document.get("excerpts", {})).items()
                },
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise PacketError(f"not a packet: {error}") from error


# ---------------------------------------------------------------------------
# The bound
# ---------------------------------------------------------------------------


def fit[T](
    items: Sequence[T],
    *,
    byte_limit: int,
    group: Callable[[T], str],
    size: Callable[[Sequence[T]], int],
) -> list[T]:
    """Fit the items under the byte ceiling, dropping the stalest first.

    Which item goes matters. Spending the whole ceiling on the first group
    would answer with a Program that has entities and no findings, which is a
    claim rather than an omission -- so each drop comes from whichever group is
    currently largest, and within a group from the tail, which is the end the
    caller ordered as least recently changed.

    The tie between two equally large groups is broken on the group's name, so
    two compiles of the same state drop the same rows. A packet that varied
    would make a rerun of the same Task a different Task.
    """
    remaining = list(items)
    while remaining and size(remaining) > byte_limit:
        held = Counter(group(item) for item in remaining)
        crowded = max(held.items(), key=lambda item: (item[1], item[0]))[0]
        for index in range(len(remaining) - 1, -1, -1):
            if group(remaining[index]) == crowded:
                del remaining[index]
                break
    return remaining


def _size(rows: Sequence[Row]) -> int:
    """What the rows cost, measured the way they will be sent.

    Nothing costs nothing, rather than the two bytes an empty array is written
    in. `fit` stops when it has nothing left to drop, so counting the framing
    would let a compile report a size over a ceiling it could not have met.
    """
    if not rows:
        return 0
    return len(
        json.dumps([row.as_dict() for row in rows], separators=(",", ":")).encode("utf-8")
    )


def bound(sections: Mapping[str, Section], *, byte_limit: int) -> dict[str, Section]:
    """Apply the packet's byte ceiling across every section at once.

    Across, not within: a per-section ceiling would let five sections that each
    fit add up to a packet that does not, and the ceiling the Spec names is on
    the packet.
    """
    kept = fit(
        [row for name in SECTIONS for row in sections.get(name, Section(name, 0)).rows],
        byte_limit=byte_limit,
        group=lambda row: row.section,
        size=_size,
    )
    held: dict[str, list[Row]] = {name: [] for name in sections}
    for row in kept:
        held[row.section].append(row)
    return {
        name: replace(section, rows=tuple(held.get(name, ())))
        for name, section in sections.items()
    }


# ---------------------------------------------------------------------------
# The compile
# ---------------------------------------------------------------------------

#: The Program's high-water Event sequence. `events` is readable by `rk2_state`
#: for exactly this reason -- it is what `rk2_revision()` is built from -- and
#: row level security scopes it to the session's Program like everything else.
REVISION = "SELECT coalesce(max(seq), 0) FROM events"

RECORDS = (
    "SELECT label, revision, digest, record"
    "  FROM (SELECT label, revision, digest, record,"
    "               row_number() OVER (ORDER BY revision DESC, label) AS rank"
    "          FROM v_records WHERE kind = $1) ranked"
    " WHERE rank <= $2 ORDER BY rank"
)

RECORD_COUNT = "SELECT count(*) FROM v_records WHERE kind = $1"

#: An evidence edge, built into the same `{record, digest}` shape `v_records`
#: gives everything else so that one Python path can carry all five sections.
#: The observation's `rk2_revision` comes along because the edge has none of
#: its own and "how stale is this" is a question about the observation.
EVIDENCE = (
    "SELECT ev.observation_label,"
    "       coalesce(rk2_revision('observations', o.id), 0) AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM v_evidence ev"
    "  LEFT JOIN observations o ON o.label = ev.observation_label"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'evidence',"
    "           'hypothesis_label', ev.hypothesis_label,"
    "           'finding_label', ev.finding_label,"
    "           'observation_label', ev.observation_label,"
    "           'polarity', ev.polarity,"
    "           'role', ev.role,"
    "           'observation_kind', ev.kind,"
    "           'summary', ev.summary,"
    "           'provenance_kind', ev.provenance_kind,"
    "           'receipt_label', ev.receipt_label,"
    "           'tool_run_label', ev.tool_run_label)) AS built(rec)"
    " ORDER BY revision DESC, ev.observation_label, ev.hypothesis_label NULLS LAST,"
    "          ev.finding_label NULLS LAST"
    " LIMIT $1"
)

EVIDENCE_COUNT = "SELECT count(*) FROM v_evidence"

#: The reachable Artifacts. Reachability is not a clause here: `v_artifacts` is
#: the Program's own references joined to the bytes they name, and row level
#: security on `artifact_references` admits only this Program's. A `WHERE`
#: repeating that would be a second, weaker copy of the policy.
#:
#: Keyed by label, like every other section, and that is ticket 06's rule rather
#: than a symmetry: "the hash is reported and is never an argument: a verb
#: taking one would read across Programs whenever the caller could guess the
#: bytes". The hash is in the record because a caller that already holds bytes
#: can check them against it; it is not the handle anything is fetched by.
ARTIFACTS = (
    "SELECT va.label,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM v_artifacts va"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'artifact',"
    "           'label', va.label,"
    "           'artifact_kind', va.kind,"
    "           'sha256', va.sha256,"
    "           'byte_size', va.byte_size,"
    "           'content_type', va.content_type,"
    "           'created_at', va.created_at)) AS built(rec)"
    " ORDER BY va.byte_size, va.label"
    " LIMIT $1"
)

ARTIFACT_COUNT = "SELECT count(*) FROM v_artifacts"


def compile(
    connection: pg.Connection,
    *,
    limits: Limits | None = None,
    load: Callable[[str], bytes | None] | None = None,
) -> Packet:
    """Compile one Program's packet on an agent-scoped connection.

    The connection is the whole scope. No Program identifier is passed, none is
    accepted, and none appears in any query: `rk2_state` sees one Program's rows
    because row level security says so, and a compile that took a Program would
    be a second opinion about which one -- the exact thing ticket 05 removed.
    """
    limits = limits or Limits()
    sections: dict[str, Section] = {}
    for name, kind in RECORD_KINDS.items():
        sections[name] = _records(connection, name, kind, limits.rows)
    sections["evidence"] = _evidence(connection, limits.rows)
    sections["artifacts"] = _artifacts(connection, limits.rows)
    kept = bound(sections, byte_limit=limits.byte_ceiling)
    return Packet(
        revision=int(connection.execute(REVISION).rows[0][0]),
        limits=limits,
        sections={name: kept[name] for name in SECTIONS},
        excerpts=_excerpts(kept["artifacts"], limits.excerpt, load),
    )


def _records(connection: pg.Connection, name: str, kind: str, rows: int) -> Section:
    staged = tuple(
        Row(
            section=name,
            label=str(label),
            revision=int(revision),
            digest=str(digest),
            record=json.loads(str(record)),
        )
        for label, revision, digest, record in connection.execute(RECORDS, (kind, rows)).rows
    )
    total = int(connection.execute(RECORD_COUNT, (kind,)).rows[0][0])
    return Section(name=name, total=total, rows=staged)


def _evidence(connection: pg.Connection, rows: int) -> Section:
    staged = tuple(
        Row(
            section="evidence",
            label=str(label),
            revision=int(revision),
            digest=str(digest),
            record=json.loads(str(record)),
        )
        for label, revision, digest, record in connection.execute(EVIDENCE, (rows,)).rows
    )
    total = int(connection.execute(EVIDENCE_COUNT).rows[0][0])
    return Section(name="evidence", total=total, rows=staged)


def _artifacts(connection: pg.Connection, rows: int) -> Section:
    """The Artifact section, whose rows have no revision of their own.

    Revision 0 rather than a lookup: an `artifact_references` row is written
    once and never edited, and the event log carries no entry for it, so
    `rk2_revision` would answer 0 for every one of them anyway. Saying 0
    directly is the same answer without the query that suggests otherwise.
    """
    staged = tuple(
        Row(
            section="artifacts",
            label=str(label),
            revision=0,
            digest=str(digest),
            record=json.loads(str(record)),
        )
        for label, digest, record in connection.execute(ARTIFACTS, (rows,)).rows
    )
    total = int(connection.execute(ARTIFACT_COUNT).rows[0][0])
    return Section(name="artifacts", total=total, rows=staged)


def _excerpts(
    artifacts: Section, ceiling: int, load: Callable[[str], bytes | None] | None
) -> dict[str, str]:
    """Stage the readable head of each Artifact, or stage nothing for it.

    Nothing is the honest answer more often than it looks. The child has no
    route to the Artifact store, so an Artifact whose head is not here is one
    whose bytes it cannot obtain at all -- and the whole blob is deliberately
    not here either. Analysing megabytes is `exec.tool_run`'s job, where the
    output is a row rather than a context window.

    Loaded by hash and keyed by label: the store is content-addressed and the
    runtime compiling the packet is the side that may address it that way, which
    is exactly the asymmetry ticket 06 asked for.
    """
    if load is None:
        return {}
    excerpts: dict[str, str] = {}
    for row in artifacts.rows:
        if not _textual(str(row.record.get("content_type") or "")):
            continue
        sha256 = str(row.record.get("sha256") or "")
        blob = load(sha256) if sha256 else None
        if blob is None:
            continue
        head = _decodable(blob[:ceiling])
        if head is not None:
            excerpts[row.label] = head
    return excerpts


def _textual(content_type: str) -> bool:
    lowered = content_type.split(";")[0].strip().lower()
    return any(lowered.startswith(prefix) for prefix in TEXTUAL)


def _decodable(head: bytes) -> str | None:
    """The head as text, having backed off a character the cut ran through.

    A ceiling lands where it lands, and UTF-8 characters are up to four bytes
    wide, so the last one can be half here. Three bytes of back-off covers
    every such cut; a head that still does not decode was not text.
    """
    for trim in range(4):
        candidate = head[: len(head) - trim] if trim else head
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Answer:
    """One bounded response, with the subtraction that produced it.

    `counts` is four numbers rather than one because the rows that are missing
    went missing in two different places, and a single "omitted" would hide
    which. `total` is what the Program holds, `staged` is what survived the
    compile, `matched` is what the caller's filter selected out of that, and
    `returned` is what the page carried. Each `omitted` marker names one of the
    two gaps, so a caller can tell "there is more" from "there is more and this
    packet never had it".
    """

    section: str
    revision: int
    rows: tuple[Row, ...]
    total: int
    staged: int
    matched: int
    omitted: tuple[Mapping[str, Any], ...] = ()

    def as_dict(self) -> dict:
        return {
            "section": self.section,
            "revision": self.revision,
            "counts": {
                "total": self.total,
                "staged": self.staged,
                "matched": self.matched,
                "returned": len(self.rows),
            },
            "records": [row.as_dict() for row in self.rows],
            "omitted": [dict(marker) for marker in self.omitted],
        }


class Reader:
    """The five state reads, answered from the packet and from nothing else."""

    def __init__(self, packet: Packet, *, page: int = DEFAULT_PAGE) -> None:
        self.packet = packet
        self.page = page

    # -- the tools ----------------------------------------------------------

    def attack_surface(self, *, entity_type: str | None = None, limit: int | None = None) -> dict:
        return self._page(
            "surface",
            limit,
            lambda row: entity_type is None or row.record.get("type") == entity_type,
        ).as_dict()

    def hypotheses(
        self,
        *,
        subject_label: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> dict:
        def wanted(row: Row) -> bool:
            if subject_label is not None and row.record.get("subject_label") != subject_label:
                return False
            return status is None or row.record.get("status") == status

        return self._page("hypotheses", limit, wanted).as_dict()

    def evidence(
        self,
        *,
        hypothesis_label: str | None = None,
        finding_label: str | None = None,
        limit: int | None = None,
    ) -> dict:
        def wanted(row: Row) -> bool:
            if hypothesis_label is not None:
                if row.record.get("hypothesis_label") != hypothesis_label:
                    return False
            if finding_label is not None:
                if row.record.get("finding_label") != finding_label:
                    return False
            return True

        return self._page("evidence", limit, wanted).as_dict()

    def receipts(self, *, receipt_labels: Iterable[str]) -> dict:
        """The named Receipts, and the names that were not in the packet.

        A missing name has more than one cause and the child can distinguish
        none of them: the Receipt may not exist, may belong to another Program,
        or may be `proxy_internal` and hidden from the agent read role by
        migration 0020's restrictive policy. So the marker says what is true --
        it was not staged -- rather than guessing which.
        """
        wanted = list(dict.fromkeys(str(label) for label in receipt_labels))
        section = self.packet.section("receipts")
        held = {row.label: row for row in section.rows}
        rows = tuple(held[label] for label in wanted if label in held)
        missing = [label for label in wanted if label not in held]
        answer = Answer(
            section="receipts",
            revision=self.packet.revision,
            rows=rows,
            total=section.total,
            staged=len(section.rows),
            matched=len(wanted),
            omitted=(
                ({"reason": "not_staged", "count": len(missing), "labels": missing},)
                if missing
                else ()
            ),
        )
        return answer.as_dict()

    def artifact(self, *, artifact_label: str, span: str | None = None) -> dict:
        """One Artifact's metadata, and as much of its head as was staged.

        By label, never by hash. Migration `program_scoped_artifacts` states the
        reason on the view itself: a verb taking a hash reads across Programs
        whenever the caller can guess the bytes, and the store is one shared
        content-addressed namespace, so guessing is the attack.

        The wire name of `span` is `range`, which is a builtin; `_launch`
        renames it on the way in rather than this module shadowing one.
        """
        section = self.packet.section("artifacts")
        row = next((item for item in section.rows if item.label == artifact_label), None)
        base: dict[str, Any] = {
            "section": "artifacts",
            "revision": self.packet.revision,
            "counts": {
                "total": section.total,
                "staged": len(section.rows),
                "matched": 1 if row else 0,
                "returned": 1 if row else 0,
            },
        }
        if row is None:
            return base | {
                "records": [],
                "omitted": [{"reason": "no_such_artifact", "label": artifact_label}],
            }
        excerpt = self.packet.excerpts.get(artifact_label)
        content, markers = _window(row, excerpt, span)
        return base | {
            "records": [row.as_dict() | {"content": content}],
            "omitted": markers,
        }

    # -- the shared page ----------------------------------------------------

    def _page(self, section: str, limit: int | None, wanted: Callable[[Row], bool]) -> Answer:
        held = self.packet.section(section)
        matched = [row for row in held.rows if wanted(row)]
        size = self.page if limit is None else max(1, limit)
        rows = matched[:size]
        markers: list[Mapping[str, Any]] = []
        if held.total > len(held.rows):
            markers.append(
                {"reason": "packet_bound", "count": held.total - len(held.rows)}
            )
        if len(matched) > len(rows):
            markers.append({"reason": "limit", "count": len(matched) - len(rows)})
        return Answer(
            section=section,
            revision=self.packet.revision,
            rows=tuple(rows),
            total=held.total,
            staged=len(held.rows),
            matched=len(matched),
            omitted=tuple(markers),
        )


def _window(
    row: Row, excerpt: str | None, span: str | None
) -> tuple[str | None, list[Mapping[str, Any]]]:
    """The requested byte window of a staged excerpt, and what it did not cover.

    Byte offsets, not character offsets, because `byte_size` is the number the
    Artifact is described by and a window in some other unit would not line up
    with it. A window that cuts through a character gets the replacement
    character for it, which is what a byte range means.
    """
    size = int(row.record.get("byte_size") or 0)
    if excerpt is None:
        return None, [{"reason": "not_staged", "byte_size": size}]
    raw = excerpt.encode("utf-8")
    markers: list[Mapping[str, Any]] = []
    if len(raw) < size:
        markers.append(
            {"reason": "excerpt_only", "staged_bytes": len(raw), "byte_size": size}
        )
    if span is None:
        return excerpt, markers
    start, _, end = span.partition("-")
    first, last = int(start), int(end)
    if first >= len(raw) or last <= first:
        markers.append(
            {"reason": "range_beyond_excerpt", "staged_bytes": len(raw), "range": span}
        )
        return None, markers
    return raw[first:last].decode("utf-8", errors="replace"), markers
