# 235 — The corpus gate is red: a shipped Playbook has no ledger record

**What to build:** Either the missing `payment-webhooks` records in
`baseline/technique-ledger.jsonl`, or the rule that says a Playbook may ship
without them. The corpus gate refuses the tree as it stands.

**Blocked by:** nothing.

**Status:** ready-for-agent

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

## Acceptance criteria

- [ ] **The gate passes.** `tests.test_intake.LedgerCorpusTest` runs its tests
      rather than erroring in `setUpClass`.
- [ ] **What was decided is written down.** Either the records exist and cite
      real sources the way every other record does, or the gate states in one
      sentence which Playbooks it does not require a record for and why.
- [ ] **The next Playbook cannot arrive the same way.** Whatever ships a
      Playbook is held to the rule, so a corpus addition that skips the ledger
      fails at the time it is made rather than on somebody else's test run.
