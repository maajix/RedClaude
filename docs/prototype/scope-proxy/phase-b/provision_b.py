#!/usr/bin/env python3
"""PROTOTYPE Phase B provisioning, run from the HOST.

This stands in for the v2 runtime, which lives on the host (decision Q30) and
holds the credential store. It reaches the provisioning listener on the proxy's
egress address -- the address the agent container has no route to.

Stdlib only so it runs anywhere.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request

PROV = "http://172.31.250.10:18081"
TARGET = "http://fixture:18099"
CREDS = [("userA", "alice", "alice-pw-9f3c"), ("userB", "bob", "bob-pw-27ae")]

def opener() -> urllib.request.OpenerDirector:
    """A FRESH client per identity, never a shared one.

    Sharing one cookie jar across identities means identity B logs in carrying
    identity A's session cookie -- and a target that rotates the session id on
    login (as it should) destroys A's session in the process. The runtime holds
    every credential, so it is the one place where two identities can quietly
    contaminate each other.
    """
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROV, "https": PROV}),
        urllib.request.HTTPCookieProcessor(),
    )


def fetch(client, url: str, identity: str,
          data: bytes | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("X-RedKraken-Identity", identity)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with client.open(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    bad = 0
    for identity, user, password in CREDS:
        client = opener()
        status, body = fetch(client, f"{TARGET}/login", identity)
        found = re.search(r'name="csrf_token" value="([^"]+)"', body)
        if not found:
            print(f"  FAIL  {identity}: no csrf on /login (HTTP {status})")
            bad += 1
            continue
        payload = urllib.parse.urlencode({
            "user": user, "password": password, "csrf_token": found.group(1),
        }).encode()
        status, body = fetch(client, f"{TARGET}/login", identity, payload)
        ok = status == 200 and '"ok": true' in body
        print(f"  {'PASS' if ok else 'FAIL'}  provisioned {identity} -> {user} "
              f"[HTTP {status}]")
        bad += 0 if ok else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
