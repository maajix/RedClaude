# 134 — An address range has no breadth floor

**What to build:** The floor for a CIDR inclusion that a wildcard inclusion has
had since the beginning, or a written decision that a range does not need one.

**Blocked by:** 117 — The CIDR arm of scope evaluation has no writer.

**Status:** resolved

**Touches:** `src/redkraken/scope.py`, `README.md`.

**PRODUCES:** new contract -- a compile-time refusal of an authorising CIDR
inclusion wider than its family's floor, returned as an
`INVALID_CONFIGURATION` violation beside the routability one.

**CONSUMED BY:** nobody new. `scope.compile_policy` is already called by
`program::run`, `callback::policy_for` and `scope::diagnose`, and every one of
them already refuses on the violations it returns.

**CONSUMES:** `scope::_unroutable` and `scope::address_refusal`, which
establish that an authorising range is refused where it is written;
`parse_network`; ticket 117's decision, for what a range does downstream.

- [x] The asymmetry is stated. A wildcard inclusion must name at least two
      labels of its own, so `*.com` is refused; `README.md` calls it "a floor,
      not a public-suffix rule". A range inclusion has no equivalent. `1.0.0.0/8`
      and `2000::/3` are globally routable at both edges, so `scope._unroutable`
      admits them, and they compile as ordinary inclusions covering sixteen
      million and more addresses.
- [x] The consequence is followed through rather than asserted. What a Program
      scoped that wide actually does depends on what mints subjects from scope,
      and ticket 117 decided a range mints no configured subject at all, so the
      first effect is on what an Entity discovered later is graded as, not on a
      first Task. This ticket carries that reading, measured, before it proposes
      a number.
- [x] The decision is written into this ticket before the code is. Either a
      minimum prefix length per family, refused at compile time beside the
      wildcard rule and stated in `README.md` in the same breath as it; or the
      rule that a range is a statement of authority the operator is answerable
      for, and breadth is theirs to declare -- in which case the ticket says
      what stops a typo, because `/8` and `/28` are one keystroke apart.
- [x] The refusal, if there is one, is at compile time. `scope._unroutable`
      already establishes the shape: refuse where it is written, not at the
      door, because a capability spent against a refused address has already
      cost something.

## Why

Found by the standards axis of the code review on `0759b7b`: *"`*.com` is
refused, but `1.0.0.0/8` and `2000::/3` compile as inclusions. The README
sentence the commit edits is the floor sentence."*

## What was measured, 2026-09-02

Criterion 2 asks for the consequence before the number. Read off the code and
off ticket 117's decision rather than assumed:

- **A range mints nothing.** `record_configured_subjects` filters
  `AND r.pattern_kind = 'exact'`
  (`20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql:203`),
  so a Program
  scoped only by range opens with no configured subject and no first Task. 117's
  decision, point 3.
- **A name inside the range is not admitted by it.** The door decides before it
  resolves, so a request naming `www.example.com` is not authorised by the range
  its address happens to fall in. 117's decision, point 2.
- **So the breadth buys two things.** An Entity reached *by address* inside the
  range is graded `target` by `decide_entity`, and the egress door authorises a
  literal address inside it. On `1.0.0.0/8` that is 16,777,216 addresses
  belonging to other people, every one of them gradeable as this Program's
  target the moment something discovers it.
- **What exists today.** `_unroutable` refuses an authorising range whose edges
  the door would refuse, so `10.0.0.0/8`, `192.168.0.0/16`, `0.0.0.0/0` and
  `::/0` are already out. Measured: `1.0.0.0/8`, `2000::/3`, `2600::/16` and
  `2a00::/12` all pass it, and so compile as inclusions.

## The decision, taken 2026-09-02

**A floor, not the operator's judgement.** The first of the two endings the
ticket offers. The second one -- breadth is the operator's to declare -- fails
its own test: it has to say what stops a typo, and nothing in this harness reads
a scope statement twice. `/8` and `/28` are one keystroke apart and the first
effect of the wrong one is a third party graded as a target, which is the class
of harm the whole scope module exists to prevent.

