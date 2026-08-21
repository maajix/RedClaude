# 113 — Open redirection is routed to a class, a trigger and a Playbook that do not line up

**What to build:** A decision about where open-redirect work goes, and the
repair of three separate misroutings that a reader of the corpus meets as one
sentence.

**Blocked by:** nothing.

**Status:** needs-triage

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
