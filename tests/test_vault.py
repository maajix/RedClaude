"""What the harness does around `op`, on either side of running it.

The vault itself is not exercised here -- a test that needs the operator's
1Password account is a test that fails on any other machine. What is tested is
everything this runtime promises about a secret: which vaults it will read,
what it hands the child, what it does with each answer `op` gives back, and
what a value can and cannot be turned into once it is in memory.

The `op` answers below are the ones `op` 2.39.0 actually produced on this host,
copied rather than invented, because the classification depends on its wording
and a test written from the documentation would agree with nothing.
"""

import copy
import json
import pickle
import subprocess
import unittest
from unittest import mock

from redkraken import isolation, vault
from redkraken.outcome import INVALID_CONFIGURATION, MISSING_DEPENDENCY, VAULT_UNREADABLE
from tests.fixtures import boundary, scratch


DYNAMIC = "4exeximtkfyxd2eywo3m7jpfwu"
STATIC = "a4g3qhvisxxcyvfzjtfpariwfe"
ITEM = f"op://{DYNAMIC}/engagement/password"

#: `op` 2.39.0, verbatim, minus its timestamp prefix.
NO_ITEM = (
    "[ERROR] could not read secret 'op://4exeximtkfyxd2eywo3m7jpfwu/nope/password': "
    'could not get item 4exeximtkfyxd2eywo3m7jpfwu/nope: "nope" isn\'t an item in the '
    '"4exeximtkfyxd2eywo3m7jpfwu" vault. Specify the item with its UUID, name, or domain.'
)
NO_FIELD = (
    "[ERROR] could not read secret 'op://4exeximtkfyxd2eywo3m7jpfwu/engagement/nope': "
    "item '4exeximtkfyxd2eywo3m7jpfwu/engagement' does not have a field 'nope'"
)
SIGNED_OUT = (
    "[ERROR] could not read secret 'op://4exeximtkfyxd2eywo3m7jpfwu/engagement/password': "
    "error initializing client: You are not currently signed in. Please run "
    "`op signin --help` for instructions"
)
NO_SESSION = "[ERROR] could not find session token for account my"
FORBIDDEN = "[ERROR] (403) Forbidden: You aren't authorized to access this resource."


def answered(stdout: str = "", *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["op"], returncode=returncode, stdout=stdout, stderr=stderr)


class Stub:
    """A stand-in for `op` that records everything it was handed.

    Stands in for `child.run` rather than for `subprocess.run`, because what is
    asserted below is what this module hands a child -- the argument vector and
    the environment -- and that is exactly `child.run`'s parameter list. A stub
    one layer lower would be re-asserting `subprocess`.
    """

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls: list[tuple[str, list[str], dict[str, str], float]] = []

    def __call__(self, binary, arguments, *, environment, timeout, stdin=None):
        self.calls.append((binary, arguments, environment, timeout))
        return self.outcome

    @property
    def environment(self) -> dict[str, str]:
        return self.calls[-1][2]

    @property
    def arguments(self) -> list[str]:
        return self.calls[-1][1]


class VaultTestCase(unittest.TestCase):
    """Every test here runs against a stubbed `op` and a named environment."""

    def setUp(self):
        self.patched = mock.patch.object(vault.shutil, "which", return_value="/usr/bin/op")
        self.patched.start()
        self.addCleanup(self.patched.stop)

    def run_op(self, outcome, *, reference: str = ITEM, environ: dict | None = None):
        stub = Stub(outcome)
        with mock.patch.object(vault.child, "run", stub):
            self.stub = stub
            return vault.read(reference, environ={"OP_SERVICE_ACCOUNT_TOKEN": "ops_token", **(environ or {})})

    def refusal(self, outcome, *, reference: str = ITEM, environ: dict | None = None) -> vault.Refused:
        with self.assertRaises(vault.Refused) as caught:
            self.run_op(outcome, reference=reference, environ=environ)
        return caught.exception


