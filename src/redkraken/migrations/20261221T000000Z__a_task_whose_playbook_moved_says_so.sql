-- ---------------------------------------------------------------------------
-- A Task whose Playbook moved says so                                (ticket 218)
--
-- Ticket 101 rewrote all fifty Playbooks, so every `source_sha256` in the
-- corpus moved at once. `execution.py:2800-2812` then refuses any Task holding
-- a selection frozen at a digest this installation no longer carries, and it is
-- right to: the record "would describe something other than what the model
-- read, and a grading run against it would be reading the wrong document"
-- (`execution.py:2775-2779`).
--
-- What happened next was measured on the here.com engagement rather than
-- assumed. The queue drained itself, because a corpus refusal counts as an
-- attempt and `cancel_reason_for` retires a Task at `max_attempts`. One pass,
-- counters read either side:
--
--     before: 14 stranded Tasks, attempts summing to 15
--     after:  13 stranded, summing to 13, T732 abandoned attempts_exhausted
--
-- Three things were wrong with that, and this migration fixes the first two.
--
-- One: the reason is a lie. The Task did not exhaust its attempts on the work,
-- it was never allowed to start. An operator reading `attempts_exhausted` on
-- thirteen Tasks reads three failed tries each, which is not what happened.
--
-- Two: it costs a full `rk run` per attempt -- twenty-four passes for twelve
-- Tasks when this was measured -- and every one of them opens the Program,
-- ranks the queue, claims a Task and refuses. The ranking pass already holds
-- both digests. It can answer in the pass it was making anyway.
--
-- Three is `hunt.sh` stopping after three non-zero laps in a row, which every
-- corpus refusal is. That one is the engagement's to fix, and its `STRANDED`
-- counter comes out when this lands.
--
-- The new reason goes BEFORE `attempts_exhausted`, not after. A stranded Task
-- that has also reached three attempts should still carry the reason that
-- binds: its Playbook is gone, and no number of further attempts would have
-- changed that.
--
-- Only selections with `dropped_because IS NULL` are read, because those are
-- the rows `SELECTED` (`execution.py:389-394`) hands to the model. A Task whose
-- every selection was already discarded is not refused by `_perform` -- `kept`
-- comes back empty and nothing is compared -- so cancelling it here would end
-- work the harness was willing to do.
--
-- `abandoned_reason` is free text: `0026_human_control.sql:449` dropped the
-- enum constraint, for the reason it states there -- the vocabulary could not
-- tell a human "no" from a human running out of time. So a new word costs no
-- migration to a type.

CREATE OR REPLACE FUNCTION cancel_reason_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean; st text; fired boolean; left_ bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = t.program_id AND p.closed_at IS NOT NULL) THEN
        RETURN 'program_closed';
    END IF;

    SELECT b.tokens_left INTO left_ FROM program_budget b WHERE b.program_id = t.program_id;
    IF left_ IS NOT NULL AND left_ <= 0 THEN RETURN 'budget_exhausted'; END IF;

    -- Ticket 218, and before the attempt counter on purpose. The pair this
    -- compares is the pair `execution.py:2802` compares: the digest and the
    -- projection version the selection froze, against what the catalogue
    -- carries now. Both, because that line refuses on either, and a version
    -- that moved with the digest unchanged is the same document under a
    -- projection the model would read differently.
    IF EXISTS (
        SELECT 1
          FROM playbook_selections s
          JOIN playbooks pb ON pb.id = s.playbook_id
         WHERE s.task_id = t.id
           AND s.dropped_because IS NULL
           AND (pb.source_sha256 IS DISTINCT FROM s.playbook_sha256
                OR pb.version IS DISTINCT FROM s.playbook_version)
    ) THEN
        RETURN 'corpus_moved';
    END IF;

    IF t.attempts >= w.max_attempts THEN RETURN 'attempts_exhausted'; END IF;

    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 'out_of_scope'; END IF;
    END IF;

    IF t.hypothesis_id IS NOT NULL THEN
        SELECT h.status, h.superseded_by IS NOT NULL INTO st, ok
          FROM hypotheses h WHERE h.id = t.hypothesis_id;
        IF ok THEN RETURN 'superseded'; END IF;
        -- 034: a refutation suppresses equivalent work only while it is still
        -- current AND something on file settles it. An imported negative is
        -- neither, and `refresh_negative_knowledge` reopens the claim in step
        -- (1) of the same pass that reaches this check in step (2), so the
        -- suppression it would otherwise inherit never survives a pass.
        IF st = 'refuted'
           AND rk2_negative_standing(rk2_current_negative(t.hypothesis_id)) = 'settled' THEN
            RETURN 'settled_negative';
        END IF;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        -- Ticket 156's one exception, written as what it is rather than as a
        -- kind list: a settled claim answers the work that was asking whether
        -- it holds, and `conclude` is not that work -- it is the work that
        -- writes down what the answer was. Only `supported`, because a refuted
        -- claim answers a conclusion too.
        IF st IN ('supported','refuted') AND NOT fired
           AND NOT (t.kind = 'conclude' AND st = 'supported') THEN
            RETURN 'answered';
        END IF;
        -- a candidate that stage 2 suppressed leaves the hypothesis gone
        IF st IS NULL THEN RETURN 'near_duplicate'; END IF;
    END IF;

    IF t.kind = 'validate' AND EXISTS (
         SELECT 1 FROM findings f WHERE f.id = t.finding_id
           AND f.status IN ('validated','reported','rejected')) THEN
        RETURN 'answered';
    END IF;

    -- The general rule, last: nothing left to learn is nothing worth running.
    --
    -- Except for `report`, and the exception is not a special case -- it is the
    -- one kind whose novelty is a function of rows that have not arrived yet.
    -- `novelty_for('report')` is 1 exactly when an unreported validated finding
    -- exists, so a report task in a young program scores 0, and without this
    -- guard `rank_pass` would abandon it as `answered` on the first pass and
    -- the program would validate findings with no report task left alive. The
    -- admission matrix found this: the fixture happened to validate FG20 before
    -- the first pass, which hid it. Nothing to report yet is unready, not
    -- answered, and `ready_for` already says so.
    IF t.kind <> 'report' AND novelty_for(t) = 0 THEN RETURN 'answered'; END IF;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION cancel_reason_for(tasks, scheduler_weights) IS
  'Why a pending Task should not be ranked, or NULL to rank it. `corpus_moved` (ticket 218) is read before the attempt counter: a Task whose active Playbook selection froze a digest or projection version the catalogue no longer carries was never allowed to start, so retiring it as `attempts_exhausted` three passes later names the wrong fact and spends three passes doing it.';
