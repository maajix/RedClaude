# 132 — Three migrations sort before one already applied

**What to build:** An ordering repair for the tail of the migration corpus, so
that a database migrated at an intermediate commit can be brought forward
instead of being told to start again.

**Blocked by:** every ticket that still holds a reserved migration timestamp.
This is a rename of recorded files, so it must be the last thing that touches
the corpus tail, not the first.

**Status:** needs-triage

- [ ] The rule is stated where the repair is made. `migrate.plan`
      (`src/redkraken/migrate.py:768-777`) refuses a pending migration that
      sorts below the highest applied one: *"is pending but sorts before the
      applied %s; recreate the database and migrate from empty"*, code
      `SCHEMA_DRIFT`. It is a whole-corpus refusal, not a per-file one, so one
      late-sorting file stops every later file with it.
- [ ] The three files are named and moved.
      `20260930T000000Z__the_desync_playbook_is_refrozen_at_the_text_it_ships.sql`
      landed first. `20260929T000000Z__the_eval_store_leaves_with_the_model_it_was_missing.sql`,
      `20260929T020000Z__an_identity_class_is_declared_and_service_is_not_one.sql`
      and `20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql` all
      landed after it and all sort below it. A fourth,
      `20260927T000000Z__a_probe_only_claim_becomes_a_finding.sql`, is a draft
      for ticket 116 and is not committed; whoever finishes 116 should give it a
      timestamp above the tail rather than the one it has.
- [ ] The reason this was not caught is written down. Every gate and every test
      builds from empty -- `CleanCreationTest` drops and recreates -- and from
      empty the corpus applies in sort order and the rule never fires. The only
      thing that sees it is a database that was migrated once and is migrated
      again, which is an operator's database and nobody's test.
- [ ] The renaming is safe and the ticket says why. A migration's identity is
      its filename, so a rename is a new identity and a fresh database applies
      it once, in the new place. The bytes inside the files do not change, so
      nothing that has already been reasoned about them stops being true. No
      persistent database in this repository holds the old identities.
- [ ] A check refuses the next one. The reserved-timestamp scheme that produced
      this hands parallel agents a slot each, and nothing compares a slot
      against what has landed since it was handed out. `tools/check_baseline.py`
      or a sibling should fail when a migration file sorts below the highest one
      in the previous commit.

## Why

Found by the standards axis of the code review on `0759b7b`, which read
`migrate.plan` rather than the corpus and reported: *"Any database already at
the base corpus refuses both files."*
