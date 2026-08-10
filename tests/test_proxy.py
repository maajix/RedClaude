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
import os
import socket
import ssl
import threading
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest import mock

from redkraken import proxy, scope, tls
from redkraken.outcome import EXIT_INVALID_CONFIGURATION
from redkraken.store import Store
from tests.fixtures import counterparty, scratch, tls_counterparty


#: A capability the way the runtime mints one: 32 random bytes in lowercase hex.
CAPABILITY = "a" * 64
OTHER = "b" * 64

#: The Program every request here is filed under.
PROGRAM_ID = "11111111-1111-1111-1111-111111111111"

#: What a refused capability looks like from the database, in the shape `pg`
#: renders one: the SQLSTATE, the message, and the frame it was raised in.
DATABASE_ERROR = (
    "23514: egress request is outside current scope | "
    "PL/pgSQL function authorize_egress_request(text,text,text,text,integer,"
    "text,text,text) line 71 at RAISE"
)


def message(pairs: list[tuple[str, str]]) -> Message:
    """One header container in the shape `BaseHTTPRequestHandler` produces."""
    headers = Message()
    for name, value in pairs:
        headers[name] = value
    return headers


def common_name(name: tuple) -> str:
    """The CN out of the nested tuples `getpeercert` returns for a distinguished name."""
    return next(value for rdn in name for key, value in rdn if key == "commonName")


