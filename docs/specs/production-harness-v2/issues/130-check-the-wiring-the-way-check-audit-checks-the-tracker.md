# 130 — Check the wiring the way check_audit checks the tracker

**What to build:** `tools/check_wiring.py`, beside `tools/check_audit.py`: one
gate that refuses a declared thing with no producer, no consumer or no caller
unless a registry row names the ticket that owes one.

**Blocked by:** nothing.

**Status:** resolved

- [x] The gate ships with a registry, not with an empty result. Every finding
      tickets 102 to 129 own is a row the gate would report today, so the tool
      is unusable unless a known gap can be recorded as a tracked absence. The
      shape already exists twice in this repo: `roster.FORBIDDEN_BUILTINS`
      (`src/redkraken/roster.py:902-931`), where every built-in a role does not
      hold states why and the compile refuses an unclassified one
      (`roster.py:1547-1551`), and `check_audit.py`'s `owed:NN`, where a requirement
      whose work is not finished names the open ticket that owes the
      verification. `check_wiring` takes the second spelling: a gap is either
      wired or `owed:NN`, and an `owed` row whose ticket is resolved is itself a
      failure.
- [x] The checks are one reconciled set, and the mapping to the four audits is
      recorded once in the tool's docstring so neither numbering has to be
      repeated afterwards:

      W1 every Contract is served or declared unserved with a reason -- 21 G1;
      W2 every declared argument is consumed end to end -- 21 G2;
      W3 every granted SQL verb has a caller, a trigger binding, a standing
      check or an `owed` row -- 21 G3, 21 G10, 23 G4, 23 G5;
      W4 every relation on the agent read surface is read by a tool or declared
      unread -- 21 G4, the read half of 23 G8;
      W5 a proposal element list has a read verb that returns it, a result mints
      no handle the read verbs cannot resolve, and a result is not narrower than
      the value it was built from -- 21 G5, G6, G7;
      W6 every table has a producer or is registered seed-only, every column a
      rule depends on has a writer, every generated column has a row that makes
      it true, every view has a reader, and every constraint is falsifiable --
      23 G1, G2, G3, G6, the write half of G8;
      W7 cross-table guard satisfiability -- 23 G7;
      W8 a Contract's declared write target has both a writer and a handler --
      23 G9;
      W9 every declared property class is emitted, gradeable and satisfiable,
      every closed set is served from the table that declares it, and a
      migration that moves a constraint re-issues the column comment -- 20 G1
      through G8;
      W10 a Playbook or Skill body names only tools the executing role holds,
      arguments those tools declare, offline programs granted to that role, and
      no artifact the same body earlier described fetching over the wire -- 22's
      eight checks.
- [x] The split between what this tool can answer and what only a live database
      can answer is decided and stated. `check_audit.py` reads files and needs
      no server; `check_wiring.py` keeps that property for W1, W2, W5, W9's
      corpus half and W10, all of which are answerable from
      `src/redkraken/**/*.py`, `src/redkraken/migrations/*.sql` and the corpus
      directories. W3, W4, W6, W7 and W8 need catalogue state, and those belong
      in `standing_checks` and `src/redkraken/integrity.py`, which already owns
      the idea -- `integrity.py:4-8`: "The defect that registry exists to
      prevent is a checker with no caller." The tool asserts that the
      database-side checks are registered; it does not reimplement them.
- [x] W3's roots are complete, or it is worse than nothing. Reachability
      propagates through the SQL call graph, and the roots include Python call
      sites, `CREATE TRIGGER ... EXECUTE FUNCTION` bindings and the query
      strings in `standing_checks`. Without the last two, every `check_*`
      function in the corpus is a false positive and the gate gets switched off.
- [x] `runtime_verb_surface` is not used as the registry, and the tool says why.
      It is catalogue-seeded
      (`20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:169-173`)
      and answers "may execute", not "does execute". The registry W3 needs is a
      new one beside it, one row per granted verb naming its caller or the
      ticket that owes one.
