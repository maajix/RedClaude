# 216 — A Playbook halt has no question code to park under

**What to build:** A question code that means "a Playbook reached a halt it
declared, and the reading stops here", so that a step which tells the operator
why it stopped can park under the reason it actually has.

**Blocked by:** nothing.

**Status:** resolved

**Touches:**
`src/redkraken/migrations/20270111T000000Z__a_declared_halt_has_a_code_to_park_under.sql`,
`src/redkraken/roster.py`, `src/redkraken/_launch.py`,
`baseline/technique-ledger.jsonl`, `tools/check_intake.py`.
Test files this ticket owns: `tests/test_roster.py`, `tests/test_intake.py`.

**PRODUCES:** new contract -- one `decision_question_codes` row, `playbook_halt`,
and the sixth member of the `question_code` enum a model may name.

**CONSUMED BY:** `park_task_for_human`
(`20261028T000000Z:407-414`), which refuses a code that is not a row; the
Playbook corpus, ticket 234; any operator console keyed on
`pending_decisions.question_code` (`ui.py:629`, `operator.py:60`).

**CONSUMES:** `decision_question_codes` (`20260814T020000Z:47-72`), the
`question_code` enum (`roster.py:1809-1827`), the `park_for_human` description
(`_launch.py:1299-1314`), `baseline/technique-ledger.jsonl`.

## What was measured

Found while landing ticket 101's step 3, and measured over the whole corpus
ledger rather than over a sample:

```
baseline/technique-ledger.jsonl
  records naming park_for_human in stop_conditions      81   (of 378)
  playbooks those records belong to                     16   (of 50)
  records naming any of the six question codes           0
src/redkraken/playbooks/
  shipped Playbooks naming park_for_human today          0
```

The harness files a parked question under one of six codes. Five were inserted
by `20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:62-72` and
the sixth by
`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:444-448`:

| code | what it means |
| --- | --- |
| `scope_ambiguous` | the request addresses something the scope document does not clearly admit |
| `destructive_action` | the request may change state at the target rather than read it |
| `third_party_impact` | the request may reach or affect somebody who is not the Program's counterparty |
| `credential_needed` | the request would be made under a borrowed identity |
| `policy_unclear` | the static floor asks, and no rule named a better reason |
| `impact_unauthorized` | a validated Finding has an impact Test, and no live operator grant covers it |

All six describe a **risk the harness detected before a call**. None describes a
**halt the Playbook itself declared**, which is what the eighty-one records are
about. Their halt triggers are readings that ran out: a declared count reached,
a control that did not answer the way the reading needs it to, an arrival inside
the window, a Finding confirmed and worth reporting. Three examples, quoted from
the ledger:

```
exceptional-conditions/01  the declared count is reached, or any answer returns
                           a record the reading did not create
grpc/02                    the first call answers about the connection rather
                           than about the method
command-directory-injection/08
                           a command sink has been proved
```

## Where the mechanism is

`park_task_for_human`
(`src/redkraken/migrations/20261028T000000Z__a_model_asks_to_be_parked_and_the_task_waits.sql:362`)
refuses at `:407-414` when the code is not a row in `decision_question_codes`,
and hands back the whole list so the caller can see what it may say.

The model-facing surface is narrower than the table. `roster.py:1813-1826`
declares the argument's `enum` with **five** members -- `impact_unauthorized` is
the runtime's own, not something an Agent may claim -- and `_launch.py:1299-1314`
tells the model in prose that there are "five question codes". So the vocabulary
a Playbook step can reach is those five, and the closest of them is
`policy_unclear`, which is a statement about the risk floor and not about the
reading.

## Why it is worth a ticket rather than a note

Nothing is broken today: no shipped Playbook names `park_for_human`, so nothing
is currently picking a wrong code. The gap arrives with ticket 101, whose steps
4 and 5 regenerate the corpus from this ledger. At that point sixteen Playbooks
carry halt prose telling the Agent to park, the Agent must pick one of five
codes, and none of them is true. What lands in `pending_decisions` is then a
halt filed under "the static floor asked", and an operator console keyed on the
code shows the wrong reason for every one of them.

The cheap wrong fix is to write `policy_unclear` into all eighty-one ledger
records. That is eighty-one recorded falsehoods, and it makes the real code
harder to add later because something would then have to find and unpick them.

## What it costs

Priced rather than assumed, by reading each end:

- **One migration.** `decision_question_codes` is a plain table with a text
  primary key. `pending_decisions.question_code` and
  `call_risk_rules.question_code` are foreign keys onto it
  (`20260814T020000Z:76-80`), so a new row breaks no existing row and no
  existing rule.
- **Two lines in the package.** The `enum` at `roster.py:1813-1826` gains the
  sixth member, and the prose at `_launch.py:1299-1314` stops saying "five".
- **The ledger, mechanically.** All eighty-one records name the same halt, so
  the code goes in with one pass and no per-record judgement.

Ticket 101 does not do this: it is a corpus rewrite, and this is a change to the
vocabulary the tool surface offers. Capability before catalogue -- the code
lands before the sixteen Playbooks that would use it.

