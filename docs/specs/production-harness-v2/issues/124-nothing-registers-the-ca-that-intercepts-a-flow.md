# 124 — Nothing registers the CA that intercepts a flow

**What to build:** A writer for `interception_cas`, so that the certificate the
door forges can be attributed to the CA that signed it, and so the door can stop
withholding what it already knows.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A run registers its CA. `interception_cas`
      (`0025_transport_claims.sql:467-503`) has nine columns, six named CHECKs
      (`interception_cas_window`, `_max_lifetime`, `_secret_ref_shape`,
      `_supersede_needs_retire`, `_no_key_material`, and the `spki_sha256`
      pattern), a partial unique index `interception_cas_one_current` (`:506-507`)
      and a purge edge (`:509-511`). There is no `INSERT INTO interception_cas`
      anywhere in the corpus, including in migrations, so every one of those is
      an assertion about an empty table.
- [ ] The door stops suppressing what it holds. `src/redkraken/proxy.py`
      currently leaves `agent_cert_sha256`, `agent_cert_issuer`,
      `agent_cert_subject` and `agent_cert_not_after` NULL, and its own
      docstring says exactly why (near `proxy.py:1981-1986`, a file under
      concurrent edit -- find it by the sentence): "`agent_cert_*` stays null
      even though the door knows the leaf it presented. Recording it means
      naming the forging key under `receipts_intercepted_leaf_names_ca`, and
      nothing yet writes the `interception_cas` row that name would point at."
      Once a CA row exists, those four columns are filled and
      `receipts.interception_ca_id` points at it.
- [ ] The consequence that is currently invisible is named: this is not a silent
      gap, it is a documented one that costs a column family. The harness knows
      the leaf it forged, cannot attribute it, and therefore records nothing --
      so `check_transport_claims`'s `unattributed_forged_leaf` arm
      (`20260815T000000Z__a_test_runs_through_the_replay_lane.sql:2435-2440`)
      never fires, not because no leaf is unattributed but because no leaf is
      recorded. Its `expired_ca_still_current` arm (`:2443-2447`) is empty for
      the same reason.
- [ ] Who writes the row is the decision this ticket settles. The lifecycle in
      the schema is engagement-bounded and operator-shaped: a `secret_ref` in
      ticket 15's format, a ninety-day maximum lifetime, one current CA per
      Program, and retire-then-supersede rotation. That is an operator command
      or a run-start step, not something the door can do for itself, and the CA
      key material lives outside the database by construction.
- [ ] The read surface follows. Ten `interception_cas` columns are on the
      agent's read surface today and every one of them is NULL, with
      `secret_ref` deliberately excluded -- `check_transport_claims` asserts
      that exclusion at `20260815T000000Z...:2472-2475`. Filling the table makes
      nine of those ten real, and the tenth stays excluded.
- [ ] `20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql:406`
      is left as it is and the ticket says why: a measurement Receipt sets
      `interception_ca_id := NULL` on purpose, because an unintercepted
      measurement has no forging key to name.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1 grades this
load-bearing: "the design's story about *which* CA intercepted a flow has no
recorded answer".

One correction. The report says `src/redkraken/proxy.py` "mentions the name but
never inserts", which reads as an oversight. The door is not overlooking the
table; it is refusing to write a leaf it cannot attribute, and it says so in
prose at the point of refusal. That makes this a deferred phase rather than a
defect -- but an undeclared one, which is why it needs a decision rather than a
patch: nothing in the tree says when the CA registry is due, and the whole
transport-claim design in 025 rests on it.

## The decision, taken 2026-08-22

**Register the authority that actually exists, and change one CHECK to let it be
registered. The row is written by the runtime, from the CA *certificate* it was
told to trust, at the point a Program first has a door to intercept with. The CA
key does not move into the secret store, and 025's channel-delivery design is
retired rather than built.**

### Why a writer cannot simply be added

The CA the schema describes and the CA this harness makes are different objects,
and one constraint is where they collide.

What ships is a per-run, on-disk root: `tls.authority(directory)`
(`src/redkraken/tls.py:293-340`) makes it with `openssl req -x509` if it is not
there and reuses it if it is, writes the key to `ca-key.pem` in a directory the
door owns (`:150-151`), gives it `DAYS = 7` (`:58`), and constrains it with
`basicConstraints=critical,CA:TRUE,pathlen:0` and
`keyUsage=critical,keyCertSign,cRLSign`. It is made by the **door**, which is
started by an operator with `--authority` (`src/redkraken/cli.py:130`,
`src/redkraken/proxy.py:3555-3568`), and the key is "handed to nobody"
(`src/redkraken/evaluation.py:248-249`).

