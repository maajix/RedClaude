"""The PostgreSQL connection the runtime owns.

Every durable fact in this system lives in one Postgres database, so the
connection to it is production code rather than a dependency choice. This module
speaks the frontend/backend protocol version 3 directly: the application ships
no third-party driver, and the operator installs nothing beyond the interpreter
to create, migrate or verify a database.

What it supports is what the runtime needs and nothing else — one connection at
a time, text-format parameters and results, explicit transactions, and the two
authentication methods a modern server offers over a network (`SCRAM-SHA-256`
and, for a trusted local socket, none at all). Anything else is refused by name
rather than approximated, so an unsupported server fails on connection instead of
part-way through a migration.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import os
import secrets
import socket
import ssl
import stringprep
import struct
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlsplit


#: Protocol version 3.0, as the two 16-bit halves the startup packet carries.
PROTOCOL_VERSION = 3 << 16

#: The magic request codes that share the startup packet's shape.
SSL_REQUEST = 80877103

DEFAULT_PORT = 5432

#: How long a connection attempt may take. A migration itself is unbounded —
#: an index build is allowed to be slow — but reaching a server is not.
DEFAULT_CONNECT_TIMEOUT = 10.0

#: Result columns are decoded by type, not guessed from their text. Anything
#: absent from this table stays the text the server sent, which is always a
#: faithful representation of the value.
_BOOLEAN = 16
_INTEGERS = (20, 21, 23, 26)
_FLOATS = (700, 701)

_SASL_SCRAM_SHA_256 = "SCRAM-SHA-256"

#: Authentication requests named so a refusal can say which one arrived.
_AUTHENTICATION_METHODS = {
    0: "none",
    2: "kerberos",
    3: "cleartext password",
    5: "md5 password",
    7: "gssapi",
    9: "sspi",
    10: "sasl",
}


class DatabaseError(Exception):
    """An error the server reported, carrying the fields it sent with it."""

    def __init__(self, fields: Mapping[str, str]) -> None:
        self.fields = dict(fields)
        self.sqlstate = self.fields.get("C", "")
        self.primary = self.fields.get("M", "")
        detail = self.fields.get("D")
        where = self.fields.get("W")
        parts = [f"{self.sqlstate}: {self.primary}" if self.sqlstate else self.primary]
        if detail:
            parts.append(detail)
        if where:
            parts.append(where.splitlines()[0])
        super().__init__(" | ".join(part for part in parts if part))


class ConnectionError_(Exception):
    """The server could not be reached, or refused to speak this protocol."""


@dataclass(frozen=True)
class Settings:
    """Where a database is and how to reach it.

    A value rather than an environment lookup, so a command can be run against a
    stated database — including one that does not exist — without the process
    environment deciding for it. The password is held here and never rendered:
    `repr` is the one place a credential leaks into a traceback by accident.
    """

    host: str
    database: str
    user: str
    port: int = DEFAULT_PORT
    password: str | None = field(default=None, repr=False)
    sslmode: str = "prefer"
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    application_name: str = "rk"

    def __repr__(self) -> str:
        return (
            f"Settings(host={self.host!r}, port={self.port!r}, "
            f"database={self.database!r}, user={self.user!r}, "
            f"sslmode={self.sslmode!r}, password={('set' if self.password else 'unset')!r})"
        )

    @property
    def is_unix_socket(self) -> bool:
        return self.host.startswith("/")

    def replace(self, **changes: object) -> Settings:
        """The same target with named fields changed, keeping the credential.

        `dataclasses.replace` rather than a hand-written field list, so a field
        added to this class is carried over instead of silently reset to its
        default the first time anything calls this.
        """
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]

    def describe(self) -> str:
        """The target as an operator names it, with no credential in it."""
        location = self.host if self.is_unix_socket else f"{self.host}:{self.port}"
        return f"{self.user}@{location}/{self.database}"


#: Connection-string keys this client understands. A key outside it is refused
#: rather than ignored, because a silently dropped `sslmode` is a downgrade.
_URL_PARAMETERS = frozenset(
    {"sslmode", "connect_timeout", "application_name", "host", "port", "user", "password", "dbname"}
)

_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})


def settings_from_url(url: str, *, application_name: str = "rk") -> Settings:
    """Read a `postgresql://` connection string into a value.

    The libpq forms an operator will already have — TCP, a unix socket directory
    in `host`, and query parameters — are accepted; a form this client cannot
    honour is refused here, before anything is opened.
    """
    parts = urlsplit(url)
    if parts.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"connection string must be postgresql://, not {parts.scheme or 'a bare path'}://")

    options = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key not in _URL_PARAMETERS:
            raise ValueError(f"unsupported connection parameter: {key}")
        options[key] = value

    database = unquote(parts.path.lstrip("/")) or options.get("dbname", "")
    if not database:
        raise ValueError("connection string names no database")

    host = options.get("host") or (unquote(parts.hostname) if parts.hostname else "") or "/var/run/postgresql"
    user = unquote(parts.username) if parts.username else options.get("user", "")
    if not user:
        raise ValueError("connection string names no user")
    password = unquote(parts.password) if parts.password else options.get("password")

    try:
        port = int(options.get("port") or parts.port or DEFAULT_PORT)
    except ValueError as error:
        raise ValueError(f"connection string has a non-numeric port: {error}") from error

    sslmode = options.get("sslmode", "prefer")
    if sslmode not in _SSL_MODES:
        raise ValueError(f"unsupported sslmode: {sslmode}")

    try:
        timeout = float(options.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT))
    except ValueError as error:
        raise ValueError(f"connection string has a non-numeric connect_timeout: {error}") from error
    if timeout <= 0:
        raise ValueError("connect_timeout must be positive")

    return Settings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        sslmode=sslmode,
        connect_timeout=timeout,
        application_name=options.get("application_name", application_name),
    )


def quote_literal(value: str) -> str:
    """A string constant for the statements that accept no parameter.

    `CREATE DATABASE`, `ALTER ROLE` and the rest of the utility statements take
    no bind parameters, so their arguments travel as text. Doubling the quote is
    the whole rule while `standard_conforming_strings` is on -- the server
    default, asserted by the caller before this is used. A NUL cannot travel in
    a text string at all, so it is refused rather than silently truncated.
    """
    if "\x00" in value:
        raise ValueError("a string constant cannot contain a NUL")
    return "'" + value.replace("'", "''") + "'"


def quote_identifier(name: str) -> str:
    """A quoted identifier, so a role or database name is never read as syntax."""
    if "\x00" in name:
        raise ValueError("an identifier cannot contain a NUL")
    return '"' + name.replace('"', '""') + '"'


def quote_array(values: Sequence[str]) -> str:
    """A `text[]` literal, for the checks that take the expected corpus."""
    quoted = ['"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' for value in values]
    return "{" + ",".join(quoted) + "}"


#: What `password_encryption` has defaulted to since PostgreSQL 14, and the
#: iteration count the server itself uses when it hashes a password.
SCRAM_ITERATIONS = 4096


def scram_verifier(password: str, *, iterations: int = SCRAM_ITERATIONS) -> str:
    """The stored form of a password, in the shape `ALTER ROLE ... PASSWORD` takes.

    `ALTER ROLE r PASSWORD 'secret'` sends the secret itself, which then appears
    in the server log of anyone running with `log_statement = 'ddl'` and in
    `pg_stat_activity` while it runs. The server accepts an already-hashed
    verifier in the same place, so provisioning sends that instead and the
    plaintext never leaves this process.
    """
    prepared = _saslprep(password).encode()
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", prepared, salt, iterations)
    stored_key = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()
    server_key = hmac.digest(salted, b"Server Key", "sha256")
    return (
        f"SCRAM-SHA-256${iterations}:{base64.b64encode(salt).decode()}"
        f"${base64.b64encode(stored_key).decode()}:{base64.b64encode(server_key).decode()}"
    )


@dataclass(frozen=True)
class Result:
    """One statement's answer: its columns, its rows and what it did."""

    columns: tuple[str, ...] = ()
    rows: tuple[tuple[object, ...], ...] = ()
    tag: str = ""

    def scalar(self) -> object:
        """The single value of a single-row, single-column answer."""
        if len(self.rows) != 1 or len(self.rows[0]) != 1:
            raise ValueError(f"expected one value, got {len(self.rows)} row(s)")
        return self.rows[0][0]

    def dicts(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(zip(self.columns, row)) for row in self.rows)


