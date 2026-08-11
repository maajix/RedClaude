"""Pure, offline assessment of version-bound credential vectors.

The runtime launch module uses the same registry in later startup phases.  This
module deliberately has no SDK, environment, home-directory or network access:
it only assesses the symbolic inputs in the sanitised evidence manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from importlib import resources
from typing import Any


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
KNOWN_RUNTIME = ("0.2.132", "2.1.224")

CREDENTIAL_VECTORS = (
    ("ANTHROPIC_API_KEY", "off_subscription_auth"),
    ("ANTHROPIC_AUTH_TOKEN", "off_subscription_auth"),
    ("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR", "startup_denial"),
    ("CLAUDE_CODE_USE_BEDROCK", "provider_reroute"),
    ("CLAUDE_CODE_USE_VERTEX", "provider_reroute"),
    ("CLAUDE_CODE_USE_FOUNDRY", "provider_reroute"),
    ("ANTHROPIC_BASE_URL", "destination_override"),
    ("apiKeyHelper", "off_subscription_auth"),
)
WATCHED_ENV_VECTORS = tuple(vector for vector, _effect in CREDENTIAL_VECTORS[:-1])

_EFFECT_BY_VECTOR = dict(CREDENTIAL_VECTORS)
_VECTOR_ORDER = {vector: index for index, (vector, _effect) in enumerate(CREDENTIAL_VECTORS)}
_SETTING_KINDS = frozenset({"managed", "explicit", "user", "project", "local"})
_ROUTES = frozenset({"anthropic_first_party", "other", "none"})
_AUTH_CLASSES = frozenset({"subscription_oauth", "api_key", "other_bearer", "none"})
_EVIDENCE_RESOURCE = "evidence/auth-resolution-sdk-0.2.132-cli-2.1.224.json"
_EVIDENCE_SHA256 = "ad6c66a24d89802034b7ee15f21b6833ce78e577b316f498de4b7e966e882a2b"


class EvidenceError(ValueError):
    """The publishable auth-resolution evidence cannot ground a verdict."""


def _violation(vector: str, source: str) -> dict[str, str]:
    return {
        "code": "credential_vector",
        "vector": vector,
        "source": source,
        "effect": _EFFECT_BY_VECTOR[vector],
    }


def _active(vector: str, value: Any) -> bool:
    if not isinstance(value, str):
        raise EvidenceError(f"symbolic value for {vector} must be a string")
    return value != "" if vector == "ANTHROPIC_API_KEY" else True


def _evaluate_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Assess symbolic launch inputs without consulting ambient process state."""
    if not isinstance(inputs, Mapping):
        raise EvidenceError("case inputs must be an object")
    environment = inputs.get("environment", {})
    settings = inputs.get("settings", [])
    setting_sources = inputs.get("setting_sources", [])
    if not isinstance(environment, Mapping):
        raise EvidenceError("inputs.environment must be an object")
    if not isinstance(settings, list):
        raise EvidenceError("inputs.settings must be an array")
    if not isinstance(setting_sources, list) or not all(
        isinstance(source, str) for source in setting_sources
    ):
        raise EvidenceError("inputs.setting_sources must be an array of strings")

    violations = []
    for vector in WATCHED_ENV_VECTORS:
        if vector in environment and _active(vector, environment[vector]):
            violations.append(_violation(vector, f"env:{vector}"))

    selected_sources = set(setting_sources)
    for setting in settings:
        if not isinstance(setting, Mapping):
            raise EvidenceError("each symbolic setting must be an object")
        kind = setting.get("kind")
        path = setting.get("path")
        document = setting.get("document")
        if kind not in _SETTING_KINDS or not isinstance(path, str) or not path:
            raise EvidenceError("each symbolic setting needs a known kind and path")
        if not isinstance(document, Mapping):
            raise EvidenceError("each symbolic setting document must be an object")
        if kind not in {"managed", "explicit"} and kind not in selected_sources:
            continue

        source_prefix = f"settings:{kind}:{path}#"
        if "apiKeyHelper" in document:
            violations.append(_violation("apiKeyHelper", source_prefix + "apiKeyHelper"))
        settings_environment = document.get("env", {})
        if not isinstance(settings_environment, Mapping):
            raise EvidenceError("a symbolic settings env member must be an object")
        for vector in WATCHED_ENV_VECTORS:
            if vector in settings_environment and _active(
                vector, settings_environment[vector]
            ):
                violations.append(_violation(vector, source_prefix + f"env.{vector}"))

    violations.sort(key=lambda item: (_VECTOR_ORDER[item["vector"]], item["source"]))
    return {"decision": "refuse" if violations else "allow", "violations": violations}


