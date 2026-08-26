# 188 — A grant nobody stages

**What to build:** a standing check that `role_skills` and the roster's own
grants say the same thing, and a mission objective whose first sentence is the
Task kind's rather than every kind's.

**Blocked by:** nothing.

**Status:** open

## What was measured

Database `rk2here`, 2026-08-25. Seventeen `recon` agent runs closed
`completed`. `agent_runs.tools_called` on every one of them is exactly
`http_request, submit_mission_result`: one request, then submit. Eleven of the
answers were 3xx and not one `Location` was followed. The Program's whole
recorded surface after 23 recon Tasks over 108 configured applications was 16
Endpoints.

Two causes, found by asking why the Skill that describes a surface walk was
never opened.

## Cause 1: the roster and the table disagreed, and nothing asked

`roster.ROLES['recon'].skills` answered `('handle-untrusted-content',)`.
`Role.skills` is derived from the `bb:roles` line of each compiled Skill, and
`enumerate-surface` named `web_hunter` alone. `agent.stage_skills` writes that
tuple into the child's launch directory and `_launch` passes it as the SDK's
`skills`, so the instructions for the one Task kind they describe were never
staged for the role that runs it. The child could not have loaded the Skill; it
was not offered one.

Meanwhile `role_skills` has held `('recon', 'enumerate-surface')` since
`20260822T000000Z`. The table records the grant, the roster stages the file, and
nothing compares them. `check_skill_registry` has an arm for a Skill no role may
load and none for a role that may load a Skill nobody stages, which is the same
failure read from the other side.

Fixed for this instance in `20261116T000000Z`, by the Skill naming `recon`.
The check is what this ticket is for: one corrected row is not a rule, and the
next Skill will be granted in the table and staged nowhere in exactly the same
way.

### Measured again, 2026-08-26, and both halves of that paragraph are wrong

There is a check. `tests/test_database.py::test_the_registry_holds_every_grant_dependency_and_runtime_tool`
compares `role_skills` against `roster.ROLES[...].skills` exactly. It has never
run in this campaign: the module skips itself without `RK_TEST_SUPERUSER_URL`,
which is 179 of the suite's skips, so every "2629 tests, OK" this ticket was
written under said nothing about the registry at all.

Pointed at a real server it fails:

```
- ('recon', 'enumerate-surface'),
   ('recon', 'handle-untrusted-content'),
   ('web_hunter', 'browser-evidence'),
```

Nine pairs in the roster, eight rows in the table. The drift is the opposite
way round from the one above: the roster stages the Skill for `recon` and the
table does not grant it.

And the row is not "correct and inert since 20260822". `20261108T000000Z:72`
is

```sql
DELETE FROM role_skills WHERE role = 'recon' AND skill_name = 'enumerate-surface';
```

with a guard in the same file asserting exactly one role holds the Skill.
`20261116T000000Z` then moved the roster back to two roles and refroze the
digests without touching `role_skills`, on a comment that says the row was
still there. Nothing re-inserts it anywhere in the corpus.

So this ticket now has three parts, not one:

- [x] **The comparison, out of a module nobody runs.** W11 in
      `tools/check_wiring.py`: `skill_grant_gaps` reads `bb:roles` from each
      `SKILL.md` and `role_skills` from the migration corpus, and reports either
      direction of disagreement. A file reader rather than a database check,
      because the frontmatter is not in the database and never will be, so
      `check_skill_registry` cannot ask this at all. It runs in a gate that
      already runs, on every checkout, with no server and no environment
      variable.

      Reading the grants means applying the corpus in order rather than as a
      set: `20261108T000000Z` deletes one row and inserts another in the same
      file. `Catalogue.role_skills` does that, and
      `test_a_withdrawn_grant_is_not_a_grant` pins it.

      It found the drift on the first run:

      ```
      wiring failed: unregistered: enumerate-surface names recon in bb:roles
      and role_skills does not grant it, so a recon Task requiring it is
      refused as unclaimable
      ```

- [x] **What the missing row costs, measured before fixing it.**
      `skills_ungranted_for` asks `role_skills`, and `claimable_for` refuses on
      it. In `rk2here` no Task sets `required_skills` at all --
      `hunt 338 | perform 2 | recon 324`, every one of them empty -- and the one
      Playbook naming the Skill is `attack-surface`, which is `web_hunter`'s,
      and `web_hunter` holds the grant. So the absence has cost nothing yet.
      The first recon Task that requires it leaves the queue as unclaimable,
      and the refusal names the Skill rather than the grant.

- [x] **Re-granted.** `20261126T000000Z`. `role_skills` holds nine rows and the
      roster publishes nine pairs, and W11 reports nothing:

      ```
      W11 skill grants             0 owed   grants 9  staged 9
      ```

      `20261108T000000Z`'s one-role guard is left alone -- an applied migration
      is immutable here, `migrate.py` calls a changed file schema drift, and the
      guard was a one-time assertion rather than a standing rule. W11 is what
      replaces it, and the register row that admitted the gap is removed rather
      than re-pointed.
- [ ] The `MISSIONS` question above, still unread for `perform`, `analyze` and
      `validate`.

## Cause 2: one sentence, written for a different kind

`Claimed.objective` built the same opening for every kind:

> Send that one request with mcp__rk2__http_request and read the answer.

For a `hunt` against a single claim that is right. For `recon` it is the
instruction not to map anything, and it is what the runs did. Ticket 156's
`_conclusion` is the precedent -- a kind whose work is not "send the request"
gets a paragraph of its own -- and `recon` now takes an opening of its own that
names its Skill instead of a request count.

The remaining question is the general one: `MISSIONS` gives each kind a
sentence and then the paragraph after it assumes one exchange. `perform`,
`analyze` and `validate` have not been read against that assumption.

## Why the Skill was named in the prompt

A Skill is offered, not loaded. The measurement here is that an offered Skill
with an accurate description went unopened seventeen times out of seventeen, so
the objective names it. That is a statement about this Task kind rather than a
policy: recon has one Skill and it is the Task.
