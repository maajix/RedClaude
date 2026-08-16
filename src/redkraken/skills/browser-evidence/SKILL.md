---
description: Take evidence through a scripted browser mission that runs behind the proxy. Use when the behaviour under test needs a rendered page, a script-driven request, or a stored session that a raw exchange cannot produce.
allowed-tools: ["Skill", "mcp__rk2__get_artifact", "mcp__rk2__get_attack_surface", "mcp__rk2__get_evidence", "mcp__rk2__get_hypotheses", "mcp__rk2__get_receipts", "mcp__rk2__run_skill_script", "mcp__rk2__run_tool", "mcp__rk2__submit_mission_result"]
bb:roles: ["web_hunter"]
bb:tool_groups: ["exec.tool_run", "state.propose", "state.read"]
bb:evidence_profile: browser_run_evidence
---

# Take browser evidence

The browser is a Tool run with a plan. What the plan asked is a digest, what
happened is a digest, and a mission with only the second is a screenshot.

## 1. Write the plan before running it

Every step is a declared action with declared arguments. The plan digest is
taken over the identity slot and the ordered steps, so two runs of one mission
share it whatever they found -- which is what makes a differing result digest
evidence about the target rather than evidence that somebody edited the plan.

Complete this step with the ordered steps and the Identity slot, if any.

## 2. Run it once, behind the door

Start the mission through `mcp__rk2__run_tool`. Every request the page makes
goes through the same proxy under the same scope decision as a hand-written
exchange, and each one has its own Receipt. There is no second egress here.

While this Skill is loaded you do not hold `mcp__rk2__http_request`. That is
deliberate: a hand-crafted exchange run beside a browser mission produces a
Receipt that looks like the browser's and was not, and the two are not
distinguishable afterwards from the evidence. Finish the mission, then decide
whether a raw exchange is a separate Task.

## 3. Cite the run, not the rendering

The evidence is the closed run: its plan digest, its result digest over the
declared outcome keys, its steps, and the Artifacts each step stored. Cite those.
A description of what the page looked like is not evidence, and neither is a
screenshot nobody can re-derive.

Complete this step when the observation names the Tool run and every Artifact
hash the conclusion rests on.

## 4. Stop on a mission that did not close

A run that hit its ceiling, was refused at the proxy, or ended without a result
digest is inconclusive and is reported as inconclusive. Do not read a partial
step list as a partial result: the digest is over the whole recorded run, and a
mission that did not close has not said anything about the target.
