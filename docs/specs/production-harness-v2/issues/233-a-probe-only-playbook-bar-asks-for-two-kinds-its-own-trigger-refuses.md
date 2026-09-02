# 233 — A probe-only Playbook bar asks for two kinds its own trigger refuses

**What to build:** One decision, applied to `http-desync`: either its
`bb:evidence` bar names `transport_parameters_observed` for the roles it gates
`supported` on, or `transport.tls_configuration` comes off its `bb:outputs` so
the bar is only ever read against an `agent_ok` class. Today it declares both
and asks for neither's admissible kind, so one half of the Playbook can never
reach `supported`.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **The unreachable state is what the criterion is stated against.**
      `transport_evidence_guard()`
      (`src/redkraken/migrations/0025_transport_claims.sql:361-394`, and
      `ENABLE ALWAYS`, so it fires for replication and restore too) returns
      early unless the row is `polarity = 'supports'` and the claim's
      `property_class` is `probe_only` in `transport_makeability`. For such a
      claim it raises unless the cited Observation is
      `transport_parameters_observed`. `http-desync` declares
      `transport.tls_configuration` in `bb:outputs`
      (`src/redkraken/playbooks/http-desync/playbook.md:4`), which is
      `probe_only` (`0025_transport_claims.sql:204`), and its bar (`:13`) asks
      `response_invariant` for `control` and `response_differential` for
      `variant`, both `supports`. Neither edge can be **inserted** for such a
      claim, by any writer, so `playbook_evidence_unmet` can never empty and
      `enforce_playbook_evidence` raises on every `supported` transition.
- [ ] **The regression is named and dated.** `http-desync`'s own
      `bb:provenance` (`:12`) records that ticket 101's rewrite moved its
      evidence rows "off `transport_parameters_observed`, which the ledger
      established has no agent-reachable writer by any path". That reasoning is
      right about the *writer* and wrong about this class: for a `probe_only`
      class it is the only kind the guard admits, so the rewrite moved the bar
      from the one admissible kind onto two inadmissible ones. Whichever way
      this ticket goes, that sentence is corrected in the same edit.
- [ ] **The other four classes are checked, not assumed.**
      `transport_makeability` (`0025_transport_claims.sql:203-233`) seeds five
      rows: `transport.tls_configuration` and `transport.certificate_trust` are
      `probe_only`, `transport.header_policy` is `agent_ok`,
      `transport.request_framing` and `transport.datagram_transport` are
      `unmakeable`. Every Playbook whose `bb:outputs` names a `probe_only`
      class is read the same way, and the count is stated. `http-desync` is the
      case this ticket was opened on, not necessarily the only one.
- [ ] **A test asserts the whole path rather than the trigger.** A claim on
      `transport.tls_configuration` under this Playbook, the bar read through
      `playbook_evidence_unmet`, and the `supported` transition either landing
      or refusing by name. The previous shape of this bug — one rule that is
      individually reasonable and a corpus row that is individually reasonable,
      collectively unsatisfiable — is caught by neither end alone, which is why
      ticket 166's reachability sweep missed it.
- [ ] **What the choice costs is written down, either way.** Naming
      `transport_parameters_observed` keeps the Playbook gradeable but ties its
      bar to a Receipt only the runtime's own measurement can produce, so no
      agent-filed edge helps. Dropping `transport.tls_configuration` from
      `bb:outputs` keeps the bar agent-reachable but stops the Playbook
      claiming the TLS leaf it was written for. Ticket 166 took the analogous
      decision for five Playbooks on 2026-08-24 and recorded the loss; this one
      does the same rather than choosing silently.

## Why

Ticket 166 was opened on the claim that Playbook evidence bars gate `supported`
on Observation kinds no verb can write, and closed on 2026-09-02 having
established the opposite for the writer question: an evidence edge filed with
the proposal that mints a claim, while the claim is still `proposed`, is counted
by `playbook_evidence_unmet` at the `supported` transition, so every kind a
proposal can mint is reachable and only the writer differs.

That sweep asked which *writer* could produce a kind. It did not ask which kinds
a claim's own `property_class` admits, and there is a second `BEFORE INSERT`
trigger on `hypothesis_evidence` that decides exactly that. So one bar in the
corpus is still unreachable, and the reason is neither provenance nor the
replay's kind derivation — it is a per-property-class rule that predates both.
166's review pass found it; 166 could not take it, because taking it would have
been its ninth acceptance criterion against a ceiling of six.

This blocks ticket 84. 84 grades every in-scope Playbook at the text it ships
and requires precision and recall to come from door runs. A graded campaign
against `http-desync`'s `transport.tls_configuration` half would return `fail`
and measure this trigger rather than the Playbook — which is precisely what
ticket 166's 2026-08-24 comment recorded happening to five other Playbooks, at a
cost of 330 million budget units, before those five were narrowed.

## Notes

Not ticket 116's problem. 116 widens `reject_non_agent_evidence` and
`reject_non_agent_citation` so the Observation a `probe_only` claim rests on may
also be cited by the Finding that rests on it. It leaves
`transport_evidence_guard` alone, so after 116 a `probe_only` claim still needs
a `transport_parameters_observed` Observation and this Playbook's bar still asks
for two other kinds. The two tickets are adjacent and neither closes the other.

Not ticket 145's problem either, for the same reason 166 gave: every kind named
here is in the vocabulary with an `allowed_provenance` some writer could
satisfy. What is wrong is that the claim's Property class forbids the kind, not
that the kind forbids the provenance.
