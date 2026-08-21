# 130 — Check the wiring the way check_audit checks the tracker

**What to build:** `tools/check_wiring.py`, beside `tools/check_audit.py`: one
gate that refuses a declared thing with no producer, no consumer or no caller
unless a registry row names the ticket that owes one.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The gate ships with a registry, not with an empty result. Every finding
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
- [ ] The checks are one reconciled set, and the mapping to the four audits is
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
- [ ] The split between what this tool can answer and what only a live database
      can answer is decided and stated. `check_audit.py` reads files and needs
      no server; `check_wiring.py` keeps that property for W1, W2, W5, W9's
      corpus half and W10, all of which are answerable from
      `src/redkraken/**/*.py`, `src/redkraken/migrations/*.sql` and the corpus
      directories. W3, W4, W6, W7 and W8 need catalogue state, and those belong
      in `standing_checks` and `src/redkraken/integrity.py`, which already owns
      the idea -- `integrity.py:4-8`: "The defect that registry exists to
      prevent is a checker with no caller." The tool asserts that the
      database-side checks are registered; it does not reimplement them.
- [ ] W3's roots are complete, or it is worse than nothing. Reachability
      propagates through the SQL call graph, and the roots include Python call
      sites, `CREATE TRIGGER ... EXECUTE FUNCTION` bindings and the query
      strings in `standing_checks`. Without the last two, every `check_*`
      function in the corpus is a false positive and the gate gets switched off.
- [ ] `runtime_verb_surface` is not used as the registry, and the tool says why.
      It is catalogue-seeded
      (`20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:169-173`)
      and answers "may execute", not "does execute". The registry W3 needs is a
      new one beside it, one row per granted verb naming its caller or the
      ticket that owes one.
- [ ] The gate is proven against a defect it would have caught, by test. The
      cheapest is ticket 38's prose claim that `open_impact_task` and
      `state_severity` "are called by the CLI and by the tests": W3 measures
      that instead of believing it, and the measurement disagrees.
- [ ] The tool refuses with a list rather than the first error, prints a
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
