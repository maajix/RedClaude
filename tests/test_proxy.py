"""The egress door, in every part of it a server is not needed to decide.

Ticket 09's fence has two halves. The database half -- which capability resolves,
which Program it belongs to, which writer may create an allowed Receipt -- is in
`tests/test_database.py`, because only a server can answer it. This file holds
the other half: what the proxy does with the bytes on either side of that
decision, which is decidable against a stub and a loopback target.

Four properties carry it.

The control headers are *taken*, not read: `take_control` removes them from the
message before anything else looks at it, so the code that builds the forwarded
request cannot include what it never held. The test for that is not "the target
did not see them" alone -- it is that the header container itself no longer
carries them, which is the difference between a rule and a habit.

A refusal happens before the target is contacted. The stub target counts the
requests it received, and every refused case must leave that count at zero. A
proxy that refuses after forwarding has already leaked the request.

Exactly one Receipt is written per exchange, by the fence rather than by the
handler, and the handler returns its identifier to the caller. A path that
answers the caller without recording anything, or records twice, is a receipt
count that no longer equals the egress count.

The capability travels to the proxy and nowhere else. `send` refuses a proxy
that is not on the loopback interface, which is the Python half of "the runtime
sends the plaintext capability only to the local proxy".
"""

from __future__ import annotations

import http.client
import json
import threading
import unittest
from email.message import Message
from http.server import ThreadingHTTPServer
from pathlib import Path

from redkraken import proxy, scope
from redkraken.outcome import EXIT_INVALID_CONFIGURATION
from redkraken.store import Store
from tests.fixtures import Target, scratch


#: A capability the way the runtime mints one: 32 random bytes in lowercase hex.
CAPABILITY = "a" * 64
OTHER = "b" * 64


def message(pairs: list[tuple[str, str]]) -> Message:
    """One header container in the shape `BaseHTTPRequestHandler` produces."""
    headers = Message()
    for name, value in pairs:
        headers[name] = value
    return headers


class Stub:
    """The database half, recorded rather than run.

    `authorize` answers for one capability and refuses every other, which is the
    whole of what the handler is allowed to know about the decision: it does not
    inspect the authorization, it forwards or it does not.
    """

    def __init__(self, *, decided: proxy.Authorization | None = None, fail: bool = False):
        self.decided = decided or proxy.Authorization(
            program_id="11111111-1111-1111-1111-111111111111",
            tool_run_id="22222222-2222-2222-2222-222222222222",
            scope_version=1,
            scope_class="target",
        )
        self.fail = fail
        self.authorized: list[tuple] = []
        self.allowed: list[dict] = []
        self.blocked: list[dict] = []

    def authorize(
        self, program_id: str, capability: str, method: str, request: scope.Request
    ) -> proxy.Authorization:
        self.authorized.append((program_id, capability, method, request))
        if capability != CAPABILITY:
            raise proxy.Refused("capability refused")
        if program_id != self.decided.program_id:
            raise proxy.Refused("capability refused")
        return self.decided

    def allowed_receipt(
        self, program_id: str, capability: str, receipt: dict, artifacts: list[dict]
    ) -> dict:
        if self.fail:
            raise proxy.Refused("receipt write refused")
        self.allowed.append(
            {"program_id": program_id, "receipt": receipt, "artifacts": artifacts}
        )
        return {"receipt_id": "33333333-3333-3333-3333-333333333333", "label": "R1"}

    def blocked_receipt(self, program_id: str, capability: str | None, receipt: dict) -> str:
        self.blocked.append({"program_id": program_id, "receipt": receipt})
        return "44444444-4444-4444-4444-444444444444"


