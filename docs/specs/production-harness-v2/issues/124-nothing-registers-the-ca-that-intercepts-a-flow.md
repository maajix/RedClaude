# 124 — Nothing registers the CA that intercepts a flow

**What to build:** A writer for `interception_cas`, so that the certificate the
door forges can be attributed to the CA that signed it, and so the door can stop
withholding what it already knows.

**Blocked by:** nothing.

**Status:** needs-triage

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
