"""PROTOTYPE mitmproxy addon: the v2 scope proxy.

Throwaway. Written fresh rather than ported from v1's `scope_proxy.py`, because
v1's addon is welded to `engagement.yaml`, a jsonl audit lane, and an nftables
containment module that v2 replaces with Postgres and container topology. What
carried over is three ideas, not code:

  * two timestamps per request -- arrival and post-throttle egress. Arrival
    timestamps are queue arrivals and cannot be shown to a program as proof of
    a rate; only the egress stamp can.
  * a blocked request is a synthesized 451 carrying its reason, never a dropped
    connection, so the agent gets a readable answer and the block is evidence.
  * parse the whole policy before deciding anything, so a malformed entry fails
    closed instead of being skipped past into an allow.

Run:  mitmdump -s addon.py --listen-port 8080
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import time
import ipaddress
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mitmproxy import http  # noqa: E402

import config  # noqa: E402
import policy  # noqa: E402
from budget import Budgets  # noqa: E402
from identity import IdentityStore  # noqa: E402
from receipts import Store, canonical  # noqa: E402

OUT = Path(os.environ.get("RK_OUT", HERE / "out"))


class ScopeProxy:
    def __init__(self) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        self.store = Store(OUT)
        self.identities = IdentityStore(config.IDENTITIES, OUT / "jars.json")
        self.budgets = Budgets(config.TARGETS)
        self.targets = {t["id"]: t for t in config.TARGETS}
        # host:port -> addresses the policy approved for it. Consumed by
        # `server_connect` so the connection lands on the address that was
        # actually checked, closing the DNS-rebinding window between the check
        # and the connect.
        self.pinned: dict[tuple[str, int], list[str]] = {}
        self.held: dict[str, str] = {}  # flow id -> target id holding a slot
        print(f"[scope-proxy] receipts -> {OUT/'PROTOTYPE-wipe-me.sqlite'}", flush=True)

    # ------------------------------------------------------------------
    def _block(self, flow: http.HTTPFlow, decision, receipt: dict) -> None:
        receipt.update(decision="blocked", reason=decision.reason,
                       target_id=decision.target_id)
        body = json.dumps({
            "blocked_by": "redkraken-scope-proxy",
            "reason": decision.reason,
            "receipt_id": receipt["receipt_id"],
        }, indent=2) + "\n"
        flow.response = http.Response.make(
            451, body,
            {"Content-Type": "application/json",
             "X-RedKraken-Decision": "blocked",
             "X-RedKraken-Receipt": receipt["receipt_id"]},
        )

    def http_connect(self, flow: http.HTTPFlow) -> None:
        """Deny at CONNECT, before any socket to the target is opened.

        This is not belt-and-braces. mitmproxy's default `connection_strategy`
        is `eager`, which opens the upstream connection while handling CONNECT
        -- i.e. BEFORE the `request` hook that holds the scope check. Relying on
        `request` alone means an out-of-scope HTTPS host still receives a TCP
        connection and a TLS handshake, which is already contact. The host-level
        decision is available here, so it is made here; path-level rules still
        run later in `request`.
        """
        url = f"https://{flow.request.host}:{flow.request.port}/"
        decision = policy.decide(url, config.TARGETS)
        if not decision.allowed:
            flow.response = http.Response.make(
                451,
                json.dumps({"blocked_by": "redkraken-scope-proxy",
                            "at": "CONNECT",
                            "reason": decision.reason}, indent=2) + "\n",
                {"Content-Type": "application/json",
                 "X-RedKraken-Decision": "blocked-at-connect"},
            )
            self.store.write({
                "receipt_id": hashlib.sha256(
                    f"{flow.id}:connect".encode()).hexdigest()[:32],
                "ts_arrival": time.time(),
                "lane": ("provisioning"
                         if flow.client_conn.sockname[1] == config.PROVISION_PORT
                         else "agent"),
                "decision": "blocked",
                "reason": f"CONNECT: {decision.reason}",
                "target_id": decision.target_id,
                "method": "CONNECT",
                "host": flow.request.host,
                "port": flow.request.port,
                "path": "",
                "identity": "none",
                "request_agent_sha": "",
                "request_wire_sha": "",
            })
        else:
            self.pinned[(decision.host, decision.port)] = decision.pinned

    async def request(self, flow: http.HTTPFlow) -> None:
        ts_arrival = time.time()
        req = flow.request
        url = req.pretty_url
        parts = urlsplit(url)

        # Which listener the client reached decides whether it is allowed to
        # carry a credential. The agent can neither see nor set this.
        lane = ("provisioning"
                if flow.client_conn.sockname[1] == config.PROVISION_PORT
                else "agent")

        identity = req.headers.get(config.IDENTITY_HEADER, "")
        if config.IDENTITY_HEADER in req.headers:
            del req.headers[config.IDENTITY_HEADER]
        csrf_raw = config.CSRF_RAW_HEADER in req.headers
        if csrf_raw:
            del req.headers[config.CSRF_RAW_HEADER]

        # Hash what the AGENT sent, before any injection. This is the artifact a
        # subagent is allowed to cite; it contains no credential material.
        agent_bytes = canonical(
            f"{req.method} {url}", list(req.headers.items(True)), req.content or b""
        )
        receipt = {
            "receipt_id": hashlib.sha256(
                f"{flow.id}:{ts_arrival}".encode()).hexdigest()[:32],
            "ts_arrival": ts_arrival,
            "lane": lane,
            "identity": identity or "none",
            "method": req.method,
            "scheme": parts.scheme,
            "host": parts.hostname or "",
            "port": parts.port or (443 if parts.scheme == "https" else 80),
            "path": parts.path or "/",
            "query_sha256": hashlib.sha256(
                (parts.query or "").encode()).hexdigest() if parts.query else "",
            "request_agent_sha": self.store.put(agent_bytes),
            "request_wire_sha": "",
            "pinned_ips": "",
            "notes": "{}",
        }
        flow.metadata["rk"] = receipt

        decision = policy.decide(url, config.TARGETS)
        if not decision.allowed:
            self._block(flow, decision, receipt)
            self.store.write(receipt)
            return

        receipt.update(target_id=decision.target_id, reason=decision.reason,
                       pinned_ips=",".join(decision.pinned))
        self.pinned[(decision.host, decision.port)] = decision.pinned

        target = self.targets.get(decision.target_id)
        notes: dict = {"lane": lane}
        if lane == "provisioning":
            # The runtime is establishing the session, so it sends the
            # credential and the proxy leaves it alone. Nothing is injected;
            # the jar is filled from the response instead.
            notes["identity"] = identity or "none"
            notes["provisioning"] = "credential passed through unmodified"
        elif identity:
            # The token the agent needs may not exist yet, or may be bound to a
            # session that has since rotated (logging in rotates it, which is
            # exactly the case that matters). Fetch one first.
            if self.identities.needs_csrf(identity, url, decision.host,
                                          req.method, target, csrf_raw):
                notes["csrf_refetch"] = await self._refresh_csrf(
                    identity, parts, target, lane)
            notes.update(self.identities.inject(
                identity, url, decision.host, req.method, req.headers,
                lambda: req.content or b"", lambda b: setattr(req, "content", b),
                target, csrf_raw,
            ))
        elif "cookie" in req.headers:
            # No identity claimed but a cookie present: the agent is carrying
            # its own session, which is the thing this design exists to prevent.
            del req.headers["cookie"]
            notes.update({"agent_sent_cookie": True, "identity": "none"})

        # Only now is the request credential-bearing, so hash it separately.
        receipt["request_wire_sha"] = self.store.put(canonical(
            f"{req.method} {url}", list(req.headers.items(True)), req.content or b""
        ))

        budget = self.budgets.get(decision.target_id)
        if budget is not None:
            await budget.slots.acquire()
            self.held[flow.id] = decision.target_id
            notes["waited_ms"] = round(await budget.throttle(), 1)
            receipt["waited_ms"] = notes["waited_ms"]

        # Stamped AFTER the bucket, so this is the enforced egress rate and not
        # the arrival rate.
        receipt["ts_egress"] = time.time()
        receipt["decision"] = "allowed"
        receipt["notes"] = json.dumps(notes)

    # ------------------------------------------------------------------
    async def _refresh_csrf(self, identity: str, parts, target: dict,
                            lane: str) -> dict:
        """Proxy-originated fetch of a CSRF token, on the same terms as the agent.

        Finding this prototype produced: a proxy that owns the session must also
        own token acquisition, because a token is bound to the session and the
        agent can never hold either. That makes the proxy a client of the target
        in its own right -- so this path is scope-checked, charged to the target
        budget, and receipted. Skipping any of the three would put unmetered,
        unreceipted traffic on a live target under the runtime's own name.

        Known prototype gap: the fetch uses urllib, so `server_connect`'s address
        pin does not apply to it -- the scope decision below re-resolves and
        re-validates, but the window between that check and urllib's own resolve
        is open. In v2 this fetch goes back through the proxy's own egress path.
        """
        source = str(target["csrf"]["extract"]["source"])
        base = f"{parts.scheme}://{parts.netloc}"
        decision = policy.decide(base.rstrip("/") + "/" + source.lstrip("/"),
                                 config.TARGETS)
        if not decision.allowed:
            return {"blocked": decision.reason}

        ts_arrival = time.time()
        budget = self.budgets.get(decision.target_id)
        waited = round(await budget.throttle(), 1) if budget else 0.0
        result = await asyncio.to_thread(
            self.identities.refresh_csrf, identity, base, decision.host, target)
        body = result.pop("body", b"")

        self.store.write({
            "receipt_id": hashlib.sha256(
                f"csrf:{identity}:{ts_arrival}".encode()).hexdigest()[:32],
            "ts_arrival": ts_arrival,
            "ts_egress": time.time(),
            "waited_ms": waited,
            # Not "agent": nothing the agent did produced this request directly,
            # and a receipt that claimed otherwise would misattribute it.
            "lane": "proxy-internal",
            "decision": "allowed" if not result.get("error") else "error",
            "reason": f"csrf refetch for {lane} lane: {decision.reason}",
            "target_id": decision.target_id,
            "identity": identity,
            "method": "GET",
            "scheme": parts.scheme,
            "host": decision.host,
            "port": decision.port,
            "path": "/" + source.lstrip("/"),
            "pinned_ips": ",".join(decision.pinned),
            "status_code": result.get("status") or None,
            "response_wire_sha": self.store.put(body) if body else "",
            "notes": json.dumps(result),
        })
        return result

    # ------------------------------------------------------------------
    def server_connect(self, data) -> None:
        """Pin the connection to an address the policy already approved."""
        if data.server.address is None:
            return
        host, port = data.server.address[0], data.server.address[1]
        try:
            ipaddress.ip_address(host)
            return  # already an address; nothing to rebind
        except ValueError:
            pass
        approved = self.pinned.get((host.lower(), port))
        if approved:
            # SNI was set from the hostname when the connection object was
            # built, so TLS still validates against the name while the socket
            # goes to the checked address.
            data.server.address = (approved[0], port)

    # ------------------------------------------------------------------
    def _release(self, flow: http.HTTPFlow) -> None:
        target_id = self.held.pop(flow.id, None)
        if target_id:
            budget = self.budgets.get(target_id)
            if budget is not None:
                budget.slots.release()

    async def response(self, flow: http.HTTPFlow) -> None:
        receipt = flow.metadata.get("rk")
        if not receipt:
            return
        try:
            resp = flow.response
            if resp is None or receipt.get("decision") == "blocked":
                return

            receipt["status_code"] = resp.status_code
            # Wire response first: it still carries Set-Cookie, so it is the
            # credential-bearing artifact that has to be encrypted in v2.
            receipt["response_wire_sha"] = self.store.put(canonical(
                f"HTTP {resp.status_code}", list(resp.headers.items(True)),
                resp.content or b""
            ))

            notes = json.loads(receipt.get("notes") or "{}")
            identity = receipt.get("identity") or "none"
            target = self.targets.get(receipt.get("target_id") or "")
            if identity != "none":
                notes.update(self.identities.capture(
                    identity, flow.request.pretty_url, receipt["host"],
                    resp.headers, resp.content or b"", target,
                    strip=(receipt.get("lane") != "provisioning"),
                ))
                self.identities.save()
            elif "set-cookie" in resp.headers:
                del resp.headers["set-cookie"]
                notes["cookies_stored"] = ["dropped: no identity claimed"]

            # A redirect is a scope decision the agent never gets to make. The
            # client would follow it and come back through here anyway, but
            # blocking at the redirect names the cause instead of reporting a
            # second, apparently unrelated block.
            if 300 <= resp.status_code < 400 and "location" in resp.headers:
                location = urljoin(flow.request.pretty_url, resp.headers["location"])
                onward = policy.decide(location, config.TARGETS)
                if not onward.allowed:
                    notes["redirect_blocked"] = {"to": location, "why": onward.reason}
                    flow.response = http.Response.make(
                        451,
                        json.dumps({"blocked_by": "redkraken-scope-proxy",
                                    "reason": f"redirect to out-of-scope: {onward.reason}",
                                    "location": location,
                                    "receipt_id": receipt["receipt_id"]}, indent=2) + "\n",
                        {"Content-Type": "application/json",
                         "X-RedKraken-Decision": "redirect-blocked",
                         "X-RedKraken-Receipt": receipt["receipt_id"]},
                    )
                    resp = flow.response
                    receipt["decision"] = "redirect-blocked"

            receipt["response_agent_sha"] = self.store.put(canonical(
                f"HTTP {resp.status_code}", list(resp.headers.items(True)),
                resp.content or b""
            ))
            resp.headers["X-RedKraken-Receipt"] = receipt["receipt_id"]
            receipt["notes"] = json.dumps(notes)
            self.store.write(receipt)
        finally:
            self._release(flow)

    def error(self, flow: http.HTTPFlow) -> None:
        receipt = flow.metadata.get("rk")
        if receipt and receipt.get("decision") != "blocked":
            receipt["decision"] = "error"
            receipt["reason"] = str(flow.error)
            self.store.write(receipt)
        self._release(flow)


addons = [ScopeProxy()]
