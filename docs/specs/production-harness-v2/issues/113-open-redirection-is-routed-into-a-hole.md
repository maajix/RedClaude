# 113 — Open redirection is routed to a class, a trigger and a Playbook that do not line up

**What to build:** A decision about where open-redirect work goes, and the
repair of three separate misroutings that a reader of the corpus meets as one
sentence.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The class does not exist. `client_side.navigation` is named as a property
      class in three places -- `src/redkraken/playbooks/ssrf-url-routing/playbook.md:128`
      ("the class is `client_side.navigation` and the Playbook is `routing`"),
      `src/redkraken/playbooks/ssrf-url-routing/references/open-redirection.md:30`
      ("the class is `client_side.navigation`. `routing` asks it"), and a
      migration comment at
      `20260902T000000Z__seven_server_side_file_and_disclosure_topics_arrive_as_playbooks_and_the_targets_that_grade_them.sql:536`.
      There is no `client_side` family: `property_class_families` holds eight
      and none of them is it. The migration comment is the third site and report
      20 lists only the two Playbook files.
- [ ] The trigger it names is listed by no Playbook. `redirect_target` is
      registered at `0032_playbooks.sql:66` and is computed --
      `subject_facts` has a branch on `relationships.type = 'redirects_to'` --
      and `grep -rn redirect_target src/redkraken/playbooks --include=playbook.md`
      returns nothing. It is a fact the harness computes for nobody.
- [ ] The Playbook it delegates to does something else. `routing` triggers on
      `flow_step` and `state_changing_method` and its declared output is
      `business_logic.workflow_order`. It does not ask about redirect targets
      and cannot claim a class about them.
- [ ] The decision is which of three repairs is right, and it is a human's.
      Add the class and a fixture to grade it, which is ticket 100's mechanism
      and would make this ticket a row in 100's table; give `routing` the
      trigger and the output, which is a change to a shipped Playbook and is
      ticket 101's; or route the reading to a class that already exists and fix
      the two reference pages, which is 101's alone. The ticket names the choice
      rather than making it, because each answer costs a different ticket.
- [ ] Whichever is chosen, the migration comment moves with the Playbook text.
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
