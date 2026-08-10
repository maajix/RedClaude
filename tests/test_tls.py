"""The run's certificate authority: everything answerable without a server.

Intercepting a tunnel means presenting a certificate the agent's client will
accept for a host the harness does not own. That is the same act an attacker
performs, and the only thing that makes it legitimate here is that the trust is
*narrow*: one authority per run, trusted by one child environment, whose private
key never leaves the directory the door owns. So the properties worth testing
are the ones that keep it narrow.

`authority` is materialisation, and what is tested is that it is idempotent and
that the key is not readable by other accounts. Idempotence is not tidiness: a
door that minted a new authority on restart would invalidate a trust root the
child had already been handed, and the failure would look like a network fault.

`context` is issue, and it is held against a real handshake rather than against
the file it wrote. A certificate that parses is not a certificate a client
accepts; the two clients here -- one trusting the run root, one trusting the
system's -- are the difference between interception that works and interception
that is a silent hole. The address-literal case is separate because a SAN that
says `DNS:127.0.0.1` parses and verifies against nothing.

`agent_environment` is the other half of criterion one, and it is a pure
function so that what the child is told can be asserted exactly. Both proxy
schemes, named in both spellings, because the prototype configured only `http`
and the gap was not visible until something asked for `https`. And the trust
root only: the private key's path is not in the environment at all, because a
child that can read the signing key can mint the door's own certificate.
"""

from __future__ import annotations

import socket
import ssl
import stat
import threading
import unittest
from pathlib import Path
from unittest import mock

from redkraken import tls
from tests.fixtures import scratch

PROXY = "http://127.0.0.1:8080"


def handshake(server: ssl.SSLContext, client: ssl.SSLContext, host: str) -> bytes:
    """One TLS handshake over a socket pair, from the client's point of view.

    A pair rather than a listener because nothing here is about routing: what is
    being asked is whether this client accepts this certificate for this name.
    """
    left, right = socket.socketpair()
    failure: list[BaseException] = []

    def serve() -> None:
        try:
            with server.wrap_socket(left, server_side=True) as wrapped:
                wrapped.recv(1)
        # Broad on purpose, and nothing is swallowed: whatever the server side
        # raised is handed back to the test thread below, where a failure is a
        # failure rather than a line on stderr.
        except BaseException as error:
            failure.append(error)
            left.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with client.wrap_socket(right, server_hostname=host) as wrapped:
            peer = wrapped.getpeercert(binary_form=True)
            wrapped.send(b"x")
    finally:
        thread.join(timeout=5)
        right.close()
    if failure:
        raise failure[0]
    assert peer is not None
    return peer


class AuthorityTest(unittest.TestCase):
    def test_the_authority_survives_a_restart_of_the_door(self):
        root = scratch()

        first = tls.authority(root / "ca")
        second = tls.authority(root / "ca")

        self.assertEqual(first.certificate, second.certificate)
        self.assertEqual(first.certificate.read_bytes(), second.certificate.read_bytes())

    def test_the_signing_key_is_not_readable_by_other_accounts(self):
        made = tls.authority(scratch() / "ca")

        self.assertEqual(0o600, stat.S_IMODE(made.key.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(made.directory.stat().st_mode))

    def test_the_certificate_is_the_only_part_meant_to_be_handed_out(self):
        made = tls.authority(scratch() / "ca")

        self.assertNotIn(b"PRIVATE KEY", made.certificate.read_bytes())
        self.assertIn(b"BEGIN CERTIFICATE", made.certificate.read_bytes())

    def test_a_leaf_is_accepted_by_a_client_trusting_the_run_root(self):
        made = tls.authority(scratch() / "ca")

        peer = handshake(
            made.context("target.example"), tls.trust(made.certificate), "target.example"
        )

        self.assertTrue(peer)

    def test_a_leaf_is_refused_by_a_client_trusting_the_system(self):
        made = tls.authority(scratch() / "ca")

        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(
                made.context("target.example"),
                ssl.create_default_context(),
                "target.example",
            )

    def test_a_leaf_is_refused_for_a_host_it_does_not_name(self):
        made = tls.authority(scratch() / "ca")

        with self.assertRaises(ssl.SSLCertVerificationError):
            handshake(
                made.context("target.example"), tls.trust(made.certificate), "other.example"
            )

    def test_an_address_literal_gets_an_address_certificate(self):
        made = tls.authority(scratch() / "ca")

        peer = handshake(made.context("127.0.0.1"), tls.trust(made.certificate), "127.0.0.1")

        self.assertTrue(peer)

    def test_one_certificate_is_issued_per_host_and_kept(self):
        made = tls.authority(scratch() / "ca")

        self.assertIs(made.context("one.example"), made.context("one.example"))
        self.assertIsNot(made.context("one.example"), made.context("two.example"))

    def test_a_host_that_could_rewrite_the_certificate_is_refused(self):
        made = tls.authority(scratch() / "ca")

        with self.assertRaises(tls.Unusable):
            made.context("target.example\nbasicConstraints=critical,CA:TRUE")

    def test_an_authority_says_which_program_it_needs(self):
        root = scratch()

        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(tls.Unusable) as raised:
                tls.authority(root / "ca")

        self.assertIn("openssl", str(raised.exception))

    def test_a_directory_that_cannot_hold_an_authority_is_refused(self):
        occupied = scratch() / "ca"
        occupied.write_text("not a directory", encoding="utf-8")

        with self.assertRaises(tls.Unusable):
            tls.authority(occupied)


class EnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.made = tls.authority(scratch() / "ca")

    def environment(self, source: dict[str, str] | None = None) -> dict[str, str]:
        return tls.agent_environment(
            source if source is not None else {"PATH": "/usr/bin"},
            proxy_url=PROXY,
            certificate=self.made.certificate,
        )

    def test_both_proxy_schemes_are_named_in_both_spellings(self):
        child = self.environment()

        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
            self.assertEqual(PROXY, child[name], name)

    def test_nothing_is_left_to_bypass_the_door(self):
        child = self.environment({"no_proxy": "localhost,127.0.0.1"})

        self.assertEqual("", child["NO_PROXY"])
        self.assertEqual("", child["no_proxy"])

    def test_the_trust_root_is_installed_for_the_clients_a_child_runs(self):
        child = self.environment()

        for name in tls.TRUST_VARIABLES:
            self.assertEqual(str(self.made.certificate), child[name], name)

    def test_the_signing_key_is_not_in_the_child_environment(self):
        child = self.environment()

        for name, value in child.items():
            self.assertNotIn(str(self.made.key), value, name)
            self.assertNotIn("PRIVATE KEY", value, name)

    def test_what_the_child_was_given_otherwise_is_kept(self):
        child = self.environment({"PATH": "/usr/bin", "HOME": "/home/agent"})

        self.assertEqual("/usr/bin", child["PATH"])
        self.assertEqual("/home/agent", child["HOME"])

    def test_the_source_is_not_edited_in_place(self):
        source: dict[str, str] = {"PATH": "/usr/bin"}

        self.environment(source)

        self.assertEqual({"PATH": "/usr/bin"}, source)


if __name__ == "__main__":
    unittest.main()
