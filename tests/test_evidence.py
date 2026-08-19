"""What `rk evidence` does with bytes, asked without a database.

The exporter's two halves separate cleanly. One half needs rows -- which Receipts
a Finding cites, what was withheld, whether the rendering a human read is still
of this source -- and is asked in `test_database`, against a real Finding, a real
chain and the real six redaction rules. The other half is arithmetic over bytes:
which ranges a set of patterns claims, what stands where a claimed range was,
what two exports of equal input must agree on, and where an export refuses before
it opens a connection. That half is here, where a failure names the function
rather than the fixture.

The rules used below are hand-written and deliberately small. The six real ones
live in `redaction_rules` and are held against their probes from both engines --
POSIX by `check_evidence_export`, `re` by `test_database` -- which is a check this
file could only weaken by copying them.
"""

import json
import unittest
from pathlib import Path

from redkraken import evidence, reporting, store, verifier
from redkraken.outcome import Ledger
from tests.fixtures import scratch


def rule(identifier: str, pattern: str, label: str | None = None) -> dict:
    """One row of `redaction_rules`, in the three columns the exporter reads."""
    return {"id": identifier, "label": label or identifier, "pattern": pattern}


DIGITS = rule("digits", r"[0-9]{4,}", "a run of digits")
WORD = rule("word", r"secret", "the word secret")


def marks_of(marks: list[dict], key: str = "rule") -> list:
    return [mark[key] for mark in marks]


