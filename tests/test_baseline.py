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
            "baseline ok: classifications=10 regressions=7 artifacts=223\n",
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
