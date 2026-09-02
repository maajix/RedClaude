# 235 — The corpus gate is red: a shipped Playbook has no ledger record

**What to build:** Either the missing `payment-webhooks` records in
`baseline/technique-ledger.jsonl`, or the rule that says a Playbook may ship
without them. The corpus gate refuses the tree as it stands.

**Blocked by:** nothing.

**Status:** claimed

**Touches:** `baseline/technique-ledger.jsonl`, `baseline/technique-sources.tsv`,
`tools/check_intake.py`, `docs/okf/`.

**PRODUCES:** new -- the ledger records and source rows behind the
`payment-webhooks` Playbook, and the OKF bundle rebuilt over the corpus that
ships.

**CONSUMED BY:** `tools/check_intake.py::check_techniques`, reading
`no ledger record is about playbook` and its own `RECORDS` count;
`tests.test_okf`, which holds the frozen bundle and three counts to the corpus;
`tests.test_playbook.Corpus`, which is where this ticket puts the same rule so
the next Playbook's author reads it.

**CONSUMES:** `src/redkraken/playbooks/payment-webhooks/playbook.md` and its
`references/provider-webhook-contracts.md`, both written by ticket 231; the
provider documentation that note cites.


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

- [x] **The gate passes.** `tests.test_intake.LedgerCorpusTest` runs its tests
      rather than erroring in `setUpClass`.
- [x] **What was decided is written down.** Either the records exist and cite
      real sources the way every other record does, or the gate states in one
      sentence which Playbooks it does not require a record for and why.
- [x] **The bundle and the counts follow the corpus.** `tests.test_okf` is
      green: the frozen bundle holds `playbooks/payment-webhooks.md`, and the
      two pinned numbers are the tree's own.
- [x] **The next Playbook cannot arrive the same way.** Whatever ships a
      Playbook is held to the rule, so a corpus addition that skips the ledger
      fails at the time it is made rather than on somebody else's test run.

## Seam check, 2026-09-02

`PRODUCES:` four records `payment-webhooks/01`--`/04` in
`baseline/technique-ledger.jsonl`, eleven rows `S1525`--`S1535` in
`baseline/technique-sources.tsv`, and the OKF bundle under `docs/okf/`
regenerated over them.

`CONSUMED BY`, each opened rather than grepped:

- `tools/check_intake.py::check_techniques` -- reads the ledger through
  `read_records` and the table through `read_sources`, and its
  `no ledger record is about playbook <book>` line is the loop over
  `books - {record["playbook"] for record in sound}`. Run:
  `NO_COLOR=1 uv run python -m tools.check_intake` now prints
  `records 382 playbooks 51`, where it raised before. Far end **reached**.
- `tests.test_okf.FreezeTest.test_the_committed_bundle_is_current` -- compares
  `okf.build(ROOT)` against the committed files one by one. Far end **reached**:
  green only after `docs/okf/` was rewritten.
- `tests.test_playbook.Corpus.test_every_shipped_playbook_has_a_ledger_record_behind_it`
  -- new here, reads `check_intake.read_records()` and differences it against
  `playbook.PLAYBOOKS`. Far end **reached**, and proved by mutation rather than
  by its own green: with the four records stripped out of the ledger it printed
  `+ ['payment-webhooks'] : payment-webhooks ships with no record in
  technique-ledger.jsonl`.

`CONSUMES:` `src/redkraken/playbooks/payment-webhooks/playbook.md`, written by
ticket 231 in commit `1ba74ee9` and unmodified here -- the four records are
written *from* it, section by section, and the arms and hand-offs they name are
that document's own. `references/provider-webhook-contracts.md` from the same
commit supplied the twenty provider addresses the six fetched sources were
picked out of.

No `NOBODY`. The one far end that is not a symbol is the provider
documentation, and it is an address rather than a citation: six pages fetched
over HTTPS on 2026-09-02, each with the sha256 of the bytes that arrived
recorded in the source table.

## Build findings, 2026-09-02

**The records passed every rule in `record_error` on the first run.** The only
thing the gate then said was
`the reviewed corpus holds 378 records, and this one holds 382`, which is the
pinned count doing its job. Nothing in the record shape had to be argued with,
and that is a fact about `check_intake` rather than about this ticket: the rules
are strict enough to be followed and specific enough to be followable.

