"""One `agent_run`, in its own process. Ticket 31.

Separate process for two reasons that are not stylistic:

  * the ticket-21 guard has to run against a *scrubbed* environment, and the
    only way to be certain nothing leaked in is to build the environment from
    an allowlist in the parent and never inherit;
  * a run that must be abortable has to be killable. The abort proof kills this
    pid mid-flight and then asks the event log to rebuild the world.

The model gets three tools and no others. It cannot write to the database: the
`propose_*` tool stages a row in `proposals`, and a separate runtime step
decides whether that proposal becomes state. LLM proposes, runtime commits.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sdk-auth-probe"))

import auth_resolution                       # noqa: E402
import rk                                    # noqa: E402
import subscription_guard as guard           # noqa: E402

import anyio                                 # noqa: E402
import claude_agent_sdk                      # noqa: E402
from claude_agent_sdk import (                # noqa: E402
    AssistantMessage, ClaudeAgentOptions, HookMatcher, ResultMessage,
    SystemMessage, create_sdk_mcp_server, query, tool,
)

JOB: dict = {}
STATE: dict = {
    "turn_input": 0, "turn_output": 0, "turns": 0,
    "tool_runs": [], "receipts": [], "proposals": [],
    "guard": None, "api_key_source": None, "cap_hit": False,
    "denied": [], "gates": [], "parked": [], "must_stop": None,
}
CAPABILITIES: dict[str, str] = {}
INIT_CORROBORATED = False
RT: rk.Runtime | None = None
MANAGED_SETTINGS = tuple(Path(path) for path in guard.MANAGED_SETTINGS)


def _violation(code: str, source: str) -> dict:
    return {"code": code, "vector": None, "source": source,
            "effect": "unverifiable"}


def _runtime_facts() -> dict:
    facts = {"sdk_version": None, "cli_version": None, "cli_path": None}
    try:
        facts["sdk_version"] = importlib.metadata.version("claude-agent-sdk")
    except (importlib.metadata.PackageNotFoundError, ValueError):
        pass
    try:
        from claude_agent_sdk import _cli_version
        facts["cli_version"] = _cli_version.__cli_version__
    except (AttributeError, ImportError):
        pass
    package_file = getattr(claude_agent_sdk, "__file__", None)
    try:
        if package_file:
            facts["cli_path"] = (
                Path(package_file).resolve().parent / "_bundled" / "claude"
            )
    except (OSError, TypeError, ValueError):
        pass
    return facts


def _read_settings(path: Path, kind: str):
    source = f"settings:{kind}:{path}#document"
    try:
        document = json.loads(path.read_text())
    except (OSError, ValueError):
        return None, _violation("settings_unreadable", source)
    if not isinstance(document, dict) or not isinstance(document.get("env", {}), dict):
        return None, _violation("settings_unreadable", source)
    return {"kind": kind, "path": str(path), "document": document}, None


def _assess_launch(options, environment, runtime, *, managed_settings=None,
                   runtime_dir: Path | None = None) -> tuple[dict, ...]:
    runtime_dir = Path(
        runtime_dir or JOB.get("launch_dir") or getattr(options, "cwd", "")
    ).resolve()
    managed_settings = MANAGED_SETTINGS if managed_settings is None else managed_settings
    other = []

    pair = (runtime.get("sdk_version"), runtime.get("cli_version"))
    runtime_unmeasured = pair not in guard.KNOWN_RUNTIMES

    runtime_cli = runtime.get("cli_path")
    try:
        expected_cli = Path(runtime_cli).resolve() if runtime_cli is not None else None
    except (OSError, TypeError, ValueError):
        expected_cli = None
    if (expected_cli is None or not expected_cli.is_file()
            or not os.access(expected_cli, os.X_OK)):
        runtime_unmeasured = True
    if runtime_unmeasured:
        other.append(_violation("unmeasured_runtime", "runtime:sdk-cli"))

    checks = {
        "env": getattr(options, "env", None) == {},
        "setting_sources": getattr(options, "setting_sources", None) == [],
        "sandbox": getattr(options, "sandbox", "missing") is None,
        "cwd": getattr(options, "cwd", None) == str(runtime_dir),
        "cli_path": expected_cli is not None
        and getattr(options, "cli_path", None) == str(expected_cli),
    }
    if not runtime_dir.is_dir():
        checks["cwd"] = False
    for field, valid in checks.items():
        if not valid:
            other.append(_violation(
                "invalid_launch", f"launch:{field}"
            ))

    symbolic_settings = []
    for raw_path in managed_settings:
        path = Path(raw_path).resolve()
        if not path.exists():
            continue
        setting, violation = _read_settings(path, "managed")
        if violation:
            other.append(violation)
        else:
            symbolic_settings.append(setting)

    settings = getattr(options, "settings", None)
    if settings is not None:
        try:
            path = Path(settings)
        except TypeError:
            path = None
        canonical = runtime_dir / "settings.json"
        if path is None or not path.is_absolute():
            other.append(_violation(
                "invalid_launch", "launch:settings"
            ))
        else:
            path = path.resolve()
            if path != canonical:
                other.append(_violation(
                    "invalid_launch", "launch:settings"
                ))
            if path.parent == runtime_dir:
                setting, violation = _read_settings(path, "explicit")
                if violation:
                    other.append(violation)
                else:
                    symbolic_settings.append(setting)

    if not isinstance(environment, dict):
        other.append(_violation(
            "invalid_launch", "launch:env"
        ))
        environment = {}
    try:
        credentials = auth_resolution.evaluate_inputs({
            "environment": environment,
            "settings": symbolic_settings,
            "setting_sources": [],
        })["violations"]
    except auth_resolution.ManifestError:
        credentials = []
        other.append(_violation(
            "invalid_launch", "launch:env"
        ))
    other.sort(key=lambda item: (item["code"], item["source"]))
    return tuple(credentials + other)


def _uuid(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-7{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _sql(script: str, role: str = "rk2_runtime", actor: str = "runtime") -> str:
    return rk.psql(script, role=role, program=JOB["program"], actor=actor)


def _one(script: str, role: str = "rk2_runtime", actor: str = "runtime") -> str:
    return rk.one(script, role=role, program=JOB["program"], actor=actor)


# ---------------------------------------------------------------------------
# hooks: ticket 13's boundary. A tool run exists because a hook opened it.
# ---------------------------------------------------------------------------

async def pre_tool(data, tool_use_id, context):
    if not INIT_CORROBORATED:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason":
                                           "startup init not corroborated"}}
    name = data.get("tool_name", "")
    args = data.get("tool_input", {}) or {}
    tuid = data.get("tool_use_id") or tool_use_id or f"anon-{len(STATE['tool_runs'])}"
    tr_id = _uuid(f"tr:{JOB['agent_run_id']}:{tuid}")
    args_blob = json.dumps(args, sort_keys=True)
    args_sha = hashlib.sha256(args_blob.encode()).hexdigest()
    try:
        # `tool_runs.args_sha256` and `.result_sha256` both FK into `artifacts`,
        # so the blob registry must know the digest before the tool run may cite
        # it. The arguments a model passed are agent-visible by construction --
        # the model wrote them -- so they go in as `agent_visible`, unencrypted.
        _sql("INSERT INTO artifacts (sha256, byte_size, content_type, "
             "visibility, encrypted) VALUES "
             f"({rk.lit(args_sha)}, {len(args_blob.encode())}, "
             "'application/json', 'agent_visible', false) "
             "ON CONFLICT (sha256) DO NOTHING;")
        _sql(f"""
        INSERT INTO tool_runs (id, program_id, label, agent_run_id, task_id, tool,
                               args, started_at, status, tool_use_id, session_id,
                               sdk_agent_id, sdk_agent_type, transport, mcp_server,
                               args_sha256)
        VALUES ({rk.lit(tr_id)}, {rk.lit(JOB['program'])},
                {rk.lit('tr-' + tuid[:40])}, {rk.lit(JOB['agent_run_id'])},
                {rk.lit(JOB.get('task_id'))}, {rk.lit(name)},
                {rk.jlit(args)}, now(), 'running', {rk.lit(tuid)},
                {rk.lit(data.get('session_id'))},
                {rk.lit(data.get('agent_id'))}, {rk.lit(data.get('agent_type'))},
                'mcp', 'rk2', {rk.lit(args_sha)})
        ON CONFLICT (id) DO NOTHING;
        """)
        STATE["tool_runs"].append({"id": tr_id, "tool": name, "tool_use_id": tuid,
                                   "decision": None})
    except rk.SqlError as e:
        # A hook that cannot record the tool run must not let the tool proceed:
        # an unrecorded call is exactly the thing receipts exist to prevent.
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason":
                                           f"tool_run not recorded: {str(e)[:120]}"}}
    # The database evaluates and stamps the gate. Only an active allow returns
    # a capability; it stays process-private until the network adapter consumes
    # it in ticket 04.
    try:
        g = json.loads(_one(f"SELECT authorize_tool_run({rk.lit(tr_id)});"))
    except Exception as exc:                      # noqa: BLE001
        _sql(f"UPDATE tool_runs SET status='denied', closed_by='PreToolUse', "
             f"finished_at=now(), hook_error='gate failed' "
             f"WHERE id={rk.lit(tr_id)} AND status='running';")
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason":
                                           f"gate failed: {str(exc)[:120]}"}}
    capability = g.pop("capability", None)
    STATE["tool_runs"][-1]["decision"] = g.get("decision")
    STATE["gates"].append({"tool": name, "decision": g.get("decision"),
                           "risk_class": g.get("risk_class"),
                           "rule": g.get("rule"), "approval": g.get("approval")})
    if g.get("decision") == "allow":
        if not capability:
            _sql(f"UPDATE tool_runs SET status='denied', closed_by='PreToolUse', "
                 f"finished_at=now(), hook_error='capability missing' "
                 f"WHERE id={rk.lit(tr_id)} AND status='running';")
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "deny",
                                           "permissionDecisionReason":
                                               "gate returned no capability"}}
        CAPABILITIES[tr_id] = capability
        return {}
    if g.get("decision") == "deny":
        _sql(f"UPDATE tool_runs SET status='denied', closed_by='PreToolUse', "
             f"finished_at=now() "
             f"WHERE id={rk.lit(tr_id)};")
        STATE["denied"].append(name)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason":
                                           f"risk gate: {g.get('risk_class')}"}}
    # ask: park, and end the RUN, not just the call. `park_for_human` stamps
    # `agent_runs.finished_at`, `stop_reason='parked'`, unbinds the session and
    # releases the identity leases -- "the run ends, the lane slot frees" is a
    # comment in the function itself. A hook that parked and then let the model
    # keep talking would be contradicting the row it just wrote, so the flag
    # here stops the query loop at the next message.
    dl = _one(f"SELECT park_for_human({rk.lit(tr_id)}, interval '30 minutes');").strip()
    STATE["parked"].append({"tool": name, "decision_label": dl})
    STATE["must_stop"] = "parked"
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason":
                                       f"parked for a human decision: {dl}"}}


async def post_tool(data, tool_use_id, context):
    tuid = data.get("tool_use_id") or tool_use_id
    match = [t for t in STATE["tool_runs"] if t["tool_use_id"] == tuid]
    if not match:
        return {}
    resp = data.get("tool_response")
    blob = json.dumps(resp, sort_keys=True, default=str)
    res_sha = hashlib.sha256(blob.encode()).hexdigest()
    _sql("INSERT INTO artifacts (sha256, byte_size, content_type, visibility, "
         f"encrypted) VALUES ({rk.lit(res_sha)}, {len(blob.encode())}, "
         "'application/json', 'agent_visible', false) "
         "ON CONFLICT (sha256) DO NOTHING;")
    _sql(f"""
    UPDATE tool_runs SET status='success', finished_at=now(),
           result_sha256={rk.lit(res_sha)}, closed_by='PostToolUse'
     WHERE id={rk.lit(match[0]['id'])} AND status='running';
    """)
    CAPABILITIES.pop(match[0]["id"], None)
    return {}


# ---------------------------------------------------------------------------
# the tool surface. Three tools; none of them writes state.
# ---------------------------------------------------------------------------

@tool("state_read", "Read program state. Named views only, no SQL.",
      {"view": str})
async def t_state_read(args):
    view = (args.get("view") or "").strip()
    views = {
        "task": "SELECT label, kind, status, subject_entity_id FROM tasks "
                "WHERE program_id = rk2_program() ORDER BY label",
        # `program_scope_rules` is keyed (program_id, version, ord) -- there is
        # no `scope_version_id` and no `selector`; the projection ticket 26
        # publishes is (effect, pattern_kind, pattern_text). The version shown
        # is the program's *current* one, so what the agent reads is what
        # `gate_tool_call` will resolve against.
        # MEASURED: `port` belongs in this projection. The first live run put
        # port 80 on the wire because this view omitted it; with the rule
        # narrowed to 18831 that request is `denied`, not merely 404.
        "scope": "SELECT r.effect, r.pattern_kind, r.pattern_text, r.port, "
                 "coalesce(r.path_prefix,'/') AS path_prefix, r.tier "
                 "FROM program_scope_rules r JOIN programs p "
                 "ON p.id = r.program_id AND p.scope_version = r.version "
                 "WHERE r.program_id = rk2_program() ORDER BY r.ord",
        # ... and `base_url` belongs here, for the same reason: it is the one
        # place in the corpus that tells an agent where the target listens.
        "endpoints": "SELECT n.label, e.method, e.path_template, a.base_url "
                     "FROM endpoints e JOIN entities n ON n.id = e.entity_id "
                     "JOIN applications a ON a.entity_id = e.application_id "
                     "WHERE e.program_id = rk2_program() ORDER BY n.label",
        "identities": "SELECT label FROM entities WHERE program_id = rk2_program() "
                      "AND type='identity' ORDER BY label",
        "hypotheses": "SELECT label, status, statement FROM hypotheses "
                      "WHERE program_id = rk2_program() ORDER BY label",
        "receipts": "SELECT id, method, path, status_code, decision FROM receipts "
                    "WHERE program_id = rk2_program() ORDER BY ts_arrival",
    }
    if view not in views:
        return {"content": [{"type": "text",
                             "text": "unknown view. one of: " + ", ".join(views)}]}
    # rk2_state: SELECT only, everywhere. The agent's read path is a role, not
    # a promise.
    out = rk.psql(views[view] + ";", role="rk2_state", program=JOB["program"])
    return {"content": [{"type": "text", "text": out.strip()[:4000] or "(no rows)"}]}


# The name and the argument names are both fixed by data in the corpus, not
# chosen here. `canonical_request()` returns early for any tool that is not
# literally `mcp__rk2__net_request`, and the facts `call_risk_rules` matches on
# are `url`, `method` and `identity_slot`. A first-party HTTP verb called
# anything else is ungated: no rule can fire on it and `tool_risk_classes`
# floors it at approval_required through the `*` fallback.
#
# MEASURED, and the reason `url` is documented as absolute: ticket 28's
# `canonical_request` parses `url` with
#   '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)(?:\?([^#]*))?$'
# and RAISEs 22023 `net_request url is not canonicalisable` on anything else.
# A relative path therefore cannot be gated at all: `gate_tool_call` throws,
# the PreToolUse hook denies fail-closed ("gate failed: ..."), and the call
# never reaches this function. There is no relative-URL convention anywhere in
# the corpus, so the tool must not invent one -- an earlier version of this
# file resolved '/api/notes/1' against the fixture port, which made the model
# emit an argument the runtime could not judge. Absolute only.
@tool("net_request", "Make a request to the target as an identity. `url` must "
                     "be absolute: scheme://host:port/path, exactly as "
                     "state_read view='endpoints' reports base_url. Use an "
                     "empty identity_slot for a public request. "
                     "You never see or supply the credential.",
      {"identity_slot": str, "url": str, "method": str})
async def t_net_request(args):
    ident = (args.get("identity_slot") or "").strip()
    url = args.get("url") or "/"
    path = "/" + url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else url
    tr = [t for t in STATE["tool_runs"] if t["tool"].endswith("net_request")]
    tr_id = tr[-1]["id"] if tr else None
    try:
        r = RT.request(url, identity=ident or None, lane="agent",
                       method=(args.get("method") or "GET").upper(),
                       capability=CAPABILITIES.get(tr_id), program=JOB["program"])
    except Exception as exc:
        return {"content": [{"type": "text", "text": f"request failed: {exc}"}],
                "is_error": True}
    pg_id = r["receipt_id"]
    if r["receipt_id"]:
        STATE["receipts"].append({"pg": pg_id, "path": path,
                                  "identity": ident, "status": r["status"]})
    body = r["body"][:1200]
    return {"content": [{"type": "text", "text": json.dumps({
        "receipt_id": pg_id, "status": r["status"], "body": body})}]}


@tool("propose_finding",
      "Propose an access-control finding. Cite the receipt_id of the request "
      "that shows it. The runtime verifies every citation before anything is "
      "recorded.",
      {"statement": str, "receipt_id": str, "evidence_excerpt": str})
async def t_propose_finding(args):
    pid = _uuid(f"prop:{JOB['agent_run_id']}:{len(STATE['proposals'])}")
    payload = {
        "statement": (args.get("statement") or "")[:600],
        "observations": [{
            "kind": "access_control",
            "summary": (args.get("statement") or "")[:200],
            "receipt_id": (args.get("receipt_id") or "").strip(),
            "excerpt": (args.get("evidence_excerpt") or "")[:200],
        }],
    }
    _sql(f"""
    INSERT INTO proposals (id, program_id, label, agent_run_id, task_id,
                           payload, status, completion, created_at)
    VALUES ({rk.lit(pid)}, {rk.lit(JOB['program'])},
            {rk.lit('prop-' + pid[:8])}, {rk.lit(JOB['agent_run_id'])},
            {rk.lit(JOB['task_id'])}, {rk.jlit(payload)},
            'staged', {rk.lit(args.get('completion') or 'complete')}, now());
    """)
    STATE["proposals"].append({"id": pid, "payload": payload})
    return {"content": [{"type": "text", "text": json.dumps({
        "proposal_id": pid, "status": "staged",
        "note": "staged only. The runtime decides whether this becomes state."})}]}


# ---------------------------------------------------------------------------

async def _run(environment=None, runtime=None, options_type=ClaudeAgentOptions,
               transport=query) -> dict:
    global INIT_CORROBORATED
    INIT_CORROBORATED = False
    environment = dict(os.environ) if environment is None else environment
    runtime = _runtime_facts() if runtime is None else runtime
    runtime_dir = Path(JOB["launch_dir"]).resolve()
    server = create_sdk_mcp_server(
        # The name is load-bearing, not cosmetic: `tool_risk_classes`
        # enumerates `mcp__rk2__*` -> constrained, and everything it does not
        # enumerate falls to `*` -> approval_required. An SDK server named
        # anything else makes every first-party tool call unrecordable.
        name="rk2", version="0.1.0",
        tools=[t_state_read, t_net_request, t_propose_finding])

    runtime_cli = runtime.get("cli_path")
    cli_path = str(Path(runtime_cli).resolve()) if runtime_cli is not None else None
    options = options_type(
        model=JOB.get("model") or None,
        max_turns=JOB.get("max_turns", 6),
        tools=[],                       # no built-in tools: no Bash, no Read.
        mcp_servers={"rk2": server},
        allowed_tools=["mcp__rk2__state_read", "mcp__rk2__net_request",
                       "mcp__rk2__propose_finding"],
        setting_sources=[],             # the operator's settings stay out
        permission_mode="bypassPermissions",
        hooks={
            "PreToolUse": [HookMatcher(hooks=[pre_tool])],
            "PostToolUse": [HookMatcher(hooks=[post_tool])],
        },
        cwd=str(runtime_dir),
        env={},
        sandbox=None,
        settings=None,
        cli_path=cli_path,
    )
    violations = _assess_launch(
        options, environment, runtime,
        managed_settings=MANAGED_SETTINGS, runtime_dir=runtime_dir,
    )
    if violations:
        raise rk.StartupRefusal(violations)

    cap = JOB.get("cap", rk.PER_RUN_CAP)
    result = None
    started = time.monotonic()
    messages = transport(prompt=JOB["prompt"], options=options)
    try:
        first = await anext(messages)
    except StopAsyncIteration:
        first = None
    valid_init = (isinstance(first, SystemMessage)
                  and getattr(first, "subtype", None) == "init"
                  and getattr(first, "data", {}).get("apiKeySource") == "none")
    if not valid_init:
        close = getattr(messages, "aclose", None)
        if close:
            await close()
        raise rk.StartupRefusal(({
            "code": "auth_source_unexpected", "vector": None,
            "source": "init:apiKeySource", "effect": "unverifiable",
        },), phase="init")
    STATE["api_key_source"] = "none"
    STATE["guard"] = "init_ok"
    INIT_CORROBORATED = True

    async for msg in messages:
        if STATE["must_stop"]:
            break
        if isinstance(msg, AssistantMessage):
            u = msg.usage or {}
            STATE["turns"] += 1
            STATE["turn_input"] += int(u.get("input_tokens") or 0) \
                + int(u.get("cache_read_input_tokens") or 0) \
                + int(u.get("cache_creation_input_tokens") or 0)
            STATE["turn_output"] += int(u.get("output_tokens") or 0)
            if STATE["turn_input"] + STATE["turn_output"] > cap:
                # The ceiling stops the run. Not a warning, not a log line.
                STATE["cap_hit"] = True
                break
        if isinstance(msg, ResultMessage):
            result = msg
    elapsed = round(time.monotonic() - started, 2)

    ru = (result.usage if result else None) or {}
    out = {
        "elapsed_s": elapsed,
        "cap": cap, "cap_hit": STATE["cap_hit"],
        "guard": STATE["guard"], "api_key_source": STATE["api_key_source"],
        "turn_sum_input": STATE["turn_input"], "turn_sum_output": STATE["turn_output"],
        "result_input": int(ru.get("input_tokens") or 0)
                        + int(ru.get("cache_read_input_tokens") or 0)
                        + int(ru.get("cache_creation_input_tokens") or 0),
        "result_output": int(ru.get("output_tokens") or 0),
        "raw_input_tokens": int(ru.get("input_tokens") or 0),
        "cache_read": int(ru.get("cache_read_input_tokens") or 0),
        "cache_write": int(ru.get("cache_creation_input_tokens") or 0),
        "num_turns": result.num_turns if result else STATE["turns"],
        "stop_reason": (result.stop_reason if result
                        else (STATE["must_stop"] or "cap_break")),
        "total_cost_usd": (result.total_cost_usd if result else None),
        "models": sorted((result.model_usage or {}).keys()) if result else [],
        "text": (result.result or "")[:1500] if result else "",
        "tool_runs": STATE["tool_runs"], "receipts": STATE["receipts"],
        "proposals": STATE["proposals"], "denied": STATE["denied"],
        "gates": STATE["gates"], "parked": STATE["parked"],
    }
    return out


def main() -> None:
    global JOB, RT
    JOB = json.loads(sys.argv[1])
    rk.CT, rk.DB = JOB["ct"], JOB["db"]
    rk.AGENT_PORT = JOB["agent_port"]
    rk.RUN = Path(JOB["run_dir"])
    RT = rk.Runtime()
    RT.proxy_out = Path(JOB["run_dir"]) / "proxy-out"

    runtime = _runtime_facts()
    try:
        out = anyio.run(_run, None, runtime)
    except rk.StartupRefusal as exc:
        print(json.dumps({"startup_refusal": {
            "phase": exc.phase,
            "sdk_version": runtime["sdk_version"],
            "cli_version": runtime["cli_version"],
            "violations": exc.violations,
        }}), file=sys.stderr)
        raise SystemExit(78) from None
    out["sdk_version"] = runtime["sdk_version"]
    out["cli_version"] = runtime["cli_version"]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
