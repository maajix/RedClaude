# 39 — Stamp a demonstrated pivot

**What to build:** Issue one runtime-authored pivot stamp only when a validated Test proves that a Finding provides a named capability under explicit conditions.

**Blocked by:** 29 — Deliver pending decisions, Halt and resume verbs; 37 — Validate a Finding through a blind validator.

**Status:** resolved

- [x] A pivot proposal names its member Finding, subject, Identity, required capabilities, provided capability, scope and safety conditions.
- [x] The runtime resolves one holding Test run whose assertions demonstrate the claimed transition rather than merely the member vulnerability.
- [x] Grant, Program, Artifact, Receipt and current Finding validity are rechecked when issuing the stamp.
- [x] The immutable stamp records exact member, Test, conditions, vocabulary and source hashes and is emitted only by runtime authority.
- [x] Missing, inferred, cross-Program, expired-grant and invalidated-member pivots are refused.
- [x] Repeating the same valid issuance is idempotent, while changed evidence requires a new stamp.

## How each is met

1. **The claim is in the specification, before the run.** A Test spec may carry
   an optional `pivot` block of exactly five fields -- `provides`, `requires`,
   `identity`, `transition`, `conditions` -- and `rk2_pivot_problem` refuses
   every other shape: a stray key, a pivot without the `impact` block it rides
   on, a `provides` or a `requires` entry that is not one of the ten words in
   `capabilities`, a `requires` list that is empty, longer than eight, repeats a
   word or names the word it provides, an `identity` that is not a slot name, a
   `transition` naming no assertion of this Test, conditions outside 035's five
   precondition kinds, and -- because criterion 1 asks for "scope and safety
   conditions" and those are two asks -- conditions stating no `scope_holds` at
   all. The member, the subject and the Identity are not
   copied into the block: the member is the Finding the impact Task was opened
   on, the subject is that Finding's, and the Identity is a slot name the run
   holds a lease on -- so the proposal names them by being about that run rather
   than by repeating them where they could disagree. Written before rather than
   after, because 035 made the spec immutable and digested and 038 made that
   digest the thing an operator's grant is over: a pivot claim authored beside a
   finished run is a claim fitted to its answer, and one in the spec is a
   prediction the run either bears out or does not. The block reaches the column
   `tests.pivot_provides` through `apply_pivot_claim`, a BEFORE INSERT trigger,
   because a CHECK may only call IMMUTABLE functions and reading the vocabulary
   is not immutable -- the same rule at the same moment through the other
   mechanism this schema has for it.

2. **Demonstrating the transition is a structural question.** Two conditions,
   both read off canonical rows. `rk2_pivot_transition_held` looks the named
   assertion up in the run's own `assertion_results` -- a lookup, not an
   interpretation -- so a run that held on the strength of its other assertions
   is refused by name. `rk2_pivot_is_the_members_own_request` compares the route
   of the action the transition reads against every action of the member's own
   validating Test, by method, scheme, host, port and path; when it matches, the
   run demonstrated the member a second time and no transition at all. Which
   Receipt the transition is read from is `rk2_pivot_transition_receipt`, which
   walks claim to assertion to action to `test_replay_actions` -- the table 035
   wrote as the run performed it -- so nothing a caller says afterwards can
   redirect it.

3. **Five rechecks, at issuing time, in one list.** `rk2_pivot_refusal` returns
   the first reason or NULL. The grant: the decision the run opened under is
   still `approved`, and `live_grant_for` still returns something for the
   equivalence key 038 recorded -- read as `d.status` and not `d.*`, because 029
   revoked the runtime's table-level SELECT and gave back every column but the
   answer. The Program: not closed, not halted. The member: still `validated` or
   `reported`, asked now rather than trusted from when the run opened. The
   Receipt: still there, still this Program's, and still `allowed`. The
   Artifacts: every wire and agent digest the transition Receipt cites is still
   held *and not retired*, named in the refusal when they are not -- 011 keeps
   the row and stamps `purged_at`, so asking only whether the row is there would
   answer yes about a body this database deliberately no longer has.
   Cross-Program is the same
   question asked once: `rk2_program_required` fences the read, so a Tool run of
   another Program is not found and gets the missing-run sentence.

