# 115 — Re-issue the column comment migration 018 left behind

**What to build:** One `COMMENT ON COLUMN`, replacing a live piece of schema
documentation that a later migration made false.

**Blocked by:** nothing.

**Status:** resolved

- [x] The comment is replaced.
      `COMMENT ON COLUMN observation_kinds.allowed_provenance`, set at
      `0018_vocabularies.sql:269-270`, ends "see the out_of_band_interaction
      note in migration 018". That note (`0018_vocabularies.sql:251-267`) says
      the kind was rejected because its provenance set would be empty, and that
      "It goes back in when the collector that generates its provenance exists:
      a third `provenance_kind` ('oob_receipt') written by a runtime-controlled
      listener."
- [x] What actually shipped is named in the replacement.
      `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:336-341`
      dropped and re-added `observation_kinds_allowed_provenance_closed` to
      admit `'callback'`, and `:348-350` inserted `callback_interaction` with
      `allowed_provenance` of `{callback}`. The provenance kind that shipped is
      `callback`, not `oob_receipt`; the kind is live, is cited by the
      `webhooks` Playbook, and is written by `resolve_callback_arrival`. The
      comment sends a reader to a rejection that no longer holds.
- [x] The `--` comment inside 018 is left alone and the replacement says so. A
      comment inside a recorded migration cannot be edited, and the house
      standard for this is already set: `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:100-104`
      re-issues a `COMMENT ON COLUMN` it invalidated and states the reason --
      "The original is a `--` comment inside a recorded migration file, which
      cannot be edited."
- [x] The distinction that makes this worth a ticket is stated: a `--` comment
      in a migration is at least dated, and a live `COMMENT ON` presents as
      current schema documentation to anybody running `\d+ observation_kinds`.
      This is the second kind.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 6 grades this "stale, and
worse than the file comment", and its gate G8 is the mechanical rule that would
have caught it: a migration that changes a constraint, a default or a closed set
on a column must re-issue `COMMENT ON` for that column in the same file.
`20260812T040000Z` moved the constraint and left the comment.

Ticket 130 is where the rule goes. This ticket is the one instance it would
report today, fixed by hand so the gate lands green.

## What was built

One migration,
`20260926T000000Z__the_live_comment_names_the_provenance_that_shipped.sql`, and
nothing else. No constraint moves, no row is written and no vocabulary changes:
the only thing that was wrong was a sentence, and the sentence is the deliverable.

`COMMENT ON COLUMN observation_kinds.allowed_provenance` keeps the rule 018
wrote, because the rule is still the rule and it is why the kind was refused.
What it drops is the pointer. The new text carries its own example -- 018 refused
`out_of_band_interaction` because an inbound arrival crosses no proxy and
analyses no stored bytes, so it could name neither of the two provenance records
that existed then -- and then says what happened next: `20260812T040000Z` built
the third record, it is `callback`, `record_callback_interaction` writes it for
an arrival on a channel the Program declared, and `callback_interaction` is
admitted on `{callback}` alone so a Receipt cannot inherit the weight of an
out-of-band confirmation. A reader of `\d+ observation_kinds` is told the
outcome instead of being sent to the argument.

The `--` note inside 018 stays exactly where it is. A recorded migration whose
file has changed is schema drift and `rk db migrate` refuses the whole corpus for
it, so the correction had to arrive as a new file whichever comment it was about.
What makes the live comment the one worth a migration is that it has no date on
it: the note is dated by the file it sits in, and a `COMMENT ON` presents as
current schema documentation to anyone reading the running database.

## What the migration's own `DO` block asserts, and what it does not

The block at the end of the file refuses to finish unless every clause of the new
sentence is true of the catalogue it describes. It asks the database, not this
file:

* the live comment on the column no longer sends a reader to the rejection;
* no `observation_kinds` row admits an empty provenance set, which is the
  standing rule the first sentence states, asked of every row rather than of the
  one that prompted the ticket;
* `callback_interaction` exists and is admitted on `{callback}` and nothing else;
* `observations_provenance_kind_check` admits `callback`, so the kind above can
  actually be written;
* `record_callback_interaction(text,jsonb,jsonb)` exists, because a provenance
  kind nothing writes is the empty set the first sentence refuses, one layer up;
* and `oob_receipt` is still not a provenance kind, so the day it ships this file
  fails and this comment is re-issued again rather than quietly understating the
  vocabulary.

The block was watched failing before it was trusted: with 018's original comment
restored on a migrated database, it raises `23514: the column comment still
sends a reader to the rejection 20260812T040000Z overturned`.

Nothing here is asserted by `tests/test_database.py`. No case was added to that
file, and the coverage it would carry is the same list above run as part of the
suite rather than as part of the migration, plus the one thing a migration cannot
ask: that a corpus applied twice still ends with this comment rather than 018's.
That is owed.

## What the ticket got wrong

The rejection note is at `0018_vocabularies.sql:251-267` and the comment it
poisoned is at `:268-269`, one line earlier than the ticket and the research
reading both say.

The writer is `record_callback_interaction`, not `resolve_callback_arrival`.
There is no function of that name anywhere in the tree: `grep -rn
resolve_callback_arrival` finds only `docs/research/wiring/20-vocabulary-wiring.md`
and this ticket file, which took it from there. The corrected name is what the
new comment carries, because a provenance kind is only as real as the collector
that writes it and that name is what a reader greps for next.
