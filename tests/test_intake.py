"""The intake ledger, its gate, and the four fixtures it produced.

Three halves, and the third is the one that makes the other two mean anything.

The first is the shipped ledger read through its gate: sixteen techniques, four
of them produced, and a report two runs agree on. The second is the gate itself,
one rule at a time, driven from the real ledger's rows with one thing changed --
a fixture ledger would agree with whatever its author believed, and this gate
exists for the day the ledger and the tree stop agreeing.

The third serves the four fixtures the ledger claims and asks each pair the
question its class is about. A row saying `fixture:recovery-flow-pair` is a
claim that something on disk grades a technique; without this half the claim is
that a directory exists.
"""

import ast
import hashlib
import http.client
import json
import tempfile
import unittest
from pathlib import Path

from redkraken import evaluation, fixture
from tests import ROOT
from tests.ledger import INTAKE, intake_rows, written
from tools import check_baseline, check_intake


#: A row that passes, to be broken one rule at a time. It is the shipped row for
#: the technique that produced the recovery fixture, so a negative below changes
#: exactly what its rule is about.
ACCEPTED = dict(zip(check_intake.FIELDS, intake_rows()[1]))

#: Where the retrieved pages are not. Named here because criterion 3 is a claim
#: about the whole package rather than about one module: retrieval is a
#: maintainer act, and what ships is the restatement.
PACKAGE = ROOT / "src" / "redkraken"

#: Modules that could fetch a writeup. `http.client` is on the list even though
#: the application uses it everywhere else, because what is checked is the gate
#: and the ledger, not the harness.
NETWORK = {"socket", "ssl", "http", "http.client", "urllib", "urllib.request", "ftplib"}


def broken(**changes: str) -> dict[str, str]:
    return {**ACCEPTED, **changes}


