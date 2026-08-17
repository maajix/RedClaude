# Production harness v2 — ticket coverage audit

Status: ticket-plan coverage complete; implementation in progress

This audit answers whether the approved ticket plan covers the production Spec
and ends in a runnable first-hunt release candidate. Coverage is a property of
the plan; the progress section below is the separate, smaller claim about what
has been built, and neither section is evidence for the other. Ticket 63 remains
the only thing that proves per-story implementation.

## Structural validation

Re-measured 2026-08-13, after tickets 67–70 were raised by the ticket-14 review,
71–73 by the ticket-18 review and 74–75 by the ticket-71 implementation and its
review, all triaged into the graph.

| Check | Result |
| --- | --- |
| Ticket files | 75, numbered continuously 01–75 |
| Ticket status | 26 `resolved`, 49 `ready-for-agent`, 0 untriaged |
| Acceptance criteria | 430 total, 150 ticked |
| Blocking edges | 134 exact title-and-number references |
| Dependency graph | Acyclic |
| Initial frontier | Ticket 01 only |
| Release reachability | Every ticket except 67–75 has a dependency path to ticket 65 |
| Absolute, scratch or issue-file paths in tickets | 0 |

Ticket 66 was added after the original 01–65 plan froze, so it did not inherit
the plan's reachability property. Ticket 62 now lists it as a blocker, which
restored it. Tickets 67–75 are in the same position and not yet resolved the
same way: each except 74 and 75 names a blocker, so none of them is a way to
start work early, but nothing downstream names them, so today they are nine sinks
beside 65 rather than work the release depends on. Whichever later ticket owns
their outcome has to list them before that claim reads "every ticket" again.

Tickets 71–73 are drift the ticket-18 review found between the compiled roster
and the scheduler that will read it: the model and effort a claimed run records,
the Identity a clamped role must hold, and the cross-role subagent cap that is
written once in `roster.py` and once as a `scheduler_weights` column. Each is
blocked by the scheduler ticket that owns the code it changes (23 and 24), which
is also why none of them was fixed under 18. Two of the three, 71 and 73, are
resolved.

Tickets 74 and 75 are what 71 found that was not 71's, and both are defects the
corpus has held since the migration that wrote them. 74: the whole-program purge
fails for a Program holding a Finding that cites a Hypothesis, because the NO
ACTION check on the rollup edge is queued ahead of the cascade that would satisfy
it. 75: `global_subagent_cap` counts the Tasks already claimed and never asks
what the claim in front of it would start, so a Program running three subagents
refuses a validate or a report that adds none. Neither names a blocker, because
nothing blocks them -- no test had reached either until a fixture claimed one
Task of every kind in one Program and then purged it. 75 is resolved: the cap is
asked only of a claim whose own lane role runs as a subagent.

Tickets 76 through 83 were raised after this re-measurement and are in none of the
counts above: the table says 75 files because that is what was measured on the
date it names. They are research and follow-up work rather than plan coverage --
76 through 78 from implementation reviews, 79 to mine public disclosures for
techniques the corpus lacks, 80 to measure the documented multiagent failure
modes against this roster, and 81 through 83 from authorised live validation
against a real target: a Program whose stored ceilings contradict each other and
could not be repaired, the door having no shipped way to run as the Agent
network's one peer, and no way to reach a claimed Task through that surface.
Like 67 through 75, nothing downstream names them, so
they are sinks beside 65 and not work the release depends on. The next
re-measurement is what moves the table, not this paragraph.

## Implementation progress

| Measure | Value |
| --- | --- |
| Resolved | 01–24, 71, 73 |
| Unblocked and open | 25, 26, 30, 31, 33, 66, 67, 68, 70, 72, 74, 75 |
| Criteria ticked | 150 of 430 |