**The number, per family:**

```
IPv4   minimum prefix length 16
IPv6   minimum prefix length 32
```

Chosen for the same reason the wildcard floor is two labels, not one: it refuses
registry space rather than judging width. IANA hands an RIR an IPv4 /8 and an
IPv6 /12; an RIR hands an ISP down to /24 in IPv4 and /32 in IPv6, and a site
gets /48. So a /16 is the widest block a single organisation ordinarily holds,
and a /32 is the smallest an ISP is given -- anything wider than either is
somebody's registry rather than somebody's network. `*.co.uk` passes the
wildcard floor and a /16 passes this one; both are still the operator's
judgement against the Program, which is what README already says.

**No override.** The wildcard floor has one, `broad`, and it is the exclusion
side rather than an escape hatch: breadth that withdraws authority needs no
floor. This floor sits under the same `effect != EXCLUDE` guard, so an exclusion
may still name `1.0.0.0/8`, and an operator who truly holds more than a /16
writes the blocks they hold.

## Resolution, 2026-09-02

`BREADTH_FLOOR = {4: 16, 6: 32}` and `_too_broad`, beside `_unroutable` in
`src/redkraken/scope.py`, asked at the same point in `compile_policy.add` and
under the same `effect != EXCLUDE` guard. Asked second, so a private range keeps
the sharper of the two answers: `10.0.0.0/8` is the harness's own infrastructure
before it is wide.

Fifteen lines of code and one README sentence. No new name any caller imports,
no caller changed, and no configuration that compiled before this and names a
block at or under the floor compiles differently now. What stops compiling is
`1.0.0.0/8`, `172.0.0.0/8`, `2000::/3`, `2a00::/12` and `2600::/16`, measured to
have passed every existing rule.

`Red:` `AssertionError: the configuration compiled` --
`tests.test_scope.CompilationTest.test_an_inclusion_may_not_name_more_than_one_allocation`,
watched failing on all four of its subtests before `_too_broad` existed, with
`AssertionError: 1 != 0` beside it from
`test_the_breadth_refusal_names_the_floor_it_is_under`, which is
`compile_policy` returning no refusal at all.

`Mutated:` twice. The floor raised to `{4: 17}`:
`AssertionError: (Violation(code='invalid_configuration',
source='scope:scope.include[1].host', detail='93.184.0.0/16 is wider than /17,
which is registry space rather than one allocation; an inclusion may not name
one'),)` -- so `test_a_range_at_the_floor_and_under_it_compiles` holds the floor
from below and this is a floor rather than a ban. The `effect != EXCLUDE` guard
dropped:
`AssertionError: (Violation(..., source='scope:scope.exclude[1].host',
detail='10.0.0.0/8 is wider than /16, ...'),)` -- so the asymmetry is asserted
from both sides, by the new test and by the existing
`test_an_exclusion_may_name_a_private_range`.

Forward references this ticket leaves standing: none. Ticket 117's decision is
cited as a measurement rather than as a debt, and it is resolved.

## Seam check, 2026-09-02

Re-run ordered by the review's Seam axis at cycle 1, because the report
`build-slice` §5 owed this ticket was missing. Greps and the recorded far ends
read against current source; the build commit was the tip when the pass ran, so
neither the seam's producer nor its consumers had moved since the code landed.
No live replay and no `REPLAYS` increment: a review-ordered re-run reads, and
this effort has no `live-inputs.md`.

`PRODUCES: new contract`, so the pass is the contract method -- make the old
behaviour happen and read what each caller does -- rather than a grep for a
value.

