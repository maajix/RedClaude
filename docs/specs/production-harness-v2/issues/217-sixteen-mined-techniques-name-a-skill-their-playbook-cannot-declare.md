# 217 — Sixteen mined techniques name a Skill their Playbook cannot declare

**What to build:** A way for a Playbook whose reading needs `analyse-source` to
run, given that naming the Skill today costs it its executing role.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Found while closing ticket 101, and measured over the whole ledger rather than
sampled. `baseline/technique-ledger.jsonl` holds 378 records across 50
Playbooks; 98 of them name a `required_skill`.

```
20 records name a required_skill their Playbook does not carry in bb:skills
   reachable 16   blocked 3   refused 1
```

The sixteen reachable ones, by Playbook and Skill:

```
5  attack-surface             -> analyse-source
2  external-resources         -> analyse-source
2  browser-script             -> analyse-source
1  object-ownership           -> analyse-source
1  client-side-path-traversal -> analyse-source
1  jwt-jose                   -> analyse-source
1  graphql                    -> analyse-source
1  authentication             -> analyse-source
1  graphql                    -> enumerate-surface
1  cms                        -> enumerate-surface
1  cookies                    -> enumerate-surface
1  cookies                    -> compare-responses
1  ssrf-url-routing           -> enumerate-surface
```

Fourteen of the sixteen want `analyse-source`.

## Where the mechanism is

`bb:skills` is not a tool list. `tools/check_wiring.py:1271-1273` derives the
executing role from it: "the role that executes it is the one role whose Skills
are a superset of them". So a Skill added to `bb:skills` is a constraint on who
may run the Playbook, not a capability handed to it.

`src/redkraken/skills/analyse-source/SKILL.md` carries `bb:roles:
["js_analyst"]`. No other Skill in the corpus is `js_analyst`-only, and
`web_hunter` does not hold it.

Adding each ledger-demanded Skill to the Playbook that wants it was simulated
against the same derivation. Eight Playbooks come out with **no** role at all:

```
attack-surface  authentication  browser-script  client-side-path-traversal
external-resources  graphql  jwt-jose  object-ownership
```

Each of those already names a `web_hunter`-only Skill (`compare-responses` or
`use-identity`), and `js_analyst` holds neither, so no role is a superset of the
union. `check_wiring` would go red on the derivation, not on a typo.

Three -- `cms`, `cookies`, `ssrf-url-routing` -- stay `web_hunter`, because what
they are missing is `enumerate-surface` or `compare-responses`, which
`web_hunter` holds.

`supply-chain` is the only Playbook in the corpus that runs under `js_analyst`.

## Why the corpus is not wrong today

W10 (`tools/check_wiring.py:33`) holds a body to naming "only tools the
executing role holds", and it is green over all 50. Every Playbook names verbs
its role can call. `cms` and `ssrf-url-routing` reach
`mcp__rk2__get_attack_surface` through their role, which is the grant that
matters at runtime.

So this is not a rewrite defect. It is the ledger and the role split disagreeing
about which Skill a technique needs, and the ledger's `required_skill` was mined
from the source the technique came from rather than derived from this harness's
roles.

## The wall, priced

```
WALL    src/redkraken/skills/analyse-source/SKILL.md `bb:roles: ["js_analyst"]`
        plus tools/check_wiring.py:1271-1273. A Playbook naming analyse-source
        together with any web_hunter-only Skill has no role as a superset.
PRICE   Either analyse-source is granted to web_hunter -- which is the
        analyse/execute split being dropped, and roster.py plus every W10
        reading moves with it -- or the two runs hand over through an Artifact.
        mcp__rk2__get_artifact is already in both Skills' tool sets, and no
        Playbook in the corpus names it, so the handover exists as a capability
        and has never been written as a step.
PURPOSE The sixteen reachable techniques should be runnable by a Playbook.
        Fourteen of them are offline readings of the application's own shipped
        source, which is the class the harness is weakest at today.
RULE    capability before catalogue.
```

The second option looks smaller and is the one this ticket leans to: it adds a
step to eight Playbooks rather than moving a role boundary that W10, `roster.py`
and the Skill corpus all rest on. It has not been proved, which is why this is a
ticket and not a patch.

## Acceptance criteria

- [ ] **One of the two prices is paid, and the other is named where the fix
      is.** Not "granted the skill" -- which option, and what the rejected one
      would have cost.
- [ ] **The sixteen reachable records each have a Playbook that can run them.**
      Measured with the same command that produced the table above, over the
      whole ledger, not over the eight.
- [ ] **`check_wiring` stays green, W10 included.** If the fix is the Artifact
      handover, the step naming `mcp__rk2__get_artifact` is a verb the executing
      role holds.
- [ ] **The count is restated after the fix.** "N of 378 records name a skill
      their Playbook does not carry" is the number this ticket moved, and a
      ticket that does not re-measure it cannot be closed.

## What this does not change

The 50 Playbooks as landed by ticket 101. They are correct against W10 and
against the role derivation. Nothing here says a step in them is wrong; it says
sixteen mined techniques have no home.
