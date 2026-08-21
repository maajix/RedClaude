# 111 — Close the open-text columns nine surface facts are computed from

**What to build:** A CHECK on `parameters.value_class`, a decision about
`technologies.name`, and the vocabulary for both served to the party that writes
them.

**Blocked by:** 110 — Serve the vocabulary out of the tables that declare it.

**Status:** ready-for-agent

- [ ] `parameters.value_class` is closed at the column. It is declared `text`
      with no constraint at `0003_entities.sql:83`; `pg_constraint` on
      `parameters` lists only `entity_type`, `location`, keys and FKs. Nine
      `subject_facts` branches test it against nine literal spellings --
      `uuid`, `integer_id`, `opaque_id`, `url`, `file`, `email`, `number`,
      `path`, `serialized` -- and those spellings exist only inside the body of
      the view (`0032_playbooks.sql:115-125` and the later replacements). A
      model writing `"value_class": "integer"` produces a valid row that matches
      no branch, and nothing anywhere refuses it or reports it.
- [ ] The writer is named so the constraint is not a surprise to it.
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
- [ ] Fifteen Playbooks are selectable only if that free-typed string lands on
      one of the nine: `object-ownership`, `external-resources`,
      `ssrf-url-routing`, `webhooks`, `file-resolution`, `file-upload`,
      `exceptional-conditions`, `payment-workflows`,
      `command-directory-injection`, `authentication`, `deserialization`,
      `browser-script`, `ssti`, `spreadsheet-injection`, `agentic-ai`.
- [ ] `technologies.name` is decided in the same ticket and may be decided
      differently. Seventeen `tech_*` facts are computed by matching
      `lower(technologies.name)` against a sixty-eight-row inline `VALUES` list
      (`20260903T000000Z__five_platform_and_supply_chain_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:136-200`),
      the column has no constraint, and the writer is the same
      `v_element ->> 'name'`. `nginx` matches; `nginx/1.24.0`, `NGINX` and
      `Nginx (Ubuntu)` do not. Eighteen Playbooks trigger on a `tech_*` fact. A
      closed CHECK on a technology name is the wrong answer and the ticket says
      what the right one is: normalisation at the writer, a reported
      near-miss, or a declared open set.
- [ ] `parameters.reflected` is named and excluded. It is the same shape one
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
