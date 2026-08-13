# 22 — Fingerprint Surface and detect change

**What to build:** Compute a deterministic Surface fingerprint after recon and record the exact deltas when the observable application surface changes.

**Blocked by:** 21 — Promote a recon Mission into typed Surface.

**Status:** resolved

- [x] Fingerprint input is a documented canonical projection of relevant Surface rows and excludes timestamps, run identifiers and ordering noise.
- [x] Identical Surface produces the same digest across runs and row insertion order.
- [x] Added, removed or materially changed endpoints, parameters, technologies and identity relationships produce typed deltas and a new digest.
- [x] Recomputing a fingerprint is an explicit runtime operation with an Event and is not a side effect of a read.
- [x] Deltas identify the affected subjects and Property classes without declaring previous negative knowledge invalid by prose.
- [x] Synthetic secure/vulnerable twins prove stable sameness and meaningful difference.

## Comments

Implemented on 2026-08-13. One migration,
`20260813T140000Z__the_surface_gets_a_fingerprint.sql`, one test case,
`SurfaceFingerprintTest`, and four lines in `execution.py` that call the new
verb in the transaction that promotes a recon result.

No new module, for 21's reason: `surface_fingerprints` has existed since 012
with `fingerprint text NOT NULL, -- contents: ticket 29` against it, and 023
already fires a retest trigger when the newest digest differs from the one a
Hypothesis was refuted under. Both halves were waiting for the middle, and the
middle is a projection, a digest over it and a comparison of two of them --
three things the database is the only honest place to compute.

### The contents were charged to 29, and 29 is not that ticket any more

012's comment names ticket 29 as the owner of what a fingerprint holds. 29 is
now the pending-decision and Halt ticket, so nothing was going to arrive from
there. The contents belong to the ticket that computes them, and the comment is
the only thing that ever said otherwise.

### The projection carries no name, no address and no identifier

Criterion 1 asks for timestamps, run identifiers and ordering noise to be
excluded. Criterion 6 asks for two twins to compare equal. The second is the
harder constraint and it decides three more exclusions.

`base_url` is out, because an Application's address is its identity rather than
its surface and a fingerprint is compared against itself over time. Entity
labels are out, because `EP7` and `EP41` are two counters, not two routes.
`identities.slot_name` is out because `identities_slot_idx` is unique per
Program since 017 -- two Applications of one Program cannot share a slot, so a
projection carrying it could never let two of them agree. What is surface-relevant about an Identity is its class, which
is also what 007's `new_identity_class` retest trigger is named for.

So the four sections are the routes, their inputs, the stack and which class of
Identity holds what. `rk2_surface_reach` writes the keys once and the
projection and the subject lookup both read it, because "a route is its method
and its path template" said twice is the place the two would stop agreeing.

### Two things are keyed by their own name and carry a list

A Technology is keyed by name with its versions beside it, and an Identity
relationship is keyed by the holder's class and the kind of hold with its
targets beside it. Both started as one element per pair, and both were wrong
for the same reason: an upgrade came out as a removal and an addition that a
reader had to pair back up, and `identity_relationship_changed` was a delta
kind nothing in the schema could ever produce, because every field of the
element was inside the key.

A vocabulary with an unreachable value is a value nobody ever has to be right
about. The test asserts all twelve are reachable, and the fixture produces all
twelve in one recompute.

### The deltas name a subject, and removals name no class

`surface_deltas` carries `subject_entity_id` where exactly one row answers to
the key, and null where none does or where two do -- a removed route no longer
has a row, and one Identity class held by two Identities is a subject the key
does not pick out. Every branch of `rk2_surface_subject` is `INTO STRICT`, so
"two rows answer to this key" is caught rather than resolved by picking one.
`subject_key` is NOT NULL either way, so every delta says what changed even when
it cannot say which row.

`surface_delta_property_classes` is criterion 5's other half as rows rather
than prose: twenty-two statements of what a section puts back in question, each
one applied to that section's `_added` and `_changed` kinds alike. Removals map
to nothing, deliberately. A route that is
gone tests nothing, and a refutation about it is not made due by its subject
disappearing -- the row is still there, with its key, for whatever later
decides otherwise.

Nothing here touches a Hypothesis. The test writes one refuted Hypothesis with
its `observed_fingerprint`, recomputes over a surface that changed underneath
it, and asserts the row is untouched -- and then asserts the join that makes it
retestable exists: this subject, this class, one delta naming both. That join
is ticket 34's; this ticket's job was to make it possible without a sentence
telling somebody what "relevant" meant.

### The operation always writes a row, including when nothing moved

`compute_surface_fingerprint` is the only writer of `surface_fingerprints` --
the test asserts that against `pg_proc`, and asserts the table carries no
trigger. It writes a row on every call, because "we looked and it was the same"
is a fact, and a function that only recorded changes could not tell an
unchanged surface from one nobody had looked at since.

