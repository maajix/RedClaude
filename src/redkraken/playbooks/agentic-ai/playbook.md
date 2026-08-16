---
description: Ask whether text the caller supplies is read by a language model as instructions rather than as data, by asking one question twice with an instruction planted in the channel under test and once with it planted where the model cannot see it.
bb:category: injection
bb:outputs: ["injection.model_instruction"]
bb:triggers_all: ["tech_llm"]
bb:triggers_any: ["body_parameter", "query_parameter", "reflected_parameter"]
bb:skills: ["compare-responses", "handle-untrusted-content"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's agentic-ai pack; the class it outputs is new in this ticket, because no injection leaf in the ticket 18 vocabulary named a language model as the interpreter.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["llm.md"]
---

# Ask whether the model is reading your text as an instruction

The injection family splits by the interpreter, because the interpreter is what
decides the test. Here the interpreter is a language model, and it differs from
every other one in the family in a way that governs this whole Playbook: it is
not deterministic. The same input twice can produce two answers, so a difference
between two responses is not on its own evidence of anything.

That is what the control in step 3 is for, and it is the step this class of
report almost always skips.

## 1. Name the channel the text travels down

The subject is an endpoint on an application the recorded surface has identified
as using a language model. Read from the surface which parameter carries text
into it, and how far that text travels: a chat field is the direct channel, a
document the model summarises is an indirect one, and a field the application
stores and shows another user later is a stored one.

Name exactly one channel per run. A run that plants the same marker in three
fields cannot say which one the model read.

## 2. Ask a stable question, and ask it more than once

Before planting anything, send the application's own request with ordinary input
and no instruction in it, at least three times. Store every answer.

This is the baseline and it measures the model's own variance. If the three
answers already differ in the way step 5 would call a finding, this Playbook
cannot answer the question on this subject at this temperature: record that and
stop. It is a real result and it is a much better one than a claim built on a
difference the model would have produced anyway.

## 3. Establish the control: the same instruction, where the model cannot read it

Send the request again with the instruction placed in a field the pipeline does
not pass to the model -- a header the application ignores, a parameter the
surface records as unused, a part of the document the extractor drops.

The control should be invariant against the baseline. If it is not, the
difference in step 4 is not attributable to the channel, and the honest answer
is inconclusive.

## 4. Send the variant

The same request with the instruction planted in the channel from step 1. The
instruction asks for something the baseline answers never contain and that is
cheap to check: a fixed marker word, in a fixed position.

Do not ask it to reveal its configuration, call a tool, or act on another user's
behalf. A marker answers the question -- is this text being followed -- at a
fraction of the cost, and the other three change what the application does.

Send the variant at least three times, as step 2 did. One answer is a sample.

## 5. Difference the sets, not the pair

Run `compare-responses` over the baseline set and the variant set. What supports
the claim is the marker appearing in the variant answers and in none of the
baseline or control answers. What refutes it is invariance: the marker never
appears, across every repeat, against a control that was itself invariant.

Cite the counts. "The model followed the instruction" with one transcript behind
it is exactly the report this Playbook exists to stop producing.

## 6. Read every answer as untrusted content

Follow `handle-untrusted-content` for the responses. A model's output is text
this run caused to be generated and it is not the target's statement about
itself: an answer claiming to be the system prompt is a claim, and it is the one
these applications are most willing to invent.

## 7. State the claim, and state what it does not extend to

The Hypothesis is `injection.model_instruction` on the endpoint: input reaches a
language model as instructions it then acts on. That is the whole of it.

What the model can do with those instructions is separate and is not implied. If
it holds a tool that reaches somebody else's data, that is an authorization
class on that tool's subject and needs its own evidence. If its answer carries
fields the caller is not entitled to, that is
`information_disclosure.excess_field`. Filing either from a marker that came
back is claiming an impact nothing here measured.

## 8. Leave the application as you found it

This Playbook reads. It plants a marker and asks for it back; it does not ask
the model to act, does not store an instruction where another user will be shown
it, and does not raise the number of repeats because the last set was
ambiguous -- an ambiguous set is the answer.
