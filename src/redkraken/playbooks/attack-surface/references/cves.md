# Known vulnerabilities, versions, and what this corpus does with them

Maintainer notes, not projected to any model. Written fresh for v2; the v1 text
is not in this repository.

## Why no Playbook here outputs "the version is old"

There is no Property class for it, and the omission is deliberate. The ticket 18
vocabulary's leaf answers "what test would settle this", and a version banner
settles nothing: the banner may be wrong, the distribution may have backported
the fix, the affected code path may not be reachable in this deployment, and the
component may not be the one answering.

A published identifier for a known vulnerability is a *reason to look*, and the
looking produces evidence of one of the classes that already exist. A template
evaluator reachable through a parameter is `injection.template` whether or not
it has an identifier attached; the identifier tells a maintainer where to point
the Playbook, and the Playbook is what produces the claim.

## Where the version does belong

In the entity graph, as a technology observation with the Receipt that showed
it. `technology_identified` is a registered observation kind and it is
non-evidential on purpose: it populates surface, informs which Playbooks are
selectable, and settles nothing by itself. That is exactly the right weight for
a banner.

Two of this corpus's trigger facts are that observation reaching the selector --
a Playbook that only makes sense against one stack is triggered by the
technology being identified rather than by a Playbook guessing from a URL.

## The failure mode this replaces

The v1 shape was a report that named an identifier, a version and a link to an
advisory, with no exchange against the target that showed the deployment was
affected. Those are the reports that consume a triager's afternoon and close as
informative, and they are indistinguishable from a scanner's output because
that is usually where they came from.

The rule this corpus enforces instead: cite the advisory in the write-up as
context if it helps a reader, and cite the run's own exchanges as the evidence.
If the only thing behind the claim is the advisory, the claim is that the
advisory exists.

## Reachability is the whole question

When a known vulnerability does turn into a Playbook here, the step that carries
the weight is the one that shows the affected code path is reachable in this
deployment by this caller. Everything before it is a reason to try, and the
system already has a place to record a reason to try: it is a Task.
