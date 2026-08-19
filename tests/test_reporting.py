"""What `render` does to a source bundle, with no database anywhere near it.

The renderer is a mapping in and a string out, which is criterion 1, and that is
exactly what makes this file possible: every rule ticket 42 states about the
bytes -- what refuses, what a narrative may say, that equal sources render equal
documents -- is a property of one function and is asked of it here. What the SQL
side promises about the bundles themselves is asked in `test_database`.

The fixtures below are the shapes `report_source_bundle` and
`chain_source_bundle` return, written out rather than fetched. A fixture that
drifts from the function it stands for is caught by the round trip in
`test_database`, which renders a bundle the database actually built.
"""

import copy
import json
import unittest
from pathlib import Path

from redkraken import reporting
from redkraken.outcome import INVALID_CONFIGURATION, Ledger
from tests.fixtures import scratch


def finding_bundle(**changes: object) -> dict:
    """One validated Finding as `report_source_bundle` projects it."""
    bundle = {
        "kind": "finding",
        "finding_label": "F-0007",
        "template": "platform.long_form",
        "digest": "b" * 64,
        "blocks": [
            {"id": "provenance_header", "name": "Provenance"},
            {"id": "scope_block", "name": "Scope"},
            {"id": "impact_sentence", "name": "Impact"},
            {"id": "affected_assets", "name": "Affected assets"},
            {"id": "attack_chain", "name": "Attack chain"},
            {"id": "poc_payload", "name": "Proof of concept"},
            {"id": "repro_steps", "name": "Steps to reproduce"},
            {"id": "controls", "name": "Baseline, variant and controls"},
            {"id": "evidence_manifest", "name": "Evidence"},
            {"id": "severity_block", "name": "Severity"},
            {"id": "limitations", "name": "Limitations"},
            {"id": "remediation", "name": "Remediation"},
        ],
        "class": {
            "id": "idor",
            "name": "Insecure direct object reference",
            "cwe": "CWE-639",
            "short_name": "IDOR",
            "remediation": "Authorise the object against the session rather than the request.",
        },
        "subject": {
            "dedup_key": "endpoint:app.example.com:GET:/api/orders/{id}",
            "type": "endpoint",
            "method": "GET",
            "path": "/api/orders/{id}",
            "base_url": "https://app.example.com",
        },
        "scope": {
            "program": "acme-web",
            "version": 4,
            "policy_sha256": "c" * 64,
            "subject_class": "in_scope",
            "subject_in_scope": True,
        },
        "provenance": {"lane": "agent", "at": "11:04:19"},
        "effects": [
            {"id": "read_other_user_data", "phrase": "read another user's data"},
            {"id": "enumerate_identifiers", "phrase": "enumerate identifiers"},
        ],
        "demonstrations": [
            {
                "class": "read_other_data",
                "description": "read data belonging to another account, tenant or user",
                "after_state": "R-0002",
                "receipts": 3,
                "cleanup_receipts": 1,
            }
        ],
        "technology": "Express",
        "chain": [
            {
                "ordinal": 1,
                "label": "Injection point",
                "template": "The `{param}` field on `{method} {path}` addresses the object.",
                "params": {"param": "id", "method": "GET", "path": "/api/orders/{id}"},
                "citations": ["R-0001", "O-0002"],
            }
        ],
        "spec_sha256": "d" * 64,
        "spec": {
            "preconditions": [
                {"kind": "identity", "detail": "a member session is provisioned"}
            ],
            "setup": [{"method": "POST", "url": "https://app.example.com/api/orders"}],
            "actions": [
                {
                    "ordinal": 1,
                    "role": "baseline",
                    "kind": "request",
                    "method": "GET",
                    "url": "https://app.example.com/api/orders/1001",
                },
                {
                    "ordinal": 2,
                    "role": "variant",
                    "kind": "request",
                    "method": "GET",
                    "url": "https://app.example.com/api/orders/1002",
                },
                {
                    "ordinal": 3,
                    "role": "control",
                    "kind": "request",
                    "method": "GET",
                    "url": "https://app.example.com/api/orders/9999",
                },
            ],
            "assertions": [
                {"id": "a1", "kind": "status_equals", "action": 2, "status": 200},
                {"id": "a2", "kind": "body_differs", "action": 2, "against": 1},
            ],
            "cleanup": [{"method": "DELETE", "url": "https://app.example.com/api/orders/1003"}],
        },
        "run": {
            "outcome": "holds",
            "lane": "agent",
            "cleanup": "done",
            "assertions": [{"id": "a1", "held": True}, {"id": "a2", "held": True}],
        },
        "evidence": [
            {
                "receipt": "R-0001",
                "method": "GET",
                "path": "/api/orders/1002",
                "status": 200,
                "request_sha": "e" * 64,
                "response_sha": "f" * 64,
                "visibility": "quotable",
            }
        ],
        "severity": {
            "vector": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N",
            "band": "high",
            "score": 6.5,
            "origin": "computed by the runtime from witnessed effects; not adjudicated",
        },
        "limitations": [
            {"code": "single_observation", "detail": "the validating Test has held once, on agent"}
        ],
        "blockers": [],
    }
    bundle.update(changes)
    return bundle


