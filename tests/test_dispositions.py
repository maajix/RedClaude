import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import check_baseline, check_dispositions


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "baseline" / "v1-dispositions.json"

#: A row that passes, to be broken one rule at a time. Every negative test below
#: starts here and changes only what the rule under test needs, so a failure
#: names the rule that fired rather than the fixture that rotted.
BUILT = {
    "source": ".claude/agents/web-vuln-hunter.md",
    "sha256": "a" * 64,
    "disposition": "rewritten",
    "replacement": "role:web_hunter",
    "verification": "tests/test_roster.py",
    "rationale": "the v1 web lens the production web hunter is named after",
}


def broken(**changes: str) -> dict[str, str]:
    return {**BUILT, **changes}


def ledger_rows(without: str | None = None) -> list[list[str]]:
    """The shipped ledger as raw rows, optionally missing the row for one source."""
    with (ROOT / "baseline" / "v1-dispositions.tsv").open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.reader(handle, delimiter="\t") if row[0] != without]


def written(rows: list[list[str]], directory: str) -> Path:
    path = Path(directory) / "v1-dispositions.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE).writerows(rows)
    return path


class DispositionLedgerTest(unittest.TestCase):
    """The ledger as it stands: it covers the census exactly and every row resolves."""

    @classmethod
    def setUpClass(cls):
        cls.report = check_dispositions.check()

    def test_every_frozen_artifact_has_exactly_one_resolved_outcome(self):
        self.assertEqual(
            "v1 dispositions\n"
            "  agent_definition     11   rewritten 10  retired 1\n"
            "  skill_directory      28   rewritten 4  absorbed 14  superseded 8  retired 2\n"
            "  playbook_topic       60   rewritten 49  absorbed 1  retired 10\n"
            "  operator_reference  112   absorbed 73  retired 39\n"
            "  sink_pack             9   absorbed 9\n"
            "  reserved              3   superseded 3\n"
            # The per-kind lines are the census by disposition and do not move.
            # `built` and `promised` do, once per migration ticket: 48 built the
            # ten references the analyst's Skill owed, so ten rows crossed, 49
            # built seven Playbooks and the eight pages hanging off them, and 50
            # built eight more Playbooks and their eight pages.
            "  total               223   built 80  promised 91  retired 52",
            self.report,
        )

    def test_the_summary_reconciles_to_the_frozen_census(self):
        # The census is the authority on how many of each kind there are, and it
        # is a different file with a different author. Reading the counts back
        # out of the report is what makes "reconciles exactly" a check rather
        # than an assertion that the same list has the same length as itself.
        counted = {
            line.split()[0]: int(line.split()[1])
            for line in self.report.splitlines()[1:-1]
        }

        self.assertEqual(check_baseline.EXPECTED_COUNTS, counted)
        self.assertEqual(223, sum(counted.values()))

    def test_the_report_does_not_move_between_runs(self):
        self.assertEqual(self.report, check_dispositions.check())

    def test_no_engagement_state_is_read_as_knowledge_input(self):
        # Resolution reads the corpora and the migration text. A checker that
        # reached a database would grade whichever engagement it was pointed at,
        # and two machines would disagree about what v1 became.
        #
        # In a subprocess because `sys.modules` is the process, not the checker:
        # asked in this one, the answer would be about whichever tests ran first.
        reached = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, json;"
                " from tools import check_dispositions;"
                " check_dispositions.check();"
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
        before = {
            path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()
        }

        check_dispositions.check()

        self.assertEqual(
            before, {path.name: path.read_bytes() for path in (ROOT / "baseline").iterdir()}
        )


