# 129 — The agent may read twenty-one relations no tool reads

**What to build:** For each relation on the agent's read surface that no tool
reaches, either the read that reaches it or the recorded decision that it stays
unreachable -- and then the grant follows the decision.

**Blocked by:** 107 — A label minted after launch must be resolvable in the run that minted it.

**Status:** needs-triage

- [ ] Every relation is placed in one of three buckets, in writing. The surface
      holds twenty-eight live relations after
      `20260922T000000Z__the_agent_connection_cannot_read_the_playbook_catalogue.sql:34-36`
      removed `playbooks` and `playbook_selections`; seven are named by a
      Contract's `reads=` tuple (`artifact_references`, `entities`, `findings`,
      `hypotheses`, `v_artifacts`, `v_evidence`, `v_records`); twenty-one are
      reached by no tool. The three buckets are: gets a read, keeps the grant
      with a stated reason, loses the grant.
- [ ] `negative_knowledge` and `negative_knowledge_retests`
      (`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1128`, `:1134`)
      are decided first, because they are the highest-value pair on the list:
      what has already been refuted, and when a refutation is due to be retried.
      An entire migration exists to keep refutations and make them due, both
      tables are on the surface, and no tool reads either. Ticket 114 owns the
      writer and the operator-side reader; this ticket owns the model's.
- [ ] `relationships` (`20260813T090000Z...:408`) is decided against a
      contradiction the audit found rather than in the abstract:
      `mcp__rk2__submit_mission_result` accepts a `relationships` element list
      (`src/redkraken/roster.py:686`), and `get_attack_surface` declares
      `reads=("v_records", "entities", "domains", ..., "identities")`
      (`roster.py:604-605`) without it. The model may propose graph edges it can
      never read back.
- [ ] The browser and tool-run evidence tables are decided as one group:
      `browser_runs`, `browser_steps`, `browser_step_results`
      (`20260814T040000Z...:519`, `:523`, `:527`), `tool_runs`
      (`20260814T030000Z...:429`), `tool_run_artifacts` (`:422`),
      `tool_run_inputs` (`20260814T050000Z...:243`), `tool_run_paths` (`:364`)
      and `test_run_receipts` (`20260815T000000Z...:2018`). These are what the
      model's own earlier work produced, and the reason they are unreadable
      today is ticket 107's: the packet is a pre-launch snapshot, so a row minted
      during the run has nowhere to be read from. That is why this ticket is
      blocked by 107 rather than beside it.
- [ ] The remainder is decided one by one and not in a batch: `entity_provenance`
      (`20260813T090000Z...:407`), `surface_facts` (`0032_playbooks.sql:700`),
      `events` (`20260810T094500Z...:366`), `report_templates`,
      `report_blocks` and `report_effects` (`20260820T000000Z...:939`, `:938`,
      `0034_reports.sql:1089`), `redaction_rules`
      (`20260821T000000Z...:595`), `program_required_headers`
      (`20260810T193000Z...:175`). Two are not defects and the ticket says so:
      `artifact_refs` (`20260810T151500Z...:211`) is reached indirectly through
      `v_artifacts`, and `rk2_state` (`0030_corpus_corrections.sql:263`) is a
      bookkeeping row.
- [ ] Where the answer is a read, the mechanism is the one that already exists
      rather than a new one: a `state.read` Contract, a section in
      `packet.SECTIONS` (`src/redkraken/packet.py:43`) and a `_records`-style
      compile step. Where the answer is no read, the grant comes off, because a
      grant is a claim that somebody reads it.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 2.4. The read surface
is a declaration of what the model is allowed to know, and three quarters of it
is unreachable by any tool the model can call. Some of that is deliberate -- the
playbook catalogue removal has its own migration and its own reasoning -- and
the rest is undeclared, which the repo's own standard (`roster.py:800-805`)
counts as accidental.

Two neighbouring absences are recorded here rather than opened as their own
tickets, because both are plausibly operator-only and neither is stated as a
decision anywhere: the evidence bundle (`evidence.export` and `evidence.verify`,
reached only from `cli.py`) and the replay lane (`replay.run`, reached from
`cli.py` and `validation.py`). `redaction_rules` and `test_run_receipts` are
their read-surface halves, so whatever this ticket decides about those two
relations decides those two questions with them.
