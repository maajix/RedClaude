# 172 -- The secret access log nobody reads, and two rules with no control

**What to build:** Three repairs to the credential audit this tree already has,
all three of them ours. **One:** `secret_access_log` records a reason and not a
requester for the one operator verb that decrypts, and the three columns `0024`
set aside for a requester are still commented *"Who asked"* while nothing in the
corpus will ever write them -- the decision that they stay null is real and is
written down twice, and the schema does not say so, so a reader of the table
concludes the audit lost something it in fact declined to invent. **Two:**
nothing in this tree reads the trail. No operator verb selects from
`secret_access_log`; outside migrations the only readers are tests. An audit
trail nobody can read is an audit trail that is not doing its job. **Three:**
`check_wire_artifact_secrecy` has eight rules and six negative controls, and the
two rules with no control are rules 3 and 4. Rule 3 is the one that says no
credential-bearing artifact is reachable from a session, which is the property
the whole seal arrangement exists to hold, and it is graded by nothing that
would go red.

**Blocked by:** nothing. The audit table, the one reveal path and the check
registry are all in the tree today.

**Status:** ready-for-agent

## Why this is not an import, and why the comparison is already closed

This ticket was opened to copy a sentence. Ticket 167 read HuntProxy, declined
the program, and named four ideas worth copying; the fourth was *"Sensitive
headers are redacted from inspection tools but available locally for
authenticated work; explicit reveals are audited"*
(`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md:255-259`),
and because that one touches credentials the operator pulled it out into its own
ticket as a measurement rather than as a build. The measurement was taken. This
tree already satisfies that sentence, and satisfies it more strictly than the
sentence asks. There is nothing to import, the comparison is finished, and
nothing below this section depends on it.

What the measurement found, with the anchors that carry it:

- **Exactly one path in this tree decrypts anything for a reader, and it is the
  operator's.** `rk artifact open` is declared at `src/redkraken/cli.py:1032-1038`
  -- the help line is *"decrypt one wire artifact to a file, deliberately and
  audited"* -- adapted at `src/redkraken/cli.py:3002` and implemented by
  `artifact.open_wire` at `src/redkraken/artifact.py:768`. It is not a Contract
  and it is not a tool. `roster.py`, `evidence.py` and `replay.py` contain no
  occurrence of `artifact_seal`, `request_wire_sha` or `response_wire_sha` at
  all, so no model names any of it. The evidence export
  (`src/redkraken/cli.py:2847-2853`) and the legacy import (`:2881-2886`) each
  say in their own docstring why they carry no key.
