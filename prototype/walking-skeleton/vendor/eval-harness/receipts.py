"""PROTOTYPE receipt shim.

Same table shape as prototype/scope-proxy/receipts.py, minus mitmproxy. Every
outbound request the runtime makes gets a row here; the harness later refuses
any claim whose evidence receipt has no row. Sequence numbers, not clocks --
two runs of the same mode must diff to nothing.
"""

import hashlib
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS receipts (
  id           TEXT PRIMARY KEY,
  run_id       TEXT NOT NULL,
  seq          INTEGER NOT NULL,
  lane         TEXT NOT NULL,
  identity     TEXT,
  method       TEXT NOT NULL,
  url          TEXT NOT NULL,
  status       INTEGER,
  req_sha256   TEXT NOT NULL,
  resp_sha256  TEXT NOT NULL
);
"""


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


class ReceiptLog:
    def __init__(self, path, run_id):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.run_id = run_id
        self.seq = 0

    def record(self, lane, identity, method, url, status, req_bytes, resp_bytes):
        self.seq += 1
        rid = "r-%s-%04d" % (self.run_id, self.seq)
        self.db.execute(
            "INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, self.run_id, self.seq, lane, identity, method, url, status,
             sha(req_bytes), sha(resp_bytes)),
        )
        self.db.commit()
        return rid

    def exists(self, rid):
        cur = self.db.execute("SELECT 1 FROM receipts WHERE id=?", (rid,))
        return cur.fetchone() is not None

    def get(self, rid):
        cur = self.db.execute(
            "SELECT id,seq,lane,identity,method,url,status FROM receipts WHERE id=?", (rid,))
        row = cur.fetchone()
        if not row:
            return None
        keys = ["id", "seq", "lane", "identity", "method", "url", "status"]
        return dict(zip(keys, row))

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    def dump(self):
        cur = self.db.execute(
            "SELECT id,seq,lane,identity,method,url,status FROM receipts ORDER BY seq")
        keys = ["id", "seq", "lane", "identity", "method", "url", "status"]
        return [dict(zip(keys, r)) for r in cur.fetchall()]


def write_jsonl(path, rows):
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
