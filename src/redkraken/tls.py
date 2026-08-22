"""The run's own certificate authority, and the trust the agent is given.

A tunnel the door cannot see inside is egress with no Receipt. So HTTPS through
this proxy is intercepted rather than relayed, and interception needs a
certificate the agent's client will accept for a host this installation does not
own. That is the same act an attacker performs. What makes it legitimate is that
the trust is narrow, and every decision here exists to keep it narrow:

  * one authority per run, in a directory the door owns, so a certificate minted
    here is worthless to anything that was not handed this run's root;
  * the signing key never leaves that directory -- the child is told where the
    *certificate* is, never the key, because a child that can sign is a child
    that can be the door;
  * the leaf names exactly one host, so an intercepted connection to one target
    cannot be replayed at another.

The certificate is issued by `openssl`, not by a Python library. The application
declares no third-party dependencies (`doctor.REQUIREMENTS`), the standard
library cannot build an X.509 certificate, and the alternative -- hand-rolling
DER -- would be a new place for a signing bug to live. Shelling out to a system binary
is already how `backup` reaches `pg_dump`; the same refusal applies when it is
missing.

What is deliberately not here: the agent's *containment*. Setting `HTTP_PROXY`
asks a client to use the door. It does not stop one that ignores it, and the
prototype's fifth finding is that containment is a routing fact rather than a
policy -- a network namespace with no route but the door's. That is ticket 11's
work, and this module's environment builder is the half of it that is honest
today: both schemes named, nothing left to bypass, one trust root installed and
no second store left to consult.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import shutil
import ssl
import stat
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import scope

#: The program that issues the certificates. It ships with every operating
#: system this harness runs on, and is already the documented way to make the
#: root secret (`seal.load_root`).
OPENSSL = "openssl"

#: How long a run's certificates are good for. Short, because they are a run's:
#: a trust root that outlives the run it was minted for is a trust root someone
#: still trusts after the door that owns its key has stopped answering.
DAYS = 7

#: How much life a certificate has to have left for this door to keep using it.
#: A door that reuses a certificate expiring in a minute is a door whose next
#: exchange fails for a reason no Receipt explains, and a long campaign restarts
#: often enough to hit it: `DAYS` is seven and story 224's campaign is longer.
MARGIN = 3600

#: The curve. P-256 rather than Ed25519 because it is the one every TLS client
#: in an agent's toolbox can verify, including the ones built against older
#: libraries, and interception that fails on the client's side is an outage with
#: no Receipt to explain it.
CURVE = "prime256v1"

#: The subject on every certificate this door issues. Fixed, because the name
#: that decides whether a client accepts the certificate is the SAN, and a
#: common name is capped at 64 characters where a host is capped at 253.
SUBJECT = "/CN=redKraken egress"

#: What the door will answer over an intercepted connection. Offered explicitly
#: so a client that would have negotiated HTTP/2 with the real target speaks
#: HTTP/1.1 to the door instead: the alternative is a handshake that succeeds and
#: a tunnel that then carries frames nothing here can read.
ALPN = ["http/1.1"]

#: A host that may appear in a certificate. Narrow on purpose. The value comes
#: off the wire in a CONNECT line, and it is about to be written into an OpenSSL
#: extension file: a host containing a newline would be a request to add
#: extensions, not a name to certify.
HOST = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,253}$")

#: Where a child is told to send its traffic. Both schemes, because the
#: prototype configured only `http` and nothing noticed until something asked
#: for `https`; both spellings, because `curl` reads the lower case and much
#: else reads the upper.
PROXY_VARIABLES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy")

#: And what a child is told not to send there: nothing.
BYPASS_VARIABLES = ("NO_PROXY", "no_proxy")

#: Where the clients an agent actually runs look for a trust root. Four names
#: for one file: OpenSSL's, Python's `requests`, `curl`'s own, and Node's.
#:
#: The first three replace the file they name; `NODE_EXTRA_CA_CERTS` adds to
#: Node's bundled roots rather than replacing them, so a Node client here trusts
#: this run *and* the public internet. That is not fixed by a further variable:
#: what closes it is having no route to the public internet, which is ticket
#: 11's, and the honest statement until then is that this list makes the door
#: trusted everywhere and untrusts the internet only where a variable can.
TRUST_VARIABLES = (
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)

#: And the half of OpenSSL's trust that is not a file. `SSL_CERT_FILE` names one
#: certificate; the hashed directory beside it is a second lookup and an
#: independent one, so a root sitting in the system's directory is still trusted
#: by a child that was handed only this run's file. Held against a handshake
#: rather than argued: in `tests/test_tls.py` a certificate that chains only
#: through the directory verifies while the directory is named, and is refused
#: once this list has emptied it.
#:
#: Emptied rather than pointed at this run's own directory, because an empty
#: value means "look in no directory" rather than "fall back to the compiled-in
#: default" -- which the same handshake shows, being the refusal it ends on.
STORE_VARIABLES = ("SSL_CERT_DIR",)

#: How many distinct hosts one run will certify. A CONNECT line is answered
#: before any capability has been offered -- it has to be, because the
#: capability arrives inside the tunnel -- so the host that reaches `context` is
#: unauthenticated input, and each host that has not been seen before forks
#: `openssl` twice and leaves a certificate in the door's directory. The ceiling
#: is far above the number of hosts a run's scope can hold and far below what a
#: client looping on fresh names would cost.
HOSTS = 256

#: The extensions on a leaf. A server certificate and nothing else: it cannot
#: sign, so a leaf that leaked is one host's problem rather than the run's.
LEAF_EXTENSIONS = (
    "basicConstraints=critical,CA:FALSE",
    "keyUsage=critical,digitalSignature,keyEncipherment",
    "extendedKeyUsage=serverAuth",
)


#: What the two halves of an authority are called inside its directory. Named
#: because the certificate is handed out and the key never is, so anything that
#: has to point at one of them from outside -- `RK_PROXY_CA_FILE`, a door started
#: in a container whose authority directory is a bind mount -- points at a name
#: this module decides rather than at a spelling it guessed.
CERTIFICATE_NAME = "ca.pem"
KEY_NAME = "ca-key.pem"

#: What a run writes where `interception_cas.secret_ref` would name a secret
#: store. A third form beside ticket 15's `op://` and `kek:`, admitted by
#: `20261007T000000Z`, and the only honest one for the authority this module
#: makes: the key is a file in a directory the door owns, it is handed to
#: nobody, and no reference to it exists anywhere -- so a `kek:` here would be a
#: claim that the key is recoverable from the secret store, which is the exact
#: lie that shape rule was written to stop.
HELD = "door:no-reference"

#: How a run records the authority its flows are intercepted under. Written here
#: rather than where it is executed, for the reason `proxy.BIND` is: the module
#: that knows what an authority is owns the sentence, and the runtime's pass
#: owns when it is said.
REGISTER = (
    "SELECT register_interception_ca($1::uuid, $2, $3, $4::timestamptz, $5::timestamptz)"
)

#: How the subject is printed for that row. OpenSSL's long attribute names with
#: `, ` between them, which is the spelling `proxy._name` produces from the same
#: certificate on the other side of a handshake -- so `interception_cas.subject`
#: and the `receipts.agent_cert_issuer` of a leaf this root signed are one
#: string rather than two renderings of one name.
NAME_FORMAT = "sep_comma_plus_space,lname,utf8"

#: And how its two dates are. `iso_8601` because the values are going into
#: `timestamptz` columns, and openssl's default -- `Aug 22 09:18:27 2026 GMT` --
#: is a month name a server parses by its own `DateStyle` rather than by the
#: standard.
DATE_FORMAT = "iso_8601"

#: The block `openssl x509 -pubkey` prints the subject public key info in. The
#: body between the two lines is the DER, base64'd, so decoding it here is one
#: fork rather than two and needs nothing but the certificate.
PUBLIC_KEY = ("-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----")


class Unusable(Exception):
    """This directory cannot hold an authority, or this host cannot be certified."""


class Missing(Unusable):
    """The program that issues certificates is not installed.

    A subclass rather than a flag, because it is the one refusal here an
    operator fixes with a package manager rather than with an argument, and the
    two exit differently: `missing_dependency` and not `invalid_configuration`.
    """


@dataclass(frozen=True)
class Authority:
    """One run's signing material, and the certificates issued from it.

    The contexts are cached because a certificate is issued by forking a program
    twice, and a proxy that did that per connection would answer a burst of
    requests to one host at the speed of a burst of key generations. The lock is
    not decoration either: the door is threaded, and two threads issuing at once
    would race on the serial file `openssl` keeps beside the key.
    """

    directory: Path
    certificate: Path
    key: Path
    _contexts: dict[str, ssl.SSLContext] = field(
        default_factory=dict, repr=False, compare=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def context(self, host: str) -> ssl.SSLContext:
        """The server side of an intercepted connection to this host."""
        name = host.strip().lower()
        with self._lock:
            found = self._contexts.get(name)
            if found is None:
                if len(self._contexts) >= HOSTS:
                    raise Unusable(
                        f"this run has already certified {HOSTS} hosts and "
                        f"{name!r} would be another"
                    )
                found = self._context(name)
                self._contexts[name] = found
            return found

    def _context(self, host: str) -> ssl.SSLContext:
        certificate, key = self._leaf(host)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        context.set_alpn_protocols(ALPN)
        return context

    def pin(self) -> str:
        """This run's leaf public key, as a client pins one.

        Base64 of the SHA-256 of the subject public key info, which is the shape
        `--ignore-certificate-errors-spki-list` takes and the shape every other
        pinning client takes. One value covers every host, because every leaf
        this authority issues is signed over the same key -- which is what makes
        a pin usable at all for a proxy that certifies hosts it has not met yet.

        The pin is for a client that cannot be given a certificate store. It is
        narrower than the alternative it replaces, not wider: a browser told to
        ignore certificate errors trusts anything, and a browser told this
        trusts one key that exists for the length of one run and is held in a
        directory the door owns.
        """
        spki = _run(
            [OPENSSL, "pkey", "-in", str(self._signing_key()), "-pubout", "-outform", "DER"]
        )
        return base64.b64encode(hashlib.sha256(spki).digest()).decode("ascii")

    def _signing_key(self) -> Path:
        """The one key every leaf is issued over, made if it is not there.

        One key rather than one per host: issuing is two forks and a key
        generation, and the host-by-host part is the certificate, not the key.
        It is also what makes `pin` a single value.
        """
        key = self.directory / "leaf-key.pem"
        if not key.exists():
            _run(
                [
                    OPENSSL, "genpkey",
                    "-algorithm", "EC",
                    "-pkeyopt", f"ec_paramgen_curve:{CURVE}",
                    "-out", str(key),
                ]
            )
            _own(key)
        return key

    def _leaf(self, host: str) -> tuple[Path, Path]:
        """Issue -- or find -- the certificate that names one host.

        Named by a digest rather than by the host, because the host is untrusted
        input and a file name is a path. The digest is not a secret; it is a
        stable name that cannot contain a separator.
        """
        if not HOST.match(host):
            raise Unusable(f"{host!r} is not a host this door can certify")
        key = self._signing_key()
        stamp = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
        certificate = self.directory / f"leaf-{stamp}.pem"
        if certificate.exists() and not spent(certificate):
            return certificate, key
        request = self.directory / f"leaf-{stamp}.csr"
        extensions = self.directory / f"leaf-{stamp}.ext"
        extensions.write_text(
            "\n".join([*LEAF_EXTENSIONS, f"subjectAltName={_san(host)}"]) + "\n",
            encoding="utf-8",
        )
        _run(
            [
                OPENSSL, "req", "-new",
                "-key", str(key),
                "-subj", SUBJECT,
                "-out", str(request),
            ]
        )
        _run(
            [
                OPENSSL, "x509", "-req", "-sha256",
                "-in", str(request),
                "-CA", str(self.certificate),
                "-CAkey", str(self.key),
                "-CAcreateserial",
                "-days", str(DAYS),
                "-extfile", str(extensions),
                "-out", str(certificate),
            ]
        )
        request.unlink(missing_ok=True)
        extensions.unlink(missing_ok=True)
        return certificate, key


def authority(directory: Path | str) -> Authority:
    """The run's authority, made if it is not there and reused if it is.

    Reused rather than replaced, and that is the whole reason this is a function
    over a directory instead of a constructor. A door that minted a new root on
    restart would invalidate the trust it had already handed the child, and the
    child would report it as a network fault an hour later.
    """
    directory = Path(directory)
    certificate = directory / CERTIFICATE_NAME
    key = directory / KEY_NAME
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise Unusable(f"{directory} cannot hold a certificate authority: {error}") from error
    if not directory.is_dir():
        raise Unusable(f"{directory} cannot hold a certificate authority: not a directory")
    made = Authority(directory, certificate, key)
    if certificate.exists() and key.exists() and not spent(certificate):
        return made
    # A root at the end of its life takes its leaves with it: every one of them
    # was signed by this key and states a validity this authority is about to
    # be outside of, so a leaf left here would be reused under a root that no
    # longer signs anything. The signing key stays, which keeps the SPKI pin the
    # child was told about the same across the reissue.
    # Named `leaf` rather than `spent`: `spent` is the module function this
    # branch was reached by, and binding it here would make the test above it an
    # unbound local read in the same scope -- an authority that exists would
    # raise rather than be reused, which is the one case this function is for.
    for leaf in sorted(directory.glob("leaf-*.pem")):
        leaf.unlink(missing_ok=True)
    _run(
        [
            OPENSSL, "req", "-x509", "-noenc", "-sha256",
            "-newkey", "ec",
            "-pkeyopt", f"ec_paramgen_curve:{CURVE}",
            "-keyout", str(key),
            "-out", str(certificate),
            "-days", str(DAYS),
            "-subj", "/CN=redKraken run authority",
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        ]
    )
    _own(key)
    return made


@dataclass(frozen=True, slots=True)
class Registration:
    """One authority as `interception_cas` records it, in the row's own order.

    Four facts and no fifth, because four is what the public half answers. The
    label is the database's to mint, the Program is the caller's, and the
    `secret_ref` is `HELD` for every authority this module makes -- so nothing
    here is a thing the writer had to be told, which is what keeps the write off
    the side that holds the key.
    """

    subject: str
    spki_sha256: str
    not_before: str
    not_after: str

    def arguments(self, program_id: str) -> tuple[str, ...]:
        """`REGISTER`'s parameters, for the one Program being intercepted."""
        return (program_id, self.subject, self.spki_sha256, self.not_before, self.not_after)