class HeaderTest(unittest.TestCase):
    """Criterion 3, on the side the target never sees."""

    def test_the_control_headers_are_removed_from_the_message_that_holds_them(self):
        headers = message(
            [
                ("Host", "target.example.test"),
                (proxy.AUTHORIZATION, f"RedKraken {CAPABILITY}"),
                (proxy.PROGRAM, "11111111-1111-1111-1111-111111111111"),
                ("Accept", "*/*"),
            ]
        )

        control = proxy.take_control(headers)

        self.assertEqual(CAPABILITY, control.capability)
        self.assertEqual("11111111-1111-1111-1111-111111111111", control.program)
        self.assertIsNone(headers.get(proxy.AUTHORIZATION))
        self.assertIsNone(headers.get(proxy.PROGRAM))
        self.assertEqual(["Host", "Accept"], headers.keys())

    def test_a_capability_given_twice_is_refused_rather_than_resolved(self):
        # Two values under one name is a request that means two things. Taking
        # the first would let a caller hide a second capability behind one the
        # proxy is known to accept.
        headers = message(
            [
                (proxy.AUTHORIZATION, f"RedKraken {CAPABILITY}"),
                (proxy.AUTHORIZATION, f"RedKraken {OTHER}"),
            ]
        )

        with self.assertRaises(proxy.Refused):
            proxy.take_control(headers)
        self.assertIsNone(headers.get(proxy.AUTHORIZATION))

    def test_a_capability_that_is_not_the_minted_shape_resolves_to_nothing(self):
        for value in (
            None,
            "",
            CAPABILITY,
            f"Basic {CAPABILITY}",
            "RedKraken " + "A" * 64,
            "RedKraken " + "a" * 63,
            "RedKraken " + "a" * 65,
            f"RedKraken {CAPABILITY} extra",
        ):
            with self.subTest(value=value):
                self.assertIsNone(proxy.capability_of(value))

    def test_every_control_and_hop_by_hop_header_is_dropped_from_the_forwarded_request(self):
        headers = message(
            [
                ("Host", "attacker.example.test"),
                ("Accept", "*/*"),
                ("Connection", "keep-alive"),
                ("Proxy-Connection", "keep-alive"),
                ("Keep-Alive", "timeout=5"),
                ("Transfer-Encoding", "chunked"),
                ("Content-Length", "9999"),
                ("TE", "trailers"),
                ("Trailer", "X-Thing"),
                ("Upgrade", "websocket"),
                ("X-RedKraken-Receipt", "R1"),
                ("X-RedKraken-Decision", "allowed"),
                ("User-Agent", "rk"),
            ]
        )

        forwarded = proxy.forwardable(headers)

        self.assertEqual([("Accept", "*/*"), ("User-Agent", "rk")], forwarded)

    def test_the_forwarded_request_line_carries_the_origin_form_with_its_query(self):
        self.assertEqual("/v1/notes?id=2", proxy.origin_form("http://a.example.test/v1/notes?id=2"))
        self.assertEqual("/", proxy.origin_form("http://a.example.test"))
        self.assertEqual("/", proxy.origin_form("http://a.example.test/"))
        # The fragment is the caller's, never the server's, and a proxy that
        # forwarded one would be sending a byte the origin never asked for.
        self.assertEqual("/x", proxy.origin_form("http://a.example.test/x#frag"))

    def test_the_query_is_recorded_as_a_digest_and_absence_is_not_a_digest_of_nothing(self):
        self.assertIsNone(proxy.query_sha256("http://a.example.test/v1"))
        first = proxy.query_sha256("http://a.example.test/v1?id=2")
        self.assertEqual(64, len(first))
        self.assertNotEqual(first, proxy.query_sha256("http://a.example.test/v1?id=3"))


