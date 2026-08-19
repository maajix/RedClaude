---
description: One unauthenticated API route served twice from one source, one variant answering every request that arrives and the other refusing with 429 after five, counted per origin because there is no caller to count.
bb:kind: own_pair
bb:classes: ["rate_limiting.per_origin"]
bb:subject: /api/v1/quotes
bb:facts: ["api_surface", "read_method", "unauthenticated_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 79 from the unauthenticated-endpoint abuse pattern that recurs across public disclosures; ground truth taken from the ticket 18 class description, and the corpus held no fixture for this class before it.
---

# A route nobody has to sign in to, and nobody counts

`GET /api/v1/quotes` returns two static rows to anyone who asks. There is no
session, no cookie and no header that changes the answer.

* **vulnerable** answers every request that arrives.
* **secure** answers five per origin per sixty seconds and then refuses with
  `429` and a `Retry-After` naming what is left of the window.

## Why this fixture is here

Ticket 79 asked which techniques in public disclosures the corpus cannot grade.
`rate_limiting.per_origin` had a Playbook and no fixture, and the corpus's only
rate-limiting fixture keys its counter on the session -- which means a Playbook
that can only read a limit off an authenticated sequence would have passed the
corpus while being unable to say anything about the surface where this class
actually bites: the routes with no session on them at all.

## What makes the class `per_origin` and not `per_identity`

There is no identity here to key a counter on. The route issues no session,
reads no cookie and answers a caller holding one exactly as it answers a caller
holding nothing, so the only counter that could exist is one on where the
requests came from, and in the secure variant that is the one that exists. The
per-identity fixture is the mirror of this: there, one caller's spending must
not change another caller's answers, and here there is no other caller to be
changed.

## What the ground truth claims

`rate_limiting.per_origin` on the vulnerable variant, and nothing else. The rows
are static and belong to nobody, so there is no object to own and no field to
withhold: `authorization.object_ownership` and
`information_disclosure.excess_field` are not gaps here, there is nothing on
this route that could make either true. Both variants answer `404` identically
for every other path and every other method, so the sequence a reading counts is
the only thing that differs. The allowance refills, which is what makes the
`Retry-After` true rather than decorative: a reading that spent it once can
spend it again a window later, and the secure variant is a rate limit rather
than a route that closed.
