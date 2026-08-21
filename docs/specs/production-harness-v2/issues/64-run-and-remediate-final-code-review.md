# 64 — Run and remediate the final code review

**What to build:** Review the complete production diff independently against repository Standards and the production Spec, fix every actionable release blocker and prove the review is clean enough to hunt.

**Blocked by:** 63 — Audit Spec, ticket and implementation coverage; 67 — Give an inbound arrival its own identity; 68 — Make an installed harness be the code it claims; 69 — Publish engagement files on an out-of-band host whose name changes; 70 — End a canary from the command line; 71 — Run a role at the roster's model and effort; 72 — Hold an Identity for every run that uses one; 73 — State the cross-role subagent cap once; 74 — Purge a Program whose Finding cites a Hypothesis; 75 — Refuse a claim for the concurrency it would actually spend; 76 — Read engagement secrets from 1Password; 77 — Evaluate carbonyl as a terminal browser for the Agent; 78 — Grade a Playbook with a real Agent behind the door; 79 — Mine public disclosures for techniques the corpus does not have; 80 — Measure the multiagent failure modes this harness can actually have; 81 — Repair a Program whose stored ceilings disagree; 82 — Run the door as the Agent network's one peer; 83 — Open the first Task of a Program; 85 — Hold the Agent network between the check and the launch; 86 — Give each Agent run its own home.

**Status:** resolved

- [x] The fixed review point predates production implementation and the reviewed head contains every completed ticket and coverage artifact.
- [x] Independent Standards and Spec reviews inspect the production runtime, schema, topology, tests, catalogue, UI, migration and operator surface rather than prototype code alone.
- [x] Every finding records severity, exact source location, violated contract, evidence and remediation.
- [x] All HIGH and MEDIUM findings are fixed with regression coverage or explicitly block release; LOW findings are fixed or dispositioned transparently.
- [x] Targeted and full validation rerun after remediation, including secret, containment, migration and long-campaign gates.
- [x] A final review pass reports no unresolved HIGH or MEDIUM finding and confirms that no production path imports or executes a prototype.

## The review

**The review point.** `135c63a` -- `DOCS: resolve production baseline ticket` --
which is the commit before `76b6bd3`, `FEAT: boot an installable rk doctor`, the
first commit in this history to add `src/redkraken/`. Everything after that
point is production implementation and nothing before it is, so a review fixed
there sees the whole of what ships. The prototypes the sixth criterion asks
about are all earlier than it: `8403027` and `9d5b97e` are the two labelled
throwaway, and nothing under `src/` imports either.

**What was reviewed.** The tree at the reviewed head rather than a diff against
it -- the runtime modules, the migration corpus, the container topology, the
tests, the Playbook and Skill catalogue, the console, the migration runner and
the operator surface. Two axes, run so that neither could see the other's
report: Standards against `CLAUDE.md`, `CONTEXT.md`, the ADRs and
`src/redkraken/migrations/README.md`, Spec against `spec.md` and the ticket
criteria.

**What it found.** 79 findings, one per row in `baseline/final-review.tsv`,
each with severity, location, violated contract, evidence and remediation: 22
HIGH, 30 MEDIUM, 27 LOW, 48 on the Spec axis and 31 on Standards. 67 are fixed
and every one of them names the run that holds it; 12 LOW are dispositioned with
the reason in the row and `-` where a run would be. Two findings were larger
than a review can close and became tickets 87 and 88.

**One severity is a judgement and is recorded as one.**
`one-playbook-has-no-fixture-to-be-graded-against` read as MEDIUM on a first
pass and is carried at LOW. The grounds are in the row: `playbooks/http-desync`
ships `draft`, a draft Playbook is never promoted, and `check_playbook_tests`
reports `draft_playbook_untestable` against it on every run, so nothing untested
is presented as tested and what is missing is coverage, which ticket 88 owns. A
reader who disagrees with the grade should read it as a MEDIUM that blocks
nothing an operator can reach.

**The rerun.** The whole suite, with containers, against a real server:

```
RK_TEST_SUPERUSER_URL=... RK_TEST_CONTAINERS=1 \
RK_TEST_AGENT_IMAGE=python:3.14-slim RK_TEST_BROWSER_IMAGE=rk2browser:test \
.venv/bin/python3 -m unittest discover -q
```

3400 tests, `OK (skipped=4)`, in 1636 s. The six gates --
`check_baseline`, `check_dispositions`, `check_coverage`, `check_secrets`,
`check_audit`, `check_intake` -- all pass. The five performance budgets are
measured in that run and printed by it; the slate, which failed the rerun before
`20260922T020000Z` turned JIT off for `offer_slate()`, reports 1159.8 ms against
1500 ms.

The long-campaign gate is ticket 65's, not this one's: it is a run against a
real target, and a person makes it. This ticket resolves with `owed:65`
outstanding in `baseline/spec-verification.tsv`, which is exactly that statement.
