# 111 — Close the open-text columns nine surface facts are computed from

**What to build:** A CHECK on `parameters.value_class`, a decision about
`technologies.name`, and the vocabulary for both served to the party that writes
them.

**Blocked by:** 110 — Serve the vocabulary out of the tables that declare it.

**Status:** resolved

- [x] `parameters.value_class` is closed at the column. It is declared `text`
      with no constraint at `0003_entities.sql:83`; `pg_constraint` on
      `parameters` lists only `entity_type`, `location`, keys and FKs. Nine
      `subject_facts` branches test it against nine literal spellings --
      `uuid`, `integer_id`, `opaque_id`, `url`, `file`, `email`, `number`,
      `path`, `serialized` -- and those spellings exist only inside the body of
      the view (`0032_playbooks.sql:115-125` and the later replacements). A
      model writing `"value_class": "integer"` produces a valid row that matches
      no branch, and nothing anywhere refuses it or reports it.
- [x] The writer is named so the constraint is not a surprise to it.
      `promote_proposal` writes the column as
      `left(nullif(btrim(v_element ->> 'value_class'),''),200)`
      (`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:1410-1418`)
      -- raw model text, truncated, otherwise unexamined -- and it is the only
      producer of typed surface in the harness. Recon does not write surface;
      the model does, and the runtime grounds it.
- [ ] The vocabulary reaches the party that writes it, which is the half a CHECK
      alone does not buy. `value_class` appears in no Python module, no Playbook
      and no Skill in the tree: `grep -rn "value_class" src/ docs/` outside
      `src/redkraken/migrations/` finds only `docs/prototype/` and two
      `docs/specs/` issue files. A closed column whose vocabulary the writer has
      never been told is a refusal a model cannot act on, which is why this
      ticket is blocked on 110.
- [x] Fifteen Playbooks are selectable only if that free-typed string lands on
      one of the nine: `object-ownership`, `external-resources`,
      `ssrf-url-routing`, `webhooks`, `file-resolution`, `file-upload`,
      `exceptional-conditions`, `payment-workflows`,
      `command-directory-injection`, `authentication`, `deserialization`,
      `browser-script`, `ssti`, `spreadsheet-injection`, `agentic-ai`.
- [x] `technologies.name` is decided in the same ticket and may be decided
      differently. Seventeen `tech_*` facts are computed by matching
      `lower(technologies.name)` against a sixty-eight-row inline `VALUES` list
      (`20260903T000000Z__five_platform_and_supply_chain_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:136-200`),
      the column has no constraint, and the writer is the same
      `v_element ->> 'name'`. `nginx` matches; `nginx/1.24.0`, `NGINX` and
      `Nginx (Ubuntu)` do not. Eighteen Playbooks trigger on a `tech_*` fact. A
      closed CHECK on a technology name is the wrong answer and the ticket says
      what the right one is: normalisation at the writer, a reported
      near-miss, or a declared open set.
- [x] `parameters.reflected` is named and excluded. It is the same shape one
      column over and drives four Playbooks, but it is a boolean, so the risk is
      omission rather than drift and there is no spelling to get wrong.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 4b calls
`parameters.value_class` "the larger hole" on its axis, and its gate G6b states
both halves: the vocabulary must be closed at the column and not inside a view
body, and it must be reachable by the party that writes it. Today the first
fails against no data, because the column is empty on a fresh database, and
would immediately start refusing the drift it exists to refuse; the second fails
outright, because `mcp_enum()` has no caller at all.

This is the direction the existing gate does not cover.
`check_playbook_integrity()`'s `fact_not_computed` rule proves that every
registered fact has a branch in `subject_facts`. Nothing proves the branch's
predicate can ever be true.

## What was built

One migration,
`20260926T010000Z__the_value_class_vocabulary_is_closed_at_the_column.sql`.
It closes one column, declares another open on purpose, and re-issues both
columns' comments so that the live schema says which is which.

`parameters_value_class_check` admits `NULL` or one of the nine, and the nine are
the nine the view computes from rather than nine somebody typed again:
`uuid`, `integer_id`, `opaque_id`, `url`, `file`, `email`, `number`, `path`,
`serialized`. NULL is admitted deliberately. The writer leaves the column null
whenever the model classified nothing, and "unclassified" is a different claim
from "classified as something no branch reads": the first computes no fact and
asserts nothing, the second computes no fact while looking like an answer.

The writer needed no change, which is the finding that made this affordable.
`promote_proposal` walks a proposal element by element inside a block whose
`EXCEPTION` arm already catches `check_violation` and files a `proposal_drops`
row with reason `refused_by_invariant` and the server's own message. So a model
that misspells a value class loses that one element and is told so in the drop,
while the endpoint, the parameters beside it and every other element of the same
proposal are promoted exactly as before. The constraint costs a line in the
answer rather than a failed submission.

