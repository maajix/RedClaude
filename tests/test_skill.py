"""What the compiler accepts, what it refuses, and what the shipped corpus is.

Two halves, and they are different questions. The first builds corpora on disk
out of text -- one well-formed skill, then that same skill broken one way at a
time -- and reads the code the refusal carries. The second asks the corpus this
package actually ships whether it is what the ticket says a corpus is.

Corpora are written rather than fixtured because every negative here is a file
that must not exist in `src/redkraken/skills/`: a skill naming a role that is
not a role, a script that is a symbolic link out of the tree, an `allowed-tools`
line reaching for `Bash`. The only way to have both the rule and its violation
is to write the violation somewhere the corpus is not.
"""

import json
import re
import unittest
from pathlib import Path

from redkraken import roster, skill
from redkraken.document import FENCE
from tests.fixtures import frontmatter, scratch


ROOT = Path(__file__).resolve().parents[1]


#: The smallest skill that compiles. Every negative below is this document with
#: one thing changed, so the thing that changed is the thing under test.
FRONTMATTER = {
    "description": "Compare two stored responses and cite what differs.",
    "bb:roles": ["web_hunter"],
    "bb:tool_groups": ["state.read"],
    "bb:evidence_profile": "allowed_receipt_only",
}

BODY = """
# A technique

## 1. Do the thing

Complete this step holding the answer.
"""

#: A script that is a transform of its stdin and nothing else, which is what
#: `check` is trying to establish about a real one.
COUNTER = """\
import json
import sys

document = json.load(sys.stdin)
json.dump({"count": len(document["artifacts"])}, sys.stdout, sort_keys=True)
"""

#: The same script with a coin in it. Two runs of a case disagree, which is the
#: only thing that separates a transform from a guess.
COIN = """\
import json
import random
import sys

json.load(sys.stdin)
json.dump({"count": random.random()}, sys.stdout, sort_keys=True)
"""


def document(fields: dict, body: str = BODY) -> str:
    """One `SKILL.md`, from a mapping, the way the parser reads one back."""
    return frontmatter(fields) + body


def corpus(**skills: str | None) -> Path:
    """A corpus root holding one directory per named skill.

    A `None` document makes the directory and leaves out the `SKILL.md`, which
    is the one negative that cannot be expressed as a document.
    """
    root = scratch() / "skills"
    root.mkdir()
    for name, text in skills.items():
        directory = root / name.replace("_", "-")
        directory.mkdir()
        if text is not None:
            (directory / skill.INSTRUCTIONS).write_text(text, encoding="utf-8")
    return root


def one(fields: dict | None = None, body: str = BODY, **changes: object) -> Path:
    """A corpus holding exactly one skill, well-formed unless a caller says otherwise."""
    return corpus(a_technique=document((fields or FRONTMATTER) | changes, body))


