---
description: Ask whether two components that both act on one request resolve the same parameter name to different values, by sending the route's own request once with the name in one carrier and once with it in two, and comparing what the application said it accepted against what it actually produced.
bb:category: injection
bb:outputs: ["injection.parameter_precedence"]
bb:triggers_all: ["repeated_parameter_name", "state_changing_method", "web_surface"]
bb:skills: ["compare-responses"]
bb:risk: constrained
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's request-parsing pack against a new parameter_precedence leaf added by ticket 56; the pack's four pages are attached as maintainer references, and its response-splitting payloads, its host-header rewrites and its filter-evasion catalogue are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-crlf-injection-and-response-splitting.md", "http-attacks-host-header.md", "parameter-pollution.md", "waf-bypasses.md"]
---

# Ask whether the thing that checked and the thing that acted read the same value

One request arrives and two components read it. A validator decides whether the
request is allowed; a builder, a renderer or a store decides what it produces.
When one name is present in two carriers -- the query string and the body -- and
the two components resolve it differently, the check passes on one value and the
work is done with the other. Nothing was smuggled and no byte was malformed. The
request was ambiguous, and the ambiguity was resolved twice.

The subject is a write on a browser-facing application whose recon pass found one
name accepted in two places. The whole reading is four requests.

## 1. Establish what one value does

Send the route's own request once, with the name in one carrier only and a value
the application accepts. Nothing about this arm is unusual: it is the request the
application expects, and it is the baseline everything below is measured against.

Record three things from the answer, because step 4 compares them:

* the status, and any `Location` the answer set
* what the answer says it accepted -- the value echoed in a receipt, a field, a
  filename, a confirmation
* what the answer or the object it points at actually is -- its content type, its
  shape, the identifier it was given

If the answer does not carry both of the last two, this reading has nothing to
difference and the verdict is `inconclusive`. A route that confirms nothing and
produces nothing observable cannot be shown to have read a value twice.

Complete this step with the three, and with the identifier of anything the
request created. Everything created here is named in the finding so an operator
can undo it.

## 2. Send the name twice

One request. The same request as step 1, plus the same name in the second carrier
with a second value, and the second value is one the application refused or does
not list -- a format outside its own list, a view it does not offer, a mode it
does not document.

One arm, one changed thing. The variable under test is the second occurrence of
the name, and everything else -- method, content type, the other parameters, the
absence of a session -- is exactly what step 1 sent. An arm that also changed the
first value cannot say which occurrence either component read.

The value in the second carrier must be one the application would refuse if it
were the only one there. That is what makes the arm mean something: if the check
had seen it, the request would not have been accepted.

## 3. Send the control

One request, and this is what keeps the reading honest: the same duplication
applied to a name the route does not act on, or the same duplication sent to a
neighbouring route on the same application.

If the control comes back exactly as step 1's baseline did, the deployment does
not refuse duplicated names as such, and a difference on the arm is about this
route's two readers. If the control comes back `400`, the deployment rejects the
shape everywhere, the arm proved nothing about precedence, and the reading stops
with `inconclusive`.

Then send step 1's request once more, unchanged. Four requests, and the fourth
says the baseline is where it was left rather than something the arm moved.

## 4. Difference what was accepted against what was produced

Run `compare-responses` over the arm and the baseline, and cite what it returns.
Then set the two halves of the arm's own answer beside each other:

* what the answer says was accepted -- the echoed value, the receipt field, the
  filename
* what was actually produced -- the content type of the artefact, its shape, the
  columns or fields it carries

The claim is these two disagreeing inside one exchange. A receipt naming the
value the check allowed, beside an artefact built from the value the check never
saw, is one component's answer and another component's work, and the caller chose
both.

Quote the request line and the two carriers verbatim, including which occurrence
was in the query string and which was in the body. A parameter-precedence finding
that does not say which carrier won is not reproducible, and which one wins is
the first thing whoever fixes it needs.

## 5. State the claim, and state what would refute it

The Hypothesis is `injection.parameter_precedence` on the subject. It is supported
when the arm was accepted, the answer names one value, the thing it produced was
built from the other, and the control showed the deployment does not reject
duplicated names as such. It is refuted when the arm is invariant against the
baseline -- one value won everywhere, or the request was rejected -- which is what
an application that resolves a name once looks like.

Anything else is inconclusive: a route whose answer shows neither what it accepted
nor what it built, a deployment that answers `400` to every duplicated name, a
second value the application turns out to accept anyway.

Three neighbours are close.

* Where one hop refuses a path and another serves it because they normalise the
  spelling differently, the class is `authorization.edge_rule` and the Playbook is
  `deployment`. That is two hops disagreeing about a path; this is two components
  disagreeing about a name.
* Where the value that wins reaches an interpreter and is executed rather than
  merely preferred, the class is whichever `injection` leaf names that interpreter
  and the reading belongs to its Playbook.
* Where the caller is not entitled to the route at all, the class is
  `authorization.function_access`. Precedence is about a caller who was entitled
  to ask, getting work done from a value that was never checked.

Cite the Artifacts, the difference the script returned, and the identifier of
anything the arm created.

## 6. The authority half, which is an observation and not a claim

Deployments that read one name from two carriers usually read the authority from
several as well: `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`.
Whether the application builds absolute links from what the caller sent is worth
noting from the answers already collected -- a `Location` header, a link in a
body, a redirect target.

It is worth noting and it is not worth an arm. Rewriting the authority a hop
routes on is how a request arrives somewhere the Program did not grant, which is
the refusal `http-attacks-host-header.md` makes at length. Read what the
route already returned, say whether a caller-supplied authority appears in it, and
leave it in the Task note for whoever holds a scope grant that covers the
question.

## 7. The ceiling

This Playbook is `constrained`, holds no session, and sends four requests to one
route on a surface nothing else is touching.

It admits that it writes. Its subject is a state-changing route and re-sending
that route's own request does whatever that route does, so `mutates_object` is the
floor rather than a formality: every object the reading creates is named in the
finding with its identifier, and the reading does not send the arm a second time
to see whether it works twice.

It does not carry a payload. The second value is a value the application refused,
not a string with a quote, a bracket, a newline or a template delimiter in it.
Both halves of a `%0d%0a` are refused outright: a value that splits a response
puts a header of the reading's choosing in front of somebody else's document, and
`http-attacks-crlf-injection-and-response-splitting.md` records why that has no
`read_only` version and no bounded blast radius.

It does not rewrite the authority. It sends no `Host` other than the one the Task
scoped, no `X-Forwarded-Host`, and no absolute-form request line. Step 6 is an
observation of what the route already returned and it is deliberately not an arm.

It does not evade a filter. Where a front end refuses the arm, that is the answer,
and the reading records the refusal rather than re-encoding the value, changing
its case, splitting it across carriers a third way or trying it as a
multipart part. A filter defeated is not a defect found, and the catalogue of ways
to defeat one is the thing `waf-bypasses.md` under this Playbook exists to
refuse.

It does not enumerate names. One name, the one the recon pass recorded in two
carriers, and one arm against it. Sending every parameter twice is a fuzz run
against a write route, and its blast radius is however many objects the route
creates.

Where one value wins everywhere, the verdict is `refuted` and the reading is over.
Where the answer shows nothing about what it built, the verdict is `inconclusive`
and it says so in those words.