- [x] The gate is proven against a defect it would have caught, by test. The
      cheapest is ticket 38's prose claim that `open_impact_task` and
      `state_severity` "are called by the CLI and by the tests": W3 measures
      that instead of believing it, and the measurement disagrees.
- [x] The tool refuses with a list rather than the first error, prints a
      one-line measurement per check when it passes, and exits non-zero
      otherwise -- the same contract as the other gates in `tools/`.

## Why

All four audits end with a "What a gate would have to assert" section, and they
are four statements of one rule: a thing this system declares -- a table, a
column, a view, a verb, a Contract, an argument, a class, a tool named in a
Playbook -- must have something on the other end of it, or a recorded reason
why not. Every one of tickets 102 through 129 exists because that rule was
enforced by review and review does not scale to 139 migrations, 509 SQL
functions, 16 Contracts and three corpora.

`docs/research/wiring/21-agent-surface-wiring.md` states the case in its own
words: the `check_*` registry exists precisely to prevent a checker with no
caller, "that gate exists for `check_*` functions and for nothing else. Every
finding in this document is the same defect in a place that gate does not look."

The ordering matters. This ticket does not block the others and is not blocked
by them: it is what stops the next twenty-eight from being written by hand in a
year's time.

## What was built

`tools/check_wiring.py`, 1814 lines, and `tests/test_wiring.py`, 340 lines and
seventeen cases. The gate runs as
`PYTHONPATH=$PWD python3 -s tools/check_wiring.py` and prints eleven lines: one
per check with what it measured, and one for the register.

It reads three trees and imports none of them. `src/redkraken/migrations/*.sql`
is lexed into runs of code, comment, single-quoted string and dollar-quoted body
before anything is scanned, because this corpus names its own verbs inside
comments constantly and a scan that did not know a comment from a statement
would have scored five mentions of `state_severity` as callers and agreed with
ticket 38. Every DDL event is collected with the position it was written at and
applied in that order, so a `DROP FUNCTION` followed by a `CREATE FUNCTION` of
the same name in one file resolves to the recreation, and the `DELETE` at
`20260810T151500Z:185` followed by the `INSERT` at `:205` resolves the read
surface the way the server would. `src/redkraken/*.py` is read with `ast`, and
docstring constants are excluded from the word scan, because a docstring that
names `select_playbooks` is not a call site. The two corpora are read for their
frontmatter and their bodies, without a YAML parser: the corpus writes its lists
and objects as JSON, so `json.loads` reads them.

## The split, which criterion 3 guessed at and got the wrong way round

Criterion 3 assigns W3, W4, W6, W7 and W8 to the database. Three of those five
are answerable from files, and the reason is that the migrations are where the
answers live: a `GRANT EXECUTE`, a `CREATE TRIGGER ... EXECUTE FUNCTION`, an
`INSERT INTO standing_checks`, a `CREATE TABLE` and every `INSERT` in a function
body are all written down in this repository. So W3, W6, W8 and all but one row
of W4 are measured here, and the split is by what a file can answer rather than
by which layer the question is about.

What is genuinely deferred is deferred by name, as a row the gate reports until
a standing check exists:

* W4's catalogue-seeded half. `20260909T000000Z:169-173` seeds part of the read
  surface from `has_column_privilege`, and no file can say what that holds.
* W6's column-writer and constraint-falsifiability arms. Both are questions
  about expressions evaluated against column defaults, and a file reader that
  attempted them would answer with the hundred and ninety-four findings the
  database audit already published and no way to tell the fifteen deliberate
  ones from the rest.
* W7 entire. Cross-table guard satisfiability means chasing every CHECK through
  every trigger's requirements and refusals along the foreign keys between them,
  and a guess at that would be wrong in the direction that matters: it would
  clear a contradiction that is there.

Each is a `Gap` naming the standing check that does not exist, which is
`integrity.py:4-8` applied to this gate's own blind spots -- "the defect that
registry exists to prevent is a checker with no caller" -- rather than a
reimplementation of what `integrity.py` owns.

## The register

