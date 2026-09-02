# 235 — The corpus gate is red: a shipped Playbook has no ledger record

**What to build:** Either the missing `payment-webhooks` records in
`baseline/technique-ledger.jsonl`, or the rule that says a Playbook may ship
without them. The corpus gate refuses the tree as it stands.

**Blocked by:** nothing.

**Status:** resolved

**Touches:** `baseline/technique-ledger.jsonl`, `baseline/technique-sources.tsv`,
`tools/check_intake.py`, `docs/okf/`, `tests/test_intake.py`,
`tests/test_okf.py`, `tests/test_playbook.py`. Review cycle 1 added
`src/redkraken/okf.py`.

**PRODUCES:** new -- the ledger records and source rows behind the
`payment-webhooks` Playbook, and the OKF bundle rebuilt over the corpus that
ships.

**CONSUMED BY:** `tools/check_intake.py::check_techniques`, reading
`no ledger record is about playbook` and its own `RECORDS` count;
`tests.test_okf.FreezeTest.test_the_committed_bundle_is_current`, reading
`the committed bundle holds different files`, and
`tests.test_okf.BundleTest.test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar`,
reading the pinned `144`;
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

`payment-webhooks` ships as a Playbook. At `1ba74ee9` the ledger was last
written by `61e3dd7a`, and the Playbook arrived after it. On the tree this
change lands on that is no longer the last writer: `48396d4b` rewrote 81 ledger
lines in between, for ticket 216's question codes, and it added no record.

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
- [x] **The next Playbook cannot arrive the same way.** The rule is asserted
      in the module a Playbook's author runs, `tests.test_playbook.Corpus`, and
      not only inside the corpus gate that ticket 231 never ran. Reworded in
      review cycle 1: the criterion first said the addition "fails at the time
      it is made", and nothing in this tree fails before a test run.

## Seam check, 2026-09-02

`PRODUCES:` four records `payment-webhooks/01`--`/04` in
`baseline/technique-ledger.jsonl`, eleven rows `S1525`--`S1535` in
`baseline/technique-sources.tsv`, and the OKF bundle under `docs/okf/`
regenerated over them. Added in review cycle 1, which found it missing:
`WROTE RECORDS 382 READ BY tools/check_intake.py::check_techniques, reading
"the reviewed corpus holds"` -- the pin this diff moved from 378, and read on
every run of the gate. Watched: the gate run against the pre-diff ledger prints
`the reviewed corpus holds 382 records, and this one holds 378`.

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
- `tests.test_okf.BundleTest` -- added in review cycle 1, which found this far
  end unwalked. Three literals in this module are counts of the corpus, and all
  three moved with the diff: `144` frontmatter blocks
  (`test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar`),
  `51` Playbooks and `86` references
  (`test_every_playbook_skill_and_reference_is_a_concept`). Far end **reached**:
  the module was red at `141 != 144` and `50 != 51` before the bundle was
  rebuilt.
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

Added in review cycle 1, which found both missing. A second `CONSUMES` far
end: `src/redkraken/replay.py::DETECTION`, the statement all four records'
`runtime_writer` cites -- the records spell it `src/redkraken/replay.py:106`,
which is the corpus's convention across 174 pre-existing records and not a
form this flow accepts as a far end. Read: line 106 is
`"SELECT close_test_replay($1::uuid, $2, $3)"` inside `DETECTION`. Far end
**reached**. And the grep over the ledger literal skipped three other hits, all
benign and none a writer: `tests/ledger.py::technique_records`,
`tests/test_intake.py` at two `read_records` sites, and
`tools/check_baseline.py::BASELINE_FILES`, which names the file and reads no
record out of it.

No `NOBODY`. The one far end that is not a symbol is the provider
documentation, and it is an address rather than a citation: six pages fetched
over HTTPS on 2026-09-02. Review cycle 1 found the sha256 of five of those six
addresses unreproducible and replaced those digests with a note; the reading
below is what the bytes said on the retrieval date, and the four
`raw.githubusercontent.com` rows still carry a digest that recomputes.

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
Playbook's arm 7. `QUESTION_CODES` entered `tools/check_intake.py` in
`48396d4b`, dated 2026-09-02, the same day as this ticket; this is the first
corpus addition written under it.

