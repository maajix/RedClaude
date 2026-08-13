# 21 — Promote a recon Mission into typed Surface

**What to build:** Let a recon Agent discover a small synthetic web surface and have the runtime deduplicate and promote its scoped Entities and Relationships with exact provenance.

**Blocked by:** 20 — Run one Task to a canonical Observation.

**Status:** resolved

- [x] A recon Mission can propose Domains, Hosts, Services, Applications, Endpoints, Parameters, Technologies and Identities using typed fields and stable evidence references.
- [x] Runtime promotion scope-checks and canonicalizes every proposed subject before creating canonical rows.
- [x] Containment and typed Relationships remain distinct, and invalid direction or vocabulary is refused.
- [x] Parallel proposals for the same semantic subject converge on one Program-scoped Entity while preserving all valid provenance.
- [x] Imported, runtime-observed and model-proposed origins remain distinguishable.
- [x] Compact Surface reads expose stable labels and never require the recon transcript.

## Comments

Implemented on 2026-08-13. One migration,
`20260813T090000Z__a_recon_run_becomes_typed_surface.sql`, plus one sentence
of child-facing prose in `_launch.py`.

No new module. Everything the criteria ask for is a question about rows the
database can already be made to answer, and the one place all six meet is
`promote_proposal`, which 020 left holding a single element list. This file
gives it three.

### The filename says recon run, not Mission

Migration filenames are permanent, and `Mission` is a refused synonym:
`CONTEXT.md` lists it under **Agent run**'s `_Avoid_` and again under **Mission
packet**'s. The ticket title predates that line. The file is named for what it
does --- a recon run becomes typed Surface --- and the ticket keeps its own
title so the tracker stays greppable.

### Containment is a foreign key, and the check says so out loud

The third criterion is two claims, and only one of them is about promotion. A
Service belongs to a Host by `services.host_id`; a Relationship is the typed
edge between two Entities that containment is not. `entity_containment` writes
that down as three rows --- which child type sits under which parent, and the
column that holds it --- and `is_containment` refuses a proposed Relationship
whose two ends are a containment pair in either direction.

It is its own refusal reason rather than `invalid_direction` because they are
different mistakes. `invalid_direction` is an orientation to reverse, and an
agent told that about a containment pair would send the same claim back around
the other way. `is_containment` says the fact is already held elsewhere.

`containment_registry_untrue` closes the loop the other way: a registry row
naming a foreign key the schema has not got would make the refusal a comment.

### The grammar is a trigger, so it is not promotion's rule

`relationship_directions` is the vocabulary with its directions --- twenty
registered ordered pairs --- and `enforce_relationship_grammar` is
`ENABLE ALWAYS` on `relationships`. Promotion asks the registry itself so it can
refuse an element individually and keep promoting the rest; the trigger asks it
again for every other writer, including a superuser session and including
whatever writes `imported` rows in 058. A grammar that lived only in
`promote_proposal` would be a rule about one caller.

`same_as` is seeded for all eight types deliberately: `0004_relationships.sql`
put it in the vocabulary as identity between two rows of the same type, and a
grammar that refused it for six of them would contradict the file that named
it.

### Convergence is the dedup key, and provenance is a row per witness

The fourth criterion is two halves that pull against each other. Converging on
one Entity means the second proposal of the same Host must not create a row;
preserving all valid provenance means it must not be a no-op either.

`rk2_dedup_key` canonicalizes the subject before anything is written --- a
lower-cased FQDN with its trailing dot gone, a base URL parsed into scheme,
host and port with the default port dropped, a path template with its
duplicate slashes collapsed --- and the Entity is looked up by it. Then
`entity_provenance` takes a row per `(subject, evidence)`, unique on
`(entity_id, origin, proposal_id, element_path)`. The second proposal adds a
witness to an Entity that already exists. Two agent runs that found the same
Host both said so, and the read shows both.

### Four origins, because three cannot stay distinguishable

The fifth criterion names three. `rk2_origins()` returns four:
`configured`, `imported`, `observed`, `proposed`. `configured` is the fourth
because the corpus already had it --- every Entity written before this file
came from an operator's scope, and the column's default has to be able to say
that without rewriting history.

`imported` has no runtime writer yet; 058 is the ticket that adds one, and the
value is in the vocabulary now because a column that cannot say `imported`
makes an importer's first row either a lie or a migration. `observed` has no
entity writer either, and that is the honest state: the only instrument the
harness has today produces a Receipt an agent then reads, so the Entity that
comes of it is `proposed`. The column distinguishes them the moment either
writer exists.

### The compact read carries the joins, so the revision has to as well

`v_records` gains an `entity` kind carrying the origin, every origin that has
since witnessed it, the containment parent and the typed relationships, capped
at twenty with `relationship_count` beside the list so a truncated read says it
was truncated. That is the sixth criterion: stable labels, no transcript.

Because the record embeds the relationships, its `revision` is the greatest of
the Entity's own and every embedded Relationship's --- `relationships` is a
row-event table (`0013_events.sql`), so a new edge moves `max(events.seq)` for
a row the reader never asked about. A revision that only tracked the Entity
would let a caller hold a stale record that compared equal.

### What the review changed

The two-axis review ran against `e1cae84` and produced findings in both axes.

Applied. The three verbatim citation blocks are one `rk2_element_evidence`,
called once per walk. `rk2_entity_types()` is a real vocabulary function rather
than a list repeated in the header, and moved into section 1 because section 3
uses it and a migration runs top to bottom. A host element whose `address` was
present but unparseable now refuses with `malformed_field` instead of being
written with a null address --- silently dropping a field the agent supplied is
the one outcome that teaches it nothing. `is_containment` became its own drop
reason, where the comment already claimed a distinct one. The entity record's
revision covers its relationships, and the capped list carries its count. An
eighth standing-check arm, `entity_type_vocabulary_disagrees`, compares
`rk2_entity_types()` against the CHECK on `entities.type`. `v_edge`/`v_edges`
became `v_relationship`/`v_relationships`, `v_class` split into `v_app_kind`
and `v_identity_class`, and `v_touched` split into `v_wrote_entity` and
`v_canonical`, because it meant two things in two functions.
`CONTEXT.md` gained **Surface** and **Origin**, and **Lane**'s `_Avoid_: origin`
now points at the term rather than at nothing.

The Spec axis asked for closed item schemas on the three element lists.
Rejected as written: `roster.OPEN_ARGUMENTS` records the decision that these
lists stay open, and item schemas would contradict the file that documents it.
The real gap it found is that a child was never told the field names, and a
field name it has to guess is a drop row with `malformed_field` on it. So
`DESCRIPTIONS["submit_mission_result"]` now names them --- every typed field of
every type, in one sentence.

Also rejected: refusing `same_as` for types with no dedup story, for the reason
above.
