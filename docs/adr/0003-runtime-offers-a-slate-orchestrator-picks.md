# The runtime offers a slate of tasks; the orchestrator picks; the runtime commits

Task selection is split. Each time a slot frees, the runtime computes the top
five pending tasks that are ready, lane-legal, identity-available and affordable,
and offers that slate to the orchestrator. The orchestrator picks one. The
runtime then commits the claim in a transaction that re-evaluates every filter.
A choice that no longer holds is refused rather than substituted; an
orchestrator that chose nothing gets the first entry that still holds, walking
from position one.

Decided because neither pure alternative is acceptable. If the runtime simply
claims the highest-ranked task, the orchestrator's judgement is unusable: it is
the only participant that sees two tasks that should run against one session, or
a task whose result would make another moot, and none of that is expressible in a
five-factor formula. If the orchestrator reads the queue and calls the subagent
tool itself, then concurrency, lane quotas and budget — cost and safety
properties — are decided by model output, and "LLM proposes, runtime commits"
becomes false at exactly the layer that spends money.

The split keeps the invariant literal rather than approximate. The runtime bounds
the choice set; the model chooses inside it; the runtime commits. That is the
same shape as the rest of the system: an agent proposes a hypothesis and the
runtime's constraints decide whether it exists, an agent reports an observation
and the runtime discards it without a provenance record.

## Consequences

- **The slate is a hot path, not a one-off.** It is recomputed every time a slot
  frees inside one long orchestrator session, so how it is served is a real cost
  question and is deliberately left to the state-access design rather than
  assumed to be one MCP call.
- **Re-validation at commit is mandatory, not defensive.** A slate offered and a
  slate acted on are separated by a model turn, during which another run can
  finish, a lease can be taken, or a scope can change. The claim transaction
  re-checks readiness, lane headroom, identity availability and skills, and this
  is the reason the slate carries an expiry.
- **A degenerate orchestrator is still correct.** One that always picks position
  one reduces the system to pure greedy ranking, and one that picks nothing gets
  the first entry that survives re-validation. The model can improve scheduling;
  it cannot break it.
- **A wrong choice is refused, not corrected.** This decision originally read
  "falls through to position one" for an off-slate or stale pick as well, and
  ticket 23 narrowed it: substituting a Task for the one that was named would
  answer a request nobody made, and the orchestrator would learn nothing from
  having asked for something that was gone. Refusal and fallback stay distinct
  because they mean different things -- one is a choice that failed, the other
  is no choice at all.
- **Lane quotas stay on the runtime's side.** They bound how many runs of each
  kind exist at once, which makes them a spend and containment control. That is
  why moving them during a run is its own open question rather than something the
  orchestrator does implicitly by choosing.
- **The orchestrator is not a task.** It runs as an agent run with a null task, so
  it never competes for a lane slot with the work it is scheduling.

Settled in historical ticket 08, decision 3.
