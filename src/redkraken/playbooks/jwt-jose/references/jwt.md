# JWT and JOSE: the header edits, and why decoding one is not a finding

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The one class this Playbook claims

`authorization.token_scope`: a token was honoured beyond what it was issued for
-- another audience, another scope, another lifetime, another key. The evidence
is a request that succeeded with a token whose own claims say it should not
have, against a control that shows the endpoint refusing a broken signature.

## Not that: "the token is readable"

A JWT payload is base64url, not encryption. Decoding it and reporting the claims
inside is not a finding, and the claims are the Program's credential material,
so the run should read them and not quote them.

Where the token was *found* is the neighbouring class, and which leaf depends on
where: a log or a client-side bundle the target serves is
`information_disclosure.artifact_exposure`, and a response that hands a caller a
token it was not entitled to is `information_disclosure.excess_field`. Neither is
the fact that a payload can be decoded.

## The header edits, and what each one needs

Every one of these is sent once, and every one needs material the target itself
published:

* **`alg: none`** (and its case variants). Strip the signature, keep the claims.
  Needs nothing. Almost never works, costs one request, and is the fastest
  refutation available.
* **`alg` changed from `RS256` to `HS256`**, signed with the target's own public
  key as the HMAC secret. Needs the public key, from the target's JWKS endpoint
  or its certificate. If the key came from anywhere else, the reading is not
  about this target.
* **`kid` pointed at another key the target serves**, including a path or an
  injection into whatever `kid` is used to look up. The evidence is a token the
  target signed for itself being accepted for something else.
* **`jku` or `x5u` pointed at a URL under our control**, which is only in scope
  where the Program permits an outbound callback, and where it does, it is a
  `callback_interaction` and belongs to a blind-validation reading rather than
  this one.

## The claims that carry scope

`aud`, `iss`, `scope`/`scp`, `azp`, `exp`, `nbf`, and any tenant claim the
application defines. The Playbook's whole point is that verification libraries
check the signature and leave these to the application. Two readings answer it:
the same genuine token sent to a second audience, and the same genuine token
sent to a route that needs a scope it does not carry.

## Not that: an expired token that is refused

A token past `exp` being rejected is the system working. The finding is a token
past `exp` being *accepted*, which needs a slot's token to have aged naturally
-- so it is an opportunistic reading, not one to manufacture by waiting.

## The rule about which tokens may be used

Tokens leased through slots, minted for us. A token lifted from a log, a mobile
bundle belonging to another user, or an exposed endpoint is somebody's live
credential; finding it is the report, using it is not part of the reading.
