# 113 — Open redirection is routed to a class, a trigger and a Playbook that do not line up

**What to build:** A decision about where open-redirect work goes, and the
repair of three separate misroutings that a reader of the corpus meets as one
sentence.

**Blocked by:** nothing.

**Status:** resolved

- [ ] The class does not exist, and ticket 100 is the migration it arrives in.
      `client_side.navigation` is named as a property class in three places -- `src/redkraken/playbooks/ssrf-url-routing/playbook.md:128`
      ("the class is `client_side.navigation` and the Playbook is `routing`"),
      `src/redkraken/playbooks/ssrf-url-routing/references/open-redirection.md:30`
      ("the class is `client_side.navigation`. `routing` asks it"), and a
      migration comment at
      `20260902T000000Z__seven_server_side_file_and_disclosure_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:536`.
      There is no `client_side` family: `property_class_families` holds eight
      and none of them is it. The migration comment is the third site and report
      20 lists only the two Playbook files.
- [ ] The trigger it names is listed by no Playbook, and ticket 101 is where it
      gets its first consumer. `redirect_target` is
      registered at `0032_playbooks.sql:66` and is computed --
      `subject_facts` has a branch on `relationships.type = 'redirects_to'` --
      and `grep -rn redirect_target src/redkraken/playbooks --include=playbook.md`
      returns nothing. It is a fact the harness computes for nobody.
- [x] The Playbook it delegates to does something else. `routing` triggers on
      `flow_step` and `state_changing_method` and its declared output is
      `business_logic.workflow_order`. It does not ask about redirect targets
      and cannot claim a class about them.
- [x] The decision is which of three repairs is right, and it is a human's.
      Add the class and a fixture to grade it, which is ticket 100's mechanism
      and would make this ticket a row in 100's table; give `routing` the
      trigger and the output, which is a change to a shipped Playbook and is
      ticket 101's; or route the reading to a class that already exists and fix
      the two reference pages, which is 101's alone. The ticket names the choice
      rather than making it, because each answer costs a different ticket.
- [x] Whichever is chosen, the migration comment moves with the Playbook text.
      A `--` comment in a recorded migration cannot be edited, so the repair is
      a sentence in the migration that supersedes it, which is the house
      standard `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:100-104`
      already sets.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 5 calls this "the worst
single row in this report" and explains why: it is a triple miss in one
sentence. The class does not exist, the trigger it names is listed by no
Playbook, and the Playbook it delegates to emits something else. "Two corpus
files route open-redirect work into a hole with three separate bottoms."

Its gate G2 is the check that would have caught the first bottom on the day it
was written: every backticked `family.leaf` token in a Playbook or Skill body is
either a declared property class or is not family-shaped. The report notes that
the second clause has to be family-gated or it drowns in `yaml.safe_load`, and
that gating on `property_class_families.id` is exact and cheap.

## The decision, taken 2026-08-22

**The first repair: a new leaf in the existing `injection` family, arriving with
the fixture that grades it, as a row in ticket 100's table. `routing` does not
get the trigger, no `client_side` family is created, and the reading is not
folded into a class that already exists. The two reference pages and the
migration comment are then repaired to name the leaf that exists -- 101's work,
and it cannot start until 100's row lands.**

**Why not fold it into `injection.url_authority`, which is the tempting answer.**
The corpus already ruled that out in writing, twice, and both statements survive
checking. `20260902T000000Z...:238-249` gives the reason `url_authority` was
minted as its own leaf rather than merged with `injection.request_forgery`: "A
target can be either without being the other ... so one leaf could not grade
both." The open-redirect page makes the identical argument one step further out
(`src/redkraken/playbooks/ssrf-url-routing/references/open-redirection.md:36-39`):
"They share a parser bug and nothing else. A route can be an open redirect and
fetch nothing; a route can fetch the caller's authority and never emit a
`Location`." And the two readings are separated by what counts as evidence, which
is the thing a grading fixture keys on: `url_authority` is graded by a
**disagreement** read off the response body -- "the authority a route validates in
a caller-supplied URL is not the authority it fetches"
(`20260902T000000Z...:274-275`) -- while this one is graded by a `Location` header
or a navigation a browser performed (`open-redirection.md:28-31`). A fixture that
graded both would have to accept two different proofs for one class, which is the
defect ticket 100 exists to stop multiplying.

