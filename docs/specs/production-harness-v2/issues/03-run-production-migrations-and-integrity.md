# 03 — Run production migrations and the integrity gate

**What to build:** Let the operator create, upgrade and verify the complete production database through supported application commands rather than prototype shell composition.

**Blocked by:** 02 — Boot an installable `rk doctor`.

**Status:** ready-for-agent

- [ ] A supported migration command applies the complete ordered schema corpus to an empty Postgres database and is safe to rerun.
- [ ] The promoted schema uses one causal Lane vocabulary — `agent`, `replay` and `proxy_internal` — while control and transport metadata use separate types.
- [ ] Row Events are trigger-authored, direct lifecycle-cache writes are refused and writes without transaction actor context fail loudly.
- [ ] All registered schema, Event, provenance, Receipt, scope, scheduler and catalogue integrity checks run through one supported gate.
- [ ] Every hard integrity check has a negative control that demonstrably makes it fail.
- [ ] Clean creation, dump, restore and post-restore integrity all pass without `docker exec psql` or prototype runtime helpers.
