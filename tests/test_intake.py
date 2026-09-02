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
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from redkraken import evaluation, fixture, playbook, skill
from tests import ROOT
from tests.ledger import (
    INTAKE,
    SOURCES,
    TECHNIQUES,
    intake_rows,
    source_rows,
    technique_records,
    written,
    written_records,
)
from tools import check_baseline, check_intake


def shipped(technique: str) -> list[str]:
    """One shipped row, found by the technique it is about rather than by position.

    Position would be a second thing the ledger's order means, and the order is
    the reader's convenience: a row inserted above these would silently move a
    negative onto a different rule.
    """
    for row in intake_rows():
        if row[0] == technique:
            return row
    raise AssertionError(f"no intake row for {technique}")


#: A row that passes, to be broken one rule at a time. It is the shipped row for
#: the technique that produced the recovery fixture, so a negative below changes
#: exactly what its rule is about.
ACCEPTED = dict(zip(check_intake.FIELDS, shipped("host-header-recovery-link")))

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

    def test_no_review_date_has_passed(self):
        # The only version of a review date that gets read is one that fails the
        # suite on the day, which is how the Playbook corpus reads its own. When
        # this fires: re-read the source, check the technique is still what the
        # row says, then move the date or retire what it produced.
        for row in self.rows:
            if row["review_by"] == check_intake.NO_REVIEW:
                continue
            with self.subTest(technique=row["technique"]):
                self.assertGreater(
                    dt.date.fromisoformat(row["review_by"]), dt.date.today(),
                    f"{row['technique']} was due for review on {row['review_by']}:"
                    f" re-read {row['source_url']}, then move the date or retire"
                    f" {row['produced']}",
                )

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

    def test_a_covering_fixture_is_read_by_the_transport_rule_too(self):
        # The rule is about the fixture that is cited, not about which column
        # cited it: a class the containment settles is not graded by a fixture
        # this ledger produced or by one it points at.
        self.assertEqual(
            "host-header-recovery-link: the schema records transport.certificate_trust"
            " as probe_only; a fixture cannot grade it",
            self.error(
                broken(
                    property_class="transport.certificate_trust",
                    produced="covered_by:fixture:url-authority-pair",
                    review_by="-",
                )
            ),
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
        duplicate = list(shipped("refusal-shape-account-oracle"))
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
        again = shipped("graphql-alias-rate-bypass")
        self.assertEqual(
            "duplicate intake technique: graphql-alias-rate-bypass",
            self.refusal(intake_rows() + [again]),
        )

    def test_an_intake_that_refuses_nothing_is_not_reading(self):
        # Covered and ungradeable rows survive the cut deliberately: neither is
        # the judgement this rule is about, which is a technique read and found
        # not worth keeping.
        header, *rows = intake_rows()
        kept = [header] + [row for row in rows if not row[6].startswith("none:")]
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
        # What is left of the window rather than a constant, because the
        # allowance refills and the refusal says when.
        self.assertIn(int(headers["Retry-After"]), range(1, 61))

    def test_one_request_spends_what_it_likes_on_one_variant_only(self):
        batch = {"operations": [{"kind": "render"}] * 200}
        status, answered, _ = self.ask(
            "resource-cost-pair", "vulnerable", "POST", "/api/v1/render", batch
        )
        self.assertEqual((200, 200, 800), (status, answered["completed"], answered["spent"]))
        status, refused, headers = self.ask(
            "resource-cost-pair", "secure", "POST", "/api/v1/render", batch
        )
        self.assertEqual(429, status)
        self.assertEqual((25, 200), (refused["ceiling"], refused["asked"]))
        # Waiting does not make an oversized batch acceptable, so the refusal
        # that names the ceiling carries no `Retry-After` to wait for.
        self.assertIsNone(headers.get("Retry-After"))

    def test_both_halves_of_the_cost_pair_count_requests_identically(self):
        # What makes the class `resource_cost` rather than a missing limit: the
        # limit both variants do have engages at the same request on both.
        one = {"operations": [{"kind": "render"}]}
        for variant in ("vulnerable", "secure"):
            status, refused, _ = self.ask(
                "resource-cost-pair", variant, "POST", "/api/v1/render", one, repeats=21
            )
            self.assertEqual((429, "rate limit exceeded"), (status, refused["error"]), variant)


class LedgerRecordTest(unittest.TestCase):
    """The corpus gate, one rule at a time, from the record that passes.

    Driven from a shipped record rather than a written one, for the reason the
    intake half gives: a record written here would agree with whatever its
    author believed, and this gate exists for the day the ledger and the tree
    stop agreeing.
    """

    @classmethod
    def setUpClass(cls):
        cls.books = frozenset(playbook.PLAYBOOKS)
        cls.skills = frozenset(skill.SKILLS)
        cls.records = check_intake.read_records()
        cls.named = frozenset(record["id"] for record in cls.records)
        cls.accepted = cls.record("exceptional-conditions/02")
        cls.source = check_intake.read_sources()[0]

    @classmethod
    def record(cls, identifier: str) -> dict:
        """One shipped record, found by its id rather than by position."""
        for record in cls.records:
            if record["id"] == identifier:
                return record
        raise AssertionError(f"no ledger record {identifier}")

    def error(self, **changes) -> str:
        return check_intake.record_error(
            {**self.accepted, **changes}, self.books, self.skills
        )

    def row_error(self, **changes) -> str:
        return check_intake.source_row_error({**self.source, **changes}, self.named)

    def test_the_shipped_record_passes(self):
        self.assertEqual("", self.error())

    def test_every_shipped_record_passes(self):
        for record in self.records:
            self.assertEqual(
                "", check_intake.record_error(record, self.books, self.skills)
            )

    def test_a_record_missing_a_field_is_refused(self):
        thinner = {**self.accepted}
        del thinner["okf_trust_tier"]
        self.assertEqual(
            "exceptional-conditions/02: missing okf_trust_tier",
            check_intake.record_error(thinner, self.books, self.skills),
        )

    def test_a_field_the_ledger_does_not_declare_is_refused(self):
        # The other direction, and the one that matters for a corpus that grew
        # by mining: a field one record carries and the rest do not is a field
        # no reader knows to look for.
        self.assertEqual(
            "exceptional-conditions/02: unknown field severity",
            self.error(severity="high"),
        )

    def test_a_prose_note_about_the_finding_path_is_allowed(self):
        self.assertEqual(
            "", self.error(finding_path_note="the door rewrites it before a target sees it")
        )

    def test_an_id_that_is_not_a_playbook_and_an_ordinal_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/two: id is not <playbook>/<NN>",
            self.error(id="exceptional-conditions/two"),
        )

    def test_a_halt_told_through_park_for_human_names_the_code_it_parks_under(self):
        # Ticket 216. The tool refuses a call carrying no `question_code`, so a
        # halt that says who is told and not what it is filed under is a step no
        # Agent can perform as written. Read off the shipped record with the
        # code taken back out, rather than from a sentence written here, because
        # what this rule has to catch is a record that stopped carrying one.
        self.assertEqual(
            "exceptional-conditions/02: a halt told through"
            " mcp__rk2__park_for_human names the question code it parks under",
            self.error(
                stop_conditions=self.accepted["stop_conditions"].replace(
                    " under question code playbook_halt", ""
                )
            ),
        )

    def test_a_record_naming_no_shipped_playbook_is_refused(self):
        self.assertEqual(
            "no-such-book/02: no playbook named no-such-book",
            self.error(id="no-such-book/02", playbook="no-such-book"),
        )

    def test_an_id_under_one_playbook_and_a_field_under_another_is_refused(self):
        # Both halves resolve on their own, which is what makes this worth its
        # own rule: the join below reads the id and the corpus reads the field,
        # so a record that disagrees with itself is read two different ways.
        self.assertEqual(
            "race-conditions/02: id names a playbook the record does not",
            self.error(id="race-conditions/02"),
        )

    def test_a_finding_path_outside_the_five_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: finding path 'maybe' is not one of"
            " reaches, observation_only, blocked, refused, out_of_scope",
            self.error(finding_path="maybe"),
        )

    def test_a_record_naming_no_shipped_skill_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: no skill named read-the-room",
            self.error(required_skill="read-the-room"),
        )

    def test_a_record_naming_no_skill_at_all_is_accepted(self):
        # Empty is a resolution rather than a gap. A technique the shipped
        # Skills do not cover is one a step performs directly.
        self.assertEqual("", self.error(required_skill=""))

    def test_a_source_list_that_is_not_a_list_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: external_sources is not a list",
            self.error(external_sources="two blog posts"),
        )

    def test_a_field_that_says_nothing_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: preconditions is empty",
            self.error(preconditions="   "),
        )

    def test_the_two_fields_that_may_say_nothing_may_say_nothing(self):
        # A technique the shipped Skills do not cover, and a record no ticket
        # has claimed. Both are answers; the rest of the fields are not.
        self.assertEqual("", self.error(required_skill="", owner_ticket=""))

    def test_a_finding_path_the_capability_state_contradicts_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: reaches means the harness is reachable,"
            " and the record says out_of_scope",
            self.error(capability_state="out_of_scope"),
        )

    def test_a_note_that_is_present_and_empty_is_refused(self):
        # It would count towards the report's tally of path notes while saying
        # nothing, which is worse than not being there.
        self.assertEqual(
            "exceptional-conditions/02: finding_path_note is present and says nothing",
            self.error(finding_path_note="  "),
        )

    def test_a_technique_too_short_to_be_a_restatement_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: technique is too short to be a restatement",
            self.error(technique="idor"),
        )

    def test_a_record_carrying_one_machines_home_directory_is_refused(self):
        # The sources table spells the same file with `~`, so a record that
        # kept the absolute path is both a leak and a join that holds only on
        # the machine that built the corpus.
        self.assertEqual(
            "exceptional-conditions/02:"
            " a path under a home directory was written into a shipped file",
            self.error(local_sources=["/home/someone/notes/idor.md"]),
        )

    def test_a_local_source_that_is_not_a_path_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: local_sources holds something that is not a name",
            self.error(local_sources=[""]),
        )

    def test_a_record_written_from_nothing_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: a record written from nothing is not a reading",
            self.error(local_sources=[], external_sources=[]),
        )

    def test_a_source_in_this_checkout_that_is_not_here_is_refused(self):
        # The hundred and eighty-six repo-relative sources are the ones a second
        # reader can open, which is exactly why a dangling one is worth
        # catching: the citation reads as checkable and is not.
        self.assertEqual(
            "exceptional-conditions/02: no file at src/redkraken/playbooks/gone/playbook.md",
            self.error(local_sources=["src/redkraken/playbooks/gone/playbook.md"]),
        )

    def test_a_source_that_walks_out_of_this_checkout_is_refused(self):
        # `..` and an absolute path both resolve to a file that exists, so a
        # rule that only asked whether the file is there would let a citation
        # point anywhere on the machine running the gate.
        for path in ("../../../etc/passwd", "/etc/passwd"):
            self.assertEqual(
                f"exceptional-conditions/02: {path} walks out of this checkout",
                self.error(local_sources=[path]),
                path,
            )

    def test_a_record_filed_under_no_concept_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02:"
            " a record filed under no concept cannot be found again",
            self.error(okf_source_ids=[]),
        )

    def test_a_phrase_too_short_to_name_anything_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: payload_family is too short to name anything",
            self.error(payload_family="x"),
        )

    def test_a_phrase_may_say_there_is_nothing_to_name(self):
        # The four-character `none` is what a field says when the reading found
        # nothing of that kind, and it is shorter than any name.
        self.assertEqual("", self.error(refuted_evidence="none"))

    def test_a_field_padded_with_invisible_characters_is_refused(self):
        # Forty zero-width spaces are neither whitespace to `strip` nor a
        # letter to a reader, so length alone would call this field filled in.
        self.assertEqual(
            "exceptional-conditions/02: technique is too short to be a restatement",
            self.error(technique="\u200b" * 40),
        )

    def test_an_arm_off_a_reachable_path_says_why_it_did_not_run(self):
        self.assertEqual(
            "exceptional-conditions/02: variant neither runs nor says why not",
            self.error(finding_path="blocked", capability_state="blocked", variant="x"),
        )

    def test_an_external_source_carrying_a_fourth_key_is_refused(self):
        # The record refuses an unknown field at the top level for the same
        # reason: a frozen record that can quietly gain a key is not frozen.
        self.assertEqual(
            "exceptional-conditions/02: an external source is not url, title, date_or_version",
            self.error(external_sources=[{
                "url": "https://example.org/a",
                "title": "a page",
                "date_or_version": "undated",
                "exfil": "s3://bucket/creds",
            }]),
        )

    def test_a_handle_that_is_not_a_name_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: mined_from holds something that is not a name",
            self.error(mined_from=[42]),
        )

    def test_an_address_filed_as_absent_is_still_held_to_the_rule(self):
        # `absent` is derived from the address, so it would otherwise be the way
        # round every rule an external source is held to.
        self.assertEqual(
            "exceptional-conditions/02: a source is retrieved over https",
            self.error(external_sources=[{
                "url": "http://operator:secret@example.org/a?session=1",
                "title": "a page nobody may cite",
                "date_or_version": "undated",
            }]),
        )

    def test_an_external_source_that_is_not_an_address_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: an external source is not url, title, date_or_version",
            self.error(external_sources=["https://example.org/a"]),
        )

    def test_a_concept_id_outside_the_mining_namespace_is_refused(self):
        # Its own namespace and not a key into the sources table, which is why
        # the rule is a form and not a lookup.
        self.assertEqual(
            "exceptional-conditions/02: 'WSTG IDNT 04'"
            " is not a concept the mining stage filed under",
            self.error(okf_source_ids=["WSTG IDNT 04"]),
        )

    def test_a_staleness_that_is_not_a_time_is_refused(self):
        self.assertEqual(
            "exceptional-conditions/02: okf_stale_after 'next spring' is not a time",
            self.error(okf_stale_after="next spring"),
        )

    def test_a_record_that_reaches_a_finding_names_three_arms(self):
        self.assertEqual(
            "exceptional-conditions/02: reaches with no control arm to run",
            self.error(control="None."),
        )

    def test_a_reading_that_only_observes_still_names_three_arms(self):
        # `observation_only` is `reachable` too: the reading gets there and
        # stops short of a Finding, which is not a reason to drop an arm.
        self.assertEqual(
            "exceptional-conditions/02: observation_only with no variant arm to run",
            self.error(finding_path="observation_only", variant="TBD"),
        )

    def test_an_arm_too_short_to_be_a_step_is_refused(self):
        # The keyword list catches `None.`; the floor catches everything a
        # half-written record puts there instead.
        self.assertEqual(
            "exceptional-conditions/02: reaches with no baseline arm to run",
            self.error(baseline="-"),
        )

    def test_a_record_that_reaches_nothing_may_have_no_arms_to_name(self):
        # The nineteen refused, thirteen blocked and two out-of-scope records
        # in this state are the point: an arm the harness cannot run is a
        # finding about the harness, and inventing one would hide it.
        self.assertEqual(
            "",
            self.error(
                finding_path="blocked",
                capability_state="blocked",
                control="Not runnable.",
                variant="None.",
            ),
        )

    def test_the_shipped_source_row_passes(self):
        self.assertEqual("", self.row_error())

    def test_a_row_id_that_is_not_a_source_id_is_refused(self):
        self.assertEqual(
            "'not-an-id' is not a source id", self.row_error(id="not-an-id")
        )

    def test_a_source_row_pointing_at_no_record_is_refused(self):
        self.assertEqual(
            "S0001: no ledger record no-such-book/02",
            self.row_error(ledger_id="no-such-book/02"),
        )

    def test_a_source_that_is_neither_local_nor_external_is_refused(self):
        self.assertEqual(
            "S0001: kind 'remembered' is not one of local, external, absent",
            self.row_error(kind="remembered"),
        )

    def test_a_digest_that_is_not_sha256_is_refused(self):
        self.assertEqual(
            "S0001: digest is not sha256 and sixty-four hex digits",
            self.row_error(digest="d083d84e"),
        )

    def test_a_local_source_that_was_never_read_is_refused(self):
        self.assertEqual(
            "S0001: a local file was named and never read",
            self.row_error(digest=""),
        )

    def test_an_external_source_that_did_not_answer_says_so(self):
        # The six rows in this state are why the rule is a note rather than a
        # digest: a page that 404s is still a page the record was written from,
        # and dropping the row would make the record's own count disagree.
        page = {"kind": "external", "url": "https://example.org/a", "digest": ""}
        self.assertEqual(
            "S0001: no digest, and no note saying what happened",
            self.row_error(**page),
        )
        self.assertEqual("", self.row_error(**page, note="HTTPError: 404"))

    def test_an_external_source_is_held_to_the_rule_the_intake_ledger_uses(self):
        # One rule for both tables in this directory, rather than a second
        # opinion beside it. No corpus URL carries a query or a fragment, so
        # the sibling's bar costs this table nothing.
        self.assertEqual(
            "S0001: a source is retrieved over https",
            self.row_error(kind="external", url="http://example.org/a"),
        )

    def test_a_source_nobody_published_carries_no_digest(self):
        # The five rows in this state say the mining stage went looking for a
        # published source of some shape and found none. A digest on one would
        # be a digest of nothing.
        self.assertEqual(
            "S0001: nothing was found here, so nothing was read",
            self.row_error(kind="absent", url=""),
        )
        self.assertEqual("", self.row_error(kind="absent", url="", digest=""))

    def test_a_source_row_carrying_one_machines_home_directory_is_refused(self):
        self.assertEqual(
            "S0001: a path under a home directory was written into a shipped file",
            self.row_error(url="/home/someone/notes/idor.md"),
        )

    def test_a_local_source_titled_anything_but_its_file_name_is_refused(self):
        # The record names the path and nothing else, so the title and the
        # version note have nothing to be compared against. Pinning them keeps
        # the table from becoming a second, unchecked place to write.
        self.assertEqual(
            "S0001: a local source is titled by its file name",
            self.row_error(title="Something Else"),
        )
        self.assertEqual(
            "S0001: a file on disk carries no version note",
            self.row_error(version_note="v2"),
        )

    def test_a_home_directory_in_any_column_is_refused(self):
        # Any of them, not this machine's: a corpus mined elsewhere would leak
        # a different one, and a rule that knew only `/home/` would pass it.
        for path in ("/home/someone/notes", "/Users/someone/notes", "/root/notes",
                     "C:\\Users\\someone\\notes"):
            self.assertEqual(
                "S0001: a path under a home directory was written into a shipped file",
                self.row_error(note=f"read from {path}"),
                path,
            )

    def test_a_source_in_this_checkout_is_hashed_again(self):
        # The hundred and eighty-six sources inside the checkout are the ones a
        # second reader can recompute, so the gate recomputes them rather than
        # only checking the file agrees with itself.
        inside = next(
            row
            for row in check_intake.read_sources()
            if row["kind"] == "local" and not row["url"].startswith("~")
        )
        self.assertEqual("", check_intake.source_row_error(inside, self.named))
        self.assertEqual(
            f"{inside['id']}: {inside['url']} no longer hashes to what was read",
            check_intake.source_row_error(
                {**inside, "digest": "sha256:" + "0" * 64}, self.named
            ),
        )

    def test_a_retrieval_date_that_is_a_shape_and_not_a_day_is_refused(self):
        self.assertEqual(
            "S0001: retrieved '0000-00-00' is not a date",
            self.row_error(retrieved="0000-00-00"),
        )

    def test_an_absent_source_may_not_carry_an_address(self):
        self.assertEqual(
            "S0001: an address was found, so it is not absent",
            self.row_error(kind="absent", url="https://example.org/a"),
        )

    def test_an_absent_source_says_what_was_looked_for(self):
        self.assertEqual(
            "S0001: nothing was found, and nothing says what was looked for",
            self.row_error(kind="absent", url="", title="", note="", digest=""),
        )

    def test_a_retrieval_date_that_is_not_a_date_is_refused(self):
        self.assertEqual(
            "S0001: retrieved 'last summer' is not a date",
            self.row_error(retrieved="last summer"),
        )


