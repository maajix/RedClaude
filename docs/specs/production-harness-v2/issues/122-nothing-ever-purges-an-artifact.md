# 122 — Nothing ever purges an Artifact

**What to build:** The retention pass the schema has described since 011: read
the view that refcounts collectable bytes, drop them from the store, and stamp
`artifacts.purged_at`.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The two ends that exist are named. `artifacts_due_for_purge`
      (`0011_lifecycle.sql:15-23`, replaced at
      `20260810T173000Z__sealed_wire_artifacts.sql:139`) selects the `sha256` of
      every Artifact not yet purged that no live Program's receipts still hold.
      `artifacts.purged_at` is the column it filters on and the column a purge
      would stamp. The view has no reader in `src/` and the column has no
      writer; thirteen SQL functions mention the column and none sets it.
- [ ] The one place the design is written down is treated as the specification.
      `src/redkraken/proxy.py:2968-2980` explains why the door does not delete
      bytes itself -- "Plaintext nobody ends up referencing is retention's to
      collect -- `artifacts_due_for_purge` is the view that refcounts it across
      Programs, and no command runs one yet." That comment sits above the two
      `store.put` calls in the exchange path, and `proxy.py` is under
      concurrent edit, so find it by that sentence rather than by the line.
      The ticket decides whose command that is: an operator verb, a scheduler
      pass, or neither.
- [ ] Whether retention runs at all is decided before it is built, and the
      decision is recorded. A harness that never purges is a defensible choice
      for a tool that holds a bounded amount of evidence for a bounded time; a
      harness that declares `programs.purge_after`, builds the refcount view,
      grants it, puts `purged_at` on the agent's read surface and then never
      collects anything is not, because every one of those declarations is a
      claim that it does.
- [ ] The consequences of the current state are stated as part of the decision:
      `artifacts.purged_at` is granted to `rk2_state` and is always NULL; the
      RLS policy `artifacts_rk2_state` describes a state no row reaches; and
      `Store.discard` (`src/redkraken/store.py:173`) is the only deletion path
      in the system, deliberately narrow -- it removes only bytes the calling
      process wrote that nothing can have referenced.
- [ ] If retention ships, it is idempotent and it is safe with the store. The
      view names bytes by hash and the store is content-addressed and shared
      across Programs, so the purge that stamps the column and the delete that
      frees the bytes have to agree about which Program's reference was the last
      one. The same comment states that hazard in its own words: bytes deleted
      out from under another Program's committed reference are evidence loss.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(d) and section 6.1:
"the purge path is declared end-to-end and connected at neither end". It is one
of four views in the whole schema with no live reader, and the only one of the
four whose absence has an unbounded cost -- every wire Artifact a hunt records
is kept for the life of the database.

`needs-triage` because the missing piece is a policy decision with an operator
surface, not a wiring fix: somebody has to say when bytes go, who runs the
command, and what the harness does about a Program whose evidence bundle has not
been exported yet.

## The decision, taken 2026-08-22

**Retention ships, as two operator verbs and not as a scheduler pass -- and the
first of the two is the one this ticket does not currently name. Nothing calls
`retire_program`, so no Program is ever retired, so no evidence can ever become
due. A collector built today would collect nothing but orphans no matter how
correct it was.**

### The half the ticket is missing

`retire_program` (`0011_lifecycle.sql:5-11`) is the only writer of
`programs.purge_after` and the only writer of `programs.closed_at` anywhere in
the corpus, and **it has no caller**: `grep -rn "retire_program" src/ tools/`
returns its own definition and two comments about it. `0002_programs.sql:13` says
the column is "set by `retire_program()`, not generated", so there is no other
route.

Every arm of `artifacts_due_for_purge` is guarded by `(p.purge_after IS NULL OR
p.purge_after > now())` (`20260810T173000Z__sealed_wire_artifacts.sql:139-156`).
With `purge_after` NULL for every Program, that predicate is true for every
Program, so every receipt, every reference and every seal protects its bytes
forever. What the view can still return is the case the door's comment describes
-- plaintext stored by an exchange that never committed a receipt or a reference
-- and nothing else. **The view is not a retention pass today; it is an orphan
sweep.** That is the fact that decides the ticket's third criterion: the harness
does not "never purge" by policy, it never purges because the clock is never
started.