def _measured_decision(wire: Mapping[str, Any]) -> str:
    """Derive allow/refuse solely from the normalised facts measured on the wire."""
    if not isinstance(wire, Mapping):
        raise EvidenceError("case wire facts must be an object")
    return (
        "allow"
        if wire.get("route") == "anthropic_first_party"
        and wire.get("auth_class") == "subscription_oauth"
        and wire.get("destination_class") == "anthropic_api"
        and isinstance(wire.get("request_count"), int)
        and not isinstance(wire["request_count"], bool)
        and wire["request_count"] > 0
        else "refuse"
    )


def _case_set(cases: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(cases, list):
        raise EvidenceError("manifest cases must be an array")
    ids = [case.get("id") if isinstance(case, Mapping) else None for case in cases]
    counts = Counter(ids)
    expected = set(REQUIRED_CASE_IDS)
    missing = [case_id for case_id in REQUIRED_CASE_IDS if counts[case_id] == 0]
    duplicate = sorted(str(case_id) for case_id, count in counts.items() if count > 1)
    additional = sorted(str(case_id) for case_id in counts if case_id not in expected)
    if missing or duplicate or additional:
        raise EvidenceError(
            "case set mismatch: "
            f"missing={missing}, duplicate={duplicate}, additional={additional}"
        )
    return {str(case["id"]): case for case in cases}


def _is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_manifest(manifest: Any) -> Mapping[str, Any]:
    if not isinstance(manifest, Mapping):
        raise EvidenceError("manifest must be an object")
    cases = _case_set(manifest.get("cases"))

    if manifest.get("schema_version") != 1:
        raise EvidenceError("unsupported manifest schema_version")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, Mapping) or not all(
        isinstance(runtime.get(key), str) and runtime[key]
        for key in ("sdk_version", "bundled_cli_version")
    ):
        raise EvidenceError("manifest runtime versions are required")
    if (runtime["sdk_version"], runtime["bundled_cli_version"]) != KNOWN_RUNTIME:
        raise EvidenceError("manifest runtime pair is not the measured pair")
    probe = manifest.get("probe")
    retained = probe.get("retained_capture") if isinstance(probe, Mapping) else None
    if not isinstance(probe, Mapping) or not _is_hex(probe.get("commit"), 40):
        raise EvidenceError("manifest probe commit must be a full git sha")
    if not isinstance(retained, Mapping) or retained.get("algorithm") != "sha256":
        raise EvidenceError("manifest retained capture must use sha256")
    if (
        not _is_hex(retained.get("digest"), 64)
        or not isinstance(retained.get("members"), int)
        or isinstance(retained["members"], bool)
        or retained["members"] < 1
    ):
        raise EvidenceError("manifest retained capture metadata is invalid")

    for case_id in REQUIRED_CASE_IDS:
        case = cases[case_id]
        _evaluate_inputs(case.get("inputs"))
        wire = case.get("wire")
        if not isinstance(wire, Mapping):
            raise EvidenceError(f"{case_id}: wire facts must be an object")
        if wire.get("route") not in _ROUTES:
            raise EvidenceError(f"{case_id}: invalid route")
        if wire.get("auth_class") not in _AUTH_CLASSES:
            raise EvidenceError(f"{case_id}: invalid auth_class")
        if not isinstance(wire.get("destination_class"), str):
            raise EvidenceError(f"{case_id}: destination_class is required")
        request_count = wire.get("request_count")
        if (
            not isinstance(request_count, int)
            or isinstance(request_count, bool)
            or request_count < 0
        ):
            raise EvidenceError(f"{case_id}: request_count must be a non-negative integer")
        if not isinstance(wire.get("api_key_source"), str):
            raise EvidenceError(f"{case_id}: api_key_source is required")
    return manifest


def _load_evidence() -> Mapping[str, Any]:
    data = resources.files(__package__).joinpath(_EVIDENCE_RESOURCE).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != _EVIDENCE_SHA256:
        raise EvidenceError(f"auth-resolution evidence digest changed: {digest}")
    try:
        manifest = json.loads(data)
    except json.JSONDecodeError as error:
        raise EvidenceError(f"auth-resolution evidence is not JSON: {error}") from error
    return _validate_manifest(manifest)


def replay_auth_resolution() -> list[dict[str, Any]]:
    """Replay the complete checked-in measurement matrix in its canonical order."""
    manifest = _load_evidence()
    cases = {case["id"]: case for case in manifest["cases"]}
    replay = []
    for case_id in REQUIRED_CASE_IDS:
        case = cases[case_id]
        decision = _evaluate_inputs(case["inputs"])
        measured = _measured_decision(case["wire"])
        if decision["decision"] != measured:
            raise EvidenceError(
                f"{case_id}: measured {measured}, evaluator returned {decision['decision']}"
            )
        replay.append({"id": case_id, **decision})
    return replay
