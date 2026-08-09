# 04 — Create or resume a Program with the same command

**What to build:** Make `rk run` create a Program from validated configuration on first use and resume the same durable Program on later use without transcript or in-memory state.

**Blocked by:** 03 — Run production migrations and the integrity gate.

**Status:** ready-for-agent

- [ ] The first `rk run` persists one Program, its configuration revision and source hash in one actor-attributed transaction.
- [ ] The same command with the same Program identity resumes existing rows and does not create a duplicate Program.
- [ ] Configuration drift is detected before execution and produces an explicit revision or refusal rather than silently replacing policy.
- [ ] Program creation and resume each emit exactly one correctly typed Event with no secret configuration values.
- [ ] Readiness failure before Program creation leaves the database unchanged; failure afterward leaves a durable, inspectable outcome.
- [ ] The command returns only durable identifiers, lifecycle, stop reason, pending decisions and an integrity summary.
