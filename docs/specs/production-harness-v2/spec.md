# RedKraken v2 production bug-bounty hunting harness

Status: ready-for-agent

## Problem Statement

The existing web-pentest harness has found real bugs, but its durable state is
not trustworthy enough over long campaigns. Agent prose, transcript history and
terminal labels can drift away from what was actually attempted, observed,
reproduced or exploited. That makes completed work look untested, untested work
look complete, and loosely related findings look like proven kill chains.

RedKraken v2 has already explored the hard parts through specifications and
prototypes: a Postgres domain model, receipt-backed egress, a startup assertion,
an agent roster, a scheduler, playbook selection, evaluation fixtures,
promotion, validation and kill-chain rules. Those artifacts proved or falsified
individual decisions, but they are not a runnable product. The repository does
not yet contain an installable production runtime, production entrypoint,
complete agent roster, complete skill catalogue or converted playbook corpus.
Several prototype boundaries also have known correctness defects and therefore
cannot be promoted by copying them.

The operator needs one functioning, local-first web and API bug-bounty hunting
harness that can run and resume long campaigns, keep scope and credentials out
of model control, spend the configured token and request budgets, preserve
evidence-backed truth, build and evaluate kill chains, and retain the useful
knowledge from v1 without retaining v1's transcript-driven state mistakes.

Completion must mean more than a green walking skeleton. It means the runtime,
operator surface, agents, skills, playbooks, evaluation corpus, migration path,
security controls and long-session recovery all exist in production form and
are exercised through the same interfaces the operator will use.

## Solution

Build RedKraken v2 as an installable local application whose highest external
seam is one idempotent operator operation: run the configured Program. The
operation creates a new Program when none exists and resumes its durable state
when it does. The CLI and local UI are adapters over the same runtime operation;
neither owns campaign truth.

Postgres rows are authoritative. Every state-changing row write and its Event
are committed in the same transaction. Agents receive bounded Mission packets,
may read only program-scoped views, and may submit only proposals. The runtime
alone claims Tasks, promotes proposals, starts Tests, changes epistemic state,
validates Findings and constructs reportable kill chains.

All target traffic crosses a single-egress proxy. A request is admitted by a
short-lived capability bound to its Program, Agent run, Tool run, Lane and live
leases. The proxy writes the authoritative Receipt, strips credentials before
the agent sees the response, and stores credential-bearing wire material only
as encrypted Artifacts. HTTP and HTTPS follow the same path. Runtime-authored
transport observations that cannot be made faithfully through interception use
an explicit proxy-internal Lane rather than borrowing an agent Receipt.

The Claude Agent SDK is started only through the runtime-owned
`agent_run(request)` interface. The agent container has no API key or usable
subscription credential. A version-bound startup assertion checks the exact
effective environment, settings and bundled CLI before transport construction,
then corroborates the first init message before serving tools. A refusal is a
fatal supervisor outcome and is reconciled durably without consuming a Task
attempt.

Six production roles divide authority: orchestrator, recon, web hunter, source
analyst, validator and deterministic reporter. Skills describe executable
capabilities, never vulnerability families or campaign workflows. Playbooks
describe investigation knowledge, select by Property class and surface facts,
reference only loadable Skills, carry provenance and expiry, and must pass both
positive and adversarial fixture evaluation before becoming stable.

The complete v1 knowledge surface is handled through a hash-addressed migration
ledger. Every v1 Agent definition, Skill directory, Playbook, operator reference
and sink pack receives an explicit disposition and replacement. The existing
web/API scope converts all 49 in-scope v1 Playbooks, absorbs references and sink
packs into the new knowledge structure, rewrites surviving capability Skills,
and records the planned retirement of Android-only material rather than silently
dropping it.

Long campaigns remain correct because no transcript is authoritative and no
model session is required to survive. Orchestrator sessions and worker Agent
runs have hard turn, token and context ceilings and may be rotated. The next
session receives a newly compiled, bounded view of canonical rows, revisions,
digests and omission markers. Crash recovery, rate-limit recovery, operator Halt
and ordinary resume all reconcile from current rows.

## User Stories

### Program and operator control

1. As an operator, I want to start a Program through one command, so that I do not need to compose internal scripts or database calls.
2. As an operator, I want the same command to resume an existing Program, so that recovery does not depend on remembering a different workflow.
3. As an operator, I want Program configuration validated before any Agent run or network request, so that malformed policy fails without side effects.
4. As an operator, I want one versioned scope policy per Program, so that every runtime decision uses the same scope definition.
5. As an operator, I want inclusions, exclusions, ports, protocols and path restrictions represented explicitly, so that scope is not inferred from prompts.
6. As an operator, I want Rules of Engagement represented as typed controls, so that mutation, credential use, pivoting and availability impact are independently governable.
7. As an operator, I want availability-impact actions denied unless an explicit grant exists, so that ordinary autonomy never becomes a denial-of-service test.
8. As an operator, I want exact target headers configured outside model-visible state, so that required program identifiers can be injected without exposing their values.
9. As an operator, I want callback and out-of-band channels declared explicitly, so that the runtime never invents adjacent infrastructure or hosts.
10. As an operator, I want Program configuration hashed and recorded, so that every result can identify the policy under which it was produced.
11. As an operator, I want configuration changes to invalidate affected assumptions, so that old scope or identity facts are not reused silently.
12. As an operator, I want a diagnostic command that checks runtime versions, database state, proxy readiness, container isolation and catalogue integrity, so that a broken machine fails before spending tokens.
13. As an operator, I want database migrations to be explicit and repeatable, so that upgrades are auditable and recoverable.
14. As an operator, I want to Halt a Program immediately at the egress door, so that already-running agents cannot continue sending requests after the stop.
15. As an operator, I want only an operator action to clear a Halt, so that an Agent cannot resume a stopped Program.
16. As an operator, I want risky or ambiguous work parked as a pending decision, so that the campaign can continue elsewhere without guessing my intent.
17. As an operator, I want pending decisions to use stable reason codes, so that the UI and audit trail do not depend on free-form prose.
18. As an operator, I want request, token, concurrency and time-window budgets configured per Program, so that cost and safety limits are enforceable.
19. As an operator, I want separate quotas for recon, hunting, analysis, validation and replay Lanes, so that one workload cannot starve the rest.
20. As an operator, I want compact status views with stable labels and revisions, so that I can understand a long campaign without loading its history.
21. As an operator, I want full records retrievable by stable label, so that compact views never force permanent information loss.
22. As an operator, I want the local UI and CLI to show the same canonical state, so that neither develops its own interpretation of completion.
23. As an operator, I want every operator mutation to produce an Event, so that manual intervention is as auditable as runtime action.
24. As an operator, I want multiple Programs isolated in one installation, so that a label, hash or identity from one Program cannot access another.
25. As an operator, I want backup and restore procedures exercised in CI, so that durable state is recoverable rather than merely persistent.

### Durable truth and provenance

