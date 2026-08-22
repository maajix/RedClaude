---
description: Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate.
bb:category: injection
bb:outputs: ["injection.template"]
bb:triggers_all: ["authenticated_endpoint", "reflected_parameter", "tech_template"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's ssti page against the template leaf of the ticket 18 vocabulary; the v1 text is attached as a maintainer reference and every sandbox escape and context read in it is refused by step 6.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "reflected_input", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "reflected_input", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "reflected_input", "polarity": "supports", "min_count": 1}]
bb:references: ["ssti.md"]
---

# Ask whether the value became the template

A template engine takes source and takes values. A route that passes the caller's
value in as a value is doing what it was built to do. A route that pastes the
value into the source -- because the greeting is built with string formatting,
because the subject line is assembled before rendering, because a customer
supplies their own snippet -- has handed the caller the template language.

The subject is an authenticated endpoint whose parameter a recon pass saw
reflected, on an Application running a template engine. The question is whether
the engine evaluated it.

## 1. Name the parameter, the reflection and the engine

Read from the state view which parameter is reflected and where it lands. A value
reflected into an attribute, into a script block or into text are three different
sinks, and the one that matters here is the one rendered by the server.

Name the engine the surface fact came from. Delimiters are not shared: `{{ }}`
for Jinja and Twig, `${ }` for Freemarker and JSP expression language, `<%= %>`
for ERB, `#{ }` for others again. A probe in the wrong delimiter is a probe for a
string.

Complete this step with the endpoint, the parameter, the sink, and the engine.

## 2. Send the probe and its twin

Two requests through `mcp__rk2__http_request`, both as whichever Identity the
Task was opened under -- the step does not choose it and there is no argument for
it, which is also what keeps the pair comparable. The parameter carries:

* the variant: an arithmetic expression in the engine's delimiters whose result
  is a different string from the expression itself
* the control: the same bytes with the closing delimiter one character short, so
  the engine has nothing to evaluate and every other byte is identical

The arithmetic matters for one reason and it is worth stating plainly: the result
must not appear anywhere in the request. If the probe's output looks like its
input, a response containing it is equally well explained by reflection -- and
reflection is by construction what this surface already does.

The one-character-shorter twin matters for the same reason in the other
direction. It is the same length, the same characters, the same everything a
filter or a length check would see, and it is not a template expression. A
control that omits the payload compares two different response sizes through two
different code paths.

The repeat policy is two rounds of the pair, four requests, with a different
arithmetic result in the second round. The second round is not a retry, it is
the check that the number in the response is this reading's number: a page that
happens to contain `49` will contain it again, and a template that evaluated
`7*7` will return `64` when asked for `8*8`. A result that does not track the
expression it was asked for is not evaluation.

## 3. Read the response, not the page

Read the bytes the server sent. Not what a browser renders, not what a
JavaScript framework shows.

This is the step the class gets wrong. An Angular or Vue application will happily
evaluate the same expression in the browser and display the same result, and that
is a real finding with a different class, a different severity and a different
fix. If the evaluated result is in the server's response body, the server
evaluated it. If the raw body contains the expression and only the rendered page
shows the result, this reading has the wrong Playbook.

## 4. Difference the two

Run `compare-responses` over the variant and the control. Cite what the script
returns.

Three outcomes:

* The variant contains the evaluated result and the control contains its own
  bytes verbatim. The engine evaluated the variant.
* Both contain their own bytes verbatim. The value is a value.
* Both are absent from the response. The reflection the surface fact recorded is
  not on this path, and the reading found no sink.

## 5. If the engine rejected it, say so as its own outcome

A template engine handed a malformed expression frequently raises, and the route
returns a 500 or an engine-shaped error. That is not the supported verdict and it
is not nothing: an engine error naming a template line is strong evidence that
the value reached the source, and the control -- which is the malformed one by
design -- is the arm most likely to produce it.

Record it and report `inconclusive` with the error cited. An engine that errored
on the control and evaluated the variant is the supported case; an engine that
errored on both has told you it parsed both, and the reading needs a probe the
engine accepts before it can claim evaluation.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.template` on the endpoint. It is supported when the
variant's evaluated result is in the server's response body and the control's
bytes came back verbatim. It is refuted when both came back verbatim -- the value
reached the sink and was passed as a value.

Two neighbours are close.

* Where the value came back verbatim into markup and a browser acted on it, the
  class is `injection.markup` and the Playbook holding it reads that. Verbatim
  reflection is this Playbook's refutation and that one's precondition.
* Where the evaluation happened in the browser rather than on the server, the
  class is `injection.client_channel` and the Playbook is `browser-messaging`.

Cite both Artifacts and the difference the script returned.

## 7. One multiplication, and nothing that escapes the sandbox

This Playbook is `read_only`.

It evaluates arithmetic. It does not walk an object graph to reach a runtime, does
not call a class loader, does not read the template context, does not print the
application's configuration or its secret key, does not read a file through a
template loader, and does not run a command.

The refusal is not only about permission. Those chains are long,
version-specific, and they half-work: a partially applied escape leaves the
template context in a state nobody can describe, in a process serving other
people. A multiplication evaluates and leaves nothing behind.

Impact belongs in the report, argued from the fact that the caller writes
template source. It does not need to be demonstrated to be true.