125 rows naming 21 open tickets: W10 41, W4 28, W3 21, W6 16, W9 9, W5 5, W1 3,
W7 1, W8 1. Every row was measured before it was written, and both directions
fail. A gap with no row is refused as `unregistered:`. A row whose gap is gone is
refused with `remove the row`, because a tracked absence that outlives its gap
goes on excusing the next one to appear under the same name. A row naming a
resolved ticket over a gap that is still there is refused too, which is the rule
`check_audit` writes for its own `owed:NN` rows.

`runtime_verb_surface` is not that register, and the tool says so where the
reader meets it. It is seeded from the catalogue at
`20260909T000000Z:169-173` and answers "may execute"; W3 asks "does execute",
and the two are the same question only in a system where nothing was ever
granted and left.

## One gap the plan cut no ticket for, and two that were not gaps

Found by measuring rather than by reading the audits. `find_in_database` is
granted to `rk2_runtime` and called by nothing, and it is recorded against this
ticket because this gate is what found it: it is the cross-table secret sweep,
and the redaction verifier ticket 125 owes is what would feed it.

`cross_program_exempt_fks` and `program_isolation_candidates` first landed here
the same way, as `owed:130` rows. Both turned out to be the database audit's own
harmless verdicts read as gaps by a check with no way to tell them apart: an
override table that stays empty on purpose reads exactly like a table nothing
fills, and a view selected only inside a `DO` block reads exactly like one
nothing selects. Naming them and excluding them by name, in `producer_gaps`
above `BY_DESIGN`, is the honest fix -- a register row would have kept this
ticket open to track two things that are not wrong, and a shape wide enough to
catch both automatically is a shape wide enough to excuse a real one.

W4 also reports seven relations more than the twenty-one the agent-surface audit
counted by hand. Four of them -- `finding_chain_step_citations`,
`finding_effects`, `report_renderings`, `report_template_blocks` -- reach the
surface through `0034_reports.sql:1084-1092`, which selects their columns out of
the catalogue and names the relations in a `WHERE` rather than writing a `VALUES`
row per column. A reading that only looked for `VALUES` missed them, and the
same statement shape is why `surface_facts`, `report_mechanisms`,
`program_known_issues` and `finding_chain_steps` are on it too.

## Two arms that are not there, and why

**W9's stale-declaration arm.** The vocabulary audit's rule is that a migration
changing a constraint on a column re-issues that column's comment in the same
file. Implemented per table it reports twenty-two files, of which exactly one is
the instance the audit names; per column it reports forty-four. The audit grades
that arm a warning and calls it partly social, and a gate that opens with
twenty-one corrections to find one stale sentence is a gate somebody turns off.
It is stated as absent in the check's own docstring rather than shipped noisy.

**W2 does not ask about a proposal's element lists.** They are read through
`proposal.Result.elements(name)`, which takes the name as a parameter and says
why it holds no copy of them: "a second copy of those names here is a second copy
that could be right about a list the schema no longer accepts." A name scan
cannot see a read like that. The question W2 would have asked wrongly is the one
W5 asks properly -- not whether the list is read, but whether anything promotes
it into a relation the read verbs return -- and W5 reports an element list no
promotion step names as its own gap.

## What it is proven against

Ticket 38 states that `open_impact_task`, `open_impact_replay` and
`state_severity` "are called by the CLI and by the tests". W3 measures it:
`open_impact_replay` is called from Python and the sentence is right about it;
the other two are granted to `rk2_runtime`, reached from no call site, no trigger
binding and no standing check, and the claim has been believed in every review
since. `TicketThirtyEightTest` asserts the sentence is still in the ticket, that
the measurement disagrees, and that the gate reports both verbs.

The rest of the suite holds the register to its own identity -- each check owes
exactly the rows it owns, and every row names an open ticket -- and asks the
readings one at a time: that a comment is not a caller, that removing the trigger
bindings or the standing-check queries from the roots loses reachability that
`check_program_isolation` depends on, that a relation named in a `WHERE` is on
the read surface, and that a Playbook is measured against the role derived from
its Skills rather than a guessed one. Both refusal directions are asserted
through `main`, which prints every reason and exits 1.