26. As an auditor, I want rows to be authoritative and Events to prove the writes, so that state is not reconstructed from incomplete transcripts.
27. As an auditor, I want each row mutation and its Event committed in one transaction, so that audit state cannot lag canonical state.
28. As an auditor, I want trigger-authored row Events, so that a new application call site cannot forget to emit one.
29. As an auditor, I want actor, Agent run, Task and trace context set transaction-locally, so that pooled database connections cannot misattribute work.
30. As an auditor, I want occurrence Events for refusals, resumes, rate limits and Halts, so that important outcomes without rows remain visible.
31. As an auditor, I want every Observation backed by a runtime-generated provenance record, so that model prose cannot become canonical truth.
32. As an auditor, I want every claim of attempted work bound to an exact Agent run and Task attempt, so that terminal labels cannot float free of execution.
33. As an auditor, I want every network-backed Observation tied to an authoritative Receipt, so that a request described in prose is not treated as a request that occurred.
34. As an auditor, I want every offline Observation tied to a Tool run and content-addressed Artifact, so that shell output alone is not evidence.
35. As an auditor, I want agent-seen and wire-seen request hashes recorded separately, so that credential injection is visible without exposing credentials.
36. As an auditor, I want dependencies and invalidations rechecked whenever a claim is read as verified, so that once-valid evidence cannot remain valid after its basis changes.
37. As an auditor, I want an unsound or incomplete derived graph reported as unsound, so that an empty graph is never interpreted as proof of no chain.
38. As an auditor, I want legacy records without attempt provenance imported as unverified, so that migration does not fabricate historical evidence.
39. As an auditor, I want status transitions represented as append-only transition rows, so that the reason and evidence for each transition survive.
40. As an auditor, I want cached status columns maintained by database rules, so that direct status writes cannot bypass transition requirements.
41. As an auditor, I want redaction policy stored once and applied to Events, diagnostics and reports, so that a second copy cannot drift and leak secrets.
42. As an auditor, I want integrity checks registered and runnable as one gate, so that schema, event, provenance, receipt and catalogue corruption are found together.
43. As an auditor, I want integrity checks to include negative controls, so that a permanently green check cannot masquerade as protection.
44. As an auditor, I want canonical state reads to be non-mutating, so that status inspection cannot recover leases or alter the campaign.
45. As an auditor, I want all timestamps, identities and source hashes retained with their records, so that reports remain attributable after a long campaign.

### Scheduling, budgets and long sessions

46. As a scheduler, I want pending Tasks ranked deterministically from canonical rows, so that the same state and weights produce the same order.
47. As a scheduler, I want ranking to include expected value, success probability, time cost and dependency unlock value, so that the fastest path to bugs can outrank isolated work.
48. As a scheduler, I want the runtime to offer a bounded Slate, so that the orchestrator never controls the whole queue.
49. As a scheduler, I want the orchestrator to choose only within the offered Slate, so that model judgement cannot bypass safety filters.
50. As a scheduler, I want the runtime to revalidate readiness, budget, Lane quota, scope and identity availability at claim time, so that a stale Slate cannot authorize work.
51. As a scheduler, I want a deterministic fallback when the orchestrator chooses nothing, and a refusal rather than a substitution when it chooses off-Slate, so that poor model output cannot stall the campaign and a choice nobody made is never answered.
52. As a scheduler, I want each Task protected by an expiring Lease, so that concurrent workers cannot execute the same attempt.
53. As a scheduler, I want each Identity protected by an exclusive Lease, so that two hunters cannot mix target sessions.
54. As a scheduler, I want Task and Identity Leases for one Agent run to share a heartbeat, so that partial liveness cannot strand one resource.
55. As a scheduler, I want startup refusal to return a Task to pending without consuming an attempt, so that machine configuration is not counted as target testing.
56. As a scheduler, I want crash reconciliation to close or recover interrupted Agent runs idempotently, so that restart cannot duplicate work or leave zombies.
57. As a scheduler, I want request and token reservations made before work starts, so that concurrent runs cannot overspend a shared budget.
58. As a scheduler, I want actual usage reconciled after each Agent run and Tool run, so that reservations do not become permanent phantom spend.
59. As a scheduler, I want rate-limit responses to schedule a durable retry time, so that agents do not spin inside a transcript.
60. As a scheduler, I want retries bounded by typed policy, so that repeated environmental failure cannot create an infinite loop.
61. As a scheduler, I want negative knowledge and unchanged Surface fingerprints to suppress redundant Tasks, so that the system does not retest the same dead end.
62. As a scheduler, I want a changed Surface fingerprint to make affected refutations due again, so that stale negative knowledge does not hide a new bug.
63. As a scheduler, I want validated pivots to unlock dependent Tasks, so that kill-chain potential influences scheduling.
64. As a scheduler, I want Agent runs to have hard token and turn ceilings, so that one session cannot consume the whole campaign.
65. As a scheduler, I want orchestrator sessions rotated at configured ceilings, so that a logical campaign does not depend on an indefinitely growing conversation.
66. As a scheduler, I want a new orchestrator session to receive only a bounded state capsule, so that transcript replay is unnecessary.
67. As a scheduler, I want every Mission packet to carry revisions, digests and omission markers, so that bounded context remains honest about what it excludes.
68. As a scheduler, I want no prior worker transcript inherited by a new Agent run, so that stale narrative cannot become current authority.
69. As a scheduler, I want concurrency enforced by runtime counters and durable quotas, so that prompt instructions are not the safety mechanism.
70. As a scheduler, I want fairness between ready Lanes after hard constraints, so that continuous hunting cannot permanently starve validation or reporting.

### Agent runtime and authority

71. As a maintainer, I want one runtime-owned `agent_run(request)` interface, so that every SDK launch crosses the same assertion and cleanup path.
72. As a maintainer, I want the runtime to construct the exact effective environment and SDK options, so that callers cannot validate one configuration and launch another.
73. As a maintainer, I want SDK and bundled CLI versions pinned to measured pairs, so that undocumented auth behavior changes fail closed.
74. As a maintainer, I want version upgrades to require a sanitised auth-resolution probe, so that a constant cannot be edited without new evidence.
75. As a maintainer, I want the child process to inspect its own effective environment, so that supervisor intent cannot hide a scrubbing defect.
76. As a maintainer, I want managed settings scanned and unrelated user or project settings excluded, so that operator configuration cannot silently widen the run.
77. As a maintainer, I want pre-spawn checks to aggregate all safely observable violations, so that remediation does not require repeated one-error starts.
78. As a maintainer, I want the first CLI init message corroborated before any tool is served, so that an unexpected auth source cannot make a target request.
79. As a maintainer, I want startup refusal to latch the supervisor fatally, so that unchanged bad configuration cannot be retried in the same process.
80. As an operator, I want no API key configured, stored or read by the harness, so that subscription-only operation cannot silently become metered API use.
81. As an operator, I want the agent container to hold no usable subscription credential, so that model-controlled code cannot exfiltrate it.
82. As an operator, I want the real authorization value confined to the control-side proxy adapter, so that target authentication works without entering Agent context.
83. As a runtime, I want one closed production roster, so that built-in or newly introduced agent types cannot be invoked accidentally.
84. As a runtime, I want the orchestrator to have state and scheduling tools but no target network capability, so that planning cannot become unrecorded testing.
85. As a runtime, I want recon agents limited to discovery Tasks, so that broad enumeration remains distinguishable from hypothesis testing.
86. As a runtime, I want web hunters limited to proposed state plus receipt-backed execution, so that they cannot promote their own conclusions.
87. As a runtime, I want JS analysts limited to content-addressed source Artifacts and offline tools, so that white-box analysis cannot create unreceipted target traffic.
88. As a runtime, I want validators started as independent top-level sessions, so that they cannot see the hunter's reasoning lineage.
89. As a runtime, I want validators to receive a column-allowlisted packet with no free-text smuggling field, so that verdicts are based only on canonical evidence.
90. As a runtime, I want reporting performed by a deterministic renderer, so that a model cannot invent report facts.
91. As a runtime, I want every role's tools, Skills, models, effort, turns and concurrency compiled from one roster, so that declarations and enforcement cannot diverge.
92. As a runtime, I want a pre-tool hook to deny calls outside the compiled role, so that tool visibility is not mistaken for enforcement.
93. As a runtime, I want subagent spawning attributed and capped, so that built-in delegation cannot escape the roster.
94. As a runtime, I want no model-facing tool to accept a Program identifier, so that a caller cannot select another Program.
95. As a runtime, I want no model-facing tool to read or set credentials, environment variables or settings, so that billing and identity remain runtime-owned.
96. As a runtime, I want structured tool contracts with closed argument schemas, so that hidden free-text authority cannot be smuggled into handlers.
97. As a runtime, I want arbitrary shell output unable to create Observations, so that granting local analysis tools does not weaken provenance.
98. As a runtime, I want every Tool run recorded before execution and closed afterward, so that missing or interrupted calls remain visible.
99. As a runtime, I want Agent completion claims treated as proposals, so that prose never marks a Task or Finding terminal.

