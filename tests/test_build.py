import hashlib
import json
import unittest
from pathlib import Path

from redkraken import build, outcome, pg, proxy
from tests.fixtures import scratch


#: A package tree in miniature: a top-level module, a migration, a fixture app,
#: and two files no digest covers (a document and a measurement). Small on
#: purpose -- what each test varies is the one module under it.
SAMPLE = {
    "artifact.py": b"print('artifact')\n",
    "migrations/0001_first.sql": b"select 1;\n",
    "fixtures/demo/app.py": b"app = None\n",
    "migrations/README.md": b"not a module\n",
    "measurements/auth.json": b"{}\n",
}


def tree(files: dict[str, bytes]) -> Path:
    """Write `files` into a scratch directory and hand back its root."""
    root = scratch()
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return root


def manifest_for(files: dict[str, bytes], **overrides) -> dict:
    """The manifest `build_backend` would write for `files`."""
    body = {
        "schema_version": build.SCHEMA_VERSION,
        "revision": "a1b2c3d4" * 5,
        "dirty": False,
        "built_at": "2026-08-17T00:00:00Z",
        "modules": {
            relative: hashlib.sha256(data).hexdigest()
            for relative, data in files.items()
            if relative.endswith(build.HASHED_SUFFIXES)
        },
    }
    body.update(overrides)
    return body


def installed(files: dict[str, bytes], **overrides) -> Path:
    """A fabricated install: the tree plus the manifest that matches it."""
    root = tree(files)
    (root / build.MANIFEST).write_text(json.dumps(manifest_for(files, **overrides)))
    return root


class ManifestReadingTest(unittest.TestCase):
    """`build.verify` over trees this test builds by hand.

    Criterion 3, made reachable: a drifted install is a directory fabricated
    here -- no wheel, no pip, no git checkout -- so a regression in the digest
    check fails in the ordinary suite rather than only in an install nobody
    runs. Criterion 4 is about the defect rather than the detector, so its test
    is the one in `test_packaging` that builds a wheel over a poisoned staging
    directory -- which needs a build, but still no checkout.
    """

    def test_a_tree_with_no_manifest_is_running_from_source(self):
        verification = build.verify(tree(SAMPLE))

        self.assertTrue(verification.source_mode)
        self.assertTrue(verification.ok)
        self.assertIsNone(verification.problem())
        # Three modules: the .py and .sql. The document and the measurement are
        # shipped but are not code, so no digest covers them.
        self.assertEqual(3, verification.module_count)

    def test_a_manifest_that_matches_the_disk_reports_its_revision(self):
        verification = build.verify(installed(SAMPLE))

        self.assertFalse(verification.source_mode)
        self.assertTrue(verification.ok)
        self.assertIsNone(verification.problem())
        self.assertEqual("a1b2c3d4" * 5, verification.revision)
        self.assertEqual(3, verification.module_count)
        self.assertEqual(64, len(verification.tree_digest))

    def test_a_changed_module_is_named_as_the_first_difference(self):
        root = installed(SAMPLE)
        (root / "artifact.py").write_bytes(b"print('tampered')\n")

        verification = build.verify(root)

        self.assertFalse(verification.ok)
        self.assertEqual("artifact.py", verification.mismatch)
        source, detail = verification.problem()
        self.assertEqual("build:artifact.py", source)
        self.assertIn("artifact.py", detail)

    def test_a_module_the_manifest_names_but_the_disk_lacks_is_a_mismatch(self):
        root = installed(SAMPLE)
        (root / "migrations" / "0001_first.sql").unlink()

        self.assertEqual("migrations/0001_first.sql", build.verify(root).mismatch)

    def test_a_module_on_disk_the_manifest_never_listed_is_a_mismatch(self):
        root = installed(SAMPLE)
        (root / "aaa_added.py").write_bytes(b"x = 1\n")  # sorts before artifact.py

        self.assertEqual("aaa_added.py", build.verify(root).mismatch)

    def test_an_unreadable_manifest_is_a_refusal_not_an_exception(self):
        root = tree(SAMPLE)
        (root / build.MANIFEST).write_text("{ not json")

        verification = build.verify(root)

        self.assertFalse(verification.ok)
        self.assertIsNone(verification.mismatch)
        self.assertIsNotNone(verification.error)
        self.assertEqual(f"build:{build.MANIFEST}", verification.problem()[0])

    def test_a_manifest_from_a_schema_this_build_cannot_read_is_refused(self):
        verification = build.verify(installed(SAMPLE, schema_version=build.SCHEMA_VERSION + 1))

        self.assertFalse(verification.ok)
        self.assertIn("schema", verification.error)

    def test_the_walk_ignores_pycache_so_a_compiled_artefact_is_not_a_module(self):
        root = installed(SAMPLE)
        cache = root / "__pycache__"
        cache.mkdir()
        (cache / "artifact.cpython-314.pyc").write_bytes(b"\x00\x01")

        self.assertTrue(build.verify(root).ok)

    def test_the_tree_digest_does_not_depend_on_creation_order(self):
        forward = build.verify(tree({"a.py": b"1\n", "b.py": b"2\n"})).tree_digest
        reverse = build.verify(tree({"b.py": b"2\n", "a.py": b"1\n"})).tree_digest

        self.assertEqual(forward, reverse)

    def test_a_manifest_missing_what_verify_reads_is_refused_not_a_crash(self):
        # `verify` reads the revision straight off the manifest, so a manifest
        # without one must come back as a refusal: a KeyError out of the door's
        # first statement is a crash where the whole point was a refusal.
        root = tree(SAMPLE)
        body = manifest_for(SAMPLE)
        del body["revision"]
        (root / build.MANIFEST).write_text(json.dumps(body))

        verification = build.verify(root)

        self.assertFalse(verification.ok)
        self.assertIn("revision", verification.error)


