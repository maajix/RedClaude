"""The scan that decides whether this repository is publishable.

Ticket 62 criterion 4. Two halves, and the second is the one that matters: that
the tree comes back clean says nothing on its own -- a scan with every rule
broken says the same thing -- so every rule here is also shown finding a
credential planted for it.

The planted values are assembled rather than written. A control that existed as
one string in this file would be a credential shape in the publishable tree, the
scan would have to forgive it, and a forgiven literal is one the scan can no
longer find anywhere. Splitting each one at a point its own rule cannot cross
keeps this file honestly clean and keeps the rule able to do its job.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import check_secrets
from tools.check_secrets import ALLOWED, RULES, Allowance, SecretsError


ROOT = Path(__file__).resolve().parents[1]

#: One planted credential per rule, in the shape a provider issues and in no
#: issuer's records. Keyed by rule name so a rule arriving without a control
#: fails by name rather than passing untested.
CONTROLS = {
    "anthropic": "sk-ant-" + "api03-CONTROLcheckSecretsPlanted",
    "onepassword": "ops_" + "C" * 43,
    "private_key": "-----BEGIN PRIVATE KEY-----\n" + "MIIC" * 30 + "\n-----END PRIVATE KEY-----",
    "url_password": "postgresql://rk2:" + "CONTROLcheckSecretsPlanted@127.0.0.1:5432/rk2",
    "aws": "AKIA" + "C" * 16,
    "github": "ghp_" + "C" * 36,
    "slack": "xoxb-" + "1111111111-CONTROLcheckSecretsPlanted",
    "google": "AIza" + "C" * 35,
    "jwt": "eyJhbGciOiJDT05UUk9MIn0." + "eyJzdWIiOiJjb250cm9sIn0.Y29udHJvbA",
    "bearer": "Bearer " + "CONTROLcheckSecretsBearerToken",
    "assigned_secret": 'token = "' + 'CONTROLcheckSecretsAssignedValue"',
}


def checkout(files: dict[str, str], ignore: str = "") -> Path:
    """A git checkout carrying `files`, so `publishable` has something to list."""
    root = Path(tempfile.mkdtemp(prefix="rk2-secrets-"))
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    if ignore:
        (root / ".gitignore").write_text(ignore, encoding="utf-8")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


class RuleTest(unittest.TestCase):
    """Each rule against the two strings it is written between."""

    def test_every_rule_still_matches_the_string_it_was_written_for(self):
        for rule in RULES:
            with self.subTest(rule.name):
                self.assertIsNotNone(rule.pattern.search(rule.probe))

    def test_every_rule_still_declines_the_string_it_must_leave_alone(self):
        for rule in RULES:
            with self.subTest(rule.name):
                self.assertIsNone(rule.pattern.search(rule.counter_probe))

    def test_a_rule_that_lost_its_probe_refuses_before_it_scans(self):
        broken = RULES[0]._replace(probe="nothing this matches")
        with mock.patch.object(check_secrets, "RULES", (broken,)):
            with self.assertRaisesRegex(SecretsError, "no longer matches its own probe"):
                check_secrets.declared()

    def test_a_rule_that_swallowed_its_counter_probe_refuses_before_it_scans(self):
        broken = RULES[0]._replace(counter_probe=RULES[0].probe)
        with mock.patch.object(check_secrets, "RULES", (broken,)):
            with self.assertRaisesRegex(SecretsError, "now matches its counter probe"):
                check_secrets.declared()

    def test_every_rule_has_a_control_that_makes_it_report(self):
        self.assertEqual({rule.name for rule in RULES}, set(CONTROLS))

    def test_no_control_is_the_probe_the_rule_already_forgives(self):
        """A rule clears what it finds in its own probe, so a control written as
        that same string would be a control the scan is required to ignore."""
        for rule in RULES:
            with self.subTest(rule.name):
                planted = rule.pattern.search(CONTROLS[rule.name])
                self.assertIsNotNone(planted)
                self.assertNotEqual(rule.probed(), rule.identifying(planted))

    def test_every_rule_finds_the_credential_planted_for_it(self):
        for rule in RULES:
            with self.subTest(rule.name):
                found = check_secrets.scan_text(CONTROLS[rule.name], "planted.txt")
                self.assertEqual([rule.name], [finding.rule for finding in found])

    def test_no_control_is_a_string_this_file_carries_whole(self):
        """The claim the assembly above is making, asked rather than assumed.

        A control written as one literal would be found by the tree scan in this
        very file, and the only way to make the tree pass again would be to
        declare it -- which would stop the rule finding that shape anywhere.
        """
        source = Path(__file__).read_bytes().decode("latin-1")
        for name, planted in CONTROLS.items():
            with self.subTest(name):
                self.assertNotIn(planted, source)

    def test_a_password_is_keyed_on_the_password_and_not_on_the_host(self):
        """`url_password` captures a group, so one declared sentinel covers every
        host it is written against rather than needing a row for each."""
        rule = {item.name: item for item in RULES}["url_password"]
        first = rule.pattern.search("postgresql://rk2:hunter2@127.0.0.1:5432/rk2")
        second = rule.pattern.search("postgresql://rk2:hunter2@example.test:5432/other")
        self.assertEqual("hunter2", rule.identifying(first))
        self.assertEqual(rule.identifying(first), rule.identifying(second))


class TreeTest(unittest.TestCase):
    """The repository as it stands."""

    def test_the_tree_this_repository_would_publish_carries_no_credential(self):
        report = check_secrets.check()
        self.assertTrue(report.startswith("secrets ok: "), report)

    def test_the_gate_runs_as_a_module_and_says_what_it_read(self):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "tools.check_secrets"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout, r"^secrets ok: files=\d+ rules=\d+ allowances=\d+\n$")

    def test_an_allowance_that_forgives_nothing_is_itself_a_problem(self):
        stale = Allowance("aws", "a fixture nobody kept", ("AKIA" + "Z" * 16,))
        with mock.patch.object(check_secrets, "ALLOWED", ALLOWED + (stale,)):
            with self.assertRaisesRegex(SecretsError, "forgives nothing"):
                check_secrets.check()

    def test_every_allowance_names_a_rule_that_exists(self):
        for allowance in ALLOWED:
            with self.subTest(allowance.rule):
                self.assertIn(allowance.rule, {rule.name for rule in RULES})


class CheckoutTest(unittest.TestCase):
    """What a clone carries, and what it does not."""

    def clean(self, root: Path, *roots: Path) -> str:
        """`check` over `root` with nothing declared, so only plants report."""
        with mock.patch.object(check_secrets, "ALLOWED", ()):
            return check_secrets.check(roots, checkout=root)

    def test_a_planted_credential_is_found_through_the_whole_gate(self):
        root = checkout({"deploy/notes.md": f"the key is {CONTROLS['aws']}\n"})
        with self.assertRaises(SecretsError) as raised:
            self.clean(root)
        self.assertIn("deploy/notes.md:1: aws", str(raised.exception))

    def test_a_file_nobody_has_committed_yet_is_still_a_file_a_clone_takes(self):
        """Untracked and unignored is one `git add` away from published, and the
        moment to find a credential in one is before that rather than after."""
        root = checkout({"scratchpad.txt": CONTROLS["github"]})
        with self.assertRaisesRegex(SecretsError, r"scratchpad\.txt:1: github"):
            self.clean(root)

    def test_an_ignored_file_is_not_a_file_a_clone_carries(self):
        root = checkout({"local.env": CONTROLS["github"]}, ignore="local.env\n")
        self.assertIn("secrets ok:", self.clean(root))

    def test_a_directory_a_run_produced_is_read_when_it_is_named(self):
        root = checkout({"README.md": "nothing here\n"})
        produced = Path(tempfile.mkdtemp(prefix="rk2-report-"))
        (produced / "report.md").write_text(CONTROLS["bearer"], encoding="utf-8")
        self.assertIn("secrets ok:", self.clean(root))
        with self.assertRaisesRegex(SecretsError, r"report\.md:1: bearer"):
            self.clean(root, produced)

    def test_a_file_past_the_ceiling_is_a_problem_rather_than_a_skip(self):
        """A scan that skipped what it could not hold would report a clean tree
        it had not read, which is the one answer worse than a finding."""
        root = checkout({"huge.log": "x" * 4096})
        with mock.patch.object(check_secrets, "CEILING", 1024):
            with self.assertRaisesRegex(SecretsError, r"huge\.log: 4096 bytes is past"):
                self.clean(root)

    def test_a_directory_that_is_not_one_is_refused(self):
        root = checkout({"README.md": "nothing here\n"})
        with self.assertRaisesRegex(SecretsError, "neither a file nor a directory"):
            self.clean(root, root / "no-such-place")

    def test_a_place_that_is_not_a_checkout_is_refused_rather_than_read_as_empty(self):
        empty = Path(tempfile.mkdtemp(prefix="rk2-not-a-checkout-"))
        with self.assertRaisesRegex(SecretsError, "not a checkout"):
            check_secrets.publishable(empty)


class FindingTest(unittest.TestCase):
    """What the report says, and the one thing it must never say."""

    def test_a_finding_names_the_place_and_the_length_and_not_the_value(self):
        planted = CONTROLS["anthropic"]
        found = check_secrets.scan_text(f"first line\nkey: {planted}\n", "settings.json")
        self.assertEqual(1, len(found))
        self.assertEqual(("anthropic", "settings.json", 2, len(planted)), tuple(found[0]))
        self.assertNotIn(planted, str(found[0]))

    def test_a_file_is_read_as_bytes_so_no_encoding_can_hide_a_credential(self):
        root = checkout({"README.md": "nothing here\n"})
        opaque = Path(root) / "capture.bin"
        opaque.write_bytes(b"\xff\xfe\x00" + CONTROLS["slack"].encode() + b"\x00\xff")
        with self.assertRaisesRegex(SecretsError, r"capture\.bin:1: slack"):
            with mock.patch.object(check_secrets, "ALLOWED", ()):
                check_secrets.check(checkout=root)


if __name__ == "__main__":
    unittest.main()
