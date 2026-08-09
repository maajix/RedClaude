"""Credential-free, local composition of startup, capability and proxy fences."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import rk
from test_startup_launch import (
    FakeOptions,
    FakeResultMessage,
    FakeSystemMessage,
    _job,
    _load_child,
    _runtime,
)


HERE = Path(__file__).resolve().parent
MAIN = rk.PROG_MAIN
OTHER = rk.PROG_EXHAUST
CONTROL_AUTH = "Bearer synthetic-subscription-fixture"
CREATE_API_KEY = "/api/oauth/claude_cli/create_api_key"


class _Target(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    observations: list[dict] = []
    lock = threading.Lock()
    capability: str | None = None

    def log_message(self, *_args):
        pass

    def _record(self, path: str) -> None:
        values = list(self.headers.values())
        with self.lock:
            self.observations.append({
                "path": path,
                "proxy_authorization": "Proxy-Authorization" in self.headers,
                "capability": bool(self.capability)
                              and any(self.capability in value for value in values),
                "control_authorization": self.headers.get("Authorization") == CONTROL_AUTH,
                "caller_authorization": self.headers.get("Authorization") ==
                                        "Bearer caller-supplied",
                "cookie": "sid=sid-userA" in self.headers.get("Cookie", ""),
            })

    def _send(self, status: int, payload: dict, cookie: bool = False) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header("Set-Cookie", "sid=sid-userA; Path=/")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        self._record(self.path)
        if self.path == "/login":
            self._send(200, {"ok": True}, cookie=True)
        elif self.path == CREATE_API_KEY:
            self._send(200, {"created": True})
        else:
            self._send(404, {"error": "not found"})

    def do_GET(self):
        self._record(self.path)
        if self.path == "/health":
            self._send(200, {"target_response": "visible"})
        elif self.path == "/api/profile":
            self._send(200 if "sid=sid-userA" in self.headers.get("Cookie", "") else 401,
                       {"target_response": "visible", "user": "userA"})
        elif self.path == "/control/ping":
            self._send(200, {
                "authorized": self.headers.get("Authorization") == CONTROL_AUTH,
            })
        else:
            self._send(404, {"error": "not found"})


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True


@unittest.skipUnless(os.environ.get("RK_COMPOSED_OFFLINE") == "1",
                     "set RK_COMPOSED_OFFLINE=1 to run the Docker/proxy proof")
class StartupCompositionTest(unittest.TestCase):
    def _reset(self) -> None:
        env = dict(os.environ, CT=rk.CT, DB=rk.DB,
                   RK_T31_CT=rk.CT, RK_T31_DB=rk.DB)
        run = subprocess.run([str(HERE / "reset.sh")], cwd=HERE, env=env,
                             capture_output=True, text=True, timeout=180)
        if run.returncode:
            self.fail((run.stderr or run.stdout)[-3000:])

    @staticmethod
    def _claim() -> tuple[str, str]:
        rk.one("SELECT rank_pass('offline');", program=MAIN, actor="runtime")
        rk.psql("SELECT offer_slate();", program=MAIN, actor="runtime")
        label = rk.one("SELECT claim_task('T_HUNT');",
                       program=MAIN, actor="runtime")
        return tuple(rk.rows(
            "SELECT a.id, a.task_id FROM agent_runs a "
            f"WHERE a.label={rk.lit(label)};", program=MAIN)[0])

    @staticmethod
    def _runtime(root: Path) -> dict:
        cli = root / "sdk/_bundled/claude"
        cli.parent.mkdir(parents=True)
        cli.write_text("synthetic executable")
        cli.chmod(0o755)
        return _runtime(cli)

    def _scenario(self) -> dict:
        self._reset()
        _Target.observations = []
        _Target.capability = None
        server = _Server(("127.0.0.1", rk.VULN_PORT), _Target)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(rk, "RUN", Path(temporary)), \
             patch.dict(os.environ, {"RK_CONTROL_AUTHORIZATION": CONTROL_AUTH}):
            runtime = rk.Runtime()
            try:
                runtime.start_proxy()
                self.assertEqual(200, runtime.provision("userA", rk.VULN_PORT)["status"])

                refused_run, refused_task = self._claim()
                rk.psql(
                    "INSERT INTO agent_sessions(program_id,session_id,agent_run_id,task_id) "
                    f"VALUES(rk2_program(),'offline-refusal',{rk.lit(refused_run)},"
                    f"{rk.lit(refused_task)});",
                    program=MAIN, actor="runtime",
                )
                child = _load_child()
                launch = Path(temporary) / "refused-launch"
                launch.mkdir()
                child.JOB = _job(launch)
                child.JOB.update(program=MAIN, agent_run_id=refused_run,
                                 task_id=refused_task)
                called = []

                async def must_not_transport(**_kwargs):
                    called.append(True)
                    yield FakeSystemMessage()

                with patch.object(child, "MANAGED_SETTINGS", ()):
                    with self.assertRaises(rk.StartupRefusal) as caught:
                        asyncio.run(child._run(
                            environment={"ANTHROPIC_API_KEY": "synthetic-do-not-render"},
                            runtime=self._runtime(Path(temporary)),
                            options_type=FakeOptions,
                            transport=must_not_transport,
                        ))
                self.assertEqual([], called)
                serialized = json.dumps({"startup_refusal": {
                    "phase": caught.exception.phase,
                    "sdk_version": "0.2.132", "cli_version": "2.1.224",
                    "violations": caught.exception.violations,
                }})
                with self.assertRaises(rk.StartupRefusal) as parsed:
                    rk._child_result("", serialized)
                request = rk.AgentRunRequest(
                    program=MAIN, agent_run_id=refused_run, task_id=refused_task,
                    prompt="synthetic fixture prompt",
                )
                with patch.object(rk, "_spawn_agent_process",
                                  side_effect=parsed.exception):
                    with self.assertRaises(rk.StartupRefusal):
                        rk.agent_run(request)

                cleanup = rk.rows(f"""
                    SELECT a.stop_reason, a.result IS NULL, t.status, t.attempts,
                           t.claimed_at IS NULL AND t.lease_expires_at IS NULL,
                           count(l.id) FILTER (WHERE l.released_at IS NULL),
                           count(s.id) FILTER (WHERE s.unbound_at IS NULL),
                           count(tr.id), count(r.id)
                      FROM agent_runs a JOIN tasks t ON t.id=a.task_id
                      LEFT JOIN identity_leases l ON l.holder_agent_run_id=a.id
                      LEFT JOIN agent_sessions s ON s.agent_run_id=a.id
                      LEFT JOIN tool_runs tr ON tr.agent_run_id=a.id
                      LEFT JOIN receipts r ON r.tool_run_id=tr.id
                     WHERE a.id={rk.lit(refused_run)}
                     GROUP BY a.stop_reason,a.result,t.status,t.attempts,
                              t.claimed_at,t.lease_expires_at;
                """, program=MAIN)[0]
                event = json.loads(rk.one(
                    "SELECT payload::text FROM events WHERE type='startup.refused' "
                    f"AND agent_run_id={rk.lit(refused_run)};", program=MAIN))
                self.assertNotIn("synthetic-do-not-render", json.dumps(event))
                self.assertEqual("1", rk.one(
                    "SELECT count(*) FROM agent_runs WHERE program_id=rk2_program();",
                    program=MAIN))

                clean_run, clean_task = self._claim()
                launch = Path(temporary) / "clean-launch"
                launch.mkdir()
                home = Path(temporary) / "agent-home/.claude"
                home.mkdir(parents=True)
                (home / ".credentials.json").write_text(
                    '{"claudeAiOauth":{"accessToken":"placeholder-only"}}')
                child = _load_child()
                child.JOB = _job(launch)
                child.JOB.update(
                    program=MAIN, agent_run_id=clean_run, task_id=clean_task,
                    ct=rk.CT, db=rk.DB, agent_port=rk.AGENT_PORT,
                    vuln_port=rk.VULN_PORT, run_dir=temporary,
                    identity_entity_ids=rk.IDENTITY_ENTITY_IDS,
                )
                child.RT = runtime
                child_environment = rk._child_environment({
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": str(home.parent),
                    "RK_CONTROL_PROXY_URL": f"http://127.0.0.1:{rk.CONTROL_PORT}",
                    "RK_CONTROL_AUTHORIZATION": CONTROL_AUTH,
                })
                self.assertNotIn(CONTROL_AUTH, child_environment.values())
                observed: dict = {}
                url = f"http://127.0.0.1:{rk.VULN_PORT}/health"

                async def transport(**_kwargs):
                    yield FakeSystemMessage()
                    data = {
                        "tool_name": "mcp__rk2__net_request",
                        "tool_input": {
                            "identity_slot": "", "url": url, "method": "GET",
                        },
                        "tool_use_id": "toolu-offline-composed",
                    }
                    self.assertEqual({}, await child.pre_tool(data, None, None))
                    tool_run = child.STATE["tool_runs"][-1]["id"]
                    capability = child.CAPABILITIES[tool_run]
                    _Target.capability = capability
                    response = await child.t_net_request(data["tool_input"])
                    observed["tool_response"] = json.loads(response["content"][0]["text"])
                    observed["capability"] = capability
                    observed["tool_run"] = tool_run
                    observed["subresource"] = runtime.request(
                        f"http://127.0.0.1:{rk.VULN_PORT}/api/profile",
                        capability=capability, program=MAIN,
                    )
                    observed["bypass"] = {
                        "missing": runtime.request(url, program=MAIN)["status"],
                        "fabricated": runtime.request(
                            url, capability="0" * 64,
                            program=MAIN)["status"],
                        "program": runtime.request(
                            url, capability=capability,
                            program=OTHER)["status"],
                    }
                    rk.psql(
                        "SET ROLE rk2_owner; UPDATE tool_runs "
                        "SET egress_token_expires_at=clock_timestamp()-interval '1 second' "
                        f"WHERE id={rk.lit(tool_run)};",
                        role="rk2_migrate", program=MAIN, actor="runtime",
                    )
                    observed["bypass"]["expired"] = runtime.request(
                        url, capability=capability,
                        program=MAIN)["status"]
                    await child.post_tool({
                        "tool_use_id": data["tool_use_id"],
                        "tool_response": response,
                    }, None, None)
                    observed["bypass"]["cleared"] = runtime.request(
                        url, capability=capability,
                        program=MAIN)["status"]
                    yield FakeResultMessage()

                with patch.object(child, "MANAGED_SETTINGS", ()):
                    clean = asyncio.run(child._run(
                        environment=child_environment,
                        runtime=self._runtime(Path(temporary) / "clean"),
                        options_type=FakeOptions, transport=transport,
                    ))

                receipt = rk.rows(
                    "SELECT r.lane,r.decision,r.status_code::text,"
                    "(r.tool_run_id=tr.id),(tr.egress_token_sha256 IS NULL) "
                    "FROM receipts r JOIN tool_runs tr ON tr.id=r.tool_run_id "
                    f"WHERE r.id={rk.lit(observed['tool_response']['receipt_id'])};",
                    program=MAIN,
                )[0]
                receipt_count = rk.one(
                    "SELECT count(*) FROM receipts WHERE decision='allowed' "
                    f"AND tool_run_id={rk.lit(observed['tool_run'])};",
                    program=MAIN,
                )
                raw_bypass = rk.raises(
                    "INSERT INTO receipts(program_id,lane,decision,reason,ts_arrival,"
                    "scope_version,scope_class) VALUES(rk2_program(),'agent','allowed',"
                    "'raw bypass',now(),1,'target');",
                    program=MAIN, actor="runtime",
                )
                fake_writer = rk.raises(
                    "SELECT write_allowed_receipt(repeat('0',64),"
                    "'{\"scope_class\":\"target\"}');",
                    program=MAIN, actor="runtime",
                )

                control_ping = runtime.request(
                    f"http://127.0.0.1:{rk.VULN_PORT}/control/ping",
                    lane="control", program=MAIN,
                    headers={"Authorization": "Bearer caller-supplied"},
                )
                create = runtime.request(
                    f"http://127.0.0.1:{rk.VULN_PORT}{CREATE_API_KEY}",
                    lane="control", program=MAIN, method="POST", body=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                control_receipt = rk.rows(
                    "SELECT lane,decision,scope_version IS NULL,scope_class,"
                    "tool_run_id IS NULL FROM receipts "
                    f"WHERE id={rk.lit(create['receipt_id'])};", program=MAIN,
                )[0]

                profiles = [row for row in _Target.observations
                            if row["path"] in {"/health", "/api/profile"}]
                pings = [row for row in _Target.observations
                         if row["path"] == "/control/ping"]
                creates = [row for row in _Target.observations
                           if row["path"] == CREATE_API_KEY]
                self.assertEqual(2, len(profiles))
                self.assertEqual(1, len(pings))
                self.assertEqual([], creates)
                self.assertTrue(all(not row["proxy_authorization"]
                                    and not row["capability"]
                                    for row in profiles))
                self.assertTrue(pings[0]["control_authorization"])
                self.assertFalse(pings[0]["caller_authorization"])
                self.assertNotIn(observed["capability"], json.dumps(clean))
                self.assertTrue(raw_bypass and fake_writer)

                return {
                    "refusal": {
                        "state": cleanup,
                        "payload": event,
                    },
                    "clean": {
                        "guard": clean["guard"],
                        "api_key_source": clean["api_key_source"],
                        "response_visible": observed["tool_response"]["status"] == 200
                                            and "target_response" in
                                            observed["tool_response"]["body"],
                        "receipt": receipt,
                        "same_capability_receipts": receipt_count,
                        "subresource_status": observed["subresource"]["status"],
                    },
                    "bypass": observed["bypass"],
                    "target_profile_requests": len(profiles),
                    "control": {
                        "ping": control_ping["status"],
                        "create_api_key": create["status"],
                        "receipt": control_receipt,
                        "target_requests": len(creates),
                    },
                }
            finally:
                runtime.stop()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_composed_proof_is_green_and_repeatable(self):
        first = self._scenario()
        second = self._scenario()
        self.assertEqual(first, second)
        self.assertEqual(["refusal", "t", "pending", "0", "t", "0", "0", "0", "0"],
                         first["refusal"]["state"])
        self.assertEqual({"missing": 407, "fabricated": 407, "program": 407,
                          "expired": 407, "cleared": 407}, first["bypass"])
        self.assertEqual(["agent", "allowed", "200", "t", "t"],
                         first["clean"]["receipt"])
        self.assertEqual("2", first["clean"]["same_capability_receipts"])
        self.assertEqual(401, first["clean"]["subresource_status"])
        self.assertEqual(["control", "blocked", "t", "control_plane", "t"],
                         first["control"]["receipt"])
        self.assertEqual(0, first["control"]["target_requests"])


if __name__ == "__main__":
    unittest.main()
