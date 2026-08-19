# 49 — Migrate recon, API and protocol Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for the seven v1 topics that discover and exercise general API and realtime surfaces.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6:** not met, and it cannot be met from this ticket. Every one of
the seven ships `draft`. `stable` is reachable only through `playbook_test_verdict`
returning `pass` for the exact text, and an evaluation run is an Agent run: the fixture
listens on loopback, `scope.compile_policy` refuses an inclusion naming a loopback address
and `authorize_identity_egress_address` refuses to dial one, so the work an Agent would do
has no route to the target that would grade it. `evaluation.py`'s docstring has named that
seam since 46; ticket 78 decided the route and ticket 84 grades the corpus over it.

Two of the seven have a second blocker that ticket 78 did not clear, and the migration
says so beside the evidence rows rather than here alone. `webhooks` needs a
`callback_interaction` for a supported claim, and that kind takes `{callback}` provenance
alone, so a loopback evaluator with no callback channel to register cannot produce one --
the alternative was accepting a response differential as proof a request was made, which
is the shape of the classic invalid SSRF report. `attack-surface` needs a `content_match`,
which takes `{tool_run}` alone, so its identification runs through `jq` over the stored
Artifact; that works for the source map its fixture exposes and for any other JSON, and an
Artifact `jq` cannot parse has no registered tool behind it and ends inconclusive. The
Playbook body states that limit rather than leaving a model to improvise past it.

What this ticket could do instead of leaving any of it silent, it did. The
`draft_playbook_untestable` rule is 036's and predates this work; what is new is that the
corpus now says which Playbooks it is about: `PlaybookEvaluationTest` asserts the warning
list is exactly the seven unevaluated ones, and `test_every_playbook_is_draft_until_a_fixture_has_graded_it`
asserts the statuses are all `draft`. The day one of them grades, both change and name it.

**Deviation on criterion 2, on one reading of it:** "maps its v1 references to explicit
Property classes" is true of each *Playbook* -- all eight declare a class, triggers,
outputs, risk, effects, Skills and evidence, and `test_every_playbook_declares_everything_criterion_one_names`
asserts it over the catalogue. It is not true reference by reference, and three of the
eight say so in their own Playbook's provenance: attack-surface's three v1 texts are
scanner, CVE and fuzzing notes and "none of them is the source of this class", and of
api's three only `rate-limit-bypass.md` named a defect. Those pages are maintainer context
for a topic, not the origin of a claim. A row-per-reference mapping would have meant
inventing a class for material that names none, which is the v1 breadth this migration set
out to stop carrying.

**Deviation on criterion 4, half of it:** every topic has its positive fixture and every
fixture is `out` for the other seven Playbooks, which is the adversarial half and is total
by construction rather than by an author's choice. What is thinner than the word
"independently" implies is the authorship: all seven fixtures and all seven Playbooks were
written in this one pass. The rule `playbook_fixture_binding` enforces -- no author writes
their own negative -- holds on the axis it is about, since the negative set for any of
them is the material written for the other topics. It does not hold in the sense of two
different people, and no schema can make it.

- [x] Agentic AI, API, Attack Surface, GraphQL, gRPC, Realtime and Webhooks each exist as authored v2 Playbooks with complete metadata and model/human projections.
- [x] Each Playbook maps its v1 references to explicit Property classes, trigger facts, output classes, risk effects, required capability Skills and evidence expectations.
- [x] Recon-oriented content proposes Surface or Hypotheses through production Mission results and never owns campaign workflow or direct promotion.
- [x] Each topic has an independently authored relevant positive fixture and participates in meaningful out-of-class adversarial coverage.
- [x] All seven are loadable by an allowed production role, selectable on matching Surface and absent from non-matching bounded context.
- [ ] Stable promotion passes the production evaluator for each exact Playbook hash with no ungrounded or off-class claims. **Partial:** all seven are registered, loadable and selected at the text they ship, and their fixtures grade; the graded run needs the real-agent route. Ticket 78 built that route; ticket 84 grades the corpus over it.

## Comments

Implemented on 2026-08-16.

### One class per topic, and the v1 breadth went to the surface instead

The seven v1 topics are broad the way a table of contents is broad. Each one became a
Playbook that claims exactly one Property class, because a Playbook is a claim and the
selector reads `bb:outputs` as one: `agentic-ai` claims `injection.model_instruction`,
`api` claims `rate_limiting.per_identity`, `attack-surface` claims
`information_disclosure.artifact_exposure`, `graphql` claims
`information_disclosure.excess_field`, `grpc` claims `authorization.function_access`,
`realtime` claims `session_handling.csrf`, `webhooks` claims `injection.request_forgery`.

The rest of each topic is surface: what an API *is*, how a GraphQL endpoint is found, what
a gRPC reflection response contains. Surface decides what gets recorded and which
Playbooks become selectable and is not a claim about anything, so it went to
`enumerate-surface` and the entity graph -- whose `applications.kind` has carried `api`
since 003, which is why there was somewhere for it to go. `references/api.md` says this in
the topic where it was hardest to give up: three v1 files, one of which named a defect, so
one class shipped and the other two stayed maintainer notes about a surface.
A Playbook claiming six classes because the topic was broad is the v1 mistake carrying v2
metadata.

