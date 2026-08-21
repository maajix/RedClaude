# 110 — Serve the vocabulary out of the tables that declare it

**What to build:** A caller for `mcp_enum`, `mcp_enum_described` and
`mcp_transport_makeability`, so that the closed sets a tool schema publishes and
the closed sets the foreign keys enforce are one statement rather than two.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The three functions acquire a caller. `mcp_enum` is at
      `src/redkraken/migrations/0018_vocabularies.sql:530`,
      `mcp_enum_described` at `:546` and `mcp_transport_makeability` at
      `0025_transport_claims.sql:674`. `grep -rn "mcp_enum\|mcp_transport_makeability"
      src/redkraken/*.py tests/ tools/` returns nothing. They have zero callers
      anywhere outside the migrations that created them.
- [ ] The schema comment that claims otherwise stops being false.
      `0018_vocabularies.sql:528-529` says "`mcp_enum()` is what the MCP server
      calls at startup to build the schema, so the enum cannot drift from the
      FK." It is not, and the comment is one of the two things this ticket
      repairs.
- [ ] The second copy is named. `src/redkraken/roster.py` builds the same closed
      sets in Python: `ENTITY_TYPES` at `:182-191` from migration 0003's CHECK,
      `HYPOTHESIS_STATUSES` at `:196` from 0007's, and the five
      `question_code` values at `:733-741`, which are the rows of
      `decision_question_codes`
      (`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:47`) --
      a seeded catalogue whose only other consumer is an FK. Two sources of
      truth for one closed set, and the database's is the unread one.
- [ ] The three are still granted to `PUBLIC`. No migration revokes EXECUTE on
      any of them from `PUBLIC`, verified: `grep -rn "REVOKE.*mcp_enum"` over
      the migrations returns nothing. Whatever the caller turns out to be, an
      unrevoked `PUBLIC` grant on a function nothing calls is either narrowed or
      spent.
- [ ] `mcp_enum` answers three vocabularies today -- `property_class`,
      `observation_kind`, `observation_kind_evidential` -- and the tool schemas
      that would use them are `submit_mission_result`'s element lists, which are
      declared `Argument("array", free_text=True)` with the reason at
      `roster.py:668-678`: the element lists "stay open because a proposal is
      raw model output". The ticket decides whether that reason survives the
      enum being available, and does not quietly overwrite it: an open element
      list whose *values* are checked against a served vocabulary is a third
      option and may be the right one.
- [ ] Ticket 111 is what a served `parameter_value_class` vocabulary would then
      close, and is blocked on this one.

## Why

`docs/research/wiring/20-vocabulary-wiring.md` section 3b calls this "the
mechanism that would have prevented every other row in this report, built in
migration 018 and never connected", and its gate G7 generalises it: "a function
granted `EXECUTE` to `rk2_runtime` and referenced only by the migration that
created it is a capability with no consumer."

`docs/research/wiring/23-database-wiring.md` section 4.2 reaches the same three
from the catalogue and grades them load-bearing for the same reason: "Two
sources of truth for the same closed set, and the database's is the unread one."

One correction to report 20, which says "All three are `GRANT EXECUTE ... TO
rk2_runtime`". There is no explicit `GRANT EXECUTE` line for any of them in
`0018_vocabularies.sql` or `0025_transport_claims.sql`. The runtime holds them
through migration 029's default privileges, which is also why all three still
carry the `PUBLIC` grant nothing ever revoked. The report's conclusion is right
and the mechanism it names is not.