What that covers is the foundation and the egress spine: installable runtime and
diagnostics, the migration corpus and its integrity gate, Program isolation and
bounded reads, redacted and encrypted Artifacts, compiled scope, the capability
proxy over HTTP and HTTPS, the container network boundary, lease-gated encrypted
Identities, the operator Halt and the aggregate request budget enforced at that
same door, the startup assertion imported as ticket 15, the first evidence
that arrives rather than being fetched -- one correlated callback on a declared
channel -- the first real Agent child, started through one door into that
same container boundary, a startup refusal that is now an outcome rather
than a crash -- the supervisor latches, the Task goes back to `pending` with its
attempt intact, and one redacted Event records that it happened -- and the
six-role roster, compiled against a measured SDK/CLI tool inventory and enforced
at every tool call by a pre-tool gate the permission mode cannot overrule, and
the handlers behind that roster's read and write contracts -- a Program-scoped
packet compiled outside the container and read inside it under bounds that state
their own subtraction, and one Mission result that lands as staging rows with a
recorded reason for every element whose provenance did not check out. On top of
that spine, two slices that run: one seeded Task through a real Agent run and
network Tool run to one grounded Observation, closing every lifecycle row it
opened, and promotion of a recon run's raw result into typed Surface -- eight
entity types with canonical dedup keys, a relationship grammar with its
directions enforced as a trigger, containment kept as the foreign key it is,
provenance kept per witness so parallel proposals converge without losing one,
and a compact Entity record that carries its origins, its parent and its edges
without the transcript -- and, on top of that Surface, a fingerprint of it: a
canonical projection carrying no address, no label and no identifier, one value
over it that two identically-built applications agree on, and twelve typed
deltas that name what moved, which row it was about and which Property classes
it puts back in question, recomputed by one runtime verb that records itself as
an Event, called in the transaction that promotes a recon result and reachable
from no read. And the scheduler's other half now closes: what makes a Task
claimable is one function both the offer and the claim read, so a bounded slate
of five carries the factors each entry was ranked on and when the offer stops
being one, the claim re-asks every condition inside its own transaction rather
than trusting that snapshot, the orchestrator's choice survives between two
processes as a row the runtime may refuse, choosing nothing walks down to the
first entry that still holds, and four claims at once leave one run and an
Event log that accounts for it. What that claim holds is now held on one clock:
the Task Lease and every Identity Lease the run took share a single heartbeat
that renews both or neither, releasing twice costs nothing, and a run that dies
leaves rows a named reconciliation verb -- reachable from no status read --
returns to `pending` without inventing an attempt, while a still-live owner
keeps what it holds. What that run is started at is now the roster's own: the
model and effort a claim records are two columns on `roles` the claim reads,
rather than one constant the scheduler spelled for every role that is not the
renderer, and the model is the alias the SDK is handed rather than the
resolution a version-bound manifest owns. How many subagents may run beside it
is now one number rather than two that happened to match: the runtime reads
`max_concurrent_subagents` off the weights row with the claim and the pre-tool
gate refuses at what it read, so an operator raising the cap raises what the
Slate offers and what the gate admits in one edit. The budgets and ranking
policy the scheduler is measured by, the hypothesis and validation half of the
epistemic pipeline, kill chains, the v1 knowledge migration and the operator
surface are untouched.

Two limits belong in the same breath as the number. The live database suite runs
only with `RK_TEST_SUPERUSER_URL` set and the container suite only with
`RK_TEST_CONTAINERS=1`, and the repository has no CI, so a clean checkout
enforces neither. And a ticked box records the implementer's judgement, not an
audit: ticket 63 is where per-story evidence is actually demanded.

## User-story coverage

Every numbered User Story is covered by at least one implementation slice and a
later release verification slice.

| Spec stories | Primary tickets |
| --- | --- |
| 1–25 — Program and operator control | 02, 04, 05, 08, 13, 14, 29, 59, 60, 62, 65 |
| 26–45 — Durable truth and provenance | 03–07, 09, 17, 20, 24, 33, 35, 37, 40, 43, 58, 61, 63 |
| 46–70 — Scheduling, budgets and long sessions | 22–29, 34, 41, 61 |
| 71–99 — Agent runtime and authority | 15–20, 27, 28, 30–32, 37, 42, 44, 48 |
| 100–125 — Egress, Identities and Artifacts | 07–14, 24, 31 |
| 126–150 — Surface, Hypotheses, Tests and Findings | 20–22, 30, 32–38 |
| 151–164 — Kill chains and dependency evaluation | 39–43 |
| 165–194 — Skills, Playbooks and v1 migration | 44–58 |
| 195–210 — Validation, reporting and visibility | 37, 40, 42, 43, 59, 60 |
| 211–230 — Installation, security and release | 01–03, 07, 10, 11, 15–18, 30, 31, 44–48, 57, 61–65 |

The implementation-time per-story evidence matrix is itself release-blocking in
ticket 63; range coverage here prevents a planning omission, while ticket 63
prevents a prose-only completion claim.

## Implementation-decision coverage

| Spec decision | Primary tickets |
| --- | --- |
| 1 — Product boundary and status vocabulary | 01, 02, 63, 64 |
| 2 — Highest external seam | 02, 04, 20, 59, 65 |
| 3 — Production runtime and packaging | 02, 03, 59, 62 |
| 4 — Program configuration and scope | 04, 08, 13, 14, 58 |
| 5 — Canonical state and transactions | 03–05, 17, 20, 24, 61 |
| 6 — Artifact storage and secrecy | 06, 07, 43 |
| 7 — Egress and Receipt authority | 09–14, 31 |
| 8 — Identities and target sessions | 12, 24 |
| 9 — Agent runtime and startup assertion | 15–17 |
| 10 — Role roster and tool contracts | 18, 19, 27, 30–32, 37, 42, 48 |
| 11 — Token-efficient context and session rotation | 19, 20, 28, 61 |
| 12 — Scheduler and lifecycle | 23–29, 41 |
| 13 — Surface and epistemic pipeline | 20–38 |
| 14 — Kill-chain model | 39–42 |
| 15 — Skills and Playbooks | 44–56 |
| 16 — Complete v1 corpus disposition | 01, 47–58 |
| 17 — Validation and reporting | 37, 42, 43 |
| 18 — Operator CLI and local UI | 02, 04, 05, 29, 59, 60 |
| 19 — Delivery phases and exit gates | 01–66, enforced by 63–65 |