def registration(certificate: Path | str) -> Registration:
    """What the row that attributes a forged leaf says, read off the certificate.

    The certificate and never the key, which is the whole reason this is safe on
    a run-start path: the side that registers the authority is not the side that
    can forge with it, and this function would work just as well against the
    file a child was handed.

    One `openssl` invocation for all four, because the four are one reading of
    one file and two forks would be two chances for them to disagree about which
    certificate is in the directory.

    Not `pin`, which is a different key. `pin` hashes `leaf-key.pem`, the one key
    every leaf this authority issues is signed *over*; `spki_sha256` is the
    root's own, the key every leaf is signed *by*. They live in the same
    directory and neither is the other.
    """
    printed = _run(
        [
            OPENSSL, "x509", "-noout",
            "-in", str(certificate),
            "-subject", "-startdate", "-enddate", "-pubkey",
            "-nameopt", NAME_FORMAT,
            "-dateopt", DATE_FORMAT,
        ]
    ).decode("utf-8", "replace")
    # Split at the key block before anything is read as `name=value`: the body
    # of a PEM block is base64, and base64 ends in `=`.
    head, marker, key = printed.partition(PUBLIC_KEY[0])
    said = dict(
        line.split("=", 1) for line in head.splitlines() if "=" in line
    )
    subject = said.get("subject", "").strip()
    not_before = said.get("notBefore", "").strip()
    not_after = said.get("notAfter", "").strip()
    if not marker or not (subject and not_before and not_after):
        raise Unusable(
            f"{certificate} is not a certificate an authority can be registered from"
        )
    return Registration(
        subject=subject,
        spki_sha256=hashlib.sha256(
            base64.b64decode("".join(key.split(PUBLIC_KEY[1])[0].split()))
        ).hexdigest(),
        not_before=not_before,
        not_after=not_after,
    )


