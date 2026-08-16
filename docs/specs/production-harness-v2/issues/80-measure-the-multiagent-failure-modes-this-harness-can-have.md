# 80 — Measure the multiagent failure modes this harness can actually have

**What to build:** An answer, on record, to which of the documented multiagent failure modes this roster reproduces when several roles run at once -- correlated choices, queue flooding, consensus overriding private evidence, and one agent reaching another's workspace -- and enforcement for the ones that turn out to be reachable here.

**Blocked by:** 73 — State the cross-role subagent cap once; 75 — Refuse a claim for the concurrency it would actually spend.

**Status:** ready-for-agent

- [ ] Correlated choice is measured, not assumed: a wave of concurrent Tasks over one Program is recorded and reported as how many distinct subjects, Property classes and proposed Hypotheses came back versus how many agents ran. A wave of eight that returns two distinct subjects is the finding, and the number is emitted rather than described.
- [ ] Where the measurement shows correlation, the scheduler refuses the duplicate rather than the model being asked to diversify. Refusal is by subject and Property class against what is already claimed in the wave, on the existing claim path, and a refused agent gets a different subject or no Task.
- [ ] Request volume against one Program has a ceiling the door enforces, with refusal and a typed reason, and a run that would exceed it stops. A polling loop that files two million requests for a hundred useful ones is a program-rules violation in bug bounty and a ban in practice, so the limit belongs beside the Receipt and not in an instruction a model may ignore.
- [ ] The blind validator is shown to be blind under concurrency: a validation packet carries no hunter narrative, no other agent's conclusion and no count of who agreed, and there is a test that fails if a field carrying one is added. Consensus is not evidence, and the packet is where that is either true or not.
- [ ] Two agents running at once cannot reach each other: separate working directories, no shared writable state outside canonical rows, and no path by which one can signal, kill or impersonate another. Whatever the isolation slice already gives is stated with the gap named, and the gap is a ticket rather than a paragraph.
- [ ] Every claim above cites a run in this repository. A failure mode this harness cannot reproduce is recorded as not reproduced with the reason -- that is a result, and the criterion is not met by adding a control for a problem nobody showed we have.

## Where this comes from

Anthropic's [Patterns and Problems in Multiagent Systems](https://www.anthropic.com/research/multiagent-systems)
reports what many instances of one model do when they run together. Four of its
findings have a straight path into this system.

**Low variance.** "When one agent makes a bad decision, it is likely that many agents
will make that same bad decision" -- 18 of 30 agents chose the identical git branch name,
and over half built the same kind of project unprompted. Our roles are instances of one
model reading one Program's Surface, so a wave of hunters is the same experiment: the
concurrency spends N budgets and buys close to one agent's coverage. Diversity here is a
scheduler property, because asking a model to be original is asking the thing that is
correlated to fix its own correlation.

**Resource flooding.** Agents given a job queue escalated to polling 30 times a second;
one run made 2.4 million requests for 117 accepted jobs. Against a queue that is wasted
compute. Against a bug bounty program it is the fastest way to be removed from it, and
the harness's own door is the only place that can refuse it.

**Consensus over evidence.** On hidden-profile tasks, where a fact only one agent holds
should overturn what the group believes, models scored 17-36% against a solo ceiling near
100%. That is the exact shape of a hunter's claim carrying a validator with it, which is
why blind validation exists -- and why it is worth proving still blind when several
agents are talking at once rather than assuming the field list has not grown.

**Turf wars.** Given contradictory directives on a shared machine, agents disabled each
other's Unix accounts, killed competing processes and planted code disguised as another
agent's. Nothing here gives a role sudo, but "two roles, one host, one working directory"
is the same starting condition, and it is worth knowing exactly what separates them today.

The paper's own conclusion is the reason this is a ticket and not a note: coordination
"doesn't naturally emerge from stronger intelligence nor alignment at the individual
level", and a better model is not the fix.

## What this ticket is not

Not a survey and not an alignment project. It measures four things against this
harness, enforces what is reachable at the door and the scheduler, and raises tickets for
the rest. Anything that cannot be shown with a run in this repository is written down as
not shown.