class RedactTest(unittest.TestCase):
    """`redact`: which ranges go, what stands in their place, in what order."""

    def test_nothing_matching_leaves_the_bytes_alone(self):
        data = b"a body with nothing anybody would remove"

        packed, marks = evidence.redact(data, [DIGITS, WORD])

        self.assertEqual(data, packed)
        self.assertEqual([], marks)

    def test_no_rules_at_all_leaves_the_bytes_alone(self):
        data = b"secret 12345"

        self.assertEqual((data, []), evidence.redact(data, []))

    def test_a_match_is_replaced_by_a_marker_the_verifier_recognises(self):
        packed, marks = evidence.redact(b"before 123456 after", [DIGITS])

        found = verifier.MARKER.findall(packed.decode("latin-1"))
        self.assertEqual(1, len(found))
        self.assertEqual(
            f"before {found[0]} after".encode(), packed
        )
        self.assertEqual(
            [{"rule": "digits", "label": "a run of digits", "offset": 7, "bytes": 6}],
            marks,
        )

    def test_the_marker_carries_which_rule_took_it_and_how_much(self):
        """Both are facts about the redaction rather than about the person.

        The range stays answerable without a digest of it: the manifest names
        the unredacted artifact's own digest and the mark carries the offset and
        the length, so a triager holding the full artifact reads exactly what
        was taken. That needs the artifact, which is the point.
        """
        removed = b"9876543210"

        packed, _ = evidence.redact(b"[" + removed + b"]", [DIGITS])

        self.assertEqual(
            "[" + verifier.MARKER_FORM.format(rule="digits", bytes=len(removed)) + "]",
            packed.decode("latin-1"),
        )

    def test_no_digest_of_a_redacted_range_leaves_in_the_marker_or_the_mark(self):
        """A telephone number, a national identifier or a card number has few
        enough possible values to walk through offline, so a SHA-256 of one is
        the value with an extra step. A bundle publishing one would be a
        redaction in name."""
        removed = b"5551234567"

        packed, marks = evidence.redact(b"call " + removed + b" back", [DIGITS])

        self.assertNotIn("sha256", marks[0])
        self.assertNotIn(verifier.digest(removed), packed.decode("latin-1"))

    def test_every_match_of_every_rule_goes_not_only_the_first(self):
        packed, marks = evidence.redact(b"1111 secret 2222 secret", [DIGITS, WORD])

        self.assertEqual(["digits", "word", "digits", "word"], marks_of(marks))
        self.assertNotIn(b"secret", packed)
        self.assertNotIn(b"1111", packed)

    def test_the_rules_run_against_the_original_and_not_against_each_other(self):
        """The reason `redact` splices once instead of substituting six times.

        A marker carries the length of what it took, a long body is a long run
        of digits, and a run of digits is a card number as far as `card` is
        concerned. Six passes in sequence would have the fifth rule matching
        inside what the second left, so this asks that a rule which would match
        a marker matches nothing.
        """
        packed, marks = evidence.redact(b"secret", [WORD, DIGITS])

        self.assertEqual(["word"], marks_of(marks))
        self.assertEqual(1, len(verifier.MARKER.findall(packed.decode("latin-1"))))

    def test_two_rules_claiming_the_same_bytes_are_resolved_once(self):
        """Overlaps go to the earlier start, then the longer match, then the
        lower identifier. A total order, so the same bytes redact the same way
        whichever order the rules arrive in."""
        overlapping = rule("aaa", r"12345678")
        narrower = rule("bbb", r"[0-9]{4}")

        packed, marks = evidence.redact(b"x12345678y", [narrower, overlapping])

        self.assertEqual(["aaa"], marks_of(marks))
        self.assertEqual(8, marks[0]["bytes"])
        self.assertEqual(1, len(verifier.MARKER.findall(packed.decode("latin-1"))))

    def test_the_order_the_rules_arrive_in_does_not_change_the_result(self):
        data = b"call 5551234567 about secret 4444"
        rules = [DIGITS, WORD, rule("aaa", r"555[0-9]+")]

        self.assertEqual(
            evidence.redact(data, rules), evidence.redact(data, list(reversed(rules)))
        )

    def test_two_matches_that_touch_are_two_markers(self):
        packed, marks = evidence.redact(b"1111secret", [DIGITS, WORD])

        self.assertEqual(["digits", "word"], marks_of(marks))
        self.assertEqual(2, len(verifier.MARKER.findall(packed.decode("latin-1"))))

    def test_a_pattern_that_can_match_nothing_matches_nothing(self):
        """A zero-width match would splice a marker in without removing a byte,
        and would do it at every offset in the artifact."""
        packed, marks = evidence.redact(b"anything at all", [rule("empty", r"x*")])

        self.assertEqual(b"anything at all", packed)
        self.assertEqual([], marks)

    def test_bytes_that_are_not_utf_8_survive_the_round_trip(self):
        """latin-1 throughout, because it is the one codec that round-trips every
        byte. Decoding as UTF-8 would put this module in the business of guessing
        an encoding and would make a redaction depend on the guess."""
        data = bytes(range(256))

        packed, marks = evidence.redact(data, [rule("none", r"zzzz")])

        self.assertEqual(data, packed)
        self.assertEqual([], marks)

    def test_the_offset_a_mark_names_is_into_the_artifact_it_came_from(self):
        packed, marks = evidence.redact(b"..secret..secret", [WORD])

        self.assertEqual([2, 10], marks_of(marks, "offset"))
        self.assertNotIn(b"secret", packed)