4. **The stamp is the whole of what it rests on.** `pivot_stamps` carries the
   member, its subject, the Identity, the Test, the Test run, the Tool run, the
   transition Receipt, the transition, `provides`, `requires`, `conditions`, the
   scope version, the vocabulary digest, the source object and its digest --
   with a CHECK that `source_sha256 = equivalence_key(source)` and a second CHECK
   that *every* column but the label and the issuing time equals its field of the
   object the digest covers, so a row whose columns say one thing and whose hash
   covers another cannot exist. All of them and not a readable subset: a column
   left out of that list is a column the hash does not defend, which is the only
   kind of column worth moving. The two fields of the source that have no column
   -- the run that validated the member, and the spec digest -- are in the object
   to move the hash when the evidence moves, and 040 reads them off `source`. It is
   immutable by trigger, `rk2_runtime` is the only role with INSERT and UPDATE
   and DELETE are revoked from it, and `issue_pivot_stamp` sets the runtime actor
   before writing -- which 026's guard reads off `session_user`, so the
   `pivot.stamped` Event could not have said anything else. The vocabulary digest
   is over the words *and* their descriptions, so re-describing a capability
   moves it and every stamp issued before keeps the old one.

5. **Fifteen refusals, each with the sentence it is refused by.** No run, no
   impact run, another Program's run (all three the same sentence, because they
   are the same absence); a run that has not closed; a Test claiming no pivot; a
   run that concluded `refutes` or `inconclusive`; a named transition that did
   not hold;
   a grant that is not approved or no longer live; a closed Program; a halted
   Program; a member that is no longer validated; a missing transition Receipt;
   a transition the door refused; cited Artifacts the database no longer holds; a
   transition that went out as an Identity other than the one claimed, or as
   nobody; and a transition the member was itself validated on. Every attempt is
   recorded either way: `pivot_proposals` takes one row per issuance, carrying
   what criterion 1 says a proposal names -- member, subject, Identity slot,
   required and provided capabilities, conditions -- beside the refusal sentence
   or the stamp it reached. Including attempts about a Tool run nobody has, so an
   operator can tell "nothing was claimed" from "everything was refused"; that
   row is the one where every one of those columns is NULL, which is itself the
   answer.

6. **Idempotence is a hash, not a flag.** `rk2_pivot_source` builds one canonical
   object -- member, the run that validated it, subject, Identity, Test, spec
   digest, Test run, Tool run, transition Receipt, the transition, `provides`,
   `requires`, `conditions`, scope version and vocabulary digest -- and `equivalence_key` of
   it is the stamp's identity, held unique per Program. Issuing again from
   unchanged evidence finds that row and returns it with `issued: false`,
   recorded as a `repeated` proposal. A second run of the same Test gives a
   different Test run, Tool run and Receipt, so it digests differently and is a
   second stamp; a member re-validated by a later run moves
   `member_validated_by`, which is why it is in the object.

## What this ticket also changed

- **The corpus has a capability vocabulary.** Ten words, reference data by 027's
  rule, global across Programs because a pivot in one Program means what it means
  in every Program. None of them names a weakness: 007 owns the property class,
  which is what a Finding is *about*, 018 owns the vulnerability class, which is
  what it *is*, and this is the third question -- what holding it *gets you*,
  which is the only thing a chain can compose over.
- **`rk2_test_spec_problem` admits one more key.** `pivot` joins `impact` as a
  part that is stated rather than performed. Every other rule in that validator
  is carried over word for word, rationale included, because a
  `CREATE OR REPLACE` replaces the whole body and what is not copied forward is
  deleted. The pivot half is enforced by the trigger beside it.
- **`pivot_proposals` is wider than the stamp it may not reach.** It records the
  subject, the Identity slot the claim named and the conditions it stated, so a
  refused attempt is a readable claim rather than a sentence about a claim that
  is no longer anywhere. The slot is the claimed one and not the door's, because
  the disagreement between those two is one of the refusals.
- **`check_pivot_stamps` joins the standing checks.** Seven arms: a stamp whose
  digest no longer covers its source, one off a member that is no longer
  validated, one whose member has since been re-validated by another run, one no
  `pivot.stamped` Event attributes to the runtime, one citing a Receipt that is
  not its own run's, one resting on a run that did not hold, and a stored Test
  requiring a capability the vocabulary has lost. Its negative control is the
  last of those, because it is the only one a migration can bring about: the Test
  is unchanged and still immutable, and the ground under it moved. Deliberately
  absent is an arm on a stamp whose vocabulary digest is not the current one --
  keeping the old digest is what recording it was for, and a check on it would go
  red at the next vocabulary change and stay red.
