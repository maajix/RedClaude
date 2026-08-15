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
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from unittest import mock

from redkraken import identity, pg, proxy, scope, seal, tls
from redkraken.outcome import EXIT_INVALID_CONFIGURATION
from redkraken.store import Store
from tests.fixtures import (
    PINNED,
    WITHDRAWN,
    Redirecting,
    counterparty,
    scratch,
    tls_counterparty,
)


#: A capability the way the runtime mints one: 32 random bytes in lowercase hex.
CAPABILITY = "a" * 64
OTHER = "b" * 64

#: The Program every request here is filed under.
PROGRAM_ID = "11111111-1111-1111-1111-111111111111"
#: And the slot the stubbed budget hands out, named so that a test asserting the
#: door gave one back is asserting it gave back the one it took.
SLOT = "33333333-3333-3333-3333-333333333333"
IDENTITY_ID = "55555555-5555-5555-5555-555555555555"

#: What a refused capability looks like from the database, in the shape `pg`
#: renders one: the SQLSTATE, the message, and the frame it was raised in.
DATABASE_ERROR = (
    "23514: egress request is outside current scope | "
    "PL/pgSQL function authorize_egress_request(text,text,text,text,integer,"
    "text,text,text) line 71 at RAISE"
)

#: The same, for the second decision. A separate string because it is a separate
#: function: a test that could not tell the two apart could not tell "the name
#: was refused" from "the address the name pointed at was".
ADDRESS_ERROR = (
    "23514: egress destination 10.0.0.5 is withdrawn by the current scope | "
    "PL/pgSQL function authorize_egress_address(text,text,text,integer,text) "
    "line 63 at RAISE"
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


def client_identity() -> tuple[tls.Authority, identity.ClientCertificate]:
    """A valid clientAuth fixture under a CA the target can require."""
    root = tls.authority(scratch() / "client-identity-authority")
    directory = scratch()
    key = directory / "client-key.pem"
    request = directory / "client.csr"
    certificate = directory / "client.pem"
    extensions = directory / "client.ext"
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=clientAuth\n",
        encoding="utf-8",
    )
    for command in (
        [
            tls.OPENSSL,
            "req",
            "-new",
            "-noenc",
            "-newkey",
            "ec",
            "-pkeyopt",
            f"ec_paramgen_curve:{tls.CURVE}",
            "-subj",
            "/CN=redKraken fixture client",
            "-keyout",
            str(key),
            "-out",
            str(request),
        ],
        [
            tls.OPENSSL,
            "x509",
            "-req",
            "-sha256",
            "-in",
            str(request),
            "-CA",
            str(root.certificate),
            "-CAkey",
            str(root.key),
            "-CAcreateserial",
            "-days",
            str(tls.DAYS),
            "-extfile",
            str(extensions),
            "-out",
            str(certificate),
        ],
    ):
        subprocess.run(command, check=True, capture_output=True)
    return root, identity.ClientCertificate(
        certificate.read_text(encoding="utf-8"), key.read_text(encoding="utf-8")
    )


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
        self.withdrawn: set[str] = set()
        #: How many requests this capability has left. What expiry, a closed Tool
        #: run and a lapsed lease all look like from the door's side is this: the
        #: capability that worked a moment ago resolves to nothing now, and the
        #: next exchange stops before the target is contacted.
        self.revoked_after: int | None = None
        #: What the budget says, and it says yes by default. A stub that refused
        #: on a limit would make every test in this file a budget test; the ones
        #: that are about the budget set this to the refusal they want.
        self.slot: proxy.Reservation | None = None
        self.authorized: list[tuple] = []
        self.addressed: list[tuple] = []
        self.reserved: list[tuple] = []
        self.released: list[tuple] = []
        self.allowed: list[dict] = []
        self.blocked: list[dict] = []
        self.identity: proxy.IdentityBinding | None = None
        #: What the Program requires on every request, and it requires none by
        #: default. A stub that always returned one would make every test in this
        #: file a header test; the ones that are about required headers set this.
        self.required: list[tuple[str, str]] | Exception = []
        self.opened: list[tuple] = []

    def authorize(
        self, program_id: str, capability: str, method: str, request: scope.Request
    ) -> proxy.Authorization:
        self.authorized.append((program_id, capability, method, request))
        if (
            request.host in self.out_of_scope
            or capability != CAPABILITY
            or program_id != self.decided.program_id
            or (self.revoked_after is not None and len(self.authorized) > self.revoked_after)
        ):
            # Shaped like the real one: `Fence.authorize` turns a `DatabaseError`
            # into this, and the detail is the server's own text down to the
            # PL/pgSQL frame the exception was raised in.
            raise proxy.Refused("capability refused", DATABASE_ERROR)
        return self.decided

    def authorize_address(
        self, program_id: str, capability: str, request: scope.Request, address: str
    ) -> None:
        """The second decision, refusing by address the way the real one does.

        Withdrawal and silence, not scope membership: a policy written in names
        answers `unlisted` about nearly every address there is, and a stub that
        refused on that would be a stricter fence than the one in the schema.

        Nothing comes back, because nothing comes back from the real one: the
        Receipt records the class the *name* was allowed as, and an address a
        name-based policy has no rule about is `unlisted` almost every time.
        """
        self.addressed.append((program_id, capability, request, address))
        if address in self.withdrawn:
            raise proxy.Refused("address refused", ADDRESS_ERROR, pinned=(address,))

    def reserve(
        self, program_id: str, capability: str, request: scope.Request
    ) -> proxy.Reservation:
        """The third decision, granted unless a test asked for otherwise.

        Recorded rather than counted: what the handler owes this method is one
        call per request that got past the capability, and what it owes `release`
        is one call per grant. Whether the arithmetic behind a refusal is right
        is a question for the database, and is asked where the database is.
        """
        self.reserved.append((program_id, capability, request))
        if self.slot is not None:
            return self.slot
        return proxy.Reservation(
            id=SLOT,
            granted=True,
            reason="reserved",
            retry_at=None,
            target=request.host,
        )

    def release(self, program_id: str, reservation: str, contacted: bool) -> None:
        self.released.append((program_id, reservation, contacted))

    def allowed_receipt(
        self,
        program_id: str,
        capability: str,
        receipt: dict,
        artifacts: list[dict],
        seals: list[dict] | None = None,
        identity: proxy.IdentityBinding | None = None,
    ) -> dict:
        if self.fail:
            raise proxy.Refused("receipt write refused")
        self.allowed.append(
            {
                "program_id": program_id,
                "receipt": receipt,
                "artifacts": artifacts,
                "seals": list(seals or []),
                "identity": identity,
            }
        )
        return {"receipt_id": "33333333-3333-3333-3333-333333333333", "label": "R1"}

    def open_identity(
        self,
        program_id: str,
        capability: str,
        identity_entity_id: str,
        identity_label: str,
        root: seal.Root,
    ) -> proxy.IdentityBinding:
        if self.identity is None:
            raise proxy.Refused("identity slot refused", "the Identity has no provisioned slot")
        self.asserts = (program_id, capability, identity_entity_id, identity_label, root)
        return self.identity

    def required_headers(
        self, program_id: str, capability: str, root: seal.Root | None
    ) -> list[tuple[str, str]]:
        self.opened.append((program_id, capability, root))
        if isinstance(self.required, Exception):
            raise self.required
        return list(self.required)

    def wire_key(
        self, program_id: str, capability: str, root: seal.Root
    ) -> tuple[int, bytes]:
        if capability != CAPABILITY or program_id != self.decided.program_id:
            raise proxy.Refused("wire seal refused", status=502)
        salt = bytes(range(seal.SALT_BYTES))
        return 1, root.program_key(salt, generation=1, program_id=program_id)

    def blocked_receipt(self, program_id: str, capability: str | None, receipt: dict) -> str:
        self.blocked.append({"program_id": program_id, "receipt": receipt})
        # A label, because that is what the writer returns and what the caller
        # can look up. A stub answering with a uuid would let a door that put a
        # row id on the wire pass this suite.
        return "R4"


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

    def test_a_reflected_identity_in_a_redirect_cannot_enter_receipt_notes(self):
        marker = b"private-redirect-token"
        headers, _ = proxy.project_identity_response(
            [("Location", f"/continue/{marker.decode()}")], b""
        )

        location = next((value for name, value in headers if name.lower() == "location"), None)
        self.assertIsNone(proxy.redirected("https://app.example.com/start", location))
        self.assertEqual([], headers)

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