def trust(certificate: Path | str) -> ssl.SSLContext:
    """A client that trusts this run's root and nothing else.

    Nothing else on purpose. The runtime half of the door talks to itself
    through the tunnel it just opened, and a context that also trusted the
    system's roots would accept a certificate from anything that had one --
    which is the failure this whole module exists to make visible.
    """
    return ssl.create_default_context(cafile=str(certificate))


def agent_environment(
    source: Mapping[str, str], *, proxy_url: str, certificate: Path | str
) -> dict[str, str]:
    """What a child is told about the door, over what it was already given.

    Three facts and no others. Where to send both schemes, that nothing is
    exempt, and which certificate to believe -- that last one twice, because
    trust is two lookups and a run root installed as the file leaves the
    directory answering for everything it held before. The signing key is not
    here and has no variable: this mapping is handed to a process that is
    assumed to be hostile, and the difference between an agent that can be
    intercepted and an agent that can intercept is exactly one file.
    """
    child = dict(source)
    for name in PROXY_VARIABLES:
        child[name] = proxy_url
    for name in BYPASS_VARIABLES:
        child[name] = ""
    for name in TRUST_VARIABLES:
        child[name] = str(certificate)
    for name in STORE_VARIABLES:
        child[name] = ""
    return child


def _san(host: str) -> str:
    """`IP:` for an address and `DNS:` for a name.

    Not interchangeable. A certificate whose SAN says `DNS:127.0.0.1` verifies
    against no client at all, and the failure arrives as a handshake error with
    nothing in it about the name.
    """
    literal = scope.unbracket(host)
    try:
        return f"IP:{ipaddress.ip_address(literal)}"
    except ValueError:
        return f"DNS:{host}"


