"""The mission packet: what fits, what is dropped, and what the child is told.

Every seam here is pure, which is the point of the module's shape. The compile
runs on the runtime's agent-scoped connection and the reader runs inside a
container with no database at all, so the only thing joining them is a JSON
document -- and a document is testable without either side.

Three properties carry the ticket:

* the bound is a subtraction that is *stated*. Nothing here asserts that rows
  fit; it asserts that a response whose rows did not fit says so, with numbers,
  so a truncated answer cannot be read as a complete one.
* the compile takes no Program. `rk2_state` row level security decides which
  Program a connection can see, and a compile that accepted an identifier would
  be a second opinion about it. A fake connection records the SQL, so this is
  an assertion about the statements the module emits.
* a packet the child cannot index into is refused when it is read, not when it
  is used. `Packet.from_dict` is the only validation the child can perform --
  it has nothing to compare against -- so it is the place a malformed document
  has to fail.

What needs a server -- that a compile against a seeded Program returns that
Program's rows and no other's -- is in `tests/test_database.py`.
"""

from __future__ import annotations

import inspect
import json
import unittest

from redkraken import packet, pg


def row(section: str, label: str, revision: int = 1, **record) -> packet.Row:
    return packet.Row(
        section=section,
        label=label,
        revision=revision,
        digest=f"{abs(hash(label)) % (16**64):064x}",
        record={"kind": section, "label": label, **record},
    )


def entity(label: str, kind: str = "endpoint", revision: int = 1) -> packet.Row:
    return row("surface", label, revision, type=kind, in_scope=True)


def hypothesis(label: str, status: str = "open", subject: str = "EP1") -> packet.Row:
    return row("hypotheses", label, 1, status=status, subject_label=subject)


def artifact(
    label: str, sha: str, byte_size: int = 10, content_type: str = "text/plain"
) -> packet.Row:
    """One staged Artifact: labelled like every other row, and hashed as a fact.

    The two are not interchangeable here and the fixture keeps them apart on
    purpose. The label is what a read is addressed by and the hash is what the
    record reports, so a reader that had quietly gone back to fetching by hash
    would fail against this shape rather than pass against a row where both
    strings were the same one.
    """
    return packet.Row(
        section="artifacts",
        label=label,
        revision=0,
        digest=sha,
        record={
            "kind": "artifact",
            "label": label,
            "artifact_kind": "runtime",
            "sha256": sha,
            "byte_size": byte_size,
            "content_type": content_type,
        },
    )


def sections(**named: packet.Section) -> dict[str, packet.Section]:
    return dict(named)


def section(name: str, rows, total: int | None = None) -> packet.Section:
    staged = tuple(rows)
    return packet.Section(name=name, total=len(staged) if total is None else total, rows=staged)


class Recorder:
    """A connection that answers each compile query, and remembers every ask.

    Keyed on the statement rather than on a fragment of it: two of the compile's
    queries read `v_records` and differ only in what they select, so a substring
    match would answer a count with a page of rows.
    """

    def __init__(self, *, revision: int = 0, staged=None, totals=None, evidence=(),
                 artifacts=()):
        self.calls: list[tuple[str, tuple]] = []
        self.revision = revision
        self.staged = staged or {}
        self.totals = totals or {}
        self.evidence = list(evidence)
        self.artifacts = list(artifacts)

    def execute(self, sql: str, parameters: tuple = ()) -> pg.Result:
        self.calls.append((sql, parameters))
        return pg.Result(columns=(), rows=tuple(self._answer(sql, parameters)), tag="SELECT")

    def _answer(self, sql: str, parameters: tuple) -> list[tuple]:
        if sql == packet.REVISION:
            return [(self.revision,)]
        if sql == packet.RECORDS:
            kind, limit = parameters
            return [
                (item.label, item.revision, item.digest, json.dumps(item.record))
                for item in self.staged.get(kind, ())
            ][:limit]
        if sql == packet.RECORD_COUNT:
            return [(self.totals.get(parameters[0], len(self.staged.get(parameters[0], ()))),)]
        if sql == packet.EVIDENCE:
            return [
                (item.label, item.revision, item.digest, json.dumps(item.record))
                for item in self.evidence
            ][: parameters[0]]
        if sql == packet.EVIDENCE_COUNT:
            return [(self.totals.get("evidence", len(self.evidence)),)]
        if sql == packet.ARTIFACTS:
            return [
                (item.label, item.digest, json.dumps(item.record))
                for item in self.artifacts
            ][: parameters[0]]
        if sql == packet.ARTIFACT_COUNT:
            return [(self.totals.get("artifacts", len(self.artifacts)),)]
        raise AssertionError(f"the compile asked something unplanned: {sql}")


