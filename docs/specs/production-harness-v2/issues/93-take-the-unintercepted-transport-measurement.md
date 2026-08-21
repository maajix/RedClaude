# 93 — Take the unintercepted transport measurement

**What to build:** The egress path that writes
`receipts.purpose = 'transport_measurement'`, and the trust decision that
measurement has to make before its receipt can be cited.

**Blocked by:** nothing. Ticket 88 shipped the fixture and the listener; this is
the lane the measurement is taken on.

**Status:** ready-for-agent

- [ ] Something in `src/redkraken/` writes `purpose = 'transport_measurement'`.
      Today nothing does: `0021_scope_policy.sql:155` gives the column a default
      of `target_traffic`, and no Python writer moves it, so the purpose 025
      built citability on has never been used.
- [ ] The measurement is the proxy process opening the connection itself, under
      the same scope decision, the same per-target concurrency slot and the same
      token bucket as Agent traffic. 025 is explicit that this is a purpose and
      not a second egress path: "One egress path survives; what changes is who
      terminates the TLS."
- [ ] The receipt records `intercepted = false` and the three wire columns
      `wire_tls_version`, `wire_chain_verified` and `wire_hostname_verified`
      from the handshake the runtime itself performed, so
      `receipts.transport_citable` computes true for a target whose chain
      verifies and false for one whose chain does not, without anybody writing
      the flag.
- [ ] The trust anchor is decided and written down. 025 says the chain is
      "verified against the SYSTEM trust store rather than the run CA", which is
      right for a live target and settles nothing for a fixture:
      `evaluation.served` mints a fresh authority per call into a directory that
      dies with the context manager and hands nobody its root, so a fixture
      measurement verifies against nothing. Either the evaluator's per-run
      authority is a trust anchor for the measurement of the Program it was
      minted for and for no other, or a fixture measurement is recorded
      unverified and stays non-citable on purpose. Whichever it is, the ticket
      says which and why.
- [ ] `tls-configuration-pair` is measured on that lane and the two halves are
      distinguishable from the receipts alone: `wire_tls_version` reads
      `TLSv1.2` against the vulnerable half and `TLSv1.3` against the secure
      half, with the same `Strict-Transport-Security` advertisement on both.
- [ ] A Playbook reading `transport.tls_configuration` can reach `supported`
      from a citable receipt, and cannot reach it from an intercepted one. 025
      built the refutation into the row; this is the ticket that proves the
      distinction is load-bearing rather than latent.

## Why

Ticket 88 closed the coverage half of
`one-playbook-has-no-fixture-to-be-graded-against` and left this half open, and
the split is deliberate rather than a shortcut.

88 gives `playbooks/http-desync` an own pair to be graded against, so its verdict
leaves `untested` and the campaign ticket 84 will spend buys something for it.
What 88 does not give it is an admissible measurement. The evidence
`transport.tls_configuration` actually turns on is a handshake the Agent did not
take: behind the interception proxy the Agent's TLS parameters are the proxy's,
which is the measurement 025's header records and the reason that migration
exists at all. `receipts.transport_citable` is generated over
`purpose = 'transport_measurement' AND intercepted = false AND decision =
'allowed' AND wire_tls_version IS NOT NULL AND wire_chain_verified IS TRUE AND
wire_hostname_verified IS TRUE`, and no receipt in this harness has ever
satisfied the first conjunct.

So the schema has held one side of an argument since 025 and nothing has ever
made the other side. That is not a defect in what ships -- nothing untested is
presented as tested, and an intercepted receipt carries its own refutation -- but
it is a lane that has never been walked, and a generated column nobody can write
is only worth what the writer that satisfies it is worth.

## What ticket 88 found out about the shape

* `grep purpose src/redkraken/proxy.py` finds prose and no writer. The column is
  reachable from SQL and from nothing else in the tree.
* `proxy.connect` already dials a target twice when the first attempt cannot
  verify: it keeps the strict attempt's words, dials again with verification
  off, and records `chain_verified = false` and `hostname_verified = false`.
  That is most of the shape of a measurement already, on the wrong purpose.
* The fixture's certificate is the evaluator's rather than the fixture's, and
  the split is the same one the fixture format already makes between ground
  truth and application: who the target *is* changes every run, and what it
  *negotiates* is the fixture's whole subject. Any trust answer here has to
  leave that split alone.
* `tests/test_fixture.py:ServingOverTls` reads the shipped pair over TLS with a
  `CERT_NONE` client and comments why: an exchange with this fixture is recorded
  as the unverified one it is. That comment is the statement of this ticket's
  question, written where the code makes it.