class Refusals(unittest.TestCase):
    """Criterion 6: every shape of malformed skill, by the code it refuses with.

    The assertions are on `SkillError.code` rather than on the sentence, for the
    reason the class docstring in `skill` gives: the sentence is for a person
    reading a refusal and should be free to improve.
    """

    def refuses(self, code: str, root: Path) -> skill.SkillError:
        with self.assertRaises(skill.SkillError) as caught:
            skill.compile_corpus(root)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    # -- the document -------------------------------------------------------

    def test_a_skill_without_instructions_is_not_a_skill(self):
        self.refuses("file_missing", corpus(a_technique=None))

    def test_frontmatter_must_open_and_close(self):
        self.refuses("frontmatter_malformed", corpus(a_technique="# no fence at all\n"))
        unclosed = FENCE + "\ndescription: a thing\n" + BODY
        self.refuses("frontmatter_malformed", corpus(a_technique=unclosed))

    def test_an_empty_frontmatter_is_refused_rather_than_defaulted(self):
        empty = f"{FENCE}\n{FENCE}\n{BODY}"
        self.refuses("frontmatter_malformed", corpus(a_technique=empty))

    def test_a_line_that_is_not_a_key_and_a_value_is_refused(self):
        self.refuses("frontmatter_malformed", one(body=BODY, **{"just some prose": ""}))

    def test_a_padded_line_is_refused_because_two_parsers_read_it_differently(self):
        padded = document(FRONTMATTER).replace(
            "bb:roles:", "  bb:roles:", 1
        )
        self.refuses("frontmatter_malformed", corpus(a_technique=padded))

    def test_a_value_yaml_would_read_as_structure_is_refused(self):
        self.refuses("frontmatter_malformed", one(description="- a list, apparently"))

    def test_a_value_carrying_a_second_key_is_refused(self):
        self.refuses("frontmatter_malformed", one(description="a thing: and another"))

    def test_a_key_stated_twice_is_refused_rather_than_resolved(self):
        text = document(FRONTMATTER).replace(
            "bb:evidence_profile: allowed_receipt_only",
            "bb:evidence_profile: allowed_receipt_only\nbb:evidence_profile: successful_tool_run",
            1,
        )
        self.refuses("duplicate_key", corpus(a_technique=text))

    def test_a_skill_with_no_body_teaches_nothing(self):
        self.refuses("body_missing", one(body="\n   \n"))

    def test_a_skill_states_every_required_key(self):
        for key in skill.REQUIRED_KEYS:
            with self.subTest(key=key):
                self.refuses(
                    "key_missing",
                    one({name: value for name, value in FRONTMATTER.items() if name != key}),
                )

    def test_a_key_nothing_reads_is_refused_rather_than_ignored(self):
        self.refuses("key_unknown", one(**{"bb:budget": "unlimited"}))

    def test_a_description_has_a_ceiling(self):
        self.refuses(
            "description_unbounded", one(description="x" * (skill.DESCRIPTION_LIMIT + 1))
        )

    # -- the keys that would reach past the text ----------------------------

    def test_no_skill_may_state_a_key_that_edits_the_frame(self):
        for key in skill.FORBIDDEN_KEYS:
            with self.subTest(key=key):
                refusal = self.refuses("key_forbidden", one(**{key: "anything"}))
                self.assertIn(key, refusal.detail)

    def test_the_forbidden_keys_are_the_ones_that_open_a_frame(self):
        # Pinned as a set, because the value of this list is that adding a key
        # to it is a decision somebody makes rather than a default.
        self.assertEqual(
            {"agent", "agents", "context", "model", "name"}, set(skill.FORBIDDEN_KEYS)
        )

    # -- names, roles and tools ---------------------------------------------

    def test_a_skill_is_named_the_way_the_script_tool_names_it(self):
        root = corpus(a_technique=document(FRONTMATTER))
        (root / "a-technique").rename(root / "A_Capability")
        self.refuses("name_invalid", root)

    def test_the_duplicates_a_corpus_can_express_are_the_ones_in_a_document(self):
        # Two skills cannot share a name: the name is the directory's and the
        # filesystem settles it. Inside a document they can, and each place is
        # refused where it is written.
        root = one(**{"bb:scripts": [
            {"name": "count.py", "description": "one", "checks": [
                {"artifacts": [], "stdout": None}]},
            {"name": "count.py", "description": "two", "checks": [
                {"artifacts": [], "stdout": None}]},
        ]})
        scripts = root / "a-technique" / skill.SCRIPT_DIR
        scripts.mkdir()
        (scripts / "count.py").write_text(COUNTER)

        self.refuses("duplicate_entry", root)
        self.refuses("duplicate_entry", one(**{"bb:roles": ["recon", "recon"]}))

    def test_a_role_list_is_a_sorted_unique_non_empty_json_array(self):
        self.refuses("value_malformed", one(**{"bb:roles": []}))
        self.refuses("value_malformed", one(**{"bb:roles": ["web_hunter", "recon"]}))
        self.refuses("duplicate_entry", one(**{"bb:roles": ["recon", "recon"]}))
        self.refuses("value_malformed", one(**{"bb:roles": ["Web Hunter"]}))

    def test_a_tool_group_that_is_not_a_group_name_at_all_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:tool_groups": ["state read"]}))

    def test_an_evidence_profile_that_could_not_be_an_id_is_refused(self):
        self.refuses("value_malformed", one(**{"bb:evidence_profile": "Allowed Receipts"}))

    # -- scripts -------------------------------------------------------------

    def test_a_declared_script_that_is_absent_is_refused(self):
        self.refuses("file_missing", one(**{"bb:scripts": [
            {"name": "count.py", "description": "count", "checks": [
                {"artifacts": [], "stdout": {"count": 0}}]}
        ]}))

    def test_a_script_with_no_check_is_deterministic_behaviour_nobody_ran(self):
        root = one(**{"bb:scripts": [
            {"name": "count.py", "description": "count", "checks": []}
        ]})
        (root / "a-technique" / skill.SCRIPT_DIR).mkdir()
        (root / "a-technique" / skill.SCRIPT_DIR / "count.py").write_text(COUNTER)
        self.refuses("check_missing", root)

    def test_a_script_name_that_is_a_path_never_reaches_the_filesystem(self):
        for name in ("../../etc/passwd", "/etc/passwd", "sub/count.py"):
            with self.subTest(name=name):
                self.refuses("path_escape", one(**{"bb:scripts": [
                    {"name": name, "description": "escape", "checks": [
                        {"artifacts": [], "stdout": None}]}
                ]}))

    def test_a_script_that_is_a_symbolic_link_is_refused_after_resolution(self):
        root = one(**{"bb:scripts": [
            {"name": "count.py", "description": "count", "checks": [
                {"artifacts": [], "stdout": {"count": 0}}]}
        ]})
        scripts = root / "a-technique" / skill.SCRIPT_DIR
        scripts.mkdir()
        outside = scratch() / "count.py"
        outside.write_text(COUNTER)
        (scripts / "count.py").symlink_to(outside)
        self.refuses("path_escape", root)

    def test_a_file_in_the_corpus_that_nothing_declares_is_refused(self):
        root = one()
        scripts = root / "a-technique" / skill.SCRIPT_DIR
        scripts.mkdir()
        (scripts / "count.py").write_text(COUNTER)
        refusal = self.refuses("stray_file", root)
        self.assertIn("count.py", refusal.detail)

    def test_a_file_beside_the_instructions_that_nothing_reads_is_refused(self):
        root = one()
        (root / "a-technique" / "notes.md").write_text("scratch\n")
        self.refuses("stray_file", root)

    def test_the_corpus_holds_directories_and_nothing_else(self):
        root = one()
        (root / "README.md").write_text("about the corpus\n")
        self.refuses("stray_file", root)

    # -- references ----------------------------------------------------------

    def test_a_reference_is_hashed_into_the_manifest_like_anything_else(self):
        root = one(**{"bb:references": ["cheatsheet.md"]})
        references = root / "a-technique" / skill.REFERENCE_DIR
        references.mkdir()
        (references / "cheatsheet.md").write_text("one page\n")

        compiled = skill.compile_corpus(root)["a-technique"]

        self.assertEqual(("cheatsheet.md",), compiled.references)
        self.assertIn(
            skill.Dependency(
                "reference", "references/cheatsheet.md", skill.digest(b"one page\n")
            ),
            compiled.dependencies,
        )

    def test_a_reference_name_that_is_a_path_never_reaches_the_filesystem(self):
        for name in ("../../etc/passwd", "/etc/passwd", "sub/cheatsheet.md"):
            with self.subTest(name=name):
                self.refuses("path_escape", one(**{"bb:references": [name]}))

    def test_a_declared_reference_that_is_absent_is_refused(self):
        self.refuses("file_missing", one(**{"bb:references": ["cheatsheet.md"]}))

    def test_a_file_in_the_reference_directory_that_nothing_declares_is_refused(self):
        root = one()
        references = root / "a-technique" / skill.REFERENCE_DIR
        references.mkdir()
        (references / "cheatsheet.md").write_text("one page\n")
        refusal = self.refuses("stray_file", root)
        self.assertIn("cheatsheet.md", refusal.detail)

    def test_a_reference_list_is_a_sorted_unique_non_empty_json_array(self):
        self.refuses("value_malformed", one(**{"bb:references": []}))
        self.refuses("value_malformed", one(**{"bb:references": ["b.md", "a.md"]}))
        self.refuses("duplicate_entry", one(**{"bb:references": ["a.md", "a.md"]}))

    def test_a_corpus_that_is_not_there_is_not_an_empty_one(self):
        self.refuses("corpus_missing", scratch() / "absent")

    def test_an_empty_corpus_is_refused(self):
        root = scratch() / "skills"
        root.mkdir()
        self.refuses("corpus_missing", root)


