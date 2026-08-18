# 67 — Give an inbound arrival its own identity

**What to build:** Make one recorded out-of-band arrival resolve to one Interaction and one Observation however many times it is handed to `rk callback accept`, so a file an operator replays cannot become a second fact about a target.

**Blocked by:** 14 — Accept one explicitly configured callback Observation.

**Status:** resolved

**Reading on the How:** all three steps as written, with one correction and one
extension. The correction: the How says the moment "falls back to
`clock_timestamp()` when a caller has none", and it cannot -- the column's
DEFAULT was `now()`, and `enforce_callback_attribution` refuses any arrival whose
moment is after `now()`, so `clock_timestamp()` refuses every plain accept.
Measured, before the fallback was `now()`: `callback interaction claims to have
arrived at 2026-08-18 07:29:35.00378+00, outside its correlator's lifetime`, on
an arrival being accepted at that instant. The extension: the Observation's
`observed_at` moved onto the same moment, because two halves of one event that
disagree about when it happened are a record no reader can order.

- [x] Accepting the same recorded arrival twice writes one `callback_interactions` row and one Observation, and the second call says so. `record_callback_interaction` inserts `ON CONFLICT ON CONSTRAINT callback_interactions_arrival_key DO NOTHING` and, when nothing was inserted, resolves the rows already there and answers `duplicate: true` without writing an Observation; `rk callback accept` holds rather than refuses, naming the arrival it resolved to. `CallbackAdmissionTest.test_one_recording_is_one_arrival_however_often_it_is_handed_over`.
- [x] The listener's own timestamp is what the row is filed under, not the moment the operator got round to accepting it. `p_arrival ->> 'received_at'` when the caller states one, `now()` when they do not; `--at` carries it in. `CallbackAdmissionTest.test_the_arrival_is_filed_under_the_moment_the_listener_recorded` compares in SQL, so the assertion is not about anybody's `DateStyle`, and `MomentTest` holds the spelling this side of the wire.
- [x] Two genuinely separate arrivals that agree in every other respect stay two rows. One microsecond apart is two arrivals and two Observations: `CallbackAdmissionTest.test_two_arrivals_that_agree_but_for_the_moment_stay_two_arrivals`.
- [x] The uniqueness is a constraint in the schema, not a check the writer makes. A hand-written INSERT that reaches past the function is answered `23505` naming `callback_interactions_arrival_key`: `CallbackAdmissionTest.test_the_identity_of_an_arrival_is_a_constraint_and_not_a_writer_rule`.

## Why

Measured on a live installation, 2026-08-12, against a real interactsh arrival:
`rk callback accept` on the same file, same host, twice, produced `CB1`/`O1` and
then `CB3`/`O3`. The artifact was reused -- the store is content-addressed, so the
second call answered `stored: false` -- but the Interaction and the Observation
are new rows. Two Observations then claim two arrivals where the listener
recorded one.

Nothing in an arrival is currently treated as an identity.
`callback_interactions` keys on `id` and carries `received_at DEFAULT now()`, so
the same bytes at the same name under the same correlator differ only in a
timestamp the caller never stated. The schema's own words are that an arrival is
admitted by a live correlator on a declared channel; it never says how many times
one arrival may be admitted.

This matters more than a duplicate row usually would. A callback Observation is
the confirming half of a Hypothesis about an out-of-band interaction, and "the
canary fired twice" is a different claim about the target than "the canary
fired". An operator who re-runs a command after a crash should not be able to
manufacture the stronger claim by accident.

## What an arrival is

One Program, one correlator, the name it arrived at, the exact bytes and the
moment the listener recorded it. Those five facts are the row's identity:

    UNIQUE (program_id, correlator_id, arrival_kind, observed_host,
            body_sha256, received_at)

`received_at` has to become the listener's timestamp for that key to mean
anything -- with the default it is the acceptance time, which is precisely what
differs between an arrival and its replay. It arrives through `p_arrival ->>
'received_at'`, falls back to `clock_timestamp()` when a caller has none, and is
already fenced by `enforce_callback_attribution`: an arrival claiming a moment
before its correlator was minted, after it expired, or in the future is refused
today and stays refused.

Two real arrivals a resolver made in the same second, at the same name, with
byte-identical requests would collapse into one row. That is the right trade: the
harness would be recording that this canary fired, which it did, and the
alternative is a schema in which no replay is distinguishable from a fact.

## How

1. **Schema.** New migration: the unique constraint above, and
   `record_callback_interaction` honouring `p_arrival ->> 'received_at'`. The
   insert becomes `ON CONFLICT ON CONSTRAINT callback_interactions_arrival_key DO
   NOTHING`; when nothing was inserted the function selects the row that is
   already there, together with the Observation derived from it, and returns it
   with `"duplicate": true`. No Observation is written on that path.
2. **CLI.** `rk callback accept` grows `--at <timestamp>` and passes it through.
   The interactsh and tunnel record formats both carry one, so the operator-facing
   path is a flag on the verb rather than a new file format. The report gains
   `duplicate`, and the assertion says which arrival the call resolved to.
3. **Docs.** Ticket 14's acceptance list gains the replay case.

## Prototyped

Against the throwaway database of the 2026-08-12 live run, with the constraint
and the rewritten function installed: one minted correlator, one arrival record
with a fixed `received_at`, accepted three times.

    attempt 1: CB7 / O7 duplicate=False
    attempt 2: CB7 / O7 duplicate=True
    attempt 3: CB7 / O7 duplicate=True
    interactions: 1 observations: 1

`ON CONFLICT DO NOTHING` sits under the `ENABLE ALWAYS` attribution trigger
without a fight: the trigger is `BEFORE INSERT`, runs before the conflict is
detected, and the immutability trigger is never reached because nothing is
updated.

## What was built

**One constraint, six columns.** `callback_interactions_arrival_key` over
`(program_id, correlator_id, arrival_kind, observed_host, body_sha256,
received_at)`. `peer_class` is deliberately not in it: it is what the listener
made of the peer, and two recordings of one arrival that disagree about it are
still one arrival. Nothing pre-existing can collide, because every row written
before this migration took `received_at` from the column DEFAULT and no two of
those share a moment.

**`ON CONFLICT ON CONSTRAINT`, not bare `ON CONFLICT`.** Named, so that a
collision on `label` -- a different accident entirely -- still raises instead of
being swallowed as a replay. The cost is a burnt label number per replay:
`assign_label()` is a BEFORE INSERT trigger, it runs before the conflict is
detected, and the counter it bumps is not rolled back. Gaps in `CB<n>` are the
price of the constraint being what decides, and nothing reads a label as a count.

**One answer for both paths.** The function branches on whether its own INSERT
returned a row and shares a single `RETURN`, so the duplicate answer cannot drift
from the fresh one. What differs is `duplicate` and whether an Observation was
written.

**The race is reported, not papered over.** If the insert loses to a transaction
this one cannot see -- any isolation above READ COMMITTED -- the recovery SELECT
finds nothing. That raises `40001`, the class a caller retries, rather than
returning a row that is not there.

**What this does not do.** A replay handed over after the correlator has expired
is still refused by `resolve_callback_correlator`, before the constraint is
reached. That is deliberate: an expired canary admits nothing, which is ticket
14's invariant, and refusing the late replay produces no second fact about the
target -- the first arrival is already on the record. Idempotence is bounded by
the correlator's lifetime.

**Measured:** the callback slice -- `CallbackAdmissionTest`, `ArtifactStoreTest`
and `tests.test_callback` -- `Ran 69 tests`, `OK`. Full suite and the three
offline gates green.
