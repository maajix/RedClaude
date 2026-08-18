# 61 — Prove long-campaign recovery and bounded context

**What to build:** Run a synthetic multi-role campaign long enough to force worker turnover, orchestrator rotation and repeated supervisor crashes, then prove the final truth matches an uninterrupted run.

**Blocked by:** 31 — Run a browser entirely through the proxy; 41 — Feed sound chain unlocks into Task ranking; 59 — Deliver the complete operator CLI.

**Status:** resolved

- [x] The fixture campaign exercises recon, browser and offline analysis, hunting, replay, validation, negative knowledge, pivot/chain scheduling, reporting and pending decisions.
- [x] Configured turn, token, decision and serialized-context ceilings force multiple fresh worker and orchestrator sessions.
- [x] Fault injection stops processes immediately before and after claim, Agent start, Tool start, Receipt write, promotion, validation, Halt and Lease release commits.
- [x] Every restart reconciles idempotently with no duplicate Events, fabricated attempts, stranded Leases, zombie runs or false terminal state.
- [x] Final canonical rows, integrity verdicts and reportable Findings/chains match an uninterrupted deterministic control run apart from expected run identifiers.
- [x] No correctness assertion depends on wall-clock sleeps, transcript replay or a model-authored summary.

## What was built

One case, `CampaignRecoveryTest`, two migrations the stops exposed, and one
production tolerance the second of them made dead. Two Programs are opened from
one configuration, the same campaign is run against both, one of them is stopped
either side of every commit the harness makes, and what the two hold at the end
is compared row for row.

**A stopped process is modelled as the one thing a stopped process is.** `Stopper`
sits in front of one connection: the statements before the named commit go
through, the commit itself goes through or does not, and every statement after
it raises. Nothing is faked about what the server then does with a transaction
whose client went away, because nothing has to be -- the connection is closed
and the work either committed or it did not. Which of the two happened is read
back off the stopper afterwards, so "stopped before the commit" is a fact about
the run rather than an intention of the fixture.

**Eight commits, sixteen stops, and three of them are made by nobody who
supervises.** Five are a supervisor's -- claim, orchestrator start, Tool start,
promotion, Lease release -- and are stopped in the pass that makes them. The
other three are the Receipt in the door, the verdict in the validator and the
Halt in the operator's console, and what they have in common is the whole
difference: the pass that finds out is not the pass that was stopped, because
no pass was. `finish_task_attempt` closes two of a pass's transactions and it is
the second that releases the Lease, so which occurrence is meant is part of
naming the commit rather than a detail of the stopper.

The eight are stopped by seven statements, because a worker Agent starting is
not a commit of its own: `claim_task` writes the Task's claim and the
`agent_runs` row that holds it in one statement, so the claim commit is the
worker's Agent start and the pair of stops either side of it is the pair the
criterion asks for. The Agent start named separately is the orchestrator's,
which is a commit somebody makes. That the two are one is asserted rather than
assumed -- every worker run in either campaign shares an `xact_id` with the Task
it holds -- because a schema that split them tomorrow would leave one of the
eight unstopped and nothing would say so.

**The Receipt hole is the one stop nothing recovers from, and the case says so
rather than working around it.** A door that dies between the bytes leaving and
the Receipt committing leaves a real hole in the record of what this machine
sent. `check_browser_runs` reports it, correctly, and it is corpus-wide rather
than Program-scoped -- so from the moment the hole exists no `rk run` against
any Program in the database will start. The phase therefore runs last, the
committed side first, and where a restart would be a lie the case asserts the
refusal instead: `test_the_one_thing_the_two_campaigns_do_not_agree_on_is_named`
holds `check_browser_runs()` to exactly one problem naming exactly that mission.
Recovery that mended this would be recovery fabricating a Receipt.

**Two clocks, one moved and one not.** The Lease TTL is half an hour, so a
restart that waited for it would be a test that took half an hour and a shorter
TTL would make every slow pass in the suite read as a crash. `elapse` moves
`lease_expires_at` and nothing else: `reconcile_leases` still reads the clock it
always reads and still decides for itself what a lapsed Lease means, which is
the half criterion 4 is about. It is the only fabricated fact in the case, it is
recorded per campaign in `cls.lapsed`, and the criterion 6 arm reads the class's
source together with the module-level pieces it is built out of -- the stopper,
the scripted child, the container stand-in -- because a wait written into one of
those is a wait the case depends on exactly as much as one written into an arm.

**What two campaigns can be asked to agree on.** Labels are per-Program
sequences, ids are per-row, digests over either are a third spelling of the same
thing, and the offline lane mints a nonce per run on top of all three. None of
them is knowledge, so `unnamed` takes them out and the comparison is made of
what a campaign is for: the claims it stated, the evidence it filed, the
Findings it settled, the verdicts, the routes it stamped and the questions it
left.

