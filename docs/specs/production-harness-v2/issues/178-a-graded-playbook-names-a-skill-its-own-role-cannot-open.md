# 178 — A graded Playbook names a Skill its own role cannot open

**What to build:** `enumerate-surface` moves from `recon` to `web_hunter`, and
`web_hunter` gains the one registered tool that Skill drives. `attack-surface`
is the only Playbook naming it, its triggers only match after recon has run,
and its Skill was held by recon alone -- so no role could ever select it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **Measured.** Canary attempt four, `attack-surface` against
      `artifact-exposure-pair`, database `rk2grade4` on 2026-08-24. Three
      repeats filed, no violations -- tickets 176 and 177 held -- and nothing
      measured:

          playbook_test_runs    3 rows (repeat 0, 1, 2), claims 0, discriminating_tp 0
          hypotheses            transport.header_policy only, never the declared class
          verdict               untested

- [x] **Unreachable from both ends, and the row counts say which.** Every
      `playbook_selections` row in the database, grouped by the kind of Task
      that asked:

          hunt      playbooks/attack-surface/playbook.md  role_lacks_skill  2
          conclude  playbooks/attack-surface/playbook.md  role_lacks_skill  1

      and the Tasks that ran:

          recon 12 done   perform 4 done   hunt 4 done   conclude 1 abandoned

      Twelve recon Tasks completed and not one produced a selection row at all.
      `bb:triggers_all` on this Playbook is `read_method` and
      `unauthenticated_endpoint`, which are facts recon *records* rather than
      facts it is *given*, so at recon time they match nothing and the Playbook
      is not a candidate. By the time they match, the Task is a hunt Task, and
      `playbook_candidates` (migration `20260918T000000Z`) drops the Playbook
      because the asking role does not hold its Skills.
- [x] **The child had the evidence and not the text.** Receipts from the same
      three repeats:

          vulnerable  /static/app.js.map            200 x5
          vulnerable  /static/app.js                200 x1
          secure      /static/app.js.map            404 x5
          secure      /zzz-nonexistent-control-path 404 x1

      The source map is exactly what `attack-surface` exists to claim on, it
      was served on one half and absent on the other, and the Playbook that
      would have named the claim was never handed over.
- [x] **Which end was wrong.** The Playbook's own text is hunt work throughout:
      step 1 requests a control path, step 3 sends one request per candidate at
      the application, and step 6 proposes the Hypothesis and says in that same
      step why `enumerate-surface`'s refusal to propose one does not apply here.
      Its triggers are facts about a route that is already known. Nothing in it
      is enumeration of an unmapped root, which is what recon is for and what
      the Skill's own step 4 stops at.
- [x] **Moved, not added.**
      `test_every_playbook_names_the_production_roles_that_can_load_it` holds the
      corpus to one role per Playbook, and a grant that let both roles load this
      one is exactly what it exists to catch: "a Playbook that two roles can
      load is a Playbook whose Skill set no longer picks out who does this
      work". `attack-surface` is the only Playbook naming the Skill, so the
      Skill goes with it. `recon` keeps `handle-untrusted-content` and loads
      what it loaded before, which the row counts above show was nothing.
- [x] **No tool group moves.** `enumerate-surface` declares `exec.tool_run`,
      `net.request`, `state.propose` and `state.read`. `web_hunter` already
      holds all four, and `state.conclude` and `exec.browser_run` besides.
      `roster._check_skills` enforces the subset rule at import, so a grant that
      widened a group would refuse there rather than reach the migration.
- [x] **One registered tool moves, and the Playbook had already said so.**
      `check_skill_registry` refuses a Skill held by a role that may not run the
      tools it drives -- "enumerate-surface may run jq, which web_hunter may
      not" -- so `offline_tool_roles` gains `('jq', 'web_hunter')` in the same
      migration. `attack-surface` step 5 writes its whole identification step on
      top of that grant and states it outright: "this Playbook's role is granted
      `jq` alone". The supported claim needs a `content_match`, `content_match`
      takes tool-run provenance alone, and the tool run the text names is `jq`.
- [x] **What that grant is bounded by.** `jq` reads one stored Artifact this
      Program already holds. It opens no socket, writes no state, and its output
      is an Artifact with a Tool run behind it. `web_hunter` already holds
      `exec.tool_run` and already runs `compare_responses` through it, so no new
      kind of execution appears -- one more filter over bytes the role could
      already read. The roster keeps `js_parse`, `js_routes` and `js_map` to
      `js_analyst` because they turn a bundle into a source conclusion; `jq`
      selects a field out of a document that is already JSON, which is what
      `recon` was trusted with. The migration asserts `web_hunter` ends holding
      exactly two offline tools and that exactly one role holds the Skill, so
      neither half can land without the other.
- [x] **Fixed.** `src/redkraken/skills/enumerate-surface/SKILL.md` names
      `web_hunter`; migration `20261108T000000Z` moves the `role_skills` row,
      inserts the `offline_tool_roles` row, refreezes the Skill's
      `source_sha256`, `version` and instruction digest, and asserts each half.
      `CleanCreationTest`, `ApplicationSubjectFactsTest`,
      `PlaybookCorpusSelectionTest`, `PlaybookSelectionTest`,
      `SkillScriptRegistryTest`, `tests.test_roster`, `tests.test_playbook` and
      `tests.test_skill` green together: 322 tests.

## Why

The three canaries before this one each found the instrument refusing to
measure, and each refusal was quiet in the same way: the run completed, the
ledger was clean, and the number at the end was zero. A Playbook nobody can
select is indistinguishable, in the verdict, from a Playbook that finds nothing
-- which is precisely the thing ticket 84 is trying to tell apart.

## Notes

Three test expectations moved with the corpus, each because it was written
against the state this ticket corrects:

- `test_every_playbook_names_the_production_roles_that_can_load_it`:
  `attack-surface` maps to `web_hunter`. (Ticket 193 later gave the Skill back
  to recon as well, so the entry is now both roles and the test's name says
  roles rather than one role.)
- `test_the_selection_reaches_a_playbook_for_an_application_subject`: the row it
  reaches is kept rather than dropped on `role_lacks_skill`.
- `test_a_skill_combination_no_role_can_load_is_reported` asked for
  `{enumerate-surface, use-identity}`, which `web_hunter` now holds both of. It
  asks for `{analyse-source, use-identity}` instead: `js_analyst` holds the
  first, `web_hunter` the second, and no role holds both.

Two other Playbooks are loadable by one non-hunt role and are **not** touched
here: `playbooks/external-resources/playbook.md` and
`playbooks/supply-chain/playbook.md` both name `analyse-source` and belong to
`js_analyst`. Unlike `attack-surface` they read a served document rather than
sending anything at the application, so js_analyst is plausibly right for them;
ticket 101 owns the other 45 Playbooks and inherits the question.

`role_skills` is seeded per Skill from `bb:roles` on disk and compared back by
`CleanCreationTest`, so the SKILL.md edit and the migration are one change and
have to land together.
