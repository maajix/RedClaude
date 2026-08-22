# 141 — A Test specification has no producer a hunt can reach

**What to build:** The writer that turns a testable Hypothesis into the `tests`
row the replay Lane runs, or the Contract that lets the role holding the claim
author one.

**Blocked by:** 140 — A testable Hypothesis never becomes a hunt Task. Until a
hunt Task is dispatched there is no run this writer would belong to.

**Status:** resolved

- [x] **The gap is stated where the audit could not see it.** `tests` has two
      `INSERT` statements in the corpus:
      `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1258`,
      which takes a Finding, and the standing-check fixture inside ticket 116's
      migration. `check_wiring`'s W6 arm counts `tests` as produced and is right
      to -- the rule it asks is whether a table has a producer, and this table
      has two. Neither is reachable from a hunt, which is a different question
      and one no gate asks. Whether W6 should ask it is part of this ticket's
      answer.
- [x] **The consequence is followed to the end before a shape is chosen.**
      `open_test_replay(p_agent_run_id, p_test_id, p_identity_slot)` takes a
      Test that already exists, so `rk test` cannot make one either.
      `testable -> testing` requires `runtime` and a Receipt, `testing ->
      supported` requires two supporting and one control Observation, and
      `propose_finding` refuses a claim that is not `supported`. So a Program
      with a perfectly good testable claim cannot reach a Finding by any route,
      and tickets 36 through 43 rest on a row that route would have written.
- [x] **The shape decision is made and written down.** A Test specification is
      immutable and its identity is its digest (`rk2_test_spec_digest`), it
      carries typed preconditions, setup, actions, assertions and cleanup
      (`rk2_test_spec_problem` refuses a key it has no part for), and ticket 35
      built the Lane that runs one. Who authors it is the open question: the
      model that holds the claim, through a Contract in `state.propose` shaped
      like `propose_finding`; or the runtime, deriving a specification from the
      Playbook the Task was selected under. The second is only available where a
      Playbook was selected, and no Playbook has ever been selected in this tree
      (ticket 101), so a derivation-only answer would ship a path nothing
      exercises.
- [x] **A refused specification says which of the thirty rules it broke.**
      `rk2_test_spec_problem` is a function rather than a CHECK for exactly this
      reason, and whatever authors a Test has to carry that sentence back to
      whoever wrote the specification rather than raising a constraint name.
- [ ] **Checked by something that would go red.** A test that stages a testable
      Hypothesis, authors a specification through whichever door this ticket
      builds, and asserts the `tests` row and the refusal path both.

## Why

Measured on 2026-08-22 against a copy of a live hunt database. A well-formed
Hypothesis promotes cleanly and lands at `proposed`. Moved to `testable` by hand
it is schedulable: `ready_for` on a hunt Task naming it answers NULL, and
`roster.ROLES['web_hunter']` holds both the `hunt` kind and
`mcp__rk2__http_request`, so the dispatch would work. What the dispatched run
cannot do is file the specification that would settle the claim -- the roster
serves nineteen Contracts and not one of them writes a `tests` row.

This is the third break in the same loop, and it is the last one before a
Finding. Ticket 139 asks a recon run for the claim it may file; ticket 140 grades
that claim testable and turns it into work; this ticket is what the work does
when it gets there.

## Answer

**The shape: a Contract, not a derivation.** `mcp__rk2__propose_test` in
`state.propose`, direction `request`, writing `test_proposals` -- the same
two-step `propose_finding` takes and for the same rule, one step earlier in the
same chain. `tests` is in `roster.CANONICAL`, so `_check_contracts` refuses any
Contract naming it in `writes`; what the tool writes is the audit row beside it
and `propose_test(text, jsonb, uuid)` decides whether a Test comes of the ask.

The alternative the ticket names -- the runtime deriving a specification from the
Playbook the Task was selected under -- was rejected on the ticket's own
measurement: `playbook_selections` has never held a row (ticket 101), so a
derivation-only answer ships a producer nothing exercises, which is this
ticket's defect reached by another road. The two are not exclusive, and the
half built here is the half both would share: a derivation added later writes
its rows through `propose_test` like any other caller, because what decides
whether a `tests` row exists is the verb and not who called it.

