#!/usr/bin/env python3
"""PROTOTYPE Phase A driver. Prints full state after every step.

Two clients on purpose:

  * `runtime` talks to the PROVISIONING listener and is allowed to hold a
    password. It stands in for the v2 runtime that owns 1Password and the KEK.
  * `agent` talks to the AGENT listener and only ever sends an identity name.
    Every assertion about credential isolation is made against this client.

The strongest single assertion in here is the last one: after the whole run,
`agent.cookies` is empty. The agent-side process holds zero cookie bytes, not
because it was careful, but because it was never given any.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
CA = OUT / "ca" / "mitmproxy-ca-cert.pem"

AGENT = "http://127.0.0.1:18080"
PROV = "http://127.0.0.1:18081"
FIX = "http://127.0.0.1:18099"
REAL = "https://yekta-it.de"

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""),
          flush=True)


def ident(name: str, **extra) -> dict:
    return {"X-RedKraken-Identity": name, **extra}


def csrf_of(body: str) -> str:
    found = re.search(r'name="csrf_token" value="([^"]+)"', body)
    return found.group(1) if found else ""


# ---------------------------------------------------------------- provisioning
def provision(identity: str, user: str, password: str) -> None:
    """Runtime lane: log in with a real credential, over a receipted path."""
    with httpx.Client(proxy=PROV, follow_redirects=False, timeout=20) as runtime:
        page = runtime.get(f"{FIX}/login", headers=ident(identity))
        token = csrf_of(page.text)
        done = runtime.post(
            f"{FIX}/login",
            data={"user": user, "password": password, "csrf_token": token},
            headers=ident(identity),
        )
        check(done.status_code == 200 and done.json().get("ok"),
              f"provision {identity} -> {user}", f"HTTP {done.status_code}")


# ------------------------------------------------------------------------ main
def main() -> int:
    print("\n=== 1. provisioning lane (runtime holds the password) ===", flush=True)
    provision("userA", "alice", "alice-pw-9f3c")
    provision("userB", "bob", "bob-pw-27ae")

    agent = httpx.Client(proxy=AGENT, follow_redirects=False, timeout=30,
                         verify=str(CA))

    print("\n=== 2. agent lane: two identities, one target ===", flush=True)
    who_a = agent.get(f"{FIX}/whoami", headers=ident("userA")).json()
    who_b = agent.get(f"{FIX}/whoami", headers=ident("userB")).json()
    print(f"    userA -> {who_a}\n    userB -> {who_b}", flush=True)
    check(who_a["user"] == "alice", "userA resolves to alice")
    check(who_b["user"] == "bob", "userB resolves to bob")
    check(who_a["session_tail"] != who_b["session_tail"],
          "identities hold distinct sessions",
          f"{who_a['session_tail']} vs {who_b['session_tail']}")
    check(who_a["cookie_header_seen"] and who_b["cookie_header_seen"],
          "server received a cookie (proxy injected it)")

    anon = agent.get(f"{FIX}/whoami").json()
    check(anon["user"] is None, "no identity header -> no session", str(anon["user"]))

    print("\n=== 3. CSRF: agent never learns the token it needs ===", flush=True)
    # The agent writes a placeholder. The proxy substitutes the real token.
    # It cannot use the token it captured before the login: logging in rotated
    # the session, and the token was bound to the session it came from -- so the
    # proxy fetches a fresh one itself, over a receipted, rate-limited path.
    note_a = agent.post(f"{FIX}/note",
                        data={"text": "alice-note", "csrf_token": "PLACEHOLDER"},
                        headers=ident("userA"))
    check(note_a.status_code == 200, "userA POST /note accepted",
          f"HTTP {note_a.status_code} {note_a.text[:80]}")
    if note_a.status_code == 200:
        check(note_a.json()["user"] == "alice", "note landed on alice")

    raw = agent.post(f"{FIX}/note",
                     data={"text": "should-fail", "csrf_token": "PLACEHOLDER"},
                     headers=ident("userA", **{"X-RedKraken-Csrf-Raw": "1"}))
    check(raw.status_code == 403, "csrf-raw opt-out is honoured (403 expected)",
          f"HTTP {raw.status_code}")

    note_b = agent.post(f"{FIX}/note",
                        data={"text": "bob-note", "csrf_token": "PLACEHOLDER"},
                        headers=ident("userB"))
    if note_b.status_code == 200:
        check(note_b.json()["user"] == "bob", "note landed on bob")
        check("alice-note" not in note_b.text, "bob cannot see alice's notes")

    print("\n=== 4. agent holds no credential material ===", flush=True)
    for name, resp in (("whoami", agent.get(f"{FIX}/whoami", headers=ident("userA"))),):
        check("set-cookie" not in {k.lower() for k in resp.headers},
              f"no Set-Cookie reaches the agent ({name})")
    check(len(agent.cookies.jar) == 0, "agent-side cookie jar is EMPTY",
          f"{len(agent.cookies.jar)} cookies")

    # An agent that tries to smuggle its own cookie gets it stripped.
    smuggle = agent.get(f"{FIX}/whoami",
                        headers=ident("userA", Cookie="FIXTSESS=stolen"))
    check(smuggle.json()["user"] == "alice",
          "agent-supplied Cookie is stripped, jar value wins")

    print("\n=== 5. scope enforcement below the agent ===", flush=True)
    cases = [
        # HTTPS is blocked at CONNECT, before a socket to the target exists, so
        # there is no tunnel to carry a 451 body -- the client sees the proxy
        # refuse the tunnel. That is the stronger outcome, not a weaker one: a
        # 451 body would mean the TLS handshake already happened.
        ("out of scope host (refused at CONNECT)", "https://example.com/", "connect"),
        ("excluded path", f"{FIX}/danger", 451),
        ("DNS rebinding (localtest.me -> loopback)", "http://localtest.me:18099/", 451),
        ("redirect to out-of-scope", f"{FIX}/redirect-out", 451),
        ("in-scope redirect survives", f"{FIX}/redirect-in", 302),
    ]
    for label, url, expect in cases:
        try:
            resp = agent.get(url, headers=ident("userA"))
            body = resp.text[:120].replace("\n", " ")
            check(expect != "connect" and resp.status_code == expect, label,
                  f"HTTP {resp.status_code}: {body}")
        except Exception as exc:  # noqa: BLE001
            check(expect == "connect" and "451" in str(exc), label,
                  f"{type(exc).__name__}: {exc}")

    print("\n=== 6. TLS interception + per-target rate limit (real target) ===",
          flush=True)
    started = time.monotonic()
    codes = []
    for _ in range(6):
        try:
            resp = agent.get(f"{REAL}/", headers=ident("anonYekta"))
            codes.append(resp.status_code)
        except Exception as exc:  # noqa: BLE001
            codes.append(f"{type(exc).__name__}")
    elapsed = time.monotonic() - started
    print(f"    codes={codes} elapsed={elapsed:.2f}s", flush=True)
    check(all(c == 200 for c in codes), "6x GET https://yekta-it.de through MITM",
          str(codes))
    # rps=2, burst=2 -> 6 requests cannot clear in under ~2s
    check(elapsed >= 1.8, "per-target rate limit held (2 rps, burst 2)",
          f"{elapsed:.2f}s for 6 requests")

    agent.close()

    print("\n=== 7. receipts ===", flush=True)
    db = sqlite3.connect(OUT / "PROTOTYPE-wipe-me.sqlite")
    total, allowed, blocked = db.execute(
        "SELECT count(*), sum(decision='allowed'), "
        "sum(decision LIKE '%blocked%') FROM receipts").fetchone()
    print(f"    receipts={total} allowed={allowed} blocked={blocked}", flush=True)
    check(total > 0, "receipts emitted", f"{total} rows")
    check((blocked or 0) >= 4, "blocked requests are receipted too",
          f"{blocked} blocked rows")

    dual = db.execute(
        "SELECT count(*) FROM receipts WHERE request_agent_sha != request_wire_sha "
        "AND request_wire_sha != ''").fetchone()[0]
    check(dual > 0, "agent-visible and wire artifacts diverge (injection proven)",
          f"{dual} rows")

    lanes = dict(db.execute("SELECT lane, count(*) FROM receipts GROUP BY lane"))
    print(f"    lanes={lanes}", flush=True)
    check(lanes.get("provisioning", 0) > 0 and lanes.get("agent", 0) > 0,
          "both lanes receipted")
    check(lanes.get("proxy-internal", 0) > 0,
          "proxy's own CSRF fetches are receipted too",
          f"{lanes.get('proxy-internal', 0)} rows")

    print("\n    sample rows:", flush=True)
    for row in db.execute(
        "SELECT decision, lane, identity, method, host, path, status_code, "
        "waited_ms, substr(reason,1,54) FROM receipts ORDER BY ts_arrival LIMIT 40"
    ):
        print("      " + " | ".join("" if c is None else str(c) for c in row),
              flush=True)

    art = list((OUT / "artifacts").rglob("*"))
    check(len([p for p in art if p.is_file()]) > 0, "content-addressed artifacts on disk",
          f"{len([p for p in art if p.is_file()])} blobs")

    print("\n=== summary ===", flush=True)
    failed = [name for ok, name, _ in RESULTS if not ok]
    print(f"  {len(RESULTS) - len(failed)}/{len(RESULTS)} passed", flush=True)
    for name in failed:
        print(f"  FAILED: {name}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