class ArtifactTest(unittest.TestCase):
    """`_artifacts`: the cited bytes, once each, beside what to say about them."""

    def setUp(self):
        self.keep = store.Store(scratch())
        self.body = b"GET /orders HTTP/1.1\r\nX: 4444555566667777\r\n"
        self.sha, _ = self.keep.put(self.body)

    def cited(self, receipt: str, direction: str) -> dict:
        return {
            "receipt": receipt,
            "direction": direction,
            "sha256": self.sha,
            "byte_size": len(self.body),
            "content_type": "message/http",
        }

    def test_one_cited_artifact_is_packed_under_its_agent_view_hash(self):
        packaged, blobs, marks = evidence._artifacts(
            self.keep, [self.cited("r1", "request")], [DIGITS]
        )

        self.assertEqual([f"{evidence.BYTES}/{self.sha}"], list(blobs))
        self.assertEqual(self.sha, packaged[0]["agent_sha256"])
        self.assertEqual(len(self.body), packaged[0]["agent_bytes"])
        self.assertEqual("message/http", packaged[0]["content_type"])
        self.assertEqual(["r1:request"], packaged[0]["cited_by"])

    def test_the_hash_and_size_recorded_are_of_the_redacted_bytes(self):
        """Not of what came out of the store. The manifest hashes what is in the
        bundle, and a recipient checking a file against a hash of the unredacted
        original would be told every artifact is broken."""
        packaged, blobs, _ = evidence._artifacts(
            self.keep, [self.cited("r1", "request")], [DIGITS]
        )
        data = blobs[packaged[0]["path"]]

        self.assertNotEqual(self.body, data)
        self.assertEqual(len(data), packaged[0]["bytes"])
        self.assertEqual(verifier.digest(data), packaged[0]["sha256"])

    def test_two_exchanges_that_carried_the_same_bytes_are_one_file(self):
        packaged, blobs, marks = evidence._artifacts(
            self.keep,
            [self.cited("r1", "request"), self.cited("r2", "response")],
            [DIGITS],
        )

        self.assertEqual(1, len(packaged))
        self.assertEqual(1, len(blobs))
        self.assertEqual(["r1:request", "r2:response"], packaged[0]["cited_by"])
        self.assertEqual(1, len(marks), "the shared artifact was redacted twice")

    def test_the_bytes_come_back_beside_the_index_and_never_inside_it(self):
        """One forgotten `pop` away from writing the artifact into the index as
        well as beside it, which is a redaction applied to one copy of something
        the bundle then ships twice."""
        packaged, _, _ = evidence._artifacts(
            self.keep, [self.cited("r1", "request")], [DIGITS]
        )

        self.assertNotIn(b"4444555566667777", json.dumps(packaged).encode())
        self.assertEqual(
            {"agent_sha256", "path", "content_type", "agent_bytes", "bytes",
             "sha256", "redactions", "cited_by"},
            set(packaged[0]),
        )

    def test_every_mark_says_which_artifact_it_was_found_in(self):
        packaged, _, marks = evidence._artifacts(
            self.keep, [self.cited("r1", "request")], [DIGITS]
        )

        self.assertEqual([self.sha], marks_of(marks, "artifact"))
        self.assertEqual(packaged[0]["redactions"][0]["offset"], marks[0]["offset"])

    def test_the_index_is_ordered_by_hash_rather_than_by_citation(self):
        other, _ = self.keep.put(b"a different body")
        named = [
            {**self.cited("r1", "request"), "sha256": other},
            self.cited("r2", "response"),
        ]

        packaged, _, _ = evidence._artifacts(self.keep, named, [])

        self.assertEqual(
            sorted([self.sha, other]), [item["agent_sha256"] for item in packaged]
        )

    def test_an_artifact_the_store_does_not_hold_is_raised_and_not_skipped(self):
        """The exporter turns this into a refusal. Packing on and shipping a
        bundle that cites an artifact it does not carry would be the one failure
        the verifier could not see, because the manifest would not name it."""
        missing = {**self.cited("r1", "request"), "sha256": "0" * 64}

        with self.assertRaises(store.Missing):
            evidence._artifacts(self.keep, [missing], [])