```
CONTRACT  an authorising CIDR inclusion wider than its family's floor now makes
          `compile_policy` return `(None, violations)` for a configuration that
          compiled before
          HANDLED BY program::run, reading `policy is None` -- refuses
            `scope_policy` before a connection is opened, so nothing is written;
            callback::policy_for, reading `policy is None`;
            scope::diagnose, reading `policy is None`
          3 on-path production readers, the only three call sites in `src/`.
          9 hits in `tests/` skipped, plus 5 prose mentions in docstrings and
          migration comments. Exercised end to end through the operator command
          rather than argued: `1.0.0.0/8` exits 3 with the violation below,
          `93.184.0.0/16` exits 0 with an 18-rule policy.
WROTE     the INVALID_CONFIGURATION violation at `scope:scope.<list>[i].host`
          READ BY program::run, callback::policy_for and scope::diagnose, each
          reading `policy is None`. No new code or source vocabulary reaches a
          consumer: `_refusal` builds the same shape `_unroutable` already
          returned, which is why no caller changed.
WROTE     BREADTH_FLOOR
          READ BY scope::_too_broad, reading `BREADTH_FLOOR[network.version]`
          -- the only code reader in the tree. `config.py`'s two shape notes
          cite the name in prose, not as an import.
WROTE     README's scope floor sentence
          READ BY operator, via reading README's scope section -- a far end
          grep cannot reach. Read against the constant instead: "at least a
          `/16` in IPv4 or a `/32` in IPv6" matches `{4: 16, 6: 32}`.
READ      pattern.kind == "cidr", pattern.text
          WRITTEN BY scope::parse_pattern -- the only call site in `src/`, and
          `text` is already canonical network text, so the re-parse inside
          `_too_broad` cannot raise on it.
READ      parse_network, for `version` and `prefixlen`
          WRITTEN BY scope::parse_pattern, as above. `version` is only ever 4
          or 6, so the `BREADTH_FLOOR` subscript cannot `KeyError`.
READ      the ordering against `_unroutable`, so `10.0.0.0/8` keeps the
          routability answer
          WRITTEN BY scope::compile_policy.add -- true in source and, since
          this review, asserted by
          `test_an_unroutable_range_keeps_the_routability_answer`.
```

No `NOBODY`, explained or otherwise. The one far end grep cannot reach is the
operator reading README, and it was read against the constant.

## Bar, 2026-09-02

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`; `grep -c '^- \[[ x]\]' <ticket>` prints `4`.
2. **The seam test passes, read by name.** This effort's spec carries no
   `## Verify command`; the modules the change reaches are named in full.

   ```
   NO_COLOR=1 uv run python -m unittest -v \
     tests.test_scope.CompilationTest.test_an_inclusion_may_not_name_more_than_one_allocation \
     tests.test_scope.CompilationTest.test_the_breadth_refusal_names_the_floor_it_is_under \
     tests.test_scope.CompilationTest.test_a_range_at_the_floor_and_under_it_compiles \
     tests.test_scope.CompilationTest.test_an_exclusion_has_no_breadth_floor_either
     ... ok  (4 lines)
     Ran 4 tests in 0.016s
     OK
   ```

   `NO_COLOR=1` is not decoration: this shell exports `FORCE_COLOR=3`, and
   Python 3.14's argparse colours its help, which fails 54 assertions in
   `tests.test_cli` that read `usage: rk <command>` off the front of
   `format_help()`. Measured, and an environment artifact rather than a defect
   in the tree.
3. **Forward references redeemed.** `grep -rn 'ticket 134'
   docs/specs/production-harness-v2/`, this ticket excluded, prints 1 line:
   `216-...md:575`, inside that ticket's dated `## Bar` block, saying its review
   left this ticket's files alone. History by the bar's own rule, no
   `CONSUMED BY`, `CONSUMES` or `deferred to` on it. Nothing was owed to this
   ticket.
