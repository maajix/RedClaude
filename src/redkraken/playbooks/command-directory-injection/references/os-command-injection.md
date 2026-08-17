# OS command injection: what the Playbook drives and what it refuses

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The core page of the pack. A route builds a string and hands it to a shell --
`system()`, `popen()`, `sh -c`, `subprocess` with `shell=True`, a backtick in a
template, an `exec` in a build script -- and part of that string came from the
caller. The page listed the separators that end one command and begin another:

```
;  &  &&  |  ||  $(...)  `...`  %0a  %0d
```

and then the three ways to notice it worked: output in the response, a delay the
caller chose, and a lookup or connection arriving at a host the caller owns.

## The half the Playbook uses

All three noticing methods, in that order of preference, and none of the payload
catalogue.

The order is not stylistic. Output in the response is the cheapest and the least
ambiguous: one request, one comparison, and the evidence is a `Receipt` anybody
can re-read. A delay is second because it costs the target real seconds and
because a network is entitled to add its own. A lookup at a callback host is
third because it proves reachability rather than execution and because it puts a
record of the engagement on somebody else's resolver.

What the Playbook takes from the page:

* The separator set above, unchanged. It is the actual grammar and there is no
  smaller one.
* The observation that a filtered separator is evidence too. A route that returns
  the same body for `;id` and for `id` has told you the value is not concatenated
  into anything; a route that returns a different body for the first has told you
  something parsed it.
* The refutation: the value comes back byte for byte and every separator is
  present in the echo. Encoding at the sink is the strongest possible answer and
  it is visible in one response.

## The half that stays out, and why

**Everything after the proof.** The page went on to reverse shells, to
`curl | sh`, to writing a webshell into a served directory, to enumerating the
host and pivoting. None of that is here, and the reason is not squeamishness: a
Playbook is a reading with a verdict, and every one of those actions is a change
to a machine somebody else runs. The verdict was already reached by the
separator that echoed.

Concretely, the Playbook is `read_only` and `approval_required`. `read_only`
because a timing primitive and an echoed separator alter nothing the target
stores. `approval_required` because both of them still run code on somebody
else's host, and the operator, not this document, is who decides that a Program's
rules of engagement allow it.

The specific refusals, so that a later reader does not have to infer them:

* No payload that writes a file, opens a listener, or starts a process that
  outlives the request.
* No `sleep` longer than the Playbook's own budget, and none at all on a route
  that a person is waiting on.
* No chaining into the second command once the first has answered.

## The trap in the whole technique

A delay is not a proof on its own. Backends stall, connection pools drain, and a
cold path is slower on its first call than on its tenth. A single slow response
to a payload carrying `sleep 5` is one sample of a distribution nobody measured.

The Playbook therefore never accepts a delay without its neutralised twin: the
same request, same length, same shape, with the separator replaced by a character
the shell does not act on, sampled the same number of times and interleaved with
the payload rather than run as a block. What is claimed is the difference between
two sampled distributions, not the duration of one request.
