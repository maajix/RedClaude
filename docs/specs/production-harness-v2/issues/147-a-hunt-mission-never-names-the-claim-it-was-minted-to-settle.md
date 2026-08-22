# 147 — A hunt mission never names the claim it was minted to settle

**What to build:** The part of `MISSIONS['hunt']` that names the Hypothesis the
Task carries and asks for the Test that would settle it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt7`, 2026-08-22, five Tasks
      executed, every run `exit 0`. Two of them were hunts:

      ```
      label|kind|status|hypothesis_id
      T3   |hunt|done  |01a02a25-f2eb-7550-86c6-bdaa998b00ae
      T5   |hunt|done  |01a02a27-9646-73f2-a534-9bf2c6c483bd
      ```

      Both children were `web_hunter`, both `stop_reason = completed`, both
      promoted Observations, and both left:

      ```
      test          |0
      test_proposals|0
      finding       |0
      ```

      `web_hunter` holds `state.propose`, which carries
      `mcp__rk2__propose_test`. The packet carried the claim: run 02's sections
      read `"hypotheses": 1`, run 04's `"hypotheses": 2`. The tool was served,
      the claim was visible, and neither run called it.

      The whole hunt mission is one sentence:

      ```python
      # src/redkraken/execution.py:101
      "hunt": "Look for one exploitable weakness in this target.",
      ```

      It does not name the Hypothesis, does not say the Task exists to settle
      one, and does not mention `propose_test`. `tasks.hypothesis_id` is
      populated on both rows, so the runtime knows which claim each hunt is for
      and does not say so.

- [x] **The mission names the claim by its label.** Not the packet's list of
      what the Program holds -- the one claim this Task was minted against.
      Ticket 140's `derive_hypothesis_hunts` writes `tasks.hypothesis_id`
      precisely so that this is a lookup and not a guess.

- [x] **The mission asks for the Test.** A hunt that cannot demonstrate the
      weakness in its own turn budget should file the plan that would, which is
      what `propose_test` is for and what ticket 141 built. Today an
      unproven hunt files Observations and the claim stays `testable` forever.

- [x] **Checked by something that would go red.** A test that the hunt mission
      text contains the Task's hypothesis label, beside `test_the_recon_mission
      _asks_for_the_hypothesis` from ticket 139.

## Why

The same defect as ticket 139, one step later in the same chain. 139 found that
a recon mission never asked for the Hypothesis it was allowed to propose, and
fixing it turned a hunt that proposed nothing into one that proposed four
claims. This is the next link: the claim now reaches `testable`, ticket 140
mints the hunt, the hunt runs, and the chain stops because nothing asks the
hunter for the one artefact that would move the claim to `supported`.

Without it the pipeline is provably open-ended: `rk2hunt7` reached two testable
claims and zero Tests, so no claim can ever reach `supported` and no Finding can
ever be filed. This is the last structural gap between a working harness and a
harness that produces a result.

## What was built, 2026-08-22

Three edits, no migration: `tasks.hypothesis_id` already carried the claim, so
the label is a join and not a new column.

`STARTED` grew a fifteenth column and a `LEFT JOIN hypotheses`. Left, because
every kind but `hunt` has no claim and a hunt minted by anything other than
`derive_hypothesis_hunts` has none either -- an inner join would have made those
Tasks unreadable rather than unclaimed.

`Claimed.hypothesis_label` defaults to `None`, which keeps every existing caller
constructing the value without it.

`Claimed.objective` gained one paragraph, after the citation rule and before the
Playbooks, for the reason the Playbooks are last: the paragraph is what the run
is graded on. It names the claim twice -- once to say what the Task is for, once
inside the `propose_test` instruction -- because the second is the argument the
call needs and a model that read the first is not thereby holding it.

### The test that would go red

`ObjectiveTest`, three cases: a hunt with a claim is told its label and asked
for the Test; a hunt without one is told nothing about a Test; and a recon Task
carrying a claim is still not asked to settle it. Proof they would fail before
the change: `git show HEAD:src/redkraken/execution.py | grep -c propose_test`
answers `0`.

`started_row` grew the column so that `Claimed.from_row` is exercised on the
shape the query now returns. Ran 148 tests, OK.
