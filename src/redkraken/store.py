"""The half of an Artifact the database cannot see: the bytes, on a filesystem.

`artifacts` records a SHA-256 and a length. Nothing in SQL can open the file
that hash names, so a row of that table is an integrity claim that no registered
check can answer on its own. This module is what answers it, and it is separate
from `artifact.py` for one reason: the integrity gate has to be able to ask, and
`rk artifact` is a command that runs *through* the gate.

Nothing here reaches a database or a connection. Every function is over bytes, a
path and a hash, which is also what makes them testable without a server.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


#: Where the artifacts live. An environment variable of its own, like the four
#: connection strings: the store is not a connection, and an operator who has
#: moved one has not moved the other.
ROOT_VARIABLE = "RK_ARTIFACT_ROOT"

#: How much of an artifact one read carries by default. Smaller than the state
#: index's ceiling because this is one payload rather than a summary of many,
#: and a caller who wants more says so and is told what it cost.
DEFAULT_BYTES = 4096


class Missing(Exception):
    """The row says these bytes exist and the store does not have them."""


class Corrupt(Exception):
    """The bytes are there and are not the bytes the identifier names."""


@dataclass(frozen=True)
class Window:
    """A bounded range, and what asking for it left out.

    The three numbers add up to the artifact by construction rather than by
    agreement: `omitted_before` and `omitted_after` are the offset and the
    remainder, so a caller cannot be told a range and a total that disagree.
    """

    size: int
    offset: int
    length: int

    @property
    def omitted_before(self) -> int:
        return self.offset

    @property
    def omitted_after(self) -> int:
        return self.size - self.offset - self.length

    @property
    def complete(self) -> bool:
        return self.length == self.size

    def summary(self) -> dict:
        return {
            "size": self.size,
            "offset": self.offset,
            "returned": self.length,
            "omitted_before": self.omitted_before,
            "omitted_after": self.omitted_after,
            "complete": self.complete,
        }


def digest(data: bytes) -> str:
    """The identifier: SHA-256 over the exact plaintext, and over nothing else."""
    return hashlib.sha256(data).hexdigest()


def window(size: int, *, offset: int = 0, limit: int | None = DEFAULT_BYTES) -> Window:
    """Which bytes a read carries, given how big the artifact is.

    An offset past the end is an empty answer with the whole artifact omitted
    before it, which is true and is what a caller paging through one sees when it
    reaches the end. A negative bound is refused rather than clamped: it is the
    caller's arithmetic that is wrong, and clamping would answer a question
    nobody asked.
    """
    if offset < 0:
        raise ValueError(f"offset {offset} is negative")
    if limit is not None and limit < 0:
        raise ValueError(f"limit {limit} is negative")
    start = min(offset, size)
    remainder = size - start
    length = remainder if limit is None else min(limit, remainder)
    return Window(size=size, offset=start, length=length)


def path_for(root: Path, sha256: str) -> Path:
    """Where one artifact is filed: two characters of fan-out, then the hash."""
    return Path(root) / sha256[:2] / sha256


def carried(data: bytes) -> dict:
    """Bytes on their way out of the process, in a form that is not a guess.

    Base64, and a field saying so. An artifact is whatever the wire or a tool
    produced; decoding it as text here would put this module in the business of
    guessing charsets and would make a report depend on the guess.
    """
    return {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}


def root_from_environment(given: Path | str | None = None) -> Path | None:
    """The store's root, from the argument or from the variable behind it."""
    value = given or os.environ.get(ROOT_VARIABLE)
    return Path(value) if value else None