class AuthorisationTest(VaultTestCase):
    """The two vault ids, which are the operator's statement and not a setting."""

    def test_both_authorised_vaults_parse(self):
        for identifier in (DYNAMIC, STATIC):
            with self.subTest(vault=identifier):
                self.assertEqual(identifier, vault.Reference.parse(f"op://{identifier}/item/field").vault)

    def test_any_other_vault_is_refused_before_a_subprocess_starts(self):
        # The whole point of the module. If this ever runs `op` first, the
        # refusal has become 1Password's rather than this harness's, and it
        # would change the day somebody widens a grant.
        stub = Stub(answered("never"))
        with mock.patch.object(vault.child, "run", stub):
            with self.assertRaises(vault.Refused) as caught:
                vault.read("op://ndbcuo3xwsnpvdzoeqmvyq7pqa/item/field", environ={})

        self.assertEqual([], stub.calls)
        self.assertEqual("vault:unauthorised", caught.exception.violation.source)
        self.assertEqual(INVALID_CONFIGURATION, caught.exception.violation.code)

    def test_a_vault_named_rather_than_identified_is_refused(self):
        # `op` resolves names perfectly well, which is exactly the problem: a
        # name is a label the operator can move between vaults, so a reference
        # spelled that way could not have been checked against anything.
        with self.assertRaises(vault.Refused) as caught:
            vault.Reference.parse("op://BugBounty Static/item/field")

        self.assertEqual("vault:unauthorised", caught.exception.violation.source)

    def test_the_authorised_vault_names_are_offered_back(self):
        with self.assertRaises(vault.Refused) as caught:
            vault.Reference.parse("op://Personal/item/field")

        self.assertIn("BugBounty Dynamic", str(caught.exception))
        self.assertIn("BugBounty Static", str(caught.exception))

    def test_the_boundary_is_the_types_and_not_the_parsers(self):
        # `parse` is one way to make a reference and `Reference(...)` is
        # another. If only the first checked, the boundary would hold for
        # today's callers and for no particular reason tomorrow's.
        with self.assertRaises(vault.Refused) as caught:
            vault.Reference(vault="ndbcuo3xwsnpvdzoeqmvyq7pqa", item="item", field="field")

        self.assertEqual("vault:unauthorised", caught.exception.violation.source)

    def test_an_unauthorised_refusal_names_the_item_and_its_vault(self):
        # Criterion 5. Both, because an operator with several references to fix
        # needs to know which one this is, and the vault alone does not say.
        with self.assertRaises(vault.Refused) as caught:
            vault.Reference.parse("op://ndbcuo3xwsnpvdzoeqmvyq7pqa/staging-account/password")

        self.assertIn("staging-account", str(caught.exception))
        self.assertIn("ndbcuo3xwsnpvdzoeqmvyq7pqa", str(caught.exception))


class ReferenceTest(unittest.TestCase):
    """What a reference is, and what it renders back as."""

    def test_a_section_is_carried_and_rendered_back(self):
        reference = vault.Reference.parse(f"op://{DYNAMIC}/item/section/field")

        self.assertEqual(("section", "field"), (reference.section, reference.field))
        self.assertEqual(f"op://{DYNAMIC}/item/section/field", str(reference))

    def test_a_reference_without_a_section_renders_back_unchanged(self):
        self.assertEqual(ITEM, str(vault.Reference.parse(ITEM)))

    def test_what_is_not_a_reference(self):
        for text in (
            "not-a-reference",
            "https://example.test/secret",
            f"op://{DYNAMIC}/item",
            f"op://{DYNAMIC}/a/b/c/d",
            f"op://{DYNAMIC}//field",
            f"op://{DYNAMIC}/item/password?attribute=otp",
            f"op://{DYNAMIC}/item/-flag",
            f"op://{DYNAMIC}/-item/field",
            f"op://{DYNAMIC}/item/two\nlines",
        ):
            with self.subTest(reference=text):
                with self.assertRaises(vault.Refused) as caught:
                    vault.Reference.parse(text)
                self.assertEqual(INVALID_CONFIGURATION, caught.exception.violation.code)

    def test_a_refusal_never_quotes_the_text_it_was_given(self):
        # A caller that pasted a password where a reference belongs has made one
        # mistake. Quoting it into a violation that is rendered, exited on and
        # stored would make that permanent.
        with self.assertRaises(vault.Refused) as caught:
            vault.Reference.parse("correct-horse-battery-staple")

        self.assertNotIn("correct-horse", str(caught.exception))

    def test_looks_like_asks_without_refusing(self):
        self.assertTrue(vault.Reference.looks_like("op://anything/at/all"))
        self.assertFalse(vault.Reference.looks_like("plain text"))
        self.assertFalse(vault.Reference.looks_like(None))
        self.assertFalse(vault.Reference.looks_like(7))