`injection.model_instruction` is the one new leaf. The injection family splits by
interpreter -- 018's own comment, "because the interpreter is the test" -- and a language
model is an interpreter with no grammar. Under `injection.template` it would have inherited
the assumption that the same input produces the same output, which is the single property
that makes the class hard to test and the reason its fixture rotates its wording.

### The fixtures are what the criteria are actually about

Seven pairs, one per topic, each a `vulnerable` and a `secure` variant compiled from one
source file so the difference between the halves is small enough to read. They are digested
rather than imported: `fixtures.source_sha256` is what a run freezes, so the process
answering requests has to be built from the bytes the catalogue recorded.

Two of them are worth naming because their restraint is the design.
`request-forgery-pair` verifies a webhook URL by fetching it and opens no socket -- the
"network" is a dict resolved in process, holding a metadata endpoint and a KV path. A
fixture that made real outbound requests would send traffic wherever a test pointed it,
which is the behaviour under study, and the class only needs the caller to choose a
destination and learn the answer. `model-instruction-pair` rotates its opening and its
summary on a per-process counter, so two identical requests differ in more than one place
and the only stable signal is the reserved value. A Playbook that differenced one response
against one other would pass on the secure variant too; the rotation is what forces the
Playbook to difference sets.

### The binding is total, and the test suite pays for that

`playbook_fixture_binding` is defined over every fixture, not over the ones an author
nominated: `in` where the classes intersect, `out` everywhere else. So a verdict needs runs
against all nine, and adding a fixture raises the bar for every Playbook that already
passed. That is the point -- the `out` half is the specificity measurement -- and the cost
lands on `PlaybookEvaluationTest`, which now opens eighteen Programs and files
twenty-seven run rows to reach one `pass`.

The first attempt at that arranged only the two fixtures the assertions name and left the
other seven Programs bare, which produced seven `test_run_froze_no_skills` warnings. The
correction is also the more honest simulation: a real evaluation selects the Playbook
against the out-side fixture and runs it, and finding nothing there is the measurement.
`PlaybookEvaluationCommandTest` deliberately does not grow with the corpus -- it grades two
fixtures, earns `untested`, and asserts the median underneath is zero, because what is
under test there is the command and not the catalogue.

### Criterion 5 is a test, not a claim

`PlaybookCorpusSelectionTest` arranges one Surface per Playbook -- eight subjects, each
carrying the facts one Playbook's triggers name -- and asserts in both directions: every
Playbook is loadable by some production role, every Playbook is selected on its own
Surface, and no Playbook reaches a subject its triggers do not describe. The eighth
assertion is that the case covers the catalogue, so a Playbook added without a Surface here
fails rather than passing unmeasured.

Six of the eight Surfaces are typed `spa`, which is the application kind no Playbook keys
on. That is what makes the negative direction mean anything: a subject typed `api` would
satisfy the `api` Playbook's triggers by accident and the "reaches nothing else" assertion
would be measuring the fixture's own type. `PlaybookSelectionTest` needed the same change
for the same reason -- it had been typed `api` since 45, when nothing keyed on that, and
the new `api` Playbook turned it into an extra `risk_above_ceiling` drop row.

### What moved in the ledger

Fifteen rows crossed from promised to built: seven `playbook:<name>` and eight
`reference:playbooks/<topic>/references/<file>.md`, now citing `tests/test_playbook.py`
instead of `ticket:49`. The report's last line reads `built 64 promised 107 retired 52`.

Citing that file meant making it prove the thing. Its `Corpus` case read `object-ownership`
alone, so it now binds the catalogue's names and the reference attachments per Playbook,
widens both reference checks over every Playbook, and widens the four cases that were
general all along: every Playbook declares a class under the category it announces and
carries both projections, names a control among its supported evidence, says what would
refute it, and has a review date in the future. A ledger row whose proof is a test that
only checks the name is in a dictionary is a citation, not a check.

Two of those stayed narrow deliberately. The exact metadata values are asserted for
`object-ownership` only -- a second copy of eight Playbooks' frontmatter in a test file is
a second thing to edit and the compiler already refuses a missing key -- and the control
*kind* is pinned only there, because what a control observes differs by class: a working
session for object ownership, an unchanged answer for `api` and `realtime`, a locale header
that reaches neither half of the prompt for `agentic-ai`. The catalogue-wide case pins the
role, which is the rule: no Playbook may claim from a variant reading alone.

Resolving this ticket also came due on the rule 48 added: a registered migration ticket is
open, or it is resolved and no row still cites it. `test_a_row_that_names_an_open_migration_ticket_is_promised`
had been using `playbook:graphql` and `ticket:49` as its example of a promise, which
stopped being a promise here; it uses `playbook:oauth` and `ticket:50` now.
