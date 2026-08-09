# 22 — Fingerprint Surface and detect change

**What to build:** Compute a deterministic Surface fingerprint after recon and record the exact deltas when the observable application surface changes.

**Blocked by:** 21 — Promote a recon Mission into typed Surface.

**Status:** ready-for-agent

- [ ] Fingerprint input is a documented canonical projection of relevant Surface rows and excludes timestamps, run identifiers and ordering noise.
- [ ] Identical Surface produces the same digest across runs and row insertion order.
- [ ] Added, removed or materially changed endpoints, parameters, technologies and identity relationships produce typed deltas and a new digest.
- [ ] Recomputing a fingerprint is an explicit runtime operation with an Event and is not a side effect of a read.
- [ ] Deltas identify the affected subjects and Property classes without declaring previous negative knowledge invalid by prose.
- [ ] Synthetic secure/vulnerable twins prove stable sameness and meaningful difference.
