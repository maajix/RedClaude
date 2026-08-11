# 07 — Encrypt credential-bearing wire Artifacts

**What to build:** Retain authoritative wire evidence without turning the database, Artifact store, logs or Agent reads into a plaintext credential archive.

**Blocked by:** 06 — Store and read a redacted Artifact.

**Status:** resolved

- [x] Wire Artifacts use authenticated encryption with runtime-owned key material outside the database and Agent-visible configuration.
- [x] Ciphertext metadata records algorithm version, nonce and plaintext hash while never storing the plaintext capability or credential.
- [x] A synthetic credential marker is absent from database dumps, logs, Events, diagnostics and ordinary Agent-visible reads.
- [x] Agent-view and wire-view Artifacts remain separate immutable references whose hashes describe the exact bytes each party saw.
- [x] Only an explicitly authorized runtime operation can decrypt a wire Artifact, and every such operation is audited.
- [x] Tampered ciphertext, wrong key material and cross-Program references fail closed without returning partial plaintext.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `acaf89c` on
2026-08-10.

`src/redkraken/seal.py` is the construction, `seal_wire` and `open_wire` in
`src/redkraken/artifact.py` are the two operations, `rk artifact seal|open` is
the adapter over them, and `20260810T173000Z__sealed_wire_artifacts.sql` is what
makes a sealed artifact a thing the database can describe and check.

0024 already had the shape: `artifact_seal` keyed by plaintext hash,
`secret_kek`, `secret_dek`, and a `secret_access_log` written on every keyholder
verb including refusals. What it did not have was an algorithm, a nonce, a
ciphertext identifier, a pairing to the agent-visible half, or anything that
wrote a row. This ticket adds those five columns, the two operations that write
them, and eight rules that hold the arrangement together.

An exchange is stored twice because two parties saw two different things. The
redacted view is an ordinary `agent_visible` artifact with a label, stored by
ticket 06's path unchanged. The wire view is an artifact whose `sha256` is the
hash of the wire bytes, whose `encrypted` and `visibility` columns say what it
is, and whose bytes exist on disk only as an envelope filed under the
ciphertext's own hash. The seal row is the pairing, and the wire view
deliberately has no `artifact_references` row: a label is how a Program reads an
artifact, so giving the wire view one would undo what the seal is for.

### What is asserted, and by what

`tests/test_seal.py` is 45 offline tests over the construction, with no database
anywhere in it. `DerivationTest` (5) is HKDF against RFC 5869's own A.1
vector, pinned rather than recomputed, plus the separation properties a
per-Program key rests on: a different salt and a different info string derive
different keys, and a length beyond what the expansion can produce is refused.
`RoundTripTest` (9) is the round trip both ways including the empty plaintext,
the ciphertext being the length of the plaintext and containing none of it, a
second seal of the same bytes producing different ones, the algorithm travelling
with the ciphertext, the envelope surviving encoding, and `Sealed.describes`,
which is how a recorded description is held against an envelope without a key.
`FailClosedTest`
(11) is every way it must not work, and its centre is
`test_every_single_bit_of_the_envelope_is_covered`: it flips each bit of a whole
envelope in turn and asserts that every one of them is refused, which is the
authenticity claim stated as a property rather than as three examples. The rest
are a truncated envelope, bytes that are not an envelope, a wrong key, another
Program's, another artifact's and another generation's associated data, and an
unknown algorithm name refused before any decryption. `RootTest` (19) is the key
file and what is derived from it — mode, size, a trailing newline that is not key
material, the check value against its documented derivation, per-Program keys,
and the audit fingerprint. `ContainmentTest` (1) is the one this module exists to
make assertable: its own source contains no driver import and no connection.

`tests/test_artifact.py::SealArgumentTest` is 7 tests over the seams that hold
before a connection is opened: the key is a path of its own rather than a key in
the configuration file, neither verb takes a hash, an open without `--authorize`
is refused by the operation rather than by argparse so that the refusal is a
recordable act, unusable key material is refused before the database, two views
that are the same bytes are not a pair, and the released plaintext is written for
its owner alone and never over an existing file. `StoreTest` gained one for
`Store.discard`.

`tests/test_cli.py::SealCommandTest` is 7 over the adapter — the key named
alongside the store and the connection string when the variable is unset, both
views required, no way to open an artifact by hash, an open with nowhere to put
what it opened refused, and neither the wire bytes nor the connection string
echoed back.

`tests/test_integrity.py::SealedStoreVerificationTest` is 6 over the gate's new
question, and the load-bearing one is that verifying an envelope needs no key at
all: the header is compared against the row, and the bytes against their hash.

