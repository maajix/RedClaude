"""What the shipped verifier says about a directory, and nothing else.

`src/redkraken/verifier.py` is the one module in this tree that may import
nothing from this tree. That is not a style rule: a copy of it travels inside
every evidence bundle as `verify.py`, and the person who runs it has this
repository, this database and this harness's key material nowhere. So this file
builds bundles out of dictionaries and bytes, breaks each of them one way, and
reads the answer.

`test_database` runs the same module over a bundle the exporter really wrote,
and runs the shipped copy as a subprocess with `PYTHONPATH` emptied. What is
here is the grammar; what is there is the round trip.
"""

import contextlib
import io
import json
import unittest
from pathlib import Path

from redkraken import verifier
from tests.fixtures import scratch


#: One redaction rule, in the shape the manifest carries it. `email` because it
#: is the pattern with the least ambiguous witness: an address is either in a
#: file or it is not.
EMAIL = {"id": "email", "label": "email address", "pattern": r"[\w.+-]+@[\w-]+\.[\w.]+"}


def bundled(root: Path, files: dict[str, bytes], **changes: object) -> dict:
    """One well-formed bundle on disk, with whatever a caller wants changed.

    Written the way `evidence._written` writes one: every file first, the
    manifest last, and the manifest's digest taken over itself minus its own
    digest and the packaging object.
    """
    for path, data in files.items():
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    document = {
        "schema": verifier.SCHEMA,
        "subject": "finding",
        "label": "F-0007",
        "required": ["report.md", "verify.py"],
        "files": [
            {"path": path, "bytes": len(data), "sha256": verifier.digest(data)}
            for path, data in sorted(files.items())
        ],
        "redaction_rules": [EMAIL],
    } | changes
    document = document | {
        "digest": verifier.manifest_digest(document),
        verifier.PACKAGING: {"exported_at": "2026-08-16T00:00:00Z"},
    }
    (root / verifier.MANIFEST).write_text(json.dumps(document, indent=2, sort_keys=True))
    return document


def plain(**files: bytes) -> dict[str, bytes]:
    """The two files every bundle in this file carries, plus whatever is asked."""
    return {
        "report.md": b"# F-0007\n\nnothing anybody would redact\n",
        "verify.py": Path(verifier.__file__).read_bytes(),
    } | {name.replace("__", "."): data for name, data in files.items()}


def codes(answer: dict) -> list[str]:
    return [problem["code"] for problem in answer["problems"]]


class ManifestTest(unittest.TestCase):
    """The digest, and what it is and is not taken over."""

    def test_two_manifests_that_differ_only_in_packaging_have_one_digest(self):
        document = {"schema": verifier.SCHEMA, "label": "F-0007"}
        first = verifier.manifest_digest(
            document | {verifier.PACKAGING: {"exported_at": "2026-08-16T00:00:00Z"}}
        )
        second = verifier.manifest_digest(
            document | {verifier.PACKAGING: {"exported_at": "2027-01-01T12:00:00Z"}}
        )

        self.assertEqual(first, second)

    def test_the_digest_is_not_taken_over_itself(self):
        document = {"schema": verifier.SCHEMA, "label": "F-0007"}

        self.assertEqual(
            verifier.manifest_digest(document),
            verifier.manifest_digest(document | {"digest": "b" * 64}),
        )

    def test_re_indenting_a_manifest_does_not_change_what_it_is_a_digest_of(self):
        document = {"schema": verifier.SCHEMA, "files": [{"path": "report.md"}]}

        self.assertEqual(
            verifier.canonical(document),
            verifier.canonical(json.loads(json.dumps(document, indent=4))),
        )

    def test_changing_anything_a_bundle_is_about_changes_the_digest(self):
        document = {"schema": verifier.SCHEMA, "label": "F-0007"}

        self.assertNotEqual(
            verifier.manifest_digest(document),
            verifier.manifest_digest(document | {"label": "F-0008"}),
        )


