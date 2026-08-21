# 123 — A secret read does not name the exchange it was made for

**What to build:** The receipt back-link on the secret audit row, so that a
credential read can be tied to the request that used it.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `secret_access_log.receipt_id` (`0024_secret_keying.sql:128`) is set by
      the writers that have a Receipt in hand. It is the only column of that
      table with no writer anywhere: a `grep` for `receipt_id` across every
      `INSERT INTO secret_access_log` in the corpus returns nothing.
- [ ] The writers are enumerated and each one either sets it or says why it
      cannot. There are thirteen: `src/redkraken/artifact.py:272-278` and twelve
      SQL sites across `20260811T140000Z__sealed_proxy_response_views.sql:246`,
      `20260811T150000Z__encrypted_identity_slots.sql` (six) and
      `20260811T190000Z__required_header_values_at_the_door.sql` (five). Six of
      them already carry `tool_run_id`, so a Tool run is identified today and an
      exchange is not.
- [ ] The distinction that makes this worth doing is stated in the ticket: a
      Tool run makes many requests, and the question a credential audit has to
      answer is which request carried the value. `receipts` is the row that
      names an exchange, and this column is the only edge between the two
      tables.
- [ ] The four other columns the audit report groups with this one are left
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