class Checks(unittest.TestCase):
    """Criterion 3: a script's declared cases, run for real."""

    def build(self, source: str, checks: list[dict]) -> Path:
        root = one(**{"bb:scripts": [
            {"name": "count.py", "description": "count the artifacts", "checks": checks}
        ]})
        scripts = root / "a-technique" / skill.SCRIPT_DIR
        scripts.mkdir()
        (scripts / "count.py").write_text(source)
        return root

    def test_a_declared_case_is_run_and_its_answer_is_the_declared_one(self):
        root = self.build(COUNTER, [
            {"artifacts": [], "stdout": {"count": 0}},
            {"artifacts": ["first", "second"], "stdout": {"count": 2}},
        ])
        compiled = skill.compile_corpus(root)

        self.assertEqual(
            ("a-technique/count.py#1", "a-technique/count.py#2"), skill.check_all(compiled)
        )

    def test_a_case_whose_answer_is_wrong_refuses(self):
        compiled = skill.compile_corpus(
            self.build(COUNTER, [{"artifacts": [], "stdout": {"count": 99}}])
        )
        with self.assertRaises(skill.SkillError) as caught:
            skill.check_all(compiled)
        self.assertEqual("check_failed", caught.exception.code)

    def test_a_script_that_answers_twice_and_differs_is_not_deterministic(self):
        compiled = skill.compile_corpus(
            self.build(COIN, [{"artifacts": [], "stdout": {"count": 0.5}}])
        )
        with self.assertRaises(skill.SkillError) as caught:
            skill.check_all(compiled)
        self.assertEqual("check_failed", caught.exception.code)
        self.assertIn("differed", caught.exception.detail)

    def test_a_case_is_handed_the_hash_of_the_text_it_states(self):
        # The author writes the text; the runner writes the digest. An author
        # who could state a digest could state one the bytes beside it do not
        # have, and every citation downstream would be over the wrong number.
        payload = json.loads(skill.Case(("first",), None).payload())

        self.assertEqual(
            [{"sha256": skill.digest(b"first"), "text": "first"}], payload["artifacts"]
        )


