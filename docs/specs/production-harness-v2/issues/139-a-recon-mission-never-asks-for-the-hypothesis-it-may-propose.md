# 139 — A recon mission never asks for the Hypothesis it may propose

**What to build:** The sentence in the recon Mission that asks for the claims a
recon run is already entitled to submit, or the recorded decision that recon
states nothing and some other role opens the first claim.

**Blocked by:** nothing. `promote_proposal` has promoted Hypotheses since
`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql`, and the
`hypotheses` element list has been on `submit_mission_result` since ticket 19.

**Status:** resolved

- [x] **What a recon run is asked for is read before it is changed.**
      `execution.py:743` composes the whole of it: *"Then call
      `mcp__rk2__submit_mission_result` once, with one observation per thing you
      actually established, each citing the Receipt the request answered with."*
      One observation per thing established, and nothing else. `MISSIONS` above
      it carries the kind's own paragraph; whichever of the two the sentence
      belongs in is part of this ticket's answer, because a Mission that
      contradicts the sentence after it is worse than either alone.
- [x] **The entitlement is established rather than assumed.** A recon run holds
      `mcp__rk2__submit_mission_result` (`roster.ROLES['recon']`), and that
      Contract's `hypotheses` element list is not narrowed by role. Six live
      hunts on 2026-08-22 confirmed it from the other side: in `rk2hunt2` a
      recon run submitted two Hypotheses unprompted and both reached promotion,
      where they were refused `claims_execution` for carrying a `status` field
      rather than for having been proposed by recon.
- [x] **The claim a recon run can honestly make is bounded.** A Hypothesis
      carries a `property_class`, a `statement`, a `rationale` answering
      mechanism, expectation and falsifier, and at least one supporting evidence
      edge or it is rolled back. A recon run has one Receipt and a handful of
      Observations, so the question this ticket answers is not "may it" but
      "which claims does one request actually ground". A Mission that invites
      more than the evidence carries manufactures `no_support` rollbacks.
- [x] **The other four hunting roles are read for the same gap.** `web_hunter`
      and `js_analyst` hold the same Contract. If their Missions ask for claims
      and recon's does not, that is a decision and it should be written down; if
      none of them ask, the gap is wider than this ticket's title.
- [x] **Whatever is decided is checked by something that would go red.** A
      sentence in a prompt is the kind of change that survives a rewrite by
      accident. The Mission text for a kind is composed in one method and is
      reachable from a test without a database or a container.

## Why

Six live hunts against a real target on 2026-08-22 (`rk2hunt` through
`rk2hunt5`) produced 47 Observations, 11 Entities and zero Hypotheses. The
harness treated that as success every time: both proposals of the last hunt were
promoted with three drops between them.

Zero is not a defect in the model's judgement. It is what the Mission asked for.
The run is told to report what it established and is never told that a claim
about what might be wrong is a thing it may file, so it files none, and every
mechanism downstream of a claim stays cold for want of an input that nobody
requested.

This ticket is small and it is first. Ticket 140 derives a hunt Task from a
testable Hypothesis; without this one there is no Hypothesis for it to derive
from, and 140 would be built against an empty table and land looking correct.

## Closing, 2026-08-22

**The sentence was missing, and it is now in the Mission rather than in the tool
description.** `execution.Slice.objective` gained a second paragraph and its
docstring gained the reason. A description says what an argument accepts; a
Mission says what the run owes back, and what a run owes back is what it
delivers.

What it now says, after the citation rule and before the Playbooks:

> An Observation is what the answer showed. A Hypothesis is what you think is
> wrong with this subject and how somebody could show you were not. File one
> wherever this answer grounds one, and file none where it does not. A claim
> carries a property_class, a statement, a rationale answering mechanism,
> expectation and falsifier, and at least one evidence edge naming an
> Observation of this run that supports it; a claim whose supporting edges do
> not survive is rolled back and takes those Observations with it. Do not say
> what state a claim is in. The runtime grades it, and a claim that states its
> own grade is refused for saying so.

It is bounded in the same breath it is asked for. The failure mode of asking is
a run that manufactures claims its one answer cannot carry, and `no_support`
rolls a claim back together with the Observations attached to it, so an invented
claim costs more than it buys. The last two sentences exist because the two
Hypotheses a recon run filed unprompted in `rk2hunt2` were both refused
`claims_execution` for carrying a `status` of `proposed`.

Placed in the shared prompt rather than in `MISSIONS['recon']`, because every
role that holds `submit_mission_result` holds the `hypotheses` element list and
none of their Missions asked for it. `MISSIONS` stays one sentence per kind,
which is what it is.

Three tests in `tests/test_execution.ObjectiveTest`: that the claim is asked for
with its parts named, that it is bounded, and that it comes after what the run
owes back rather than displacing it. `tests.test_execution` runs 145 tests, OK.