class SecretTest(unittest.TestCase):
    """The one type that holds a value, and every way it declines to give it up."""

    def setUp(self):
        self.reference = vault.Reference.parse(ITEM)
        self.secret = vault.Secret("correct-horse-battery-staple", self.reference)

    def test_the_value_is_reached_by_asking_for_it(self):
        self.assertEqual("correct-horse-battery-staple", self.secret.reveal())

    def test_no_way_of_rendering_it_renders_the_value(self):
        for rendered in (repr(self.secret), str(self.secret), f"{self.secret}", format(self.secret, ">40")):
            with self.subTest(rendered=rendered):
                self.assertNotIn("correct-horse", rendered)
                self.assertIn(str(self.reference), rendered)

    def test_it_cannot_be_serialised_into_an_event_or_an_artifact(self):
        with self.assertRaises(TypeError):
            json.dumps({"header": self.secret})

    def test_it_cannot_be_copied_or_pickled(self):
        with self.assertRaises(TypeError):
            pickle.dumps(self.secret)
        with self.assertRaises(TypeError):
            copy.deepcopy(self.secret)

    def test_it_has_no_attribute_dictionary_to_walk(self):
        # `__slots__`, so a report builder that reflects over its inputs finds
        # nothing to reflect over.
        with self.assertRaises(TypeError):
            vars(self.secret)


class ChildProcessTest(VaultTestCase):
    """What `op` is handed, which is where a token leaks if it leaks anywhere."""

    def test_the_reference_travels_as_an_argument_and_the_token_does_not(self):
        # `/proc/<pid>/cmdline` is world-readable for as long as the child
        # lives. The reference is not a secret; the token is.
        self.run_op(answered("value"))

        self.assertEqual(["read", "--no-newline", ITEM], self.stub.arguments)
        self.assertNotIn("ops_token", " ".join(self.stub.arguments))
        self.assertEqual("ops_token", self.stub.environment["OP_SERVICE_ACCOUNT_TOKEN"])

    def test_the_child_inherits_only_what_op_needs(self):
        self.run_op(
            answered("value"),
            environ={
                "PATH": "/usr/bin",
                "HOME": "/home/operator",
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "OP_SESSION_my": "session",
                "RK_ARTIFACT_KEY": "/etc/rk2/key",
                "AWS_SECRET_ACCESS_KEY": "not-op-business",
            },
        )

        self.assertEqual(
            {"PATH", "HOME", "XDG_RUNTIME_DIR", "OP_SESSION_my", "OP_SERVICE_ACCOUNT_TOKEN"},
            set(self.stub.environment),
        )

    def test_a_read_that_succeeded_returns_exactly_what_op_printed(self):
        # `--no-newline`, so there is no newline to strip and a value that ends
        # in one survives.
        secret = self.run_op(answered("value\n"))

        self.assertEqual("value\n", secret.reveal())

    def test_a_field_with_nothing_in_it_is_refused(self):
        refusal = self.refusal(answered(""))

        self.assertEqual("vault:empty_field", refusal.violation.source)

    def test_a_field_too_large_to_be_a_credential_is_refused(self):
        refusal = self.refusal(answered("x" * (vault.MAX_SECRET_BYTES + 1)))

        self.assertEqual("vault:oversized_field", refusal.violation.source)
        self.assertNotIn("xxxx", str(refusal))

    def test_op_missing_from_the_machine_is_a_dependency_and_not_a_configuration(self):
        with mock.patch.object(vault.shutil, "which", return_value=None):
            with self.assertRaises(vault.Refused) as caught:
                vault.read(ITEM, environ={})

        self.assertEqual(MISSING_DEPENDENCY, caught.exception.violation.code)

    def test_a_child_that_would_not_run_or_would_not_finish_is_reported_as_such(self):
        for outcome in (
            "/usr/bin/op did not finish within 30 seconds",
            "/usr/bin/op could not be run: no such file",
        ):
            with self.subTest(outcome=outcome):
                refusal = self.refusal(outcome)
                self.assertEqual(VAULT_UNREADABLE, refusal.violation.code)


