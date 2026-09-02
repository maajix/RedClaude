# 219 — One hunt per machine is the Agent network's rule, not the scheduler's

**What to build:** Either a per-launch Agent boundary, so a second `rk run` on
one machine gets its own internal network and door, or the sentence in
`hunt.sh` that says a second worker cannot exist. Today the scheduler invites
concurrency the isolation layer refuses, and the refusal arrives three laps
into a hunt.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`claim_task` is built for concurrent callers and says so
(`0023_scheduler_ranking.sql:841-851`):

> `pg_advisory_xact_lock(program)` serialises the counting window. It is the
> same lock the loop already holds per program ... so this function is safe
> whether the caller is the loop or a second runtime process.

The roster agrees. `roles.max_concurrent` is 2 for `web_hunter` and 2 for
`js_analyst`, `scheduler_weights.max_concurrent_subagents` is 3, and the
`rk2here` queue on 2026-08-29 held 548 `hunt`, 215 `recon` and 1 `perform` --
work for all three lanes at once.

Three `hunt.sh` workers were started against that queue. Two died on lap 3 and
the third lost its first lap:

```
lap 01 -> refused | ok False | exit 3
lap 02 -> refused | ok False | exit 3
lap 03 -> refused | ok False | exit 3
STOPPING after 03: 3 laps in a row exited non-zero
```

```
invalid_configuration | door | no Agent run was started because the Door and
  runtime could not be matched to this Program: the Agent network has peers
  other than the proxy: rk2-agent-fe6a805d06694c5baba7a25bf397c44f
invalid_configuration | environment:RK_AGENT_IMAGE | the Agent boundary could
  not be provided to choose in: another launch on this machine holds the Agent
  network: rk2here-agent
```

Two guards, both deliberate, both in `isolation.py`:

- `one_peer` (`:1738-1764`) refuses when the Agent network carries any peer
  besides the door. A second child on that network is a child the first one can
  address, which is the property the internal network exists to deny.
- `hold_network` (`:1391-1412`) takes an exclusive `flock` named by the
  network's digest, so a second launch is refused "a moment earlier" than
  `one_peer` would refuse it. Its own words: "Refused rather than queued. A
  launch that waited would hold a claimed Task open for as long as the child in
  front of it runs."

Both are right. Neither is discoverable from the scheduler side, which is the
whole ticket.

## The wall, priced

```
WALL    isolation.py:1391-1412 (`hold_network`) and :1738-1764 (`one_peer`).
        One `$RK_AGENT_NETWORK` per installation, one child on it at a time,
        enforced twice. Read in source 2026-08-29; both ends read -- the
        launcher that takes the claim and the topology check that would catch
        it if the claim were skipped.
PRICE   Not one line. A second worker needs its own internal network, its own
        door container and its own host port, which is `setup.sh:29-38`
        parameterised and `here-env.sh` carrying `RK_AGENT_NETWORK`,
        `RK_AGENT_PROXY_CONTAINER`, `RK_PROXY_URL` and `RK_AGENT_PROXY_URL`
        per worker. The database side is already built and needs nothing:
        `20260811T170000Z__egress_budget_at_the_door.sql:81` says the token
        bucket is "a row rather than process memory: two proxies serving one
        Program must see one bucket", so N doors against one Program already
        share one rate limit against the target. What is missing is the
        provisioning, not the accounting.
PURPOSE The hunt is here to find a Finding, not to run fast. A second worker
        is worth having and is worth nothing at all if standing it up widens
        the egress boundary, because the boundary is what makes the run
        publishable. So the fix is a real fix or it is the refusal, written
        where the operator reads it.
RULE    Capability before catalogue. The isolation is the capability. Nothing
        here is worked around: either a launch gets its own boundary, or one
        launch per machine is stated where `hunt-parallel.sh` would otherwise
        invite a second.
```

## Acceptance criteria

- [x] **A second launch on one machine either works or is refused before it
      starts.** Today it is refused on lap 1, after `rk run` has opened the
      Program, swept decisions and ranked the queue -- and the operator reads
      it three laps later as "3 laps in a row exited non-zero", which names the
      streak and not the cause.