class Stub:
    """The database half, recorded rather than run.

    `authorize` answers for one capability and refuses every other, which is the
    whole of what the handler is allowed to know about the decision: it does not
    inspect the authorization, it forwards or it does not.

    It also refuses by host, through the same exception, because the real one
    does: `authorize_egress_request` raises the same `DatabaseError` for a
    capability that resolves to nothing and for a target outside the scope it
    resolves to. A test about scope that reached for a wrong capability instead
    would pass without the host ever being looked at.
    """

    def __init__(self, *, decided: proxy.Authorization | None = None, fail: bool = False):
        self.decided = decided or proxy.Authorization(
            program_id=PROGRAM_ID,
            tool_run_id="22222222-2222-2222-2222-222222222222",
            scope_version=1,
            scope_class="target",
        )
        self.fail = fail
        self.out_of_scope: set[str] = set()
        self.authorized: list[tuple] = []
        self.allowed: list[dict] = []
        self.blocked: list[dict] = []

    def authorize(
        self, program_id: str, capability: str, method: str, request: scope.Request
    ) -> proxy.Authorization:
        self.authorized.append((program_id, capability, method, request))
        if (
            request.host in self.out_of_scope
            or capability != CAPABILITY
            or program_id != self.decided.program_id
        ):
            # Shaped like the real one: `Fence.authorize` turns a `DatabaseError`
            # into this, and the detail is the server's own text down to the
            # PL/pgSQL frame the exception was raised in.
            raise proxy.Refused("capability refused", DATABASE_ERROR)
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
                (proxy.PROGRAM, "11111111-1111-1111-1111-111111111111"),
            ]
        )

        control = proxy.take_control(headers)

        self.assertTrue(control.ambiguous)
        self.assertIsNone(control.capability)
        self.assertIsNone(headers.get(proxy.AUTHORIZATION))
        # The Program was named once and unambiguously, and it survives the
        # refusal: it is what the record of this attempt is filed under.
        self.assertEqual("11111111-1111-1111-1111-111111111111", control.program)

    def test_a_program_given_twice_leaves_nothing_to_file_the_attempt_under(self):
        headers = message(
            [
                (proxy.AUTHORIZATION, f"RedKraken {CAPABILITY}"),
                (proxy.PROGRAM, "11111111-1111-1111-1111-111111111111"),
                (proxy.PROGRAM, "22222222-2222-2222-2222-222222222222"),
            ]
        )

        control = proxy.take_control(headers)

        self.assertTrue(control.ambiguous)
        self.assertIsNone(control.program)
        self.assertIsNone(headers.get(proxy.PROGRAM))

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
        cls.target, cls.thread = counterparty()
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

    def connector(
        self, host: str, port: int, timeout: float, protocol: str
    ) -> http.client.HTTPConnection:
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

    def test_a_door_with_no_authority_refuses_the_tunnel_rather_than_relaying_it(self):
        # This door was started without a certificate authority, so it cannot
        # terminate a tunnel -- and the fallback is not to relay one, because a
        # tunnel this fence cannot see inside is egress with no Receipt. The door
        # that does have one is `TunnelTest` below.
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

    def test_a_capability_sent_twice_is_refused_and_still_recorded(self):
        # The refusal is not in question; the record is. A caller who could make
        # their own attempt unrecorded by sending one header twice would have
        # found the cheapest way past this fence there is -- refused, and
        # invisible to whoever reads the Receipts afterwards.
        response = self.through(
            "http://target.example.test/v1/notes",
            headers=[(proxy.AUTHORIZATION, f"RedKraken {OTHER}")],
        )
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.AMBIGUOUS, response.headers[proxy.DECISION])
        self.assertEqual([], self.target.seen)
        self.assertEqual(1, len(self.fence.blocked))
        filed = self.fence.blocked[0]
        self.assertEqual("11111111-1111-1111-1111-111111111111", filed["program_id"])
        self.assertEqual("ambiguous control headers", filed["receipt"]["reason"])

    def test_two_program_headers_leave_nothing_to_file_the_attempt_under(self):
        # The other half of the same take. Here the ambiguous header is the one
        # that would have said whose audit trail this belongs in, and filing it
        # under a guess would put a stranger's row in somebody's Program.
        response = self.through(
            "http://target.example.test/v1/notes",
            headers=[(proxy.PROGRAM, "99999999-9999-9999-9999-999999999999")],
        )
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.AMBIGUOUS, response.headers[proxy.DECISION])
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.blocked)

    def test_a_receipt_that_cannot_be_written_is_not_reported_as_an_allowed_request(self):
        # The target has already answered by this point, so the bytes are spent.
        # What must not happen is the caller reading a 200 for an exchange with
        # no Receipt behind it -- and what must still happen is a record, because
        # bytes crossed. It cannot be the allowed one, so it is the blocked one,
        # and it carries the two facts that say the request left: the moment of
        # egress and the status the target answered with.
        self.fence.fail = True

        response = self.through("http://target.example.test/v1/notes")
        body = response.read()

        self.assertEqual(502, response.status)
        self.assertEqual(proxy.RECEIPT_REFUSED, response.headers[proxy.DECISION])
        self.assertNotIn(b"target answered", body)
        self.assertEqual([], self.fence.allowed)
        self.assertEqual(1, len(self.fence.blocked))
        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("receipt write refused", filed["reason"])
        self.assertEqual(200, filed["status_code"])
        self.assertIn("ts_egress", filed)

    def test_a_refusal_tells_the_caller_the_reason_and_not_the_database_error(self):
        # The caller is the thing being fenced, and what explains a fence refusal
        # is the server's own error text: a SQLSTATE, a message naming which rule
        # said no, and the function and line it was raised in. The decision header
        # is what a caller branches on and the reason is what the Receipt cites;
        # neither of them is a map of the schema.
        response = self.through("http://target.example.test/v1/notes", capability=OTHER)
        body = response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.REFUSED, response.headers[proxy.DECISION])
        self.assertEqual("capability refused", response.headers[proxy.DETAIL])
        self.assertNotIn("23514", str(response.headers) + body.decode())
        self.assertNotIn("PL/pgSQL", str(response.headers) + body.decode())

    def test_a_refusal_names_the_record_it_wrote_for_the_attempt(self):
        # Without it, "refused and recorded" and "refused and lost" are the same
        # answer on the wire, and `_spend` reads a refusal with no Receipt as an
        # integrity failure -- which is what it should mean.
        response = self.through("http://target.example.test/v1/notes", capability=OTHER)
        response.read()

        self.assertEqual("44444444-4444-4444-4444-444444444444", response.headers[proxy.RECEIPT])
        self.assertEqual(1, len(self.fence.blocked))

    def test_a_refusal_before_contact_records_no_moment_of_egress(self):
        # The falsification for the row above: if every blocked Receipt carried
        # an egress time, the one that carries it would say nothing.
        response = self.through("http://target.example.test/v1/notes", capability=OTHER)
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.target.seen)
        filed = self.fence.blocked[0]["receipt"]
        self.assertNotIn("ts_egress", filed)
        self.assertNotIn("status_code", filed)