Held against the table (`0025_transport_claims.sql:467-503`), three of the four
things that look like obstacles are not:

* `interception_cas_max_lifetime` caps life at 90 days. Seven passes.
* `program_id NOT NULL` and `interception_cas_one_current` look wrong for an
  authority one door shares across Programs, and are not: the row is a statement
  that *this Program's* flows were intercepted under *that* key, so the same
  authority is registered once per Program, one row each, exactly one current.
  Nothing about the table has to change for that.
* `spki_sha256` is derivable without the key: the SPKI comes out of the
  certificate, and the door already does the equivalent computation over its
  other key in `Authority.pin` (`tls.py:207-224`). One note for the
  implementer -- `pin()` hashes the **leaf signing key** (`leaf-key.pem`), not
  the root; `spki_sha256` is the root's, and the two are different keys in the
  same directory.

The one that does block it is `interception_cas_secret_ref_shape CHECK
(secret_ref ~ '^(op://|kek:)')` on a `NOT NULL` column. The shipped key has no
secret reference of any kind -- it is a file in the door's directory -- so there
is no honest string to write, and writing one would be a lie about where key
material lives, which is the exact thing that CHECK and
`interception_cas_no_key_material` exist to prevent. **The migration that ships
the writer is the migration that admits a third form: a CA whose key is held by
the door and referenced nowhere.**

### Why not build 025's design instead

025's own preamble (`0025_transport_claims.sql:458-465`) sets up the choice: the
CA key is ticket 15's to hold "in the RUNTIME process ... so either the CA key
travels the runtime->proxy channel or 15's holder must be reachable from the
proxy. It must be the former; the proxy must not become a second 1Password
client." What shipped is a third option the preamble did not consider, and it is
better than either: the key is never in the runtime, never in a message, never in
1Password, and never lives longer than a week. `tls.py:55-57` states the property
that would be given up -- "a trust root that outlives the run it was minted for is
a trust root someone still trusts after the door that owns its key has stopped
answering." Moving a CA private key through an IPC channel to lengthen its life to
ninety days is the wrong trade, and the two constraints 025 wrote to keep key
material out of the database are satisfied more completely by the design that
ships than by the one it anticipated.

### Why not delete the table

`receipts_intercepted_leaf_names_ca` (`0025:154-157`) is what makes the door's
silence mandatory rather than merely cautious: an intercepted Receipt that names
a leaf must name the CA. Without a registry there is no CA to name, so the four
`agent_cert_*` columns can never be filled on any intercepted exchange, and the
transport-claim family loses the evidence it was built to carry. Deleting the
table would make that permanent rather than pending.

### Who writes the row

The runtime, not the door. The door holds the key and must not gain a database
grant that lets it describe itself; the runtime already holds the CA
**certificate** -- it verifies every target against `$RK_PROXY_CA_FILE`
(`src/redkraken/door.py:349`, the variable at `proxy.py:181`) -- and subject,
`not_before`, `not_after` and the SPKI all come out of that public half. So the
write needs no key access at all, which is the property that makes it safe to put
on the run-start path.

## What was measured

`grep -rn "INSERT INTO interception_cas" src/ tools/` returns **nothing**, in
Python and in the migration corpus alike -- the ticket's claim, verified. The
certificate the door makes carries a 7-day validity, subject
`/CN=redKraken run authority`, and a key at a filesystem path; the table requires
a `secret_ref` matching `^(op://|kek:)`. That single CHECK is the only one of the
six the shipped authority fails.

## Note on the ticket's read-surface criterion

Ten `interception_cas` columns are on the agent's read surface with `secret_ref`
excluded, and `check_transport_claims` asserts the exclusion
(`20260815T000000Z...:2472-2475`). Under this decision `secret_ref` stops
carrying a reference at all for door-held CAs, and the exclusion still stands as
written -- a column that may name a secret store for some rows must stay off the
surface for all of them. Nothing in the read surface needs to change; nine of the
ten columns simply stop being NULL.
