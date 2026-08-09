import ast
import copy
import json
import unittest
from pathlib import Path

import auth_resolution as auth


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "evidence/auth-resolution-sdk-0.2.132-cli-2.1.224.json"


class AuthResolutionEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = auth.load_manifest(MANIFEST)
        cls.cases = {case["id"]: case for case in cls.manifest["cases"]}

    def test_complete_manifest_replays(self):
        replay = auth.replay_manifest(self.manifest)
        self.assertEqual(list(auth.REQUIRED_CASE_IDS), [row["id"] for row in replay])
        self.assertEqual(
            {"baseline", "api_key_empty", "proj_helper_isolated"},
            {row["id"] for row in replay if row["decision"] == "allow"},
        )

    def test_case_set_is_checked_before_case_bodies(self):
        mutations = []

        missing = copy.deepcopy(self.manifest)
        missing["cases"] = missing["cases"][:-1]
        missing["cases"][0]["wire"] = {}
        mutations.append(missing)

        duplicate = copy.deepcopy(self.manifest)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        duplicate["cases"][0]["wire"] = {}
        mutations.append(duplicate)

        additional = copy.deepcopy(self.manifest)
        additional["cases"].append({"id": "unexpected"})
        additional["cases"][0]["wire"] = {}
        mutations.append(additional)

        for mutation in mutations:
            with self.subTest(ids=[case["id"] for case in mutation["cases"]]):
                with self.assertRaisesRegex(auth.ManifestError, "^case set mismatch"):
                    auth.validate_manifest(mutation)

    def test_mixed_vectors_return_all_violations_in_registry_order(self):
        decision = auth.evaluate_inputs(self.cases["prec_key_vs_token"]["inputs"])
        self.assertEqual("refuse", decision["decision"])
        self.assertEqual(
            [
                {
                    "code": "credential_vector",
                    "vector": "ANTHROPIC_API_KEY",
                    "source": "env:ANTHROPIC_API_KEY",
                    "effect": "off_subscription_auth",
                },
                {
                    "code": "credential_vector",
                    "vector": "ANTHROPIC_AUTH_TOKEN",
                    "source": "env:ANTHROPIC_AUTH_TOKEN",
                    "effect": "off_subscription_auth",
                },
            ],
            decision["violations"],
        )

    def test_only_measured_api_key_empty_value_is_unset(self):
        for vector in auth.WATCHED_ENV_VECTORS:
            with self.subTest(vector=vector):
                decision = auth.evaluate_inputs(
                    {"environment": {vector: ""}, "setting_sources": [], "settings": []}
                )
                expected = "allow" if vector == "ANTHROPIC_API_KEY" else "refuse"
                self.assertEqual(expected, decision["decision"])

    def test_project_settings_are_excluded_only_when_the_source_is_excluded(self):
        self.assertEqual(
            "allow", auth.evaluate_inputs(self.cases["proj_helper_isolated"]["inputs"])["decision"]
        )
        self.assertEqual(
            "refuse", auth.evaluate_inputs(self.cases["proj_helper_loaded"]["inputs"])["decision"]
        )

    def test_subscription_label_without_a_request_is_not_positive_evidence(self):
        wire = copy.deepcopy(self.cases["baseline"]["wire"])
        wire["request_count"] = 0
        self.assertEqual("refuse", auth.measured_decision(wire))

    def test_replay_has_no_ambient_or_network_import_path(self):
        tree = ast.parse((HERE / "auth_resolution.py").read_text())
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            imports.isdisjoint({"claude_agent_sdk", "glob", "os", "probe", "socket", "urllib"})
        )
        self.assertNotIn(".home(", (HERE / "auth_resolution.py").read_text())

    def test_fixture_contains_only_sanitised_facts(self):
        text = MANIFEST.read_text()
        for forbidden in (
            "/home/",
            "credential_headers",
            "sha12",
            "sk-ant-",
            "mitmproxy-ca",
            "Authorization",
            "x-api-key",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        json.loads(text)


if __name__ == "__main__":
    unittest.main()
