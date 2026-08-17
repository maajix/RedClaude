# 57 — Close the 223-row v1 disposition ledger

**What to build:** Prove that the complete v1 Agent, Skill and Playbook knowledge surface has a verified v2 outcome and that the production catalogue contains every planned web/API replacement.

**Blocked by:** 48 — Rework v1 Agents, Skills, references and sink packs; 49 — Migrate recon, API and protocol Playbooks; 50 — Migrate authentication and Identity Playbooks; 51 — Migrate authorization and business-logic Playbooks; 52 — Migrate browser and client-side Playbooks; 53 — Migrate injection Playbooks; 54 — Migrate server-side, file and disclosure Playbooks; 55 — Migrate platform and supply-chain Playbooks; 56 — Migrate HTTP integrity and parsing Playbooks.

**Status:** resolved

**Deviation on criterion 2:** the evaluation half is not decidable here. "Passing
hash-specific production evaluations" is a fact about `playbook_test_verdict`, which
reads test runs filed by an Agent against a fixture -- a database and a live run, where
this gate is offline, opens nothing and writes nothing, exactly like the row gate it
extends. What is offline-decidable is the precondition the phrase rests on: the digest
the schema corpus registers for a Playbook is the digest of the text this checkout
ships, so the document the database would grade is the document in the wheel. That is
now checked for all fifty. The verdict itself stays where ticket 46 put it -- both
`playbook_test_verdict` and `playbook_promotion_evidence` take a `p_sha` and no Playbook
reaches `stable` without one -- and the route by which a real Agent reaches a fixture is
ticket 78's.

- [x] The final ledger reconciles exactly 11 Agent definitions, 28 Skill directories, 60 Playbook topics, 112 operator references, 9 sink packs and 3 reserved files.
- [ ] Exactly 49 in-scope web/API Playbooks exist, validate, are loadable and have passing hash-specific production evaluations. **Partial:** exist, validate, load and are registered at the text they ship, per the deviation above. Ticket 78 closes the evaluation half.
- [x] Ten Android Playbooks, two Android Skills, one Android Agent and the 39 Android operator references carry explicit reversible scope-retirement records; one remaining topic is absorbed as reference material.
- [x] All 73 in-scope references and 9 sink packs resolve from at least one bounded Skill or Playbook reference and none is injected globally.
- [x] There are zero missing replacements, stale source hashes, dangling Skills, unloadable stable Playbooks, duplicate dispositions or unresolved manifest rows.
- [x] Adding, deleting or modifying a v1 knowledge artifact makes the coverage gate fail with the exact unclassified identity.

## Comments

Implemented on 2026-08-17.

### Why a second gate

`tools/check_dispositions` asks one question of each of the 223 rows -- does this row
resolve? -- and asks it row by row, so it can say nothing about the shape of the answer.
A ledger where every row resolves can still be a migration that did not finish: 48
Playbooks where the plan said 49, a reference file sitting in a directory whose Playbook
was deleted, a Skill nothing loads, a catalogue entry whose registered digest is a text
that no longer ships. Each of those is a property of the whole and none is visible from
inside a row.

`tools/check_coverage` is that reading. It runs the row gate first and inherits its
refusals -- a row pointing at a Playbook that is not there would otherwise be counted
here as a Playbook that is -- then adds five arithmetic checks over one `Closure`
gathered once. Its numbers are constants, not derivations: counting the Playbooks in the
corpus and asserting the corpus has that many is not a test, and "forty-nine" is a
decision the plan took and has to keep. `python3 -m tools.check_coverage` prints seven
lines and exits 0.

```
v1 coverage
  in-scope playbooks      49   loadable 49  frozen 49
  in-scope references     73   attached 73
  sink packs               9   attached 9
  absorbed topics          1   attached 1
  retired: android        52   agent_definition 1  skill_directory 2  playbook_topic 10  operator_reference 39
  catalogue               50   skills 6  references 84
  census                 223   reconciled
```

### What each reading proves

**Criterion 1** is two readings. `plan_errors` spends the census: 49 rewritten plus 10
retired plus 1 absorbed is the 60 Playbook topics the manifest froze, 73 absorbed plus
39 retired is its 112 operator references, and 9 is its 9 sink packs. That is the one
place the constants meet a number they cannot agree with by construction, because
`EXPECTED_COUNTS` was frozen by the census ticket and the four spending numbers were
decided by the migration tickets; move either side alone and the sum stops closing. It
speaks for three kinds rather than six: what became of the 11 Agent definitions and 28
Skill directories is a per-row question the ledger answers and no criterion counts.
`census_errors` then compares the ledger's own rows, keyed by kind, against the same six
totals. The row gate forces that today -- it refuses a ledger whose sources are not the
manifest's -- and it is asked again because that is a property of another checker's
implementation rather than of the ledger.

