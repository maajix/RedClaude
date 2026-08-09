"""Receipts and content-addressed artifacts.

SQLite because the receipt SCHEMA is ticket 07's decision, not this
prototype's. What is being proven here is that emission is possible, cheap, and
complete -- including for blocked requests, which are the receipts that matter
most when a program asks what the harness did.

Two hashes per direction, not one. The agent-visible bytes and the wire bytes
differ exactly by the credential material the proxy injected, so:

  * `*_agent_sha` is what a subagent may cite as evidence, and is safe to show.
  * `*_wire_sha` is what actually crossed the network, and is the only thing
    that can be replayed or shown to a program -- and it is credential-bearing,
    so in v2 it is the artifact that must be encrypted under the KEK (Q20).

Collapsing them into one hash forces a choice between evidence that is
reproducible and evidence that is safe to put in a model's context.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
    receipt_id        TEXT PRIMARY KEY,
    ts_arrival        REAL NOT NULL,
    ts_egress         REAL,
    waited_ms         REAL,
    decision          TEXT NOT NULL,
    reason            TEXT NOT NULL,
    lane              TEXT NOT NULL,
    target_id         TEXT,
    identity          TEXT,
    method            TEXT,
    scheme            TEXT,
    host              TEXT,
    port              INTEGER,
    path              TEXT,
    query_sha256      TEXT,
    pinned_ips        TEXT,
    status_code       INTEGER,
    request_agent_sha TEXT,
    request_wire_sha  TEXT,
    response_wire_sha TEXT,
    response_agent_sha TEXT,
    notes             TEXT
);
"""


def canonical(head: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    """A stable serialisation to hash.

    Header order off the wire is not stable enough to hash directly, and hashing
    the raw socket bytes would make two identical requests hash differently
    because of ordering alone -- which destroys the deduplication the
    content-addressed store exists for.
    """
    lines = [head]
    for name, value in sorted((n.lower(), v) for n, v in headers):
        lines.append(f"{name}: {value}")
    return ("\n".join(lines) + "\n\n").encode("utf-8", "replace") + body


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "PROTOTYPE-wipe-me.sqlite",
                                  check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def put(self, blob: bytes) -> str:
        digest = hashlib.sha256(blob).hexdigest()
        path = self.artifacts / digest[:2] / digest
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        return digest

    def write(self, row: dict) -> None:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        self.db.execute(
            f"INSERT OR REPLACE INTO receipts ({cols}) VALUES ({marks})",
            list(row.values()),
        )
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT count(*) FROM receipts").fetchone()[0]