`tests/test_database.py::SealedWireArtifactTest` is 21 live tests, the eighth
question that module asks and the fourth case in it that commits — what survives
the transaction is the subject. Criterion 3 is asked of the database rather than
of an archive: `rk db dump` writes a compressed custom-format file, so a grep
over one would pass whether the marker were in it or not. `find_in_database`
reads every column of every ordinary table, partitioned parent and materialised
view in `public` and answers where a value occurs; the marker occurs nowhere, and
the same question about the Program's own slug answers, so the absence is an
answer rather than a query that matches nothing.

`check_wire_artifact_secrecy()` has six negative controls in `CONTROLS`,
registered as `wire_artifact_secrecy`: credential-bearing bytes with no seal
describing them, a seal over material the artifact row calls agent-visible and
unencrypted, a sealed pair whose agent-visible half no Program names, the
ciphertext registered as a second artifact in its own right, `GRANT SELECT
(nonce) ON artifact_seal TO rk2_state`, and a wrapped data key inserted into
`secret_dek`.

Run on 2026-08-10 against `pgvector/pgvector:pg18` — PostgreSQL 18.4 with
pgvector 0.8.6, the pairing tickets 03 through 06 were verified on. The whole
suite with the server present is 460 tests, green, no skips, in 160s; without one
it is 356 with 12 skipped. `tools/check_baseline.py` reports `classifications=10
regressions=7 artifacts=223`, unchanged. There is still no typechecker configured
in this repository, so what ran in its place is `python3 -m compileall -q src
tests`, clean.

### Decisions worth naming

**The construction is built out of the standard library, and says so in every
ciphertext.** The runtime has no dependencies — `pyproject.toml` declares
`dependencies = []` — and the standard library has no vetted AEAD. So `seal.py`
is HKDF-SHA256 for derivation, a SHA-256 keystream in counter mode for
confidentiality, and HMAC-SHA256 over algorithm, nonce, ciphertext and associated
data for authenticity, in encrypt-then-MAC order, under two subkeys derived from
the nonce so that nothing encrypts and authenticates with the same bytes. The tag
is compared with `hmac.compare_digest` and verified before anything is decrypted,
so there is no ordering in which a caller receives bytes that were not
authenticated. This is the weakest part of the ticket and it is deliberate rather
than overlooked: the mitigation is that `alg` is recorded on the seal row and carried
in the envelope header, and `seal_algorithms` is a registry rather than a CHECK.
Adding AES-GCM or ChaCha20-Poly1305 later is a row in that table and a branch in
`unseal`; every existing seal keeps naming what it was actually sealed under, and
nothing has to be re-encrypted to be readable.

**There is no key in the database, wrapped or otherwise.** 0024's design wrapped
a data key per scope. This derives one instead, per Program and per generation,
from a file the operator names on the command line — so `secret_dek` stays empty
and rule 8 asserts that it does. What `secret_kek` holds is a random salt and 16
bytes of an HMAC output; neither is the secret, and the check value is what makes
"wrong key material" answerable before any ciphertext is touched, rather than an
authentication failure that looks like corruption three steps later. A derived
key needs no row, which is a stronger reading of "outside the database" than a
wrapped one.

**The plaintext hash is a hash of the exchange, not of the credential.** §2 asks
for the plaintext hash to be recorded, which would be alarming if the plaintext
were a token: a digest of a short secret is a secret. The plaintext here is a
whole wire message, so its digest is not, and it is the identifier the artifact
already had.

**The audit row goes down before the bytes do.** Each is its own statement, so a
failure between them leaves one of two states. A recorded open whose file never
appeared is an over-report an operator can dismiss; plaintext on disk that the
trail does not account for is the thing §5 exists to prevent. The release failing
after the row is recorded too, so the pair reads as what happened rather than as
a contradiction, and `test_a_release_that_cannot_land_is_still_on_the_record`
asserts exactly that ordering by pre-occupying the `--into` path.

**The plaintext leaves through a file and never through a report.** `rk artifact
open` writes it with `O_EXCL` and mode 0600, set at creation rather than
afterwards, and refuses to clobber — a report is printed to a terminal,
redirected into a log and pasted into a ticket, which is the set of places §3
says a credential may not reach.

**A refused seal takes its own ciphertext back up.** Ticket 06's rule is that
bytes are written before the row and never deleted, because another writer may
already have committed a reference to exactly those bytes. That reasoning does
not reach a ciphertext: its nonce was drawn a moment ago, so no other writer can
arrive at its hash and no row will ever name it. Leaving it would be an
unreferenceable file no check can reach and no purge can collect, so `seal_wire`
discards it on the way out of the contested transaction. `Store.discard` is
documented as being for that one case and not as a general delete.

