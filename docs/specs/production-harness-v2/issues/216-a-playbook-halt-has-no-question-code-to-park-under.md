# 216 — A Playbook halt has no question code to park under

**What to build:** A question code that means "a Playbook reached a halt it
declared, and the reading stops here", so that a step which tells the operator
why it stopped can park under the reason it actually has.

**Blocked by:** nothing.

**Status:** claimed

**Touches:**
`src/redkraken/migrations/20270111T000000Z__a_declared_halt_has_a_code_to_park_under.sql`,
`src/redkraken/roster.py`, `src/redkraken/_launch.py`,
`baseline/technique-ledger.jsonl`, `tools/check_intake.py`,
`tests/test_roster.py`, `tests/test_intake.py`.

**PRODUCES:** new contract -- one `decision_question_codes` row, `playbook_halt`,
and the sixth member of the `question_code` enum a model may name.

**CONSUMED BY:** `park_task_for_human`
(`20261028T000000Z:407-414`), which refuses a code that is not a row; the
Playbook corpus, whose halt paragraphs today say that none of the five codes
says this; any operator console keyed on `pending_decisions.question_code`.

**CONSUMES:** `decision_question_codes` (`20260814T020000Z:47-72`), the
`question_code` enum (`roster.py:1809-1818`), the `park_for_human` description
(`_launch.py:1299-1309`), `baseline/technique-ledger.jsonl`.

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

The model-facing surface is narrower than the table. `roster.py:1771-1775`
declares the argument's `enum` with **five** members -- `impact_unauthorized` is
the runtime's own, not something an Agent may claim -- and `_launch.py:1282`
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
- **Two lines in the package.** The `enum` at `roster.py:1771-1775` gains the
  sixth member, and the prose at `_launch.py:1282` stops saying "five".
- **The ledger, mechanically.** All eighty-one records name the same halt, so
  the code goes in with one pass and no per-record judgement.

Ticket 101 does not do this: it is a corpus rewrite, and this is a change to the
vocabulary the tool surface offers. Capability before catalogue -- the code
lands before the sixteen Playbooks that would use it.

## Acceptance criteria

- [x] **A code exists for a declared halt.** One row in
      `decision_question_codes`, whose `meaning` and `asked_when` say that the
      Playbook's own stop condition fired, rather than that a risk rule did.
- [x] **A model may name it.** It is in the `enum` at `roster.py:1771-1775` and
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
  records naming any question code                       0
src/redkraken/playbooks/
  shipped Playbooks                                     51
  shipped Playbooks naming park_for_human               39   (the ticket says 0)
  shipped Playbooks naming a question code              42
  shipped Playbooks saying there are five codes          9   (in 9 files)
```

Every one of the eighty-one occurrences sits in field 5 of `stop_conditions`,
`who is told`, and every record splits into exactly six ` | ` fields. So the
mechanical pass this ticket priced is one token replacement and no per-record
judgement, as written.

### The wall this ticket did not have

**Wall.** Ticket 101 is `resolved`, so the corpus rewrite this ticket forecast
has already happened. It did not file eighty-one falsehoods. It routed around
the missing code in prose, in nine sentences in nine Playbooks:

```
src/redkraken/playbooks/authentication/playbook.md:168
  Every other halt is a reading that ran out -- a declared count reached, a
  credential burnt, a lockout or a 429 arriving mid-sequence -- and none of the
  five codes says that, so those are reported through the Task's own record.
```

Adding a sixth code makes the count in those nine sentences wrong, and makes
their routing decision -- report rather than park -- a decision nobody has
re-taken since the code exists.

**Price.** Rewriting the nine paragraphs to park under the new code is not a
prose fix: it changes what an Agent does at a declared halt in nine Playbooks,
from finishing the Task with a report to stopping it and waiting for a person.
For a halt like "a command sink has been proved" those are opposite behaviours,
and the ledger and the corpus disagree about which is right -- the ledger says
`park_for_human`, the corpus says the Task's own record.

**Purpose.** This ticket is the capability: a code that says what happened, so
that whoever adopts it is not choosing between a wrong code and no code. Its own
words: "Capability before catalogue -- the code lands before the sixteen
Playbooks that would use it."

**Rule.** The code, the enum, the description, the ledger and the checker land
here. The nine corpus paragraphs are not rewritten by this ticket, and the
routing question they hold -- does a declared halt park, or report? -- is filed
as its own ticket rather than answered in passing. What lands here does not make
those paragraphs say anything false: they will still be nine Playbooks that
report rather than park, which is what they already do.

The description is rendered from the enum rather than counted by hand, the way
ticket 145 renders `observation_provenance`. That is the same defect this ticket
is about: a sentence that counted a closed vocabulary and went stale when the
vocabulary grew.

## Build findings, 2026-09-02

Three things this build ran into that are not this ticket's work. None of them
blocked it; each is written down here rather than fixed in passing.

- **DISCOVERY. `tests.test_intake.LedgerCorpusTest` is red on `main`, before
  this change.** `check_techniques()` raises `no ledger record is about playbook
  payment-webhooks`. Measured on the parent commit `1ba74ee9` with this
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
- **DISCOVERY. The nine corpus paragraphs are now a decision nobody has
  taken.** Priced above. A Playbook that says a declared halt is reported
  through the Task's own record, and eighty-one ledger records that say the same
  halt is told to the operator through `park_for_human`, disagree about the same
  halt. This ticket gives that halt a truthful code and does not settle which of
  the two is right.

## Resolution, 2026-09-02

One row, one enum member, one rendered sentence, eighty-one records and one
refusal. No verb changed, no rule changed, no existing decision moved.

`playbook_halt` is seeded by
`20270111T000000Z__a_declared_halt_has_a_code_to_park_under.sql` and means the
Playbook's own stop condition fired. It is the sixth member of the
`question_code` enum, and the fifth of the seven rows the table now holds that a
model may name -- `impact_unauthorized` stays out, for the reason the ticket
gives.

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

Forward references this ticket leaves standing: none. The three findings above
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
   The two tests this ticket owns are green in that run and were read by name:

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
   2 lines. Nothing in the effort was waiting on this ticket, so there was
   nothing to rewrite.
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
   `git status --short --untracked-files=all`, this ticket's own eight paths:
   the migration (untracked), `roster.py`, `_launch.py`,
   `baseline/technique-ledger.jsonl`, `tools/check_intake.py`,
   `tests/test_roster.py`, `tests/test_intake.py` and this file. They are the
   `Touches` line plus this ticket's two test files. Four other files in the
   same working tree -- `tests/test_database.py`, `tests/test_playbook.py`,
   `tests/test_vertical.py`, `TASKS.md` and ticket 169 -- are another
   session's repair of ticket 166's review findings and are deliberately not in
   this commit.
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