**Why `injection` and not a new `client_side` family.** The eight families are
questions, not layers (`0018_vocabularies.sql:47-64`), and `injection` is
"whether attacker-controlled input reaches an interpreter, parser or fetcher" --
the browser's URL resolver being an interpreter is exactly the reading three
shipped leaves already take. `20260829T000000Z...:228-234` added
`injection.client_channel`, `injection.client_path` and
`injection.foreign_resource`, all three browser-side, all three under `injection`,
one of them ("input decides which external host supplies script, style or markup
to the page") a near-neighbour of this one in everything but the sink. A ninth
family invented for one leaf would be the first family with a single member and
would have to be justified against those three. The leaf this ticket proposes is
`injection.navigation_target` -- *input decides which host a route sends the
caller's browser to* -- and the name is the part a maintainer may change; the
family is the part the evidence settles.

**Why `routing` cannot take it.** `routing` is not merely aimed elsewhere, it is
declared elsewhere: `src/redkraken/playbooks/routing/playbook.md:3-5` reads
`bb:category: business_logic`, `bb:outputs: ["business_logic.workflow_order"]`,
`bb:triggers_all: ["flow_step", "state_changing_method"]`, and its description is
about completing a flow in order and then reaching a step from a session that
never took it. Handing it `redirect_target` and a second output in another family
would make it two Playbooks sharing a name, and the selection funnel treats a
Playbook as one question with one trigger set. The emitter belongs to a Playbook
whose whole question is where the browser is sent -- 101's business, and 101 is
already the ticket for "the Playbooks the 131 researched techniques have no home
in".

**What that fixes, in the ticket's own three bottoms.** The class comes to exist
(bottom one). `redirect_target` gets its first consumer, which is the only reason
the harness computes it (bottom two): the fact is registered at
`0032_playbooks.sql:66` and computed in every rebuild of `subject_facts` since,
most recently `20260904T000000Z...:121-124`, and `grep -rn redirect_target
src/redkraken/playbooks --include=playbook.md` returns nothing. And `routing` is
left alone, so bottom three is repaired by correcting the two sentences that point
at it rather than by changing a shipped Playbook (bottom three).

## What was measured

`property_class_families` holds exactly eight rows, all inserted at
`0018_vocabularies.sql:47-64`, and no later migration inserts another -- `grep -rn
"property_class_families" src/redkraken/migrations/` finds the table, that one
INSERT, and five foreign-key references. There is no `client_side` family and no
class whose id begins `client_side.`. Forty-seven Playbook bodies were read: none
lists `redirect_target` in `bb:triggers_all`, and `routing`'s declared output is
`business_logic.workflow_order` and nothing else. Three of the browser-side leaves
minted in the last three months sit under `injection`
(`20260829T000000Z...:229-234`).

## Correction: the third site is a comment about disposition, not a routing claim

The ticket lists `20260902T000000Z...:536` as the third site naming
`client_side.navigation` and treats the three as one misrouting. Read in place
(`:530-540`) the migration comment is doing something different from the two
Playbook pages: it is explaining why a v1 reference page is attached to
`ssrf-url-routing` even though its subject is graded elsewhere -- "the disposition
ledger records where each v1 page went, not where its subject is graded". It
repeats the bad class name and so must still be superseded, but whoever writes the
superseding sentence should supersede the *class name* and leave the disposition
reasoning standing, because that reasoning is correct and is load-bearing for
ticket 47's ledger. The house standard the ticket cites for how to do that
(`20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:100-104`) is the right
one.

## What was built, 2026-08-22

One migration and two corpus files. No property class is inserted, no Playbook
gains a trigger or an output, and `routing` is not opened.

`src/redkraken/migrations/20261004T000000Z__the_open_redirect_reading_names_no_class_this_schema_lacks.sql`
does three things. It re-issues `COMMENT ON TABLE playbook_references`, which is
the live object the superseded `--` comment sits above: ticket 45's sentence
about human-only material is kept whole, 20260902's disposition reasoning is
promoted onto it in the words the Correction section above asked for -- "a row
records where a v1 page went, not where its subject is graded" -- and only the
class name is superseded. It re-freezes `playbooks/ssrf-url-routing/playbook.md`
from `230cd69c8` / `843d0cf8f` to `74756d306` / `429c2cd22`, in the `VALUES`
shape `tools/check_coverage.py` reads. And it re-hashes the attached
`open-redirection.md` from `9372af0aa` to `0a10ef088`, because
`playbook_references.sha256` is what tells a maintainer whether the page moved.

`playbooks/ssrf-url-routing/playbook.md` step 6 kept its third neighbour bullet
and lost both false claims in it. It now says that this corpus holds no Playbook
that asks where a browser is sent and no class that grades it, that it is not
`routing` and why, and that a claim made there would have no class to carry it.

`playbooks/ssrf-url-routing/references/open-redirection.md` lost the sentence
that routed the reading to `client_side.navigation` on a `redirect_target`
trigger, and gained a section that states all three misses against the artifacts
that disprove them, records the decision above in short form, and names ticket
100 for the leaf and its fixture and ticket 101 for the emitter. It writes no
leaf name of its own: the corpus rule that a backticked `family.leaf` in any
shipped `.md` must be a declared class is already enforced by
`tests/test_playbook.py:629` over `playbooks/`, `fixtures/` and `skills/`, and
it caught a first draft of this page that named the proposed leaf.

## What was measured

The four gates, from the worktree root, all rc=0. The three that read the tree
were also run against a pristine checkout with only these files applied, because
several other tickets were in flight in the same worktree and a green run there
says nothing about this change on its own:

* `PYTHONPATH=$PWD python3 -s tools/check_audit.py` -- rc=0. This ticket is
  `resolved` and reaches ticket 65, which is what the run before the Blocked-by
  edit refused.
* `PYTHONPATH=$PWD python3 -s tools/check_wiring.py` -- rc=0, with
  `W9 vocabulary 9 owed  property classes 57  emitted 50  unmakeable 2` and
  `register 94 rows`, both unchanged from the reading before this change. That is
  the point: no class was added, so no W9 finding was added, so no register row
  was needed and none was written.
* `PYTHONPATH=$PWD python3 -s tools/check_baseline.py` -- rc=0,
  `classifications=10 regressions=7 adapters=10 artifacts=223 frozen`.
* `PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py` -- rc=0,
  `in-scope playbooks 49  loadable 49  frozen 49`, which is the reading that
  holds the re-freeze above to the bytes this checkout ships.

`python -m unittest tests.test_playbook` -- 58 tests, OK. It is the case that
matters here rather than a gate:
`test_no_shipped_document_names_a_property_class_the_vocabulary_lacks` is gate G2
already implemented, and unlike `check_wiring`'s W9 it reads reference pages and
fixture ground truth as well as Playbook bodies. It failed a first draft of
`open-redirection.md` that wrote the proposed leaf name down, which is why that
name is in this ticket and in no shipped document.

The migration was applied to a scratch database provisioned from empty:
`migrate ok: True`, the comment read back off `\d+ playbook_references`, and
both digests read back at the values this file names. Its closing `DO` block was
then watched failing, one arm at a time, against that database: the comment
wiped (`the live comment on playbook_references does not carry the
supersession`), the comment written without the disposition sentence (`the
supersession dropped the disposition reasoning it was told to keep`), the
Playbook digest made stale (`ssrf-url-routing is registered at aaaa..., not at
the text this file froze`), the reference digest made stale (`open-redirection.md
is attached at bbbb..., not at the bytes this file hashed`), a
`redirect_target` trigger inserted (`redirect_target has a consumer already, and
ticket 113 records that it has none`), a `client_side` family inserted (`a
client_side family exists after all`), and a second output given to `routing`
(`routing emits {business_logic.workflow_order,injection.markup}`). The control
passed before and after every one.

## What was not paid, and why

Criteria one and two are unticked and both are deferred by the decision itself
rather than by this agent.

**The leaf is ticket 100's row.** The decision says it "arrives with the fixture
that grades it, as a row in ticket 100's table", and the gate agrees: `W9` in
`tools/check_wiring.py` refuses any declared property class that no Playbook
emits and that nothing declares unmakeable -- it is what already reports
`authentication.recovery_flow` and four others, all registered `owed:101`.
Inserting `injection.navigation_target` here with no emitter would have turned
that gate red for two new findings, and the register row that would excuse it is
ticket 101's to write when the emitter lands. So the class is still absent and
this ticket adds nothing to the vocabulary.

**`redirect_target` still has no consumer.** It is ticket 101's, for the reason
the decision gives: the emitter belongs to a Playbook whose whole question is
where the browser is sent, and `routing` cannot be it. The migration's `DO` block
asserts the absence rather than assuming it, so the day some file gives the fact
a consumer this assertion is where it is found out.

What is paid today is that no shipped document points at the hole any more. The
class name is gone from both corpus files and superseded on the live comment,
and nothing in the tree now tells a reader that `routing` grades a redirect
target.
