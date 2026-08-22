# 145 — An observation kind that takes only a tool run is offered a receipt

**What to build:** The part of the `observations` element shape that stops a run
citing a Receipt for a kind whose `allowed_provenance` is `{tool_run}` alone, or
the recorded decision that this stays a promotion-time refusal.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **The measurement is in the ticket.** `rk2hunt6`, 2026-08-22: two of
      fifteen drops are `incompatible_provenance` citing `content_match`. Both
      elements were well formed and named a real Receipt:

      ```json
      {"ref": "o_content", "kind": "content_match", "receipt_label": "R3",
       "subject_label": "APP2", "statement": "The page embeds a schema.org ..."}
      ```

      `observation_kinds` says `content_match|{tool_run}`. A Receipt is a
      request and its answer; a content match is a claim about what was found
      inside a body, which the schema holds is a tool's reading and not the
      request's own record.

- [ ] **The choice is made rather than assumed.** JSON Schema cannot express
      "if `kind` is `content_match` then `receipt_label` is forbidden" in the
      one-level element shape the roster renders, so the honest options are two:
      split the argument so that kinds taking a tool run are a separate list, or
      leave it as a promotion refusal and make the refusal say what to cite
      instead. The second is cheap and is what the drop already almost does.

- [ ] **Checked by something that would go red.** Whichever is chosen,
      `VocabularyAgreementTest` should fail if `observation_kinds`'
      `allowed_provenance` ever disagrees with what the roster tells a run.

## Why

Small, and deliberately filed apart from 144. Thirteen of `rk2hunt6`'s fifteen
drops are the rationale shape and two are this. It costs a Program two
Observations per run and stops nothing: it is the kind of residue worth knowing
about rather than the kind worth blocking a hunt on.
