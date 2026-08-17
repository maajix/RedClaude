---
description: Ask whether a route's failures describe the process that had them, by sending two arms whose values violate a parameter's type in two different ways beside one value the route's own rule rejects, and differencing the two failures against each other and against a baseline that was itself invariant.
bb:category: information_disclosure
bb:outputs: ["information_disclosure.error_detail"]
bb:triggers_all: ["authenticated_endpoint", "quantity_valued_parameter", "read_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's exceptional-conditions page against the error_detail leaf of the ticket 18 vocabulary; the v1 page carried no attachments, and its fuzzing lists and its overlong-input advice are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "error_detail", "polarity": "supports", "min_count": 1}]
---

# Ask what the route says when it is surprised

A route that has decided what its inputs may be answers the same short sentence
to everything else. A route that has not decided lets the failure happen further
in, and whatever caught it says where it was: a file, a line, a class, a query, a
version, a host name.

The subject is an authenticated read endpoint carrying a parameter that takes a
quantity. The question is whether a value outside what the route expected
produces a description of the process rather than a description of the input, and
the whole reading is six requests.

## 1. Name the parameter and its two rules

Read the parameter from the state view. Then say two things about it, from the
route's own behaviour rather than from a guess:

* what type it takes -- a count, a page size, an amount, an offset
* what the route's own rule about it is -- a maximum, a minimum, a precision

Both matter, because the reading needs a value that breaks the type and a value
that breaks only the rule, and the second one is the control.

Complete this step with the endpoint, the parameter, its type and its rule.

## 2. Establish the baseline, twice

Send the request under the leased Identity through `mcp__rk2__http_request` with
`identity_slot` set, with the parameter carrying an ordinary value the route
accepts. Then send it again, unchanged.

Where the subject takes no session at all, send both without `identity_slot` and
say so in the record. Nothing in this reading is about who asked -- the arms
differ in one parameter value and the claim is about what the route says when it
is surprised -- so a route that answers everybody is a route this reading can
still difference. What it may not do is mix the two: every request in every step
below carries the same standing as the baseline did.

Two identical requests, because everything after this compares failures against
each other and against this. A route that carries a request id, a timestamp or a
trace header in every answer is not byte-stable, and the comparison has to know
that before it reads two failures as different.

## 3. Send the value the route's own rule rejects

One request, with a value of the right type that the rule from step 1 refuses: a
count above the maximum, a page below the first, an amount with too many decimal
places.

Then send it again. Two identical requests, because this failure is the control
and a control that varies between sends is not one.

This is the harmless failure, and it is what the rest of the reading is measured
against. A route that answers it with a short sentence naming the rule is a route
that has decided what its inputs may be -- and the question is whether it decided
for values the rule never anticipated too.

## 4. Send the two arms

Two more requests. Both carry values that are not of the parameter's type at all,
and they are different from each other:

* a short word, `all`
* a different short word, `none`

Short and ordinary, both of them. The variable under test is that the value is
not a number; nothing else about it should be unusual, and an arm that is a
thousand characters long or full of metacharacters is testing a different route
than the one the Task names.

Interleave with the baseline. Hold everything else constant.

## 5. Difference the stored bytes

Run `compare-responses` over the two arms, then over one arm and the
rule-rejected control. Cite what the script returns.

Arm against arm is the differential that matters: two failures for two values
that are wrong in the same way, and if they differ, the route is quoting
something about each attempt rather than answering a decision it made in advance.

Arm against control says how far the difference goes. A route whose type failure
looks nothing like its rule failure is a route where one of the two was handled
and the other escaped.

Then read what the arm actually said, and name in the observation which of these
is present -- this is the observation the claim rests on:

* a source path, a line number or a function name
* an exception class or a stack frame
* a query, a statement fragment or a schema name
* a framework version, a build string, a host name, a container id
* an internal URL, an internal service name or a private address

A failure that quotes only the caller's own value carries none of those.

## 6. State the claim, and state what would refute it

The Hypothesis is `information_disclosure.error_detail` on the endpoint. It is
supported when the two arms differ from each other, the two baseline requests
were invariant, the rule-rejected control was invariant across its two sends, and
at least one arm carried something from the list in step 5. It is refuted when
the two arms are invariant against each other against a stable baseline -- the
route decided in advance, and every value that is not a quantity gets the same
sentence.

Anything else is inconclusive: an unstable baseline, a route behind a gateway
that rewrites every 5xx into the same page, a parameter the route ignores
entirely.

Two neighbours are close.

* Where the extra text is a field the route always returns and the contract never
  declared, rather than something a failure produced, the class is
  `information_disclosure.undeclared_field` and the Playbook is
  `information-disclosure`.
* Where the extra text is a key, a token or a password, the class is
  `information_disclosure.credential_material` and the Playbook is `secrets`,
  whatever produced it.

Cite the Artifacts and the difference the script returned. Quote the internal
detail in the observation, because that quotation is the finding -- and quote
only enough of it to identify what leaked.

## 7. The ceiling

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends six requests to one endpoint, and the widest value in any of them is a
four-letter word.

It does not fuzz. It does not send a wordlist, a long string, a deeply nested
document, a value chosen to consume memory, a value chosen to take a long time,
or a request rate that a route would notice. It does not repeat a failing request
to see whether the failure changes under load. The property is that a surprised
route describes itself, and one surprise already showed that.

Where the route answers every unexpected value with the same gateway page, the
verdict is `inconclusive` and it routes to an operator. A reading that responds
by making the input stranger is looking for a way to hurt the route, and this
Playbook does not have one.
