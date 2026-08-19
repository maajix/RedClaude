# 84 — Grade the shipped Playbook corpus over the door

**What to build:** The graded runs the corpus migrations deferred: every in-scope Playbook hash evaluated against its bound fixtures through the door route, with the verdicts filed and whatever passes promoted at the text it ships.

**Blocked by:** ticket 78, which built the door route this grades over.

**Status:** ready-for-agent

- [ ] Every in-scope web/API Playbook is graded at the exact text it ships, against each fixture `playbook_fixture_binding` gives it, through an Agent boundary rather than the zero-filing loopback path.
- [ ] Each filed run is a door run that reached its fixture: `playbook_test_runs.route` is `door`, the run has Tool runs, and `check_playbook_tests` reports no `test_run_reached_nothing` against it.
- [ ] Positive recall and adversarial precision are graded from those runs, not from offline fixture grading, and the verdict for each hash follows from what was filed.
- [ ] A Playbook that passes reaches `stable` through `playbook_test_verdict` and `playbook_promotion_evidence` at its own `p_sha`; one that fails stays `draft` and says why.
- [ ] The run is repeatable from the shipped surface -- `rk playbook evaluate` per Playbook and fixture, with the boundary the environment declares -- and its cost is stated before it starts, because each repeat is a real Agent run.
- [ ] The eleven deferred criteria across tickets 46 and 49 through 57 are ticked or restated, each citing the graded runs that closed it.

## Why

Ticket 78 built the route these criteria were waiting for. Until then an
evaluation run was an Agent run against a fixture on loopback, and
`scope.compile_policy` and `authorize_identity_egress_address` both refuse
loopback, so the corpus migrations (49 through 57) shipped their Playbooks
`draft`, graded their fixtures offline, and deferred the production halves to
"the route above". Ticket 46's own sixth criterion deferred the same thing from
the other end: every seam but the proxy.

78 closed the route -- an evaluation now serves its fixture on the agent network
and the door dials it by address, with a Receipt per request and
`playbook_test_runs.route` recording which way the run went -- and proved it on
one Playbook, `object-ownership`, in `ContainedEvaluationTest`. What it did not
do is grade the other forty-eight. That is measurement, not plumbing: it costs a
real Agent run per repeat per fixture, it wants a stated budget, and its result
is a set of verdicts that may not all be `pass`.

Splitting it out keeps the two statements apart. 78 says the route exists and is
tested. This ticket says what the corpus scores on it.
