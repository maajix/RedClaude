# 103 — The impact, severity, pivot and chain verbs have no caller either

**What to build:** Callers for the six granted verbs that run from a validated
Finding to a sound kill chain, on whatever dispatch shape ticket 102 settles.

**Blocked by:** 102 — Nothing in this tree has ever created a Finding.

**Status:** needs-triage

- [ ] Each of these six is granted to `rk2_runtime` and has zero callers in
      `src/redkraken/*.py`, verified by grep against the current tree:
      `open_impact_task`
      (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209`,
      granted `:2033`), `state_severity` (`20260816T000000Z...:1725`, granted
      `:2036`), `apply_computed_cvss` (`20260816T000000Z...:1851`, granted
      `:2037`), `issue_pivot_stamp`
      (`20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931`,
      granted `:1121`), `build_kill_chain`
      (`20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538`, granted
      `:924`) and `read_kill_chain` (`20260818T000000Z...:797`, granted `:925`).
      `open_impact_replay` is the one verb of this group that does have a
      caller, at `src/redkraken/replay.py:96`.
- [ ] Ticket 38's factual claim is corrected rather than repeated. It says
      "`open_impact_task`, `open_impact_replay` and `state_severity` are called
      by the CLI and by the tests". Two thirds of that is false: only
      `open_impact_replay` has a Python caller. `open_impact_task` and
      `state_severity` appear in `tests/test_database.py` (three and six times
      respectively) and nowhere else. A dated correction note is appended to
      ticket 38 naming this ticket, and its `**Status:** resolved` is not
      changed.
- [ ] `read_kill_chain` is granted to `rk2_human` and has no caller in `src/`:
      one reference in `tests/test_database.py` and nothing else. `rk report
      chain` (`src/redkraken/cli.py:1517`) is a live verb that reaches
      `read_chain_report`, not this, so the operator's read of a composed chain
      is a verb granted to the operator's role and reachable from no command.
      It is not the only such verb -- fifty-six functions carry a `rk2_human`
      EXECUTE grant and about half have no Python caller -- but most of those
      are predicates a standing check or another function calls from inside SQL,
      and this one is a top-level read with nothing above it.
- [ ] `apply_computed_cvss` is the one member of this group already documented
      as knowingly dead, at
      `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:440-443`:
      "038 dropped `apply_computed_severity` and left `apply_computed_cvss`
      behind it, and nothing in this corpus calls that function." The ticket
      decides between wiring it and dropping it, and does not leave it as the
      third state.
- [ ] `compose_finding_report`
      (`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461`) is
      classified with the same reading and is not silently carried. It is
      owner-only, it has no grant to any role, and `src/redkraken/reporting.py`
      calls `read_finding_report` instead. Either it is superseded and says so
      in a `COMMENT ON`, or it is wired.
- [ ] Tickets 39 and 40 each carry a dated note naming this ticket as the owner
      of the deferral. Their own claims check out -- `issue_pivot_stamp` appears
      once in `tests/test_database.py`, `build_kill_chain` four times and
      `read_kill_chain` once, and neither ticket claimed a CLI caller -- so the
      note corrects the record about the ticket they deferred to and nothing
      else.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 3.2, table B, and
`docs/research/wiring/23-database-wiring.md` section 4.2, which reach the same
twelve verbs from opposite directions: one from the grant, one from the
catalogue. Report 23 puts it as "a designed verb with a full test suite and no
production caller", and notes that every one of the 26 uncalled functions in the
corpus is granted to `rk2_runtime`, the role the harness connects as, and that
eleven of them are additionally published in `runtime_verb_surface`.

Ticket 65's fourth criterion is "A demonstrated pivot is evaluated in a sound
kill chain, while an intentionally missing or invalid pivot remains visibly
unreportable." Nothing in this tree can build the chain that criterion is about.
