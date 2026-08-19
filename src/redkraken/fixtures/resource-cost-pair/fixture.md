---
description: A batch route served twice from one source, both variants refusing an origin after twenty requests and only one of them refusing a single request that asks for unbounded work.
bb:kind: own_pair
bb:classes: ["rate_limiting.resource_cost"]
bb:subject: /api/v1/render
bb:facts: ["api_surface", "json_request", "state_changing_method", "unauthenticated_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 79 from the batched-operation abuse pattern that recurs across public disclosures of GraphQL and JSON batch APIs; ground truth taken from the ticket 18 class description, and the corpus held no fixture for this class before it.
---

# A limit that counts requests while the work is somewhere else

`POST /api/v1/render` takes `{"operations": [{"kind": "render"}, ...]}` and
answers with what it completed and what that cost. Both variants refuse an
origin after twenty requests, with the same `429` and the same `Retry-After`.
One request is where they differ:

* **vulnerable** performs whatever the batch names. A single request carrying
  two hundred operations is answered `200` with `"completed": 200`, spending
  fifty times what the operator's limit was written to allow.
* **secure** refuses a batch of more than twenty-five operations with `429`,
  naming the ceiling and what was asked.

## Why this fixture is here

Ticket 79 asked which techniques in public disclosures the corpus cannot grade.
`rate_limiting.resource_cost` had a Playbook and no fixture, and the reason the
technique keeps working in the field is exactly the shape here: the rate limit
is present, correct, and counting the wrong noun. A reading that establishes
"there is a limit and it engages" has established nothing about this class.

The batch is JSON rather than GraphQL because what the class is about is the
ratio between one request and the work it commands, and a query language would
put a parser between the reading and that ratio without changing the claim.

## What makes the class `resource_cost` and not a rate-limiting gap

Both variants enforce the same per-origin request limit, so a run that counts
requests measures the two sides as identical: twenty answered, then `429` from
both. The only reading that separates them is one that varies the size of a
single request. `rate_limiting.per_origin` is therefore not merely absent from
the ground truth -- the limit that class is about is present and working on the
vulnerable variant.

## What the ground truth claims

`rate_limiting.resource_cost` on the vulnerable variant, and nothing else. No
work is actually performed for an operation: the answer reports what the request
was allowed to ask for, at a fixed cost per operation, so two repeats of one
reading agree under any machine load and no run can read its own slowness as the
finding. Nothing in the batch is interpreted, so `injection.object_graph` and
`injection.query_operator` have nothing here to be true of.
