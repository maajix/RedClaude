---
description: An assertion consumer served twice from one source, both verifying the same signature over the same region, one of them reading the subject from a sibling key the signature never covered and the other refusing any document that states a subject twice.
bb:kind: own_pair
bb:classes: ["authentication.federation_trust"]
bb:subject: /sso/acs
bb:facts: ["state_changing_method", "tech_saml"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 50 against the ticket 18 class description, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# Two readers, one document, and the key that overrides the signed one

`GET /sso/assertion` mints the one document this fixture will ever sign:

```json
{"signed": {"subject": "alice@fixture.invalid", "issuer": "fixture-idp",
            "audience": "fixture-sp"}, "signature": "..."}
```

`POST /sso/acs` consumes it and issues a session. `GET /whoami` says whose.

Both variants verify the same HMAC over the `signed` object and answer `401` to
a signature that does not check out. The difference is where the subject comes
from afterwards:

* **vulnerable** prefers a top-level `subject` key when the document carries
  one. The signature covered `signed`; the session is minted for the copy
  outside it.
* **secure** reads the subject from the verified region only, and refuses a
  document that states one outside it with `400`.

## Why the wrapping is a sibling key rather than an XML tree

The class is the disagreement between the verified region and the region the
application acts on. `Object` wrappers, relocated assertions and comment-split
text nodes are all ways of producing that disagreement in one particular
serialisation; none of them is the defect.

Modelling it as one JSON key keeps the pair readable and keeps the fixture from
grading a run on whether it can drive an XML canonicaliser. The Playbook's
`saml.md` reference carries the tree-shaped variants for a maintainer working a
real target.

## Nothing here can be forged

The signing key never leaves the fixture and `GET /sso/assertion` mints for one
subject: its own. A run's only material is that document, and every variant is
that document with one edit -- which is exactly the constraint the Playbook puts
on a real engagement, where an assertion for anybody else is somebody else's
credential.

## The reading that settles it

`GET /whoami` after the callback. A `200` from `POST /sso/acs` says a session
exists; it does not say whose, and on this pair the difference between the
variants is entirely in that name.

## What is not here

Replay: the same unmodified document is accepted every time by both variants,
which makes that reading useless as a discriminator here. It is
`business_logic.replay` and a different class.

No external entities, no metadata, no certificate hygiene. Each of those is a
real finding in this space and none of them is this class.

## Ground truth

* **vulnerable** holds `authentication.federation_trust`. The minted document
  with `"subject": "mallory@fixture.invalid"` added beside it returns a session,
  and `GET /whoami` answers with that name.
* **secure** holds nothing this catalogue declares. The same document is `400`,
  and the unmodified one logs in as `alice@fixture.invalid`.
