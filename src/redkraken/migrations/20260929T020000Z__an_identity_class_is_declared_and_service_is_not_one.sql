-- ---------------------------------------------------------------------------
-- 20260929T020000Z__an_identity_class_is_declared_and_service_is_not_one.sql
--                                                                  (ticket 112)
--
-- `identities.class` has been closed to four values since 0003 and reachable at
-- two of them. Every `INSERT INTO identities` in the tree writes a literal:
-- `_project_identities` wrote `'user'`, `rk2_anonymous_identity` and
-- `promote_proposal` write `'anonymous'`, and there is no `UPDATE identities SET
-- class` anywhere. So `privileged` had no writer and `service` had neither a
-- writer nor a reader.
--
-- The cost of the first is a surface fact whose predicate nothing could
-- satisfy. `privileged_identity_available` is registered at
-- `0032_playbooks.sql:79` and has had a `subject_facts` branch in all nine
-- migrations that rebuilt the view; the live branch (`20260904T000000Z...:216`)
-- tests `identities.class = 'privileged'`. It is harmless today only because no
-- Playbook lists it as a trigger, and that is a trap rather than a rescue: the
-- first Playbook that does becomes silently unselectable forever, and the
-- `fact_not_computed` gate will not say so, because it proves the view mentions
-- the fact and not that the predicate can hold.
--
-- THE CLASS COMES FROM CONFIGURATION, BECAUSE NOTHING ELSE CAN PRODUCE IT.
--
-- The fact that decides this is a CHECK rather than a missing function.
-- `0003_entities.sql:111` says `CHECK (class = 'anonymous' OR secret_ref IS NOT
-- NULL)`, so any row that is ever `privileged` must carry a `secret_ref`, and
-- the only writer of `secret_ref` in this tree is `_project_identities`
-- (`src/redkraken/program.py`), which takes it from
-- `configuration.document["identity"]`. The set of rows that could ever be
-- privileged is therefore exactly the set configuration creates, and "a writer
-- for privileged" can only mean "the operator's file says so".
--
-- A runtime writer is not merely unbuilt; the grants forbid it. The state
-- role's SELECT on `identities` is a column grant that deliberately omits
-- `secret_ref` (`0020_state_access.sql:217-221`, "`identities` minus one
-- column. Not a view, not a redaction: a grant, checked by the executor on
-- every query"), and that connection holds no write privilege on the table at
-- all. A runtime path that promoted an Identity would have to produce a
-- `secret_ref` for a row through a connection that cannot read the column.
--
-- And privilege is not observable in the first place. Whether a credential is
-- an administrator's is a fact about how the operator provisioned the account,
-- not a property of any response the harness can fetch. A Playbook that
-- inferred it from "this session sees an admin panel" would be writing a guess
-- into a closed vocabulary that other Playbooks' triggers read as ground truth.
-- The configuration document is where facts the runtime cannot discover already
-- live: `rules_of_engagement` is the precedent, and the `identity` entry
-- already carries exactly one such fact per entry in `slot_ref`.
--
-- WHAT AN OPERATOR WHO WROTE `class = "service"` IS TOLD.
--
-- Nothing, because nobody can have. `service` was never a configuration key and
-- never a value any writer produced, so no document in the world names it and
-- no row in any database carries it; section 1 proves the second half rather
-- than asserting it. What the word did have is a collision: `entities.type =
-- 'service'` is a port on a host (`0003_entities.sql:10`, `:48`), which is what
-- every other use of the string in this tree means
-- (`0015_epistemic_corrections.sql:45`, `20260813T090000Z...:164`). An Identity
-- class spelled like an Entity type is a collision a vocabulary should not
-- keep, and a value that is inert is a state a closed vocabulary should have to
-- declare rather than reach by silence. An operator who wants a machine account
-- in scope declares it as an `identity` entry like any other and classes it
-- `user` or `privileged` by what it can reach, which is the question a Playbook
-- asks; "it is not a person" is not.
--
-- `anonymous` is untouched and is a different state, checked in passing:
-- `rk2_anonymous_identity` and `promote_proposal` both write it, so
-- `anonymous_identity_available` (`0032_playbooks.sql:80`) is genuinely
-- computable and genuinely listed by no Playbook.
--
-- Depends on 0003 (the column and both CHECKs) and 20260904T000000Z (the branch
-- whose predicate section 3 asserts). A new file rather than an edit to either:
-- a recorded migration whose file has changed is schema drift and `rk db
-- migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. What is recorded, before the set is narrowed over it
-- ===========================================================================

-- No writer can have produced one, which is the ticket's finding and not a
-- guarantee about somebody's database: a hand-written repair, a restored dump
-- from a tree that had one, or a fixture would all land here. A row outside the
-- three cannot be repaired from this file -- which class was meant is a fact
-- about a credential nobody here can see -- so this refuses with a sentence
-- naming what it found rather than leaving PostgreSQL to refuse the `ALTER`
-- below with a message about one row and no instruction.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM identities WHERE class = 'service';
    IF n > 0 THEN
        RAISE EXCEPTION '% identity row(s) carry the retired class ''service''', n
          USING DETAIL = 'nothing in this tree ever wrote that value and nothing '
                         'ever read it; reclass each row as user or privileged by '
                         'what the credential can reach, and apply this migration '
                         'again',
                ERRCODE = '23514';
    END IF;
END $$;


-- ===========================================================================
-- 2. Three classes, and the reason each one is reachable
-- ===========================================================================

ALTER TABLE identities DROP CONSTRAINT identities_class_check;
ALTER TABLE identities ADD CONSTRAINT identities_class_check
    CHECK (class IN ('anonymous', 'user', 'privileged'));

-- The rule where a reader of the live schema meets it, which a `--` comment in
-- a migration file is not. Each of the three is named with the writer that
-- produces it, because the defect this file closes was a value in this list
-- that had none, and a reader who cannot see the writers cannot see it coming.
COMMENT ON COLUMN identities.class IS
 'What the operator provisioned this slot as, closed to three values. `anonymous` is what the runtime mints for a slot nobody provisioned -- rk2_anonymous_identity and promote_proposal write it, and the paired CHECK admits it with no secret_ref. `user` and `privileged` both carry material and both come from the configuration document: _project_identities is the only writer of secret_ref in the tree, so the set of rows that can be anything but anonymous is exactly the set the operator declared. Privilege is not discoverable -- whether a credential is an administrator''s is a fact about provisioning rather than about any response -- so there is deliberately no runtime path that promotes a row, and the state role''s column grant, which omits secret_ref, would refuse to be one. `service` was retired here: it had no writer, no reader and no subject_facts branch, and the word already means a port on a host two tables away.';


-- ===========================================================================
-- 3. The predicate that could not hold, holding
-- ===========================================================================

-- The claim is not that the column admits `privileged` -- it always did -- but
-- that a row written the way `_project_identities` now writes one satisfies the
-- expression `subject_facts` reads. That expression is copied out of the live
-- view body (`20260904T000000Z...:216-219`) rather than referenced, because the
-- fact row itself is per in-scope Endpoint and building one would mean a scope
-- version, an Application, an Endpoint and a projection -- a Surface fixture
-- that would assert the parts of the view this file did not change.
--
-- Written and then rolled back, because it is an assertion and not state: the
-- inner block is a subtransaction, the sentinel at the bottom unwinds every
-- write, and a real refusal carries a different SQLSTATE and leaves.
DO $$
DECLARE v_program uuid; v_entity uuid; v_holds boolean; v_refused boolean;
BEGIN
    BEGIN
        INSERT INTO programs (slug, name)
        VALUES ('ticket-112-proof', 'ticket 112 proof')
        RETURNING id INTO v_program;

        -- The two statements `_project_identities` issues for a new label, in
        -- the order it issues them and with the class it now takes from the
        -- `identity` entry rather than from a literal.
        INSERT INTO entities (program_id, type, dedup_key, metadata)
        VALUES (v_program, 'identity', 'configured-identity:root',
                jsonb_build_object('source', 'program_configuration',
                                   'configuration_revision', 1))
        RETURNING id INTO v_entity;
        INSERT INTO identities (entity_id, slot_name, class, secret_ref)
        VALUES (v_entity, 'root', 'privileged', 'slot://identity/root');

        SELECT EXISTS (SELECT 1 FROM entities ie JOIN identities i ON i.entity_id = ie.id
                        WHERE ie.program_id = v_program AND i.class = 'privileged'
                          AND i.invalidated_at IS NULL)
          INTO v_holds;
        IF NOT v_holds THEN
            RAISE EXCEPTION
                'ticket 112: privileged_identity_available still reads false for a '
                'program whose configuration declared a privileged slot';
        END IF;

        -- And the retired value, refused at the column rather than ignored by
        -- every reader, which is the difference this file is making.
        BEGIN
            UPDATE identities SET class = 'service' WHERE entity_id = v_entity;
            v_refused := false;
        EXCEPTION WHEN check_violation THEN
            v_refused := true;
        END;
        IF NOT v_refused THEN
            RAISE EXCEPTION 'ticket 112: the column still admits the retired class ''service''';
        END IF;

        RAISE EXCEPTION 'ticket 112 proof' USING ERRCODE = 'RK112';
    EXCEPTION WHEN SQLSTATE 'RK112' THEN
        NULL;
    END;
END $$;
