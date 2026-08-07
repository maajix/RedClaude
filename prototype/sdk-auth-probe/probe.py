"""Ticket 21 probe driver: which credential does the SDK-spawned CLI actually use?

PROTOTYPE - throwaway.

For each credential vector, spawn one SDK run in a scrubbed environment whose
HTTPS traffic is intercepted by fake_upstream.py, then read back which
credential reached the wire. Identification is by sha256[:12] of the secret:
every vector carries its own distinct fake value, and the operator's real OAuth
token has a fingerprint of its own, so the winner is never ambiguous.

No working API key is used anywhere, and no request leaves the machine.

    .venv/bin/python probe.py [vector-id ...]
"""

import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).parent
OUT = HERE / "out"
VENV_PY = HERE / ".venv/bin/python"
# Per-invocation: two probe drivers running at once would otherwise interleave
# their wire captures into one file and cross-attribute credentials.
CAPTURE = OUT / f"capture-{os.getpid()}.jsonl"
MITM_CONF = OUT / "mitm-conf"
PROXY_PORT = 8899
PROMPT = "Reply with exactly: PROBE_OK"

# Deliberately unusable. Shaped like the real thing so no format check short
# circuits the resolution being measured.
FAKE = {
    "env_api_key": "sk-ant-api03-PROBEenvkey" + "0" * 74 + "AA",
    "env_auth_token": "sk-ant-oat01-PROBEauthtoken" + "0" * 70 + "AA",
    "helper_key": "sk-ant-api03-PROBEhelperkey" + "0" * 71 + "AA",
    "fd_key": "sk-ant-api03-PROBEfdkey" + "0" * 75 + "AA",
    "proj_helper_key": "sk-ant-api03-PROBEprojhelper" + "0" * 70 + "AA",
    "settings_env_key": "sk-ant-api03-PROBEsettingsenv" + "0" * 69 + "AA",
}