def chain_bundle(**changes: object) -> dict:
    """One sound kill chain as `chain_source_bundle` projects it."""
    bundle = {
        "kind": "chain",
        "chain": "C-0002",
        "template": "platform.chain_long_form",
        "digest": "a" * 64,
        "blocks": [
            {"id": "chain_header", "name": "Chain"},
            {"id": "scope_block", "name": "Scope"},
            {"id": "chain_composition", "name": "How this chain was established"},
            {"id": "chain_transitions", "name": "Transitions"},
            {"id": "chain_evidence", "name": "Evidence"},
            {"id": "chain_severity", "name": "Severity"},
            {"id": "limitations", "name": "Limitations"},
        ],
        "sound": True,
        "unsound": None,
        "entry": ["session:member"],
        "source_sha256": "9" * 64,
        "execution": "composed",
        "scope": {"program": "acme-web", "version": 4, "policy_sha256": "c" * 64},
        "steps": [
            {
                "stamp": "P-0001",
                "depth": 1,
                "member": "F-0007",
                "class": "idor",
                "subject": "E-0003",
                "identity": "member",
                "transition": "read",
                "provides": "data:orders",
                "requires": ["session:member"],
                "conditions": {"authenticated": True},
            },
            {
                "stamp": "P-0002",
                "depth": 2,
                "member": "F-0009",
                "class": "auth_bypass",
                "subject": "E-0004",
                "identity": "member",
                "transition": "escalate",
                "provides": "session:admin",
                "requires": ["data:orders"],
                "conditions": {},
            },
        ],
        "edges": [{"from": "P-0001", "to": "P-0002", "capability": "data:orders"}],
        "evidence": [
            {
                "stamp": "P-0001",
                "receipt": "R-0001",
                "method": "GET",
                "path": "/api/orders/1002",
                "status": 200,
                "spec_sha256": "d" * 64,
            }
        ],
        "severity": {
            "band": "high",
            "basis": "demonstrated_end_impact",
            "graded": True,
            "ends": [
                {
                    "stamp": "P-0002",
                    "member": "F-0009",
                    "band": "high",
                    "basis": "demonstrated",
                    "vector": "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
                    "score": 8.1,
                }
            ],
            "carried": [{"stamp": "P-0001", "member": "F-0007", "band": "medium"}],
        },
        "limitations": [],
    }
    bundle.update(changes)
    return bundle


def headings(document: str) -> list[str]:
    return [line[3:] for line in document.splitlines() if line.startswith("## ")]


