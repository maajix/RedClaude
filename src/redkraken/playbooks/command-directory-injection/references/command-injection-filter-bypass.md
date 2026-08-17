# Command injection filter bypass: read for the refutation, not the payload

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The evasion catalogue. A target has a deny list, and the page is how to get past
it: `$IFS` and `${IFS}` and `<` for a blocked space, `w'h'oami` and `w\hoami` and
`$'\x77hoami'` for a blocked word, `$@` and `""` inserted mid-token, base64 into
`base64 -d | sh`, hex, reversed strings, wildcard expansion such as `/bin/c?t`,
environment-variable slicing such as `${PATH:0:1}` to build a `/` without typing
one.

## The half the Playbook uses

One idea, and it is the opposite of the page's purpose: **a deny list that can be
walked around is not a control, and observing that it can be is a finding about
the control rather than a step towards a bigger one.**

The Playbook uses this in exactly one place. When the direct separator is
rejected -- a 400, a scrubbed echo, a "invalid character" message -- the reading
does not stop and does not escalate. It sends one substitution of a blocked
character, chosen to be inert: `$IFS` where a space was refused, or one
concatenation quote inside a word that is otherwise harmless. If that request now
behaves like the unfiltered one, the route filters characters and does not
escape, and that difference is the whole of what gets reported.

The evidence shape stays what it was: a differential against a neutralised
control, not a demonstration of a command.

## The half that stays out, and why

**The rest of the catalogue, and the intent behind it.** Base64-into-a-shell,
wildcard expansion of a binary path, and reversed-string tricks all exist to run
something the filter meant to stop. The Playbook does not want to run anything.
Once "the filter can be walked around" has been shown with one inert
substitution, every further bypass adds risk and no evidence.

There is a second reason, specific to how findings are graded here. A report
built on a chain of five evasions is a report the target can close by fixing one
of them, and the reader has to reconstruct which. A report built on "the route
concatenates into a shell and filters characters instead of escaping" names the
defect.

## The trap in the whole technique

Bypass work is absorbing and it produces the feeling of progress without
producing evidence. It is very common to spend an hour finding an encoding that
gets a payload past a filter, and to end that hour with no observation that was
not available in the first five minutes -- because the filter was never the
finding.

The check the Playbook applies before any bypass attempt: *if this works, what
observation will I have that I do not have now?* If the answer is "the same
differential, through a different encoding", the attempt is skipped.
