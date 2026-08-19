---
description: A password-recovery route that builds the reset link's authority from the request's own Host header on one variant and from its configured origin on the other.
bb:kind: own_pair
bb:classes: ["authentication.recovery_flow"]
bb:subject: /account/recover
bb:facts: ["api_surface", "email_valued_parameter", "header_parameter", "json_request", "state_changing_method", "unauthenticated_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 79 from the host-header account-takeover pattern that recurs across public disclosures; ground truth taken from the ticket 18 class description, and the corpus held no fixture for this class before it.
---

# A reset link addressed by the caller

`POST /account/recover` takes `{"email": "..."}` and answers `202` with the
message that would have been mailed. There is no mail transport here, so the
delivery preview in the answer is the fixture's stand-in for the mailbox: it is
returned identically by both variants, and a claim about the preview itself is a
claim about the fixture rather than about the target.

The link inside it is the whole difference:

* **vulnerable** builds the link's authority from the request's `Host` header,
  so a caller that asks with a `Host` of its own choosing is answered with a
  reset link pointing at that authority, carrying a live token.
* **secure** builds it from `ORIGIN` and never reads `Host` at all.

## Why this fixture is here

Ticket 79 asked which techniques in public disclosures the corpus cannot grade.
`authentication.recovery_flow` was a class with a Playbook and no fixture, and
the recurring real-world shape of it is not a weak token: it is a strong token
delivered to an authority the attacker named. A fixture that varied token
entropy would grade a different claim, and would grade it against a generator
rather than against a flow.

The reflection is one step removed from the request that caused it, which is the
part a reading has to carry: what comes back is not the header echoed, it is a
credential addressed by it. Both variants return a live token in the delivery
preview, so a Playbook that reports `information_disclosure.credential_material`
here has reported the mailbox -- the same claim would hold against the secure
variant, where the flow is sound.

## What the ground truth claims

`authentication.recovery_flow` on the vulnerable variant, and nothing else. The
route is unauthenticated, so there is no session to fix and no privilege to
cross. An address that is not registered is answered exactly as a registered one
is -- same status, same body shape -- so
`information_disclosure.identifier_oracle` is not merely absent from the ground
truth: nothing on this route could make it true. Tokens are issued from a fixed
list because what is under test is where the link points, not how the token was
drawn.