## Acceptance criteria

- [x] **A code exists for a declared halt.** One row in
      `decision_question_codes`, whose `meaning` and `asked_when` say that the
      Playbook's own stop condition fired, rather than that a risk rule did.
- [x] **A model may name it.** It is in the `enum` at `roster.py:1813-1826` and
      in the tool's description, which no longer says there are five.
- [x] **The refusal still refuses.** A code outside the table is still turned
      away by `park_task_for_human` with the list attached, proved by a test
      that names a code this harness does not file under.
- [x] **The eighty-one records carry it.** `baseline/technique-ledger.jsonl` is
      updated in the same change, and `tools/check_intake.py` refuses a record
      whose `stop_conditions` name `park_for_human` without naming a code.

## What this does not change

`impact_unauthorized` stays out of the model-facing `enum`. It is the runtime's
own question about a grant it went looking for, and a model that could claim it
could ask for an impact replay by asking to be parked.

## Re-measured, 2026-09-02

Two of the numbers this ticket was written on have moved, and one of them
changes what the ticket has to do. Counted again over the tree as it stands:

```
baseline/technique-ledger.jsonl
  records naming park_for_human in stop_conditions      81   (of 378)
  playbooks those records belong to                     16
  records naming any question code    0 before, 81 after
src/redkraken/playbooks/
  shipped Playbooks                                     51
  shipped Playbooks naming park_for_human               39   (the ticket says 0)
  shipped Playbooks naming a question code              42
  shipped Playbooks counting the codes at five          11  (in 10 files)
  ... plus Playbooks asserting no code says a reading
      ran out, without counting them                     21
  ... union, whose stated premise this change falsifies  31
```

Every one of the eighty-one occurrences sits in field 5 of `stop_conditions`,
`who is told`, and each of those eighty-one splits into exactly six ` | `
fields. That is not true of the corpus: over all 378 the spread is 257 records
with no ` | ` at all and 121 with six. So the
mechanical pass this ticket priced is one token replacement and no per-record
judgement, as written.

### The wall this ticket did not have

**Wall.** Ticket 101 is `resolved`, so the corpus rewrite this ticket forecast
has already happened. It did not file eighty-one falsehoods. It routed around
the missing code in prose. Re-counted at review: eleven sentences in ten
Playbooks count the codes at five, and twenty-one further Playbooks assert that
no served code says a reading ran out without counting them -- thirty-one in
all. One of the eleven:

```
src/redkraken/playbooks/authentication/playbook.md:168
  Every other halt is a reading that ran out -- a declared count reached, a
  credential burnt, a lockout or a 429 arriving mid-sequence -- and none of the
  five codes says that, so those are reported through the Task's own record.
```

Adding a sixth code makes the count in those eleven sentences wrong, makes the
premise of all thirty-one Playbooks wrong, and makes their routing decision --
report rather than park -- a decision nobody has re-taken since the code
exists.

**Price.** Rewriting the thirty-one paragraphs to park under the new code is not
a prose fix: it changes what an Agent does at a declared halt in thirty-one
Playbooks,
from finishing the Task with a report to stopping it and waiting for a person.
For a halt like "a command sink has been proved" those are opposite behaviours,
and the ledger and the corpus disagree about which is right -- the ledger says
`park_for_human`, the corpus says the Task's own record.

**Purpose.** This ticket is the capability: a code that says what happened, so
that whoever adopts it is not choosing between a wrong code and no code. Its own
words: "Capability before catalogue -- the code lands before the sixteen
Playbooks that would use it."

**Rule.** The code, the enum, the description, the ledger and the checker land
here. The thirty-one corpus paragraphs are not rewritten by this ticket, and the
routing question they hold -- does a declared halt park, or report? -- is filed
as ticket 234 rather than answered in passing.

What lands here *does* make those paragraphs say something false, and this
ticket does not pretend otherwise. `playbook_halt` means "the Playbook's own
stop condition fired and the reading stops here", and the migration's own
comment says a model naming it "is a model saying its own reading ran out" --
which is word for word what twenty-one of the thirty-one deny, as in
`src/redkraken/playbooks/deployment/playbook.md`: "because no question code in
the served set says a reading ran out of tells". Eleven more state a count that
is now wrong. The behaviour those Playbooks describe still runs; the reason they
give for it is stale from this commit, and ticket 234 owns every one of the
thirty-one.

The description is rendered from the enum rather than counted by hand, the way
ticket 145 renders `observation_provenance`. That is the same defect this ticket
is about: a sentence that counted a closed vocabulary and went stale when the
vocabulary grew.

## Build findings, 2026-09-02

Three things this build ran into that are not this ticket's work. None of them
blocked it; each is written down here rather than fixed in passing.

- **DISCOVERY. `tests.test_intake.LedgerCorpusTest` is red on `main`, before
  this change.** `check_techniques()` raises `no ledger record is about playbook
  payment-webhooks`. Measured on the parent commit `766b21e1` with this
  ticket's files stashed, so it is not this ticket's doing: `payment-webhooks`
  ships as a Playbook and no record in `baseline/technique-ledger.jsonl` names
  it. The corpus gate is part of the release gate, so this is red on the gate
  and not only in a test module.