**Five arguments and not one `spec` object.** A single object would have to be
`free_text` -- there is no `element` for an object -- and `OPEN_ARGUMENTS` would
have to say why the most consequential document on this surface is the one the
roster describes least. Five arrays name the five parts `rk2_test_spec_problem`
closes, so a sixth is refused by `additionalProperties: false`, and each closed
vocabulary is served as an `Argument.element` enum the CLI checks before
`PreToolUse` runs. `impact` and `pivot` are stored parts and are deliberately
not arguments: an impact block is what an operator's grant is measured against
and a pivot block claims a capability, so a model that could write either would
be authorizing its own impact.

**Only the vocabularies are in the schema.** Everything else the shape rule says
-- absolute canonical urls, an action numbered by its position, no two assertions
sharing an identifier, all three roles present -- stays where the sentence is.
This is the opposite of the trade `submit_mission_result` makes and it is the
same reasoning: there, a rule the schema cannot see costs one element in a
`proposal_drops` row written after the run ended, so refusing early is worth a
retry; here the answer arrives while the run is still going and names which of
the thirty rules broke, which is strictly more than a rejected call quoting a
regex can say.

**The bound.** `_launch.REFUSED_SPECIFICATIONS = 6`, derived the way
`REFUSED_PROPOSALS = 3` is but from the other end. Three is "one more than the
number of correctable mistakes" because six of `rk2_finding_refusal`'s eight
arms are about evidence. Here almost every refusal is correctable, so the bound
is how many times a converging run can be told something new:
`rk2_test_spec_problem` answers with the *first* problem and walks five parts in
a fixed order, so a run fixing one refusal at a time learns at most one thing
per part, and six is one more than five. A created or existing outcome is not
counted, and `tests_hypothesis_id_spec_sha256_key` already bounds the only way a
run could repeat itself successfully.

**W6 is right and this ticket does not change it.** The rule W6 asks is whether
a table has a producer, and `tests` had two. "Reachable from a run" is a
different question; the gate that could ask it is W3's reachability walk with
the Contract surface as a root rather than the whole package's name set, and
that is a change to `check_wiring` this ticket did not make.

### What was built

| file | what |
|---|---|
| `src/redkraken/roster.py` | five vocabulary constants, the Contract, `PROPOSE_TEST`, `minItems`/`maxItems` for a bounded array |
| `src/redkraken/_launch.py` | `Specification`, `REFUSED_SPECIFICATIONS`, `SPENT_SPECIFICATIONS`, `SPECIFICATION_PARTS`, the description and the handler |
| `src/redkraken/migrations/20261010T000000Z__a_hunt_files_the_test_that_would_settle_its_claim.sql` | `test_proposals` and `propose_test` |
| `tests/test_specification.py` | 28 tests: the contract, the gate, the ask and the corpus |
| `tests/test_roster.py` | the vocabulary drift extraction for the four `rk2_test_*` functions, and the element-enum wiring test widened from one contract to all |

### What is still owed

1. **`src/redkraken/agent.py` has no dispatch arm for the verb.** `_Tools.__call__`
   dispatches on a closed list of six and `roster.PROPOSE_TEST` is not on it, so
   the call answers `unknown_call` until the arm lands. The child side, the
   roster, the schema, the gate, the table and the verb are all in place.
2. **The database test.** The last criterion asks for a test that stages a
   testable Hypothesis, authors a specification and asserts both the `tests` row
   and the refusal path. That test belongs in `tests/test_database.py` beside
   `ReplayTestRunTest`, which is the only module with a server. It was validated
   by hand against `rk2probe` -- all four refusal sentences, `created`, `existing`,
   and the authored Test accepted by `open_test_replay` with `decision: allow` --
   but it is not yet a test that would go red.
3. **A pre-existing defect this work surfaced.** `Channel.call` writes
   `{**arguments, "verb": verb}` and `isolation` hands that object through
   unchanged, so a contract's arguments arrive flat. `_Tools.__call__` reads
   `call.get("arguments")` for both `propose_finding` and `mint_callback`, which
   is `None` in production: every Finding proposal a real run has made was
   carried to `propose_finding` as three empty strings. The supervisor-side tests
   pass because they feed a nested `arguments` key the child never sends.
