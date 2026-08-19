import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import check_baseline


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_baseline.py"
MANIFEST = ROOT / "baseline" / "v1-manifest.tsv"


def run_check(*arguments: str, repo: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--repo", str(repo), *arguments],
        cwd=ROOT,
        env={"PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
    )


def run_source(
    relative: str,
    content: str | bytes,
    executable: bool = False,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as temporary:
        repo = Path(temporary)
        source = repo / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            source.write_bytes(content)
        else:
            source.write_text(content, encoding="utf-8")
        if executable:
            source.chmod(0o755)
        return run_check(repo=repo)


class BaselineCliTest(unittest.TestCase):
    def test_checked_in_baseline_passes(self):
        result = run_check()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "baseline ok: classifications=10 regressions=7 adapters=10 artifacts=223 frozen\n",
            result.stdout,
        )

    def test_production_import_from_prototype_is_rejected(self):
        result = run_source("src/bad.py", "from docs.prototype import runtime\n")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/bad.py: forbidden import docs.prototype", result.stderr)

    def test_classified_production_tool_is_scanned(self):
        result = run_source("tools/bad.py", "from docs.prototype import runtime\n")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("tools/bad.py: forbidden import docs.prototype", result.stderr)

    def test_extensionless_python_import_from_docs_is_rejected(self):
        result = run_source(
            "deploy/runner",
            "#!/usr/bin/env python3\nfrom docs.prototype import runtime\n",
            executable=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("deploy/runner: forbidden import docs.prototype", result.stderr)

    def test_stored_prototype_path_is_rejected_before_execution(self):
        result = run_source(
            "src/loader.py",
            "from pathlib import Path\n"
            "import subprocess\n"
            "LEGACY = Path('docs/prototype/runtime.py')\n"
            "subprocess.run([LEGACY])\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/loader.py: forbidden tree reference", result.stderr)

    def test_exec_open_from_prototype_is_rejected(self):
        result = run_source(
            "src/loader.py",
            "exec(open('docs/prototype/runtime.py').read())\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/loader.py: forbidden tree reference", result.stderr)

    def test_absolute_prototype_path_is_rejected(self):
        result = run_source(
            "src/loader.py",
            "import subprocess\n"
            "subprocess.run(['/opt/redkraken/docs/prototype/runtime.py'])\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/loader.py: forbidden tree reference", result.stderr)

    def test_multi_parent_prototype_path_is_rejected(self):
        result = run_source(
            "src/loader.py",
            "from pathlib import Path\n"
            "LEGACY = Path('../../docs/prototype/runtime.py')\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/loader.py: forbidden tree reference", result.stderr)

    def test_bytes_prototype_path_is_rejected(self):
        result = run_source(
            "src/loader.py",
            "exec(open(b'docs/prototype/runtime.py').read())\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/loader.py: forbidden tree reference", result.stderr)

    def test_pyproject_entry_point_into_docs_is_rejected(self):
        result = run_source(
            "pyproject.toml",
            "[project.scripts]\nrk = 'docs.prototype.runtime:main'\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("pyproject.toml:2: forbidden tree dependency", result.stderr)

    def test_container_build_cannot_copy_documentation_tree(self):
        result = run_source(
            "deploy/Dockerfile",
            "FROM python:3\nCOPY docs /app/docs\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("deploy/Dockerfile:2: forbidden tree dependency", result.stderr)

    def test_shipped_prose_may_use_a_forbidden_root_as_an_english_word(self):
        # The Skill and Playbook corpora are markdown inside `src`, so they are
        # scanned, and in a reference -- maintainer prose no model can open --
        # a bare word is a word: "prototype pollution" is a defect class and
        # "the docs" is a noun. This is the exemption the Python scan already
        # makes for docstrings.
        result = run_source(
            "src/redkraken/skills/a-technique/references/pack.md",
            "A deep merge is the prototype pollution shape, and the docs say so.\n",
        )

        self.assertNotIn("forbidden tree dependency", result.stderr)

    def test_a_skill_body_is_not_prose_and_keeps_the_bare_token_sweep(self):
        # The exemption is for text a person reads. `SKILL.md` is text a model
        # reads, so a bare root in one is an instruction to use it -- and `/tmp`
        # is spelled without a separator, which only this sweep catches.
        result = run_source(
            "src/redkraken/skills/a-technique/SKILL.md",
            "Write the intermediate bundle to /tmp and read it back.\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "src/redkraken/skills/a-technique/SKILL.md:1: forbidden tree dependency",
            result.stderr,
        )

    def test_shipped_prose_may_not_point_into_a_forbidden_tree(self):
        # The other half: dropping the bare-token sweep must not drop the check.
        result = run_source(
            "src/redkraken/skills/a-technique/references/pack.md",
            "The rule this replaces is in docs/prototype/SKILL-FORMAT.md.\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "src/redkraken/skills/a-technique/references/pack.md:1: forbidden tree dependency",
            result.stderr,
        )

    def test_python_encoding_cookie_does_not_bypass_boundary(self):
        result = run_source(
            "src/latin1.py",
            b"# -*- coding: latin-1 -*-\nLABEL = 'caf\xe9'\nfrom docs.prototype import runtime\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/latin1.py: forbidden import docs.prototype", result.stderr)

    def test_production_symlink_into_prototype_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            prototype = repo / "docs" / "prototype" / "runtime.py"
            prototype.parent.mkdir(parents=True)
            prototype.write_text("VALUE = 1\n", encoding="utf-8")
            source = repo / "src" / "runtime.py"
            source.parent.mkdir()
            source.symlink_to(prototype)

            result = run_check(repo=repo)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/runtime.py: forbidden symlink target", result.stderr)

    def test_nonproduction_shipping_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            claim = repo / "docs" / "prototype" / "claim" / "README.md"
            claim.parent.mkdir(parents=True)
            claim.write_text("# Claim\n\nStatus: implemented\n", encoding="utf-8")

            errors = check_baseline.implementation_claim_errors(
                repo,
                [{"path": "docs/prototype/claim", "classification": "validated_prototype"}],
            )

        self.assertEqual(
            ["docs/prototype/claim/README.md:3: non-production work claims shipping status"],
            errors,
        )

    def test_a_second_network_client_is_rejected_where_it_appears(self):
        # Story 221: the alternate path is not opened by a commit that says so,
        # it is opened by three lines that read as housekeeping.
        result = run_source(
            "src/redkraken/collector.py",
            "import http.client\n\n\ndef fetch(host):\n    return http.client.HTTPConnection(host)\n",
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "src/redkraken/collector.py: reaches http.client outside the approved adapters",
            result.stderr,
        )

    def test_a_client_imported_by_name_is_the_same_client(self):
        result = run_source(
            "src/redkraken/collector.py",
            'import importlib\n\n\ndef fetch():\n    return importlib.import_module("socket")\n',
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("reaches socket outside the approved adapters", result.stderr)

    def test_a_receipt_written_from_python_is_rejected(self):
        result = run_source(
            "src/redkraken/collector.py",
            'SAVE = "INSERT INTO receipts (program_id) VALUES ($1)"\n',
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "src/redkraken/collector.py:1: a Receipt is written by the door, not by Python",
            result.stderr,
        )

    def test_a_fixture_may_serve_and_may_not_dial(self):
        listening = run_source(
            "src/redkraken/fixtures/made-up-pair/app.py",
            "from http.server import ThreadingHTTPServer\n",
        )
        dialling = run_source(
            "src/redkraken/fixtures/made-up-pair/app.py",
            "import urllib.request\n",
        )

        self.assertEqual(0, listening.returncode, listening.stderr)
        self.assertNotEqual(0, dialling.returncode)
        self.assertIn(
            "src/redkraken/fixtures/made-up-pair/app.py: a fixture serves, "
            "and this one reaches urllib.request",
            dialling.stderr,
        )

    def test_an_adapter_that_stopped_speaking_is_delisted_rather_than_kept(self):
        # An allowlist nobody prunes ends up naming half the tree, and then it
        # permits rather than bounds.
        adapters = {"src/redkraken/quiet.py": "nothing, as it turns out"}
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / "src" / "redkraken").mkdir(parents=True)
            (repo / "src" / "redkraken" / "quiet.py").write_text("import json\n", encoding="utf-8")

            errors = check_baseline.alternate_path_errors(repo, ["src"], [], adapters)

        self.assertEqual(
            ["src/redkraken/quiet.py: listed as a network adapter but reaches no wire"], errors
        )

    def test_an_adapter_the_registry_does_not_hold_is_refused_by_the_registry(self):
        status = json.loads((ROOT / "baseline" / "status.json").read_text(encoding="utf-8"))
        for change in (
            {"src/redkraken/nowhere.py": "a file that is not there"},
            {"tests/test_baseline.py": "a file outside the production tree"},
            {"src/redkraken/pg.py": "  "},
        ):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                registry = Path(temporary) / "status.json"
                registry.write_text(json.dumps({**status, "network_adapters": change}))

                with self.assertRaises(check_baseline.BaselineError):
                    check_baseline.read_status(registry)

    def test_missing_v1_corpus_fails_without_rewriting_manifest(self):
        before = MANIFEST.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            result = run_check("--v1", temporary)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("v1 census differs from frozen manifest", result.stderr)
        self.assertEqual(before, MANIFEST.read_bytes())

    def test_duplicate_manifest_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary) / "manifest.tsv"
            lines = MANIFEST.read_text(encoding="utf-8").splitlines()
            duplicate.write_text("\n".join([*lines, lines[1]]) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(check_baseline.BaselineError, "duplicate manifest source"):
                check_baseline.read_manifest(duplicate)

    def test_emptying_the_registry_does_not_empty_the_scan(self):
        registry = check_baseline.read_status()
        scanned = [
            *registry["production_roots"],
            *[
                entry["path"]
                for entry in registry["classifications"]
                if entry["classification"] == "production"
            ],
        ]

        self.assertEqual([], check_baseline.unscanned_shipped_roots(ROOT, scanned))
        self.assertEqual(["src"], check_baseline.unscanned_shipped_roots(ROOT, []))

    def test_forbidden_roots_must_cover_the_prototype_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry = check_baseline.read_status()
            registry["forbidden_dependency_roots"] = ["one", "two", "three", "four"]
            renamed = Path(temporary) / "status.json"
            renamed.write_text(json.dumps(registry), encoding="utf-8")

            with self.assertRaisesRegex(
                check_baseline.BaselineError, "prototype tree is reachable from production"
            ):
                check_baseline.read_status(renamed)

    def test_manifest_comparison_names_each_kind_of_drift(self):
        expected = [
            {"kind": "agent_definition", "source": "a", "lines": "1", "sha256": "1"},
            {"kind": "agent_definition", "source": "b", "lines": "1", "sha256": "2"},
        ]
        actual = [
            {"kind": "agent_definition", "source": "b", "lines": "2", "sha256": "3"},
            {"kind": "agent_definition", "source": "c", "lines": "1", "sha256": "4"},
        ]

        self.assertEqual(
            ["missing v1 artifact: a", "added v1 artifact: c", "changed v1 artifact: b"],
            check_baseline.compare_manifest(expected, actual),
        )


if __name__ == "__main__":
    unittest.main()
