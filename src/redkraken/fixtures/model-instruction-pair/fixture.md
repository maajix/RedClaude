---
description: An assistant endpoint answering questions about a supplied document, served twice from one source, one variant pasting the document into the operator's own instructions and the other passing it as data, with wording that rotates on both.
bb:kind: own_pair
bb:classes: ["injection.model_instruction"]
bb:subject: /assistant
bb:facts: ["body_parameter", "tech_llm"]
bb:identities: []
bb:provenance: Written for ticket 49 against the class this ticket adds to the ticket 18 vocabulary, from what the class says rather than from any Playbook's steps; no upstream corpus.
---

# Text somebody else wrote, read as instructions

`POST /assistant` with `{"question": ..., "document": ...}` answers a question
about the document. The document is the untrusted half: in the case this class
is about, it was written by somebody other than the caller.

The variants differ in where it lands in the prompt:

* **vulnerable** pastes the document into the operator's own instructions, so
  the model cannot tell which half it wrote. A directive in the document is
  obeyed, and the reserved support code comes back in the answer.
* **secure** passes the document as data. The same directive is described --
  the answer says the document asked for something and that it will not -- and
  the code never appears.

## The wording rotates, on both variants

Two identical requests produce two different answers on either variant: the
opening and the summary sentence each advance per request. This is the property
the fixture exists to hold, and it is deliberately not noise around the edges of
the response but the response's whole visible shape.

A run that sends one request, compares it against one baseline, and reports the
difference will find a difference here every single time, on both halves of the
pair, and will be wrong about both. The only stable signal is whether
`RK-SUPPORT-7712` is present, and reaching it requires more than one sample of
each side.

The rotation is a counter and not a random draw, so a repeat is reproducible
from the same bytes -- the fixture is restarted per repeat and the sequence
starts again.

## The control channel

`X-Client-Locale` reaches neither half of the prompt, on either variant. A
directive planted there changes nothing. That is what a control plants into, and
a run whose control also produced the behaviour has learned that its
differencing was measuring something other than the injection.

## What the ground truth claims

`injection.model_instruction` on the vulnerable variant, and nothing else.

The reserved code is a string in the prompt, not a credential to anything; the
finding is that the boundary between instructions and data does not hold, and
the code is how a run can check it without arguing about prose. Nothing here
reaches SQL, a shell, a template or a parser, so the rest of the injection
family is not a gap in this file -- there is nothing that could make it true.
The route is anonymous and stores nothing, so `authorization.*`,
`session_handling.*` and `business_logic.replay` against this fixture are false
positives. The failure body is one fixed sentence, so
`information_disclosure.error_detail` is one too.

## The model is a function in app.py

It follows directives found in the trusted half of its prompt, describes ones
found in the untrusted half, and rotates its phrasing. That is all of it, and it
is all this class needs from a target: somewhere for the boundary to be, and
enough variance that a single comparison cannot settle anything.