- [x] **If per-launch boundaries are built, `one_peer` still holds for each
      one.** N networks, N doors, one child on each. A test that finds two
      children on one network fails.
- [x] **The shared token bucket is measured, not assumed.** Two doors against
      one Program, one target, and the count of admitted requests matches a
      single door's limit rather than twice it.
- [x] **`rk doctor` names the boundary a launch would take.** An operator
      asking whether a second worker can start should not have to read
      `isolation.py`.
- [x] **The engagement's `hunt-parallel.sh` stops inviting what cannot
      happen.** It was written on 2026-08-29 against the scheduler's
      concurrency and the roster's caps, both of which say three; it does not
      survive contact with the isolation layer.

## What this does not change

`hold_network` refusing rather than queueing, and `one_peer` refusing a second
child on one internal network. Both are the boundary a Finding is published
against.

## The decision, taken 2026-08-30

**The refusal, not the per-launch boundary.** The ticket offers two answers and
asks for one; this is the second.

The price of the first is what decided it. A second worker needs its own
internal network, its own door container and its own host port -- `setup.sh`
parameterised and four more variables per worker in `here-env.sh` -- and every
one of those is a second egress boundary to get right. The purpose line of this
ticket's own wall says why that matters: "a second worker is worth having and is
worth nothing at all if standing it up widens the egress boundary, because the
boundary is what makes the run publishable."

And throughput is not what this campaign is short of. `rk2here` holds nine
Findings and states no severity about any of them, because nothing validates one
(tickets 105, 224). A second worker would produce candidates faster and change
nothing about the number that reach `medium`.

So the rule is written where the operator meets it, and the per-launch boundary
is left unbuilt. Criteria 2 and 3 are conditional on building it -- "if
per-launch boundaries are built" -- and are checked off as not-applicable under
this decision rather than as work done.

## What was built, 2026-08-30

**`isolation.unclaimed(network)`** (`isolation.py`), beside `held`. It takes the
same claim and lets it go again, and answers the refusal `held` would have made
or nothing. A probe and not a guard: the window between this answer and the
`held` inside the launch belongs to nobody, and it is `held` that closes it.
What it buys is the word, one lap earlier than the refusal that means it.

**`cli._slice` asks it first.** Before the state URL, before the store, before
the Program is opened, before the queue is ranked and before a Task is claimed.
The refusal names the network and the remedy: "a second worker on this machine
needs its own network, its own door and its own host port". That is criterion 1
-- the same refusal, moved from lap 3 to lap 0.

**`rk doctor` reports the claim** and does not fail on it. A machine with a hunt
on it is a machine working; what the operator asking "can I start another one" is
owed is the fact. `agent_boundary` now ends either "and no launch holds it, so
one child may start on it" or "and a launch on this machine already holds it, so
a second `rk run` against it would be refused". That is criterion 4.

**`hunt-parallel.sh` is one worker.** It was a loop over `seq 1 $WORKERS`; it is
now `exec hunt.sh`, with the measurement and the price of the real fix in its
header. That is criterion 5.

## What was verified

- `tests/test_isolation.py::test_the_probe_answers_what_the_next_launch_would_find`
  -- a real second process holds the claim, the probe says the same word `held`
  would, and the probe lets the claim go again. That last half is the one failure
  a probe cannot have: a probe that kept the claim would refuse the launch it was
  asked on behalf of.
- `tests/test_cli.py::AgentNetworkClaimTest` -- two `rk run` processes, one real
  `flock`, one `XDG_RUNTIME_DIR`. The second is refused with `agent_network`
  naming the network and the remedy, and a run on a free network is refused for
  its own reasons and not for this one.
- `tests/test_doctor.py` -- the boundary is reported both ways and `doctor` stays
  green either way.

## What is still true

`hold_network` refuses rather than queues, and `one_peer` refuses a second child
on one internal network. Both are the boundary a Finding is published against,
and neither moved.
