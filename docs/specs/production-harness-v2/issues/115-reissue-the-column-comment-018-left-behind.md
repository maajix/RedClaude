# 115 — Re-issue the column comment migration 018 left behind

**What to build:** One `COMMENT ON COLUMN`, replacing a live piece of schema
documentation that a later migration made false.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The comment is replaced.
      `COMMENT ON COLUMN observation_kinds.allowed_provenance`, set at
      `0018_vocabularies.sql:269-270`, ends "see the out_of_band_interaction
      note in migration 018". That note (`0018_vocabularies.sql:251-267`) says
      the kind was rejected because its provenance set would be empty, and that
      "It goes back in when the collector that generates its provenance exists:
      a third `provenance_kind` ('oob_receipt') written by a runtime-controlled
      listener."
- [ ] What actually shipped is named in the replacement.
      `20260812T040000Z__a_callback_arrives_on_a_declared_channel.sql:336-341`
      dropped and re-added `observation_kinds_allowed_provenance_closed` to
      admit `'callback'`, and `:348-350` inserted `callback_interaction` with
      `allowed_provenance` of `{callback}`. The provenance kind that shipped is
      `callback`, not `oob_receipt`; the kind is live, is cited by the
      `webhooks` Playbook, and is written by `resolve_callback_arrival`. The
      comment sends a reader to a rejection that no longer holds.
- [ ] The `--` comment inside 018 is left alone and the replacement says so. A
      comment inside a recorded migration cannot be edited, and the house
      standard for this is already set: `20260922T060000Z__a_fixture_may_own_its_own_handshake.sql:100-104`
      re-issues a `COMMENT ON COLUMN` it invalidated and states the reason --
      "The original is a `--` comment inside a recorded migration file, which
      cannot be edited."
- [ ] The distinction that makes this worth a ticket is stated: a `--` comment
      in a migration is at least dated, and a live `COMMENT ON` presents as
      current schema documentation to anybody running `\d+ observation_kinds`.
      This is the second kind.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 6 grades this "stale, and
worse than the file comment", and its gate G8 is the mechanical rule that would
have caught it: a migration that changes a constraint, a default or a closed set
on a column must re-issue `COMMENT ON` for that column in the same file.
`20260812T040000Z` moved the constraint and left the comment.

Ticket 130 is where the rule goes. This ticket is the one instance it would
report today, fixed by hand so the gate lands green.