Every projection is DISTINCT because every projection is lossy: two Findings of
one campaign share a title, two Tests of one Hypothesis share a lane, and a
differential says the same sentence about the baseline of each. Rows that
project equal are ordinary and are not duplicates of anything. What would be a
duplicate is the two campaigns disagreeing about how many, so the multiplicity
DISTINCT sets aside is compared rather than dropped: the same projections
without it, campaign against campaign, in
`test_the_two_campaigns_recorded_each_thing_the_same_number_of_times`. They
agree table for table, which is the statement a set comparison on its own cannot
make -- a restart that recorded an Observation the first pass had already
recorded would be counted there and hidden here.

**"No fabricated attempt" is asked of the Tasks a scheduler handed out.** The
Tasks this case fabricates for the offline, browser and validation lanes are
left out on purpose: `claimed_agent_run` writes a claimed Task and its run in
one statement without going through `claim_task`, so its `attempts` is zero by
construction and would read as a run nobody counted. What the criterion is about
is exactly the Tasks the pass log names, and for those the count of runs equals
the count of attempts -- an attempt with no run behind it is work a Task was
charged for and never did, and a run with no attempt is a Task handed out
without being counted.

**Clearing a Halt is a revision too.** Two Halts leave a standing at revision 4,
not 2, and both campaigns reach the same pair. That is the assertion: the
stopped console's first Halt never reached the server, and the operator typing
it again is what makes the two ledgers the same length. Nothing in the harness
recovered it, and nothing should have -- a Halt is a person's decision and a
restart that re-raised one would be the harness deciding to stop itself.

**The judgement stop costs an attempt and not a truth.** A validator stopped
before its verdict commits leaves the Finding among the candidates and the
attempt `unanswered`; somebody asks again, the second validator files a verdict,
and the Finding ends `validated` in both campaigns off one attempt in the
control and two in the injected one. Asking again is `between` in `restart` --
a person's move, made after the machine has finished recovering, because a
restart that decided a Finding needed looking at again would be the harness
deciding what to believe.

**A restore has nothing left to be forgiven for.** The stops put a Receipt write
inside a subtransaction, and `emit_event` recorded `pg_current_xact_id()` --
which reports the parent's id, not the one that wrote the tuple -- so part (d)
of the event log check read a sound write as a row nobody accounted for.
`20260913T010000Z` records the row's own `xmin` instead and lets an event
account for its row when the event's own tuple carries that `xmin` too. A
restore rewrites a row and its event together, which is the same shape, so a
restored database now passes the check outright. `entitled_by_a_restore` was
built for the failure that no longer happens, and a tolerance that outlives its
false positive can only forgive a true one: it is gone, with the `restored=`
parameter that reached it from `rk db restore`, and the restore gates exactly as
`rk db verify` does. Ticket 03 and ADR 0002 record the supersession.

**A rotation is a ceiling and not a long campaign.** A session records the
numbers it was admitted under and the reason it closed, and the case reads both
back: the five numbers are the ones the campaign installed, and every session of
both campaigns ended on one of `turns`, `tokens` or `decisions`. Rotation on its
own would say the campaign was long, which is the thing this case has instead of
a real one.

**A recovery with nothing to recover does nothing, and writing is doing.**
Every restart above runs against wreckage, so each of them proves a recovery
rather than the absence of one. The word in criterion 4 is *idempotently*, and
what answers it is both verbs run once more over a campaign nothing has touched:
`resume_program` and `reconcile_leases`, every count they report zero, and the
Event log exactly as long afterwards as before. A sweep that settled a Task
already settled or released a Lease already released would write a row, a row
writes an Event, and that Event is the duplicate the criterion forbids -- told
apart from an honest second observation by the fact that nothing happened in
between. It runs before the door's death, because from the moment a request has
no Receipt nothing may start and a recovery asked to run then would be measuring
the refusal.

**A Task closed is a Task that earned it.** `done` because the runtime accepted
a structured result of it, `abandoned` for attempts because it has none left,
and recovery is the one place both are decided about work nobody was watching.
The first of the two is the bug this campaign found: a Task whose result had
already been accepted went back into the queue, and the campaign paid a second
attempt for knowledge it already had. `settle_recovered_tasks` makes the split
`finish_task_attempt` makes for one run, once, for a set of them; the arm holds
every terminal Task in both campaigns to the fact that closed it.

**The campaign ranks under the weights the corpus is standing on.** The ceiling
row is the active row with five session limits overridden, taken through
`jsonb_populate_record` rather than a hand-written column list: a list written
today omits every weight a later migration adds, and the omitted column arrives
at its default. `w_unlock` defaults to zero, so the first draft ranked the whole
campaign with the chain-unlock term switched off -- one of the three tickets
this one is blocked by, silently absent from the thing meant to exercise it. The
teardown stands back up the version that was standing when the case started
rather than version 1, for the same reason: the corpus arrives already
reweighted, and the case that hands the next one a scheduler nobody chose is
a case that reports its own damage as somebody else's failure.
