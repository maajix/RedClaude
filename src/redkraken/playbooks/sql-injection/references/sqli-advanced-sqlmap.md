# sqlmap: why this Playbook does not run it

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

Operating sqlmap. The request-capture workflow (`-r request.txt`), the switches
that matter (`--level`, `--risk`, `--technique`, `--dbms`, `--tamper`), reading
its output, and the escalation path from detection through `--dump` to `--os-shell`
and `--file-read`.

## Where a scanner fits in v2, and where it does not

This repository runs offline tools through a registry, in an isolated runner,
with a recorded `tool_run` and its artifacts. That machinery exists and sqlmap
would be a plausible entry in it. This Playbook still does not invoke it, and the
reasons are structural rather than a dislike of the tool.

**A Playbook is a reading with a verdict, and the verdict must be legible.**
The evidence rows on this Playbook name a differential and its neutralised
control. A scanner's answer is "injectable, boolean-based blind, payload
attached". To promote that to `supported` the harness would have to trust the
tool's internal comparison -- a comparison this repository never saw, over a
baseline it never captured, with a control it cannot inspect. The evidence model
here exists precisely so that no verdict rests on a claim nobody can re-read.

**Its defaults are not `read_only`.** At `--level 3` and above sqlmap tests
headers and cookies as a matter of course; `--risk 2` admits heavy time-based
queries; `--risk 3` admits `OR`-based payloads that widen an UPDATE's WHERE
clause. Those are real writes against a live target. Constraining the tool to a
safe subset by flag is possible and it is a configuration that has to be right
every time, on every route, with no way for the harness to verify it was.

**Its request volume does not fit the budget.** A default run against one
parameter is in the thousands of requests. This harness runs Programs under an
explicit rate limit, and a Playbook that spends the whole budget on one
parameter has starved every other reading in the queue.

**Extraction is the point of the tool.** `--dump` is where sqlmap earns its
reputation, and it is exactly what these notes refuse everywhere else.

## What is kept

One idea: **the tamper-script concept**, which the custom-tampering note carries
in its own right. A payload that fails may be failing at a filter rather than at
the database, and knowing the difference changes the verdict.

And one operational habit, which is genuinely good: **capture the request first,
work from the capture.** The Playbook's steps operate on a recorded request with
its identity, headers and body intact, so the true and false arms differ in one
field and not in whatever a hand-typed second request happened to change.

## The trap in the whole technique

A scanner turns a reading into a result you did not derive. When the report comes
back and a triager asks why the boolean arms differed, the honest answer after a
scanner run is "the tool said so" -- and the tool's own log is the only evidence
that exists.

There is also the failure that gets people removed from Programs: sqlmap pointed
at a route that turned out to be a write path, on a production database, with
`--risk` high enough to modify rows. The tool did what it was told. Nobody
decided to do it.

If an operator wants sqlmap in the loop, the right shape is a registered tool run
that an operator launches deliberately, with its artifacts recorded, feeding a
reading that still has to produce its own differential. Not a step inside a
Playbook that selects itself.