**Ticket 216's new rule was satisfied by writing, not by repair.** All four
records' `stop_conditions` name `mcp__rk2__park_for_human under question code
playbook_halt`, and `payment-webhooks/01` also names `credential_needed` for the
Playbook's arm 7. That rule landed four days ago in the same corpus gate; this
is the first corpus addition written under it.

**Two sources had to be re-fetched to be citable at all.**
`source_error` refuses a query string, so `docs.stripe.com/webhooks?lang=node`
is not an address this ledger takes and the page was re-fetched at
`docs.stripe.com/webhooks`. That fetch then came back in German, because the
page is served per `Accept-Language`: it was fetched a third time with
`Accept-Language: en-US`, and the source row's `note` column says so, because a
digest whose bytes depend on a request header nobody wrote down is a digest a
second reader cannot recompute.

**One reading has no published provider contract behind it, and says so.**
`payment-webhooks/03` is the out-of-order and terminal-state reading. None of
the three verification pages this ledger now holds -- Stripe, Adyen, PayPal --
states whether deliveries arrive in the order the events occurred, so the record
cites the OWASP draft's Event Ordering section and one `absent` source whose
`version_note` names the three pages that were checked. That is the sixth
`absent` row in the corpus and the first one filed for a provider contract
rather than for an OWASP scenario.

**The bundle carried more drift than this ticket's own.** Regenerating
`docs/okf/` also rewrote `playbooks/payment-workflows.md` (23 added, 10 deleted)
and minted `references/payment-workflows--payment-process-contracts.md`. Both
are ticket 231's, left behind by the same commit that shipped the Playbook
without records. They are in this diff because the bundle is generated whole and
there is no way to regenerate one file of it; the alternative was to commit a
bundle that is still stale in a second place.

**The documented way to regenerate the bundle does not run.**
`tests.test_okf.FreezeTest`'s docstring gives
`okf.write(pathlib.Path('.'), pathlib.Path('docs/okf'))` as the fix, and it
raises `ValueError: '/home/majix/redKrakenV2/src/redkraken/playbooks/agentic-ai/
references/llm.md' is not in the subpath of '.'` --  `_corpus_path` calls
`relative_to` on an unresolved root. The docstring now says
`pathlib.Path('.').resolve()`, which is what the test itself uses
(`ROOT = Path(__file__).resolve().parent.parent`). One character short of the
same defect ticket 236 owns for the database command.

## Resolution, 2026-09-02

Four records, not a carve-out. The gate's rule -- every shipped Playbook has a
reading behind it -- was measured to be the right rule before it was obeyed: of
the fifty-one Playbooks that ship, fifty already had records, and thirty-three
carry a `references/` directory, so a reference note is demonstrably not what
the corpus accepts in place of a record.

`payment-webhooks/01` is the signature and raw-body reading and the only one of
the four with `finding_path: reaches`. The other three are `observation_only`,
and that is the Playbook's own decision rather than a capability ceiling: every
arm in all four records runs. Section 4 hands a duplicate application to
`race-conditions`, section 5 hands a reversed lifecycle pair to `routing` for
`business_logic.workflow_order`, and section 6 hands a generously-read authentic
event to `payment-workflows` and `routing`. The Playbook keeps only the claim
about the credential, so the records keep only that as reachable.

`RECORDS` moved from 378 to 382 in `tools/check_intake.py`, and the report
snapshot in `tests.test_intake` moved with it -- records, playbooks, path notes,
sources, external, absent and digested, plus `reaches` and `observation_only`.
`tests.test_okf`'s three pinned numbers were re-measured to 144 frontmatter
blocks, 51 Playbooks and 86 references.

Criterion 4 is one test in `tests/test_playbook.py::Corpus`, which is the module
somebody adding a Playbook runs. The rule it asserts already existed in
`check_techniques`; what did not exist was the rule being asked anywhere near
the corpus it is about, which is exactly how ticket 231 shipped a Playbook and
left the gate red for everyone else.

`Red:` `tools.check_intake.IntakeError: no ledger record is about playbook
payment-webhooks` -- raised out of `setUpClass`, so
`tests.test_intake.LedgerCorpusTest` reported `Ran 0 tests` and
`FAILED (errors=1)`. Watched on this tree before the first record was written.
Beside it, `AssertionError: 141 != 144` and `AssertionError: 50 != 51` from
`tests.test_okf.BundleTest`, and
`the committed bundle holds different files` from `FreezeTest`.

`Mutated:` the four records stripped back out of the ledger with `grep -v`, and
`tests.test_playbook.Corpus.test_every_shipped_playbook_has_a_ledger_record_behind_it`
printed `- []` / `+ ['payment-webhooks'] : payment-webhooks ships with no record
in technique-ledger.jsonl: a Playbook is written from the ledger, so the records
go in with it`. The ledger was restored from a copy taken before the mutation,
not with `git checkout`.

Forward references this ticket leaves standing: none. Nothing anywhere in the
effort cites this ticket's number, and it owed nothing.

