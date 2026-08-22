# 137 — pgvector is installed by a path nothing can remove

**What to build:** The last step of ticket 127 — taking the `vector` extension
out of the provisioning path — which that ticket could not take because the
install sits in a recorded migration and the extension cannot be installed by
anyone else.

**Blocked by:** nothing. Ticket 127 removed every reader; what is left is the
install itself.

**Status:** needs-triage

- [ ] The reason it could not be done inside 127 is stated, because it is the
      whole shape of the problem. Measured from the catalogue rather than from
      an error string:

          SELECT rolname, rolsuper FROM pg_roles WHERE rolname='rk2_migrate'
            -> ('rk2_migrate', False)
          SELECT DISTINCT name, version, trusted, superuser
            FROM pg_available_extension_versions WHERE name='vector'
            -> ('vector', '0.8.6', False, True)

      `trusted=false, superuser=true` means no non-superuser may install it on
      any database. `0001_extensions.sql:2` runs `CREATE EXTENSION IF NOT EXISTS
      vector` as `rk2_migrate`, and it succeeds only because `provision()`
      installed the extension first as the superuser. Take the install out of
      `provision()` and `rk db migrate` stops at migration two.
- [ ] The four things that have to move in one change are named and moved
      together. Section 6(f) of
      `20261003T000000Z__a_key_collision_is_the_whole_of_the_trace.sql` asserts
      the extension is still present and names them in its failure text. That
      assertion is the thing this ticket turns off, and it is where the list is.
- [ ] `src/redkraken/backup.py:76-82` no longer names it. `PROVISIONED_EXTENSIONS
      = ("vector",)` is the restore side of the same install: a dump restored
      into a database whose provisioning no longer creates the extension is a
      dump restored into a database that does not have it.
- [ ] `docs/adr/0001-rows-authoritative-events-same-transaction.md:13` is
      corrected. It gives three hot paths as the reason rows are authoritative —
      recursive CTE traversal, `FOR UPDATE SKIP LOCKED`, and "pgvector
      similarity search". The third no longer exists. The decision stands on the
      other two, so this is a stale sentence rather than a withdrawn ADR, and it
      needs whoever holds `docs/adr/` rather than whoever holds the migration.

## Why

Ticket 127 removed the four embedding tables, the five `eval_*` readers' cousins
and every `hnsw.*` setting, and reported this one criterion unpaid with the
measurement above rather than working around it. Cut here so the last step has
an owner and the assertion that guards it has something to point at.
