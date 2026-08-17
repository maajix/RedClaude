# SQL injection to code execution: out, and where the impact goes instead

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The end of the pack: turning a working injection into a shell on the database
host. `xp_cmdshell` on MSSQL, re-enabled through `sp_configure` if somebody had
turned it off. `COPY ... FROM PROGRAM` on PostgreSQL, or a C extension loaded via
`CREATE FUNCTION`. `SELECT ... INTO OUTFILE` on MySQL to write a webshell into a
served directory, or `UDF` loading through `lib_mysqludf_sys`. Then the follow-on:
credentials from configuration files, lateral movement, persistence.

## Why the Playbook does not run any of it

**It is not `read_only`, in the plainest sense available.** Every primitive on
that list either starts a process, writes a file, or changes the database's
configuration. This Playbook is declared `read_only` and the declaration is
enforced by the harness, not by intention.

**It answers no question the reading asked.** The hypothesis is "input reaches a
database query". It was answered by the boolean pair. Running a command on the
database host adds severity to a report and adds no evidence to a verdict that
is already complete.

**It leaves the scope.** A Program names hosts. A database server is frequently
not among them, and a shell on it reaches an internal network that certainly is
not. Nothing in the Playbook's selection can know where the database lives, which
means the reading cannot know whether the step it is about to take is in scope.

**It is the step that is hardest to undo.** A webshell written into a served
directory is a backdoor on somebody's production host. Even removed immediately,
it existed, and for the window it existed anybody who found it had the access it
granted. That is not a risk a reading gets to take on the target's behalf.

## Where impact goes instead

This repository has a place for it. A `Finding` carries an impact narrative, and
this repository's impact model argues from what a finding permits rather than
from what was demonstrated. "The route concatenates caller input into a
statement" supports an argument about arbitrary read of the schema, about
authentication bypass, about code execution where the engine and the service
account allow it -- and that argument is written in the report, sourced from the
evidence that exists.

The relevant fact to record, because it strengthens the argument at no cost, is
what the reading already saw: the engine (from the fingerprint step, which runs
anyway to build the control) and whether errors indicate an unusually privileged
role. Both come from observations the reading made for other reasons. Neither
requires a further request.

## The trap in the whole technique

The escalation is available and cheap, and the argument for taking it is always
the same: a triager will downgrade a boolean differential, and a screenshot of
`whoami` closes the ticket at critical.

Sometimes true. It is also how researchers get removed from Programs, and it
inverts who decided. A rules-of-engagement document that permits testing for
injection does not permit executing commands on a database server, and the
distance between the two is not covered by "I was demonstrating impact".

The version that holds up: a clean differential, a well-written impact section, a
named defect, and an offer to demonstrate further with written permission. Slower
to triage. It has never ended an engagement.
