# 80 — Measure the multiagent failure modes this harness can actually have

**What to build:** An answer, on record, to which of the documented multiagent failure modes this roster reproduces when several roles run at once -- correlated choices, queue flooding, consensus overriding private evidence, and one agent reaching another's workspace -- and enforcement for the ones that turn out to be reachable here.

**Blocked by:** 73 — State the cross-role subagent cap once; 75 — Refuse a claim for the concurrency it would actually spend.

**Status:** resolved

- [x] Correlated choice is measured, not assumed: a wave of concurrent Tasks over one Program is recorded and reported as how many distinct subjects, Property classes and proposed Hypotheses came back versus how many agents ran. A wave of eight that returns two distinct subjects is the finding, and the number is emitted rather than described.
- [x] Where the measurement shows correlation, the scheduler refuses the duplicate rather than the model being asked to diversify. Refusal is by subject and Property class against what is already claimed in the wave, on the existing claim path, and a refused agent gets a different subject or no Task.
- [x] Request volume against one Program has a ceiling the door enforces, with refusal and a typed reason, and a run that would exceed it stops. A polling loop that files two million requests for a hundred useful ones is a program-rules violation in bug bounty and a ban in practice, so the limit belongs beside the Receipt and not in an instruction a model may ignore.
- [x] The blind validator is shown to be blind under concurrency: a validation packet carries no hunter narrative, no other agent's conclusion and no count of who agreed, and there is a test that fails if a field carrying one is added. Consensus is not evidence, and the packet is where that is either true or not.
- [x] Two agents running at once cannot reach each other: separate working directories, no shared writable state outside canonical rows, and no path by which one can signal, kill or impersonate another. Whatever the isolation slice already gives is stated with the gap named, and the gap is a ticket rather than a paragraph.
- [x] Every claim above cites a run in this repository. A failure mode this harness cannot reproduce is recorded as not reproduced with the reason -- that is a result, and the criterion is not met by adding a control for a problem nobody showed we have.

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

## What was built

`baseline/multiagent-modes.tsv` is the answer, and everything below is what one
of its seven rows cites. One row per mode, with a verdict from a closed set --
`measured`, `enforced`, `reproduced`, `not_reproduced` -- the mechanism that
earned it, and the test that is the run. `tests/test_modes.py` imports every
cited run and looks it up, so a record whose citations went stale fails the
suite rather than being discovered a year later by somebody reading the file.
A `reproduced` row has to name a ticket in its note, which is the criterion
about gaps being tickets rather than paragraphs, enforced on the record itself.

**Correlated choice is measured.** `wave_report(uuid)` counts what a Program's
agents came back with -- distinct subjects, distinct Property classes, distinct
claims -- against how many of them ran, off the `hypothesis_provenance` rows
20260814T070000Z has written since Hypotheses became promotable. Nothing new is
recorded to make the measurement possible, and a Program whose wave never
happened reads as zeroes rather than as a missing table. `panels.WAVE` puts the
five numbers on the operator console. `WaveMeasurementTest` promotes through the
real proposal path from four distinct agent runs: four agents, two subjects, two
Property classes, three claims. The measurement is emitted, not described.

**The duplicate is refused at the claim.** `subject_held_for(tasks)` is a new
arm of `claimable_for`, between `lane_full` and `global_subagent_cap`: a Task
whose kind, subject and Property class are already held by a `claimed` or
`running` claim of the same Program is refused `subject_held`. Refused rather
than cancelled -- the proposal survives, the second agent gets a different
subject or no Task, and the moment the first run ends the same Task is claimable
again. Asking the model to diversify is asking the thing that is correlated to
correct its own correlation.

The key includes `kind` because a `validate` and a `hunt` over one subject are
not the same work. It is not the same key as `tasks_live_dedup_idx`, and the
difference is the finding: that index is unique over
`(program_id, kind, subject_entity_id, hypothesis_id, finding_id)`, so it
already refused two live Tasks naming one Hypothesis. What it admits is two
Hypotheses about one subject and one Property class, which is exactly the shape
a correlated wave produces. `SlateClaimTest.arrange_subject_held` builds that
shape with two different Identities, because with one the earlier
`identity_held` arm fires and the demonstration proves nothing.

**The flood is refused at the door.** Already built by 20260813T230000Z and
proved here rather than added: twenty-five requests past an exhausted
`budget_requests` are answered 407 with `budget exhausted` and no `Retry-After`,
no name is resolved, no socket is opened, and the target sees nothing. The
engagement's record stays at what it actually spent while `exhausted` counts the
loop -- two numbers, and the distance between them is the finding. The paper's
2.4 million requests for 117 accepted jobs is a program-rules violation in bug
bounty, which is why the limit is beside the Receipt and not in an instruction.

**The blind packet is blind under concurrency.** 20260815T180000Z built the
packet from a column allowlist and asserted the allowlist reaches none of the
relations a hunter's prose lives in. That list is about narrative; this file adds
the same assertion over the relations agreement is kept in -- `verdicts`,
`validation_attempts`, `validation_queue`, `review_gates` -- because a count of
who agreed is not prose and would have passed every check written so far.
`BlindPacketUnderConcurrencyTest` carries a peer's claim about the same subject
all the way to a verdict, serves the packet, has a third agent open a candidate
about that subject while the session is open, and reads the document again from
two connections inside transactions neither has committed. Every read is the
same bytes, and the key list is pinned in the test, so a field carrying a peer's
conclusion fails whatever else it brings with it.

The mode itself is `not_reproduced` and that is the honest verdict: the roster
runs one validator session at a time and a second is refused by name, so there
is no group here whose belief could displace a private fact. The enforcement is
recorded as its own row rather than folded into that one, because what is
enforced is the packet and what is unreachable is the mode.

**Turf wars split in two.** The workspace half is not reproduced: every child
runs `--read-only` as uid 65534 with `cap-drop ALL`, `no-new-privileges`, a
tmpfs scratch of its own and no engine socket, the only writable host state is
what the runtime mounts, and the canonical rows are written through verbs the
database authorises per Program. There is no path from one child to another's
filesystem, process table or credential.

The network half is reproduced, and it is the one gap this ticket found.
`isolation.run` calls `one_peer`, which refuses if anything but the door is on
the Agent network, and then starts a container on that network. It is a
check-then-act, the engine holds nothing between the two, and `RK_AGENT_NETWORK`
is one name for a whole installation -- so two launches inside each other's
window both see a clear network and both attach, and an internal network carries
every route across itself.
`test_a_peer_that_arrives_after_the_check_is_reachable_by_the_child` shows it
deterministically rather than by racing: the peer is attached inside the launch
call, after `one_peer` has returned, and the child comes up and reaches it.
Ticket 85 is where that is answered; the test says in its own docstring that it
exists to record the gap and should not outlive it.

`check_wave_measurement()` holds all of it from the standing side: neither wave
function is reachable from a connection an agent holds, `subject_held_for` reads
no clock, and no two claims of one Program hold the same kind, subject and
Property class. Its negative control grants `wave_report` to `rk2_state`, which
is the failure that matters -- a model that can read how many of its peers
proposed what has been handed the consensus a blind packet exists to withhold.