- **DISCOVERY. The command `docs/agents/testing.md` gives for a database run
  silently runs nothing.** `flock -w 3600 /tmp/rk2-db.lock uv run python -m
  unittest tests.test_database.<Class>` prints `Ran 0 tests ... OK (skipped=1)`
  with the reason `another session holds /tmp/rk2-db.lock; a hunt is running on
  this cluster`. `setUpModule` takes that lock itself, so the documented outer
  `flock` is the session it then refuses to run beside. A reader who trusts the
  exit status reads a green schema run that never happened.
- **DISCOVERY. The corpus paragraphs are now a decision nobody has
  taken.** Priced above; the build counted nine of them and the review
  re-measured thirty-one. A Playbook that says a declared halt is reported
  through the Task's own record, and eighty-one ledger records that say the same
  halt is told to the operator through `park_for_human`, disagree about the same
  halt. This ticket gives that halt a truthful code and does not settle which of
  the two is right.

## Seam check, 2026-09-02

Run at review (gate 6), because `build-slice` §5 left no report at this address.
Greps and recorded far ends read against current source; no live replay, no
`live-inputs.md` in this effort, `REPLAYS` untouched.

```
WROTE  decision_question_codes row 'playbook_halt'
       READ BY  20261028T000000Z::park_task_for_human, reading
                `decision_question_codes` (:407-414, the refusal that returns
                the whole list) -- read in source, fired in AgentAskTest
       READ BY  the PRIMARY KEY at decision_question_codes(question_code),
                20260814T020000Z:47
       READ BY  the FOREIGN KEYs pending_decisions_question_code_fkey and
                call_risk_rules_question_code_fkey, 20260814T020000Z:76-80
       READ BY  redkraken.migrate::load -- 248 migrations, 0 violations
       READ BY  redkraken.ui::Handler (ui.py:629) and redkraken.operator
                (operator.py:60), rendered verbatim, no five-item label map
       READ BY  tests.test_database.AgentAskTest::
                test_a_refused_code_names_the_whole_list_it_is_not_in, which
                derives its expectation from the table and cannot go stale

WROTE  the sixth `question_code` enum member (roster.py:1825)
       READ BY  redkraken.roster::Argument.schema, reading `enum` -> served
                JSON Schema carries all six
       READ BY  redkraken.roster::_value_fault (roster.py:2783), the call gate
       READ BY  redkraken._launch::DESCRIPTIONS["park_for_human"] -> _carry ->
                @tool -> create_sdk_mcp_server; `"five" in description` is False
       READ BY  tools/check_intake.py::QUESTION_CODES -> record_error
       READ BY  tools/check_wiring.py::read_surface, still resolving six members

WROTE  " under question code playbook_halt" in 81 ledger records
       READ BY  tools/check_intake.py::record_error, reading
                `mcp__rk2__park_for_human`; check_techniques grades all 378
       READ BY  ticket 234 (status `ready-for-agent`) for the corpus half
       READ BY  NOBODY at runtime, by design: nothing regenerates the corpus
                from the ledger. This is the ticket's "capability before
                catalogue", and 234 is the named far end.

WROTE  the refusal in tools/check_intake.py::record_error
       READ BY  check_techniques -> main (the corpus gate), and
                tests.test_intake.LedgerRecordTest (two methods)

WROTE  three new issue files 234, 235, 236
       READ BY  tools/check_audit.py::read_tickets -> the `tickets` figure at
                check_audit.py:930 -> tests/test_audit.py::AuditGateTest.
                Was NOT refreshed by the build; repaired in this review.

READ   decision_question_codes   WRITTEN BY 20260814T020000Z (5 rows) and
                                 20260816T000000Z:444 (1 row)
READ   roster.PARK_FOR_HUMAN     WRITTEN BY roster.py:2149
READ   baseline/technique-ledger.jsonl
                                 WRITTEN BY operator, by hand at
                                 baseline/technique-ledger.jsonl (ticket 101),
                                 and by this change
CONTRACT  park_task_for_human's refusal now lists 7 codes, not 6
       HANDLED BY tests.test_database.AgentAskTest::
                  test_a_refused_code_names_the_whole_list_it_is_not_in
                  (table-derived, so the seventh row does not strand it)
```

**The three that hide.** Name drift: clean -- `playbook_halt` is the only
spelling in the tree; `playbook_stop` appears solely in this ticket's own
`Mutated:` record. Unit and type drift: clean -- `stop_conditions` is `str` at
both ends, the token appears exactly once per record, all 81 in field 5 of six.
Vocabulary drift: the enum (6) is a strict subset of the table (7), the
checker's allow-list *is* the enum by reference, the description renders it, and
the SQL refusal reads the table -- all four agree. The one disagreement is the
thirty-one corpus paragraphs, owned by ticket 234.

Findings from this pass carry their verdicts in the review block below, under
the `[seam]` tag, rather than being verdicted twice.

## Resolution, 2026-09-02

