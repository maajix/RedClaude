# 118 — An Identity Entity is left classified `denied`

**What to build:** A projection call after each of the two places that create an
Identity Entity with a raw INSERT, so that an Entity with no address comes out
`not_addressable` rather than sitting at the column default of `denied`.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `rk2_anonymous_identity(uuid)` projects what it creates. It inserts the
      Program's anonymous Identity at
      `20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql:177-180`
      with `(program_id, type, dedup_key, metadata)` and returns. Nothing
      re-projects, so the row keeps `entities.scope_class` at its declared
      default of `'denied'` and `scope_reason` at `'unlisted'`
      (`0021_scope_policy.sql:434-436`) until the next scope version bump.
      `scope_class_of_entity` would classify it `not_addressable` for both
      fields, on the `p_kind IS NULL` arm at
      `20260810T193000Z__scope_policy_compilation.sql:424-427`.
- [ ] The identity slots the operator configured are projected on the path
      where they are not today. `src/redkraken/program.py:1037-1047` inserts
      them with the same four columns, and in the ordinary case the
      `set_scope_version` call at `:940-943` reprojects the whole Program in
      the same transaction and the class is correct by the time the
      transaction commits. It is not reprojected when `_project_scope`
      takes its unchanged-policy early return at `:847-865`, which is reachable
      for a Program whose configuration is byte-identical and whose identity
      rows are missing.
- [ ] The consequence is asserted, not just the column. `chain_soundness` reads
      exactly this column at
      `20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:721-729` --
      `WHERE cs.chain_id = p_chain AND e.scope_class = 'denied'` -- and returns
      "the subject of step X is no longer in scope". Its own prose at `:713-720`
      explains why it reads `denied` and not `NOT in_scope`: 021 "has a fourth
      class for an entity that has no address at all -- an identity slot, a
      technology fingerprint", and reading the boolean "would make every chain
      composed on one permanently unsound for a reason that is not about scope
      at all". An unprojected Identity Entity defeats that reasoning, because it
      is sitting in the class the check does refuse. A test composes a chain
      with an Identity subject and asserts the chain is sound.
- [ ] `add_entity` is either used or its comment is corrected. Its own
      `COMMENT ON FUNCTION`
      (`20260813T090000Z__a_recon_run_becomes_typed_surface.sql:131-134`) says
      the origin "defaults to the operator's configuration because that is the
      only caller this function has ever had". It has no caller in `src/` at
      all: `grep -rn "add_entity" src/redkraken/*.py` returns nothing. Six
      other statements insert into `entities` directly
      (`20260813T090000Z...:1008`, `20260814T070000Z...:1366`,
      `20260831T000000Z...:206`, `20260905T000000Z...:636`,
      `20260908T010000Z...:177`, `src/redkraken/program.py:1039`), and four of
      the six set the scope selector columns themselves and are followed by a
      projection. This ticket does not require them to be routed through
      `add_entity`; it requires the comment to stop claiming a caller that does
      not exist.
- [ ] Nothing about the projection guard changes.
      `refresh_scope_projection` refuses outside a runtime session
      (`0021_scope_policy.sql:514-518`), and both callers this ticket adds are
      already in one: `rk2_anonymous_identity` is granted to `rk2_runtime` and
      runs under a clamped Task, and `program.py` sets the actor at `:504`.

## Why

`docs/research/wiring/23-database-wiring.md` lists `add_entity` twice as
"bypassed by raw INSERT at `program.py:1039`" (`:671`, `:761`) without saying
what the bypass costs. Checked in the tree, the cost is not the one the phrasing
suggests: the label is minted anyway by the `entities_assign_label` trigger
(`0015_epistemic_corrections.sql:108`), so there is no unique-key collision on
`entities.label`, and the configuration path does reproject in the same
transaction on every answer except the unchanged-policy return. The live
instance of the defect is the other writer the report does not connect to it,
`rk2_anonymous_identity`, which creates an Entity mid-run and never projects at
all.

Two classes, `denied` and `not_addressable`, exist precisely so that "the
operator refused this address" and "this is not an address" are different
answers. Every Entity that is the second and reads as the first is a hole in
that distinction, and `chain_soundness` is where it becomes visible: a kill
chain whose pivot ran as the anonymous Identity reports itself unsound.