def imported(path: Path) -> set[str]:
    """Every module name one file imports, without importing it to find out."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class IntakeLedgerTest(unittest.TestCase):
    """The ledger as it stands: every row resolves and the report does not move."""

    @classmethod
    def setUpClass(cls):
        cls.rows = check_intake.read_ledger()
        cls.report = check_intake.check()

    def test_every_row_resolves_and_the_counts_are_the_ones_reviewed(self):
        self.assertEqual(
            "technique intake\n"
            "  sources read              16\n"
            "  rows                      16   "
            "produced 4  covered 5  refused 3  ungradeable 4\n"
            # The refusals are the half of the reading that produced no file,
            # and they are listed because a count of them is the only visible
            # evidence that anything was rejected at all.
            "  dead_technique             1\n"
            "  target_specific            1\n"
            "  unreproducible             1\n"
            "  harness_owned              2\n"
            "  normalised_by_the_door     1\n"
            "  protocol_out_of_reach      1",
            self.report,
        )

    def test_two_runs_of_the_gate_agree(self):
        self.assertEqual(self.report, check_intake.check())

    def test_reading_the_ledger_leaves_baseline_untouched(self):
        # Criterion 8: a gate that rewrote what it grades could agree with
        # itself about a ledger nobody wrote.
        before = self.digests()
        check_intake.check()
        self.assertEqual(before, self.digests())

    def digests(self) -> dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "baseline").iterdir())
        }

    def test_the_ledger_is_one_of_the_files_baseline_may_hold(self):
        self.assertIn(INTAKE.name, check_baseline.BASELINE_FILES)

    def test_every_produced_fixture_is_in_the_shipped_corpus(self):
        produced = [
            row["produced"].split(":", 1)[1]
            for row in self.rows
            if row["produced"].startswith("fixture:")
        ]
        self.assertEqual(
            ["recovery-flow-pair", "identifier-oracle-pair",
             "resource-cost-pair", "per-origin-limit-pair"],
            produced,
        )
        for name in produced:
            self.assertIn(name, fixture.FIXTURES)

    def test_the_classes_the_intake_produced_had_no_case_before_it(self):
        # What the ticket asked for: techniques the corpus does not have. A row
        # producing a fixture for a class something else already grades would be
        # a row that read a page and learned nothing, which is what `covered_by`
        # is for.
        produced = {
            row["property_class"]
            for row in self.rows
            if row["produced"].startswith("fixture:")
        }
        graded = {
            one: [name for name, held in fixture.FIXTURES.items() if one in held.classes]
            for one in produced
        }
        self.assertEqual(
            {one: 1 for one in produced},
            {one: len(names) for one, names in graded.items()},
        )

    def test_no_source_is_read_behind_an_account_this_harness_holds(self):
        for row in self.rows:
            self.assertEqual("", check_intake.source_error(row["source_url"]), row["technique"])

    def test_a_restatement_carries_no_report_prose_from_its_source(self):
        # Not provable by a checker and not claimed to be. What is checkable is
        # the size of the claim and that nothing was pasted in wholesale, which
        # is what the bounds hold.
        floor, ceiling = check_intake.RATIONALE
        for row in self.rows:
            self.assertLessEqual(floor, len(row["rationale"]), row["technique"])
            self.assertLessEqual(len(row["rationale"]), ceiling, row["technique"])


class IntakeBoundaryTest(unittest.TestCase):
    """Criterion 3 and 4: what retrieval is, and where it is not."""

    def test_nothing_in_the_package_reads_the_intake_ledger(self):
        found = [
            path.relative_to(ROOT).as_posix()
            for path in PACKAGE.rglob("*.py")
            if "technique-intake" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual([], found)

    def test_the_gate_itself_cannot_fetch_a_writeup(self):
        # The gate is where a retrieval would be convenient to add, so it is
        # where the absence is worth asserting: it reads files this checkout
        # already holds and nothing else.
        self.assertEqual(set(), imported(ROOT / "tools" / "check_intake.py") & NETWORK)

    def test_a_retrieved_page_is_recorded_by_digest_and_not_by_its_bytes(self):
        for row in check_intake.read_ledger():
            self.assertRegex(row["digest"], check_intake.DIGEST)


class IntakeRowTest(unittest.TestCase):
    """The gate, one rule at a time, from the row that passes."""

    @classmethod
    def setUpClass(cls):
        cls.words = check_intake.vocabulary(ROOT)

    def error(self, row: dict[str, str]) -> str:
        found, _ = check_intake.row_error(row, self.words)
        return found

    def state(self, row: dict[str, str]) -> str:
        found, state = check_intake.row_error(row, self.words)
        self.assertEqual("", found)
        return state

    def test_the_shipped_row_passes(self):
        self.assertEqual("produced", self.state(ACCEPTED))

    def test_a_class_outside_the_shipped_vocabulary_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: authentication.magic_link is not a shipped"
            " Property class; a technique that fits none of them proposes a migration",
            self.error(broken(property_class="authentication.magic_link")),
        )

    def test_an_event_kind_is_not_a_property_class(self):
        self.assertEqual(
            "host-header-recovery-link: finding.created is an event kind,"
            " not a Property class",
            self.error(broken(property_class="finding.created")),
        )

    def test_an_output_that_is_not_on_disk_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: there is no fixture recovery-flow-pairs",
            self.error(broken(produced="fixture:recovery-flow-pairs")),
        )

    def test_a_class_the_schema_says_is_unmakeable_cannot_be_graded_by_a_fixture(self):
        self.assertEqual(
            "host-header-recovery-link: the schema records transport.request_framing"
            " as unmakeable; a fixture cannot grade it",
            self.error(broken(property_class="transport.request_framing")),
        )

    def test_producing_nothing_needs_a_reason_from_the_closed_set(self):
        self.assertEqual(
            "host-header-recovery-link: busy is not one of"
            " ['dead_technique', 'target_specific', 'unreproducible']",
            self.error(broken(produced="none:busy", review_by="-")),
        )

    def test_producing_nothing_with_a_reason_is_a_row_that_passes(self):
        self.assertEqual(
            "refused", self.state(broken(produced="none:dead_technique", review_by="-"))
        )

    def test_ungradeable_names_why_the_harness_cannot_stage_it(self):
        self.assertEqual(
            "host-header-recovery-link: hard is not one of"
            " ['harness_owned', 'normalised_by_the_door', 'protocol_out_of_reach']",
            self.error(broken(produced="ungradeable:hard", review_by="-")),
        )

    def test_already_covered_names_what_covers_it(self):
        self.assertEqual(
            "host-header-recovery-link: covered_by names what covers it,"
            " one of fixture, playbook, skill",
            self.error(broken(produced="covered_by:the-other-one", review_by="-")),
        )

    def test_a_covering_output_that_does_not_exist_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: there is no fixture no-such-pair",
            self.error(broken(produced="covered_by:fixture:no-such-pair", review_by="-")),
        )

    def test_what_grades_a_live_technique_carries_a_review_date(self):
        self.assertEqual(
            "host-header-recovery-link: what grades a live technique carries a review date",
            self.error(broken(review_by="-")),
        )

    def test_a_review_date_falls_after_the_retrieval(self):
        self.assertEqual(
            "host-header-recovery-link: a review date falls after the retrieval",
            self.error(broken(review_by=ACCEPTED["retrieved"])),
        )

    def test_a_row_that_produced_nothing_has_nothing_to_review(self):
        self.assertEqual(
            "host-header-recovery-link: nothing was produced, so there is nothing"
            " to review (-)",
            self.error(broken(produced="none:dead_technique")),
        )

    def test_a_source_that_is_not_public_material_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: a source is retrieved over https",
            self.error(broken(source_url="http://example.test/report")),
        )
        self.assertEqual(
            "host-header-recovery-link: a source URL carries no credentials",
            self.error(broken(source_url="https://reader@example.test/report")),
        )
        self.assertEqual(
            "host-header-recovery-link: a source URL carries no query or fragment",
            self.error(broken(source_url="https://example.test/report?token=abcd")),
        )

    def test_a_digest_that_is_not_a_digest_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: digest is sha256:<64 hex> of what was read",
            self.error(broken(digest="sha256:abc")),
        )

    def test_a_page_cannot_be_retrieved_before_it_was_published(self):
        self.assertEqual(
            "host-header-recovery-link: retrieved before it was published",
            self.error(broken(published="2030-01-01")),
        )

    def test_a_publication_date_is_as_precise_as_the_source_states(self):
        for published in ("undated", "2023", "2023-11", "2023-11-14"):
            self.assertEqual("produced", self.state(broken(published=published)))
        self.assertEqual(
            "host-header-recovery-link: published is a date as precise as the"
            " source states, or undated",
            self.error(broken(published="November 2023")),
        )

    def test_a_restatement_the_size_of_a_label_is_refused(self):
        self.assertEqual(
            "host-header-recovery-link: a restatement is between 120 and 600"
            " characters, not 17",
            self.error(broken(rationale="host header thing")),
        )

    def test_a_restatement_carries_no_url(self):
        self.assertEqual(
            "host-header-recovery-link: a restatement carries no URL;"
            " provenance is its own column",
            self.error(broken(rationale=ACCEPTED["rationale"] + " See https://a.test/x")),
        )

    def test_a_technique_is_named_rather_than_numbered(self):
        self.assertEqual(
            "t1: a technique is named in three to eight lowercase words",
            self.error(broken(technique="t1")),
        )


class IntakeCoverageTest(unittest.TestCase):
    """The ledger as a whole: nothing counted twice, nothing produced unclaimed."""

    def refusal(self, rows: list[list[str]]) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = written(rows, directory, INTAKE.name)
            with self.assertRaises(check_intake.IntakeError) as refused:
                check_intake.check(ledger=path)
        return str(refused.exception)

    def test_two_rows_may_not_produce_one_output(self):
        rows = intake_rows()
        duplicate = list(rows[2])
        duplicate[0] = "second-claim-on-one-fixture"
        duplicate[6] = "fixture:recovery-flow-pair"
        self.assertEqual(
            "second-claim-on-one-fixture: duplicate coverage,"
            " host-header-recovery-link already produced fixture:recovery-flow-pair",
            self.refusal(rows + [duplicate]),
        )

    def test_a_fixture_written_from_a_disclosure_is_claimed_by_a_row(self):
        # The other direction of the same rule. A fixture citing this ticket and
        # named by no row is a file in the corpus whose provenance nobody can
        # check, which is the state the ledger exists to make impossible.
        self.assertEqual(
            "no intake row produced fixture recovery-flow-pair,"
            f" which cites {check_intake.INTAKE_TICKET}",
            self.refusal(intake_rows(without="host-header-recovery-link")),
        )

    def test_a_technique_appears_once(self):
        rows = intake_rows()
        self.assertEqual(
            "duplicate intake technique: graphql-alias-rate-bypass",
            self.refusal(rows + [rows[5]]),
        )

    def test_an_intake_that_refuses_nothing_is_not_reading(self):
        rows = intake_rows()
        kept = [rows[0]] + [row for row in rows[1:] if row[6].startswith("fixture:")]
        self.assertEqual(
            "an intake that never refuses anything is an intake that is not reading",
            self.refusal(kept),
        )


class ProducedFixtureTest(unittest.TestCase):
    """The four fixtures, asked the question each one's class is about.

    Both halves of each pair are served from the corpus the catalogue digested,
    so what is exercised is the file a Playbook will be graded against rather
    than a copy of it written for this module.
    """

    def ask(
        self,
        name: str,
        variant: str,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict[str, str] | None = None,
        repeats: int = 1,
    ) -> tuple[int, dict, dict[str, str]]:
        """The last of `repeats` identical requests to one variant, read back."""
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        sent = dict(headers or {})
        if payload is not None:
            sent["Content-Type"] = "application/json"
        with evaluation.served(fixture.FIXTURES[name], variant) as where:
            connection = http.client.HTTPConnection(where.host, where.port, timeout=5)
            try:
                for _ in range(repeats):
                    connection.request(method, path, payload, sent)
                    answer = connection.getresponse()
                    read = answer.read()
            finally:
                connection.close()
        return answer.status, json.loads(read), dict(answer.getheaders())

    def test_a_recovery_link_is_addressed_by_the_caller_on_one_variant_only(self):
        asked = {"email": "dana@fixture.test"}
        elsewhere = {"Host": "attacker.fixture.test"}
        status, vulnerable, _ = self.ask(
            "recovery-flow-pair", "vulnerable", "POST", "/account/recover", asked, elsewhere
        )
        self.assertEqual(202, status)
        self.assertTrue(
            vulnerable["delivered"]["link"].startswith("https://attacker.fixture.test/"),
            vulnerable,
        )
        status, secure, _ = self.ask(
            "recovery-flow-pair", "secure", "POST", "/account/recover", asked, elsewhere
        )
        self.assertEqual(202, status)
        self.assertTrue(
            secure["delivered"]["link"].startswith("https://accounts.fixture.test/"), secure
        )

    def test_the_recovery_route_answers_an_unregistered_address_the_same_way(self):
        # The precision control: a run that read this route as an enumeration
        # oracle would be reporting a class the ground truth does not claim.
        unknown = {"email": "nobody@fixture.test"}
        for variant in ("vulnerable", "secure"):
            status, answered, _ = self.ask(
                "recovery-flow-pair", variant, "POST", "/account/recover", unknown
            )
            self.assertEqual((202, "sent"), (status, answered["status"]), variant)
            self.assertIsNone(answered["delivered"], variant)

    def test_a_refusal_tells_a_registered_address_from_an_unknown_one_on_one_variant(self):
        unknown = {"email": "nobody@fixture.test", "password": "whatever"}
        wrong = {"email": "dana@fixture.test", "password": "whatever"}
        self.assertEqual(
            404, self.ask("identifier-oracle-pair", "vulnerable", "POST", "/session", unknown)[0]
        )
        self.assertEqual(
            401, self.ask("identifier-oracle-pair", "vulnerable", "POST", "/session", wrong)[0]
        )
        for asked in (unknown, wrong):
            self.assertEqual(
                401, self.ask("identifier-oracle-pair", "secure", "POST", "/session", asked)[0]
            )

    def test_both_halves_of_the_oracle_pair_still_authenticate(self):
        correct = {"email": "dana@fixture.test", "password": "correct-horse-9f21"}
        for variant in ("vulnerable", "secure"):
            status, answered, _ = self.ask(
                "identifier-oracle-pair", variant, "POST", "/session", correct
            )
            self.assertEqual((200, "dana@fixture.test"), (status, answered["email"]), variant)

    def test_an_unauthenticated_route_is_counted_by_origin_on_one_variant_only(self):
        sixth = 6
        status, answered, _ = self.ask(
            "per-origin-limit-pair", "vulnerable", "GET", "/api/v1/quotes", repeats=sixth
        )
        self.assertEqual((200, 2), (status, len(answered["quotes"])))
        status, refused, headers = self.ask(
            "per-origin-limit-pair", "secure", "GET", "/api/v1/quotes", repeats=sixth
        )
        self.assertEqual((429, "rate limit exceeded"), (status, refused["error"]))
        self.assertEqual("60", headers["Retry-After"])

    def test_one_request_spends_what_it_likes_on_one_variant_only(self):
        batch = {"operations": [{"kind": "render"}] * 200}
        status, answered, _ = self.ask(
            "resource-cost-pair", "vulnerable", "POST", "/api/v1/render", batch
        )
        self.assertEqual((200, 200, 800), (status, answered["completed"], answered["spent"]))
        status, refused, _ = self.ask(
            "resource-cost-pair", "secure", "POST", "/api/v1/render", batch
        )
        self.assertEqual(429, status)
        self.assertEqual((25, 200), (refused["ceiling"], refused["asked"]))

    def test_both_halves_of_the_cost_pair_count_requests_identically(self):
        # What makes the class `resource_cost` rather than a missing limit: the
        # limit both variants do have engages at the same request on both.
        one = {"operations": [{"kind": "render"}]}
        for variant in ("vulnerable", "secure"):
            status, refused, _ = self.ask(
                "resource-cost-pair", variant, "POST", "/api/v1/render", one, repeats=21
            )
            self.assertEqual((429, "rate limit exceeded"), (status, refused["error"]), variant)


if __name__ == "__main__":
    unittest.main()