class VerifierTest(unittest.TestCase):
    """One well-formed bundle, and every way one arrives broken."""

    def setUp(self):
        self.root = scratch()

    def test_a_bundle_nobody_has_touched_passes(self):
        bundled(self.root, plain())

        answer = verifier.verify(self.root)

        self.assertTrue(answer["ok"], answer["problems"])
        self.assertEqual(2, answer["files"])
        self.assertEqual(verifier.SCHEMA, answer["schema"])

    def test_a_directory_with_no_manifest_is_not_a_bundle(self):
        self.assertEqual(["manifest_missing"], codes(verifier.verify(self.root)))

    def test_a_manifest_that_is_not_json_stops_the_check(self):
        (self.root / verifier.MANIFEST).write_text("{not json")

        self.assertEqual(["manifest_unreadable"], codes(verifier.verify(self.root)))

    def test_a_schema_this_verifier_does_not_know_stops_the_check(self):
        """Refused rather than interpreted.

        A verifier that guessed the layout of a schema it had never seen would
        answer confidently about a document it had misread, which is worse than
        saying it cannot read it.
        """
        bundled(self.root, plain(), schema="rk2-evidence/99")

        answer = verifier.verify(self.root)

        self.assertEqual(["schema_unknown"], codes(answer))
        self.assertIn("rk2-evidence/99", answer["problems"][0]["detail"])

    def test_an_edited_manifest_is_caught_even_when_every_file_still_hashes(self):
        document = bundled(self.root, plain())
        document["label"] = "F-somebody-elses"
        (self.root / verifier.MANIFEST).write_text(json.dumps(document, sort_keys=True))

        self.assertEqual(["manifest_digest_mismatch"], codes(verifier.verify(self.root)))

    def test_a_file_the_manifest_names_and_that_is_not_there(self):
        bundled(self.root, plain())
        (self.root / "report.md").unlink()

        self.assertEqual(["file_missing"], codes(verifier.verify(self.root)))

    def test_a_file_whose_bytes_were_changed_under_its_name(self):
        bundled(self.root, plain())
        data = (self.root / "report.md").read_bytes()
        (self.root / "report.md").write_bytes(data[:-2] + b"X" + data[-1:])

        self.assertEqual(["file_hash_mismatch"], codes(verifier.verify(self.root)))

    def test_a_file_that_grew_says_so_about_its_size_as_well(self):
        bundled(self.root, plain())
        (self.root / "report.md").write_bytes(b"a much longer document than the one named")

        self.assertEqual(
            ["file_hash_mismatch", "file_size_mismatch"], sorted(codes(verifier.verify(self.root)))
        )

    def test_a_file_nobody_named(self):
        """The direction that is easiest to leave out and matters most.

        Every per-file check passes on a bundle somebody has added a file to.
        Only the scan the other way round finds it.
        """
        bundled(self.root, plain())
        (self.root / "extra.txt").write_text("a file nobody named")

        answer = verifier.verify(self.root)

        self.assertEqual(["file_unlisted"], codes(answer))
        self.assertEqual("extra.txt", answer["problems"][0]["path"])

    def test_an_unlisted_file_in_a_subdirectory_is_found_by_its_posix_path(self):
        bundled(self.root, plain())
        (self.root / "artifacts").mkdir()
        (self.root / "artifacts" / ("a" * 64)).write_bytes(b"bytes nothing indexes")

        answer = verifier.verify(self.root)

        self.assertEqual([f"artifacts/{'a' * 64}"], [p["path"] for p in answer["problems"]])

    def test_a_manifest_that_owes_a_file_and_lists_none(self):
        bundled(self.root, plain(), required=["report.md", "verify.py", "receipts.json"])

        answer = verifier.verify(self.root)

        self.assertEqual(["required_file_unlisted"], codes(answer))
        self.assertEqual("receipts.json", answer["problems"][0]["path"])

    def test_the_manifest_is_not_read_as_a_file_it_does_not_index(self):
        """A document cannot carry its own hash, so it is not one of the files."""
        bundled(self.root, plain())

        self.assertTrue(verifier.verify(self.root)["ok"])
        self.assertNotIn(
            verifier.MANIFEST,
            [item["path"] for item in json.loads(
                (self.root / verifier.MANIFEST).read_text()
            )["files"]],
        )

    def test_every_problem_is_reported_rather_than_the_first(self):
        bundled(self.root, plain())
        (self.root / "report.md").write_bytes(b"changed")
        (self.root / "extra.txt").write_text("added")

        self.assertEqual(
            ["file_hash_mismatch", "file_size_mismatch", "file_unlisted"],
            sorted(codes(verifier.verify(self.root))),
        )


