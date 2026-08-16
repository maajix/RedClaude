# Bypassing a limit, and why that is not what the Playbook does

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## The distinction this file exists to hold

There are two questions about a rate limit and they have different evidence.

*Is there a limit at all?* That is the api Playbook. It sends a declared
sequence under one Identity and reads whether anything ever changed. Supported
is the invariance, refuted is the limit engaging, and the control is that the
Identity was authenticated throughout.

*Can a limit that exists be evaded?* That is a different claim with a different
shape: something did engage, and a variation on the request made it stop
engaging. The variation is the finding, and the evidence for it is the pair of
sequences rather than one.

The Playbook only asks the first. This is the file that says why it is worth
adding the second later rather than folding it in now.

## The variations worth knowing about, when the second one is written

Each of these is a claim that the counter is keyed on something the caller
controls.

* **A forwarded-for style header.** The limit is keyed on a client address the
  application reads out of a header rather than off the socket. Reproduces as:
  the sequence engages, the same sequence with the header varying does not.
* **Case, encoding or a trailing separator in the path.** The counter is keyed
  on the raw path, and two spellings of one route are two counters.
* **A second method for the same operation.** The limit is on the method, not
  the operation.
* **Batching.** One request carries many operations, so the counter counts one.
  Note the class: this is `rate_limiting.resource_cost`, not `per_identity`, and
  it is where the GraphQL and the JSON-RPC shapes meet.
* **The unauthenticated path to the same work.** The limit is enforced on the
  authenticated route and the anonymous one shares the backend.

## Why none of them is in the Playbook body

Every one of them doubles the requests spent, and each doubles them on a target
that has already demonstrated a limit -- which is to say, on a target that is
already counting and may already be treating the caller as abusive. A Playbook
that walks the list above is a Playbook whose worst case is a sequence of
sequences.

Sending them requires two things this ticket does not build: a per-Program
ceiling the door enforces rather than a number written in a document, and a
class of claim that carries "the counter is keyed on X" as its statement. The
first is ticket 80. The second is a leaf question for whoever writes it.

## The invalid-report shape

`429` did not appear within twelve requests, therefore there is no rate limit.
There may be a limit at a hundred, at a thousand, or per hour rather than per
minute. The api Playbook's claim is scoped to the sequence it actually sent, and
its step 1 requires the count to be written down first for exactly this reason:
the claim a reader can check is "twelve identical requests under one account
were all answered", and that is a smaller statement than "unbounded".

Keep it that small. A finding that overstates its own measurement is refuted by
the first person who reproduces it.
