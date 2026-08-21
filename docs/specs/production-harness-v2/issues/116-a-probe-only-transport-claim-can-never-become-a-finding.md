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
