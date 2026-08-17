# Host header attacks: the observation is kept, the rewrite is refused

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The authority is not one field, and the page was a list of the others: `Host`,
`X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Server`, `X-Original-URL`,
`X-Rewrite-URL`, `Forwarded`, and an absolute-form request line for the hops that
still honour one. Two hops read different ones, and the application builds
absolute links from whichever it trusts.

Then the yields, which are why the page existed. Password reset poisoning: request
a reset with a rewritten authority, and the link in the message the application
sends points at the rewriting host, so whoever clicks it hands over their token.
Web cache poisoning: get an absolute link built from an attacker-chosen authority
stored under the real URL. Routing: reach an internal virtual host by naming it,
or reach a service that has no route from the internet because the front end
resolved the authority the caller supplied.

## Why the Playbook refuses the arms

**Reset poisoning sends a message to a person.** The arm only means anything if
the application actually delivers, and delivery is to a real address with a real
token in it. That is a live account, somebody's inbox, and a credential in flight.
There is no `read_only` version and no undo.

**Cache poisoning is served to the next caller.** Same refusal the response
splitting note beside this one makes, for the same reason: the entry outlives the
request that created it and is handed to people who are not part of this
engagement.

**Routing by rewritten authority is leaving scope.** Getting a front end to
forward on the strength of an authority the reading supplied causes a request to
arrive somewhere the Program did not grant. It does not become acceptable because
the request left from inside the target. This harness resolves a name once,
decides about the addresses it answered with, and dials the one it decided about;
an arm whose purpose is to reach a different destination defeats that by design.

## What the Playbook kept

Step 6, and it is an observation rather than an arm. Deployments that read one
parameter name from two carriers usually read the authority from several as well,
so the reading is already looking at responses that would show it: a `Location`
header, a link in a body, a redirect target. Say whether a caller-supplied
authority appears in one of them, from what was already returned, and put it in
the Task note.

That is not nothing. "This route builds absolute links from the authority the
caller sent" is the fact that decides whether the reset-poisoning question is
worth an operator's time, and it costs no request at all.

## Why it is an observation and not this Playbook's class

The Playbook under this name asks whether two components resolve one parameter
name to two values. An authority read from two headers is the same shape one layer
over, and it would be tempting to fold in -- but the evidence is different. The
parameter question is settled inside one exchange, by a receipt and an artefact
the reading already holds. The authority question is only settled by what the
application does with the link afterwards, which is a message, a cache entry or a
forwarded request, and all three are refused above.

So the fixture that grades this Playbook serves `X-Forwarded-Host` on both
variants and ignores it on both. A reading that reports the authority as the
finding has reported something neither half of that target does, which is the
control doing its job.