class ResidueTest(unittest.TestCase):
    """Criterion 6, which is the one failure a clean-looking bundle can have."""

    def setUp(self):
        self.root = scratch()

    def test_a_bundle_carrying_what_a_rule_was_written_to_remove(self):
        bundled(self.root, plain(**{"receipts__json": b'{"owner": "alice@example.com"}'}))

        answer = verifier.verify(self.root)

        self.assertEqual(["redaction_incomplete"], codes(answer))
        self.assertEqual("receipts.json", answer["problems"][0]["path"])
        self.assertIn("email address", answer["problems"][0]["detail"])

    def test_a_marker_is_not_read_as_the_thing_it_replaced(self):
        """The markers carry the length of what they took, and a length is digits.

        A rescan that read the markers would find a long run of digits in one
        and report the redaction as the thing that needs redacting. Removed
        before the scan, and this is the arm that says so. The byte count here
        is large enough to trip the rule, because a marker short enough not to
        would make this pass whether the markers were removed or not.
        """
        marker = verifier.MARKER_FORM.format(rule="phone", bytes=123456789012)
        phone = {"id": "phone", "label": "telephone number",
                 "pattern": r"\+?[0-9][0-9 ().-]{7,}[0-9]"}
        self.assertRegex(marker, phone["pattern"])
        bundled(
            self.root,
            plain(**{"receipts__json": marker.encode()}),
            redaction_rules=[phone],
        )

        self.assertTrue(verifier.verify(self.root)["ok"])

    def test_the_verifier_itself_is_not_scanned(self):
        """It is code, and its own patterns would be read as residue.

        The one packaged file that is furniture rather than evidence. Everything
        a bundle carries *about* a target is read, and this arm exists so that
        the exclusion is a decision somebody can see rather than an oversight.
        """
        bundled(self.root, plain())

        self.assertTrue(verifier.verify(self.root)["ok"])
        self.assertFalse(verifier._scanned(verifier.VERIFIER))
        self.assertTrue(verifier._scanned("report.md"))

    def test_a_rule_this_engine_cannot_compile_is_a_finding_of_its_own(self):
        """The pattern is stored as POSIX and applied by `re`.

        If the two disagree, the bundle was redacted by something other than what
        the manifest says redacted it, and a verifier that skipped the rule would
        be reporting on a redaction it had not checked.
        """
        bundled(self.root, plain(), redaction_rules=[{"id": "broken", "pattern": "([unclosed"}])

        answer = verifier.verify(self.root)

        self.assertEqual(["rule_unusable"], codes(answer))
        self.assertEqual("broken", answer["problems"][0]["path"])

    def test_a_rule_with_no_pattern_at_all_is_the_same_finding(self):
        bundled(self.root, plain(), redaction_rules=[{"id": "nameless"}])

        self.assertEqual(["rule_unusable"], codes(verifier.verify(self.root)))

    def test_a_manifest_with_no_rules_scans_nothing_and_says_nothing(self):
        bundled(self.root, plain(**{"receipts__json": b'{"owner": "alice@example.com"}'}),
                redaction_rules=[])

        self.assertTrue(verifier.verify(self.root)["ok"])


class ArtifactIndexTest(unittest.TestCase):
    """`artifacts.json` against the manifest: the bundle's two indexes.

    The same export writes both, which is why a recipient should not be made to
    assume they agree. Where they disagree, an artifact moved after one of them
    was written and every other check in the module passes.
    """

    PACKED = b"the packed bytes of one artifact\n"

    def setUp(self):
        self.root = scratch()

    def index(self, **changes: object) -> dict[str, bytes]:
        entry = {
            "path": "artifacts/aa",
            "bytes": len(self.PACKED),
            "sha256": verifier.digest(self.PACKED),
        } | changes
        return plain() | {
            "artifacts/aa": self.PACKED,
            "artifacts.json": json.dumps([entry]).encode(),
        }

    def test_two_indexes_that_agree_pass(self):
        bundled(self.root, self.index())

        self.assertTrue(verifier.verify(self.root)["ok"])

    def test_an_artifact_the_index_names_and_the_manifest_does_not(self):
        files = self.index(path="artifacts/bb")

        bundled(self.root, files)
        answer = verifier.verify(self.root)

        self.assertEqual(["artifact_unlisted"], codes(answer))
        self.assertEqual("artifacts/bb", answer["problems"][0]["path"])

    def test_the_two_indexes_disagreeing_about_one_artifact(self):
        bundled(self.root, self.index(sha256="c" * 64))

        answer = verifier.verify(self.root)

        self.assertEqual(["artifact_hash_disagrees"], codes(answer))
        self.assertIn(verifier.digest(self.PACKED)[:12], answer["problems"][0]["detail"])

    def test_a_size_the_two_indexes_disagree_about_is_the_same_finding(self):
        bundled(self.root, self.index(bytes=1))

        self.assertEqual(["artifact_hash_disagrees"], codes(verifier.verify(self.root)))

    def test_an_index_that_is_not_json_is_a_finding_of_its_own(self):
        bundled(self.root, plain() | {"artifacts.json": b"{not json"})

        self.assertEqual(["artifact_index_unreadable"], codes(verifier.verify(self.root)))

    def test_a_bundle_with_no_artifact_index_is_not_faulted_here(self):
        """A bundle that owes one has it in the manifest, and `_file` reports
        its absence against that entry. Reporting it twice, once under a code
        about disagreement, would name a disagreement nothing is party to."""
        bundled(self.root, plain())

        self.assertTrue(verifier.verify(self.root)["ok"])