class FitTest(unittest.TestCase):
    """Which item goes first, and whether two compiles agree about it."""

    def test_everything_under_the_ceiling_is_kept_in_the_order_it_arrived(self):
        items = [entity(f"EP{n}") for n in range(5)]

        kept = packet.fit(
            items, byte_limit=packet.DEFAULT_BYTES, group=lambda item: item.section,
            size=packet._size,
        )

        self.assertEqual(items, kept)

    def test_the_drop_comes_from_the_largest_group_rather_than_from_the_front(self):
        # The failure this refutes: spending the ceiling on whatever was
        # serialized first, which answers with a Program that has entities and
        # no hypotheses. That is a claim, and the packet is not allowed to make
        # claims -- only to state subtractions.
        crowded = [entity(f"EP{n}") for n in range(6)]
        sparse = [hypothesis("H1")]
        every = crowded + sparse

        kept = packet.fit(
            every,
            byte_limit=packet._size(every) - 1,
            group=lambda item: item.section,
            size=packet._size,
        )

        self.assertIn(sparse[0], kept)
        self.assertEqual(5, sum(1 for item in kept if item.section == "surface"))

    def test_within_a_group_the_tail_goes_first(self):
        items = [entity(f"EP{n}", revision=10 - n) for n in range(4)]

        kept = packet.fit(
            items,
            byte_limit=packet._size(items) - 1,
            group=lambda item: item.section,
            size=packet._size,
        )

        self.assertEqual(items[:3], kept)

    def test_two_equally_large_groups_are_broken_on_the_group_name(self):
        # Determinism is the property, not the winner: a packet that varied
        # between two compiles of the same state would make a rerun of one Task
        # a different Task.
        items = [entity("EP1"), entity("EP2"), hypothesis("H1"), hypothesis("H2")]
        ceiling = packet._size(items) - 1

        first = packet.fit(
            items, byte_limit=ceiling, group=lambda item: item.section, size=packet._size
        )
        again = packet.fit(
            items, byte_limit=ceiling, group=lambda item: item.section, size=packet._size
        )

        self.assertEqual(first, again)
        self.assertEqual(3, len(first))

    def test_an_empty_sequence_costs_nothing_rather_than_the_framing(self):
        # `fit` stops when it has nothing left to drop, so a size that counted
        # `[]` as two bytes would let a compile report itself over a ceiling it
        # could not have met.
        self.assertEqual(0, packet._size([]))