The first fingerprint of an Application produces no deltas. There is nothing to
have changed from, and N `added` rows against an empty predecessor would put
the whole of a first recon into a table whose rows mean "this moved".

The Event is an occurrence event, not a row event: 030 already classified
`surface_fingerprints` as `derived`, and one act that produces one fingerprint
and thirteen deltas is one thing that happened, not fourteen. That is what
`scheduler.ranked` has been doing since 013, and CONTEXT.md's Event entry said
an occurrence event has "no row at all" -- true of a refusal, not of either of
these. The entry now says what the corpus does: the distinction is what the
Event mirrors, not whether a row exists.

`fingerprint_program_surface` is what makes "after recon" a fact rather than an
intention. `promote_proposal` returns labels, not which Application each row
landed under, so the runtime asks for the Program and `execution.py` calls it in
the promotion's own transaction. An Application the promotion never touched gets
the row that says so, which is the same decision as recomputing an unchanged
surface: looking and finding nothing is a fact worth keeping.

### v_surface_deltas carries no identifier, which is 020's rule and not a habit

The compact read was written with `id`, `program_id` and both fingerprint
uuids on it, and `check_state_access`'s `uuid_in_view` arm refused the
migration on the spot. The fix is not a cast: a fingerprint is named by its own
value, because that is what a fingerprint is, and a subject is named by its
label, because that is what a subject is called. Ticket 34 joins
`surface_deltas` itself, on the runtime role, where the identifiers live.

The view is criterion 5's own read and not a spare one: "deltas identify the
affected subjects and Property classes" is a join, and a caller that made the
join itself would be a second place deciding what a delta puts back in
question.

### What the review changed

A two-axis review ran against the finished change. Fourteen findings; twelve
applied, two answered.

The one that mattered was a glossary breach the whole file was built on.
CONTEXT.md tells this system to avoid hash, version, snapshot and signature for
a Surface fingerprint, and the change had shipped `rk2_surface_digest`, a
`digest` payload key, a `recipe_version`, and a view that renamed the column it
selected -- `now_fp.fingerprint AS digest`. A fifth synonym is the same mistake
the avoid list exists to stop, so the value is called `fingerprint` everywhere
now: the function, the payload, the return value and both view columns.
`digest` survives in exactly one place, describing sha256 as an operation.
CONTEXT.md gained the word to its own avoid list.

`rk2_surface_version()` went rather than being renamed. Nothing branched on it,
no criterion asked for it, and it put a value that is not about the Surface
inside the thing the fingerprint is taken over.

Three duplications and a silence:

- The `member_of` reachability rule was written twice, in the projection and in
  the subject lookup. It is `rk2_surface_holds` now, and both read it.
- `compute_surface_fingerprint` built its Event payload and its return value as
  two nearly identical objects. One object, said once, and a test asserts the
  two are the same thing.
- `('added'),('removed'),('changed')` appeared in the seed, in a CHECK and in a
  check arm. `rk2_surface_changes()` is 021's `rk2_origins` pattern applied to
  it.
- `rk2_surface_subject`'s `CASE` ended in `ELSE NULL`, so a fifth registered
  section would have given every one of its deltas a null subject and no arm
  would have noticed. It raises.

Three things the SQL did not do that a comment said it did:

- `projection_section_missing` asked whether *any* stored fingerprint carried
  the section, so one old row kept the arm green forever -- including in the
  case the comment named. It asks the function, over an Application that does
  not exist, whose projection still carries all four sections.
- `UNIQUE (fingerprint_id, kind, subject_key)` was described as making a
  repeated recompute idempotent. It cannot: the second recompute mints its own
  fingerprint row. What it actually forbids is now what it says.
- The endpoint key was `upper(en.method)`, and `endpoints` is unique on the
  method as written. Two rows differing only in case would have collided into
  one key, cross-joined in the comparison and aborted the recompute on the
  delta's own unique key. The key is the method as stored, and a test writes
  both spellings.

Two claims in this file and the migration were true of a schema that changed
three tickets ago: `identities_slot_idx` has been per Program since 017, not
global. The exclusion stands; the reason was stale. And the endpoints and
parameters branch of the subject lookup was a plain `SELECT INTO`, which would
have picked one row where the file claimed it named none.

Answered rather than applied: the spec axis read `v_surface_deltas` as
unrequested, and it is criterion 5's own join, above. It also read the four
`_removed` kinds as satisfying neither half of criterion 5, since they map to
no class and resolve to no subject. That is the decision the file argues for
twice and a test asserts: a subject that is gone tests nothing.

### What 023 still gets wrong, and why this file did not fix it

`rank_pass` reads the newest fingerprint per **Program**, and a Program with
two Applications now has two rows racing for "newest". The fingerprint is per
Application because 012 made `application_entity_id` NOT NULL, so the ranking
half has been comparing across Applications since it was written.

Left alone on purpose. 023 is frozen corpus owned by tickets 23 and 34, and a
ticket that changed what fires a retest in the same breath as inventing the
input would be two changes nobody could review apart.
