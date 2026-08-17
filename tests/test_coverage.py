import dataclasses
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from redkraken import playbook, roster, skill

from tests.ledger import ledger_rows, written
from tools import check_baseline, check_coverage, check_dispositions


ROOT = Path(__file__).resolve().parents[1]

#: One v1 topic that got a Playbook, and the Playbook it got. Used wherever a
#: test needs a row it can break: it is a `rewritten` `playbook_topic`, which is
#: the shape criterion 2 counts, and its replacement is in the corpus.
TOPIC = "playbooks/graphql/README.md"
REPLACEMENT = "playbook:graphql"


class CoverageGateTest(unittest.TestCase):
    """The tree as it stands: the migration's plan and the checkout agree."""

    @classmethod
    def setUpClass(cls):
        cls.report = check_coverage.check()

    def test_the_report_is_the_migration_plan_measured_against_the_tree(self):
        self.assertEqual(
            "v1 coverage\n"
            # Every number here is counted from the ledger and the corpus rather
            # than printed from the plan, so this is the plan and the tree
            # agreeing rather than the plan quoted twice.
            "  in-scope playbooks      49   loadable 49  frozen 49\n"
            "  in-scope references     73   attached 73\n"
            "  sink packs               9   attached 9\n"
            "  absorbed topics          1   attached 1\n"
            "  retired: android        52   agent_definition 1  skill_directory 2"
            "  playbook_topic 10  operator_reference 39\n"
            # `catalogue` counts what this checkout ships, which is the
            # forty-nine replacements plus whatever v2 authored for itself --
            # `object-ownership` and the one reference hanging off it, which is
            # why the reference count is one above the ledger's eighty-three
            # claims.
            "  catalogue               50   skills 6  references 84\n"
            "  census                 223   reconciled",
            self.report,
        )

    def test_the_report_does_not_move_between_runs(self):
        self.assertEqual(self.report, check_coverage.check())

    def test_the_gate_refuses_what_the_row_gate_refuses(self):
        # One command, two gates. A ledger that does not resolve has no shape
        # worth measuring, so the closing gate does not get its own opinion
        # about a row: it raises the row gate's error, unchanged.
        with tempfile.TemporaryDirectory() as directory:
            path = written(ledger_rows(without=TOPIC), directory)

            with self.assertRaises(check_dispositions.LedgerError) as refused:
                check_coverage.check(ledger=path)

        self.assertEqual(f"no disposition for v1 artifact: {TOPIC}", str(refused.exception))

    def test_no_engagement_state_is_read_as_knowledge_input(self):
        # The row gate's rule, restated because this gate could break it on its
        # own: coverage is a property of the corpus on disk, and a checker that
        # reached a database would answer differently on two machines.
        reached = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, json;"
                " from tools import check_coverage;"
                " check_coverage.check();"
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

    def test_checking_writes_nothing(self):
        before = {path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()}

        check_coverage.check()

        self.assertEqual(
            before, {path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()}
        )

    def test_the_command_prints_the_report_and_succeeds(self):
        run = subprocess.run(
            [sys.executable, "-B", "-m", "tools.check_coverage"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(self.report + "\n", run.stdout)


class CoveragePlanTest(unittest.TestCase):
    """Criterion 1's arithmetic: the plan spends the frozen census exactly."""

    def test_the_shipped_plan_spends_every_kind_it_speaks_for(self):
        self.assertEqual([], check_coverage.plan_errors())

    def test_the_totals_it_spends_against_are_the_census_ticket_s(self):
        # The reason this reading is not circular: the right-hand side is a
        # different file with a different author, frozen before any of these
        # migration tickets was written.
        self.assertEqual(
            {"playbook_topic": 60, "operator_reference": 112, "sink_pack": 9},
            {
                kind: check_baseline.EXPECTED_COUNTS[kind]
                for kind in ("playbook_topic", "operator_reference", "sink_pack")
            },
        )

    def test_a_plan_one_playbook_short_leaves_a_topic_unspent(self):
        with mock.patch.object(check_coverage, "IN_SCOPE_PLAYBOOKS", 48):
            self.assertEqual(
                ["the plan spends 59 of the census's 60 playbook_topic"],
                check_coverage.plan_errors(),
            )

    def test_a_retirement_the_plan_forgot_leaves_a_reference_unspent(self):
        split = {**check_coverage.RETIRED_BY_SCOPE["android"], "operator_reference": 38}

        with mock.patch.dict(check_coverage.RETIRED_BY_SCOPE, {"android": split}):
            self.assertEqual(
                ["the plan spends 111 of the census's 112 operator_reference"],
                check_coverage.plan_errors(),
            )


class CoverageCase(unittest.TestCase):
    """A base for the readings, which are pure functions over one gathered tree.

    Each reading is asked against the real coverage with one thing changed,
    rather than against a checkout somebody broke: the readings are what the gate
    is, and a test that had to delete a Playbook from `src/` to reach one would
    be testing the filesystem.
    """

    @classmethod
    def setUpClass(cls):
        cls.policy = check_dispositions.read_policy()
        cls.coverage = check_coverage.gather(check_dispositions.LEDGER, cls.policy)

    def altered(self, **changes) -> check_coverage.Coverage:
        return dataclasses.replace(self.coverage, **changes)

    def rows_without(self, source: str) -> list[dict[str, str]]:
        return [row for row in self.coverage.rows if row["source"] != source]

    def rows_with(self, source: str, **changes: str) -> list[dict[str, str]]:
        return [
            {**row, **changes} if row["source"] == source else row for row in self.coverage.rows
        ]


class CoverageCensusTest(CoverageCase):
    """Criterion 1: the ledger covers the frozen census, kind by kind."""

    def test_the_shipped_ledger_reconciles(self):
        self.assertEqual([], check_coverage.census_errors(self.coverage))

    def test_a_kind_the_ledger_is_short_of_names_the_kind_and_both_counts(self):
        self.assertEqual(
            ["playbook_topic: the ledger holds 59 of the census's 60"],
            check_coverage.census_errors(self.altered(rows=self.rows_without(TOPIC))),
        )


class CoverageCatalogueTest(CoverageCase):
    """Criterion 2: the forty-nine exist, load, and ship the text on record."""

    def test_the_shipped_catalogue_closes(self):
        self.assertEqual([], check_coverage.catalogue_errors(self.coverage))

    def test_every_in_scope_playbook_is_loadable_by_one_role(self):
        # The positive control for the refusal below, and criterion 2's own
        # words. It is a property of the roster rather than of the Playbook:
        # a Playbook whose Skills are spread across two roles is two halves that
        # never meet inside one Agent run.
        named = self.coverage.replacements("playbook_topic", "rewritten", "playbook")

        self.assertEqual(49, len(set(named)))
        for name in sorted(set(named)):
            with self.subTest(playbook=name):
                self.assertTrue(roster.loadable(playbook.PLAYBOOKS[name]))

    def test_a_plan_of_forty_nine_refuses_a_ledger_that_names_fewer(self):
        found = check_coverage.catalogue_errors(self.altered(rows=self.rows_without(TOPIC)))

        self.assertEqual(
            ["the plan is 49 in-scope Playbooks and the ledger names 48"], found
        )

    def test_a_replacement_the_corpus_does_not_hold_is_named(self):
        rows = self.rows_with(TOPIC, replacement="playbook:never-written")

        self.assertIn(
            "in-scope Playbook never-written is not in the corpus",
            check_coverage.catalogue_errors(self.altered(rows=rows)),
        )

    def test_a_registration_that_drifted_from_the_shipped_text_is_named(self):
        # What "hash-specific evaluation" rests on. The verdict is taken at the
        # digest the database holds, so a registration that no longer matches the
        # file means every promotion resting on it is about another document.
        one = playbook.PLAYBOOKS["graphql"]
        drifted = {**self.coverage.registered, one.path: "0" * 64}

        self.assertIn(
            f"{one.path}: registered at {'0' * 12} and ships {one.sha256[:12]}",
            check_coverage.catalogue_errors(self.altered(registered=drifted)),
        )

    def test_a_playbook_no_migration_registers_is_named(self):
        one = playbook.PLAYBOOKS["graphql"]
        absent = {
            path: digest
            for path, digest in self.coverage.registered.items()
            if path != one.path
        }

        self.assertIn(
            f"{one.path}: the schema corpus registers no such Playbook",
            check_coverage.catalogue_errors(self.altered(registered=absent)),
        )

    def test_the_last_migration_to_register_a_playbook_is_the_one_read(self):
        # Registration is an upsert and the corpus is concatenated in apply
        # order, so a Playbook re-frozen by a later ticket is held at the later
        # digest. Reading the first would make a re-text look like drift.
        found = check_coverage.registered_playbooks(
            "INSERT INTO playbooks (path, source_sha256) VALUES\n"
            f" ('playbooks/one/playbook.md',\n  '{'a' * 64}');\n"
            "INSERT INTO playbooks (path, source_sha256) VALUES\n"
            f" ('playbooks/one/playbook.md',\n  '{'b' * 64}');\n"
        )

        self.assertEqual({"playbooks/one/playbook.md": "b" * 64}, found)

    def test_every_shipped_playbook_is_registered_at_the_text_it_ships(self):
        for name, one in sorted(playbook.PLAYBOOKS.items()):
            with self.subTest(playbook=name):
                self.assertEqual(one.sha256, self.coverage.registered.get(one.path))


class CoverageRetirementTest(CoverageCase):
    """Criterion 3: the split by kind, under a scope with a reversal on record."""

    def test_the_shipped_retirements_account_for_themselves(self):
        self.assertEqual([], check_coverage.retirement_errors(self.coverage))

    def test_one_more_retirement_of_a_kind_is_named_with_both_counts(self):
        rows = self.rows_with(
            TOPIC,
            disposition="retired",
            replacement="retired:android",
            verification="baseline/v1-dispositions.json",
        )

        self.assertIn(
            "android: 11 of playbook_topic retired where the register accounts for 10",
            check_coverage.retirement_errors(self.altered(rows=rows)),
        )

    def test_a_kind_the_register_says_nothing_about_may_not_retire(self):
        rows = self.rows_with(
            "playbooks/index.md",
            disposition="retired",
            replacement="retired:android",
            verification="baseline/v1-dispositions.json",
        )

        self.assertIn(
            "android: reserved may not be retired: nothing in the register accounts for it",
            check_coverage.retirement_errors(self.altered(rows=rows)),
        )

    def test_a_retirement_under_a_scope_the_plan_never_split_is_named(self):
        # Criterion 3 is about the Android scope by name. A second scope can be
        # registered as properly as the first -- reason, reversal and all -- and
        # the row gate would take it; what it would not have is a reversal
        # written against these artifacts, which is the whole of what makes a
        # retirement reversible rather than a deletion with a note beside it.
        rows = self.rows_with(
            TOPIC,
            disposition="retired",
            replacement="retired:mobile",
            verification="baseline/v1-dispositions.json",
        )

        self.assertIn(
            f"{TOPIC}: retired under retired:mobile, which the plan writes no split for",
            check_coverage.retirement_errors(self.altered(rows=rows)),
        )

    def test_the_one_absorbed_topic_is_counted_and_a_second_is_refused(self):
        rows = self.rows_with(
            TOPIC,
            disposition="absorbed",
            replacement="reference:skills/analyse-source/references/frameworks.md",
        )

        self.assertIn(
            "the plan absorbs 1 v1 topic as reference material and the ledger absorbs 2",
            check_coverage.retirement_errors(self.altered(rows=rows)),
        )


class CoverageReferenceTest(CoverageCase):
    """Criterion 4: every absorbed page is attached, and nothing sits loose."""

    def test_the_shipped_references_are_all_attached(self):
        self.assertEqual([], check_coverage.reference_errors(self.coverage))

    def test_a_reference_belongs_to_exactly_one_document(self):
        # "Bounded" is a property of the path rather than of a rule somebody
        # applies: the first two segments are the document, so there is no
        # spelling of a reference that belongs to everybody.
        for name, owner in sorted(self.coverage.declared.items()):
            with self.subTest(reference=name):
                parent, document, directory, _ = name.split("/")
                self.assertIn(parent, ("skills", "playbooks"))
                self.assertEqual("references", directory)
                self.assertEqual(f"{parent.removesuffix('s')} {document}", owner)

    def test_a_page_no_document_declares_is_named(self):
        loose = "playbooks/graphql/references/nobody-asked-for-this.md"

        self.assertEqual(
            [f"{loose}: sits in a references directory no document declares it from"],
            check_coverage.reference_errors(
                self.altered(present=self.coverage.present | {loose})
            ),
        )

    def test_a_row_whose_page_lost_its_document_is_named_with_the_row(self):
        # How a reference outlives the Playbook it was written for: the ledger
        # row still resolves against the filesystem, and nothing can reach the
        # page any more.
        orphaned = "playbooks/graphql/references/api-graphql.md"
        declared = {
            name: owner for name, owner in self.coverage.declared.items() if name != orphaned
        }

        found = check_coverage.reference_errors(self.altered(declared=declared))

        self.assertIn(f"{orphaned} is attached to no document", "\n".join(found))

    def test_the_two_absorbing_kinds_are_counted_apart(self):
        # A sink pack absorbed into vocabulary rather than into a page still
        # resolves -- `absorbed` may name either -- and it is no longer one of
        # the nine documents somebody can be handed, which is what the count is.
        rows = self.rows_with(
            "playbooks/code-review/sinks-go.md", replacement="vocabulary:property_class_families"
        )

        self.assertIn(
            "the plan absorbs 9 of sink_pack and the ledger absorbs 8",
            check_coverage.reference_errors(self.altered(rows=rows)),
        )


class CoverageSkillTest(CoverageCase):
    """Criterion 5's remaining half: nothing in the corpus is dangling."""

    def test_no_skill_is_dangling(self):
        self.assertEqual([], check_coverage.skill_errors(self.coverage))

    def test_every_skill_is_named_by_a_playbook_and_held_by_a_role(self):
        named = {name for one in playbook.PLAYBOOKS.values() for name in one.skills}
        granted = {name for role in roster.ROLES.values() for name in role.skills}

        self.assertEqual(set(skill.SKILLS), named)
        self.assertEqual(set(skill.SKILLS), granted)


class CoverageDriftTest(unittest.TestCase):
    """Criterion 6: drift names the artifact rather than the count.

    Through `check()` rather than through a reading, because what the criterion
    asks about is the command an operator runs. Three of the four ways a v1
    artifact can drift -- gone, arrived, edited -- are row-level and the row gate
    is where they fire; the fourth is a shape only the closing gate can see. The
    closing gate's other artifact-naming refusals are reached from
    `CoverageCatalogueTest` and `CoverageReferenceTest`, where a drifted
    registration and an orphaned page each name their path.
    """

    def refusal(self, rows: list[list[str]], policy: dict | None = None) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = written(rows, directory)
            policy_path = check_dispositions.POLICY
            if policy is not None:
                policy_path = Path(directory) / "v1-dispositions.json"
                policy_path.write_text(json.dumps(policy), encoding="utf-8")

            with self.assertRaises(
                (check_dispositions.LedgerError, check_coverage.CoverageError)
            ) as refused:
                check_coverage.check(ledger=path, policy_path=policy_path)
        return str(refused.exception)

    def test_an_artifact_that_lost_its_outcome_is_named(self):
        self.assertEqual(
            f"no disposition for v1 artifact: {TOPIC}", self.refusal(ledger_rows(without=TOPIC))
        )

    def test_an_artifact_the_census_does_not_hold_is_named(self):
        rows = ledger_rows(without=TOPIC)
        rows.append([
            "playbooks/invented/README.md", "b" * 64, "rewritten",
            "playbook:invented", "tests/test_playbook.py", "authored from nowhere",
        ])

        self.assertIn(
            "disposition for something the census does not hold:"
            " playbooks/invented/README.md",
            self.refusal(rows),
        )

    def test_a_modified_artifact_is_named(self):
        rows = [
            [row[0], "c" * 64, *row[2:]] if row[0] == TOPIC else row for row in ledger_rows()
        ]

        self.assertIn(
            f"{TOPIC}: disposition was taken against a stale source hash", self.refusal(rows)
        )

    def test_two_rows_claiming_one_replacement_are_named_by_the_row_gate(self):
        # A row-level fault, and it names both artifacts rather than reporting
        # that the plan's forty-nine has become forty-eight. The closing gate
        # never sees this ledger: the row gate raises first, which is what
        # `check` promises.
        rows = [
            [*row[:3], REPLACEMENT, *row[4:]] if row[0] == "playbooks/grpc/README.md" else row
            for row in ledger_rows()
        ]

        self.assertIn(
            "playbooks/grpc/README.md: duplicate coverage,"
            f" {TOPIC} already claims {REPLACEMENT}",
            self.refusal(rows),
        )

    def test_a_shape_no_row_can_show_is_named_by_the_closing_gate(self):
        # The closing gate's own half, end to end. Every row here resolves: the
        # second scope is registered with a reason and a reversal, something is
        # retired under it, and the row gate has nothing left to object to. What
        # is wrong is that the plan wrote no split for that scope, so the
        # reversal on record accounts for none of what it took -- and the refusal
        # names the artifact that left.
        registered = check_dispositions.read_policy()
        policy = {
            **registered,
            "retirements": [
                *registered["retirements"],
                {
                    "scope": "mobile",
                    "reason": "a second scope, registered as properly as the first",
                    "reversal": "whatever this scope's reversal would one day be",
                },
            ],
        }
        rows = [
            [row[0], row[1], "retired", "retired:mobile", "baseline/v1-dispositions.json", row[5]]
            if row[0] == TOPIC
            else row
            for row in ledger_rows()
        ]

        self.assertIn(
            f"{TOPIC}: retired under retired:mobile, which the plan writes no split for",
            self.refusal(rows, policy=policy),
        )


if __name__ == "__main__":
    unittest.main()
