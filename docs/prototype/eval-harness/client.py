"""PROTOTYPE runtime-side HTTP client.

Stands in for the scope proxy. Two properties are all that matter here:

1. It holds the credentials. Callers name an identity ("userA") and never see
   the cookie -- the same split ticket 04 measured, reproduced cheaply so the
   harness can grade findings that were produced under it.
2. Every request produces a receipt. A caller can only cite what it actually
   did, which is what makes "discard any observation whose receipt does not
   exist" enforceable at scoring time rather than at prompt time.

Three lanes: `agent` (driven by the system under test), `runtime-internal`
(logins the agent never sees) and `replay` (the harness re-executing a test
spec). They are separated so a claim cannot cite a receipt the harness itself
produced while grading it.
"""

import http.client
import json


class Response:
    __slots__ = ("status", "body", "receipt_id")

    def __init__(self, status, body, receipt_id):
        self.status = status
        self.body = body
        self.receipt_id = receipt_id

    def json(self):
        try:
            return json.loads(self.body)
        except ValueError:
            return None

    def as_dict(self):
        return {"status": self.status, "body": self.body, "receipt_id": self.receipt_id}


class Runtime:
    """Credentials live here and nowhere else the SUT can reach."""

    def __init__(self, host, port, receipts, secrets):
        self.host = host
        self.port = port
        self.receipts = receipts
        self._secrets = secrets           # identity -> {user, password}
        self._jar = {}                    # identity -> cookie, runtime-side only
        self.lane_counts = {}

    def _conn(self):
        return http.client.HTTPConnection(self.host, self.port, timeout=5)

    def _raw(self, lane, identity, method, path, body, cookie):
        headers = {"Accept": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        payload = None
        if body is not None:
            payload = json.dumps(body, sort_keys=True).encode()
            headers["Content-Type"] = "application/json"
        conn = self._conn()
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        set_cookie = resp.getheader("Set-Cookie")
        conn.close()
        req_repr = "%s %s\n%s" % (method, path, payload.decode() if payload else "")
        rid = self.receipts.record(lane, identity, method,
                                   "http://%s:%d%s" % (self.host, self.port, path),
                                   resp.status, req_repr, data)
        self.lane_counts[lane] = self.lane_counts.get(lane, 0) + 1
        return resp.status, data.decode(), set_cookie, rid

    def _cookie_for(self, identity):
        if identity is None:
            return None
        if identity not in self._jar:
            creds = self._secrets[identity]
            status, _, set_cookie, _ = self._raw(
                "runtime-internal", identity, "POST", "/login",
                {"user": creds["user"], "password": creds["password"]}, None)
            if status != 200 or not set_cookie:
                raise RuntimeError("fixture login failed for %s (%d)" % (identity, status))
            self._jar[identity] = set_cookie.split(";")[0]
        return self._jar[identity]

    def request(self, lane, identity, method, path, body=None):
        """Caller names an identity. Caller never receives credential material."""
        cookie = self._cookie_for(identity)
        status, text, _set_cookie, rid = self._raw(lane, identity, method, path, body, cookie)
        return Response(status, text, rid)   # Set-Cookie deliberately dropped here
