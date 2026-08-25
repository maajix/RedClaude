-- ---------------------------------------------------------------------------
-- 20261112T000000Z__the_refusal_preview_asks_both_halves_of_the_bar.sql
--                                                        (ticket 182)
--
-- `hypothesis_transition_refusal` asks the playbook evidence bar as well as the
-- 007 rule, because both of them refuse the write it is a preview of.
--
-- What was measured. Database `rk2grade8`, 2026-08-25, canary attempt eight.
-- The first evaluation, `attack-surface` against `artifact-exposure-pair`,
-- exited 3 on:
--
--     what this replay recorded was refused: playbook
--     playbooks/attack-surface/playbook.md requires 1 x (role=control,
--     kind=response_differential) for supported, found 0
--
-- The other four evaluations then exited 9 without doing any work at all, on
-- `integrity_failed: 2 problem(s): (replay_without_run,TR4,"closed as error and
-- wrote no Test run"); (replay_left_testing,H1,"a replay of TST1 closed and the
-- claim is still testing")`. One Program that could not reach `supported` left
-- the database in a state `rk db verify` refuses, and `rk run` checks integrity
-- before every pass, so it stopped the whole campaign.
--
-- The mechanism, end to end. TR4 performed its three actions; the control leg
-- answered 404 and is on record as R6. `close_test_replay` then reached its
-- settling step, which does not attempt the transition -- it asks
-- `hypothesis_transition_refusal` first and downgrades to `inconclusive` if the
-- answer is non-NULL, exactly so that a conclusion the epistemic machine will
-- not take is still a recorded Test run. The answer was NULL, because this
-- function is the body of `enforce_hypothesis_transition` and nothing else.
-- `enforce_playbook_evidence`, a second trigger on the same insert, then raised.
-- That aborted the whole close: no `test_runs` row, `tool_runs` left `running`,
-- the claim left `testing`. `replay._abandon` re-ran the same refusing statement
-- and got the same refusal, so the row stayed open, and `resume_program` on the
-- next pass closed it as `error` -- which is the exact pair
-- `check_test_replays` names.
--
-- Why the preview was half. 0032 states the relationship outright: the playbook
-- trigger is "named to sort before enforce_hypothesis_transition ... the two
-- checks are a conjunction, so declaring min_count 1 cannot lower the" bar. A
-- preview of a conjunction has to ask both conjuncts. This one asked one, and
-- its own COMMENT is honest about which: "why 007 would refuse this hypothesis
-- transition".
--
-- What this does not change. The bar itself, the trigger, the Playbook rows and
-- the sentence a refusal is phrased in are all untouched: the arm added here
-- calls `playbook_evidence_unmet`, which is what the trigger calls, and formats
-- the string the trigger formats. A transition that was admitted before is
-- admitted now; what changes is that one which would have been raised on is now
-- reported, so `close_test_replay` can do what it was already written to do
-- with the answer.
--
-- Nor does it change what `attack-surface` scored. A replay whose control leg
-- produced no `response_differential` still cannot settle a claim as
-- `supported`. After this it settles `inconclusive`, says why in the
-- transition's rationale, writes its Test run, and the campaign continues.
--
-- The function is otherwise the text 20260815T000000Z shipped, replaced whole
-- because that is how a plpgsql body is amended.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION hypothesis_transition_refusal(
        p_hypothesis uuid,
        p_from       text,
        p_to         text,
        p_actor_kind text,
        p_receipt    uuid,
        p_agent_run  uuid)
RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE
    r         transition_rules%ROWTYPE;
    n_support integer;
    n_control integer;
    lane      text;
    v_profile text;
    v_ok      boolean;
    v_unmet   record;
