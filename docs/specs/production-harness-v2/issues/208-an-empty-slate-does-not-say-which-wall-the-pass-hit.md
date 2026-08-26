# 208 — An empty Slate does not say which wall the pass hit

**What to build:** A pass offered nothing says why it was offered nothing.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk2here`, 2026-08-26, immediately after ticket 207 released twelve parked
Tasks back onto the Slate. The whole sitting:

```
lap 01 -> nothing_to_execute | ok True | exit 0
STOPPING after 01: no work left
```

The report said, in full:

```
ASSERT slate True no Task is ready; nothing was claimed
```

`no work left`, with 685 Tasks pending.

## The reason, which was there to be asked for

`claimable_for(t, w)` is the predicate `offer_slate` filters on. Asked directly:

```
lane_tokens_reserved             653
hunt.hypothesis_not_testable      28
hunt.no_address                    6
perform.claim_not_testable         1
```

and the lanes behind it:

```
kind    token_budget   tokens_spent   tokens_free
recon    200000000      187846908      12153092
hunt     200000000      180832800      19167200
```

A claim reserves the worst case, and `run_tokens` is 20,000,000. Neither
working lane had one run's worth of ceiling left, so every Task in both was
unready. The Program's own total is 2,000,000,000, of which about 368,000,000
was spent -- so 1.6 billion tokens sat unspendable behind a per-lane ceiling
that said nothing about itself.

## Why the sentence mattered

"no Task is ready; nothing was claimed" is a true statement about the Slate and
a misleading one about the campaign. `hunt.sh` renders it as `no work left` and
stops, which is right for a campaign that finished and wrong for a campaign
that ran into a ceiling an operator can raise in one line of TOML. The two are
indistinguishable in the report, and the second is the one that needs a person.

Same shape as ticket 206: the mechanism was right and the word the driver loop
reads was wrong.

## What was changed

`Slice._unready` asks `claimable_for` over the Program's pending Tasks,
grouped, and appends the counts to the sentence:

```
no Task is ready; nothing was claimed; 653 lane_tokens_reserved,
28 hunt.hypothesis_not_testable, 6 hunt.no_address, 1 perform.claim_not_testable
```

A Program with nothing pending says `no Task is pending` instead, which is the
campaign that really is done.

The opening words are unchanged: three cases in the suite read them, and they
are the half that was never wrong.

Held and never failed, and a read that raises is swallowed: this is a sentence
about a pass that has already ended.

- [x] An empty Slate with pending Tasks names the refusals behind it, with counts.
- [x] An empty Slate with nothing pending says so.
- [x] The sentence still opens with the words the suite reads.
- [x] A failure to compute the reason does not turn a finished pass into a refusal.
