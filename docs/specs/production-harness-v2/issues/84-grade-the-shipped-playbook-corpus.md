# 84 — Grade the shipped Playbook corpus over the door

**What to build:** The graded runs the corpus migrations deferred: every in-scope Playbook hash evaluated against its bound fixtures through the door route, with the verdicts filed and whatever passes promoted at the text it ships.

**Blocked by:** 78 — Grade a Playbook with a real Agent behind the door; 233 — A probe-only Playbook bar asks for two kinds its own trigger refuses (`http-desync` cannot be graded at its shipped text until that is decided; raised by ticket 166's review pass, 2026-09-02).

**Status:** ready-for-human

- [ ] Every in-scope web/API Playbook is graded at the exact text it ships, against each fixture `playbook_fixture_binding` gives it, through an Agent boundary rather than the zero-filing loopback path.
- [ ] Each filed run is a door run that reached its fixture: `playbook_test_runs.route` is `door`, the run has Tool runs, and `check_playbook_tests` reports no `test_run_reached_nothing` against it.
- [ ] Positive recall and adversarial precision are graded from those runs, not from offline fixture grading, and the verdict for each hash follows from what was filed.
- [ ] A Playbook that passes reaches `stable` through `playbook_test_verdict` and `playbook_promotion_evidence` at its own `p_sha`; one that fails stays `draft` and says why.
- [x] The run is repeatable from the shipped surface -- `rk playbook evaluate` per Playbook and fixture, with the boundary the environment declares -- and its cost is stated before it starts, because each repeat is a real Agent run.
- [ ] The eleven deferred criteria across tickets 46 and 49 through 57 are ticked or restated, each citing the graded runs that closed it.

## Why

Ticket 78 built the route these criteria were waiting for. Until then an
evaluation run was an Agent run against a fixture on loopback, and
`scope.compile_policy` and `authorize_identity_egress_address` both refuse
loopback, so the corpus migrations (49 through 57) shipped their Playbooks
`draft`, graded their fixtures offline, and deferred the production halves to
"the route above". Ticket 46's own sixth criterion deferred the same thing from
the other end: every seam but the proxy.

78 closed the route -- an evaluation now serves its fixture on the agent network
and the door dials it by address, with a Receipt per request and
`playbook_test_runs.route` recording which way the run went -- and proved it on
one Playbook, `object-ownership`, in `ContainedEvaluationTest`. What it did not
do is grade the other forty-eight. That is measurement, not plumbing: it costs a
real Agent run per repeat per fixture, it wants a stated budget, and its result
is a set of verdicts that may not all be `pass`.

Splitting it out keeps the two statements apart. 78 says the route exists and is
tested. This ticket says what the corpus scores on it.

## What was built, and what is left

`rk playbook cost` states the campaign before it starts, which is criterion 5's
second half and the reason the rest of this ticket is not an agent's to run. It
reads the two things the verdict reads -- `playbook_fixture_binding` and
`playbook_test_policy` -- discounts every repeat already filed at the text a
Playbook ships, and reports what the corpus still owes:

    50 Playbook(s) against 55 bound fixture(s) each, 0 of the required
    repeat(s) already filed at the text they ship
    16500 Agent run(s) still owed, reserving 3300000000 token(s) against
    the 200000-token envelope one run is ranked against

Sixteen thousand five hundred, because the binding is total: every one of the
55 fixtures is bound to every one of the 50 Playbooks, `required_repeats` is 3, and
every fixture in this catalogue is an `own_pair`, so one repeat is two Programs
-- the vulnerable half and the control. Nothing in that number is an estimate.
The token figure is the reservation those runs imply at
`scheduler_weights.cost_reference_tokens`, in the unit 023 says this harness is
scarce in; no price is invented, because dollars are not a column here.

The command also states the route, and that is the part that decides whether the
spend buys a measurement. `rk playbook evaluate` on a machine describing no
Agent boundary opens each Program and attempts nothing in it, so a corpus graded
that way files 16500 honest zeroes. The campaign therefore needs a machine with
the boundary ticket 78 built -- an agent image, an internal network, a door and
its certificate -- and an Agent credential to spend.

That is why the remaining criteria stay open and this ticket is
`ready-for-human`: the work left is not code but a decision about spend on
infrastructure the sandbox this was built in does not have. The five unticked
boxes are one run of the surface that now exists, and the eleven deferred
criteria across tickets 46 and 49 through 57 are waiting on its result rather
than on anything else being built.

## What one Playbook in the fifty will grade, before anybody spends on it

Ticket 88 gave `playbooks/http-desync` the own pair it had never had, so it is
now bound like the other forty-nine and this campaign will file runs for it.
What those runs return is worth knowing in advance: `tls-configuration-pair`
serves the same bytes under the same advertisement on both halves, and the field
they differ in is the negotiated TLS version, which an Agent behind the
interception proxy cannot observe. So that Playbook reaches clause 4 of
`playbook_test_verdict` and grades `fail` -- `median discriminating finding < 1`
-- rather than `pass`, and it will do that however many runs this campaign
spends on it.

The lane that would change the answer is ticket 93, the unintercepted transport
measurement. This ticket is not blocked on it: forty-nine Playbooks are graded
on evidence their Agent can actually take, and the fiftieth grades honestly on
the evidence available. It is recorded here so the spend is decided knowing it.

## The decision on spend

Delegated to the agent and taken here, so the ticket says what it is waiting
for rather than waiting for it to be decided again. **The full 16500-run
campaign is not what to buy.** What to buy is a slice of it at full binding and
shipped repeats, and the end-to-end question the campaign does not answer goes
to a real engagement instead.

### Why the campaign cannot simply be trimmed

The two obvious economies are both refused by the schema, and the refusals are
the design rather than an oversight:

* **Fewer fixtures per Playbook.** `playbook_test_verdict` clause 3 -- "the
  binding is total, so the run set must be too" -- returns `untested` while any
  bound fixture has no run at that text, and `untested` blocks promotion. The
  totality is what ticket 17 bought: the `out` half is every fixture authored
  for somebody else's Playbook, which is the only reason an author cannot pick
  the cases their own Playbook is graded on. Grading a Playbook against a
  chosen subset of its binding buys a number nobody should believe.
* **Fewer repeats.** `playbook_test_policy.required_repeats` is settable from 1
  to 32, and dropping it to 1 would cut the campaign to 5400 runs. The
  migration that introduced it says why 3 is the floor: it is the smallest
  number for which the median in clause 4 means agreement rather than
  rounding. Turning it down does not make the campaign cheaper; it makes
  `pass` mean something weaker without saying so in the verdict.

So the only honest lever is **which Playbooks are graded**, each one whole.

### What a slice costs, and what it buys

One Playbook graded fully is 55 bound fixtures x 3 repeats x 2 Programs per
own-pair repeat = **330 Agent runs**, reserving 66000000 tokens against the
same 200000-token envelope `rk playbook cost` reports the whole campaign
against. Ten Playbooks is 3300 runs and a fifth of the campaign; each of the
ten gets a verdict that can actually promote it to `stable` at its own `p_sha`,
and the other forty stay `draft` with `check_playbook_tests` saying so every
run, which is the state the harness already models honestly.

Run it with the surface criterion 5 already ticked: `rk playbook evaluate
--playbook <path> --fixture <name>` once per bound fixture, on a machine
carrying the boundary ticket 78 built.

### Why the rest goes to an engagement rather than to more runs

`select_playbooks` sorts `(status = 'stable') DESC` and **does not filter on
it**. A `draft` Playbook is selectable today; it ranks below a graded one and
is otherwise usable. So the corpus being ungraded does not stop a hunt, and a
hunt is where the failures this campaign structurally cannot see live -- scope
compilation against a real program, the door against a real upstream, evidence
against a target nobody authored a ground truth for. The campaign measures
whether a Playbook fires where its own catalogue says it should; it says
nothing about whether the harness finds a bug.

Order, therefore: grade a slice so the ranking has something behind it, hunt
for the rest, and let what the hunt breaks decide which further Playbooks are
worth 324 runs each.

## What the five high-yield pairs measured

The slice this ticket authorised was run on 2026-08-25 as canary 12, database
`rk2grade12`, over a detached worktree of `808a8a2a` at
`out/grading-freeze-20260825T134359Z.json` -- `dirty: False`, source sha256
`ed1707522cc5`, 197 migrations. Five evaluations, all exit 0, no violations, 30
Programs, which is 5 x 3 repeats x 2 Programs per own-pair repeat exactly.
`check_test_replays` reported 0 problems and `rk db verify` 97 assertions with 0
violations.

**Criterion 2 holds for every run filed.** All 15 `playbook_test_runs` carry
`route = 'door'`, every one has Tool runs -- 157 across the fifteen, fewest 4,
most 15 -- and `check_playbook_tests` reports no `test_run_reached_nothing`
against any of them. The route ticket 78 built carried the whole slice.

**The corpus scored nothing on it.** `discriminating_tp` is 0 on all fifteen
runs. So are `false_positives`, `admitted_secure`, `ungrounded` and
`out_of_scope`. `attack-surface`, `browser-script`, `cookies` and
`payment-workflows` filed no claim at all across three repeats each;
`object-ownership` filed 1, 1 and 3 and discriminated none of them. 0 Findings,
34 Test runs (26 `refutes`, 8 `holds`), 139 Tasks done and none errored.

All fifteen rows are `side = 'in'`, which is what a high-yield pair is: 0036's
`playbook_fixture_binding` computes the side from `playbook_outputs x
fixture_classes` and refuses the caller's opinion of it. No `out` row can exist
until a Playbook is graded against the rest of its binding, so the
false-positive number above is a structural zero rather than a measured one.
Each evaluation says as much in its own verdict: `untested: 54 fixture(s) in the
binding have no run at this text`.

### Why the four scored nothing

`check_playbook_tests` warns `test_run_froze_no_skills` against exactly the four
Playbooks that filed no claim, and not against `object-ownership`. The freeze is
not a record of what an Agent did with a Skill; migration
`20260914T000000Z__a_fixture_is_reached_by_address_not_by_name` fills
`playbook_test_run_skills` from `playbook_selection_skills` for selections on
the vulnerable Program `WHERE s.dropped_because IS NULL`. An empty freeze
therefore says the Playbook was never selected and kept on that Program, which
is upstream of anything it could have claimed.

`playbook_selections` says which:

| Playbook | selections | frozen Skills | claims |
| --- | --- | --- | --- |
| `object-ownership` | 6 kept, 1 dropped `role_lacks_skill` | 6 | 1, 1, 3 |
| `attack-surface` | 2 kept | 0 | 0 |
| `browser-script` | none | 0 | 0 |
| `cookies` | none | 0 | 0 |
| `payment-workflows` | none | 0 | 0 |

Three of the five were never offered to an Agent on any Program in the canary.
`payment-workflows` declares the same two Skills as `object-ownership` --
`compare-responses` and `use-identity` -- so this is not a role that lacks a
Skill; that reason was recorded once, against the one Playbook that was
selected six other times. `attack-surface` was kept twice and still froze
nothing, which the freeze's own `s.program_id = p_vulnerable` clause admits: a
selection on the control half is not one of these.

Why selection never offered the three is not traced here and is not this
ticket's to answer. What the slice establishes is that the zero is not a
detection result: four of the five Playbooks were never in a position to detect
anything, so no larger campaign on the same corpus will read differently until
selection does.

### What stays open

`ready-for-human` is unchanged. The decision is which spend to authorise; the
spend still needs an Agent credential and the boundary an agent image, internal
network, door and certificate make up, none of which this sandbox has. The
eleven deferred criteria across tickets 46 and 49 through 57 stay deferred, and
they stay deferred for the Playbooks outside the slice however large the slice
is.
