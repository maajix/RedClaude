---
description: Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one leased workload token to a route while a second tenant is named first in the request line and then in the header that selects one, and closing on a Test whose own assertions carry the difference.
bb:category: authorization
bb:outputs: ["authorization.tenant_isolation"]
bb:triggers_all: ["header_parameter", "tenant_boundary", "unknown_auth_endpoint"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's workload-identities pack against the tenant-isolation leaf of the ticket 18 vocabulary, and rewritten for ticket 101 against the merged ledger's four readings for this slug. The shipped page put the tenant selector in a header alone, which before ticket 211 no Test action could state; the request-line reading is now spelled first and the header reading second, and both close a Test. The refuted variant kind is response_differential rather than an invariant, because close_test_replay reads the Observation kind off the Test specification and not off the outcome. The duplicated-header variant is blocked and credential harvesting is refused, and both are named at the end rather than dropped. Repaired in review -- section 4 had no control action of its own and both sections leaned on a second Task's refusal that no Test can cite, so the negative is now an arm the leased credential itself sends and each Test carries an in-spec control.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# The credential belongs to a workload; ask which tenant it can speak for

A workload credential is issued to a program rather than to a person, and the
component that authenticates it is often not the component that decides which
tenant it may read. Where those two never compare notes, the selection is made
by whatever the caller wrote -- a path segment, a query parameter, a header --
and the credential is only as confined as that string.

Arms are sent with `mcp__rk2__http_request`, and an arm that settles a claim is
an action of a Test proposed with `mcp__rk2__propose_test`. The writer of a
settlement is close_test_replay, which derives the transition and the
Observation kind from the Test's own assertions alone; an Observation filed
through `mcp__rk2__submit_mission_result` is a real evidence edge beside it and
settles nothing. Because that kind is read off the specification and not the
outcome, a Test naming a differing assertion writes response_differential
whichever way the arms went, which is why refuting this Playbook carries the
kind that supports it. Every Test holds at least three actions and fills all
three roles -- baseline, variant and control. Since ticket 211 an action states
the header and the body it plans, which is what puts the header reading of
section 4 on the Finding path at all.

## 1. Get a workload credential the Program issued

Read the route and its tenant selector from the state view with
`mcp__rk2__get_attack_surface`, then take the credential from a slot through
`use-identity`. For this class the slot holds a service credential the operator
provisioned for the engagement, in a tenant the Program names, and the Task was
opened under it, so no step below chooses it and there is no argument for it.

The Program must hold identities in at least two tenants. The second tenant is
what makes this a comparison rather than a guess, and without it the reading
does not start. Tenant identifiers come from the Program's own material or from
what the target itself disclosed; this Playbook does not enumerate them, and a
strange identifier that produces a different error is a naming oracle rather
than access. Where the second identifier is one the target disclosed rather
than one the Program holds, park the Task with `mcp__rk2__park_for_human`,
handing that Task's label to `task_label` and third_party_impact to
`question_code`, before it is sent, because the records that come back would
belong to somebody who is not in the engagement.

This step reads state and leases a credential. Nothing in it is graded.

## 2. Establish both ends of the scale

The top of the scale is the route read with the credential attached and the
caller's own tenant named, sent twice unchanged. Two identical sends, because
everything below is differenced against them: a route that answers its own two
differently is not one this reading can difference, and that verdict is
inconclusive and names the element that moved.

The bottom of the scale is the same read under the same leased credential,
naming a tenant identifier of the right shape that was never issued, which must
be refused. Take it once with `mcp__rk2__http_request` BEFORE any Test is
proposed and file its refusal as the credential_effect Observation in the role
control through `mcp__rk2__submit_mission_result`, which promote_proposal
writes: an edge cannot be added to a claim once it is past proposed, and the
first recorded Test action moves it there. That edge is this Playbook's declared
control leg, and it is the whole of it.

The read with no credential at all belongs to a different Task and carries no
edge here. A leased Identity owns Cookie and every header it declares for the
origin and replaces a plan-stated one before the wire, so an identity-less arm
cannot be sent from this Task at all; and a proposal element citing another Tool
run's Receipt is dropped as another run's evidence, so a reading taken elsewhere
cannot be cited here either. Where the route turns out to answer a caller
holding nothing, it has no tenant isolation to breach and what it has instead is
a missing authentication finding that belongs elsewhere. Name the neighbour and
do not perform it.

This section establishes and files; it closes no Test and grades nothing.

## 3. Name the second tenant in the request line

Where the selector is a path segment or a query parameter --
/t/<tenant>/orders, /api/orgs/<org-id>/, ?tenant=<id> -- the whole differential
rides the request line, and one Test carries the reading end to end. The
baseline is the caller's own tenant. The variant is the identical request with
a single substitution, the second tenant the Program holds. The control is a
tenant identifier that certainly does not exist, which must fail differently
from the second tenant's answer; where it does not, the reading is measuring a
naming oracle and stops.

The Test names body_differs on the variant against the baseline and
body_differs on the control against the variant. No arm spells a dot segment or
a percent-encoded dot, which the replay lane refuses in a specification url, so
a tenant identifier shaped like one is reported and not sent.

## 4. Name the second tenant in the header

Where the selector is a header, the same three arms are spelled in the header a
Test action now states. The name matches the harness's own header pattern, it
is neither hop-by-hop nor internally prefixed, and its value is printable
ASCII, so it forwards and the replay opens carrying it. The baseline is the
caller's own tenant in that header, the variant is the second tenant, and a
further variant omits the header entirely, where the route may fall back to a
default nobody meant.

The control is that same header carrying a tenant identifier that certainly does
not exist -- an action of this specification and not a reading borrowed from
somewhere else, because every action of a Test hangs off one replay run and a
Receipt from another run is another run's evidence. It must fail differently
from the second tenant's answer; where it does not, the reading is measuring a
naming oracle and stops. The Test names body_differs on the second-tenant arm
against the caller's own, and body_equals between the two baseline sends.
Section 2's refusal is an agent-filed edge beside this Test and is not one of
its actions.

## 5. Difference the bodies, not the statuses

Run `compare-responses` over the two stored Artifacts with
`mcp__rk2__run_skill_script`, whose `first` and `second` are the baseline and
the variant, and cite what it returns. close_offline_tool_run files that run's
output as its own Artifact; this section reads what the Test already settled and
grades nothing of its own. A differing assertion reads the response
body digest alone, so a volatile header changes nothing about it; an identifier
the route stamps inside the BODY is the real hazard, and where one is present,
difference a path that does not carry it.

A status of 200 is not the finding. The body has to carry records, counts or
identifiers belonging to the second tenant and absent from the caller's own
answer, and the report quotes the smallest thing that shows it. An empty list
for the second tenant refutes nothing on its own: it is both the answer of a
route that scoped correctly and the answer of a tenant with no records, and the
difference is not visible from here.

## 6. Propose the claim, and say what would refute it

Propose the claim with `mcp__rk2__propose_finding`. The Hypothesis is
`authorization.tenant_isolation` on the route. It is supported when a variant
returned another tenant's records as the Test asserted, the baseline pair was
invariant, and the never-issued tenant was refused. It is refuted when no
variant produced a body differing from the caller's own tenant's answer,
whether it was answered identically or refused outright, which the lane still
records under the kind the specification named. Anything else is inconclusive.

Stop at the first variant whose body carries the second tenant's records
against this Test's own control, the never-issued tenant identifier sent under
the same leased credential. Proving it twice adds
nothing, and every extra request puts another tenant's data in our evidence.

This section carries a proposal and closes no Test of its own, so it grades
nothing.

## 7. Read only, one tenant sideways, and what is not sent

Effects are read_only and every arm is a read. This Playbook does not write
into a second tenant, does not walk a tenant identifier space, and does not
read further once one variant has answered. One tenant sideways is the whole
claim.

Two readings are named here and performed nowhere. The duplicated tenant header
-- the same header name carrying the caller's own tenant and then the second
tenant in one request, so that the component which authorises reads one
occurrence and the component which queries reads the other -- is blocked by the
tool schema rather than by policy: the headers argument is an object, a JSON
object holds one value per name, and there is no repeated form, no array form
and no argv anywhere in the contract. It is dropped from section 4 rather than
approximated, and the query-string reading that looks interchangeable with it
belongs to `request-parsing`.

Taking a workload credential the Program did not lease is refused -- from a
metadata service, a build log, a container filesystem or an exposed document.
The finding in that case is that the document was reachable at all, which is
re-filed as what was actually observed and routed to the Playbook that owns it.
The adjacency is the reason this refusal is written down rather than assumed:
the request that reads a metadata index shape is one path segment away from the
credentials path.

This section performs nothing and grades nothing.

5 of 7 steps cannot be graded.
