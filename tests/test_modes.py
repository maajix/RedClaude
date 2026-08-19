"""The multiagent findings record, reconciled against the runs it cites.

Ticket 80 measures four documented multiagent failure modes against this
harness and writes down what each one turned out to be here. The record is
`baseline/multiagent-modes.tsv`, one row per mode with a verdict and the run
that earned it, and a record whose citations have gone stale is worse than no
record: it reads as evidence and is a memory of one.

So every row is resolved. The verdict comes from a closed vocabulary, the
mechanism names something, and the cited run is imported and looked up -- a
test that was renamed, moved or deleted fails here rather than being discovered
by somebody reading the file a year later. What is not asserted is that the
cited run passes: the suite is what says that, and asking it here would mean
this file starting a database.
"""

import csv
import importlib
import unittest

from tests.ledger import MODES, table_rows
from tools import check_baseline


#: The columns, in order. A record whose reader guesses at its own shape is a
#: record that can lose a column to a stray tab and still be read.
FIELDS = ("mode", "paper_finding", "verdict", "mechanism", "cited_run", "note")

#: What a mode may have turned out to be. `not_reproduced` is a result and not
#: an absence of one -- the criterion this record answers says so in as many
#: words -- and `reproduced` without an enforcement beside it is what a ticket
#: is for.
VERDICTS = {"measured", "enforced", "reproduced", "not_reproduced"}


def rows() -> list[dict[str, str]]:
    """The record, as one dictionary per mode."""
    with MODES.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class ModesRecordTest(unittest.TestCase):
    """Ticket 80, criterion 6: every claim cites a run, and every run exists."""

    def setUp(self):
        self.rows = rows()

    def test_the_record_is_the_shape_it_says_it_is(self):
        [header, *body] = table_rows(MODES)
        self.assertEqual(list(FIELDS), header)
        self.assertEqual([], [row for row in body if len(row) != len(FIELDS)])
        self.assertEqual([], [row for row in body if not all(field.strip() for field in row)])

    def test_no_mode_is_written_down_twice(self):
        named = [row["mode"] for row in self.rows]
        self.assertEqual(sorted(set(named)), sorted(named))

    def test_every_verdict_is_one_of_the_four(self):
        self.assertEqual(
            [], sorted({row["verdict"] for row in self.rows} - VERDICTS)
        )

    def test_every_mode_the_ticket_measured_is_here(self):
        """The four modes the paper names, against the rows that answer them.

        Named rather than counted: a record that lost the flooding row would
        still have seven rows if somebody added an eighth, and the criterion is
        about the four modes rather than about the size of the file.
        """
        self.assertEqual(
            [],
            sorted(
                {"correlated_choice", "correlated_duplicate", "resource_flooding",
                 "consensus_over_evidence", "turf_wars_network"}
                - {row["mode"] for row in self.rows}
            ),
        )

    def test_every_cited_run_is_a_test_this_repository_has(self):
        for row in self.rows:
            with self.subTest(mode=row["mode"]):
                module_name, case_name, test_name = row["cited_run"].rsplit(".", 2)
                case = getattr(importlib.import_module(module_name), case_name, None)
                self.assertIsNotNone(case, row["cited_run"])
                self.assertTrue(issubclass(case, unittest.TestCase), row["cited_run"])
                self.assertTrue(test_name.startswith("test_"), row["cited_run"])
                self.assertTrue(callable(getattr(case, test_name, None)), row["cited_run"])

    def test_a_reproduced_mode_names_the_ticket_that_answers_it(self):
        """Criterion 6's other half, from the side that is not a control.

        A mode this harness does reproduce and has not enforced is the one kind
        of row that has to point somewhere: the criterion says the gap is a
        ticket rather than a paragraph, and a `reproduced` row whose note is
        only a description is that paragraph.
        """
        for row in self.rows:
            if row["verdict"] != "reproduced":
                continue
            with self.subTest(mode=row["mode"]):
                self.assertRegex(row["note"], r"ticket \d+")

    def test_the_record_is_one_of_the_files_baseline_may_hold(self):
        self.assertIn(MODES.name, check_baseline.BASELINE_FILES)
