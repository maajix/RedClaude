"""Callback admission: everything answerable without a listener or a server.

Three seams are pure and each one carries a criterion.

`_name` is the spelling. An arrival is compared against the channel list by
name, so a name canonicalised one way here and another way in SQL would be a
name the two halves disagree about; the tests hold it against `normalize_host`
rather than against itself.

`_correlator` is the attribution. Ticket 14 says a correlator binds one inbound
record to one run, and the binding starts by finding the token in the name it
arrived at: the label immediately beneath the channel endpoint, whatever the
target's own resolver put above it. The endpoint itself carries none, and an
interaction nobody can attribute is refused rather than filed.

The third is the refusal surface, and it is the one worth having offline: an
undeclared host, the endpoint's own parent, an adjacent name, a channel this
Program does not declare and a lifetime nobody chose are all refused before a
connection is opened, so nothing about them reaches the database and the bytes
of an arrival at somebody else's host are never stored.

What needs a server -- that a live correlator confirms exactly one Hypothesis,
that a missing, expired, fabricated or cross-Program one confirms none, and that
the exact inbound bytes become an immutable Observation -- is in
`tests/test_database.py`.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from redkraken import callback, config, pg, scope
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INVALID_CONFIGURATION,
    Ledger,
)
from tests.fixtures import SCOPED, VALID, scratch, write


UNREACHABLE = "postgresql://rk2_runtime@127.0.0.1:1/rk2"

#: The DNS channel `SCOPED` declares, and one arrival at it.
ENDPOINT = "dns.example.org"
CORRELATOR = "0123456789abcdef0123456789abcdef"
BODY = b"\x00\x01\x81\x80 query for a canary\n"


def settings() -> pg.Settings:
    return pg.settings_from_url(UNREACHABLE, application_name="rk callback")


def channel(host: str = ENDPOINT, kind: str = "dns") -> scope.Channel:
    return scope.Channel(name="oob", kind=kind, host=host)


def arrival(data: bytes = BODY) -> Path:
    """One recorded interaction, as a listener would have left it on disk."""
    path = scratch() / "arrival.bin"
    path.write_bytes(data)
    return path


def policy(text: str = SCOPED) -> scope.Policy:
    configuration, refusals = config.load(write(text))
    assert configuration is not None, refusals
    compiled, violations = scope.compile_policy(configuration)
    assert compiled is not None, violations
    return compiled


class NameTest(unittest.TestCase):
    """The observed host, in the one spelling the policy compares in."""

    def test_the_name_is_canonicalised_the_way_every_other_host_is(self):
        for raw in (
            f" {CORRELATOR}.{ENDPOINT} ",
            f"{CORRELATOR}.{ENDPOINT}.",
            f"{CORRELATOR}.{ENDPOINT}".upper(),
        ):
            with self.subTest(raw):
                ledger = Ledger()

                self.assertEqual(f"{CORRELATOR}.{ENDPOINT}", callback._name(ledger, raw))
                self.assertEqual(
                    scope.normalize_host(raw), callback._name(Ledger(), raw)
                )
                self.assertFalse(ledger.violations)

    def test_a_name_that_is_not_one_is_refused_rather_than_repaired(self):
        for raw in ("", "   ", f"{CORRELATOR}..{ENDPOINT}", f"{CORRELATOR} {ENDPOINT}"):
            with self.subTest(repr(raw)):
                ledger = Ledger()

                self.assertIsNone(callback._name(ledger, raw))

                self.assertTrue(ledger.violations)


class CorrelatorTest(unittest.TestCase):
    """Which label of the observed name the runtime minted."""

    def test_the_correlator_is_the_label_beneath_the_endpoint(self):
        self.assertEqual(
            CORRELATOR,
            callback._correlator(Ledger(), f"{CORRELATOR}.{ENDPOINT}", channel()),
        )

    def test_labels_the_target_put_above_it_do_not_change_it(self):
        # A resolver that queried `www.<correlator>.<endpoint>` is reporting one
        # arrival on one canary. What it prefixed is the target's business.
        for observed in (
            f"www.{CORRELATOR}.{ENDPOINT}",
            f"a.b.c.{CORRELATOR}.{ENDPOINT}",
        ):
            with self.subTest(observed):
                self.assertEqual(
                    CORRELATOR,
                    callback._correlator(Ledger(), observed, channel()),
                )

    def test_the_endpoint_itself_carries_no_correlator_and_is_refused(self):
        ledger = Ledger()

        self.assertIsNone(callback._correlator(ledger, ENDPOINT, channel()))

        self.assertTrue(ledger.violations)

    def test_a_correlator_is_one_dns_label_with_room_to_spare(self):
        # 63 is the label ceiling. A correlator that did not fit would be an
        # address no canary could be embedded at.
        self.assertLessEqual(callback.CORRELATOR_BYTES * 2, 63)


class AcceptTest(unittest.TestCase):
    """What `accept` refuses before it has anything to record."""

    def test_a_name_no_channel_admits_never_opens_a_connection(self):
        for host in (
            # The parent of the endpoint: a channel admits what is beneath it
            # and nothing above it.
            "example.org",
            # An adjacent name that ends in the endpoint's text but not in its
            # labels.
            f"{ENDPOINT}.evil.test",
            # A target, which is the other direction the confusion runs.
            "app.example.com",
        ):
            with self.subTest(host):
                opened, result = self.refused(host=host)

                opened.assert_not_called()
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_the_endpoint_itself_is_refused_before_the_database(self):
        opened, result = self.refused(host=ENDPOINT)

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_something_a_listener_cannot_say_about_a_peer_is_refused(self):
        opened, result = self.refused(peer="target")

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_an_arrival_that_is_not_bytes_that_exist_is_refused(self):
        for name, data in (
            ("empty", b""),
            ("oversized", b"x" * (callback.MAX_ARRIVAL_BYTES + 1)),
        ):
            with self.subTest(name):
                opened, result = self.refused(source=arrival(data))

                opened.assert_not_called()
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_an_arrival_that_is_not_there_is_refused_before_the_database(self):
        opened, result = self.refused(source=scratch() / "absent.bin")

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        opened, result = self.refused(
            source_text=SCOPED.replace("requests = 100", "requests = -1")
        )

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = callback.accept(
            settings(),
            write(SCOPED),
            f"{CORRELATOR}.{ENDPOINT}",
            arrival(),
            root=scratch(),
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.exit_code)

    def test_nothing_is_stored_before_the_arrival_is_admitted(self):
        root = scratch() / "artifacts"

        callback.accept(
            settings(),
            write(SCOPED),
            f"{CORRELATOR}.{ENDPOINT}",
            arrival(),
            root=root,
        )

        self.assertFalse(root.exists())

    def test_every_refusal_reports_the_keys_an_accepted_arrival_reports(self):
        for name, call in (
            ("refused", lambda: self.refused(host="example.org")[1]),
            (
                "unreachable",
                lambda: callback.accept(
                    settings(),
                    write(SCOPED),
                    f"{CORRELATOR}.{ENDPOINT}",
                    arrival(),
                    root=scratch(),
                ),
            ),
        ):
            with self.subTest(name):
                self.assertEqual({"program_id", "callback"}, set(call().facts))

    def refused(self, *, host=None, source=None, peer="unknown", source_text=SCOPED):
        with mock.patch.object(
            pg, "connect", side_effect=AssertionError("connected")
        ) as opened:
            result = callback.accept(
                settings(),
                write(source_text),
                host if host is not None else f"{CORRELATOR}.{ENDPOINT}",
                source if source is not None else arrival(),
                root=scratch(),
                peer=peer,
            )
        return opened, result


class ProvisionTest(unittest.TestCase):
    """What `provision` refuses before it mints anything."""

    def test_a_channel_this_program_does_not_declare_is_refused(self):
        for name in ("oob-http", "", "OOB-DNS", "oob-dns.example.net"):
            with self.subTest(repr(name)):
                # `VALID` declares `oob-dns` and nothing else, so `oob-http` is
                # a channel that exists in another Program's configuration.
                opened, result = self.refused(channel=name, source_text=VALID)

                opened.assert_not_called()
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_a_lifetime_a_correlator_may_not_have_is_refused(self):
        for lifetime in (0, -1, callback.MAX_LIFETIME + 1):
            with self.subTest(lifetime):
                opened, result = self.refused(lifetime=lifetime)

                opened.assert_not_called()
                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_the_longest_lifetime_a_correlator_may_have_reaches_the_database(self):
        for lifetime in (1, callback.DEFAULT_LIFETIME, callback.MAX_LIFETIME):
            with self.subTest(lifetime):
                result = callback.provision(
                    settings(), write(SCOPED), "oob-dns", "TEC1", lifetime=lifetime
                )

                self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.exit_code)

    def test_a_configuration_that_does_not_validate_never_opens_a_connection(self):
        opened, result = self.refused(
            source_text=SCOPED.replace("requests = 100", "requests = -1")
        )

        opened.assert_not_called()
        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.exit_code)

    def test_every_refusal_reports_the_keys_a_minted_correlator_reports(self):
        for name, call in (
            ("refused", lambda: self.refused(channel="absent")[1]),
            (
                "unreachable",
                lambda: callback.provision(
                    settings(), write(SCOPED), "oob-dns", "TEC1"
                ),
            ),
        ):
            with self.subTest(name):
                self.assertEqual({"program_id", "callback"}, set(call().facts))

    def refused(
        self,
        *,
        channel="oob-dns",
        lifetime=callback.DEFAULT_LIFETIME,
        source_text=SCOPED,
    ):
        with mock.patch.object(
            pg, "connect", side_effect=AssertionError("connected")
        ) as opened:
            result = callback.provision(
                settings(), write(source_text), channel, "TEC1", lifetime=lifetime
            )
        return opened, result


class ChannelProjectionTest(unittest.TestCase):
    """The compiled channel list is what the database is asked to store."""

    def test_a_declared_channel_compiles_to_the_row_it_is_projected_as(self):
        # By name rather than by the order they were written in, because `ord`
        # in `program_callback_channels` comes from this list: two runs of the
        # same configuration have to project the same rows.
        compiled = policy()

        self.assertEqual(
            [
                {"name": "oob-dns", "kind": "dns", "host": ENDPOINT},
                {"name": "oob-http", "kind": "http", "host": "callback.example.org"},
            ],
            [entry.summary() for entry in compiled.channels],
        )

    def test_the_most_specific_declaration_is_the_one_an_arrival_came_in_on(self):
        # Two channels, one beneath the other. Both admit the arrival, so which
        # one is chosen decides the correlator: beneath the child it is the
        # canary, beneath the parent it is the child's own first label.
        nested = policy(
            SCOPED.replace(
                '[[callback]]\nname = "oob-dns"',
                f'[[callback]]\nname = "oob-near"\nkind = "dns"\n'
                f'host = "a.{ENDPOINT}"\n\n[[callback]]\nname = "oob-dns"',
            )
        )
        observed = f"{CORRELATOR}.a.{ENDPOINT}"

        verdict = scope.decide_callback(nested, observed)
        endpoint = nested.channel(verdict.channel)

        self.assertEqual("oob-near", verdict.channel)
        self.assertEqual(f"a.{ENDPOINT}", endpoint.host)
        self.assertEqual(
            CORRELATOR, callback._correlator(Ledger(), observed, endpoint)
        )

    def test_an_arrival_on_the_only_channel_that_admits_it_picks_that_one(self):
        compiled = policy()

        for host, expected in (
            (ENDPOINT, ENDPOINT),
            ("callback.example.org", "callback.example.org"),
        ):
            with self.subTest(host):
                verdict = scope.decide_callback(compiled, f"{CORRELATOR}.{host}")

                self.assertEqual(
                    expected, compiled.channel(verdict.channel).host
                )


if __name__ == "__main__":
    unittest.main()