class BoundTest(unittest.TestCase):
    """The ceiling is on the packet, and the totals survive the cut."""

    def test_the_ceiling_is_applied_across_sections_rather_than_within_each(self):
        every = [entity(f"EP{n}") for n in range(4)] + [hypothesis(f"H{n}") for n in range(4)]
        held = sections(
            surface=section("surface", every[:4]),
            hypotheses=section("hypotheses", every[4:]),
        )

        kept = packet.bound(held, byte_limit=packet._size(every) // 2)

        staged = sum(len(item.rows) for item in kept.values())
        self.assertLess(staged, 8)
        self.assertLessEqual(packet._size([r for s in kept.values() for r in s.rows]),
                             packet._size(every) // 2)

    def test_what_the_program_holds_is_not_reduced_by_the_cut(self):
        # The total is the number every omission marker is a subtraction from,
        # so a bound that lowered it would erase the evidence that it cut.
        held = sections(surface=section("surface", [entity(f"EP{n}") for n in range(4)], total=99))

        kept = packet.bound(held, byte_limit=1)

        self.assertEqual(99, kept["surface"].total)
        self.assertEqual((), kept["surface"].rows)


class PacketDocumentTest(unittest.TestCase):
    """What crosses the process boundary, and what the child refuses to read."""

    def document(self) -> packet.Packet:
        return packet.Packet(
            revision=17,
            limits=packet.Limits(rows=5, byte_limit=100, token_limit=10, excerpt=64),
            sections=sections(
                surface=section("surface", [entity("EP1")], total=3),
                artifacts=section("artifacts", [artifact("AF1", "a" * 64)]),
            ),
            excerpts={"AF1": "hello"},
        )

    def test_a_packet_survives_the_round_trip_it_is_sent_through(self):
        original = self.document()

        again = packet.Packet.from_dict(json.loads(json.dumps(original.as_dict())))

        self.assertEqual(original.as_dict(), again.as_dict())
        self.assertEqual(17, again.revision)
        self.assertEqual(3, again.section("surface").total)
        self.assertEqual("hello", again.excerpts["AF1"])

    def test_the_smaller_of_the_two_ceilings_is_the_one_that_binds(self):
        # A compile honouring only the larger would satisfy the configuration
        # and not the sentence the configuration comes from.
        self.assertEqual(40, packet.Limits(byte_limit=100, token_limit=10).byte_ceiling)
        self.assertEqual(100, packet.Limits(byte_limit=100, token_limit=1000).byte_ceiling)

    def test_a_section_the_packet_never_carried_reads_as_empty_rather_than_missing(self):
        empty = packet.Packet().section("receipts")

        self.assertEqual(0, empty.total)
        self.assertEqual((), empty.rows)

    def test_a_document_that_is_not_a_packet_is_refused_where_it_is_read(self):
        malformed = {
            "no rows": {"sections": {"surface": {"total": 1}}},
            "no total": {"sections": {"surface": {"rows": []}}},
            "no digest": {
                "sections": {
                    "surface": {"total": 1, "rows": [{"label": "EP1", "revision": 1,
                                                      "record": {}}]}
                }
            },
            "a revision that is not one": {"revision": "recent"},
            "a section that is not a mapping": {"sections": {"surface": ["EP1"]}},
            "limits that are not numbers": {"limits": {"rows": "plenty"}},
        }

        for fault, document in malformed.items():
            with self.subTest(fault=fault):
                with self.assertRaises(packet.PacketError):
                    packet.Packet.from_dict(document)

    def test_a_section_name_the_reader_has_no_tool_for_is_dropped_rather_than_served(self):
        again = packet.Packet.from_dict(
            {"sections": {"surface": {"total": 0, "rows": []},
                          "credentials": {"total": 1, "rows": []}}}
        )

        self.assertEqual(["surface"], sorted(again.sections))


class CompileTest(unittest.TestCase):
    """What the compile asks the database, and what it never asks it."""

    def connection(self, **overrides) -> Recorder:
        fields = {
            "revision": 42,
            "staged": {
                "entity": [entity(f"EP{n}") for n in range(3)],
                "hypothesis": [hypothesis("H1")],
                "receipt": [row("receipts", "R1")],
            },
            "totals": {"entity": 9, "hypothesis": 1, "receipt": 1},
            "evidence": [row("evidence", "OB1", hypothesis_label="H1")],
            "artifacts": [artifact("AF2", "b" * 64)],
        }
        fields.update(overrides)
        return Recorder(**fields)

    def test_the_compiled_packet_carries_every_section_and_the_program_revision(self):
        compiled = packet.compile(self.connection())

        self.assertEqual(42, compiled.revision)
        self.assertEqual(list(packet.SECTIONS), list(compiled.sections))
        self.assertEqual(9, compiled.section("surface").total)
        self.assertEqual(3, len(compiled.section("surface").rows))
        self.assertEqual(("OB1",), tuple(r.label for r in compiled.section("evidence").rows))

    def test_no_statement_and_no_parameter_carries_a_program(self):
        # Ticket 05's property, restated for the packet: the connection is the
        # scope. A compile that took a Program would be able to disagree with
        # the row level security that already decided which one this is.
        recorder = self.connection()

        packet.compile(recorder)

        self.assertNotIn("program", str(inspect.signature(packet.compile)))
        for sql, parameters in recorder.calls:
            with self.subTest(sql=sql[:40]):
                self.assertNotIn("program", sql.lower())
                self.assertNotIn("program_id", [str(item) for item in parameters])

    def test_the_row_limit_is_sent_to_the_database_rather_than_applied_after(self):
        recorder = self.connection()

        packet.compile(recorder, limits=packet.Limits(rows=2))

        pages = [parameters for sql, parameters in recorder.calls if sql == packet.RECORDS]
        self.assertEqual([("entity", 2), ("hypothesis", 2), ("receipt", 2)], pages)
        self.assertEqual(2, len(packet.compile(recorder, limits=packet.Limits(rows=2))
                                .section("surface").rows))

    def test_a_compile_with_no_loader_stages_metadata_and_no_bytes(self):
        # The child has no route to the Artifact store, so an absent loader is
        # not a degraded compile -- it is the compile saying the bytes are not
        # obtainable, which the reader then reports as `not_staged`.
        compiled = packet.compile(self.connection())

        self.assertEqual({}, dict(compiled.excerpts))
        self.assertEqual(1, len(compiled.section("artifacts").rows))

    def test_only_artifacts_worth_reading_as_text_have_a_head_staged(self):
        blobs = {"b" * 64: b"readable", "c" * 64: b"\x00\x01\x02\x03"}
        recorder = self.connection(
            artifacts=[
                artifact("AF2", "b" * 64, byte_size=8),
                artifact("AF3", "c" * 64, byte_size=4,
                         content_type="application/octet-stream"),
            ]
        )

        compiled = packet.compile(recorder, load=blobs.get)

        self.assertEqual({"AF2": "readable"}, dict(compiled.excerpts))

    def test_a_head_cut_through_a_character_is_backed_off_rather_than_dropped(self):
        blobs = {"b" * 64: "aä".encode("utf-8")}
        recorder = self.connection(artifacts=[artifact("AF2", "b" * 64, byte_size=3)])

        compiled = packet.compile(
            recorder, limits=packet.Limits(excerpt=2), load=blobs.get
        )

        self.assertEqual("a", compiled.excerpts["AF2"])

    def test_an_artifact_the_store_no_longer_has_stages_no_head(self):
        recorder = self.connection(artifacts=[artifact("AF2", "b" * 64)])

        compiled = packet.compile(recorder, load=lambda _: None)

        self.assertEqual({}, dict(compiled.excerpts))

    def test_the_byte_ceiling_cuts_the_compiled_packet(self):
        recorder = self.connection(
            staged={"entity": [entity(f"EP{n}") for n in range(20)], "hypothesis": [],
                    "receipt": []},
            totals={"entity": 20, "hypothesis": 0, "receipt": 0},
            evidence=[],
            artifacts=[],
        )

        compiled = packet.compile(recorder, limits=packet.Limits(rows=20, byte_limit=400))

        self.assertLess(len(compiled.section("surface").rows), 20)
        self.assertEqual(20, compiled.section("surface").total)
        self.assertLessEqual(compiled.bytes, 400)


class ReaderTest(unittest.TestCase):
    """The five reads, answered from the document and from nothing else."""

    def reader(self, **overrides) -> packet.Reader:
        held = sections(
            surface=section(
                "surface",
                [entity("EP1"), entity("EP2"), entity("HST1", kind="host")],
                total=12,
            ),
            hypotheses=section(
                "hypotheses",
                [
                    hypothesis("H1", status="open", subject="EP1"),
                    hypothesis("H2", status="validated", subject="EP1"),
                    hypothesis("H3", status="open", subject="HST1"),
                ],
            ),
            evidence=section(
                "evidence",
                [
                    row("evidence", "OB1", hypothesis_label="H1", finding_label=None),
                    row("evidence", "OB2", hypothesis_label=None, finding_label="F1"),
                ],
            ),
            receipts=section("receipts", [row("receipts", "R1"), row("receipts", "R2")], total=8),
            artifacts=section("artifacts", [artifact("AF1", "a" * 64, byte_size=11)]),
        )
        document = packet.Packet(
            revision=7, sections=held, excerpts={"AF1": "hello world"}
        )
        return packet.Reader(document, **overrides)

    # -- the counts ---------------------------------------------------------

    def test_every_answer_carries_the_revision_it_was_compiled_against(self):
        for answer in (
            self.reader().attack_surface(),
            self.reader().hypotheses(),
            self.reader().evidence(),
            self.reader().receipts(receipt_labels=["R1"]),
            self.reader().artifact(artifact_label="AF1"),
        ):
            with self.subTest(section=answer["section"]):
                self.assertEqual(7, answer["revision"])

    def test_rows_the_program_holds_that_the_packet_never_had_are_marked(self):
        answer = self.reader().attack_surface()

        self.assertEqual(
            {"total": 12, "staged": 3, "matched": 3, "returned": 3}, answer["counts"]
        )
        self.assertEqual([{"reason": "packet_bound", "count": 9}], answer["omitted"])

    def test_the_page_and_the_packet_are_two_different_omissions(self):
        # One number would hide which: "there is more" and "there is more and
        # this packet never had it" are answered differently by a caller.
        answer = self.reader().attack_surface(limit=1)

        self.assertEqual(1, answer["counts"]["returned"])
        self.assertEqual(
            [{"reason": "packet_bound", "count": 9}, {"reason": "limit", "count": 2}],
            answer["omitted"],
        )

    def test_a_section_that_was_staged_whole_is_marked_with_nothing(self):
        answer = self.reader().hypotheses()

        self.assertEqual([], answer["omitted"])
        self.assertEqual(3, answer["counts"]["total"])

    def test_the_default_page_bounds_a_read_that_asked_for_no_limit(self):
        small = self.reader(page=2)

        answer = small.attack_surface()

        self.assertEqual(2, answer["counts"]["returned"])
        self.assertIn({"reason": "limit", "count": 1}, answer["omitted"])

    # -- the filters --------------------------------------------------------

    def test_the_surface_can_be_narrowed_to_one_entity_type(self):
        answer = self.reader().attack_surface(entity_type="host")

        self.assertEqual(["HST1"], [item["label"] for item in answer["records"]])
        self.assertEqual(3, answer["counts"]["staged"])
        self.assertEqual(1, answer["counts"]["matched"])

    def test_hypotheses_can_be_narrowed_by_subject_and_by_status_together(self):
        every = self.reader()

        self.assertEqual(
            ["H1", "H2"],
            [item["label"] for item in every.hypotheses(subject_label="EP1")["records"]],
        )
        self.assertEqual(
            ["H1", "H3"],
            [item["label"] for item in every.hypotheses(status="open")["records"]],
        )
        self.assertEqual(
            ["H1"],
            [
                item["label"]
                for item in every.hypotheses(subject_label="EP1", status="open")["records"]
            ],
        )

    def test_evidence_is_narrowed_by_the_hypothesis_or_the_finding_it_ties_to(self):
        every = self.reader()

        self.assertEqual(
            ["OB1"],
            [item["label"] for item in every.evidence(hypothesis_label="H1")["records"]],
        )
        self.assertEqual(
            ["OB2"],
            [item["label"] for item in every.evidence(finding_label="F1")["records"]],
        )

    def test_a_filter_that_matches_nothing_is_an_empty_answer_and_not_an_error(self):
        answer = self.reader().hypotheses(status="refuted")

        self.assertEqual([], answer["records"])
        self.assertEqual(0, answer["counts"]["matched"])

    # -- the receipts -------------------------------------------------------

    def test_asking_for_no_receipts_lists_the_ones_this_packet_reached(self):
        # The same reason `artifact()` lists: a Receipt label is cited by an
        # Observation's provenance, and a child that cannot see which labels
        # the packet holds can only cite one it guessed.
        answer = self.reader().receipts()

        self.assertEqual("receipts", answer["section"])
        self.assertEqual(["R1", "R2"], [item["label"] for item in answer["records"]])
        self.assertEqual(2, answer["counts"]["matched"])

    def test_the_receipt_list_is_paged_by_the_limit_it_was_given(self):
        answer = self.reader().receipts(limit=1)

        self.assertEqual(["R1"], [item["label"] for item in answer["records"]])
        self.assertIn({"reason": "limit", "count": 1}, answer["omitted"])

    def test_named_receipts_come_back_and_the_names_that_did_not_are_listed(self):
        answer = self.reader().receipts(receipt_labels=["R1", "R99"])

        self.assertEqual(["R1"], [item["label"] for item in answer["records"]])
        self.assertEqual(
            [
                {"reason": "packet_bound", "count": 6},
                {"reason": "not_staged", "count": 1, "labels": ["R99"]},
            ],
            answer["omitted"],
        )

    def test_a_receipt_named_twice_is_answered_once(self):
        answer = self.reader().receipts(receipt_labels=["R1", "R1", "R2"])

        self.assertEqual(["R1", "R2"], [item["label"] for item in answer["records"]])
        self.assertEqual(2, answer["counts"]["matched"])

    def test_matched_counts_the_named_receipts_the_packet_holds_not_the_names(self):
        # `matched` is what the filter selected out of what was staged, so it
        # cannot exceed `staged`: a number above it would claim the filter
        # picked rows the compile never had.
        answer = self.reader().receipts(receipt_labels=["R1", "R98", "R99"])

        self.assertEqual(
            {"total": 8, "staged": 2, "matched": 1, "returned": 1}, answer["counts"]
        )

    def test_a_receipt_the_packet_lacks_says_it_was_not_staged_rather_than_why(self):
        # The child cannot tell absent from another Program's from
        # `proxy_internal`, and a marker that guessed would be the child
        # asserting something it has no way to know. `packet_bound` rides along
        # for the same reason: six Receipts this Program has did not fit, so
        # "not staged" is a fact about the packet and not about the Program.
        answer = self.reader().receipts(receipt_labels=["R99"])

        self.assertEqual(
            [
                {"reason": "packet_bound", "count": 6},
                {"reason": "not_staged", "count": 1, "labels": ["R99"]},
            ],
            answer["omitted"],
        )

    # -- the artifact -------------------------------------------------------

    def test_asking_for_no_artifact_lists_the_ones_this_packet_reached(self):
        # The only way a label is learnable. A Receipt record carries
        # `request_agent_sha` and `response_agent_sha`, and a hash is not
        # something this surface accepts as an argument -- so without the list,
        # a reachable Artifact is one the child can hold the hash of and never
        # name.
        answer = self.reader().artifact()

        self.assertEqual("artifacts", answer["section"])
        self.assertEqual(["AF1"], [item["label"] for item in answer["records"]])
        self.assertEqual("a" * 64, answer["records"][0]["record"]["sha256"])

    def test_the_artifact_list_is_bounded_and_says_what_it_left_out(self):
        held = sections(
            artifacts=section(
                "artifacts",
                [artifact("AF1", "a" * 64), artifact("AF2", "b" * 64)],
                total=9,
            )
        )
        reader = packet.Reader(packet.Packet(sections=held), page=1)

        answer = reader.artifact()

        self.assertEqual(
            {"total": 9, "staged": 2, "matched": 2, "returned": 1}, answer["counts"]
        )
        self.assertEqual(
            [{"reason": "packet_bound", "count": 7}, {"reason": "limit", "count": 1}],
            answer["omitted"],
        )

    def test_the_artifact_list_carries_no_bytes(self):
        # Listing is metadata. The head is staged per Artifact and served when
        # one is named, because a list that inlined every head would be the
        # packet's byte ceiling spent by a verb that was asked for an index.
        answer = self.reader().artifact()

        self.assertNotIn("content", answer["records"][0])

    def test_an_artifact_outside_the_packet_is_an_omission_rather_than_an_error(self):
        answer = self.reader().artifact(artifact_label="AF9")

        self.assertEqual([], answer["records"])
        self.assertEqual([{"reason": "no_such_artifact", "label": "AF9"}],
                         answer["omitted"])

    def test_a_staged_head_is_served_whole_when_no_range_is_asked_for(self):
        answer = self.reader().artifact(artifact_label="AF1")

        self.assertEqual("hello world", answer["records"][0]["content"])
        self.assertEqual([], answer["omitted"])

    def test_a_range_windows_into_the_staged_head_by_bytes(self):
        answer = self.reader().artifact(artifact_label="AF1", span="0-5")

        self.assertEqual("hello", answer["records"][0]["content"])

    def test_a_range_past_what_was_staged_is_refused_with_the_size_that_was(self):
        answer = self.reader().artifact(artifact_label="AF1", span="50-60")

        self.assertIsNone(answer["records"][0]["content"])
        self.assertEqual(
            [{"reason": "range_beyond_excerpt", "staged_bytes": 11, "range": "50-60"}],
            answer["omitted"],
        )

    def test_an_artifact_whose_head_was_partly_staged_says_how_much(self):
        held = sections(artifacts=section("artifacts", [artifact("AF1", "a" * 64, byte_size=4096)]))
        reader = packet.Reader(packet.Packet(sections=held, excerpts={"AF1": "head"}))

        answer = reader.artifact(artifact_label="AF1")

        self.assertEqual(
            [{"reason": "excerpt_only", "staged_bytes": 4, "byte_size": 4096}],
            answer["omitted"],
        )

    def test_an_artifact_whose_bytes_were_never_staged_says_so_and_still_describes_it(self):
        held = sections(artifacts=section("artifacts", [artifact("AF1", "a" * 64, byte_size=900)]))
        reader = packet.Reader(packet.Packet(sections=held))

        answer = reader.artifact(artifact_label="AF1")

        self.assertIsNone(answer["records"][0]["content"])
        self.assertEqual(900, answer["records"][0]["record"]["byte_size"])
        self.assertEqual([{"reason": "not_staged", "byte_size": 900}], answer["omitted"])

    # -- the boundary the reader is on the wrong side of ---------------------

    def test_an_empty_packet_answers_every_read_rather_than_failing(self):
        # This is the packet a run gets when its Program holds nothing yet, and
        # it is also what a child gets if a compile returned nothing. Either
        # way the child answers with zeroes; a handler that raised would make
        # an empty Program indistinguishable from a broken runtime.
        reader = packet.Reader(packet.Packet())

        for answer in (
            reader.attack_surface(),
            reader.hypotheses(),
            reader.evidence(),
            reader.receipts(receipt_labels=[]),
        ):
            with self.subTest(section=answer["section"]):
                self.assertEqual([], answer["records"])
                self.assertEqual(0, answer["counts"]["total"])


if __name__ == "__main__":
    unittest.main()
