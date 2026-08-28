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
import tempfile
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

    def owes_a_live_gap(self):
        """The lowest open ticket every one of whose `owed` rows is still a gap.

        Read off the register rather than named, because a fixture that names a
        ticket is a fixture the next ticket to finish its work breaks, and this
        class is here to ask about the register rather than about whichever
        debt happened to be outstanding on the day it was written.
        """
        found = {gap.key for gap in self.gaps}
        rows: dict[int, list[str]] = {}
        for key, row in sorted(check_wiring.OWED_GAPS.items()):
            number = check_wiring.TICKET.match(row)
            if number:
                rows.setdefault(int(number.group(1)), []).append(key)
        for number, keys in sorted(rows.items()):
            if set(keys) <= found:
                return number, keys
        self.fail("no owed ticket holds a live gap for these fixtures to use")

    def test_a_row_naming_a_resolved_ticket_over_a_live_gap_is_refused(self):
        # The rule `check_audit` writes for its own `owed:NN` rows, in the place
        # it costs the most: work that was called finished while the gap it was
        # meant to close is still measurable.
        #
        # Neither the ticket nor its rows are written out. This fixture used to
        # name 102 and then 103, and both closed their own gaps and left it
        # asserting nothing, so it takes the first ticket the register still
        # owes a whole live gap to -- every row of it, or the flip would raise a
        # second kind of error and the comparison below would be measuring two
        # rules at once.
        number, owed = self.owes_a_live_gap()
        tickets = {
            **self.wiring.tickets,
            number: dataclasses.replace(
                self.wiring.tickets[number], status=check_audit.RESOLVED
            ),
        }

        errors = check_wiring.register_errors(self.gaps, tickets)

        self.assertEqual(
            [
                f"register: {key} names owed:{number}, which is resolved,"
                " and the gap is still here"
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
        # Over a key that is still a gap, for the same reason and read the same
        # way: a row re-pointed onto a gap somebody has since filled is refused
        # twice, and this case is about the tracker rather than about the tree.
        _, owed = self.owes_a_live_gap()

        with mock.patch.dict(check_wiring.OWED_GAPS, {owed[0]: "owed:9999"}):
            errors = check_wiring.register_errors(self.gaps, self.wiring.tickets)

        self.assertEqual(
            [f"register: {owed[0]} names owed:9999 and the tracker holds no such ticket"],
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

    def test_a_semicolon_the_mask_already_knows_about_does_not_end_a_statement(self):
        # Ticket 210. A seeded statement used to end at the first semicolon in
        # the raw file, so a semicolon inside a comment, a literal or a
        # dollar-quoted body cut every row written after it out of the gate's
        # reading -- and the gate then passed, because a row it never saw is a
        # row it cannot disagree with. All three shapes are asked here, in the
        # one statement, because the mask that answers them is one mask.
        sql = (
            "INSERT INTO property_classes (id, name) VALUES\n"
            " -- a section comment; with a semicolon in it\n"
            " ('first',  'a description; and its second half'),\n"
            " ('second', $tag$a body; and its second half$tag$),\n"
            " ('third',  'no semicolon at all');\n"
            "INSERT INTO property_classes (id, name) VALUES ('fourth', 'next');\n"
        )

        code = check_wiring.masked(sql, check_wiring.segments(sql))
        text = check_wiring.statement(sql, code, 0)

        self.assertEqual(
            [("first",), ("second",), ("third",)], check_wiring.rows(text, 1)
        )
        # The statement ends where the mask says and not one row later: the
        # second `INSERT` is a correction the corpus may write, and reading the
        # two as one would make a later migration a second opinion.
        self.assertNotIn("fourth", text)
        # And the content is still taken off the original, which is the half of
        # the docstring that was right: the mask blanks the literals a seeding
        # statement is entirely made of.
        self.assertIn("a description; and its second half", text)

    def test_every_observation_kind_the_corpus_seeds_reaches_the_reading(self):
        # What the truncated read cost, measured against the shipped corpus:
        # `0018_vocabularies.sql:216` seeds sixteen kinds, and the gate saw
        # eleven. The five it lost sit below the `-- non-evidential: surface
        # facts. Real observations, provenance and all; they` comment whose
        # semicolon ended the statement, and they are exactly the five the
        # check reading this map exists to ask about.
        evidential = self.wiring.catalogue.evidential

        self.assertEqual(16, len(evidential))
        self.assertEqual(11, sum(evidential.values()))
        self.assertEqual(
            {
                "artifact_captured": False,
                "endpoint_discovered": False,
                "identity_established": False,
                "parameter_discovered": False,
                "technology_identified": False,
            },
            {name: value for name, value in sorted(evidential.items()) if not value},
        )

    def test_a_withdrawn_grant_is_not_a_grant(self):
        # The reading W11 rests on, and the shape the corpus really writes:
        # `20261108T000000Z` deletes one row and inserts another in the same
        # file. A reader that took these statements as a set would report a
        # grant the corpus has already withdrawn, and W11 would then agree with
        # the frontmatter about a row the database does not hold. Read from a
        # corpus of its own rather than from the tree, so it stays a statement
        # about the reader after the next migration moves a grant.
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "0001_grant.sql").write_text(
                "INSERT INTO role_skills (role, skill_name) VALUES\n"
                "    ('recon',      'enumerate-surface'),\n"
                "    ('js_analyst', 'analyse-source');\n",
                encoding="utf-8",
            )
            (Path(root) / "0002_move.sql").write_text(
                "-- INSERT INTO role_skills (role, skill_name)"
                " VALUES ('recon', 'analyse-source');\n"
                "DELETE FROM role_skills WHERE role = 'recon'"
                " AND skill_name = 'enumerate-surface';\n"
                "INSERT INTO role_skills (role, skill_name)"
                " VALUES ('web_hunter', 'enumerate-surface');\n",
                encoding="utf-8",
            )
            held = check_wiring.read_catalogue(Path(root)).role_skills

        # The delete is applied where it is written, the multi-row insert is
        # read whole, and a statement inside a comment grants nothing.
        self.assertEqual(
            {
                ("js_analyst", "analyse-source"),
                ("web_hunter", "enumerate-surface"),
            },
            set(held),
        )

    def test_the_two_sources_agree_about_every_skill(self):
        # W11 over the tree as it ships. The drift this check was written from
        # -- `enumerate-surface` staged for `recon` and granted to nobody --
        # was live when it was written and `20261126T000000Z` closed it, so
        # what the tree owes now is silence.
        self.assertEqual([], check_wiring.skill_grant_gaps(self.wiring))

    def test_a_skill_staged_for_a_role_that_was_never_granted_it_is_reported(self):
        # The direction that costs work: the frontmatter stages the file and
        # the table refuses the claim, so a Task requiring the Skill leaves the
        # queue as unclaimable without a word anywhere. Built by taking the
        # grant out of the reading rather than by editing the corpus, so the
        # case is about the check and not about today's rows.
        without = dataclasses.replace(
            self.wiring,
            catalogue=dataclasses.replace(
                self.wiring.catalogue,
                role_skills=self.wiring.catalogue.role_skills
                - {("recon", "enumerate-surface")},
            ),
        )

        found = check_wiring.skill_grant_gaps(without)

        self.assertIn("W11 recon enumerate-surface", [gap.key for gap in found])
        self.assertIn(
            "role_skills does not grant it",
            next(gap.detail for gap in found if gap.subject == "recon enumerate-surface"),
        )

    def test_a_grant_the_corpus_stages_for_nobody_is_reported_too(self):
        # The other direction: a row in the table naming a role whose Skills
        # never name it back. A grant nobody uses rather than work that is
        # dropped, and reported because it is the same disagreement read
        # backwards.
        extra = dataclasses.replace(
            self.wiring,
            catalogue=dataclasses.replace(
                self.wiring.catalogue,
                role_skills=self.wiring.catalogue.role_skills
                | {("js_analyst", "use-identity")},
            ),
        )

        found = check_wiring.skill_grant_gaps(extra)

        self.assertIn("W11 js_analyst use-identity", [gap.key for gap in found])
        self.assertIn(
            "never staged for the child",
            next(gap.detail for gap in found if gap.subject == "js_analyst use-identity"),
        )


    # -- W12, the Test a Playbook says it will perform ------------------------

    @staticmethod
    def playbook(name: str, evidence: list[dict], text: str = "") -> check_wiring.Body:
        """One synthetic Playbook, so the case is about the check and not the corpus.

        The corpus is rewritten by the ticket this check was written for, so a
        case that took its example from a shipped body would stop being about
        the reading the day that body changed.
        """
        return check_wiring.Body(
            name=name, kind="playbook", front={"bb:evidence": evidence},
            text=text or "A baseline, a variant and a control walk into a Test.",
        )

    def asked(self, *bodies: check_wiring.Body) -> list[check_wiring.Gap]:
        return check_wiring.test_shape_gaps(
            dataclasses.replace(self.wiring, corpus=bodies)
        )

    def test_a_refutation_is_graded_on_a_kind_the_replay_lane_can_write(self):
        # The exact half. `close_test_replay` takes the Observation kind from
        # the specification, so a role carries one kind whichever way the run
        # comes out, and a Playbook asking for `response_invariant` on refuted
        # and something else on supported has written a refutation it cannot
        # reach.
        found = self.asked(self.playbook("probe", [
            {"to_status": "refuted", "role": "variant", "kind": "response_invariant"},
            {"to_status": "supported", "role": "variant", "kind": "response_differential"},
        ]))

        self.assertEqual(["W12 probe variant refuted"], [gap.key for gap in found])
        self.assertIn("the refuted leg is unreachable", found[0].detail)

    def test_the_rule_is_not_narrowed_to_the_kind_that_is_commonest(self):
        # The reading the first draft got wrong. Of the thirty-one bodies this
        # finds in the shipped corpus the supported leg asks for
        # `response_differential` in sixteen, so a check written against that
        # one kind would have found half of them and called the corpus clean.
        for kind in ("state_change", "credential_effect", "error_detail",
                     "content_match", "timing_differential", "callback_interaction"):
            with self.subTest(kind=kind):
                found = self.asked(self.playbook("probe", [
                    {"to_status": "refuted", "role": "variant",
                     "kind": "response_invariant"},
                    {"to_status": "supported", "role": "variant", "kind": kind},
                ]))

                self.assertEqual(["W12 probe variant refuted"], [gap.key for gap in found])

    def test_two_legs_that_ask_for_one_kind_are_not_reported(self):
        # A Test whose variant is graded invariant either way is a Test the lane
        # can settle, and the roles are not compared across each other: a
        # control asking for something else is a different action.
        found = self.asked(self.playbook("probe", [
            {"to_status": "refuted", "role": "variant", "kind": "response_invariant"},
            {"to_status": "supported", "role": "variant", "kind": "response_invariant"},
            {"to_status": "supported", "role": "control", "kind": "response_differential"},
        ]))

        self.assertEqual([], found)

    def test_a_body_that_declares_no_evidence_list_is_reported(self):
        found = self.asked(check_wiring.Body(
            name="probe", kind="playbook", front={},
            text="A baseline, a variant and a control.",
        ))

        self.assertEqual(["W12 probe evidence"], [gap.key for gap in found])

    def test_the_prose_reading_reports_itself_as_a_heuristic(self):
        # W12b. It measures vocabulary and the rule it stands in for is
        # `rk2_test_spec_problem`'s, so the sentence it emits has to say both --
        # a reader who takes this for the enforcement will go looking for the
        # wrong thing when a spec is refused.
        found = self.asked(self.playbook(
            "probe",
            [{"to_status": "supported", "role": "variant", "kind": "response_differential"}],
            text="Send the request, then send it again without the header.",
        ))

        self.assertEqual(["W12 probe roles"], [gap.key for gap in found])
        self.assertTrue(found[0].detail.startswith("heuristic: "))
        self.assertIn("baseline, variant, control", found[0].detail)
        self.assertIn("rk2_test_spec_problem at propose_test", found[0].detail)

    def test_a_role_named_inside_a_longer_word_is_not_a_role_named(self):
        # `controlled` is not `control`. A substring match would read this body
        # as naming one of the three and pass over it.
        found = self.asked(self.playbook(
            "probe",
            [{"to_status": "supported", "role": "variant", "kind": "response_differential"}],
            text="A baseline, a variant, and a controlled comparison.",
        ))

        self.assertEqual(["W12 probe roles"], [gap.key for gap in found])
        self.assertIn("never names control", found[0].detail)

    def test_what_the_shipped_corpus_owes_is_counted_and_registered(self):
        # The number this gate was switched on with, so that the rewrite has
        # something to measure itself against. Thirty-one bodies grade an
        # unreachable refutation and thirty-five never name all three roles;
        # fifteen of the fifty name them all.
        found = check_wiring.test_shape_gaps(self.wiring)
        unreachable = [gap for gap in found if gap.subject.endswith(" refuted")]
        unnamed = [gap for gap in found if gap.subject.endswith(" roles")]

        self.assertEqual(31, len(unreachable))
        self.assertEqual(35, len(unnamed))
        self.assertEqual(len(found), len(unreachable) + len(unnamed))
        # And every one of them is on the register, against the ticket that owes
        # the rewrite. The other direction -- a row with no gap -- is
        # `register_errors`' and is asked in `WiringRegisterTest`.
        self.assertEqual(
            {"owed:101"},
            {check_wiring.OWED_GAPS.get(gap.key) for gap in found},
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

    def test_the_two_verbs_the_claim_was_wrong_about_are_called_now(self):
        # The measurement the prose stood in for, and the repair it produced.
        # 38 said all three verbs "are called by the CLI and by the tests"; one
        # third of that was true, because `open_impact_replay` is called from
        # Python, and the other two were granted to the runtime and reached
        # from no call site, no trigger binding and no standing check. Ticket
        # 103 gave them the callers the sentence had already claimed:
        # `propose_impact_task` and `propose_severity` are served as Contracts,
        # dispatched from `agent.py`, and each calls the verb underneath it.
        self.assertIn("open_impact_replay", self.reached)
        self.assertIn("open_impact_task", self.reached)
        self.assertIn("state_severity", self.reached)
        for caller, verb in (
            ("propose_impact_task", "open_impact_task"),
            ("propose_severity", "state_severity"),
        ):
            with self.subTest(verb=verb):
                # The whole of the chain, not that the verb is somehow reached:
                # Python names the proposer, the proposer's body calls the verb,
                # and the verb is still on the runtime's surface, which is what
                # made W3 ask about it in the first place.
                self.assertIn(caller, self.wiring.surface.names)
                self.assertIn(verb, self.wiring.catalogue.calls[caller])
                self.assertIn(check_wiring.RUNTIME, self.wiring.catalogue.grants[verb])

    def test_the_gate_reports_neither_of_them(self):
        # The other side of the same repair. W3 reported both verbs for as long
        # as 38's sentence stood in for a caller; ticket 103 wired them, so the
        # check that disagreed with the prose now agrees with the tree, and a
        # regression that took either caller away would put the key back.
        found = {gap.key for gap in check_wiring.verb_gaps(self.wiring)}

        self.assertEqual(set(), {"W3 open_impact_task", "W3 state_severity"} & found)


if __name__ == "__main__":
    unittest.main()