class ManifestTest(unittest.TestCase):
    """`_manifest`: what a bundle says about itself, and what it is a digest of."""

    def built(self, **changes: object) -> dict:
        answers = evidence._Answers(
            evidence.EXPORT, subject="finding", label="F-0007", template="hackerone-v1"
        )
        answers.slug = "selftest"
        gathered = {
            "receipts": [],
            "artifacts": [],
            "specifications": [],
            "required": ["verify.py", "report.md"],
            "exclusions": [{"code": "wire_artifact", "detail": "sealed", "items": 2}],
            "rules": [DIGITS],
        } | changes
        return evidence._manifest(
            answers,
            {"digest": "a" * 64},
            evidence._Evidence(**gathered),
            {"report.md": b"# F-0007\n", "verify.py": b"# code\n"},
            [{"artifact": "b" * 64, "rule": "digits", "offset": 0, "bytes": 4}],
        )

    def test_the_manifest_names_every_file_with_its_size_and_hash(self):
        document = self.built()

        self.assertEqual(
            [
                {"path": "report.md", "bytes": 9, "sha256": verifier.digest(b"# F-0007\n")},
                {"path": "verify.py", "bytes": 7, "sha256": verifier.digest(b"# code\n")},
            ],
            document["files"],
        )

    def test_the_manifest_is_its_own_digest_by_the_verifiers_arithmetic(self):
        document = self.built()

        self.assertEqual(verifier.manifest_digest(document), document["digest"])

    def test_the_wall_clock_is_the_only_key_outside_the_digest(self):
        """Criterion 5, made checkable rather than asserted in a docstring."""
        first = self.built()
        second = self.built()

        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(
            {key: value for key, value in first.items() if key != verifier.PACKAGING},
            {key: value for key, value in second.items() if key != verifier.PACKAGING},
        )
        self.assertEqual(["exported_at"], list(second[verifier.PACKAGING]))

    def test_the_rules_travel_with_the_bundle_so_the_rescan_can_run(self):
        """A verifier told the patterns separately could not rescan, and a
        verifier that could not rescan would be taking the redaction on the same
        trust as the report."""
        self.assertEqual([DIGITS], self.built()["redaction_rules"])

    def test_what_was_withheld_is_named_rather_than_silently_absent(self):
        self.assertEqual(
            [{"code": "wire_artifact", "detail": "sealed", "items": 2}],
            self.built()["excluded"],
        )

    def test_the_required_files_are_recorded_in_one_order(self):
        self.assertEqual(["report.md", "verify.py"], self.built()["required"])

    def test_the_schema_the_renderer_and_what_this_is_about_are_recorded(self):
        document = self.built()

        self.assertEqual(verifier.SCHEMA, document["schema"])
        self.assertEqual(reporting.VERSION, document["renderer"])
        self.assertEqual("hackerone-v1", document["template"])
        self.assertEqual("a" * 64, document["source_digest"])

    def test_the_manifest_carries_one_version_of_the_packing_and_not_two(self):
        """The verifier ships inside the bundle, so what packed it and what reads
        it are one release. A second key holding the same string is a difference
        a recipient would go looking for and not find."""
        self.assertNotIn("version", self.built())

    def test_changing_anything_the_bundle_is_about_changes_the_digest(self):
        self.assertNotEqual(
            self.built()["digest"], self.built(rules=[WORD])["digest"]
        )

    def test_a_bundle_with_no_filed_rendering_makes_no_claim_about_one(self):
        self.assertNotIn("rendering", self.built())


