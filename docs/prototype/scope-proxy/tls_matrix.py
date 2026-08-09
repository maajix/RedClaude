#!/usr/bin/env python3
"""PROTOTYPE: what TLS interception costs, measured against a real target.

Ticket 04 asks what breaks with TLS interception against real targets and what a
client has to trust. Both halves are measurable rather than arguable, so this
script measures them: it handshakes with yekta-it.de four ways -- directly, and
through the proxy under three different trust configurations -- and prints the
negotiated parameters and the certificate each way produced.

Raw sockets rather than httpx, deliberately. The question is about the TLS layer
itself (version, cipher, ALPN, chain), and an HTTP client hides all four behind
a response object.
"""

from __future__ import annotations

import json
import socket
import ssl
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CA = HERE / "out" / "ca" / "mitmproxy-ca-cert.pem"
PROXY = ("127.0.0.1", 18080)
HOST, PORT = "yekta-it.de", 443

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""),
          flush=True)


def _connect_via_proxy() -> socket.socket:
    sock = socket.create_connection(PROXY, timeout=15)
    sock.sendall(
        f"CONNECT {HOST}:{PORT} HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n\r\n".encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    status = buf.split(b"\r\n", 1)[0].decode("latin-1")
    if b" 200 " not in buf.split(b"\r\n", 1)[0]:
        sock.close()
        raise RuntimeError(f"proxy refused CONNECT: {status}")
    return sock


def probe(label: str, *, via_proxy: bool, cafile: str | None,
          verify: bool = True, alpn: list[str] | None = None) -> dict:
    """One handshake. Returns what the client learned about the peer."""
    out: dict = {"label": label, "via_proxy": via_proxy, "verify": verify}
    try:
        if verify:
            ctx = ssl.create_default_context(cafile=cafile)
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(alpn or ["h2", "http/1.1"])

        raw = _connect_via_proxy() if via_proxy else socket.create_connection(
            (HOST, PORT), timeout=15)
        with ctx.wrap_socket(raw, server_hostname=HOST) as tls:
            out["tls_version"] = tls.version()
            out["cipher"] = tls.cipher()[0]
            out["alpn"] = tls.selected_alpn_protocol()
            der = tls.getpeercert(binary_form=True) or b""
            out["cert_sha256"] = __import__("hashlib").sha256(der).hexdigest()[:32]
            if verify:
                cert = tls.getpeercert() or {}
                issuer = {k: v for part in cert.get("issuer", ()) for k, v in part}
                subject = {k: v for part in cert.get("subject", ()) for k, v in part}
                out["issuer"] = issuer.get("commonName") or issuer.get(
                    "organizationName", "?")
                out["subject"] = subject.get("commonName", "?")
                out["not_after"] = cert.get("notAfter", "?")
            # Enough of a request to see whether the server answers at all.
            tls.sendall(
                f"GET / HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n"
                f"X-RedKraken-Identity: anonYekta\r\n\r\n".encode())
            head = tls.recv(2048).decode("latin-1", "replace")
            if out["alpn"] == "h2":
                # An HTTP/1.1 request over an h2 connection gets an h2 SETTINGS
                # frame back, not a status line. Say so rather than printing the
                # frame bytes as if they were text.
                out["http_status"] = "(h2 negotiated; HTTP/1.1 request not answered)"
            else:
                out["http_status"] = head.split("\r\n", 1)[0]
            out["hsts"] = any(line.lower().startswith("strict-transport-security")
                              for line in head.split("\r\n"))
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def show(result: dict) -> None:
    print(f"\n  --- {result['label']}", flush=True)
    for key in ("tls_version", "cipher", "alpn", "issuer", "subject", "not_after",
                "cert_sha256", "http_status", "hsts", "error"):
        if key in result:
            print(f"      {key:<13} {result[key]}", flush=True)


def curl(label: str, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                           "--max-time", "20", *args, f"https://{HOST}/"],
                          capture_output=True, text=True)
    detail = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    print(f"      {label:<34} rc={proc.returncode} {detail[:90]}", flush=True)
    return proc.returncode, detail


