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


class BaselineCliTest(unittest.TestCase):
    def test_checked_in_baseline_passes(self):
        result = run_check()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "baseline ok: classifications=9 regressions=6 artifacts=223\n",
            result.stdout,
        )

    def test_production_import_from_prototype_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            source = repo / "src" / "bad.py"
            source.parent.mkdir()
            source.write_text("from docs.prototype import runtime\n", encoding="utf-8")

            result = run_check(repo=repo)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("src/bad.py: forbidden import docs.prototype", result.stderr)

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