class AddressTest(unittest.TestCase):
    """Criteria 2 and 3, in the parts that need no socket and no decision."""

    def test_every_address_the_public_internet_does_not_route_to_is_refused(self):
        # Named one class at a time rather than asserted as "not global", because
        # the sentence in the blocked Receipt is what an operator reads to tell a
        # hostile target from a misconfigured Program. `224.0.0.1` is the reason
        # the multicast check exists at all: `is_global` answers yes for it.
        for address, said in (
            ("0.0.0.0", "unspecified"),
            ("::", "unspecified"),
            ("127.0.0.1", "loopback"),
            ("::1", "loopback"),
            ("::ffff:127.0.0.1", "loopback"),
            ("169.254.169.254", "link-local"),
            ("fe80::1", "link-local"),
            ("224.0.0.1", "multicast"),
            ("ff02::1", "multicast"),
            ("10.0.0.5", "not a public"),
            ("192.168.1.1", "not a public"),
            ("172.16.0.1", "not a public"),
            ("100.64.0.1", "not a public"),
            ("::ffff:10.0.0.5", "not a public"),
            ("not-an-address", "not an address"),
        ):
            with self.subTest(address=address):
                refused = proxy.unroutable(address)

                self.assertIsNotNone(refused)
                self.assertIn(said, refused)

    def test_a_public_address_is_the_one_thing_that_may_be_dialled(self):
        for address in (PINNED, "2606:2800:220:1:248:1893:25c8:1946"):
            with self.subTest(address=address):
                self.assertIsNone(proxy.unroutable(address))

    def test_a_name_that_answers_with_one_bad_address_answers_for_all_of_them(self):
        # The rebinding signature. Taking the address that passes would leave the
        # choice of which half gets dialled with whoever runs the zone, on a
        # lookup this door does not repeat.
        with self.assertRaises(proxy.Refused) as raised:
            proxy.destination(
                "target.example.test", 443, lambda host, port: (PINNED, "127.0.0.1")
            )

        self.assertEqual("address refused", raised.exception.reason)
        # Both, because a record naming only the offending one would not show
        # that a public answer was on offer beside it.
        self.assertEqual((PINNED, "127.0.0.1"), raised.exception.pinned)

    def test_a_name_that_answers_with_nothing_reaches_no_socket(self):
        for resolver in (
            lambda host, port: (),
            lambda host, port: (_ for _ in ()).throw(socket.gaierror("no such host")),
        ):
            with self.subTest(resolver=resolver):
                with self.assertRaises(proxy.Refused) as raised:
                    proxy.destination("target.example.test", 443, resolver)

                self.assertEqual("target unresolved", raised.exception.reason)
                # Nothing was resolved, so nothing is pinned: a blocked Receipt
                # carrying an empty address column would be a claim about an
                # answer that never came.
                self.assertEqual((), raised.exception.pinned)

    def test_the_addresses_come_back_in_the_order_the_resolver_gave_them(self):
        # The first is the one dialled, so the order is not decoration. Duplicates
        # collapse because a name with an A record and a matching AAAA-mapped one
        # has said one thing twice.
        addresses = proxy.destination(
            "target.example.test", 443, lambda host, port: (PINNED, "93.184.216.36", PINNED)
        )

        self.assertEqual((PINNED, "93.184.216.36"), addresses)

    def test_a_redirect_target_is_canonicalised_before_it_is_recorded(self):
        for location, expected in (
            ("/followed", "http://a.example.test/followed"),
            ("https://B.EXAMPLE.test:443/x", "https://b.example.test/x"),
            # Resolved against the request, and normalised: the record names the
            # URL a client would actually go to, not the one the target typed.
            ("../admin", "http://a.example.test/admin"),
            ("/v1/%2e%2e/admin", "http://a.example.test/admin"),
        ):
            with self.subTest(location=location):
                self.assertEqual(
                    expected, proxy.redirected("http://a.example.test/v1/notes", location)
                )

    def test_a_redirect_that_points_nowhere_usable_is_recorded_as_nothing(self):
        # Rather than as prose holding whatever the target sent. A `Location` this
        # module cannot canonicalise is one no client will follow through this
        # fence either, and putting it in the record unparsed would put target
        # bytes in a column an operator reads as the door's own words.
        for location in (None, "", "   ", "ftp://a.example.test/x", "https://a..b/x"):
            with self.subTest(location=location):
                self.assertIsNone(
                    proxy.redirected("http://a.example.test/v1/notes", location)
                )