@dataclass(frozen=True)
class Store:
    """The artifacts themselves, addressed by the hash of what is in them."""

    root: Path

    def put(self, data: bytes) -> tuple[str, bool]:
        """File these bytes under their hash, and say whether they were new.

        Written under a temporary name in the same directory and renamed, so a
        crash part-way leaves no file under a hash whose bytes are incomplete --
        the one corruption that would otherwise survive every check that reads
        by name.

        A hit is verified rather than adopted. Existence is not content: a file
        damaged after it was filed -- by the disk, by a restore, by anything
        that did not come through here -- would otherwise be taken as these
        bytes because its name matches, and the caller would commit a reference
        over material nobody has read back. That is the one corruption this
        module says it stops, and the name it is filed under is not evidence of
        it. So the bytes are read and hashed, and a disagreement is `Corrupt`
        rather than a second write: rewriting would erase the only sign that
        something else on this machine is damaging files, and every other row
        already pointing at that hash would silently start meaning something new.
        """
        sha256 = digest(data)
        path = path_for(self.root, sha256)
        if path.exists():
            # The verification, and it is a statement rather than an assignment
            # because what it returns is bytes this caller already holds:
            # `load` reads the filed copy back and raises `Corrupt` when it no
            # longer hashes to the name it is filed under.
            self.load(sha256)
            return sha256, False
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_name(f".{sha256}.{os.getpid()}")
        pending.write_bytes(data)
        pending.replace(path)
        return sha256, True

    def holds(self, sha256: str) -> bool:
        """Whether these bytes are already filed, without reading them back.

        The store holds Agent-visible artifacts as themselves and credential-
        bearing ones only as sealed envelopes filed under the envelope's hash,
        so a hit on a plaintext hash is the fact that those bytes are on this
        filesystem -- and only that. It is not what the proxy asks: whether an
        Agent may read an Artifact is a fact about a grant rather than about a
        file, and the proxy asks the database for it through `proxy.READS`,
        which selects `program_reads_artifact`.

        So nothing in production calls this, and it is here on purpose: it is
        the one way to state the *negative*, which `load` can only raise.
        `tests/test_database.py` asks it of an import that redacted a secret and
        of one that refused bytes no longer hashing to the name they arrived
        under; absence is the whole claim in both, and a test spelling it
        `path_for(...).exists()` would assert the filing scheme rather than ask
        the store.
        """
        return path_for(self.root, sha256).exists()

    def discard(self, sha256: str) -> bool:
        """Remove bytes this process wrote that nothing can have referenced.

        Not a general delete, and it is not the way an artifact is retired --
        that is a purge, and it goes through the database. This is for the one
        case `put` creates and cannot resolve: bytes written on the way into a
        transaction that then rolled back. Deleting those is safe only where no
        other writer could have arrived at the same hash, which is true of a
        ciphertext -- its nonce is fresh, so its hash is unreachable to anyone
        else -- and false of plaintext, where another Program may already have
        committed a reference to exactly those bytes.
        """
        try:
            path_for(self.root, sha256).unlink()
        except FileNotFoundError:
            return False
        return True

    def load(self, sha256: str) -> bytes:
        """The whole plaintext, verified against the name it is filed under."""
        path = path_for(self.root, sha256)
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise Missing(f"{sha256} is not in the store at {self.root}") from error
        except OSError as error:
            raise Missing(f"{sha256} cannot be read: {error}") from error
        found = digest(data)
        if found != sha256:
            raise Corrupt(f"{sha256} is filed under its hash but hashes to {found}")
        return data

    def read(self, sha256: str, view: Window) -> bytes:
        """One range of a verified artifact.

        The whole plaintext is hashed and only then sliced. Hashing the slice
        would verify the answer against itself, and a range that misses the
        damage would read clean out of a corrupted artifact.
        """
        return self.load(sha256)[view.offset : view.offset + view.length]

    def verify(self, named: list[dict]) -> dict:
        """Hold every named hash against the bytes filed under it.

        Takes what the database said -- a label and a hash per row -- because the
        question is always "is the record still true of the store", never "what
        does the store contain". A file nobody's row names is not a failure; a
        row whose file is gone is.
        """
        broken: list[dict] = []
        for item in named:
            try:
                self.load(item["sha256"])
            except (Missing, Corrupt) as error:
                broken.append({"label": item["label"], "detail": str(error)})
        return {
            "sound": not broken,
            "verified": len(named) - len(broken),
            "broken": broken,
            "root": str(self.root),
        }
