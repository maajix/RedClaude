# 42 — Render Findings and chains deterministically

**What to build:** Produce submission-ready Finding and kill-chain reports as deterministic projections of currently validated canonical rows.

**Blocked by:** 37 — Validate a Finding through a blind validator; 40 — Build and evaluate a sound kill chain.

**Status:** resolved

- [x] The reporter is a pure renderer with no model, tools, target access or state mutation.
- [x] Only validated Findings and sound, review-cleared chains can render; candidate, rejected, invalidated or gated records are refused.
- [x] Reports include scope, affected subjects, reproduction, baseline/variant/controls, demonstrated impact, limitations, evidence identifiers and remediation context.
- [x] Chain reports distinguish individually demonstrated composition from an actually executed end-to-end chain.
- [x] Equivalent input rows in different order render byte-identically.
- [x] Optional narrative is off by default and, when enabled, cannot introduce an identifier or factual field absent from the deterministic projection.

## How each is met

1. **The signature is the criterion.** `render(bundle, *, narrative=None) -> str`
   takes a mapping and returns a string, and there is nothing else in the room:
   no connection, no settings, no model handle, no clock, no environment. It
   cannot reach a target because it is given nothing that could, and it cannot
   mutate state because it is given nothing that holds any. `PurityTest` asserts
   the whole parameter list rather than a rule about it, which is the same move
   041 made for a prediction that has nowhere to be stored.

   The other half is the path either side of that call, because purity in one
   function is worth nothing if the read that feeds it writes. All five read
   functions -- `report_source_bundle`, `chain_source_bundle`,
   `chain_source_digest`, `read_finding_report`, `read_chain_report` -- are
   declared STABLE, and `test_the_read_surface_the_reporter_uses_cannot_write`
   reads `provolatile` out of `pg_proc` for all five: PostgreSQL refuses a write
   inside a non-VOLATILE function, so the property is enforced by the server and
   not by a convention. `_report` in `cli.py` opens one connection and nothing
   else: no boundary, no egress door, no artifact store, so there is no capability
   in the command's hands to spend. The one write on the path is
   `record_rendering`, which is behind `--record`, files bytes and touches no
   Finding row.

2. **Neither gate is computed here.** A Finding renders when every row
   `report_blockers` returns is soft; a chain renders when
   `rk2_chain_unsoundness` returns NULL. There is deliberately no
   `chain_report_blockers`: 040's sentence already asks 039's question of every
   step, the four a chain has of its own, and -- in its arm (f) -- the two review
   gates that hold a member, `known_issue` and `duplicate`. "Review-cleared" is
   therefore asked rather than re-worded, and a second wording would be free to
   drift the day 040's is edited. The six blockers 040 left out stay out for a
   reason it could only half state, written down at the head of section 4 of the
   migration: `no_effect`, `no_chain` and `unwitnessed_effect` empty a Finding's
   own impact sentence and attack chain, which a chain report does not render;
   `cvss_stale` and `severity_unstated` are about a band no chain report prints;
   and `not_validated` fires on a member that has been reported, which is when a
   chain is most worth having.

   `Refused` carries every reason rather than the first, because a Finding is
   usually blocked several times over and an operator told one reason fixes it
   and meets the next.

   The half that costs something is `record_rendering`, which answers `blocked`
   rather than `refused` when a hard blocker stands: bytes rendered before a
   blocker appeared cannot be filed after one.
   `test_the_bytes_of_a_blocked_finding_cannot_be_filed_either` files a string
   against a Finding with three standing blockers and then asserts no
   `report_renderings` row carries it.

3. **The criterion is a function, and the check reads it.**
   `rk2_report_required_blocks(subject)` lists criterion 3's nine subjects mapped
   onto the block registry, and `check_report_projection` arm 1 fails any
   template flagged `complete` that is missing one of them. Without that function
   the check would have to name `platform.long_form` as a literal, and a template
   renamed later would make the check pass by asking nothing. Arm 2 requires
   exactly one complete form per subject, so "the complete form" names something.

   Three of the nine had no block at all in 034 and four more were needed for the
   chain side, so `report_blocks` gained `scope_block`, `controls`,
   `limitations`, `chain_header`, `chain_composition`, `chain_transitions` and
   `chain_evidence`, and a `subjects` column saying which subject each may appear
   under -- the renderer for `severity_block` reads a CVSS vector a chain does not
   have, so the pairing is a fact about the block and not a convention a template
   author is trusted with.

   "Demonstrated impact" is 038's row and not 034's effect, and the bundle
   carries both under those two words. `effects` is what an observation
   witnessed; `demonstrations` is what an impact run proved, with an after-state
   Receipt and a performed cleanup behind it, and `_impact_sentence` prints them
   under two headings. A section that printed only the first would give the
   weaker of the two the stronger one's evidence.

   The limitations block is derived and never authored: a limitations section a
   model wrote says what its author wanted a reader to worry about.
   `finding_limitations` has seven arms -- soft blockers, review signals, an
   unfinished cleanup, an assertion that settled nothing either way, a Test that
   has held exactly once, fewer demonstrations than witnessed effects, and
   evidence that is credential-bearing and so cited by hash only. The sixth is
   counted rather than named per effect: `finding_effects.effect_id` is a
   `report_effects` id, `impact_demonstrations.impact_class` is an
   `impact_classes` id, and nothing in the schema maps one vocabulary onto the
   other -- so no row can say which effect a given demonstration proved, and a
   per-effect sentence keyed off a per-Finding predicate would name one effect
   and mean another.
   `chain_limitations` adds its own (a branching composition is more than one
   route) and carries every member's up under the member's label, because a
   limitation stated on a member's report and dropped from the chain report
   composed on it would be one the composition hid.

   The role split the criterion asks for is not a bundle key. `spec` already
   carries every action under the role it was written for, and grouping them is
   what a renderer is for; a second grouped copy in the bundle would be the same
   three lists in two places.

