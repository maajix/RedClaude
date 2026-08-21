# 122 — Nothing ever purges an Artifact

**What to build:** The retention pass the schema has described since 011: read
the view that refcounts collectable bytes, drop them from the store, and stamp
`artifacts.purged_at`.

**Blocked by:** nothing.

**Status:** needs-triage

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
