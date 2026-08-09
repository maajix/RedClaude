import importlib.metadata
import json
import sys
import unittest

from redkraken import doctor
from redkraken.doctor import Requirements
from redkraken.outcome import (
    EXIT_INVALID_CONFIGURATION,
    EXIT_MISSING_DEPENDENCY,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
)
from tests.fixtures import VALID, scratch, write


def installed_distribution() -> tuple[str, str] | None:
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name and distribution.version:
            return name, distribution.version
    return None


class ReadinessTest(unittest.TestCase):
    def test_ready_runtime_and_configuration_report_success(self):
        diagnosis = doctor.diagnose(write(VALID))

        self.assertTrue(diagnosis.ok)
        self.assertEqual(EXIT_OK, diagnosis.exit_code)
        self.assertEqual((), diagnosis.violations)
        self.assertTrue(all(assertion.ok for assertion in diagnosis.assertions))
        self.assertEqual("acme-web", diagnosis.as_dict()["configuration"]["program_name"])

    def test_readiness_is_reported_without_a_configuration(self):
        diagnosis = doctor.diagnose(None)

        self.assertTrue(diagnosis.ok)
        self.assertIsNone(diagnosis.as_dict()["configuration"])
        self.assertIn("configuration", [assertion.name for assertion in diagnosis.assertions])

    def test_result_names_versions_and_is_serialisable(self):
        report = doctor.diagnose(write(VALID)).as_dict()

        self.assertEqual(1, report["schema_version"])
        self.assertEqual("doctor", report["command"])
        self.assertEqual(doctor.supported_python(), report["supported_python"])
        self.assertEqual(".".join(str(part) for part in sys.version_info[:3]), report["python_version"])
        self.assertEqual(report, json.loads(json.dumps(report)))

    def test_diagnostic_output_carries_hashes_but_no_references(self):
        rendered = json.dumps(doctor.diagnose(write(VALID)).as_dict())
        configuration = json.loads(rendered)["configuration"]

        self.assertEqual(64, len(configuration["source_sha256"]))
        self.assertEqual(64, len(configuration["canonical_sha256"]))
        self.assertNotIn("slot://identity/member", rendered)
        self.assertNotIn("slot://header/bounty-id", rendered)


class DistinctOutcomeTest(unittest.TestCase):
    def test_invalid_configuration_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(write(VALID.replace('[program]\n', '[program]\nowner = "someone"\n')))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertEqual(["config:program.owner"], [item.source for item in diagnosis.violations])
        self.assertIsNone(diagnosis.as_dict()["configuration"])

    def test_unsupported_configuration_version_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(write(VALID.replace("schema_version = 1", "schema_version = 2")))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_unsupported_interpreter_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(None, python_version=(3, 15, 0))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)
        self.assertEqual(["runtime:python"], [item.source for item in diagnosis.violations])
        self.assertIn("3.15.0", diagnosis.violations[0].detail)

    def test_interpreter_below_the_supported_range_is_refused(self):
        diagnosis = doctor.diagnose(None, python_version=(3, 13, 9))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_a_version_that_says_nothing_is_refused_rather_than_ignored(self):
        """An empty version is a stated fact about the interpreter, not an absent one."""
        diagnosis = doctor.diagnose(None, python_version=())

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_missing_runtime_module_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(modules=("redkraken_absent_module",))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertEqual(
            ["runtime:module:redkraken_absent_module"],
            [item.source for item in diagnosis.violations],
        )

    def test_missing_declared_distribution_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(distributions=(("redkraken-absent", "1.0.0"),))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertEqual(
            ["runtime:distribution:redkraken-absent"],
            [item.source for item in diagnosis.violations],
        )
        self.assertIn("is not installed", diagnosis.violations[0].detail)

    def test_declared_distribution_version_must_match(self):
        installed = installed_distribution()
        if installed is None:
            self.skipTest("no installed distribution to compare against")
        name, version = installed

        diagnosis = doctor.diagnose(
            None, requirements=Requirements(distributions=((name, "0.0.0"),))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertIn("0.0.0", diagnosis.violations[0].detail)
        self.assertIn(version, diagnosis.violations[0].detail)

    def test_declared_distribution_at_its_pinned_version_is_ready(self):
        installed = installed_distribution()
        if installed is None:
            self.skipTest("no installed distribution to compare against")

        diagnosis = doctor.diagnose(None, requirements=Requirements(distributions=(installed,)))

        self.assertEqual(EXIT_OK, diagnosis.exit_code)


class AggregationTest(unittest.TestCase):
    def test_every_violation_is_reported_and_the_runtime_outranks_the_operator(self):
        diagnosis = doctor.diagnose(
            write(VALID.replace("requests = 5000", "requests = 0")),
            python_version=(3, 15, 0),
        )

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)
        self.assertEqual(
            ["config:budgets.requests", "runtime:python"],
            sorted(item.source for item in diagnosis.violations),
        )

    def test_a_failed_assertion_accompanies_every_violation(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(modules=("redkraken_absent_module", "json"))
        )

        self.assertEqual(
            {"module:json": True, "module:redkraken_absent_module": False},
            {
                assertion.name: assertion.ok
                for assertion in diagnosis.assertions
                if assertion.name.startswith("module:")
            },
        )


class NoSideEffectTest(unittest.TestCase):
    def test_diagnosis_writes_nothing_beside_the_configuration(self):
        directory = scratch()
        source = directory / "program.toml"
        source.write_text(VALID, encoding="utf-8")
        before = source.read_bytes()

        doctor.diagnose(source)

        self.assertEqual(["program.toml"], [entry.name for entry in directory.iterdir()])
        self.assertEqual(before, source.read_bytes())


if __name__ == "__main__":
    unittest.main()