- **Everything else that touches plaintext returns it to nobody.** The door
  decrypts a provisioned header value in memory to put it on the wire
  (`src/redkraken/proxy.py:1678-1691`) and audits the attempt on both outcomes
  through `_confirm_headers_open` (`:1700`, called at `:1695` and `:1697`), which
  writes `secret_access_log`
  (`src/redkraken/migrations/20260811T190000Z__required_header_values_at_the_door.sql:193`,
  `:228`). The Identity's cookie jar is the same shape
  (`src/redkraken/identity.py:451`, docstring at `:187`: *"decrypted only in
  proxy memory"*).
- **The scrubbing half was here first.** `proxy._scrubbed`
  (`src/redkraken/proxy.py:766`) is reached from `project_identity_request`
  (`:719`) for the Agent's view of a request and from
  `project_identity_response` (`:677`) for the response, over the renderings
  `_renderings` (`:780`) enumerates; `response_for_agent` (`:663`) drops the
  wire-only header set before either runs. The two views are hashed separately
  and the wire view is the sealed one (`proxy.wire_view`, `:880`), which is what
  makes `CONTEXT.md:650-653` true: a Receipt *"carries the hashes of what the
  agent saw and what actually crossed the wire, which differ by exactly the
  injected credentials."*
- **The reveal is gated before it is informative.** `--authorize` is checked
  before the label is even looked up, so an unauthorized caller learns nothing
  about which labels have a seal behind them
  (`src/redkraken/artifact.py:822-838`), and the refusal is itself a row
  (`:824-831`).
- **Refusals are audited as loudly as successes**, and `_access` says why in its
  own docstring (`src/redkraken/artifact.py:1228-1234`): an audit trail with only
  the successes in it answers *"who opened this"* and cannot answer *"who
  tried"*.
- **The audit row goes down before the bytes do**, deliberately, and the comment
  at `src/redkraken/artifact.py:942-948` says which of the two possible failure
  states that ordering chooses and why that one is the acceptable one. The
  release row is at `:949-959`.
- **The record carries no secret and the plaintext never reaches a report.** The
  row keeps `value_len` and a four-byte keyed fingerprint and never the value
  (`src/redkraken/migrations/0024_secret_keying.sql:105-109`, `:130-131`); the
  report keeps the path, the length, the hash, the fingerprint and the
  operator's reason and nothing else (`src/redkraken/artifact.py:977-989`); the
  bytes go to a file opened `O_EXCL` at mode `0o600` (`:1268-1276`), for the
  reason stated at `:794-797`.
- **The row names the exchange it was opened out of**, since ticket 123.
  `receipt_id` is found by joining the artifact's plaintext hash back to the
  Receipt that recorded it as `request_wire_sha` or `response_wire_sha`, rather
  than carried down from a caller (`src/redkraken/artifact.py:290-305` for the
  query, `:873` for the call, and
  `src/redkraken/migrations/20260925T030000Z__a_secret_read_names_the_exchange.sql:58-69`
  for why it had to be found rather than held).

The sentence asks that explicit reveals be audited. This tree audits the
attempts as well, ties each one to the exchange it was made for, keeps a keyed
fingerprint so the same value turning up elsewhere is recognisable without the
value being reconstructable, and refuses to put the bytes anywhere a report can
be pasted. The idea was here before it was read anywhere else. That result is
recorded in ticket 167 under *"Answer, 2026-08-24"*, and it is the reason this
ticket is not an import. The three gaps below were found while taking that
measurement and would be exactly the same three if HuntProxy had never been
read.

## Criteria

- [ ] **Gap one: "who asked" is a reason and not a requester, and the schema
      still advertises three columns nothing will write.** `0024` provided the
      columns for a requester and commented them *"Who asked. The keyholder
      reads these off SO_PEERCRED; a caller cannot forge them"* --
      `src/redkraken/migrations/0024_secret_keying.sql:121-122` for the comment,
      `:123-125` for `peer_pid`, `peer_uid`, `peer_exe`. The insert
      `rk artifact open` uses binds none of them and no `tool_run_id` either:
      `src/redkraken/artifact.py:282-288` names `verb, scope_kind, scope_id,
      kek_gen, program_id, receipt_id, field, value_len, value_fpr, outcome,
      detail` and stops. So "who asked" on this verb is the free text an operator
      typed after `--authorize`, carried in `detail` (`:956`), which is a reason
      and not an identity. Two thirds of that is already decided and the decision
      is not reopened here: the peer columns stay null because every writer in
      this corpus would be writing about *itself*, and *"a process filling those
      three in about itself is recording a claim it could have made up"*
      (`src/redkraken/artifact.py:268-271`, restated and reaffirmed at
      `src/redkraken/migrations/20260925T030000Z__a_secret_read_names_the_exchange.sql:27-31`);
      `tool_run_id` is bound by the door's SQL writers, which have a Tool run in
      hand (for one,
      `src/redkraken/migrations/20260811T190000Z__required_header_values_at_the_door.sql:348`),
      and an operator opening an artifact weeks later is inside no Tool run and
      has none to offer. What is left is small and it is the whole of this
      criterion: the schema still says *"Who asked"* over three columns that are
      never written, and nothing at the schema says why. Close it by recording
      that conclusion in this ticket -- the identity of the requester is the
      operator's own shell and the trail records their stated reason instead --
      and, only if a migration is being written for another part of this ticket
      anyway, by one `COMMENT ON COLUMN` per column saying the columns are for a
      keyholder reading another process and stay null when the writer is the
      process itself. A migration whose only content is three comments is not
      worth its own file; the recorded answer is.
- [ ] **Gap two: nothing reads the trail.** `secret_access_log` is written from
      `src/redkraken/artifact.py:1252-1265` and from SQL writers inside four
      migrations, and nothing anywhere selects from it except tests:
      `src/redkraken/cli.py` never names the table. It is deliberately unreadable
      by a model -- classified `audit` rather than event-emitting at
      `src/redkraken/migrations/0030_corpus_corrections.sql:120`, with the reason
      on the same line, and unreachable from the agent connection by
      `check_wire_artifact_secrecy` rule 7
      (`src/redkraken/migrations/20260810T173000Z__sealed_wire_artifacts.sql:307-332`)
      -- and none of that is the same as an operator being able to read it.
      Answer whether the operator needs a verb for this at all. A `SELECT`
      written into this ticket that an operator pastes is a real answer and the
      cheapest one; an `rk artifact audit`-shaped verb is a larger one. Pick the
      smaller unless there is a stated reason not to. Whatever the answer, the
      read is over the columns that are actually filled -- `at`, `verb`,
      `program_id`, `receipt_id`, `field`, `value_len`, `value_fpr`, `outcome`,
      `detail` -- and it widens the read to no role that cannot already reach the
      table.
- [ ] **Gap three: two rules of the check that keeps this true have no negative
      control.** `check_wire_artifact_secrecy()` is defined at
      `src/redkraken/migrations/20260810T173000Z__sealed_wire_artifacts.sql:228`
      and registered as `wire_artifact_secrecy` at `:348-350`. It has eight
      rules. `tests/test_database.py:1920-1986` holds six controls against it,
      covering rules 1, 2, 5, 6, 7 and 8. Rule 3,
      `credential_bearing_artifact_reachable` (`:253-271`, the row it emits named
      at `:259`), is the rule that says no credential-bearing artifact is
      reachable from a session, and it has no control. Rule 4,
      `sealed_pair_incomplete` (`:274-284`, named at `:276`), has none either.
      Write one control for each, in `CONTROLS` (`tests/test_database.py:1075`),
      as a `Control` (`tests/test_database.py:786`), and make each one seed an
      actual violation: rule 3's control writes an encrypted or non-agent-visible
      artifact and then a `receipts` or `artifact_references` row that reaches
      it; rule 4's writes a seal whose `agent_sha256` names bytes that are
      purged, encrypted or absent. A control that merely lengthens a list is not
      a control. The precedent for what a real one looks like is the six already
      there -- each is one statement that makes one rule fire, with a comment
      saying which -- and the harness that proves it fires is
      `NegativeControlTest` (`tests/test_database.py:2679`), whose
      `test_each_check_fails_when_its_subject_is_broken` (`:2766`) asserts the
      named check appears in the failures and whose `rolled_back` (`:2723`)
      asserts the database is left as it was found.
- [ ] **Any new `check_` function is registered, or none is written.** The
      expected answer is that none is needed: gap three is test coverage of a
      check that already exists. If one turns out to be needed, it goes in
      `standing_checks`
      (`src/redkraken/migrations/0030_corpus_corrections.sql:546-551`) in the
      same migration that defines it, because `check_check_registration()`
      (`:618-638`) fails the very run that introduces an unregistered checker,
      and `assert_standing_checks()` (`:599`) raises on any failing row at the
      end of every `rk db migrate`. A registered check with no negative control
      is half a check; both halves or neither.
- [ ] **Nobody new can see a secret when this ticket closes.** State it as a diff
      and check it: no role gains a grant, no Contract gains a table, no
      `state_read_surface` row is added
      (`src/redkraken/migrations/0030_corpus_corrections.sql:246-254` -- *"rk2_state
      holds no relation-level grant: this table is the grant"*), and
      `check_state_grants()` (`:303`) and `check_wire_artifact_secrecy()` both
      still pass. If the work turns out to need any of those, it is a different
      ticket and it does not get done under this one.
- [ ] **No new reveal is built here, and a model-facing reveal is out of scope.**
      Adding any new capability that hands out plaintext is outside this ticket,
      and a model-facing one is outside every ticket. A reveal is the operator's,
      never a model's. `rk artifact open` stays the only path that decrypts for a
      reader, its shape does not change, and nothing this ticket delivers may
      become reachable from a Contract -- which for gap two means the trail
      reader, whatever shape it takes, is an operator's read and is not compiled
      into `CONTRACTS`.

## Notes

Not a regression and not a gap in the door. Everything in the section above has
been true since ticket 07's migration and ticket 123's follow-up. The three gaps
are in the audit's completeness, its readability and its test coverage, not in
the boundary: no unscrubbed byte reaches a reader it should not today, and none
of the three, left open, would change that. What gap three would change is
whether anyone would notice if that stopped being true.

Not ticket 125's problem. That ticket is about a redaction miss having nowhere
to be recorded; `redaction_failure` (`0024_secret_keying.sql:143`) is its table.
This one is about the deliberate opposite -- a release that was meant, and what
the record of it owes.
