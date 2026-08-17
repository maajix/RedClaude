"""What `rk import` refuses before it has a connection to refuse it with.

The import splits the same way the export does. One half needs rows -- which
scope class a v1 host earns here, what a hint rolls up to, whether the bytes an
export claims are bytes this Program holds -- and is asked in `test_database`,
against a compiled scope and the real writer. The other half is arithmetic over
a directory: is this an export, is it the export it says it is, and are the four
lists in it lists. That half is here, where a failure names the function rather
than the fixture.

Criterion 1 is the reason this file exists at all. "Import accepts only an
explicit operator-selected export ... and never crawls live engagement
directories implicitly" is a property of what the reader is given, not of what
it finds, so every case below hands it one path and no search of any kind is
available for it to fall back on.
"""

import json
import unittest
from pathlib import Path

from redkraken import legacy, store, verifier
from tests.fixtures import EXPORT_BLOB as BLOB
from tests.fixtures import EXPORT_BODY as BODY
from tests.fixtures import EXPORT_LISTS as LISTS
from tests.fixtures import export as bundle
from tests.fixtures import scratch


PROGRAM = "acme-web"
EXPORTED = "2026-03-01T09:15:00Z"


class ExportReadTest(unittest.TestCase):
    """`read`: one directory, held against its own manifest and nothing else."""

    def refusal(self, where: Path) -> legacy.Refused:
        with self.assertRaises(legacy.Refused) as raised:
            legacy.read(where)
        return raised.exception

    def test_a_well_formed_export_reads_as_its_four_lists(self):
        export = legacy.read(bundle())

        self.assertEqual(legacy.SCHEMA, export.schema)
        self.assertEqual(PROGRAM, export.program)
        self.assertEqual(EXPORTED, export.exported_at)
        self.assertEqual(sorted(legacy.PAYLOAD), sorted(export.lists))
        self.assertEqual(LISTS["surface"], export.lists["surface"])

    def test_what_identifies_an_export_is_the_hash_of_its_own_manifest(self):
        """Criterion 2's attribution, and it has to be derived rather than read.

        A source hash an export states about itself is a field somebody can
        write anything into, and every row an import writes hangs off it.
        """
        where = bundle()
        document = json.loads((where / legacy.MANIFEST).read_text(encoding="utf-8"))

        export = legacy.read(where)

        self.assertEqual(verifier.manifest_digest(document), export.digest)
        self.assertEqual(
            {"schema": legacy.SCHEMA, "source_sha256": export.digest, "exported_at": EXPORTED},
            export.source,
        )

    def test_two_exports_of_the_same_state_have_the_same_identity(self):
        """Which is what makes idempotence a property of the export rather than
        of the directory it was unpacked into."""
        self.assertEqual(legacy.read(bundle()).digest, legacy.read(bundle()).digest)

    def test_a_directory_with_no_manifest_is_not_an_export(self):
        where = scratch() / "empty"
        where.mkdir()

        refusal = self.refusal(where)

        self.assertEqual(legacy.MANIFEST, refusal.path)
        self.assertIn("there is no manifest.json", refusal.detail)

    def test_a_schema_this_reader_does_not_know_stops_the_read(self):
        refusal = self.refusal(bundle(schema="rk2-v1-export/2"))

        self.assertEqual(legacy.MANIFEST, refusal.path)
        self.assertIn("rk2-v1-export/2", refusal.detail)
        self.assertIn(legacy.SCHEMA, refusal.detail)

    def test_a_manifest_edited_after_it_was_written_is_refused(self):
        where = bundle()
        document = json.loads((where / legacy.MANIFEST).read_text(encoding="utf-8"))
        document["program"] = "somebody-else"
        (where / legacy.MANIFEST).write_text(json.dumps(document), encoding="utf-8")

        refusal = self.refusal(where)

        self.assertEqual("the manifest is not what it says it is", refusal.detail)

    def test_a_manifest_that_states_no_program_or_no_time_is_refused(self):
        for key in ("program", "exported_at"):
            with self.subTest(key):
                refusal = self.refusal(bundle(**{key: "   "}))

                self.assertEqual(f"the manifest states no {key}", refusal.detail)

    def test_a_named_file_that_is_not_there_is_refused(self):
        where = bundle()
        (where / BLOB).unlink()

        refusal = self.refusal(where)

        self.assertEqual(BLOB, refusal.path)
        self.assertIn("it is not here", refusal.detail)

    def test_a_named_file_of_the_wrong_length_is_refused_before_it_is_hashed(self):
        where = bundle()
        (where / BLOB).write_bytes(BODY + b" ")

        refusal = self.refusal(where)

        self.assertEqual(BLOB, refusal.path)
        self.assertIn(f"{len(BODY)} byte(s) recorded, {len(BODY) + 1} here", refusal.detail)

    def test_a_named_file_of_the_right_length_and_the_wrong_bytes_is_refused(self):
        where = bundle()
        edited = bytearray(BODY)
        edited[-2:] = b"X}"
        (where / BLOB).write_bytes(bytes(edited))

        refusal = self.refusal(where)

        self.assertEqual(BLOB, refusal.path)
        self.assertIn(store.digest(BODY), refusal.detail)

    def test_a_file_the_manifest_does_not_name_is_refused(self):
        """`verifier._missing_from_manifest`'s argument, read in the other
        direction. Every per-file check passes on a directory somebody added a
        file to, and what arrived is no longer the export that was signed."""
        where = bundle()
        stray = f"{Path(BLOB).parent.as_posix()}/a2.json"
        (where / stray).write_bytes(b"{}")

        refusal = self.refusal(where)

        self.assertEqual(stray, refusal.path)
        self.assertEqual("it is in the export and the manifest does not name it", refusal.detail)

    def test_an_artifact_the_manifest_names_and_the_export_omits_is_not_a_read_failure(self):
        """The `absent` state, which is most of what a real v1 export looks like:
        v1 pruned its store and kept the rows. It is a disposition rather than a
        refusal, because refusing here would make an honest export unreadable."""
        export = legacy.read(bundle(blobs={}, drop=BLOB))

        self.assertNotIn(BLOB, export.files)
        self.assertEqual([{"ref": "A1", "path": BLOB, "sha256": store.digest(BODY)}],
                         export.lists["artifacts"])

    def test_a_manifest_that_names_none_of_the_four_documents_is_refused(self):
        for key, name in legacy.PAYLOAD.items():
            with self.subTest(key):
                refusal = self.refusal(bundle(drop=name))

                self.assertEqual(legacy.MANIFEST, refusal.path)
                self.assertEqual(f"the manifest names no {name}", refusal.detail)

    def test_a_manifest_with_no_file_list_at_all_is_refused(self):
        where = scratch() / "listless"
        where.mkdir()
        document = {"schema": legacy.SCHEMA, "program": PROGRAM, "exported_at": EXPORTED}
        (where / legacy.MANIFEST).write_text(
            json.dumps(document | {"digest": verifier.manifest_digest(document)}),
            encoding="utf-8",
        )

        self.assertEqual("the manifest names no files", self.refusal(where).detail)

    def test_a_manifest_entry_naming_a_path_outside_the_export_is_refused(self):
        for path in ("/etc/passwd", "../elsewhere/surface.json"):
            with self.subTest(path):
                where = bundle()
                document = json.loads((where / legacy.MANIFEST).read_text(encoding="utf-8"))
                document["files"].append({"path": path, "bytes": 0, "sha256": store.digest(b"")})
                document["digest"] = verifier.manifest_digest(
                    {k: v for k, v in document.items() if k != "digest"}
                )
                (where / legacy.MANIFEST).write_text(json.dumps(document), encoding="utf-8")

                refusal = self.refusal(where)

                self.assertEqual(path, refusal.path)
                self.assertIn("outside the export", refusal.detail)

    def test_a_payload_that_is_not_a_list_of_records_is_refused(self):
        refusal = self.refusal(bundle(lists={"surface": {"S1": "an object"}}))

        self.assertEqual(legacy.PAYLOAD["surface"], refusal.path)
        self.assertEqual("it is not a list of records", refusal.detail)

    def test_a_record_with_no_ref_is_refused_where_it_can_still_be_pointed_at(self):
        """A record with no handle is a record no disposition can be reported
        about, which is criterion 5's whole subject. Refusing at read time names
        the ordinal in the file; refusing in the writer names nothing useful."""
        refusal = self.refusal(bundle(lists={"findings": [{"ref": "V-1"}, {"severity": "high"}]}))

        self.assertEqual(legacy.PAYLOAD["findings"], refusal.path)
        self.assertEqual("record 1 carries no ref", refusal.detail)

    def test_a_payload_document_that_is_not_json_is_refused(self):
        where = bundle()
        broken = b"{not json"
        (where / legacy.PAYLOAD["scope"]).write_bytes(broken)
        document = json.loads((where / legacy.MANIFEST).read_text(encoding="utf-8"))
        for entry in document["files"]:
            if entry["path"] == legacy.PAYLOAD["scope"]:
                entry.update(bytes=len(broken), sha256=store.digest(broken))
        document["digest"] = verifier.manifest_digest(
            {k: v for k, v in document.items() if k != "digest"}
        )
        (where / legacy.MANIFEST).write_text(json.dumps(document), encoding="utf-8")

        refusal = self.refusal(where)

        self.assertEqual(legacy.PAYLOAD["scope"], refusal.path)
        self.assertIn("not readable as JSON", refusal.detail)

    def test_the_reader_needs_no_database_no_store_and_no_configuration(self):
        """Criterion 1 as a property of the module rather than of a run.

        Everything above ran with no connection string, no artifact root and no
        Program, which is what makes "the operator selected this directory" the
        only way an export is ever reached.
        """
        source = Path(legacy.__file__).read_text(encoding="utf-8")
        body = source.split("def read(", 1)[1].split("\ndef run(", 1)[0]

        for reached in ("connect", "execute", "environ", "getenv", "cwd()", "home()"):
            with self.subTest(reached):
                self.assertNotIn(reached, body)
        # The one walk there is, and it is rooted at the argument. A second one,
        # or one rooted anywhere else, is the implicit crawl criterion 1 names.
        self.assertEqual(1, body.count(".rglob("))
        self.assertIn('source.rglob("*")', body)


class ExportShapeTest(unittest.TestCase):
    """The vocabulary the two halves of the command agree on."""

    def test_the_four_states_are_the_four_the_writer_checks(self):
        """`record_v1_import` refuses a state outside this tuple, and the
        reporting in `_filed` counts by it. Two spellings of a closed set is the
        way an import silently stops counting one of them."""
        self.assertEqual(("retained", "redacted", "stale", "absent"), legacy.STATES)

    def test_the_kind_an_import_files_under_is_not_one_an_operator_can_ask_for(self):
        """The one thing that turns a demoted row into imported Surface is
        whether a reference of this kind exists, so `rk artifact put --kind`
        offering it would let an operator promote anything by hand."""
        from redkraken import artifact

        self.assertNotIn(legacy.KIND, artifact.KINDS)
