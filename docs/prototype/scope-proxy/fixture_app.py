#!/usr/bin/env python3
"""PROTOTYPE target app. Throwaway; state is in memory and dies with the process.

Exists because the real target (yekta-it.de) has a CAPTCHA on /user/login and a
closed /user/register, so there is no way to drive two authenticated identities
against it. This app supplies the half of ticket 04 that needs a login, a
session cookie, and a CSRF token whose shape I control; yekta-it.de supplies the
half that needs real TLS and a real server.

Deliberately includes session-id rotation on login, because a jar that survives
rotation is the only proof the proxy is tracking a session rather than replaying
one cookie value.
"""

from __future__ import annotations

import html
import json
import secrets
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

USERS = {"alice": "alice-pw-9f3c", "bob": "bob-pw-27ae"}
SESSIONS: dict[str, dict] = {}
NOTES: dict[str, list[str]] = {"alice": [], "bob": []}
COOKIE = "FIXTSESS"


def new_session(user: str | None = None) -> str:
    sid = secrets.token_hex(16)
    SESSIONS[sid] = {"user": user, "csrf": secrets.token_hex(16)}
    return sid


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "redkraken-fixture/0"

    def log_message(self, *args):  # quiet
        pass

    # -- helpers ---------------------------------------------------------
    def session(self) -> tuple[str, dict]:
        raw = self.headers.get("Cookie", "")
        jar = SimpleCookie()
        jar.load(raw) if raw else None
        sid = jar[COOKIE].value if COOKIE in jar else ""
        if sid not in SESSIONS:
            sid = new_session()
            self._set_cookie = sid
        return sid, SESSIONS[sid]

    def send(self, code: int, body: str, ctype="text/html; charset=utf-8",
             extra: dict | None = None) -> None:
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        if getattr(self, "_set_cookie", ""):
            self.send_header(
                "Set-Cookie",
                f"{COOKIE}={self._set_cookie}; Path=/; HttpOnly; SameSite=Lax",
            )
            self._set_cookie = ""
        if getattr(self, "_set_xsrf", ""):
            # Deliberately NOT HttpOnly: this is the double-submit pattern, where
            # page JS is supposed to read the cookie and echo it in a header.
            # It is the case that breaks hardest when a proxy owns the cookies.
            self.send_header(
                "Set-Cookie", f"XSRF={self._set_xsrf}; Path=/; SameSite=Lax")
            self._set_xsrf = ""
        self.end_headers()
        self.wfile.write(raw)

    def form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    # -- routes ----------------------------------------------------------
    def do_GET(self):
        self._set_cookie = ""
        self._set_xsrf = ""
        path = urlsplit(self.path).path
        sid, sess = self.session()
        user = sess["user"]

        if path == "/":
            return self.send(200, "<h1>fixture</h1><p>public</p>")

        if path == "/login":
            return self.send(200,
                '<form method="post" action="/login">'
                f'<input type="hidden" name="csrf_token" value="{sess["csrf"]}">'
                '<input name="user"><input name="password" type="password">'
                '<button>go</button></form>')

        if path == "/whoami":
            return self.send(200, json.dumps({
                "user": user,
                "session_tail": sid[-6:],
                # Proof of what actually arrived. If the agent held a cookie
                # this would still be true -- what matters is that the receipt
                # shows the agent never sent one.
                "cookie_header_seen": bool(self.headers.get("Cookie")),
                "authorization_seen": bool(self.headers.get("Authorization")),
            }, indent=2), "application/json")

        if path == "/notes":
            if not user:
                return self.send(401, json.dumps({"error": "not logged in"}),
                                 "application/json")
            items = "".join(f"<li>{html.escape(n)}</li>" for n in NOTES[user])
            return self.send(200,
                f'<ul>{items}</ul><form method="post" action="/note">'
                f'<input type="hidden" name="csrf_token" value="{sess["csrf"]}">'
                '<input name="text"><button>add</button></form>')

        if path == "/xhr":
            self._set_xsrf = sess["csrf"]
            return self.send(200, """<html><body><h1>xhr</h1><script>
(async () => {
  const m = document.cookie.match(/(?:^|; )XSRF=([^;]*)/);
  const token = m ? m[1] : "";
  let status = 0, body = "";
  try {
    const r = await fetch("/xhr-note", {
      method: "POST",
      headers: {"X-CSRF-Token": token, "Content-Type": "application/json"},
      body: JSON.stringify({text: "from-browser"}),
    });
    status = r.status; body = await r.text();
  } catch (e) { body = String(e); }
  window.__rk = {cookie: document.cookie, token_seen_by_js: token,
                 status: status, body: body};
})();
</script></body></html>""")

        if path == "/danger":
            return self.send(200, "EXCLUDED PATH REACHED -- proxy failed")

        if path == "/redirect-out":
            return self.send(302, "", extra={"Location": "https://example.com/"})

        if path == "/redirect-in":
            return self.send(302, "", extra={"Location": "/whoami"})

        if path == "/slow":
            time.sleep(0.2)
            return self.send(200, "slow ok")

        return self.send(404, "nope")

    def do_POST(self):
        self._set_cookie = ""
        self._set_xsrf = ""
        path = urlsplit(self.path).path
        sid, sess = self.session()
        fields = self.form()

        if path == "/login":
            if fields.get("csrf_token") != sess["csrf"]:
                return self.send(403, json.dumps({"error": "bad csrf"}),
                                 "application/json")
            user = fields.get("user", "")
            if USERS.get(user) != fields.get("password"):
                return self.send(403, json.dumps({"error": "bad credentials"}),
                                 "application/json")
            SESSIONS.pop(sid, None)
            self._set_cookie = new_session(user)  # rotate on privilege change
            return self.send(200, json.dumps({"ok": True, "user": user}),
                             "application/json")

        if path == "/note":
            if not sess["user"]:
                return self.send(401, json.dumps({"error": "not logged in"}),
                                 "application/json")
            if fields.get("csrf_token") != sess["csrf"]:
                return self.send(403, json.dumps({
                    "error": "bad csrf",
                    "got": fields.get("csrf_token", "")[:8],
                }), "application/json")
            NOTES[sess["user"]].append(fields.get("text", ""))
            return self.send(200, json.dumps({
                "ok": True, "user": sess["user"], "notes": NOTES[sess["user"]],
            }), "application/json")

        if path == "/xhr-note":
            # Double-submit: the header must echo the non-HttpOnly cookie. The
            # server never looks at the form body for a token.
            if not sess["user"]:
                return self.send(401, json.dumps({"error": "not logged in"}),
                                 "application/json")
            sent = self.headers.get("X-CSRF-Token", "")
            if sent != sess["csrf"]:
                return self.send(403, json.dumps({
                    "error": "bad double-submit token",
                    "got": sent[:8] or "(empty)",
                }), "application/json")
            NOTES[sess["user"]].append("xhr")
            return self.send(200, json.dumps({"ok": True, "user": sess["user"]}),
                             "application/json")

        return self.send(404, "nope")


if __name__ == "__main__":
    import os
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    # Loopback by default so Phase A never exposes the fixture; Phase B needs
    # it on the container's network interface instead.
    bind = os.environ.get("RK_FIXTURE_BIND", "127.0.0.1")
    print(f"[fixture] http://{bind}:{port}", flush=True)
    ThreadingHTTPServer((bind, port), Handler).serve_forever()