class LedgerCorpusTest(unittest.TestCase):
    """The corpus as a whole: the counts, and the two rules no single row breaks."""

    @classmethod
    def setUpClass(cls):
        cls.report = check_intake.check_techniques()

    def refusal(self, records: list[dict], rows: list[list[str]]) -> str:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(check_intake.IntakeError) as refused:
                check_intake.check_techniques(
                    written_records(records, directory),
                    written(rows, directory, SOURCES.name),
                )
        return str(refused.exception)

    def test_the_corpus_resolves_and_the_counts_are_the_ones_reviewed(self):
        self.assertEqual(
            "technique ledger\n"
            "  records                  382   playbooks 51  skills 6  path notes 105\n"
            "  sources                 1536   local 715  external 815  absent 6"
            "  digested 1522\n"
            # The five paths are listed in full rather than only the ones with
            # rows, because a path that fell to zero is the change worth seeing.
            "  reaches                  249\n"
            "  observation_only          25\n"
            "  blocked                   43\n"
            "  refused                   55\n"
            "  out_of_scope              10",
            self.report,
        )

    def test_two_runs_of_the_gate_agree(self):
        self.assertEqual(self.report, check_intake.check_techniques())

    def test_no_record_has_gone_stale(self):
        # Read here rather than in the gate, so the gate stays independent of
        # the day it runs. Same rule the intake half holds its review dates to:
        # the only version of a staleness date that gets read is one that fails
        # the suite on the day. When this fires: re-read the record's sources,
        # check the technique is still what it says, then move the date.
        for record in check_intake.read_records():
            with self.subTest(record=record["id"]):
                self.assertGreater(
                    dt.datetime.fromisoformat(record["okf_stale_after"]),
                    dt.datetime.now(dt.timezone.utc),
                    f"{record['id']} went stale on {record['okf_stale_after']}:"
                    f" re-read its sources, then move the date",
                )

    def test_an_id_claimed_by_two_records_is_refused(self):
        records = technique_records()
        again = next(one for one in records if one["id"] == "exceptional-conditions/02")
        # Two lines, because a repeated id also breaks the run of ordinals under
        # its Playbook. This is the one the test is about.
        self.assertIn(
            "exceptional-conditions/02: 2 records share one id",
            self.refusal(records + [again], source_rows()),
        )

    def test_a_corpus_with_records_cut_off_the_end_is_refused(self):
        # The run of ordinals cannot see this one: a file with the last record
        # of every Playbook removed is still numbered from one with no gap, and
        # it still covers all fifty-one Playbooks.
        records = technique_records()
        last = {one["playbook"]: one["id"] for one in records}
        kept = [one for one in records if one["id"] not in set(last.values())]
        self.assertIn(
            "the reviewed corpus holds 382 records, and this one holds 331",
            self.refusal(kept, source_rows()),
        )

    def test_a_corpus_whose_sources_table_is_empty_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(check_intake.IntakeError) as refused:
                check_intake.check_techniques(
                    written_records(technique_records(), directory),
                    written([list(check_intake.SOURCE_FIELDS)], directory, SOURCES.name),
                )
        self.assertIn(
            "a corpus whose sources table is empty cites nothing", str(refused.exception)
        )

    def test_a_record_whose_id_is_not_text_reports_rather_than_raises(self):
        # The known-id set is built from every record that parsed, so that one
        # bad record does not also report each of its source rows as pointing
        # at nothing. A list cannot go in that set.
        records = technique_records()
        records[0]["id"] = []
        self.assertIn("[]: id is not text", self.refusal(records, source_rows()))

    def test_a_playbook_missing_one_of_its_records_is_refused(self):
        # What refuses a truncated corpus. Cutting a file to its first record
        # per Playbook still covers every Playbook, so coverage alone cannot
        # see it; the run of ordinals can.
        kept = [one for one in technique_records() if one["id"] != "cookies/03"]
        self.assertIn(
            "playbook cookies: 7 records and no cookies/03",
            self.refusal(kept, source_rows()),
        )

    def test_one_page_read_twice_may_not_yield_two_digests(self):
        # What the sources table is for. One page is cited by four records on
        # average, so a digest recorded once per citation is a digest that can
        # disagree with itself.
        rows = source_rows()
        twice = [one for one in rows[1:] if one[3] == rows[1][3]]
        twice[-1][7] = "sha256:" + "0" * 64
        self.assertIn(
            "was read twice, and the two disagree",
            self.refusal(technique_records(), rows),
        )

    def test_a_source_a_record_names_has_a_row_of_its_own(self):
        self.assertEqual(
            "exceptional-conditions/01: local sources: 1 named, 0 in the table,"
            " missing '~/Downloads/Personal-Knowledge-Base/3. Completed/Web attacks/"
            "Insecure Direct Object References (IDOR)/3_Mass_IDOR_Enumeration_INFO.md'",
            self.refusal(technique_records(), source_rows(without="S0001")),
        )

    def test_a_row_pointing_at_a_page_its_record_never_named_is_refused(self):
        # The join is on the address rather than on how many there are. A table
        # that kept the count and changed the page would otherwise pass, and a
        # digest is only evidence of what was read if it was taken from the
        # thing the record cites.
        rows = source_rows()
        for row in rows:
            if row[0] == "S0001":
                row[3] = "~/Downloads/somebody-elses-notes.md"
                row[4] = "somebody-elses-notes.md"
        self.assertEqual(
            "exceptional-conditions/01: local sources: 1 named, 1 in the table,"
            " missing '~/Downloads/Personal-Knowledge-Base/3. Completed/Web attacks/"
            "Insecure Direct Object References (IDOR)/3_Mass_IDOR_Enumeration_INFO.md',"
            " unnamed '~/Downloads/somebody-elses-notes.md'",
            self.refusal(technique_records(), rows),
        )

    def test_a_table_that_retitles_a_page_its_record_named_is_refused(self):
        # Only the digest moved out of the record. The address, the title and
        # the version note are still in both files, so the join compares all
        # three rather than letting one of them drift.
        rows = source_rows()
        page = next(one for one in rows if one[0] == "S0002")
        page[4] = "Something Else Entirely"
        # One address on both sides of the report, because the address is not
        # what moved: the title is part of what the two files have to agree on.
        self.assertEqual(
            f"exceptional-conditions/01: external sources: 1 named, 1 in the table,"
            f" missing {page[3]!r}, unnamed {page[3]!r}",
            self.refusal(technique_records(), rows),
        )

    def test_a_playbook_with_no_record_behind_it_is_refused(self):
        # What refuses a truncated file: a gate that only read what it was
        # given would call an empty ledger consistent with an empty table.
        kept = [one for one in technique_records() if one["playbook"] != "cookies"]
        found = self.refusal(kept, source_rows())
        self.assertIn("no ledger record is about playbook cookies", found)

    def test_both_corpus_files_are_ones_baseline_may_hold(self):
        self.assertIn(TECHNIQUES.name, check_baseline.BASELINE_FILES)
        self.assertIn(SOURCES.name, check_baseline.BASELINE_FILES)


if __name__ == "__main__":
    unittest.main()
