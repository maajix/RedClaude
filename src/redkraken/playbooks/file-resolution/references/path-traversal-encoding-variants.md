# Encoding variants: the bypass table, and the one line of it the reading uses

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The table. Every way of writing `../` that some layer somewhere decodes:

* `%2e%2e%2f`, and `%252e%252e%252f` for the proxy that decodes twice
* `..%c0%af` and `..%ef%bc%8f`, overlong and full-width UTF-8 forms
* `....//` and `..././`, which survive a single non-recursive strip of `../`
* `..\` and `%5c` on Windows, and mixed `..\/` for the parser that accepts both
* a leading `/` to make the join absolute, and `C:\` or `\\host\share` for UNC
* a trailing `%00` for the null-byte truncation of a suffix a language appends
* `.` and space suffixes that Windows strips after the extension check
* a normalising CDN in front of an application that does not normalise, so the
  two disagree about what the path was

The page then told you to walk the table until one entry got through.

## Why the Playbook does not run it

**Walking a table is fuzzing.** Sixteen encodings times a handful of depths is a
few hundred requests against one parameter, all of them shaped like an attack.
That is a rate and a signature the Playbook's six requests are specifically not,
and it is the difference between a reading and a scan.

**The table is a list of ways to defeat a filter, and a filter is not the
subject.** Every entry exists because some layer strips, decodes or rejects the
plain form. Finding which entry survives tells you about that layer. The
Hypothesis is about whether the resolution is checked, and a route whose only
defence is a strip list is already answering that question -- in the affirmative,
badly -- as soon as the plain form is refused and the resolution is not.

**The exotic entries reach beyond a read.** UNC paths make the target open an SMB
connection to a host on the network, which is an outbound request and a
credential-relay primitive, not a file read. Null-byte truncation depends on
runtime versions in ways that make the failure mode unknowable.

**Success on entry fourteen is unreportable.** A finding whose reproduction is
"send this double-encoded overlong-UTF-8 string" is one the triager cannot verify
without the same fuzzing, and one the fix will address by adding an entry to the
strip list.

## What is kept

One line: percent-decoding happens somewhere, so the reading sends the plain
form and lets the transport encode it. `../vault/ledger.txt` in the parameter
value, encoded once by the request layer, is what the route sees, and that is the
form a report can be written about.

Also kept: the observation that a CDN and an application can disagree about what
the path was. That disagreement is a real class and the Playbook names it -- in
`web-cache`, where the question is what the cache stored, not what the
filesystem returned.

## The trap in the whole technique

The table teaches a habit that survives it: treating "my payload got through" as
the finding. It is not. Getting through is the precondition; the finding is that
the read landed outside the directory, which is a claim about a filesystem and
not about a string.

A reading that reports an accepted `%2e%2e%2f` without a document from outside
the base has reported that a route accepts percent signs.