### Egress, identities and artifacts

100. As an operator, I want all agent-originated HTTP and HTTPS traffic forced through one proxy, so that no target exchange lacks policy enforcement and a Receipt.
101. As an operator, I want raw TCP, external DNS and alternate proxy paths unavailable from the agent container, so that model-controlled tools cannot route around the proxy.
102. As an operator, I want scope canonicalized and checked against the actual outbound request, so that redirects, alternate encodings and DNS changes cannot reuse an earlier decision.
103. As an operator, I want the proxy to pin and revalidate resolved addresses, so that DNS rebinding cannot turn an in-scope name into an out-of-scope destination.
104. As an operator, I want redirects and browser subresources independently authorized, so that one allowed page cannot open arbitrary egress.
105. As an operator, I want a short-lived random capability for each allowed Tool run, so that an Agent cannot fabricate an allowed Receipt.
106. As an operator, I want only a capability digest in canonical state, so that database or diagnostic output does not reveal the bearer value.
107. As an operator, I want capabilities bound to Program, Agent run, Tool run, Lane and live leases, so that reuse across work is refused.
108. As an operator, I want capabilities cleared when a Tool run finishes, parks, denies or aborts, so that stale authorization cannot be replayed.
109. As an operator, I want proxy authorization stripped before forwarding, logging and persistence, so that it never reaches the target or evidence bundle.
110. As an auditor, I want allowed and blocked exchanges represented by distinct database-owned writers, so that a caller cannot label its own request allowed.
111. As an auditor, I want allowed Receipts rejected unless their active Tool run and capability are valid, so that even a privileged fixture loader cannot open the hole silently.
112. As an auditor, I want Lane restricted to `agent`, `replay` or `proxy_internal`, so that causal provenance has one vocabulary.
113. As an auditor, I want control-channel and transport claims represented separately from Lane, so that unrelated concepts cannot broaden causal provenance.
114. As an auditor, I want a replay Receipt provably emitted by a replay capability, so that validation traffic cannot be mislabeled as agent traffic.
115. As an auditor, I want proxy-internal observations identified explicitly, so that TLS and protocol facts are not attributed to an intercepted agent view.
116. As an operator, I want Identity names exposed to agents but credential material retained by the proxy, so that an Agent can choose a role without holding its secret.
117. As an operator, I want cookies and target credentials stored encrypted and scoped to one Identity, so that session reuse does not leak across identities or Programs.
118. As an operator, I want credential-bearing wire bodies and headers encrypted at rest, so that the Artifact store does not become a plaintext secret archive.
119. As an operator, I want decrypted wire Artifacts unavailable to Agents by default, so that evidence retention does not widen model access.
120. As an operator, I want agent-visible Artifacts redacted and content-addressed, so that exact bytes can be cited without exposing injected secrets.
121. As an operator, I want browser navigation, XHR, fetch and subresource traffic to use the same egress policy, so that browser automation is not a second network path.
122. As an operator, I want screenshots, DOM captures and source bundles linked to the Receipts that produced them, so that browser evidence remains attributable.
123. As an operator, I want external callback observations accepted only from configured channels with correlation tokens, so that unrelated inbound traffic cannot confirm a hypothesis.
124. As an operator, I want per-target rate limiting enforced at egress, so that concurrent agents cannot exceed the aggregate request budget.
125. As an operator, I want Program Halt checked at egress for every request, so that already-issued capabilities cannot outlive a stop.

### Surface, hypotheses, tests and Findings

126. As a recon agent, I want discovered Domains, Hosts, Services, Applications, Endpoints, Parameters, Technologies and Identities stored as typed Entities, so that later work has stable subjects.
127. As a recon agent, I want typed Relationships separated from containment, so that graph meaning is not hidden in generic edges.
128. As a recon agent, I want duplicate surface proposals merged by runtime rules, so that parallel discovery does not multiply the same Entity.
129. As a recon agent, I want source and runtime provenance attached to each discovery, so that imported and observed surface can be distinguished.
130. As a scheduler, I want a Surface fingerprint recomputed after recon, so that material change can invalidate negative knowledge.
131. As a hunter, I want Hypotheses named by one subject and Property class, so that proposed bugs deduplicate on domain meaning rather than prose similarity.
132. As a hunter, I want near matches visible before proposing a Hypothesis, so that parallel agents can extend existing work instead of duplicating it.
133. As a hunter, I want refuted Hypotheses returned with their conditions and evidence, so that I do not repeat a settled negative test blindly.
134. As a hunter, I want to propose structured evidence edges with polarity and role, so that baselines, variants and controls remain distinguishable.
135. As a runtime, I want only the runtime to move a Hypothesis into testing, so that a hunter cannot claim execution before a Test run exists.
136. As a runtime, I want supported, refuted and inconclusive outcomes derived from Test assertions and evidence, so that status does not depend on narrative confidence.
137. As a test author, I want each Test to contain typed preconditions, setup, actions, assertions and cleanup, so that it is executable and reviewable.
138. As a test author, I want request actions represented structurally rather than as shell strings, so that scope, identity and risk can be checked before execution.
139. As a test author, I want control and variant actions explicit, so that a single interesting response cannot establish a vulnerability.
140. As a test author, I want mutation cleanup verified against authoritative after-state, so that tests do not leave target or fixture state ambiguous.
141. As a validator, I want a Finding to reference its Hypotheses and reproducing Test runs, so that validation evaluates the claimed vulnerability rather than adjacent traffic.
142. As a validator, I want replay performed through the same proxy and Receipt path under the replay Lane, so that reproduction is independently attributable.
143. As a validator, I want a Finding unable to become validated without a holding replay of its own Test, so that evidence from another claim cannot promote it.
144. As a validator, I want failed assertions and insufficient evidence recorded without destroying the candidate, so that the runtime can schedule the missing work precisely.
145. As a validator, I want invalidated dependencies to return a Finding to review rather than silently leave it validated, so that truth follows its evidence.
146. As an operator, I want only a human action to move a validated Finding to reported, so that submission remains deliberate.
147. As an operator, I want exploit impact distinguished from detection, so that a safe confirmation is not labeled as destructive exploitation.
148. As an operator, I want higher-risk exploitation represented as a separate Task with its own grant and Test, so that discovery authority does not imply detonation authority.
149. As an operator, I want rejected Findings retained with reasons, so that repeated false positives can improve playbooks and scheduling.
150. As an operator, I want severity derived from demonstrated impact and program context, so that banners or generic errors cannot inflate it.

### Kill chains and dependency evaluation

