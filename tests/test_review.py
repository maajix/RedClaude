"""The final review's findings record, reconciled against the runs it cites.

Ticket 64 reviews the whole production tree against the repository's standards
and against the production spec, and this is where what the review found is
written down. The record is `baseline/final-review.tsv`, one row per finding,
and it exists because a review whose findings live in a conversation is a review
nobody can check: the criteria ask for severity, location, violated contract,
evidence and remediation per finding, and for every high and medium one to be
fixed with regression coverage rather than remembered.

So every row resolves. The severity and the disposition come from closed
vocabularies, the location names a file this checkout has, and a fixed row cites
a run that is imported and looked up -- a regression test that was renamed or
deleted fails here rather than being noticed by whoever reads the file next
year. What is not asserted is that the cited run passes: the suite says that,
and asking it here would mean this file starting a database.
"""

import importlib
import unittest
from pathlib import Path

from tests import ROOT
from tests.ledger import REVIEW, table_rows
from tools import check_baseline


#: The columns, in order. A record whose reader guesses at its own shape is a
#: record that can lose a column to a stray tab and still be read.
FIELDS = (
    "finding",
    "axis",
    "surface",
    "severity",
    "location",
    "contract",
    "evidence",
    "remediation",
    "disposition",
    "cited_run",
)

#: The two reviews, kept apart on purpose: a change can follow every standard
#: while implementing the wrong thing, and one axis reranked into the other is
#: one axis masking it.
AXES = {"standards", "spec"}

#: What a finding can be worth. `high` is a release blocker, `medium` is a real
#: defect with a way around it, `low` is naming, prose or cosmetics.
SEVERITIES = {"high", "medium", "low"}

#: What happened to it. `fixed` is the only disposition a high or a medium may
#: end at; `dispositioned` is a low judged not worth the change, with the reason
#: in the remediation column; `blocking` is the criterion's other allowed
#: outcome for a high or a medium -- not fixed, and release stops for it.
DISPOSITIONS = {"fixed", "dispositioned", "blocking"}


def rows() -> list[dict[str, str]]:
    """The record, as one dictionary per finding, off the reader the gates use."""
    [header, *body] = table_rows(REVIEW)
    return [dict(zip(header, row)) for row in body]


class FinalReviewRecordTest(unittest.TestCase):
    """Ticket 64, criteria 3, 4 and 6: what the review found, and where it went."""

    def setUp(self):
        self.rows = rows()

    def test_the_record_is_the_shape_it_says_it_is(self):
        [header, *body] = table_rows(REVIEW)
        self.assertEqual(list(FIELDS), header)
        self.assertEqual([], [row for row in body if len(row) != len(FIELDS)])
        self.assertEqual([], [row for row in body if not all(field.strip() for field in row)])

    def test_no_finding_is_written_down_twice(self):
        named = [row["finding"] for row in self.rows]
        self.assertEqual(sorted(set(named)), sorted(named))

    def test_every_axis_severity_and_disposition_is_one_of_the_words(self):
        self.assertEqual([], sorted({row["axis"] for row in self.rows} - AXES))
        self.assertEqual([], sorted({row["severity"] for row in self.rows} - SEVERITIES))
        self.assertEqual([], sorted({row["disposition"] for row in self.rows} - DISPOSITIONS))

    def test_every_finding_names_a_file_this_checkout_has(self):
        """Criterion 3's exact source location, checked as one.

        A finding whose location has stopped naming anything is a finding
        nobody can re-examine, which is the difference between a record and a
        recollection.
        """
        for row in self.rows:
            with self.subTest(finding=row["finding"]):
                named = Path(ROOT / row["location"].partition(":")[0])
                self.assertTrue(named.exists(), row["location"])

    def test_every_fixed_finding_cites_a_run_this_repository_has(self):
        """Criterion 4: fixed with regression coverage, and the coverage named.

        A fix without a run beside it is a fix that lasts until the next person
        who does not know it was a finding.
        """
        for row in self.rows:
            if row["disposition"] != "fixed":
                continue
            with self.subTest(finding=row["finding"]):
                module_name, case_name, test_name = row["cited_run"].rsplit(".", 2)
                case = getattr(importlib.import_module(module_name), case_name, None)
                self.assertIsNotNone(case, row["cited_run"])
                self.assertTrue(issubclass(case, unittest.TestCase), row["cited_run"])
                self.assertTrue(test_name.startswith("test_"), row["cited_run"])
                self.assertTrue(callable(getattr(case, test_name, None)), row["cited_run"])

    def test_only_a_low_finding_may_be_dispositioned_rather_than_fixed(self):
        """Criterion 4's other half: a high or a medium is fixed or it blocks."""
        for row in self.rows:
            if row["disposition"] != "dispositioned":
                continue
            with self.subTest(finding=row["finding"]):
                self.assertEqual("low", row["severity"])
                self.assertEqual("-", row["cited_run"])

    def test_nothing_high_or_medium_is_still_open(self):
        """Criterion 6: the final pass reports no unresolved high or medium.

        The rows are what says so, so this is the assertion that would fail on
        the day a blocker is written down and the release is cut anyway.
        """
        self.assertEqual(
            [],
            [row["finding"] for row in self.rows if row["disposition"] == "blocking"],
        )

    def test_the_record_is_one_of_the_files_baseline_may_hold(self):
        self.assertIn(REVIEW.name, check_baseline.BASELINE_FILES)