4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_scope tests.test_config \
     tests.test_program tests.test_callback tests.test_proxy tests.test_doctor \
     tests.test_cli -q
     Ran 552 tests in 111.066s
     OK
   ```

   `git diff --numstat`: `scope.py` 47 added and 0 deleted, of which 15 are
   code, 13 comment, 13 docstring and 6 blank; `tests/test_scope.py`
   46 added and 0 deleted; `README.md` 5 added and 3 deleted, the floor sentence
   rewritten to carry both floors. No `.skip`, no deleted test, no removed
   assertion. `tests/test_database.py` is untouched by
   this change: `compile_policy` runs before anything is stored, and no shipped
   or test configuration names a block wider than the floor.
5. **The diff is what the ticket asked for.**
   `git status --short --untracked-files=all` holds four paths:
   `src/redkraken/scope.py`, `README.md` -- the `Touches` line -- plus
   `tests/test_scope.py`, this ticket's test file, and this ticket.
6. **The blocks.** `grep -c '^## Resolution' <ticket>` prints `1`,
   `grep -c '^## Bar' <ticket>` prints `1`, `grep -c '^## Handoff' <ticket>`
   prints `0`.

**Judgement, red and mutated.** Both watched in this session, and the two
messages in `## Resolution` are quoted from those runs.

**Judgement, no unexplained NOBODY.** The far end is `compile_policy`'s three
callers -- `program::run`, `callback::policy_for` and `scope::diagnose` -- each
of which already refuses a configuration on the violations it returns. Nothing
new reads anything. The `## Seam check` block this line rests on was missing at
build time and was written by the review's Seam axis at cycle 1; see it above.

**Judgement, the live run reached this ticket's case.** There is no
`live-inputs.md` in this effort and `spec.md` names no `## Load` figure for this
path. The refusal does happen before any live system -- a configuration naming
`1.0.0.0/8` never reaches a door, which is the point of refusing it where it is
written -- but that is not a reason not to run it, and the review replaced the
argument with the run: see the operator command under the review's repair paste
below. The live end that exists -- the door's own `address_refusal` -- is
unchanged and still the second half of the same rule.

**Judgement, no injected double.** None was injected. Every test writes a real
configuration and compiles it through `config.load` and `scope.compile_policy`.

### Review cycle 1 repair paste, 2026-09-02

The machine lines re-run because cycle 1's NOW verdicts changed production code
(`scope.py`'s refusal detail and two docstrings, `config.py`'s two shape notes).
Appended under this heading rather than as a new dated one: a dated `## Bar`
heading is a build's.

1. **Every acceptance criterion is ticked.** `grep -c '^- \[ \]' <ticket>`
   prints `0`; `grep -c '^- \[[ x]\]' <ticket>` prints `4`. No criterion was
   added by this cycle, so the ticket resolves rather than returning to
   `build-slice`.
2. **The seam test passes, read by name.** The four original tests plus the one
   this review added.

   ```
   NO_COLOR=1 uv run python -m unittest -v \
     tests.test_scope.CompilationTest.test_an_inclusion_may_not_name_more_than_one_allocation \
     tests.test_scope.CompilationTest.test_the_breadth_refusal_names_the_floor_it_is_under \
     tests.test_scope.CompilationTest.test_a_range_at_the_floor_and_under_it_compiles \
     tests.test_scope.CompilationTest.test_an_exclusion_has_no_breadth_floor_either \
     tests.test_scope.CompilationTest.test_an_unroutable_range_keeps_the_routability_answer
     Ticket 134: the range half of README's floor sentence. ... ok
     test_the_breadth_refusal_names_the_floor_it_is_under ... ok
     test_a_range_at_the_floor_and_under_it_compiles ... ok
     test_an_exclusion_has_no_breadth_floor_either ... ok
     test_an_unroutable_range_keeps_the_routability_answer ... ok
     Ran 5 tests in 0.015s
     OK
   ```
3. **Forward references redeemed.** Unchanged by this cycle: the only
   `ticket 134` hit outside this file is still `216-...md:575`, inside that
   ticket's dated `## Bar` block, carrying no debt token. Nothing was owed.