151. As a hunter, I want a proposed pivot to name the exact capability it provides and preconditions it requires, so that chaining is structural rather than rhetorical.
152. As a runtime, I want a pivot accepted only when a validated Test run demonstrates the transition, so that inferred reachability cannot license a chain.
153. As a runtime, I want kill-chain members linked by stable Finding and Test identifiers, so that edits to summaries do not change graph identity.
154. As a runtime, I want chain edges derived from validated member state and proved pivots, so that Agents cannot write arbitrary chain edges.
155. As an auditor, I want chain soundness to include member validity, Artifact integrity, scope, identity, grants and invalidations, so that one stale link cannot leave the chain green.
156. As an auditor, I want cyclic, disconnected or vocabulary-invalid chains refused, so that graph shape remains interpretable.
157. As an operator, I want a chain represented as a reportable Finding composition, so that it follows the same validation and reporting discipline as an individual bug.
158. As an operator, I want chain severity based on demonstrated end impact without double-counting member impact, so that aggregation is defensible.
159. As a scheduler, I want a chain's missing precondition translated into candidate Tasks, so that the graph can guide the next useful test.
160. As a scheduler, I want marginal unlock value included in ranking, so that a modest pivot that unlocks several high-value paths can outrank an isolated lead.
161. As a validator, I want each member and pivot reproducible independently when full-chain replay would be unsafe, so that safety does not force an ungrounded chain claim.
162. As a reporter, I want the rendered chain to distinguish demonstrated steps from explicitly bounded inference, so that the report never overstates end-to-end execution.
163. As an operator, I want review gates on chain rendering, so that sensitive or high-impact chains remain unrenderable until cleared.
164. As an operator, I want chain invalidation propagate from any invalid member or pivot, so that reports cannot retain a broken composition.

### Skills, Playbooks and v1 knowledge migration

165. As a maintainer, I want Skills to describe executable capabilities rather than vulnerability families, so that role grants and Playbook requirements have operational meaning.
166. As a maintainer, I want campaign workflows implemented by the scheduler rather than Skills, so that an instruction document cannot own lifecycle state.
167. As a maintainer, I want vulnerability families represented by Property classes and Playbooks, so that routing knowledge is not duplicated in Skill names.
168. As a maintainer, I want each Skill versioned, hash-addressed and validated in CI, so that a Mission packet records the exact instruction used.
169. As a maintainer, I want deterministic Skill logic placed in scripts with runnable checks, so that prompts are not used for work code can perform.
170. As a maintainer, I want Skills unable to widen a role's tool surface, so that loading instruction cannot grant authority.
171. As a maintainer, I want every Playbook to reference existing Skills, Property classes, trigger facts, risk effects and evidence expectations, so that it is selectable and testable.
172. As a maintainer, I want every stable Playbook loadable by at least one role holding all required Skills, so that the catalogue contains no dead entries.
173. As a maintainer, I want Playbook selection driven by Property class, surface facts, role, risk ceiling, conflicts and expiry, so that the model does not read the whole corpus.
174. As a maintainer, I want a strict small cap on selected Playbooks per subject, so that context remains bounded even when the catalogue grows.
175. As a maintainer, I want the selected Playbook text and Skill hashes recorded on the Task, so that later evaluation knows what actually ran.
176. As a maintainer, I want edited or expired Playbooks excluded from new Tasks until reevaluated, so that old evidence does not bless new text.
177. As a maintainer, I want Playbook promotion require runtime provenance and passing fixture evaluation, so that a verified date in imported prose cannot self-promote.
178. As a maintainer, I want every Playbook evaluated against positive and adversarial negative fixtures, so that recall alone cannot make it pass.
179. As a maintainer, I want fixture ground truth independent from the Playbook under test, so that an author cannot write both the answer and the grading rule.
180. As a maintainer, I want repeated fixture results aggregated deterministically, so that one stochastic success cannot promote unstable knowledge.
181. As a maintainer, I want ungrounded claims and off-class findings fail a Playbook, so that a Playbook that always fires is detected.
182. As a maintainer, I want stale, failing or newly untestable Playbooks demoted automatically, so that the stable catalogue stays honest.
183. As a maintainer, I want the v1 corpus inventoried by kind, path and hash, so that completeness is measured against an exact source set.
184. As a maintainer, I want every one of the 223 inventoried v1 artifacts assigned a disposition, replacement and test, so that nothing disappears accidentally.
185. As a maintainer, I want all 11 v1 Agent definitions mapped to the production roster or an explicit scope retirement, so that useful lenses survive without preserving unsafe authority.
186. As a maintainer, I want all 28 v1 Skill directories rewritten, absorbed, superseded or retired according to the migration ledger, so that file count is not confused with capability coverage.
187. As a maintainer, I want all 49 in-scope v1 Playbooks authored in the v2 format, so that the production harness retains its web and API hunting knowledge.
188. As a maintainer, I want the remaining v1 Playbook topic absorbed or explicitly retired, so that the 60-topic census balances exactly.
189. As a maintainer, I want all 112 operator references and 9 sink packs linked into Playbooks or Skills, so that deep technique material remains reachable without entering every Mission packet.
190. As a maintainer, I want the 10 Android-only Playbooks, two Android Skills and one Android Agent recorded as out of current scope, so that their absence is deliberate and reversible.
191. As a maintainer, I want CI to fail when the live v1 corpus gains or changes an unclassified artifact, so that the migration ledger cannot silently become stale.
192. As a maintainer, I want no engagement state, credentials, raw captures or target secrets copied into the v2 test corpus, so that knowledge migration does not become data leakage.
193. As a maintainer, I want v1 findings used only as prioritization evidence at family granularity, so that missing Playbook and Skill provenance is not fabricated.
194. As a maintainer, I want imported v1 terminal states demoted or correlated to exact retained evidence, so that historical drift is not inherited as truth.

### Validation, reporting and operator visibility

195. As a validator, I want the validation packet built from an empty structure and an explicit column allowlist, so that new fields cannot leak hunter reasoning accidentally.
196. As a validator, I want no network, shell, source tree or exploit tools, so that judgement cannot alter the target or collect new evidence invisibly.
197. As a validator, I want verdict choices closed to confirmed, refuted or insufficient with failed assertion identifiers, so that free-form confidence cannot mutate state.
198. As a runtime, I want a verdict treated as input to database-enforced transitions rather than direct authority, so that evidence constraints still decide the outcome.
199. As a reporter, I want reports rendered only from validated rows, so that every statement has a canonical source.
200. As a reporter, I want deterministic output for the same rows, so that report diffs reveal state changes rather than model variation.
201. As a reporter, I want optional narrative constrained to identifiers already present in rendered rows, so that rephrasing cannot introduce a new host, path or parameter.
202. As a reporter, I want each Finding include reproduction, controls, impact, scope, evidence references and remediation context, so that the result is submission-ready.
203. As a reporter, I want each evidence bundle contain redacted agent-view material and verifiable hashes, so that an external reviewer can confirm integrity without receiving credentials.
204. As an operator, I want dashboards to distinguish proposed, attempted, observed, supported, validated, exploited and reported states, so that no single green badge hides provenance depth.
205. As an operator, I want unsound state, stale Playbooks, invalid Artifacts and overdue validation visible as first-class warnings, so that silence is not interpreted as health.
206. As an operator, I want current Agent runs, Tasks, Leases, budgets and pending decisions visible without transcript access, so that operations remain compact.
207. As an operator, I want a Finding and chain graph navigable through stable identifiers, so that related evidence can be followed without reading every Agent response.
208. As an operator, I want reports exportable without the runtime database, so that submission artifacts remain usable after campaign shutdown.
209. As an operator, I want UI summaries treated as cacheable projections, so that a failed summarizer cannot change or hide canonical state.
210. As an operator, I want no automatic external submission, so that disclosure remains a deliberate human act.