**Two sources had to be re-fetched to be citable at all.**
`source_error` refuses a query string, so `docs.stripe.com/webhooks?lang=node`
is not an address this ledger takes and the page was re-fetched at
`docs.stripe.com/webhooks`. That fetch then came back in German, because the
page is served per `Accept-Language`: it was fetched a third time with
`Accept-Language: en-US`, and the source row's `note` column says so, because a
digest whose bytes depend on a request header nobody wrote down is a digest a
second reader cannot recompute. Review cycle 1 found a second, unrecorded
re-spelling beside it: the OWASP draft is cited in the reference note as
`github.com/OWASP/CheatSheetSeries/blob/master/...`, an HTML view, and S1527,
S1530, S1532 and S1535 all carry the raw address
`raw.githubusercontent.com/OWASP/CheatSheetSeries/master/...` the digest was
taken from. Those four are the only rows added here whose bytes reproduce.

**One reading has a provider contract behind it and one absence beside it.**
`payment-webhooks/03` is the out-of-order and terminal-state reading. This
paragraph said the opposite until review cycle 1: it claimed no provider page
states whether deliveries arrive in the order the events occurred, and the
Stripe page the record already cited carries a section headed "Event ordering"
saying "Stripe doesn't guarantee the delivery of events in the order that
they're generated. ... Make sure that your event destination isn't dependent on
receiving events in a specific order." The record now cites that section as
`S1536`, and the `absent` row `S1533` is narrowed to what is genuinely absent:
a positive ordering *guarantee* a receiver could rely on, which Stripe refuses
outright and Adyen and PayPal say nothing about. That is still the sixth
`absent` row in the corpus and the first filed for a provider contract rather
than for an OWASP scenario, and it no longer stands in for a published fact.

**The bundle carried more drift than this ticket's own.** Regenerating
`docs/okf/` also rewrote `playbooks/payment-workflows.md` (23 added, 10 deleted)
and minted `references/payment-workflows--payment-process-contracts.md`. Both
are ticket 231's, left behind by the same commit that shipped the Playbook
without records. They are in this diff because the bundle is generated whole and
there is no way to regenerate one file of it; the alternative was to commit a
bundle that is still stale in a second place.

**The documented way to regenerate the bundle did not run, and cycle 1 fixed
the code rather than the docstring.** `tests.test_okf.FreezeTest`'s docstring
gives `okf.write(pathlib.Path('.'), pathlib.Path('docs/okf'))` as the fix, and
it raised `ValueError: '/home/majix/redKrakenV2/src/redkraken/playbooks/
agentic-ai/references/llm.md' is not in the subpath of '.'` -- `_corpus_path`
calls `relative_to`, which is lexical, on whatever root it was handed. The
build session patched the docstring to `pathlib.Path('.').resolve()` and called
that the fix; two review axes landed on it independently and said the defect was
still in the code, so `okf.build` now resolves `root` once at its own door and
the docstring is back to `pathlib.Path('.')`. One character short of the same
defect ticket 236 owns for the database command, and unlike that one it was in
production code.

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

### Re-run, review cycle 1

Under the same heading and not a new one, because this is the same ticket's bar
re-cleared after the cycle's NOW repairs. Measured on the tree that lands on
`a9c86cfd`, which is the parent this commit has -- the pin the Ticket axis found
missing from item 4 above.

1. **Every acceptance criterion is ticked.**

   ```
   grep -c '^- \[ \]' <ticket>    0
   grep -c '^- \[[ x]\]' <ticket>  4
   ```

