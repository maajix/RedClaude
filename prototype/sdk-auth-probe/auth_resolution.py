"""Pure, offline replay of the measured Claude auth-resolution matrix."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


REQUIRED_CASE_IDS = (
    "baseline",
    "api_key",
    "auth_token",
    "api_key_empty",
    "base_url",
    "api_key_helper",
    "fd",
    "bedrock",
    "vertex",
    "foundry",
    "settings_env_key",
    "proj_helper_isolated",
    "proj_helper_loaded",
    "prec_key_vs_token",
    "prec_key_vs_helper",
    "prec_token_vs_helper",
    "prec_key_vs_bedrock",
)

WATCHED_ENV_VECTORS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_BASE_URL",
)

_RULES = {
    "ANTHROPIC_API_KEY": "off_subscription_auth",
    "ANTHROPIC_AUTH_TOKEN": "off_subscription_auth",
    "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR": "startup_denial",
    "CLAUDE_CODE_USE_BEDROCK": "provider_reroute",
    "CLAUDE_CODE_USE_VERTEX": "provider_reroute",
    "CLAUDE_CODE_USE_FOUNDRY": "provider_reroute",
    "ANTHROPIC_BASE_URL": "destination_override",
    "apiKeyHelper": "off_subscription_auth",
}
_VECTOR_ORDER = {name: index for index, name in enumerate(_RULES)}
_SETTING_KINDS = {"managed", "explicit", "user", "project", "local"}
_ROUTES = {"anthropic_first_party", "other", "none"}
_AUTH_CLASSES = {"subscription_oauth", "api_key", "other_bearer", "none"}


class ManifestError(ValueError):
    pass


def _violation(vector: str, source: str) -> dict[str, str]:
    return {
        "code": "credential_vector",
        "vector": vector,
        "source": source,
        "effect": _RULES[vector],
    }


def _active(vector: str, value: Any) -> bool:
    if not isinstance(value, str):
        raise ManifestError(f"symbolic value for {vector} must be a string")
    return value != "" if vector == "ANTHROPIC_API_KEY" else True


def evaluate_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate symbolic launch inputs without consulting ambient state."""
    if not isinstance(inputs, Mapping):
        raise ManifestError("case inputs must be an object")
    environment = inputs.get("environment", {})
    settings = inputs.get("settings", [])
    setting_sources = inputs.get("setting_sources", [])
    if not isinstance(environment, Mapping):
        raise ManifestError("inputs.environment must be an object")
    if not isinstance(settings, list):
        raise ManifestError("inputs.settings must be an array")
    if not isinstance(setting_sources, list) or not all(
        isinstance(source, str) for source in setting_sources
    ):
        raise ManifestError("inputs.setting_sources must be an array of strings")

    violations = []
    for vector in WATCHED_ENV_VECTORS:
        if vector in environment and _active(vector, environment[vector]):
            violations.append(_violation(vector, f"env:{vector}"))

    selected_sources = set(setting_sources)
    for setting in settings:
        if not isinstance(setting, Mapping):
            raise ManifestError("each symbolic setting must be an object")
        kind = setting.get("kind")
        path = setting.get("path")
        document = setting.get("document")
        if kind not in _SETTING_KINDS or not isinstance(path, str) or not path:
            raise ManifestError("each symbolic setting needs a known kind and path")
        if not isinstance(document, Mapping):
            raise ManifestError("each symbolic setting document must be an object")
        if kind not in {"managed", "explicit"} and kind not in selected_sources:
            continue

        prefix = f"settings:{kind}:{path}#"
        if "apiKeyHelper" in document:
            violations.append(_violation("apiKeyHelper", prefix + "apiKeyHelper"))
        settings_environment = document.get("env", {})
        if not isinstance(settings_environment, Mapping):
            raise ManifestError("a symbolic settings env member must be an object")
        for vector in WATCHED_ENV_VECTORS:
            if vector in settings_environment and _active(
                vector, settings_environment[vector]
            ):
                violations.append(_violation(vector, prefix + f"env.{vector}"))

    violations.sort(key=lambda item: (_VECTOR_ORDER[item["vector"]], item["source"]))
    return {"decision": "refuse" if violations else "allow", "violations": violations}