4. **The word is computed from the stamps, not set by anybody.** Every pivot
   stamp names the Tool run that demonstrated it, so `rk2_chain_execution`
   restricts the chain graph to one run at a time and asks whether that run's
   stamps cover a whole path from an entry step to a terminal one. They do:
   `executed`. They do not: `composed`. A walk that changed runs half way is two
   demonstrations, which is what composition already means, so the recursive term
   joins on the run as well as on the edge. `chain_composition` then states which
   of the two this is in a paragraph a triager reads once, rather than leaving it
   to be inferred from whether the transitions happen to share an identifier.

5. **Every list arrives ordered by a fact, and nothing below re-sorts.** Both
   bundles build every array with `jsonb_agg(... ORDER BY ...)` over a column
   that means something -- `finding_effects.ordinal`, `finding_chain_steps.ordinal`,
   citation ordinal, `chain_steps.depth` then the stamp label, receipt arrival
   then label -- and the renderer iterates what it is handed, never re-groups by a
   dictionary and never asks the clock.

   The test is about rows and not about a mapping.
   `render_the_same_rows_in_another_order` deletes the Finding's two effects and
   writes them back with ordinal 2 physically first, then does the same to step
   1's two citations, and asserts the bundle, its digest and the rendered bytes
   are all unchanged. `test_the_shuffle_really_did_move_the_rows` reads the two
   effect rows back in `id` order and asserts the ordinals now run 2 then 1,
   because without it the arm above would pass over a shuffle that did nothing.

6. **A narrative is a paragraph that may rephrase and may not add.** `--narrative`
   takes a path; absent, `render` is called with `narrative=None` and the document
   has no authored line in it. Given one, it is a JSON object of block identifier
   to one paragraph, and only three blocks accept one -- `impact_sentence`,
   `limitations`, `remediation`, the ones that argue rather than record. A
   narrative under `evidence_manifest` would be prose beside a list of hashes,
   where the only thing it could add is emphasis. `chain_composition` is
   deliberately not among them: it is the whole of criterion 4, the distinction
   it draws is made of ordinary words, and the token check below would let a
   paragraph there assert the opposite of the sentence above it.

   What it may say is bounded token by token. `_claims` pulls out of a paragraph
   the tokens that look like factual claims -- identifiers, numbers, paths, hosts,
   hashes, versions -- and every one must appear among `_scalars(bundle)`, the
   scalars the projection itself carries. The projection and not the rendered
   document, which is criterion 6's own wording: a short form omits blocks, and
   binding the sentence to the document would make what an operator may write
   depend on which form was asked for. Ordinary words pass untouched, so a
   sentence can rephrase the projection and cannot introduce an endpoint, a
   status, a version or a count the projection does not have. Accepted prose is
   marked in the document under `NARRATIVE_MARK` rather than blended into it, so
   a triager who wants only what the harness established can find where that
   stops.

## What this ticket also changed

- **`compose_finding_report` is here, and it is not one of the six criteria.**
  034 built `finding_effects`, `finding_chain_steps` and
  `finding_chain_step_citations`, wrote the grounding trigger over them, and
  nothing in the tree ever inserted a row. Every criterion 3 report would have
  rendered "No effect is recorded against this Finding" forever. The composer is
  the writer those three tables never had: it takes the effects and the steps as
  one document, replaces the previous composition inside a subtransaction, and
  answers with the blockers that are LEFT rather than with a grade of what it was
  given -- a composer that graded its own input would carry a second copy of
  `report_blockers`. It calls `SET CONSTRAINTS chain_step_grounding IMMEDIATE`
  around the writes, so 034's deferred trigger answers as a returned refusal
  instead of aborting the caller's transaction at commit, long after the call
  that was wrong. `test_a_composition_the_tables_refuse_comes_back_as_a_sentence`
  asks nine wrong compositions and reads nine sentences, and
  `test_a_refused_composition_leaves_the_one_that_held` asserts the composition
  that held is still there afterwards, because the DELETE lives inside the
  catching block too.