4. **Existing tests still pass, none skipped, deleted or weakened.**

   ```
   NO_COLOR=1 uv run python -m unittest tests.test_scope tests.test_config \
     tests.test_program tests.test_callback tests.test_proxy tests.test_doctor \
     tests.test_cli -q
     Ran 553 tests in 118.350s
     OK
   ```

   553 rather than the build's 552: this cycle added one test and removed none.
   `git diff --numstat` over this review's own paths: `README.md` 7/6,
   `TASKS.md` 1/1, `config.py` 7/2, `scope.py` 9/6, `tests/test_scope.py` 17/0.
   `git diff -- tests/test_scope.py | grep '^-'` prints `0` lines, and no
   `.skip`, `# type: ignore`, `noqa` or `nosemgrep` appears on any added line in
   those five paths. The two removed test lines and six silencer hits visible in
   a whole-tree grep are the concurrent session's `tests/test_database.py`, not
   this review's.
5. **The diff is what the review asked for.**
   `git status --short --untracked-files=all` holds eight paths. Six are this
   review's and are staged: `README.md`, `TASKS.md`, this ticket,
   `src/redkraken/config.py`, `src/redkraken/scope.py`,
   `tests/test_scope.py`. Two are the concurrent session's work on ticket 236 --
   `236-...md` and `tests/test_database.py` -- and are deliberately not staged.
   `config.py` and `TASKS.md` sit outside this ticket's `Touches` line: they are
   NOW repairs on findings the review raised there, which is what a review
   commit carries.
6. **The blocks.** `grep -c '^## Resolution'` prints `1`, `grep -c '^## Bar'`
   prints `1`, `grep -c '^## Handoff'` prints `0`, and
   `grep -c '^## Seam check'` now prints `1` where it printed `0` before this
   cycle.

**Judgement, red and mutated, for this cycle's repairs.** Both watched in this
session. The message correction was red first:
`AssertionError: 'more than one allocation' not found in '1.0.0.0/8 is wider
than /16, which is registry space rather than one allocation; an inclusion may
not name one'`. The precedence test was born green, so the mutation is its sole
proof -- `_too_broad` moved above `_unroutable` in `compile_policy.add`:
`AssertionError: 'not a globally routable address range' not found in
'10.0.0.0/8 is wider than /16, which is more than one allocation; an inclusion
may not name one'`. The mutation was reverted and `scope.py`'s diff re-read to
confirm it left nothing behind.

Note on the build's own `Mutated:` quotes above: they quote the pre-review
wording `registry space rather than one allocation`. They are left standing as
the record of what that session watched; the detail now reads `more than one
allocation`, so a future re-mutation prints the new wording.

**Judgement, the operator run, replacing the argued live line.**

```
NO_COLOR=1 uv run python -m redkraken scope --config <SCOPED with 1.0.0.0/8>
  "violations": [{ "code": "invalid_configuration",
    "source": "scope:scope.include[1].host",
    "detail": "1.0.0.0/8 is wider than /16, which is more than one allocation;
               an inclusion may not name one" }]
  exit 3

NO_COLOR=1 uv run python -m redkraken scope --config <SCOPED with 93.184.0.0/16>
  "rules": 18, "targets": 5, "exclusions": 9
  exit 0
```

Both sides of the floor, through the whole operator path rather than through
`compile_policy` alone.

**Judgement, criterion 3's ordering.** The tick on "The decision is written into
this ticket before the code is" rests on the build session's word and cannot be
reconstructed from history: the decision, the code, the README sentence and the
tests all land in `4a30fe66`, and at its parent this file is `needs-triage` with
no decision section. This review can confirm the substance -- the decision
section reasons its way to `/16` and `/32` from registry allocation practice
without reference to the implementation -- but not the order. Recorded here
rather than left implicit, because this session did not witness it.


## Review findings, 2026-09-02 — cycle 1