2. **The seam test passes, read by name.** One test longer than the run above:
   `test_the_root_is_normalised_before_it_is_used_as_a_prefix`, the red this
   cycle's `okf.py` repair was written against.

   ```
   NO_COLOR=1 uv run python -m unittest -v \
     tests.test_intake.LedgerCorpusTest.test_the_corpus_resolves_and_the_counts_are_the_ones_reviewed \
     tests.test_intake.LedgerCorpusTest.test_two_runs_of_the_gate_agree \
     tests.test_playbook.Corpus.test_every_shipped_playbook_has_a_ledger_record_behind_it \
     tests.test_okf.FreezeTest.test_the_committed_bundle_is_current \
     tests.test_okf.BundleTest.test_every_playbook_skill_and_reference_is_a_concept \
     tests.test_okf.BundleTest.test_every_frontmatter_block_the_bundle_writes_is_inside_the_grammar \
     tests.test_okf.BundleTest.test_the_root_is_normalised_before_it_is_used_as_a_prefix
     ... ok  (7 lines)
     Ran 7 tests in 0.429s
     OK
   ```

   The repair is also readable without a test runner, because it is the command
   the docstring publishes:

   ```
   NO_COLOR=1 uv run python -c "import pathlib; from redkraken import okf;
     print(len(okf.write(pathlib.Path('.'), pathlib.Path('docs/okf'))), 'files')"
   148 files
   ```

   Before the repair the same line raised
   `ValueError: '/home/majix/redKrakenV2/src/redkraken/playbooks/agentic-ai/references/llm.md' is not in the subpath of '.'`.

3. **Forward references redeemed.** One hit outside this file, and it is
   history rather than a debt:

   ```
   grep -rn 'ticket 235' docs/specs/production-harness-v2/ | grep -v '235-the-corpus-gate'
   docs/specs/production-harness-v2/issues/236-the-documented-database-test-command-runs-nothing.md:137:ticket 235's commit `5c35ca1e` because that ticket had to run it. Two
   ```

   Ticket 236 cites this ticket's commit as the reason it did not re-run a
   thirty-minute suite. Nothing is owed back.

4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_intake tests.test_okf \
     tests.test_baseline tests.test_audit tests.test_playbook \
     tests.test_release tests.test_packaging tests.test_skill -q
     Ran 431 tests in 93.052s
     OK (skipped=3)
   ```

   431 and not the 430 item 4 above quotes: one test was added by this cycle.
   The three skips are the same `tests.test_audit.RunnableProbe` skips named
   there, and `FAILED (failures=2, errors=1)` -- which is what that command
   printed on `a9c86cfd`, and the reason the Ticket axis called item 4's paste a
   verdict for a tree that no longer exists -- is now `OK`: the failures were
   `tests/test_audit.py`'s `resolved 201` snapshot, stale since ticket 134
   resolved, and this cycle re-measured it to 203.

   All four gates `docs/agents/testing.md` tier 2 names, and not the two item 4
   ran:

   ```
   python -m tools.check_intake     rc=0, both reports printed
   python -m tools.check_wiring     W12 test shapes  0 owed   playbooks 51  evidence rows 153  naming three roles 51
   python -m tools.check_audit      rc=0
   python -m tools.check_baseline   baseline ok: classifications=10 regressions=7 adapters=11 artifacts=223 frozen
   tools/check_coverage.py          catalogue  51   skills 6  references 86
                                    census    223   reconciled
   ```

   `git diff --numstat HEAD`, quoted rather than described, this ticket's paths
   only -- `docs/.../233-...md` is in the working tree and is ticket 233's, not
   this commit's:

   ```
   3	3	baseline/technique-ledger.jsonl
   8	7	baseline/technique-sources.tsv
   115	32	docs/specs/production-harness-v2/issues/235-...md
   4	0	src/redkraken/okf.py
   1	1	tests/test_audit.py
   2	2	tests/test_intake.py
   12	3	tests/test_okf.py
   ```

   No `.skip`, no deleted test, no removed assertion. The ledger's 3/3 is
   `payment-webhooks/01`, `/03` and `/04` rewritten in place, one line each;
   the table's 8/7 is six digests dropped for a note, S1533 narrowed, and S1536
   added; `src/redkraken/okf.py` is four added lines, three of them the comment.

5. **The diff is what the ticket asked for.**

   ```
   git status --short --untracked-files=all
    M baseline/technique-ledger.jsonl
    M baseline/technique-sources.tsv
    M docs/specs/production-harness-v2/issues/233-a-probe-only-playbook-bar-asks-for-two-kinds-its-own-trigger-refuses.md
    M docs/specs/production-harness-v2/issues/235-the-corpus-gate-is-red-a-shipped-playbook-has-no-ledger-record.md
    M src/redkraken/okf.py
    M tests/test_audit.py
    M tests/test_intake.py
    M tests/test_okf.py
   ```

   Eight paths, none elided and none abbreviated -- the correction the Bar axis
   asked for on item 5, which narrated this list instead of quoting it. Seven
   are this commit's. The eighth, ticket 233's file, is that ticket's own
   in-progress build work and is committed with explicit pathspecs elsewhere.
   `docs/okf/` is absent because the bundle is byte-identical after the
   `okf.py` repair, which is the point of the repair.

6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

**Judgement, red and mutated.** The cycle's one production-code repair was
written against a watched red: `okf.build(ROOT / "src" / "..")` raised
`ValueError: ... is not in the subpath of '/home/majix/redKrakenV2/src/..'`
before `build` resolved its root, and passes after. The unresolved spelling in
the test is the documented one, not a contrived one -- `FreezeTest`'s docstring
hands a caller `pathlib.Path('.')`.

**Judgement, no unexplained NOBODY.** Two far ends the cycle found unwalked are
now walked in `## Seam check`: `tests.test_okf.BundleTest`'s three corpus counts,
and `src/redkraken/replay.py::DETECTION`. The skipped-hit count is recorded.

