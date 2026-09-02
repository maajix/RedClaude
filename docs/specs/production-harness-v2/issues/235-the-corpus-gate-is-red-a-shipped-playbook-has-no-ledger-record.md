# 235 — The corpus gate is red: a shipped Playbook has no ledger record

**What to build:** Either the missing `payment-webhooks` records in
`baseline/technique-ledger.jsonl`, or the rule that says a Playbook may ship
without them. The corpus gate refuses the tree as it stands.

**Blocked by:** nothing.

**Status:** ready-for-agent

**PRODUCES:** new -- either `payment-webhooks` records in the technique ledger,
or a written rule admitting a Playbook that has none.

**CONSUMED BY:** `tools/check_intake.py::check_techniques`, reading
`no ledger record is about playbook`; `tests.test_intake.LedgerCorpusTest`,
which is red on this account today.

**CONSUMES:** `baseline/technique-ledger.jsonl`,
`src/redkraken/playbooks/payment-webhooks/playbook.md` (shipped by ticket 231).

**Touches:** `baseline/technique-ledger.jsonl`, `tools/check_intake.py`.


## What was measured

Measured on 2026-09-02 on commit `1ba74ee9` with every other change stashed, so
this is the tree and not somebody's working copy:

```
uv run python -m unittest tests.test_intake.LedgerCorpusTest
  ERROR: setUpClass
  tools.check_intake.IntakeError: no ledger record is about playbook payment-webhooks

grep -c '"playbook": "payment-webhooks"' baseline/technique-ledger.jsonl   0
ls -d src/redkraken/playbooks/payment-webhooks                             exists
```

`check_techniques()` is the corpus gate and it raises, so the failure is not
confined to one test module: the gate is part of the release gate, and it
refuses before it grades anything else.

`payment-webhooks` ships as a Playbook. The ledger was last written by
`61e3dd7a`, and the Playbook arrived after it.

Three more tests fail for the same reason, found on 2026-09-02 by running every
module except `tests/test_database.py`. All four reds are one Playbook arriving
without the bookkeeping that follows a Playbook:

```
tests.test_okf.BundleTest.test_every_playbook_skill_and_reference_is_a_concept
  AssertionError: 50 != 51                       (playbook.PLAYBOOKS is pinned at 50)
tests.test_okf.BundleTest.test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar
  AssertionError: 141 != 144                     (three more frontmatter blocks)
tests.test_okf.FreezeTest.test_the_committed_bundle_is_current
  the committed bundle holds different files     (playbooks/payment-webhooks.md is not in it)
```

Two of those are pinned counts and one is the frozen OKF bundle, so the repair
is the same shape in all three: the bundle is rebuilt and the numbers are
re-measured, in the change that adds the ledger records.

## Acceptance criteria

- [ ] **The gate passes.** `tests.test_intake.LedgerCorpusTest` runs its tests
      rather than erroring in `setUpClass`.
- [ ] **What was decided is written down.** Either the records exist and cite
      real sources the way every other record does, or the gate states in one
      sentence which Playbooks it does not require a record for and why.
- [ ] **The bundle and the counts follow the corpus.** `tests.test_okf` is
      green: the frozen bundle holds `playbooks/payment-webhooks.md`, and the
      two pinned numbers are the tree's own.
- [ ] **The next Playbook cannot arrive the same way.** Whatever ships a
      Playbook is held to the rule, so a corpus addition that skips the ledger
      fails at the time it is made rather than on somebody else's test run.
