# The playground technique, and the line it sits on

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 text described

A vendor-hosted OAuth debugging console -- the Google OAuth 2.0 Playground is
the well known one -- lets a person paste a client identifier, run an
authorisation flow interactively, and receive the code or token in the console.
The v1 note used it to show that a client identifier shipped to the browser is
not a secret, and that whatever an application's client is trusted for can be
exercised outside that application.

## What survives into v2, and what does not

What survives is the *observation*: a public client identifier plus a
registered redirect target is enough to drive a flow. That is why the Playbook
above records the client identifier and the redirect target as surface, and why
"the client identifier is exposed" is not itself a finding.

What does not survive is the tool. A third-party console is a service the
Program did not authorise: driving the engagement's flows through somebody
else's infrastructure puts the target's codes, tokens and account identifiers
into a system nobody agreed to, and the transcript of that flow is outside the
evidence store the engagement controls.

## The v2 equivalent

Everything the console demonstrated can be done with the two things this
Playbook already has:

* a browser under `browser-evidence`, driving the flow at the application's own
  authorisation URL with the parameters the application itself ships
* a second clean browser profile as the counterfactual

That keeps every request between us, the target, and the identity provider the
target chose -- which is the same set of parties the honest flow already
involves.

## The redirect target is the constraint

Any flow this Playbook drives ends at a redirect target the application
registered. That is what keeps the code inside the target's own origin, and it
is also why the interesting variant is delivering a callback to a *second
browser*, not delivering it to a *second host*: the second host is the
`redirect_uri` question, and its reading has to establish that the authorisation
server accepts an unregistered target before anything follows from it.

## What to do with a genuinely public client that grants too much

If the application's own client identifier authorises scopes far beyond what the
application uses, record it, and read what those scopes reach *on our own leased
account*. The finding is what the scope grants, evidenced once. It is not a
finding that a scope string is long.
