"""What the Playbook compiler accepts, what it refuses, and what it hands a model.

Three halves, which is one more than `test_skill` has and for a reason: a Skill
is compiled and granted, while a Playbook is compiled, *projected* and then
selected. So the middle section here is about the projection -- what is in it,
what is provably not, and which edits move which digest.

Corpora are written on disk rather than fixtured, for `test_skill`'s reason:
every negative below is a document that must not exist in
`src/redkraken/playbooks/`, and the only way to have both the rule and its
violation is to write the violation somewhere the corpus is not.
"""

import datetime as dt
import re
import unittest
from pathlib import Path

from redkraken import playbook, roster, skill
from redkraken.document import FENCE
from tests.fixtures import frontmatter, scratch
from tools import check_dispositions, check_intake


#: The smallest Playbook that compiles. Every negative below is this document
#: with one thing changed, so the thing that changed is the thing under test.
FRONTMATTER = {
    "description": "Ask whether the object named in a request is checked against the caller.",
    "bb:category": "authorization",
    "bb:outputs": ["authorization.object_ownership"],
    "bb:triggers_all": ["multiple_test_identities", "object_identifier"],
    "bb:skills": ["compare-responses", "use-identity"],
    "bb:risk": "constrained",
    "bb:effects": "read_only",
    "bb:baseline": "stable_session",
    "bb:status": "draft",
    "bb:stale_after": "2099-01-01",
    "bb:provenance": "Written for the suite; no upstream card.",
    "bb:evidence": [
        {"to_status": "supported", "role": "variant",
         "kind": "response_differential", "polarity": "supports", "min_count": 1},
    ],
}

BODY = """
# Ask who the object belongs to

## 1. Name the object

Complete this step holding the endpoint and the parameter that names the object.
"""

#: A string that appears only in reference material. Criterion 2 is the claim
#: that it cannot reach a model, and the way to test a claim about absence is to
#: make the thing being looked for unmistakable.
MARKER = "MAINTAINER-ONLY-e7d1c0"

REFERENCE = f"""\
# Why this Playbook insists on a control

{MARKER}

A one-Identity test has three explanations and picks one.
"""


def document(fields: dict, body: str = BODY) -> str:
    """One `playbook.md`, from a mapping, the way the parser reads one back."""
    return frontmatter(fields) + body


def corpus(references: dict[str, str] | None = None, **playbooks: str | None) -> Path:
    """A corpus root holding one directory per named Playbook.

    A `None` document makes the directory and leaves out the `playbook.md`,
    which is the one negative that cannot be expressed as a document. Reference
    files are written into every directory, because every negative that needs
    them needs them on the one Playbook under test.
    """
    root = scratch() / "playbooks"
    root.mkdir()
    for name, text in playbooks.items():
        directory = root / name.replace("_", "-")
        directory.mkdir()
        if text is not None:
            (directory / playbook.DOCUMENT).write_text(text, encoding="utf-8")
        if references:
            (directory / playbook.REFERENCE_DIR).mkdir()
            for file_name, content in references.items():
                (directory / playbook.REFERENCE_DIR / file_name).write_text(
                    content, encoding="utf-8"
                )
    return root


def one(fields: dict | None = None, body: str = BODY, **changes: object) -> Path:
    """A corpus holding exactly one Playbook, well-formed unless a caller says so."""
    return corpus(object_ownership=document((fields or FRONTMATTER) | changes, body))


def cited(fields: dict | None = None, body: str = BODY,
          reference: str = REFERENCE, **changes: object) -> Path:
    """The same, with one maintainer reference declared and present."""
    declared = (fields or FRONTMATTER) | {"bb:references": ["why.md"]} | changes
    return corpus({"why.md": reference}, object_ownership=document(declared, body))


def compiled(root: Path) -> playbook.Playbook:
    return playbook.compile_corpus(root)["object-ownership"]