Section 1 of the file is a pre-flight refusal rather than a repair. A row already
carrying a spelling outside the nine cannot be fixed from a migration: the value
is a claim a model made about a parameter, clearing it would rewrite a recorded
observation and move the surface fingerprint that hashes it, and guessing which
of the nine was meant is the model's job. So the file counts those rows, names
the distinct spellings and tells the operator what to do, instead of leaving
PostgreSQL to refuse the `ALTER` with a message about one row and no instruction.

## The `technologies.name` half, which was a decision rather than a constraint

**A declared open set**, which is the third of the three answers the criterion
allowed, and no CHECK.

The reason is that the sixty-nine-row list in `subject_facts` is a set of
readings this corpus happens to have Playbooks for, not a classification of
anything. The set of technologies in the world is open, so a CHECK there would
refuse a true observation of a component nobody listed, and losing the row is a
worse answer than recording it and computing no fact from it. `value_class` is
the opposite case: a closed classification with exactly one reader, where a tenth
spelling is never a discovery.

What the open set costs is now written on the column instead of waiting to be
rediscovered: the reading lowercases, so `NGINX` matches `nginx`, and a name that
arrives carrying its version or its packager -- `nginx/1.24.0`,
`Nginx (Ubuntu)` -- matches nothing and computes no fact for the eighteen
Playbooks that trigger on one. `technologies.version` is the column the writer
already fills from its own field, which is where the rest of that string belongs.

## What the migration's own `DO` block asserts, and what is owed

The closing block asserts the property, not the act. Both sides of it are read
back out of the catalogue -- `pg_get_constraintdef` for the column and
`pg_get_viewdef` for the view -- so neither can be satisfied by restating a list
in the migration:

* the set the column admits and the set `subject_facts` computes `value_class`
  facts from are the same set, so a spelling on one side and not the other fails
  the migration in either direction;
* the live constraint expression, evaluated with each of those spellings
  substituted for the column, holds for every one of them;
* it does not hold for `integer`, `uuid_v4` or `UUID` -- the ticket's own
  example, a near miss, and the right word in the wrong case;
* and it does hold for `NULL`, which is the writer's ordinary case and would
  otherwise be refused by a constraint that looked correct.

Section 1's refusal is asserted the same way it fires: with the constraint
dropped and one `integer` row present, it raises `23514: 1 parameter(s) carry a
value_class outside the nine: 'integer'`.

Nothing in `tests/test_database.py` asserts any of this. No case was added there.
What is owed to that file is the part a migration cannot ask: that a real
`promote_proposal` call carrying `"value_class": "integer"` drops one element as
`refused_by_invariant`, promotes the rest of the proposal, and leaves the
Endpoint above it intact; that an in-scope parameter written with one of the nine
produces the `subject_facts` row the Playbook trigger reads; and that the corpus
applied twice still ends with one constraint of this name and no other.

## What this ticket does not close

The third criterion, and it is left unticked on purpose. `value_class` still
reaches the party that writes it nowhere: `submit_mission_result` declares its
element lists as free text, `mcp_enum` has no caller at all, and no Playbook or
Skill spells out the nine. Until ticket 110 lands, the constraint teaches the
vocabulary by refusing rather than by telling, which is the weaker half of the
pair 018 describes. What ships here is the half that holds whatever the tool
schema ends up saying -- against a fixture, a repair script or a future tool that
forgot -- and it is also what gives 110 a single source to serve: the closed set
is now on the column, so serving it is reading it rather than writing a third
copy of nine strings.

## What the ticket got wrong

**Eleven Playbooks depend on the nine spellings, not fifteen.** The fifteen in
the criterion is the count for the parameter block as a whole:
`SELECT count(DISTINCT p.path) FROM playbooks p JOIN playbook_triggers pt
ON pt.playbook_id = p.id WHERE pt.fact IN (the eight value_class facts)` answers
11, and adding `reflected_parameter` answers 15. The four it adds --
`agentic-ai`, `browser-script`, `ssti`, `spreadsheet-injection` -- trigger on
`parameters.reflected`, which the ticket's own last criterion names and excludes
because a boolean has no spelling to get wrong.

**The technology list is sixty-nine rows computing nineteen `tech_*` facts**, not
sixty-eight computing seventeen. Counted twice: over the `VALUES` block in
`20260904T000000Z`, which is the live definition of the view, and over
`surface_facts`, which registers exactly nineteen ids matching `tech\_%`.

**`NGINX` already matches.** The join is
`ON known.name = lower(t.name)` (`20260903T000000Z...:201`), so case is the one
kind of drift that half of this pair already handles. `nginx/1.24.0` and
`Nginx (Ubuntu)` are the real misses, and the column comment now says so.