class ApprovedReportTest(unittest.TestCase):
    """Ticket 64: which bytes become `report.md`, and what says so.

    The staleness check compares the rows a rendering was made from. It cannot
    compare the document, because the renderer takes an optional narrative: a
    filed rendering may carry one, and a re-render of the same rows does not.
    So a bundle could ship a report that differed from the approved one by whole
    paragraphs with every hash in it agreeing.
    """

    APPROVED = b"# F-0007\n\nwhat a human read, narrative and all.\n"
    FRESH = "# F-0007\n"

    def answers(self, **filed: object) -> evidence._Answers:
        answers = evidence._Answers(
            evidence.EXPORT, subject="finding", label="F-0007", template="hackerone-v1"
        )
        answers.slug = "selftest"
        if filed:
            answers.filed = {
                "rendering": "0192f000-0000-7000-8000-000000000001",
                "rendered_at": "2026-08-19T09:00:00Z",
                "approved": True,
                "content": self.APPROVED.decode("utf-8"),
                "content_sha256": verifier.digest(self.APPROVED),
            } | filed
        return answers

    def test_a_finding_nobody_has_read_ships_the_document_just_rendered(self):
        ledger = Ledger()

        self.assertEqual(
            self.FRESH.encode("utf-8"),
            evidence._approved(ledger, self.answers(), self.FRESH),
        )

    def test_a_filed_rendering_is_what_the_bundle_ships_and_not_the_re_render(self):
        ledger = Ledger()
        answers = self.answers(approved=True)

        self.assertEqual(self.APPROVED, evidence._approved(ledger, answers, self.FRESH))
        # And it says so, because a bundle whose report is not what these rows
        # render to today is a thing an operator should read in the outcome
        # rather than discover by diffing.
        said = " ".join(item.detail for item in ledger.assertions if item.name == "report")
        self.assertIn("is not what these rows render to today", said)

    def test_a_filed_rendering_whose_bytes_are_not_its_hash_is_refused(self):
        ledger = Ledger()
        answers = self.answers(content="somebody else's document\n")

        self.assertIsNone(evidence._approved(ledger, answers, self.FRESH))
        self.assertEqual(
            ["report_renderings"], [item.source for item in ledger.violations]
        )

    def test_the_manifest_names_the_rendering_the_report_is(self):
        answers = self.answers(approved=True)
        document = evidence._manifest(
            answers,
            {"digest": "a" * 64},
            evidence._Evidence(
                receipts=[], artifacts=[], specifications=[],
                required=["report.md"], exclusions=[], rules=[],
            ),
            {"report.md": self.APPROVED},
            [],
        )

        self.assertEqual(
            {
                "id": "0192f000-0000-7000-8000-000000000001",
                "rendered_at": "2026-08-19T09:00:00Z",
                "approved": True,
                "content_sha256": verifier.digest(self.APPROVED),
            },
            document["rendering"],
        )
        # The claim is checkable by somebody who has only the bundle: the file
        # entry and the rendering entry are the same hash.
        self.assertEqual(
            document["rendering"]["content_sha256"],
            next(item["sha256"] for item in document["files"] if item["path"] == "report.md"),
        )


class RefusedBundleTest(unittest.TestCase):
    """`_verified`: what becomes of a bundle its own verifier will not pass."""

    LEFT = b"call 5551234567 back\n"

    def refused(self) -> Path:
        """A bundle that fails the one check criterion 6 is about.

        `redaction_incomplete` rather than a broken hash: it is the refusal that
        says a packed file still carries what a rule was written to remove, so
        it is the one where leaving the directory behind leaves that material on
        disk under a name an operator has every reason to read as a bundle.
        """
        where = scratch() / "bundle"
        where.mkdir()
        (where / "report.md").write_bytes(self.LEFT)
        document = {
            "schema": verifier.SCHEMA,
            "required": ["report.md"],
            "files": [
                {
                    "path": "report.md",
                    "bytes": len(self.LEFT),
                    "sha256": verifier.digest(self.LEFT),
                }
            ],
            "redaction_rules": [DIGITS],
        }
        (where / verifier.MANIFEST).write_text(
            json.dumps(
                document
                | {
                    "digest": verifier.manifest_digest(document),
                    verifier.PACKAGING: {"exported_at": "2026-08-16T00:00:00Z"},
                },
                sort_keys=True,
            )
        )
        return where

    def verified(self, where: Path) -> tuple[Ledger, evidence._Answers]:
        ledger = Ledger()
        answers = evidence._Answers(
            evidence.EXPORT, subject="finding", label="F-0007", template="hackerone-v1"
        )
        answers.bundle = {"path": str(where)}
        evidence._verified(ledger, answers, where)
        return ledger, answers

    def test_a_bundle_the_verifier_refuses_is_not_left_where_it_was_written(self):
        where = self.refused()

        ledger, answers = self.verified(where)

        self.assertFalse(where.exists())
        self.assertTrue(answers.bundle["removed"])
        self.assertFalse(answers.bundle["verified"])

    def test_the_refusal_names_what_was_wrong_before_it_says_what_it_removed(self):
        """Both, and in that order. An operator told only that a directory was
        deleted has been told nothing about why."""
        ledger, _ = self.verified(self.refused())

        self.assertEqual(["verifier"], [violation.source for violation in ledger.violations])
        self.assertIn("redaction_incomplete", ledger.violations[0].detail)
        self.assertIn("was removed", ledger.assertions[-1].detail)

    def test_a_bundle_that_passes_stays_exactly_as_it_was_written(self):
        where = self.refused()
        (where / "report.md").write_bytes(self.LEFT)
        document = json.loads((where / verifier.MANIFEST).read_text(encoding="utf-8"))
        document["redaction_rules"] = []
        document["digest"] = verifier.manifest_digest(document)
        (where / verifier.MANIFEST).write_text(json.dumps(document, sort_keys=True))

        ledger, answers = self.verified(where)

        self.assertEqual([], ledger.violations)
        self.assertTrue(answers.bundle["verified"])
        self.assertNotIn("removed", answers.bundle)
        self.assertEqual(self.LEFT, (where / "report.md").read_bytes())


