# 40 — Build and evaluate a sound kill chain

**What to build:** Compose validated member Findings through demonstrated pivots and expose a reportable chain only while every member, edge and safety condition remains sound.

**Blocked by:** 39 — Stamp a demonstrated pivot.

**Status:** resolved

- [x] Agents may propose member order and capability flow but cannot write canonical chain edges or verdicts.
- [x] Runtime construction derives edges from compatible `requires` and `provides` values backed by current pivot stamps.
- [x] Integrity rejects cycles, disconnected members, vocabulary mismatch, cross-Program rows, unsatisfied requirements and ambiguous Identity flow.
- [x] Reportable reads recheck member validation, Test runs, Artifacts, Receipts, grants, scope, invalidations and review gates.
- [x] Invalidating any member or pivot makes the chain explicitly unsound and unrenderable without deleting its history.
- [x] Fixtures cover a valid linear chain, valid branch, missing pivot, cycle, stale member and an empty graph that must not be interpreted as a negative result.

## How each is met

1. **The proposal is two fields, and neither is the graph.** `build_kill_chain`
   takes a set of stamps and an opaque `p_flow` object; the runtime derives the
   edges, the depths and the order and writes its own. The agent's story goes to
   `chain_proposals`, beside the answer rather than inside it, and is read by
   nothing in this migration -- which is the point: it is kept so an operator can
   see what the agent believed and how that differed from what the stamps say.
   `rk2_runtime` holds INSERT on the four tables and `rk2_state` and `rk2_proxy`
   hold nothing at all, UPDATE and DELETE are revoked from every role, and the
   four tables carry `reject_mutation_unless_purging` triggers -- so a step or an
   edge can only ever be *added*, and only by the role `build_kill_chain` sets
   before writing. Verdicts have no column to be written to: there is no verdict
   anywhere in the schema, which is the shortest proof an agent cannot forge one.

2. **An edge is a join, not a row somebody decided on.** `rk2_chain_edges` is one
   query -- `u.provides = ANY (d.requires)` over the members of this Program --
   and every function that *derives* a graph reads it through that one query --
   depths, cycles, connectivity, Identity flow and the builder's own INSERT --
   so the graph a chain is validated as and the graph it is written as cannot be
   two graphs. Two places read something else on purpose:
   `rk2_chain_problem`'s unsatisfied-requirement arm asks about a capability
   rather than a pair, so an edge is not the shape of its question; and
   `check_kill_chains` reads the stored `chain_edges` rows precisely because a
   check that re-derived them could never notice that what is stored has drifted
   from what would be derived. "Backed by current pivot stamps" is 039's own
   sentence asked once per
   step: `rk2_pivot_refusal(program, tool_run)` at build time and again at every
   read. Not re-worded here, because a refusal worded twice is two rules
   pretending to be one, and they diverge the day one is edited. `chain_edges`
   stores what was derived; arm (c) of the standing check asks whether that is
   still what would be derived.

3. **Twelve refusals in one list, ordered so each rule reads a graph the rules
   above it have made sense of.** `rk2_chain_problem` returns the first or NULL:
   the empty graph, a NULL in the array, more than sixteen steps, a member this
   Program never stamped (which is missing and cross-Program at once, because
   from inside a fenced read they are the same absence), a member named twice, a
   chain of one, two vocabularies, a step 039 would no longer stamp, a cycle,
   an unsatisfied requirement, a disconnected member, ambiguous Identity flow.
   Three of those orderings are load-bearing. The empty graph is asked first
   because every rule below it is a `NOT EXISTS` and a `NOT EXISTS` over nothing
   is true -- an empty chain would pass integrity, pass soundness, and render as
   a claim the harness proved something. The cycle is asked before requirements,
   because a cycle satisfies its own by construction. And the stamps are
   resolved before anything, because every later rule reads columns off them.
   Ambiguous Identity flow is two parents disagreeing and nothing choosing --
   not fan-out, which criterion 6 asks to work, and not a step running as
   somebody new, which is what most pivots are for.

