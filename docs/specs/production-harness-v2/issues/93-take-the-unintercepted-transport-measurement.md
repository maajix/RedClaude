# 93 — Take the unintercepted transport measurement

**What to build:** The egress path that writes
`receipts.purpose = 'transport_measurement'`, and the trust decision that
measurement has to make before its receipt can be cited.

**Blocked by:** nothing. Ticket 88 shipped the fixture and the listener; this is
the lane the measurement is taken on.

**Status:** resolved

- [x] Something in `src/redkraken/` writes `purpose = 'transport_measurement'`.
      Today nothing does: `0021_scope_policy.sql:155` gives the column a default
      of `target_traffic`, and no Python writer moves it, so the purpose 025
      built citability on has never been used.
- [x] The measurement is the proxy process opening the connection itself, under
      the same scope decision, the same per-target concurrency slot and the same
      token bucket as Agent traffic. 025 is explicit that this is a purpose and
      not a second egress path: "One egress path survives; what changes is who
      terminates the TLS."
- [x] The receipt records `intercepted = false` and the three wire columns
      `wire_tls_version`, `wire_chain_verified` and `wire_hostname_verified`
      from the handshake the runtime itself performed, so
      `receipts.transport_citable` computes true for a target whose chain
      verifies and false for one whose chain does not, without anybody writing
      the flag.
- [x] The trust anchor is decided and written down. 025 says the chain is
      "verified against the SYSTEM trust store rather than the run CA", which is
      right for a live target and settles nothing for a fixture:
      `evaluation.served` mints a fresh authority per call into a directory that
      dies with the context manager and hands nobody its root, so a fixture
      measurement verifies against nothing. Either the evaluator's per-run
      authority is a trust anchor for the measurement of the Program it was
      minted for and for no other, or a fixture measurement is recorded
      unverified and stays non-citable on purpose. Whichever it is, the ticket
      says which and why.
- [x] `tls-configuration-pair` is measured on that lane and the two halves are
      distinguishable from the receipts alone: `wire_tls_version` reads
      `TLSv1.2` against the vulnerable half and `TLSv1.3` against the secure
      half, with the same `Strict-Transport-Security` advertisement on both.
- [x] A Playbook reading `transport.tls_configuration` can reach `supported`
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

## What was built

One migration,
`20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql`, and the
door-side caller of the writer it installs.

`record_transport_measurement(p_capability, p_receipt)` is the writer. It is
`SECURITY DEFINER`, `rk2_proxy` is the only role granted `EXECUTE` on it, and it
is the only way that role can put a row in `receipts` or in `tool_runs` -- the
door still holds no `INSERT` on either, which the migration asserts. It resolves
the capability the same way every other door verb does, refuses a payload that
carries the capability back in it, and settles four columns itself rather than
believing the caller: `purpose = 'transport_measurement'`, `lane =
'proxy_internal'`, `decision = 'allowed'` and `intercepted = false`. Every
`agent_*` column and `interception_ca_id` are cleared rather than refused, so a
door with a bug files an honest row instead of failing an exchange that already
happened. The lane is assigned here because it could not be derived:
`rk2_capability_lane` answers `agent` or `replay` and has no third answer, and
this row is neither.