def main() -> int:
    if not CA.exists():
        print(f"missing CA at {CA}; start the proxy first (run_tls.sh)")
        return 2

    print("=== A. what the target's TLS actually is (no proxy) ===", flush=True)
    direct = probe("direct, system trust store", via_proxy=False, cafile=None)
    show(direct)
    check("error" not in direct, "direct handshake succeeded",
          direct.get("error", ""))

    print("\n=== B. what an agent behind the proxy sees ===", flush=True)
    proxied = probe("via proxy, trusting the run's CA", via_proxy=True,
                    cafile=str(CA))
    show(proxied)
    check("error" not in proxied, "proxied handshake succeeded",
          proxied.get("error", ""))

    print("\n=== C. a client that does NOT trust the run's CA ===", flush=True)
    untrusting = probe("via proxy, system trust store only", via_proxy=True,
                       cafile=None)
    show(untrusting)
    check("CERTIFICATE_VERIFY_FAILED" in untrusting.get("error", ""),
          "untrusting client fails closed, loudly",
          untrusting.get("error", "")[:90])

    print("\n=== D. the tempting shortcut: verification off ===", flush=True)
    blind = probe("via proxy, verification disabled", via_proxy=True,
                  cafile=None, verify=False)
    show(blind)
    check("error" not in blind, "verification-off client connects to anything",
          blind.get("error", ""))

    print("\n=== E. same proxy, client offering only http/1.1 ===", flush=True)
    forced = probe("via proxy, ALPN http/1.1 only", via_proxy=True,
                   cafile=str(CA), alpn=["http/1.1"])
    show(forced)
    check(forced.get("http_status", "").startswith("HTTP/1.1"),
          "http/1.1-only client gets a readable HTTP/1.1 answer",
          forced.get("http_status", forced.get("error", ""))[:60])

    print("\n=== what this costs ===", flush=True)
    if "error" not in direct and "error" not in proxied:
        check(direct.get("cert_sha256") != proxied.get("cert_sha256"),
              "the agent never sees the target's certificate",
              f"{direct.get('issuer')} vs {proxied.get('issuer')}")
        same_tls = direct.get("tls_version") == proxied.get("tls_version")
        same_cipher = direct.get("cipher") == proxied.get("cipher")
        same_alpn = direct.get("alpn") == proxied.get("alpn")
        print(f"      tls_version match: {same_tls} "
              f"({direct.get('tls_version')} vs {proxied.get('tls_version')})",
              flush=True)
        print(f"      cipher match:      {same_cipher} "
              f"({direct.get('cipher')} vs {proxied.get('cipher')})", flush=True)
        print(f"      alpn match:        {same_alpn} "
              f"({direct.get('alpn')} vs {proxied.get('alpn')})", flush=True)
        # Not an assertion about this target -- a statement about the class of
        # finding. Whatever these values are, they describe the PROXY's stack.
        print("      => every TLS-layer observation an agent makes describes the",
              flush=True)
        print("         proxy's stack, not the target's. TLS findings have to be",
              flush=True)
        print("         made by the runtime, out of band, over path A.", flush=True)
        if not same_alpn:
            print(f"      => AND the protocol itself diverges: the target speaks",
                  flush=True)
            print(f"         {direct.get('alpn')} but the agent is offered "
                  f"{proxied.get('alpn')}. mitmproxy negotiates its", flush=True)
            print("         client side independently of its server side, so an",
                  flush=True)
            print("         agent can 'confirm' HTTP/2 behaviour on a target that",
                  flush=True)
            print("         has none. Pin it with --set http2=false, or accept",
                  flush=True)
            print("         that no protocol-level finding is citable.", flush=True)

    print("\n=== what a non-Python client has to trust ===", flush=True)
    curl("curl + run CA", ["--proxy", f"http://{PROXY[0]}:{PROXY[1]}",
                           "--cacert", str(CA)])
    rc_bare, detail_bare = curl(
        "curl, no CA (expected failure)", ["--proxy", f"http://{PROXY[0]}:{PROXY[1]}"])
    check(rc_bare != 0, "curl fails without the run CA", f"rc={rc_bare}")
    print(f"      CA file: {CA}", flush=True)
    print("      Each runtime has its OWN trust store: Python needs the file or",
          flush=True)
    print("      SSL_CERT_FILE, curl needs --cacert or CURL_CA_BUNDLE, Node needs",
          flush=True)
    print("      NODE_EXTRA_CA_CERTS, Go needs SSL_CERT_FILE. One env var does not",
          flush=True)
    print("      cover them, which is why this belongs in the container image.",
          flush=True)

    print("\n=== summary ===", flush=True)
    failed = [name for ok, name, _ in RESULTS if not ok]
    print(f"  {len(RESULTS) - len(failed)}/{len(RESULTS)} passed", flush=True)
    for name in failed:
        print(f"  FAILED: {name}", flush=True)
    (HERE / "out" / "tls_matrix.json").write_text(
        json.dumps([direct, proxied, untrusting, blind, forced], indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