BEGIN
    -- Ticket 182. The playbook bar, asked here because it is enforced there.
    -- `enforce_playbook_evidence` (0032) is a second trigger on the same insert,
    -- named to sort before `enforce_hypothesis_transition` so that the stricter
    -- rule refuses before the base rule has applied its UPDATE, and 0032 calls
    -- the two "a conjunction". This function was written as the body of the base
    -- trigger alone -- its own comment says "why 007 would refuse" -- so it
    -- answered one half of that conjunction and admitted transitions the other
    -- half raises on.
    --
    -- What that cost. `close_test_replay` asks this function rather than
    -- attempting the transition, and says why in its own comment: "Asked, not
    -- attempted. What comes back is a verdict about the conclusion and not an
    -- error in this transaction, and the run settles for what it can still say."
    -- A NULL here that the trigger then refused turned that downgrade into a
    -- raise. The whole close rolled back, so the Tool run stayed `running` with
    -- its Test run unwritten and the claim still `testing`; the next pass's
    -- reconciliation closed the abandoned run as `error`. `check_test_replays`
    -- reports that pair as `replay_without_run` and `replay_left_testing`, and
    -- `rk run` refuses every later pass on a failed integrity check -- so one
    -- Program that could not reach `supported` stopped every Program in the
    -- database.
    --
    -- First in the body, because the trigger that owns it fires first: this is
    -- the sentence a writer would actually be given, in the words it would be
    -- given it in.
    SELECT * INTO v_unmet FROM playbook_evidence_unmet(p_hypothesis, p_to) LIMIT 1;
    IF FOUND THEN
        RETURN format('playbook %s requires %s x (role=%s, kind=%s) for %s, found %s',
            v_unmet.path, v_unmet.need, v_unmet.req_role, v_unmet.req_kind,
            p_to, v_unmet.have);
    END IF;

    SELECT * INTO r FROM transition_rules
     WHERE machine = 'hypothesis'
       AND from_status = p_from
       AND to_status = p_to;
    IF NOT FOUND THEN
        RETURN format('illegal transition %s -> %s', p_from, p_to);
    END IF;

    IF r.required_actor_kind IS NOT NULL AND p_actor_kind <> r.required_actor_kind THEN
        RETURN format('transition %s -> %s requires actor_kind %s, got %s',
            p_from, p_to, r.required_actor_kind, p_actor_kind);
    END IF;

    IF r.requires_receipt AND p_receipt IS NULL THEN
        RETURN format('transition %s -> %s requires a tool receipt', p_from, p_to);
    END IF;

    -- D7 / C23: decision 15 applied to transitions, not only to observations.
    -- The proxy fetching its own CSRF token is not evidence of anything.
    IF p_receipt IS NOT NULL THEN
        SELECT receipts.lane INTO lane FROM receipts WHERE id = p_receipt;
        IF lane = 'proxy_internal' THEN
            RETURN format(
                'receipt %s is lane proxy_internal and cannot back a transition',
                p_receipt);
        END IF;
    END IF;

    -- The stronger form: the cited receipt must be one this hypothesis's test run
    -- produced, so a conclusion cannot rest on an unrelated request that happened
    -- to be receipted.
    IF r.requires_test_linked_receipt AND NOT EXISTS (
            SELECT 1
              FROM test_run_receipts trr
              JOIN test_runs tr ON tr.id = trr.test_run_id
              JOIN tests te     ON te.id = tr.test_id
             WHERE trr.receipt_id = p_receipt
               AND te.hypothesis_id = p_hypothesis) THEN
        RETURN format(
            'transition %s -> %s must cite a receipt produced by a test run of hypothesis %s',
            p_from, p_to, p_hypothesis);
    END IF;

    SELECT count(*) FILTER (WHERE role IN ('baseline','variant')),
           count(*) FILTER (WHERE role = 'control')
      INTO n_support, n_control
      FROM hypothesis_evidence WHERE hypothesis_id = p_hypothesis;

    IF n_support < r.min_supporting_evidence THEN
        RETURN format('transition %s -> %s needs %s evidence rows, found %s',
            p_from, p_to, r.min_supporting_evidence, n_support);
    END IF;
    IF n_control < r.min_control_evidence THEN
        RETURN format('transition %s -> %s needs a control observation', p_from, p_to);
    END IF;

    -- Ticket 09: a skill may be stricter than the default, never looser. The
    -- profile arrives on the task row from the PreToolUse hook. A transition with
    -- no agent run is not attributable to a skill and gets the default.
    IF r.consults_evidence_profile AND p_agent_run IS NOT NULL THEN
        SELECT tk.evidence_profile_id INTO v_profile
          FROM agent_runs ar JOIN tasks tk ON tk.id = ar.task_id
         WHERE ar.id = p_agent_run;
        IF v_profile IS NOT NULL THEN
            EXECUTE format('SELECT %I($1)', 'evidence_profile_' || v_profile)
               INTO v_ok USING p_hypothesis;
            IF NOT coalesce(v_ok, false) THEN
                RETURN format('evidence profile %s is not satisfied for hypothesis %s',
                    v_profile, p_hypothesis);
            END IF;
        END IF;
    END IF;

    RETURN NULL;
END $fn$;