class Refusals(unittest.TestCase):
    """Criterion 5: every shape of malformed Playbook, by the code it refuses with.

    The assertions are on `PlaybookError.code` rather than on the sentence, for
    the reason `document.DocumentError` gives: the sentence is for a person
    reading a refusal and should be free to improve.
    """

    def refuses(self, code: str, root: Path) -> playbook.PlaybookError:
        with self.assertRaises(playbook.PlaybookError) as caught:
            playbook.compile_corpus(root)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    # -- the document -------------------------------------------------------

    def test_a_playbook_without_a_document_is_not_a_playbook(self):
        self.refuses("file_missing", corpus(object_ownership=None))

    def test_frontmatter_must_open_and_close(self):
        self.refuses("frontmatter_malformed", corpus(object_ownership="# no fence\n"))
        unclosed = FENCE + "\ndescription: a thing\n" + BODY
        self.refuses("frontmatter_malformed", corpus(object_ownership=unclosed))

    def test_a_document_the_two_parsers_would_read_differently_is_refused(self):
        # The same two rules as the Skill and fixture corpora, from the same
        # place: `document.text` holds them once so the three corpora cannot
        # start meaning different things by the same bytes.
        self.refuses(
            "frontmatter_malformed", corpus(object_ownership=document(FRONTMATTER) + "\r\n")
        )
        raw = corpus(object_ownership=document(FRONTMATTER))
        (raw / "object-ownership" / playbook.DOCUMENT).write_bytes(
            b"---\ndescription: \xff\n---\nx\n"
        )
        self.refuses("frontmatter_malformed", raw)

    def test_a_playbook_with_no_body_teaches_nothing(self):
        self.refuses("body_missing", one(body="\n"))

    def test_a_key_stated_twice_is_refused_rather_than_resolved(self):
        doubled = document(FRONTMATTER).replace(
            "bb:risk: constrained", "bb:risk: constrained\nbb:risk: autonomous", 1
        )
        self.refuses("duplicate_key", corpus(object_ownership=doubled))

    def test_a_key_nothing_reads_is_refused(self):
        self.refuses("key_unknown", one(**{"bb:severity": "high"}))

    def test_every_required_key_is_required(self):
        for key in playbook.REQUIRED_KEYS:
            with self.subTest(key=key):
                fields = {k: v for k, v in FRONTMATTER.items() if k != key}
                self.refuses("key_missing", one(fields))

    def test_a_second_identity_beside_the_directory_name_is_refused(self):
        for key in playbook.FORBIDDEN_KEYS:
            with self.subTest(key=key):
                self.refuses("key_forbidden", one(**{key: "something"}))

    def test_a_file_nothing_declares_is_refused(self):
        root = one()
        (root / "object-ownership" / "notes.md").write_text("stray", encoding="utf-8")
        self.refuses("stray_file", root)

    def test_a_reference_that_is_declared_and_absent_is_refused(self):
        self.refuses("file_missing", one(**{"bb:references": ["missing.md"]}))

    def test_a_reference_that_is_present_and_undeclared_is_refused(self):
        root = corpus({"why.md": REFERENCE}, object_ownership=document(FRONTMATTER))
        self.refuses("stray_file", root)

    def test_a_reference_that_is_a_path_is_refused_before_the_filesystem(self):
        self.refuses("path_escape", one(**{"bb:references": ["../../etc/passwd"]}))

    def test_a_reference_that_is_a_symbolic_link_out_of_the_tree_is_refused(self):
        root = cited()
        link = root / "object-ownership" / playbook.REFERENCE_DIR / "why.md"
        target = scratch() / "elsewhere.md"
        target.write_text(REFERENCE, encoding="utf-8")
        link.unlink()
        link.symlink_to(target)
        self.refuses("path_escape", root)

    # -- what the values mean -----------------------------------------------

    def test_a_playbook_with_no_required_trigger_matches_every_subject(self):
        self.refuses("value_malformed", one(**{"bb:triggers_all": []}))

    def test_a_fact_that_is_required_and_also_optional_is_refused(self):
        self.refuses("duplicate_entry", one(**{"bb:triggers_any": ["object_identifier"]}))

    def test_an_output_outside_the_declared_category_is_refused(self):
        self.refuses("category_mismatch", one(**{"bb:outputs": ["injection.sql"]}))

    def test_a_list_that_is_not_in_sorted_order_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:skills": ["use-identity", "compare-responses"]}))

    def test_a_name_that_is_not_a_name_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:outputs": ["Authorization.Object"]}))
        self.refuses("value_malformed", one(**{"bb:category": "Authorization"}))
        self.refuses("value_malformed", one(**{"bb:triggers_all": ["Object Identifier"]}))

    def test_a_closed_vocabulary_is_closed(self):
        self.refuses("value_malformed", one(**{"bb:risk": "reckless"}))
        self.refuses("value_malformed", one(**{"bb:effects": "mutates_everything"}))
        self.refuses("value_malformed", one(**{"bb:baseline": "quiet"}))
        self.refuses("value_malformed", one(**{"bb:status": "provisional"}))

    def test_a_review_date_that_is_not_a_date_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:stale_after": "soon"}))

    def test_a_description_that_is_not_one_line_is_refused(self):
        self.refuses("value_unbounded", one(description="x" * (playbook.DESCRIPTION_LIMIT + 1)))

    def test_risk_may_not_be_lower_than_the_effects_admit(self):
        # The mirror of `playbooks_risk_matches_effects`. Compiled here as well
        # as constrained there, because a document that reached the INSERT would
        # fail with a message about a constraint instead of about the line.
        self.refuses("risk_understates_effects",
                     one(**{"bb:effects": "mutates_session", "bb:risk": "autonomous"}))
        self.refuses("risk_understates_effects",
                     one(**{"bb:effects": "mutates_account", "bb:risk": "constrained"}))

    # -- what the evidence has to be ----------------------------------------

    def test_evidence_that_states_nothing_for_supported_cannot_make_its_claim(self):
        refuted = [{"to_status": "refuted", "role": "variant",
                    "kind": "response_invariant", "polarity": "refutes", "min_count": 1}]
        self.refuses("evidence_missing", one(**{"bb:evidence": refuted}))

    def test_two_evidence_rows_on_one_key_are_refused(self):
        twice = [dict(FRONTMATTER["bb:evidence"][0]) for _ in range(2)]
        twice[1]["min_count"] = 2
        self.refuses("duplicate_entry", one(**{"bb:evidence": twice}))

    def test_a_minimum_of_zero_is_not_a_requirement(self):
        # `playbook_evidence` is a conjunction with `transition_rules`, so a zero
        # cannot lower the base minimum and would in fact do nothing at all.
        zero = [dict(FRONTMATTER["bb:evidence"][0]) | {"min_count": 0}]
        self.refuses("value_malformed", one(**{"bb:evidence": zero}))

    def test_an_evidence_row_names_a_role_and_a_transition_that_exist(self):
        for change in ({"role": "bystander"}, {"to_status": "proved"},
                       {"polarity": "hints"}, {"kind": "Response Differential"}):
            with self.subTest(**change):
                row = [dict(FRONTMATTER["bb:evidence"][0]) | change]
                self.refuses("value_malformed", one(**{"bb:evidence": row}))

    # -- the corpus ---------------------------------------------------------

    def test_a_corpus_that_is_not_there_is_not_an_empty_one(self):
        self.refuses("corpus_missing", scratch() / "absent")

    def test_an_empty_corpus_is_refused(self):
        root = scratch() / "playbooks"
        root.mkdir()
        self.refuses("corpus_missing", root)

    def test_a_playbook_named_the_way_a_path_is_not_is_refused(self):
        root = scratch() / "playbooks"
        root.mkdir()
        (root / "Object Ownership").mkdir()
        self.refuses("name_invalid", root)