class Connection:
    """One session with one database.

    The class is deliberately small: send a statement, read its answer, and know
    whether a transaction is open. Everything the runtime layers on top of that —
    ordering, bookkeeping, checks — is Python that this class cannot be talked
    into skipping.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.parameters: dict[str, str] = {}
        self.notices: list[dict[str, str]] = []
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
        self._transaction_status = b"I"

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def connect(cls, settings: Settings) -> Connection:
        connection = cls(settings)
        connection._open()
        return connection

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._send(b"X", b"")
        except OSError:
            pass
        finally:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    @property
    def server_version(self) -> str:
        return self.parameters.get("server_version", "")

    @property
    def in_transaction(self) -> bool:
        return self._transaction_status != b"I"

    # -- statements --------------------------------------------------------

    def execute(self, sql: str, parameters: Sequence[object] = ()) -> Result:
        """Run one statement and return its answer.

        With parameters the extended protocol is used, so a value is never text
        this module has to quote. Without them the simple protocol is used, which
        is the only way to send a migration: a file is many statements, and they
        must reach the server as they were written.
        """
        if parameters:
            return self._extended(sql, parameters)
        results = self._simple(sql)
        return results[-1] if results else Result()

    def execute_script(self, sql: str) -> tuple[Result, ...]:
        """Run a multi-statement script, returning every statement's answer."""
        return self._simple(sql)

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """One explicit transaction: committed on success, rolled back on error.

        Explicit rather than implicit because the whole point of the migration
        runner is that a file and the row recording it commit together. A caller
        that never opens one gets a statement per transaction, which is the
        server's rule, not this module's.
        """
        self.execute("BEGIN")
        try:
            yield self
        except BaseException:
            if self._socket is not None:
                try:
                    self.execute("ROLLBACK")
                except (DatabaseError, ConnectionError_, OSError):
                    pass
            raise
        else:
            self.execute("COMMIT")

    # -- protocol ----------------------------------------------------------

    def _open(self) -> None:
        self._socket = _open_socket(self.settings)
        if not self.settings.is_unix_socket and self.settings.sslmode != "disable":
            self._request_tls()
        elif self.settings.sslmode in {"require", "verify-ca", "verify-full"}:
            raise ConnectionError_(
                f"sslmode={self.settings.sslmode} cannot be honoured over a unix socket"
            )

        startup = {
            "user": self.settings.user,
            "database": self.settings.database,
            "application_name": self.settings.application_name,
            "client_encoding": "UTF8",
        }
        body = bytearray(struct.pack("!i", PROTOCOL_VERSION))
        for key, value in startup.items():
            body += key.encode() + b"\x00" + value.encode() + b"\x00"
        body += b"\x00"
        self._send(None, bytes(body))
        self._authenticate()

    def _request_tls(self) -> None:
        assert self._socket is not None
        self._send(None, struct.pack("!i", SSL_REQUEST))
        answer = self._read_exactly(1)
        if answer == b"S":
            context = _tls_context(self.settings)
            self._socket = context.wrap_socket(
                self._socket,
                server_hostname=self.settings.host if context.check_hostname else None,
            )
            return
        if answer != b"N":
            raise ConnectionError_("server answered the TLS request with neither S nor N")
        if self.settings.sslmode in {"require", "verify-ca", "verify-full"}:
            raise ConnectionError_(
                f"server refused TLS and sslmode={self.settings.sslmode} requires it"
            )

    def _authenticate(self) -> None:
        while True:
            tag, body = self._receive()
            if tag == b"R":
                request = struct.unpack("!i", body[:4])[0]
                if request == 0:
                    continue
                if request == 10:
                    self._authenticate_sasl(body[4:])
                    continue
                method = _AUTHENTICATION_METHODS.get(request, f"request {request}")
                raise ConnectionError_(
                    f"server asked for {method} authentication, which this client does not support"
                )
            if tag == b"Z":
                self._transaction_status = bytes(body[:1])
                return
            self._absorb(tag, body)

    def _authenticate_sasl(self, body: bytes) -> None:
        mechanisms = [name.decode() for name in body.split(b"\x00") if name]
        if _SASL_SCRAM_SHA_256 not in mechanisms:
            raise ConnectionError_(
                "server offers no supported SASL mechanism: " + ", ".join(mechanisms)
            )
        if self.settings.password is None:
            raise ConnectionError_(
                f"{self.settings.describe()} requires a password and none was supplied"
            )

        exchange = _Scram(self.settings.password)
        first = exchange.client_first()
        self._send(
            b"p",
            _SASL_SCRAM_SHA_256.encode() + b"\x00" + struct.pack("!i", len(first)) + first,
        )

        tag, message = self._receive()
        if tag != b"R" or struct.unpack("!i", message[:4])[0] != 11:
            self._absorb(tag, message)
            raise ConnectionError_("server broke the SASL exchange after the first message")
        self._send(b"p", exchange.client_final(bytes(message[4:])))

        tag, message = self._receive()
        if tag != b"R" or struct.unpack("!i", message[:4])[0] != 12:
            self._absorb(tag, message)
            raise ConnectionError_("server broke the SASL exchange before completing it")
        exchange.verify(bytes(message[4:]))

    def _simple(self, sql: str) -> tuple[Result, ...]:
        self._send(b"Q", sql.encode() + b"\x00")
        return self._collect()

    def _extended(self, sql: str, parameters: Sequence[object]) -> Result:
        encoded = [_encode(value) for value in parameters]
        parse = b"\x00" + sql.encode() + b"\x00" + struct.pack("!h", 0)
        bind = bytearray(b"\x00\x00")
        bind += struct.pack("!h", 0)
        bind += struct.pack("!h", len(encoded))
        for value in encoded:
            if value is None:
                bind += struct.pack("!i", -1)
            else:
                bind += struct.pack("!i", len(value)) + value
        bind += struct.pack("!h", 0)

        self._send(b"P", parse)
        self._send(b"B", bytes(bind))
        self._send(b"D", b"P\x00")
        self._send(b"E", b"\x00" + struct.pack("!i", 0))
        self._send(b"S", b"")
        results = self._collect()
        return results[-1] if results else Result()

    def _collect(self) -> tuple[Result, ...]:
        """Read one command cycle, to the `ReadyForQuery` that ends it.

        The first error is kept and raised only once the cycle has drained. A
        client that raised immediately would leave the connection mid-answer, and
        the next statement would read this one's rows.
        """
        results: list[Result] = []
        columns: tuple[str, ...] = ()
        rows: list[tuple[object, ...]] = []
        decoders: tuple[int, ...] = ()
        failure: DatabaseError | None = None

        while True:
            tag, body = self._receive()
            if tag == b"T":
                columns, decoders = _row_description(body)
                rows = []
            elif tag == b"D":
                rows.append(_data_row(body, decoders))
            elif tag in {b"C", b"I"}:
                results.append(
                    Result(columns=columns, rows=tuple(rows), tag=_cstring(body) if tag == b"C" else "")
                )
                columns, decoders, rows = (), (), []
            elif tag == b"E":
                error = DatabaseError(_fields(body))
                failure = failure or error
            elif tag == b"Z":
                self._transaction_status = bytes(body[:1])
                if failure is not None:
                    raise failure
                return tuple(results)
            else:
                self._absorb(tag, body)

    def _absorb(self, tag: bytes, body: bytes) -> None:
        """Handle the messages that can arrive at any point in any cycle."""
        if tag == b"S":
            key, _, rest = body.partition(b"\x00")
            self.parameters[key.decode("utf-8", "replace")] = _cstring(rest)
        elif tag == b"N":
            self.notices.append(_fields(body))
        elif tag == b"E":
            raise DatabaseError(_fields(body))
        elif tag in {b"K", b"1", b"2", b"3", b"n", b"t", b"s", b"c"}:
            return

    # -- framing -----------------------------------------------------------

    def _send(self, tag: bytes | None, body: bytes) -> None:
        if self._socket is None:
            raise ConnectionError_("the connection is closed")
        length = struct.pack("!i", len(body) + 4)
        packet = (tag or b"") + length + body
        try:
            self._socket.sendall(packet)
        except OSError as error:
            raise ConnectionError_(f"sending to {self.settings.describe()} failed: {error}") from error

    def _receive(self) -> tuple[bytes, bytes]:
        header = self._read_exactly(5)
        tag = header[:1]
        length = struct.unpack("!i", header[1:])[0]
        if length < 4:
            raise ConnectionError_(f"server sent a message of impossible length {length}")
        return tag, self._read_exactly(length - 4)

    def _read_exactly(self, count: int) -> bytes:
        if self._socket is None:
            raise ConnectionError_("the connection is closed")
        while len(self._buffer) < count:
            try:
                chunk = self._socket.recv(65536)
            except OSError as error:
                raise ConnectionError_(
                    f"reading from {self.settings.describe()} failed: {error}"
                ) from error
            if not chunk:
                raise ConnectionError_(f"{self.settings.describe()} closed the connection")
            self._buffer += chunk
        taken = bytes(self._buffer[:count])
        del self._buffer[:count]
        return taken


