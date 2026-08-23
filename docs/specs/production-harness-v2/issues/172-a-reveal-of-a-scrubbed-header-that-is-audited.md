# 172 -- A reveal of a scrubbed header that is audited

**What to build:** First a measurement and only then, if the measurement asks
for it, a build. Ticket 167 named four ideas worth copying from HuntProxy and
this is the fourth, promoted here at the operator's instruction because it is
the one that touches credentials. The question is not "add an audited reveal".
The question is "does this tree have an explicit reveal at all, and if it does,
is it audited" -- and the answer decides whether anything gets written. A first
reading, recorded below with anchors, says the reveal exists, is the operator's,
and is already audited more thoroughly than the sentence being checked against
asks for. What is left is three named gaps in the audit and its standing
controls, each of which closes either with a small change or with a recorded
decision that it stays open.

**Blocked by:** nothing. The reveal path, the audit table and the check registry
are all in the tree today.

**Status:** ready-for-agent

- [ ] **Nothing is copied.** No HuntProxy source is read into this repository,
      quoted as code, or paraphrased into code. One sentence of its prose is
      quoted, and it is quoted as a specification to hold this tree against:
      *"Sensitive headers are redacted from inspection tools but available
      locally for authenticated work; explicit reveals are audited."* That
      sentence is the whole of the inbound material. Ticket 167 section 5
      settled the licence question for reading, and reading is all that happens
      here.
- [ ] **The central question is answered with a result either way, and "no
      second path exists" is a good outcome that closes it.** The question is
      whether any path in this tree hands an unscrubbed header or an unscrubbed
      body to anybody, by any route: operator CLI, artifact read, replay,
      evidence export, legacy import, database dump, report. The first reading
      found exactly one, `rk artifact open`, and found nothing else. Re-run the
      search rather than trusting this paragraph, record what it covered, and
      record the count. If the count is still one, say so and move on; a
      measurement that confirms the tree is already closed is the result, not a
      failure to find work.
- [ ] **The one reveal is named and its shape is stated.** `rk artifact open`
      is declared at `src/redkraken/cli.py:1032-1038` -- the help line is
      *"decrypt one wire artifact to a file, deliberately and audited"* --
      adapted at `src/redkraken/cli.py:3002` and implemented by
      `artifact.open_wire` at `src/redkraken/artifact.py:768`. It is an
      operator command. It is not a Contract, not a tool, and reaches no model:
      `roster.py`, `evidence.py` and `replay.py` contain no occurrence of
      `artifact_seal`, `request_wire_sha` or `response_wire_sha` at all, and
      `src/redkraken/cli.py:2847-2853` says why the export has no key -- *"a
      sealed wire artifact is never reached, so a command able to unseal one
      would be a capability this operation has no use for."*
- [ ] **The scrubbing side is verified rather than assumed.** `proxy._scrubbed`
      is at `src/redkraken/proxy.py:766`, as ticket 167 said. It is reached from
      `project_identity_request` (`:719`) for the Agent's view of a request and
      from `project_identity_response` (`:677`) for the response, over the
      renderings `_renderings` (`:780`) enumerates; `response_for_agent`
      (`:663`) drops the wire-only header set before either runs. The two views
      are hashed separately and the wire view is the sealed one
      (`proxy.wire_view`, `:880`), which is what makes `CONTEXT.md:650-653`
      true: a Receipt *"carries the hashes of what the agent saw and what
      actually crossed the wire, which differ by exactly the injected
      credentials."* Confirm each of these line numbers before writing anything
      that depends on them.
- [ ] **The audit is checked field by field against the four things an audit
      record owes, and each is answered yes or no with an anchor.** *Who asked*,
      *when*, *which row*, and *the record carries no secret*. What the reading
      found:
      **When** is `secret_access_log.at`, `timestamptz NOT NULL DEFAULT now()`
      (`src/redkraken/migrations/0024_secret_keying.sql:113`).
      **Which row** is `receipt_id`, written since ticket 123 and back-linked
      through the wire hash rather than carried down from a caller
      (`src/redkraken/artifact.py:290-305` for the query, `:873` for the call,
      and `src/redkraken/migrations/20260925T030000Z__a_secret_read_names_the_exchange.sql:58-70`
      for why it had to be found rather than held).
      **No secret** holds twice over: the row keeps `value_len` and a four-byte
      keyed fingerprint and never the value
      (`0024_secret_keying.sql:104-109`, `:130-131`), and the report keeps the
      path, the length, the hash, the fingerprint and the operator's reason and
      nothing else (`src/redkraken/artifact.py:977-989`), with the bytes going
      to a file opened `O_EXCL` at mode `0o600` (`:1268-1276`).
      **Who asked** is the one that is only half answered, and it is the next
      criterion.
