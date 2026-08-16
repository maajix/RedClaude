---
description: Ask whether a document something else embeds writes a value it never fetched into its own DOM as markup, by planting one registered probe in the page and showing that no request left the browser between the planting and the verdict.
bb:category: injection
bb:outputs: ["injection.client_channel"]
bb:triggers_all: ["embedded_document", "read_method", "web_surface"]
bb:skills: ["browser-evidence"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's dom-vulnerabilities and prototype-pollution pages, against a new client-channel leaf added by ticket 52; both v1 texts are attached as maintainer references and both describe sources step 3 names and cannot drive.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "reflected_input", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "reflected_input", "polarity": "supports", "min_count": 1}]
bb:references: ["dom-vulnerabilities.md", "prototype-pollution.md"]
---

# The value the server never saw

Some of what a page renders never crossed the network. A fragment, a message from
the document that framed this one, a value the page kept from an earlier screen,
a key an attacker put on an object every other object inherits from -- all of
them are inputs, none of them appears in a Receipt, and a reading built on
differencing requests is blind to every one.

The subject is a document something else embeds, which is what makes it a
document handed values it did not fetch. The question is whether one of those
values becomes markup.

## 1. Say which document is embedded, and by what

The Surface says something embeds this route. Name both ends: the parent that
loads it and this document's own URL. A widget, a preview pane, an editor frame
and a payment field are all this shape, and each of them is a document whose
caller is another document rather than a person.

Complete this step with the two routes and what the embedding is for.

## 2. Load it once, planting nothing

Plan a mission that loads this document directly, top level, and ends with
`probe markup_injection`.

Directly rather than framed, because the probe evaluates in the document it was
run against and a probe run in a parent cannot see into a child. The reading is
about what this document does with what it is given, and loading it alone is how
that becomes observable.

This is the control, and it is a `response_invariant`: the probe's marker is not
already in the page. Without it, a document that happened to carry `rk-probe`
would grade as injected on every reading.

## 3. Say which channel can be driven, and which cannot

Three of this class's sources exist and this harness can drive exactly one of
them. Say which was used, in the observation, rather than leaving a reader to
assume.

* A **field the page reads without a round trip** -- a live preview, a
  search-as-you-type, a composer that renders as it is typed -- can be driven.
  `inject` types the probe's own payload into it and nothing is submitted.
* A **fragment** cannot. `navigate` refuses a URL carrying one, by design and not
  by omission: a fragment never leaves the browser, so a Receipt could not
  describe the URL that was loaded, and a mission whose plan and whose Receipts
  disagree is a mission that proves nothing.
* A **cross-document message** cannot. No action here sends one, because sending
  one means holding a second origin, and this Program has scope over one.

A reading whose only candidate source is one of the last two ends here and is
reported `inconclusive`. A listener read out of source is a listener; it is not a
value that arrived.

## 4. Plant the probe, and send nothing

Plan the second mission: `navigate` to the document, `inject` the probe into the
field, `wait_for` whatever the page renders it into, then `probe
markup_injection` and `capture_dom`.

No `click`. That is the whole design of the step. `inject`, `wait_for`,
`capture_dom` and `probe` all declare `reaches_network` false, so a run whose
Receipts hold one `navigate` and nothing else is a run in which the value never
crossed the door. That Receipt list is the evidence that separates this class
from `injection.markup`: not an argument that the server did not see the value,
but the absence of the request that would have carried it.

`inject` types the probe's own payload and the plan cannot choose it. The thing
planted and the thing looked for are one registry row, so a verdict cannot be
arranged by picking a marker the page was going to contain.

## 5. Read the verdict, and say what it means

* `reflected` -- the parser built an `rk-probe` element out of a value that never
  reached the server. That is the claim.
* `escaped` -- the value reached the sink and something encoded it. That is the
  refutation, and it is the stronger one: it shows the path works and the
  encoding held.
* `absent` -- the value did not reach the document at all. Inconclusive, not
  refuted: this reading did not find the sink.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.client_channel` on the document. It is supported
when a mission that planted the registered probe returns `reflected` and its
Receipts show no request carrying the value, against a control mission that
returned `absent`. It is refuted when the same mission returns `escaped`.

Two neighbours are close, and the Receipt list tells all three apart.

* Where the value did cross the network and came back in the response, the class
  is `injection.markup` and belongs to the Playbook holding it. The trigger there
  is a parameter a recon pass saw the server reflect; the trigger here is a
  document with no such parameter.
* Where the page built a request path out of the value rather than rendering it,
  the class is `injection.client_path`.

Cite the Tool run: plan digest, result digest, the step that carried the probe,
the captured document's Artifact hash, and the Receipts the run produced.

## 7. One marker, one document, no second origin

This Playbook's effects are `read_only`. It plants one inert custom element with
no script, no attribute a browser acts on and no content, and it reads one
verdict.

It does not frame the target anywhere, does not host a parent document, does not
send a message from an origin the tester controls, and does not write a value the
page keeps for a later visitor. A prototype-pollution gadget is read out of the
source rather than triggered, and the reason is that a planted key on a shared
ancestor persists for the whole document and changes how every later
step in the mission behaves, so a run that pollutes is a run whose remaining
observations describe the pollution.

A mission that hit its ceiling or was refused at the proxy is inconclusive and is
reported as inconclusive.
