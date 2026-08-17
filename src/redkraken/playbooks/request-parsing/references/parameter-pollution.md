# Parameter pollution: kept, narrowed to one name and one arm

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The precedence table and what to do with it. Send one name twice and find out
which occurrence the stack keeps: the first, the last, both concatenated with a
comma, both as an array, or one per layer -- the page listed the behaviour of a
dozen server frameworks, and the useful observation underneath the table was that
two components of one request path frequently disagree.

Then the applications of that. A validator that reads the first occurrence and a
handler that reads the last. A front end that filters on the query string while
the application reads the body. An array where a scalar was expected, so a check
written for a string compares against a list and passes. Names duplicated across
carriers -- query and body, query and cookie, body and header -- rather than
inside one. Nested and bracketed spellings that some parsers flatten and others
keep. Then the endings: get past an allow list, get past a rate limit keyed on a
value the limiter reads and the application does not, change what an audit record
says a request contained.

## Why the Playbook kept it

Because the observable is a disagreement inside one exchange, and both halves of
it are in the answer. Nothing needs to be smuggled, nothing needs to be malformed,
and the reading does not have to guess what the framework is: it sends the name
twice and reads what the application says it accepted beside what it produced.

This is the one topic in the v1 pack under this name whose test survives whole.
The Playbook's steps are the page's core arm, made into an arm rather than a
table.

## What the Playbook narrowed

**One name, from the recon pass, rather than every name.** The trigger is a route
where the same name is already known to be accepted in two carriers, which is a
fact the recon pass recorded rather than a thing to discover by sending. Sending
every parameter twice is a fuzz run against a write route, and its blast radius is
however many objects the route creates.

**One arm, not the framework table.** Which occurrence wins is interesting to
whoever fixes it and is not what makes the finding. What makes it is that the
answer names one value and the artefact was built from the other. The Playbook
asks for both halves to be quoted with their carriers named, which tells a
maintainer the precedence without the reading having had to enumerate it.

**A value the application refuses, rather than a payload.** The second occurrence
carries something outside the application's own list -- a format it does not
offer, a view it does not document. That is what makes the arm mean something: had
the check seen it, the request would not have been accepted. A value with a quote
or a bracket in it is a different Playbook's question and is refused by the
ceiling.

**No rate-limit arm.** Getting past a limiter by polluting the value it keys on is
on the v1 list, and testing it means sending enough requests to be limited. That
is an availability-affecting pattern, and the ticket that authored this Playbook
excludes those unless they are separately granted and bounded.

## What is worth remembering when writing it up

Name the carriers. "The parameter was accepted twice" is not reproducible;
"`view` in the query string and `view` in the form body, the receipt named the
query value and the artefact was built from the body value" is. Which side won is
the first thing the fix depends on, and it is free -- the reading already has it.

Name what was created. This is a write, the reading made an object, and the
identifier goes in the finding so the operator can remove it.