class HandshakeTest(unittest.TestCase):
    """A target with a bad certificate is reached, and the certificate is filed.

    The targets this harness exists to reach are targets under test. An expired,
    a self-signed or a misnamed certificate is one of the findings it is looking
    for, and the door that refuses to speak to it produces no status, no bytes
    and -- because the refusal it wrote said `target unreachable` and nothing
    else -- no statement about the certificate either. So the strict attempt is
    made first, and what it failed with is kept.

    The fixture's target is signed by an authority that is not in this machine's
    trust store, which is what every one of those defects looks like from the
    door's side: a chain that does not verify. What the assertions are about is
    not that it connected but that the row can tell the difference between a
    verified target and this one.
    """

    @classmethod
    def setUpClass(cls):
        cls.target, cls.thread, cls.target_ca = tls_counterparty()
        cls.plain, cls.plain_thread = counterparty()
        cls.addClassCleanup(cls.target.shutdown)
        cls.addClassCleanup(cls.plain.shutdown)

    def dial(self, protocol: str = "https") -> proxy.Handshake | None:
        port = (self.target if protocol == "https" else self.plain).server_address[1]
        connection, negotiated = proxy.connect(
            "127.0.0.1", port, 5.0, protocol, "127.0.0.1", None
        )
        self.addCleanup(connection.close)
        # Used, not just opened. A socket dropped mid-handshake is a reset the
        # target logs from its own thread, and what is under test here is a
        # connection an exchange could be made over.
        connection.request("GET", "/v1/notes")
        connection.getresponse().read()
        return negotiated

    def test_a_target_whose_certificate_does_not_verify_is_still_reached(self):
        negotiated = self.dial()

        self.assertIsNotNone(negotiated)
        self.assertTrue(negotiated.tls_version.startswith("TLSv1."), negotiated.tls_version)
        self.assertEqual("127.0.0.1", negotiated.sni)
        self.assertRegex(negotiated.cert_sha256, r"^[0-9a-f]{64}$")

    def test_the_certificate_that_did_not_verify_is_what_the_record_says(self):
        negotiated = self.dial()

        # Both false, and both are columns rather than prose: `transport_citable`
        # is generated from exactly these two, so a downgraded exchange cannot be
        # cited as a measurement of the target's transport however it is read.
        self.assertFalse(negotiated.chain_verified)
        self.assertFalse(negotiated.hostname_verified)
        # And the target's own words for what was wrong with it, which is the
        # finding: "self-signed", "expired" and "does not match" all arrive here.
        self.assertIn("CERTIFICATE_VERIFY_FAILED", negotiated.defect)

    def test_a_plain_target_negotiates_nothing_and_says_so(self):
        # Nothing rather than a record full of nulls: "this hop was not TLS" and
        # "this hop was TLS and told us nothing" are different facts, and the
        # Receipt tells them apart by whether the columns were written at all.
        self.assertIsNone(self.dial("http"))

    def test_the_two_sides_are_recorded_together_or_the_wire_side_alone(self):
        wire = self.dial()
        agent = proxy.Handshake(
            tls_version="TLSv1.3",
            cipher="TLS_AES_256_GCM_SHA384",
            alpn="http/1.1",
            sni=None,
            cert_sha256="a" * 64,
            cert_issuer="commonName=RedKraken run authority",
            cert_subject="commonName=target.example.test",
            cert_not_after=None,
            chain_verified=True,
            hostname_verified=True,
        )

        both = proxy.transport(agent, wire)
        alone = proxy.transport(agent, None)

        self.assertEqual("TLSv1.3", both["agent_tls_version"])
        self.assertEqual(wire.cert_sha256, both["wire_cert_sha256"])
        self.assertFalse(both["wire_chain_verified"])
        # The leaf the door forged is known and still not written: naming it
        # means naming the forging key under `receipts_intercepted_leaf_names_ca`,
        # and nothing yet writes the `interception_cas` row it would point at.
        self.assertNotIn("agent_cert_sha256", both)
        # Neither side without the wire side. An agent-only row is the one a door
        # that did not know it was lying would write, and the table refuses it.
        self.assertEqual({}, alone)
        self.assertEqual({}, proxy.transport(None, None))

    def test_the_wire_side_may_be_recorded_with_no_agent_side_at_all(self):
        # A client that sent an absolute-form https request over a cleartext hop
        # instead of opening a tunnel. There is a target handshake to describe
        # and no agent one, and dropping the first to match the second would lose
        # the certificate of the exchange that actually happened.
        recorded = proxy.transport(None, self.dial())

        self.assertNotIn("agent_tls_version", recorded)
        self.assertIsNotNone(recorded["wire_cert_sha256"])
        self.assertFalse(recorded["wire_hostname_verified"])

    def test_a_certificate_defect_and_a_redirect_are_both_kept(self):
        wire = self.dial()

        self.assertEqual("redirect to http://a.example.test/x", proxy._notes(
            "redirect to http://a.example.test/x", None
        ))
        self.assertIn("CERTIFICATE_VERIFY_FAILED", proxy._notes(None, wire))
        # One column, both statements: a certificate defect must not be the
        # reason a redirect stops being recorded.
        together = proxy._notes("redirect to http://a.example.test/x", wire)
        self.assertIn("redirect to", together)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", together)
        self.assertIsNone(proxy._notes(None, None))