class DispositionRowTest(unittest.TestCase):
    """One row at a time: what a disposition may say, and what it may not."""

    @classmethod
    def setUpClass(cls):
        cls.policy = check_dispositions.read_policy()
        cls.names = check_dispositions.resolvable_names(ROOT, cls.policy)

    def error(self, row: dict[str, str], kind: str = "agent_definition") -> str:
        found, _ = check_dispositions.row_error(row, kind, self.names, ROOT, self.policy)
        return found

    def state(self, row: dict[str, str], kind: str = "agent_definition") -> str:
        found, state = check_dispositions.row_error(row, kind, self.names, ROOT, self.policy)
        self.assertEqual("", found)
        return state

    def test_a_row_that_names_something_here_is_built(self):
        self.assertEqual("built", self.state(BUILT))

    def test_a_row_that_names_an_open_migration_ticket_is_promised(self):
        self.assertEqual(
            "promised",
            self.state(
                broken(replacement="playbook:api-authorization", verification="ticket:51"),
                kind="playbook_topic",
            ),
        )

    def test_a_replacement_that_is_nowhere_is_a_missing_replacement(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: missing replacement role:mobile_hunter",
            self.error(broken(replacement="role:mobile_hunter")),
        )

    def test_a_resolved_ticket_may_not_leave_the_replacement_unbuilt(self):
        # The day a migration ticket is marked resolved, every row that promised
        # something to it comes due. This is the ledger's self-maintenance:
        # nobody has to remember to look. Driven through 46, which is genuinely
        # resolved, because no migration ticket is yet -- which is the point.
        policy = {**self.policy, "migration_tickets": [*self.policy["migration_tickets"], "46"]}
        found, _ = check_dispositions.row_error(
            broken(replacement="playbook:nothing-built-it", verification="ticket:46"),
            "playbook_topic",
            self.names,
            ROOT,
            policy,
        )

        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: ticket:46 is resolved"
            " and playbook:nothing-built-it is still missing",
            found,
        )

    def test_a_replacement_that_exists_may_not_still_cite_its_ticket(self):
        # The other direction, and the one that keeps the ledger current: the day
        # a Playbook is authored, the row that promised it has to say where the
        # proof is instead of who promised it.
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: role:web_hunter exists,"
            " so cite the proof rather than ticket:48",
            self.error(broken(verification="ticket:48")),
        )

    def test_a_verification_that_is_not_there_is_refused(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: verification tests/test_lens.py is not a file",
            self.error(broken(verification="tests/test_lens.py")),
        )

    def test_a_directory_is_not_a_proof(self):
        # `tests/` exists, and a check that only asked whether the path existed
        # would take that as evidence that a role works.
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: verification tests is not a file",
            self.error(broken(verification="tests")),
        )

    def test_a_ticket_outside_the_migration_is_not_a_contract(self):
        # 78 is a real open ticket in this tracker and has nothing to do with the
        # v1 migration. A row parked against it would read as covered.
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: ticket:78 is not one of the migration tickets",
            self.error(broken(replacement="role:nobody", verification="ticket:78")),
        )

    def test_an_unwritten_ticket_is_not_a_verification(self):
        policy = {**self.policy, "migration_tickets": [*self.policy["migration_tickets"], "99"]}
        found, _ = check_dispositions.row_error(
            broken(replacement="role:nobody", verification="ticket:99"),
            "agent_definition",
            self.names,
            ROOT,
            policy,
        )

        self.assertEqual(".claude/agents/web-vuln-hunter.md: ticket:99 is not a ticket", found)

    def test_a_ticket_with_no_status_is_not_an_open_ticket(self):
        # An issue file with no `Status:` line is unlabelled, not open. Reading
        # the absence as "not resolved" would let a row be promised to a ticket
        # nobody is triaging.
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "issues").mkdir()
            (Path(directory) / "issues" / "99-untriaged.md").write_text("# 99 - untriaged\n")
            found, _ = check_dispositions.row_error(
                broken(replacement="role:nobody", verification="ticket:99"),
                "agent_definition",
                self.names,
                Path(directory),
                {"issue_root": "issues", "migration_tickets": ["99"]},
            )

        self.assertEqual(".claude/agents/web-vuln-hunter.md: ticket:99 has no status", found)

    def test_a_reference_may_not_be_the_thing_everyone_loads(self):
        # v1's failure mode exactly: a document that is context for whoever is
        # running. A reference resolves under one Skill or one Playbook or it is
        # not a reference.
        self.assertEqual(
            "playbooks/sql-injection/blind.md: 'references/blind.md'"
            " is not a bounded reference attachment",
            self.error(
                broken(
                    source="playbooks/sql-injection/blind.md",
                    disposition="absorbed",
                    replacement="reference:references/blind.md",
                    verification="ticket:53",
                ),
                kind="operator_reference",
            ),
        )

    def test_an_impossible_disposition_for_the_kind_is_refused(self):
        self.assertEqual(
            "playbooks/api/pagination.md: a operator_reference cannot be rewritten",
            self.error(broken(source="playbooks/api/pagination.md"), kind="operator_reference"),
        )

    def test_a_disposition_may_not_name_the_wrong_kind_of_thing(self):
        # Absorbed into a role is how a v1 document becomes an Agent's ambient
        # authority again, which is the shape this migration exists to leave
        # behind.
        self.assertEqual(
            ".claude/skills/access-control: absorbed may name property_class"
            " or vocabulary or reference, not role",
            self.error(
                broken(
                    source=".claude/skills/access-control",
                    disposition="absorbed",
                    replacement="role:web_hunter",
                ),
                kind="skill_directory",
            ),
        )

    def test_an_unregistered_retirement_scope_is_refused(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: retirement scope 'ios' is not registered",
            self.error(
                broken(
                    disposition="retired",
                    replacement="retired:ios",
                    verification="baseline/v1-dispositions.json",
                )
            ),
        )

    def test_a_retirement_is_verified_by_the_register(self):
        # A retirement cited against a test file would be citing something that
        # cannot be evidence for a deliberate absence: no test passes because
        # android is gone. The register is where the reason and the reversal are.
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: a retirement is verified by the register,"
            " not tests/test_roster.py",
            self.error(broken(disposition="retired", replacement="retired:android")),
        )

    def test_the_register_is_not_evidence_that_something_works(self):
        # The mirror of the rule above, and the reason it is a rule: the file
        # that records intentions would otherwise pass as proof of any of them.
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: the register records retirements,"
            " it does not prove one exists",
            self.error(broken(verification="baseline/v1-dispositions.json")),
        )

    def test_a_row_without_a_rationale_is_refused(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: no rationale",
            self.error(broken(rationale="   ")),
        )

    def test_an_unknown_disposition_is_refused(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: unknown disposition 'deferred'",
            self.error(broken(disposition="deferred")),
        )

    def test_a_replacement_without_a_namespace_is_refused(self):
        self.assertEqual(
            ".claude/agents/web-vuln-hunter.md: 'web_hunter' is not a namespaced replacement",
            self.error(broken(replacement="web_hunter")),
        )