def _own(path: Path) -> None:
    """Key material, readable by this account and no other."""
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def spent(certificate: Path) -> bool:
    """Whether this certificate is past `MARGIN` from the end of its life.

    Asked of a file rather than remembered, because the reuse this answers is
    reuse across processes: the door that issued it is not the door reading it a
    week later. `-checkend` is openssl's own answer and its exit code is the
    whole result -- nonzero for "expires within that many seconds", which is
    also what an unreadable or truncated certificate gets, and both are reasons
    to issue a new one rather than to hand this one to a client.
    """
    if shutil.which(OPENSSL) is None:
        raise Missing(
            f"{OPENSSL} is not on PATH; it issues the certificate that lets this "
            "door see inside a tunnel"
        )
    finished = subprocess.run(
        [OPENSSL, "x509", "-checkend", str(MARGIN), "-noout", "-in", str(certificate)],
        capture_output=True,
        check=False,
    )
    return finished.returncode != 0


def _run(command: list[str]) -> bytes:
    """One `openssl` invocation, or the reason it could not be one.

    The missing-program case is answered before the call rather than caught
    after it, because `FileNotFoundError` from `subprocess` names the program
    and not what the operator has to install.

    Bytes come back because one caller asks for a key in DER, and the callers
    whose output is a file it wrote ignore them. Read as bytes throughout rather
    than by a flag the caller passes: what `openssl` prints is binary or text
    depending on the subcommand, and the one place that matters -- the refusal
    below -- has to survive either.
    """
    if shutil.which(command[0]) is None:
        raise Missing(
            f"{command[0]} is not on PATH; it issues the certificate that lets this "
            "door see inside a tunnel"
        )
    finished = subprocess.run(command, capture_output=True, check=False)
    if finished.returncode != 0:
        said = (finished.stderr or finished.stdout).decode("utf-8", "replace")
        detail = said.strip().splitlines()
        raise Unusable(
            f"{command[0]} {command[1]} refused: {detail[-1] if detail else 'no output'}"
        )
    return finished.stdout
