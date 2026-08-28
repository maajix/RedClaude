# 216 — A Playbook halt has no question code to park under

**What to build:** A question code that means "a Playbook reached a halt it
declared, and the reading stops here", so that a step which tells the operator
why it stopped can park under the reason it actually has.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Found while landing ticket 101's step 3, and measured over the whole corpus
ledger rather than over a sample:

```
baseline/technique-ledger.jsonl
  records naming park_for_human in stop_conditions      81   (of 378)
  playbooks those records belong to                     16   (of 50)
  records naming any of the six question codes           0
src/redkraken/playbooks/
  shipped Playbooks naming park_for_human today          0
```

The harness files a parked question under one of six codes. Five were inserted
by `20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:62-72` and
the sixth by
`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:444-448`:

| code | what it means |
| --- | --- |
| `scope_ambiguous` | the request addresses something the scope document does not clearly admit |
| `destructive_action` | the request may change state at the target rather than read it |
| `third_party_impact` | the request may reach or affect somebody who is not the Program's counterparty |
| `credential_needed` | the request would be made under a borrowed identity |
| `policy_unclear` | the static floor asks, and no rule named a better reason |
| `impact_unauthorized` | a validated Finding has an impact Test, and no live operator grant covers it |

All six describe a **risk the harness detected before a call**. None describes a
**halt the Playbook itself declared**, which is what the eighty-one records are
about. Their halt triggers are readings that ran out: a declared count reached,
a control that did not answer the way the reading needs it to, an arrival inside
the window, a Finding confirmed and worth reporting. Three examples, quoted from
the ledger:

```
exceptional-conditions/01  the declared count is reached, or any answer returns
                           a record the reading did not create
grpc/02                    the first call answers about the connection rather
                           than about the method
command-directory-injection/08
                           a command sink has been proved
```

## Where the mechanism is

`park_task_for_human`
(`src/redkraken/migrations/20261028T000000Z__a_model_asks_to_be_parked_and_the_task_waits.sql:362`)
refuses at `:407-414` when the code is not a row in `decision_question_codes`,
and hands back the whole list so the caller can see what it may say.

The model-facing surface is narrower than the table. `roster.py:1771-1775`
declares the argument's `enum` with **five** members -- `impact_unauthorized` is
the runtime's own, not something an Agent may claim -- and `_launch.py:1282`
tells the model in prose that there are "five question codes". So the vocabulary
a Playbook step can reach is those five, and the closest of them is
`policy_unclear`, which is a statement about the risk floor and not about the
reading.

## Why it is worth a ticket rather than a note

Nothing is broken today: no shipped Playbook names `park_for_human`, so nothing
is currently picking a wrong code. The gap arrives with ticket 101, whose steps
4 and 5 regenerate the corpus from this ledger. At that point sixteen Playbooks
carry halt prose telling the Agent to park, the Agent must pick one of five
codes, and none of them is true. What lands in `pending_decisions` is then a
halt filed under "the static floor asked", and an operator console keyed on the
code shows the wrong reason for every one of them.

The cheap wrong fix is to write `policy_unclear` into all eighty-one ledger
records. That is eighty-one recorded falsehoods, and it makes the real code
harder to add later because something would then have to find and unpick them.

## What it costs

Priced rather than assumed, by reading each end:

- **One migration.** `decision_question_codes` is a plain table with a text
  primary key. `pending_decisions.question_code` and
  `call_risk_rules.question_code` are foreign keys onto it
  (`20260814T020000Z:76-80`), so a new row breaks no existing row and no
  existing rule.
- **Two lines in the package.** The `enum` at `roster.py:1771-1775` gains the
  sixth member, and the prose at `_launch.py:1282` stops saying "five".
- **The ledger, mechanically.** All eighty-one records name the same halt, so
  the code goes in with one pass and no per-record judgement.

Ticket 101 does not do this: it is a corpus rewrite, and this is a change to the
vocabulary the tool surface offers. Capability before catalogue -- the code
lands before the sixteen Playbooks that would use it.

## Acceptance criteria

- [ ] **A code exists for a declared halt.** One row in
      `decision_question_codes`, whose `meaning` and `asked_when` say that the
      Playbook's own stop condition fired, rather than that a risk rule did.
- [ ] **A model may name it.** It is in the `enum` at `roster.py:1771-1775` and
      in the tool's description, which no longer says there are five.
- [ ] **The refusal still refuses.** A code outside the table is still turned
      away by `park_task_for_human` with the list attached, proved by a test
      that names a code this harness does not file under.
- [ ] **The eighty-one records carry it.** `baseline/technique-ledger.jsonl` is
      updated in the same change, and `tools/check_intake.py` refuses a record
      whose `stop_conditions` name `park_for_human` without naming a code.

## What this does not change

`impact_unauthorized` stays out of the model-facing `enum`. It is the runtime's
own question about a grant it went looking for, and a model that could claim it
could ask for an impact replay by asking to be parked.
