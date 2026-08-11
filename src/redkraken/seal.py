"""Authenticated encryption for wire artifacts, over bytes and a key and nothing else.

A wire artifact is the exact bytes that crossed the network, which is what makes
it worth keeping and what makes it dangerous to keep: it carries the credential
the harness injected. Ticket 07 asks for it to be retained without the database,
the store, the logs or an agent read becoming a place a credential can be found.

Three properties do that, and all three are decidable here:

* **The key is not in the database.** What is stored is a salt and a check value
  derived from the root secret, never the secret and never a key wrapped under
  it. The secret is a file this process reads and no statement can open, so a
  database dump is a dump of ciphertext.
* **The ciphertext is bound to what it is.** The tag covers the algorithm, the
  nonce, the ciphertext and an associated-data string naming the Program, the
  key generation and the plaintext hash. Moving a sealed artifact to another
  Program's row, or renaming its algorithm, or pointing it at a different
  plaintext hash, are all detected by the same comparison.
* **A failure returns nothing.** The tag is checked before a single byte is
  decrypted, so there is no path on which this module produces a truncated or
  garbled plaintext for a caller to mistake for the real one.

The construction is HKDF-SHA256 for derivation, an HMAC-SHA256 counter mode for
the keystream, and encrypt-then-MAC with HMAC-SHA256 over a length-prefixed
header. It is written out of `hashlib`, `hmac` and `secrets` because this
package has no runtime dependencies and adding one to reach AES-GCM would change
what the harness is. That tradeoff is real and is named in the ticket: the
algorithm travels with every ciphertext as `alg`, so replacing this with a
library AEAD is a new version string beside the old one rather than a rewrite of
anything that reads sealed material.

Nothing here talks to a server, and the secret is kept out of `repr` so it
cannot arrive in a report by way of a traceback.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

#: The algorithm this module writes. Stored beside every ciphertext, because a
#: ciphertext whose construction is implied by the code that happens to be
#: installed cannot be opened once that code has moved on.
ALG = "rk-hkdf-sha256-ctr-hmac-v1"

#: Where the root secret is, for a process that is allowed to know.
KEY_VARIABLE = "RK_ARTIFACT_KEY"

BLOCK = hashlib.sha256().digest_size
KEY_BYTES = 32
NONCE_BYTES = 32
SALT_BYTES = 32
TAG_BYTES = BLOCK
CHECK_BYTES = 16
FINGERPRINT_BYTES = 4

MAGIC = b"RKSEAL\x01"
_STREAM = b"rk2/artifact-stream/v1"
_SUBKEYS = b"rk2/artifact-seal/v1"


class Tampered(Exception):
    """The ciphertext, the key or the context is not the one this was sealed under.

    One exception for all three, deliberately. Which of them is wrong is a fact
    about material the caller was not able to authenticate, and reporting it
    would answer questions -- was the key right, was the Program right -- for
    someone holding the store and guessing.
    """


class Unusable(Exception):
    """Key material this process will not use, established before any ciphertext."""


def hkdf(ikm: bytes, *, salt: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 extract-and-expand over SHA-256.

    Every key in this module is a derivation of the one secret, so `info` is what
    keeps two keys apart: a Program key, an audit fingerprint key and a check
    value come from the same bytes and can never be substituted for one another.
    """
    if length < 0:
        raise ValueError(f"length {length} is negative")
    if length > 255 * BLOCK:
        raise ValueError(f"length {length} is beyond what one expansion produces")
    prk = hmac.new(salt or bytes(BLOCK), ikm, hashlib.sha256).digest()
    output = bytearray()
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return bytes(output[:length])


def new_salt() -> bytes:
    return secrets.token_bytes(SALT_BYTES)


