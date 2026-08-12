"""Pure, offline assessment of version-bound credential vectors.

The runtime launch module uses the same registry in later startup phases.  This
module deliberately has no SDK, environment, home-directory or network access:
it only assesses the symbolic inputs in the sanitised measurement manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class _VectorRule:
    name: str
    effect: str
    measurement_case: str
    empty_is_unset: bool = False


_VECTOR_RULES = (
    _VectorRule("ANTHROPIC_API_KEY", "off_subscription_auth", "api_key", True),
    _VectorRule("ANTHROPIC_AUTH_TOKEN", "off_subscription_auth", "auth_token"),
    _VectorRule("CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR", "startup_denial", "fd"),
    _VectorRule("CLAUDE_CODE_USE_BEDROCK", "provider_reroute", "bedrock"),
    _VectorRule("CLAUDE_CODE_USE_VERTEX", "provider_reroute", "vertex"),
    _VectorRule("CLAUDE_CODE_USE_FOUNDRY", "provider_reroute", "foundry"),
    _VectorRule("ANTHROPIC_BASE_URL", "destination_override", "base_url"),
    _VectorRule("apiKeyHelper", "off_subscription_auth", "api_key_helper"),
)
_ENV_VECTOR_RULES = _VECTOR_RULES[:-1]
_HELPER_RULE = _VECTOR_RULES[-1]
WATCHED_ENV_VECTORS = tuple(rule.name for rule in _ENV_VECTOR_RULES)

#: The keys every refusal this runtime raises carries: the ones minted here from
#: the measured matrix, and the ones `agent` mints for what it could not measure
#: at all. Stated once, because two modules shaping a refusal differently is an
#: operator rendering the same finding two ways.
VIOLATION_KEYS = frozenset({"code", "vector", "source", "effect"})

_VECTOR_ORDER = {rule.name: index for index, rule in enumerate(_VECTOR_RULES)}
_SETTING_KINDS = frozenset({"managed", "explicit", "user", "project", "local"})
_ROUTES = frozenset({"anthropic_first_party", "other", "none"})
_AUTH_CLASSES = frozenset({"subscription_oauth", "api_key", "other_bearer", "none"})
_MANIFEST_RESOURCE = "measurements/auth-resolution-sdk-0.2.132-cli-2.1.224.json"
_MANIFEST_SHA256 = "ad6c66a24d89802034b7ee15f21b6833ce78e577b316f498de4b7e966e882a2b"


class ManifestError(ValueError):
    """The auth-resolution measurement manifest cannot ground a verdict."""


def _violation(rule: _VectorRule, source: str) -> dict[str, str]:
    return {
        "code": "credential_vector",
        "vector": rule.name,
        "source": source,
        "effect": rule.effect,
    }


def _active(rule: _VectorRule, value: Any) -> bool:
    if not isinstance(value, str):
        raise ManifestError(f"symbolic value for {rule.name} must be a string")
    return value != "" if rule.empty_is_unset else True


def _environment_violations(
    environment: Mapping[str, Any], source_prefix: str
) -> list[dict[str, str]]:
    violations = []
    for rule in _ENV_VECTOR_RULES:
        if rule.name in environment and _active(rule, environment[rule.name]):
            violations.append(_violation(rule, source_prefix + rule.name))
    return violations


def evaluate_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Assess symbolic launch inputs without consulting ambient process state."""
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

    violations = _environment_violations(environment, "env:")

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

        source_prefix = f"settings:{kind}:{path}#"
        if "apiKeyHelper" in document:
            violations.append(_violation(_HELPER_RULE, source_prefix + "apiKeyHelper"))
        settings_environment = document.get("env", {})
        if not isinstance(settings_environment, Mapping):
            raise ManifestError("a symbolic settings env member must be an object")
        violations.extend(_environment_violations(settings_environment, source_prefix + "env."))

    violations.sort(key=lambda item: (_VECTOR_ORDER[item["vector"]], item["source"]))
    return {"decision": "refuse" if violations else "allow", "violations": violations}


def _is_positive_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _measured_decision(wire: Mapping[str, Any]) -> str:
    """Derive allow/refuse solely from the normalised facts measured on the wire."""
    if not isinstance(wire, Mapping):
        raise ManifestError("case wire facts must be an object")
    return (
        "allow"
        if wire.get("route") == "anthropic_first_party"
        and wire.get("auth_class") == "subscription_oauth"
        and wire.get("destination_class") == "anthropic_api"
        and _is_positive_count(wire.get("request_count"))
        else "refuse"
    )


