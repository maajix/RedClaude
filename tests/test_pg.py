import base64
import hashlib
import hmac
import socket
import struct
import unittest

from redkraken import pg
from redkraken.pg import ConnectionError_, Settings


class SettingsFromUrlTest(unittest.TestCase):
    def test_a_tcp_connection_string_is_read_whole(self):
        settings = pg.settings_from_url("postgresql://rk2_migrate:secret@db.example:6543/rk2")

        self.assertEqual(
            ("db.example", 6543, "rk2", "rk2_migrate", "secret"),
            (settings.host, settings.port, settings.database, settings.user, settings.password),
        )

    def test_the_port_and_ssl_mode_have_defaults(self):
        settings = pg.settings_from_url("postgresql://rk2@db.example/rk2")

        self.assertEqual((5432, "prefer", None), (settings.port, settings.sslmode, settings.password))

    def test_percent_escapes_are_decoded(self):
        settings = pg.settings_from_url("postgresql://rk2:p%40ss%2Fword@db.example/rk2")

        self.assertEqual("p@ss/word", settings.password)

    def test_a_socket_directory_may_be_given_as_a_parameter(self):
        settings = pg.settings_from_url("postgresql:///rk2?user=rk2&host=/var/run/postgresql")

        self.assertTrue(settings.is_unix_socket)
        self.assertEqual("/var/run/postgresql", settings.host)

    def test_query_parameters_are_read(self):
        settings = pg.settings_from_url(
            "postgresql://rk2@db.example/rk2?sslmode=require&connect_timeout=3&application_name=rk-migrate"
        )

        self.assertEqual(
            ("require", 3.0, "rk-migrate"),
            (settings.sslmode, settings.connect_timeout, settings.application_name),
        )

    def test_an_unusable_connection_string_is_refused_before_anything_opens(self):
        refused = {
            "postgresql://db.example/rk2": "names no user",
            "postgresql://rk2@db.example/": "names no database",
            "mysql://rk2@db.example/rk2": "must be postgresql",
            "postgresql://rk2@db.example/rk2?sslmode=maybe": "unsupported sslmode",
            "postgresql://rk2@db.example/rk2?pool_size=4": "unsupported connection parameter",
            "postgresql://rk2@db.example/rk2?connect_timeout=0": "must be positive",
            "postgresql://rk2@db.example/rk2?connect_timeout=soon": "non-numeric connect_timeout",
        }
        for url, expected in refused.items():
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as refusal:
                    pg.settings_from_url(url)
                self.assertIn(expected, str(refusal.exception))


class SettingsTest(unittest.TestCase):
    def test_the_password_is_never_rendered(self):
        settings = pg.settings_from_url("postgresql://rk2:hunter2@db.example/rk2")

        self.assertNotIn("hunter2", repr(settings))
        self.assertIn("password='set'", repr(settings))
        self.assertNotIn("hunter2", settings.describe())

    def test_a_target_describes_itself_without_a_credential(self):
        settings = pg.settings_from_url("postgresql://rk2:hunter2@db.example:6543/rk2")

        self.assertEqual("rk2@db.example:6543/rk2", settings.describe())

    def test_replacing_a_field_keeps_the_credential(self):
        settings = pg.settings_from_url("postgresql://rk2:hunter2@db.example/rk2")

        replaced = settings.replace(database="postgres")

        self.assertEqual(("postgres", "hunter2"), (replaced.database, replaced.password))


