# Race conditions and timing attacks: one pack, two unrelated readings

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What v1 put in one folder

The v1 pack carried four things under one heading: a general note on races, user
enumeration via response timing, data exfiltration via response timing, and the
race-condition material itself. They sit together because a stopwatch is
involved in all four, and that is the only thing they have in common.

The split this corpus makes:

* **the race** -- two requests inside the check-to-write gap, and the target's
  own counter afterwards says the action applied twice. That is
  `business_logic.replay` and it is the Playbook this file is attached to.
* **the stopwatch readings** -- a response that takes longer for a real username
  than a fake one, or a response whose duration carries a bit of a secret. Those
  produce a `timing_differential` Observation and, where they resolve to a
  class, it is `information_disclosure.identifier_oracle` rather than anything in
  `business_logic`.

Keeping them apart is the whole point of the attached Playbook's step 5. A run
that shows two responses arriving 4ms apart has shown that two responses arrived
4ms apart.

## The gap, concretely

```
  read   balance = 100          <- request A
  read   balance = 100          <- request B, inside the gap
  write  balance = 100 - 100    <- A
  write  balance = 100 - 100    <- B
```

Both requests passed a check that was true when they read it. The window is
usually a database round trip, sometimes a cache lookup, occasionally a whole
external call. Anything that is "check, then act" with the two steps not made
atomic has this shape: coupon redemption, invite acceptance, withdrawal, seat
reservation, one-time token consumption, follow/unfollow counters, vote
counting, file upload quotas.

Applications that are correct close it with a lock held across both steps, a
unique constraint that makes the second write fail, or a conditional update
(`UPDATE ... WHERE used = false`) that does the check and the write in one
statement.

## Why the sequential control is not optional

The Playbook refuses to proceed without sending the action twice in sequence
first, and this is where most reported race findings fall apart. Three things it
rules out:

* the action was never single-use to begin with, so nothing was broken
* the second copy was accepted because a session, a nonce or a cart was
  refreshed between them, not because of concurrency
* the counter does not mean what the report assumed -- some counters are
  eventually consistent and move twice on their own

Once the sequential control shows attempt two refused with the count unmoved,
the concurrent pair has something to contradict.

## On the "send twenty" habit

The public technique writing favours large parallel bursts, single-packet
attacks and HTTP/2 frame tricks to shrink the arrival window. Those exist
because the window can be short. They are also indistinguishable from load, and
on a live bug-bounty target load is the thing most likely to get an engagement
stopped.

Two requests is what the attached Playbook sends, on purpose. If two do not land
inside the window, the reading is inconclusive and says so, and widening the
burst is a decision for a human with the Program's rules in front of them rather
than something a run does by itself.

## What is not this claim

* a `500` from the losing request. That is a crash, worth an `error_detail`
  reading, and not evidence the action applied twice
* two `200`s. A correct application may answer both and apply one
* a slower response under concurrency. That is capacity
* anything that races money out of an account, a payout, a transfer or a
  third-party notification. The Playbook stops at the sequential control there
  and reports that instead