**Criterion 2** takes the 49 `rewritten` `playbook:` replacements the ledger names,
requires that many distinct ones and that each is in the corpus; then, over the whole
corpus rather than the 49, that some single role can load every Skill a Playbook names
and that the schema corpus registers it at the digest it ships. Loadability and
registration are asked of all 50 because criterion 5 wants zero unloadable Playbooks and
a v2-authored one is as capable of being unloadable as a migrated one.

**Criterion 3** splits the 52 retirements by scope and then by kind, and compares each
against the register. The split is what makes a retirement auditable: "52 artifacts
retired" hides which 52, and the Android reversal on record is written against exactly
these four numbers -- "the one Agent definition, two Skills, ten Playbook topics and
thirty-nine references are still in the frozen census". Per scope rather than over every
retirement, because two scopes sharing a total would each be accounted for by the
other's reversal; a row retired under a scope the plan writes no split for is named with
its source. Reversibility itself is the row gate's -- it already refuses a scope without
a `reason` and a `reversal`. Then the one absorbed topic is counted.

**Criterion 4** runs both directions. Every `reference:` replacement must name a page
some Skill or Playbook declares, which is how a page outliving its document shows up:
the directory stays, the file stays, and nothing can reach it. And every file actually
sitting in a `references/` directory must be declared by the document that owns it,
which is the "none is injected globally" half -- a reference's first two path segments
name its owner, so there is no spelling for a page belonging to everybody, and a loose
file's only possible reader is something that opens the directory.

**Criterion 5** is the remaining half: no Skill that no Playbook names, and none that no
role holds.

**Criterion 6** is met on the paths that already exist and was not duplicated. A deleted
v1 artifact is `no disposition for v1 artifact: X`; one that was never in the census is
`disposition for something the census does not hold: X`; a modified one is `X:
disposition was taken against a stale source hash`; and the census drifting under the
ledger is `check_baseline --v1 <v1 checkout>`'s `missing/added/changed v1 artifact: X`,
which is not in the four-command sequence because the v1 tree is not in this repository
and the operator has to hand it in. Each names the artifact rather than a count.

Those four are row-level, which is the honest shape of the criterion: a v1 artifact is a
census row here. The closing gate's own artifact-naming refusals are about the tree it
landed in -- a registration that drifted from the text it ships, a page whose declaring
document went away, a page sitting loose in a `references/` directory -- and
`CoverageDriftTest` reaches one of them end to end through `check()`, with a second
retirement scope registered as properly as the first and nothing in the plan accounting
for what it took.

### The registration regex

Reading registrations out of the schema corpus with the row gate's
`INSERT INTO {table} \([^)]*\) VALUES(.*?);` finds 9 of 50: it truncates at the first
semicolon, and a Playbook's `provenance` prose contains semicolons. So this one matches
the path literal and the digest immediately after it -- the shape every migration writes
and the only place the two appear adjacent -- and needs no statement boundary. It is
narrow on purpose: a corpus that stopped matching reports the Playbook as unregistered,
which is a refusal somebody reads rather than a pass nobody notices. Later registrations
win, because the corpus is concatenated in apply order and every registration is an
upsert, so a Playbook re-frozen by a later ticket reads at the digest that ticket set.

### One spelling of "loadable", and one of the ledger fixtures

`roster.loadable` is published rather than left inline in `_check_playbooks`, and the
gate calls it. The predicate was written twice for a while -- once where the roster
refuses an unloadable corpus at import, once where criterion 2 asks it of the forty-nine
by name -- and two spellings of one rule are two rules the day somebody edits one. The
gate's question is still worth asking after the roster's: an import error says the
corpus is broken, and this says which Playbook a reader cannot be handed.

The same for the ledger fixtures. `tests/ledger.py` holds `ledger_rows` and `written`,
which both gates' tests use to write a broken copy of the real ledger into a temporary
directory. Reading the shipped file rather than building a small one is the point: a
fixture ledger agrees with whatever its author believed, and these gates exist to catch
the day the ledger and the tree stop agreeing.

### The report is measured

Every number the report prints is counted from the ledger and the corpus, including the
four the plan also states. The gate has already refused if the two disagree, so the
output cannot differ -- but a line that prints its own expectation reads the same whether
or not anybody looked, and this one does not.

### Where the proof is

- `tests/test_coverage.py` -- 37 tests. The exact report string and its stability; that
  the gate inherits the row gate's refusals, reads no engagement state (`redkraken.pg`,
  `store`, `state`, `socket` and `ssl` are absent from a subprocess's `sys.modules`) and
  writes nothing; one class per criterion, each altering the real `Coverage` through
  `dataclasses.replace` so the failure is produced from the shipped tree rather than
  from a fixture; and `CoverageDriftTest` for criterion 6.
- `tests/test_dispositions.py` -- the row gate's own tests, now borrowing the open
  migration ticket out of the tracker instead of naming one. The literal was 56, then
  57, and each time the ticket it named was resolved the test failed on the day the
  ledger was most correct.
- `README.md` -- the fourth offline check, beside the three that were already there.
