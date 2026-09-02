-- ---------------------------------------------------------------------------
-- 20270111T000000Z__a_declared_halt_has_a_code_to_park_under.sql
--                                                                   (ticket 216)
--
-- The six codes a parked question could be filed under all named a risk the
-- harness detected before a call: a scope it could not resolve, a method that
-- writes, a blast radius past the counterparty, a borrowed identity, the static
-- floor, an impact with no grant. None of them named the other kind of stop --
-- the one a Playbook declared for itself and then reached.
--
-- Eighty-one records in `baseline/technique-ledger.jsonl` are about that kind:
-- a declared count reached, a control that stopped answering the way the
-- reading needs, a sink proved, an arrival inside the window. Each one says the
-- operator is told through `mcp__rk2__park_for_human`, and until this row there
-- was no true code to say it under. `policy_unclear` was the near miss and it
-- is a statement about the risk floor, so eighty-one records filed under it
-- would have been eighty-one recorded falsehoods and a console showing the
-- wrong reason for every one of them.
--
-- One row and nothing else. `decision_question_codes` is a plain reference
-- table with a text primary key; `pending_decisions.question_code` and
-- `call_risk_rules.question_code` are foreign keys onto it
-- (20260814T020000Z:76-80), so a new row invalidates no existing row and fires
-- no existing rule. What a rule asks is unchanged: nothing selects this code
-- yet, and a model naming it is a model saying its own reading ran out.
-- ---------------------------------------------------------------------------

INSERT INTO decision_question_codes (question_code, meaning, asked_when, owner_ticket) VALUES
    ('playbook_halt',
     'the Playbook''s own stop condition fired and the reading stops here',
     'a halt the Playbook declared is observed by the run performing it, rather than a risk rule firing before a call',
     '216');

DO $check$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM decision_question_codes
                    WHERE question_code = 'playbook_halt') THEN
        RAISE EXCEPTION 'the declared-halt code was not seeded';
    END IF;
END $check$;
