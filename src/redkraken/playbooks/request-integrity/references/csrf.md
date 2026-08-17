# CSRF: the class survives, the proof does not, and neither lives here

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Cross-site request forgery, end to end. Find a state-changing route. Remove the
token and resend. Send somebody else's token. Send an empty token, a token of the
right length made of the wrong characters, the token from a different session.
Change the method -- `POST` to `GET`, or `POST` with a method override header.
Change the content type to one a form can produce, so no preflight is required.
Read `SameSite` off the session cookie and decide whether the browser would have
attached it at all. Then check the referrer defences: send no `Referer`, send one
from an origin that contains the trusted host as a substring. Finish by hosting a
form that submits itself, loading it in a browser holding the victim's session,
and showing the state that changed.

## Why the Playbook refuses all of it

**The proof is a write on somebody's account.** Every arm on that list ends with a
request that changes state, and the finishing move changes it on a session that
is not the reading's. `request-integrity` is `read_only`. A Playbook that sent
half the arms would be doing the risky part of the work and drawing a weaker
conclusion than one that sent none.

**The class already has a home, and one class has one home.** 018 named
`session_handling.csrf` -- "a state-changing request is accepted without proof of
same-origin intent" -- and `realtime` outputs it, graded by `websocket-csrf-pair`.
The binding between Playbooks and targets is computed from declared classes, so a
second Playbook outputting this one would be graded on that fixture too, and two
results answering one question say nothing about which document was right.

**The hosted form is somebody else's browser.** Same refusal the CORS note beside
this one makes for the same reason: the claim is about what the application
accepts, and a demonstration that drives a browser has run software this
engagement does not own to show a thing the response already said.

## What the Playbook kept

The distinction, which is the part of the page worth keeping and the part readings
get wrong. Reading and writing across origins are two defects with two mechanisms.
A response readable by another origin is a disclosure and its evidence is a pair
of response headers. A request accepted from another origin is an integrity defect
and its evidence is a state change. They frequently appear together, they are
frequently reported as one thing, and the fix for each does nothing for the other.

Step 5 of the Playbook names `session_handling.csrf` as a neighbour for exactly
this reason: a reading that has found a permissive read policy has not found
forgery, and saying so is part of the finding rather than a caveat on it.

## What is worth carrying if a write route is the subject

Two facts from the page, both cheap and both observations rather than tests.

`SameSite` on the session cookie is readable from the response that set it, and
it decides whether a browser would have attached the session to a cross-site
request at all. `Lax` is the modern default and it makes most of the v1 arm list
inapplicable to `GET`-shaped navigation only.

The content type the route accepts is readable from the application's own
documentation of itself or from one ordinary request. A route that accepts only
`application/json` requires a preflight, and a preflight is a permission the
application has to have granted for the forged write to arrive at all.

Neither is a claim. Both belong in a Task note for whoever picks up the write
side, and neither is worth a request of its own.
