# 67 — Give an inbound arrival its own identity

**What to build:** Make one recorded out-of-band arrival resolve to one Interaction and one Observation however many times it is handed to `rk callback accept`, so a file an operator replays cannot become a second fact about a target.

**Blocked by:** 14 — Accept one explicitly configured callback Observation.

**Status:** ready-for-agent

- [ ] Accepting the same recorded arrival twice writes one `callback_interactions` row and one Observation, and the second call says so.
- [ ] The listener's own timestamp is what the row is filed under, not the moment the operator got round to accepting it.
- [ ] Two genuinely separate arrivals that agree in every other respect stay two rows.
- [ ] The uniqueness is a constraint in the schema, not a check the writer makes.

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