def sha12(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def credential_names() -> dict[str, str]:
    """sha12 -> human name, including the operator's real OAuth token."""
    names = {sha12(v): k for k, v in FAKE.items()}
    creds = pathlib.Path.home() / ".claude/.credentials.json"
    if creds.exists():
        oauth = json.loads(creds.read_text()).get("claudeAiOauth", {})
        for field in ("accessToken", "refreshToken"):
            if oauth.get(field):
                names[sha12(oauth[field])] = f"oauth_{field}"
    return names


def helper_script() -> str:
    path = OUT / "probe-api-key-helper.sh"
    path.write_text(f"#!/bin/sh\nprintf %s '{FAKE['helper_key']}'\n")
    path.chmod(0o755)
    return str(path)


def settings_file(name: str, body: dict) -> str:
    path = OUT / f"settings-{name}.json"
    path.write_text(json.dumps(body))
    return str(path)


def project_dir() -> str:
    """A working directory carrying a project-level apiKeyHelper in .claude/.

    This is the vector the harness cannot control by scrubbing its own env: a
    settings file it never wrote, in a directory it was pointed at.
    """
    path = OUT / "projdir"
    helper = OUT / "probe-project-helper.sh"
    helper.write_text(f"#!/bin/sh\nprintf %s '{FAKE['proj_helper_key']}'\n")
    helper.chmod(0o755)
    (path / ".claude").mkdir(parents=True, exist_ok=True)
    (path / ".claude/settings.json").write_text(json.dumps({"apiKeyHelper": str(helper)}))
    return str(path)


def vectors() -> list[dict]:
    """id, env delta, optional settings file, optional fd secret, what it tests."""
    helper = helper_script()
    return [
        {"id": "baseline", "env": {}, "note": "no credential vector set"},
        {"id": "api_key", "env": {"ANTHROPIC_API_KEY": FAKE["env_api_key"]}},
        {"id": "auth_token", "env": {"ANTHROPIC_AUTH_TOKEN": FAKE["env_auth_token"]}},
        # Can the harness neutralise an inherited key by blanking it, or does
        # an empty value still count as set? Decides whether the assertion
        # tests presence or truthiness.
        {"id": "api_key_empty", "env": {"ANTHROPIC_API_KEY": ""}},
        # Not a billing vector, but the same silent-redirect shape: does the
        # OAuth token get sent to whatever host ANTHROPIC_BASE_URL names?
        {"id": "base_url", "env": {"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{PROXY_PORT}"}},
        {
            "id": "api_key_helper",
            "env": {},
            "settings": settings_file("helper", {"apiKeyHelper": helper}),
        },
        {"id": "fd", "env": {}, "fd_secret": FAKE["fd_key"]},
        # These three reach for a cloud provider's own credential chain, which
        # can sit on a long timeout of its own; 45s is enough to see the choice.
        {"id": "bedrock", "env": {"CLAUDE_CODE_USE_BEDROCK": "1"}, "timeout_s": 45},
        {"id": "vertex", "env": {"CLAUDE_CODE_USE_VERTEX": "1"}, "timeout_s": 45},
        {"id": "foundry", "env": {"CLAUDE_CODE_USE_FOUNDRY": "1"}, "timeout_s": 45},
        # A settings file can carry an env block. If that block is applied
        # before auth resolution, "scan settings for apiKeyHelper" is not
        # enough - a settings file can set ANTHROPIC_API_KEY itself.
        {
            "id": "settings_env_key",
            "env": {},
            "settings": settings_file(
                "envblock", {"env": {"ANTHROPIC_API_KEY": FAKE["settings_env_key"]}}
            ),
        },
        # Does SDK isolation mode (setting_sources=[]) keep a settings file the
        # harness did not write out of the auth path?
        {"id": "proj_helper_isolated", "env": {}, "cwd": project_dir(), "setting_sources": []},
        {
            "id": "proj_helper_loaded",
            "env": {},
            "cwd": project_dir(),
            "setting_sources": ["project"],
        },
        # Precedence: which one wins when two are set at once.
        {
            "id": "prec_key_vs_token",
            "env": {
                "ANTHROPIC_API_KEY": FAKE["env_api_key"],
                "ANTHROPIC_AUTH_TOKEN": FAKE["env_auth_token"],
            },
        },
        {
            "id": "prec_key_vs_helper",
            "env": {"ANTHROPIC_API_KEY": FAKE["env_api_key"]},
            "settings": settings_file("helper", {"apiKeyHelper": helper}),
        },
        {
            "id": "prec_token_vs_helper",
            "env": {"ANTHROPIC_AUTH_TOKEN": FAKE["env_auth_token"]},
            "settings": settings_file("helper", {"apiKeyHelper": helper}),
        },
        {
            "id": "prec_key_vs_bedrock",
            "env": {
                "ANTHROPIC_API_KEY": FAKE["env_api_key"],
                "CLAUDE_CODE_USE_BEDROCK": "1",
            },
        },
    ]


def scrubbed_env(ca_pem: str) -> dict:
    """A known-clean base env: nothing ANTHROPIC_*/CLAUDE_* survives from this shell."""
    keep = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "XDG_RUNTIME_DIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(
        {
            "TERM": "dumb",
            "HTTPS_PROXY": f"http://127.0.0.1:{PROXY_PORT}",
            "HTTP_PROXY": f"http://127.0.0.1:{PROXY_PORT}",
            "NO_PROXY": "",
            "SSL_CERT_FILE": ca_pem,
            "NODE_EXTRA_CA_CERTS": ca_pem,
            "REQUESTS_CA_BUNDLE": ca_pem,
            "CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK": "1",
        }
    )
    return env