One row, one enum member, one rendered sentence, eighty-one records and one
refusal. No verb changed, no rule changed, no existing decision moved.

`playbook_halt` is seeded by
`20270111T000000Z__a_declared_halt_has_a_code_to_park_under.sql` and means the
Playbook's own stop condition fired. It is the sixth member of the
`question_code` enum, and the sixth of the six rows a model may name. The table
now holds seven; `impact_unauthorized` is the seventh and stays out of the enum,
for the reason the ticket gives.

The description a run reads is no longer counted by hand. It renders the served
enum, the way `roster.observation_provenance` renders `allowed_provenance` for
ticket 145: the defect this ticket is about is a sentence that said "five" and
was wrong the day a sixth code existed, and a second hand-written list would be
the same defect one code later. `tools/check_intake.py` reads the same enum, so
a record is graded against the words the model is actually offered rather than
against a list restated in the tool.

`Red:` `AssertionError: 'playbook_halt' not found in ('scope_ambiguous',
'destructive_action', 'third_party_impact', 'credential_needed',
'policy_unclear')` --
`tests.test_roster.VocabularyAgreementTest.test_the_codes_a_model_may_park_under_are_codes_the_corpus_files`,
watched failing before the migration existed. The ledger half was red in the
same run:
`AssertionError: 'exceptional-conditions/02: a halt told th[65 chars]nder' != ''`
--
`tests.test_intake.LedgerRecordTest.test_a_halt_told_through_park_for_human_names_the_code_it_parks_under`,
which is the checker rule not existing yet.

`Mutated:` twice, once per end. The migration seeded `playbook_stop` instead:
`AssertionError: {'scope_ambiguous', 'destructive_action', 'policy_unclear',
'playbook_halt', 'third_party_impact', 'credential_needed'} not less than or
equal to {'scope_ambiguous', 'destructive_action', 'policy_unclear',
'impact_unauthorized', 'third_party_impact', 'playbook_stop',
'credential_needed'}` -- so the test reads the corpus and not the enum agreeing
with itself. One shipped record lost the code again:
`AssertionError: '' != 'exceptional-conditions/01: a halt told th[65 chars]nder'`
from `test_every_shipped_record_passes` -- so the checker rule bites the real
ledger and not only a record written here.

Forward references this ticket leaves standing: 234, the corpus far end of
this ticket's CONSUMED BY head. The three findings above
were filed as tickets of their own rather than as references from here, by
number: 234 the routing question, 235 the red corpus gate, 236 the documented
database command that runs nothing.

## Bar, 2026-09-02

Machine lines, each with the command that decided it.

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`. Four criteria, four ticked, none deferred.
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`, so the command is the one the change's own files
   decide, named in full:

   ```
   uv run python -m unittest tests.test_roster tests.test_intake \
     tests.test_baseline tests.test_coverage -q
     Ran 283 tests in 21.349s
     FAILED (errors=1)
   ```

   The one error is `tests.test_intake.LedgerCorpusTest.setUpClass`, measured
   red on the parent commit with this ticket's files stashed and filed as 235.
   The two tests this ticket owns are green in that run and were read by name,
   together with the pre-existing test its second mutation was aimed at:

   ```
   uv run python -m unittest \
     tests.test_roster.VocabularyAgreementTest.test_the_codes_a_model_may_park_under_are_codes_the_corpus_files \
     tests.test_intake.LedgerRecordTest.test_a_halt_told_through_park_for_human_names_the_code_it_parks_under \
     tests.test_intake.LedgerRecordTest.test_every_shipped_record_passes -q
     Ran 3 tests -- OK
   ```

   The database end, because this change is a migration:

   ```
   RK_TEST_DATABASE=rk2_t216 uv run python -m unittest \
     tests.test_database.CleanCreationTest tests.test_database.AgentAskTest -q
     Ran 19 tests in 30.252s
     OK
   ```

   `CleanCreationTest` is the corpus applying from empty with the new file in
   it; `AgentAskTest` holds
   `test_a_refused_code_names_the_whole_list_it_is_not_in`, which is criterion
   3 and now compares the refusal against seven rows rather than six. Run
   without an outer `flock`, for the reason filed as 236.
3. **Forward references redeemed.** `grep -rn 'ticket 216'
   docs/specs/production-harness-v2/`, this ticket's own file excluded, prints
   2 lines, both prose in a ticket this build minted and neither a seam-field
   head nor a `deferred to`:

   ```
   234-...md:6   and the corpus says the other, and ticket 216 removed the reason the corpus gave
   234-...md:15  Measured on 2026-09-02, while landing ticket 216:
   ```

   Nothing in the effort was waiting on this ticket, so there was nothing to
   rewrite.
4. **Existing tests still pass, none skipped, deleted or weakened.** The runs
   above, plus `git diff --shortstat` over the six changed source and test
   files: `6 files changed, 164 insertions(+), 85 deletions(-)`. Eighty-one of
   each are `baseline/technique-ledger.jsonl`, one rewritten line per record
   carrying the code. That leaves 83 inserted and 4 deleted across the other
   five files, and the four deletions are the three prose lines of the
   hand-counted sentence in `_launch.py` and the import line
   `tools/check_intake.py` extends. No `.skip`, no removed assertion, no
   deleted test.
