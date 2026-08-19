# 84 — Grade the shipped Playbook corpus over the door

**What to build:** The graded runs the corpus migrations deferred: every in-scope Playbook hash evaluated against its bound fixtures through the door route, with the verdicts filed and whatever passes promoted at the text it ships.

**Blocked by:** ticket 78, which built the door route this grades over.

**Status:** ready-for-human

- [ ] Every in-scope web/API Playbook is graded at the exact text it ships, against each fixture `playbook_fixture_binding` gives it, through an Agent boundary rather than the zero-filing loopback path.
- [ ] Each filed run is a door run that reached its fixture: `playbook_test_runs.route` is `door`, the run has Tool runs, and `check_playbook_tests` reports no `test_run_reached_nothing` against it.
- [ ] Positive recall and adversarial precision are graded from those runs, not from offline fixture grading, and the verdict for each hash follows from what was filed.
- [ ] A Playbook that passes reaches `stable` through `playbook_test_verdict` and `playbook_promotion_evidence` at its own `p_sha`; one that fails stays `draft` and says why.
- [x] The run is repeatable from the shipped surface -- `rk playbook evaluate` per Playbook and fixture, with the boundary the environment declares -- and its cost is stated before it starts, because each repeat is a real Agent run.
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

## What was built, and what is left

`rk playbook cost` states the campaign before it starts, which is criterion 5's
second half and the reason the rest of this ticket is not an agent's to run. It
reads the two things the verdict reads -- `playbook_fixture_binding` and
`playbook_test_policy` -- discounts every repeat already filed at the text a
Playbook ships, and reports what the corpus still owes:

    50 Playbook(s) against 54 bound fixture(s) each, 0 of the required
    repeat(s) already filed at the text they ship
    16200 Agent run(s) still owed, reserving 3240000000 token(s) against
    the 200000-token envelope one run is ranked against

Sixteen thousand two hundred, because the binding is total: every one of the 54
fixtures is bound to every one of the 50 Playbooks, `required_repeats` is 3, and
every fixture in this catalogue is an `own_pair`, so one repeat is two Programs
-- the vulnerable half and the control. Nothing in that number is an estimate.
The token figure is the reservation those runs imply at
`scheduler_weights.cost_reference_tokens`, in the unit 023 says this harness is
scarce in; no price is invented, because dollars are not a column here.

The command also states the route, and that is the part that decides whether the
spend buys a measurement. `rk playbook evaluate` on a machine describing no
Agent boundary opens each Program and attempts nothing in it, so a corpus graded
that way files 16200 honest zeroes. The campaign therefore needs a machine with
the boundary ticket 78 built -- an agent image, an internal network, a door and
its certificate -- and an Agent credential to spend.

That is why the remaining criteria stay open and this ticket is
`ready-for-human`: the work left is not code but a decision about spend on
infrastructure the sandbox this was built in does not have. The five unticked
boxes are one run of the surface that now exists, and the eleven deferred
criteria across tickets 46 and 49 through 57 are waiting on its result rather
than on anything else being built.