class ScramTest(unittest.TestCase):
    """The RFC 7677 exchange, pinned to the vector the RFC publishes."""

    NONCE = "rOprNGfwEbeRWgbNEkqO"
    SERVER_FIRST = (
        "r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
        "s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096"
    )
    CLIENT_FINAL = (
        "c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
        "p=dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ="
    )
    SERVER_FINAL = "v=6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4="

    def exchange(self) -> pg._Scram:
        return pg._Scram("pencil", username="user", nonce=self.NONCE)

    def test_the_client_names_no_user_because_the_startup_packet_did(self):
        self.assertEqual(
            b"n,,n=,r=" + self.NONCE.encode(),
            pg._Scram("pencil", nonce=self.NONCE).client_first(),
        )

    def test_the_client_first_message_carries_the_nonce(self):
        self.assertEqual(b"n,,n=user,r=" + self.NONCE.encode(), self.exchange().client_first())

    def test_the_proof_matches_the_published_vector(self):
        exchange = self.exchange()
        exchange.client_first()

        self.assertEqual(
            self.CLIENT_FINAL.encode(), exchange.client_final(self.SERVER_FIRST.encode())
        )

    def test_a_server_that_knows_the_password_is_accepted(self):
        exchange = self.exchange()
        exchange.client_first()
        exchange.client_final(self.SERVER_FIRST.encode())

        exchange.verify(self.SERVER_FINAL.encode())

    def test_a_server_that_cannot_prove_the_password_is_refused(self):
        exchange = self.exchange()
        exchange.client_first()
        exchange.client_final(self.SERVER_FIRST.encode())

        with self.assertRaises(ConnectionError_) as refusal:
            exchange.verify(b"v=" + ("A" * 43 + "=").encode())

        self.assertIn("prove it knows the password", str(refusal.exception))

    def test_a_server_that_does_not_extend_the_client_nonce_is_refused(self):
        exchange = self.exchange()
        exchange.client_first()

        with self.assertRaises(ConnectionError_) as refusal:
            exchange.client_final(b"r=someoneelse,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096")

        self.assertIn("does not extend", str(refusal.exception))

    def test_a_server_error_is_reported_as_itself(self):
        exchange = self.exchange()
        exchange.client_first()
        exchange.client_final(self.SERVER_FIRST.encode())

        with self.assertRaises(ConnectionError_) as refusal:
            exchange.verify(b"e=invalid-proof")

        self.assertIn("invalid-proof", str(refusal.exception))

    def test_two_exchanges_do_not_share_a_nonce(self):
        first = pg._Scram("pencil").client_first()
        second = pg._Scram("pencil").client_first()

        self.assertNotEqual(first, second)

    def test_an_ascii_password_is_prepared_unchanged(self):
        self.assertEqual("pencil", pg._saslprep("pencil"))

    def test_saslprep_maps_a_non_ascii_space_to_a_space(self):
        self.assertEqual("a b", pg._saslprep("a b"))

    def test_saslprep_refuses_a_prohibited_character(self):
        with self.assertRaises(ValueError):
            pg._saslprep("pencil")


class PreparedPasswordTest(unittest.TestCase):
    def test_a_password_saslprep_prohibits_refuses_the_connection(self):
        # Reached during authentication, where a bare ValueError is a traceback:
        # every other refusal this module raises is one a caller classifies.
        with self.assertRaises(ConnectionError_) as refusal:
            pg._Scram("pen\x07cil")

        self.assertIn("SASLprep", str(refusal.exception))


class VerifierTest(unittest.TestCase):
    """The stored form of a password, so provisioning never sends the password."""

    def test_the_verifier_is_the_shape_the_server_stores(self):
        verifier = pg.scram_verifier("pencil")
        mechanism, _, rest = verifier.partition("$")
        parameters, _, keys = rest.partition("$")
        iterations, _, salt = parameters.partition(":")
        stored, _, server = keys.partition(":")

        self.assertEqual("SCRAM-SHA-256", mechanism)
        self.assertEqual(str(pg.SCRAM_ITERATIONS), iterations)
        self.assertEqual(16, len(base64.b64decode(salt)))
        self.assertEqual(32, len(base64.b64decode(stored)))
        self.assertEqual(32, len(base64.b64decode(server)))

    def test_the_password_itself_never_appears_in_it(self):
        self.assertNotIn("pencil", pg.scram_verifier("pencil"))

    def test_each_verifier_carries_its_own_salt(self):
        self.assertNotEqual(pg.scram_verifier("pencil"), pg.scram_verifier("pencil"))

    def test_the_keys_are_the_ones_the_published_vector_derives(self):
        # The RFC 7677 vector fixes the salt and the iteration count, so the
        # stored key is the one an exchange against this verifier would expect.
        salt = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
        salted = hashlib.pbkdf2_hmac("sha256", b"pencil", salt, 4096)
        stored = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()

        self.assertEqual(
            "SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ=="
            f"${base64.b64encode(stored).decode()}:"
            f"{base64.b64encode(hmac.digest(salted, b'Server Key', 'sha256')).decode()}",
            _verifier_with_salt("pencil", salt),
        )