class PurityTest(unittest.TestCase):
    """Criterion 1, which is a property of the signature and of nothing else."""

    def test_the_same_bundle_renders_the_same_bytes_every_time(self):
        bundle = finding_bundle()

        self.assertEqual(reporting.render(bundle), reporting.render(finding_bundle()))

    def test_rendering_leaves_the_bundle_exactly_as_it_arrived(self):
        # A renderer that sorted a list in place would make the second render of
        # one bundle a render of a different bundle, and the digest filed beside
        # the bytes would be the digest of neither.
        bundle = finding_bundle()
        before = copy.deepcopy(bundle)

        reporting.render(bundle)

        self.assertEqual(before, bundle)

    def test_the_key_order_of_the_bundle_does_not_reach_the_bytes(self):
        # `json.loads` preserves the order the database wrote, and two servers
        # are free to build one object's keys in two orders.
        forward = finding_bundle()
        reversed_ = dict(reversed(list(forward.items())))

        self.assertEqual(reporting.render(forward), reporting.render(reversed_))

    def test_a_bundle_that_is_neither_subject_is_refused_rather_than_guessed(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(finding_bundle(kind="observation"))

        self.assertEqual("bundle", refusal.exception.source)


class GateTest(unittest.TestCase):
    """Criterion 2: what may become a document at all."""

    def test_a_hard_blocker_refuses_and_every_reason_is_carried(self):
        blocked = finding_bundle(
            blockers=[
                {"severity": "hard", "code": "no_effect", "detail": "nothing to say"},
                {"severity": "hard", "code": "cvss_stale", "detail": "stored null"},
            ]
        )

        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(blocked)

        self.assertEqual("report_blockers", refusal.exception.source)
        self.assertEqual(
            ("no_effect: nothing to say", "cvss_stale: stored null"), refusal.exception.reasons
        )

    def test_a_soft_blocker_renders_and_arrives_as_a_limitation(self):
        # 038's `severity_scope_moved` is the case: worth telling a triager,
        # not a reason to withhold the report.
        soft = finding_bundle(
            blockers=[
                {"severity": "soft", "code": "severity_scope_moved", "detail": "stated at 3"}
            ],
            limitations=[
                {"code": "soft_blocker", "detail": "severity_scope_moved: stated at 3"}
            ],
        )

        document = reporting.render(soft)

        self.assertIn("- soft_blocker: severity_scope_moved: stated at 3", document)

    def test_an_unsound_chain_refuses_with_the_reason_040_gave(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(chain_bundle(sound=False, unsound="member F-0009 is a duplicate"))

        self.assertEqual("chains", refusal.exception.source)
        self.assertEqual(("member F-0009 is a duplicate",), refusal.exception.reasons)

    def test_a_chain_bundle_with_no_verdict_at_all_is_still_refused(self):
        # `chain_source_bundle` answers a short object for a chain of another
        # Program, and "no verdict" must not read as "no objection".
        with self.assertRaises(reporting.Refused):
            reporting.render(
                {"kind": "chain", "chain": None, "template": "platform.chain_long_form"}
            )

    def test_a_finding_bundle_stating_no_blocker_list_is_refused_like_the_chain(self):
        # The same asymmetry from the other side: `render` is a mapping-in
        # function `evidence` calls too, so a bundle that never asked 034 is a
        # bundle that reaches here, and an absent list is not an empty one.
        bundle = finding_bundle()
        del bundle["blockers"]

        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(bundle)

        self.assertEqual("report_blockers", refusal.exception.source)
        self.assertEqual(("the bundle states no blocker list",), refusal.exception.reasons)


class FormTest(unittest.TestCase):
    """Criterion 3: the sections, and a form this renderer cannot honour."""

    def test_the_document_carries_the_form_s_headings_in_the_form_s_order(self):
        bundle = finding_bundle()

        document = reporting.render(bundle)

        self.assertEqual([block["name"] for block in bundle["blocks"]], headings(document))
        self.assertTrue(document.startswith("# F-0007\n"))

    def test_every_section_the_long_form_states_renders_something(self):
        # A heading over nothing is a report that looks complete and answers
        # none of what the section was put in the form to answer.
        document = reporting.render(finding_bundle())
        sections = document.split("## ")[1:]

        for section in sections:
            body = section.split("\n", 1)[1].strip()
            self.assertNotEqual("", body, section.splitlines()[0])

    def test_criterion_3_s_eight_subjects_are_all_in_the_finding_document(self):
        document = reporting.render(finding_bundle())

        self.assertIn("- Program: acme-web", document)                       # scope
        self.assertIn("- Subject: endpoint:app.example.com", document)       # affected assets
        self.assertIn("1. [baseline] GET https://app.example.com", document)  # reproduction
        self.assertIn("Control:", document)                                  # controls
        self.assertIn("- read_other_data: read data belonging", document)    # demonstrated impact
        self.assertIn("- single_observation:", document)                     # limitations
        self.assertIn("request sha256 " + "e" * 64, document)                # evidence identifiers
        self.assertIn("Authorise the object against the session", document)  # remediation

    def test_the_assertion_verdicts_are_beside_the_actions_that_produced_them(self):
        document = reporting.render(finding_bundle())

        self.assertIn("The validating run holds on the agent lane, and its cleanup is done.",
                      document)
        self.assertIn("- a1: held", document)

    def test_an_inconclusive_assertion_is_not_reported_as_a_failure(self):
        # 035 records a null verdict for an assertion the runtime could not
        # evaluate, and `not held` would be a claim nobody made.
        bundle = finding_bundle()
        bundle["run"] = dict(bundle["run"], assertions=[{"id": "a1", "held": None}])

        self.assertIn("- a1: could not be evaluated", reporting.render(bundle))

    def test_a_form_that_states_no_block_is_refused(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(finding_bundle(blocks=[]))

        self.assertEqual("report_template_blocks", refusal.exception.source)

    def test_a_block_this_version_cannot_render_is_refused_by_name(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(blocks=[{"id": "executive_summary", "name": "Summary"}])
            )

        self.assertEqual("report_blocks", refusal.exception.source)
        self.assertIn("executive_summary", refusal.exception.reasons[0])
        self.assertIn(reporting.VERSION, refusal.exception.reasons[0])

    def test_a_finding_with_no_composition_still_renders_a_sentence_in_each_section(self):
        # The composition is a hard blocker's business, not this function's, so
        # a bundle that reaches here without one says so rather than printing a
        # blank section.
        bare = finding_bundle(
            effects=[], demonstrations=[], chain=[], evidence=[], limitations=[]
        )

        document = reporting.render(bare)

        self.assertIn("No effect is recorded against this Finding.", document)
        self.assertIn("No mechanism is recorded against this Finding.", document)
        self.assertIn("No exchange is cited by this Finding.", document)
        self.assertIn("Nothing further is known to limit what is stated above.", document)


class ImpactTest(unittest.TestCase):
    """The two words 038 separates, kept separate in the section that prints them."""

    def test_a_witnessed_effect_and_a_demonstrated_impact_read_as_two_things(self):
        document = reporting.render(finding_bundle())

        self.assertIn("Witnessed effects:", document)
        self.assertIn("- read another user's data", document)
        self.assertIn("Demonstrated impact:", document)
        self.assertIn(
            "- read_other_data: read data belonging to another account, tenant or "
            "user (after-state R-0002, 3 exchange(s), 1 undone)",
            document,
        )

    def test_effects_with_no_impact_run_behind_them_say_so_in_the_same_section(self):
        # Otherwise the section reads as though the witnessed list had the
        # after-state Receipt and the performed cleanup that only 038 produces.
        document = reporting.render(finding_bundle(demonstrations=[]))

        self.assertIn("Witnessed effects:", document)
        self.assertIn("No impact run has demonstrated one of these effects.", document)
        self.assertNotIn("Demonstrated impact:", document)


class ChainFormTest(unittest.TestCase):
    """Criterion 4, which is one word the report has to get right."""

    def test_a_composed_chain_says_it_was_assembled_from_separate_demonstrations(self):
        document = reporting.render(chain_bundle(execution="composed"))

        self.assertIn("No single run has yet walked it end to end", " ".join(document.split()))
        self.assertNotIn("One run walked this chain end to end", document)

    def test_an_executed_chain_says_one_run_walked_it(self):
        document = reporting.render(chain_bundle(execution="executed"))

        self.assertIn("One run walked this chain end to end", document)

    def test_the_transitions_carry_the_capability_each_one_needs_and_leaves(self):
        document = reporting.render(chain_bundle())

        self.assertIn("   requires session:member", document)
        self.assertIn("   provides data:orders by read", document)
        self.assertIn("- P-0001 -> P-0002 (data:orders)", document)

    def test_the_band_is_the_end_impact_and_the_route_is_not_added_to_it(self):
        document = reporting.render(chain_bundle())

        self.assertIn("- Band: high, from the demonstrated end impact", document)
        self.assertIn(
            "- Demonstrated at P-0002 (F-0009): high, CVSS 8.1 "
            "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
            document,
        )
        self.assertIn("P-0001 (F-0007) medium", " ".join(document.split()))
        self.assertIn("none of them is added to the band above", " ".join(document.split()))

    def test_a_one_step_chain_says_there_is_nothing_beside_the_end_to_add(self):
        document = reporting.render(
            chain_bundle(
                severity={
                    "band": "critical",
                    "basis": "demonstrated_end_impact",
                    "graded": True,
                    "ends": [
                        {
                            "stamp": "P-0001",
                            "member": "F-0007",
                            "band": "critical",
                            "basis": "demonstrated",
                            "vector": None,
                            "score": None,
                        }
                    ],
                    "carried": [],
                }
            )
        )

        self.assertIn("- Band: critical, from the demonstrated end impact", document)
        self.assertIn("- Demonstrated at P-0001 (F-0007): critical\n", document)
        self.assertIn("nothing beside it to add", " ".join(document.split()))

    def test_a_chain_ending_at_an_ungraded_finding_says_so_instead_of_printing_info(self):
        # `info` is where a Finding sits before anybody grades it, so a chain
        # that printed it as its band would understate a composition that
        # reached further than its last member has been assessed.
        document = reporting.render(
            chain_bundle(
                severity={
                    "band": "info",
                    "basis": "demonstrated_end_impact",
                    "graded": False,
                    "ends": [
                        {
                            "stamp": "P-0002",
                            "member": "F-0009",
                            "band": "info",
                            "basis": "undetermined",
                            "vector": None,
                            "score": None,
                        }
                    ],
                    "carried": [{"stamp": "P-0001", "member": "F-0007", "band": "high"}],
                }
            )
        )

        self.assertIn("- Band: not stated. This chain ends at P-0002 (F-0009)", document)
        self.assertNotIn("- Band: info", document)
        self.assertIn("P-0001 (F-0007) high", " ".join(document.split()))

    def test_a_chain_that_states_no_edge_says_so_rather_than_printing_a_heading(self):
        document = reporting.render(chain_bundle(edges=[]))

        self.assertIn("The chain states no capability edge between these steps.", document)


class MechanismTest(unittest.TestCase):
    """The one place a curated sentence meets a value taken off a target."""

    def test_a_slot_is_filled_from_the_step_s_parameters(self):
        document = reporting.render(finding_bundle())

        self.assertIn(
            "1. The `id` field on `GET /api/orders/{id}` addresses the object. [R-0001, O-0002]",
            document,
        )

    def test_a_brace_in_a_parameter_value_is_not_read_as_a_second_slot(self):
        # A parameter value is a token from a target's own response, so it can
        # hold anything -- and `str.format` would try to resolve `{admin}`.
        self.assertEqual(
            "took {admin} whole",
            reporting._filled("took {value} whole", {"value": "{admin}"}),
        )

    def test_a_slot_with_no_parameter_is_left_visible_rather_than_emptied(self):
        # A sentence quietly missing a word reads as a complete claim about
        # something else; the slot left standing reads as the mistake it is.
        self.assertEqual("the {param} field", reporting._filled("the {param} field", {}))


class NarrativeTest(unittest.TestCase):
    """Criterion 6: off by default, and adding no fact when it is on."""

    def test_no_narrative_is_the_default_and_leaves_no_mark(self):
        self.assertNotIn(reporting.NARRATIVE_MARK, reporting.render(finding_bundle()))

    def test_a_sentence_that_only_rephrases_the_projection_is_kept_and_marked(self):
        document = reporting.render(
            finding_bundle(),
            narrative={
                "impact_sentence": "A member reading /api/orders/1002 receives 200 "
                "and another account's order."
            },
        )

        self.assertIn(reporting.NARRATIVE_MARK, document)
        self.assertIn("another account's order.", document)

    def test_a_sentence_stating_a_fact_the_projection_does_not_carry_is_refused(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(),
                narrative={"impact_sentence": "It also exposes /admin/users."},
            )

        self.assertEqual("argument:--narrative", refusal.exception.source)
        self.assertIn("/admin/users", refusal.exception.reasons[0])

    def test_a_token_that_only_hides_inside_a_longer_one_is_still_a_new_fact(self):
        # The response hash starts `ffff`; a sentence claiming port 4444 must
        # not pass because those digits appear somewhere in the projection.
        with self.assertRaises(reporting.Refused):
            reporting.render(
                finding_bundle(), narrative={"impact_sentence": "Reachable on 4444."}
            )

    def test_a_parameter_spelled_in_letters_is_a_fact_like_any_other(self):
        # Story 201 names the parameter beside the host and the path, and a
        # parameter name carries no slash, no digit and no dot -- so a predicate
        # reading punctuation alone lets a sentence invent one.
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(),
                narrative={"impact_sentence": "The handler also trusts redirect_uri."},
            )

        self.assertIn("redirect_uri", refusal.exception.reasons[0])

    def test_a_header_the_projection_never_saw_cannot_be_named(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(),
                narrative={"remediation": "Stop honouring X-Forwarded-Host here."},
            )

        self.assertIn("X-Forwarded-Host", refusal.exception.reasons[0])

    def test_a_bare_capitalised_acronym_is_a_claim_and_not_a_word(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(), narrative={"impact_sentence": "The IMDS answers too."}
            )

        self.assertIn("IMDS", refusal.exception.reasons[0])

    def test_the_identifiers_the_projection_carries_may_still_be_said(self):
        # The bound is the projection and not a ban on the shape: this bundle
        # carries `IDOR` as the class short name and `read_other_user_data` as
        # an effect, so a sentence using them introduces nothing.
        document = reporting.render(
            finding_bundle(),
            narrative={
                "impact_sentence": "This IDOR is read_other_user_data and nothing more."
            },
        )

        self.assertIn("This IDOR is read_other_user_data and nothing more.", document)

    def test_ordinary_words_are_not_asked_to_be_facts(self):
        # The bare lowercase word is the one shape this cannot decide, so it is
        # left as prose deliberately: nothing here tells `handler` the noun from
        # `handler` the parameter without a vocabulary of English.
        document = reporting.render(
            finding_bundle(),
            narrative={"remediation": "The fix is cheap and belongs in the handler."},
        )

        self.assertIn("The fix is cheap and belongs in the handler.", document)

    def test_a_block_that_records_rather_than_argues_takes_no_narrative(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(finding_bundle(), narrative={"evidence_manifest": "Note."})

        self.assertIn("takes no narrative", refusal.exception.reasons[0])

    def test_a_narrative_for_a_section_this_form_does_not_have_is_refused(self):
        # Otherwise the prose is silently dropped and the operator believes the
        # document says something it does not.
        short = finding_bundle(blocks=[{"id": "impact_sentence", "name": "Impact"}])

        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(short, narrative={"remediation": "Patch it."})

        self.assertIn("is not a section of", refusal.exception.reasons[0])

    def test_every_refusable_sentence_is_reported_and_not_only_the_first(self):
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                finding_bundle(),
                narrative={
                    "impact_sentence": "Also /admin/users.",
                    "evidence_manifest": "Note.",
                },
            )

        self.assertEqual(2, len(refusal.exception.reasons))

    def test_a_narrative_may_be_offered_to_a_chain_report_too(self):
        document = reporting.render(
            chain_bundle(limitations=[{"code": "single_observation", "detail": "held once"}]),
            narrative={"limitations": "Each hop was shown on its own."},
        )

        self.assertIn("Each hop was shown on its own.", document)

    def test_the_one_word_criterion_4_turns_on_takes_no_narrative(self):
        # `_claims` asks about identifiers and digits, and "composed" and
        # "executed" are neither. A paragraph under this block could state the
        # opposite of the sentence above it and introduce no token at all.
        with self.assertRaises(reporting.Refused) as refusal:
            reporting.render(
                chain_bundle(),
                narrative={"chain_composition": "One run walked the whole thing."},
            )

        self.assertIn("takes no narrative", refusal.exception.reasons[0])


class NarrativeFileTest(unittest.TestCase):
    """What `--narrative` accepts before the sentences are judged at all."""

    def read(self, text: str):
        path = scratch() / "narrative.json"
        path.write_text(text, encoding="utf-8")
        ledger = Ledger()
        return ledger, reporting._read_narrative(ledger, path)

    def test_an_object_of_strings_is_taken(self):
        ledger, document = self.read(json.dumps({"remediation": "Patch it."}))

        self.assertEqual({"remediation": "Patch it."}, document)
        self.assertEqual([], ledger.violations)

    def test_a_file_that_is_not_json_is_refused_as_configuration(self):
        ledger, document = self.read("not json")

        self.assertIsNone(document)
        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in ledger.violations])

    def test_a_document_whose_values_are_not_sentences_is_refused(self):
        ledger, document = self.read(json.dumps({"remediation": ["Patch it."]}))

        self.assertIsNone(document)
        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in ledger.violations])

    def test_a_file_that_is_not_there_is_refused_by_name(self):
        ledger = Ledger()

        self.assertIsNone(reporting._read_narrative(ledger, scratch() / "absent.json"))
        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in ledger.violations])