class DispositionCoverageTest(unittest.TestCase):
    """The ledger against the census: nothing uncovered, nothing counted twice."""

    def refusal(self, rows: list[list[str]]) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = written(rows, directory)

            with self.assertRaises(check_dispositions.LedgerError) as refused:
                check_dispositions.check(ledger=path)
        return str(refused.exception)

    def test_a_deleted_row_names_the_artifact_that_lost_its_outcome(self):
        self.assertEqual(
            "no disposition for v1 artifact: playbooks/graphql/README.md",
            self.refusal(ledger_rows(without="playbooks/graphql/README.md")),
        )

    def test_a_row_the_census_does_not_hold_is_refused(self):
        rows = ledger_rows(without="playbooks/graphql/README.md")
        rows.append([
            "playbooks/invented/README.md", "b" * 64, "rewritten",
            "playbook:invented", "ticket:49", "authored from nowhere",
        ])

        self.assertIn(
            "disposition for something the census does not hold: playbooks/invented/README.md",
            self.refusal(rows),
        )

    def test_a_disposition_taken_against_a_stale_hash_is_refused(self):
        rows = [
            [row[0], "c" * 64, *row[2:]] if row[0] == "playbooks/graphql/README.md" else row
            for row in ledger_rows()
        ]

        self.assertIn(
            "playbooks/graphql/README.md: disposition was taken against a stale source hash",
            self.refusal(rows),
        )

    def test_two_rows_may_not_claim_one_replacement(self):
        rows = [
            [*row[:3], "playbook:graphql", *row[4:]] if row[0] == "playbooks/grpc/README.md" else row
            for row in ledger_rows()
        ]

        self.assertIn(
            "playbooks/grpc/README.md: duplicate coverage,"
            " playbooks/graphql/README.md already claims playbook:graphql",
            self.refusal(rows),
        )

    def test_five_lenses_may_share_one_role(self):
        # The negative control for the rule above. Collapsing five v1 web Agents
        # into one role is the roster working, so `role` is deliberately not an
        # exclusive namespace and the ledger that ships proves it.
        claims = [
            row["replacement"]
            for row in check_dispositions.read_ledger()
            if row["replacement"] == "role:web_hunter"
        ]

        self.assertEqual(5, len(claims))

    def test_many_v1_documents_may_share_one_runtime_control(self):
        # The same exemption for the other three shared namespaces, since a
        # migration that could not collapse would not be a migration.
        shared = {
            row["replacement"]
            for row in check_dispositions.read_ledger()
            for namespace in [row["replacement"].split(":", 1)[0]]
            if namespace in {"control", "property_class", "retired"}
        }

        self.assertLess(len(shared), 223)
        self.assertNotIn("control", check_dispositions.EXCLUSIVE)

    def test_a_source_may_not_be_dispositioned_twice(self):
        rows = ledger_rows()
        rows.append(rows[-1])

        self.assertIn("duplicate disposition source: ", self.refusal(rows))

    def test_a_row_that_is_not_the_declared_width_is_refused(self):
        # A surplus column is the quiet way a frozen table gains a field: every
        # named column still reads, and the seventh goes somewhere nobody looks.
        rows = [
            [*row, "and one more"] if row[0] == "playbooks/graphql/README.md" else row
            for row in ledger_rows()
        ]

        self.assertIn(
            "malformed disposition row: playbooks/graphql/README.md", self.refusal(rows)
        )


