# Why this Playbook insists on a control

Maintainer notes. Nothing here reaches a model: the model projection is built
from the frontmatter and the body of `playbook.md`, and this file is not in it.
It is hashed and recorded so a maintainer can find it, and it is deliberately
outside the text a running Agent reads.

## The failure this was written against

A one-Identity object-ownership test is the most common shape in every public
bug bounty write-up, and it is the shape that produces the most invalid reports.
The pattern is:

1. fetch `/api/orders/1041` as yourself, get 200;
2. fetch `/api/orders/1042`, get 200 as well;
3. report "IDOR".

Step 2 has three explanations and the report picks one. The object might not be
anybody else's. `1042` might be a public order. The route might return the
caller's own order regardless of the identifier in the path. Every one of those
produces the same two 200s.

The second Identity is what removes the ambiguity, and the *control* exchange --
label B against label B's own object -- is what removes the second ambiguity, in
the refuting direction. A 403 under label B is only evidence of an enforced
boundary if label B's session was working at the time. Otherwise the run has
measured an expired cookie.

This is why `bb:evidence` requires a `control` row for `supported` and not only
a `variant` row. The database enforces it at the transition
(`enforce_playbook_evidence`), so a run that skipped the control cannot promote
the Hypothesis even if the model is convinced.

## Why the baseline is `stable_session`

The differential is a statement about one session's authority at one moment. A
Playbook running beside this one that logs out, rotates a token or changes a
password moves the thing being measured, and the measurement silently becomes
about the rotation instead. `playbooks_conflict` derives that from
`baseline = 'stable_session'` against another Playbook's `effects`, so no author
maintains a compatibility list.

## Why the status is `draft`

Ticket 25's promotion guard refuses `stable` until a fixture pair containing
`authorization.object_ownership` has been run against this exact text, and the
fixture catalogue is empty. `draft` is the honest state, and selection admits
draft Playbooks -- it only excludes `deprecated`.

## Review date

`bb:stale_after` is a review date, not an expiry of the Playbook. When it
passes, re-read the body against what the surface actually looks like now and
move the date, or deprecate the Playbook. The suite fails on the day it passes,
which is the only version of a review date that gets read.
