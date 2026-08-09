"""Ticket 31 runtime — the parts the nine proofs share.

Not a runtime worth shipping. It is the smallest thing that can drive one
hypothesis from discovery to validation through the *composed* design, so that
the places the pieces do not link show up as failures rather than as prose.

Three connections, deliberately, because the corpus draws three boundaries and a
skeleton that used one would prove nothing about any of them:

  rk2_runtime  the loop. DML + EXECUTE, no DDL. RK2_DATABASE_URL.
  rk2_state    what an agent reads through. No INSERT/UPDATE/DELETE anywhere.
  rk2_human    the only role whose membership authorises actor_kind='human'.

All three go over `docker exec` into the container rather than TCP, because the
roles are provisioned LOGIN-without-password and the image's pg_hba trusts the
unix socket. That is a prototype shortcut and it is the only one.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import UUID

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
RUN = Path(os.environ.get("RK_T31_RUN", HERE / "run"))

CT = os.environ.get("RK_T31_CT", "rk2-t31-pg")
DB = os.environ.get("RK_T31_DB", "rk2")

VULN_PORT = int(os.environ.get("RK_T31_VULN_PORT", "18831"))
SECURE_PORT = int(os.environ.get("RK_T31_SECURE_PORT", "18832"))
AGENT_PORT = int(os.environ.get("RK_AGENT_PORT", "18830"))
PROVISION_PORT = int(os.environ.get("RK_PROVISION_PORT", "18833"))
CONTROL_PORT = int(os.environ.get("RK_CONTROL_PORT", "18834"))

# The three ceilings the operator set for this ticket. Hard, not guidance.
BUDGET_MAIN = 200_000
BUDGET_EXHAUST = 5_000
PER_RUN_CAP = 50_000

PROG_MAIN = "31111111-3111-7111-8111-111111111111"
PROG_EXHAUST = "31222222-3222-7222-8222-222222222222"

VENVPY = os.environ.get(
    "RK_T31_VENVPY",
    "/home/majix/redKrakenV2/prototype/sdk-auth-probe/.venv/bin/python",
)

INHERITED_AGENT_ENV = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR",
    "XDG_RUNTIME_DIR", "SHELL",
)


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    program: str
    agent_run_id: str
    task_id: str | None
    prompt: str
    max_turns: int = 6
    model: str | None = None
    cap: int = PER_RUN_CAP
    vuln_port: int | None = None
    identity_entity_ids: Mapping[str, str] | None = None
    kill_after_first_tool_run: bool = False


class StartupRefusal(RuntimeError):
    def __init__(self, violations, phase: str = "pre_spawn",
                 sdk_version: str | None = None, cli_version: str | None = None):
        self.violations = tuple(violations)
        self.phase = phase
        self.sdk_version = sdk_version
        self.cli_version = cli_version
        if phase not in {"pre_spawn", "init"} or not self.violations:
            raise ValueError("invalid startup refusal")
        keys = {"code", "vector", "source", "effect"}
        if any(not isinstance(item, Mapping) or set(item) != keys
               for item in self.violations):
            raise ValueError("invalid startup refusal violation")
        super().__init__("startup refused: " + json.dumps(
            self.violations, sort_keys=True, separators=(",", ":")
        ))


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------

class SqlError(RuntimeError):
    pass


def psql(script: str, role: str = "rk2_runtime", program: str | None = None,
         actor: str | None = None, quiet: bool = False) -> str:
    """Run a script on one connection, with the session helper applied first.

    `app.actor_kind` is prepended rather than left to the caller because
    `emit_event()` raises when it is unset, and forgetting it is the single
    easiest way to write a proof that fails for the wrong reason.
    """
    # A `DO` block rather than `SELECT set_config(...)`: the prelude must not
    # contribute rows, or every caller of `rows()`/`one()` silently parses the
    # session setup as data. (Found the hard way: P1 read the program id as a
    # slate entry.)
    prelude = []
    if program:
        prelude.append(
            "DO $rkp$ BEGIN PERFORM set_config('rk2.program_id', %s, false); END $rkp$;"
            % _lit(program))
    if actor:
        prelude.append(
            "DO $rka$ BEGIN PERFORM set_config('app.actor_kind', %s, false); END $rka$;"
            % _lit(actor))
    body = "\n".join(prelude) + "\n" + script
    p = subprocess.run(
        ["docker", "exec", "-i", CT, "psql", "-U", role, "-d", DB,
         "-v", "ON_ERROR_STOP=1", "-At", "-F", "\t", "-q", "-f", "-"],
        input=body, capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise SqlError((p.stderr or p.stdout).strip()[:2000])
    return p.stdout


def one(script: str, **kw) -> str:
    out = psql(script, **kw).strip().splitlines()
    return out[-1] if out else ""


def rows(script: str, **kw) -> list[list[str]]:
    return [ln.split("\t") for ln in psql(script, **kw).strip().splitlines() if ln]


def _lit(s) -> str:
    if s is None:
        return "NULL"
    if isinstance(s, bool):
        return "true" if s else "false"
    if isinstance(s, (int, float)):
        return str(s)
    return "'" + str(s).replace("'", "''") + "'"


def lit(s) -> str:
    return _lit(s)


def jlit(obj) -> str:
    return _lit(json.dumps(obj, sort_keys=True)) + "::jsonb"


def raises(script: str, **kw) -> str | None:
    """Return the error text, or None if the script did NOT raise.

    Every adversarial check in this file is written this way round: the check
    that matters is the one that fails when the guard is missing.
    """
    try:
        psql(script, **kw)
        return None
    except SqlError as e:
        return str(e)


# ---------------------------------------------------------------------------
# processes: the ticket-05 fixture pair and the ticket-04 proxy
# ---------------------------------------------------------------------------

def _wait_port(port: int, timeout: float = 20.0, host: str = "127.0.0.1") -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), 0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


class Runtime:
    """Owns every child process the skeleton starts, so abort can kill them."""

    def __init__(self, logdir: Path | None = None):
        self.logdir = Path(logdir or (RUN / "logs"))
        self.logdir.mkdir(parents=True, exist_ok=True)
        self.procs: dict[str, subprocess.Popen] = {}
        self.proxy_out = RUN / "proxy-out"

    # -- fixtures ----------------------------------------------------------
    def start_fixtures(self) -> None:
        app = VENDOR / "eval-harness" / "fixture" / "app.py"
        for name, variant, port in (("fixture-vuln", "vuln", VULN_PORT),
                                    ("fixture-secure", "secure", SECURE_PORT)):
            env = dict(os.environ, VARIANT=variant)
            log = (self.logdir / f"{name}.log").open("a")
            self.procs[name] = subprocess.Popen(
                [sys.executable, str(app), str(port)],
                env=env, stdout=log, stderr=log)
            log.close()
            if not _wait_port(port):
                raise RuntimeError(f"{name} did not come up on {port}")

    # -- proxy -------------------------------------------------------------
    def _materialise_proxy(self) -> Path:
        """Copy ticket 04's addon next to ticket 31's config.

        mitmproxy puts the addon's own directory on sys.path, so `import config`
        inside `addon.py` resolves to whatever sits beside it. Copying rather
        than editing is what keeps `vendor/` byte-identical to `5e5ca2e`.
        """
        d = RUN / "proxy"
        d.mkdir(parents=True, exist_ok=True)
        for mod in ("policy.py", "identity.py", "receipts.py", "budget.py"):
            shutil.copy2(VENDOR / "scope-proxy" / mod, d / mod)
        shutil.copy2(VENDOR / "scope-proxy" / "addon.py", d / "scope_addon.py")
        shutil.copy2(HERE / "capability_addon.py", d / "addon.py")
        shutil.copy2(HERE / "rk.py", d / "rk.py")
        shutil.copy2(HERE / "proxy_config.py", d / "config.py")
        return d

    def start_proxy(self) -> None:
        d = self._materialise_proxy()
        self.proxy_out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ,
                   RK_OUT=str(self.proxy_out),
                   RK_AGENT_PORT=str(AGENT_PORT),
                   RK_PROVISION_PORT=str(PROVISION_PORT),
                   RK_CONTROL_PORT=str(CONTROL_PORT))
        log = (self.logdir / "proxy.log").open("a")
        self.procs["proxy"] = subprocess.Popen(
            ["mitmdump", "-q", "-s", str(d / "addon.py"),
             "--mode", f"regular@127.0.0.1:{AGENT_PORT}",
             "--mode", f"regular@127.0.0.1:{PROVISION_PORT}",
             "--mode", f"regular@127.0.0.1:{CONTROL_PORT}",
             "--set", "connection_strategy=lazy",
             "--set", f"confdir={self.proxy_out}/ca"],
            cwd=str(d), env=env, stdout=log, stderr=log)
        log.close()
        if (not _wait_port(AGENT_PORT, 40)
                or not _wait_port(PROVISION_PORT, 40)
                or not _wait_port(CONTROL_PORT, 40)):
            raise RuntimeError("proxy did not come up")

    def stop(self, *names: str) -> None:
        for n in (names or tuple(self.procs)):
            p = self.procs.pop(n, None)
            if p and p.poll() is None:
                p.send_signal(signal.SIGKILL)
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    pass

    # -- the one egress path ----------------------------------------------
    def request(self, url: str, identity: str | None = None,
                lane: str = "agent", method: str = "GET",
                body: bytes | None = None,
                headers: dict[str, str] | None = None,
                capability: str | None = None,
                program: str | None = None) -> dict:
        """Every outbound byte in this prototype goes through here.

        Returns the proxy's own receipt id, the status, and the agent-visible
        body. The credential is never in this function: the proxy holds it.
        """
        ports = {"agent": AGENT_PORT, "provisioning": PROVISION_PORT,
                 "control": CONTROL_PORT}
        if lane not in ports:
            raise ValueError(f"unknown proxy lane: {lane}")
        port = ports[lane]
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{port}"}))
        req = urllib.request.Request(url, data=body, method=method)
        if identity:
            req.add_header("X-RedKraken-Identity", identity)
        if capability:
            req.add_header("Proxy-Authorization", f"RedKraken {capability}")
        if program:
            req.add_header("X-RedKraken-Program", program)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with opener.open(req, timeout=30) as r:
                raw, status, hdrs = r.read(), r.status, dict(r.headers)
        except urllib.error.HTTPError as e:
            try:
                raw, status, hdrs = e.read(), e.code, dict(e.headers)
            finally:
                e.close()
        return {
            "receipt_id": hdrs.get("X-RedKraken-Receipt"),
            "status": status,
            "body": raw.decode("utf-8", "replace"),
            "body_sha256": hashlib.sha256(raw).hexdigest(),
        }

    def provision(self, identity: str, port: int) -> dict:
        """Establish `identity`'s session on the provisioning lane.

        This is the only place a password exists in the runtime, and it exists
        here for exactly one request. The agent process never imports this
        module's config and never sees this lane: the provisioning listener is
        a different port, and in the containerised topology (phase B) it is
        bound to an address the agent has no route to.
        """
        sys.path.insert(0, str(HERE))
        import proxy_config
        sec = proxy_config.IDENTITIES[identity]["secrets"]
        body = json.dumps({"user": sec["user"], "password": sec["password"]})
        r = self.request(f"http://127.0.0.1:{port}/login", identity=identity,
                         lane="provisioning", method="POST",
                         body=body.encode(),
                         headers={"Content-Type": "application/json"})
        return r

    # -- proxy receipt store ----------------------------------------------
    def proxy_receipt(self, receipt_id: str) -> dict | None:
        import sqlite3
        db = self.proxy_out / "PROTOTYPE-wipe-me.sqlite"
        if not db.exists():
            return None
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM receipts WHERE receipt_id = ?",
                        (receipt_id,)).fetchone()
        con.close()
        return dict(r) if r else None

    def proxy_receipt_count(self) -> int:
        import sqlite3
        db = self.proxy_out / "PROTOTYPE-wipe-me.sqlite"
        if not db.exists():
            return 0
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        n = con.execute("SELECT count(*) FROM receipts").fetchone()[0]
        con.close()
        return n


# ---------------------------------------------------------------------------
# capability-backed proxy receipt writer
# ---------------------------------------------------------------------------

def write_capability_receipt(program: str, capability: str, receipt: dict,
                             identity_entity_id: str | None) -> str:
    """Persist proxy facts; authority fields come only from the capability."""
    # `receipts` FKs all four hash columns into `artifacts`, so the blob
    # registry has to know a hash before a receipt may cite it. This is where
    # ticket 13's dual hashing stops being a naming convention and becomes a
    # privilege boundary: the *agent* hashes are `agent_visible`, the *wire*
    # hashes cover bytes that carry the injected credential and are therefore
    # `credential_bearing`, which `artifacts_check` will only accept when
    # `encrypted` is true.
    #
    # DIVERGENCE, same family as the egress token below: ticket 04's proxy
    # stores hashes and never stores or measures the bodies, so `byte_size` is
    # recorded as 0 here. A registry whose sizes are all zero cannot answer
    # "how much have we retained", which ticket 20's retention pass needs.
    hashes = [receipt.get(name) or None for name in (
        "request_agent_sha", "request_wire_sha",
        "response_agent_sha", "response_wire_sha")]
    psql("SELECT register_proxy_artifacts("
         + ", ".join(lit(value) for value in [capability, *hashes]) + ");",
         role="rk2_proxy", program=program, actor="runtime")

    stamp = lambda value: (datetime.fromtimestamp(value, timezone.utc).isoformat()
                           if value else None)
    payload = {
        "reason": receipt.get("reason") or "",
        "identity_entity_id": identity_entity_id,
        "method": receipt.get("method"), "scheme": receipt.get("scheme"),
        "host": receipt.get("host"), "port": receipt.get("port"),
        "path": receipt.get("path"),
        "query_sha256": receipt.get("query_sha256") or None,
        "pinned_ips": receipt.get("pinned_ips") or None,
        "status_code": receipt.get("status_code"),
        "ts_arrival": stamp(receipt.get("ts_arrival")),
        "ts_egress": stamp(receipt.get("ts_egress")),
        "waited_ms": receipt.get("waited_ms"),
        "request_agent_sha": receipt.get("request_agent_sha") or None,
        "request_wire_sha": receipt.get("request_wire_sha") or None,
        "response_agent_sha": receipt.get("response_agent_sha") or None,
        "response_wire_sha": receipt.get("response_wire_sha") or None,
        "notes": receipt.get("notes") or "{}", "scope_class": "target",
    }
    return one(
        f"SELECT write_allowed_receipt({lit(capability)}, {jlit(payload)});",
        role="rk2_proxy", program=program, actor="runtime")


def write_blocked_receipt(program: str, receipt: dict,
                          capability: str | None = None) -> str:
    """Persist a refusal through the writer that cannot create an allow."""
    return one(
        f"SELECT write_blocked_receipt({lit(program)}, {jlit(receipt)}, "
        f"{lit(capability)});",
        role="rk2_proxy", program=program, actor="runtime")


# ---------------------------------------------------------------------------
# the live model call
# ---------------------------------------------------------------------------

IDENTITY_ENTITY_IDS = {
    "userA": "31aaaaaa-0000-7000-8000-000000000005",
    "userB": "31aaaaaa-0000-7000-8000-000000000006",
}


def agent_run(request: AgentRunRequest) -> dict:
    """One `agent_run`: a live model call under the per-run token sub-cap.

    Runs in a child process on the ticket-21 venv (claude-agent-sdk 0.2.132),
    with an environment built from an allowlist rather than inherited, so a run
    that silently switched to API billing would show up as a guard failure
    rather than as a bill. The child returns measured token usage; nothing here
    estimates.

    `kill_after_first_tool_run` is the abort proof: SIGKILL the pid the moment
    the first tool run is open, so the crash lands in the worst place — a tool
    run recorded as `running`, an agent run with no result, a task claimed by
    nobody. Resume has to rebuild that from the log alone.
    """
    launch_root = (RUN / "agent-runs").resolve()
    launch_dir = (launch_root / request.agent_run_id).resolve()
    if launch_dir.parent != launch_root:
        raise ValueError("agent_run_id must be one path component")
    launch_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "prompt": request.prompt,
        "max_turns": request.max_turns,
        "model": request.model,
        "cap": request.cap,
        "program": request.program,
        "agent_run_id": request.agent_run_id,
        "task_id": request.task_id,
        "ct": CT, "db": DB,
        "agent_port": AGENT_PORT,
        "vuln_port": request.vuln_port if request.vuln_port is not None else VULN_PORT,
        "run_dir": str(RUN),
        "launch_dir": str(launch_dir),
        "identity_entity_ids": dict(request.identity_entity_ids)
        if request.identity_entity_ids is not None else IDENTITY_ENTITY_IDS,
    }
    try:
        return _spawn_agent_process(request, job, _child_environment(os.environ))
    except StartupRefusal as refusal:
        _close_startup_refusal(request, refusal)
        raise


def _close_startup_refusal(request: AgentRunRequest,
                           refusal: StartupRefusal) -> None:
    """Commit the one durable refusal outcome when canonical rows exist."""
    try:
        UUID(request.program)
        UUID(request.agent_run_id)
    except ValueError:
        return
    one(
        "SELECT close_startup_refusal("
        f"{lit(request.agent_run_id)}, {lit(refusal.phase)}, "
        f"{lit(refusal.sdk_version)}, {lit(refusal.cli_version)}, "
        f"{jlit(refusal.violations)});",
        program=request.program, actor="runtime",
    )


def _child_environment(source: Mapping[str, str]) -> dict[str, str]:
    env = {key: source[key] for key in INHERITED_AGENT_ENV if key in source}
    if proxy := source.get("RK_CONTROL_PROXY_URL"):
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, NO_PROXY="")
    if ca_file := source.get("RK_CONTROL_CA_FILE"):
        env.update(SSL_CERT_FILE=ca_file, NODE_EXTRA_CA_CERTS=ca_file,
                   REQUESTS_CA_BUNDLE=ca_file)
    return env


def _spawn_agent_process(request: AgentRunRequest, job: dict,
                         environment: Mapping[str, str]) -> dict:
    argv = [VENVPY, str(HERE / "agent_child.py"), json.dumps(job)]

    if not request.kill_after_first_tool_run:
        p = subprocess.run(argv, capture_output=True, text=True, env=environment,
                           timeout=900)
        return _child_result(p.stdout, p.stderr)

    proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=environment)
    killed_at = None
    deadline = time.time() + 300
    while time.time() < deadline and proc.poll() is None:
        n = one(f"SELECT count(*) FROM tool_runs WHERE agent_run_id="
                f"{lit(request.agent_run_id)} AND status='running';",
                program=request.program)
        if n and int(n) > 0:
            proc.kill()
            killed_at = "first_tool_run_open"
            break
        time.sleep(0.25)
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()
    if killed_at is None:
        out, err = proc.communicate()
        return _child_result(out, err)
    return {"killed": killed_at, "returncode": proc.returncode}


def _child_result(out: str, err: str) -> dict:
    for ln in reversed((err or "").strip().splitlines()):
        if not ln.startswith("{"):
            continue
        try:
            result = json.loads(ln)
        except ValueError:
            continue
        if set(result) == {"startup_refusal"}:
            refusal = result["startup_refusal"]
            if isinstance(refusal, dict) and set(refusal) == {
                "phase", "sdk_version", "cli_version", "violations"
            }:
                raise StartupRefusal(
                    refusal["violations"], refusal["phase"],
                    refusal["sdk_version"], refusal["cli_version"],
                )
    for ln in reversed((out or "").strip().splitlines()):
        if ln.startswith("{"):
            try:
                result = json.loads(ln)
                if "startup_refusal" in result:
                    refusal = result["startup_refusal"]
                    if isinstance(refusal, dict):
                        raise StartupRefusal(
                            refusal["violations"], refusal["phase"],
                            refusal.get("sdk_version"), refusal.get("cli_version"),
                        )
                    raise StartupRefusal(refusal)
                return result
            except ValueError:
                continue
    raise RuntimeError("agent child produced no result: "
                       + (err or out or "")[-1500:])


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []
        self.failed = 0

    def ok(self, proof: str, what: str, detail: str = "") -> None:
        self.items.append(("PASS", proof, f"{what} {detail}".strip()))
        print(f"  PASS  [{proof}] {what} {detail}".rstrip(), flush=True)

    def bad(self, proof: str, what: str, detail: str = "") -> None:
        self.failed += 1
        self.items.append(("FAIL", proof, f"{what} {detail}".strip()))
        print(f"  FAIL  [{proof}] {what} {detail}".rstrip(), flush=True)

    def note(self, proof: str, what: str, detail: str = "") -> None:
        self.items.append(("NOTE", proof, f"{what} {detail}".strip()))
        print(f"  NOTE  [{proof}] {what} {detail}".rstrip(), flush=True)

    def check(self, cond: bool, proof: str, what: str, detail: str = "") -> bool:
        (self.ok if cond else self.bad)(proof, what, detail)
        return bool(cond)

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(
            [{"verdict": v, "proof": p, "what": w} for v, p, w in self.items],
            indent=1))
