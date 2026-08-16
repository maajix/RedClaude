# Clickjacking: the header is the claim, the frame is the demo

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A recipe with an HTML file at the end of it. Load the target in an `iframe`,
overlay a decoy with `opacity: 0`, position the real button under the fake one,
screenshot the result, attach the HTML to the report. Plus a list of the header
values that stop it and a note on `X-Frame-Options: ALLOW-FROM` being dead.

The recipe is correct. It is also the part that does not survive contact with
this harness, and the reason is not squeamishness.

## Why the demo page cannot be built here

A framing proof-of-concept has to be served from an origin that is not the
target. Somebody must host it. Every option is a problem this Program has not
authorised:

* a domain the tester owns, which is a third party the scope never named
* a paste or gist service, which publishes the target's name and a working
  attack to an indexed public URL
* `localhost`, which the target's `frame-ancestors` will not treat as a
  different site in the way the report implies

So the harness reads the policy instead. That loses the screenshot and keeps the
claim, because the claim was always about the header.

## The half the Playbook uses

Four headers, read off an ordinary `GET`:

```
Content-Security-Policy: frame-ancestors 'self'    <- the modern rule
X-Frame-Options: DENY | SAMEORIGIN                 <- the older one
Set-Cookie: ...; SameSite=Lax|Strict|None          <- whether the session travels
Access-Control-Allow-Origin / -Credentials         <- whether the answer is readable
```

Two facts about how they interact, both of which change the reading:

* Where `frame-ancestors` is present, a browser ignores `X-Frame-Options`
  entirely. A page with `X-Frame-Options: DENY` and a CSP whose `frame-ancestors`
  is `*` is framable.
* `ALLOW-FROM` is not implemented by any current browser. A page relying on it is
  a page with no framing policy, and it reads as protected to anyone grepping for
  the header name.

## The half that stays out, and why

* **Hosting the frame.** Above.
* **Drag-and-drop, cursor-jacking, double-click timing and the rest of the UI
  redress family.** These need a served page as well, and each of them is a claim
  about a user's attention rather than about the target's configuration.
* **`SameSite` as the finding.** A cookie that will not travel cross-site is a
  reason the attack fails, not a defect. It belongs in the reading as the thing
  that decides how much the missing header costs.
* **Whether the forged request would succeed.** That is
  `session_handling.csrf` and a different Playbook holds it. This one stops at
  what the target published.

## The trap in the whole technique

Most pages are framable and almost none of it matters. A marketing page, a
documentation route, a login form with no session yet: framing them buys
nothing, and a report that lists every route with no `frame-ancestors` is a
scanner's output with a person's name on it.

The Playbook triggers on a state-changing form for exactly this reason. The
question is not "can this be framed" but "is there a single click here that does
something to the account", and if there is not, the header's absence is a
hardening note.
