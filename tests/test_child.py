"""Running one trusted host program, and reading back what it said.

Two callers share this -- `rk db dump` reaching `pg_dump`, and the vault
reaching `op` -- and each of them has its own tests about what it does with the
answer. What is left here is the part neither of them should be re-asserting:
that a program which never ran is distinguishable from one that ran and failed,
and that a child's own words are bounded before they reach a report.

The programs run below are `sys.executable`, so these are real processes and
not a stubbed `subprocess`. The thing being tested is the boundary around a
child, which a fake child cannot be wrong about.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from redkraken import child


def python(source: str) -> list[str]:
    return ["-c", source]


class RunTest(unittest.TestCase):
    """A program that ran, a program that could not, and a program that would not stop."""

    def run_python(self, source: str, *, timeout: float = 30.0, stdin=subprocess.DEVNULL):
        return child.run(
            sys.executable,
            python(source),
            environment={"LC_ALL": "C.UTF-8"},
            timeout=timeout,
            stdin=stdin,
        )

    def test_a_program_that_ran_comes_back_with_its_own_status_and_streams(self):
        completed = self.run_python(
            "import sys; sys.stdout.write('out'); sys.stderr.write('err'); sys.exit(3)"
        )

        self.assertIsInstance(completed, subprocess.CompletedProcess)
        self.assertEqual((3, "out", "err"), (completed.returncode, completed.stdout, completed.stderr))

    def test_a_program_that_is_not_there_comes_back_as_a_sentence(self):
        # A string rather than an exception, and rather than a `CompletedProcess`
        # with some invented status: the caller's next question is which of its
        # own violations to record, and a status it made up would answer it
        # wrongly.
        outcome = child.run(
            "/nonexistent/rk2-not-a-program", [], environment={}, timeout=30.0
        )

        self.assertIsInstance(outcome, str)
        self.assertIn("could not be run", outcome)

    def test_a_program_that_would_not_finish_is_stopped_and_said_so(self):
        outcome = self.run_python("import time; time.sleep(30)", timeout=0.4)

        self.assertIsInstance(outcome, str)
        self.assertIn("did not finish within", outcome)

    def test_the_child_gets_the_environment_it_was_given_and_no_other(self):
        completed = self.run_python(
            "import os, json; print(json.dumps(sorted(os.environ)))"
        )

        self.assertEqual(["LC_ALL"], json.loads(completed.stdout))

    def test_stdin_is_closed_so_a_prompt_ends_rather_than_waits(self):
        # An unattended campaign cannot answer a prompt. A child holding this
        # process's stdin open is one that waits for the timeout instead of
        # failing in a way the caller can report.
        completed = self.run_python("import sys; print(len(sys.stdin.read()))", timeout=10.0)

        self.assertEqual("0", completed.stdout.strip())


class WordsTest(unittest.TestCase):
    """What a failed child said, on its way into somebody's refusal."""

    def test_everything_it_said_collapses_onto_one_line(self):
        self.assertEqual("one two three", child.collapse("one\n  two\t\nthree\n"))

    def test_a_child_that_said_nothing_still_produces_a_sentence(self):
        self.assertEqual("no output", child.tail("   \n\t ", limit=100))

    def test_the_end_is_kept_because_that_is_where_a_program_says_why(self):
        text = "preamble " * 100 + "ERROR: the actual reason"

        self.assertTrue(child.tail(text, limit=40).endswith("ERROR: the actual reason"))

    def test_the_bound_is_the_callers_and_is_honoured(self):
        for limit in (1, 10, 500, 2000):
            with self.subTest(limit=limit):
                self.assertLessEqual(len(child.tail("z" * 5000, limit=limit)), limit)

    def test_what_fits_is_returned_whole(self):
        self.assertEqual("short", child.tail("short", limit=500))


if __name__ == "__main__":
    unittest.main()