def start_proxy() -> subprocess.Popen:
    MITM_CONF.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PROBE_CAPTURE=str(CAPTURE))
    proc = subprocess.Popen(
        [
            shutil.which("mitmdump"),
            "-q",
            "-s",
            str(HERE / "fake_upstream.py"),
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(PROXY_PORT),
            "--set",
            f"confdir={MITM_CONF}",
            "--set",
            "connection_strategy=lazy",
        ],
        cwd=HERE,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(120):
        try:
            socket.create_connection(("127.0.0.1", PROXY_PORT), 0.5).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                raise SystemExit(f"mitmdump died: {proc.stderr.read().decode()[:2000]}")
            time.sleep(0.25)
    raise SystemExit("mitmdump never listened")


def marker(text: str) -> None:
    with CAPTURE.open("a") as fh:
        fh.write(json.dumps({"marker": text}) + "\n")


def read_capture() -> list[dict]:
    if not CAPTURE.exists():
        return []
    return [json.loads(line) for line in CAPTURE.read_text().splitlines() if line.strip()]


def events_after(events: list[dict], run_id: str) -> list[dict]:
    out, seen = [], False
    for event in events:
        if event.get("marker") == run_id:
            seen = True
            continue
        if seen:
            if "marker" in event:
                break
            out.append(event)
    return out


def classify(events: list[dict], names: dict[str, str]) -> dict:
    hosts, creds = [], []
    for event in events:
        if event["host"] not in hosts:
            hosts.append(event["host"])
        for header, fp in event.get("credential_headers", {}).items():
            entry = {
                "header": header,
                "scheme": fp["scheme"],
                "credential": names.get(fp["sha12"], f"unknown:{fp['sha12']}"),
            }
            if entry not in creds:
                creds.append(entry)
    return {"hosts": hosts, "credentials": creds, "requests": len(events)}


def run_vector(vector: dict, base_env: dict, names: dict) -> dict:
    job = {
        "prompt": PROMPT,
        "cwd": vector.get("cwd", str(HERE)),
        "timeout_s": vector.get("timeout_s", 90),
        "settings_path": vector.get("settings"),
        "fd_secret": vector.get("fd_secret"),
        "setting_sources": vector.get("setting_sources", []),
    }
    env = dict(base_env, **vector["env"])
    marker(vector["id"])
    started = time.monotonic()
    proc = subprocess.run(
        [str(VENV_PY), str(HERE / "runner.py"), json.dumps(job)],
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    try:
        run = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        run = {"error": {"class": "RunnerCrash", "message": proc.stderr[-2000:]}, "messages": []}

    observed = classify(events_after(read_capture(), vector["id"]), names)
    return {
        "id": vector["id"],
        "env_keys": sorted(vector["env"]),
        "settings": bool(vector.get("settings")),
        "fd": bool(vector.get("fd_secret")),
        "wall_s": round(time.monotonic() - started, 1),
        "observed": observed,
        "result": summarize(run),
        "raw": run,
    }


def summarize(run: dict) -> dict:
    system_init = next(
        (m["value"] for m in run["messages"] if m["class"] == "SystemMessage" and m["value"].get("subtype") == "init"),
        None,
    )
    result = next((m["value"] for m in run["messages"] if m["class"] == "ResultMessage"), None)
    text = " ".join(
        block.get("text", "")
        for m in run["messages"]
        if m["class"] == "AssistantMessage"
        for block in m["value"].get("content", [])
    ).strip()
    return {
        "error": run.get("error"),
        "text": text[:200],
        "result_subtype": (result or {}).get("subtype"),
        "is_error": (result or {}).get("is_error"),
        "total_cost_usd": (result or {}).get("total_cost_usd"),
        "init_keys": sorted((system_init or {}).get("data", {})) if system_init else None,
        "auth_fields": {
            k: v
            for k, v in ((system_init or {}).get("data", {})).items()
            if any(word in k.lower() for word in ("key", "auth", "credential", "oauth", "source", "account"))
        },
        "stderr_tail": run.get("stderr", [])[-6:],
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    CAPTURE.unlink(missing_ok=True)
    wanted = set(sys.argv[1:])
    chosen = [v for v in vectors() if not wanted or v["id"] in wanted]
    names = credential_names()

    proxy = start_proxy()
    ca_pem = str(MITM_CONF / "mitmproxy-ca-cert.pem")
    base_env = scrubbed_env(ca_pem)
    results = []
    try:
        for vector in chosen:
            print(f"--- {vector['id']}", flush=True)
            results.append(run_vector(vector, base_env, names))
            print(json.dumps(results[-1]["observed"]), flush=True)
            print(json.dumps(results[-1]["result"])[:600], flush=True)
    finally:
        proxy.terminate()

    versions = subprocess.run(
        [str(VENV_PY), "-c", "import importlib.metadata as m, claude_agent_sdk._cli_version as c;"
         "print(m.version('claude-agent-sdk'), c.__cli_version__)"],
        capture_output=True,
        text=True,
    ).stdout.split()
    payload = {
        "sdk_version": versions[0] if versions else None,
        "bundled_cli_version": versions[1] if len(versions) > 1 else None,
        "results": results,
    }
    # One file per batch: the matrix is long enough that it is run in pieces,
    # and a shared filename would erase the previous piece.
    batch = "_".join(v["id"] for v in chosen) if wanted else "all"
    target = OUT / f"results-{batch}.json"
    target.write_text(json.dumps(payload, indent=2))
    shutil.copy(CAPTURE, OUT / f"capture-{batch}.jsonl")
    print(f"\nwrote {target}")


if __name__ == "__main__":
    main()
