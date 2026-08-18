import unittest

from redkraken import outcome
from redkraken.outcome import (
    BUILD_MISMATCH,
    EXIT_BUILD_MISMATCH,
    EXIT_INVALID_CONFIGURATION,
    EXIT_MISSING_DEPENDENCY,
    EXIT_OK,
    EXIT_UNCLASSIFIED,
    EXIT_UNSUPPORTED_VERSION,
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    UNSUPPORTED_VERSION,
    Violation,
)


def violation(code: str, source: str = "config", detail: str = "detail") -> Violation:
    return Violation(code=code, source=source, detail=detail)


class ExitCodeTest(unittest.TestCase):
    def test_nothing_observed_is_the_only_way_to_exit_zero(self):
        self.assertEqual(EXIT_OK, outcome.exit_code(()))

    def test_each_class_has_its_own_status(self):
        self.assertEqual(
            [EXIT_INVALID_CONFIGURATION, EXIT_MISSING_DEPENDENCY, EXIT_UNSUPPORTED_VERSION],
            [
                outcome.exit_code((violation(code),))
                for code in (INVALID_CONFIGURATION, MISSING_DEPENDENCY, UNSUPPORTED_VERSION)
            ],
        )

    def test_the_most_fundamental_class_decides(self):
        found = (violation(INVALID_CONFIGURATION), violation(MISSING_DEPENDENCY))

        self.assertEqual(EXIT_MISSING_DEPENDENCY, outcome.exit_code(found))
        self.assertEqual(
            EXIT_UNSUPPORTED_VERSION,
            outcome.exit_code(found + (violation(UNSUPPORTED_VERSION),)),
        )

    def test_a_build_mismatch_is_its_own_status_above_operator_configuration(self):
        self.assertEqual(EXIT_BUILD_MISMATCH, outcome.exit_code((violation(BUILD_MISMATCH),)))
        self.assertEqual(
            EXIT_BUILD_MISMATCH,
            outcome.exit_code((violation(INVALID_CONFIGURATION), violation(BUILD_MISMATCH))),
        )

    def test_a_class_this_table_does_not_know_still_exits_non_zero(self):
        """Reporting a refusal and exiting `0` would read as a ready machine."""
        self.assertEqual(EXIT_UNCLASSIFIED, outcome.exit_code((violation("invented_later"),)))
        self.assertNotEqual(EXIT_OK, EXIT_UNCLASSIFIED)


class OrderTest(unittest.TestCase):
    def test_violations_are_ordered_by_class_then_by_where_they_were_observed(self):
        found = [
            violation(INVALID_CONFIGURATION, "config:program.name"),
            violation(INVALID_CONFIGURATION, "config:budgets.requests"),
            violation(MISSING_DEPENDENCY, "runtime:module:ssl"),
            violation(UNSUPPORTED_VERSION, "runtime:python"),
        ]

        self.assertEqual(
            [
                "runtime:python",
                "runtime:module:ssl",
                "config:budgets.requests",
                "config:program.name",
            ],
            [item.source for item in outcome.ordered(found)],
        )

    def test_an_unknown_class_is_ordered_last_rather_than_dropped(self):
        found = [violation("invented_later", "elsewhere"), violation(UNSUPPORTED_VERSION)]

        self.assertEqual(
            [UNSUPPORTED_VERSION, "invented_later"], [item.code for item in outcome.ordered(found)]
        )


if __name__ == "__main__":
    unittest.main()