class DispositionPolicyTest(unittest.TestCase):
    """The closed vocabularies the rows draw on."""

    def policy(self, **changes) -> Path:
        document = json.loads(POLICY.read_text())
        document.update(changes)
        path = Path(self.directory) / "v1-dispositions.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.directory = holder.name

    def test_a_retirement_must_say_what_would_bring_it_back(self):
        path = self.policy(retirements=[{"scope": "android", "reason": "out of scope"}])

        with self.assertRaisesRegex(
            check_dispositions.LedgerError, "retirement needs a reason and a reversal: android"
        ):
            check_dispositions.read_policy(path)

    def test_a_scope_nothing_is_retired_under_is_refused(self):
        path = self.policy(
            retirements=[
                *json.loads(POLICY.read_text())["retirements"],
                {"scope": "ios", "reason": "never in scope", "reversal": "never"},
            ]
        )

        with self.assertRaises(check_dispositions.LedgerError) as refused:
            check_dispositions.check(policy_path=path)

        self.assertEqual(
            "retirement scope nothing is retired under: ios", str(refused.exception)
        )

    def test_the_issue_root_must_be_a_directory_in_this_checkout(self):
        path = self.policy(issue_root="docs/specs/nothing-here")

        with self.assertRaisesRegex(
            check_dispositions.LedgerError, "issue root does not exist"
        ):
            check_dispositions.read_policy(path)

    def test_the_migration_tickets_must_be_registered(self):
        path = self.policy(migration_tickets=[])

        with self.assertRaisesRegex(
            check_dispositions.LedgerError, "migration tickets must be present and numeric"
        ):
            check_dispositions.read_policy(path)

    def test_a_registered_ticket_is_open_or_has_no_row_left_citing_it(self):
        # The set is small enough to read, so read it: a number in here that
        # names nothing would silently turn every row citing it into a refusal
        # nobody expected. A registered ticket stays registered after it lands
        # -- 48 is resolved and its ten rows are built -- so what has to hold is
        # the pair: an open ticket is a promise anybody can still call in, and a
        # resolved one is a promise with nothing left citing it.
        policy = check_dispositions.read_policy()
        promised = {
            row["verification"].removeprefix("ticket:")
            for row in check_dispositions.read_ledger()
            if row["verification"].startswith("ticket:")
        }

        for number in policy["migration_tickets"]:
            with self.subTest(ticket=number):
                status = check_dispositions.ticket_status(ROOT, policy["issue_root"], number)

                self.assertIn(status, ("ready-for-agent", "resolved"), number)
                self.assertEqual(status == "resolved", number not in promised, number)


class DispositionVocabularyTest(unittest.TestCase):
    """Where the resolvable names come from, since none of them is written here."""

    @classmethod
    def setUpClass(cls):
        cls.names = check_dispositions.resolvable_names(ROOT, check_dispositions.read_policy())

    def test_property_classes_are_read_from_the_schema_corpus(self):
        self.assertIn("authorization.object_ownership", self.names["property_class"])
        self.assertIn("transport.request_framing", self.names["property_class"])
        self.assertIn("authorization", self.names["property_class"])
        self.assertNotIn("authz.horizontal", self.names["property_class"])

    def test_a_vocabulary_is_what_the_schema_calls_reference_data(self):
        # Not a second list of table names kept beside the checker: a vocabulary
        # is exactly a table every Program shares, and the schema registers those
        # in one place already.
        self.assertIn("property_class_families", self.names["vocabulary"])
        self.assertNotIn("tasks", self.names["vocabulary"])

    def test_a_control_is_a_module_of_the_application(self):
        self.assertIn("scope", self.names["control"])
        self.assertNotIn("launch", self.names["control"])
        self.assertNotIn("startup", self.names["control"])

    def test_the_insert_reader_takes_the_first_column_of_every_row(self):
        found = check_dispositions.inserted_ids(
            "INSERT INTO t (id, note) VALUES\n"
            " ('one','a note about (parentheses)'),\n"
            " ('two','it''s quoted');\n"
            "INSERT INTO other (id) VALUES ('three');\n",
            "t",
        )

        self.assertEqual({"one", "two"}, found)


if __name__ == "__main__":
    unittest.main()
