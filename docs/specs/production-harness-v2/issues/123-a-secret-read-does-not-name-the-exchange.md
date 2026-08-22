# 123 — A secret read does not name the exchange it was made for

**What to build:** The receipt back-link on the secret audit row, so that a
credential read can be tied to the request that used it.

**Blocked by:** nothing.

**Status:** resolved

- [x] `secret_access_log.receipt_id` (`0024_secret_keying.sql:128`) is set by
      the writers that have a Receipt in hand. It is the only column of that
      table with no writer anywhere: a `grep` for `receipt_id` across every
      `INSERT INTO secret_access_log` in the corpus returns nothing.
- [x] The writers are enumerated and each one either sets it or says why it
      cannot. There are thirteen: `src/redkraken/artifact.py:272-278` and twelve
      SQL sites across `20260811T140000Z__sealed_proxy_response_views.sql:246`,
      `20260811T150000Z__encrypted_identity_slots.sql` (six) and
      `20260811T190000Z__required_header_values_at_the_door.sql` (five). Six of
      them already carry `tool_run_id`, so a Tool run is identified today and an
      exchange is not.
- [x] The distinction that makes this worth doing is stated in the ticket: a
      Tool run makes many requests, and the question a credential audit has to
      answer is which request carried the value. `receipts` is the row that
      names an exchange, and this column is the only edge between the two
      tables.
- [x] The four other columns the audit report groups with this one are left
      alone, and the reason is recorded rather than rediscovered.
      `peer_pid`, `peer_uid` and `peer_exe` are deliberately NULL, and
      `src/redkraken/artifact.py:268-271` says so: "they exist to record what a
      keyholder reads off SO_PEERCRED about somebody else, and a process writing
      them about itself would be recording a claim it could have made up".
      `dek_gen` is NULL because `secret_dek` is superseded -- `artifact_seal`
      seals against `secret_kek` directly -- which is ticket 126's neighbourhood
      and not this one.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(f) lists five columns
of `secret_access_log` as having no writer and calls the receipt back-link "the
load-bearing one: it is the only edge that would tie a secret read to the
request that used it".

One correction to the report. It presents all five as the same gap. Three of
them are a documented decision with the reasoning in the source, and a fourth
follows from a superseded key design. Narrowed to the one column that is a
defect, this is a small change: the writers that know a Receipt pass it.

## What was built

One migration,
`20260925T030000Z__a_secret_read_names_the_exchange.sql`, and the Python writer
that had to find its Receipt rather than hold one.

`record_proxy_exchange(text,jsonb,jsonb,jsonb)` is replaced whole (`:126-327`)
with two statements in the other order. It audited the wire seals of an exchange
and then minted that exchange's Receipt a few lines later, so it had the Receipt
all along and had it too late; now `write_allowed_receipt` runs first and the
`secret_access_log` rows carry `v_id`. Nothing else in the body moves. The
ordering had no durability to give up: this is one function in one transaction,
so neither statement outlives the other, and the "audit row before the thing it
records" rule that `rk artifact open` keeps is kept there because that command
writes a file the database cannot roll back.

`record_identity_proxy_exchange` is replaced for the same reason (`:337-443`).
It audited the session state a target issued and then delegated the Receipt to
`record_proxy_exchange`; the delegated call now has a name, the exchange is filed
before the capture is audited, and the row cites it. The Identity slot is still
updated above under the lock it was already taken with, so nothing about who wins
a concurrent capture moves, and the caller gets exactly the document it got
before.

`rk artifact open` is the third writer, and it is the one that had to go looking.
An operator opening a sealed wire artifact holds a label and nothing else,
possibly weeks after the exchange. The edge was already in the schema and had
never been read: a sealed wire artifact is filed under the hash of its plaintext,
and that hash is what the Receipt of the exchange recorded as `request_wire_sha`
or `response_wire_sha`. `artifact.EXCHANGE` (`artifact.py:300-304`) is that
lookup, `_exchange` (`artifact.py:1199-1212`) is the one caller of it, and
`open_wire` settles the answer once when the label resolves
(`artifact.py:872`) and carries it into every row it writes from there on.

No column, no constraint, no grant and no foreign key. The column is `0024`'s and
has been waiting for a writer; the two functions keep their signatures, so
`CREATE OR REPLACE` keeps their owner and their access list, which the migration
asserts in both directions rather than restating the grants. There is no FK to
`receipts` because `secret_access_log.program_id` is `ON DELETE SET NULL` on the
principle that an access that happened is a fact a purge does not erase, and an
unconstrained `receipt_id` keeps that property without a second cascade edge to
declare.

## The refusals name it too, and that is the point of most of it

