-- The two surfaces the previous file left behind                     (ticket 105)
--
-- `20261224T000000Z__the_orchestrator_asks_for_a_validation.sql` dropped
-- `report_queue` and added `propose_validation`, and `check_runtime_privileges`
-- reported both on the first `rk db migrate` after it:
--
--     integrity_failed | standing:runtime_privileges | 2 problem(s):
--       (runtime_table_surface_names_missing_object,report_queue,
--        "no such relation in public");
--       (runtime_holds_undeclared_verb,"propose_validation(text)",
--        "closed to PUBLIC and executable by rk2_runtime with no
--         runtime_verb_surface row")
--
-- Both are the same rule seen from its two ends and both are right. Ticket 66
-- made the runtime's privileges a register rather than an observation: a table
-- the runtime may touch has four rows in `runtime_table_surface` and a verb it
-- may execute has one in `runtime_verb_surface`, and the check compares the
-- register against the grants in either direction. A table that is gone leaves
-- four rows naming nothing, and a verb granted with no row is a grant nobody
-- declared.
--
-- The previous file is left as it is rather than edited, because it is applied
-- and `check_migrations` holds its digest. That is the same reason
-- `20261222T000000Z` gave for not editing `20261221T000000Z`, and it is why the
-- corpus grows a small file rather than gaining a quiet one.
--
-- Written as its own migration and not folded into the next feature, because
-- what it records is a decision: `propose_validation` is a verb the runtime may
-- execute, and `report_queue` is a table nothing may, because there is no such
-- table.

DELETE FROM runtime_table_surface WHERE table_name = 'report_queue';

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('propose_validation(text)', '105',
     'the caller of request_validation, which had none: resolves the Finding label '
     'and answers the queue row or the refusal as a document, so that one refused '
     'ask does not abort the transaction the supervisor holds open across a run')
ON CONFLICT (verb) DO NOTHING;