5. **The diff is what the ticket asked for.**
   `git status --short --untracked-files=all`, this ticket's own eleven paths:
   the migration (untracked), `roster.py`, `_launch.py`,
   `baseline/technique-ledger.jsonl`, `tools/check_intake.py`,
   `tests/test_roster.py`, `tests/test_intake.py`, this file, and the three
   ticket files this build minted -- `234-`, `235-`, `236-`. They are the
   `Touches` line, this ticket's two test files, and three flow-minted ticket
   files. Eight other files in the same working tree -- `tests/test_database.py`,
   `tests/test_playbook.py`, `tests/test_vertical.py`, `TASKS.md` and tickets
   `84-`, `166-`, `169-`, `233-` -- are another session's repair of ticket 166's
   review findings and are deliberately not in this commit; `git show --stat
   48396d4b` confirms none of them is.
6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

Judgement lines.

**Judgement, red and mutated.** Both watched in this session. The two `Red:`
messages in `## Resolution` are from the run before the migration and the
checker rule existed; the two `Mutated:` messages are from seeding
`playbook_stop` in place of `playbook_halt` and from taking the code back out
of one shipped record. Each mutation failed the end it was aimed at and only
that end.

**Judgement, no unexplained NOBODY.** The far ends are all named and all in
this repository: `park_task_for_human` refuses on the table, the description
is read by every run through `_launch.DESCRIPTIONS`, and the ledger is read by
`tools/check_intake.py`. The one far end this ticket does not reach is the
corpus, filed as 234 rather than left as `NOBODY`.

**Judgement, the live run reached this ticket's case.** There is no
`live-inputs.md` in this effort. The database run above is the live end that
matters here: the corpus applies from empty and `park_task_for_human` refuses
an unknown code against the seven rows the table now holds, which is the case
this ticket changes. No Agent has yet named the new code in a real park; nothing
in the corpus tells one to, which is 234's work.

**Judgement, no injected double.** None was injected. Both new tests read files
on disk -- the migration text and the shipped ledger -- and the database run
uses a real PostgreSQL 18 server.

### Bar re-run, review cycle 1 repair, 2026-09-02

The review's NOW repairs touched this file, tickets 234/235/236, ticket 65's
release closure, one comment in `_launch.py` and one snapshot line in
`tests/test_audit.py`. No production behaviour changed, so no new red test was
owed; the machine lines were re-run and are pasted here under the existing
heading rather than under a new dated one.

```
$ grep -c '^- \[ \]' <this ticket>
0
$ grep -c '^## Resolution' <this ticket>   ->  1
$ grep -c '^## Bar' <this ticket>          ->  1
$ grep -c '^## Handoff' <this ticket>      ->  0
$ grep -c '^## Seam check' <this ticket>   ->  1     (was 0; the gap this cycle repaired)
```

```
$ uv run python -m unittest tests.test_roster tests.test_intake \
    tests.test_baseline tests.test_coverage -q
  Ran 283 tests in 21.412s
  FAILED (errors=1)
```

The one error is unchanged from the build: `LedgerCorpusTest.setUpClass`,
`IntakeError: no ledger record is about playbook payment-webhooks`, filed as
235. Confirmed at the fixed point independently of the build's own claim:
`payment-webhooks` ships as a Playbook at `766b21e1` and the ledger names it 0
times at `766b21e1` and 0 times at HEAD, with 378 records at both.

```
$ uv run python -m unittest \
    tests.test_roster.VocabularyAgreementTest.test_the_codes_a_model_may_park_under_are_codes_the_corpus_files \
    tests.test_intake.LedgerRecordTest.test_a_halt_told_through_park_for_human_names_the_code_it_parks_under \
    tests.test_intake.LedgerRecordTest.test_every_shipped_record_passes
  Ran 3 tests in 0.165s
  OK
```

**The line the build never ran.** `tests.test_audit` was outside the four
modules the build chose, and this commit's own bookkeeping is inside it. Run in
a detached worktree at the build commit, with the concurrent session's work
absent:

```
$ git worktree add --detach /tmp/rk2-216iso 48396d4b
$ uv run python -m unittest tests.test_audit.AuditGateTest
  AssertionError: '... tickets 231 resolved 199 ...'
                != '... tickets 234 resolved 199 ...'
  Ran 6 tests in 20.097s
  FAILED (failures=1)
```

231 issue files at `766b21e1`, 234 at `48396d4b`. The snapshot was refreshed the
way commit `0071ab7c` refreshed it for ticket 230. Setting this ticket
`resolved` then surfaced a second, separate consequence:

```
ticket 216: resolved, and no path reaches ticket 65 from it
```

`check_audit.graph_errors` holds that a resolved ticket must sit in ticket 65's
transitive `Blocked by` closure, and commit `1ba74ee9` appended ticket 231 to
that line in the same commit that resolved it. 216 is appended here for the same
reason, and the error is gone.