### Installation, security and release quality

211. As a maintainer, I want one installable Python application with pinned runtime dependencies, so that production behavior is not assembled from prototype directories.
212. As a maintainer, I want one supported local container topology for Postgres, proxy, agent and fixtures, so that security claims refer to a reproducible deployment.
213. As a maintainer, I want production code unable to import from documentation or prototype trees, so that experiments cannot become hidden dependencies.
214. As a maintainer, I want secrets supplied through runtime-owned secret mounts or environment injection outside Agent visibility, so that configuration files remain publishable.
215. As a maintainer, I want logs structured and redacted by default, so that debugging does not leak capabilities, cookies, authorization or target data.
216. As a maintainer, I want offline unit and integration tests to require no provider network or operator credential, so that every commit can be checked safely.
217. As a maintainer, I want live provider probes separated, explicit and version-bump-only, so that ordinary CI never spends subscription tokens.
218. As a maintainer, I want all fixtures synthetic and locally hosted, so that tests cannot touch a real bounty target accidentally.
219. As a maintainer, I want secret scanning cover tracked and publishable unignored files, so that generated or moved fixtures are not missed.
220. As a maintainer, I want static checks reject direct SDK construction outside the Agent runtime, so that the startup assertion has one enforceable seam.
221. As a maintainer, I want static checks reject direct Receipt inserts and direct network clients outside approved adapters, so that alternate paths cannot emerge quietly.
222. As a maintainer, I want HTTP and HTTPS containment proven from inside the real agent container, so that proxy environment variables are not mistaken for isolation.
223. As a maintainer, I want fault injection around every durable transition, so that a crash before or after commit has a specified idempotent outcome.
224. As a maintainer, I want a long synthetic campaign repeatedly rotate sessions and restart processes, so that correctness does not depend on one healthy transcript.
225. As a maintainer, I want bounded-context assertions measure the serialized Mission packet and orchestrator capsule, so that token efficiency is a release property.
226. As a maintainer, I want performance checks cover Slate computation, graph traversal, catalogue selection and compact reads at realistic corpus sizes, so that durable truth does not make the harness unusably slow.
227. As a maintainer, I want clean database creation, migration upgrade, dump, restore and integrity checks exercised together, so that schema evolution is production-ready.
228. As a maintainer, I want the complete synthetic vertical slice executed twice from identical state, so that decisions and relationships are reproducible.
229. As a maintainer, I want every known prototype defect retained as a regression test, so that promotion cannot reintroduce a falsified claim.
230. As a maintainer, I want a final Standards and Spec review against the production diff, so that prototype completion is never again reported as product completion.

## Implementation Decisions

### 1. Product boundary and status vocabulary

- Existing experiments remain evidence and prior art. Production modules never
  import from or execute a documentation, scratch or prototype tree.
- A prototype may be `explored`, `validated` or `falsified`. Only installable
  runtime code exercised through production adapters may be `implemented`.
- The existing startup-assertion work is treated as a validated prototype until
  its behavior is promoted through the production Agent runtime and the composed
  acceptance test.
- Temporary experiments may be built under `/tmp`. No `/tmp` artifact is a
  deliverable or dependency.

### 2. Highest external seam

- The primary interface is `run(program_reference) -> run_outcome`. The operator
  CLI exposes it as `rk run`; the local UI invokes the same application
  operation. A Program with existing durable state resumes automatically.
- `run_outcome` reports only durable identifiers, current lifecycle, stop reason,
  pending decisions and integrity summary. Full records are fetched separately
  by stable identifier.
- Diagnostic, migration, import and report commands are supporting operator
  interfaces. They do not implement alternate campaign runtimes.
- End-to-end acceptance tests cross the `rk run` seam. Internal tests cross a
  lower seam only when the behavior belongs to a true external dependency or a
  security boundary that needs focused negative controls.

### 3. Production runtime and packaging

- The product is one installable Python application, one Postgres schema and a
  local container topology. Python is retained because the validated SDK,
  proxy and fixture work already uses it; a second application language would
  add an unnecessary seam.
- The runtime is split into deep modules with small interfaces: Program runtime,
  State, Agent runtime, Egress, Knowledge catalogue, Evaluation and Reporting.
  Callers use domain verbs rather than table-shaped repositories.
- Adapters exist only where behavior genuinely varies: real versus fake SDK,
  real versus synthetic target transport, and production versus isolated test
  process. Internal implementation helpers are not promoted to public ports.
- The CLI uses the standard library unless a production dependency already
  provides the necessary behavior. Configuration parsing, validation and error
  rendering stay centralized.
- Runtime dependencies, Claude Agent SDK and bundled CLI expectations are pinned.
  A dependency lock and reproducible container images are release artifacts.

### 4. Program configuration and scope

- Program configuration is versioned, declarative, validated and hashed before
  persistence. Secret values are references to runtime-owned secret material,
  never inline values returned by reads.
- One compiled scope policy is used by configuration validation, proxy egress,
  callback admission, browser automation and report rendering.
- Scope contains positive targets and explicit exclusions. It does not authorize
  DNS enumeration, certificate-transparency discovery, reverse-IP discovery,
  virtual-host probing or adjacent hosts unless they are explicitly present.
- Rules of Engagement are typed fields for mutation, sensitive-data access,
  credential use, pivoting and availability impact. An absent permission is a
  denial.
- Required headers are injected at the proxy. Agent-visible policy exposes their
  names, never their values.
- Every configuration revision records its source hash and invalidates dependent
  surface or epistemic state through explicit runtime operations.

### 5. Canonical state and transactions

- Postgres rows are the sole authority. Events are an append-only completeness
  proof and audit trail, never the state reconstruction path.
- Row Events are emitted by database triggers. State-changing runtime operations
  begin an explicit transaction and set Program, actor, Agent run, Task, trace
  and causal Event context with transaction-local settings.
- Occurrence Events are inserted explicitly by the runtime for outcomes without
  a source row. Their schemas are registered and validated.
- Program-scoped rows derive Program from the runtime-bound database session.
  Model-facing calls cannot name a Program. Database roles and row-level policy
  enforce isolation rather than post-filtering results.
- Domain transitions are append-only rows. Cached lifecycle fields are maintained
  and guarded by database logic. Direct terminal-state updates are refused.
- The validated migration corpus is promoted into the production migration set
  only after vocabulary conflicts and review findings are corrected. Migration,
  restore and standing-integrity runners become supported application commands,
  not shell composition around a container.

### 6. Artifact storage and secrecy

- Artifacts are addressed by the SHA-256 hash of their plaintext and referenced
  from Program-scoped rows. Storage may deduplicate globally; reachability never
  does.
- Credential-bearing Artifacts use authenticated encryption with key material
  outside the database and outside Agent-visible configuration. Ciphertext,
  nonce, algorithm version and plaintext hash are stored; plaintext is released
  only to explicitly authorized runtime adapters.
- Agent-view and wire-view Artifacts are separate references. Redaction is never
  represented by overwriting the authoritative wire Artifact.
- Logs, Events and diagnostics may carry identifiers, lengths and digests but not
  capabilities, authorization values, cookies, secret headers or decrypted wire
  bytes.

### 7. Egress and Receipt authority

- The agent container has one reachable network peer: the proxy. Raw internet,
  target container networks, external DNS, provisioning ports and control ports
  are inaccessible from the agent network namespace.