4. **The reportable read rechecks eight things, and only three of them are
   written here.** `rk2_chain_unsoundness` runs six arms in order: (a) 039's
   refusal per step, which *is* member validation, Test runs, Artifacts,
   Receipts and grants -- all five, in the sentence that already owns them; (b)
   the entry set, because a chain that started from a session is not a chain once
   the Identity that granted it is gone; (c) invalidated Identities; (d) the
   scope version the stamps were issued under against the Program's now; (e) a
   subject whose scope class is `denied`; (f) review gates. Arm (c) sits above
   arm (d) and that is a decision rather than a reading order: 012 invalidates an
   Identity when the configuration stops declaring it, and a changed
   configuration records its policy again -- so every withdrawn Identity arrives
   with a moved scope version behind it, and asked the other way round the
   Identity sentence would be unreachable and an operator who took a session away
   would be told the document moved. Arm (e) reads `scope_class = 'denied'` and
   not `NOT in_scope`, because 021 has a fourth class for a thing with no address
   at all -- an identity slot, a technology fingerprint -- and a Finding about a
   technology has a subject like that. Arm (f) names two of the eight hard codes
   034 registered and 038 extended rather than excluding two: `known_issue` and
   `duplicate` are where somebody decided the Finding may not be carried. The
   other six are not soundness questions, and `not_validated` is the one worth
   spelling out because it is *not* arm (a) restated -- the two deliberately
   disagree. 039 admits a member that is `validated` or `reported`, because a
   Finding somebody wrote up is not a Finding somebody withdrew;
   `report_blockers` holds anything other than `validated`, because 034 is about
   rendering that Finding's own report and one already sent must not be sent
   twice. Both are right about their own question, and reading 034's answer here
   would make a chain go unsound the moment its strongest member was submitted --
   which is the moment the chain is most worth having.
   `test_a_member_that_has_been_reported_keeps_its_chain_sound` pins it, and
   asserts the blocker really was raised so that it is a gate declined rather
   than a gate that never fired. `no_effect`, `no_chain` and
   `unwitnessed_effect` are about v1 report rows 042 has not assembled yet, and
   `cvss_stale` and `severity_unstated` are about the severity band, which is not
   a question about whether the transitions hold. Those two still stop the
   *report*, because 034 reads the blockers itself.

5. **Unsound is a sentence, and nothing is deleted to produce it.** The verdict
   is computed on every read and stored nowhere, so there is no cache to go stale
   on the day it matters. `read_kill_chain` on an unsound chain returns the
   label, `sound: false`, the reason, and `steps: null, edges: null` -- there is
   no partial render, because half a chain in front of a human is a claim the
   harness did not make. The rows stay: the case counts `chains`, `chain_steps`,
   `chain_edges`, `chain_proposals` and `pivot_stamps` before it moves the ground
   under a chain six ways in turn, counts them again afterwards, and asserts the
   two snapshots are equal and non-zero. A before-and-after and not a pair of
   literals, because literals would agree just as well with six reads that had
   deleted everything and a number written down after. A chain that
   stopped being true is the most useful history there is -- it records what the
   harness believed and what changed underneath it.

6. **Six shapes as fixtures, and the empty one twice.** A linear chain of two
   steps with the one edge the stamps imply; a branch of one step reaching two,
   both at depth 1, which is why steps carry a depth and not an ordinal; a
   missing pivot, refused by the id nobody stamped; a cycle, refused as its own
   ancestor; a stale member, through 039's refusal after the member's status is
   forced back; and the empty graph. The empty graph is refused by
   `build_kill_chain` in its first sentence *and* reported by
   `chain_composes_fewer_than_two_steps` in the standing check, because the verb
   refusing it does not stop a restore or a hand-written repair from leaving one
   -- and that check's negative control builds the emptiness directly, since
   `reject_mutation_unless_purging` means the steps cannot be carved out from
   under a real chain.

## What this ticket also changed

- **The Program's starting capabilities are derived, not declared.**
  `rk2_chain_entry` returns `anonymous_reach` always, and
  `authenticated_session` exactly when an operator provisioned a live
  non-anonymous Identity. Read off `identity_slots` and not `identities`,
  because 012 declares a slot and seals the material separately and a slot
  nobody provisioned is a session nothing can be sent as. If a chain could name
  its own entry set, every chain would name all ten words and every chain would
  be sound -- which `enforce_chain_entry` now refuses outright, beside the two
  rules about `entry` that were already there. All three are triggers rather
  than CHECK constraints for one reason: each reads the capability vocabulary,
  and a CHECK may only call IMMUTABLE functions. The column's own CHECK is
  `cardinality(entry) >= 1` and carries no ceiling, because the honest ceiling
  is a count of a table.