class RecordedAssertionTest(unittest.TestCase):
    """One install, one assertion name, whichever caller asks for it."""

    def test_an_install_that_matches_holds_the_build_assertion(self):
        ledger = outcome.Ledger()

        verification = build.record(ledger, installed(SAMPLE))

        self.assertTrue(verification.ok)
        self.assertEqual([], ledger.violations)
        self.assertEqual([build.ASSERTION], [one.name for one in ledger.assertions])
        self.assertTrue(ledger.assertions[0].ok)

    def test_an_install_that_drifted_fails_the_same_assertion(self):
        root = installed(SAMPLE)
        (root / "artifact.py").write_bytes(b"print('tampered')\n")
        ledger = outcome.Ledger()

        build.record(ledger, root)

        self.assertFalse(ledger.assertions[0].ok)
        self.assertEqual(build.ASSERTION, ledger.assertions[0].name)
        self.assertEqual(
            [(outcome.BUILD_MISMATCH, "build:artifact.py")],
            [(one.code, one.source) for one in ledger.violations],
        )


class InstalledPackageTest(unittest.TestCase):
    def test_the_running_harness_verifies_against_its_own_install(self):
        # A source checkout is source mode; a wheel is a match. Either way the
        # harness must never report its own install as drifted.
        self.assertTrue(build.verify().ok)


class ProxyServeBuildTest(unittest.TestCase):
    def test_serve_refuses_to_listen_when_the_install_does_not_match(self):
        root = installed(SAMPLE)
        (root / "artifact.py").write_bytes(b"print('tampered')\n")
        settings = pg.settings_from_url("postgres://rk:rk@127.0.0.1:5432/rk")

        report = proxy.serve(settings, root=scratch(), build_anchor=root)

        self.assertFalse(report.ok)
        self.assertEqual(outcome.EXIT_BUILD_MISMATCH, report.exit_code)
        self.assertEqual(proxy.SERVE, report.command)
        self.assertEqual(["build:artifact.py"], [item.source for item in report.violations])
        self.assertIsNone(report.facts["endpoint"])


if __name__ == "__main__":
    unittest.main()
