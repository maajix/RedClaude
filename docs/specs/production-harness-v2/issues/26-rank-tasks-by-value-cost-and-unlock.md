# 26 — Rank Tasks by value, cost and unlock

**What to build:** Give the scheduler an auditable priority that balances expected finding value, success probability, time, safety cost, novelty and dependency unlock.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** ready-for-agent

- [ ] Each rank result exposes normalized value, probability, estimated time, safety cost, novelty, direct unlock and weights-version components.
- [ ] The formula and tie-breakers are deterministic for the same canonical rows.
- [ ] A low-cost Task that provably unlocks several valuable ready paths can outrank a higher isolated score.
- [ ] Unsupported or unsound dependency edges contribute zero unlock value rather than a guessed penalty or benefit.
- [ ] Operator-configured weights are versioned and changing them creates a new Ranking pass without rewriting historical passes.
- [ ] Fixture scenarios cover greedy ranking, unlock ranking, equal scores, missing estimates and bounded fallback defaults.
