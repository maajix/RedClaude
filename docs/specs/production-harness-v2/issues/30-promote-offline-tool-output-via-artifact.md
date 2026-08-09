# 30 — Promote offline Tool output through an Artifact

**What to build:** Execute one allowlisted offline analysis tool in isolation and make its exact output usable as evidence only through a recorded Tool run and content-addressed Artifact.

**Blocked by:** 18 — Compile and enforce the six-role roster; 20 — Run one Task to a canonical Observation.

**Status:** ready-for-agent

- [ ] Tool definitions use a closed registry of executable, argument schema, version, timeout, resource ceiling and compatible roles.
- [ ] Execution occurs in an isolated runtime with no target network path unless the tool explicitly uses the proxy adapter.
- [ ] A Tool run is recorded before process start and closed on success, failure, timeout and supervisor death.
- [ ] Stdout, stderr and declared outputs become bounded content-addressed Artifacts with hashes and tool-version provenance.
- [ ] A structured Mission proposal may cite those Artifacts, but shell text alone cannot create an Observation.
- [ ] Unknown tools, extra arguments, path escape, resource overflow and foreign Artifacts fail closed with synthetic negative tests.
