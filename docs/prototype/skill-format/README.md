# prototype/skill-format — evidence for map ticket 09

Not a build. This branch exists to make the ticket-09 decisions survive contact
with the CLI that actually ships, per the map's standing rule that a ticket does
not resolve on a design that never ran.

## What ran

| Component | Purpose |
|---|---|
| `validate_skills.py` | The CI half of Q8 — 12 static rules, each tagged with the decision it enforces |
| `probe_sdk.py` | Three live claims the decisions rest on (A, B/B2, C) |
| `skills/` | Two positive fixtures: one maximal, one minimal |
| `fixtures/invalid/` | One negative fixture that breaks every rule at once |
| `roles.yaml`, `evidence_profiles.yaml` | Stand-ins; tickets 11 and 06/07 own the real ones |

Environment: SDK 0.2.132 with its bundled CLI **2.1.224** (`--version` confirms),
Python 3.13. All six credential vectors from ticket 01 confirmed unset before
any run, so every result below is on the subscription path.

## Probe results

**A — unknown `bb:` frontmatter keys survive the parse.** PASS. `probe-alpha`
carries `bb:evidence_profile` and a `bb:scripts` block and still loads on
2.1.224, listed with its description intact. This was read off *minified 2.1.42*
during the grilling; the whole `bb:` namespace decision rested on a version we
do not ship. It holds.

One incidental fact worth keeping: `bb:evidence_profile` is a legal YAML key
only because no space follows the first colon. `bb: evidence_profile` would
parse as something else entirely, and `bb:notes: some text: here` fails to parse
at all unless the value is quoted — which is how the negative fixture first
failed, before it could break any of the rules it was written to break.

**B — the initialize listing does not filter.** FAIL, and the failure was mine.
With `skills=["probe-alpha"]` the initialize response's `commands` array still
contains `probe-beta`. That array is the CLI's own discovery listing, which is
not what the SDK claims to filter.

**B2 — the model's listing does filter.** PASS. Same options, but asking the
model: it lists `probe-alpha` and nothing else, and on being told to invoke
`probe-beta` it answers

> `probe-beta` is not in my available skills list (only `probe-alpha` is), and
> the Skill tool only accepts names from that listing.

So `AgentDefinition.skills` works exactly as the docstring says — a context
filter over the model's listing plus rejection at the Skill tool. B and B2
together are the sharper statement: the full inventory is still visible to the
*client* through initialize, so the filter is a steering mechanism and never a
containment one. Q3's ruling that the security boundary lives at the role's tool
list and at the network layer is what carries the weight.

**C — a PreToolUse hook on `Skill` fires and can read the name.** PASS.

```json
{"tool_name": "Skill", "skill": "probe-alpha",
 "sha256": "b4016bcf3d9608b03e5fc9dc0d5a3cf4a3d4b0f9545ba9f3aa16a45eef78cb40"}
```

The hook resolved the SKILL.md and hashed it in the same call. That single
mechanism answers two decisions: which skill to bind an evidence profile to
(Q13), and the use-time content hash that keeps a finding reproducible across a
later edit to the skill (Q9).

## Validator against the real v1 corpus

`validate_skills.py /home/majix/web-pentest-harness/.claude/skills` — 28
directories, **28 errors, 0 warnings**:

- 27 × R4 `name` is present. The key is forbidden because it creates a second
  identity beside the directory name, and the CLI uses the directory. **12 of
  the 27 have already drifted** — `access-control` declares
  `access-control-attacks`, `injection` declares `injection-attacks`, and so on
  down. Those twelve are addressed throughout v1 by a label the SDK never uses.
- 1 × R2 `families/` has no SKILL.md at all.

Both are mechanical to fix, which is ticket 17's job, not this one. The point
here is that the validator met the corpus it must accept before the format was
declared settled.

The negative fixture exercises R4, R5, R6, R7, R8, R9 and R10 in one file; R6
needs its own roster (`fixtures/invalid/roles.yaml`) because otherwise R7 fires
first and masks it.

## Reproducing

```sh
SDK=<path to extracted claude_agent_sdk 0.2.132>
chmod +x $SDK/claude_agent_sdk/_bundled/claude     # the wheel extracts without +x

python3 validate_skills.py skills --roles roles.yaml --profiles evidence_profiles.yaml
python3 validate_skills.py fixtures/invalid --roles fixtures/invalid/roles.yaml \
        --profiles evidence_profiles.yaml
python3 validate_skills.py /home/majix/web-pentest-harness/.claude/skills \
        --profiles evidence_profiles.yaml

PYTHONPATH=$SDK python3.13 probe_sdk.py a     # local stdio, no network
PYTHONPATH=$SDK python3.13 probe_sdk.py b2    # costs a model turn
PYTHONPATH=$SDK python3.13 probe_sdk.py c     # costs a model turn
```

`probe_sdk.py` pins `setting_sources=["project"]` so the operator's own
`~/.claude/skills` cannot leak into a filtering result and make it meaningless.
