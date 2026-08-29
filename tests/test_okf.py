"""Whether the knowledge view is an OKF v0.2 bundle, and still the corpus.

Two questions, and they are different. The first is conformance: does this
bundle satisfy the specification at
<https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md>,
including the families ticket 101 named rather than only the three hard rules of
section 11. The second is drift: is the committed bundle still what the current
corpus generates. A bundle that conforms and describes last month's Playbooks is
a provenance view that lies precisely where it claims to be trustworthy.

The negative controls exist for `tests/test_database.py`'s reason, stated in its
own docstring: a check nobody has seen fail is a check nobody knows is wired up.
Every rule `okf.validate` enforces is broken here on purpose once, and the test
asserts it is the rule that fires, and on which side of the split -- a rule that
quietly moved from `faults` to `advisories` is a gate that quietly stopped
refusing.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from redkraken import okf, playbook, skill

ROOT = Path(__file__).resolve().parent.parent

#: Where the bundle lives. Here and not in `redkraken.okf`, because
#: `check_baseline` forbids production code under `src/` from naming a path in
#: the documentation tree, and it is right to: the installable application does
#: not read this bundle and must not depend on it existing.
BUNDLE = ROOT / "docs" / "okf"


class BundleTest(unittest.TestCase):
    """What the generator produces, before anything is written to disk."""

    @classmethod
    def setUpClass(cls):
        cls.files = okf.build(ROOT)

    def test_the_bundle_conforms(self):
        self.assertEqual(((), ()), okf.validate(self.files))

    def test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar(self):
        # The positive corpus, and the reason `frontmatter_faults` is a
        # grammar rather than a guess: a checker that has only ever been shown
        # what it must refuse does not know what it must admit. The count is
        # stated so a file that silently stops carrying a block is a failure
        # here rather than a silent skip.
        blocks = 0
        for name, text in sorted(self.files.items()):
            if not text.startswith("---\n"):
                continue
            blocks += 1
            self.assertEqual((), okf.frontmatter_faults(name, text), name)
        self.assertEqual(141, blocks)

    def test_the_reserved_log_carries_no_frontmatter(self):
        # Section 9: "Log files carry no frontmatter." The three section
        # indexes carry none either, by section 8.
        without = sorted(n for n, t in self.files.items() if not t.startswith("---\n"))
        self.assertEqual(
            ["log.md", "playbooks/index.md", "references/index.md", "skills/index.md"], without
        )

    def test_every_playbook_skill_and_reference_is_a_concept(self):
        # The count is stated as three sums rather than as 145, so a failure
        # says which corpus moved.
        references = sum(len(one.references) for one in playbook.PLAYBOOKS.values())
        references += sum(len(one.references) for one in skill.SKILLS.values())
        self.assertEqual(50, len(playbook.PLAYBOOKS))
        self.assertEqual(6, len(skill.SKILLS))
        self.assertEqual(84, references)
        for name in playbook.PLAYBOOKS:
            self.assertIn(f"playbooks/{name}.md", self.files)
        for name in skill.SKILLS:
            self.assertIn(f"skills/{name}.md", self.files)
        self.assertEqual(
            references,
            sum(1 for name in self.files if name.startswith("references/") and "index" not in name),
        )

    def test_the_root_index_is_the_only_index_with_frontmatter(self):
        # Section 8. An index elsewhere carrying frontmatter would be a concept
        # wearing a reserved name, which is the one shape a consumer may not
        # route.
        self.assertTrue(self.files["index.md"].startswith("---\nokf_version: \"0.2\"\n---\n"))
        for name in ("playbooks/index.md", "skills/index.md", "references/index.md"):
            self.assertFalse(self.files[name].startswith("---"), name)

    def test_no_concept_claims_a_trust_tier_it_has_not_earned(self):
        # The tier is derived from `verified`, and nothing in this corpus has
        # been verified: every Playbook ships `draft` because no fixture has
        # graded it. Writing the key would move all fifty to machine-confirmed
        # on the strength of a generator having run.
        for name, text in self.files.items():
            self.assertNotIn("\nverified:", text, name)
        for name, one in playbook.PLAYBOOKS.items():
            self.assertEqual("draft", one.status, name)
            self.assertIn("\nstatus: draft\n", self.files[f"playbooks/{name}.md"])

    def test_the_bb_contract_round_trips_as_extension_keys(self):
        # "Consumers SHOULD preserve unknown keys when round-tripping." Ours are
        # the `bb:` half, and this asserts they arrive intact rather than being
        # summarised into OKF's own vocabulary, which would lose the closed set.
        for name, one in playbook.PLAYBOOKS.items():
            text = self.files[f"playbooks/{name}.md"]
            self.assertIn(f"\nbb:category: {one.category}\n", text)
            self.assertIn(f"\nbb:risk: {one.risk}\n", text)
            self.assertIn(f"\nbb:effects: {one.effects}\n", text)
            self.assertIn(f"\nbb:baseline: {one.baseline}\n", text)
            self.assertIn(f"\nbb:version: {one.version}\n", text)
            self.assertIn(f"\nbb:sha256: {one.sha256}\n", text)
            for klass in one.property_classes:
                self.assertIn(klass, text)
            for fact in one.triggers_all:
                self.assertIn(fact, text)

    def test_the_playbook_skill_reference_graph_is_complete(self):
        # The link half of criterion three: every Skill a Playbook names is
        # reachable from its concept, and every Skill names back the Playbooks
        # that load it. `validate` already proved no link dangles; this proves
        # none is missing.
        for name, one in playbook.PLAYBOOKS.items():
            text = self.files[f"playbooks/{name}.md"]
            for used in one.skills:
                self.assertIn(f"](/skills/{used}.md)", text)
            for reference in one.references:
                self.assertIn(f"](/references/{name}--{reference.name[:-3]}.md)", text)
        for name, one in skill.SKILLS.items():
            text = self.files[f"skills/{name}.md"]
            for who in playbook.PLAYBOOKS.values():
                if name in who.skills:
                    self.assertIn(f"](/playbooks/{who.name}.md)", text)

    def test_generation_is_deterministic(self):
        # It has to be, or the freeze test below is noise. Nothing here reads a
        # clock, and `BUILT_AT` is the constant that keeps it that way.
        self.assertEqual(self.files, okf.build(ROOT))

    def test_a_source_id_collision_is_refused_rather_than_overwritten(self):
        # Two references sharing an id would silently drop one concept and
        # leave a footnote pointing at whichever survived. The corpus has no
        # collision today, so the control makes one.
        one = next(iter(playbook.PLAYBOOKS.values()))
        twin = playbook.PLAYBOOKS[one.name]
        forged = {one.name: one, "duplicate": twin}
        if not one.references:
            self.skipTest("the first Playbook carries no reference to collide")
        with self.assertRaises(okf.BundleError):
            okf.build(ROOT, playbooks=forged, skills={})


class NegativeControlTest(unittest.TestCase):
    """Each rule `validate` enforces, broken once, asserted to be the one that fires."""

    @classmethod
    def setUpClass(cls):
        cls.files = okf.build(ROOT)

    def broken(self, **changes: str) -> tuple[str, ...]:
        """The section 11 faults, which are the only ones a consumer may refuse over."""
        return okf.validate({**self.files, **changes})[0]

    def advised(self, **changes: str) -> tuple[str, ...]:
        """The soft rules, reported and never fatal."""
        return okf.validate({**self.files, **changes})[1]

    def test_a_missing_root_index_advises_rather_than_refuses(self):
        # Section 8 spells it "MAY appear in any directory, including the
        # bundle root". A bundle without one discloses less; it does not fail.
        without = {k: v for k, v in self.files.items() if k != "index.md"}
        faults, advisories = okf.validate(without)
        self.assertEqual((), faults)
        self.assertIn("the bundle has no root index.md", advisories)

    def test_a_root_index_without_the_version_is_advised(self):
        # Section 12 lists the field among the ones a root index MAY carry, and
        # section 11 does not ask for it at all. Reported, never fatal.
        changed = {"index.md": "# no frontmatter\n\n[a](/log.md)\n"}
        self.assertEqual((), self.broken(**changed))
        advisories = self.advised(**changed)
        self.assertTrue(any("okf_version" in one for one in advisories), advisories)

    def test_a_concept_without_frontmatter_is_named(self):
        faults = self.broken(**{"playbooks/cookies.md": "# just prose\n"})
        self.assertIn("playbooks/cookies.md: no parseable frontmatter block", faults)

    def test_a_concept_without_a_type_is_named(self):
        faults = self.broken(**{"playbooks/cookies.md": "---\ntitle: x\n---\n\nbody\n"})
        self.assertIn(
            "playbooks/cookies.md: no non-empty type, which is the one required key", faults
        )

    def test_a_log_that_grew_frontmatter_is_named(self):
        faults = self.broken(**{"log.md": "---\ntype: Log\n---\n\n## 2026-08-28\n"})
        self.assertIn("log.md: the reserved log carries a frontmatter block", faults)

    def test_a_log_without_a_date_heading_is_named(self):
        faults = self.broken(**{"log.md": "# Bundle history\n\nsomething happened\n"})
        self.assertIn("log.md: the reserved log carries no ISO 8601 date heading", faults)

    def test_a_log_that_is_not_newest_first_is_named(self):
        text = "# Bundle history\n\n## 2026-08-01\n\n- a\n\n## 2026-08-28\n\n- b\n"
        faults = self.broken(**{"log.md": text})
        self.assertIn("log.md: the reserved log is not newest first", faults)

    def test_a_non_root_index_carrying_frontmatter_is_named(self):
        faults = self.broken(**{"skills/index.md": "---\ntype: Skill\n---\n\n[a](/log.md)\n"})
        self.assertIn("skills/index.md: only the root index.md may carry frontmatter", faults)

    def test_an_index_with_no_links_is_named(self):
        faults = self.broken(**{"skills/index.md": "# Skills\n\nnothing here\n"})
        self.assertIn("skills/index.md: an index with no links discloses nothing", faults)

    def test_an_actor_outside_the_three_spellings_is_advised(self):
        text = self.files["skills/use-identity.md"].replace(
            "by: process:redkraken-okf", "by: whoever"
        )
        faults = self.advised(**{"skills/use-identity.md": text})
        self.assertTrue(any("not an OKF actor spelling" in fault for fault in faults), faults)

    def test_a_status_outside_the_lifecycle_family_is_advised(self):
        text = self.files["skills/use-identity.md"].replace("\nstatus: stable\n", "\nstatus: fine\n")
        faults = self.advised(**{"skills/use-identity.md": text})
        self.assertTrue(any("outside the lifecycle family" in fault for fault in faults), faults)

    def test_a_stale_after_that_is_a_date_and_not_an_instant_is_advised(self):
        text = self.files["skills/use-identity.md"].replace(
            "\nstale_after: 2027-08-28T00:00:00Z\n", "\nstale_after: 2027-08-28\n"
        )
        faults = self.advised(**{"skills/use-identity.md": text})
        self.assertTrue(any("not an absolute instant" in fault for fault in faults), faults)

    def test_a_footnote_matching_no_source_is_advised(self):
        # A defect in this bundle and not one of section 11's three rules, so
        # it is reported rather than refused. `test_the_bundle_conforms` still
        # holds the advisory list empty, which is where this stays graded.
        text = self.files["playbooks/attack-surface.md"] + "\n\nA claim.[^invented]\n"
        changed = {"playbooks/attack-surface.md": text}
        self.assertEqual((), self.broken(**changed))
        self.assertIn(
            "playbooks/attack-surface.md: footnote [^invented] matches no sources[].id",
            self.advised(**changed),
        )

    def test_a_source_nobody_cites_is_advised(self):
        text = self.files["playbooks/attack-surface.md"].replace(
            "[^attack-surface--cves]: Known vulnerabilities, versions, and what this corpus does with them\n",
            "",
        )
        changed = {"playbooks/attack-surface.md": text}
        self.assertEqual((), self.broken(**changed))
        self.assertIn(
            "playbooks/attack-surface.md: source id attack-surface--cves is declared"
            " and never cited",
            self.advised(**changed),
        )

    def test_a_link_to_nothing_is_advised(self):
        text = self.files["playbooks/cookies.md"] + "\n\n[gone](/skills/does-not-exist.md)\n"
        self.assertIn(
            "playbooks/cookies.md: bundle-relative link /skills/does-not-exist.md resolves to nothing",
            self.advised(**{"playbooks/cookies.md": text}),
        )


class GrammarTest(unittest.TestCase):
    """Every rule of `okf.frontmatter_faults`, broken once.

    A table and not twenty methods, because these are twenty instances of one
    question -- does this line leave the seven forms -- and twenty method names
    restating the `want` column would be the same sentence written twice. The
    positive half of the grammar is proved in `BundleTest` against the whole
    emitted bundle, which is the half a negative corpus cannot prove.
    """

    #: `(what it breaks, the block, the phrase the fault must carry)`.
    CASES = (
        ("no block at all", "# just prose\n", "no frontmatter block opens the file"),
        ("an unclosed block", "---\ntype: Log\n", "never closed"),
        ("an empty block", "---\n---\n\nbody\n", "block is empty"),
        ("a tab", "---\ntype: Log\n\tid: x\n---\n\nbody\n", "a tab is not indentation"),
        ("a line that is no pair", "---\ntype Log\n---\n\nbody\n", "is not `key: value`"),
        ("a blank line", "---\ntype: Log\n\n---\n\nbody\n", "is not `key: value`"),
        ("an upper-case key", "---\nType: Log\n---\n\nbody\n", "'Type' is not a key"),
        ("a twice-namespaced key", "---\na:b:c: x\n---\n\nbody\n", "is not a key"),
        ("a key stated twice", "---\ntype: Log\ntype: Skill\n---\n\nbody\n", "is stated twice"),
        ("a block scalar", "---\ntype: |\n---\n\nbody\n", "which YAML reads as structure"),
        ("a folded scalar", "---\ntype: >\n---\n\nbody\n", "which YAML reads as structure"),
        ("an anchor", "---\ntype: &a Log\n---\n\nbody\n", "which YAML reads as structure"),
        ("an alias", "---\ntype: *a\n---\n\nbody\n", "which YAML reads as structure"),
        ("a tag", "---\ntype: !!str Log\n---\n\nbody\n", "which YAML reads as structure"),
        ("a merge key", "---\n<<: x\n---\n\nbody\n", "is not a key"),
        ("a second colon", "---\ntype: a: b\n---\n\nbody\n", "a colon YAML would read"),
        ("a comment introducer", "---\ntype: Log #c\n---\n\nbody\n", "comment introducer"),
        ("an unclosed quote", '---\ntitle: "a\n---\n\nbody\n', "never closes"),
        ("an undefined escape", '---\ntitle: "a\\qb"\n---\n\nbody\n', "YAML does not define"),
        ("a quote that ends early", '---\ntitle: "a"b"\n---\n\nbody\n', "closes its quote early"),
        ("an unclosed sequence", "---\ntags: [a, b\n---\n\nbody\n", "never closes"),
        ("an empty element", "---\ntags: [a,,b]\n---\n\nbody\n", "an empty element"),
        ("a trailing comma", "---\ntags: [a, b,]\n---\n\nbody\n", "an empty element"),
        ("an empty sequence", "---\ntags: []\n---\n\nbody\n", "empty flow sequence"),
        ("a missing space", "---\ntags: [a,b]\n---\n\nbody\n", "comma and a space"),
        ("an unclosed mapping", "---\ngenerated: { by: x\n---\n\nbody\n", "never closes"),
        ("a mapping with no pair", "---\ngenerated: { x }\n---\n\nbody\n", "not a `key: value`"),
        ("an orphan indent", "---\ntype: Log\n  - id: x\n---\n\nbody\n", "under no block"),
        ("an odd indent", "---\nsources:\n   id: x\n---\n\nbody\n", "indented 3 spaces"),
        ("a two-space non-entry", "---\nsources:\n  id: x\n---\n\nbody\n", "opens no sequence"),
        ("a four-space entry", "---\nsources:\n    - id: x\n---\n\nbody\n", "four spaces in"),
        # A flow indicator ends the scalar wherever it stands, so each of these
        # four is two elements to a parser and one to a leading-character check.
        ("a bracket inside an element", "---\ntags: [a[b]\n---\n\nbody\n", "ends a scalar"),
        ("a bracket that closes early", "---\ntags: [a]b]\n---\n\nbody\n", "ends a scalar"),
        ("a brace inside an element", "---\ntags: [a{b}]\n---\n\nbody\n", "ends a scalar"),
        ("a bracket inside a mapping", "---\ngenerated: { by: a[b }\n---\n\nbody\n",
         "ends a scalar"),
    )

    def test_every_shape_outside_the_grammar_is_refused(self):
        for what, block, want in self.CASES:
            with self.subTest(what):
                faults = okf.frontmatter_faults("x.md", block)
                self.assertTrue(faults, f"{what} was admitted")
                self.assertTrue(any(want in fault for fault in faults), (what, faults))

    def test_the_seven_forms_are_admitted(self):
        # One line per form, so a refusal here says which form the grammar lost
        # rather than only that the bundle stopped conforming.
        block = (
            "---\n"
            "type: Log\n"
            "tags: [a, b, c]\n"
            'okf_version: "0.2"\n'
            "generated: { by: process:redkraken-okf, at: 2026-08-28T00:00:00Z }\n"
            "bb:category: injection\n"
            "sources:\n"
            "  - id: a--b\n"
            "    resource: /references/a--b.md\n"
            "---\n\nbody\n"
        )
        self.assertEqual((), okf.frontmatter_faults("x.md", block))

    def test_a_key_is_split_at_the_first_colon_and_space_and_not_the_first_colon(self):
        # The rule the first draft had backwards, and the reason `bb:category`
        # is one key and `stale_after: 2027-02-15T00:00:00Z` is one scalar.
        block = "---\nbb:category: injection\nstale_after: 2027-02-15T00:00:00Z\n---\n\nbody\n"
        self.assertEqual((), okf.frontmatter_faults("x.md", block))


class FreezeTest(unittest.TestCase):
    """The committed bundle is what this corpus generates, file by file.

    Committed rather than generated on demand for the reason every digest in
    this tree is written down: a view nobody can diff is a view nobody notices
    going wrong. The failure below names the file, and the fix is never to
    relax the assertion -- it is `python -c "import pathlib; from redkraken import
    okf; okf.write(pathlib.Path('.'), pathlib.Path('docs/okf'))"` and a reading
    of the diff.
    """

    def test_the_committed_bundle_is_current(self):
        expected = okf.build(ROOT)
        target = BUNDLE
        self.assertTrue(target.is_dir(), f"{target} has never been written")
        on_disk = {
            path.relative_to(target).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(target.rglob("*.md"))
        }
        self.assertEqual(
            sorted(expected), sorted(on_disk), "the committed bundle holds different files"
        )
        for name in sorted(expected):
            self.assertEqual(expected[name], on_disk[name], f"{target}/{name} is stale")

    def test_the_bundle_carries_nothing_but_markdown(self):
        # Section 11 is about `.md` files, and a stray file under the root is
        # material a consumer walking the bundle cannot classify.
        strays = sorted(
            path.relative_to(BUNDLE).as_posix()
            for path in BUNDLE.rglob("*")
            if path.is_file() and path.suffix != ".md"
        )
        self.assertEqual([], strays)


if __name__ == "__main__":
    unittest.main()
