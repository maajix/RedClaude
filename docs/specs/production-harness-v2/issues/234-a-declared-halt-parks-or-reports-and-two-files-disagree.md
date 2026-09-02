# 234 — A declared halt parks or reports, and two files disagree

**What to build:** One decision, written once and then applied to both places
that state it: when a Playbook reaches a halt it declared for itself, does the
run park the Task for a person, or finish it with a report? The ledger says one
and the corpus says the other, and ticket 216 removed the reason the corpus gave
for choosing.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Measured on 2026-09-02, while landing ticket 216:

```
baseline/technique-ledger.jsonl
  records whose stop_conditions name park_for_human       81   (of 378)
  ... all of them in field 5, `who is told`
src/redkraken/playbooks/
  Playbooks saying a declared halt goes to the Task's own
  record because none of the five codes says it            9
```

The nine say it in these words, quoted from
`src/redkraken/playbooks/authentication/playbook.md:168`:

```
Every other halt is a reading that ran out -- a declared count reached, a
credential burnt, a lockout or a 429 arriving mid-sequence -- and none of the
five codes says that, so those are reported through the Task's own record.
```

Ticket 216 seeded `playbook_halt`, which does say that. So the premise those
nine sentences rest on is gone, and the routing they chose is now a choice
rather than a workaround.

## Why it is not obvious

The two endings are not variations on one behaviour. A park stops the Task and
waits for an operator; a report finishes it. For a halt like `command-directory-injection/08`
-- "a command sink has been proved" -- parking stalls a Task that has something
to file, and for a halt like `exceptional-conditions/01` -- "any answer returns
a record the reading did not create" -- reporting hands back a Task nobody was
asked about. It is plausible that the right answer is neither one for all
eighty-one, in which case the deliverable is the rule that sorts them.

## Acceptance criteria

- [ ] **The rule is written where a reader finds it.** One statement, in the
      corpus's own vocabulary, of which halts park and which report.
- [ ] **The eighty-one records agree with it.** Each record's `who is told`
      field says the ending the rule gives it, and `tools/check_intake.py`
      grades that rather than only the presence of a code.
- [ ] **The nine Playbooks agree with it.** No shipped Playbook states a reason
      that no longer holds, and none counts the question codes.