The Tool run is the writer's own. It inserts one with `tool =
'rk2.transport_measurement'`, `transport = 'runtime'`, no `tool_use_id` and no
`agent_run_id`, and files the Receipt under that. A probe filed under the agent's
Tool run would be evidence about a party attributed to that party.

`Handler._measure` is the caller. It runs after the answer has been written, on
the scope decision that was already made: it dials the address `_pin` pinned, for
the Program that decision was made for, and refuses to run for a class a
measurement may not be filed under. It takes its own `fence.reserve` slot from
the same per-target concurrency and the same token bucket the exchange took one
from, so a handshake is egress and is counted as egress, and a Program with no
budget left is not measured now. One target is measured once per door process,
keyed on `(program, host, port)`; a target that could not be measured gives its
claim back so a later request tries again. Every failure is logged and swallowed:
an exchange that was served stays served whether or not the door also managed to
measure the target it served from.

No Identity is offered on that socket. A measurement is about what the target's
transport is, which it is before anybody authenticates, and spending a leased
credential to open a connection nobody sends a request on would spend it on a
question it cannot answer.

## The trust anchor, which is the half of this ticket that was a decision

The first of the two answers criterion 4 allowed: **the evaluator's per-run
authority is a trust anchor for the measurement of the Program it was minted
for, and for no other.**

The other answer was available and would have been cheaper -- record a fixture
measurement unverified and let it stay non-citable. It was rejected because it
makes `transport.tls_configuration` ungradeable in exactly the way ticket 88
closed the other half of: `transport_citable` requires `wire_chain_verified` and
`wire_hostname_verified`, a fixture's certificate is minted per run, and a
measurement verified against nothing is a measurement no Playbook can cite. The
class would have had a fixture, a listener and a lane, and still no verdict.

So the anchor is written down as a column. `fixture_addresses.trust_anchor` holds
the certificate text, under two checks: it is present exactly when the protocol
is `https`, and it looks like a certificate and not like a private key. The first
stops an anchor being recorded for a handshake that does not happen, which is the
kind of row that is later read as permission for something else; the second is
the split the evaluator already makes, at the boundary where it is handed over --
`evaluation.served` reads `authority.certificate` and hands the text on, and the
signing key never leaves the directory that dies with the context manager.

The scope is the Program and the lifetime is the evaluation.
`open_fixture_address` takes the anchor as its sixth argument and
`authorize_fixture_address` hands it back with the address and the class, both
keyed on the Program the capability resolves in, and the row is purged with
everything else the evaluation wrote. `proxy.connect` takes it as a keyword and
passes it as `cadata`, which replaces the system store for that dial rather than
adding to it: the probe of a fixture trusts that authority and nothing else, and
the probe of a live target passes no anchor and trusts the system store, which is
what 025 says it should.

The agent side is untouched. The exchange the agent asked for still terminates at
this door and the agent still sees the forged leaf on a chain it cannot check --
the anchor is kept for the probe and for nothing else. That is the split ticket
88 asked this ticket to leave alone: who the target *is* changes every run, and
what it *negotiates* is the fixture's whole subject.

## Two rules that had contradicted this since before it was written

Both were found by writing the first citable Receipt this harness has ever had,
and both are narrowed rather than lifted.

**025's shape constraint predates the `fixture` class.**
`receipts_transport_measurement_shape` admitted `scope_class = 'target'` only,
because it was written before there were fixtures. Grading the one class that can
only be settled by a measurement is what the fixture is for, so `fixture` is
admitted beside `target`, and the three classes the clause excluded --
`egress_support`, `control_plane`, `denied` -- are still excluded.

**007's decision 15 refuses every `proxy_internal` Receipt as evidence.** It was
written for the door's own housekeeping, which was the only thing that Lane had
ever carried, and 025 then built `transport_parameters_observed` on a Receipt
that must be `proxy_internal`. The two have been unsatisfiable together since the
day 025 shipped, and nothing noticed because no such Receipt existed. The guard
now asks `NOT transport_citable` as well as the Lane, so the door's housekeeping
backs nothing exactly as before -- asserted, not assumed -- and a measurement can
back the Observation it was taken for. It reads the generated column rather than
`purpose`, so what it admits is what the schema already computes rather than a
second opinion about it. `hypothesis_transition_refusal` is deliberately left
alone: it asks about the Receipt a *transition* cites, which is a Test run's.

## What it is asserted with

Thirteen cases in `tests/test_database.py` under `PH2-93` and six in
`tests/test_proxy.py`. The pair is measured end to end with no container in it:
both halves of `tls-configuration-pair` are served by `evaluation.served`,
dialled by `proxy.connect` against the anchor the evaluator minted for each, and
filed -- `wire_tls_version` reads `TLSv1.2` against the vulnerable half and
`TLSv1.3` against the secure half, while the `Strict-Transport-Security`
advertisement read back over the same connection is identical on both. A Playbook
reading the response alone would find one target twice.