class RefusalTest(unittest.TestCase):
    """Which of the two things the second decision refused, the Receipt says so.

    That decision resolves the capability again before it looks at an address, so
    the same function raises for a Tool run that closed, a Program that was
    retired or a lease that lapsed since the first decision -- criterion 5's
    "between parent and child requests" landing one step later than usual. Both
    arrive as `23514`, so the text is what separates them, and a Receipt reading
    `address refused` for a lapsed lease sends an auditor to look at an address
    that was never the problem.
    """

    def failure(self, message: str) -> pg.DatabaseError:
        """One server error, in the fields the server actually sends them in."""
        return pg.DatabaseError(
            {
                "C": "23514",
                "M": message,
                "W": (
                    "PL/pgSQL function authorize_egress_address"
                    "(text,text,text,integer,text) line 63 at RAISE"
                ),
            }
        )

    def test_a_capability_that_lapsed_between_the_two_decisions_says_so(self):
        refused = proxy._refusal(self.failure("egress capability refused"), PINNED)

        self.assertEqual("capability refused", refused.reason)
        # Still pinned: the address was resolved, and a record that dropped it
        # would lose the one fact proving no socket was opened towards it.
        self.assertEqual((PINNED,), refused.pinned)

    def test_an_address_the_scope_withdrew_says_that_instead(self):
        refused = proxy._refusal(
            self.failure(f"egress destination {PINNED} is withdrawn by the current scope"),
            PINNED,
        )

        self.assertEqual("address refused", refused.reason)
        self.assertEqual((PINNED,), refused.pinned)

    def test_either_way_the_detail_is_the_server_own_words(self):
        for message in (
            "egress capability refused",
            "egress destination states no port in 1-65535",
        ):
            with self.subTest(message=message):
                refused = proxy._refusal(self.failure(message), PINNED)

                self.assertIn(message, refused.detail)
                self.assertIn("line 63 at RAISE", refused.detail)


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
        #: What the resolver answers with, and what it was asked. Both are the
        #: test's to set and to read: a name that answers with two addresses, or
        #: with none, is a case the door has to decide, and a refusal that
        #: resolved anything at all is a lookup that should not have happened.
        self.answers: tuple[str, ...] = (PINNED,)
        self.resolved: list[tuple[str, int]] = []
        self.dialled: list[tuple[str, int, str, str]] = []
        self.client_certificates: list[identity.ClientCertificate | None] = []
        self.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=self.fence,
            store=Store(self.root),
            connector=self.connector,
            resolver=self.resolver,
        )
        self.serving = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.serving.start()
        self.addCleanup(self.stop)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.serving.join(timeout=5)

    def resolver(self, host: str, port: int) -> tuple[str, ...]:
        """Every name answers with whatever this test decided it answers with."""
        self.resolved.append((host, port))
        if isinstance(self.answers, OSError):
            raise self.answers
        return self.answers

    def connector(
        self,
        host: str,
        port: int,
        timeout: float,
        protocol: str,
        address: str,
        client_certificate: identity.ClientCertificate | None,
    ) -> tuple[http.client.HTTPConnection, proxy.Handshake | None]:
        """The fixture, wherever the name pointed, and a record of both.

        No `Handshake`: these connections are handed back before they are
        dialled, so there is no handshake to read off one. What `connect` reads
        off a real socket has its own test.
        """
        self.dialled.append((host, port, protocol, address))
        self.client_certificates.append(client_certificate)
        mtls = getattr(self, "mtls", None)
        if protocol == "https" and mtls is not None:
            target, server_authority = mtls
            context = ssl.create_default_context(cafile=str(server_authority.certificate))
            if client_certificate is not None:
                client_certificate.install(context)
            return http.client.HTTPSConnection(
                "127.0.0.1",
                target.server_address[1],
                timeout=timeout,
                context=context,
            ), None
        return (
            http.client.HTTPConnection("127.0.0.1", self.target_port, timeout=timeout),
            None,
        )

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

    def refunds(self, count: int = 1) -> list[tuple]:
        """The slots the door gave back, waited for rather than sampled.

        `_serve` releases in a `finally`, which runs after the response has been
        written, so a client that has read its body has not necessarily seen the
        refund recorded yet. Sampling `fence.released` the instant `read()`
        returns tests this machine's scheduler; waiting for the count tests the
        door. The wait is bounded so a release that never comes fails as an
        empty list rather than as a hang.
        """
        deadline = time.monotonic() + 5
        while len(self.fence.released) < count and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.fence.released

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

    def test_the_address_that_was_decided_is_the_address_that_was_dialled(self):
        # Criterion 2. The name is resolved once, that answer is what the second
        # decision is made against, and it is what the socket is opened to: the
        # connector is handed an address rather than a name, so there is no
        # second lookup for a zone with a one-second life to answer differently.
        self.through("http://target.example.test/v1/notes").read()

        self.assertEqual([("target.example.test", 80)], self.resolved)
        self.assertEqual([("target.example.test", 80, "http", PINNED)], self.dialled)
        self.assertEqual(1, len(self.fence.addressed))
        _, capability, request, address = self.fence.addressed[0]
        self.assertEqual(CAPABILITY, capability)
        self.assertEqual("target.example.test", request.host)
        self.assertEqual(PINNED, address)
        self.assertEqual(PINNED, self.fence.allowed[0]["receipt"]["pinned_ips"])

    def test_the_receipt_names_every_address_the_name_answered_with(self):
        # Not only the one that was used. The check that let this request through
        # was made of all of them, and a record naming one could not be read back
        # as evidence that the others were looked at.
        self.answers = (PINNED, "93.184.216.36")

        self.through("http://target.example.test/v1/notes").read()

        self.assertEqual(PINNED, self.dialled[0][3])
        self.assertEqual(
            f"{PINNED},93.184.216.36", self.fence.allowed[0]["receipt"]["pinned_ips"]
        )

    def test_a_name_is_not_resolved_for_a_request_that_was_going_to_be_refused(self):
        # A lookup is egress: it leaves this machine carrying the name that was
        # asked for. Made before the decision, it would be an unrecorded channel
        # out of here for every refused request -- one that says a great deal to
        # whoever runs the zone and nothing to any Receipt.
        self.fence.out_of_scope.add("target.example.test")

        response = self.through("http://target.example.test/v1/notes")

        self.assertEqual(407, response.status)
        self.assertEqual([], self.resolved)
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.fence.addressed)
        self.assertEqual([], self.target.seen)

    def test_a_name_that_resolves_off_the_public_internet_opens_no_socket(self):
        # The rebinding case, and with it every address a name could point at
        # that this machine can reach and the internet cannot: the door itself,
        # the database behind it, the operator's network, the metadata endpoint.
        for answers in (
            ("127.0.0.1",),
            ("169.254.169.254",),
            (PINNED, "10.0.0.5"),
        ):
            with self.subTest(answers=answers):
                self.fence.blocked.clear()
                self.target.seen.clear()
                self.dialled.clear()
                self.answers = answers

                response = self.through("http://target.example.test/v1/notes")

                self.assertEqual(407, response.status)
                self.assertEqual([], self.dialled)
                self.assertEqual([], self.target.seen)
                filed = self.fence.blocked[0]["receipt"]
                self.assertEqual("address refused", filed["reason"])
                self.assertEqual(",".join(answers), filed["pinned_ips"])
                # In scope by name and refused by address, which is the case
                # worth telling apart from a request that was never in scope: a
                # `denied` here would file the two under one shape.
                self.assertEqual("target", filed["scope_class"])
                # Nothing left, so nothing waited: the moment of egress is what
                # separates a refusal from a refusal after contact.
                self.assertNotIn("ts_egress", filed)
                # And the policy was never asked. An address this door will not
                # dial is refused on its shape, before a decision is spent on it.
                self.assertEqual([], self.fence.addressed)

    def test_a_name_that_resolves_to_nothing_is_refused_with_no_address_named(self):
        self.answers = socket.gaierror("Name or service not known")

        response = self.through("http://target.example.test/v1/notes")

        # 502 and `target-unreachable`, not 407 and `capability-refused`. The
        # capability was minted, resolved and spent; what answered with nothing
        # is the target, and a 407 would ask this caller for the one thing that
        # was not missing. The Receipt has said so all along -- this is the same
        # sentence on the wire.
        self.assertEqual(502, response.status)
        self.assertEqual(proxy.UNREACHABLE, response.headers[proxy.DECISION])
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.target.seen)
        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("target unresolved", filed["reason"])
        self.assertNotIn("pinned_ips", filed)

    def test_a_socket_that_never_opened_is_not_answered_as_a_refused_capability(self):
        # The other half of the same distinction, on the far side of the
        # decisions: the name resolved, the address passed policy, the budget
        # reserved, and the dial failed. A target under test is down, or
        # firewalled, or speaking something this door cannot -- all findings
        # about the target, and none of them a capability an agent can improve.
        def refused(*arguments: object) -> tuple[http.client.HTTPConnection, None]:
            raise ConnectionRefusedError(111, "Connection refused")

        self.server.connector = refused

        response = self.through("http://target.example.test/v1/notes")
        response.read()

        self.assertEqual(502, response.status)
        self.assertEqual(proxy.UNREACHABLE, response.headers[proxy.DECISION])
        self.assertEqual([], self.fence.allowed)
        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("target unreachable", filed["reason"])
        # The dial happened, so the row says the request left this machine and
        # names the address it left for. A refusal made before contact is a
        # different fact and is recorded as one.
        self.assertIn("ts_egress", filed)
        self.assertEqual(PINNED, filed["pinned_ips"])

    def test_an_address_the_program_withdrew_is_refused_before_the_socket(self):
        # Criterion 2's second half, and the half the shape check cannot make:
        # the address is a perfectly routable one, the name passed the first
        # decision, and what refuses it is the current policy withdrawing the
        # machine. The door does not know why -- it cannot read the rules -- it
        # only ever learns the verdict.
        self.answers = (WITHDRAWN,)
        self.fence.withdrawn.add(WITHDRAWN)

        response = self.through("http://target.example.test/v1/notes")

        self.assertEqual(407, response.status)
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.target.seen)
        self.assertEqual(
            [(PROGRAM_ID, CAPABILITY, WITHDRAWN)],
            [(program, held, address) for program, held, _, address in self.fence.addressed],
        )
        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("address refused", filed["reason"])
        self.assertEqual(WITHDRAWN, filed["pinned_ips"])
        self.assertEqual("target", filed["scope_class"])
        # The database's own text explains it to the log and to nothing else.
        self.assertEqual("address refused", response.headers[proxy.DETAIL])
        self.assertNotIn("withdrawn by the current scope", str(response.headers))

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

    def test_target_credentials_are_stripped_and_the_wire_response_is_sealed(self):
        marker = "rk2-target-cookie-4f72d9"
        handler = self.target.RequestHandlerClass
        previous = handler.response_headers
        handler.response_headers = (("Set-Cookie", f"session={marker}; Secure; HttpOnly"),)
        self.addCleanup(setattr, handler, "response_headers", previous)
        root = seal.Root("test-only-root", b"p" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)

        response = self.through("http://target.example.test/v1/credential")
        body = response.read()

        self.assertEqual(200, response.status)
        self.assertEqual(self.target.RequestHandlerClass.answer, body)
        self.assertIsNone(response.headers.get("Set-Cookie"))
        recorded = self.fence.allowed[0]
        receipt = recorded["receipt"]
        self.assertIsNotNone(receipt["response_wire_sha"])
        self.assertNotEqual(receipt["response_agent_sha"], receipt["response_wire_sha"])
        visible = Store(self.root).load(receipt["response_agent_sha"])
        self.assertNotIn(marker.encode(), visible)

        [description] = recorded["seals"]
        envelope = Store(self.root).load(description["ciphertext_sha256"])
        self.assertNotIn(marker.encode(), envelope)
        key = self.fence.wire_key(PROGRAM_ID, CAPABILITY, root)[1]
        opened = seal.unseal(
            key,
            seal.Sealed.decode(envelope),
            aad=seal.associated_data(
                program_id=PROGRAM_ID,
                sha256=description["sha256"],
                generation=description["kek_gen"],
            ),
        )
        self.assertIn(marker.encode(), opened)
        self.assertFalse((self.root / description["sha256"][:2] / description["sha256"]).exists())

    def test_a_named_identity_is_injected_without_entering_the_agent_view(self):
        marker = "rk2-target-bearer-identity-8c40d1"
        root = seal.Root("test-only-root", b"i" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)
        self.fence.decided = proxy.Authorization(
            program_id=PROGRAM_ID,
            tool_run_id="22222222-2222-2222-2222-222222222222",
            scope_version=1,
            scope_class="target",
            identity_entity_id=IDENTITY_ID,
            identity_label="member",
        )
        self.fence.identity = proxy.IdentityBinding.provisioned(
            entity_id=IDENTITY_ID,
            label="member",
            revision=1,
            material={
                "schema_version": 1,
                "origins": [
                    {
                        "url": "http://target.example.test/",
                        "headers": [{"name": "Authorization", "value": f"Bearer {marker}"}],
                        "cookies": [],
                    }
                ],
            },
        )

        response = self.through("http://target.example.test/v1/identity")
        response.read()

        _, _, seen = self.target.seen[0]
        self.assertEqual(
            [f"Bearer {marker}"],
            [value for name, value in seen if name == "authorization"],
        )
        recorded = self.fence.allowed[0]
        receipt = recorded["receipt"]
        self.assertEqual(IDENTITY_ID, receipt["identity_entity_id"])
        self.assertNotEqual(receipt["request_agent_sha"], receipt["request_wire_sha"])
        visible = Store(self.root).load(receipt["request_agent_sha"])
        self.assertNotIn(marker.encode(), visible)

        [description] = [item for item in recorded["seals"] if item["field"] == "target_request"]
        envelope = Store(self.root).load(description["ciphertext_sha256"])
        self.assertNotIn(marker.encode(), envelope)
        key = self.fence.wire_key(PROGRAM_ID, CAPABILITY, root)[1]
        opened = seal.unseal(
            key,
            seal.Sealed.decode(envelope),
            aad=seal.associated_data(
                program_id=PROGRAM_ID,
                sha256=description["sha256"],
                generation=description["kek_gen"],
            ),
        )
        self.assertIn(marker.encode(), opened)

    def test_a_required_header_reaches_the_target_and_not_the_agent_view(self):
        """The whole of story 8: the target sees it, the model does not.

        Written against the wire the target read rather than against the receipt,
        because the failure this covers was a harness in which the record and the
        agent view agreed perfectly about a header neither of them had.
        """
        marker = "rk2-bounty-identifier-4d81ba"
        root = seal.Root("test-only-root", b"h" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)
        self.fence.required = [("X-Bounty-Id", marker)]

        response = self.through("http://target.example.test/v1/required")
        response.read()

        _, _, seen = self.target.seen[0]
        self.assertEqual(
            [marker], [value for name, value in seen if name == "x-bounty-id"]
        )
        recorded = self.fence.allowed[0]
        receipt = recorded["receipt"]
        self.assertNotEqual(receipt["request_agent_sha"], receipt["request_wire_sha"])
        visible = Store(self.root).load(receipt["request_agent_sha"])
        self.assertNotIn(marker.encode(), visible)
        self.assertNotIn(b"X-Bounty-Id", visible)

        [description] = [item for item in recorded["seals"] if item["field"] == "target_request"]
        envelope = Store(self.root).load(description["ciphertext_sha256"])
        self.assertNotIn(marker.encode(), envelope)
        opened = seal.unseal(
            self.fence.wire_key(PROGRAM_ID, CAPABILITY, root)[1],
            seal.Sealed.decode(envelope),
            aad=seal.associated_data(
                program_id=PROGRAM_ID,
                sha256=description["sha256"],
                generation=description["kek_gen"],
            ),
        )
        self.assertIn(marker.encode(), opened)

    def test_a_required_header_the_agent_set_itself_is_replaced_at_the_door(self):
        """The Program's value wins, and the agent's spelling of the name loses.

        A model that writes its own `X-Bounty-Id` is either guessing or probing.
        Appending would send two, and which one the target honours is its own
        business; the door owns this field, so it takes the agent's copy out
        first -- case-insensitively, because the wire is.
        """
        root = seal.Root("test-only-root", b"h" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)
        self.fence.required = [("X-Bounty-Id", "rk2-the-program-value")]

        response = self.through(
            "http://target.example.test/v1/required",
            headers=[("x-BOUNTY-id", "rk2-the-agent-guess")],
        )
        response.read()

        _, _, seen = self.target.seen[0]
        self.assertEqual(
            ["rk2-the-program-value"],
            [value for name, value in seen if name == "x-bounty-id"],
        )

    def test_a_required_header_with_no_value_refuses_before_the_target_is_contacted(self):
        """No value, no request. The alternative is unattributable traffic.

        The refusal names itself: `required-header-refused` is not
        `capability-refused`, because the capability was good and the thing
        missing is one an operator fixes with `rk header provision`.
        """
        self.fence.required = proxy.Refused(
            proxy.HEADER_MISSING,
            "X-Bounty-Id is required on every request and no value is provisioned",
            status=502,
        )

        response = self.through("http://target.example.test/v1/required")
        response.read()

        self.assertEqual(502, response.status)
        self.assertEqual(
            proxy.HEADERLESS, response.headers.get("X-RedKraken-Decision")
        )
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.allowed)
        [blocked] = self.fence.blocked
        self.assertEqual(proxy.HEADER_MISSING, blocked["receipt"]["reason"])

    def test_a_reflected_identity_token_is_removed_from_every_agent_response_field(self):
        marker = "rk2-reflected-identity-token-97e1d3"
        cookie = "rk2-reflected-cookie-89b2a4"
        old_cookie = "rk2-rotated-cookie-17d6f8"
        handler = self.target.RequestHandlerClass
        prior_headers, prior_answer = handler.response_headers, handler.answer
        handler.response_headers = (
            ("X-Reflected-Token", f"prefix {marker}"),
            (f"X-{marker}", "reflected in the field name"),
            ("Set-Cookie", f"session={cookie}; HttpOnly"),
        )
        handler.answer = (
            f'{{"authorization":"Bearer {marker}","old":"{old_cookie}",'
            f'"session":"{cookie}"}}'.encode()
        )
        self.addCleanup(setattr, handler, "response_headers", prior_headers)
        self.addCleanup(setattr, handler, "answer", prior_answer)
        root = seal.Root("test-only-root", b"r" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)
        self.fence.decided = proxy.Authorization(
            program_id=PROGRAM_ID,
            tool_run_id="22222222-2222-2222-2222-222222222222",
            scope_version=1,
            scope_class="target",
            identity_entity_id=IDENTITY_ID,
            identity_label="member",
        )
        self.fence.identity = proxy.IdentityBinding.provisioned(
            entity_id=IDENTITY_ID,
            label="member",
            revision=1,
            material={
                "schema_version": 1,
                "origins": [
                    {
                        "url": "http://target.example.test/",
                        "headers": [
                            {"name": "Authorization", "value": f"Bearer {marker}"}
                        ],
                        "cookies": [f"session={old_cookie}; Path=/; HttpOnly"],
                    }
                ],
            },
        )

        response = self.through("http://target.example.test/v1/reflection")
        body = response.read()

        self.assertEqual(b"", body)
        self.assertNotIn(marker.encode(), body)
        self.assertNotIn(cookie.encode(), body)
        self.assertNotIn(old_cookie.encode(), body)
        self.assertIsNone(response.headers.get("X-Reflected-Token"))
        self.assertIsNone(response.headers.get(f"X-{marker}"))
        receipt = self.fence.allowed[0]["receipt"]
        self.assertNotEqual(receipt["response_agent_sha"], receipt["response_wire_sha"])
        visible = Store(self.root).load(receipt["response_agent_sha"])
        self.assertNotIn(marker.encode(), visible)
        self.assertNotIn(cookie.encode(), visible)
        self.assertNotIn(old_cookie.encode(), visible)
        [description] = [
            item for item in self.fence.allowed[0]["seals"] if item["field"] == "target_response"
        ]
        envelope = Store(self.root).load(description["ciphertext_sha256"])
        opened = seal.unseal(
            self.fence.wire_key(PROGRAM_ID, CAPABILITY, root)[1],
            seal.Sealed.decode(envelope),
            aad=seal.associated_data(
                program_id=PROGRAM_ID,
                sha256=description["sha256"],
                generation=description["kek_gen"],
            ),
        )
        self.assertIn(marker.encode(), opened)
        self.assertIn(cookie.encode(), opened)
        self.assertIn(old_cookie.encode(), opened)

    def test_an_identity_client_certificate_reaches_only_the_https_connector(self):
        server_authority = tls.authority(scratch() / "mtls-target-authority")
        client_authority, credential = client_identity()
        target_context = server_authority.context("127.0.0.1")
        target_context.load_verify_locations(cafile=str(client_authority.certificate))
        target_context.verify_mode = ssl.CERT_REQUIRED
        target, thread = counterparty(context=target_context)
        self.addCleanup(thread.join, 5)
        self.addCleanup(target.server_close)
        self.addCleanup(target.shutdown)
        self.mtls = (target, server_authority)
        root = seal.Root("test-only-root", b"m" * seal.KEY_BYTES)
        self.server.root_secret = root
        self.addCleanup(setattr, self.server, "root_secret", None)
        self.fence.decided = proxy.Authorization(
            program_id=PROGRAM_ID,
            tool_run_id="22222222-2222-2222-2222-222222222222",
            scope_version=1,
            scope_class="target",
            identity_entity_id=IDENTITY_ID,
            identity_label="member",
        )
        self.fence.identity = proxy.IdentityBinding.provisioned(
            entity_id=IDENTITY_ID,
            label="member",
            revision=1,
            material={
                "schema_version": 1,
                "origins": [
                    {
                        "url": "https://target.example.test/",
                        "headers": [],
                        "cookies": [],
                        "client_certificate": {
                            "certificate_pem": credential.certificate_pem,
                            "private_key_pem": credential.private_key_pem,
                        },
                    }
                ],
            },
        )

        response = self.through("https://target.example.test/v1/mtls")
        response.read()

        self.assertEqual(200, response.status)
        [credential] = self.client_certificates
        self.assertIsNotNone(credential)
        self.assertIn("BEGIN CERTIFICATE", credential.certificate_pem)
        self.assertEqual(1, len(target.seen))
        self.assertEqual(
            credential.public_sha256(),
            self.fence.allowed[0]["receipt"]["identity_tls_cert_sha256"],
        )

    def test_an_oversized_captured_session_becomes_a_fence_refusal(self):
        binding = proxy.IdentityBinding.provisioned(
            entity_id=IDENTITY_ID,
            label="member",
            revision=1,
            material={
                "schema_version": 1,
                "origins": [
                    {
                        "url": "https://target.example.test/",
                        "headers": [],
                        "cookies": [],
                    }
                ],
            },
        )
        binding.changed = binding.session.capture(
            "https://target.example.test/",
            [("Set-Cookie", f"cookie{index}=x") for index in range(6_000)],
        )
        binding.root = seal.Root("test-only-root", b"o" * seal.KEY_BYTES)
        binding.salt = b"s" * seal.SALT_BYTES
        binding.generation = 1

        with self.assertRaises(proxy.Refused) as raised:
            proxy.Fence(None).allowed_receipt(
                PROGRAM_ID, CAPABILITY, {}, [], binding=binding
            )

        self.assertEqual("identity session refused", raised.exception.reason)

    def test_a_target_credential_response_fails_closed_without_the_artifact_key(self):
        marker = "rk2-target-cookie-no-key"
        handler = self.target.RequestHandlerClass
        previous = handler.response_headers
        handler.response_headers = (("Set-Cookie", f"session={marker}"),)
        self.addCleanup(setattr, handler, "response_headers", previous)

        response = self.through("http://target.example.test/v1/credential")
        body = response.read()

        self.assertEqual(502, response.status)
        self.assertEqual(proxy.REFUSED, response.headers[proxy.DECISION])
        self.assertIsNone(response.headers.get("Set-Cookie"))
        self.assertEqual(b"", body)
        self.assertEqual([], self.fence.allowed)
        self.assertEqual("wire response refused", self.fence.blocked[0]["receipt"]["reason"])

    def test_a_stored_request_transcript_holds_no_control_header(self):
        self.through("http://target.example.test/v1/notes").read()

        receipt = self.fence.allowed[0]["receipt"]
        stored = Store(self.root).load(receipt["request_agent_sha"])

        self.assertIn(b"GET /v1/notes HTTP/1.1", stored)
        self.assertNotIn(CAPABILITY.encode(), stored)
        self.assertNotIn(b"Proxy-Authorization", stored)
        self.assertNotIn(b"X-RedKraken", stored)

    def test_an_exhausted_budget_refuses_before_the_name_is_even_resolved(self):
        # Ticket 13, criterion 4. The refusal is not about this request -- the
        # capability resolved and the target was in scope -- so what has to be
        # true is that nothing left the machine anyway: no lookup, no socket, and
        # a blocked Receipt saying which limit it was.
        self.fence.slot = proxy.Reservation(
            id=None, granted=False, reason="budget exhausted", retry_at=None, target="t"
        )

        response = self.through("http://target.example.test/v1/notes")
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual(proxy.BUDGETED, response.headers[proxy.DECISION])
        self.assertEqual("budget exhausted", response.headers[proxy.DETAIL])
        self.assertEqual([], self.resolved)
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.target.seen)
        self.assertEqual(1, len(self.fence.blocked))
        self.assertEqual("budget exhausted", self.fence.blocked[0]["receipt"]["reason"])
        # And nothing to give back: there was no slot, so releasing one would be
        # refunding a Program a request it never took.
        self.assertEqual([], self.fence.released)

    def test_a_throttled_request_is_told_when_to_come_back(self):
        # The other half of criterion 4: durable retry information. It is in the
        # Receipt as a moment, because a row is what a retry is reconstructed
        # from later, and on the wire as seconds, because the caller's clock is
        # not this machine's.
        later = datetime.now(timezone.utc) + timedelta(seconds=42)
        self.fence.slot = proxy.Reservation(
            id=None, granted=False, reason="rate limited", retry_at=later, target="t"
        )

        response = self.through("http://target.example.test/v1/notes")
        response.read()

        self.assertEqual(proxy.BUDGETED, response.headers[proxy.DECISION])
        self.assertEqual("rate limited", response.headers[proxy.DETAIL])
        self.assertIn(int(response.headers["Retry-After"]), range(1, 43))
        self.assertEqual(
            later.isoformat(), self.fence.blocked[0]["receipt"]["retry_after"]
        )
        self.assertEqual([], self.target.seen)

    def test_a_served_request_gives_its_slot_back_and_says_it_reached_the_target(self):
        # Criterion 3 depends on this: a slot that is never released is a Program
        # throttling itself, and a slot released as uncontacted is a request the
        # Program made and was not charged for.
        self.through("http://target.example.test/v1/notes").read()

        self.assertEqual(1, len(self.fence.reserved))
        self.assertEqual(
            [("11111111-1111-1111-1111-111111111111", SLOT, True)], self.refunds()
        )

    def test_a_slot_taken_for_a_request_that_never_left_is_given_back_unspent(self):
        # The refund. The name resolves off the public internet, so the request
        # is refused after it reserved and before anything was dialled: the
        # Program's allowance should be exactly where it started.
        self.answers = ("127.0.0.1",)

        response = self.through("http://target.example.test/v1/notes")
        response.read()

        self.assertEqual(407, response.status)
        self.assertEqual([], self.dialled)
        self.assertEqual(
            ("11111111-1111-1111-1111-111111111111", SLOT, False), self.refunds()[0]
        )

    def test_a_request_with_no_capability_reserves_nothing(self):
        # Order, stated as a test: the budget is asked after the capability, so a
        # caller with no capability cannot drain a Program's allowance by sending
        # requests that were never going to be authorized.
        self.through("http://target.example.test/v1/notes", capability=None).read()

        self.assertEqual([], self.fence.reserved)
        self.assertEqual([], self.fence.released)

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
        #
        # It is a label and not a row id, which is the same name the served path
        # answers with. `rk state --label` resolves labels and nothing else, so a
        # uuid here would be a citation the caller it is handed to cannot follow.
        response = self.through("http://target.example.test/v1/notes", capability=OTHER)
        response.read()

        self.assertEqual("R4", response.headers[proxy.RECEIPT])
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