Four axes, run as four subagents that could not see each other, against the
fixed point `58eecad5` (the build commit's parent) with the diff pinned at
`git diff 58eecad5..4a30fe66` rather than `...HEAD`, because a concurrent
session is committing to `main`. 279 changed lines across four files: one
logical change, reviewable in one sitting.

- [seam] **134::## Seam check: the report `build-slice` §5 owes this ticket was never appended, so the Seam axis had nothing to read and the pass had to be re-derived from source. The Bar's NOBODY judgement names the three far ends but carries no `WROTE`/`READ` record and is not at that address.** — required — NOW. The pass was re-run by the Seam axis (report missing, not stale) and its `WROTE`/`READ` record now sits at the ticket's `## Seam check, 2026-09-02`. Read, not replayed: no `REPLAYS` touched, and this effort has no `live-inputs.md`.
- [seam] **scope.py::compile_policy.add: the Resolution's precedence claim — `_too_broad` asked second, so `10.0.0.0/8` keeps the sharper routability answer — is asserted by nothing. `refused()` compares violation sources and both refusals emit `scope:scope.include[1].host`, so swapping the two guards leaves every test green.** — nit — NOW. `test_an_unroutable_range_keeps_the_routability_answer` asserts the routability detail on the one input that fails both rules. Born green, so the mutation is its proof: `_too_broad` moved above `_unroutable`, the test failed, and the mutation was reverted.
- [seam] **config.py::_RANGE_SHAPE, ::_WILDCARD: the loader-side notes still state the pre-134 world — `_RANGE_SHAPE` names `scope._unroutable` as the only compile-time refusal a range spelling faces and picks its example from that premise; `_WILDCARD` keeps README's old unqualified breadth sentence. No behaviour is wrong; `config.py` is the one place the sentence README rewrote survives unrewritten.** — nit — NOW. Both notes now carry the floor and cite `scope.BREADTH_FLOOR`, and `_WILDCARD`'s sentence gained README's "under the floor" qualifier. Comment-only, so no red test.
- [seam] **134::CONSUMED BY, ::CONSUMES: three citations do not resolve — `scope.py:1487`, `scope.py:1216-1244` offered for `address_refusal` which is at `scope.py:243`, and a migration filename that has never existed.** — nit — NOW. `CONSUMED BY` and `CONSUMES` now name symbols per `cut-slices` Rule 2, and the migration filename is corrected. The line numbers were the defect, not the facts they addressed.
- [ticket] **scope.py::_unroutable: the docstring immediately above the new helper says of `172.0.0.0/8` "That range compiles", which `_too_broad` made false in this same commit — measured, it now returns the breadth refusal. The Resolution's enumeration of what stops compiling omits it as a fifth case, and it is the one block this file's own prose and ticket 117 single out by name.** — required — NOW. The docstring now says the floor takes `172.0.0.0/8` first and that the straddling gap survives only at or under the floor, with `203.0.112.0/22` around `203.0.113.0/24` as a case verified in this session to still compile. `172.0.0.0/8` added to the Resolution's list as its fifth refused block.
- [ticket] **scope.py::compile_policy.add: the same precedence claim, measured from the other side — swapping the two guards leaves 608 tests green across eight modules. Converged with [seam].** — required — NOW. Same repair as the [seam] entry above. The two axes converged on it independently, which is why it was treated as this cycle's third structural finding rather than a nit.
- [ticket] **134::criterion 3 "The decision is written into this ticket before the code is": the tick asserts an ordering the repository cannot show. `git log --follow` on the ticket gives two commits; at `58eecad5` the file is `needs-triage` with no decision section, and `4a30fe66` lands the decision, the code, the README sentence and the tests together. The substance is delivered; only the "before" is unevidenced, and the Bar carries a witness line for red and mutated but none for this.** — required — NOW. Recorded rather than re-asserted: a judgement paragraph under `## Bar` now states that the "before" rests on the build session's word, cannot be reconstructed from `4a30fe66`, and that this review confirms the decision's substance but not its order. No criterion added -- the substance was delivered.
- [ticket] **134::CONSUMED BY: `program.py:241` and `callback.py:625` are exact at the build commit, but `scope.py:1487` resolves only at the parent — it is `scope.py:1534` at `4a30fe66`. Converged with [bar] and [seam].** — nit — NOW. Same repair as the [seam] citation entry; both entries kept because both axes raised it.
- [ticket] **134::What was measured: `20260831T000000Z__a_program_opens_with_a_subject.sql:203` names a file that has never existed in the tree; the `AND r.pattern_kind = 'exact'` filter is at that line of `20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql`. The claim is true, the address is not, and criterion 2 rests on this block.** — nit — NOW. Corrected to `20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql:203`, opened and read to confirm the filter sits on that line.
- [ticket] **134::Resolution: "Nine lines of code", and the Bar's "9 are code and 38 are the constant's note and the helper's docstring", are unmeasured. Classified: the 47 added lines are 15 code, 13 comment, 13 docstring, 6 blank.** — nit — NOW. Corrected to 15 code / 13 comment / 13 docstring / 6 blank in both places. Measured here rather than taken from an axis: two axes agreed on the 47 total and one produced a split summing to 49.
- [ticket] **134::What was measured: "117's correction, point 2" misattributes — 117's two `## Correction:` sections are about `proxy.py` not being the second evaluator and about a CHECK comment. The claim is point 2 of 117's decision, and it is confirmed in source by `Pattern.covers`.** — nit — NOW. Corrected to "117's decision, point 2".
- [ticket] **134::Resolution: "Nothing new is exported" is false as written — `BREADTH_FLOOR` carries no leading underscore and `scope.py` has no `__all__`, so it is importable.** — nit — NOW. Reworded to "No new name any caller imports", which is what the sentence was reaching for and is true.
- [ticket] **README.md:259: the rewrite left a 128-character line in a paragraph otherwise wrapped at 80. Converged with [bar] and [craft] — three axes.** — nit — NOW. The paragraph was reflowed; its longest line is now 78. Three axes converged here.
- [bar] **134::## Seam check: `grep -c '^## Seam check'` prints 0, so the standing bar's judgement line "The `## Seam check` report shows no unexplained NOBODY" is ticked with nothing under it, and `/prove` has no report to read. The ticket changed an interface, which is exactly the `seam-check` trigger. Converged with [seam].** — required — NOW. Converged with [seam]; one repair. The judgement line now points at the report it rests on, and the grep prints 1 where it printed 0.
- [bar] **scope.py::diagnose: the `CONSUMED BY` line and the Bar's NOBODY judgement both cite `scope.py:1487`, which this commit's own 47 added lines pushed to 1534; line 1487 is now the operator-diagnostic comment banner. `cut-slices` Rule 2 exists for this failure mode. Converged with [ticket] and [seam].** — required — NOW. Both citations replaced with symbols. The line had drifted again to 1537 by the time this review's own docstring repair landed -- the argument for Rule 2 made twice inside one cycle.
- [bar] **134::## Bar: the live-run judgement argues no run was possible — "this refusal happens before any live system" — when one operator command reaches the case. A reason not to run stood where a one-command run fits.** — nit — NOW. The argument was replaced with the run: `rk scope --config` exits 3 with the violation on `1.0.0.0/8` and 0 with an 18-rule policy on `93.184.0.0/16`, both pasted under `## Bar`.
- [bar] **134::## Bar: bar line 4 characterizes its numstat instead of quoting it, against the bar's own "never characterize output instead of quoting it"; the three numstat totals beside it reproduce exactly. Converged with [ticket].** — nit — NOW. The characterization is corrected, and the repair paste quotes its own numbers per path instead of describing them.
- [bar] **TASKS.md:437: still lists 134 under "Bewusst zurückgestellt" — deliberately postponed, not required for the first autonomous milestone — while the ticket was built. Not a bar line 3 failure: the line carries no debt token and TASKS.md:425 declares itself a derived view.** — nit — NOW. Dropped from the deferral list. Staged as a single hunk applied to the index, because a concurrent session's ticket 236 edit sits in the same file and must not ride this commit.
- [craft] **scope.py::_unroutable: the paragraph directly above the new helper now states the opposite of current behaviour, and it is the comment a maintainer of this area reads first. Converged with [ticket] — two axes landed on it independently, which is signal about its weight.** — required — NOW. Converged with [ticket]; one repair, described there. Two independent axes landing on it is what moved it above the nits.
- [craft] **scope.py::_too_broad: the operator-facing detail asserts "which is registry space rather than one allocation" for every prefix under the floor, including `1.0.0.0/15` — two /16s, not registry space. The ticket's own reasoning is that an operator must be able to tell what they wrote from the refusal.** — nit — NOW. The detail now reads "is wider than /N, which is more than one allocation" -- `_too_broad`'s own summary wording -- and the registry reasoning stays in the `BREADTH_FLOOR` note where it is correct. Red first: the new assertion failed against the old string before the string changed.
- [craft] **config.py:146-148: the third copy of the floor sentence still ends "how wide an inclusion may be remains the operator's judgement against the Program" — the clause README just qualified with "under the floor", and the clause the new `BREADTH_FLOOR` note cites README for. A reader of `config.py` concludes there is no width limit. Converged with [seam].** — nit — NOW. Converged with [seam]; one repair covering both `config.py` notes.
- [craft] **README.md:254-259: the 128-character line, plus "Those are floors, not a public-suffix rule" mismatching number, and "not a width judgement" sitting two clauses before "remains the operator's judgement". Converged with [ticket] and [bar].** — nit — NOW. Converged with [ticket] and [bar] on the wrap, and the number disagreement is fixed too: the sentence now reads "Both are floors rather than public-suffix rules or width judgements".
- [craft] **scope.py::compile_policy.add: two consecutive `if effect != EXCLUDE and ...` guards, the second carrying five comment lines whose first sentence exists only to say "same guard as above, for the same reason". The duplicated condition is what forced the duplicated prose.** — nit — DECLINED. The two guards read as two independent rules, which is what they are: one asks the door's question and one asks the floor's, each returning its own refusal. Merging them couples two rules deliberately kept separable, for the three tokens the repeated condition costs. `review-pass` says not to block on taste on shipped, tested, correct code.
- [craft] **scope.py::_too_broad, ::BREADTH_FLOOR: the module spells a bool predicate as an adjective (`_unroutable`) and a reason-or-None as `<subject>_refusal` (`address_refusal`). `_too_broad` reads as the first and returns the second, which is why the call site needs `is not None`. `BREADTH_FLOOR` is public while the file's other one-helper numeric limits are private, with 0 references outside `scope.py`.** — nit — DECLINED on the rename. The false sentence it rested on -- "Nothing new is exported" -- was fixed as its own finding above, so the ticket no longer misdescribes the constant. A rename is a production change whose only red test would assert a naming convention, and the constant has no reader outside `scope.py` to break. The observation is right; the churn is not worth it. If a second reader ever appears, `_breadth_refusal` is the name.
- [craft] **tests/test_scope.py::CompilationTest: `test_an_exclusion_has_no_breadth_floor_either` is `test_an_exclusion_may_name_a_private_range` five lines below it with one literal changed, and `test_the_breadth_refusal_names_the_floor_it_is_under` re-implements `refused()` inline on the same input as the test above it, dropping that helper's `policy is None` guard.** — nit — DECLINED. Parallel structure with the rule each test sits beside is this module's existing style -- the new breadth tests deliberately mirror the `_unroutable` tests directly above them. The inline `refused()` re-implementation is forced by that helper returning sources only, and it is the shape the neighbouring detail test already uses; the `AttributeError` path needs a fixture that fails to load, which this one does not.
- [craft] **134::Bar item 4: the numstat split is wrong, though the judgement it was offered to support still holds — the file's own prose:code ratio is 0.60, `_unroutable` alone is 1.5, the new code 1.73, so the density fits its neighbours. Converged with [ticket] and [bar].** — nit — NOW. Converged with [ticket] and [bar]; the split is corrected and the density judgement it supported is left standing, because it was independently re-measured and holds.

Review cycle 1 of 3 — undecided: none