- HTTP and HTTPS clients receive explicit proxy and trust configuration. The
  runtime adapter configures both schemes and tests both; environment variables
  alone are not considered containment.
- Every target exchange resolves a short-lived capability and rechecks canonical
  scope, DNS/IP policy, Program Halt, budget, Lane, Tool run state and Leases at
  the time of egress.
- The canonical Lane vocabulary is exactly `agent`, `replay` and
  `proxy_internal`. Control traffic and transport-claim metadata use separate
  fields and types.
- Allowed Receipts can be created only through the capability-backed database
  writer. Blocked attempts use a different writer that cannot create an allowed
  Receipt.
- The proxy database role has no raw Receipt insert privilege. A database
  invariant rejects any allowed Receipt whose capability, Tool run, Program,
  Agent run, Task or Lane binding is invalid.
- One capability may cover independently checked redirects or subresources of
  one Tool run. It is cleared on every terminal Tool run path.
- Proxy authorization is held only in memory, stripped before target forwarding
  and excluded from Receipt and Artifact material.
- TLS certificate, protocol and cipher claims that interception would distort
  are produced by a proxy-internal runtime probe with their own Receipts and are
  never inferred from the agent-side MITM connection.

### 8. Identities and target sessions

- An Identity is a named Entity and proxy upstream slot. Agents receive labels
  and non-secret metadata only.
- Credential acquisition and session provisioning are operator- or runtime-owned
  control operations. They cannot be invoked through hunter tools.
- Cookie jars, authorization material and client certificates remain encrypted
  on the proxy side and are isolated by Program and Identity.
- A live Identity Lease is required before its slot is used. The proxy rechecks
  the Lease rather than trusting a previously captured decision.
- Agent responses have target credentials removed. When removal changes bytes,
  both agent-view and wire-view hashes record the transformation.

### 9. Agent runtime and startup assertion

- `agent_run(request)` is the only external interface of the Agent runtime. It
  constructs the child environment, runtime-owned settings directory, SDK
  options and bundled CLI path; runs the startup assertion; opens the transport;
  corroborates init; serves tools; and performs durable cleanup.
- The supervisor passes a positive environment allowlist plus runtime-owned proxy
  and CA settings. SDK `env` cannot append watched variables after inspection,
  and setting sources are explicit and isolated.
- Known SDK/CLI pairs and credential vectors are data derived from a sanitised
  evidence manifest. Unknown versions, missing bundled binaries, malformed
  settings and every observed or conservative vector fail closed.
- The pre-spawn phase runs before SDK transport construction. The init phase must
  be the first message and must report the expected no-key source before any
  tool schema or handler becomes available.
- A refusal produces one structured `startup.refused` occurrence Event when a
  Program exists; closes the Agent run; returns its Task without consuming an
  attempt; releases Identity and Task Leases; clears session bindings; latches
  the supervisor; and exits non-zero. Repeating cleanup is a no-op.
- A refusal before Program creation writes no invalid Event and exits before SDK
  transport construction.

### 10. Role roster and tool contracts

- The production roster contains six roles:
  - `orchestrator`: runtime-started model session; reads state and chooses from a
    Slate; cannot contact targets or execute technique Skills.
  - `recon`: orchestrator-started worker for scoped surface discovery.
  - `web_hunter`: orchestrator-started worker for hypothesis and Test work.
  - `js_analyst`: orchestrator-started worker for offline source, JavaScript
    and source-map Artifacts.
  - `validator`: runtime-started independent model session with one blind packet
    and a closed verdict tool.
  - `reporter`: deterministic renderer with no model, turns or tools.
- The roster is one source for model, effort, turn ceiling, role kind, task kinds,
  builtin tools, MCP groups, Skill grants, concurrency and invocation authority.
- Tool visibility narrows context but is not enforcement. A pre-tool gate
  attributes the call, checks the compiled roster and denies every unlisted tool,
  role or delegation even if the SDK permission mode would otherwise allow it.
- Model-facing tool schemas are closed. Program selection, credentials, raw SQL,
  arbitrary process creation and direct canonical writes are absent.
- State reads are bounded and include omission markers, revisions and digests.
  State proposals write only staging rows. Scheduling and promotion verbs remain
  runtime authority.
- Arbitrary local analysis may be available through an isolated tool runner, but
  its output becomes evidence only through an Artifact-backed Tool run and
  runtime promotion.

### 11. Token-efficient context and session rotation

- Mission packets are compiled from canonical rows for one Task and contain its
  objective, scope subset, budgets, relevant positive and negative knowledge,
  stop conditions, revisions, digests and omission markers. The selected
  Playbooks arrive with the objective and the role's Skills are staged into the
  child's launch directory: both are read before the first turn rather than
  fetched during it, and a packet carrying a second copy would be a second
  statement of what the run was given. Identity is not among them. Which
  Identity a request is sent under is bound to the Tool run by the database at
  the moment the capability is minted, so a packet naming one would be naming a
  choice the child does not make.
- Mission packets have a configured serialized byte and estimated-token ceiling.
  Large Artifacts and full records are fetched by stable identifier rather than
  embedded.
- Worker Agent runs are fresh sessions. They do not inherit the orchestrator or
  earlier worker transcript.
- The runtime offers a bounded Slate of five Tasks. The orchestrator sees compact
  value, probability, cost, risk and unlock factors, not the entire queue.
- The ADR decision that the runtime offers and commits while the orchestrator
  chooses remains. Its earlier assumption of one indefinitely long orchestrator
  session is amended: sessions rotate at configured turn, token or decision
  ceilings, and logical continuity comes only from rows.
- Rotation emits an occurrence Event and starts a new session from a compact
  capsule. No summary generated by the old session is authoritative.

### 12. Scheduler and lifecycle

- Ranking passes are deterministic and clock-free given rows and a weights
  version. Eligibility is evaluated separately from ranking.
- The runtime offers the top five ready, Lane-legal, affordable,
  identity-available Tasks. A claim transaction rechecks all filters and uses a
  deterministic fallback.
- Task and Identity Leases use database time, one heartbeat and idempotent
  release. Lease recovery is a runtime operation, never a side effect of reads.
- Token, request and Lane budgets use reservations before concurrency is admitted
  and reconcile actual usage on completion or abort.
- Retryable environmental outcomes schedule durable retry timestamps. Refusal,
  policy denial, inconclusive evidence and target-negative results remain distinct
  outcomes.
- Ranking includes direct value, probability, estimated time, safety cost,
  novelty and marginal dependency unlock. Each component and weights version is
  returned for audit.
- A validated pivot may create or unlock Tasks through runtime rules. A proposed
  chain never changes readiness by itself.

### 13. Surface and epistemic pipeline

- Agents submit one Mission result containing proposed Entities, Relationships,
  Observations, Hypotheses, evidence edges, suggested Tasks and a completion
  claim. It is staging data, not canonical truth.
- Promotion validates stable labels, Program reachability, scope, Receipts,
  Artifacts, Tool runs, schema, vocabulary, duplicate cells and transition
  preconditions in one transaction.
- Observations are immutable. Evidence is an edge from an Observation to a
  claim, with polarity and baseline/variant/control role.
- A Hypothesis is unique by Program, subject, Property class and relevant
  Identity cell. Its lifecycle changes only through transition rows.
- Negative knowledge retains refutation conditions, Surface fingerprint and the
  delta that makes retest due.
- Tests are immutable executable specifications. A revision creates a new Test.
  Actions are typed request or tool specifications, never shell strings.