class Version(unittest.TestCase):
    """Criterion 1 and criterion 5: what a version is, and what moves it."""

    def build(self, script: str) -> skill.Skill:
        root = one(**{"bb:scripts": [
            {"name": "count.py", "description": "count", "checks": [
                {"artifacts": [], "stdout": {"count": 0}}]}
        ]})
        scripts = root / "a-technique" / skill.SCRIPT_DIR
        scripts.mkdir()
        (scripts / "count.py").write_text(script)
        return skill.compile_corpus(root)["a-technique"]

    def test_the_version_is_the_digest_of_the_manifest_and_nothing_else(self):
        compiled = self.build(COUNTER)
        manifest = "".join(f"{item.line()}\n" for item in compiled.dependencies)

        self.assertEqual(skill.digest(manifest.encode("utf-8")), compiled.version)

    def test_editing_a_script_moves_the_version_and_leaves_the_text_alone(self):
        first = self.build(COUNTER)
        second = self.build(COUNTER + "\n# a comment nobody reads\n")

        self.assertEqual(first.sha256, second.sha256)
        self.assertNotEqual(first.version, second.version)

    def test_editing_the_instructions_moves_both(self):
        first = skill.compile_corpus(one())["a-technique"]
        second = skill.compile_corpus(one(body=BODY + "\n## 2. And another\n"))["a-technique"]

        self.assertNotEqual(first.sha256, second.sha256)
        self.assertNotEqual(first.version, second.version)

    def test_the_manifest_covers_every_file_the_skill_owns(self):
        compiled = self.build(COUNTER)

        self.assertEqual(
            (
                skill.Dependency("instruction", "SKILL.md", compiled.sha256),
                skill.Dependency(
                    "script", "scripts/count.py", compiled.scripts["count.py"].sha256
                ),
            ),
            compiled.dependencies,
        )