def associated_data(*, program_id: str, sha256: str, generation: int) -> bytes:
    """What this ciphertext is, in a form the tag covers.

    The Program that owns it, the key generation it was sealed under, and the
    hash of the plaintext it is. A sealed artifact copied into another Program's
    row is still authentic bytes; it is this string that makes it the wrong
    answer rather than a working one.
    """
    return (
        f"{_SUBKEYS.decode()}|alg={ALG}|gen={generation}"
        f"|program={program_id}|sha256={sha256}"
    ).encode("utf-8")


def identity_associated_data(
    *,
    program_id: str,
    identity_id: str,
    generation: int,
    binding_revision: int,
    revision: int,
) -> bytes:
    """Bind slot ciphertext to one Identity, declaration and mutable revision.

    Slot plaintext deliberately has no unkeyed digest in canonical state: a
    small cookie or password document must not become offline-guessable through
    its hash.  The authenticated revision prevents an older, otherwise valid
    envelope being moved back onto the current row.
    """
    if revision < 1:
        raise ValueError("an Identity slot revision starts at one")
    if binding_revision < 1:
        raise ValueError("an Identity binding revision starts at one")
    return (
        f"rk2/identity-slot/v1|alg={ALG}|gen={generation}|program={program_id}"
        f"|identity={identity_id}|binding={binding_revision}|revision={revision}"
    ).encode("utf-8")


@dataclass(frozen=True)
class Sealed:
    """One ciphertext and everything needed to authenticate it, minus the key."""

    alg: str
    nonce: bytes
    tag: bytes
    ciphertext: bytes

    def encode(self) -> bytes:
        """The bytes that go in the store.

        Self-describing, and with the ciphertext length written down: a file
        truncated in transit is then a fact the reader establishes rather than a
        shorter body it authenticates against a tag it also read short.
        """
        alg = self.alg.encode("utf-8")
        if len(alg) > 255:
            raise ValueError("algorithm name is too long to record")
        return b"".join(
            (
                MAGIC,
                bytes([len(alg)]),
                alg,
                self.nonce,
                self.tag,
                len(self.ciphertext).to_bytes(8, "big"),
                self.ciphertext,
            )
        )

    @classmethod
    def decode(cls, envelope: bytes) -> Sealed:
        """Read an envelope, or refuse. Never a best effort."""
        head = len(MAGIC) + 1
        if len(envelope) < head or envelope[: len(MAGIC)] != MAGIC:
            raise Tampered("not a sealed artifact envelope")
        width = envelope[len(MAGIC)]
        cut = head + width
        if len(envelope) < cut + NONCE_BYTES + TAG_BYTES + 8:
            raise Tampered("sealed artifact envelope is shorter than its own header")
        try:
            alg = envelope[head:cut].decode("utf-8")
        except UnicodeDecodeError as error:
            raise Tampered("sealed artifact names no readable algorithm") from error
        nonce = envelope[cut : cut + NONCE_BYTES]
        cut += NONCE_BYTES
        tag = envelope[cut : cut + TAG_BYTES]
        cut += TAG_BYTES
        size = int.from_bytes(envelope[cut : cut + 8], "big")
        cut += 8
        ciphertext = envelope[cut:]
        if len(ciphertext) != size:
            raise Tampered(
                f"sealed artifact carries {len(ciphertext)} byte(s) and declares {size}"
            )
        return cls(alg, nonce, tag, ciphertext)

    def describes(self, alg: object, nonce: object) -> bool:
        """Whether a stored description is a description of *this* envelope.

        The database records the algorithm and the nonce, and so does the
        envelope, and two callers have to hold one against the other: the gate,
        which does it without a key, and `rk artifact open`, which does it before
        deriving one. Neither reads the ciphertext to decide, because a row
        describing a ciphertext other than the one on disk is already wrong.
        """
        return self.alg == str(alg) and self.nonce.hex() == str(nonce)