- Test runs reserve budgets, use replay capabilities, produce Receipts and
  Artifacts, evaluate assertions deterministically and record an outcome.
- Findings reference their Hypotheses and validating Test runs. Candidate,
  validating, validated, rejected and reported transitions are database-guarded;
  reported remains human-only.
- Severity and exploit state are separate from validation. Demonstrated impact
  requires its own authorized Test and evidence.

### 14. Kill-chain model

- A pivot claim names `requires`, `provides`, subject, Identity, scope and safety
  conditions. A runtime-authored pivot stamp is issued only from a holding Test
  run that demonstrates the transition.
- A kill chain is a derived composition of member Findings and stamped pivots.
  Agents may propose membership but cannot write canonical edges or verdicts.
- Chain integrity rechecks member validation, pivot stamps, dependencies,
  Artifacts, Receipts, invalidations, scope and review gates on every reportable
  read.
- A reportable chain uses the Finding validation/reporting discipline and cannot
  be rendered while any required member, pivot or review gate is unsound.
- Full-chain detonation is not required when it would exceed Rules of Engagement.
  Independently reproduced members and pivots may establish composition, but the
  report must distinguish this from an executed end-to-end chain.
- Marginal unlock value is derived from sound dependency edges and feeds the
  scheduler without becoming canonical evidence of exploitability.

### 15. Skills and Playbooks

- A Skill is executable capability instruction. Skill names describe actions
  such as surface enumeration, identity pairing, response comparison, browser
  evidence, source analysis or untrusted-content handling; they do not duplicate
  Property-class families.
- Deterministic behavior lives in checked scripts or runtime tools. Skill prose
  explains judgement and use of those capabilities.
- Skill metadata declares compatible roles, required tool groups, evidence
  profile, version and optional references. A Skill cannot request a tool group
  its role does not hold.
- A Playbook is knowledge selected for a subject. Its metadata declares Property
  class, trigger facts, output classes, risk effects, baseline, required Skills,
  conflicts, expiry and evidence expectations. Human-only material is excluded
  from the model projection by structure rather than heading heuristics.
- Selection proceeds through trigger facts, Property class, role, risk ceiling,
  Skill loadability, conflicts, status and expiry, then applies a hard small cap.
  The selected text and dependency hashes are frozen onto the Task.
- Stable promotion requires runtime evidence that this exact Playbook text
  contributed to grounded work and a passing fixture verdict for this exact
  hash. An edit returns it to draft.
- Evaluation binds Playbooks to independently authored fixture classes, runs
  positive and out-of-class adversarial cases for repeated samples, fails
  ungrounded and false-positive claims, and requires at least one relevant
  positive plus one meaningful negative before pass.

### 16. Complete v1 corpus disposition

- A generated manifest freezes every v1 knowledge artifact by kind, relative
  path, line count and SHA-256. The initial expected census is 223 rows: 11 Agent
  definitions, 28 Skill directories, 60 Playbook topics, 112 operator references,
  9 sink packs and 3 reserved bundle files.
- Every manifest row carries exactly one disposition, rationale, replacement
  identifier and verification reference. CI fails on a missing row, duplicate
  row, stale hash or replacement that does not exist.
- The 11 v1 Agents map as planned: five lenses into `web_hunter`, two into
  `recon`, two into `js_analyst`, one into the deterministic reporter, and
  one Android Agent to an explicit scope retirement. Orchestrator and validator
  are new v2 roles.
- The 28 v1 Skill directories map as planned: four capability Skills are
  rewritten, fourteen routing Skills are absorbed into the Property-class
  vocabulary, five are superseded by runtime or reporting enforcement, three
  workflow Skills are superseded by the scheduler, and two Android Skills are
  explicitly retired for the current scope. Replacement capability Skills
  required by v2 Playbooks are authored and tested even when they have no
  one-to-one v1 file.
- Of the 60 Playbook topics, 49 web/API topics are fully authored in the v2
  format, ten Android topics are explicitly retired and one topic is absorbed as
  reference material. All 112 operator references and 9 sink packs are linked
  from the relevant Playbooks or Skills rather than loaded globally.
- Existing v1 Findings carry family-level prioritization evidence only because
  they do not record Playbook or Skill provenance. They cannot promote v2
  Playbooks or validate imported Findings.
- No v1 engagement directories or raw state are test fixtures. Import reads an
  operator-selected export, validates and redacts it, and defaults all
  provenance-deficient claims to unverified or retest-required.

### 17. Validation and reporting

- Validation packets are constructed by positive column selection from canonical
  Finding, Hypothesis, Test, Test-run, Receipt and Artifact rows. Hunter prose and
  transcript identifiers have no route into the packet.
- The validator has one read-once packet and one closed verdict operation. It has
  no tools for network, source, Artifacts outside the packet, shell or delegation.
- A verdict is recorded but database rules decide whether the requested Finding
  transition is admissible.
- The reporter is a pure deterministic projection of validated rows. Optional
  narrative is disabled by default and, when enabled, may only rephrase existing
  identifiers and facts.
- Evidence bundles contain redacted reproductions, controls, hashes and stable
  references. Encrypted credential material is excluded unless an operator
  performs a separate explicit export.

### 18. Operator CLI and local UI

- The supported CLI covers run/resume, doctor, migrate, Program creation and
  inspection, Halt/clear, pending decisions, record reads, import, validation,
  report and integrity checks. Narrow mutations are explicit verbs; there is no
  generic SQL or JSON patch command.
- The local UI reads the same bounded application queries and invokes the same
  operator verbs. It never reads Postgres tables directly.
- UI summaries and caches are non-authoritative and keyed by source hashes. A
  summarization failure falls back to canonical text.
- Stable identifiers link Program, Task, Agent run, Tool run, Receipt, Artifact,
  Observation, Hypothesis, Test, Finding and chain views.

### 19. Delivery phases and exit gates

1. **Truth and consolidation.** Correct prototype-versus-production status,
   preserve relevant design evidence in the current tree, freeze the v1 census
   and register all known review defects. Exit when no production claim depends
   on a prototype path and every design source is reachable.
2. **Production kernel.** Deliver packaging, configuration, Postgres connections,
   transaction context, migrations, Artifacts and operator diagnostics. Exit on
   clean create, upgrade, integrity, dump and restore through supported commands.
3. **Egress and startup boundary.** Deliver container isolation, HTTP/HTTPS proxy,
   capability Receipts, encrypted wire Artifacts, Identity slots and the promoted
   startup assertion. Exit on real-container bypass tests and every auth-vector
   refusal through an actual child process.
4. **Single-Task vertical slice.** Deliver one `rk run` path that creates or
   resumes a Program, claims one Task, launches one Agent, serves one network
   tool, promotes one grounded result and exits cleanly. Exit when crash points,
   refusal and a second identical run leave deterministic state.
5. **Campaign runtime.** Deliver the roster, tool contracts, Mission packets,
   scheduler, Slates, Leases, budgets, session rotation, browser/tool runners,
   pending decisions and Halt. Exit on a multi-role synthetic campaign with
   forced rotation and restart.
6. **Epistemics and kill chains.** Deliver promotion, Tests, replay, validation,
   Findings, negative knowledge, pivots, chains and deterministic reports. Exit
   when false terminal claims and unsound chains are refused by negative controls.
7. **Knowledge completeness.** Deliver production Skills, all 49 in-scope v2
   Playbooks, absorbed references, fixture corpus, evaluation and the 223-row v1
   disposition gate. Exit only at zero unresolved, stale or unloadable artifacts
   and passing stable-Playbook evaluations.