class ExchangeTest(unittest.TestCase):
    """What happens on the wire, against a stub decision and a real target."""

    @classmethod
    def setUpClass(cls):
        cls.target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        cls.target.seen = []
        cls.target.daemon_threads = True
        cls.thread = threading.Thread(target=cls.target.serve_forever, daemon=True)
        cls.thread.start()
        cls.target_port = cls.target.server_address[1]
        cls.root = scratch() / "proxy-store"
        cls.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.target.shutdown()
        cls.target.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.target.seen.clear()
        self.fence = Stub()
        self.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=self.fence,
            store=Store(self.root),
            connector=self.connector,
        )
        self.serving = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.serving.start()
        self.addCleanup(self.stop)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.serving.join(timeout=5)

    def connector(self, host: str, port: int, timeout: float) -> http.client.HTTPConnection:
        """Every name resolves to the fixture. Address policy is ticket 11's."""
        return http.client.HTTPConnection("127.0.0.1", self.target_port, timeout=timeout)

    def through(
        self,
        url: str,
        *,
        capability: str | None = CAPABILITY,
        program: str | None = "11111111-1111-1111-1111-111111111111",
        method: str = "GET",
        headers: list[tuple[str, str]] | None = None,
        body: bytes | None = None,
    ) -> http.client.HTTPResponse:
        """One request at the door, header by header.

        Not `client.request(headers=...)`: that takes a mapping, and a caller
        sending the same header twice is one of the things under test.
        """
        sending = list(headers or [])
        if capability is not None:
            sending.append((proxy.AUTHORIZATION, f"RedKraken {capability}"))
        if program is not None:
            sending.append((proxy.PROGRAM, program))
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_address[1], timeout=5
        )
        self.addCleanup(client.close)
        client.putrequest(method, url)
        for name, value in sending:
            client.putheader(name, value)
        if body is not None:
            client.putheader("Content-Length", str(len(body)))
        client.endheaders(body)
        return client.getresponse()

    def test_an_authorized_request_reaches_the_target_and_answers_with_a_receipt(self):
        # Criteria 2 and 4 on the happy path: the target answers, the fence wrote
        # exactly one allowed Receipt, and the caller is handed its label.
        response = self.through("http://target.example.test/v1/notes?id=2")
        body = response.read()

        self.assertEqual(200, response.status)
        self.assertEqual(b'{"note":"target answered"}', body)
        self.assertEqual("R1", response.headers[proxy.RECEIPT])
        self.assertEqual(1, len(self.target.seen))
        self.assertEqual(1, len(self.fence.allowed))
        self.assertEqual([], self.fence.blocked)

        receipt = self.fence.allowed[0]["receipt"]
        self.assertEqual("GET", receipt["method"])
        self.assertEqual("http", receipt["scheme"])
        self.assertEqual("target.example.test", receipt["host"])
        self.assertEqual(80, receipt["port"])
        self.assertEqual("/v1/notes", receipt["path"])
        self.assertEqual(200, receipt["status_code"])
        self.assertEqual("target", receipt["scope_class"])
        self.assertEqual(64, len(receipt["query_sha256"]))

    def test_the_target_never_receives_the_capability_or_any_control_header(self):
        # Criterion 3. Asked of the bytes the target actually read, not of the
        # bytes the proxy meant to send.
        self.through(
            "http://target.example.test/v1/notes", headers=[("Accept", "*/*")]
        ).read()

        _, path, seen = self.target.seen[0]
        names = [name for name, _ in seen]

        self.assertEqual("/v1/notes", path)
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        self.assertEqual([], [name for name in names if name.startswith("x-redkraken-")])
        self.assertNotIn(CAPABILITY, json.dumps(seen))
        # The Host the target sees is the one the proxy decided against, never
        # the one the caller wrote: they are the same name or the decision was
        # about a different server than the request reached.
        self.assertEqual(["target.example.test"], [v for n, v in seen if n == "host"])

    def test_a_header_the_caller_sent_twice_crosses_once_per_time_it_was_sent(self):
        # The Receipt names a hash of the request, so "what was sent" has to be
        # one set of bytes rather than two nearly-equal ones. A mapping loses the
        # first `Cookie` on the wire while the transcript still shows both, which
        # makes the hash a claim about a request the target never received.
        self.through(
            "http://target.example.test/v1/notes",
            headers=[("Cookie", "a=1"), ("Cookie", "b=2")],
        ).read()

        _, _, seen = self.target.seen[0]
        stored = Store(self.root).load(self.fence.allowed[0]["receipt"]["request_agent_sha"])

        self.assertEqual(["a=1", "b=2"], [value for name, value in seen if name == "cookie"])
        self.assertEqual(2, stored.count(b"Cookie: "))

    def test_the_stored_request_is_byte_for_byte_what_the_target_read(self):
        # A body-less POST is the case that separates the two: `http.client`
        # adds `Content-Length: 0` to one, and a transcript built before that
        # happened would be a hash of a request nobody sent.
        self.through("http://target.example.test/v1/notes", method="POST", body=b"").read()

        _, _, seen = self.target.seen[0]
        stored = Store(self.root).load(self.fence.allowed[0]["receipt"]["request_agent_sha"])
        head = stored.split(b"\r\n\r\n", 1)[0].decode("ascii").split("\r\n")
        recorded = [tuple(line.split(": ", 1)) for line in head[1:]]

        self.assertEqual("POST /v1/notes HTTP/1.1", head[0])
        self.assertEqual(sorted(seen), sorted((name.lower(), value) for name, value in recorded))

    def test_the_receipt_names_the_bytes_of_both_directions_and_never_the_capability(self):
        self.through("http://target.example.test/v1/notes").read()

        recorded = self.fence.allowed[0]
        artifacts = {item["sha256"]: item for item in recorded["artifacts"]}
        receipt = recorded["receipt"]

        self.assertEqual(2, len(artifacts))
        self.assertIn(receipt["request_agent_sha"], artifacts)
        self.assertIn(receipt["response_agent_sha"], artifacts)
        for item in artifacts.values():
            self.assertGreater(item["byte_size"], 0)
            store = Store(self.root)
            self.assertEqual(item["byte_size"], len(store.load(item["sha256"])))
        self.assertNotIn(CAPABILITY, json.dumps(receipt))
        # The wire view is a claim about bytes that differ from the agent's, and
        # nothing differs until an identity is injected: ticket 12 fills these.
        self.assertIsNone(receipt["request_wire_sha"])
        self.assertIsNone(receipt["response_wire_sha"])

    def test_a_stored_request_transcript_holds_no_control_header(self):
        self.through("http://target.example.test/v1/notes").read()

        receipt = self.fence.allowed[0]["receipt"]
        stored = Store(self.root).load(receipt["request_agent_sha"])

        self.assertIn(b"GET /v1/notes HTTP/1.1", stored)
        self.assertNotIn(CAPABILITY.encode(), stored)
        self.assertNotIn(b"Proxy-Authorization", stored)
        self.assertNotIn(b"X-RedKraken", stored)

    def test_a_missing_capability_is_refused_before_the_target_is_contacted(self):
        # Criterion 5, first arm.
        response = self.through("http://target.example.test/v1/notes", capability=None)
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.REFUSED, response.headers[proxy.DECISION])
        self.assertEqual([], self.target.seen)
        self.assertEqual(1, len(self.fence.blocked))
        self.assertEqual([], self.fence.allowed)
        self.assertEqual("blocked", self.fence.blocked[0]["receipt"]["decision"])

    def test_a_fabricated_capability_is_refused_before_the_target_is_contacted(self):
        response = self.through("http://target.example.test/v1/notes", capability=OTHER)
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.target.seen)
        self.assertEqual(1, len(self.fence.blocked))
        self.assertEqual([], self.fence.allowed)

    def test_a_capability_offered_under_another_program_reaches_nothing(self):
        response = self.through(
            "http://target.example.test/v1/notes",
            program="99999999-9999-9999-9999-999999999999",
        )
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.target.seen)
        self.assertEqual(
            "99999999-9999-9999-9999-999999999999", self.fence.blocked[0]["program_id"]
        )

    def test_a_request_that_names_no_program_is_refused_and_files_nothing(self):
        # There is no Program to file the record under, and guessing one would
        # put a stranger's blocked Receipt in somebody's audit trail.
        response = self.through("http://target.example.test/v1/notes", program=None)
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.blocked)
        self.assertEqual([], self.fence.allowed)

    def test_a_request_the_policy_module_cannot_read_is_refused_before_egress(self):
        response = self.through("http://a..example.test/v1")
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.target.seen)
        self.assertEqual(1, len(self.fence.blocked))

    def test_a_request_addressed_to_the_proxy_itself_is_not_a_request_to_forward(self):
        # Origin form means "you are the origin server". The fence has no
        # resource to serve, and answering one would be an unauthenticated
        # surface on the one process that holds every capability in flight.
        response = self.through("/v1/notes")
        response.read()

        self.assertEqual(400, response.status)
        self.assertEqual([], self.target.seen)

    def test_a_tunnel_is_refused_rather_than_opened(self):
        # HTTPS through CONNECT is ticket 10. Refusing it here is the honest
        # answer: a tunnel this fence cannot see inside is egress with no Receipt.
        response = self.through("target.example.test:443", method="CONNECT")
        response.read()

        self.assertEqual(405, response.status)
        self.assertEqual(proxy.TUNNEL, response.headers[proxy.DECISION])
        self.assertEqual([], self.target.seen)

    def test_a_tunnel_carrying_two_capabilities_is_answered_rather_than_dropped(self):
        # The take runs before the refusal on this path too, and a caller that
        # gets no answer at all learns the same thing from a closed socket that a
        # 405 tells them -- except that nothing recorded which refusal it was.
        response = self.through(
            "target.example.test:443",
            method="CONNECT",
            headers=[(proxy.AUTHORIZATION, f"RedKraken {OTHER}")],
        )
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.AMBIGUOUS, response.headers[proxy.DECISION])
        self.assertEqual([], self.target.seen)

    def test_a_receipt_that_cannot_be_written_is_not_reported_as_an_allowed_request(self):
        # The target has already answered by this point, so the bytes are spent.
        # What must not happen is the caller reading a 200 for an exchange with
        # no Receipt behind it.
        self.fence.fail = True

        response = self.through("http://target.example.test/v1/notes")
        body = response.read()

        self.assertEqual(502, response.status)
        self.assertNotIn(b"target answered", body)
        self.assertEqual([], self.fence.allowed)


class RuntimeTest(unittest.TestCase):
    """The half that holds the plaintext capability, offline."""

    def test_the_capability_is_refused_a_proxy_that_is_not_on_this_machine(self):
        result = proxy.send(
            None,
            Path("does-not-matter.toml"),
            "http://target.example.test/v1",
            proxy_url="http://proxy.example.net:8080",
        )

        self.assertFalse(result.ok)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
        self.assertEqual(
            ["proxy_endpoint"], [item.name for item in result.assertions if not item.ok]
        )

    def test_the_loopback_endpoints_are_the_ones_it_accepts(self):
        for url, expected in (
            ("http://127.0.0.1:8080", ("127.0.0.1", 8080)),
            ("http://localhost:9", ("localhost", 9)),
            ("http://[::1]:8080", ("::1", 8080)),
        ):
            with self.subTest(url=url):
                self.assertEqual(expected, proxy.endpoint(url))
        for url in ("http://proxy.example.net:8080", "https://127.0.0.1:8080", "127.0.0.1:8080"):
            with self.subTest(url=url):
                with self.assertRaises(proxy.Refused):
                    proxy.endpoint(url)


if __name__ == "__main__":
    unittest.main()