class RefusalTest(VaultTestCase):
    """One distinct answer per thing that can be wrong, per criterion 5."""

    def test_each_answer_op_gives_has_its_own_refusal(self):
        expected = {
            NO_ITEM: ("vault:no_such_item", INVALID_CONFIGURATION),
            NO_FIELD: ("vault:no_such_field", INVALID_CONFIGURATION),
            SIGNED_OUT: ("vault:locked", VAULT_UNREADABLE),
            NO_SESSION: ("vault:locked", VAULT_UNREADABLE),
            FORBIDDEN: ("vault:forbidden", VAULT_UNREADABLE),
        }
        observed = {}
        for stderr in expected:
            refusal = self.refusal(answered(returncode=1, stderr=stderr))
            observed[stderr] = (refusal.violation.source, refusal.violation.code)

        self.assertEqual(expected, observed)

    def test_every_refusal_names_the_reference(self):
        for stderr in (NO_ITEM, NO_FIELD, SIGNED_OUT, FORBIDDEN, "something new in op 3"):
            with self.subTest(stderr=stderr):
                refusal = self.refusal(answered(returncode=1, stderr=stderr))
                self.assertIn(ITEM, str(refusal))

    def test_a_locked_vault_says_how_to_authenticate(self):
        refusal = self.refusal(answered(returncode=1, stderr=SIGNED_OUT))

        self.assertIn(vault.TOKEN_VARIABLE, str(refusal))

    def test_an_answer_this_module_does_not_know_is_still_refused_with_ops_words(self):
        # A wording that changes in a later `op` costs precision, never safety.
        refusal = self.refusal(answered(returncode=1, stderr="[ERROR] something new in op 3"))

        self.assertEqual(("vault:op", VAULT_UNREADABLE), (refusal.violation.source, refusal.violation.code))
        self.assertIn("something new in op 3", str(refusal))

    def test_a_failed_read_never_carries_what_the_child_printed(self):
        # `op` produces no value when it fails, and this is the assertion that
        # keeps it that way if it ever does.
        refusal = self.refusal(answered("leaked-value", returncode=1, stderr=NO_ITEM))

        self.assertNotIn("leaked-value", str(refusal))

    def test_an_unclassified_answer_is_bounded(self):
        refusal = self.refusal(answered(returncode=1, stderr="[ERROR] " + "z" * 4000))

        self.assertLess(len(str(refusal)), vault.STDERR_LIMIT + len(ITEM) + 100)


class CredentialTest(VaultTestCase):
    """Where the service account token comes from, in the order it is looked for."""

    def token(self, content: bytes, *, mode: int = 0o600):
        path = scratch() / "token"
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def test_a_token_already_exported_is_used_as_it_stands(self):
        path = self.token(b"ops_from_file")
        self.run_op(answered("value"), environ={vault.TOKEN_PATH_VARIABLE: str(path)})

        self.assertEqual("ops_token", self.stub.environment[vault.TOKEN_VARIABLE])

    def test_a_token_on_disk_is_read_when_nothing_is_exported(self):
        path = self.token(b"ops_from_file\n")
        stub = Stub(answered("value"))
        with mock.patch.object(vault.child, "run", stub):
            vault.read(ITEM, environ={vault.TOKEN_PATH_VARIABLE: str(path)})

        self.assertEqual("ops_from_file", stub.environment[vault.TOKEN_VARIABLE])

    def test_a_token_file_readable_by_more_than_its_owner_is_refused(self):
        # Rotated rather than repaired: a token the group could read is a token
        # that may already have been read, and quietly narrowing the mode would
        # hide that from the one person who can rotate it.
        path = self.token(b"ops_from_file", mode=0o640)
        stub = Stub(answered("value"))
        with mock.patch.object(vault.child, "run", stub):
            with self.assertRaises(vault.Refused) as caught:
                vault.read(ITEM, environ={vault.TOKEN_PATH_VARIABLE: str(path)})

        self.assertEqual([], stub.calls)
        self.assertIn("0640", str(caught.exception))

    def test_a_token_file_that_is_named_and_absent_is_refused_rather_than_skipped(self):
        # Falling through to whatever session the machine happens to have is the
        # opposite of what naming a file means.
        with self.assertRaises(vault.Refused) as caught:
            vault.read(ITEM, environ={vault.TOKEN_PATH_VARIABLE: str(scratch() / "absent")})

        self.assertIn("does not exist", str(caught.exception))

    def test_an_empty_token_file_is_refused(self):
        path = self.token(b"   \n")
        with self.assertRaises(vault.Refused) as caught:
            vault.read(ITEM, environ={vault.TOKEN_PATH_VARIABLE: str(path)})

        self.assertIn("no token", str(caught.exception))

    def test_with_no_token_anywhere_op_is_still_asked(self):
        # The desktop-app path. Refusing here would be this module deciding that
        # a machine with 1Password running has no way to authenticate; `op`
        # knows better, and says so in words that become `vault:locked`.
        stub = Stub(answered("value"))
        with mock.patch.object(vault.child, "run", stub):
            with mock.patch.object(vault, "DEFAULT_TOKEN_PATH", scratch() / "absent"):
                vault.read(ITEM, environ={"HOME": "/home/operator"})

        self.assertEqual(1, len(stub.calls))
        self.assertNotIn(vault.TOKEN_VARIABLE, stub.environment)