class Projection(unittest.TestCase):
    """Criterion 2, and the two digests that make criterion 4 provable.

    The claim is that maintainer material is *structurally* absent from what a
    model receives -- not filtered out, but with nowhere to go. So these test
    both directions: the text does not appear, and the shape has no field it
    could appear in.
    """

    def test_reference_material_is_not_in_what_the_model_receives(self):
        one_playbook = compiled(cited())
        # Linked for a maintainer: the row names the file and hashes the bytes
        # the marker is in, so the two halves of the criterion are about one
        # document rather than about two that happen to share a name.
        self.assertEqual("why.md", one_playbook.references[0].name)
        self.assertEqual(playbook.digest(REFERENCE.encode("utf-8")),
                         one_playbook.references[0].sha256)
        # And absent from everything a model is handed.
        self.assertNotIn(MARKER, one_playbook.projection.canonical())
        self.assertNotIn(MARKER, one_playbook.projection.instructions)

    def test_the_projection_has_nowhere_to_put_maintainer_material(self):
        # The structural half. A filter can be forgotten; a dataclass with no
        # field for the thing cannot carry it whatever anybody forgets.
        fields = set(playbook.Projection.__dataclass_fields__)
        self.assertEqual(set(), fields & {"references", "provenance", "status",
                                          "stale_after", "triggers_all", "triggers_any",
                                          "category", "name"})

    def test_the_projection_carries_everything_the_agent_has_to_act_on(self):
        one_playbook = compiled(cited())
        projection = one_playbook.projection
        self.assertEqual("playbooks/object-ownership/playbook.md", projection.path)
        self.assertEqual(("authorization.object_ownership",), projection.property_classes)
        self.assertEqual(("compare-responses", "use-identity"), projection.skills)
        self.assertEqual(("constrained", "read_only", "stable_session"),
                         (projection.risk, projection.effects, projection.baseline))
        self.assertTrue(projection.evidence)
        self.assertIn("Name the object", projection.instructions)

    def test_the_render_shows_every_field_the_projection_carries(self):
        # `text()` is what the runtime hands a child, and the class docstring's
        # guarantee is about the fields. A render that dropped one would be a
        # second filter -- quieter than the first and never reviewed as one.
        rendered = compiled(cited()).projection.text()
        self.assertNotIn(MARKER, rendered)
        for name in playbook.Projection.__dataclass_fields__:
            with self.subTest(field=name):
                value = getattr(compiled(cited()).projection, name)
                if name == "evidence":
                    for one in value:
                        self.assertIn(one.to_status, rendered)
                        self.assertIn(one.kind, rendered)
                        self.assertIn(one.role, rendered)
                elif isinstance(value, tuple):
                    for one in value:
                        self.assertIn(one, rendered)
                else:
                    self.assertIn(value.strip(), rendered)

    def test_the_render_does_not_move_what_the_projection_is_identified_by(self):
        # A render is a view. If it were part of the canonical form, changing
        # how a Playbook reads to a model would change the digest a selection
        # froze -- and every recorded run would look as though it read
        # different text.
        one_playbook = compiled(cited())
        self.assertNotIn(one_playbook.projection.text(), one_playbook.projection.canonical())

    def test_a_playbook_keeps_no_second_copy_of_what_it_projects(self):
        # The projection is the one place these values live. A field of the same
        # name beside it would be a second copy that a later edit could move
        # without moving the digest the model's text is identified by.
        self.assertEqual(
            set(),
            set(playbook.Playbook.__dataclass_fields__)
            & set(playbook.Projection.__dataclass_fields__),
        )

    def test_editing_a_reference_moves_neither_digest(self):
        before = compiled(cited())
        after = compiled(cited(reference=REFERENCE + "\nOne more paragraph.\n"))
        self.assertEqual(before.sha256, after.sha256)
        self.assertEqual(before.version, after.version)
        self.assertNotEqual(before.references[0].sha256, after.references[0].sha256)

    def test_editing_the_review_date_moves_the_document_and_not_the_projection(self):
        before = compiled(one())
        after = compiled(one(**{"bb:stale_after": "2098-01-01"}))
        self.assertNotEqual(before.sha256, after.sha256)
        self.assertEqual(before.version, after.version)

    def test_editing_the_body_moves_both(self):
        before = compiled(one())
        after = compiled(one(body=BODY + "\n## 2. And then\n\nComplete this step.\n"))
        self.assertNotEqual(before.sha256, after.sha256)
        self.assertNotEqual(before.version, after.version)

    def test_the_document_digest_is_the_document(self):
        root = one()
        source = (root / "object-ownership" / playbook.DOCUMENT).read_bytes()
        self.assertEqual(playbook.digest(source), compiled(root).sha256)

    def test_specificity_is_derived_and_not_declared(self):
        self.assertEqual(2, compiled(one()).specificity)
        self.assertEqual(1, compiled(one(**{"bb:triggers_all": ["object_identifier"]})).specificity)


