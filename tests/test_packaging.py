import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
import unittest

import redkraken
from redkraken import doctor
from tests import ROOT
from tests.fixtures import VALID, scratch, write


def environment() -> dict[str, str]:
    """A clean environment, so an installed command cannot reach the checkout."""
    keep = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
    return {name: os.environ[name] for name in keep if name in os.environ}


class PackagingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_one_application_exposes_the_operator_command(self):
        self.assertEqual("redkraken", self.pyproject["project"]["name"])
        self.assertEqual({"rk": "redkraken.cli:main"}, self.pyproject["project"]["scripts"])
        self.assertEqual(["src"], self.pyproject["tool"]["setuptools"]["packages"]["find"]["where"])

    def test_only_the_application_is_shipped(self):
        self.assertEqual(
            ["redkraken*"], self.pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
        )

    def test_the_version_has_one_source(self):
        self.assertEqual(
            {"attr": "redkraken.__version__"},
            self.pyproject["tool"]["setuptools"]["dynamic"]["version"],
        )
        self.assertEqual(["version"], self.pyproject["project"]["dynamic"])

    def test_the_supported_interpreter_range_is_declared_once(self):
        self.assertEqual(doctor.supported_python(), self.pyproject["project"]["requires-python"])

    def test_production_dependencies_are_declared_as_exact_pins(self):
        self.assertEqual(
            [f"{name}=={version}" for name, version in doctor.REQUIREMENTS.distributions],
            self.pyproject["project"]["dependencies"],
        )

    def test_the_build_is_reproducible_from_pinned_requirements(self):
        requirements = self.pyproject["build-system"]["requires"]

        self.assertTrue(requirements)
        for requirement in requirements:
            self.assertIn("==", requirement, f"{requirement} is not an exact pin")


class InstallationTest(unittest.TestCase):
    """The documented installation path, run against a pristine copy.

    Everything else drives the command line from the source tree, which proves
    the code but not the packaging. This installs the application the way the
    README tells an operator to and then runs the shipped `rk` script.
    """

    def buildable(self) -> None:
        """Skip unless this machine can build offline against the pinned backend.

        Without network access the build uses the interpreter's own setuptools,
        so a machine carrying a different one cannot satisfy the pin. That is a
        fact about the machine, not about the packaging under test.
        """
        if importlib.util.find_spec("ensurepip") is None:
            self.skipTest("the documented installation path needs ensurepip")
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        for requirement in pyproject["build-system"]["requires"]:
            name, _, pinned = requirement.partition("==")
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                self.skipTest(f"the offline installation path needs {requirement}")
            if installed != pinned:
                self.skipTest(f"the offline installation path needs {requirement}, not {installed}")

    def test_the_installed_command_reports_its_version_and_diagnoses(self):
        self.buildable()

        checkout = scratch() / "checkout"
        checkout.mkdir()
        for name in ("pyproject.toml", "README.md"):
            shutil.copy(ROOT / name, checkout / name)
        shutil.copytree(
            ROOT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__")
        )
        venv = checkout / ".venv"
        # A home of its own, so an operator's pip configuration cannot decide
        # what this test installs or where it looks for it.
        installer = environment() | {"HOME": str(scratch()), "PIP_CONFIG_FILE": os.devnull}

        created = subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
            env=installer,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, created.returncode, created.stderr)

        installed = subprocess.run(
            [
                str(venv / "bin" / "pip"),
                "install",
                "--no-build-isolation",
                "--check-build-dependencies",
                "--no-index",
                "--no-cache-dir",
                ".",
            ],
            cwd=str(checkout),
            env=installer,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)

        rk = str(venv / "bin" / "rk")
        version = subprocess.run(
            [rk, "--version"], env=environment(), text=True, capture_output=True, check=False
        )
        self.assertEqual(f"rk {redkraken.__version__}\n", version.stdout)

        report = subprocess.run(
            [rk, "doctor", "--config", str(write(VALID))],
            env=environment(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, report.returncode, report.stderr)
        self.assertTrue(json.loads(report.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