Every outcome of `open` after the label resolves carries the exchange, not only
the release: a generation that is gone, a key file that is not this
installation's, sealed bytes that cannot be read, bytes that do not
authenticate, and a plaintext that could not be written out. Which request an
operator tried and failed to open a credential for is the question an audit asks
after the fact, and a trail that carried the answer only when the attempt
succeeded would carry it least often where it matters most.

Two Receipts naming one artifact is answered with nothing rather than with the
first of them. Identical wire bytes sent twice are one content-addressed
artifact and two exchanges, and choosing between them would put a request in the
trail that the read cannot be shown to have been made for. A back-link that is
sometimes a guess is worth less than one that is always a fact.

## The ten writers that do not set it, and why each cannot

Four are the proxy-side opens, and they are what makes this narrower than it
looks. `open_identity_slot` and `open_required_headers` write an `attempted`
row, `confirm_identity_slot_open` and `confirm_required_headers_open` write its
terminal outcome, and all four run while the request is still being built:
before it is sent, before there is a status code, and before anything has a
Receipt to name. The pair could be back-filled once the exchange lands and
deliberately is not. `secret_access_log.operation_id` exists precisely so that
the outcome of an attempt is a second row rather than an edit of the first, and
an audit table that is UPDATE-ed to add a fact is an audit table that can be
UPDATE-ed to remove one. What ties those four rows to their exchange is the Tool
run they share with it and the order they were written in, which is weaker than
a foreign key and is the honest strength of what is known. Closing that half
means the door carrying its `audit_id` into the exchange writer, which is a
change to `src/redkraken/proxy.py` and a decision about append-only audit.

Six are control side: `identity_slot_keying`, `confirm_identity_root_check`,
`provision_identity_slot`, `header_slot_keying`, `confirm_header_root_check` and
`provision_header_slot`, all under `rk identity provision` and `rk header
provision`, where an operator is establishing key material before anything has
been sent anywhere. There is no exchange and there is no request a value has yet
been used for. Sealing in `rk artifact seal` is the same case from the other
direction: it is bytes arriving for the first time, and an exchange that had
already recorded them would have sealed them itself.

## The four columns the report grouped with this one

Left exactly as they are, with the reason written where the next reader meets it
rather than in this file alone. `peer_pid`, `peer_uid` and `peer_exe` exist to
record what a keyholder reads off `SO_PEERCRED` about somebody else, and every
writer in this corpus is writing about itself; `artifact.py:281-292` has said so
since ticket 07 and now says the rest of it too. `dek_gen` numbers a wrapped data
key, and there is none: ticket 07 replaced `0024`'s envelope with a key derived
per Program and per generation from a file the operator names, `artifact_seal`
seals against `secret_kek` directly, and `check_wire_artifact_secrecy` grades a
row in `secret_dek` a violation rather than an absence.

That last one had a consequence outside this ticket's files.
`tools/check_wiring.py` carried `"W6 secret_dek": "owed:123"` -- a register row
saying this ticket owed `secret_dek` a producer. It does not and nobody does:
the corpus refuses one. The row is removed and `secret_dek` is named in
`BY_DESIGN` beside `cross_program_exempt_fks` and
`program_isolation_candidates`, which is where that gate keeps the relations the
database audit itself grades harmless. The audit's own word for this table is
"harmless-superseded rather than load-bearing".

## What it is asserted with

Seven cases in `tests/test_artifact.py:547-659`, and the migration's own
assertion block (`:462-521`).

The Python cases are about the two halves that can be wrong. The lookup has to
be bounded by the Program and asked about the wire hash, has to answer with the
exchange when exactly one Receipt names those bytes, and has to answer with
nothing both when none does and when two do. The parameters have to land in the
positions the statement reads them from, which is checked by binding every
placeholder the statement declares -- a receipt passed into the slot the field
name is read from would be a column quietly filled with the wrong thing rather
than a failure. A refused open is checked separately from a released one, and a
writer with no exchange to name is checked to leave the column null rather than
to leave it out.

The migration asserts what a column list can show and what it cannot. That the
column exists, that both bodies name it, that the Receipt is minted before the
audit row in the writer that mints one -- a body that named the column and still
wrote the row first would insert a NULL and satisfy everything else -- and that
replacing the two functions neither dropped the door's `EXECUTE` on
`record_identity_proxy_exchange` nor handed back the direct `EXECUTE` on
`record_proxy_exchange` that `20260811T150000Z` revoked. The standing
`capability_receipt_fence` asks those last two on every run; this is the
assertion at the moment the access list is at risk.

Verified end to end against a migrated database: one exchange filed through
`record_proxy_exchange` with one wire seal, and one through
`record_identity_proxy_exchange`, each leaving a `secret_access_log` row whose
`receipt_id` is the Receipt the same call minted.