class Corpus(unittest.TestCase):
    """The Playbook this package actually ships, against what the ticket says."""

    def setUp(self):
        self.corpus = playbook.PLAYBOOKS
        self.one = self.corpus["object-ownership"]

    def test_the_corpus_ships_inside_the_package(self):
        # Not at the repository root: `rk` runs what it was installed with, and
        # a directory beside the repository ships in a checkout and not a wheel.
        self.assertTrue(playbook.CORPUS.is_relative_to(Path(playbook.__file__).parent))
        self.assertTrue((playbook.CORPUS / "object-ownership" / playbook.DOCUMENT).is_file())

    def test_the_shipped_playbook_declares_everything_criterion_one_names(self):
        self.assertEqual("authorization", self.one.category)
        self.assertEqual(("authorization.object_ownership",), self.one.property_classes)
        self.assertEqual(("multiple_test_identities", "object_identifier"), self.one.triggers_all)
        self.assertEqual(("body_parameter", "path_parameter", "query_parameter"),
                         self.one.triggers_any)
        self.assertEqual(("compare-responses", "use-identity"), self.one.skills)
        self.assertEqual(("constrained", "read_only", "stable_session"),
                         (self.one.risk, self.one.effects, self.one.baseline))
        self.assertTrue(self.one.provenance)
        self.assertTrue(self.one.evidence)

    def test_every_playbook_declares_everything_criterion_one_names(self):
        # The same clause as above, over the whole catalogue rather than one
        # Playbook, because 49's ledger rows cite this file as their proof and
        # "the name is in PLAYBOOKS" is not what those rows claim. The values
        # are not written down here -- a second copy of eight Playbooks' metadata
        # is a second thing to edit, and the compiler already refuses a missing
        # key. What is asserted is that nothing is declared empty, that the
        # class it outputs sits under the category it announces, and that both
        # projections carry text.
        for name, one in self.corpus.items():
            with self.subTest(playbook=name):
                self.assertTrue(one.description)
                self.assertTrue(one.property_classes)
                self.assertTrue(one.triggers_all or one.triggers_any)
                self.assertTrue(one.skills)
                self.assertTrue(one.provenance)
                self.assertTrue(one.evidence)
                self.assertTrue(all(row.startswith(f"{one.category}.")
                                    for row in one.property_classes))
                self.assertTrue(one.projection.instructions.strip())
                self.assertTrue(one.projection.canonical().strip())

    def test_every_shipped_playbook_has_a_ledger_record_behind_it(self):
        # Ticket 235. `check_techniques` already refuses a Playbook with no
        # record behind it, and it did refuse this tree -- but it is read by
        # `tests.test_intake`, which is not the module somebody adding a
        # Playbook runs. So a Playbook shipped with no reading behind it, and
        # the corpus gate went red for everyone else. The same rule is asserted
        # here, beside the corpus it is about, where the author of the next
        # Playbook will see it.
        written = {record["playbook"] for record in check_intake.read_records()}
        missing = sorted(set(self.corpus) - written)
        self.assertEqual(
            [], missing,
            f"{', '.join(missing)} ships with no record in"
            f" {check_intake.TECHNIQUES.name}: a Playbook is written from the"
            f" ledger, so the records go in with it",
        )

    def test_every_playbook_requires_a_control_before_it_may_claim_anything(self):
        # The one rule these Playbooks exist for, and the reason it is asserted
        # over the catalogue: a Playbook whose supported evidence is all
        # `variant` is a Playbook that can claim from one reading, which is the
        # v1 failure this corpus replaces. What the control observes differs by
        # class -- a working session, an unchanged answer, a difference the
        # limit did not make -- so the kind is not pinned, only the role.
        for name, one in self.corpus.items():
            with self.subTest(playbook=name):
                supported = {(row.role, row.kind) for row in one.evidence
                             if row.to_status == "supported"}
                self.assertTrue(any(role == "control" for role, _ in supported))
                self.assertTrue(any(role == "variant" for role, _ in supported))

    def test_the_shipped_playbook_names_a_control_a_verb_can_actually_write(self):
        # `object-ownership` pins both kinds, where the catalogue-wide case
        # above pins only the roles. It pinned `credential_effect` on the
        # control until 2026-08-24 -- a refusal under the second Identity is
        # evidence of a boundary only if that session was working, and that kind
        # is the observation which says it was. The reading was right, and what
        # was wrong was the writer rather than the reachability: no *replay*
        # derives that kind, because `close_test_replay` reads the kind off the
        # Test specification. Ticket 166 established that an agent filing the
        # edge with the proposal that mints the claim reaches the same bar, so
        # the narrowing here bought a bar the replay alone can meet, not the
        # only bar that was meetable.
        #
        # So the bar is the strongest one a verb can meet, and the kind is the
        # same on both legs. `close_test_replay` reads the kind off the Test
        # specification, not off the outcome: an action any `status_differs` or
        # `body_differs` assertion names -- as its `action` or as its `against`
        # -- is `response_differential`, and a comparison names both of its
        # legs. So a Playbook whose whole method is a comparison writes that one
        # kind for the control as well. What is lost is that the bar no longer
        # distinguishes "the session worked" from "this leg was compared". The
        # way back to it is an agent filing a `credential_effect` edge with the
        # proposal, which ticket 166 measured as counting at this bar; whether
        # this Playbook's text should ask for that again is a corpus decision
        # and not this test's.
        supported = {(row.role, row.kind) for row in self.one.evidence
                     if row.to_status == "supported"}
        self.assertIn(("control", "response_differential"), supported)
        self.assertIn(("variant", "response_differential"), supported)

    def test_every_playbook_says_what_would_refute_it(self):
        for name, one in self.corpus.items():
            with self.subTest(playbook=name):
                self.assertTrue(any(row.to_status == "refuted" for row in one.evidence))

    def test_every_playbook_is_draft_until_a_fixture_has_graded_it(self):
        # `playbooks_stable_is_promoted` plus 036's promotion guard make
        # `stable` unreachable until the evaluator has run the exact text, and
        # no evaluation has: the door refuses to dial the loopback a fixture
        # listens on, which is ticket 78. Selection admits draft -- only
        # `deprecated` is excluded -- so this is the honest state and not a gap.
        # When one of these promotes, this line is what says which.
        self.assertEqual(
            {name: "draft" for name in self.corpus},
            {name: one.status for name, one in self.corpus.items()},
        )

    def test_no_review_date_has_passed(self):
        # The only version of a review date that gets read is one that fails the
        # suite on the day. When this fires: re-read the body against what the
        # surface looks like now, then move the date or deprecate the Playbook.
        for name, one in self.corpus.items():
            with self.subTest(playbook=name):
                self.assertGreater(
                    one.stale_after, dt.date.today(),
                    f"{one.path} was due for review on {one.stale_after}: "
                    "re-read it, then move bb:stale_after or deprecate it",
                )

    def test_the_catalogue_is_the_topics_that_have_been_migrated_so_far(self):
        # The migrated v1 topics plus Playbooks authored for v2 itself. The v1
        # subset is also resolved by `check_dispositions`; writing the complete
        # shipping set here keeps a new native Playbook from arriving only on
        # disk and never becoming part of the measured catalogue.
        self.assertEqual(
            [
                "agentic-ai",
                "api",
                "api-authorization",
                "attack-surface",
                "authentication",
                "browser-framing",
                "browser-messaging",
                "browser-realtime",
                "browser-script",
                "browser-storage",
                "client-side-path-traversal",
                "cms",
                "command-directory-injection",
                "cookies",
                "deployment",
                "deserialization",
                "exceptional-conditions",
                "external-resources",
                "file-resolution",
                "file-upload",
                "graphql",
                "grpc",
                "http-desync",
                "identity-lifecycle",
                "identity-parsing",
                "information-disclosure",
                "jwt-jose",
                "kubernetes",
                "logging",
                "nosql-injection",
                "oauth",
                "object-ownership",
                "orm",
                "payment-webhooks",
                "payment-workflows",
                "race-conditions",
                "realtime",
                "request-integrity",
                "request-parsing",
                "routing",
                "secrets",
                "spreadsheet-injection",
                "sql-injection",
                "ssrf-url-routing",
                "ssti",
                "structured-injection",
                "supply-chain",
                "web-cache",
                "webauthn",
                "webhooks",
                "workload-identities",
            ],
            sorted(self.corpus),
        )

    def test_every_reference_is_attached_to_the_one_playbook_that_absorbed_it(self):
        # This includes both `absorbed -> reference:<path>` disposition rows and
        # v2-native maintainer contracts. What makes either kind checkable is
        # the attachment, so the pairing is bound rather than only the count.
        self.assertEqual(
            {
                "agentic-ai": ("llm.md",),
                "api": ("api-soap.md", "api.md", "rate-limit-bypass.md"),
                "api-authorization": ("idor.md", "uuids.md"),
                "attack-surface": ("auto-scanners.md", "cves.md", "ffuf.md"),
                "authentication": ("cloud-aws-cognito.md", "http-attacks-password-reset.md",
                                   "sign-up-login-register.md", "type-juggling.md"),
                "browser-framing": ("clickjacking.md", "cors-xssi.md"),
                "browser-messaging": ("dom-vulnerabilities.md", "prototype-pollution.md"),
                "browser-realtime": ("websocket-attacks.md",),
                "browser-script": ("dangling-markup.md", "xss.md"),
                "cms": ("cms-drupal.md", "cms-joomla.md", "cms-wordpress.md"),
                # Two of these five describe classes `command-directory-injection`
                # does not grade. They are attached here because that is where
                # v1's pack put them, and this mapping records where each v1 page
                # went rather than where its subject is now read.
                "command-directory-injection": ("command-injection-filter-bypass.md",
                                                "ldap-injections.md", "os-command-injection.md",
                                                "shells.md", "xxe.md"),
                # One of these two describes work `deployment` refuses outright:
                # `http-attacks-tls-attacks.md` is a transport audit the scope
                # proxy makes unobservable, and it is attached here because that
                # is where v1's pack put it.
                "deployment": ("apache-tomcat.md", "http-attacks-tls-attacks.md"),
                "deserialization": ("deserialization-attacks.md",),
                "external-resources": ("broken-link-hijacking.md",),
                "file-resolution": ("lfi.md", "path-traversal-encoding-variants.md",
                                    "php-filter-chain-lfi-rce.md"),
                "file-upload": ("file-upload.md",),
                "graphql": ("api-graphql.md",),
                "http-desync": ("http-attacks-http-2-downgrading.md",
                                "http-attacks-request-smuggling-and-http-desync.md",
                                "proxy-tunnels.md"),
                "identity-parsing": ("saml.md",),
                "jwt-jose": ("jwt.md",),
                "oauth": ("oauth2-attack-via-google-oauth2-playground.md", "oauth2.md"),
                "object-ownership": ("why-two-identities.md",),
                "payment-webhooks": ("provider-webhook-contracts.md",),
                "payment-workflows": ("payment-process-contracts.md",),
                "race-conditions": ("race-conditions-and-timing-attacks.md",),
                "request-integrity": ("cors.md", "csrf.md"),
                "request-parsing": ("http-attacks-crlf-injection-and-response-splitting.md",
                                    "http-attacks-host-header.md", "parameter-pollution.md",
                                    "waf-bypasses.md"),
                "routing": ("http-attacks-verb-tampering.md", "status-code-bypass.md"),
                "sql-injection": ("sqli-advanced-sqli-techniques.md", "sqli-advanced-sqlmap.md",
                                  "sqli-blind-sql-injection.md", "sqli-custom-tampering.md",
                                  "sqli-identifying-vulnerabilities.md",
                                  "sqli-intro-to-mssql-sql-server.md",
                                  "sqli-leaking-netntlm-hashes.md", "sqli-out-of-band-dns.md",
                                  "sqli-postgresql-specific-techniques.md",
                                  "sqli-remote-code-execution.md", "sqli-time-based-sqli.md",
                                  "sqli.md"),
                # Three of these four describe questions `ssrf-url-routing`
                # does not grade -- one is `routing`'s and two end at
                # `webhooks` -- and they are attached here for the reason
                # the five above are.
                "ssrf-url-routing": ("dns-rebinding.md", "open-redirection.md",
                                     "pdf-generators.md", "ssrf.md"),
                "ssti": ("ssti.md",),
                "structured-injection": ("smtp-header-injection.md", "xpath-injections.md"),
                "web-cache": ("cache-poisoning.md",),
            },
            {
                name: tuple(reference.name for reference in one.references)
                for name, one in self.corpus.items()
                if one.references
            },
        )

    def test_every_reference_is_material_a_maintainer_can_open(self):
        for name, one in self.corpus.items():
            for reference in one.references:
                with self.subTest(playbook=name, reference=reference.name):
                    path = playbook.CORPUS.parent / reference.path
                    self.assertTrue(path.is_file())
                    self.assertEqual(playbook.digest(path.read_bytes()), reference.sha256)

    def test_no_shipped_document_names_a_property_class_the_vocabulary_lacks(self):
        # A Playbook's `bb:outputs` is checked against `property_classes` by a
        # foreign key at apply time. Its *prose* is not, and neither is a
        # fixture's ground truth or a maintainer reference -- and those are
        # where a Playbook says which neighbouring class a reading belongs to
        # instead. A plausible name that no leaf carries sends the next reader
        # to a class that does not exist, and nothing in the schema notices.
        #
        # Backticked `family.leaf` only, and only where the family is real: the
        # corpus writes class names in backticks throughout, and the family
        # filter is what keeps `app.py` and `fixture.md` out of the scan.
        schema = check_dispositions.schema_text(Path(playbook.__file__).parents[2])
        classes = check_dispositions.inserted_ids(schema, "property_classes")
        families = check_dispositions.inserted_ids(schema, "property_class_families")
        named = re.compile(r"`([a-z_]+\.[a-z_]+)`")
        for tree in ("playbooks", "fixtures", "skills"):
            for path in sorted((Path(playbook.__file__).parent / tree).rglob("*.md")):
                for found in named.findall(path.read_text(encoding="utf-8")):
                    if found.split(".")[0] in families:
                        with self.subTest(document=path.name, named=found):
                            self.assertIn(found, classes)

    def test_no_reference_text_reaches_a_shipped_projection(self):
        for name, one in self.corpus.items():
            canonical = one.projection.canonical()
            for reference in one.references:
                body = (playbook.CORPUS.parent / reference.path).read_text(encoding="utf-8")
                for line in body.splitlines():
                    stripped = line.strip()
                    if len(stripped) > 40:
                        with self.subTest(playbook=name, line=stripped[:40]):
                            self.assertNotIn(stripped, canonical)