def _verifier_with_salt(password: str, salt: bytes) -> str:
    """The verifier this module builds, with the vector's salt in place of a random one."""
    original = pg.secrets.token_bytes
    pg.secrets.token_bytes = lambda _count: salt
    try:
        return pg.scram_verifier(password)
    finally:
        pg.secrets.token_bytes = original


class QuotingTest(unittest.TestCase):
    """The utility statements take no parameters, so their arguments are quoted."""

    def test_a_quote_inside_a_string_constant_is_doubled(self):
        self.assertEqual("'rk2''s password'", pg.quote_literal("rk2's password"))

    def test_a_quote_inside_an_identifier_is_doubled(self):
        self.assertEqual('"rk2""owner"', pg.quote_identifier('rk2"owner'))

    def test_an_identifier_is_never_read_as_syntax(self):
        self.assertEqual('"rk2; DROP DATABASE rk2"', pg.quote_identifier("rk2; DROP DATABASE rk2"))

    def test_a_nul_is_refused_rather_than_truncated(self):
        for value in ("a\x00b",):
            with self.assertRaises(ValueError):
                pg.quote_literal(value)
            with self.assertRaises(ValueError):
                pg.quote_identifier(value)

    def test_an_array_literal_quotes_every_member(self):
        self.assertEqual('{"0001_first","0002_second"}', pg.quote_array(["0001_first", "0002_second"]))

    def test_an_array_member_cannot_close_the_literal(self):
        self.assertEqual('{"a\\"b","c\\\\d"}', pg.quote_array(['a"b', "c\\d"]))


class WireTest(unittest.TestCase):
    """The decoding half of the protocol, against messages built by hand."""

    def test_error_fields_are_read_by_their_letters(self):
        body = b"SERROR\x00C23514\x00Mnew row violates check\x00Dthe detail\x00\x00"

        fields = pg._fields(body)

        self.assertEqual({"S": "ERROR", "C": "23514", "M": "new row violates check", "D": "the detail"}, fields)

    def test_an_error_names_its_sqlstate_and_detail(self):
        error = pg.DatabaseError({"C": "23514", "M": "violates check", "D": "why", "W": "in trigger\nline 2"})

        self.assertEqual("23514", error.sqlstate)
        self.assertIn("violates check", str(error))
        self.assertIn("why", str(error))
        self.assertIn("in trigger", str(error))
        self.assertNotIn("line 2", str(error))

    def test_a_row_is_decoded_by_its_column_types(self):
        description = struct.pack("!h", 3)
        for name, oid in ((b"ok", 16), (b"count", 20), (b"label", 25)):
            description += name + b"\x00" + struct.pack("!ihihih", 0, 0, oid, -1, -1, 0)
        columns, types = pg._row_description(description)

        row = struct.pack("!h", 3)
        for value in (b"t", b"42", b"programs"):
            row += struct.pack("!i", len(value)) + value

        self.assertEqual(("ok", "count", "label"), columns)
        self.assertEqual((True, 42, "programs"), pg._data_row(row, types))

    def test_a_null_stays_absent_rather_than_becoming_a_value(self):
        row = struct.pack("!h", 1) + struct.pack("!i", -1)

        self.assertEqual((None,), pg._data_row(row, (25,)))

    def test_values_are_sent_as_text_the_server_parses(self):
        self.assertEqual([None, b"t", b"f", b"7", b"name"], [pg._encode(v) for v in (None, True, False, 7, "name")])

    def test_a_result_reads_one_value_or_says_why_it_cannot(self):
        result = pg.Result(columns=("n",), rows=((1,),), tag="SELECT 1")

        self.assertEqual(1, result.scalar())
        self.assertEqual(({"n": 1},), result.dicts())
        with self.assertRaises(ValueError):
            pg.Result(columns=("n",), rows=((1,), (2,))).scalar()


