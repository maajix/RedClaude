---
description: Ask whether a machine-to-machine credential is confined to the tenant it was issued in, by sending one workload token to a route while naming a second tenant in the header that selects one.
bb:category: authorization
bb:outputs: ["authorization.tenant_isolation"]
bb:triggers_all: ["header_parameter", "tenant_boundary", "unknown_auth_endpoint"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 50 as the v2 replacement for v1's workload-identities pack, against the tenant-isolation leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
---

# The credential belongs to a workload; ask which tenant it can speak for

Service credentials -- a cluster service account, a cloud instance role, a
CI token, an internal service's mTLS identity -- are issued to a *workload*
inside a tenant: a project, a namespace, an organisation, an account. The token
proves the workload. Which tenant's data the request touches is usually decided
somewhere else: a header, a path segment, a field the caller fills in.

Where nothing compares the two, a credential that is entirely legitimate reads
another tenant. This Playbook fires where the Program holds identities in at
least two tenants, because the second tenant is what makes the reading a
comparison instead of a guess.

## 1. Get a workload credential the Program issued

Follow `use-identity`. The credential is leased through a slot like any other,
and for this class the slot holds a service credential rather than a user's: a
token the operator provisioned for the engagement, in a tenant the Program
names.

Never harvest one. A token scraped from an exposed metadata service, a build log
or a container is a credential nobody granted, and the finding there is that the
document was reachable -- `information_disclosure.artifact_exposure` -- not the
input to this one.

## 2. Establish both ends of the scale

Send one read to the route with the credential attached and the caller's own
tenant named. Store the answer.

Send the same read with the credential removed, and again with a credential of
the same shape that was never issued. Store those. The refusal is the control
and it is a `credential_effect`: the route authenticates. An unauthenticated
route that answers everybody the same way is not a tenant-isolation finding, it
is `authorization.function_access` and a different reading.

## 3. Name the second tenant, change nothing else

One variant per reading, each the stored request with a single substitution:

* the tenant header set to the second tenant the Program holds
* the tenant header set to a tenant identifier the target's own responses
  disclosed
* the header duplicated: our tenant first, the second tenant after
* the header omitted, where the route may fall back to a default

The identifiers come from the Program's own material or from what the target
told us. This Playbook does not enumerate tenant names, and a strange
identifier that produces a different error is a naming oracle, not access.

## 4. Difference the bodies, not the statuses

Run `compare-responses` over each variant and the two ends. A `200` is not the
finding. The finding is a `response_differential`: the body carries records,
counts or identifiers that belong to the second tenant and are absent from the
caller's own answer, and the same request without the credential is refused.

That needs bytes on both sides. Where a side's body is in the sealed wire view,
`compare-responses` has nothing to difference and says so, and the reading is
inconclusive: report it with both Receipt labels rather than differencing the two
status lines and calling the result a differential.

Where the second tenant is one the Program holds, verify from that side: read
the same resource as the second tenant's own Identity and check the record is
the one that came back. That is what turns a plausible body into a claim.

## 5. Propose the claim, and say what would refute it

The Hypothesis is `authorization.tenant_isolation` on the endpoint. It is
supported when a credential issued in one tenant returned another tenant's data,
against a control that shows the route refusing an unauthenticated caller. It is
refuted when every variant is answered exactly as the caller's own tenant is --
the header is ignored -- or when it is refused the way the missing credential is.

An empty list for the second tenant refutes nothing on its own. It is the answer
of a route that scoped correctly and the answer of a tenant with no records, and
the difference between those is not visible from here.

## 6. Read only, one tenant sideways

Effects are `read_only`. No variant writes into a tenant, and a write is how a
scoping question becomes damage to somebody's production data. The reading stops
at the first differential: proving it twice adds nothing, and every extra request
is another tenant's data in our evidence store.
