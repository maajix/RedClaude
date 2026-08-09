"""Operator tool: turn explicit probe result/capture pairs into a safe manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import auth_resolution as auth
import probe


def _symbolic_document(document: dict[str, Any]) -> dict[str, Any]:
    unknown = set(document) - {"apiKeyHelper", "env"}
    if unknown:
        raise ValueError(f"refusing to copy unknown settings keys: {sorted(unknown)}")
    symbolic = {}
    if "apiKeyHelper" in document:
        symbolic["apiKeyHelper"] = "synthetic_helper"
    if "env" in document:
        if not isinstance(document["env"], dict):
            raise ValueError("settings env must be an object")
        symbolic["env"] = {
            name: "" if value == "" else "synthetic_nonempty"
            for name, value in document["env"].items()
        }
    return symbolic


def _symbolic_inputs(vector: dict[str, Any]) -> dict[str, Any]:
    environment = {
        name: "" if value == "" else "synthetic_nonempty"
        for name, value in vector.get("env", {}).items()
    }
    if vector.get("fd_secret"):
        environment["CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"] = "synthetic_nonempty"

    settings = []
    if vector.get("settings"):
        document = json.loads(Path(vector["settings"]).read_text())
        settings.append(
            {
                "kind": "explicit",
                "path": "/fixture/runtime/settings.json",
                "document": _symbolic_document(document),
            }
        )
    if vector.get("cwd") and Path(vector["cwd"]) != probe.HERE:
        project_settings = Path(vector["cwd"]) / ".claude/settings.json"
        settings.append(
            {
                "kind": "project",
                "path": "/fixture/project/.claude/settings.json",
                "document": _symbolic_document(json.loads(project_settings.read_text())),
            }
        )
    return {
        "environment": environment,
        "setting_sources": list(vector.get("setting_sources", [])),
        "settings": settings,
    }


def _read_batches(
    pairs: list[tuple[Path, Path]],
) -> tuple[dict, dict, str, str, str]:
    results = {}
    events = {}
    versions = set()
    digest = hashlib.sha256()

    for result_path, capture_path in sorted(pairs, key=lambda pair: pair[1].name):
        result_document = json.loads(result_path.read_text())
        versions.add(
            (result_document.get("sdk_version"), result_document.get("bundled_cli_version"))
        )
        for result in result_document.get("results", []):
            case_id = result.get("id")
            if case_id in results:
                raise ValueError(f"duplicate result case: {case_id}")
            results[case_id] = result

        current = None
        for line in capture_path.read_text().splitlines():
            event = json.loads(line)
            if "marker" in event:
                current = event["marker"]
                if current in events:
                    raise ValueError(f"duplicate capture case: {current}")
                events[current] = []
            elif current is not None:
                events[current].append(event)

        digest.update(capture_path.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(capture_path.read_bytes()).digest())

    if len(versions) != 1:
        raise ValueError(f"probe batches disagree on runtime: {sorted(versions)}")
    sdk_version, cli_version = versions.pop()
    return results, events, digest.hexdigest(), sdk_version, cli_version


def _wire_facts(vector: dict, result: dict, events: list[dict]) -> dict[str, Any]:
    inference = [event for event in events if "/v1/messages" in event.get("path", "")]
    if inference:
        hosts = {event.get("host") for event in inference}
        route = "anthropic_first_party" if hosts == {"api.anthropic.com"} else "other"
        destination = (
            "anthropic_api"
            if route == "anthropic_first_party"
            else "loopback"
            if hosts <= {"127.0.0.1", "localhost"}
            else "other"
        )
        fake_names = {probe.sha12(value): name for name, value in probe.FAKE.items()}
        credentials = [
            (header.lower(), fake_names.get(fingerprint.get("sha12")))
            for event in inference
            for header, fingerprint in event.get("credential_headers", {}).items()
        ]
        observed_names = {
            item.get("credential") for item in result["observed"].get("credentials", [])
        }
        if any(header == "x-api-key" for header, _ in credentials):
            auth_class = "api_key"
        elif any(name == "env_auth_token" for _, name in credentials):
            auth_class = "other_bearer"
        elif "oauth_accessToken" in observed_names and credentials:
            auth_class = "subscription_oauth"
        else:
            raise ValueError(f"{vector['id']}: cannot classify inference credentials")
        request_count = len(inference)
    else:
        provider_events = [
            event
            for event in events
            if event.get("host") in {"169.254.169.254", "metadata.google.internal."}
        ]
        route = "other" if provider_events else "none"
        destination = "gcp_metadata" if provider_events else "none"
        auth_class = "none"
        request_count = len(provider_events)

    api_key_source = result.get("result", {}).get("auth_fields", {}).get("apiKeySource")
    if not isinstance(api_key_source, str):
        raise ValueError(f"{vector['id']}: missing apiKeySource")
    return {
        "route": route,
        "auth_class": auth_class,
        "destination_class": destination,
        "request_count": request_count,
        "api_key_source": api_key_source,
    }


def build_manifest(pairs: list[tuple[Path, Path]], probe_commit: str) -> dict[str, Any]:
    results, events, digest, sdk_version, cli_version = _read_batches(pairs)
    vectors = {vector["id"]: vector for vector in probe.vectors()}
    cases = []
    for case_id in auth.REQUIRED_CASE_IDS:
        if case_id not in vectors or case_id not in results or case_id not in events:
            raise ValueError(f"missing probe material for {case_id}")
        cases.append(
            {
                "id": case_id,
                "inputs": _symbolic_inputs(vectors[case_id]),
                "wire": _wire_facts(vectors[case_id], results[case_id], events[case_id]),
            }
        )
    manifest = {
        "schema_version": 1,
        "runtime": {
            "sdk_version": sdk_version,
            "bundled_cli_version": cli_version,
        },
        "probe": {
            "commit": probe_commit,
            "retained_capture": {
                "algorithm": "sha256",
                "digest": digest,
                "members": len(pairs),
            },
        },
        "cases": cases,
    }
    auth.replay_manifest(manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-commit", required=True)
    parser.add_argument(
        "--batch",
        action="append",
        nargs=2,
        required=True,
        metavar=("RESULTS_JSON", "CAPTURE_JSONL"),
    )
    args = parser.parse_args(argv)
    pairs = [(Path(result), Path(capture)) for result, capture in args.batch]
    print(json.dumps(build_manifest(pairs, args.probe_commit), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