class BoundaryTest(unittest.TestCase):
    """The token stays on the side of the fence the operator's authorisation is on."""

    def test_nothing_behind_the_fence_can_inherit_the_service_account_token(self):
        # An Agent or a tool that inherited it would be reading the operator's
        # vault directly, and the two-vault list above would be a statement
        # about this module rather than about the harness.
        child = isolation.container_environment(
            boundary(), {vault.TOKEN_VARIABLE: "ops_token", "LANG": "C.UTF-8"}
        )

        self.assertNotIn(vault.TOKEN_VARIABLE, child)
        self.assertNotIn(vault.TOKEN_VARIABLE, isolation.INHERITED)
        self.assertNotIn(vault.TOKEN_VARIABLE, isolation.TOOL_ENVIRONMENT)


class ResolveTest(VaultTestCase):
    """Turning a document full of references into one full of values."""

    def resolve(self, document, stdout="value"):
        stub = Stub(answered(stdout))
        with mock.patch.object(vault.child, "run", stub):
            self.stub = stub
            return vault.resolve(document, environ={vault.TOKEN_VARIABLE: "ops_token"})

    def test_a_reference_anywhere_in_the_document_becomes_its_value(self):
        document, count = self.resolve(
            {"origins": [{"headers": [{"name": "Authorization", "value": ITEM}]}]}
        )

        self.assertEqual("value", document["origins"][0]["headers"][0]["value"])
        self.assertEqual(1, count)

    def test_everything_that_is_not_a_reference_is_left_alone(self):
        original = {"schema_version": 1, "url": "https://example.test/", "cookies": [], "on": True}

        document, count = self.resolve(dict(original))

        self.assertEqual(original, document)
        self.assertEqual(0, count)

    def test_keys_are_structure_and_are_never_resolved(self):
        # A document whose shape depends on a vault is one nobody can read.
        document, count = self.resolve({ITEM: "value"})

        self.assertEqual({ITEM: "value"}, document)
        self.assertEqual(0, count)

    def test_the_same_reference_twice_is_one_read(self):
        # A service account has an hourly budget, and one material file naming
        # the same field for two origins should spend one of it.
        document, count = self.resolve({"a": ITEM, "b": ITEM})

        self.assertEqual({"a": "value", "b": "value"}, document)
        self.assertEqual((2, 1), (count, len(self.stub.calls)))

    def test_one_refusal_stops_the_document(self):
        stub = Stub(answered(returncode=1, stderr=NO_ITEM))
        with mock.patch.object(vault.child, "run", stub):
            with self.assertRaises(vault.Refused):
                vault.resolve({"value": ITEM}, environ={vault.TOKEN_VARIABLE: "ops_token"})


if __name__ == "__main__":
    unittest.main()
