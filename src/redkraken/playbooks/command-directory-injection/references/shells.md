# Shells: the grammar behind the separator list

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

A reference card for the shells a target might be running, and how they differ
where it matters for injection: `sh`, `bash`, `zsh`, `cmd.exe` and PowerShell.
Word splitting, quoting rules, which characters begin a substitution, what
survives a `"` and what does not, and the Windows pair -- `&` and `|` in
`cmd.exe`, `;` and backtick-free subexpressions in PowerShell.

It was the page you read after a payload did not work, to find out whether the
target was filtering or whether you had written a payload for the wrong
interpreter.

## The half the Playbook uses

The distinction between *a separator that is filtered* and *a separator that is
not a separator here*. It is the single most useful thing in the page and the one
a reading gets wrong most often.

A route that ignores `;` may be running `cmd.exe`, where `;` is an ordinary
character. A route that ignores `$(...)` may be running a shell that never
performs substitution inside the quoting the caller landed in. Neither is a
refutation, and a reading that reports "not injectable" after one separator has
reported the separator rather than the route.

So the Playbook's step that chooses payloads chooses at least one from each of
three families -- a statement separator, a substitution, and a newline -- and a
reading that has not tried all three does not get to say "refuted". It says
`inconclusive`, which is the honest verdict for a question that was asked once.

## The half that stays out, and why

**The quoting-escape tables.** Working out whether the value lands inside single
quotes, inside double quotes, or bare, and then writing the escape that breaks
out of each, is real work and it is the work of exploitation rather than
detection. A value that reaches a shell at all is the finding; which quote it
landed in decides how far somebody could push it, and that is a conversation for
the report's impact section, not a step here.

**The Windows half beyond the separator set.** PowerShell's own parsing has
enough surface for its own document. What is carried forward is the observation
that `&` and `|` matter and `;` may not, which is what keeps a reading from
declaring a Windows target clean.

## The trap in the whole technique

Assuming one shell for the whole target. A modern application is a fleet: the
route that resizes an image may shell out inside a container built from a
distroless base with `busybox` as `/bin/sh`, while the route that exports a
report runs on a Windows worker in the same cluster. Two routes on one host name
can sit on two interpreters, and a separator set proven on one says nothing about
the other.

The practical consequence for the Playbook: the verdict is about the subject
endpoint and is recorded against it, never about the Application.
