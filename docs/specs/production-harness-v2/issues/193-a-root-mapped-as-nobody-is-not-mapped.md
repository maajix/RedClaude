# 193 — A root mapped as nobody is not mapped

**What to build:** Recon novelty counts what has been claimed in the state the Task will run in, not what has been claimed about the host by anyone.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** Database `rk2here`, 2026-08-25,
      eleven laps after ticket 191 put both states on the queue. Every one of
      the 453 Receipts was still anonymous, and all 255 authenticated Tasks sat
      `pending` and ready. The ranking says why:

      ```
      slot_name      | count | nov_min | nov_max | safe_min | safe_max | cost_min | cost_max
      _anonymous     |    83 | 1.000   | 1.000   | 0.3667   | 0.3667   | 0.29921  | 0.29921
      here-primary   |   108 | 0.625   | 1.000   | 0.3667   | 0.3667   | 0.29921  | 0.29921
      here-secondary |   108 | 0.625   | 1.000   | 0.3667   | 0.3667   | 0.29921  | 0.29921
      ```

      Every component but novelty is byte-identical across the three states.
      With `slate_size = 5` and ties broken by age, the older anonymous Tasks
      took every slate, forever.

- [x] **The arm that did it.** `novelty_for`'s recon arm is
      `1.0 - claimed families / all families`, and it counted claims by
      `hypotheses.subject_entity_id` alone. A host walked as nobody therefore
      discounted the signed-in Task for the same host — the harness read "we
      know this root" from a walk that had never seen the signed-in surface.

- [x] **The count is keyed by state.** The arm now only counts a claim whose
      provenance leads back to a Task that selected the same Identity:
      `hypothesis_provenance` → `agent_runs` → `tasks.selected_identity_entity_id`.
      That chain is the only route there is from a claim back to the state it
      was reached in.

- [x] **Guarded in the migration.** An unclaimed subject is still novelty 1.0
      in every state, and no recon Task is discounted for another state's
      claims.

## Why

Ticket 191 made the work exist. It did not make the work reachable: derived
Tasks that never outrank anything are the same as Tasks that were never
derived, and eleven laps of a live engagement went by proving it.

The deeper point is what novelty is for. It is the harness's answer to "have we
already looked at this", and looking is done from somewhere. Two states of the
same host are two surfaces, and a count that cannot tell them apart will always
report the second one as already seen.

## What this does not change

Ranking otherwise. Safety, cost and age are untouched, and the anonymous Tasks
on unclaimed hosts still rank exactly where they did.
