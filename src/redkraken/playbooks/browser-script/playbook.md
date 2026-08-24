---
description: Ask whether a parameter a recon pass saw reflected reaches the browser as markup the parser builds an element from, by planting one registered probe through a scripted browser mission and reading the verdict the probe returns.
bb:category: injection
bb:outputs: ["injection.markup"]
bb:triggers_all: ["query_parameter", "reflected_parameter", "web_surface"]
bb:skills: ["browser-evidence"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's xss and dangling-markup pages, against the markup leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and the second is where step 4's contexts come from.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "reflected_input", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "reflected_input", "polarity": "supports", "min_count": 1}]
bb:references: ["dangling-markup.md", "xss.md"]
---

# Ask the parser, not the response body

A parameter that comes back in a response is a parameter that came back. Whether
it came back as markup is a question about what a parser built, and grep on a
response body cannot answer it: the same bytes are an element on one page and
text on another, and which one happened is decided by the context they landed in
and by the escaping applied on the way.

So the reading is a browser mission, and the only thing it plants is a registered
probe.

Both missions below are started through `mcp__rk2__browse`, whose one argument is
`steps`. Follow `browser-evidence` for the plan, the wait after every step that
changes the page, and the rule that everything the run brought back is the
target's.

## 1. Fix which reflection is being tested

The Surface says a parameter was seen reflected. Name it: the route, the
parameter, and the place in the document its value appeared. A reading that
plants a marker without knowing where the value lands has one bit of evidence and
no explanation of it.

Complete this step with the route, the parameter name and the observed reflection
site.

## 2. Load the page once with nothing planted

Plan a mission whose first `navigate` loads the route with the parameter carrying
an ordinary value, and whose last step is `probe markup_injection`.

This is the control, and it is a `response_invariant`: it says the probe's own
marker is not already in the document. Without it, a page that happened to
contain `rk-probe` would grade as injected on every reading, and nothing later
would notice.

## 3. Plant the probe's payload, once

Plan the second mission: `navigate` to the route, `inject` the probe into the
field the parameter is bound to, `click` what submits it, `wait_for` the result
container, then `probe markup_injection`.

`inject` types the probe's own payload. The plan does not supply it and cannot
choose it. That is the point of the registry: the thing planted and the thing
looked for are one row written by one owner, so a verdict cannot be arranged by
picking a marker that was going to be there anyway.

`capture_dom` after the probe stores the serialised document as an Artifact, and
the observation cites it. A verdict with no document beside it is a number.

## 4. Read the verdict, and say what it means

The probe answers with one of three words and each of them is a different
finding.

* `reflected` -- the parser built an `rk-probe` element. The value reached the
  document as markup. That is the claim.
* `escaped` -- the marker is in the document as text. The value reached the
  document and something encoded it. That is the refutation, and it is a stronger
  refutation than a missing marker because it shows the path works and the
  encoding held.
* `absent` -- the marker is not in the document at all. The value did not arrive.
  That is not a refutation of the class; it is a reading that did not reach the
  sink, and it is inconclusive.

`rk-probe` is a custom element with no script, no attribute a browser acts on and
no content. Planting it changes what the document is without changing what it
does, which is what makes the same payload safe against a live target and
decisive against a fixture.

## 5. Say what was not shown

An element is not execution and this Playbook does not claim execution. What has
been shown is that caller-controlled bytes became markup in the target's origin.
What has not been shown is that a script tag would have run, that a Content
Security Policy would have permitted it, or that a session would have been
readable from there.

Two neighbours are close enough to name.

* Where the value lands inside an attribute that was never closed, the reading is
  the one v1 called dangling markup: no script executes and the rest of the
  document is still consumed by whatever the value opened. That is the same
  class, read at a different depth -- the first half is a value that reached the
  parser, the second is what the parser then swallowed on its way to the next
  quote. Say which half the observation shows.
* Where the value never reaches the server at all -- a fragment, a message from
  another document, a value the page kept -- that is `injection.client_channel`
  and belongs to the Playbook holding it. The trigger here is a parameter a recon
  pass saw the server reflect.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.markup` on the parameter. It is supported when a
mission that planted the registered probe returns `reflected`, against a control
mission that returned `absent` on the same route. It is refuted when the same
mission returns `escaped`.

Cite the Tool run: its plan digest, its result digest, the step that carried the
probe and the Artifact hash of the captured document. A description of what the
page looked like is not evidence.

## 7. One marker, one origin, no payload

This Playbook's effects are `read_only`. It plants one inert element and reads
one verdict. It does not iterate an encoding list, does not send a payload that
executes, does not call out to a collector, and does not store anything in the
target that another user would load.

Every request the mission makes goes through the same door under the same scope
decision as a hand-written exchange, and each has its own Receipt. There is no
second egress. A mission that hit its ceiling or was refused at the proxy is
inconclusive and is reported as inconclusive.
