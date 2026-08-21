# 91 — Rewrite the browser-evidence Skill with what the reading taught

**What to build:** A rewritten `src/redkraken/skills/browser-evidence/SKILL.md` that carries the four things ticket 89 found agent-browser's Skill corpus says better than ours does, written in our ten verbs, under our licence notice, with the registry digest moved to match.

**Blocked by:** nothing. Ticket 89 is resolved and ADR 0005 records why only the text was kept.

**Status:** resolved

- [x] The wait discipline is written down. Agents fail more often from a bad wait than from a bad selector, so the Skill says which wait follows which page-changing action -- after a `click` that submits, after a `navigate`, after a `fill` that triggers a live search -- in terms of `wait_for` and the selector the plan already had to name.
- [x] Every channel whose output is untrusted is enumerated, not summarised as a principle. What `capture_dom` stored, what `assert_text` matched, what a `probe` returned, what a page put in the console: each is named as content the target controls, and the Skill says what an Agent may do with it.
- [x] Troubleshooting is written as symptom, cause, next action -- not as advice. Each row is a thing the Agent will actually see (a `wait_for` that returned `matched: false`, a `navigate` with `document_loaded: false`, a run with no result digest) against the next step to take.
- [x] The first-visit sentence is carried whole, in our terms: driving a browser is the right tool for the first visit and the wrong tool for the hundredth. The Skill says what the hundredth visit is instead, which is a Tool run or a Skill script, not a mission.
- [x] The record-twice discipline is stated as ours: two runs of one plan share a `plan_sha256`, so a differing result digest is a fact about the target. The Skill says to run the plan twice before treating a difference as a finding.
- [x] Only our ten actions are named: `navigate`, `wait_for`, `fill`, `inject`, `click`, `assert_text`, `assert_absent`, `probe`, `capture_dom`, `screenshot`. No verb from anybody else's CLI appears, and nothing the Skill tells an Agent to run is outside what its roster grants.
- [x] The Apache-2.0 attribution and a statement of change are present, because the source text is Apache-2.0 and (c) 2025 Vercel, Inc. Where the notice sits is a decision this ticket makes and writes down; it is not left implicit.
- [x] The frontmatter is unchanged in meaning: same `description` intent, same `allowed-tools`, same `bb:roles`, `bb:tool_groups` and `bb:evidence_profile`. This ticket rewrites instructions, not a capability grant.
- [x] The registry follows the file. `skills.source_sha256`, `skills.version` and the `skill_dependencies` row for `SKILL.md` are updated in a new migration with the digests read out of `skill.SKILLS`, never typed from memory, and `CleanCreationTest` passes.

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

Built. `src/redkraken/skills/browser-evidence/SKILL.md` goes from 50 lines and
2,600 bytes to 187 lines and 11,798 bytes. That is the cost and it is worth
stating plainly: this file is loaded into every `web_hunter` Task that drives a
browser, so the rewrite roughly quadruples what that role reads before it starts.
The four original evidence steps are carried unchanged in substance -- write the
plan, run it behind the door, cite the run, stop on a run that did not close --
and everything added is about the failure the ticket names, which is a step that
ran before the page was ready.

The wait discipline sits in its own step rather than as advice inside step 1,
because it is a thing to do rather than a thing to know. It is written against
what the driver actually does, not against what a plan looks like:

- `click` waits internally for `Page.loadEventFired` and settles for the step
  timeout when none arrives, so a click that opened nothing and a click that
  opened something slowly both report `matched: true`. That is the whole reason
  a submitting click needs a `wait_for` after it, and the Skill says so in those
  terms.
- `fill` and `inject` dispatch `input` and `change` and return. They do not wait
  at all.
- `assert_text` and `assert_absent` are not in `HALT_ON_FALSE`, so an assertion
  that read the document too early records a `matched` about the old document
  and the mission carries on. `assert_absent` is the dangerous one, because a
  literal that has not rendered yet is absent and the step passes.

The untrusted channels are five, and five is the number because five is what a
run can bring back: the `dom`, `screenshot`, `probe` and `console` Artifact
streams, plus the two assertions, which match against a document the target
rendered. The screenshot belongs on that list for the reason the DOM does -- it
is a picture of the target's own words, and reading words out of a picture is
still reading what the target wrote. The Skill names each one as content the target wrote and states what
an Agent may do with it -- quote by Artifact hash and step ordinal, count,
compare against the other run of the same plan -- against what it may not.
`handle-untrusted-content` remains the rule; this is its list for a browser run.

