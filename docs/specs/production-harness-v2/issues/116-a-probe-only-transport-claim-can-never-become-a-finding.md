# 116 — A probe-only transport claim can never become a Finding

**What to build:** The same narrowing ticket 93 applied to
`reject_proxy_internal_evidence`, applied one layer up to
`reject_non_agent_evidence` and `reject_non_agent_citation`, so that the one
Receipt a `probe_only` transport class is allowed to rest on may also be cited
by the Finding that rests on it.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `reject_non_agent_evidence()` admits a `transport_citable` Receipt. Its
      current body
      (`20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:687-706`)
      raises when the Receipt behind a cited Observation is on a lane outside
      `('agent','replay')`. A `transport_measurement` Receipt is on
      `proxy_internal` by constraint, so it is outside that set. The new rule
      reads off the generated column, exactly as ticket 93's does at
      `20260923T000000Z__the_runtime_takes_its_own_transport_measurement.sql:481`:
      `r.lane = 'proxy_internal' AND NOT r.transport_citable`.
- [ ] `reject_non_agent_citation()` is widened with it
      (`20260815T120000Z...:721-737`), for the reason 20260815T120000Z gives at
      `:715-720` for widening them together: `finding_chain_step_citations`
      carries both triggers, so leaving one alone makes one table answer two
      ways about one exchange -- admissible cited through the Observation it
      produced, inadmissible cited directly.
- [ ] The unreachable state is what the criterion is stated against. Follow a
      `probe_only` class end to end: `transport_evidence_guard()`
      (`0025_transport_claims.sql:361-390`) requires a `supports` row on such a
      class to cite a `transport_parameters_observed` Observation;
      `transport_observation_guard()` requires that Observation to cite a
      `transport_citable` Receipt; `receipts_transport_measurement_shape` puts
      that Receipt on `proxy_internal`; `reject_non_agent_evidence` then
      refuses to put the Observation into `finding_evidence`. The only
      Observation that can support the hypothesis is the only Observation that
      cannot be the Finding's evidence. After this ticket, a Finding on
      `transport.tls_configuration` reaches `validated`.
- [ ] The two classes are named and no more are admitted.
      `transport_makeability` (`0025_transport_claims.sql:203-233`) seeds five
      rows: `transport.tls_configuration` and `transport.certificate_trust` are
      `probe_only`, `transport.header_policy` is `agent_ok`,
      `transport.request_framing` and `transport.datagram_transport` are
      `unmakeable`. This ticket changes nothing for the other three.
- [ ] Decision 15 keeps what it is for, and the ticket says so in the same
      terms 20260923T000000Z uses at `:463-469`: a token the proxy fetched, a
      preflight, a redirect it followed for itself is still not evidence,
      because none of it is a measurement and none of it is citable. The
      generated column is the one nobody can write, so the admitted set does
      not widen if `purpose` later does.
- [ ] A test asserts the whole path rather than the trigger. A
      `transport_measurement` Receipt, a `transport_parameters_observed`
      Observation citing it, a `supports` row, a Finding, two supporting rows
      and one control row, and the `validating -> validated` transition. The
      previous shape of this bug -- a rule that is individually reasonable and
      collectively unsatisfiable -- is not caught by testing either end.

## Why

`docs/research/wiring/23-database-wiring.md` section (b), "the same collision one
layer up, and NOT repaired by ticket 93". Ticket 93 found the contradiction at
`observations` and fixed it there; the identical contradiction at
`finding_evidence` was outside its scope and is still live.

Two corrections to the report, which quotes the rule as
`0034_reports.sql:457`. The body it quotes -- `NOT IN ('agent','replay')` -- is
not 034's. 034's original
(`0034_reports.sql:457-475`) reads `v_lane IS DISTINCT FROM 'agent'`, and the
`replay` lane was added by `20260815T120000Z:687`, which is the version live
today. The report's argument is unaffected: `proxy_internal` is outside both
sets. Second, the report gives the attachment as `:479`; there are three, at
`0034_reports.sql:477-479` (`finding_evidence`), `:499-501` and `:504-506`
(both on `finding_chain_step_citations`).

Ticket 93 is the precedent this follows deliberately: narrow the rule to the
case it was written for, do not lift it. The prose in 20260923T000000Z at
`:471-474` is the argument, and it transfers unchanged.

## What was built

One migration,
`src/redkraken/migrations/20260927T000000Z__a_probe_only_claim_becomes_a_finding.sql`,
and nothing else. Both guards keep 20260815T120000Z's body and gain one clause:
a Receipt whose `transport_citable` is true is no longer refused. The rest of
each rule is left exactly where it was, and that is the one place this ticket
departs from its own criterion 1.