class DestinationTest(unittest.TestCase):
    """`_empty`: where a bundle may be written, asked before anything is read."""

    def setUp(self):
        self.root = scratch()
        self.ledger = Ledger()

    def test_a_path_that_does_not_exist_yet_is_where_a_bundle_goes(self):
        self.assertTrue(evidence._empty(self.ledger, self.root / "new"))
        self.assertEqual([], self.ledger.violations)

    def test_an_existing_empty_directory_is_allowed(self):
        (self.root / "empty").mkdir()

        self.assertTrue(evidence._empty(self.ledger, self.root / "empty"))

    def test_a_directory_that_already_holds_a_bundle_is_refused(self):
        """Refused rather than merged into. A second export over the first would
        leave the artifacts of the first behind, the manifest would not name
        them, and the verifier would report a bundle somebody had added files
        to -- which is true, and is not what happened."""
        (self.root / "used").mkdir()
        (self.root / "used" / verifier.MANIFEST).write_text("{}")

        self.assertFalse(evidence._empty(self.ledger, self.root / "used"))
        self.assertIn("is not empty", self.ledger.violations[0].detail)
        self.assertEqual("argument:--out", self.ledger.violations[0].source)

    def test_a_file_where_a_directory_was_named_is_refused(self):
        (self.root / "afile").write_text("not a directory")

        self.assertFalse(evidence._empty(self.ledger, self.root / "afile"))
        self.assertIn("is not a directory", self.ledger.violations[0].detail)


class ExportRefusalTest(unittest.TestCase):
    """The refusals `export` reaches before it opens a connection."""

    def setUp(self):
        self.root = scratch()

    def exported(self, out: Path, configuration: Path) -> object:
        return evidence.export(
            None,
            configuration,
            subject="finding",
            label="F-0007",
            template="hackerone-v1",
            out=out,
            root=self.root / "store",
        )

    def test_an_occupied_destination_is_refused_before_the_configuration_is_read(self):
        """`_empty` costs a `listdir` and every refusal after it costs a round
        trip, so an operator who named an occupied directory hears about it now.
        The configuration path here does not exist, and reaching it would raise
        rather than refuse -- which is what makes the ordering visible."""
        (self.root / "used").mkdir()
        (self.root / "used" / "already").write_text("here")

        answered = self.exported(self.root / "used", self.root / "nowhere.toml")

        self.assertFalse(answered.ok)
        self.assertEqual(["bundle"], [item.name for item in answered.assertions if not item.ok])

    def test_an_unreadable_configuration_is_refused_before_a_connection(self):
        """`None` is passed as the runtime settings, so a connection cannot be
        opened at all. Reaching one would raise rather than refuse."""
        answered = self.exported(self.root / "new", self.root / "nowhere.toml")

        self.assertFalse(answered.ok)
        self.assertEqual(
            ["configuration"], [item.name for item in answered.assertions if not item.ok]
        )
        self.assertTrue(answered.violations)

    def test_a_refused_export_reports_the_facts_it_had_and_writes_nothing(self):
        answered = self.exported(self.root / "new", self.root / "nowhere.toml")

        self.assertEqual(evidence.EXPORT, answered.as_dict()["command"])
        self.assertEqual(set(evidence.FACTS), set(answered.facts))
        self.assertEqual("F-0007", answered.facts["label"])
        self.assertIsNone(answered.facts["bundle"])
        self.assertFalse((self.root / "new").exists())


