---
description: Use when a JavaScript bundle is the only description of an API surface that exists.
---

# JS attack surface analysis

Second fixture skill. Minimal by design: `description` is the only required key
(Q12), and this file proves the format tolerates a skill that declares nothing
else.

Beta is the skill `probe_filter.py` withholds from the restricted agent, so a
listing that still shows it means `AgentDefinition.skills` is not filtering.