```
$ uv run python -c "import tools.check_audit as ca; a=ca.gather(); \
    print([l for l in ca.report(a).splitlines() if 'tickets' in l])"
  ['  tickets                235   resolved 201  audited 63  deferred criteria 11']
  report matches snapshot: True
```

The whole report now matches the snapshot line for line. `tests.test_audit`
still cannot go green, for two reasons this ticket does not own and may not
touch:

```
ticket 84: blocked by 2026, which does not exist
ticket 166: resolved, and no path reaches ticket 65 from it
```

Both are the concurrent session's files, landed in `33fc8ebc`. Recorded as a
finding below and owed to that session.

```
$ git status --short --untracked-files=all
 M docs/specs/production-harness-v2/issues/216-...md
 M docs/specs/production-harness-v2/issues/234-...md
 M docs/specs/production-harness-v2/issues/235-...md
 M docs/specs/production-harness-v2/issues/236-...md
 M docs/specs/production-harness-v2/issues/65-prove-first-hunt-release-candidate.md
 M src/redkraken/_launch.py
 M tests/test_audit.py
```

Seven paths, all this review's. Four others in the same tree -- `README.md`,
ticket `134-`, `src/redkraken/scope.py`, `tests/test_scope.py` -- are the
concurrent session's live work on ticket 134 and are deliberately not staged.

**The database end, re-run at review.** Every axis reader was barred from this
module, so all four left it unsettled; it is re-run here because the ticket is a
migration.

```
$ RK_TEST_SUPERUSER_URL=... RK_TEST_DATABASE=rk2_rev216 \
    uv run python -m unittest tests.test_database.CleanCreationTest
  Ran 9 tests in 25.526s
  OK
```

The corpus applies from empty with `20270111T000000Z` in it. Run without an
outer `flock`, because `setUpModule` takes `/tmp/rk2-db.lock` itself and an
outer one makes the module skip whole with exit status 0 — the trap filed as
236, confirmed again here.

## Review findings, 2026-09-02 — cycle 1

Fixed point `766b21e1`, the parent of `48396d4b`, this ticket's first and only
build commit. The diff reviewed is `766b21e1..48396d4b`, 11 files, 598
insertions, 90 deletions. HEAD advanced to `33fc8ebc` mid-review when a
concurrent session committed ticket 166's review; the eight paths that commit
touched are disjoint from this ticket's eleven, so its work was excluded from
this diff rather than merged into it. Four axes, run as four subagents that
could not see each other, reported apart below.

- [seam] **`tests/test_audit.py::AuditGateTest`: the build added issue files 234, 235 and 236 and did not refresh the audit snapshot, so this commit is red on its own bookkeeping and the Bar's "existing tests still pass" never ran the module that holds it.** — required — NOW. Isolated at the build commit in a detached worktree: `tickets 231` asserted, `234` actual, one failure and nothing else. Snapshot refreshed to the tree's true `235 / resolved 201`, the way `0071ab7c` did for ticket 230.
- [seam] **`check_audit.py::graph_errors`: setting this ticket `resolved` puts it outside ticket 65's `Blocked by` closure, which the gate reads as finished work nothing downstream asks for.** — required — NOW. Found while making the closing edit, not by an axis. `216 — A Playbook halt has no question code to park under` appended to ticket 65's release closure, exactly as `1ba74ee9` appended 231 in the commit that resolved it. Error gone.
- [seam] **`216::## Seam check`: `build-slice` §5 left no report at its address, so the Seam axis had nothing to cold-read and the Bar's "no unexplained NOBODY" judgement rested on a report that does not exist.** — required — NOW. The pass was run at review (greps and recorded far ends against current source, no live replay, `REPLAYS` untouched) and the record is now at `## Seam check, 2026-09-02`. Converged with [ticket] and [bar].
- [seam] **`check_audit.py::graph_errors`: the audit gate raises on `ticket 84: blocked by 2026, which does not exist` and `ticket 166: resolved, and no path reaches ticket 65 from it`, so `tests.test_audit` cannot go green whatever this ticket does.** — required — REOPEN ticket 166. Both defects landed in `33fc8ebc` and live in files this session is barred from touching (`84-`, `166-`). Owed to the concurrent session: 166 needs the same release-closure append this ticket just made, and 84's blocker `2026` looks like a typo for a real ticket number.
- [seam] **`216::## Re-measured`: the Rule certifies "What lands here does not make those paragraphs say anything false", which is untrue.** — required — NOW. Reworded to say plainly that the reason clause goes stale on landing. Converged with [ticket] and [bar].
- [seam] **`216::## Resolution`: "the fifth of the seven rows the table now holds that a model may name" contradicts "the sixth member of the enum" in the same sentence.** — nit — NOW. Now "the sixth of the six rows a model may name", with the seventh named as `impact_unauthorized`. Converged with [ticket], [bar] and [craft] — four axes on one sentence.
- [seam] **`216::## Re-measured`: "every record splits into exactly six ` | ` fields" is true of the eighty-one and false of the corpus; over all 378 the spread is 257 with none and 121 with six.** — nit — NOW. Scoped to the eighty-one and the real spread stated. Converged with [ticket].