class TunnelTest(unittest.TestCase):
    """The same door, with an authority, answering HTTPS.

    Everything here is one claim: an HTTPS run crosses the *same* capability,
    scope and Receipt path as an HTTP one. So the assertions are deliberately the
    ones `ExchangeTest` already makes -- one allowed Receipt, no target contact on
    a refusal, no control header at the target -- asked again through a tunnel.
    A second code path that answered them differently would be the finding.
    """

    @classmethod
    def setUpClass(cls):
        cls.target, cls.thread, cls.target_ca = tls_counterparty()
        cls.target_port = cls.target.server_address[1]
        cls.authority = tls.authority(scratch() / "door-authority")
        cls.trust = tls.trust(cls.authority.certificate)
        cls.root = scratch() / "tunnel-store"
        cls.root.mkdir(parents=True, exist_ok=True)
        # A port bound and released: nothing answers there, which is how the
        # regression below tells "went through the door" from "went to the target".
        with socket.socket() as spare:
            spare.bind(("127.0.0.1", 0))
            cls.unreachable = spare.getsockname()[1]

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
            authority=self.authority,
        )
        self.serving = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.serving.start()
        self.addCleanup(self.stop)
        # `ProxyHandler` asks `proxy_bypass` before it uses a proxy, and that
        # reads the environment. A developer machine with `no_proxy=127.0.0.1`
        # would send every request below straight past the door and pass the
        # regression test for the wrong reason.
        self.enterContext(mock.patch.dict(os.environ, {"no_proxy": "", "NO_PROXY": ""}))

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.serving.join(timeout=5)

    def connector(
        self, host: str, port: int, timeout: float, protocol: str
    ) -> http.client.HTTPConnection:
        """The door's outbound side, verifying the target it was sent to.

        In production this is `proxy.connect`, which verifies against the system
        store; here the fixture's own root stands in for it. The point of the
        substitution is what stays the same: the door checks the target's
        certificate itself, because the agent no longer can.
        """
        return http.client.HTTPSConnection(
            "127.0.0.1",
            self.target_port,
            timeout=timeout,
            context=ssl.create_default_context(cafile=str(self.target_ca)),
        )

    def control(self, capability: str | None = CAPABILITY, program: str = PROGRAM_ID) -> dict:
        headers = {proxy.PROGRAM: program}
        if capability is not None:
            headers[proxy.AUTHORIZATION] = f"RedKraken {capability}"
        return headers

    def spend(
        self,
        url: str,
        *,
        capability: str = CAPABILITY,
        program: str = PROGRAM_ID,
        method: str = "GET",
    ) -> proxy.Answer:
        """One request the way `rk proxy request` sends one.

        The runtime's own client, called directly rather than reimplemented:
        what is under test includes the CONNECT it writes and the refusal it
        keeps, and a test client that wrote its own would be proving a shape
        nothing in production uses.
        """
        return proxy._through(
            self.server.server_address,
            url,
            method,
            capability,
            program,
            5.0,
            scope.canonical_request(url),
            self.trust,
        )

    def tunnel(self, url: str, **control: str) -> tuple[scope.Request, ssl.SSLSocket]:
        """Open the tunnel and hand back the TLS socket inside it."""
        request = scope.canonical_request(url)
        raw = socket.create_connection(self.server.server_address, timeout=5)
        self.addCleanup(raw.close)
        refusal = proxy._tunnel(raw, request, self.control(**control))
        self.assertIsNone(refusal, "the door refused the tunnel")
        secured = self.trust.wrap_socket(raw, server_hostname=request.host)
        self.addCleanup(secured.close)
        return request, secured

    def inside(
        self, request: scope.Request, secured: ssl.SSLSocket, url: str, headers: dict
    ) -> http.client.HTTPResponse:
        """One request in a tunnel that is already open, on the caller's terms."""
        client = http.client.HTTPConnection(request.host, request.port, timeout=5)
        client.sock = secured
        self.addCleanup(client.close)
        client.request("GET", proxy.origin_form(url), headers=headers)
        return client.getresponse()

    def fetch(self, url: str, *, schemes: tuple[str, ...] = ("http", "https")):
        """One request the way an ordinary client sends one.

        `urllib` rather than this suite's own socket writing, because the split
        that matters is one no hand-written client would make by accident: it
        moves `Proxy-Authorization` onto the CONNECT and leaves every other
        header on the request inside the tunnel.
        """
        door = "http://%s:%d" % self.server.server_address
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({scheme: door for scheme in schemes}),
            urllib.request.HTTPSHandler(context=self.trust),
        )
        asked = urllib.request.Request(url)
        asked.add_header(proxy.AUTHORIZATION, f"RedKraken {CAPABILITY}")
        asked.add_header(proxy.PROGRAM, PROGRAM_ID)
        return opener.open(asked, timeout=5)

    def test_an_https_target_is_reached_through_the_tunnel_and_answers_with_a_receipt(self):
        # Criterion 2, and the whole of the ticket in one assertion: the Receipt
        # is the same row `ExchangeTest` gets, with `https` where `http` was.
        answer = self.spend("https://target.example.test/v1/notes?id=2")

        self.assertEqual(200, answer.status)
        self.assertEqual(b'{"note":"target answered"}', answer.body)
        self.assertEqual("R1", answer.receipt)
        # Nothing here refused, so the door says nothing about a decision: that
        # absence is what the runtime closes a Tool run as success on.
        self.assertIsNone(answer.decision)
        self.assertEqual(1, len(self.target.seen))
        self.assertEqual(1, len(self.fence.allowed))
        self.assertEqual([], self.fence.blocked)

        filed = self.fence.allowed[0]["receipt"]
        self.assertEqual("GET", filed["method"])
        self.assertEqual("https", filed["scheme"])
        self.assertEqual("target.example.test", filed["host"])
        self.assertEqual(443, filed["port"])
        self.assertEqual("/v1/notes", filed["path"])
        self.assertEqual(200, filed["status_code"])
        self.assertEqual("target", filed["scope_class"])
        self.assertEqual(64, len(filed["query_sha256"]))
        self.assertTrue(filed["intercepted"])

    def test_the_capability_is_read_when_the_two_hops_carry_a_header_each(self):
        # What an ordinary client does. A door that read the CONNECT alone would
        # see a capability naming no Program; one that read the request inside it
        # alone would see a Program with no capability. Both are 407s, and both
        # would make this fence unusable by anything but its own runtime.
        answer = self.fetch("https://target.example.test/v1/notes")

        self.assertEqual(200, answer.status)
        self.assertEqual("R1", answer.headers[proxy.RECEIPT])
        self.assertEqual(1, len(self.fence.allowed))

    def test_the_tunnel_is_terminated_at_the_door_and_never_reaches_the_target(self):
        # Criterion 5's sharpest edge. The certificate the client verifies is one
        # this run minted seconds ago, which is the same statement as "no wire-only
        # material reaches the agent": what the agent sees of the connection is the
        # door's, and the target's own certificate is a fact only the door holds.
        _, secured = self.tunnel("https://target.example.test/v1/notes")
        peer = secured.getpeercert()

        self.assertEqual("redKraken run authority", common_name(peer["issuer"]))
        self.assertEqual("redKraken egress", common_name(peer["subject"]))
        self.assertEqual((("DNS", "target.example.test"),), peer["subjectAltName"])
        # A CONNECT is not an exchange: nothing was sent inside this tunnel, and
        # so nothing was sent anywhere.
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.authorized)
        self.assertEqual([], self.fence.allowed)
        self.assertEqual([], self.fence.blocked)

    def test_the_target_never_receives_the_capability_or_any_control_header(self):
        # Criterion 5, asked of the bytes the target read. The capability crossed
        # the CONNECT hop this time, which is a hop `forwardable` never sees, so
        # "the forwarded request holds no control header" has to be re-established
        # rather than inherited.
        self.fetch("https://target.example.test/v1/notes").read()

        _, path, seen = self.target.seen[0]
        names = [name for name, _ in seen]

        self.assertEqual("/v1/notes", path)
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        self.assertEqual([], [name for name in names if name.startswith("x-redkraken-")])
        self.assertNotIn(CAPABILITY, json.dumps(seen))
        self.assertEqual(["target.example.test"], [v for n, v in seen if n == "host"])

    def test_an_out_of_scope_https_target_is_refused_before_the_target_is_contacted(self):
        # Criterion 4. The capability and the Program are the good ones, so the
        # only thing left to refuse this request is the host it names. The tunnel
        # still opens -- refusing the CONNECT would answer "is this host in
        # scope" for free -- and the request inside it is refused before a socket
        # towards the target exists, with the blocked Receipt naming the https
        # target it was refused for.
        self.fence.out_of_scope.add("admin.example.test")

        answer = self.spend("https://admin.example.test/v1/notes")

        self.assertEqual(407, answer.status)
        self.assertEqual(b"", answer.body)
        self.assertEqual("44444444-4444-4444-4444-444444444444", answer.receipt)
        # Named as well as recorded: a Receipt with no decision beside it is what
        # the runtime reads as a served request, and this one was not served.
        self.assertEqual(proxy.REFUSED, answer.decision)
        self.assertEqual("capability refused", answer.detail)
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.allowed)
        self.assertEqual(1, len(self.fence.blocked))

        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("blocked", filed["decision"])
        self.assertEqual("capability refused", filed["reason"])
        self.assertEqual("https", filed["scheme"])
        self.assertEqual("admin.example.test", filed["host"])
        self.assertEqual(443, filed["port"])
        self.assertEqual("/v1/notes", filed["path"])
        self.assertNotIn("ts_egress", filed)
        # And the host is what the fence was asked about, not just what the row
        # says afterwards.
        self.assertEqual(
            ["admin.example.test"], [asked.host for *_, asked in self.fence.authorized]
        )

    def test_the_agent_is_answered_without_the_capability_it_spent(self):
        # Criterion 5 from the side the other two tests do not cover: the target
        # sees a stripped request and the tunnel ends at the door, but neither
        # says what came back. A door that echoed the authorization it was given,
        # or named the transcripts it had just sealed, would leak on this hop and
        # on no other.
        answer = self.fetch("https://target.example.test/v1/notes")
        returned = answer.read()
        names = [name.lower() for name in answer.headers.keys()]
        text = json.dumps(list(answer.headers.items()))

        self.assertEqual(200, answer.status)
        self.assertEqual(b'{"note":"target answered"}', returned)
        self.assertNotIn(proxy.AUTHORIZATION.lower(), names)
        self.assertNotIn(proxy.PROGRAM.lower(), names)
        # One control header comes back, and it is the Receipt's label. The
        # decision and the detail are refusal-only, and this was not a refusal.
        self.assertEqual(
            [proxy.RECEIPT.lower()], [name for name in names if name.startswith("x-redkraken-")]
        )
        self.assertNotIn(CAPABILITY, text)
        self.assertNotIn(CAPABILITY.encode(), returned)
        # Wire-only material: the transcripts are registered against the Receipt
        # and the agent is told none of their digests.
        for artifact in self.fence.allowed[0]["artifacts"]:
            self.assertNotIn(artifact["sha256"], text)
            self.assertNotIn(artifact["sha256"].encode(), returned)

    def test_a_tunnel_and_the_request_inside_it_that_disagree_are_refused_and_recorded(self):
        # Two hops is two places to put a capability, and a door that let the
        # inner one win would let a caller open a tunnel with a capability that
        # resolves and spend a different one inside it.
        request, secured = self.tunnel("https://target.example.test/v1/notes")
        answer = self.inside(
            request,
            secured,
            "https://target.example.test/v1/notes",
            {proxy.AUTHORIZATION: f"RedKraken {OTHER}"},
        )
        answer.read()

        self.assertEqual(407, answer.status)
        self.assertEqual(proxy.AMBIGUOUS, answer.headers[proxy.DECISION])
        self.assertEqual(proxy.TWO_HOPS, answer.headers[proxy.DETAIL])
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.authorized)
        self.assertEqual(1, len(self.fence.blocked))
        self.assertEqual(PROGRAM_ID, self.fence.blocked[0]["program_id"])

    def test_a_capability_on_one_hop_only_is_the_capability(self):
        # The falsification for the row above: agreement is not "both hops said
        # it". One hop saying it and the other saying nothing is the normal case,
        # and a merge that refused it would refuse every client there is.
        request, secured = self.tunnel("https://target.example.test/v1/notes", capability=None)
        answer = self.inside(
            request,
            secured,
            "https://target.example.test/v1/notes",
            {proxy.AUTHORIZATION: f"RedKraken {CAPABILITY}"},
        )
        answer.read()

        self.assertEqual(200, answer.status)
        self.assertEqual(1, len(self.fence.allowed))

    def test_a_client_holding_the_run_root_cannot_verify_a_target_it_reaches_directly(self):
        # Criterion 3, the half this module owns. The agent is handed exactly one
        # trust root and it is the door's, so a client that ignores the proxy
        # variables and dials a target itself cannot verify what answers.
        #
        # That is not containment and is not claimed as it: a client that also
        # ignores certificate verification still reaches the target, and closing
        # that is a routing fact -- a namespace with no route but the door's --
        # which is ticket 11's first criterion, not this one's.
        direct = http.client.HTTPSConnection(
            "127.0.0.1", self.target_port, timeout=5, context=self.trust
        )
        self.addCleanup(direct.close)

        with self.assertRaises(ssl.SSLCertVerificationError):
            direct.request("GET", "/v1/notes")

        self.assertEqual([], self.target.seen)

    def test_a_client_configured_for_only_the_http_scheme_leaves_by_no_door(self):
        # Criterion 6, against the prototype: `docs/prototype/walking-skeleton`
        # installed a `ProxyHandler` holding one scheme, and every https request
        # an agent made went straight out. The url names a port nothing listens
        # on, so the two configurations are told apart by where the failure comes
        # from: the door answers, or the target's own address refuses.
        url = f"https://127.0.0.1:{self.unreachable}/v1/notes"

        with self.assertRaises(urllib.error.URLError):
            self.fetch(url, schemes=("http",))

        self.assertEqual([], self.fence.authorized)
        self.assertEqual([], self.fence.allowed)
        self.assertEqual([], self.fence.blocked)
        self.assertEqual([], self.target.seen)

        answered = self.fetch(url, schemes=("http", "https"))

        self.assertEqual(200, answered.status)
        self.assertEqual("R1", answered.headers[proxy.RECEIPT])
        self.assertEqual(1, len(self.fence.allowed))
        self.assertEqual(1, len(self.target.seen))

    def test_the_door_itself_refuses_a_target_no_public_authority_vouches_for(self):
        # Every test above substitutes `connector`, so this is the one that runs
        # the production one. The fixture target holds a certificate from an
        # authority nobody has heard of, which is what a target impersonated
        # between the door and the internet would look like: the door refuses it,
        # and it is the only side left that can, because the agent is looking at
        # this door's certificate rather than the target's.
        outbound = proxy.connect("127.0.0.1", self.target_port, 5.0, "https")
        self.addCleanup(outbound.close)

        with self.assertRaises(ssl.SSLCertVerificationError):
            outbound.request("GET", "/v1/notes")

        self.assertEqual([], self.target.seen)


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

    def test_the_door_refuses_to_listen_anywhere_a_stranger_could_reach_it(self):
        # The mirror of the assertion above. A capability that may only be sent
        # to a local proxy is worth nothing if the proxy binds an interface the
        # network can reach: what arrives there is bearer material, spendable by
        # whoever got to the port first.
        for host in ("0.0.0.0", "::", "10.0.0.5"):
            with self.subTest(host=host):
                result = proxy.serve(None, root=scratch(), host=host, port=0)

                self.assertFalse(result.ok)
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)
                self.assertEqual(
                    ["listener"], [item.name for item in result.assertions if not item.ok]
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
