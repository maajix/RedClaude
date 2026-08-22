"""The wiring gate, asked against the tree it is for.

Every reading here is taken from the real migrations, the real roster and the
real corpus, for the reason `test_audit` gives: the readings are what the gate
is, and a test that had to write a migration to reach one would be testing the
filesystem instead. The register is the exception, because the register is the
only part of this gate that can be wrong in two directions at once, and both are
asked by holding the tree still and changing the register underneath it.

The one test that matters most is the last: ticket 38 states in prose that three
verbs are called, and this gate measures that instead of believing it.
"""

import contextlib
import dataclasses
import functools
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools import check_audit, check_wiring


ROOT = Path(__file__).resolve().parents[1]

#: The claim this gate exists to have caught, quoted from the resolved ticket
#: that made it, and the three verbs it makes the claim about.
CLAIM = "are called by the CLI and by the tests"
TICKET_38 = ROOT / "docs" / "specs" / "production-harness-v2" / "issues"
CLAIMED = ("open_impact_task", "open_impact_replay", "state_severity")

#: A subprocess that reads this tree has to be told to leave the user's site
#: packages out of it. A `tools` package installed there shadows this one, and
#: the import that resolved to it would be checking somebody else's repository.
ENVIRONMENT = {**os.environ, "PYTHONPATH": str(ROOT)}


@functools.cache
def read():
    """One reading of the tree, shared by every class that asks the same one of it.

    Cached because it is the same answer four times over: the readings are pure
    and the tree does not move while the suite runs, and reading a hundred and
    thirty-nine migrations once per class is the difference between a gate test
    somebody runs and one they skip.
    """
    return check_wiring.gather()


def gaps(wiring):
    """Every gap the ten checks find, in the order the report walks them."""
    return [gap for _, _, reading in check_wiring.CHECKS for gap in reading(wiring)]


