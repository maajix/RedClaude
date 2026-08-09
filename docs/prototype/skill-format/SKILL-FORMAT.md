# The v2 skill format

Settled by map ticket 09. Every rule below is enforced by `validate_skills.py`
or was verified by `probe_sdk.py`; see `README.md` for the evidence.

## What a skill is

A reusable procedural capability that teaches an agent *how* to approach a class
of task. It is **instruction, not code**: prose an agent reads, never a step list
a runtime executes. A runtime that executed skill steps would be proposing
actions, which breaks *LLM proposes, runtime commits* from the runtime's side and
puts it in conflict with the scheduler over who chooses the next action.

The runtime owns **gates**, not procedures: provenance, scope, budget, lane.

## Layout

```
skills/<name>/            identity is the directory name
├── SKILL.md              required
├── references/           progressive disclosure, loaded after selection
└── scripts/              deterministic code, run only via run_skill_script
```

`skills/` sits at the harness repo root — versioned with the code, visible as
source rather than buried in a dotdir — and is mounted **read-only** into the
agent container as `.claude/skills`. A skill file the agent can rewrite mid-run
is a provenance hole.

## Frontmatter

| Key | Status | Notes |
|---|---|---|
| `description` | **required** | The context pointer. Its wording decides invocation. |
| `allowed-tools` | optional | Narrows the role's tools. Never widens. |
| `bb:evidence_profile` | optional | Names a registered predicate; stricter than default only. |
| `bb:scripts` | optional | `[{name, description, args: <JSON Schema>}]` |
| `name` | **forbidden** | Second identity beside the directory; already drifted in 12 of v1's 27. |
| `model` | **forbidden** | Model policy belongs to the role. |
| `agent` | **forbidden** | Would route around the roster. |
| `context: fork` | **forbidden** | Would route around the scheduler. |

Everything else the straw-man format proposed is gone, each because an owner
already exists elsewhere: `workflow` (the agent's prose), `inputs` and `requires`
(the scheduler's readiness predicate over current rows), `outputs` (the schema),
`memory_reads` / `memory_writes` (the state-access interface), `stop_conditions`
(the proxy, the scheduler, and the state machine). A declared field nothing reads
is documentation that drifts and then lies.

The `bb:` prefix is legal because unknown frontmatter keys are ignored rather
than rejected — verified on CLI 2.1.224 — and because YAML admits a colon inside
a plain key when no space follows it. Quote any `bb:` **value** containing a
colon.

## Selection

The model chooses; the runtime constrains the menu. Per-role menus come from
`AgentDefinition.skills`, which filters the model's listing and makes the Skill
tool reject anything unlisted. A task row may carry a `skill_hint`, never a
binding.

This is **steering, not containment** — the full inventory still reaches the
client through the initialize response, and the files stay readable via Read and
Bash. The security boundary is the role's tool list plus the network layer.

## Authoring

Skills are written to the `writing-for-agents` standard: the body sits on the
information hierarchy with steps first and reference disclosed into
`references/`; the description is a context pointer that front-loads its leading
word and names one trigger per branch; prose prompts the positive rather than
banning the negative.

CI cannot check any of that. CI proves a skill is **well-formed and wired**;
review judges whether it is **good**; the eval harness judges whether it works.

## Evidence and provenance

A PreToolUse hook on `Skill` records the skill name and the SHA-256 of its
SKILL.md onto the current task row. That single record does two jobs: it binds
`bb:evidence_profile` to the transition that needs it, and it keeps a finding
reproducible after the skill is edited.

Profiles are SQL — `evidence_profile_<id>(hypothesis_id) returns boolean` in a
migration, plus a row in `evidence_profiles`. Admissibility stays a database
invariant; a skill may only tighten it. No skill, or no declared profile, means
the default applies.

Scripts run through one `run_skill_script(skill, script, args)` tool that
validates against the declared JSON Schema before spawning and writes a
provenance row. Not Bash: a Bash-executed script's output could enter state with
nothing behind it.

## Versioning

Skills are versioned with the code and referenced by name. No semver, no pinning
from playbooks — a playbook carries its own expiry and promotion lifecycle, and
pinning the two together re-couples what the skill/playbook split exists to
separate. Reproducibility comes from the use-time content hash instead; a
breaking change means a new directory, with the old one kept until playbooks
migrate. CI fails on a playbook naming a skill that does not exist.

## Validator rules

`validate_skills.py <skills-dir> [--roles] [--profiles] [--playbooks]`

R1 slug directory · R2 SKILL.md parses · R3 `description` present · R4 no
forbidden key · R5 no unknown key outside `bb:` · R6 `allowed-tools` does not
widen · R7 some role can load it · R8 profile is registered · R9 scripts exist
with valid schemas · R10 reference links resolve · R11 description is one
bounded line *(warning)* · R12 no playbook names a missing skill.
