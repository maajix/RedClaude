# 105 — Two request Contracts name a queue nothing serves

**What to build:** A decision, then a handler or a deletion, for
`mcp__rk2__request_validation` and `mcp__rk2__request_report`, and for
`report_queue`, which is a declared table with no producer, no consumer and a
Contract pointing at it.

**Blocked by:** 102 — Nothing in this tree has ever created a Finding.

**Status:** needs-triage

- [ ] `report_queue` is settled first, because it is the cleaner case.
      Declared at `0020_state_access.sql:134` with a state CHECK, an FK to
      `programs`, two RLS policies, a row in that migration's program-scoping
      registry at `:185` and a row in `0030_corpus_corrections.sql` classifying
      it `derived`. `grep -rn "INSERT INTO report_queue"` over
      `src/redkraken/migrations/*.sql` and `src/redkraken/*.py` returns nothing,
      and no function, view or Python module reads it. The only thing in the
      tree that names it as a write target is
      `src/redkraken/roster.py:722-725`, `writes=("report_queue",)`.
- [ ] Contrast the two siblings in the same tool group, which do have
      producers, and let the contrast decide the shape: `validation_queue` is
      filled by `rk finding validate` (`src/redkraken/cli.py:1278`) and
      `pending_decisions` by `park_authorized_tool_run` and
      `rk2_ask_about_impact`. `report_queue` has neither, so a handler for
      `request_report` would be the first writer of a table nothing drains.
- [ ] `request_validation` is the one of the three unserved Contracts with a
      written reason:
      `docs/specs/production-harness-v2/issues/37-validate-finding-blindly.md:94-97`
      says the verb exists, the CLI calls it, and "the tool it makes that step
      through belongs to the orchestrator dispatch ticket". That ticket is 102.
      This ticket does not re-argue 37; it records whether 102's answer serves
      this Contract or retires it.
- [ ] Whichever way each goes, the roster stops carrying an undecided one. A
      Contract that will not be served is deleted from `CONTRACTS` or moved into
      the explicit `name -> reason` register ticket 130 introduces, in the shape
      `roster.FORBIDDEN_BUILTINS` (`roster.py:902-931`) already proves works:
      every built-in a role does not hold states why, and the compile refuses an
      unclassified one.
- [ ] The two decisions are allowed to differ, and the ticket says so. A report
      is a projection of what holds and the last step of one is reserved for a
      human (`cli.py:1331-1332`, "`validated -> reported` is reserved for a
      human actor"), which is an argument for retiring `request_report`
      outright. A validation request is a hand-off between two runtime roles,
      which is an argument for serving `request_validation`.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1 calls `report_queue`
"the cleanest instance of the defect on this axis: a declared queue with no
producer, no consumer and a contract pointing at it", and its gate G9 names it
as "the one place where the Python layer and the schema layer each declare half
of a feature and neither implements it".

`docs/research/wiring/21-agent-surface-wiring.md` section 1.3 reaches the same
two Contracts from the tool side and grades the group "deliberate but
unfinished": `src/redkraken/agent.py:143-146` states a plan, not a decision not
to build, and a plan that has been a comment since the group was compiled is
what this ticket is for.