def seal(key: bytes, plaintext: bytes, *, aad: bytes, nonce: bytes | None = None) -> Sealed:
    """Encrypt, then authenticate everything the reader will need to trust.

    A fresh nonce per call, so sealing one plaintext twice produces two
    unrelated ciphertexts. Equal ciphertexts would tell anyone holding the store
    and no key at all that two wire bodies were the same body.
    """
    if len(key) != KEY_BYTES:
        raise Unusable(f"a key is {KEY_BYTES} bytes, not {len(key)}")
    if nonce is None:
        nonce = secrets.token_bytes(NONCE_BYTES)
    if len(nonce) != NONCE_BYTES:
        raise Unusable(f"a nonce is {NONCE_BYTES} bytes, not {len(nonce)}")
    stream, authentication = _subkeys(key, nonce)
    ciphertext = _xor(plaintext, _keystream(stream, len(plaintext)))
    tag = _tag(authentication, alg=ALG, nonce=nonce, ciphertext=ciphertext, aad=aad)
    return Sealed(ALG, nonce, tag, ciphertext)


def unseal(key: bytes, sealed: Sealed, *, aad: bytes) -> bytes:
    """The plaintext, or nothing.

    The tag is verified first and the return is the only thing after it. There
    is no ordering here in which a caller receives bytes that were not
    authenticated, which is the whole of "fails closed without returning partial
    plaintext".
    """
    if sealed.alg != ALG:
        raise Tampered(f"sealed under {sealed.alg!r}, which this runtime does not implement")
    if len(sealed.nonce) != NONCE_BYTES or len(sealed.tag) != TAG_BYTES:
        raise Tampered("sealed artifact header is not the shape this algorithm writes")
    if len(key) != KEY_BYTES:
        raise Unusable(f"a key is {KEY_BYTES} bytes, not {len(key)}")
    stream, authentication = _subkeys(key, sealed.nonce)
    expected = _tag(
        authentication,
        alg=sealed.alg,
        nonce=sealed.nonce,
        ciphertext=sealed.ciphertext,
        aad=aad,
    )
    if not hmac.compare_digest(expected, sealed.tag):
        raise Tampered("sealed artifact does not authenticate under this key and context")
    return _xor(sealed.ciphertext, _keystream(stream, len(sealed.ciphertext)))


@dataclass(frozen=True)
class Root:
    """The installation's root secret, and the keys that come out of it.

    The secret is kept out of `repr` on purpose. This object is held by
    report-building code, and a dataclass that printed its own key would put it
    in the first traceback anything logged.
    """

    path: Path
    secret: bytes = field(repr=False)

    def check(self, salt: bytes, *, generation: int) -> bytes:
        """The value stored beside the salt, which is safe to store and to compare.

        It is what makes "wrong key material" answerable before any ciphertext is
        read: a runtime holding the wrong secret derives a different check and
        stops, rather than failing later in a way that looks like corruption.
        """
        return hmac.new(
            self._kek(salt, generation), b"rk2/rootcheck/v1", hashlib.sha256
        ).digest()[:CHECK_BYTES]

    def program_key(self, salt: bytes, *, generation: int, program_id: str) -> bytes:
        """One Program's key, derived rather than stored.

        0024 kept a wrapped key per scope. Deriving instead means the database
        holds no key material at all, wrapped or otherwise, and a Program added
        later needs no row before its first artifact can be sealed.
        """
        return hkdf(
            self._kek(salt, generation),
            salt=b"",
            info=f"rk2/artifact-dek/v1|program={program_id}".encode("utf-8"),
            length=KEY_BYTES,
        )

    def identity_key(
        self,
        salt: bytes,
        *,
        generation: int,
        program_id: str,
        identity_id: str,
    ) -> bytes:
        """One Identity's key, isolated from every other Identity and Artifact."""
        return hkdf(
            self._kek(salt, generation),
            salt=b"",
            info=(
                f"rk2/identity-dek/v1|program={program_id}|identity={identity_id}"
            ).encode("utf-8"),
            length=KEY_BYTES,
        )

    def fingerprint(self, data: bytes) -> bytes:
        """A keyed four bytes: enough to say two values are one, not enough to guess either.

        An unkeyed digest of a short credential is a credential, because the
        space is small enough to search. This one cannot be searched without the
        root secret, which is what makes it safe in an audit row.
        """
        audit = hkdf(self.secret, salt=b"", info=b"rk2/audit-fp/v1", length=KEY_BYTES)
        return hmac.new(audit, data, hashlib.sha256).digest()[:FINGERPRINT_BYTES]

    def _kek(self, salt: bytes, generation: int) -> bytes:
        return hkdf(
            self.secret,
            salt=salt,
            info=f"rk2/kek/v1|gen={generation}".encode("utf-8"),
            length=KEY_BYTES,
        )