## Bar, 2026-09-02

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`; `grep -c '^- \[[ x]\]' <ticket>` prints `4`.
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`; the tests this change reaches are named in full.

   ```
   NO_COLOR=1 uv run python -m unittest -v \
     tests.test_intake.LedgerCorpusTest.test_the_corpus_resolves_and_the_counts_are_the_ones_reviewed \
     tests.test_intake.LedgerCorpusTest.test_two_runs_of_the_gate_agree \
     tests.test_playbook.Corpus.test_every_shipped_playbook_has_a_ledger_record_behind_it \
     tests.test_okf.FreezeTest.test_the_committed_bundle_is_current \
     tests.test_okf.BundleTest.test_every_playbook_skill_and_reference_is_a_concept \
     tests.test_okf.BundleTest.test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar
     ... ok  (6 lines)
     Ran 6 tests in 0.409s
     OK
   ```

   `NO_COLOR=1` is not decoration: this shell exports `FORCE_COLOR=3`, and
   Python 3.14's argparse colours its help, which fails 54 assertions in
   `tests.test_cli` that read `usage: rk <command>` off the front of
   `format_help()`. Measured, and an environment artifact rather than a defect
   in the tree.
3. **Forward references redeemed.** `grep -rn 'ticket 235'
   docs/specs/production-harness-v2/`, this ticket excluded, prints nothing.
   Nothing was owed to this ticket and it redeemed nothing.
4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_intake tests.test_okf \
     tests.test_baseline tests.test_audit tests.test_playbook \
     tests.test_release tests.test_packaging tests.test_skill -q
     Ran 430 tests in 89.606s
     OK (skipped=3)
   ```

   The three skips are all `tests.test_audit.RunnableProbe`, which exists to
   be skipped: `skipped 'no database'`, `skipped 'no database is installed, so
   this interpreter is a measured runtime, roughly'` and
   `skipped 'claude_agent_sdk is installed, so this interpreter is a measured
   runtime'`. None is this change's and none is new. Both corpus gates also run
   clean as programs -- `python -m tools.check_intake` prints both reports, and
   `python -m tools.check_wiring` prints
   `W12 test shapes      0 owed   playbooks 51  evidence rows 153  naming three
   roles 51`.

   `git diff --numstat`: `baseline/technique-ledger.jsonl` 4 added and 0 deleted
   -- four records, one line each; `baseline/technique-sources.tsv` 11 added and
   0 deleted; `tools/check_intake.py` 2 added and 2 deleted -- the `RECORDS`
   value and one word of its note; `tests/test_intake.py` 7 and 7 -- the report
   snapshot and the tail-cut count; `tests/test_okf.py` 5 and 5 -- three pinned
   numbers, one total in a comment, and the docstring's regeneration command;
   `tests/test_playbook.py` 18 added and 1 deleted, the new test and its import.
   Under `docs/okf/`: six files rewritten and three minted, all generated.
   No `.skip`, no deleted test, no removed assertion. `tests/test_database.py`
   is untouched: nothing in this change reaches SQL.
5. **The diff is what the ticket asked for.**
   `git status --short --untracked-files=all` holds, beside this ticket file:
   `baseline/technique-ledger.jsonl`, `baseline/technique-sources.tsv`,
   `tools/check_intake.py` and nine paths under `docs/okf/` -- the `Touches`
   line -- plus `tests/test_intake.py`, `tests/test_okf.py` and
   `tests/test_playbook.py`, this ticket's test files. One other path is dirty
   and is deliberately **not** in this commit:
   `docs/specs/production-harness-v2/issues/134-...md`, which ticket 134's
   review cycle is writing into while this ran.
6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

**Judgement, red and mutated.** Both watched in this session. The red is quoted
from the run made on this tree before the first record existed, and the mutation
is quoted from the run made with the four records stripped back out.

**Judgement, no unexplained NOBODY.** Every far end in `## Seam check` is a
symbol that was opened or a command that was run. The one non-symbol far end is
the provider documentation, and it is recorded as six addresses with the sha256
of the bytes each served.

**Judgement, the live run reached this ticket's case.** There is no
`live-inputs.md` in this effort. The live part of this ticket is the six
fetches, and they were live: HTTP 200 from `docs.stripe.com`, `docs.adyen.com`,
`developer.paypal.com` twice, `raw.githubusercontent.com` and
`lightningsecurity.io` on 2026-09-02, with the digest of each recorded in
`baseline/technique-sources.tsv`. No page was cited from memory and none was
carried over from an earlier mining pass.

**Judgement, Rule 3b.** No double was injected. The records describe readings a
Task performs against a Program-owned provider sandbox, and this ticket wrote
none of that machinery -- it wrote the corpus entry the machinery is selected
from.