class RenderingTest(unittest.TestCase):
    """Ticket 64: the one claim a bundle makes about something outside itself.

    `report.md` can be a document a human read and approved, and an approval
    names exact bytes. Every other hash in a bundle was written by the export
    that wrote the file it names, so this is the only check here a recipient can
    make against a fact they were told separately.
    """

    REPORT = b"# F-0007\n\nnothing anybody would redact\n"

    def setUp(self):
        self.root = scratch()

    def named(self, **changes: object) -> dict:
        return {
            "id": "0192f000-0000-7000-8000-000000000001",
            "rendered_at": "2026-08-19T09:00:00Z",
            "approved": True,
            "content_sha256": verifier.digest(self.REPORT),
        } | changes

    def test_a_report_that_is_the_rendering_the_manifest_names_passes(self):
        bundled(self.root, plain(), rendering=self.named())

        self.assertTrue(verifier.verify(self.root)["ok"])

    def test_a_report_that_is_not_the_rendering_named_is_a_finding(self):
        bundled(self.root, plain(), rendering=self.named(content_sha256="c" * 64))

        answer = verifier.verify(self.root)

        self.assertEqual(["rendering_mismatch"], codes(answer))
        self.assertEqual(verifier.REPORT, answer["problems"][0]["path"])
        self.assertIn("cccccccccccc", answer["problems"][0]["detail"])

    def test_a_manifest_naming_a_rendering_and_shipping_no_report(self):
        files = {name: data for name, data in plain().items() if name != verifier.REPORT}
        bundled(self.root, files, required=["verify.py"], rendering=self.named())

        self.assertEqual(["rendering_unlisted"], codes(verifier.verify(self.root)))

    def test_a_bundle_that_claims_no_rendering_is_not_faulted_for_one(self):
        """A chain has no rendering row and a Finding nobody has read has none.
        Failing those would be failing a bundle for a claim it did not make."""
        bundled(self.root, plain())

        self.assertTrue(verifier.verify(self.root)["ok"])


class CommandTest(unittest.TestCase):
    """`python3 verify.py <bundle>`: one argument, one document, one status."""

    def setUp(self):
        self.root = scratch()

    def run_it(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = verifier.main(list(argv))
        return status, out.getvalue(), err.getvalue()

    def test_a_bundle_that_holds_exits_zero_and_prints_the_answer(self):
        bundled(self.root, plain())

        status, out, err = self.run_it(str(self.root))

        self.assertEqual(0, status)
        self.assertEqual("", err)
        self.assertTrue(json.loads(out)["ok"])

    def test_a_bundle_that_does_not_exits_one_and_says_which_file(self):
        bundled(self.root, plain())
        (self.root / "report.md").unlink()

        status, out, _ = self.run_it(str(self.root))

        self.assertEqual(1, status)
        self.assertEqual(["file_missing"], [p["code"] for p in json.loads(out)["problems"]])

    def test_the_wrong_number_of_arguments_exits_two_with_a_usage_line(self):
        for argv in ([], [str(self.root), "and another"]):
            status, out, err = self.run_it(*argv)

            self.assertEqual(2, status, argv)
            self.assertEqual("", out)
            self.assertIn("usage: verify.py <bundle-directory>", err)


class IndependenceTest(unittest.TestCase):
    """The property the whole module exists for, asked of its own source."""

    def test_the_verifier_imports_nothing_from_this_package(self):
        source = Path(verifier.__file__).read_text(encoding="utf-8")
        imports = sorted(
            line.strip()
            for line in source.splitlines()
            if line.startswith(("import ", "from ")) and "__future__" not in line
        )

        self.assertEqual(
            [
                "from collections.abc import Mapping",
                "from pathlib import Path",
                "import hashlib",
                "import json",
                "import re",
                "import sys",
            ],
            imports,
        )
        self.assertNotIn("redkraken", source)


if __name__ == "__main__":
    unittest.main()
