-- ---------------------------------------------------------------------------
-- 20270112T000000Z__a_probe_only_class_comes_off_the_bar_it_cannot_meet.sql
--                                                                  (ticket 233)
--
-- `playbooks/http-desync` declared two Property classes and a bar neither of
-- whose `supported` rows either of them could ever meet on one of them.
-- `bb:outputs` named `transport.header_policy` and `transport.tls_configuration`;
-- `bb:evidence` asked `response_invariant` in role `control` and
-- `response_differential` in role `variant`, both `polarity: supports`. The
-- second class is `probe_only` in `transport_makeability` (`0025:204`), and
-- `transport_evidence_guard` (`0025:361-395`, `ENABLE ALWAYS`) refuses every
-- `supports` edge on a `probe_only` claim that does not cite a
-- `transport_parameters_observed` Observation. So neither bar row could be
-- INSERTED for such a claim, by any writer: `playbook_evidence_unmet` could
-- never empty and `enforce_playbook_evidence` raised on every `supported`
-- transition. Ticket 166 asked which verb could WRITE a kind and found every
-- kind reachable; it did not ask which kinds a claim's own Property class
-- admits, and this is that second question.
--
-- Which way it went, and why it is not symmetric. An evidence row is
-- `{to_status, role, kind, polarity, min_count}` and carries no Property class,
-- so one bar is read against every class the Playbook emits. Naming
-- `transport_parameters_observed` on the two `supported` roles would therefore
-- have asked for a measurement Receipt (`0025:304-308`) on the
-- `transport.header_policy` claim as well -- and that claim is an ordinary
-- agent-lane response differential, which is the whole of this Playbook's
-- executable reading. Option A repairs the half that cannot work by breaking
-- the half that does. So the class comes off `bb:outputs` instead.
--
-- What is lost, stated rather than skipped. The Playbook stops claiming the TLS
-- leaf its slug is named for. That is a smaller loss than it reads as, because
-- `0025:204` is the register saying why the claim was never sound: the agent
-- terminates TLS against the interception proxy, version and cipher matched the
-- origin by coincidence and ALPN did not. A `transport.tls_configuration`
-- Finding filed off this Playbook's reading would have described the proxy.
--
-- What it costs elsewhere, measured. `playbook_fixture_binding` (`0036:122`) is
-- derived from `playbook_outputs` against `fixture_classes`, so ticket 88's
-- `tls-configuration-pair` -- the one fixture in the corpus whose ground truth
-- is its handshake -- becomes `out` for every Playbook and grades none. It is
-- still an `out`-side fixture for all 51, so it still measures specificity,
-- and `http-desync` itself stays bound and gradeable through
-- `header-policy-pair`, which is what the second and third assertions below
-- check. Ticket 88's own purpose is not undone: it opened a binding for a
-- Playbook that had none, and ticket 101 has since given this Playbook an
-- `agent_ok` class with a fixture of its own.
--
-- What it owes. After this, no Playbook emits `transport.tls_configuration`, so
-- `tools/check_wiring.py`'s W9 reports the same gap it already reports for
-- `transport.certificate_trust`. It is owed to ticket 237 -- a Playbook step
-- that files a `transport_parameters_observed` Observation off the runtime's own
-- unintercepted measurement -- and not to ticket 116, which widens
-- `reject_non_agent_evidence` and `reject_non_agent_citation` and leaves
-- `transport_evidence_guard` alone.
--
-- The digests move because `bb:outputs` and `bb:provenance` are in the document
-- `playbooks.source_sha256` is a digest of, so `20261219T000000Z`'s pair for
-- this path is superseded here. Last write wins in apply order, which is the
-- shape `tools/check_coverage.py` reads -- the path and the digest adjacent in a
-- `VALUES` row, as `20260930T000000Z` explains at length.
--
-- A new file rather than an edit to an earlier one: a recorded migration whose
-- file has changed is schema drift and `rk db migrate` refuses the whole corpus
-- for it.
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; v_playbook uuid;
BEGIN
    SELECT id INTO v_playbook FROM playbooks
     WHERE path = 'playbooks/http-desync/playbook.md';
    IF v_playbook IS NULL THEN
        RAISE EXCEPTION 'ticket 233: the desync Playbook is not in the catalogue';
    END IF;

    DELETE FROM playbook_outputs
     WHERE playbook_id = v_playbook
       AND property_class = 'transport.tls_configuration';
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 233: removed % output row(s) and meant one', n;
    END IF;

    -- The class the Playbook keeps, and the reading it really performs.
    SELECT count(*) INTO n FROM playbook_outputs
     WHERE playbook_id = v_playbook;
    IF n <> 1 THEN
        RAISE EXCEPTION
            'ticket 233: the desync Playbook now declares % output class(es), expected one', n;
    END IF;

    -- And the fixture side of that, because the whole point of ticket 88 was a
    -- Playbook whose verdict stopped at `untested` for want of an `in`-side own
    -- pair. Deliberately the same reading as
    -- `TransportBarTest.test_the_fixture_the_removed_class_declared_now_grades_nobody`:
    -- asserted here so a corpus applied without the test suite still refuses the
    -- shape, not because there is a second reader. `playbook_test_verdict` counts own pairs on the `in` side and
    -- nothing else, so this is the assertion that says the removal did not put
    -- this Playbook back where 88 found it.
    SELECT count(*) INTO n FROM playbook_fixture_binding(v_playbook) b
     WHERE b.side = 'in' AND b.kind = 'own_pair';
    IF n <> 1 THEN
        RAISE EXCEPTION
            'ticket 233: the desync Playbook binds % own pair(s) on the in side, expected one', n;
    END IF;

    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version,
           provenance    = v.provenance
      FROM (VALUES
            ('playbooks/http-desync/playbook.md',
             'e80023c5beabddf9b8129ee5c927baa4747fe533368dc20ae92e26eb58dc6ba1',
             'aa8147bb07ad841e5fba1bfb4e51198996aba3f749c6c3f850f6ab94fffbdf74',
             'Written for ticket 56 as the v2 replacement for v1''s http-desync pack against the tls_configuration leaf 018 already named; the pack''s three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by section 4, because 025 records request framing as unmakeable and enforces that in a trigger. Rewritten for ticket 101 against the merged ledger; the one reading that executes is a header-policy reading, so bb:outputs gained transport.header_policy, the evidence rows moved off transport_parameters_observed and the roles swapped -- the repeat is the control, the sibling the variant. That move was right about the writer and wrong about the class -- on a probe_only claim transport_evidence_guard admits that kind and no other, so the tls_configuration half was unsatisfiable. Ticket 233 took transport.tls_configuration off bb:outputs instead, because one bar is read against every class a Playbook names; the reading that would support it is owed to 237.')
           ) AS v(path, source_sha256, version, provenance)
     WHERE p.path = v.path;

    -- An UPDATE that matches nothing succeeds, so the count is asserted where it
    -- is written -- `20260928T020000Z`'s reason, and `20260930T000000Z`'s.
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 233: re-froze % desync Playbook row(s) and meant one', n;
    END IF;

    -- The reading this ticket was opened on, as a query, and total over the
    -- catalogue rather than over this Playbook: the register seeds two
    -- `probe_only` classes, and a second Playbook declaring either of them would
    -- ship the same unsatisfiable bar. Zero rows is the claim.
    --
    -- Scope, stated rather than assumed: this block runs once, at this file's
    -- place in apply order, so what it guards is the corpus as of this file. A
    -- later migration that reintroduced the shape would apply afterwards and
    -- never be seen. The standing form of this invariant is W7
    -- `guard_satisfiability` -- "no guard requires a row another guard refuses"
    -- -- which `tools/check_wiring.py:303` carries as `owed:116`.
    SELECT count(*) INTO n
      FROM playbook_outputs o
      JOIN transport_makeability m ON m.property_class = o.property_class
      JOIN playbook_evidence e ON e.playbook_id = o.playbook_id
     WHERE m.makeability = 'probe_only'
       AND e.polarity = 'supports'
       AND e.observation_kind <> 'transport_parameters_observed';
    IF n <> 0 THEN
        RAISE EXCEPTION
            'ticket 233: % bar row(s) ask a probe_only class for a kind its guard refuses', n;
    END IF;
END $$;
