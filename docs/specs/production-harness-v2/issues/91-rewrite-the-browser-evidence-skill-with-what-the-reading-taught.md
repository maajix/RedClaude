# 91 — Rewrite the browser-evidence Skill with what the reading taught

**What to build:** A rewritten `src/redkraken/skills/browser-evidence/SKILL.md` that carries the four things ticket 89 found agent-browser's Skill corpus says better than ours does, written in our ten verbs, under our licence notice, with the registry digest moved to match.

**Blocked by:** nothing. Ticket 89 is resolved and ADR 0005 records why only the text was kept.

**Status:** ready-for-agent

- [ ] The wait discipline is written down. Agents fail more often from a bad wait than from a bad selector, so the Skill says which wait follows which page-changing action -- after a `click` that submits, after a `navigate`, after a `fill` that triggers a live search -- in terms of `wait_for` and the selector the plan already had to name.
- [ ] Every channel whose output is untrusted is enumerated, not summarised as a principle. What `capture_dom` stored, what `assert_text` matched, what a `probe` returned, what a page put in the console: each is named as content the target controls, and the Skill says what an Agent may do with it.
- [ ] Troubleshooting is written as symptom, cause, next action -- not as advice. Each row is a thing the Agent will actually see (a `wait_for` that returned `matched: false`, a `navigate` with `document_loaded: false`, a run with no result digest) against the next step to take.
- [ ] The first-visit sentence is carried whole, in our terms: driving a browser is the right tool for the first visit and the wrong tool for the hundredth. The Skill says what the hundredth visit is instead, which is a Tool run or a Skill script, not a mission.
- [ ] The record-twice discipline is stated as ours: two runs of one plan share a `plan_sha256`, so a differing result digest is a fact about the target. The Skill says to run the plan twice before treating a difference as a finding.
- [ ] Only our ten actions are named: `navigate`, `wait_for`, `fill`, `inject`, `click`, `assert_text`, `assert_absent`, `probe`, `capture_dom`, `screenshot`. No verb from anybody else's CLI appears, and nothing the Skill tells an Agent to run is outside what its roster grants.
- [ ] The Apache-2.0 attribution and a statement of change are present, because the source text is Apache-2.0 and (c) 2025 Vercel, Inc. Where the notice sits is a decision this ticket makes and writes down; it is not left implicit.
- [ ] The frontmatter is unchanged in meaning: same `description` intent, same `allowed-tools`, same `bb:roles`, `bb:tool_groups` and `bb:evidence_profile`. This ticket rewrites instructions, not a capability grant.
- [ ] The registry follows the file. `skills.source_sha256`, `skills.version` and the `skill_dependencies` row for `SKILL.md` are updated in a new migration with the digests read out of `skill.SKILLS`, never typed from memory, and `CleanCreationTest` passes.

## Why this is asked

ADR 0005 declined agent-browser and kept its prose, and the prose has to land
somewhere or the decision was a paragraph. Four things in their `core` Skill and
their `trust-boundaries` reference are better written than what
`src/redkraken/skills/browser-evidence/SKILL.md` says today, and none of them is
about Rust or about a daemon. They are about how an agent that drives a browser
gets things wrong.

Our Skill is fifty lines and every one of them is about evidence: write the plan,
run it behind the door, cite the run, stop on a run that did not close. That is
correct and it stays. What it does not say is anything about the failure an Agent
will actually hit first, which is a step that ran before the page was ready and
an assertion that read a document that had already moved on.

## What their text has that ours does not

Read out of `skill-data/core/SKILL.md` and `references/trust-boundaries.md`, both
Apache-2.0:

- **Waits, named per action.** Their claim, which matches what our own step lists
  look like when they go wrong: bad waits cause more failures than bad selectors.
  They follow it with a short list of which wait to pick after which
  page-changing action. Ours says nothing about waiting at all.
- **Untrusted output, enumerated.** Not "treat page content as untrusted" but a
  list: snapshot text, console messages, network response bodies, error overlays.
  A list is checkable and a principle is not.
- **Troubleshooting as symptom, cause, next command.** Three columns, no prose.
  An Agent reading it mid-run can find its own symptom.
- **`derive-client`'s one sentence:** driving a browser is the right tool for the
  first visit and the wrong tool for the hundredth. That is a scoping rule this
  harness needs more than they do, because our browser run is expensive: a
  container, a plan digest, a step list and a reconciliation against Receipts.
- **Record twice.** Theirs is about flaky pages. Ours is stronger and already
  true by construction, and the Skill never says so: the plan digest is fixed, so
  the second run's result digest is the measurement.

Their ref-staleness rule has no analogue here. Their refs go stale because a
snapshot hands out `@eN` handles that a re-render invalidates; our plans carry
CSS selectors the plan author wrote, which do not expire. That part is not
carried.

## The boundary this ticket does not cross

The rewrite is a file of instructions. It does not:

- add an action to `browser_actions`, which is a migration and a driver change
  and a different ticket;
- widen `allowed-tools`, which is a capability grant;
- tell an Agent to run anything a roster does not already give its role;
- describe a compact page representation. ADR 0005 left that open as a possible
  new action with its own declared outcome keys, measured first. Until somebody
  measures it, the Skill describes `capture_dom` and nothing else.

## The licence, which is settled and still has to be written

agent-browser is Apache-2.0, "Copyright 2025 Vercel, Inc." Apache-2.0 permits a
derivative in a differently licensed work provided the notice travels and the
changes are stated. This ticket carries both. It does not copy their sentences
wholesale where ours would say it better; the two places worth carrying close to
verbatim are the bad-waits claim and the first-visit sentence, and both are short
enough to quote and attribute.

## Comments