- **A chain's digest is a digest of digests.** `source` is the members'
  `source_sha256` values in sorted order, the entry set and the vocabulary
  digest; a stamp's digest already covers everything that stamp rests on, so a
  chain's identity covers the whole tree beneath it. Two agents proposing the
  same stamps in two orders build one chain and the second is recorded
  `repeated`.
- **Two fixture bugs that were invisible at scope version 1.**
  `ReplayFixture.receipted` and `ImpactRunFixture.undone` wrote the literal
  `1` into `receipts.scope_version`, and `rk2_pivot_source` reads the stamp's
  scope version off the transition Receipt rather than off the Program row. Both
  now read `programs.scope_version`, which is what made this ticket's scope arm
  testable at all.
- **`PivotStampFixture.settled` closes the runs it abandons.**
  `check_execution_closure`'s `open_agent_run_on_settled_task` arm is
  corpus-wide, not per Program, so a fixture that abandoned a Task while its
  agent run stayed open turned every later `program.run` in the process red.
- **`check_kill_chains` joins the standing checks.** Seven arms: a chain whose
  digest no longer covers its source, one composing fewer than two steps, a
  stored edge the stamps no longer agree with, a chain composing two
  vocabularies, one no `chain.built` Event attributes to the runtime, a step
  requiring what nothing in its chain supplies, and a cycle among the stored
  edges.

## What is not covered

- **No verb is served to a model, and there is no CLI.** `build_kill_chain` and
  `read_kill_chain` are called by the tests. Which stamps are worth composing is
  the orchestrator's decision, as it is for 038's and 039's verbs.
- **A chain is not ranked and not rendered.** Feeding chain unlocks into
  ranking is 041 and rendering a chain is 042; this ticket ends at "here is a
  graph, and here is whether it still holds".
- **Merges are permitted and not distinguished.** Two steps reaching one is a
  chain here, and the only thing said about it is that the two must have run as
  one Identity. Whether a merge is a stronger claim than a branch is a question
  about impact, which is 038's and 042's.
- **`chain_composes_fewer_than_two_steps` cannot be reached through the verb.**
  Neither can a stored cycle or an edge the stamps disagree with. All three are
  arms about rows that arrived some other way -- a restore, a partial purge, a
  repair -- which is what a standing check is for and why its negative control
  has to build the shape rather than provoke it.
- **The entry set is asked of the Program, so a chain can go unsound for a
  reason no member moved.** Withdrawing the last non-anonymous Identity makes
  every chain whose first step needed a session unsound at once. That is the
  rule working, and it is also the loudest way this migration can go red.

---

**Correction, 2026-08-21.** The caller claim in "What is not covered" checks
out: `build_kill_chain` and `read_kill_chain` are called by
`tests/test_database.py` and by nothing in `src/`. `read_kill_chain` is granted
to `rk2_human`, so a chain is a thing the operator is meant to be able to read
and no operator command reads one. The deferral to an "orchestrator dispatch ticket" is what was wrong: no such ticket
existed. Ticket 102 owns the Finding path these chains are composed from, and
ticket 103 owns both verbs.

**Correction closed, 2026-08-23.** The deferral above was owned by ticket 103,
and 103 has now taken it -- and split the two verbs. `build_kill_chain` is a
runtime step in the impact close path: it is the third statement of the `IMPACT`
verb set at `src/redkraken/replay.py:121-123`, run by `_downstream` (`:508`)
immediately after the pivot stamp, in the transaction that closed the run
(`:310`). The members are the stamps the Program already holds and everything
else is derived, so `p_flow` goes as SQL NULL rather than as a sentence the
process invented; a refusal is a hold (`:556`) and a rebuild of the same members
answers `"built": false` (`:562-564`). `read_kill_chain` became the operator read
this note said no command reached: `rk report soundness`
(`src/redkraken/cli.py:1531`, dispatching to `_report_soundness` at `:2828`)
reaches a new `soundness()` at `src/redkraken/reporting.py:776`, which runs
`SELECT read_kill_chain($1::uuid)` (`:101`, executed at `:830`) and passes the
verdict back whole. It is a sibling of `rk report chain` and not a Contract,
because a model that could ask whether its own chain is sound would be reading
the verdict on its own work.