def connect(settings: Settings) -> Connection:
    return Connection.connect(settings)


def _open_socket(settings: Settings) -> socket.socket:
    if settings.is_unix_socket:
        path = os.path.join(settings.host, f".s.PGSQL.{settings.port}")
        endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        endpoint.settimeout(settings.connect_timeout)
        try:
            endpoint.connect(path)
        except OSError as error:
            endpoint.close()
            raise ConnectionError_(f"cannot reach {path}: {error}") from error
        return endpoint
    try:
        endpoint = socket.create_connection(
            (settings.host, settings.port), timeout=settings.connect_timeout
        )
    except OSError as error:
        raise ConnectionError_(f"cannot reach {settings.describe()}: {error}") from error
    endpoint.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return endpoint


def _tls_context(settings: Settings) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if settings.sslmode == "verify-full":
        return context
    # `verify-full` is the only mode that checks the name, and it returned
    # above. It is also turned off before the mode below turns verification
    # off entirely, because ssl refuses that combination in the other order.
    context.check_hostname = False
    if settings.sslmode != "verify-ca":
        context.verify_mode = ssl.CERT_NONE
    return context


def _cstring(body: bytes) -> str:
    end = body.find(b"\x00")
    return body[: end if end >= 0 else len(body)].decode("utf-8", "replace")


