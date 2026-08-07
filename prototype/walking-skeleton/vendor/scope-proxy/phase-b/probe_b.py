#!/usr/bin/env python3
"""PROTOTYPE Phase B probe. Runs INSIDE the agent container and tries to escape.

Stdlib only -- the point is that a bare container with nothing installed still
cannot get out, so installing nothing is part of the test.

Every check is written as "the agent attempts X", because that is the threat
model: the agent is not assumed to cooperate with the proxy, it is assumed to
try whatever a compromised or confused agent would try.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.request

LABEL = os.environ.get("RK_LABEL", "agent")
DNS_EXPECT = os.environ.get("RK_DNS_EXPECT", "open")
CA = "/out/ca/mitmproxy-ca-cert.pem"
PROXY = "http://proxy:18080"

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""),
          flush=True)


def note(name: str, detail: str) -> None:
    print(f"  ....  {name}: {detail}", flush=True)


def resolves(host: str) -> tuple[bool, str]:
    try:
        return True, socket.gethostbyname(host)
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def tcp(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "connected"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def via_proxy(url: str, identity: str = "") -> tuple[int, dict, str]:
    ctx = ssl.create_default_context(cafile=CA)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}),
        urllib.request.HTTPSHandler(context=ctx),
    )
    req = urllib.request.Request(url)
    if identity:
        req.add_header("X-RedKraken-Identity", identity)
    try:
        with opener.open(req, timeout=25) as resp:
            return resp.status, dict(resp.headers), resp.read().decode(
                "utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")


def default_route() -> str:
    try:
        with open("/proc/net/route") as handle:
            for line in handle.read().splitlines()[1:]:
                cols = line.split()
                if len(cols) > 2 and cols[1] == "00000000":
                    raw = bytes.fromhex(cols[2])
                    return ".".join(str(b) for b in reversed(raw))
    except OSError:
        pass
    return "none"


def main() -> int:
    print(f"\n=== {LABEL} ===", flush=True)
    note("default route", default_route())

    print("\n  -- can the agent reach anything on its own?", flush=True)
    ok, detail = tcp("1.1.1.1", 443)
    check(not ok, "raw TCP to the internet fails", detail[:70])

    ok, detail = resolves("fixture")
    check(not ok, "the target is not even resolvable from the agent", detail[:70])
    if ok:
        reachable, why = tcp(detail, 18099)
        check(not reachable, "the target is not reachable from the agent", why[:70])

    ok, detail = tcp("proxy", 18081)
    check(not ok, "the provisioning lane is unreachable from the agent",
          detail[:70])

    # Measured rather than assumed: an `internal: true` network closes external
    # DNS as well, so the embedded resolver is not a side channel here. The
    # hardened variant blackholes the upstream anyway and still resolves
    # container names, which is what makes it a safe default rather than a
    # trade-off.
    ok, detail = resolves("example.com")
    check(not ok, f"external DNS is closed ({DNS_EXPECT} config)", detail[:70])

    print("\n  -- what the agent CAN do, and only through the proxy", flush=True)
    ok, detail = resolves("proxy")
    check(ok, "the proxy is the one name that resolves", detail[:70])

    try:
        status, headers, body = via_proxy("http://fixture:18099/whoami", "userA")
        who = json.loads(body)
        check(status == 200 and who.get("user") == "alice",
              "proxied request reaches the target with an injected identity",
              f"HTTP {status} user={who.get('user')}")
        check("Set-Cookie" not in headers and "set-cookie" not in headers,
              "no credential material comes back to the agent")
        check(bool(headers.get("X-RedKraken-Receipt")),
              "every answer carries its receipt id",
              headers.get("X-RedKraken-Receipt", ""))
    except Exception as exc:  # noqa: BLE001
        check(False, "proxied request reaches the target", f"{type(exc).__name__}: {exc}")

    try:
        status, _, _ = via_proxy("https://yekta-it.de/", "anonYekta")
        check(status == 200, "proxied HTTPS to the real target works", f"HTTP {status}")
    except Exception as exc:  # noqa: BLE001
        check(False, "proxied HTTPS to the real target works",
              f"{type(exc).__name__}: {exc}")

    try:
        status, _, _ = via_proxy("https://example.com/", "userA")
        check(False, "out-of-scope host is refused through the proxy",
              f"unexpectedly got HTTP {status}")
    except Exception as exc:  # noqa: BLE001
        check("451" in str(exc), "out-of-scope host is refused through the proxy",
              f"{type(exc).__name__}: {str(exc)[:60]}")

    failed = [name for ok, name, _ in RESULTS if not ok]
    print(f"\n  {len(RESULTS) - len(failed)}/{len(RESULTS)} passed", flush=True)
    for name in failed:
        print(f"  FAILED: {name}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
