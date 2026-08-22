---
description: Ask whether the target delivers its session where page script can hold it rather than in a cookie the browser keeps closed, by reading how the credential arrives and replaying the script-readable half of it on its own.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.client_storage"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "web_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 against a new client-storage leaf added by ticket 52; v1 had no page on this topic, so nothing is attached rather than a placeholder.
bb:evidence: [{"to_status": "refuted", "role": "control", "kind": "header_policy_observed", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "credential_effect", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "credential_effect", "polarity": "supports", "min_count": 1}]
---

# Where the session is kept decides who else can hold it

A cookie marked `HttpOnly` is a credential the page's own script cannot read. A
token handed to the page in a response body is a credential the page's own script
must read, which means every script the page loads can read it too -- the
analytics bundle, the tag manager, the dependency that changed owner last month,
and anything a markup defect puts in the document.

The question is not where the value ended up. It is where the target put it.

## 1. Establish the session the way the target intends

Read the subject route as the Task's own Identity. The run acts as whichever
Identity the Task was opened under -- the step does not choose it and there is no
argument for it -- so a Task opened under no Identity is the wrong Task for this
reading and is returned rather than worked around. Store the whole exchange: the
request that authenticated, every `Set-Cookie` it produced, and the response
body.

That is the control and it is a `credential_effect`: the session, held as the
target hands it out, reaches the route. Without it, a later failure is equally
well explained by a route that never worked.

`stable_session` is the baseline. One session across every step below, because a
reading that re-authenticated between the steps is comparing two sessions.

## 2. Read where the value was put

Two places, and they are not exclusive.

* **Cookies.** For each one the login set, record `HttpOnly`, `Secure`,
  `SameSite`, `Domain` and `Path`. A `header_policy_observed`, and the header text
  goes in the observation rather than a summary of it.
* **The response body.** A token, a bearer, a session identifier, a signed blob,
  an API key -- anything the page would have to read to use. Record which field,
  and record that it is the same value the cookie carries where it is.

A target that sets an `HttpOnly` cookie and *also* returns the same value in the
body has published it. The cookie's flag is doing nothing that the body does not
undo.

## 3. Replay the script-readable half alone

Send the subject route again with the body-borne value as the only credential --
in the `Authorization` header, or in whatever header the page's own requests use
-- and with no cookie at all.

That is the variant, and it is the reading. If the route answers with the same
authenticated content, then the value the target handed to script is a working
credential on its own, and it does not matter what the cookie's flags said.

Run `compare-responses` over this answer, the step 1 answer and an anonymous
answer to the same route. Three responses, because a route that answers the same
thing to everyone has been misread as leaking.

## 4. Say what this reading did not see

This harness has no action that reads Web Storage. There is no probe for
`localStorage`, no probe for `sessionStorage`, and adding one would be adding an
expression evaluated in the page for a question the exchange above already
answers.

So the claim is about delivery and about effect: the target put a working
credential where script can hold it. A reading that wants to assert the value is
*in* `localStorage` rather than in a closure, a variable or a memory-held store
has not seen that, and reports `inconclusive` for that part rather than asserting
it. Say so in the observation. The difference matters to a remediation and it
does not matter to the claim.

## 5. State the claim, and state what would refute it

The Hypothesis is `information_disclosure.client_storage` on the route. It is
supported when the value the target delivered to page script authenticates on its
own, against a control showing the session works when held the intended way. It
is refuted when the session travels only in a cookie the page cannot read and no
body-borne value authenticates.

Two neighbours, both close.

* A cookie whose `Domain` or `Path` reaches further than the application is
  `session_handling.cookie_scope`. That is a cookie exposed to the wrong origin;
  this is a credential exposed to script at the right one.
* A response carrying fields beyond what the caller is entitled to is
  `information_disclosure.excess_field`. A token belonging to the caller is not an
  excess field -- it is their own session, delivered somewhere it should not have
  been.

## 6. Read the credential; do not spend it

This Playbook's effects are `read_only`. Every request it sends is a `GET` the
Identity was entitled to make, and the credential it replays is the tester's own.

It does not lift a value belonging to another Identity, does not put the value
anywhere it was not already, does not log out to see what survives -- that is
`session_handling.lifetime` and a different Playbook -- and does not write the
value into a report unredacted. What is cited is the field it arrived in and the
Receipt it arrived on.
