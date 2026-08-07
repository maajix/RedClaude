"""PROTOTYPE fixture: one app, two variants, one intended difference.

VARIANT=vuln   -> GET /api/notes/<id> serves any note (IDOR)
VARIANT=secure -> same route 403s unless the caller owns the note

Everything else in this file is shared by both variants by construction: there
is one source file and one flag, so "near-identical" is not a claim that has to
be maintained by hand. Deterministic session ids on purpose -- the comparability
probe compares response bytes across the two variants, so nothing may be random.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

VULN = os.environ.get("VARIANT", "vuln") == "vuln"

USERS = {
    "userA": {"id": 1, "password": "pw-a", "email": "a@example.test"},
    "userB": {"id": 2, "password": "pw-b", "email": "b@example.test"},
}
NOTES = {
    1: {"id": 1, "owner": 1, "title": "alpha", "body": "ALPHA-SECRET-0001"},
    2: {"id": 2, "owner": 2, "title": "bravo", "body": "BRAVO-SECRET-0002"},
}
# deterministic: sid is a pure function of the username
SESSIONS = {f"sid-{name}": USERS[name]["id"] for name in USERS}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fixture"
    sys_version = ""

    def log_message(self, fmt, *args):
        sys.stderr.write("fixture %s\n" % (fmt % args))

    def _send(self, code, payload):
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _uid(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sid="):
                return SESSIONS.get(part[4:])
        return None

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if path == "/login":
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            user = USERS.get(data.get("user", ""))
            if not user or user["password"] != data.get("password"):
                return self._send(401, {"error": "bad credentials"})
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "sid=sid-%s; Path=/" % data["user"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send(404, {"error": "not found"})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            # deliberately variant-blind: the probe diffs this
            return self._send(200, {"ok": True})
        if path == "/__variant":
            # harness-only, excluded from the probe
            return self._send(200, {"variant": "vuln" if VULN else "secure"})

        uid = self._uid()
        if path == "/api/profile":
            if uid is None:
                return self._send(401, {"error": "unauthenticated"})
            name = next(n for n, u in USERS.items() if u["id"] == uid)
            return self._send(200, {"id": uid, "user": name, "email": USERS[name]["email"]})

        if path == "/api/notes":
            if uid is None:
                return self._send(401, {"error": "unauthenticated"})
            mine = [n for n in NOTES.values() if n["owner"] == uid]
            return self._send(200, {"notes": sorted(mine, key=lambda n: n["id"])})

        if path.startswith("/api/notes/"):
            if uid is None:
                return self._send(401, {"error": "unauthenticated"})
            try:
                note_id = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._send(400, {"error": "bad id"})
            note = NOTES.get(note_id)
            if note is None:
                return self._send(404, {"error": "not found"})
            # ---- the one intended difference between the two variants ----
            if not VULN and note["owner"] != uid:
                return self._send(403, {"error": "forbidden"})
            # --------------------------------------------------------------
            return self._send(200, note)

        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(sys.argv[1])
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