- [ticket] **`216::## Re-measured` + `## The wall`: "nine sentences in nine Playbooks" understates the corpus this change falsifies by a factor of three, and the wrong count propagated into ticket 234's measurement block and its criterion 3.** — blocker — NOW. Re-measured over all 51 shipped `playbook.md` with whitespace normalised: 11 sentences in 10 Playbooks count the codes at five, and 21 further Playbooks deny that any served code says a reading ran out without counting them — 31 in the union. The build's single-line grep missed two sentences that wrap `five\ncodes` and all 21 that never use the word. `playbook_halt`'s own `meaning` and its migration comment ("a model naming it is a model saying its own reading ran out") are word for word what the 21 deny. Corrected here and in 234, whose criterion now lists all 31 by name so the session that executes it cannot rewrite nine and leave twenty-two.
- [ticket] **`216::criterion 2` and `## Where the mechanism is`: `roster.py:1771-1775` is `mint_callback`'s `channel` and `subject_label`, not the `question_code` enum — three sites.** — required — NOW. Rewritten to `roster.py:1813-1826`. The `CONSUMES` head cited `1809-1818` for the same enum, so one ticket cited two places for one thing.
- [ticket] **`216::## What it costs`: `_launch.py:1282` is `state_severity` prose about severity bands, not the `park_for_human` description — two sites.** — required — NOW. Rewritten to `_launch.py:1299-1314`, and the `CONSUMES` head's stale `1299-1309` with it.
- [ticket] **`216::## Seam check`: absent, so the axis that exists to read it had nothing to read.** — required — NOW. Converged with [seam]; repaired there.
- [ticket] **`216::**CONSUMED BY:**`: the corpus far end reads "the Playbook corpus, whose halt paragraphs today say that none of the five codes says this", which is not one of `cut-slices` Rule 2's forms, while the Bar's judgement claims the corpus is "filed as 234 rather than left as `NOBODY`".** — required — NOW. Rewritten to `the Playbook corpus, ticket 234`, and `## Resolution` now lists 234 as the one forward reference this ticket leaves standing instead of claiming none.
- [ticket] **Tickets 234, 235 and 236 are headline-only: none carries `PRODUCES`, `CONSUMED BY`, `CONSUMES` or `Touches`, which `hold-the-line` forbids ("a verdict is not a licence for a headline-only ticket").** — required — NOW. All four template lines added to each, written with concrete symbol citations so no new forward-reference debt was created. Verified against `check_audit.gather()`: no new citation or ticket errors.
- [ticket] **`216::## Re-measured`: "records naming any question code 0", under a heading that says "Counted again over the tree as it stands", is 81 after this build and reads as criterion 4 undone.** — required — NOW. Restated as "0 before, 81 after".
- [ticket] **`216::## Resolution`: "fifth of the seven rows".** — nit — NOW. Converged; repaired once.
- [ticket] **`216::## Bar` line 5: "this ticket's own eight paths" against a commit carrying eleven, and "Four other files" introducing a list of five.** — nit — NOW. Both counts corrected, the three minted ticket files accounted for as flow-minted, and all eight foreign paths named. Converged with [bar].
- [ticket] **`tools/check_intake.py::PARK`: criterion 4 says the checker refuses a record whose `stop_conditions` "name `park_for_human`", but `PARK` is `roster.PARK_FOR_HUMAN` — the prefixed `mcp__rk2__park_for_human` — so a record naming the bare verb would escape the gate.** — nit — DECLINED. Measured before declining: all 81 occurrences use the prefixed form and so do all 378 records, because the ledger's `who is told` field cites tool names as the tool surface spells them. A bare-verb record is not a shape this corpus produces, and widening the match is production code for a case that cannot arrive. If ticket 234 changes how that field is graded, it inherits the question.
- [ticket] **`216::## Re-measured`: the six-field claim over-generalises from the eighty-one to the corpus.** — nit — NOW. Converged with [seam].

