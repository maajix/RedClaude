import ast
import copy
import json
import unittest
from unittest import mock

from redkraken import _startup
from tests import ROOT


SOURCE = ROOT / "src" / "redkraken" / "_startup.py"
MANIFEST = (
    ROOT
    / "src"
    / "redkraken"
    / "measurements"
    / "auth-resolution-sdk-0.2.132-cli-2.1.224.json"
)


class AuthResolutionManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = _startup._load_manifest()

    def test_the_complete_measured_matrix_replays_offline(self):
        replay = _startup.replay_auth_resolution()

        self.assertEqual(("0.2.132", "2.1.224"), _startup.KNOWN_RUNTIME)
        self.assertEqual(list(_startup.REQUIRED_CASE_IDS), [row["id"] for row in replay])
        self.assertEqual(
            {"baseline", "api_key_empty", "proj_helper_isolated"},
            {row["id"] for row in replay if row["decision"] == "allow"},
        )

    def test_case_identity_drift_is_rejected_before_case_bodies(self):
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
                with self.assertRaisesRegex(_startup.ManifestError, "^case set mismatch"):
                    _startup._validate_manifest(mutation)

    def test_each_measured_case_returns_its_literal_structured_violations(self):
        expected = {
            "baseline": [],
            "api_key": [
                ("ANTHROPIC_API_KEY", "env:ANTHROPIC_API_KEY", "off_subscription_auth")
            ],
            "auth_token": [
                ("ANTHROPIC_AUTH_TOKEN", "env:ANTHROPIC_AUTH_TOKEN", "off_subscription_auth")
            ],
            "api_key_empty": [],
            "base_url": [
                ("ANTHROPIC_BASE_URL", "env:ANTHROPIC_BASE_URL", "destination_override")
            ],
            "api_key_helper": [
                (
                    "apiKeyHelper",
                    "settings:explicit:/fixture/runtime/settings.json#apiKeyHelper",
                    "off_subscription_auth",
                )
            ],
            "fd": [
                (
                    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
                    "env:CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
                    "startup_denial",
                )
            ],
            "bedrock": [
                (
                    "CLAUDE_CODE_USE_BEDROCK",
                    "env:CLAUDE_CODE_USE_BEDROCK",
                    "provider_reroute",
                )
            ],
            "vertex": [
                (
                    "CLAUDE_CODE_USE_VERTEX",
                    "env:CLAUDE_CODE_USE_VERTEX",
                    "provider_reroute",
                )
            ],
            "foundry": [
                (
                    "CLAUDE_CODE_USE_FOUNDRY",
                    "env:CLAUDE_CODE_USE_FOUNDRY",
                    "provider_reroute",
                )
            ],
            "settings_env_key": [
                (
                    "ANTHROPIC_API_KEY",
                    "settings:explicit:/fixture/runtime/settings.json#env.ANTHROPIC_API_KEY",
                    "off_subscription_auth",
                )
            ],
            "proj_helper_isolated": [],
            "proj_helper_loaded": [
                (
                    "apiKeyHelper",
                    "settings:project:/fixture/project/.claude/settings.json#apiKeyHelper",
                    "off_subscription_auth",
                )
            ],
            "prec_key_vs_token": [
                ("ANTHROPIC_API_KEY", "env:ANTHROPIC_API_KEY", "off_subscription_auth"),
                (
                    "ANTHROPIC_AUTH_TOKEN",
                    "env:ANTHROPIC_AUTH_TOKEN",
                    "off_subscription_auth",
                ),
            ],
            "prec_key_vs_helper": [
                ("ANTHROPIC_API_KEY", "env:ANTHROPIC_API_KEY", "off_subscription_auth"),
                (
                    "apiKeyHelper",
                    "settings:explicit:/fixture/runtime/settings.json#apiKeyHelper",
                    "off_subscription_auth",
                ),
            ],
            "prec_token_vs_helper": [
                (
                    "ANTHROPIC_AUTH_TOKEN",
                    "env:ANTHROPIC_AUTH_TOKEN",
                    "off_subscription_auth",
                ),
                (
                    "apiKeyHelper",
                    "settings:explicit:/fixture/runtime/settings.json#apiKeyHelper",
                    "off_subscription_auth",
                ),
            ],
            "prec_key_vs_bedrock": [
                ("ANTHROPIC_API_KEY", "env:ANTHROPIC_API_KEY", "off_subscription_auth"),
                (
                    "CLAUDE_CODE_USE_BEDROCK",
                    "env:CLAUDE_CODE_USE_BEDROCK",
                    "provider_reroute",
                ),
            ],
        }

        replay = {row["id"]: row for row in _startup.replay_auth_resolution()}
        for case_id, records in expected.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(
                    [
                        {
                            "code": "credential_vector",
                            "vector": vector,
                            "source": source,
                            "effect": effect,
                        }
                        for vector, source, effect in records
                    ],
                    replay[case_id]["violations"],
                )

    def test_only_the_measured_empty_api_key_is_unset(self):
        for vector in _startup.WATCHED_ENV_VECTORS:
            with self.subTest(vector=vector):
                result = _startup._evaluate_inputs(
                    {"environment": {vector: ""}, "setting_sources": [], "settings": []}
                )
                self.assertEqual(
                    "allow" if vector == "ANTHROPIC_API_KEY" else "refuse",
                    result["decision"],
                )

    def test_subscription_labels_without_a_request_are_not_a_positive_measurement(self):
        baseline = next(case for case in self.manifest["cases"] if case["id"] == "baseline")
        wire = copy.deepcopy(baseline["wire"])
        wire["request_count"] = 0

        self.assertEqual("refuse", _startup._measured_decision(wire))

    def test_a_different_refusal_shape_cannot_corroborate_a_vector_effect(self):
        manifest = copy.deepcopy(self.manifest)
        cases = {case["id"]: case for case in manifest["cases"]}
        cases["base_url"]["wire"] = copy.deepcopy(cases["fd"]["wire"])

        with self.assertRaisesRegex(
            _startup.ManifestError,
            "base_url: wire outcome does not measure destination_override",
        ):
            _startup._replay_manifest(manifest)

    def test_changed_manifest_is_rejected_before_case_evaluation(self):
        with (
            mock.patch.object(_startup, "_MANIFEST_SHA256", "0" * 64),
            mock.patch.object(_startup, "_validate_manifest") as validate,
            self.assertRaisesRegex(_startup.ManifestError, "manifest digest changed"),
        ):
            _startup._load_manifest()

        validate.assert_not_called()

    def test_replay_has_no_ambient_sdk_or_network_import_path(self):
        source = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
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
            imports.isdisjoint(
                {"claude_agent_sdk", "glob", "os", "probe", "socket", "subprocess", "urllib"}
            )
        )
        self.assertNotIn(".home(", source)

    def test_publishable_fixture_contains_only_sanitised_facts(self):
        text = MANIFEST.read_text(encoding="utf-8")
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
