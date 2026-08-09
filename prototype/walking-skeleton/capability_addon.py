"""Capability fence around the vendored scope proxy."""

from __future__ import annotations

import json
import re
import uuid
from urllib.parse import urlsplit

from mitmproxy import http

import config
import rk
import scope_addon


AUTH = "Proxy-Authorization"
PROGRAM = "X-RedKraken-Program"
CAPABILITY = re.compile(r"^RedKraken ([0-9a-f]{64})$")


class CapabilityProxy:
    def __init__(self, scope):
        self.scope = scope
        self.live: dict[str, tuple[str, str]] = {}
        self.connect: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _lane(flow) -> str:
        port = flow.client_conn.sockname[1]
        if port == config.PROVISION_PORT:
            return "provisioning"
        if port == config.CONTROL_PORT:
            return "control"
        return "agent"

    @staticmethod
    def _connection_id(flow) -> str:
        return str(getattr(flow.client_conn, "id", flow.id))

    def _take(self, flow) -> tuple[str | None, str | None]:
        request = flow.request
        raw = request.headers.get(AUTH, "")
        program = request.headers.get(PROGRAM, "")
        if AUTH in request.headers:
            del request.headers[AUTH]
        if PROGRAM in request.headers:
            del request.headers[PROGRAM]
        match = CAPABILITY.fullmatch(raw)
        if not raw and not program:
            return self.connect.get(self._connection_id(flow), (None, None))
        try:
            program = str(uuid.UUID(program))
        except (ValueError, AttributeError):
            return None, None
        return (match.group(1) if match else None), program

    @staticmethod
    def _authorized(capability: str, program: str, method: str, url: str,
                    identity: str = "") -> bool:
        try:
            return bool(rk.one(
                "SELECT tool_run_id FROM authorize_egress_request("
                f"{rk.lit(capability)}, {rk.lit(method)}, {rk.lit(url)}, "
                f"{rk.lit(identity)});",
                role="rk2_proxy", program=program,
            ))
        except rk.SqlError:
            return False

    def _refuse(self, flow, at: str, auth: tuple[str | None, str | None]) -> None:
        capability, program = auth
        url = (flow.request.pretty_url if at != "CONNECT" else
               f"https://{flow.request.host}:{flow.request.port}/")
        parts = urlsplit(url)
        receipt_id = None
        if program:
            try:
                receipt_id = rk.write_blocked_receipt(program, {
                    "reason": "capability refused", "method": flow.request.method,
                    "scheme": parts.scheme, "host": parts.hostname or "",
                    "port": parts.port or (443 if parts.scheme == "https" else 80),
                    "path": parts.path or "/", "status_code": 407,
                    "notes": json.dumps({"at": at}),
                }, capability)
            except rk.SqlError:
                pass
        headers = {"Content-Type": "application/json",
                   "X-RedKraken-Decision": "capability-refused"}
        if receipt_id:
            headers["X-RedKraken-Receipt"] = receipt_id
        flow.response = http.Response.make(
            407,
            json.dumps({"blocked_by": "redkraken-capability", "at": at}) + "\n",
            headers,
        )

    def _refuse_control(self, flow, program: str | None, reason: str,
                        status: int = 403) -> None:
        parts = urlsplit(flow.request.pretty_url)
        receipt_id = None
        if program:
            try:
                receipt_id = rk.write_blocked_receipt(program, {
                    "lane": "control", "reason": reason,
                    "method": flow.request.method, "scheme": parts.scheme,
                    "host": parts.hostname or "",
                    "port": parts.port or (443 if parts.scheme == "https" else 80),
                    "path": parts.path or "/", "status_code": status,
                    "notes": json.dumps({"at": "control"}),
                })
            except rk.SqlError:
                pass
        headers = {"Content-Type": "application/json",
                   "X-RedKraken-Decision": "control-refused"}
        if receipt_id:
            headers["X-RedKraken-Receipt"] = receipt_id
        flow.response = http.Response.make(
            status, json.dumps({"blocked_by": "redkraken-control",
                                "reason": reason}) + "\n", headers)

    def http_connect(self, flow) -> None:
        if self._lane(flow) != "agent":
            self._take(flow)  # hop-by-hop headers never reach a target
            return self.scope.http_connect(flow)
        auth = self._take(flow)
        url = f"https://{flow.request.host}:{flow.request.port}/"
        if not all(auth) or not self._authorized(*auth, "CONNECT", url):
            self._refuse(flow, "CONNECT", auth)
            return
        self.connect[self._connection_id(flow)] = auth
        self.scope.http_connect(flow)

    async def request(self, flow) -> None:
        lane = self._lane(flow)
        if lane == "control":
            _, program = self._take(flow)
            for name in ("Authorization", "x-api-key"):
                if name in flow.request.headers:
                    del flow.request.headers[name]
            if urlsplit(flow.request.pretty_url).path == \
                    "/api/oauth/claude_cli/create_api_key":
                self._refuse_control(flow, program, "create_api_key refused")
                return
            if not config.CONTROL_AUTHORIZATION:
                self._refuse_control(flow, program, "control authorization unavailable", 503)
                return
            await self.scope.request(flow)
            receipt = flow.metadata.get("rk")
            if receipt and receipt.get("decision") == "allowed":
                receipt["lane"] = "control"
                flow.request.headers["Authorization"] = config.CONTROL_AUTHORIZATION
                receipt["request_wire_sha"] = self.scope.store.put(
                    scope_addon.canonical(
                        f"{flow.request.method} {flow.request.pretty_url}",
                        list(flow.request.headers.items(True)),
                        flow.request.content or b""))
                notes = json.loads(receipt.get("notes") or "{}")
                notes["control_authorization"] = "proxy-injected"
                receipt["notes"] = json.dumps(notes)
            return
        if lane != "agent":
            self._take(flow)
            await self.scope.request(flow)
            return
        auth = self._take(flow)
        identity = flow.request.headers.get(config.IDENTITY_HEADER, "")
        if not all(auth) or not self._authorized(
                *auth, flow.request.method, flow.request.pretty_url, identity):
            self._refuse(flow, "request", auth)
            return
        await self.scope.request(flow)
        receipt = flow.metadata.get("rk")
        if receipt and receipt.get("decision") == "allowed":
            self.live[flow.id] = auth

    def server_connect(self, data) -> None:
        self.scope.server_connect(data)

    async def response(self, flow) -> None:
        auth = self.live.get(flow.id)
        try:
            await self.scope.response(flow)
            receipt = flow.metadata.get("rk")
            if not auth or not receipt or receipt.get("decision") != "allowed":
                return
            identity = config.IDENTITIES.get(receipt.get("identity"), {})
            receipt_id = rk.write_capability_receipt(
                auth[1], auth[0], receipt, identity.get("entity_id"))
            flow.response.headers["X-RedKraken-Receipt"] = receipt_id
        except rk.SqlError:
            flow.response = http.Response.make(
                502, '{"error":"receipt write refused"}\n',
                {"Content-Type": "application/json",
                 "X-RedKraken-Decision": "receipt-refused"},
            )
        finally:
            self.live.pop(flow.id, None)

    def error(self, flow) -> None:
        try:
            self.scope.error(flow)
        finally:
            self.live.pop(flow.id, None)


addons = [CapabilityProxy(scope_addon.addons[0])]