**Judgement, the live run reached this ticket's case.** The cycle's live part is
the re-fetch that settled the blocker: `https://docs.stripe.com/webhooks` with
`Accept-Language: en-US,en;q=0.9`, HTTP 200 on 2026-09-02, carrying
`{"level":3,"anchored":true,"toc":"Event ordering","id":"event-ordering"}` and
the paragraph quoted in `S1536`. The same pass measured, twice per address, that
five of the six addresses return different bytes seconds apart; only
`raw.githubusercontent.com` returned `c32bdd63129f44b8...` both times.

**Judgement, Rule 3b.** No double was injected. The one code change resolves a
path.


## Review findings, 2026-09-02 — cycle 1

Fixed point `4a30fe66`, the parent of this ticket's first build commit
`5c35ca1e`. Four axes read `git diff 4a30fe66...HEAD` as four blind subagents.

- [ticket] **`baseline/technique-sources.tsv::S1533`: the `absent` row's stated ground is false against the source it names.** Its `version_note` says none of the three verification pages states whether deliveries arrive in the order the events occurred, but `https://docs.stripe.com/webhooks` -- the page S1525 and S1529 digested -- carries a section headed "Event ordering": "Stripe doesn't guarantee the delivery of events in the order that they're generated. ... Make sure that your event destination isn't dependent on receiving events in a specific order." Against criterion 2, an `absent` row is standing where the cited page publishes the fact. — blocker — NOW. `S1533` is narrowed to the absence that is real -- a positive ordering guarantee, which Stripe refuses outright and Adyen and PayPal are silent on -- and the Stripe Event ordering section is cited on `payment-webhooks/03` as the new external row `S1536`. Re-fetched and confirmed before the edit.
- [ticket] **`baseline/technique-ledger.jsonl::payment-webhooks/03`: `notes` repeats the same false claim**, as does `## Build findings`' "One reading has no published provider contract behind it, and says so". The reading does have a published provider contract behind it. — blocker — NOW. `notes` rewritten and the `## Build findings` paragraph rewritten with it; both now say the reading has a published provider contract behind it and what the absence beside it covers.
- [bar] **`src/redkraken/okf.py::_corpus_path`: a real defect was routed around in prose instead of fixed in code.** `okf.build(Path('.'))` raises `ValueError: '.../playbooks/agentic-ai/references/llm.md' is not in the subpath of '.'`; the ticket patched `tests/test_okf.py::FreezeTest`'s docstring to `pathlib.Path('.').resolve()` and then declared "Forward references this ticket leaves standing: none". Ticket 236 never mentions `okf`, so the Build finding's "the same defect ticket 236 owns" is an analogy, not an owner. Standing-bar move 4: unfinished work with no verdict. — required — NOW. `build` resolves `root` once at its own door, against a watched red (`okf.build(ROOT / "src" / "..")`), and the docstring is back to the `pathlib.Path('.')` it published. Production code, so the red came first and the machine lines were re-run.
- [craft] **`tests/test_okf.py::FreezeTest`: the docstring workaround leaves the one-line defect in the code** and every future caller of `okf.write` still has to know the incantation. Normalise once in `_corpus_path`; no test pins the raise. Converged with the Bar axis, independently. — required — NOW, converged with the Bar axis on the same line. Same repair: normalised once in `build`, docstring reverted, and `tests.test_okf.BundleTest.test_the_root_is_normalised_before_it_is_used_as_a_prefix` now pins the raise so it cannot come back.
- [bar] **`baseline/technique-sources.tsv::S1525-S1535`: the digest column is unrecomputable for six of the ten external rows.** Two consecutive fetches seconds apart give two different sha256 for `docs.stripe.com/webhooks`, `docs.adyen.com/.../verify-hmac-signatures`, `lightningsecurity.io/blog/bypassing-payments-using-webhooks/`, `developer.paypal.com/api/webhooks/v1/verify-webhook-signature-post/` and `developer.paypal.com/api/nvp-soap/ipn/ht-ipn/`; only the four `raw.githubusercontent.com` rows reproduce (`c32bdd63…f46e`, twice). The Build findings priced this wall for `Accept-Language` alone and stopped one page short of their own rule. — required — NOW. Re-measured all six addresses twice: five return different bytes seconds apart. Those six rows -- `S1525`, `S1526`, `S1528`, `S1529`, `S1531`, `S1534`, and the new `S1536` -- lose the digest and carry the note `check_intake.source_row_error` requires in its place. The four `raw.githubusercontent.com` rows keep theirs. `digested` moved 1528 to 1522 and the `tests.test_intake` snapshot with it.
- [ticket] **`## Bar` item 4 quotes a green run for a tree that no longer exists.** It reads `Ran 430 tests in 89.606s / OK (skipped=3)`; the same eight-module command on the commit under review gives `Ran 424 tests ... FAILED (failures=2, errors=1, skipped=3)`. The reds are ticket 134's -- `4a30fe66` set `Status: resolved` without moving `tests/test_audit.py`'s `resolved 201` snapshot -- but the Bar states a verdict without naming the commit it was measured on, which `## What was measured` does name. — required — NOW. Item 4's paste is left standing as history and the re-run below it names the commit it was measured on, as `## What was measured` does. The cause was `tests/test_audit.py`'s `resolved 201` snapshot, stale since ticket 134 resolved; re-measured to 203 in this commit, and the eight-module command is `OK` again.
- [bar] **`## Bar` line 5 carries no output at all.** `git status --short --untracked-files=all` is re-narrated in prose, the nine `docs/okf/` paths are unnamed and one path is abbreviated to `134-...md`. The standing bar forbids characterising output instead of quoting it, and this is the one line whose check *is* reading the output. The file list is correct against `Touches`. — required — NOW. The porcelain output is pasted verbatim in the re-run below, eight paths, none abbreviated.
- [ticket] **`baseline/technique-ledger.jsonl::payment-webhooks/01`: `variant` contradicts the Playbook for half of Adyen's surface.** It says "Adyen signs a colon-delimited concatenation of named fields, so for Adyen that arm asks nothing"; the Playbook says the two families are signed over different material and the Adyen page says "Make sure that the request body is as it is -- do not deserialize it". — required — NOW. The clause is scoped to Adyen's Standard webhooks, which sign an ordered escaped field concatenation, and says plainly that Adyen's other families are signed over the raw body and the arm applies to them -- which is what the Playbook's section 2 says.
- [seam] **`## Seam check, 2026-09-02`: the `PRODUCES` list omits `tools/check_intake.py::RECORDS`**, which this diff moved 378 to 382 and which `check_techniques` reads on every run; the ticket's own `CONSUMED BY` line names it. Verified read, not dead wiring: the gate run against the pre-diff ledger prints `the reviewed corpus holds 382 records, and this one holds 378`. — nit — NOW. The produce line is added with its far end and the watched output.
- [seam] **`## Seam check, 2026-09-02`: `tests.test_okf` is walked only as `FreezeTest`**, so `BundleTest`'s 144, 51 and 86 pins get no far-end verdict, only a restatement in `## Resolution` and a run in `## Bar` item 2. — nit — NOW. A fourth bullet walks `BundleTest` and its three corpus counts, with the red each was measured against.
- [seam] **`baseline/technique-ledger.jsonl::payment-webhooks/01`: `runtime_writer` cites `src/redkraken/replay.py:106`, a line-number address**, which `seam-check` step 3 and `cut-slices` Rule 2 forbid as a far end, and the seam report records no far end for it. The citation is correct and 174 pre-existing records carry the same address, so it is the corpus's convention rather than this ticket's regression. — nit — NOW. `## Seam check` records the far end in the form this flow accepts, `src/redkraken/replay.py::DETECTION`, and says that the records keep the line-number spelling because 174 pre-existing records carry it and this ticket does not get to change the corpus's citation form on its own.
- [seam] **`## Seam check, 2026-09-02`: no count of skipped hits on the ledger literal**, which `seam-check` step 2 requires. The unenumerated readers are `tests/ledger.py::technique_records`, `tests/test_intake.py` at two sites and `tools/check_baseline.py::BASELINE_FILES`; all three are benign. — nit — NOW. Three skipped hits recorded by name, with what each does with the file.
- [seam] **`baseline/technique-sources.tsv::S1527`: only one of the two address re-spellings is recorded.** `## Build findings` covers Stripe's stripped query string and says nothing about the OWASP draft moving from the reference note's `github.com/OWASP/CheatSheetSeries/blob/master/...` to the digested `raw.githubusercontent.com/OWASP/CheatSheetSeries/master/...` that S1527, S1530, S1532 and S1535 all carry. — nit — NOW. The OWASP re-spelling is named in `## Build findings` beside Stripe's stripped query string.
- [bar] **`## Bar` item 4: `git diff --numstat` is re-narrated too**, and the eleven `docs/okf/` rows are elided as "six files rewritten and three minted" with no elision marker. Every quoted number is right and all five moved pins are re-measurements rather than thresholds lowered. — nit — NOW. The numstat is pasted verbatim in the re-run below.
- [bar] **`## Bar` item 4 ran two of the four gates `docs/agents/testing.md` tier 2 names.** With no `## Verify command` in the spec, tier 2 is the standing substitute; the line ran `check_intake` and `check_wiring` and not `check_audit`, `check_baseline` or `check_coverage`, whose own `catalogue 51 skills 6 references 86` line moves with this diff. — nit — NOW. All four tier-2 gates are run and quoted in the re-run below, `check_coverage`'s moving `catalogue 51 skills 6 references 86` line included.
- [ticket] **`## Build findings`: "That rule landed four days ago in the same corpus gate" is a relative age, and wrong.** `QUESTION_CODES` entered `tools/check_intake.py` in `48396d4b`, dated 2026-09-02, the same day as this ticket. — nit — NOW. Replaced with the commit, `48396d4b`, and its date.
- [ticket] **`## What was measured`: "The ledger was last written by `61e3dd7a`" is true at the measurement commit and false for the tree this lands on** -- `48396d4b` rewrote 81 ledger lines in between. — nit — NOW. Scoped to `1ba74ee9` and followed by what is true of the tree this lands on, naming `48396d4b` and its 81 rewritten lines.
- [ticket] **`baseline/technique-ledger.jsonl::payment-webhooks/02`: `refuted_evidence` names `response_invariant, role variant`, a kind the Playbook's `bb:evidence` never declares.** The Playbook's refuted row is `kind: response_differential`, which `/01` restates, and the record's own `runtime_writer` derives `response_differential` from the `body_differs` assertions. Same in `/03` and `/04`. 206 of 382 records carry the identical pair, so it is the corpus's shape rather than this ticket's invention, but the claim that the records "invent nothing the Playbook does not say" does not hold for this field. — nit — NOW, for what this ticket wrote. `/03` and `/04` gained the sentence `/02` already carried: the invariant is a kind this Playbook's bar cannot grade, recorded as the honest outcome rather than as a Finding. The absolute "every arm" derivation in `runtime_writer` is left as it stands in all four -- it derives the *supported* kind, it is byte-identical across 206 of 382 records, and re-deriving the corpus's convention is not this ticket's work.
- [craft] **`baseline/technique-ledger.jsonl::payment-webhooks/03`, `payment-webhooks/04`: the absolute "every arm below" claim in `runtime_writer` is not reconciled with their own `refuted_evidence`.** `/02` carries the reconciling sentence; `/03` and `/04` do not, and the string is byte-identical across all four records. Converged with the Ticket axis, independently. — nit — NOW, converged with the Ticket axis on the same pair of records. Same repair, and the byte-identical `runtime_writer` string is deliberately left alone for the reason recorded on that entry.
- [craft] **`baseline/technique-ledger.jsonl::payment-webhooks/01`: `technique` enumerates six alterations where `variant` and the Playbook's section 3 enumerate seven.** The missing one is item 4, the signed test event sent to the wrong endpoint or environment. One record answers "how many arms" two ways, and `variant` is a verbatim second copy of the numbered list. — nit — NOW. The seventh arm -- a signed test event sent to the wrong endpoint or environment -- is added to the `technique` sentence, so the two fields agree on seven.
- [craft] **`baseline/technique-sources.tsv::S1525`, `S1529`: the `note` column repeats what the same row's `version_note` already says.** `note` had exactly one user in the preceding 1524 rows, and `version_note` is the column `link_errors` joins against the record. — nit — NOW, and the Bar axis's digest finding is what made it clean: `note` now carries the byte-instability sentence, which is the fact `check_intake` requires there and which `version_note` does not state. The `Accept-Language` fact stays in `version_note` alone.
- [craft] **`tests/test_okf.py::FreezeTest`: the edited docstring line is 89 characters where the surrounding prose wraps at 72-82.** — nit — NOW. Moot and fixed together: the docstring went back to `pathlib.Path('.')` and was rewrapped to the surrounding width.
- [craft] **`docs/okf/log.md`: the bundle's own history is a hardcoded single 2026-08-28 bootstrap entry** (`src/redkraken/okf.py:499-514`), so a regeneration that mints three concepts ships a bundle whose history file says nothing has happened since bootstrap. Pre-existing and outside this ticket's `Touches`. — nit — DECLINED. Pre-existing, generated, outside this ticket's `Touches`, and a `nit` may not be routed to a ticket. Nothing in the tree reads `docs/okf/log.md` as provenance -- `okf.validate` does not grade it and no gate opens it -- and the bundle's real history is the git log of `docs/okf/`. If the OKF consumer ever needs a changelog, that is a shape question for `shape-idea`, not a repair here.
- [ticket] **`CONSUMED BY`: the second head is a module plus prose rather than `<module::symbol>, reading <literal>`.** `## Seam check` does resolve it to `tests.test_okf.FreezeTest.test_the_committed_bundle_is_current`; only the head is off-form. — nit — NOW. Both heads now name a symbol and the literal each reads.
- [ticket] **`Acceptance criteria`: criterion 4 says "fails at the time it is made rather than on somebody else's test run", and nothing fails at corpus-add time.** What shipped is the rule `check_techniques` already enforced, asserted a second time in the module a Playbook's author runs. It still only fails on a test run. — nit — NOW. The criterion is reworded to what was built and says in the same breath that the earlier wording overclaimed. No criterion added, so this cycle still closes the ticket.
- [ticket] **`Touches`: the three test files in the diff are not on the line.** It lists `baseline/technique-ledger.jsonl`, `baseline/technique-sources.tsv`, `tools/check_intake.py` and `docs/okf/`; Bar 5 discloses `tests/test_intake.py`, `tests/test_okf.py` and `tests/test_playbook.py` as "this ticket's test files". — nit — NOW. The three are added, and so is `src/redkraken/okf.py`, which this cycle's repair touches.

Review cycle 1 of 3 — undecided: none
