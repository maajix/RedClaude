# 58 — Import v1 state without fabricating truth

**What to build:** Let an operator import a redacted v1 export for continuity and prioritization while refusing to manufacture Receipt, attempt, validation or exploitation provenance that v1 did not retain.

**Blocked by:** 34 — Retain refutation and make it due on Surface change; 36 — Create a candidate Finding from a supported Hypothesis; 57 — Close the 223-row v1 disposition ledger.

**Status:** resolved

**Reading on criterion 3:** "exact verifiable attempt/Artifact provenance" reduces to
Artifact provenance, because v1 retained no attempt provenance to be exact about. It kept
no Receipt for a request, no Tool run behind an Artifact and no Agent run behind a
Playbook choice, so there is nothing in an export for a check to be exact against. The
one thing an export can carry that is checkable without trusting it is bytes, and the
check is that they hash to the name the export filed them under. That is what decides
origin here: a row the export retained bytes for is `imported`, a row with nothing behind
it is `proposed`, and there is no third answer an export could earn.

Two limits of that reading, stated rather than buried. The first: `rk2-v1-export/1` is
defined by this ticket, so "an export carries no attempt provenance" is a decision about
the format as much as a fact about v1 -- and it is the decision, because a field for a
worker or an hour would be a field v1 filled from its own account of itself with nothing
underneath it, which is the fabrication the ticket is named after. `V-worker` is the
fixture that holds it: the record names a tester and a time, the schema reads neither, and
the hint it becomes is the same hint the six records that name nothing become. The second:
what the hash verifies is the bytes, not the association. That a Surface row points at
those bytes is the export's claim and stays the export's claim; `imported` therefore means
"the export tied this row to bytes that are the bytes it named", which is stronger than a
label and weaker than a Receipt, and is why an imported row is still not a Finding.

**Reading on criterion 3's second half:** "unverified proposals **or** retest-required
knowledge" is a disjunction and both branches are here. Surface takes the first: origin
`proposed`, which is what the runtime's own promotion writes for something nobody has
confirmed. Findings take the second: a v1 finding becomes a row in `v1_finding_hints`,
which carries a count, a ceiling and no claim -- there is no status, no leaf class and no
Finding to act on, so the only thing an operator can do with one is test the subject
again. Nothing writes a refutation. 034's negative knowledge is the record of a Test this
harness ran and found nothing, and a v1 label is not that; filing one from an export would
be the same invention in the other direction, and would make a Surface change fall due for
an attempt nobody made.

- [x] Import accepts only an explicit operator-selected export with a versioned schema and never crawls live engagement directories implicitly.
- [x] Configuration, Surface, family-level finding hints and retained non-secret Artifacts are validated, normalized and attributed to an import source hash.
- [x] Historical rows with exact verifiable attempt/Artifact provenance may retain that provenance; all others become unverified proposals or retest-required knowledge.
- [x] `confirmed`, `exploited`, `tested`, completed or exhausted labels alone cannot create supported Hypotheses, validated Findings, attempts, Receipts or pivot stamps.
- [x] Import is idempotent, Program-isolated and reports every accepted, merged, demoted, skipped and redacted record.
- [x] Synthetic fixtures include misleading terminal labels, missing workers/times, stale Artifacts, secrets and cross-Program identifiers and prove fail-closed outcomes.

## Comments

Implemented on 2026-08-17.

`src/redkraken/migrations/20260905T000000Z__v1_state_crosses_into_this_schema_as_imported.sql`,
`src/redkraken/legacy.py`, the `import` subcommand in `src/redkraken/cli.py`,
`tests/test_legacy.py`, `tests/fixtures.py::export`, `ImportCommandTest` in
`tests/test_cli.py`, and `V1ImportTest` and `V1ImportRefusalTest` in
`tests/test_database.py`.

### The module is `legacy` and the command is `import`

`import` is a Python keyword, so the module cannot be called that. `legacy` is the next
most honest name: what it reads is the previous harness's account of an engagement, and
the whole design is about how little of that account this schema is willing to adopt.

### Why the split between the reader and the writer

