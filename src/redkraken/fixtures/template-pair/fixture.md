---
description: An authenticated preview route served twice from one source, one variant pasting the submitted text into the template's source before rendering and the other passing it in as a value, beside a draft counter that changes on every request and a quote route that reflects without rendering.
bb:kind: own_pair
bb:classes: ["injection.template"]
bb:subject: /preview
bb:facts: ["authenticated_endpoint", "reflected_parameter", "tech_template"]
bb:identities: ["alice"]
bb:provenance: Written for ticket 53 against the template class description from the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; the noisy counter and the reflecting quote route are the precision controls ticket 53 criterion 5 asks for.
---

# A value that became the source

`POST /preview` takes a body carrying `message` and returns the rendered
greeting. Both variants render, both reflect the submitted text into the answer,
and both use the same engine. The difference is which side of the engine the text
arrives on:

* **vulnerable** builds the template source by concatenation, so anything in the
  message that looks like an expression is an expression.
* **secure** renders a fixed source and passes the message in as a value, so the
  same characters are text.

The engine understands `{{ <name> }}` and `{{ <number>*<number> }}` and nothing
else. It is small deliberately: the class turns on whether a caller's bytes are
part of the source, not on which engine's delimiters they are written in.

## What the two arms do here

Against **vulnerable**, `{{7*7}}` renders as `49` -- a string that appears
nowhere in the request, which is what makes it evidence rather than a reflection.
`{{7*7}` is one character shorter at the closing delimiter, matches no
expression, and comes back verbatim.

Against **secure**, both come back verbatim, because the message is a value and
the source never contained it. The pair is invariant, which is this class's
refutation, and it is a refutation in the strongest available sense: the message
did reach the page, visibly, and was still not evaluated.

Both variants reflect. That is the whole difficulty of this class and the reason
the probe's output has to differ from its input.

## The two precision controls, on both variants

`POST /preview/live` returns a draft number that increases on every request, so a
reading that skipped its baseline has a route it can be wrong about.

`POST /preview/quote` puts the message back in the response and renders nothing
at all. It is the decoy for the reading that reports this class from a reflection:
the payload appears in the answer, unchanged, and no engine ever saw it.

## What the ground truth claims, and what it does not

`injection.template` on `/preview` of the vulnerable variant, and nothing else
anywhere.

The rendering happens in this process and the evaluated result is in the bytes
the server sends, so a reading that reports `injection.client_channel` here has
attributed server-side evaluation to a browser. The answer is JSON with no
script, no markup sink and no browser needed, so `injection.markup` is false
against every route. Nothing here reaches a query, a shell or a document parser,
and nothing is stored: the counter is the only state and it never reaches the
template.
