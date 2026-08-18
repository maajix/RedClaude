"""The release audit, read the way the other gate tests read theirs.

Every reading is asked against the real Spec, the real tracker and the real map
with one thing changed, because the readings are what the gate is: a test that
had to edit `spec.md` to reach one would be testing the filesystem. The one
exception is the run mode, which is asked against a probe in this file -- a suite
that passes and a suite that stands down -- since the thing it has to prove is
that a citation which skipped is not evidence.
"""

import contextlib
import dataclasses
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_audit, check_baseline


ROOT = Path(__file__).resolve().parents[1]

#: One requirement with a plain map row, used wherever a test needs a row it can
#: break: a user story implemented by one resolved ticket and checked by tests
#: this checkout can run.
STORY = "story:001"
#: One requirement whose evidence is a gate rather than a test.
GATE_BACKED = "story:230"


class RunnableProbe(unittest.TestCase):
    """Two outcomes the run mode has to tell apart, held still in one file."""

    def test_this_one_holds(self):
        self.assertTrue(True)

    def test_this_one_stands_down(self):
        self.skipTest("no database")


class AuditGateTest(unittest.TestCase):
    """The tree as it stands: the Spec is delivered and the map says by what."""

    @classmethod
    def setUpClass(cls):
        cls.report = check_audit.check()

    def test_the_report_is_the_spec_measured_against_the_tracker(self):
        self.assertEqual(
            "spec coverage\n"
            "  stories                230   decisions 19  testing 24  scope 9  regressions 7\n"
            "  evidence               211   tests 205  gates 6\n"
            "  tickets                 83   resolved 77  audited 62  deferred criteria 11\n"
            "  area: runtime          143   anchors 1\n"
            "  area: agents            37   anchors 2\n"
            "  area: skills             7   anchors 1\n"
            "  area: playbooks         14   anchors 2\n"
            "  area: operator          33   anchors 2\n"
            "  area: v1_import         17   anchors 2\n"
            "  area: long_session      15   anchors 2\n"
            "  area: first_hunt        23   anchors 1",
            self.report,
        )

    def test_the_report_does_not_move_between_runs(self):
        self.assertEqual(self.report, check_audit.check())

    def test_checking_writes_nothing(self):
        before = {path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()}

        check_audit.check()

        self.assertEqual(
            before, {path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()}
        )

    def test_no_engagement_state_is_read_as_evidence(self):
        # The static pass reads documents and the tree. A checker that opened a
        # database would answer differently on two machines, and the release
        # would depend on which one ran it.
        reached = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, json;"
                " from tools import check_audit;"
                " check_audit.check();"
                " print(json.dumps(sorted(sys.modules)))",
            ],
            cwd=ROOT,
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
            [sys.executable, "-B", "-m", "tools.check_audit"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(self.report + "\n", run.stdout)

    def test_the_command_reports_every_reason_it_refused(self):
        # One exit code, every reason. A gate that stopped at the first missing
        # row would make closing the map a queue rather than a piece of work.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spec-evidence.tsv"
            rows = (ROOT / "baseline" / "spec-evidence.tsv").read_text(encoding="utf-8")
            path.write_text(
                "\n".join(
                    line
                    for line in rows.splitlines()
                    if not line.startswith(("story:001\t", "story:002\t"))
                )
                + "\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()

            with mock.patch.object(check_audit, "MAP", path):
                with contextlib.redirect_stderr(stderr):
                    code = check_audit.main([])

        self.assertEqual(1, code)
        self.assertEqual(
            "audit failed: story:001: the spec states it and the map does not\n"
            "story:002: the spec states it and the map does not",
            stderr.getvalue().strip(),
        )


class AuditSpecTest(unittest.TestCase):
    """What the audit measures against: the Spec's own text, not a copy of it."""

    @classmethod
    def setUpClass(cls):
        cls.status = check_baseline.read_status()
        cls.root = check_audit.spec_root(cls.status)
        cls.requirements = check_audit.read_spec(cls.root, cls.status)

    def test_every_kind_of_requirement_is_read_out_of_the_documents(self):
        self.assertEqual(
            (230, 19, 24, 9, 7),
            tuple(
                sum(1 for key in self.requirements if key.startswith(prefix))
                for prefix in ("story:", "decision:", "testing:", "scope:", "regression:")
            ),
        )

    def test_a_spec_missing_a_story_is_refused_before_anything_is_mapped(self):
        with mock.patch.object(check_audit, "STORIES", 231):
            with self.assertRaises(check_audit.AuditError) as refused:
                check_audit.read_spec(self.root, self.status)

        self.assertEqual(
            "the spec must hold user stories 1 through 231, numbered in order",
            str(refused.exception),
        )

    def test_the_spec_is_found_through_the_registry_rather_than_a_spelled_path(self):
        # The gate never names the tree it audits. It asks the registry which
        # tree is classified as this specification, so a Spec that moved without
        # the registry moving with it fails rather than passing quietly.
        classified = [
            entry["path"]
            for entry in self.status["classifications"]
            if entry["classification"] == check_audit.DOCUMENTATION
        ]

        self.assertIn(str(self.root.relative_to(check_baseline.CHECKOUT)), classified)

    def test_a_registry_that_classifies_no_such_tree_refuses(self):
        with mock.patch.object(check_audit, "SPEC_SLUG", "no-such-specification"):
            with self.assertRaises(check_audit.AuditError) as refused:
                check_audit.spec_root(self.status)

        self.assertEqual(
            "the status registry classifies 0 trees as no-such-specification",
            str(refused.exception),
        )


class AuditCase(unittest.TestCase):
    """A base for the readings, which are pure functions over one gathered audit."""

    @classmethod
    def setUpClass(cls):
        cls.audit, cls.root, cls.status = check_audit.gather()

    def altered(self, **changes) -> check_audit.Audit:
        return dataclasses.replace(self.audit, **changes)

    def rows_without(self, source: str) -> list[dict[str, str]]:
        return [row for row in self.audit.rows if row["source"] != source]

    def rows_with(self, source: str, **changes: str) -> list[dict[str, str]]:
        return [
            {**row, **changes} if row["source"] == source else row for row in self.audit.rows
        ]

    def tickets_with(self, number: int, **changes) -> dict[int, check_audit.Ticket]:
        return {
            **self.audit.tickets,
            number: dataclasses.replace(self.audit.tickets[number], **changes),
        }


class AuditMapTest(AuditCase):
    """Criteria 1, 2 and 5: one row per requirement, and no row that is prose."""

    def test_the_shipped_map_covers_the_spec(self):
        self.assertEqual([], check_audit.map_errors(self.audit))

    def test_a_requirement_nobody_mapped_is_named_as_missing(self):
        self.assertEqual(
            [f"{STORY}: the spec states it and the map does not"],
            check_audit.map_errors(self.altered(rows=self.rows_without(STORY))),
        )

    def test_a_row_for_a_requirement_the_spec_does_not_state_is_refused(self):
        invented = [*self.audit.rows, {**self.audit.rows[0], "source": "story:999"}]

        self.assertEqual(
            ["story:999: the map claims a requirement the spec does not state"],
            check_audit.map_errors(self.altered(rows=invented)),
        )

    def test_a_requirement_reworded_after_it_was_mapped_stops_matching(self):
        # The whole point of freezing the digest. The evidence may still pass;
        # it was chosen against words that are no longer in the Spec.
        reworded = {**self.audit.requirements, STORY: "As an operator, I want something else."}
        digest = hashlib.sha256(reworded[STORY].encode("utf-8")).hexdigest()

        self.assertEqual(
            [
                f"{STORY}: mapped at {self.audit.rows[0]['sha256'][:12]}"
                f" and the spec now states {digest[:12]}"
            ],
            check_audit.map_errors(self.altered(requirements=reworded)),
        )

    def test_a_row_filed_under_an_area_the_audit_does_not_name_is_refused(self):
        self.assertEqual(
            [f"{STORY}: plumbing is not one of the audited areas"],
            check_audit.map_errors(self.altered(rows=self.rows_with(STORY, area="plumbing"))),
        )

    def test_a_requirement_no_ticket_implements_is_refused(self):
        self.assertEqual(
            [f"{STORY}: no ticket implements it"],
            check_audit.map_errors(self.altered(rows=self.rows_with(STORY, tickets=""))),
        )

    def test_a_requirement_implemented_by_unfinished_work_is_refused(self):
        # Criterion 1's other half: a story is not delivered because a ticket
        # says it will be.
        self.assertEqual(
            [f"{STORY}: ticket 77 is ready-for-agent, not resolved"],
            check_audit.map_errors(self.altered(rows=self.rows_with(STORY, tickets="77"))),
        )

    def test_a_requirement_implemented_by_a_ticket_nobody_wrote_is_refused(self):
        self.assertEqual(
            [f"{STORY}: names ticket 99, which the tracker does not hold"],
            check_audit.map_errors(self.altered(rows=self.rows_with(STORY, tickets="99"))),
        )

    def test_a_requirement_nothing_checks_is_release_blocking(self):
        self.assertEqual(
            [f"{STORY}: no test or gate checks it"],
            check_audit.map_errors(self.altered(rows=self.rows_with(STORY, evidence=""))),
        )

    def test_a_requirement_checked_only_by_prose_is_release_blocking(self):
        # Criterion 5. A document cannot go red, so citing one is the same as
        # citing nothing -- and it is the citation an audit is most tempted by.
        self.assertEqual(
            [f"{STORY}: docs/adr/0003-program-runtime.md is neither a test nor a gate"],
            check_audit.map_errors(
                self.altered(
                    rows=self.rows_with(STORY, evidence="docs/adr/0003-program-runtime.md")
                )
            ),
        )

    def test_a_test_this_checkout_cannot_run_is_refused(self):
        self.assertEqual(
            [f"{STORY}: tests.test_database.NoSuchTest is not a test this checkout can run"],
            check_audit.map_errors(
                self.altered(rows=self.rows_with(STORY, evidence="tests.test_database.NoSuchTest"))
            ),
        )

    def test_a_gate_this_checkout_does_not_ship_is_refused(self):
        self.assertEqual(
            [f"{GATE_BACKED}: gate:tools.check_nothing is not a gate this checkout ships"],
            check_audit.map_errors(
                self.altered(rows=self.rows_with(GATE_BACKED, evidence="gate:tools.check_nothing"))
            ),
        )


class AuditTicketTest(AuditCase):
    """Criterion 3: the audited range is finished, and the tracker proves when."""

    def test_every_audited_ticket_is_resolved_with_a_revision(self):
        self.assertEqual([], check_audit.ticket_errors(self.audit, self.root))

    def test_an_unfinished_ticket_in_the_range_is_named_with_its_status(self):
        errors = check_audit.ticket_errors(
            self.altered(tickets=self.tickets_with(20, status="ready-for-agent")), self.root
        )

        self.assertEqual("ticket 20: ready-for-agent, not resolved", errors[0])
        # And every ticket that was allowed to resolve over it says so too.
        self.assertEqual(
            [
                "ticket 21: blocked by 20, which is ready-for-agent",
                "ticket 23: blocked by 20, which is ready-for-agent",
                "ticket 30: blocked by 20, which is ready-for-agent",
                "ticket 31: blocked by 20, which is ready-for-agent",
            ],
            errors[1:],
        )

    def test_a_resolved_ticket_with_no_criteria_at_all_is_refused(self):
        self.assertEqual(
            ["ticket 20: resolved with no acceptance criteria"],
            check_audit.ticket_errors(
                self.altered(tickets=self.tickets_with(20, criteria=())), self.root
            ),
        )

    def test_an_unticked_criterion_that_defers_to_nothing_is_refused(self):
        self.assertEqual(
            ["ticket 20: unticked criterion names no open ticket: the browser was fast enough"],
            check_audit.ticket_errors(
                self.altered(
                    tickets=self.tickets_with(
                        20, criteria=((False, "the browser was fast enough"),)
                    )
                ),
                self.root,
            ),
        )

    def test_an_unticked_criterion_that_names_finished_work_is_refused(self):
        # A deferral to a resolved ticket is not a deferral. Nobody owes it.
        self.assertEqual(
            ["ticket 20: unticked criterion names no open ticket: closed by ticket 46"],
            check_audit.ticket_errors(
                self.altered(
                    tickets=self.tickets_with(20, criteria=((False, "closed by ticket 46"),))
                ),
                self.root,
            ),
        )

    def test_an_unticked_criterion_that_names_open_work_is_the_shipped_deferral(self):
        self.assertEqual(
            [],
            check_audit.ticket_errors(
                self.altered(
                    tickets=self.tickets_with(
                        20, criteria=((False, "**Partial:** Ticket 78 closes it."),)
                    )
                ),
                self.root,
            ),
        )

    def test_a_ticket_resolved_over_an_unresolved_blocker_is_refused(self):
        self.assertEqual(
            ["ticket 20: blocked by 77, which is ready-for-agent"],
            check_audit.ticket_errors(
                self.altered(tickets=self.tickets_with(20, blockers=(77,))), self.root
            ),
        )

    def test_a_ticket_no_revision_resolved_is_refused(self):
        # The revision is the commit that wrote the resolved status into the
        # file, so a ticket the tracker has no history for cannot claim one.
        self.assertEqual(
            ["ticket 20: no revision resolved it"],
            check_audit.ticket_errors(
                self.altered(tickets=self.tickets_with(20, name="20-never-committed")), self.root
            ),
        )

    def test_the_revision_it_resolves_is_the_commit_that_resolved_the_ticket(self):
        revision = check_audit.resolution(self.root, self.audit.tickets[20])
        shown = subprocess.run(
            ["git", "-C", str(ROOT), "show", "--format=%H", "-s", revision],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertEqual(revision, shown.stdout.strip())


class AuditGraphTest(AuditCase):
    """Criterion 4: the plan is a graph, it terminates, and it terminates at 65."""

    def test_the_shipped_graph_is_acyclic_and_ends_at_the_release(self):
        self.assertEqual([], check_audit.graph_errors(self.audit))

    def test_a_blocker_nobody_wrote_is_named(self):
        # Detaching a ticket from its blockers also detaches everything above it
        # from the release, so this reading is asked for the edge it is about.
        self.assertEqual(
            ["ticket 20: blocked by 99, which does not exist"],
            [
                error
                for error in check_audit.graph_errors(
                    self.altered(tickets=self.tickets_with(20, blockers=(99,)))
                )
                if "does not exist" in error
            ],
        )

    def test_a_cycle_is_reported_as_the_path_that_closes_it(self):
        self.assertEqual(
            ["the dependency graph holds a cycle: 17 -> 20 -> 17"],
            [
                error
                for error in check_audit.graph_errors(
                    self.altered(tickets=self.tickets_with(17, blockers=(20,)))
                )
                if "cycle" in error
            ],
        )

    def test_finished_work_the_release_does_not_rest_on_is_refused(self):
        # The shape tickets 66 through 83 arrived in: resolved, green, and
        # attached to nothing downstream. Ticket 64 names them, which is what
        # makes them part of this release rather than beside it.
        self.assertEqual(
            [f"ticket 83: resolved, and no path reaches ticket 65 from it"],
            check_audit.graph_errors(
                self.altered(
                    tickets=self.tickets_with(
                        64, blockers=tuple(n for n in self.audit.tickets[64].blockers if n != 83)
                    )
                )
            ),
        )

    def test_a_tracker_without_the_release_outcome_cannot_be_audited(self):
        without = {n: t for n, t in self.audit.tickets.items() if n != check_audit.RELEASE_OUTCOME}

        self.assertEqual(
            ["the tracker holds no release outcome: ticket 65"],
            check_audit.graph_errors(self.altered(tickets=without)),
        )


class AuditAreaTest(AuditCase):
    """Criterion 6: the eight subsystems are covered, and each names its anchor."""

    def test_every_audited_area_holds_requirements_and_cites_its_anchors(self):
        self.assertEqual([], check_audit.area_errors(self.audit))

    def test_an_area_the_map_covers_nowhere_is_named(self):
        with mock.patch.dict(check_audit.AREAS, {"mobile": ("tests.test_android",)}):
            self.assertEqual(
                ["mobile: the map covers no requirement in this area"],
                check_audit.area_errors(self.audit),
            )

    def test_an_area_whose_anchor_nothing_cites_is_named(self):
        with mock.patch.dict(check_audit.AREAS, {"skills": ("tests.test_skill", "tests.test_ui")}):
            self.assertEqual(
                ["skills: no requirement in this area is checked by tests.test_ui"],
                check_audit.area_errors(self.audit),
            )


class AuditRegressionTest(AuditCase):
    """Criterion 2's registered half: each prototype defect keeps its tickets."""

    def test_every_registered_regression_names_the_tickets_it_requires(self):
        self.assertEqual([], check_audit.regression_errors(self.audit, self.status))

    def test_a_regression_mapped_without_a_required_ticket_is_refused(self):
        self.assertEqual(
            ["regression:RK-REG-006: the registry requires ticket 17 and the map does not name it"],
            check_audit.regression_errors(
                self.altered(rows=self.rows_with("regression:RK-REG-006", tickets="16")),
                self.status,
            ),
        )


class AuditRunTest(AuditCase):
    """The `--run` half: the cited evidence is executed, and a skip proves nothing."""

    def test_the_selection_is_every_cited_test_at_its_broadest_citation(self):
        selected = check_audit.selected(
            [
                {"evidence": "tests.test_cli.RunCommandTest;gate:tools.check_baseline"},
                {"evidence": "tests.test_cli.RunCommandTest.test_one;tests.test_ui.ServerTest"},
            ]
        )

        # The method is dropped because its case is cited too: `unittest` would
        # otherwise load and run it under both names.
        self.assertEqual(["tests.test_cli.RunCommandTest", "tests.test_ui.ServerTest"], selected)

    def test_a_citation_that_holds_is_evidence(self):
        errors, report = check_audit.run_errors(
            ["tests.test_audit.RunnableProbe.test_this_one_holds"], stream=io.StringIO()
        )

        self.assertEqual([], errors)
        self.assertIn("tests 1", report)

    def test_a_citation_that_stood_down_proves_nothing(self):
        errors, _ = check_audit.run_errors(
            ["tests.test_audit.RunnableProbe.test_this_one_stands_down"], stream=io.StringIO()
        )

        self.assertEqual(
            [
                "test_this_one_stands_down (tests.test_audit.RunnableProbe"
                ".test_this_one_stands_down): skipped, so it proves nothing"
            ],
            errors,
        )


if __name__ == "__main__":
    unittest.main()
