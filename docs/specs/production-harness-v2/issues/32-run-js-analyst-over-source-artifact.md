# 32 — Run the JS analyst over a source Artifact

**What to build:** Let the JS analyst inspect a content-addressed JavaScript or source-map Artifact and propose grounded Surface or Hypothesis updates without target egress.

**Blocked by:** 30 — Promote offline Tool output through an Artifact.

**Status:** ready-for-agent

- [ ] The JS analyst receives only reachable source Artifacts, the bounded Mission packet and its allowed offline analysis capabilities.
- [ ] Its runtime has no target network capability, credential material or arbitrary Program read surface.
- [ ] Source parsing, endpoint extraction and source-map recovery run through recorded Tool runs with exact tool and input hashes.
- [ ] Proposed endpoints, parameters and hypotheses cite the source Artifact and Tool run that produced them.
- [ ] Runtime promotion rejects conclusions citing missing, changed, foreign or non-source Artifacts.
- [ ] A synthetic bundle with known routes and a secure decoy demonstrates grounded recall without invented endpoints.