**Two Programs cannot seal identical wire bytes, and that is 0024's rule.**
`artifact_seal.sha256` is the primary key, installation-wide, and 0024 states the
reason: with per-Program keys, deduplicating on the plaintext hash would let
purging one Program shred evidence another still references. So the second seal
is refused and receipted rather than deduped. The refusal is a runtime-visible
one — an operator running `rk artifact seal` sees it — and an agent learns
nothing, because no agent-reachable surface names the seal at all.

**The gate verifies envelopes while holding no key.** A sealed artifact is
reachable through no reference, so `integrity.artifacts()` walking references
alone would pass a database whose ciphertext was gone. It reads the seal rows
too, holds each envelope against its own hash and its recorded header, and
`test_a_missing_envelope_fails_the_gate_that_holds_no_key` is the control: every
registered check still passes with the ciphertext deleted, because no statement
in the database can open a file.

### Raised by review and deliberately not built here

- **The proxy now integrates this primitive for target authentication response
  headers.** A target-supplied `Set-Cookie` is removed from the Agent response
  and plaintext Artifact while the exact response is stored only as an
  authenticated encrypted envelope. Ticket 12 still owns Identity injection,
  encrypted session state and Identity-specific body projections; it extends
  this boundary rather than introducing the first proxy-side sealed view.

- **`--authorize` is a reason, not an identity.** It records why the plaintext
  was released, and the trail records the reason verbatim, but nothing here says
  *who*. `secret_access_log` has held `peer_pid`, `peer_uid` and `peer_exe` since
  0024, unset, for a keyholder process that reads them off `SO_PEERCRED`; nothing
  on this branch runs such a process, and nothing in it models an operator, so
  there is no identity to fill those columns from. Until there is, "explicitly
  authorized" is asserted as an explicit act carrying a stated reason, which is
  what this branch can honestly claim.
- **Nothing retires a released plaintext.** `rk artifact open` writes a file the
  operator now owns, and neither the command nor any later one deletes it or
  reports on it. 0024 reserves a `shred` verb in `secret_access_log`'s CHECK
  constraint for exactly this, and it has no writer yet.
- **The proxy's placeholder artifacts are unsealed on purpose.** Rule 2 fires on
  an encrypted artifact with bytes and no seal, and excludes `byte_size = 0`,
  because `register_proxy_artifacts()` registers four hashes per intercepted call
  with no bytes behind any of them. There is nothing to seal until ticket 09
  stores real bytes, and it will store them through this path. Left as it is,
  that exclusion cannot hide a credential: a row with no bytes has none.
- **The glossary is not updated.** `CONTEXT.md` defines **Artifact** and says
  nothing about a seal, an envelope or key material. As with ticket 06, no
  implementation ticket in this branch edits that file — `docs/agents/domain.md`
  says the glossary is maintained by `/domain-modeling` — so the terms this
  ticket introduces are documented in the migration header and belong in the
  glossary whenever that skill runs next.

### The wire view names its exchange, 2026-08-11

A sealed wire view is now `x-redkraken-exchange: <arrival> <method> <url>`
followed by the message, and the hash that identifies the artifact is the hash
of that document. Criterion 4 still holds -- the two views are separate
immutable references and each hash describes exactly what its party is shown --
but the wire hash is no longer the hash of the target's message alone, and that
is the change.

What forced it is the store, not the cryptography. One hash is the whole
identity of an artifact, and an artifact is either agent-visible or
credential-bearing and never both. The bytes of a message are not unique to an
exchange: fetch a page anonymously and then with an Identity, whose wire view is
that same message, and the two classifications land on one row. Whichever
exchange arrived second could not be recorded at all -- `record_proxy_exchange`
refused it, the door answered 502, and the bytes were already spent. Both orders
happened, in the ordinary case of reading a page and then reading it as somebody.

Neither party loses anything to the added line. The Receipt already carries the
moment and the request in the clear, so the line reveals nothing the record does
not, and it withholds nothing: the message follows it unaltered. It is written
under the internal prefix, which `describes_this_hop` keeps off the wire in both
directions, so it is the door's own statement and never something a target sent.
The transcript was already a reconstruction rather than the socket's bytes --
`transcript()` says so -- and this makes it a reconstruction of one exchange.

`tests/test_database.py::ProxyEgressTest` has the two orders as two cases, each
of which fails with `(502, 'receipt-refused')` without this: an authenticated
fetch of bytes the Agent already read, and an anonymous fetch of bytes an
Identity already sealed. The first also records the other half of the rule --
when the message is already in the store as an Agent artifact, the door hands it
to the Agent rather than projecting it away, because withholding bytes a Program
can already read under a hash it already holds is theatre, and sealing them
would pair that Program's plaintext with a ciphertext of itself.
