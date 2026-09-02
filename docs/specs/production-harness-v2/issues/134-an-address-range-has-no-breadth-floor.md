# 134 — An address range has no breadth floor

**What to build:** The floor for a CIDR inclusion that a wildcard inclusion has
had since the beginning, or a written decision that a range does not need one.

**Blocked by:** 117 — The CIDR arm of scope evaluation has no writer.

**Status:** claimed

**Touches:** `src/redkraken/scope.py`, `README.md`.

**PRODUCES:** new contract -- a compile-time refusal of an authorising CIDR
inclusion wider than its family's floor, returned as an
`INVALID_CONFIGURATION` violation beside the routability one.

**CONSUMED BY:** nobody new. `scope.compile_policy` is already called by
`program.py:241`, `callback.py:625` and `scope.py:1487`, and every one of them
already refuses on the violations it returns.

**CONSUMES:** `_unroutable` and `address_refusal` (`scope.py:1216-1244`), which
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
  (`20260831T000000Z__a_program_opens_with_a_subject.sql:203`), so a Program
  scoped only by range opens with no configured subject and no first Task. 117's
  decision, point 3.
- **A name inside the range is not admitted by it.** The door decides before it
  resolves, so a request naming `www.example.com` is not authorised by the range
  its address happens to fall in. 117's correction, point 2.
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

Nine lines of code and one README sentence. Nothing new is exported, no caller
changed, and no configuration that compiled before this and names a block at or
under the floor compiles differently now. What stops compiling is
`1.0.0.0/8`, `2000::/3`, `2a00::/12` and `2600::/16`, measured to have passed
every existing rule.

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

   `git diff --numstat`: `scope.py` 47 added and 0 deleted, of which 9 are code
   and 38 are the constant's note and the helper's docstring; `tests/test_scope.py`
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
callers -- `program.py:241`, `callback.py:625`, `scope.py:1487` -- each of which
already refuses a configuration on the violations it returns. Nothing new reads
anything.

**Judgement, the live run reached this ticket's case.** There is no
`live-inputs.md` in this effort, and this refusal happens before any live
system: a configuration naming `1.0.0.0/8` never reaches a door, which is the
point of refusing it where it is written. The live end that exists -- the door's
own `address_refusal` -- is unchanged and still the second half of the same
rule.

**Judgement, no injected double.** None was injected. Every test writes a real
configuration and compiles it through `config.load` and `scope.compile_policy`.
