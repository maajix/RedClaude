# 237 — A probe-only transport class has no Playbook step that can support it

**What to build:** A Playbook step that files a `transport_parameters_observed`
Observation off the runtime's own unintercepted measurement, so that a
`probe_only` transport class has a reading behind it — or the written decision
that the two `probe_only` classes are probe-lane facts and no Playbook will
ever emit them.

**Blocked by:** 233 — A probe-only Playbook bar asks for two kinds its own
trigger refuses; 116 — A probe-only transport claim can never become a Finding.

**Status:** open

**CONSUMES:** `transport_makeability`
(`src/redkraken/migrations/0025_transport_claims.sql:203-233`);
`transport_evidence_guard` (`:361-395`); the runtime's own transport
measurement, added by ticket 93.

**CONSUMED BY:** `tools/check_wiring.py::vocabulary_gaps` (W9), which reports a
declared class no Playbook emits and carries two such gaps as `owed` today.

- [ ] **Which of the two classes this is for is decided, not assumed.**
      `transport.tls_configuration` and `transport.certificate_trust` are both
      `probe_only` and both currently emitted by nobody. They rest on
      different measurements — TLS version, cipher and ALPN for the first,
      the certificate chain for the second — and the register names different
      `allowed_fields` for each. One ticket may answer both or only one, and it
      says which.
- [ ] **The step names the Observation and the Receipt it rests on.**
      `transport_observation_guard`
      (`0025_transport_claims.sql:304-308`) refuses a
      `transport_parameters_observed` Observation that cites an intercepted
      agent-lane Receipt. So the step has to reach the measurement lane, and
      the Playbook says how a model asks for one rather than describing a
      reading no model can perform.
- [ ] **The bar it declares is one the guard admits.** Every
      `polarity: supports` row of the Playbook's `bb:evidence` names
      `transport_parameters_observed`, because for a `probe_only` claim that is
      the only kind `transport_evidence_guard` admits. This is the rule ticket
      233 was opened on, and this ticket is the other side of it.
- [ ] **The W9 gap closes or is re-owed in writing.**
      `tools/check_wiring.py`'s `OWED` registry carries
      `W9 transport.certificate_trust` and, after 233,
      `W9 transport.tls_configuration`. Whichever this ticket answers is
      removed from the registry rather than left standing beside a Playbook
      that now emits the class.

## Why

Ticket 233 measured that the bar in `http-desync` asked for two Observation
kinds that `transport_evidence_guard` refuses on a `probe_only` claim, and took
the only repair that does not break the Playbook's working half: it removed
`transport.tls_configuration` from `bb:outputs`. That leaves the class declared
by the schema, gradeable by the register, and emitted by nobody — the same
state `transport.certificate_trust` has been in since ticket 101, and for the
same reason.

Ticket 116 is not this ticket. 116 widens `reject_non_agent_evidence` and
`reject_non_agent_citation` so that a `probe_only` claim's Observation may also
be cited by the Finding that rests on it. After 116 the class can reach a
Finding; it still has no Playbook step that produces the Observation the guard
demands. Both are needed and neither closes the other.

Ticket 93 took the unintercepted transport measurement, so the Receipt this
step would rest on exists. What does not exist is a Playbook that asks a model
to obtain one, which is why `rk2_gradable_claims`' makeability arm refuses
nothing that reaches it today —
`tests.test_database.HypothesisHuntTest.arrange_refuses` records that in its
own docstring, and records that it was left untested rather than tested against
a row the runtime cannot hold.
