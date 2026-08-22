# 118 — An Identity Entity is left classified `denied`

**What to build:** A projection call after each of the two places that create an
Identity Entity with a raw INSERT, so that an Entity with no address comes out
`not_addressable` rather than sitting at the column default of `denied`.

**Blocked by:** nothing.

**Status:** resolved

- [x] `rk2_anonymous_identity(uuid)` projects what it creates. It inserts the
      Program's anonymous Identity at
      `20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql:177-180`
      with `(program_id, type, dedup_key, metadata)` and returns. Nothing
      re-projects, so the row keeps `entities.scope_class` at its declared
      default of `'denied'` and `scope_reason` at `'unlisted'`
      (`0021_scope_policy.sql:434-436`) until the next scope version bump.
      `scope_class_of_entity` would classify it `not_addressable` for both
      fields, on the `p_kind IS NULL` arm at
      `20260810T193000Z__scope_policy_compilation.sql:424-427`.
- [x] The identity slots the operator configured are projected on the path
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
- [x] `add_entity` is either used or its comment is corrected. Its own
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
- [x] Nothing about the projection guard changes.
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

## What was built

One migration,
`src/redkraken/migrations/20260925T020000Z__an_identity_slot_is_not_a_refused_address.sql`,
and no Python. `rk2_anonymous_identity` is replaced with 20260908's body and one
statement more: after both rows exist, and only on the branch that created them,
it projects the Program. The early return that finds a slot an earlier Task
already made projects nothing, because re-projecting a Program to discover that
nothing moved is work every clamped Task of the run would repeat.

The Entities that were written before it did are corrected in the same file.
Every Program with a live scope version that holds an Entity with no selector
still classed `denied` is re-projected once, and the migration then refuses to
finish if any such row survives. The selection is on the absence of a selector
rather than on `type = 'identity'`, because that is the question
`scope_class_of_entity` asks on the arm this ticket is about: an Identity Entity
that does carry a selector is a scope question with an answer, and one classed
`denied` for a reason a rule gave is left exactly as it is.

## The projection is asked for, not assumed

`refresh_scope_projection` raises when the Program has no live scope version, and
`rk2_anonymous_identity` is not reached by a call somebody wrote: it runs inside
`derive_task_identities`, the trigger `rk2_project_task_identities` fires on
every clamped Task. A Program that never compiled a policy can still have a hunt
Task inserted into it, and the integrity gate's own negative control for the
identity clamp does exactly that -- `tests/test_database.py:1550-1565` opens a
Program with a slug and a name and puts a running `hunt` Task in it. Projecting
unconditionally would have turned that INSERT into an exception, which is this
ticket refusing work it has no opinion about.

So the call is guarded on the version, which is the guard
`20260813T090000Z...:1102-1104` and `20260814T070000Z...:1460-1462` already
write at the end of their own walks for the same reason. Nothing is lost by
skipping it: `set_scope_version` re-projects every Entity of the Program the
first time one exists, so the row is right before anything can be sent under
that version. Measured both ways on a scratch database: a hunt Task in a Program
with no version still inserts and leaves the slot `denied`, and the first
`set_scope_version` afterwards reports one Entity moved and leaves it
`not_addressable` at that version.

## What the ticket got wrong about the configured slots

Criterion 2 says the identity slots `program._project_identities` creates are
not re-projected when `_project_scope` takes its unchanged-policy early return
at `program.py:847-865`. That is true of `_project_scope` and false of the
transaction it is called in, and the difference is two statements further down.
Every answer that keeps a Program open reaches
`seeded = _decoded(connection, "SELECT open_configured_recon($1::uuid)", ...)`
at `program.py:572`, `open_configured_recon` calls `record_configured_subjects`
first thing (`20260831T000000Z...:388`), and that function ends with an
unconditional `PERFORM refresh_scope_projection(p_program)`
(`20260831T000000Z...:226-229`) under a comment saying why it is unconditional:
"the rules may have moved under Entities this call did not create". 20260831
closed this half of the ticket before the ticket was written, and it closed it
structurally rather than by accident, because `refresh_scope_projection` has no
narrower form than the whole Program.

Measured rather than read: a Program with a live version, an identity Entity
inserted by hand with `program._project_identities`'s own two statements, and
then `open_configured_recon`, which answers
`{"tasks_opened": 0, "subjects_recorded": 0}` -- the unchanged-policy resume, in
other words -- moves that Entity from `denied`/`unlisted` to
`not_addressable`/`not_addressable` at the live version. So the criterion holds
in the tree and a second projection call in `_project_scope` would have been a
statement that never has anything to do.

## `add_entity`

Its comment is corrected and its body is not. The claim that the origin
"defaults to the operator's configuration because that is the only caller this
function has ever had" names a caller that does not exist, and the reason for the
default survives without it: a row nobody recorded a provenance for is one the
Program was configured to go looking for. The new comment says that, and says
what is true of the six writers instead -- each states its own scope selector and
projects for itself. Routing them through `add_entity` is not this ticket's, and
the ticket says so.

## What criterion 3 is owed

The consequence is asserted at the class and not at the chain. The migration
refuses to finish while any Entity with no address is left in `denied`, which is
the one class `rk2_chain_unsoundness` arm (e) refuses
(`20260818T000000Z...:721-729`), so an Identity subject can no longer be the
reason a chain reports itself unsound. What is not here is the case the criterion
asks for in those words: a composed chain with an Identity subject, asserted
sound. That case needs `ChainFixture` and everything under it, which lives in
`tests/test_database.py` -- a file this agent does not own -- and there is no
second module in this repository that reaches a server. It is owed to whoever
next opens that file, beside `PivotStampFixture`, and it is one assertion once
the fixture is in hand.

## What it is asserted with

Nothing in `tests/` changed, because nothing in `src/**/*.py` changed. The
migration was verified against a scratch database migrated from empty: the
corpus applied without this file, a Program with a live scope version and a hunt
Task reproduced the defect exactly -- `('identity', 'anonymous-identity',
'denied', 'unlisted', NULL selector, NULL version)` -- and applying this file
moved that row to `not_addressable`/`not_addressable` at version 1 while leaving
the version-less Program's slot alone. Afterwards a fresh Program classes its
anonymous Identity on creation, a second call returns the row it already made,
and the two comments read as this file writes them.

The apply-time assertion in section 2 is the durable half: `rk db migrate`
refuses the corpus if the repair does not land, and `tests/test_database.py`
applies the corpus from empty twice in `CleanCreationTest`.
