# 204 — Two states of one claim halve every chain unlock

**What to build:** a chain unlock share divided by the claims that could supply
the requirement rather than by the Tasks, so that a Program able to work two
Identity states has twice the ways to pivot and not half the reason to.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`ChainUnlockTest` seeds two candidate claims that a sound chain is one
requirement short of, and asserts criterion 6: a useful low-cost pivot outranks
a Task no chain is waiting on. It did not.

```
pivot    priority 0.09840642827103532
isolated priority 0.10050018206403608
```

The pivot is worth 0.20 on its own against the isolated Task's 0.30, and the
whole of criterion 6 is that a full share of a `high` member — 0.75, at
`w_unlock` 0.5 — is what puts it in front. Half a share does not.

## The mechanism

`chain_unlock_for` divides a member's severity weight by

```sql
count(DISTINCT u2.task_id) ... WHERE k2.status = 'pending'
```

`20261120T000000Z` doubled that count. Ticket 191 made the hunt frontier a
(claim, Identity) pair rather than a claim, so a claim that names nobody owes
one hunt Task per state the Program can work — anonymous and each provisioned
account. Two Tasks, one claim. The divisor went from 2 to 4 and every share
halved.

The function's own comment says the weight is "shared between the pending Tasks
that could supply that requirement". What supplies the requirement is the claim
being settled. The two state Tasks are two ways of settling ONE claim, not two
ways of supplying the requirement — either one answers it, so they are
alternatives and not additions. Counting them apart says a Program that can work
two states has half the reason to pivot, which is the opposite of what having
two states is for.

## Answer

- [x] **`20261205T000000Z` divides by claims.** `count(DISTINCT
      coalesce(k2.hypothesis_id, u2.task_id))`. A Task with a Hypothesis is
      counted once per Hypothesis however many states it is worked in; a Task
      without one — a recon, a perform, a hunt nothing was derived for — is
      counted as itself, which is what it was counted as before.

- [x] **A one-state Program is unchanged.** One state is one Task per claim, so
      the two counts coincide and the expression computes exactly the number it
      computed before the file. The cap at one and every other term are
      untouched: what moves is the denominator, and only where 191 put more than
      one Task behind one claim.

- [x] **The row counts under it doubled, and that is correct.**
      `derive_chain_unlocks` writes one row per (Task, chain, capability, stamp),
      so two states of a claim carry two sets of rows — each Task individually
      could reach the member. `ChainUnlockTest` now expects four rather than two
      throughout, and asserts the share stayed a half through the doubling.

- [x] **The lag is named rather than fixed.** `rank_pass` runs
      `derive_chain_unlocks` before `derive_hypothesis_hunts`, so the pass that
      mints a candidate Task writes rows only for the state it minted itself, and
      the next pass writes the rows for the other state. It converges in one
      pass and nothing reads the intermediate state, so the order is left as it
      is and the fixture says why.

## Why

A ranking term that reverses its answer because the Program grew a second
Identity is a term that measures the harness rather than the campaign.
