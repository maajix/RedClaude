"""Run the reference assertion against every measured vector. Ticket 21.

PROTOTYPE - throwaway.

The probe measured, for each credential vector, which credential actually
reached POST /v1/messages. This replays those same vector definitions past
subscription_guard and checks the guard's verdict against what the wire showed:

    guard raises  <=>  the inference call did NOT go out on the subscription

No SDK runs, no network: it reads probe.vectors() for the inputs and the
capture files for the ground truth, so the assertion is tested against
measurement rather than against my reading of the CLI.

    .venv/bin/python verify_guard.py
"""

import json
import pathlib
import sys

import probe
import subscription_guard as guard

OUT = probe.OUT
FD_NUMBER_IN_PROBE = "4"  # runner.py opened the pipe as fd 4; any value is "set"


def ground_truth() -> dict[str, dict]:
    """Per vector: did the inference call go out on the subscription?

    True only if a POST /v1/messages reached api.anthropic.com carrying the
    real OAuth bearer token and nothing else. A vector that never got that far
    (cloud providers, the fd vector) is not on the subscription either - it
    either billed elsewhere or did not run.
    """
    names = probe.credential_names()
    truth: dict[str, dict] = {}
    current = None
    for path in sorted(OUT.glob("capture-*.jsonl")):
        if path.name == "capture-all.jsonl" and len(list(OUT.glob("capture-*.jsonl"))) > 1:
            pass  # capture-all.jsonl holds the full matrix; per-batch files add the rest
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("marker"):
                current = event["marker"]
                truth.setdefault(current, {"inference_calls": [], "source": path.name})
                continue
            if current is None or "/v1/messages" not in event.get("path", ""):
                continue
            creds = {
                names.get(f["sha12"], f["sha12"][:8])
                for f in (event.get("credential_headers") or {}).values()
            }
            truth[current]["inference_calls"].append(
                {"host": event["host"], "credentials": sorted(creds)}
            )

    for entry in truth.values():
        calls = entry["inference_calls"]
        entry["on_subscription"] = bool(calls) and all(
            call["host"] == "api.anthropic.com" and call["credentials"] == ["oauth_accessToken"]
            for call in calls
        )
    return truth


def measured_api_key_source() -> dict[str, str | None]:
    sources = {}
    for path in sorted(OUT.glob("results-*.json")):
        for entry in json.loads(path.read_text())["results"]:
            sources[entry["id"]] = entry["result"]["auth_fields"].get("apiKeySource")
    return sources


def guard_verdict(vector: dict) -> str | None:
    """None if the guard would let this run start, else the refusal reason."""
    env = dict(vector.get("env") or {})
    if vector.get("fd_secret"):
        env["CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"] = FD_NUMBER_IN_PROBE
    try:
        guard.assert_environment(
            env=env,
            cwd=vector.get("cwd", probe.HERE),
            setting_sources=vector.get("setting_sources", []),
            settings_path=vector.get("settings"),
        )
    except guard.SubscriptionViolation as exc:
        return str(exc)
    return None


def main() -> int:
    truth = ground_truth()
    sources = measured_api_key_source()
    failures = []

    print(f"{'vector':22} {'measured':12} {'guard':8} {'apiKeySource':18} verdict")
    for vector in probe.vectors():
        vid = vector["id"]
        if vid not in truth:
            print(f"{vid:22} {'NOT MEASURED':12} - skipped")
            failures.append(f"{vid}: no capture data")
            continue
        on_sub = truth[vid]["on_subscription"]
        reason = guard_verdict(vector)
        allowed = reason is None
        ok = allowed == on_sub
        if not ok:
            failures.append(
                f"{vid}: wire said on_subscription={on_sub}, guard "
                f"{'allowed' if allowed else 'refused'}"
            )
        print(
            f"{vid:22} {'subscription' if on_sub else 'OFF':12} "
            f"{'allow' if allowed else 'refuse':8} {str(sources.get(vid)):18} "
            f"{'ok' if ok else 'MISMATCH'}"
        )

    # The runtime's own report, checked separately: it is a supplement, and the
    # vectors it misses are part of the finding, so they are asserted too.
    print("\napiKeySource coverage (assert_init_message alone):")
    expected_blind = {"auth_token", "fd", "bedrock", "vertex", "foundry", "base_url"}
    for vid, source in sorted(sources.items()):
        if vid not in truth:
            continue
        on_sub = truth[vid]["on_subscription"]
        try:
            guard.assert_init_message({"apiKeySource": source})
            caught = False
        except guard.SubscriptionViolation:
            caught = True
        blind = (not on_sub) and not caught
        if blind != (vid in expected_blind):
            failures.append(f"{vid}: apiKeySource blind-spot changed (blind={blind})")
        if blind:
            print(f"  {vid:22} MISSED by apiKeySource={source!r} (env check is what catches it)")

    # Fail closed on an untested runtime.
    versions = json.loads((OUT / "results-all.json").read_text())
    guard.assert_runtime_known(versions["sdk_version"], versions["bundled_cli_version"])
    try:
        guard.assert_runtime_known(versions["sdk_version"], "9.9.9")
        failures.append("assert_runtime_known accepted an untested CLI version")
    except guard.SubscriptionViolation:
        pass
    print(
        f"\nruntime gate: SDK {versions['sdk_version']} / CLI "
        f"{versions['bundled_cli_version']} accepted, CLI 9.9.9 refused"
    )

    if failures:
        print("\nFAILED:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("\nOK: guard verdict matches the wire on every measured vector")
    return 0


if __name__ == "__main__":
    sys.exit(main())