class WiringGateTest(unittest.TestCase):
    """The tree as it stands: every gap in it is a gap somebody owes."""

    @classmethod
    def setUpClass(cls):
        cls.wiring = read()
        cls.gaps = gaps(cls.wiring)
        cls.report = check_wiring.check()

    def test_the_report_measures_every_check_in_order(self):
        lines = self.report.splitlines()

        self.assertEqual("wiring", lines[0])
        self.assertEqual(
            [code for code, _, _ in check_wiring.CHECKS] + ["register"],
            [line.split()[0] for line in lines[1:]],
        )
        # A measurement, not a verdict. Every line has to carry a number it read
        # out of the tree, so a reading that quietly stopped looking shows up.
        self.assertTrue(all(any(word.isdigit() for word in line.split()) for line in lines[1:]))

    def test_each_check_owes_exactly_the_register_rows_it_owns(self):
        # The identity the whole gate rests on: what a check finds and what the
        # register excuses are the same set, check by check. Counting them apart
        # here is what makes the report's `owed` column worth reading.
        for code, _, _ in check_wiring.CHECKS:
            with self.subTest(check=code):
                self.assertEqual(
                    sum(1 for key in check_wiring.OWED_GAPS if key.split()[0] == code),
                    len({gap.key for gap in self.gaps if gap.check == code}),
                )

    def test_every_register_row_names_a_ticket_in_the_state_its_spelling_claims(self):
        # The two spellings are opposites about the ticket. `owed:NN` is a debt
        # and a resolved ticket cannot owe one; `decided:NN` cites an argument
        # and an open ticket has not finished having it. Read off the register
        # rather than written out, so a new row of either kind is checked
        # without this case being touched.
        for key, row in check_wiring.OWED_GAPS.items():
            with self.subTest(row=key):
                owed = check_wiring.TICKET.match(row)
                decided = check_wiring.DECIDED_TICKET.match(row)
                self.assertTrue(owed or decided, row)
                number = owed or decided
                ticket = self.wiring.tickets[int(number.group(1))]
                self.assertEqual(bool(decided), ticket.resolved)

    def test_the_report_does_not_move_between_runs(self):
        self.assertEqual(self.report, check_wiring.check())

    def test_checking_writes_nothing(self):
        before = {
            path: path.read_bytes()
            for path in sorted(check_wiring.MIGRATIONS.glob("*.sql"))
        }

        check_wiring.check()

        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_no_engagement_state_is_read_as_evidence(self):
        # The gate reads the tree and nothing else. One that opened a database
        # would answer differently on two machines, and a gap would be a gap
        # only where somebody had a server running.
        reached = subprocess.run(
            [
                sys.executable,
                "-s",
                "-c",
                "import sys, json;"
                " from tools import check_wiring;"
                " check_wiring.check();"
                " print(json.dumps(sorted(sys.modules)))",
            ],
            cwd=ROOT,
            env=ENVIRONMENT,
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(
            [],
            [
                name
                for name in json.loads(reached.stdout)
                if name in {"redkraken.pg", "redkraken.store", "redkraken.state", "socket", "ssl"}
            ],
        )

    def test_the_command_prints_the_report_and_succeeds(self):
        run = subprocess.run(
            [sys.executable, "-s", "-B", "-m", "tools.check_wiring"],
            cwd=ROOT,
            env=ENVIRONMENT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(self.report + "\n", run.stdout)

    def test_the_command_reports_every_reason_it_refused(self):
        # One exit code, every reason, and both directions of the register in
        # the same refusal: a gap nobody recorded and a row nothing matches.
        register = {
            key: owed
            for key, owed in check_wiring.OWED_GAPS.items()
            if key not in ("W7 guard_satisfiability", "W8 report_queue")
        }
        register["W1 mcp__rk2__nothing_declares_this"] = "owed:105"
        stderr = io.StringIO()

        with mock.patch.object(check_wiring, "OWED_GAPS", register):
            with contextlib.redirect_stderr(stderr):
                code = check_wiring.main([])

        self.assertEqual(1, code)
        self.assertEqual(
            "wiring failed: unregistered: no standing check named guard_satisfiability asserts"
            " that no guard requires a row another guard refuses\n"
            "unregistered: mcp__rk2__request_report writes report_queue and nothing ever inserts"
            " into it\n"
            "register: W1 mcp__rk2__nothing_declares_this names owed:105 and this tree has no"
            " such gap; remove the row",
            stderr.getvalue().strip(),
        )


class WiringRegisterTest(unittest.TestCase):
    """The register reconciled against a tree that is held still."""

    @classmethod
    def setUpClass(cls):
        cls.wiring = read()
        cls.gaps = gaps(cls.wiring)

    def test_a_row_naming_a_resolved_ticket_over_a_live_gap_is_refused(self):
        # The rule `check_audit` writes for its own `owed:NN` rows, in the place
        # it costs the most: work that was called finished while the gap it was
        # meant to close is still measurable.
        #
        # Ticket 103 stands in for the rule, and the two rows this fixture used
        # to name are why it has to: ticket 102 gave `open_finding` its caller,
        # so those gaps are gone and a fixture over a closed gap asserts
        # nothing. The keys are read off the register rather than written out,
        # because the next ticket to close its own rows would otherwise break
        # this test instead of being caught by the gate.
        ticket = self.wiring.tickets[103]
        tickets = {
            **self.wiring.tickets,
            103: dataclasses.replace(ticket, status=check_audit.RESOLVED),
        }
        owed = sorted(key for key, row in check_wiring.OWED_GAPS.items() if row == "owed:103")
        self.assertTrue(owed, "ticket 103 owes no register row for this fixture to use")

        errors = check_wiring.register_errors(self.gaps, tickets)

        self.assertEqual(
            [
                f"register: {key} names owed:103, which is resolved, and the gap is still here"
                for key in owed
            ],
            errors,
        )

    def test_a_decision_citing_an_open_ticket_is_refused(self):
        # The `decided` half of the same rule. Ticket 138 is resolved and is the
        # one row that carries the spelling; reopening it under the fixture has
        # to make the row an error, or the register would be excusing a gap on
        # an argument nobody had finished.
        ticket = self.wiring.tickets[138]
        tickets = {**self.wiring.tickets, 138: dataclasses.replace(ticket, status="ready-for-agent")}
        decided = sorted(
            key for key, row in check_wiring.OWED_GAPS.items() if row == "decided:138"
        )
        self.assertTrue(decided, "ticket 138 carries no decided row for this fixture to use")

        errors = check_wiring.register_errors(self.gaps, tickets)

        self.assertEqual(
            [
                f"register: {key} names decided:138, which is not resolved,"
                " so the decision it cites has not been made"
                for key in decided
            ],
            errors,
        )

    def test_a_decision_that_outlived_its_gap_is_refused(self):
        # A `decided` row is held to the gap exactly as an `owed` row is. The
        # spelling changes what is claimed about the ticket and nothing about
        # the absence, because a row excusing a gap that has been filled would
        # go on excusing the next one to appear under the same name.
        gaps = [gap for gap in self.gaps if gap.key != "W3 find_in_database"]

        errors = check_wiring.register_errors(gaps, self.wiring.tickets)

        self.assertIn(
            "register: W3 find_in_database names decided:138 and this tree has no such gap;"
            " remove the row",
            errors,
        )

    def test_a_row_spelled_neither_way_is_refused(self):
        with mock.patch.dict(check_wiring.OWED_GAPS, {"W3 open_impact_task": "ticket:105"}):
            errors = check_wiring.register_errors(self.gaps, self.wiring.tickets)

        self.assertEqual(
            [
                "register: W3 open_impact_task is recorded as 'ticket:105',"
                " which is neither an owed:NN nor a decided:NN row"
            ],
            errors,
        )

    def test_a_row_naming_no_ticket_at_all_is_refused(self):
        with mock.patch.dict(check_wiring.OWED_GAPS, {"W3 open_impact_task": "owed:9999"}):
            errors = check_wiring.register_errors(self.gaps, self.wiring.tickets)

        self.assertEqual(
            ["register: W3 open_impact_task names owed:9999 and the tracker holds no such ticket"],
            errors,
        )


class WiringReadingTest(unittest.TestCase):
    """The four readings the checks are taken from, asked one at a time."""

    @classmethod
    def setUpClass(cls):
        cls.wiring = read()
        cls.reached = cls.wiring.reachable()

    def test_a_comment_is_not_a_caller(self):
        # The false positive that would have made this gate agree with the
        # prose: this corpus names its own verbs in comments constantly, and a
        # scan that did not know a comment from a statement would score every
        # one of them as a call site.
        sql = (
            "-- state_severity(finding) is called here, allegedly.\n"
            "CREATE FUNCTION probe() RETURNS void LANGUAGE sql AS $body$\n"
            "  SELECT 1 /* open_impact_task(task) */;\n"
            "  SELECT 'apply_computed_cvss(finding)'::text;\n"
            "  SELECT rk2_pivot_source(1);\n"
            "$body$;\n"
        )

        runs = check_wiring.segments(sql)
        code = check_wiring.masked(sql, runs)
        body = "".join(
            check_wiring.inner(sql, start, stop)
            for kind, start, stop in runs
            if kind == "quoted" and check_wiring.DOLLAR.match(sql, start)
        )

        self.assertEqual(["probe"], check_wiring.CALL.findall(code))
        self.assertEqual(["rk2_pivot_source"], check_wiring.CALL.findall(body))
        # The mask is the same length as the file it was taken from, which is
        # what lets a drop and a recreate in one file be applied in order.
        self.assertEqual(len(sql), len(code))

    def test_the_roots_include_the_two_that_name_no_python(self):
        # Without trigger bindings and standing-check queries every constraint
        # trigger and every `check_*` function in this corpus is an orphan, the
        # gate opens with hundreds of false findings and somebody switches it
        # off. Each root class is removed in turn to show what it holds up.
        without = dataclasses.replace(
            self.wiring,
            catalogue=dataclasses.replace(self.wiring.catalogue, standing=frozenset()),
        )
        no_triggers = dataclasses.replace(
            self.wiring,
            catalogue=dataclasses.replace(self.wiring.catalogue, triggers=frozenset()),
        )

        self.assertLess(len(without.reachable()), len(self.reached))
        self.assertLess(len(no_triggers.reachable()), len(self.reached))
        self.assertIn("check_program_isolation", self.reached)
        self.assertNotIn("check_program_isolation", without.reachable())

    def test_a_relation_named_in_a_where_is_on_the_read_surface(self):
        # The half of the surface a reading of `VALUES` rows alone would miss:
        # `0034_reports.sql:1084-1092` puts eleven relations on it by selecting
        # their columns out of the catalogue and naming them in a `WHERE`.
        self.assertLessEqual(
            {"finding_chain_step_citations", "finding_effects", "report_renderings"},
            self.wiring.catalogue.read_surface,
        )
        self.assertTrue(self.wiring.catalogue.catalogue_seeded)

    def test_a_playbook_is_measured_against_the_role_that_executes_it(self):
        # W10 has no question to ask until this derivation lands: a Playbook
        # states the Skills it needs and never states a role.
        executing = self.wiring.executing

        self.assertEqual("web_hunter", executing["browser-evidence"])
        self.assertEqual(len(self.wiring.corpus), len(executing))
        # A body whose Skills no single role holds is left without one rather
        # than given the first that fits, and the checks that need a role say
        # nothing about it instead of measuring it against a guess.
        self.assertTrue(
            all(
                role in self.wiring.surface.roles
                for role in executing.values()
                if role is not None
            )
        )


class TicketThirtyEightTest(unittest.TestCase):
    """The defect this gate is proven against, which is a sentence in a resolved ticket."""

    @classmethod
    def setUpClass(cls):
        cls.wiring = read()
        cls.reached = cls.wiring.reachable()
        cls.ticket = next(TICKET_38.glob("38-*.md")).read_text(encoding="utf-8")

    def test_the_claim_is_still_the_one_this_gate_disagrees_with(self):
        self.assertIn(CLAIM, self.ticket)
        for verb in CLAIMED:
            with self.subTest(verb=verb):
                self.assertIn(verb, self.ticket)

    def test_two_of_the_three_verbs_it_calls_called_are_called_by_nothing(self):
        # The measurement the prose stood in for. `open_impact_replay` is called
        # from Python and the sentence is right about it; the other two are
        # granted to the runtime, reached from no call site, no trigger binding
        # and no standing check, and the sentence was written in one review and
        # believed in every one after it.
        self.assertIn("open_impact_replay", self.reached)
        self.assertNotIn("open_impact_task", self.reached)
        self.assertNotIn("state_severity", self.reached)
        for verb in ("open_impact_task", "state_severity"):
            with self.subTest(verb=verb):
                self.assertIn(check_wiring.RUNTIME, self.wiring.catalogue.grants[verb])

    def test_the_gate_reports_both_of_them(self):
        found = {gap.key for gap in check_wiring.verb_gaps(self.wiring)}

        self.assertLessEqual({"W3 open_impact_task", "W3 state_severity"}, found)


if __name__ == "__main__":
    unittest.main()