## Testing-decision coverage

| Test obligation | Tickets |
| --- | --- |
| Highest `rk run` seam | 20, 61, 65 |
| Database, migration and negative controls | 03–07, 17, 20, 24, 35–40, 62 |
| Real HTTP/HTTPS/container boundary | 09–13, 16, 17, 31, 62 |
| Auth evidence and startup matrix | 15–17 |
| Scheduler, budgets, Leases and recovery | 23–29, 41, 61 |
| Bounded context and session rotation | 19, 28, 61 |
| Epistemic and kill-chain shortcuts | 33–43 |
| Skill and Playbook quality | 44–57 |
| Safe legacy import | 58 |
| Deterministic report and export | 42, 43 |
| Secret, restore, performance and clean-install gates | 01, 07, 43, 62 |
| Database role privilege surface | 66, re-verified on install and restore by 62 |
| Independent final review | 63, 64 |
| Full first-hunt dress rehearsal | 65 |

## Out-of-scope enforcement

| Constraint | Enforcing tickets |
| --- | --- |
| Android remains a visible future milestone, not a silent omission | 47, 57 |
| No unconfigured adjacent-host or infrastructure discovery | 08, 11, 14 |
| No ungranted destructive, availability or third-party impact | 13, 29, 38 |
| No automatic external submission | 42, 59 |
| No API-key or alternate-provider billing path | 15–17 |
| Local-first rather than distributed SaaS/multi-tenant operation | 02, 05, 62 |
| Rows remain authoritative; no event-sourced reconstruction | 03, 04, 61 |
| No automatic promotion of legacy terminal labels | 58 |
| No production generation or imports from prototypes | 01, 02, 62, 64 |

## Known prototype-regression coverage

| Regression | Tickets |
| --- | --- |
| HTTPS could bypass the capability proxy | 10, 11 |
| Replay traffic was labeled as agent traffic | 03, 35 |
| Prototype components used noncanonical Lane values | 03, 35 |
| Credential-bearing wire material was plaintext | 07, 43 |
| Actor context was session-wide rather than transaction-local | 03, 04 |
| The composed startup proof mocked the claimed process seam | 16, 17, 20 |
| Startup refusal did not latch the supervisor | 17 |

## v1 corpus reconciliation

| v1 inventory | Planned disposition tickets | Required total |
| --- | --- | --- |
| Agent definitions | 18, 48, 57 | 11 |
| Skill directories | 44, 48, 57 | 28 |
| In-scope Playbooks | 45, 46, 49–57 | 49 |
| Android Playbooks | 57 | 10 explicit retirements |
| Absorbed Playbook topic | 57 | 1 reference disposition |
| Operator references | 48, 57 | 112 linked references |
| Sink packs | 48, 57 | 9 linked packs |
| Reserved files | 47, 57 | 3 explicit dispositions |
| Legacy engagement state | 58 | unverified or retest-required unless exact provenance survives |

The eight Playbook batches reconcile to all 49 in-scope topics:

| Ticket | Topics |
| --- | ---: |
| 49 — Recon/API/protocol | 7 |
| 50 — Authentication/Identity | 8 |
| 51 — Authorization/business logic | 4 |
| 52 — Browser/client side | 8 |
| 53 — Injection | 7 |
| 54 — Server/file/disclosure | 7 |
| 55 — Platform/supply chain | 5 |
| 56 — HTTP integrity/parsing | 3 |
| **Total** | **49** |

## First-hunt readiness

Ticket 65 is not a documentation-only finish. Its acceptance path starts from a
fresh installation and must exercise scoped recon, production Skill and Playbook
selection, a meaningful negative result, a real fixture Finding through replay
and blind validation, a sound and an intentionally unsound chain, restart/resume,
deterministic reporting and standalone evidence verification.

Ticket 65 is blocked by the remediated final review, which is blocked by the
230-story implementation audit, hardening gates, full operator product,
long-campaign recovery and every upstream implementation slice. Therefore a
green ticket 65 implies a runnable harness suitable for configuring the first
authorized live test hunt; it cannot be reached by completing only prototypes,
schema work or catalogue files.

## Verdict

**PASS at ticket-plan level**, re-confirmed at 66 tickets. The approved
dependency graph covers the complete production Spec, the complete planned v1
knowledge migration and an end-to-end first-hunt release outcome. Thirteen
tickets are resolved and the remaining fifty-three carry the runtime
functionality; ticket 63 is still what proves implementation evidence for every
story, and nothing in this file substitutes for it.