- **`report_renderings` has a writer for the first time.** 034 designed the table
  and `enforce_report_approval` names a row in it, so ticket 19's approval gate
  has been a door onto a wall. `record_rendering` recomputes the source digest
  and hashes the bytes itself rather than accepting either from the caller, since
  those two are exactly what the approval gate compares -- a digest this process
  supplied would be a comparison against this process's own claim.
- **`report_review_signals` third column has a name.** 034 left it unaliased, so
  it was `?column?` and a second reader could not name it without quoting
  something PostgreSQL invented. Renamed to `detail`.
- **`check_report_projection` joins the standing checks.** Six arms: a complete
  form missing a block its criterion names, a subject without exactly one complete
  form, a form carrying a block that is not about its subject, a form with no
  blocks at all, a form whose ordinals skip or start late, and a chain step whose
  parameters do not fill a slot its mechanism declares. The last is the other half
  of 034's `mechanism_slot_mismatch`: 034 checks that a mechanism's declared slots
  are the ones its sentence uses, and this checks that a step supplies them,
  because a renderer is what turns an unfilled slot into a report with `{path}`
  printed where the path should be. Every arm has a negative control, forged onto
  a scratch form of the case's own and removed again -- `report_templates` is a
  global table, and an arm asserted by breaking the form the rest of the suite
  renders from would leave it broken for every case after it.
- **`ReportProjectionTest` clears two tables in its teardown.**
  `finding_effects.witness_observation_id` and
  `finding_chain_step_citations.observation_id` reference `observations` with no
  `ON DELETE`, so dropping the Program cascades into the observations and into
  those two in an order PostgreSQL picks, and it picks the observation first.
  This is the only case in the file that has such a row.

## What is not covered

- **Criterion 4's `executed` cannot be reached through the door today, and the
  SQL side says so.** 039 issues one stamp per impact run and
  `pivot_stamps_immutable` refuses to repoint a stamp's `tool_run_id`, so there
  is no arrangement in this harness that produces one run whose stamps cover a
  whole path. `test_the_chain_report_says_which_kind_of_demonstration_it_is`
  therefore pins `composed` and asserts the two stamps came from two distinct
  runs, which is the fact that makes it `composed`. Both wordings are pinned in
  `tests/test_reporting.py`, where the bundle is written out and `execution` can
  be set to either -- so the `executed` branch is tested, against a hand-written
  bundle, and the recursive query that decides between them is tested against a
  real chain.
- **The composer has no CLI and is served to nobody.** For 040's reason:
  `compose_finding_report` is called by the tests, and what a Finding's effects
  and mechanism steps are is a judgement whose author is the validated Finding's
  own evidence. Wiring it to a model-facing verb is a decision about who composes
  a report, which is a different ticket from how one renders.
- **A chain report carries four of criterion 3's nine subjects, and that is the
  design rather than an omission.** `rk2_report_required_blocks('chain')` names
  the chain header, scope, the composition, the transitions, their evidence and
  the limitations; it does not name reproduction, baseline/variant/controls,
  demonstrated impact or remediation. Those four are facts about one validated
  Finding -- one specification, one validating run, one impact run, one
  vulnerability class -- and a chain is a composition of several. A chain report
  that carried them would carry each member's copy, which is each member's own
  report reprinted inside a document about the composition. What the chain
  report does carry is the pointer: every transition names the member it came
  from by label, so a triager reading it can ask for that member's report and
  get exactly those four sections about exactly one Finding.
- **The short forms are not complete forms and nothing asks them to be.**
  `rk2.default` and `rk2.chain` are deliberately shorter -- the operator's few
  parts, fitting on a screen -- and `complete = false` says so. Criterion 3 is a
  claim about `platform.long_form` and `platform.chain_long_form`, and the check
  only holds those two to it.
- **A rendering is filed against a Finding and never against a chain.**
  `report_renderings.finding_id` is NOT NULL and an approval is a transition of
  one Finding, so `--record` is absent from the chain form rather than refused
  there. A chain report is bytes an operator keeps; it is not a row the approval
  gate can name.
- **The narrative check is over tokens, not over meaning.** A paragraph made
  entirely of ordinary words passes, and a sentence that draws a wrong conclusion
  from facts the projection does carry passes too. What is bounded is the set of
  identifiers and factual fields that can appear, which is what criterion 6 asks
  for; whether the argument built out of them is sound is what a human approval
  is for.
- **`finding_source_digest` and `chain_source_digest` exclude the gate on
  purpose.** What identifies a document is what it says, and whether it may be
  rendered right now is not part of that -- 034's argument for leaving `blockers`
  out of the Finding digest, applied to the `sound`/`unsound` pair that answers
  the same question on the chain side. So a Finding that gains a soft blocker
  renders different bytes and a different digest; one that gains a hard blocker
  renders nothing at all, and its digest is unchanged.
- **No report is submitted anywhere.** This ticket renders bytes and files them.
  Everything about a platform, a submission, a triager's reply or a duplicate
  ruling is somebody else's.
