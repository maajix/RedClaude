# Automated scanners, and why this harness is not one

Maintainer notes. Nothing here reaches a model, for the reason `ffuf.md` gives:
the projection carries the frontmatter and the body of `playbook.md` and nothing
else. Written fresh for v2; the v1 text is not in this repository.

## The decision this file records

A scanner is a program that sends a large fixed set of requests and reports
which ones produced a pattern it recognises. This system deliberately does not
wrap one, and the reason is not that scanners are bad at what they do.

It is that a scanner's output is a claim without a control. It reports "this
response matched", and every clause of the verdict this corpus is graded by --
grounded, not admitted on the secure twin, not fired on an out-of-class fixture
-- is a question about a comparison the scanner did not make. A finding this
harness cannot re-derive from stored Artifacts is a finding it cannot file, and
that rule is what makes the rest of the pipeline mean anything.

There is a second reason, which is about volume. A scanner run against a bug
bounty target is tens of thousands of requests, and the programs that ban
automated scanning say so in their rules precisely because they have been on the
receiving end of one.

## What is used instead

A registered Tool run, one tool at a time, with its arguments and its output
recorded as Artifacts, proposing surface. `jq` over a stored response is the
smallest example of the shape and it is the whole idea: the run is a row, the
output is content-addressed, and the claim built on it cites both.

Where a scanner's *knowledge* is worth having -- the paths it knows to try, the
response shapes it knows to recognise -- it belongs in a Playbook's steps, where
it is versioned, projected to the model, and graded against fixtures.

## What to do when an operator asks for one anyway

Say what it would produce: a list of matches, no control, no re-derivable
evidence, and a request volume the Program's own rules may forbid. If the
Program permits it and the operator wants it, it is a Tool run under the
Program's rules of engagement with the rate written down, and its output is
surface. It is not a route to a Hypothesis, and nothing in this corpus should
grow one.