def _fields(body: bytes) -> dict[str, str]:
    fields = {}
    for part in body.split(b"\x00"):
        if part:
            fields[part[:1].decode()] = part[1:].decode("utf-8", "replace")
    return fields


def _row_description(body: bytes) -> tuple[tuple[str, ...], tuple[int, ...]]:
    count = struct.unpack("!h", body[:2])[0]
    offset = 2
    names: list[str] = []
    types: list[int] = []
    for _ in range(count):
        end = body.index(b"\x00", offset)
        names.append(body[offset:end].decode("utf-8", "replace"))
        offset = end + 1
        types.append(struct.unpack("!i", body[offset + 6 : offset + 10])[0])
        offset += 18
    return tuple(names), tuple(types)


def _data_row(body: bytes, types: tuple[int, ...]) -> tuple[object, ...]:
    count = struct.unpack("!h", body[:2])[0]
    offset = 2
    values: list[object] = []
    for index in range(count):
        length = struct.unpack("!i", body[offset : offset + 4])[0]
        offset += 4
        if length < 0:
            values.append(None)
            continue
        text = body[offset : offset + length].decode("utf-8", "replace")
        offset += length
        values.append(_decode(text, types[index] if index < len(types) else 0))
    return tuple(values)


def _decode(text: str, oid: int) -> object:
    if oid == _BOOLEAN:
        return text == "t"
    if oid in _INTEGERS:
        return int(text)
    if oid in _FLOATS:
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _encode(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return b"t" if value else b"f"
    if isinstance(value, bytes):
        return b"\\x" + value.hex().encode()
    return str(value).encode()


class _Scram:
    """The client half of one `SCRAM-SHA-256` exchange (RFC 5802, RFC 7677).

    Channel binding is not advertised: this client asks for `SCRAM-SHA-256`
    rather than `-PLUS`, so a server configured to require binding refuses the
    mechanism outright instead of the two sides disagreeing about what was bound.
    """

    def __init__(self, password: str, *, username: str = "", nonce: str | None = None) -> None:
        self._password = _saslprep(password)
        # The server already knows who is connecting: the startup packet named
        # the user, and RFC 5802 says this field is then empty. It is a
        # parameter only so the published test vectors, which carry a username,
        # can be run against this implementation unchanged.
        self._username = username
        self._nonce = nonce or base64.b64encode(secrets.token_bytes(18)).decode()
        self._first_bare = ""
        self._server_signature = b""

    def client_first(self) -> bytes:
        self._first_bare = f"n={self._username},r={self._nonce}"
        return f"n,,{self._first_bare}".encode()

    def client_final(self, server_first: bytes) -> bytes:
        message = server_first.decode()
        attributes = _scram_attributes(message)
        nonce = attributes.get("r", "")
        if not nonce.startswith(self._nonce):
            raise ConnectionError_("server nonce does not extend the client nonce")
        try:
            salt = base64.b64decode(attributes["s"])
            iterations = int(attributes["i"])
        except (KeyError, ValueError) as error:
            raise ConnectionError_(f"server sent a malformed SCRAM challenge: {error}") from error

        salted = hashlib.pbkdf2_hmac("sha256", self._password.encode(), salt, iterations)
        client_key = hmac.digest(salted, b"Client Key", "sha256")
        stored_key = hashlib.sha256(client_key).digest()

        without_proof = f"c=biws,r={nonce}"
        auth_message = f"{self._first_bare},{message},{without_proof}".encode()
        signature = hmac.digest(stored_key, auth_message, "sha256")
        proof = bytes(a ^ b for a, b in zip(client_key, signature))

        server_key = hmac.digest(salted, b"Server Key", "sha256")
        self._server_signature = hmac.digest(server_key, auth_message, "sha256")
        return f"{without_proof},p={base64.b64encode(proof).decode()}".encode()

    def verify(self, server_final: bytes) -> None:
        attributes = _scram_attributes(server_final.decode())
        if "e" in attributes:
            raise ConnectionError_(f"server refused the SCRAM exchange: {attributes['e']}")
        try:
            signature = base64.b64decode(attributes["v"])
        except (KeyError, ValueError) as error:
            raise ConnectionError_("server sent no SCRAM verifier") from error
        if not hmac.compare_digest(signature, self._server_signature):
            raise ConnectionError_("server failed to prove it knows the password")


def _scram_attributes(message: str) -> dict[str, str]:
    attributes = {}
    for part in message.split(","):
        key, separator, value = part.partition("=")
        if separator and len(key) == 1:
            attributes[key] = value
    return attributes


def _saslprep(value: str) -> str:
    """RFC 4013 preparation of a password.

    An ASCII password passes through unchanged, which is the ordinary case. The
    rest of the profile is implemented rather than skipped so that a password
    containing a non-breaking space is the same password here as it is in the
    server's stored verifier.
    """
    if value.isascii() and value.isprintable():
        return value
    mapped = "".join(
        " " if stringprep.in_table_c12(character) else character
        for character in value
        if not stringprep.in_table_b1(character)
    )
    prepared = unicodedata.normalize("NFKC", mapped)
    for character in prepared:
        if (
            stringprep.in_table_c12(character)
            or stringprep.in_table_c21_c22(character)
            or stringprep.in_table_c3(character)
            or stringprep.in_table_c4(character)
            or stringprep.in_table_c5(character)
            or stringprep.in_table_c6(character)
            or stringprep.in_table_c7(character)
            or stringprep.in_table_c8(character)
            or stringprep.in_table_c9(character)
        ):
            raise ValueError("password contains a character SASLprep prohibits")
    return prepared
