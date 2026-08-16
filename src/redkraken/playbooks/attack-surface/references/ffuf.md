# Content discovery, and what it costs to be wrong about it

Maintainer notes. Nothing here reaches a model: the model projection is built
from the frontmatter and the body of `playbook.md`, and this file is not in it.
It is hashed and recorded so a maintainer can find it.

Written fresh. The v1 corpus is not in this repository -- `baseline/` froze
identity and digest, deliberately without content -- so this is the v2 text for
the v1 name rather than a copy of the v1 text, and nothing here claims fidelity
to what that file said.

## Why the Playbook proposes candidates instead of running a wordlist

The Playbook's step 2 asks for a short list with a reason per entry. That is not
a preference about tidiness. Three things follow from it.

A wordlist run is thousands of requests against one Program, which is the
resource-flooding shape a program's rules of engagement are written to forbid
and the fastest route to being removed from one. Whatever it finds, it finds
after the removal is already deserved.

A wordlist run has no control. It produces a list of paths that answered 200,
and a server with a catch-all answers every path with 200. The Playbook's step 1
exists because the difference against a path nobody deployed is the only thing
that makes any of the answers readable, and a tool that reports statuses does
not have it.

And a wordlist run is not this Playbook's class. `artifact_exposure` is about a
document that was deployed by accident, and the evidence is what the document
turns out to be. A path that exists is surface, and surface belongs in the
entity graph rather than in a hypothesis.

## Where a discovery run does belong

Behind the Program's rules of engagement, as an explicit Tool run, with the
concurrency and the wordlist recorded, proposing entities and nothing else. That
is `enumerate-surface` with a registered tool, not a Playbook: the record of it
is a Tool run and its Artifacts, which is a thing a later reader can re-derive.

The distinction the migration is drawing is between enumeration, which is
allowed to be broad and produces surface, and a claim, which has to be narrow
and produces evidence. v1 mixed them, and the mixing is why its output was a
list of 200s somebody had to triage by hand.

## Rate, and the number that matters

If a discovery run happens, the number to write down before it starts is
requests per second, not the wordlist size. The wordlist decides how long it
takes; the rate decides whether anyone notices, and the second is what a program
complains about.

## What a 200 is not

It is not a file. It is not a finding. It is not reproducible on its own -- a
CDN, a load balancer with a stale route and a single-page application router all
produce it. The Playbook's control is what turns it into an observation, and
without the control the honest record is that a path answered and nothing else
is known.
