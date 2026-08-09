import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import redkraken
from redkraken.outcome import (
    EXIT_INVALID_CONFIGURATION,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
    EXIT_USAGE,
)
from tests.test_config import VALID


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"

#: Records the effects `rk doctor` promises never to have, rather than raising
#: inside the hook, so a failure names the event that happened.
DRIVER = """
import json, os, sys

observed = []


def hook(event, arguments):
    if event.startswith((
        "socket.", "urllib.", "http.client", "ftplib.", "smtplib.",
        "subprocess.", "os.exec", "os.system", "os.spawn", "os.fork",
    )):
        observed.append(event)
    elif event == "open":
        mode, flags = arguments[1], arguments[2]
        written = (
            any(character in mode for character in "wxa+")
            if mode
            else bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        )
        if written:
            observed.append("open:" + str(arguments[0]))


sys.addaudithook(hook)

from redkraken.cli import main

code = main(sys.argv[1:])
loaded = sorted({getattr(module, "__file__", None) or "" for module in sys.modules.values()})
sys.stderr.write(json.dumps({"exit": code, "events": observed, "loaded": loaded}))
"""


def environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(SOURCE),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "redkraken", *arguments],
        cwd=str(cwd or ROOT),
        env=environment(),
        text=True,
        capture_output=True,
        check=False,
    )


def observe(*arguments: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", DRIVER, *arguments],
        cwd=str(ROOT),
        env=environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stderr)


def write(text: str, name: str = "program.toml") -> Path:
    source = Path(tempfile.mkdtemp()) / name
    source.write_text(text, encoding="utf-8")
    return source


class VersionTest(unittest.TestCase):
    def test_version_is_reported_in_a_stable_form(self):
        result = run("--version")

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertEqual(f"rk {redkraken.__version__}\n", result.stdout)


class DoctorCommandTest(unittest.TestCase):
    def test_valid_configuration_reports_readiness(self):
        result = run("doctor", "--config", str(write(VALID)))

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual("acme-web", report["configuration"]["program_name"])
        self.assertEqual([], report["violations"])

    def test_readiness_is_reported_without_a_configuration(self):
        result = run("doctor")

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["configuration"])

    def test_invalid_configuration_exits_three(self):
        result = run("doctor", "--config", str(write(VALID.replace("[budgets]\n", "[budgets]\nspend = 1\n"))))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(
            [{"code": "invalid_configuration", "source": "config:budgets.spend", "detail": "unknown key"}],
            report["violations"],
        )

    def test_absent_configuration_file_exits_three(self):
        result = run("doctor", "--config", str(Path(tempfile.mkdtemp()) / "absent.toml"))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)

    def test_unsupported_configuration_version_exits_four(self):
        result = run("doctor", "--config", str(write(VALID.replace("schema_version = 1", "schema_version = 9"))))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, result.returncode)
        self.assertEqual(
            ["unsupported_version"],
            [violation["code"] for violation in json.loads(result.stdout)["violations"]],
        )

    def test_missing_command_is_a_usage_error(self):
        result = run()

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("usage: rk", result.stderr)

    def test_unknown_command_is_a_usage_error(self):
        result = run("hunt")

        self.assertEqual(EXIT_USAGE, result.returncode)


class ContainmentTest(unittest.TestCase):
    def test_diagnosis_creates_no_state_and_sends_no_traffic(self):
        source = write(VALID)

        observed = observe("doctor", "--config", str(source))

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_OK, observed["exit"])
        self.assertEqual(["program.toml"], [entry.name for entry in source.parent.iterdir()])

    def test_refusal_creates_no_state_and_sends_no_traffic(self):
        observed = observe("doctor", "--config", str(write("schema_version = 4\n")))

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_UNSUPPORTED_VERSION, observed["exit"])

    def test_no_module_is_loaded_from_a_nonproduction_tree(self):
        observed = observe("doctor", "--config", str(write(VALID)))

        outside = [
            name
            for name in observed["loaded"]
            if name and not Path(name).resolve().is_relative_to(SOURCE)
            and Path(name).resolve().is_relative_to(ROOT)
        ]
        self.assertEqual([], outside)

    def test_secret_bearing_references_never_reach_the_output(self):
        text = VALID.replace("slot://identity/member", "slot://identity/s3cr3t-sentinel")

        result = run("doctor", "--config", str(write(text)))

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)

    def test_unparsable_configuration_is_refused_without_echoing_its_content(self):
        text = 'schema_version = 1\n[program]\nname = "acme"\ntoken "s3cr3t-sentinel"\n'

        result = run("doctor", "--config", str(write(text)))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)


if __name__ == "__main__":
    unittest.main()
