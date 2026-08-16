---
description: An internal metrics route served twice from one source, both verifying the same workload token, one of them returning whichever project a header names and the other refusing a header that disagrees with the project the token was issued in.
bb:kind: own_pair
bb:classes: ["authorization.tenant_isolation"]
bb:subject: /internal/metrics
bb:facts: ["header_parameter", "tenant_boundary", "unknown_auth_endpoint"]
bb:identities: ["alpha-runner", "beta-runner"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# The token says which workload; the header says which project

`GET /internal/tokens` hands out two workload tokens, one for project `alpha`
and one for `beta`, the same two on both variants. `GET /internal/metrics` is the
subject: `Authorization: Bearer <token>` proves the caller and `X-Project`
selects whose metrics come back.

* **vulnerable** selects the project the header names. `alpha`'s token with
  `X-Project: beta` returns `beta`'s rows.
* **secure** compares the two. A header that disagrees with the token is `403`,
  an absent header means the token's own project, and two headers in one request
  are `400`.

## Both tenants are ours

That is the precondition the class needs and the reason the Playbook fires only
where a Program holds identities in at least two tenants. With one tenant there
is nothing to name in the header that is not already the caller's, and a run
would be guessing project identifiers -- which is a naming oracle, not access.

Here both projects are the engagement's, so the second tenant's rows are
verifiable from the second tenant's own token, which is what turns a plausible
body into a claim.

## The bodies differ, the statuses do not

`alpha` has 41 builds and two queued; `beta` has 7 and one. Both come back
`200`. A run that reads the status line learns nothing on this pair, and a
report has to name the rows it saw and say which tenant they belong to.

## The duplicated header

`X-Project: alpha, beta` is what a repeated header looks like once the client
library folds it. The vulnerable variant takes the last value, which is the
ordinary parsing bug behind this class; the secure one refuses the request. It
is a second variant for the same class rather than a second class.

## The control

No token, or a token this fixture did not issue: `401` on both variants. Without
it, a body full of `beta`'s rows would be indistinguishable from a route that
serves everybody, which is `authorization.function_access` and a different pair.

## What is not here

No writes. The Playbook's effects are `read_only` and a fixture that accepted a
write into the second tenant would be teaching a run to make one.

No exposed credential to harvest. Finding a token in a metadata service or a
build log is `information_disclosure.artifact_exposure`, and it is the input to
a different reading rather than to this one.

## Ground truth

* **vulnerable** holds `authorization.tenant_isolation`. `alpha`'s token with
  `X-Project: beta` returns `beta`'s runner, build count and queue.
* **secure** holds nothing this catalogue declares. That request is `403`, and
  `beta`'s rows are only reachable with `beta`'s token.
