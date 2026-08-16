# Language models as targets, and what makes a claim about one checkable

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## Why this needed a new Property class

`injection.model_instruction` was added by this ticket. The injection family in
this corpus splits by the interpreter -- SQL, template, command, document parser
-- because the interpreter is what decides what a payload means and therefore
what test settles the question. A language model is an interpreter with no
grammar, and that is a difference in kind rather than a variation on
`injection.template`.

The alternative was to file these under an existing class and lose the thing
that makes them hard: the same input does not always produce the same output.

## The one property that makes the evidence rules different

Every other Playbook in this corpus can send a request twice and expect the same
answer. This one cannot. A single differing response proves nothing, because a
model produces differing responses to identical inputs by design.

Everything unusual about the agentic-ai Playbook follows from that:

* The baseline is measured at least three times, not once.
* The variant is sent at least three times.
* The comparison is between two *sets* of responses, not two responses.
* The write-up cites how many of each set showed the behaviour.

A run that sends one payload, sees one surprising answer and files a Hypothesis
has produced a coin flip with a screenshot.

## What counts as the behaviour, and what does not

The claim is that attacker-supplied text reached the model as instructions the
model then acted on. Acting on them has to be observable in something other
than the model's own prose.

Strongest: an action the pipeline took that it does not take at baseline -- a
tool the model called, a request the backend made, a record it wrote. That is a
different observation kind and often a different class entirely, and it is the
better finding.

Adequate: the response contains content the baseline never contains across
repeats, and the content is specific enough that it could not be a paraphrase --
a nonce the payload named, a field from a context the caller was not given.

Not adequate: the model says it will do something. Models say things. A model
that outputs "I have deleted the record" has output a sentence.

Not adequate: the model breaks a stylistic rule. Refusing less, swearing, or
adopting a persona is a policy matter for the operator of the model, not a
security finding about the application, unless the persona is what gets it to
disclose or act.

## The control step, and why it is the honest half

The control plants the same instruction where the pipeline is expected to drop
it -- a field the prompt template does not interpolate, a header nothing reads.
If the behaviour appears there too, the model was not following the injected
instruction: something else in the exchange produced it, and the run has learned
that its differencing is measuring noise.

This is the step that gets skipped, and skipping it is what produces the reports
that read as "the chatbot said something weird".

## Direct and indirect

Direct: the payload is in the caller's own input. The caller is instructing a
model on their own behalf, so the claim needs a boundary being crossed -- data
from another tenant, an action outside the caller's authority. A model
persuaded to say something rude to the person who asked for it is not a
finding.

Indirect: the payload is in content the model consumes on someone else's behalf
-- a document, a page, a record another user wrote. This is where the real
findings are, because there the boundary is obvious: the instruction's author
and the model's principal are different people.

The Playbook's triggers admit both because the plumbing is the same. The
write-up has to say which one it found, and for direct injection it has to name
the boundary.

## Scope discipline on a live target

The model is not the target. The application that embeds it is. A Program's
rules of engagement bound the application; they say nothing about the model
vendor, and a run that spends a thousand requests exploring what a model will
say has attacked neither.

Related: the system prompt is not a secret worth a report on its own. Extracting
it is a good demonstration that the injection worked, and it is evidence for the
claim rather than the claim.
