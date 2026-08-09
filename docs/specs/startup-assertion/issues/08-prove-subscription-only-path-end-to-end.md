# 08 — Prove the subscription-only path end to end

**What to build:** Compose the finished startup assertion and receipt fence in the credential-free target topology and leave one offline proof that a clean agent run works while every known alternate startup path fails without zombie state, secret exposure or fabricated success.

**Blocked by:** 06 — Remove raw allowed-receipt writes; 07 — Close startup refusals without losing work

**Status:** resolved

- [x] The composed fixture runs the agent process with placeholder credentials only; the real authorization value exists solely at the proxy side of the topology.
- [x] A clean run passes pre-spawn and init checks, serves one tool request through a valid capability and records an allowed receipt whose target response is visible to the agent.
- [x] Each of the seven watched environment variables and `apiKeyHelper`, injected separately through the real launch interface, refuses before unsafe tool service and produces the exact structured effect/source.
- [x] The complete 17-case offline evidence replay remains green in the same suite, including mixed precedence cases and project-settings isolation.
- [x] The network-only `create_api_key` path is refused on the control lane and cannot produce an API key or allowed target receipt.
- [x] Refused runs leave no open agent run, claimed task, consumed attempt, live identity lease, `agent_sessions` binding, tool run or receipt; a subsequent clean restart succeeds.
- [x] Capability bypass probes fail at the database and contact no target, while the target never sees proxy authorization or a live subscription credential.
- [x] Repeating the composed proof from identical state yields the same decisions, event payload shapes and receipt relationships.
- [x] CI uses no external network, installed Claude SDK or operator credentials, and secret scanning passes over every publishable fixture and test artifact.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `d550fd3`, on
2026-08-09. `run_offline.sh` passes the 17-case replay, 16 launch tests, the
twice-reset composed proof and Gitleaks without SDK, credentials or provider
network. The full schema gate passes 41 migrations, 113 tables, 20 standing
checks and 97 assertions, including dump/restore and clean rebuild.