8. **Operator product and migration.** Deliver complete CLI, local UI, safe v1
   importer and standalone evidence/report exports. Exit on operator UAT from a
   fresh install and from a redacted legacy export.
9. **Hardening and release.** Deliver long-campaign fault injection, bounded
   context measurements, performance checks, secret scans, container containment,
   upgrade/restore drills and final Standards/Spec review. Exit only when all
   gates pass from a clean checkout and no runtime import or command references a
   prototype.

## Testing Decisions

- The highest test seam is the operator's `rk run` operation in the production
  container topology. It must prove Program creation/resume, scheduling, actual
  child launch, real proxy traversal, Receipt creation, promotion, durable state
  and exit outcome together.
- A good test asserts externally observable domain outcomes: rows, Events,
  Receipts, Artifacts, process outcomes, target contacts and rendered reports.
  It does not assert private helper calls or copy prototype implementation shape.
- Focused module tests are retained only where the highest seam would hide an
  important negative matrix: auth-resolution evaluation, scope canonicalization,
  transaction context, capability resolution, Playbook parsing/selection,
  deterministic grading and rendering.
- Real security boundaries are not mocked in their acceptance tests. Agent
  container isolation, HTTP/HTTPS proxying, capability stripping, encrypted
  storage, child-process environment, init ordering and fatal supervisor latching
  use the real production adapters against synthetic local fixtures.
- Fake SDK streams are appropriate for exhaustive offline init and error-shape
  tests, but they cannot satisfy the composed startup acceptance criterion.
- The auth-resolution suite replays the fixed sanitised 17-case evidence manifest
  without network, SDK or credentials. A separate explicit version-bump probe is
  never part of ordinary CI.
- The composed startup suite parameterizes every watched environment and settings
  vector through the public Agent-runtime interface. It proves zero SDK transport
  construction for pre-spawn refusal, zero tool service before init, durable
  cleanup and refusal of a second launch in the same supervisor.
- Proxy tests exercise HTTP and local TLS targets, redirects, subresources,
  missing/fabricated/cross-Program/expired/cleared capabilities, DNS rebinding,
  alternate URL forms, Halt, aggregate rate limits and target-contact negative
  controls.
- Receipt tests turn each invariant red by removing its capability or binding.
  Replay tests assert the Receipt Lane matches the capability Lane and the Test
  run that consumes it.
- Artifact tests use synthetic credential markers, verify authenticated
  encryption and redaction, prove plaintext absence from database/logs/events,
  and prove Agent reads cannot reach encrypted wire material.
- Database tests start from empty state, apply every migration, run all registered
  standing checks with negative controls, dump, restore, rerun checks and compare
  schema/catalogue identity.
- Fault-injection tests stop the process immediately before and after each
  durable commit in claim, Agent start, Tool start, Receipt write, promotion,
  validation, refusal, Halt and lease release. Restart must be idempotent and
  must not fabricate attempts or duplicate Events.
- Scheduler tests use fixed rows and weights and assert deterministic Slates,
  claim revalidation, fallback, Lane fairness, budget reservations, lease
  exclusivity and dependency unlock ranking.
- Long-session tests run a synthetic campaign large enough to require multiple
  worker and orchestrator rotations, force process restarts throughout, and
  compare final canonical state to an uninterrupted run. No test uses wall-clock
  sleeps as correctness evidence.
- Context-efficiency tests measure serialized Mission packets and orchestrator
  capsules against configured byte/token ceilings, assert omission markers, and
  prove full transcripts are neither loaded nor required for resume.
- Epistemic tests attempt every forbidden shortcut: Observation without
  provenance, Hypothesis testing without a Test run, Finding validation with an
  unrelated Receipt, exploit status without an authorized impact Test, and
  reporting without a human transition.
- Kill-chain tests cover a valid branched chain, missing pivot, invalidated member,
  cross-Program member, cycle, disconnected graph, expired grant, unsafe full
  replay and independently proven composition. An empty or unsound graph never
  produces a negative conclusion.
- Skill tests validate metadata, role compatibility, tool non-widening, content
  hash and runnable scripts. Playbook tests validate schema, vocabulary,
  loadability, projection, selection, expiry, conflicts and positive/adversarial
  fixture verdicts.
- The v1 coverage test regenerates the census read-only, compares all 223
  dispositions and hashes, resolves every replacement and fails on any addition,
  deletion, drift or untested replacement.
- Migration tests use synthetic legacy exports. They prove no secret material is
  copied and no provenance-deficient historical state becomes supported,
  validated or exploited automatically.
- Report tests render shuffled equivalent input byte-identically, refuse
  unvalidated rows and prevent optional narrative from introducing new
  identifiers.
- Secret scans cover the publishable tracked/unignored tree, fixture outputs,
  generated reports and container build contexts. Real engagement data is never
  a fixture.
- Performance tests measure the actual corpus and realistic synthetic surface
  sizes. They establish budgets for Slate computation, Playbook selection,
  compact state reads, graph integrity and report rendering without weakening
  correctness constraints.
- Final acceptance runs the entire production suite twice from clean state,
  performs operator UAT through CLI and UI, then runs independent Standards and
  Spec review against the production diff.

## Out of Scope

- Android application, device, APK, ADB and mobile-network testing are outside
  the initial production scope. Their v1 Agent, Skills and ten Playbooks remain
  explicitly dispositioned for a future mobile milestone.
- Infrastructure discovery outside explicitly configured web/API scope is not
  authorized. Certificate-transparency search, reverse-IP enumeration,
  uncontrolled virtual-host discovery and adjacent-host expansion are excluded.
- Automatic destructive exploitation, denial-of-service, third-party impact and
  actions beyond the Program's Rules of Engagement are excluded.
- Automatic submission to bug-bounty platforms is excluded. The harness produces
  evidence and reports; a human reports them.
- API-key billing and alternate cloud-provider auth are excluded. The runtime
  refuses those credential vectors rather than supporting them.
- Multi-host distributed scheduling, hosted SaaS operation and untrusted remote
  tenants are excluded from the local-first release.
- Event-sourced state reconstruction and historical database time travel are
  excluded. Rows remain authoritative.
- Automatic promotion of legacy v1 Findings, terminal lead states or Playbooks
  from prose, dates or status labels is excluded.
- Production code generation from prototypes is excluded. Prototype behavior is
  reimplemented only through production interfaces and regression tests.

## Further Notes

- The current repository is a design evidence base, not a production harness.
  The first implementation phase must correct that status explicitly.
- The startup slice's known review failures are mandatory regression cases:
  HTTPS must not bypass the proxy; replay must not be labeled agent traffic;
  credential-bearing wire material must not be stored plaintext; actor context
  must be transaction-local; the composed proof must cross a real child/container
  seam and every credential vector; startup refusal must latch the supervisor.
- The v1 migration ledger measures completeness, but disposition is not blind
  copying. Runtime-enforced policy replaces prompt policy, scheduler logic
  replaces workflow Skills, Property classes replace routing Skills, and unsafe
  Agent authority is deliberately removed.
- The six-role roster and capability-based Skill model supersede prototype
  inconsistencies in which vulnerability-family names were treated as Skills.
- The existing runtime-offers/orchestrator-picks ADR remains authoritative for
  scheduling authority. This spec narrows only session lifetime: durable rows,
  not an indefinitely long orchestrator transcript, carry continuity.
- A release is not complete while any production command imports a prototype,
  any v1 manifest row lacks a verified disposition, any in-scope Playbook remains
  unauthored or untestable, or any terminal Finding/chain claim can be produced
  without its required provenance.
