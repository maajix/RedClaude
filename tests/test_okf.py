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
asserts it is the rule that fires.
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
        self.assertEqual((), okf.validate(self.files))

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
        return okf.validate({**self.files, **changes})

    def test_a_missing_root_index_is_named(self):
        without = {k: v for k, v in self.files.items() if k != "index.md"}
        self.assertIn("the bundle has no root index.md", okf.validate(without))

    def test_a_root_index_without_the_version_is_named(self):
        faults = self.broken(**{"index.md": "# no frontmatter\n\n[a](/log.md)\n"})
        self.assertTrue(any("okf_version" in fault for fault in faults), faults)

    def test_a_concept_without_frontmatter_is_named(self):
        faults = self.broken(**{"playbooks/cookies.md": "# just prose\n"})
        self.assertIn("playbooks/cookies.md: no parseable frontmatter block", faults)

    def test_a_concept_without_a_type_is_named(self):
        faults = self.broken(**{"playbooks/cookies.md": "---\ntitle: x\n---\n\nbody\n"})
        self.assertIn(
            "playbooks/cookies.md: no non-empty type, which is the one required key", faults
        )

    def test_a_log_that_lost_its_type_is_named(self):
        faults = self.broken(**{"log.md": "---\ntitle: x\n---\n\nbody\n"})
        self.assertIn("log.md: the reserved log carries no type: Log", faults)

    def test_a_non_root_index_carrying_frontmatter_is_named(self):
        faults = self.broken(**{"skills/index.md": "---\ntype: Skill\n---\n\n[a](/log.md)\n"})
        self.assertIn("skills/index.md: only the root index.md may carry frontmatter", faults)

    def test_an_index_with_no_links_is_named(self):
        faults = self.broken(**{"skills/index.md": "# Skills\n\nnothing here\n"})
        self.assertIn("skills/index.md: an index with no links discloses nothing", faults)

    def test_an_actor_outside_the_three_spellings_is_named(self):
        text = self.files["skills/use-identity.md"].replace(
            "by: process:redkraken-okf", "by: whoever"
        )
        faults = self.broken(**{"skills/use-identity.md": text})
        self.assertTrue(any("not an OKF actor spelling" in fault for fault in faults), faults)

    def test_a_status_outside_the_lifecycle_family_is_named(self):
        text = self.files["skills/use-identity.md"].replace("\nstatus: stable\n", "\nstatus: fine\n")
        faults = self.broken(**{"skills/use-identity.md": text})
        self.assertTrue(any("outside the lifecycle family" in fault for fault in faults), faults)

    def test_a_stale_after_that_is_a_date_and_not_an_instant_is_named(self):
        text = self.files["skills/use-identity.md"].replace(
            "\nstale_after: 2027-08-28T00:00:00Z\n", "\nstale_after: 2027-08-28\n"
        )
        faults = self.broken(**{"skills/use-identity.md": text})
        self.assertTrue(any("not an absolute instant" in fault for fault in faults), faults)

    def test_a_footnote_matching_no_source_is_named(self):
        text = self.files["playbooks/attack-surface.md"] + "\n\nA claim.[^invented]\n"
        faults = self.broken(**{"playbooks/attack-surface.md": text})
        self.assertIn(
            "playbooks/attack-surface.md: footnote [^invented] matches no sources[].id", faults
        )

    def test_a_source_nobody_cites_is_named(self):
        text = self.files["playbooks/attack-surface.md"].replace(
            "[^attack-surface--cves]: Known vulnerabilities, versions, and what this corpus does with them\n",
            "",
        )
        faults = self.broken(**{"playbooks/attack-surface.md": text})
        self.assertIn(
            "playbooks/attack-surface.md: source id attack-surface--cves is declared and never cited",
            faults,
        )

    def test_a_link_to_nothing_is_named(self):
        text = self.files["playbooks/cookies.md"] + "\n\n[gone](/skills/does-not-exist.md)\n"
        faults = self.broken(**{"playbooks/cookies.md": text})
        self.assertIn(
            "playbooks/cookies.md: bundle-relative link /skills/does-not-exist.md resolves to nothing",
            faults,
        )


class FreezeTest(unittest.TestCase):
    """The committed bundle is what this corpus generates, file by file.

    Committed rather than generated on demand for the reason every digest in
    this tree is written down: a view nobody can diff is a view nobody notices
    going wrong. The failure below names the file, and the fix is never to
    relax the assertion -- it is `python -c "from redkraken import okf, pathlib;
    okf.write(pathlib.Path('.'))"` and a reading of the diff.
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