class Corpus(unittest.TestCase):
    """The corpus this package ships, against what the ticket says a corpus is."""

    def test_every_technique_the_ticket_names_is_a_skill(self):
        self.assertEqual(
            (
                "analyse-source",
                "browser-evidence",
                "compare-responses",
                "enumerate-surface",
                "handle-untrusted-content",
                "use-identity",
            ),
            tuple(skill.SKILLS),
        )

    def test_no_skill_is_named_for_a_vulnerability_family_or_a_workflow(self):
        # Criterion 2, as the one check that can be written for it: the corpus
        # is the enumeration, so a family name is caught by there being no such
        # directory. This pins the families v1 actually shipped as skills.
        families = {
            "access-control", "auth-session", "business-logic", "injection",
            "ssrf", "xss", "idor", "recon-workflow",
        }

        self.assertEqual(set(), families & set(skill.SKILLS))

    def test_every_skill_carries_a_description_a_model_can_select_on(self):
        for name, one_skill in skill.SKILLS.items():
            with self.subTest(name=name):
                self.assertTrue(one_skill.description.strip())
                self.assertLessEqual(len(one_skill.description), skill.DESCRIPTION_LIMIT)
                # "Use when ..." is how the SDK's own selection works: the
                # description is read before the body is, so it has to say when.
                self.assertIn("Use when", one_skill.description)

    def test_every_declared_check_in_the_shipped_corpus_passes(self):
        self.assertEqual(
            (
                "analyse-source/extract_paths.py#1",
                "analyse-source/extract_paths.py#2",
                "analyse-source/extract_paths.py#3",
                "compare-responses/compare.py#1",
                "compare-responses/compare.py#2",
            ),
            skill.check_all(),
        )

    def test_the_v1_code_review_packs_are_bound_to_the_skill_that_reads_source(self):
        # Ticket 48. v1 shipped `playbooks/code-review/` -- one README and nine
        # language sink lists -- as context every Agent carried. The migration's
        # claim is not that the knowledge was kept but that it was *bound*, so
        # the check is both halves: these ten belong to the one technique that
        # reads source, and no other shipped skill has any reference at all.
        self.assertEqual(
            (
                "code-review.md",
                "sinks-csharp.md",
                "sinks-go.md",
                "sinks-java.md",
                "sinks-js.md",
                "sinks-kotlin.md",
                "sinks-php.md",
                "sinks-python.md",
                "sinks-ruby.md",
                "sinks-rust.md",
            ),
            skill.SKILLS["analyse-source"].references,
        )
        self.assertEqual(
            {"analyse-source"},
            {name for name, one in skill.SKILLS.items() if one.references},
        )

    def test_each_pack_is_headed_by_classes_the_selector_can_select_on(self):
        # Ticket 48. Binding ten filenames proves the attachment and nothing
        # about what is inside them, so this reads the packs: a sink list is
        # organised by Property class because that is the vocabulary a Playbook
        # triggers on, and a heading that is nearly a class -- an event kind, a
        # family that was renamed -- is a match that arrives carrying a word
        # nothing downstream selects on.
        from tools import check_dispositions

        classes = check_dispositions.resolvable_names(
            ROOT, check_dispositions.read_policy()
        )["property_class"]
        packs = [
            name
            for name in skill.SKILLS["analyse-source"].references
            if name.startswith("sinks-")
        ]
        self.assertEqual(9, len(packs))
        for name in packs:
            text = (
                skill.CORPUS / "analyse-source" / skill.REFERENCE_DIR / name
            ).read_text(encoding="utf-8")
            headings = re.findall(r"^## (\S+)$", text, re.MULTILINE)
            with self.subTest(pack=name):
                self.assertTrue(headings)
                self.assertEqual([], sorted(set(headings) - classes))
                # The closing section is the pack's own refusal to be read as a
                # verdict list, which is the failure mode a sink list has.
                self.assertIn("\n## What a match is not\n", text)

    def test_no_skill_body_sends_a_model_to_a_file_it_cannot_open(self):
        # `Read` is forbidden to every role, so a reference is material a
        # maintainer opens and nothing a running Agent can reach. A body that
        # named one would be an instruction the runtime cannot carry out, which
        # is worse than an absent reference: the model would go looking.
        for name, one_skill in skill.SKILLS.items():
            body = one_skill.source.decode("utf-8").split(FENCE, 2)[-1]
            for reference in (*one_skill.references, skill.REFERENCE_DIR + "/"):
                with self.subTest(skill=name, reference=reference):
                    self.assertNotIn(reference, body)

    def test_the_corpus_ships_inside_the_package(self):
        # Not a style point. `rk` runs what it was installed with, and a corpus
        # at the repository root is one that exists in a checkout and not in a
        # wheel -- so the failure would be at load time on an installed system
        # and never here.
        self.assertEqual(Path(skill.__file__).resolve().parent / "skills", skill.CORPUS)
        self.assertTrue((skill.CORPUS / "use-identity" / skill.INSTRUCTIONS).is_file())


