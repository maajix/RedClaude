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
has no third-party dependencies (`doctor.REQUIREMENTS`), the standard library
cannot build an X.509 certificate, and the alternative -- hand-rolling DER --
would be a new place for a signing bug to live. Shelling out to a system binary
is already how `backup` reaches `pg_dump`; the same refusal applies when it is
missing.

What is deliberately not here: the agent's *containment*. Setting `HTTP_PROXY`
asks a client to use the door. It does not stop one that ignores it, and the
prototype's fifth finding is that containment is a routing fact rather than a
policy -- a network namespace with no route but the door's. That is ticket 11's
work, and this module's environment builder is the half of it that is honest
today: both schemes named, nothing left to bypass, one trust root installed.
"""

from __future__ import annotations

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

#: The program that issues the certificates. It ships with every operating
#: system this harness runs on, and is already the documented way to make the
#: root secret (`seal.load_root`).
OPENSSL = "openssl"

#: How long a run's certificates are good for. Short, because they are a run's:
#: a trust root that outlives the run it was minted for is a trust root someone
#: still trusts after the door that owns its key has stopped answering.
DAYS = 7

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
#: The first three replace the store they name; `NODE_EXTRA_CA_CERTS` adds to
#: Node's bundled roots rather than replacing them, so a Node client here trusts
#: this run *and* the public internet. That is not fixed by a fifth variable:
#: what closes it is having no route to the public internet, which is ticket
#: 11's, and the honest statement until then is that this list makes the door
#: trusted everywhere and untrusts the internet only where a variable can.
TRUST_VARIABLES = (
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
)

#: The extensions on a leaf. A server certificate and nothing else: it cannot
#: sign, so a leaf that leaked is one host's problem rather than the run's.
LEAF_EXTENSIONS = (
    "basicConstraints=critical,CA:FALSE",
    "keyUsage=critical,digitalSignature,keyEncipherment",
    "extendedKeyUsage=serverAuth",
)


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
                found = self._context(name)
                self._contexts[name] = found
            return found

    def _context(self, host: str) -> ssl.SSLContext:
        certificate, key = self._leaf(host)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        context.set_alpn_protocols(ALPN)
        return context

    def _leaf(self, host: str) -> tuple[Path, Path]:
        """Issue -- or find -- the certificate that names one host.

        Named by a digest rather than by the host, because the host is untrusted
        input and a file name is a path. The digest is not a secret; it is a
        stable name that cannot contain a separator.
        """
        if not HOST.match(host):
            raise Unusable(f"{host!r} is not a host this door can certify")
        key = self.directory / "leaf-key.pem"
        if not key.exists():
            _run(_generate(key))
            _own(key)
        stamp = hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]
        certificate = self.directory / f"leaf-{stamp}.pem"
        if certificate.exists():
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
    certificate = directory / "ca.pem"
    key = directory / "ca-key.pem"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise Unusable(f"{directory} cannot hold a certificate authority: {error}") from error
    if not directory.is_dir():
        raise Unusable(f"{directory} cannot hold a certificate authority: not a directory")
    made = Authority(directory, certificate, key)
    if certificate.exists() and key.exists():
        return made
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
    exempt, and which certificate to believe. The signing key is not here and
    has no variable: this mapping is handed to a process that is assumed to be
    hostile, and the difference between an agent that can be intercepted and an
    agent that can intercept is exactly one file.
    """
    child = dict(source)
    for name in PROXY_VARIABLES:
        child[name] = proxy_url
    for name in BYPASS_VARIABLES:
        child[name] = ""
    for name in TRUST_VARIABLES:
        child[name] = str(certificate)
    return child


def _san(host: str) -> str:
    """`IP:` for an address and `DNS:` for a name.

    Not interchangeable. A certificate whose SAN says `DNS:127.0.0.1` verifies
    against no client at all, and the failure arrives as a handshake error with
    nothing in it about the name.
    """
    literal = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        return f"IP:{ipaddress.ip_address(literal)}"
    except ValueError:
        return f"DNS:{host}"


def _generate(key: Path) -> list[str]:
    return [
        OPENSSL, "genpkey",
        "-algorithm", "EC",
        "-pkeyopt", f"ec_paramgen_curve:{CURVE}",
        "-out", str(key),
    ]


def _own(path: Path) -> None:
    """Key material, readable by this account and no other."""
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _run(command: list[str]) -> None:
    """One `openssl` invocation, or the reason it could not be one.

    The missing-program case is answered before the call rather than caught
    after it, because `FileNotFoundError` from `subprocess` names the program
    and not what the operator has to install.
    """
    if shutil.which(command[0]) is None:
        raise Missing(
            f"{command[0]} is not on PATH; it issues the certificate that lets this "
            "door see inside a tunnel"
        )
    finished = subprocess.run(command, capture_output=True, text=True, check=False)
    if finished.returncode != 0:
        detail = (finished.stderr or finished.stdout).strip().splitlines()
        raise Unusable(
            f"{command[0]} {command[1]} refused: {detail[-1] if detail else 'no output'}"
        )