- [ ] **Gap one: the row records a reason and not a requester.** `0024` provided
      three columns for exactly this and commented them *"Who asked. The
      keyholder reads these off SO_PEERCRED; a caller cannot forge them"*
      (`src/redkraken/migrations/0024_secret_keying.sql:120-123`:
      `peer_pid`, `peer_uid`, `peer_exe`). The insert this command uses binds
      none of them, and binds no `tool_run_id` either --
      `src/redkraken/artifact.py:282-288` names `verb, scope_kind, scope_id,
      kek_gen, program_id, receipt_id, field, value_len, value_fpr, outcome,
      detail` and stops. So today "who asked" is the free text an operator typed
      after `--authorize`, carried in `detail`
      (`src/redkraken/artifact.py:956`), which is a reason and not an identity.
      Decide one of two things and record it: fill the three columns from the
      calling process, or write down that an operator command running as the
      operator has no second identity to record and the columns stay null for
      that reason. Either is an acceptable close. What is not acceptable is
      leaving the columns undecided, because a column that exists and is never
      written reads as an audit that lost something.
- [ ] **Gap two: nothing reads the trail.** `secret_access_log` is written from
      `src/redkraken/artifact.py:1252-1265` and from four migration functions,
      and no operator verb selects from it: the only readers outside migrations
      are tests. `src/redkraken/cli.py` never names the table. It is deliberately
      unreadable by a model -- classified `audit` rather than event-emitting at
      `src/redkraken/migrations/0030_corpus_corrections.sql:120`, with the
      reason on the same line, and unreachable from the agent connection by
      `check_wire_artifact_secrecy` rule 7
      (`src/redkraken/migrations/20260810T173000Z__sealed_wire_artifacts.sql:307-332`)
      -- and none of that is the same as an operator being able to read it.
      Answer whether the operator needs a verb for this at all. A `SELECT`
      written into this ticket that an operator pastes is a real answer and the
      cheapest one; a `rk artifact audit`-shaped verb is a larger one. Pick the
      smaller unless there is a stated reason not to. Do not widen the read to
      any role that cannot already reach the table.
- [ ] **Gap three: two rules of the check that keeps this true have no negative
      control.** `check_wire_artifact_secrecy()` is defined at
      `src/redkraken/migrations/20260810T173000Z__sealed_wire_artifacts.sql:228`
      and registered as `wire_artifact_secrecy` at `:348-350`. It has eight
      rules. `tests/test_database.py:1920-1986` holds six controls against it,
      covering rules 1, 2, 5, 6, 7 and 8. Rule 3,
      `credential_bearing_artifact_reachable` (`:253-271`, the row it emits
      named at `:259`), is the rule that says no credential-bearing artifact is
      reachable from a session, which is the exact property this ticket is
      about -- and it has no control. Rule 4, `sealed_pair_incomplete`
      (`:274-284`, named at `:276`), has none either. Write one control for
      each, in `CONTROLS` (`tests/test_database.py:1075`), as a `Control`
      (`tests/test_database.py:786`), and make each one seed an actual
      violation: rule 3's control writes an encrypted or non-agent-visible
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
- [ ] **Any new `check_` function is registered, or none is written.** If the
      answer to the three gaps needs no new checker, say so and skip this. If it
      needs one, it goes in `standing_checks`
      (`src/redkraken/migrations/0030_corpus_corrections.sql:546-551`) in the
      same migration that defines it, because `check_check_registration()`
      (`:618-636`) fails the very run that introduces an unregistered checker,
      and `assert_standing_checks()` (`:599`) raises on any failing row at the
      end of every `rk db migrate`. A registered check with no negative control
      is half a check; both halves or neither.
