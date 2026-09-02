# 234 — A declared halt parks or reports, and two files disagree

**What to build:** One decision, written once and then applied to both places
that state it: when a Playbook reaches a halt it declared for itself, does the
run park the Task for a person, or finish it with a report? The ledger says one
and the corpus says the other, and ticket 216 removed the reason the corpus gave
for choosing.

**Blocked by:** nothing.

**Status:** ready-for-agent

**PRODUCES:** changed contract -- the rule that decides, for a declared halt,
whether the run parks the Task or finishes it with a report, stated once and
then applied to both files that state it.

**CONSUMED BY:** `tools/check_intake.py::record_error`, reading the
`who is told` field of `stop_conditions`; the thirty-one shipped `playbook.md`
halt paragraphs that today give a reason ticket 216 made stale; an Agent at a
declared halt, via the `question_code` enum served by
`roster.py::CONTRACTS["mcp__rk2__park_for_human"]`.

**CONSUMES:** the `decision_question_codes` row `playbook_halt`
(`20270111T000000Z:28-32`, written by 216), `baseline/technique-ledger.jsonl`
(81 records), `src/redkraken/playbooks/*/playbook.md` (31 files).

**Touches:** `baseline/technique-ledger.jsonl`, `tools/check_intake.py`,
`src/redkraken/playbooks/*/playbook.md`.


## What was measured

Measured on 2026-09-02, while landing ticket 216:

```
baseline/technique-ledger.jsonl
  records whose stop_conditions name park_for_human       81   (of 378)
  ... all of them in field 5, `who is told`
src/redkraken/playbooks/
  Playbooks counting the codes at five                    10  (11 sentences)
  Playbooks asserting no served code says a reading ran
  out, without counting them                              21
  union, whose stated premise ticket 216 falsified        31  (of 51)
```

Ten count the codes, in these words, quoted from
`src/redkraken/playbooks/authentication/playbook.md:168`:

```
Every other halt is a reading that ran out -- a declared count reached, a
credential burnt, a lockout or a 429 arriving mid-sequence -- and none of the
five codes says that, so those are reported through the Task's own record.
```

Twenty-one more do not count the codes but deny that any of them says this, as
in `src/redkraken/playbooks/deployment/playbook.md`: "because no question code
in the served set says a reading ran out of tells".

Ticket 216 seeded `playbook_halt`, whose `meaning` is "the Playbook's own stop
condition fired and the reading stops here" and whose migration comment says a
model naming it "is a model saying its own reading ran out" -- which is word for
word what those twenty-one deny. So the premise all thirty-one rest on is gone,
and the routing they chose is now a choice rather than a workaround. The count
of nine this ticket was cut with was measured by a single-line grep; two of the
thirty-one wrap the phrase across a newline and twenty-one never use the word
"five" at all.

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
- [ ] **The thirty-one Playbooks agree with it.** No shipped Playbook states a
      reason that no longer holds, and none counts the question codes. The
      thirty-one are `api`, `api-authorization`, `agentic-ai`, `attack-surface`,
      `authentication`, `browser-messaging`, `command-directory-injection`,
      `cookies`, `deployment`, `deserialization`, `graphql`, `grpc`,
      `identity-parsing`, `information-disclosure`, `jwt-jose`, `kubernetes`,
      `logging`, `nosql-injection`, `oauth`, `orm`, `realtime`,
      `request-integrity`, `request-parsing`, `routing`, `secrets`,
      `spreadsheet-injection`, `ssti`, `structured-injection`, `web-cache`,
      `webauthn`, `webhooks`.
- [ ] **The codes are read off the contract, not restated.** `roster.py`
      publishes `QUESTION_CODES` beside `PARK_FOR_HUMAN` the way
      `RUN_TOOL_NAMES` is published at `roster.py:2099`, and
      `tools/check_intake.py` and `src/redkraken/_launch.py` read that rather
      than each spelling out
      `CONTRACTS[PARK_FOR_HUMAN].arguments["question_code"].enum`. Added by
      ticket 216's review, cycle 1.
