---
description: Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by reading the policy the target serves rather than by putting the page in a frame.
bb:category: transport
bb:outputs: ["transport.header_policy"]
bb:triggers_all: ["form_request", "state_changing_method", "web_surface"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's clickjacking and CORS/XSSI pages, against the header-policy leaf of the ticket 18 vocabulary; both v1 texts are attached as maintainer references and both describe headers step 1 and step 2 read.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "header_policy_observed", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "header_policy_observed", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "header_policy_observed", "polarity": "supports", "min_count": 1}]
bb:references: ["clickjacking.md", "cors-xssi.md"]
---

# Ask what the target tells the browser, not what the browser would do

A page that writes is driven by a browser, and two of the rules deciding whether
another site can drive it are rules the target states and the browser enforces:
who may frame this document, and who may read what it answers. Both are headers.
Neither is visible in a response body, and neither is settled by loading the page
and looking at it.

The subject is a form that writes. The question is what the target says about it
to a browser that arrived from somewhere else.

## 1. Read the document the form lives on

`GET` the page that carries the form, as whichever Identity the Task was opened
under -- the step does not choose it and there is no argument for it -- and record
the response headers whole. Three of them answer the framing question and they do not
agree with each other by construction:

* `Content-Security-Policy`, and specifically a `frame-ancestors` directive
* `X-Frame-Options`, which is older and which a browser ignores where
  `frame-ancestors` is present
* `Set-Cookie`, and the `SameSite` attribute on the cookie the form's session
  rides in

That is a `header_policy_observed` and it is the reading. Cite the header text
rather than a summary of it.

Complete this step with: the three headers as served, and which of them the
target sent at all.

## 2. Ask the same page as a stranger

Send the same request again carrying an `Origin` header that names a host the
target does not control, and record what changed. What is being read is
`Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` and `Vary`:
whether the target hands a foreign origin permission to read the answer, and
whether it hands it that permission with the session attached.

`Access-Control-Allow-Origin: *` with no credentials is not this claim. That is a
target publishing something it means to publish. The pairing that matters is an
origin reflected back beside `Access-Control-Allow-Credentials: true`.

## 3. Difference the two, and keep the default

Run `compare-responses` over the step 1 headers and the step 2 headers. A policy
header that appears only when a foreign `Origin` was sent, or that changes value
with it, is a different fact from one that is always there, and the two read
identically unless both were taken.

Step 1 is the control for exactly that reason. Without it, a header observed once
cannot be told from a header the request provoked.

## 4. Say which layer produced the answer

Three layers can produce the same-looking refusal and only one of them is this
claim.

* The **browser** may refuse regardless. A `SameSite=Lax` session cookie is not
  sent on a cross-site form POST at all, so a missing `frame-ancestors` on a page
  whose session cookie is `SameSite=Strict` is a weaker claim than the same
  absence beside `SameSite=None`. Say which was served.
* The **server** may check the request itself, with an `Origin` allowlist applied
  in the application or a token in the form. That is `session_handling.csrf` and
  belongs to the Playbook holding that class. This one is about the policy the
  target publishes, not about whether a forged request would be accepted.
* The **proxy** produces nothing here, and that is a measurement rather than an
  assumption. Response headers cross this proxy unmodified, and the one request
  header it adds is the `Authorization` the runtime injected and therefore knows
  about, which is why `transport.header_policy` is the one class in its family an
  agent-lane Receipt can settle. TLS version, cipher, certificate identity and request
  framing are the same family and are not readable from these Receipts at all.

## 5. State the claim, and state what would refute it

The Hypothesis is `transport.header_policy` on the page. It is supported when the
served headers leave a state-changing document framable by any origin, or
readable with credentials by an origin the target does not control, against a
control taken without a foreign `Origin`. It is refuted when the served policy
names the origins it permits and the foreign one is not among them.

A page nobody gains anything by framing is not refuted. It is a claim with no
impact, and that is a separate judgement recorded separately. An absent header on
a document that changes nothing is likewise not this subject: the trigger is a
write.

## 6. Read the headers; frame nothing

This Playbook's effects are `read_only` and its whole evidence is response
headers. It does not build a framing page, does not host anything, does not ask a
browser to load the target inside a document at an origin the tester controls,
and does not submit the form. A page that had to be framed somewhere to be read
has been served from somewhere, and that somewhere is a third party this Program
has no scope over.

One extra request per reading, the same route with a foreign `Origin`, and it is
a `GET`. Nothing here writes.
