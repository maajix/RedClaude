# 19 — Serve bounded MCP reads and Mission proposals

**What to build:** Give an executing role compact Program-scoped context and one structured outbound proposal path without granting direct authority over canonical state.

**Blocked by:** 05 — Prove Program isolation and bounded reads; 18 — Compile and enforce the six-role roster.

**Status:** ready-for-agent

- [ ] State read tools expose only the current Program's labelled Surface, Hypotheses, evidence, Receipts and reachable Artifacts under explicit bounds.
- [ ] Every bounded response carries revisions, digests, counts and omission markers so truncation cannot look complete.
- [ ] The single Mission-result operation accepts structured proposed Entities, Relationships, Observations, Hypotheses, evidence edges, suggested Tasks and a completion claim.
- [ ] Mission results write only staging rows; no executing role can promote, validate, report or set Task lifecycle directly.
- [ ] Observation proposals referencing absent, foreign or incompatible provenance are retained as rejected staging outcomes rather than canonical truth.
- [ ] Closed schemas reject unexpected free text and Program identifiers before handler execution.