def key_from_environment(given: Path | str | None = None) -> Path | None:
    """The root secret's file, from the argument or from the variable behind it."""
    value = given or os.environ.get(KEY_VARIABLE)
    return Path(value) if value else None


def load_root(path: Path | str) -> Root:
    """Read the root secret, or say why this file is not one.

    Three refusals, all before anything is sealed or opened. A file that is not
    there, a file another account can read, and a file with less material in it
    than a key needs. The mode check is not decoration: key material outside the
    database is only outside the database for accounts that cannot read it.

    One trailing newline is dropped, because `openssl rand -hex 32 > key` -- the
    documented way to make one -- writes it, and treating it as material would
    make the same secret two different keys depending on how it was written down.
    """
    path = Path(path)
    try:
        info = path.stat()
    except FileNotFoundError as error:
        raise Unusable(f"no key material at {path}") from error
    except OSError as error:
        raise Unusable(f"key material at {path} cannot be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unusable(f"key material at {path} is not a file")
    mode = stat.S_IMODE(info.st_mode)
    if mode & 0o077:
        raise Unusable(
            f"key material at {path} is readable by other accounts (mode {mode:04o}); "
            "chmod 600 it"
        )
    try:
        secret = path.read_bytes()
    except OSError as error:
        raise Unusable(f"key material at {path} cannot be read: {error}") from error
    if secret.endswith(b"\r\n"):
        secret = secret[:-2]
    elif secret.endswith(b"\n"):
        secret = secret[:-1]
    if len(secret) < KEY_BYTES:
        raise Unusable(
            f"key material at {path} is {len(secret)} byte(s); {KEY_BYTES} is the minimum"
        )
    return Root(path, secret)


def _subkeys(key: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    """Separate keys for the keystream and for the tag, per nonce.

    One key used for both would let a chosen ciphertext relate the two, and the
    nonce as salt is what keeps the keystream from repeating across artifacts
    sealed under the same Program key.
    """
    material = hkdf(key, salt=nonce, info=_SUBKEYS, length=KEY_BYTES * 2)
    return material[:KEY_BYTES], material[KEY_BYTES:]


def _keystream(key: bytes, length: int) -> bytes:
    """Counter mode over HMAC-SHA256.

    A counter rather than a chain, so the length a caller can ask for is not
    capped at the 255 blocks HKDF-Expand stops at. Wire bodies are bigger than
    that.
    """
    prf = hmac.new(key, digestmod=hashlib.sha256)
    output = bytearray()
    counter = 0
    while len(output) < length:
        block = prf.copy()
        block.update(_STREAM + counter.to_bytes(8, "big"))
        output += block.digest()
        counter += 1
    return bytes(output[:length])


def _tag(key: bytes, *, alg: str, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """One MAC over every field a reader will act on, lengths first.

    Length prefixes because concatenation without them is ambiguous: two
    different field splits that produce the same byte string would produce the
    same tag, and the associated data is caller-supplied text.
    """
    parts = (alg.encode("utf-8"), nonce, aad, ciphertext)
    header = b"".join(len(part).to_bytes(8, "big") for part in parts)
    return hmac.new(key, header + b"".join(parts), hashlib.sha256).digest()


def _xor(data: bytes, pad: bytes) -> bytes:
    if not data:
        return b""
    return (int.from_bytes(data, "big") ^ int.from_bytes(pad, "big")).to_bytes(len(data), "big")
