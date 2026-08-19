---
description: A sign-in route that refuses an unregistered address and a wrong password differently on one variant and identically on the other.
bb:kind: own_pair
bb:classes: ["information_disclosure.identifier_oracle"]
bb:subject: /session
bb:facts: ["api_surface", "email_valued_parameter", "json_request", "state_changing_method", "unauthenticated_endpoint"]
bb:identities: []
bb:provenance: Written for ticket 79 from the account-enumeration pattern that recurs across public disclosures; ground truth taken from the ticket 18 class description, and the corpus held no fixture for this class before it.
---

# A refusal that answers a question nobody asked

`POST /session` takes `{"email": ..., "password": ...}`. A correct pair is
answered `200`. The two variants differ only in how they refuse:

* **vulnerable** answers `404` and *no account exists for that email address*
  when the address is not registered, and `401` and *the email address or the
  password is wrong* when it is registered and the password is not. One request
  per address decides membership.
* **secure** answers `401` and the same sentence either way.

## Why this fixture is here

Ticket 79 asked which techniques in public disclosures the corpus cannot grade.
`information_disclosure.identifier_oracle` had a Playbook and no fixture, and
the reason it kept appearing in disclosures is that nothing here is broken in
the usual sense: the route authenticates correctly, refuses correctly, and leaks
the register anyway.

The difference is in the shape of the answer rather than in its timing. A timing
oracle would grade the same class and would grade it unreliably, because two
repeats of one reading under different machine load would disagree. What varies
here is the status and the sentence, so a reading that got it right once gets it
right every time, which is what a fixture owes a grade.

## What the ground truth claims

`information_disclosure.identifier_oracle` on the vulnerable variant, and
nothing else. Both variants check the password before answering `200`, so no
credential is accepted that should not be and
`authentication.credential_verification` is not made true here. The register is
two fixed rows and the passwords are compared, not returned, so a claim of
`information_disclosure.error_detail` against either variant is a false
positive: neither refusal carries anything from inside the process.