- **`ImpactRunFixture` learned to hold an Identity.** A slot-bearing replay needs
  the whole chain -- the configured `[[identity]]`, `identity.provision` sealing
  the material into the slot, an `identity_leases` row written by the owner with
  the holder's *own* Task lease expiry, the slot passed to `open_impact_replay`,
  the Receipts carrying `identity_entity_id`, and the lease released when the run
  stops sending. Two of those are rules rather than decoration: 023's standing
  check reads one clock, so a lease expiry half a millisecond off the Task's is
  two clocks; and releasing through `release_leases` would give back the Task
  lease as well, which 023 reads as a claimed Task nobody is holding.
- **Two grants per Test, not one.** `rk2_impact_digest` includes the Identity
  slot, so the same Test sent as nobody is a different thing for an operator to
  have approved -- which is the rule working, and which the fixture obeys by
  asking twice.

## What is not covered

- **No verb is served to a model, and there is no CLI.** `issue_pivot_stamp` is
  called by the tests. Which run is worth stamping is the orchestrator's
  decision, and the tool it makes that decision through belongs to the
  orchestrator dispatch ticket -- as it does for 038's three verbs.
- **Nothing composes stamps yet.** A stamp says one capability was obtained from
  one member under one set of conditions. Joining them into a chain, and asking
  whether the chain is sound, is 040 -- which is why the stamp carries every
  column that join will need instead of leaving them to be re-derived.
- **"The member is no longer validated" is reached by forgery, because there is
  no front door.** 007 gives a validated Finding exactly one exit,
  `validated → reported`, and it needs a `human` actor -- which 026 reads off
  `session_user`, and `rk2_human` holds no INSERT on `finding_transitions` --
  plus 034's approved rendering and no hard blockers. Nothing in this corpus
  moves a Finding to `rejected` from there at all. So the case writes the column
  under the guard rather than through it: `findings_status_guard` off for one
  owner statement, the run issued from, the status put back, and the guard
  ALWAYS again inside the same transaction. The refusal that comes back is the
  real one and the state it read was not, which is the honest version of a test
  for a state the schema has no verb for. The corpus-level version of the same
  question is arm (b) of the standing check, which is where a member that moved
  after the fact is reported.
- **The refusal for a Receipt the door denied is reachable only by hand.** 011
  writes no Tool-run capability for a denied request, so a run whose transition
  was refused has no `test_replay_actions` row to read the Receipt from and the
  missing-Receipt arm answers first. The arm stays because the two are different
  facts -- "nothing answered" and "something answered no" -- and only one of them
  is about the door.
- **A stamp is not evidence that the capability persists.** It records that a run
  was seen to obtain it at one moment, under one scope version, with one
  Identity. Whether the same request would still work tomorrow is a question only
  another run could answer.

---

**Correction, 2026-08-21.** The caller claim in "What is not covered" checks
out: `issue_pivot_stamp` is called by `tests/test_database.py` and by nothing in
`src/`. What is not true is the deferral. The "orchestrator dispatch ticket"
this section names, here and for 038's three verbs, did not exist in the tree
when this ticket resolved. It is now ticket 102, which owns the Finding path
itself, and ticket 103, which owns `issue_pivot_stamp` and the other verbs
downstream of a Finding that still have no production caller.

**Correction closed, 2026-08-23.** The deferral above was owned by ticket 103,
and 103 has now taken it. `issue_pivot_stamp` is a runtime step in the impact
close path rather than a verb served to a model: it is the third member of the
`IMPACT` verb set at `src/redkraken/replay.py:111`, and `_downstream` (`:508`)
runs it at `:310`, inside the same transaction that has just run
`close_impact_replay` (`:110`) -- a stamp that outlived a close that rolled back
would be a reading of a run nobody has. Both parameters name rows this machine
wrote, the Tool run the file has just closed and the agent run it was opened
for, so there is nothing a model could contribute. A refusal is a hold in the
document and not a failed command (`:545`), and a second call on one Tool run
answers `"issued": false` and is reported as already stamped from that evidence
(`:548-550`). A pivot is now stamped outside a test.