The troubleshooting table is eleven rows and every symptom in the left column is
something the record or the plan actually carries: `matched: false`,
`document_loaded: false`, `http_status: 0`, `captured: false`, a truncated
Artifact, a step count below the plan's, a run with no result digest, and one
row whose symptom is a plan with a `click` and no `wait_for` after it.

The last of those is worded carefully. `close_browser_run` writes
`result_digest` on a mission it closes as `error` exactly as it does on one it
closes as `success`, and `check_browser_runs` faults a closed run that has none
-- so "a closed run with no result digest" is not a state an Agent reads. What
an Agent reads is a run with no digest, which is a run that never closed.

This is the only Skill in the corpus that carries a markdown table, and its rows
run to about 250 columns against a house width of eighty. That is a deliberate
deviation rather than an oversight: the third criterion asks for rows -- symptom,
cause, next action -- and a markdown table row cannot be wrapped without becoming
three rows. The cells were cut to the shortest wording that still says the thing.
The alternative, a prose list, is what the criterion says not to write.

Two channels do not carry a step ordinal, and the Skill says so rather than
pretending they do. `tool_run_artifacts_browser_step_ck` admits
`browser_step_ordinal` only for the `dom`, `screenshot` and `probe` streams, so
the console Artifact is the whole mission's and is cited by hash and run; and an
assertion produces no Artifact at all, only a `matched` key inside the result
digest, so it is cited by step. `http_status` is 0 rather than null on
purpose -- `rk2_browser_outcome_word` admits a boolean, a small integer or a
lowercase word, and JSON null is none of the three -- so "0" is a row an Agent
will see and not a placeholder.

Their ref-staleness rule is not carried, as the ticket asked. It has no analogue:
a plan here names CSS selectors its author wrote, and those do not expire when
the page re-renders.

**Where the notice sits, and why it is the only place.** At the foot of the body,
under its own heading. This was not a preference. `skill._compile` refuses a
frontmatter key nothing reads (`key_unknown`), so a `licence:` or `bb:notice:`
field would fail to compile; and `document.strays` refuses any file in a Skill
directory that is not `SKILL.md`, `scripts/` or `references/`, so a `NOTICE` file
beside it would fail the same way -- and a `references/` entry would have to be
declared in `bb:references`, which would move the dependency manifest and break
this ticket's own eighth criterion. Last in the body is also where it belongs on
the merits: it is addressed to whoever reads this repository, not to the Agent
working a Task. The file says all of this in its own words, so the placement is a
decision a later reader can find rather than one they have to reconstruct.

Two claims are carried close to verbatim and both are short: that agents fail
more often from bad waits than from bad selectors, and that driving a browser is
the right tool for the first visit and the wrong tool for the hundredth. The
enumeration *shape* is theirs too, and is credited as such. Everything else is
written against this harness's ten actions, its outcome keys, its Receipts and
its digests, none of which exist in the source work.

Frontmatter is byte-identical: `git diff -U0` opens at line 21, which is the
first line of the body. `description`, `allowed-tools`, `bb:roles`,
`bb:tool_groups` and `bb:evidence_profile` are untouched, and no action was added
to `browser_actions`. This is a rewrite of instructions, not a capability grant.

The registry follows in
`migrations/20260922T050000Z__a_bad_wait_fails_more_missions_than_a_bad_selector.sql`.
The digests were read out of `skill.SKILLS` rather than typed:
`source_sha256` and the `skill_dependencies` row for `SKILL.md` both move to
`b9333b50...`, and `version` -- the digest over the one-line dependency manifest --
moves to `b4b6d9d9...`. `CleanCreationTest` passes against a database built from
the corpus.

Two things in `ticket-coverage.md` were repaired here that ticket 91 did not
cause, and they are declared rather than slipped in. The "Implementation
progress" table still read `490 of 536` and `Resolved | 01-64, 66-83, 85-87,
89-90`, which is the reading from before ticket 92 was built -- the commit that
built 92 updated the structural table above it and not this one. And two
sentences said tickets 79 and 80 were open and outside the release graph; both
have been `resolved` for some time and both hang off ticket 64 like 76 through
78 and 81 through 83 do. The file's whole claim is that its numbers are the
gate's numbers on the date at the top, so a stale count in it is the defect it
exists to prevent.
