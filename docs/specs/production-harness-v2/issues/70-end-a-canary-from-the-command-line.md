# 70 — End a canary from the command line

**What to build:** `rk callback clear`, so ending a correlator early is a verb rather than SQL on the runtime connection.

**Blocked by:** 14 — Accept one explicitly configured callback Observation.

**Status:** resolved

**Reading on the How:** as written, with one thing the How left implicit made
explicit. The How says the report carries the channel and the interaction count
"when the correlator was this Program's", which means the answer has to say
whether it was -- so the report carries `known` alongside `cleared`. Without it,
the second clear of a canary and a mistyped id are the same two `false`s, and
telling those apart is the whole of criterion 1's second half.

- [x] An operator can clear one correlator by id, and a second clear says it changed nothing. `callback.clear` answers `cleared: true` the first time and `cleared: false, known: true` the second, and the ended canary admits nothing after. `CallbackAdmissionTest.test_a_canary_ends_by_verb_and_the_verb_says_what_it_caught` and `.test_ending_a_canary_that_is_already_over_changes_nothing_and_says_so`.
- [x] Clearing another Program's correlator answers the same as clearing an unknown one. Identical facts but for the id echoed back, and the foreign canary is still live afterwards: `CallbackAdmissionTest.test_another_programs_canary_is_answered_as_one_that_never_existed`.
- [x] The report names the channel and how many arrivals the correlator had already admitted. `channel` and `interactions`, counted per correlator rather than per Program, which the first test holds by minting two canaries under one Program and clearing one.

## Why

`clear_callback_correlator(uuid)` exists, works, and is described in its own
comment as the operator's way to end a canary early -- when the test that carried
it is over, or when the payload turns out to have gone somewhere it should not
have. `rk callback` offers `provision` and `accept` and nothing else, so using it
means opening a runtime connection by hand and remembering to
`set_config('rk2.program_id', ...)` first, because the function filters on
`rk2_program()` and silently answers `false` without it. That was measured on
2026-08-12: the first call returned `false` for a correlator that existed, for
exactly that reason.

The second half of the argument is the one that matters. The reason to clear a
correlator early is usually that a payload leaked somewhere it should not have,
which is the moment nobody should be composing SQL.

## How

`rk callback clear --config <path> --correlator <uuid>`, on the runtime
connection, binding the Program the configuration names before calling the
function. The report carries `cleared: true|false` and, when the correlator was
this Program's, the channel it was minted on and the number of interactions
already filed under it -- an operator ending a canary in a hurry should see
whether it had already fired.

Nothing about the correlator's plaintext is involved: it is cleared by row id,
which is what `rk callback provision` already prints.

## What was built

**The function answers `jsonb` instead of `boolean`.** Which is why
`20260911T000000Z__a_canary_ends_by_verb.sql` drops and recreates it rather than
replacing it: a return type is not something `CREATE OR REPLACE FUNCTION` may
change. Nothing in the tree read the boolean; the one caller that existed is a
test that discards it.

**Dropping a function drops its grants, so the file re-asks both directions.**
`check_callback_admission()` is the negative half -- no keyholder may execute
the four callback verbs -- and on its own it would have let a forgotten `GRANT`
through green, because its one positive arm is about a different function. So
`check_runtime_privileges()` runs beside it: `runtime_verb_surface` has carried
a row for `clear_callback_correlator(uuid)` since 66, and arm 5 is exactly "a
declared verb the runtime cannot execute".

**One statement rather than a read and then a write.** The scoping predicate is
a CTE used by both halves, so it is written once, and the count is taken in the
same statement that does the clearing: an arrival landing between two statements
would be a report saying this canary was ended having admitted a number that was
already stale.

**`cleared` and `known` are two different facts.** `cleared` is what this call
did; `known` is what it found. They differ exactly on the second clear of a
canary this Program minted, which is the case an operator re-running the command
after a crash is in, and it is the one that must not read the same as having
named an id nobody minted.

**A foreign canary is answered as an absent one.** One read, scoped the way the
UPDATE is scoped, so a correlator of another Program leaves every value NULL --
the same values an id nobody minted leaves. A verb that said "not yours" for one
and "no such thing" for the other would be a way for a compromised run to
enumerate another Program's canaries, and the Program doing the asking is the one
that run is bound to. The test asserts the two answers are equal rather than
merely both unsuccessful.

**The count is the correlator's, not the Program's.** `count(*)` over
`callback_interactions` filtered on that correlator id. One canary firing must
not make another look like it did, which the test holds by minting two under one
Program.

**The plaintext is a shape this verb cannot refuse.** A correlator is 16 bytes of
hex, and so is a UUID with its dashes removed, so `uuid.UUID` reads the plaintext
of a canary as an identifier. `_identifier` therefore refuses only what is not a
UUID at all -- the address, a word, a truncated token -- and a plaintext that
happens to parse reaches the database, matches no row, and comes back as the
answer an unknown id gets. Refusing it on shape would mean refusing ids that are
real. Held in two halves, because it is two claims:
`ClearTest.test_the_correlator_plaintext_is_a_shape_this_verb_cannot_refuse` says
it gets past the shape gate, and the third case of
`CallbackAdmissionTest.test_another_programs_canary_is_answered_as_one_that_never_existed`
-- the minting Program asking about its own canary by plaintext -- says what the
database then answers.

**What this does not do.** It does not clear by address, by channel, or in bulk.
Ending every canary of a Program is `program purge`'s business or the expiry's;
a verb that took a channel name would be one keystroke away from ending every
canary of a live engagement, and the reason to reach for this verb is that one
specific payload went somewhere it should not have.

**Measured:** `tests.test_callback`, `tests.test_cli` and
`CallbackAdmissionTest` -- `Ran 197 tests`, `OK`. Full suite and the three
offline gates green.