def measured_decision(wire: Mapping[str, Any]) -> str:
    """Derive the observed decision from sanitised wire facts alone."""
    if not isinstance(wire, Mapping):
        raise ManifestError("case wire facts must be an object")
    return (
        "allow"
        if wire.get("route") == "anthropic_first_party"
        and wire.get("auth_class") == "subscription_oauth"
        and wire.get("destination_class") == "anthropic_api"
        and isinstance(wire.get("request_count"), int)
        and wire["request_count"] > 0
        else "refuse"
    )


def _case_set(cases: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(cases, list):
        raise ManifestError("manifest cases must be an array")
    ids = [case.get("id") if isinstance(case, Mapping) else None for case in cases]
    counts = Counter(ids)
    expected = set(REQUIRED_CASE_IDS)
    missing = [case_id for case_id in REQUIRED_CASE_IDS if counts[case_id] == 0]
    duplicate = sorted(str(case_id) for case_id, count in counts.items() if count > 1)
    additional = sorted(str(case_id) for case_id in counts if case_id not in expected)
    if missing or duplicate or additional:
        raise ManifestError(
            "case set mismatch: "
            f"missing={missing}, duplicate={duplicate}, additional={additional}"
        )
    return {str(case["id"]): case for case in cases}


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, Mapping):
        raise ManifestError("manifest must be an object")
    cases = _case_set(manifest.get("cases"))

    if manifest.get("schema_version") != 1:
        raise ManifestError("unsupported manifest schema_version")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, Mapping) or not all(
        isinstance(runtime.get(key), str) and runtime[key]
        for key in ("sdk_version", "bundled_cli_version")
    ):
        raise ManifestError("manifest runtime versions are required")
    probe = manifest.get("probe")
    retained = probe.get("retained_capture") if isinstance(probe, Mapping) else None
    if not isinstance(probe, Mapping) or not _is_hex(probe.get("commit"), 40):
        raise ManifestError("manifest probe commit must be a full git sha")
    if not isinstance(retained, Mapping) or retained.get("algorithm") != "sha256":
        raise ManifestError("manifest retained capture must use sha256")
    if not _is_hex(retained.get("digest"), 64) or not isinstance(
        retained.get("members"), int
    ) or retained["members"] < 1:
        raise ManifestError("manifest retained capture metadata is invalid")

    for case_id in REQUIRED_CASE_IDS:
        case = cases[case_id]
        evaluate_inputs(case.get("inputs"))
        wire = case.get("wire")
        if not isinstance(wire, Mapping):
            raise ManifestError(f"{case_id}: wire facts must be an object")
        if wire.get("route") not in _ROUTES:
            raise ManifestError(f"{case_id}: invalid route")
        if wire.get("auth_class") not in _AUTH_CLASSES:
            raise ManifestError(f"{case_id}: invalid auth_class")
        if not isinstance(wire.get("destination_class"), str):
            raise ManifestError(f"{case_id}: destination_class is required")
        request_count = wire.get("request_count")
        if not isinstance(request_count, int) or isinstance(request_count, bool) or request_count < 0:
            raise ManifestError(f"{case_id}: request_count must be a non-negative integer")
        if not isinstance(wire.get("api_key_source"), str):
            raise ManifestError(f"{case_id}: api_key_source is required")


def _is_hex(value: Any, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    return all(character in "0123456789abcdef" for character in value)


def replay_manifest(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_manifest(manifest)
    cases = {case["id"]: case for case in manifest["cases"]}
    replay = []
    for case_id in REQUIRED_CASE_IDS:
        case = cases[case_id]
        decision = evaluate_inputs(case["inputs"])
        measured = measured_decision(case["wire"])
        if decision["decision"] != measured:
            raise ManifestError(
                f"{case_id}: measured {measured}, evaluator returned {decision['decision']}"
            )
        replay.append({"id": case_id, **decision})
    return replay


def load_manifest(path: str | Path) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot load manifest: {exc}") from exc
    validate_manifest(manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path(__file__).parent
        / "evidence/auth-resolution-sdk-0.2.132-cli-2.1.224.json",
    )
    args = parser.parse_args(argv)
    replay = replay_manifest(load_manifest(args.manifest))
    for row in replay:
        print(f"{row['id']}: {row['decision']} ({len(row['violations'])} violations)")
    print(f"OK: {len(replay)}/{len(REQUIRED_CASE_IDS)} auth-resolution cases replayed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