class AgainstTheRoster(unittest.TestCase):
    """Criterion 4: a skill reaches for nothing the role that loads it lacks."""

    def test_every_role_a_skill_names_holds_the_tool_to_load_it(self):
        for name, one_skill in skill.SKILLS.items():
            for role_name in one_skill.roles:
                with self.subTest(skill=name, role=role_name):
                    role = roster.ROLES[role_name]
                    self.assertIn(roster.SKILL, role.builtin_tools)
                    self.assertFalse(role.rendered)

    def test_every_tool_group_a_skill_needs_is_one_its_roles_already_hold(self):
        for name, one_skill in skill.SKILLS.items():
            for role_name in one_skill.roles:
                with self.subTest(skill=name, role=role_name):
                    self.assertEqual(
                        (),
                        tuple(sorted(set(one_skill.tool_groups) - set(roster.ROLES[role_name].tool_groups))),
                    )

    def test_an_allowed_tools_line_only_ever_narrows(self):
        # Against what the skill itself declared, which is the set the compile
        # uses. `Role.tools` is every group the role holds, a strict superset,
        # and a test written over it would pass corpora the compile refuses.
        for name, one_skill in skill.SKILLS.items():
            if not one_skill.allowed_tools:
                continue
            with self.subTest(skill=name):
                declared = {
                    member
                    for group in one_skill.tool_groups
                    for member in roster.TOOL_GROUPS[group]
                }
                for role_name in one_skill.roles:
                    declared |= set(roster.ROLES[role_name].builtin_tools)
                self.assertEqual((), tuple(sorted(set(one_skill.allowed_tools) - declared)))

    def test_no_allowed_tools_line_exposes_a_forbidden_builtin(self):
        for name, one_skill in skill.SKILLS.items():
            with self.subTest(skill=name):
                self.assertEqual(
                    (),
                    tuple(sorted(set(one_skill.allowed_tools) & set(roster.FORBIDDEN_BUILTINS))),
                )

    def test_the_roster_derives_each_role_s_skills_from_the_corpus(self):
        derived: dict[str, list[str]] = {name: [] for name in roster.ROLES}
        for name, one_skill in sorted(skill.SKILLS.items()):
            for role_name in one_skill.roles:
                derived[role_name].append(name)

        self.assertEqual(
            {name: tuple(sorted(names)) for name, names in derived.items()},
            {name: role.skills for name, role in roster.ROLES.items()},
        )

    def test_every_runtime_tool_a_skill_names_is_one_run_tool_runs(self):
        for name, one_skill in skill.SKILLS.items():
            if not one_skill.runtime_tools:
                continue
            with self.subTest(skill=name):
                self.assertEqual(
                    (), tuple(sorted(set(one_skill.runtime_tools) - set(roster.RUN_TOOL_NAMES)))
                )
                self.assertIn(roster.RUN_TOOL_GROUP, one_skill.tool_groups)

    def test_a_role_that_loads_nothing_holds_no_tool_to_load_with(self):
        # The SDK reads an empty `skills` list as "every skill", so a role that
        # holds the tool and is granted nothing has the widest surface there is.
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertEqual(bool(role.skills), roster.SKILL in role.builtin_tools)

    def test_the_gate_admits_exactly_the_skills_the_role_was_granted(self):
        # The compile decides what fits; this is the one of the three
        # containment points that runs while a model does.
        for name, role in roster.ROLES.items():
            if not role.skills:
                continue
            gate = roster.Gate(name)
            with self.subTest(role=name):
                for granted in role.skills:
                    call = roster.Call(roster.SKILL, {roster.SKILL_NAME: granted})
                    self.assertIsNone(gate.decide(call))
                stranger = next(other for other in skill.SKILLS if other not in role.skills)
                denial = gate.decide(roster.Call(roster.SKILL, {roster.SKILL_NAME: stranger}))
                self.assertIsNotNone(denial)
                self.assertEqual(roster.UNGRANTED_SKILL, denial.rule)

    def test_a_role_that_loads_nothing_is_denied_every_skill(self):
        for name, role in roster.ROLES.items():
            if role.skills or role.rendered:
                continue
            gate = roster.Gate(name)
            with self.subTest(role=name):
                denial = gate.decide(
                    roster.Call(roster.SKILL, {roster.SKILL_NAME: "use-identity"})
                )
                self.assertIsNotNone(denial)


