# 02 — Add a capability-backed receipt path beside legacy writes

**What to build:** Add the expansion half of the receipt fence: an allowed tool run can be authorised through the database, receive a short-lived egress capability, and use a database-owned receipt writer without breaking existing serving paths yet.

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] A runtime-only database operation evaluates the existing pure tool gate and stamps the resulting decision; callers cannot write the decision column directly.
- [x] Only an active `allow` decision mints a cryptographically random 256-bit capability, and canonical state stores only its SHA-256 digest.
- [x] Capability resolution binds program, tool run, open parent agent run and current task lease when a task exists.
- [x] A database-owned writer derives the receipt's tool-run link and decision from a resolved capability instead of accepting an `allowed` literal.
- [x] Missing, fabricated, cross-program, inactive and expired capabilities are refused by the new path.
- [x] No plaintext capability appears in events, receipts, database state or diagnostic output.
- [x] The legacy receipt writer remains available during this expansion ticket, and the ticket makes no claim that bypass is closed until ticket 06 contracts it.
- [x] Existing receipt, engagement and tool-gate checks remain green alongside focused positive and negative tests for the new path.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `3cb8cd0`, on
2026-08-09. PostgreSQL owns gate stamps and five-minute 256-bit capabilities;
only SHA-256 reaches canonical state. K01-K04, all 86 schema assertions, the
dump/restore lifecycle, 11 launch tests and diff-only Gitleaks are green. The
walking-skeleton capability paths pass; its three remaining failures are the
pre-existing scheduler/state-surface divergences recorded by that prototype.