- [ ] **Nobody new can see a secret when this ticket closes.** State it as a
      diff and check it: no role gains a grant, no Contract gains a table, no
      `state_read_surface` row is added
      (`src/redkraken/migrations/0030_corpus_corrections.sql:246-254` -- *"rk2_state
      holds no relation-level grant: this table is the grant"*), and
      `check_state_grants()` (`:303`) and `check_wire_artifact_secrecy()` both
      still pass. If the work turns out to need any of those, it is a different
      ticket and it does not get done under this one.
- [ ] **Giving a model a reveal is out of scope and is named as out of scope.**
      A reveal, if it exists at all, is the operator's. There is no
      model-facing verb for it, there is no ticket here to write one, and
      nothing in this ticket's deliverables may become reachable from a
      Contract. The half of the HuntProxy sentence that says *"available
      locally for authenticated work"* means locally to a person at a terminal
      with the key location in hand, and that is how it is read here.
- [ ] **If a reveal is ever written -- here or later -- these are its
      criteria.** Written down once, in this ticket, so a future author does not
      have to derive them: the record says who asked, when, which row it was
      opened out of, and carries no secret itself; the refusals are recorded as
      loudly as the successes; the audit row is written before the bytes are
      released; and the plaintext leaves through a file the caller names and
      never through a report. All four are already how `open_wire` behaves --
      `src/redkraken/artifact.py:1228-1234` for refusals being logged, `:942-948`
      for the ordering and the reason it is that way round, `:794-797` for the
      report rule -- so this criterion is satisfied by citing them, not by
      writing them again.

## Why this is asked, and what the first reading found

Ticket 167 evaluated HuntProxy against this harness, declined the program, and
named four ideas worth copying. Three of them are additive -- fuzz response
grouping, HAR export, and the plugin contract as a shape for an executable
Playbook step. The fourth is not additive at all, and that is why the operator
pulled it out into its own ticket: it is about credentials, and a ticket that
starts life as "add a reveal" is a ticket that ends life having widened who can
see one. So it starts as a measurement instead.

Quoted from ticket 167 section 3, fourth bullet
(`docs/specs/production-harness-v2/issues/167-evaluate-huntproxy-against-the-door.md:255-259`):

> **"Sensitive headers are redacted from inspection tools but available locally
> for authenticated work; explicit reveals are audited."** This tree already
> scrubs (`proxy._scrubbed:766`) and already differs the two hashes
> (`CONTEXT.md:650-653`). The half worth checking we have is the *audited
> explicit reveal*.

The half worth checking turns out to be there. `src/redkraken/artifact.py:43-49`
states the design in the module's own words: *"`open` is the only thing that
decrypts, and it refuses unless an operator says in the invocation that they
meant to. It never returns plaintext in the report ... The bytes go to a file the
caller names, and the report says where, how many and which hash. Every attempt,
taken or refused, is a `secret_access_log` row."* The implementation matches:
`--authorize` is checked before the label is even looked up, so an unauthorized
caller learns nothing about which labels have a seal behind them
(`src/redkraken/artifact.py:822-838`), and both the denial and the release are
rows (`:824-831`, `:949-959`).

That is a stronger property than the sentence being checked against asks for.
HuntProxy's sentence asks that explicit reveals be audited. This tree audits the
attempts as well, ties each one to the exchange it was made for, keeps a keyed
fingerprint so the same value turning up elsewhere is recognisable without the
value being reconstructable, and refuses to put the bytes anywhere a report can
be pasted. The honest result of the measurement is that the idea was already
here before it was read anywhere else.

## What the search covered, so a re-run knows what to beat

The first reading looked for a route by which unscrubbed material reaches a
reader, and found these and no others:

- **The model.** Nothing. `roster.py` names no seal, no wire hash and no key.
  Every credential-bearing artifact is unreachable from a session by
  construction, and rule 3 of `check_wire_artifact_secrecy` is what says so
  (`src/redkraken/migrations/20260810T173000Z__sealed_wire_artifacts.sql:253-271`).
- **The agent connection.** Nothing. `rk artifact get`
  (`src/redkraken/cli.py:925-969`, adapter at `:2611`) reads *"as the agent
  connection sees it"* -- through `rk2_state`, which holds no relation-level
  grant on anything and no column grant on `artifact_seal`,
  `secret_access_log`, `secret_kek`, `secret_dek`, `redaction_failure` or
  `seal_algorithms`, checked twice over at
  `20260810T173000Z__sealed_wire_artifacts.sql:307-332`.
- **The evidence export.** Nothing, and deliberately: `src/redkraken/cli.py:2847-2853`.
- **The legacy import.** Nothing, and for the mirrored reason:
  `src/redkraken/cli.py:2881-2886`.
- **The door itself.** The door decrypts a provisioned header value in memory to
  put it on the wire (`src/redkraken/proxy.py:1678-1691`) and returns it to no
  caller; the attempt is audited on both outcomes through
  `_confirm_headers_open` (`src/redkraken/proxy.py:1700`, called on both outcomes at `:1695` and `:1697`), which writes
  `secret_access_log`
  (`src/redkraken/migrations/20260811T190000Z__required_header_values_at_the_door.sql:193`,
  `:228`). The Identity's cookie jar is the same shape
  (`src/redkraken/identity.py:451`, docstring at `:187`: *"decrypted only in
  proxy memory"*).
- **`rk artifact open`.** The one path. Operator-only, key-gated,
  authorization-gated, audited on every outcome, and it writes to a file rather
  than to a report.

A re-run that finds a second path has found something worth more than this whole
ticket, and should say so first.

## Notes

Not a regression and not a gap in the door. Everything above has been true since
ticket 07's migration and ticket 123's follow-up. The three gaps this ticket
names are in the audit's completeness and in its test coverage, not in the
boundary: no unscrubbed byte reaches a reader it should not today, and none of
the three, left open, would change that.

Not ticket 125's problem. That ticket is about a redaction miss having nowhere to
be recorded; `redaction_failure` (`0024_secret_keying.sql:143`) is its table.
This one is about the deliberate opposite -- a release that was meant, and what
the record of it owes.
