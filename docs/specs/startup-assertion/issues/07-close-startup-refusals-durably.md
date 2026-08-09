# 07 — Close startup refusals without losing work

**What to build:** Turn both pre-spawn and init refusal into one durable, idempotent runtime outcome so a machine misconfiguration stops safely without stranding an agent run, consuming a task attempt or trusting prose about completion.

**Blocked by:** 05 — Corroborate init before any tool is served

**Status:** resolved

- [x] The event catalogue contains runtime-authored `startup.refused`, distinct from the LLM-authored `agent.refused`, with the exact versioned phase/runtime/violations payload from the spec.
- [x] One transaction locks the open agent run, finishes it with stop reason `refusal` and no promoted result, and emits exactly one occurrence event with matching program/run/task context.
- [x] The same transaction returns the task to `pending` without consuming an attempt, clears claim/lease timestamps, releases every identity lease and removes the `agent_sessions` binding.
- [x] Repeating cleanup for the same run is a no-op and cannot emit a second refusal event.
- [x] Pre-spawn and init refusals use the same transaction, and neither path creates a hypothesis transition, tool run or receipt.
- [x] After cleanup the supervisor accepts no new agent run and exits non-zero, preventing a retry loop against unchanged machine configuration.
- [x] A refusal before any program exists emits no invalid event, renders the same structured record to stderr and exits non-zero before SDK construction.
- [x] Event payloads and rendered diagnostics include vector names and sources but no environment, settings or credential values.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `d550fd3`, on
2026-08-09. L01-L05 prove transactional cleanup, retry idempotence, exact event
shape, released leases/session binding and zero tool or receipt residue.
