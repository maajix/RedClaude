"""Encrypted Identity slot plaintext, while it is inside the proxy process.

The durable representation of this document is an authenticated ciphertext.
This module only knows the short-lived plaintext after the proxy has opened a
slot: origin-bound static headers and a standards-based cookie jar.  It never
acquires credentials and never talks to a target on its own.
"""

from __future__ import annotations

import http.cookiejar
import hmac
import json
import os
import re
import ssl
from dataclasses import dataclass, field
from email.message import Message
from pathlib import Path
from urllib.parse import urlsplit

from redkraken import config, migrate, pg, program, seal, vault
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report
from redkraken.store import digest


SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1024 * 1024
COMMAND = "identity provision"
KEYING = (
    "SELECT identity_entity_id::text, revision, binding_revision, generation,"
    "       salt_hex, root_check_hex, audit_id"
    "  FROM identity_slot_keying($1::uuid, $2, $3::bytea, $4::bytea)"
)
CONFIRM_ROOTCHECK = "SELECT confirm_identity_root_check($1::uuid, $2, $3::uuid, $4)"
PROVISION = "SELECT provision_identity_slot($1::uuid, $2, $3::bigint, $4::jsonb)"
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_FORBIDDEN = frozenset(
    {
        "connection",
        "content-length",
        "cookie",
        "host",
        "proxy-authorization",
        "transfer-encoding",
        "x-redkraken-program",
    }
)


class Invalid(ValueError):
    """Provisioned Identity material is not the closed document this runtime reads."""


class _Request:
    """The small request protocol ``http.cookiejar`` consumes."""

    def __init__(self, url: str):
        parts = urlsplit(url)
        self._url = url
        self._host = parts.hostname or ""
        self.unverifiable = False
        self.origin_req_host = self._host
        self._headers: dict[str, str] = {}

    def get_full_url(self) -> str:
        return self._url

    def get_host(self) -> str:
        return self._host

    @property
    def host(self) -> str:
        return self._host

    @property
    def type(self) -> str:
        return urlsplit(self._url).scheme

    def has_header(self, name: str) -> bool:
        return name in self._headers

    def get_header(self, name: str, default=None):
        return self._headers.get(name, default)

    def add_unredirected_header(self, name: str, value: str) -> None:
        self._headers[name] = value

    def header_items(self) -> list[tuple[str, str]]:
        return list(self._headers.items())


class _Response:
    def __init__(self, values: list[str]):
        self._headers = Message()
        for value in values:
            self._headers["Set-Cookie"] = value

    def info(self) -> Message:
        return self._headers


@dataclass(frozen=True)
class ClientCertificate:
    """One upstream TLS credential, loaded without a plaintext filesystem copy."""

    certificate_pem: str = field(repr=False)
    private_key_pem: str = field(repr=False)
    password: str | None = field(default=None, repr=False)

    def public_sha256(self) -> str:
        """Hash the leaf certificate bytes used for upstream Identity TLS."""
        found = re.search(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            self.certificate_pem,
            re.DOTALL,
        )
        if found is None:
            raise Invalid("the client Identity has no leaf certificate")
        try:
            der = ssl.PEM_cert_to_DER_cert(found.group(0))
        except ValueError as error:
            raise Invalid("the client Identity leaf certificate is not valid PEM") from error
        return digest(der)

    def install(self, context: ssl.SSLContext) -> None:
        """Load this credential through an anonymous in-memory Linux file."""
        if not hasattr(os, "memfd_create"):
            raise Invalid("this platform cannot load a client Identity without a plaintext file")
        material = (self.certificate_pem.rstrip() + "\n" + self.private_key_pem).encode()
        descriptor = os.memfd_create("rk2-client-identity", flags=os.MFD_CLOEXEC)
        try:
            remaining = memoryview(material)
            while remaining:
                written = os.write(descriptor, remaining)
                if written == 0:
                    raise Invalid("the in-memory client Identity stopped accepting bytes")
                remaining = remaining[written:]
            os.lseek(descriptor, 0, os.SEEK_SET)
            try:
                context.load_cert_chain(f"/proc/self/fd/{descriptor}", password=self.password)
            except ssl.SSLError as error:
                raise Invalid(f"the client certificate cannot be loaded: {error}") from error
        finally:
            os.close(descriptor)


