---
description: Ask whether a state-changing page tells the browser, in the headers a browser enforces, that another origin may neither frame it nor read what it answers, by differencing the policy the target serves against a sibling route of the same deployment and against the same request carrying a foreign Origin.
bb:category: transport
bb:outputs: ["transport.header_policy"]
bb:triggers_all: ["form_request", "state_changing_method", "web_surface"]
bb:skills: ["browser-evidence", "compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 52 as the v2 replacement for v1's clickjacking and CORS/XSSI pages, against the header-policy leaf of the ticket 18 vocabulary; rewritten for ticket 101 against the merged technique ledger, which carries four readings and one standing refusal for this slug. One frontmatter key moved -- browser-evidence joins bb:skills, because the cookie attribute set in section 5 is readable in the browser lane and on no other. bb:evidence is unchanged -- header_policy_observed is agent-filed on all three legs, so the refuted leg already asks for the kind its own role asks for on supported. Repaired in review, where every Test in the file was found to settle on a formality no assertion could read; the file now proposes no Test, opens no Finding, and treats its bar's variant and control as Observation roles. Repaired again in round 3, where section 3 listed six Origin values under a stated budget of four -- the literal null is out, since a hosted document produces it, and the budget is the five left.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "header_policy_observed", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "header_policy_observed", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "header_policy_observed", "polarity": "supports", "min_count": 1}]
bb:references: ["clickjacking.md", "cors-xssi.md"]
---

# Ask what the target tells the browser, not what the browser would do

A page that writes is driven by a browser, and two of the rules deciding whether another
site can drive it are rules the target states and the browser enforces: who may frame this
document, and who may read what it answers. Both are headers, neither is visible in a
response body, and neither is settled by loading the page. Six response header names are
stripped from the agent view on every path and none is a framing or a CORS header, so the
served policy is inside the transcript.

## 1. How a reading here is settled, and what it may not assert

**This Playbook produces a lead and never a Finding**, and that is a property of where the
answer lives rather than of the reading. No assertion kind names a header: the set is
exactly status_equals, status_differs, body_equals and body_differs, and the two body
kinds read the stored response body digest alone. The whole subject here is a header, so
an assertion can say only that the exchange had the shape the reading expected, which is
equally true of a page that publishes no policy at all and of a page that publishes a good
one. A Test built on that settles supported on a formality, so no step below proposes one
and no step below opens a Finding.

Every arm is an ordinary `mcp__rk2__http_request`. The policy travels as
header_policy_observed Observations filed WITH the proposal through
`mcp__rk2__submit_mission_result`, which promote_proposal writes, because an edge cannot
be added to a claim once it is past proposed and nothing here comes after the proposal to
add one from. The bar this Playbook declares is a header_policy_observed in the role
variant and one in the role control, and those are Observation roles rather than Test
action roles: no step below performs a baseline, variant or control action.

The control in every reading here is the baseline sent a second time, unchanged. That arm
establishes that the route's body is stable: a CSRF token, a request id or a rotating
panel moves it on its own, and such a route answers no comparison below. Where the pair
does not hold, record the verdict inconclusive with the reason "response body not stable"
rather than narrowing the comparison after the answers were seen -- a halt that is a
reading run out, reported through the Task's own record.

## 2. Difference the write page against a sibling of the same deployment

The baseline is the document carrying the state-changing form, as whichever Identity the
Task was opened under; the step does not choose it and there is no argument for it. The
variant is a second route of the same deployment the application itself frames -- a login
step, an embedded widget, a printable view. The control is the baseline repeated.

Read that the repeat and the baseline agree and that the sibling was served at all. Both
are preconditions of the comparison rather than results of it, and neither is asserted,
because nothing settles here. The policy difference between the two is not something any
assertion can state, which is why this Playbook reads on header_policy_observed: file one
edge per Receipt naming `Content-Security-Policy`, specifically its `frame-ancestors`
directive, and `X-Frame-Options`, which a browser ignores where `frame-ancestors` is
present. Cite the header text, not a summary of it.

The comparison is between two policies rather than one policy read alone.
`X-Frame-Options: DENY` beside a CSP whose `frame-ancestors` is `*` is a framable page,
and a grep for the header name reads it as protected. Where the write document and the
sibling publish the same policy, nothing is missing on the write page in particular, and
that is the refutation. Where the sibling sits on a host the scope document does not
clearly admit, do not send it: ask through `mcp__rk2__park_for_human` for this Task to
be parked, naming it in `task_label` and scope_ambiguous in `question_code`, and let a
person decide which sibling is in scope.

## 3. Ask the same page as a stranger

The Origin arms are ordinary sends through `mcp__rk2__http_request`, whose headers
argument carries each one, and none of them is an action of anything. The baseline is the
authenticated route with no Origin header at all, so a header that is always there can be
told from one the request provoked. The variants are that same route carrying an Origin
naming a host the target does not control, then the suffix neighbour, the prefix neighbour
and the scheme downgrade of a trusted subdomain, one send each; the literal null is out,
because it arrives from a hosted document and section 8 refuses hosting one. The control is
the no-Origin baseline repeated, and a second control is worth its send: an Origin of
sixteen random characters at a domain nobody owns.

Read whether each Origin arm's status and body equal the baseline's. Equality means the
target answered a stranger exactly as it answered nobody, so no origin check gated the
answer, and the grant itself is read out of the transcript: `Access-Control-Allow-Origin`,
`Access-Control-Allow-Credentials` and `Vary`, filed as header_policy_observed per arm.
The pairing that matters is an origin reflected back beside
`Access-Control-Allow-Credentials: true`; if the random-label arm is echoed too, the
target reflects any origin and no allowlist was consulted. A target that answers a foreign
Origin with a different status is one that does check, and that is the refutation,
recorded as one. `Access-Control-Allow-Origin: *` with no credentials is a target
publishing something it means to publish, and is a refutation rather than a weak claim.

The ceiling travels with the claim: `Access-Control-Allow-Origin` describes what a browser
would let a script read, so what is shown is the permission granted and never a read a
page achieved. Five Origin values go out and no sixth -- the four foreign spellings and the
random-label control -- and that halt is a reading run out, reported through the Task.

## 4. Ask who wrote the policy

Where a parameter demonstrably reaches a response-header value -- a report-uri, a nonce
source read out of the request -- the subject changes from what the target published to
who wrote it. The baseline is the route with that parameter carrying an ordinary value,
the variant is the same route with a directive-shaped value, and the control is the route
with the parameter absent entirely, which separates a directive generated per request from
a static one. The planted value travels in the query string, because that is the parameter
the application copies.

An equal body is not the reading on its own. A value the application dropped leaves the
document unmoved too, which is exactly what the control with the parameter absent
produces, so body equality cannot separate the two. What carries this reading is the
served header text: file the header_policy_observed edge for all three arms and read the
variant's directive against the control's. The claim holds only where the variant's header
carries the planted value and the control's does not, with a reflected_input edge naming
where it landed. Where the value came back in the document instead, that is markup
injection and belongs to the Playbook holding that class.

Plant an inert directive that changes the header text without widening what a browser
would permit, and stop there; a source-list entry naming an origin is the shape to refuse,
because widening the subject's own protection is a change to the subject. Record that a
widened policy was never tested for honour.

## 5. Read what a missing header costs, out of the browser's own jar

`Set-Cookie` is one of the six response headers stripped from the agent view on every
path, so `SameSite` is readable in the browser lane and nowhere else.

Run `mcp__rk2__browse`: navigate to an unauthenticated page of the origin, read the cookie
inventory, complete the login, and read it again. A third read on an unrelated path of the
same origin is the control arm, and identical attributes there confirm the reading is
about the cookie rather than about the page that happened to be loaded. The registry
strips cookie values before the Artifact exists, so what is stored is the name, domain,
path, httpOnly, secure, sameSite and prefix, and nothing spendable. The writer is
promote_proposal again, filing the inventory as a content_match Observation over the
browse run, which is a tool run and satisfies that kind's provenance directly.

A browse step is never a Test action -- the action kinds a Test may hold are requests
alone -- and no step here opens a Finding in any case; what this one does is modify the
cost of the claim section 2 reads, and it is cited there. Where the plan cannot finish the
login inside its step ceiling, report the framing reading without the cost modifier and
say plainly that SameSite was not read: "not recorded" and `SameSite=None` must not look
the same in a report.

## 6. Say which layer produced the answer

This section is a lead: it names no verb and files no result, so the system cannot grade
it. The **browser** may refuse regardless -- a `SameSite=Lax` session cookie is not sent
on a cross-site form POST at all, so a missing `frame-ancestors` beside a
`SameSite=Strict` session is the weaker claim. The **server** may check the request
itself, with an `Origin` allowlist or a form token; that is `session_handling.csrf` and
belongs to the Playbook holding that class. The **proxy** produces nothing, and that is a
measurement: response headers cross it unmodified, which is why `transport.header_policy`
is the one class in its family an agent-lane Receipt can read at all.

## 7. State the lead, and state what would refute it

The Hypothesis is `transport.header_policy` on the page, and it stays proposed. This
Playbook opens no Finding from its own readings: rk2_finding_refusal admits one only on
the settling transition close_test_replay writes, that transition comes from a Test's own
assertions, and no assertion here can read a header. The evidence supports the claim when
the served headers leave a state-changing document framable by any origin, or readable
with credentials by an origin the target does not control, against a control taken without
a foreign Origin. It refutes it when the served policy names the origins it permits and
the foreign one is not among them. Each Observation is filed with the polarity it carries,
and an operator decides what the lead is worth. A page nobody gains anything by framing is
not refuted; it is a claim with no impact, and that is a separate judgement recorded
separately.

## 8. Read the headers; frame nothing

One refusal covers six techniques, and the reason travels because DoubleClickjacking is in
a recent Top 10 and will be re-proposed. The clickjacking demo, prefilled-form and
multistep redress, frame-buster neutralisation by a sandbox attribute, DoubleClickjacking,
reverse tabnabbing through an unrestricted opener and the credentialless-iframe upgrade of
a self-XSS each need a document served from an origin that is not the target, and this
harness hosts none; DoubleClickjacking needs multi-window control besides, and the
credentialless upgrade needs model-authored JavaScript. This is a standing decision and
not a capability gap somebody may close, and a refusal is not a step the system grades.
The reachable residue of all six is the header reading in section 2, and that is no loss:
the claim was always about the header. Nothing here builds a framing page or submits the
form.

8 of 8 steps cannot be graded.