- [bar] **`216::## Re-measured`: "shipped Playbooks saying there are five codes 9 (in 9 files)" is 11 sentences in 10 files; a single-line grep missed `authentication/playbook.md:168`, whose sentence wraps, and the second sentence in `cookies`.** — required — NOW. Converged with the [ticket] blocker and repaired with it; independently re-measured before accepting, which is how the 21 uncounted Playbooks were found.
- [bar] **`216::## Bar` line 5: the one line whose whole job is comparing the file list leaves the three ticket files this build minted unexplained, and characterises the output instead of quoting it, which the bar forbids.** — required — NOW. Rewritten with the raw short-status output quoted whole.
- [bar] **`216::## Bar`: "Judgement, no unexplained NOBODY" rests on a `## Seam check` report that `grep -c` prints `0` for, while the sibling ticket built the same day carries one — so this is not an effort-wide absence.** — required — NOW. Converged with [seam] and [ticket]; the report now exists.
- [bar] **`216::## Bar` line 5: names four foreign files and lists five, omitting three the concurrent session also touched.** — required — NOW. Converged with [ticket]. All eight named from `git show --stat 33fc8ebc`; the substantive claim was sound — `git show --stat 48396d4b` excludes every one.
- [bar] **`docs/specs/production-harness-v2/spec.md`: the effort has no `## Verify command`, so bar lines 2 and 4 were measured against a scope this ticket chose for itself, excluding `tests/test_playbook.py`, `tests/test_vertical.py` and all but two classes of `tests/test_database.py` — and, as this cycle found, `tests/test_audit.py`.** — required — ALREADY OWNED by ticket 166, which priced this exact wall in writing and ruled that `docs/agents/testing.md` tier 1 stands in. The ticket's claim that the command is absent is true. Naming it in `spec.md` is effort-level work in another session's file; the concrete cost of its absence is the audit-gate finding above, which is repaired here.
- [bar] **`216::## Resolution`: "fifth of the seven rows".** — nit — NOW. Converged; repaired once.
- [bar] **`216::## Bar` line 3: reports "prints 2 lines" without quoting them, while the bar says quoted hits under `## Bar` are history and must be quoted whole.** — nit — NOW. Both hits pasted verbatim; neither is a seam-field head nor a `deferred to`, so the line does pass.
- [bar] **`216::## Build findings`: "Measured on the parent commit `1ba74ee9`" — the parent of `48396d4b` is `766b21e1`.** — nit — NOW. Corrected to `766b21e1`, which is also the commit the red was independently reconfirmed on.
- [bar] **`216::## Bar` line 2: "The two tests this ticket owns are green" precedes a paste naming three, the third being pre-existing and the mutation target.** — nit — NOW. Reworded to name the mutation target as such.
- [bar] **`216::**Touches:**` lists `tests/test_roster.py` and `tests/test_intake.py`, but the bar says `Touches` lists production files only and line 5 then counts them twice.** — nit — NOW. Test files moved to their own line.

- [craft] **`_launch.py::DESCRIPTIONS["park_for_human"]`: the rendered clause restates a vocabulary `Argument.schema()` already serves in the payload's `enum`, and `_launch.py:1053-1057` states this repo's own standard against exactly that — measured, it is the only one of eight top-level enum arguments whose members are all named in its prose.** — required — DECLINED. The measurement is sound and the standard is quoted correctly, but criterion 2 of this ticket asks in as many words for the code to be "in the `enum` ... and in the tool's description", so deleting the clause would fail the ticket rather than satisfy it. The defect the standard guards against is staleness, and rendering off the served enum makes staleness structurally impossible here — which is the same remedy ticket 145 chose. `submit_verdict` names 3 of its 3 members in prose, so naming enum members is not unprecedented in this file. If the standard is to be enforced uniformly across all eight arguments, that is its own ticket and not a change to make inside a review of this one.
- [craft] **`_launch.py:1306` and `tools/check_intake.py:282-285`: the four-hop chain `roster.CONTRACTS[PARK_FOR_HUMAN].arguments["question_code"].enum` is spelled out in two modules, where `roster.py:2099` already publishes exactly this shape as `RUN_TOOL_NAMES` beside its verb constant, commented "read off its contract rather than restated ... so the corpus and the gate cannot come to hold different opinions".** — required — CRITERION on ticket 234. The repo states the pattern one line from where the second copy was written, so this is real; it is also production code in two modules, which makes it planned work rather than a review repair. 234 already edits `tools/check_intake.py` for its own criterion 2, so it is the cheapest honest home. Added there as a fourth criterion naming both call sites; 234 now carries 4, under `hold-the-line`'s ceiling of six.
- [craft] **`20270111T000000Z...sql::DO $check$`: the trailing block re-asks what its own `INSERT` three lines above already answered — `migrate.py:673` wraps each file in one transaction and `migrate.py:74` refuses in-file transaction control, so it cannot run unless the insert succeeded.** — nit — DECLINED. The reader's own measurement is the reason: the idiom appears in 82 of 248 migrations, and deleting seven lines of SQL is a production change that would owe a red test for a block that costs nothing and fails loudly if the seed is ever moved. Everything else in the file matches its siblings.
- [craft] **`_launch.py:1302`: the new comment's locator sends the reader "one line up" for ticket 145's reason, which is 239 lines up at `_launch.py:1063-1068`.** — nit — NOW. Cited as `:1063-1068`. Comment only, so no red test was owed.
- [craft] **`roster.py:1818-1824` / `tests/test_roster.py:1953-1957`: the `impact_unauthorized` rationale is repeated near-verbatim in the enum comment and the test docstring, where this file's habit is to point rather than restate.** — nit — DECLINED. A test that carries the reason it asserts something is a test that survives being read alone, and the two copies are 6 lines apart in intent, not a vocabulary that can drift into disagreement. Recorded so the next review does not raise it again.
- [craft] **`216::## Resolution`: "fifth of the seven rows".** — nit — NOW. Fourth axis to land on this one sentence; repaired once.

Cycle 1 minted no tickets and added one criterion, to ticket 234 rather than to
this one, so this ticket takes `resolved` in this commit. Ticket 234 now carries
4 criteria and 235 and 236 carry 3 each, all under the ceiling of six.

Review cycle 1 of 3 — undecided: none