@dataclass(frozen=True)
class Origin:
    scheme: str
    host: str
    port: int
    #: The names and their values, and the values are credentials -- an
    #: `Authorization` line, a session cookie, an API key. Out of the `repr`
    #: for the same reason the certificate below it is: this is a frozen
    #: dataclass, so the default `repr` is what a traceback frame, a logged
    #: object and an `assert` message would all render in full.
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    source_url: str
    client_certificate: ClientCertificate | None = field(default=None, repr=False)

    def matches(self, url: str) -> bool:
        parts = urlsplit(url)
        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return False
        return (parts.scheme, (parts.hostname or "").lower(), port) == (
            self.scheme,
            self.host,
            self.port,
        )


class Session:
    """One Identity's headers and cookie jar, decrypted only in proxy memory."""

    def __init__(self, origins: tuple[Origin, ...], jar: http.cookiejar.CookieJar):
        self.origins = origins
        self.jar = jar

    @classmethod
    def from_material(cls, material: dict) -> Session:
        _keys(material, {"schema_version", "origins"}, "Identity material")
        if material.get("schema_version") != SCHEMA_VERSION:
            raise Invalid(f"Identity material schema_version must be {SCHEMA_VERSION}")
        raw_origins = material.get("origins")
        if not isinstance(raw_origins, list) or not raw_origins:
            raise Invalid("Identity material origins must be a non-empty list")

        jar = http.cookiejar.CookieJar()
        origins: list[Origin] = []
        seen: set[tuple[str, str, int]] = set()
        for index, raw in enumerate(raw_origins):
            if not isinstance(raw, dict):
                raise Invalid(f"Identity material origins[{index}] must be an object")
            _keys(
                raw,
                {"url", "headers", "cookies", "client_certificate"},
                f"origins[{index}]",
                optional={"client_certificate"},
            )
            url = raw.get("url")
            if not isinstance(url, str):
                raise Invalid(f"origins[{index}].url must be a string")
            try:
                parts = urlsplit(url)
            except ValueError as error:
                # `urlsplit` raises on a malformed IPv6 literal, and this is
                # material a vault may have written: an uncaught `ValueError`
                # leaves `provision` as a traceback rather than as a refusal,
                # and a traceback out of this function is one raised with the
                # resolved document in its frames.
                raise Invalid(f"origins[{index}].url is not a URL") from error
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise Invalid(f"origins[{index}].url must be an absolute HTTP URL")
            if parts.username is not None or parts.password is not None or parts.fragment:
                raise Invalid(f"origins[{index}].url may not carry userinfo or a fragment")
            try:
                port = parts.port or (443 if parts.scheme == "https" else 80)
            except ValueError as error:
                raise Invalid(f"origins[{index}].url has no usable port") from error
            key = (parts.scheme, parts.hostname.lower(), port)
            if key in seen:
                raise Invalid(f"origins[{index}] repeats an origin")
            seen.add(key)

            headers = _headers(raw.get("headers"), index)
            cookies = raw.get("cookies")
            if not isinstance(cookies, list) or not all(isinstance(value, str) for value in cookies):
                raise Invalid(f"origins[{index}].cookies must be a list of Set-Cookie strings")
            if any("\r" in value or "\n" in value for value in cookies):
                raise Invalid(f"origins[{index}].cookies contains a line break")
            try:
                for value in cookies:
                    value.encode("latin-1")
            except UnicodeEncodeError as error:
                raise Invalid(f"origins[{index}].cookies is not HTTP header text") from error
            if cookies:
                jar.extract_cookies(_Response(cookies), _Request(url))
            client_certificate = _client_certificate(raw.get("client_certificate"), index)
            if client_certificate is not None and parts.scheme != "https":
                raise Invalid(f"origins[{index}].client_certificate requires an HTTPS origin")
            origins.append(Origin(*key, headers, url, client_certificate))
        session = cls(tuple(origins), jar)
        if len(session.encode()) > MAX_STATE_BYTES:
            raise Invalid(f"Identity slot plaintext exceeds {MAX_STATE_BYTES} bytes")
        return session

    @classmethod
    def decode(cls, encoded: bytes) -> Session:
        try:
            material = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Invalid("Identity slot plaintext is not a JSON document") from error
        if not isinstance(material, dict):
            raise Invalid("Identity slot plaintext must be an object")
        # Persisted documents use normalized cookie objects, not provisioning
        # Set-Cookie strings. Convert them through the one constructor so the
        # closed header/origin validation does not have a second spelling.
        cookies = material.pop("cookie_jar", None)
        session = cls.from_material(material)
        if cookies is None:
            return session
        if not isinstance(cookies, list):
            raise Invalid("Identity slot cookie_jar must be a list")
        session.jar = _decode_cookies(cookies)
        return session

    def encode(self) -> bytes:
        document = {
            "schema_version": SCHEMA_VERSION,
            "origins": [
                {
                    "url": origin.source_url,
                    "headers": [
                        {"name": name, "value": value} for name, value in origin.headers
                    ],
                    # Provisioning cookies are consumed into the normalized jar.
                    "cookies": [],
                    **(
                        {
                            "client_certificate": {
                                "certificate_pem": origin.client_certificate.certificate_pem,
                                "private_key_pem": origin.client_certificate.private_key_pem,
                                **(
                                    {"password": origin.client_certificate.password}
                                    if origin.client_certificate.password is not None
                                    else {}
                                ),
                            }
                        }
                        if origin.client_certificate is not None
                        else {}
                    ),
                }
                for origin in self.origins
            ],
            "cookie_jar": [_encode_cookie(cookie) for cookie in self.jar],
        }
        return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def inject(self, url: str, headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return the wire headers after this Identity owns its credential fields."""
        origin = next((item for item in self.origins if item.matches(url)), None)
        static = origin.headers if origin is not None else ()
        owned = {name.lower() for name, _ in static} | {"cookie"}
        answer = [(name, value) for name, value in headers if name.lower() not in owned]
        answer.extend(static)
        request = _Request(url)
        self.jar.add_cookie_header(request)
        cookie = request.get_header("Cookie")
        if cookie:
            answer.append(("Cookie", cookie))
        return answer

    def capture(self, url: str, headers: list[tuple[str, str]]) -> bool:
        """Keep target-issued cookies in this Identity and report whether it changed."""
        values = [value for name, value in headers if name.lower() in ("set-cookie", "set-cookie2")]
        if not values:
            return False
        before = self.encode()
        self.jar.extract_cookies(_Response(values), _Request(url))
        return self.encode() != before

    def client_certificate(self, url: str) -> ClientCertificate | None:
        """Return the upstream TLS credential only for its exact HTTPS origin."""
        origin = next((item for item in self.origins if item.matches(url)), None)
        return origin.client_certificate if origin is not None else None

def seal_session(
    session: Session,
    *,
    root: seal.Root,
    program_id: str,
    identity_id: str,
    generation: int,
    salt: bytes,
    binding_revision: int,
    revision: int,
) -> dict:
    """Describe one authenticated slot revision without exposing its plaintext."""
    plaintext = session.encode()
    if len(plaintext) > MAX_STATE_BYTES:
        raise Invalid(f"Identity slot plaintext exceeds {MAX_STATE_BYTES} bytes")
    key = root.identity_key(
        salt,
        generation=generation,
        program_id=program_id,
        identity_id=identity_id,
    )
    encrypted = seal.seal(
        key,
        plaintext,
        aad=seal.identity_associated_data(
            program_id=program_id,
            identity_id=identity_id,
            generation=generation,
            binding_revision=binding_revision,
            revision=revision,
        ),
    )
    envelope = encrypted.encode()
    return {
        "revision": revision,
        "binding_revision": binding_revision,
        "alg": encrypted.alg,
        "nonce_hex": encrypted.nonce.hex(),
        "kek_gen": generation,
        "envelope_hex": envelope.hex(),
        "ciphertext_sha256": digest(envelope),
        "byte_size": len(plaintext),
        "value_fpr_hex": root.fingerprint(plaintext).hex(),
    }


def open_session(
    *,
    root: seal.Root,
    program_id: str,
    identity_id: str,
    revision: int,
    binding_revision: int,
    generation: int,
    salt: bytes,
    root_check: bytes,
    alg: str,
    nonce: bytes,
    envelope: bytes,
) -> Session:
    """Authenticate and open one slot revision, returning no partial plaintext."""
    expected = root.check(salt, generation=generation)
    if not hmac.compare_digest(expected, root_check):
        raise seal.Unusable("the proxy artifact key does not match this installation")
    encrypted = seal.Sealed.decode(envelope)
    if not encrypted.describes(alg, nonce.hex()):
        raise seal.Tampered("Identity slot row and envelope disagree")
    key = root.identity_key(
        salt,
        generation=generation,
        program_id=program_id,
        identity_id=identity_id,
    )
    plaintext = seal.unseal(
        key,
        encrypted,
        aad=seal.identity_associated_data(
            program_id=program_id,
            identity_id=identity_id,
            generation=generation,
            binding_revision=binding_revision,
            revision=revision,
        ),
    )
    return Session.decode(plaintext)


def provision(
    runtime: pg.Settings | None,
    configuration_path: Path,
    label: str,
    material_path: Path,
    *,
    root_secret: seal.Root | None = None,
    key_path: seal.Location | None = None,
) -> Report:
    """Seal operator-provided material into one configured Identity slot.

    This is a control-side adapter, not a hunter tool.  Its report contains the
    stable label, revision and non-secret counts only; paths, references and
    values are deliberately absent.
    """
    ledger = Ledger()
    facts: dict = {"program_id": None, "program_slug": None, "identity": None}
    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return report(COMMAND, ledger, **facts)
    slug = configuration.document["program"]["name"]
    facts["program_slug"] = slug
    labels = {str(item["name"]) for item in configuration.document["identity"]}
    if label not in labels:
        ledger.fail(
            "identity",
            f"{label!r} is not a configured Identity label",
            code=INVALID_CONFIGURATION,
            source="argument:--identity",
        )
        return report(COMMAND, ledger, **facts)

    try:
        raw = Path(material_path).read_bytes()
        if len(raw) > MAX_STATE_BYTES:
            raise Invalid(f"Identity material exceeds {MAX_STATE_BYTES} bytes")
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise Invalid("Identity material must be an object")
        # Before validation and after parsing, which is the only window where a
        # credential out of the vault is a credential and not yet a document.
        # Everything below this line treats what it holds as material the
        # operator wrote, and every refusal it can raise names a position --
        # `origins[0].headers[1].value` -- rather than a value, so a secret that
        # fails validation is still a secret nobody wrote down.
        document, references = vault.resolve(document)
        session = Session.from_material(document)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, Invalid) as error:
        ledger.fail(
            "identity_material",
            f"the control-side material cannot be used: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return report(COMMAND, ledger, **facts)
    except vault.Refused as refusal:
        ledger.refuse("identity_material", refusal.violation.detail, [refusal.violation])
        return report(COMMAND, ledger, **facts)

    root = root_secret
    if root is None:
        location = seal.key_from_environment(key_path)
        if location is None:
            ledger.fail(
                "identity_key",
                f"no key was provided; pass --key or set {seal.KEY_VARIABLE}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{seal.KEY_VARIABLE}",
            )
            return report(COMMAND, ledger, **facts)
        try:
            root = seal.load_root(location)
        except (OSError, seal.Unusable) as error:
            ledger.fail(
                "identity_key",
                f"the key cannot be used: {error}",
                code=INVALID_CONFIGURATION,
                source="argument:--key",
            )
            return report(COMMAND, ledger, **facts)
        except vault.Refused as refusal:
            # In the vault's own words. A locked vault is not a key to correct,
            # and reporting it as one sends an operator to a reference that is
            # already right.
            ledger.refuse("identity_key", refusal.violation.detail, [refusal.violation])
            return report(COMMAND, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(COMMAND, ledger, **facts)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(COMMAND, ledger, **facts)
        program_id = program.resolve(ledger, connection, slug)
        if program_id is None:
            return report(COMMAND, ledger, **facts)
        facts["program_id"] = program_id
        connection.execute("SELECT set_config('rk2.program_id', $1, false)", (program_id,))
        proposed = seal.new_salt()
        rows = connection.execute(
            KEYING,
            (program_id, label, proposed, root.check(proposed, generation=1)),
        ).rows
        if not rows:
            ledger.fail(
                "identity",
                "the configured Identity did not resolve to a control-side slot",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(COMMAND, ledger, **facts)
        (
            identity_id,
            current,
            binding_revision,
            generation,
            salt_hex,
            root_check_hex,
            audit_id,
        ) = rows[0]
        salt = bytes.fromhex(str(salt_hex))
        expected_check = root.check(salt, generation=int(generation))
        matched = hmac.compare_digest(expected_check, bytes.fromhex(str(root_check_hex)))
        connection.execute(
            CONFIRM_ROOTCHECK,
            (program_id, label, str(audit_id), "ok" if matched else "denied"),
        )
        if not matched:
            ledger.fail(
                "identity_key",
                "the key does not match this installation",
                code=INVALID_CONFIGURATION,
                source="identity_slots",
            )
            return report(COMMAND, ledger, **facts)
        revision = int(current) + 1
        state = seal_session(
            session,
            root=root,
            program_id=program_id,
            identity_id=str(identity_id),
            generation=int(generation),
            salt=salt,
            binding_revision=int(binding_revision),
            revision=revision,
        )
        written = int(
            connection.execute(
                PROVISION,
                (program_id, label, int(current), json.dumps(state, separators=(",", ":"))),
            ).scalar()
        )

    facts["identity"] = {
        "label": label,
        "revision": written,
        "origins": len(session.origins),
        "headers": sum(len(origin.headers) for origin in session.origins),
        "cookies": sum(1 for _ in session.jar),
        # How many values came out of the vault rather than out of the file, so
        # an operator can tell the two apart without either being printed.
        "references": references,
    }
    ledger.hold(
        "identity",
        f"{label} revision {written}: {facts['identity']['origins']} origin(s), "
        f"{facts['identity']['headers']} static header(s), "
        f"{facts['identity']['cookies']} cookie(s), "
        f"{references} vault reference(s)",
    )
    return report(COMMAND, ledger, **facts)


def _keys(
    document: dict,
    expected: set[str],
    source: str,
    *,
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    extra = set(document) - expected
    missing = expected - optional - set(document)
    if extra or missing:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(sorted(missing)))
        if extra:
            detail.append("unknown " + ", ".join(sorted(extra)))
        raise Invalid(f"{source} has " + "; ".join(detail))


def _client_certificate(value: object, origin: int) -> ClientCertificate | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise Invalid(f"origins[{origin}].client_certificate must be an object")
    _keys(
        value,
        {"certificate_pem", "private_key_pem", "password"},
        f"origins[{origin}].client_certificate",
        optional={"password"},
    )
    certificate = value.get("certificate_pem")
    private_key = value.get("private_key_pem")
    password = value.get("password")
    if not isinstance(certificate, str) or "-----BEGIN CERTIFICATE-----" not in certificate:
        raise Invalid(f"origins[{origin}].client_certificate.certificate_pem is not PEM")
    if not isinstance(private_key, str) or not re.search(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----", private_key
    ):
        raise Invalid(f"origins[{origin}].client_certificate.private_key_pem is not PEM")
    if password is not None and not isinstance(password, str):
        raise Invalid(f"origins[{origin}].client_certificate.password must be a string")
    return ClientCertificate(certificate, private_key, password)


def _headers(value: object, origin: int) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise Invalid(f"origins[{origin}].headers must be a list")
    answer: list[tuple[str, str]] = []
    #: Where each name was first given, so the refusal for a repeat can name
    #: the two positions. The name itself is not said: `vault.resolve` replaces
    #: every string in the document, including one written in the `name`
    #: position, so a message quoting it would be this module writing a
    #: credential into a violation the command reports.
    seen: dict[str, int] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise Invalid(f"origins[{origin}].headers[{index}] must be an object")
        _keys(item, {"name", "value"}, f"origins[{origin}].headers[{index}]")
        name, header_value = item.get("name"), item.get("value")
        if not isinstance(name, str) or not _TOKEN.fullmatch(name):
            raise Invalid(f"origins[{origin}].headers[{index}].name is not an HTTP token")
        lowered = name.lower()
        if lowered in _FORBIDDEN or lowered.startswith("x-redkraken-"):
            raise Invalid(f"origins[{origin}].headers[{index}].name is proxy-owned")
        if lowered in seen:
            raise Invalid(
                f"origins[{origin}].headers[{index}].name repeats "
                f"origins[{origin}].headers[{seen[lowered]}].name"
            )
        if not isinstance(header_value, str) or "\r" in header_value or "\n" in header_value:
            raise Invalid(f"origins[{origin}].headers[{index}].value is not one header value")
        try:
            header_value.encode("latin-1")
        except UnicodeEncodeError as error:
            raise Invalid(
                f"origins[{origin}].headers[{index}].value is not HTTP header text"
            ) from error
        seen[lowered] = index
        answer.append((name, header_value))
    return tuple(answer)


def _encode_cookie(cookie: http.cookiejar.Cookie) -> dict:
    return {
        "version": cookie.version,
        "name": cookie.name,
        "value": cookie.value,
        "port": cookie.port,
        "port_specified": cookie.port_specified,
        "domain": cookie.domain,
        "domain_specified": cookie.domain_specified,
        "domain_initial_dot": cookie.domain_initial_dot,
        "path": cookie.path,
        "path_specified": cookie.path_specified,
        "secure": cookie.secure,
        "expires": cookie.expires,
        "discard": cookie.discard,
        "comment": cookie.comment,
        "comment_url": cookie.comment_url,
        "rest": cookie._rest,
        "rfc2109": cookie.rfc2109,
    }


def _decode_cookies(items: list) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    expected = {
        "version", "name", "value", "port", "port_specified", "domain",
        "domain_specified", "domain_initial_dot", "path", "path_specified",
        "secure", "expires", "discard", "comment", "comment_url", "rest", "rfc2109",
    }
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise Invalid(f"cookie_jar[{index}] must be an object")
        _keys(item, expected, f"cookie_jar[{index}]")
        try:
            jar.set_cookie(http.cookiejar.Cookie(**item))
        except (TypeError, ValueError) as error:
            raise Invalid(f"cookie_jar[{index}] is not a cookie") from error
    return jar