class RecordArgumentTest(unittest.TestCase):
    """The one thing `run` decides before it opens anything."""

    def test_every_fact_this_command_declares_is_on_the_report_it_returns(self):
        # `FACTS` is what an operator and `rk2 db check` are told this command
        # answers. A key declared and never sent is a promise the report does
        # not keep, and the report is the only thing either of them reads.
        outcome = reporting.run(
            None,
            Path("/nonexistent/rk.toml"),
            subject="chain",
            label="C-0002",
            template="platform.chain_long_form",
            record=True,
        )

        self.assertEqual(set(reporting.FACTS), set(outcome.facts))

    def test_recording_a_chain_is_refused_before_a_connection_is_asked_for(self):
        # The settings and the configuration path are both unusable on purpose:
        # if this refusal moved below either of them, this test would fail with
        # the wrong error instead of passing.
        outcome = reporting.run(
            None,
            Path("/nonexistent/rk.toml"),
            subject="chain",
            label="C-0002",
            template="platform.chain_long_form",
            record=True,
        )

        self.assertFalse(outcome.ok)
        self.assertEqual([INVALID_CONFIGURATION], [item.code for item in outcome.violations])
        self.assertEqual("argument:--record", outcome.violations[0].source)


if __name__ == "__main__":
    unittest.main()