The same absence is visible from the operator's side. `program.lifecycle()`
(`src/redkraken/program.py:169-175`) turns the two timestamps into one of three
words -- `open`, `closed`, `retired` -- and two of the three are unreachable.
Every Program this harness has ever created is `open`, permanently.

### Why operator verbs and not a scheduler pass

Retiring an engagement is a judgement the harness has no signal for. There is no
computed source for `closed_at` anywhere in the corpus, and there could not
honestly be one: a bug bounty engagement ends because a person says it ended.
And the deletion is irreversible against evidence a person may still owe someone
-- ticket 43's export and the backup path (`src/redkraken/backup.py:65-73`, whose
`REFERENCED` union exists precisely so "a backup that carried only the labelled
half would restore a Program whose credential-bearing evidence had quietly gone")
are both operator actions. A timer that deleted bytes nobody had exported would
be the harness destroying evidence on its own initiative, which is the one thing
a tool that produces evidence must not do.

So: one verb that retires a Program and starts the ninety-day clock, and one verb
that collects what has come due. The collector may be run from the retire verb's
tail, but it is the same verb surface either way.

### Three things the collector must get right, each already stated somewhere

1. **The stamp goes through the database and the delete follows it, not the
   reverse.** `Store.discard` says so about itself
   (`src/redkraken/store.py:184-193`): "Not a general delete, and it is not the
   way an artifact is retired -- that is a purge, and it goes through the
   database ... Deleting those is safe only where no other writer could have
   arrived at the same hash, which is true of a ciphertext ... and false of
   plaintext, where another Program may already have committed a reference to
   exactly those bytes." So `discard` is not the deletion primitive for this pass,
   and the ordering is: stamp `purged_at`, commit, then unlink -- a crash between
   the two leaves a stamped row and an unreferenced file, which is recoverable,
   where the other order leaves a live row pointing at nothing, which is evidence
   loss.
2. **A sealed Artifact is not filed under the hash the view returns.** The view
   selects `artifacts.sha256`; for a wire Artifact that is the *plaintext* hash,
   which `20260810T173000Z...:102-103` calls "the identifier of the artifact this
   seal describes, and **never the name of a file**". The bytes on disk are under
   `artifact_seal.ciphertext_sha256` ("The store is filed under this"). A
   collector that unlinked the hashes the view returns would delete nothing for
   every sealed exchange and leave every envelope behind.
3. **The post-purge sweep is a different query from the view.** `0011:25-28`
   spells it out: "Purge is `DELETE FROM programs WHERE id = $1` -- every table
   above cascades, including events. Blob deletion afterwards is refcounted by
   the same `NOT EXISTS` query **with the time predicate dropped**." Those are two
   passes with two predicates, and the ticket should build the one it names rather
   than assume they are the same statement.

**Rejected: deciding that this harness does not do retention.** That answer is
available in principle -- the ticket makes the case for it -- but it would mean
deleting `retire_program`, `programs.closed_at`, `programs.purge_after`,
`artifacts.purged_at`, its RLS policy, the view, two of the three arms of
`program.lifecycle()` and the door's own comment, and it would leave the harness
with no way to say an engagement is over. Every wire Artifact of every hunt kept
for the life of the database is not a bounded cost.

## What was measured

`grep -rn "retire_program" src/ tools/` -- three hits, all in migrations, none a
call. `grep` for writers of `programs.closed_at` across the whole migration
corpus -- one statement, `0011:8`, inside `retire_program`. (The other
`SET closed_at` statements in the tree are `orchestrator_sessions` at
`20260814T010000Z...:306` and validation sessions at `20260815T180000Z...:1509`,
`:1587`, `:1646`; they are different tables.) `grep -rn "purge" src/redkraken/cli.py`
-- **zero** hits, so there is no operator surface for any of this today.

## Correction: a tool-run Artifact is protected, and the ticket's hazard is
narrower than it reads

The ticket's last criterion warns that the collector must not free bytes another
Program's committed reference still holds. True, and worth knowing that the
tool-run half of that worry is already closed by a trigger: every
`tool_run_artifacts` row must name an Artifact the Program already references --
"The Artifact has to be one this Program holds. Reachability is the reference,
never the hash" (`20260814T030000Z__an_offline_tool_becomes_evidence.sql:457-467`).
So a tool-run Artifact always has an `artifact_references` row and is protected by
the view's second arm. The live hazard is the plaintext-sharing case named in
`store.discard`'s docstring, and it is the one the ordering rule above answers.