class RefusedByTheRoster(unittest.TestCase):
    """Criterion 6's second half: a well-formed skill that does not fit.

    Every case here is a document `skill` would compile without complaint --
    the roles are spelled like roles, the groups like groups -- and that the
    roster refuses because of what those names mean once the roles are known.
    The corpus module cannot ask these questions; it does not know a role from
    a word.

    `_check_skills` is called directly rather than through `_compile`, because
    a compile that got past it would go on to check things this corpus says
    nothing about. It publishes onto `ROLES` only after every rule has held, so
    a refusal here leaves the roster exactly as it was -- which is what
    `test_a_refused_corpus_leaves_the_roster_alone` is about.
    """

    def fitted(self, **changes: object) -> skill.Skill:
        """One skill that fits, before a caller breaks exactly one thing."""
        fields = {
            "name": "a-technique",
            "description": "Compare two stored responses. Use when both are recorded.",
            "roles": ("web_hunter",),
            "tool_groups": ("state.read",),
            "evidence_profile": "allowed_receipt_only",
            "allowed_tools": (),
            "runtime_tools": (),
            "scripts": {},
            "references": (),
            "source": b"---\n---\n# A technique\n",
            "sha256": skill.digest(b"---\n---\n# A technique\n"),
            "dependencies": (),
        }
        return skill.Skill(**(fields | changes))

    def refuses(self, fragment: str, **changes: object) -> None:
        with self.assertRaises(roster.RosterError) as caught:
            roster._check_skills({"a-technique": self.fitted(**changes)})
        self.assertIn(fragment, str(caught.exception))

    def test_a_tool_group_that_is_not_a_group_is_refused(self):
        self.refuses("is not a tool group", tool_groups=("state.everything",))

    def test_a_role_that_is_not_a_roster_role_is_refused(self):
        self.refuses("is not a roster role", roles=("penetration_tester",))

    def test_a_role_that_runs_no_model_cannot_be_taught_anything(self):
        self.refuses("runs no model to read it", roles=("reporter",))

    def test_a_role_with_no_skill_tool_cannot_be_granted_a_skill(self):
        self.refuses("has no tool to load a skill with", roles=("validator",))

    def test_a_tool_group_the_role_does_not_hold_is_refused(self):
        # The rule the whole module exists for: instructions cannot reach for
        # authority the compile did not already grant the role that reads them.
        self.refuses("does not hold", tool_groups=("validate.judge",))

    def test_an_allowed_tools_line_that_adds_a_tool_is_refused(self):
        self.refuses(
            "allowed-tools widens to",
            allowed_tools=("mcp__rk2__http_request",),
        )

    def test_an_allowed_tools_line_carrying_a_forbidden_builtin_is_refused(self):
        for builtin in ("Bash", "Read", "WebFetch", "Workflow"):
            with self.subTest(builtin=builtin):
                self.refuses("allowed-tools exposes", allowed_tools=(builtin,))

    def test_a_runtime_tool_run_tool_does_not_run_is_refused(self):
        self.refuses(
            "is not a tool run_tool runs",
            tool_groups=(roster.RUN_TOOL_GROUP,),
            runtime_tools=("bash",),
        )

    def test_a_runtime_tool_named_without_the_group_that_runs_it_is_refused(self):
        # The skill would compile, the role holds every group it asked for, and
        # the instruction is still telling a model to make a call the gate will
        # refuse. Criterion 4 read the other way round.
        self.refuses(f"without {roster.RUN_TOOL_GROUP}", runtime_tools=("jq",))

    def test_an_allowed_tools_line_may_narrow_to_nothing_it_declared(self):
        # The positive the widening rule is the boundary of: subtracting is
        # always allowed, so a line naming one tool out of a group it holds is
        # not a refusal.
        roster._check_skills({"a-technique": self.fitted(allowed_tools=("Skill",))})

    def test_a_refused_corpus_leaves_the_roster_alone(self):
        before = {name: role.skills for name, role in roster.ROLES.items()}
        with self.assertRaises(roster.RosterError):
            roster._check_skills({
                "first": self.fitted(name="first"),
                "second": self.fitted(name="second", roles=("penetration_tester",)),
            })

        self.assertEqual(before, {name: role.skills for name, role in roster.ROLES.items()})

    def tearDown(self):
        # Every test above either refuses -- which publishes nothing -- or
        # publishes a corpus of one. Recompiling puts the shipped grants back so
        # the file's order does not decide what the next test sees.
        roster._check_skills(skill.SKILLS)


if __name__ == "__main__":
    unittest.main()