class VerifyCommandTest(unittest.TestCase):
    """`rk evidence verify`: the shipped check, reported in this tree's terms."""

    def setUp(self):
        self.root = scratch()

    def bundled(self, **files: bytes) -> Path:
        where = self.root / "bundle"
        where.mkdir()
        written = {"report.md": b"# F-0007\n"} | files
        for path, data in written.items():
            (where / path).write_bytes(data)
        document = {
            "schema": verifier.SCHEMA,
            "required": ["report.md"],
            "files": [
                {"path": path, "bytes": len(data), "sha256": verifier.digest(data)}
                for path, data in sorted(written.items())
            ],
            "redaction_rules": [],
        }
        (where / verifier.MANIFEST).write_bytes(
            json.dumps(
                document
                | {"digest": verifier.manifest_digest(document),
                   verifier.PACKAGING: {"exported_at": "2026-08-16T00:00:00Z"}},
                indent=2,
                sort_keys=True,
            ).encode()
        )
        return where

    def test_a_bundle_that_holds_is_reported_as_holding(self):
        answered = evidence.verify(self.bundled())

        self.assertTrue(answered.ok, answered.violations)
        self.assertEqual(0, answered.exit_code)
        self.assertEqual(
            {"path": str(self.root / "bundle"), "files": 1, "verified": True, "problems": []},
            answered.facts["bundle"],
        )

    def test_a_bundle_that_does_not_is_reported_problem_by_problem(self):
        where = self.bundled()
        (where / "added.txt").write_text("a file nobody named")

        answered = evidence.verify(where)

        self.assertFalse(answered.ok)
        self.assertNotEqual(0, answered.exit_code)
        self.assertEqual(["file_unlisted"], answered.facts["bundle"]["problems"])
        self.assertIn("added.txt", answered.violations[0].detail)
        self.assertEqual("argument:bundle", answered.violations[0].source)

    def test_verify_asks_nothing_about_a_program_because_it_has_none(self):
        """The property the subcommand exists to preserve: it reads the directory
        and nothing else, which is what makes it the same check a recipient runs."""
        answered = evidence.verify(self.bundled())

        self.assertEqual(evidence.VERIFY, answered.as_dict()["command"])
        self.assertIsNone(answered.facts["program_id"])
        self.assertIsNone(answered.facts["subject"])
        self.assertIsNone(answered.facts["template"])

    def test_a_directory_that_is_not_a_bundle_is_a_refusal_and_not_a_crash(self):
        answered = evidence.verify(self.root / "nothing-here")

        self.assertFalse(answered.ok)
        self.assertEqual(["manifest_missing"], answered.facts["bundle"]["problems"])


class DocumentTest(unittest.TestCase):
    """`_json` and `_now`: the two places determinism could quietly leak."""

    def test_two_equal_documents_are_the_same_bytes(self):
        first = evidence._json({"b": 1, "a": [3, 2]})
        second = evidence._json({"a": [3, 2], "b": 1})

        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual({"a": [3, 2], "b": 1}, json.loads(first))

    def test_the_export_stamp_is_a_second_resolution_utc_instant(self):
        stamp = evidence._now()

        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


if __name__ == "__main__":
    unittest.main()