def _message(tag: bytes, body: bytes = b"") -> bytes:
    return tag + struct.pack("!i", len(body) + 4) + body


#: An ordinary end of cycle: one command tag, then idle.
_DONE = _message(b"C", b"SELECT 1\x00") + _message(b"Z", b"I")


class MessageLoopTest(unittest.TestCase):
    """What the client does with what the server sends, over a socket pair.

    A pair rather than a server because the cases that matter are the ones a
    healthy server never produces: a message this client does not implement, a
    COPY it cannot speak, and a peer that has gone away mid-statement.
    """

    def connection(self) -> tuple[pg.Connection, socket.socket]:
        ours, theirs = socket.socketpair()
        self.addCleanup(ours.close)
        self.addCleanup(theirs.close)
        connection = pg.Connection(Settings(host="/run/postgresql", database="rk2", user="rk2_migrate"))
        connection._socket = ours
        # A client that waits for a message the server is never going to send
        # hangs the whole suite rather than failing one case. The deadline is
        # the harness's, not the client's: nothing here is slow.
        ours.settimeout(5)
        return connection, theirs

    def test_a_message_this_client_does_not_implement_is_refused_by_name(self):
        # FunctionCallResponse. Dropping it silently leaves the next statement
        # reading this cycle's remainder, which is worse than saying so.
        connection, server = self.connection()
        server.sendall(_message(b"V", b"\x00\x00\x00\x00") + _DONE)

        with self.assertRaises(ConnectionError_) as refusal:
            connection.execute("SELECT 1")

        self.assertIn("V", str(refusal.exception))

    def test_a_copy_the_server_starts_is_refused_rather_than_waited_on(self):
        # The backend blocks for CopyData that this client will never send, so
        # absorbing CopyInResponse would hang the migration holding the lock.
        connection, server = self.connection()
        server.sendall(_message(b"G", b"\x00\x00\x00"))

        with self.assertRaises(ConnectionError_) as refusal:
            connection.execute("COPY t FROM stdin")

        self.assertIn("COPY", str(refusal.exception))

    def test_a_connection_that_lost_the_stream_refuses_the_next_statement(self):
        connection, server = self.connection()
        server.sendall(_message(b"V") + _DONE)
        with self.assertRaises(ConnectionError_):
            connection.execute("SELECT 1")

        with self.assertRaises(ConnectionError_) as refusal:
            connection.execute("SELECT 2")

        self.assertIn("no longer usable", str(refusal.exception))

    def test_an_asynchronous_notice_does_not_end_the_cycle(self):
        connection, server = self.connection()
        server.sendall(_message(b"N", b"SNOTICE\x00Mrelation exists\x00\x00") + _DONE)

        result = connection.execute("SELECT 1")

        self.assertEqual("SELECT 1", result.tag)
        self.assertEqual([{"S": "NOTICE", "M": "relation exists"}], connection.notices)

    def test_a_peer_that_went_away_does_not_turn_closing_into_a_traceback(self):
        # The path where a report has just been built and is about to be lost:
        # `__exit__` closes, and the Terminate cannot be sent.
        connection, server = self.connection()
        server.close()

        connection.close()

        self.assertIsNone(connection._socket)

    def test_the_connect_budget_is_cleared_once_the_session_is_open(self):
        # A migration is unbounded -- an index build is allowed to be slow -- so
        # the deadline for reaching a server must not become one per statement.
        connection, _ = self.connection()
        connection._socket.settimeout(pg.DEFAULT_CONNECT_TIMEOUT)

        connection._clear_connect_timeout()

        self.assertIsNone(connection._socket.gettimeout())


class ServerNameTest(unittest.TestCase):
    def test_a_hostname_is_sent_as_the_server_name(self):
        # libpq has sent SNI since PostgreSQL 14, and an SNI-routed endpoint
        # rejects or misroutes a handshake without it.
        self.assertEqual("db.internal", pg._sni_hostname("db.internal"))

    def test_an_address_carries_no_server_name(self):
        self.assertIsNone(pg._sni_hostname("10.0.0.5"))
        self.assertIsNone(pg._sni_hostname("::1"))


if __name__ == "__main__":
    unittest.main()