class PaymentMethodTest(unittest.TestCase):
    """Ticket 231: payment coverage is procedure, not a topic list."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = playbook.compile_corpus(playbook.CORPUS)
        cls.process = cls.corpus["payment-workflows"]
        cls.webhook = cls.corpus["payment-webhooks"]

    def test_the_process_playbook_can_settle_each_business_logic_class_it_teaches(self):
        self.assertEqual(
            (
                "business_logic.quantity_or_price",
                "business_logic.replay",
                "business_logic.workflow_order",
            ),
            self.process.property_classes,
        )

    def test_the_incoming_webhook_is_authentication_not_outbound_request_forgery(self):
        self.assertEqual(
            ("authentication.credential_verification",),
            self.webhook.property_classes,
        )
        self.assertNotIn("injection.request_forgery", self.webhook.property_classes)

    def test_the_payment_methods_name_the_state_that_grades_them(self):
        instructions = self.process.projection.instructions.lower()
        for method in (
            "discount, credit and coupon composition",
            "currency, minor units and rounding",
            "capture, cancel and refund order",
            "idempotency keys",
            "reconcile five views",
        ):
            with self.subTest(method=method):
                self.assertIn(method, instructions)
        self.assertIn("authoritative", instructions)

    def test_each_provider_contract_is_in_the_executable_webhook_method(self):
        instructions = self.webhook.projection.instructions.lower()
        for provider in ("stripe", "adyen", "paypal"):
            with self.subTest(provider=provider):
                self.assertIn(provider, instructions)
        for property_ in ("raw body", "freshness", "duplicate", "authoritative state"):
            with self.subTest(property_=property_):
                self.assertIn(property_, instructions)


class AgainstTheRoster(unittest.TestCase):
    """Criterion 5's second half: a well-formed Playbook that does not fit.

    `_check_playbooks` is called directly rather than through `_compile`, for
    `test_skill`'s reason: a compile that got past it would go on to check
    things this corpus says nothing about.
    """

    def fitted(self, **changes: object) -> playbook.Playbook:
        return compiled(one(**changes))

    def refuses(self, fragment: str, **changes: object) -> None:
        with self.assertRaises(roster.RosterError) as caught:
            roster._check_playbooks({"object-ownership": self.fitted(**changes)})
        self.assertIn(fragment, str(caught.exception))

    def test_the_shipped_corpus_fits_the_roster(self):
        roster._check_playbooks(playbook.PLAYBOOKS)

    def test_a_skill_that_is_not_a_skill_is_refused(self):
        self.refuses("is not a skill", **{"bb:skills": ["read-minds"]})

    def test_a_combination_no_single_role_can_load_is_refused(self):
        # Two Skills that exist, held by two different roles. A Playbook is run
        # inside one Agent run, so this is not a Playbook that runs -- it is
        # two halves that never meet.
        self.refuses("at once", **{"bb:skills": ["analyse-source", "use-identity"]})

    def test_some_role_holds_every_skill_the_shipped_playbook_needs(self):
        needed = set(playbook.PLAYBOOKS["object-ownership"].skills)
        holders = [name for name, role in roster.ROLES.items() if needed <= set(role.skills)]
        self.assertTrue(holders, f"no role loads {sorted(needed)}")

    def test_every_skill_the_shipped_corpus_names_is_in_the_skill_corpus(self):
        for name, one_playbook in playbook.PLAYBOOKS.items():
            with self.subTest(playbook=name):
                self.assertEqual((), tuple(set(one_playbook.skills) - set(skill.SKILLS)))


if __name__ == "__main__":
    unittest.main()