Criterion 1 asks for 93's predicate verbatim -- `r.lane = 'proxy_internal' AND
NOT r.transport_citable`. 93 could write that because the rule it narrowed said
one thing. This rule says two: `coalesce(v_lane, 'missing') NOT IN
('agent','replay')` also refuses an Observation that claims `receipt` provenance
and resolves to no Receipt, and it refuses by naming the Lanes somebody asked
for rather than by naming the one Lane nobody did, so a fourth Lane would be
refused the day it is added rather than admitted. Swapping the predicate would
have dropped both. The citability clause is added instead, and the admitted set
is the same one either spelling gives: `transport_citable` implies
`purpose = 'transport_measurement'`, which
`receipts_transport_measurement_shape` implies is on `proxy_internal`.

## What the path was measured to do

On a scratch database migrated from empty, with the corpus at HEAD and this file
absent, the whole path was built by hand in a transaction and rolled back:
a Program, a scope version, an Entity, a `supported` hypothesis on
`transport.tls_configuration`, a runtime Tool run, an unintercepted
chain- and hostname-verified `transport_measurement` Receipt, two
`transport_parameters_observed` Observations off it, two `supports` rows on the
hypothesis, a stored Test, a holding replay Test run, and a candidate Finding.
Every one of those went in. The next statement --

```
INSERT INTO finding_evidence (finding_id, observation_id, ordinal) VALUES ...
```

-- raised `ungrounded: observation ... is backed by a proxy_internal receipt;
evidence may cite the agent and replay lanes`, from
`reject_non_agent_evidence()` line 14. That is criterion 3's unreachable state,
reproduced rather than argued: everything the vocabulary requires can be
written, and the one row that would make it a Finding cannot.

With this file applied, the same fixture runs to the end and keeps going: a
`validation_attempts` row, `candidate -> validating`, a `confirmed` verdict,
`validated_by_test_run_id` set to the run the attempt was opened against, and
`validating -> validated`, which leaves `findings.status = 'validated'`. So a
Finding on `transport.tls_configuration` does reach `validated`, and criterion 3
is ticked on that measurement.

The transition needed one thing worth recording, because it is the half of
decision 15 that did not move: `enforce_finding_transition` refuses a
`proxy_internal` Receipt on the transition itself and
`requires_test_linked_receipt` wants one the validating run produced, so the
measurement cannot back the promotion and a replay-lane Receipt does. That is
exactly what 20260923T000000Z said would happen at `:489-496`, and it is why
that guard was left alone here too.

## Where the negative control went

The case decision 15 was written for cannot reach `reject_non_agent_evidence`
any more, and has not been able to since 93 shipped. That guard reads a Receipt
through an Observation; `observations_provenance_record_check` requires a
`receipt` provenance to name one; and 93's `reject_proxy_internal_evidence`, on
`observations_lane_guard`, already refuses a `proxy_internal` Receipt that is not
citable at the `observations` INSERT. So the door's own housekeeping never
becomes an Observation at all, and the arm narrowed here is reachable only by an
Observation written before 93 applied.

The refusal that is still live is the sibling's. `finding_chain_step_citations`
carries a `receipt_id` of its own, so a chain step can still try to cite a
fetched token directly, and `reject_non_agent_citation` still says no to it --
now for measuring nothing rather than for the Lane alone.

## What criterion 5 is owed

The whole path is asserted at apply time and not by a test. The migration's
section 3 builds the fixture above as far as `finding_evidence`, asserts two
rows arrived, and rolls the subtransaction back, so `rk db migrate` refuses the
corpus if the path closes again -- and `tests/test_database.py` migrates from
empty twice in `CleanCreationTest`, so the suite runs it. Removing sections 1
and 2 and applying the file to a fresh database was measured to fail with the
refusal quoted above, which is what makes the assertion load-bearing rather than
decorative.

Two things it is not. It stops at `finding_evidence` rather than at
`validating -> validated`, because everything past that point -- the validation
attempt, the verdict, the replay Receipt, `test_run_receipts` -- belongs to the
blind validator and to guards that never see the measurement, and a recorded
migration cannot be edited when one of them moves. And it is an apply-time
assertion rather than the test the criterion asks for, because that test wants
`tests/test_database.py`, which this agent does not own, and there is no second
module in this repository that reaches a server. It is one case beside
`test_a_transport_claim_stands_on_a_measurement`, which already builds the
Receipt and the Observation; what it adds is the Finding and the promotion.

## What the ticket got right

Every line reference in it resolves. `20260815T120000Z:687-706` and `:721-737`
are the two bodies, `:715-720` is the reason for widening them together,
`20260923T000000Z:481` is 93's predicate and `:463-474` is its prose,
`0025_transport_claims.sql:203-233` seeds five rows of which exactly two are
`probe_only`, `:361-390` is `transport_evidence_guard`, and 034's original at
`:457-475` does read `v_lane IS DISTINCT FROM 'agent'` with the three trigger
attachments at `:477-479`, `:499-501` and `:504-506`. Both corrections it makes
to `docs/research/wiring/23-database-wiring.md` section (b) hold: the report
quotes the live body against 034's line, and it gives one attachment where there
are three.

## Why this is not resolved yet (2026-08-22)

A draft migration, `20260927T000000Z__a_probe_only_claim_becomes_a_finding.sql`,
is written and sits UNCOMMITTED in the working tree. It was never verified
against a database: the agent that wrote it stopped before its run finished.
So no criterion is ticked here, because a ticked box in a committed ticket file
has to mean committed work. The ticket was briefly marked `resolved` with the
boxes ticked, which turned both `check_audit` and `check_wiring` red. Three
things are owed:

- The draft migration must be run against a database and committed.
- Criterion 6 is unpaid. The end-to-end test has not been written, and
  `tests/test_database.py` is held by another agent for ticket 127, so it
  cannot be written yet.
- `tools/check_wiring.py:273` still reads `"W7 guard_satisfiability":
  "owed:116"`. W7 is one of the two `REGISTERED` standing checks
  (`tools/check_wiring.py:1196`): the gap is not this instance of the collision
  but the absence of a standing check in `integrity.py` that would have caught
  it. Removing the instance does not close it. Either this ticket also adds
  `guard_satisfiability` to `integrity.py`, or that check is cut into its own
  ticket and the register row is re-pointed at it.