Criterion 1 is a property of what the reader is given, not of what it finds. `read` opens
one directory, refuses five ways an export can be wrong, and reaches no connection, no
store, no environment variable and no configuration -- which is what makes "the operator
selected this directory" the only route by which an export is ever reached.
`test_legacy` asserts that as a property of the module and not only of a run: the source
of `read` contains no `connect`, `execute`, `environ`, `getenv`, `cwd()` or `home()`, and
exactly one walk, rooted at the argument.

Everything that needs rows is `record_v1_import`'s, and the two halves run in one
transaction because they are one claim. The writer decides whether a Surface row is
imported or demoted by asking whether this Program holds an `imported` reference to the
bytes behind it, so a filing that committed without the recording would leave bytes in
the store the audit says were never taken, and a recording that committed without the
filing is refused by the writer's own check on the way in.

### The refusals are the feature

Nearly every design decision here is something the schema will not do.

`proposals.agent_run_id` and `proposals.task_id` are NOT NULL, so an import cannot route
through `promote_proposal` without fabricating an Agent run and a Task -- which is the
exact fabrication the ticket forbids. The three parentless Surface types therefore get
their own walk, with `promote_proposal`'s canonicalization copied rather than called.
Endpoints and parameters do not cross at all: a route recovered from a v1 database is a
claim about a request nothing in the export witnessed.

`v1_finding_hints` has no `property_class`, `status`, `title` or `finding_id` column, and
`check_v1_import()` watches `information_schema.columns` so a later migration cannot add
one quietly. A v1 status reaches the record's `detail` -- a sentence an operator reads --
and nothing else.

`imported` is deliberately absent from `artifact.KINDS`, which is the vocabulary
`rk artifact put --kind` offers. The one thing that turns a demoted row into imported
Surface is whether such a reference exists, so an operator able to mint one by hand could
make any claim look correlated.

A Program whose scope policy has not been compiled is refused with a HINT rather than
imported wide, because every record below is admitted on the strength of a scope class
and that Program has none to give.

An export naming one record twice is refused by name, in one pass before anything is
written. `v1_import_records` is unique on (import, kind, ref) and would otherwise refuse
the second one halfway through with a constraint name, which tells an operator holding a
bad export nothing about which record to look at.

### What is not refused, and why

Two exports of one engagement disagreeing about one artifact -- v1 pruned it between them,
or a redaction rule shipped between them -- is a disagreement between exports and not a
caller lying about what it filed. The retained/not-retained cross-check therefore asks
whether an *earlier import of this Program* accepted those bytes before it raises, and the
record says so in its own sentence. Refusing it would leave the second import unrunnable
with no way to withdraw the first.

Which of two voices for one address the export happens to list first decides nothing. The
Entity's origin lifts out of `proposed` when a correlated record joins it and never in the
other direction, and never over an origin the runtime itself established: an import is the
weakest voice in the table. Without that, the report would be a fact about the order of
rows in a file.

### What the fixtures carry

One export, in `V1ImportTest`, holding every shape criterion 6 names at once: `confirmed`
and `exploited` labels with nothing behind them, a record naming the worker and the hour
and six naming neither, an Artifact repacked around a modified body so that the manifest
agrees and v1's own row does not, a body matching the shipped `bearer` redaction rule, an
Artifact the export names and does not carry, records naming another engagement, an
address spelt `APP.example.com.`, and one address written twice in each order -- the bytes
on the second voice as well as on the first. Twenty-six records, four accepted, three
merged, six demoted, twelve skipped and one redacted, and the emptiness of `hypotheses`,
`tests`, `test_runs`, `findings`, `receipts`, `tool_runs`, `agent_runs`, `pivot_stamps`,
`pivot_proposals`, `proposals` and `tasks` asserted over the lot.

`V1ImportRefusalTest` calls `record_v1_import` directly, because what it asks about is an
account of an import that disagrees with what the database holds -- and `legacy.run` is
the thing that keeps the two in step, so a caller going through it cannot produce one. A
compromised or simply wrong caller can, which is why the writer checks rather than
trusting.