def _wire_effects(wire: Mapping[str, Any]) -> frozenset[str]:
    """Effects consistent with one normalised, non-subscription wire outcome."""
    route = wire.get("route")
    auth_class = wire.get("auth_class")
    destination = wire.get("destination_class")
    request_count = wire.get("request_count")
    if (
        route == "anthropic_first_party"
        and auth_class in {"api_key", "other_bearer"}
        and destination == "anthropic_api"
        and _is_positive_count(request_count)
    ):
        return frozenset({"off_subscription_auth"})
    if (
        route == "other"
        and auth_class == "subscription_oauth"
        and destination == "loopback"
        and _is_positive_count(request_count)
    ):
        return frozenset({"destination_override"})
    if (
        route == "other"
        and auth_class == "none"
        and destination == "gcp_metadata"
        and _is_positive_count(request_count)
    ):
        return frozenset({"provider_reroute"})
    if (
        route == "none"
        and auth_class == "none"
        and destination == "none"
        and request_count == 0
    ):
        # These measured inputs share an observable shape: the file
        # descriptor stopped startup, while Bedrock and Foundry selected a
        # provider without contacting an endpoint captured by the probe.
        return frozenset({"startup_denial", "provider_reroute"})
    return frozenset()


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


def _is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_manifest(manifest: Any) -> Mapping[str, Any]:
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
    if (runtime["sdk_version"], runtime["bundled_cli_version"]) != KNOWN_RUNTIME:
        raise ManifestError("manifest runtime pair is not the measured pair")
    probe = manifest.get("probe")
    retained = probe.get("retained_capture") if isinstance(probe, Mapping) else None
    if not isinstance(probe, Mapping) or not _is_hex(probe.get("commit"), 40):
        raise ManifestError("manifest probe commit must be a full git sha")
    if not isinstance(retained, Mapping) or retained.get("algorithm") != "sha256":
        raise ManifestError("manifest retained capture must use sha256")
    if (
        not _is_hex(retained.get("digest"), 64)
        or not isinstance(retained.get("members"), int)
        or isinstance(retained["members"], bool)
        or retained["members"] < 1
    ):
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
        if (
            not isinstance(request_count, int)
            or isinstance(request_count, bool)
            or request_count < 0
        ):
            raise ManifestError(f"{case_id}: request_count must be a non-negative integer")
        if not isinstance(wire.get("api_key_source"), str):
            raise ManifestError(f"{case_id}: api_key_source is required")
    return manifest


def _load_manifest() -> Mapping[str, Any]:
    data = resources.files(__package__).joinpath(_MANIFEST_RESOURCE).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != _MANIFEST_SHA256:
        raise ManifestError(f"auth-resolution manifest digest changed: {digest}")
    try:
        manifest = json.loads(data)
    except json.JSONDecodeError as error:
        raise ManifestError(f"auth-resolution manifest is not JSON: {error}") from error
    return _validate_manifest(manifest)


def _replay_manifest(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = _validate_manifest(manifest)
    cases = {case["id"]: case for case in manifest["cases"]}
    measured_effects = {}
    for rule in _VECTOR_RULES:
        wire_effects = _wire_effects(cases[rule.measurement_case]["wire"])
        if rule.effect not in wire_effects:
            raise ManifestError(
                f"{rule.measurement_case}: wire outcome does not measure {rule.effect}"
            )
        measured_effects[rule.name] = rule.effect

    replay = []
    for case_id in REQUIRED_CASE_IDS:
        case = cases[case_id]
        decision = evaluate_inputs(case["inputs"])
        measured = _measured_decision(case["wire"])
        if decision["decision"] != measured:
            raise ManifestError(
                f"{case_id}: measured {measured}, evaluator returned {decision['decision']}"
            )
        for violation in decision["violations"]:
            if violation["effect"] != measured_effects[violation["vector"]]:
                raise ManifestError(
                    f"{case_id}: evaluator effect for {violation['vector']} "
                    "differs from its measured wire outcome"
                )
        replay.append({"id": case_id, **decision})
    return replay


def replay_auth_resolution() -> list[dict[str, Any]]:
    """Replay the complete checked-in measurement matrix in its canonical order."""
    return _replay_manifest(_load_manifest())