class Redirected(unittest.TestCase):
    """A door, a redirecting target and a client that follows what it is told.

    The fixture and none of the assertions, because the two suites below assert
    different things about the same arrangement: one where every hop is in scope
    and one where the second is not. Sharing it by inheritance would mean one of
    them inheriting three tests it replaces, which reads as "the same tests, run
    twice" and is not.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = scratch() / "redirect-store"
        cls.root.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.target, self.thread = counterparty(self.handler())
        self.target_port = self.target.server_address[1]
        self.addCleanup(self.shutdown)
        self.fence = Stub()
        self.dialled: list[str] = []
        self.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=self.fence,
            store=Store(self.root),
            connector=self.connector,
            resolver=lambda host, port: (PINNED,),
        )
        self.serving = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.serving.start()
        self.addCleanup(self.stop)
        self.enterContext(mock.patch.dict(os.environ, {"no_proxy": "", "NO_PROXY": ""}))

    def handler(self) -> type:
        return Redirecting

    def shutdown(self) -> None:
        self.target.shutdown()
        self.target.server_close()
        self.thread.join(timeout=5)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.serving.join(timeout=5)

    def connector(
        self,
        host: str,
        port: int,
        timeout: float,
        protocol: str,
        address: str,
        client_certificate: identity.ClientCertificate | None,
    ) -> tuple[http.client.HTTPConnection, proxy.Handshake | None]:
        self.dialled.append(address)
        return (
            http.client.HTTPConnection("127.0.0.1", self.target_port, timeout=timeout),
            None,
        )

    def fetch(self, url: str):
        """One request from a client that follows what it is told to follow."""
        door = "http://%s:%d" % self.server.server_address
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": door}))
        asked = urllib.request.Request(url)
        asked.add_header(proxy.AUTHORIZATION, f"RedKraken {CAPABILITY}")
        asked.add_header(proxy.PROGRAM, PROGRAM_ID)
        return opener.open(asked, timeout=5)


class RedirectTest(Redirected):
    """Criteria 3, 4 and 5: every hop is its own exchange, or it is not one.

    An ordinary client, following an ordinary redirect. That is the whole design
    of it: the door does not follow, because following would be an exchange
    nobody asked for against a target nobody named. The client follows, comes
    back through the same fence, and the second request is decided from nothing
    but itself -- its own capability check, its own address, its own Receipt.

    `urllib` rather than a hand-written pair of requests, because what is under
    test is the behaviour of a client the door does not control: a test that sent
    the second request itself would be asserting that the suite follows
    redirects, which nothing in production depends on.
    """

    def test_a_followed_redirect_is_a_second_exchange_with_a_receipt_of_its_own(self):
        answer = self.fetch("http://target.example.test/v1/notes")

        self.assertEqual(200, answer.status)
        self.assertEqual(b'{"note":"target answered"}', answer.read())
        # Two of everything, which is the criterion: two decisions, two lookups,
        # two sockets, two Receipts, two contacts at the target.
        self.assertEqual(2, len(self.fence.authorized))
        self.assertEqual(2, len(self.fence.addressed))
        self.assertEqual([PINNED, PINNED], self.dialled)
        self.assertEqual(2, len(self.fence.allowed))
        self.assertEqual([], self.fence.blocked)
        self.assertEqual(
            ["/v1/notes", "/followed"], [path for _, path, _ in self.target.seen]
        )
        # One capability, spent twice and resolved twice. §7 has subresources and
        # redirects sharing one, and each earning its own verdict is what makes
        # the sharing safe rather than a second request nobody decided. That both
        # Receipts land under the parent's Tool run is the database's half of the
        # criterion and is asserted there: the Tool run is resolved from the
        # capability inside the fence, so a stub asserting it here would be
        # asserting its own constant.
        self.assertEqual({CAPABILITY}, {held for _, held, _, _ in self.fence.authorized})
        self.assertEqual({CAPABILITY}, {held for _, held, _, _ in self.fence.addressed})
        # Two Receipts, and two different exchanges rather than one written twice.
        self.assertEqual(
            [("/v1/notes", 303), ("/followed", 200)],
            [
                (written["receipt"]["path"], written["receipt"]["status_code"])
                for written in self.fence.allowed
            ],
        )

    def test_the_receipt_for_a_redirect_names_where_it_pointed(self):
        # The chain, written down. Without it the child Receipt names a URL
        # nobody asked for, and an auditor cannot tell a followed redirect from
        # an agent that invented a target for itself.
        self.fetch("http://target.example.test/v1/notes").read()

        parent, child = (written["receipt"] for written in self.fence.allowed)

        self.assertEqual(303, parent["status_code"])
        self.assertEqual(
            "redirect to http://target.example.test/followed", parent["notes"]
        )
        self.assertEqual(200, child["status_code"])
        self.assertEqual("/followed", child["path"])
        # And the child says nothing about a redirect, because it is not one.
        self.assertIsNone(child["notes"])

    def test_a_capability_that_stopped_resolving_stops_the_next_hop_before_contact(self):
        # Criterion 5 on the door's side. Expiry, a closed Tool run, a finished
        # agent run and a lapsed lease are one thing from here: the capability
        # that worked for the parent resolves to nothing for the child, and the
        # child never reaches the target.
        self.fence.revoked_after = 1

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch("http://target.example.test/v1/notes")

        raised.exception.close()
        self.assertEqual(407, raised.exception.code)
        self.assertEqual(1, len(self.fence.allowed))
        self.assertEqual(1, len(self.fence.blocked))
        self.assertEqual([PINNED], self.dialled)
        self.assertEqual(["/v1/notes"], [path for _, path, _ in self.target.seen])
        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("capability refused", filed["reason"])
        self.assertEqual("/followed", filed["path"])
        # Refused before the name was even resolved, so nothing about the child
        # left this machine at all.
        self.assertNotIn("pinned_ips", filed)
        self.assertNotIn("ts_egress", filed)


class CrossHostRedirectTest(Redirected):
    """The same chain, pointed at a host the Program does not cover.

    A redirect is the cheapest way to ask a fence to fetch something it would
    have refused: the first URL is in scope, and the answer to it names the
    second. Every assertion here is that the second one is decided anyway.
    """

    def handler(self) -> type:
        class Elsewhere(Redirecting):
            elsewhere = "http://other.example.test/followed"

        return Elsewhere

    def setUp(self):
        super().setUp()
        self.fence.out_of_scope.add("other.example.test")

    def test_a_followed_redirect_is_a_second_exchange_with_a_receipt_of_its_own(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch("http://target.example.test/v1/notes")

        raised.exception.close()
        self.assertEqual(407, raised.exception.code)
        self.assertEqual(2, len(self.fence.authorized))
        self.assertEqual(1, len(self.fence.allowed))
        self.assertEqual(1, len(self.fence.blocked))
        # One contact, and it is the parent's. The refused hop opened nothing.
        self.assertEqual(["/v1/notes"], [path for _, path, _ in self.target.seen])
        self.assertEqual([PINNED], self.dialled)
        self.assertEqual("other.example.test", self.fence.blocked[0]["receipt"]["host"])

    def test_the_receipt_for_a_redirect_names_where_it_pointed(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch("http://target.example.test/v1/notes")
        raised.exception.close()

        parent = self.fence.allowed[0]["receipt"]

        # Canonicalised, and by this module rather than repeated from the wire:
        # the port the scheme implies is dropped and the host is lowercased, so
        # the note is the spelling the next decision was made against.
        self.assertEqual(
            "redirect to http://other.example.test/followed", parent["notes"]
        )

    def test_a_capability_that_stopped_resolving_stops_the_next_hop_before_contact(self):
        # The parent is enough here: with the child refused for its host as well,
        # this class would be asserting the same thing twice.
        self.fence.revoked_after = 1

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch("http://target.example.test/v1/notes")

        raised.exception.close()
        self.assertEqual(407, raised.exception.code)
        self.assertEqual([PINNED], self.dialled)
        self.assertEqual(1, len(self.fence.blocked))


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
        #: What every name inside a tunnel answers with, and which addresses a
        #: socket was opened to. The same two seams `ExchangeTest` has, because
        #: the claim this class makes is that the https path is the http one.
        self.answers: tuple[str, ...] = (PINNED,)
        self.dialled: list[str] = []
        self.server = proxy.listen(
            ("127.0.0.1", 0),
            fence=self.fence,
            store=Store(self.root),
            connector=self.connector,
            resolver=lambda host, port: self.answers,
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
        self,
        host: str,
        port: int,
        timeout: float,
        protocol: str,
        address: str,
        client_certificate: identity.ClientCertificate | None,
    ) -> tuple[http.client.HTTPConnection, proxy.Handshake | None]:
        """The door's outbound side, verifying the target it was sent to.

        In production this is `proxy.connect`, which verifies against the system
        store; here the fixture's own root stands in for it. The point of the
        substitution is what stays the same: the door checks the target's
        certificate itself, because the agent no longer can.
        """
        self.dialled.append(address)
        context = ssl.create_default_context(cafile=str(self.target_ca))
        if client_certificate is not None:
            client_certificate.install(context)
        return http.client.HTTPSConnection(
            "127.0.0.1",
            self.target_port,
            timeout=timeout,
            context=context,
        ), None

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
        self.assertEqual("R4", answer.receipt)
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

    def test_an_address_withdrawn_inside_a_tunnel_is_refused_like_any_other(self):
        # Criterion 2 on the https path, which is the path a rebinding answer is
        # worth the most on: the leaf the door mints is for the name in the
        # CONNECT line, so a name that moves between the tunnel and the request
        # inside it would otherwise be a target certificate this door verified
        # for one machine and a socket it opened to another.
        self.answers = (WITHDRAWN,)
        self.fence.withdrawn.add(WITHDRAWN)

        answer = self.spend("https://target.example.test/v1/notes")

        self.assertEqual(407, answer.status)
        self.assertEqual(proxy.REFUSED, answer.decision)
        self.assertEqual("address refused", answer.detail)
        # The tunnel opened and the target was never contacted through it.
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.target.seen)
        self.assertEqual([], self.fence.allowed)

        filed = self.fence.blocked[0]["receipt"]
        self.assertEqual("address refused", filed["reason"])
        self.assertEqual("https", filed["scheme"])
        self.assertEqual(WITHDRAWN, filed["pinned_ips"])
        # The name was decided first and the address second, through the same
        # two calls a plain request makes.
        self.assertEqual(
            [("target.example.test", 443)],
            [(asked.host, asked.port) for *_, asked in self.fence.authorized],
        )
        self.assertEqual(
            [("target.example.test", WITHDRAWN)],
            [(asked.host, address) for _, _, asked, address in self.fence.addressed],
        )

    def test_a_name_inside_a_tunnel_that_answers_off_the_public_internet_is_refused(self):
        # The rebinding answer itself, on the https path. `127.0.0.1` is where
        # the fixture target listens, so an answer the door accepted here would
        # be a socket to the loopback interface of the machine running the door.
        self.answers = ("127.0.0.1",)

        answer = self.spend("https://target.example.test/v1/notes")

        self.assertEqual(407, answer.status)
        self.assertEqual("address refused", answer.detail)
        self.assertEqual([], self.dialled)
        self.assertEqual([], self.target.seen)
        self.assertEqual("127.0.0.1", self.fence.blocked[0]["receipt"]["pinned_ips"])
        # Refused by the door before the database was asked: the address never
        # reached the second decision, because it is not one this door dials
        # whatever a policy says about it.
        self.assertEqual([], self.fence.addressed)

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

    def test_the_door_itself_checks_the_target_no_public_authority_vouches_for(self):
        # Every test above substitutes `connector`, so this is the one that runs
        # the production one. The fixture target holds a certificate from an
        # authority nobody has heard of, which is both what a target impersonated
        # between the door and the internet would look like and what a target
        # with an expired or self-signed certificate looks like. The door is the
        # only side that can tell, because the agent is looking at this door's
        # certificate rather than the target's.
        #
        # It is checked here rather than in the request after it, because pinning
        # moved the handshake into `connect`: the socket is opened against the
        # decided address and wrapped immediately, so there is no moment where a
        # caller holds a connection whose peer has not been looked at.
        #
        # It is reached anyway, and that is the deliberate half. Refusing gave
        # the agent "target unreachable" and no certificate, which is the one
        # answer that is useless about a target under test. The verdict is on the
        # Receipt instead: the chain and the name were not verified, so
        # `transport_citable` is false for this exchange whatever is done with it.
        connection, negotiated = proxy.connect(
            "127.0.0.1", self.target_port, 5.0, "https", "127.0.0.1", None
        )
        self.addCleanup(connection.close)

        self.assertFalse(negotiated.chain_verified)
        self.assertFalse(negotiated.hostname_verified)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", negotiated.defect)
        self.assertRegex(negotiated.cert_sha256, r"^[0-9a-f]{64}$")
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
