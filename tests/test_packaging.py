import sys
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from redkraken import doctor


ROOT = Path(__file__).resolve().parents[1]


class PackagingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_one_application_exposes_the_operator_command(self):
        self.assertEqual("redkraken", self.pyproject["project"]["name"])
        self.assertEqual({"rk": "redkraken.cli:main"}, self.pyproject["project"]["scripts"])
        self.assertEqual(["src"], self.pyproject["tool"]["setuptools"]["packages"]["find"]["where"])

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
            [f"{name}=={version}" for name, version in doctor.REQUIRED_DISTRIBUTIONS],
            self.pyproject["project"]["dependencies"],
        )

    def test_the_build_is_reproducible_from_pinned_requirements(self):
        requirements = self.pyproject["build-system"]["requires"]

        self.assertTrue(requirements)
        for requirement in requirements:
            self.assertIn("==", requirement, f"{requirement} is not an exact pin")


if __name__ == "__main__":
    unittest.main()
