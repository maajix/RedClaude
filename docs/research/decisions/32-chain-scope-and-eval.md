# 32 — Three decisions settled by measurement

Every claim below is either a line of the corpus quoted at its file and line, or
a command and the output it actually produced. Nothing here is inferred from a
ticket.

## How the measurements were taken

A database of my own, `rk2_proto_b`, provisioned and migrated from the corpus as
it stood on 2026-08-22 (143 migrations applied, `migrate ok: True`). The role
passwords were deliberately not set, because roles are cluster-global and four
other worktrees share this server: every connection in the probes is opened as
the superuser and immediately issues `SET SESSION AUTHORIZATION rk2_runtime` (or
`rk2_migrate`, or `rk2_human`). That moves `session_user` as well as
`current_user`, so `human_actor_session()` (`0026_human_control.sql:54-57`), row
level security and the table grants all read exactly what they would have read
had the connection authenticated as the role. The probes themselves live under
`/tmp/rk2-proto-b/` and the database was dropped at the end.

The scaffolding is the suite's own. `ReportFixture` in `tests/test_database.py`
(`:34879`) carries a claim from a stated Hypothesis to a validated Finding, an
authorized impact run and a stamped pivot without a container or a network, so
the six verbs were called against evidence the runtime itself wrote rather than
against rows assembled by hand.

## Ticket 103 — who calls the chain verbs

### What was measured

Each of the six was called on a real Program with a real validated Finding, and
each was called again with arguments a model could plausibly send and should not
be able to get away with. What follows is the output, verbatim.

**`open_impact_task(p_finding uuid, p_spec jsonb, p_created_by_run uuid)`**
(`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209`). The
first and third parameters are facts the runtime holds. The second is not. It is
a whole Test specification, and the block that makes it an impact Test is four
authored fields checked by `rk2_impact_problem` (`:88-141`): a class from
`impact_classes`, an `effect` sentence, a `cleanup` sentence, and the ordinal of
the action that reads the state the Test leaves behind. Called with such a
document it answered:

```
{"task": "T9", "test": "TST4", "finding": "F1",
 "risk_class": "approval_required", "impact_class": "write_target_state"}
```

and it refused, in order, a Finding that is not validated ("finding F3 is
candidate and impact is proved on a validated detection"), a specification with
no impact block ("this specification states no impact to authorize"), a
forbidden class ("impact class degrade_availability is forbidden, and no grant
admits it") and a class outside the vocabulary ("no impact class named
steal_the_database"). Every refusal is about the Finding or about the
vocabulary; none of them is about the four fields the caller authored, which is
the point. The runtime cannot write that document, because nothing in the
database says which request undoes a write or which action reads the state
afterwards.

**`state_severity(p_finding uuid, p_severity text, p_basis text, p_rationale
text)`** (`:1725`). `p_rationale` is prose between 20 and 2000 characters
(`20260816T000000Z...:1698`, surfacing as
`severity_statements_rationale_check`), and `p_severity` is one of four bands.
The basis is narrowed by the function but not determined by it. Measured, in one
Program, in this order:

```
state_severity REFUSES: demonstrated_impact before any demonstration exists
  no impact has been demonstrated for F1
state_severity REFUSES: program_context asking for high
  the Program context alone does not make F1 a high Finding
state_severity REFUSES: a basis that is not one of the three
  severity rests on a demonstration, a constrained inference or the Program
  context, not on gut_feeling
state_severity REFUSES: a rationale under 20 characters
  new row for relation "severity_statements" violates check constraint
  "severity_statements_rationale_check"
state_severity RETURNS: constrained_inference / high (no demonstration yet)
  {"was": "info", "basis": "constrained_inference", "finding": "F1",
   "severity": "high", "demonstration": null, "scope_version": 1}
state_severity REFUSES: constrained_inference now a demonstration exists
  finding F1 has a demonstrated impact and needs no inference
state_severity RETURNS: demonstrated_impact / high
  {"was": "high", "basis": "demonstrated_impact", "severity": "high",
   "demonstration": "01a0283f-726e-7eac-b22a-8f8230724c7a"}
```

The two calls left two rows in `severity_statements`, both with `actor_kind =
'runtime'`. So the basis is constrained by state and the band is not: `high` was
accepted twice on two different bases, and the only band the state forbids is
`high` or `critical` on `program_context`. The word and the reason are a
judgement.

The question the ticket asks about `rk2_demonstrated` resolves cleanly.
`rk2_demonstrated` (`20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:375-393`)
reads which assertion kinds held, which roles the exchanges carried and how many
Receipts there were. It is stored on `findings.demonstrated`, and nothing in
`state_severity` reads it. The severity is not derived from it, and it could not
be: a count of Receipts does not say whether a finding is `medium` or `high`.

**`apply_computed_cvss(p_finding uuid)`** (`:1851`). One parameter, and the
answer is entirely derived. The body calls `compute_finding_cvss`
(`0034_reports.sql:743-787`), which reads `finding_effects` joined to
`report_effects`, the replayed spec's preconditions and
`vulnerability_classes.cvss_ui`, and returns a vector. Measured:

```
apply_computed_cvss REFUSES: before any finding_effects row exists
  finding 01a0283f-7022-749a-afc0-1a80a1251ebb has no witnessed effect:
  nothing to score
apply_computed_cvss RETURNS (after the effects exist)
  AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:N
```

There is a stronger fact than the signature. Immediately before that call,
`compose_finding_report` answered with the blocker list, and the list contained:

```
{"code": "cvss_stale", "detail": "stored null, computed AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:N"}
```

The database computes the value, notices that it is not stored, and reports its
own absence as a hard blocker with the answer written out in the detail. After
`apply_computed_cvss` ran, `report_blockers` over the same Program returned no
`cvss_stale` row at all. A model asked to call this verb would be reading a
sentence the runtime wrote and handing the same sentence back.

**`issue_pivot_stamp(p_tool_run_id uuid, p_agent_run_id uuid)`**
(`20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931`).
Both parameters are identifiers of rows this machine created. Every column of
the stamp comes out of `rk2_pivot_source`, and the file says so at :992-993: "Every
column out of the source object and none of them out of a second read of the
same rows". Measured:

```
issue_pivot_stamp RETURNS
  {"stamp": "PV1", "issued": true, "member": "F1", "refusal": null,
   "provides": "other_account_data", "requires": ["authenticated_session"],
   "source_sha256": "50627592d5590bd3b5ac1e9ebd70d1f8e57a6ee5d6a31eab00bacafa20929f46"}
issue_pivot_stamp RETURNS (called again on the same tool run)
  {"stamp": "PV1", "issued": false, ... same source_sha256 ...}
issue_pivot_stamp REFUSES: a tool run id nobody has
  {"stamp": null, "refusal": "no authorized impact run of this Program is
   recorded under that Tool run"}
```

The second call is the whole argument. Calling it twice is not two stamps, and
the only thing a caller can vary is which Tool run it names. There is exactly
one Tool run that has just been closed by `close_impact_replay`, and the runtime
is what closed it.

**`build_kill_chain(p_members uuid[], p_flow jsonb, p_agent_run_id uuid)`**
(`20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538`). It does take
a caller-supplied list of stamps; it does not take a chain. The edges, the
depths, the entry set and the connected component are all derived. Asked of the
same Program with no proposal at all:

```
every pivot stamp this Program holds
  [('PV1','other_account_data','{authenticated_session}'),
   ('PV2','credential_material','{other_account_data}')]
the graph the runtime derives from them without being told anything
  edges:  [('PV1','PV2','other_account_data')]
  depths: [('PV1',0), ('PV2',1)]
  reached (the connected component, derived): 2
  entry:  ["anonymous_reach", "authenticated_session"]
```

Those four answers come from `rk2_chain_edges` (`:94`), `rk2_chain_depths`
(`:116`), `rk2_chain_reached` (`:162`) and `rk2_chain_entry` (`:62`), and each
was called with nothing but the Program id and the stamps already in the table.
The builder itself is idempotent under member order:

```
build_kill_chain RETURNS: two stamps that compose
  {"built": true, "chain": "KC1", "edges": 1, "steps": 2,
   "source_sha256": "df00307f24df415b74c5955c02fa8077e22def45ecfbf02ac40dafba9953c23e"}
build_kill_chain RETURNS: the same two members proposed in the other order
  {"built": false, "chain": "KC1", "edges": 1, "steps": 2,
   "source_sha256": "df00307f24df415b74c5955c02fa8077e22def45ecfbf02ac40dafba9953c23e"}
```

and every refusal it gave is structural rather than a matter of taste: "a chain
of no steps is not an empty chain", "one stamp is a stamp, and a chain composes
at least two", "no pivot stamp of this Program is recorded under
00000000-0000-7000-8000-000000000000".

That leaves `p_flow`, and `p_flow` is the one thing in this verb a model could
contribute. The corpus says what happens to it, at
`20260818T000000Z...:520-522`, on the column itself: "What the agent said the
capabilities do between its members. Recorded and never read". The stored rows
bear it out:

```
chain_proposals for the Program
  ('refused',  None, 'a chain of no steps is not an empty chain, ...')
  ('refused',  None, 'one stamp is a stamp, and a chain composes at least two')
  ('refused',  None, 'no pivot stamp of this Program is recorded under 000...')
  ('built',    {"story": "the note carries the token"}, None)
  ('repeated', None, None)
```

and a catalogue search over every function body in the database for the word
`flow` returns `build_kill_chain` (which writes it), `rk2_chain_problem` (where
the word occurs in the comment "Ambiguous Identity flow"),
`record_callback_interaction` and `record_v1_import`. Nothing reads the column.

**`read_kill_chain(p_chain uuid)`** (`:797`). A read, and the one verb of the six
whose grant already names the operator. Measured from the live catalogue:

```
read_kill_chain(p_chain uuid)   EXECUTE: rk2_human, rk2_runtime
```

It answered with the composed chain, its two steps, its one edge and
`"sound": true`, and answered a chain id nobody has with `{"chain": null,
"sound": false, "unsound": "no chain of this Program is recorded under that id"}`
rather than an exception.

**`compose_finding_report(p_finding uuid, p_composition jsonb)`**
(`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461`). The
composition is a judgement and the file says so at :436-437: "which observation
witnesses which effect is a judgement, not a join". Measured:

```
compose_finding_report RETURNS
  {"steps": 2, "effects": 2, "outcome": "composed", "citations": 4,
   "blockers": [{"code": "cvss_stale", "detail": "stored null, computed ..."}]}
compose_finding_report REFUSES: no effects
  effects must be a non-empty array: a composition with no effect leaves the
  no_effect blocker standing
compose_finding_report REFUSES: a witness observation the Finding does not cite
  insert or update on table "finding_effects" violates foreign key constraint
  "finding_effects_witness_observation_id_program_id_fkey"
```

One correction to the ticket, measured off `pg_proc.proacl` rather than off the
migration text. Ticket 103 says `compose_finding_report` "is owner-only, it has
no grant to any role". It is not owner-only:

```
 compose_finding_report | {=X/rk2_owner,rk2_owner=X/rk2_owner,rk2_runtime=X/rk2_owner}
```

The leading `=X` is the default PUBLIC grant, which nothing revoked, so every
role in the cluster can execute it, including `rk2_proxy` and `rk2_state`. Every
other verb in the group has an explicit ACL with no PUBLIC entry. The absence of
a `GRANT` line in the migration is not the same fact as the absence of a grant,
and for this function the difference is a wider surface rather than a narrower
one.

### What it decides

The answer is split, and the line that splits it is whether the verb has a
parameter the runtime could not fill from a row it wrote itself.

Served Contracts, on ticket 102's pattern, for three:

- `open_impact_task`, because `p_spec` is an authored impact Test.
- `state_severity`, because `p_severity` and `p_rationale` are a judgement the
  state constrains and does not determine.
- `compose_finding_report`, because the witness of each effect and the mechanism
  of each step are the judgement the file was written around.

Runtime steps for three:

- `apply_computed_cvss`, because it has one parameter, its answer is computed by
  `compute_finding_cvss`, and `report_blockers` already emits `cvss_stale` with
  the computed vector in the detail. The runtime should call it where that
  blocker would otherwise be raised. Ticket 103's fourth criterion says the
  ticket decides between wiring it and dropping it: wire it, as a step, and it
  stops being dead without anything being handed to a model.
- `issue_pivot_stamp`, because both parameters name rows the runtime created and
  the verb is idempotent on the digest of the evidence. It belongs immediately
  after `close_impact_replay` in the same code path.
- `build_kill_chain`, because the members are the stamps and the graph over them
  is derived by four functions that take nothing but the Program id. The
  runtime can compose every connected component of its own stamps, and the
  builder's idempotence means doing so repeatedly costs one row lookup. The only
  thing lost is `p_flow`, which the schema states is never read.

And one operator read: `read_kill_chain`. It is already granted to `rk2_human`
and reachable from no command. `rk report chain` (`src/redkraken/cli.py:1519`, reaching
`read_chain_report` at `src/redkraken/reporting.py:69`)
reaches `read_chain_report`, which is the rendered projection; this is the
soundness answer, and the natural home is a sibling operation rather than a
Contract, because a model that could ask whether its own chain is still sound
would be reading the verdict on its own work.

That split is consistent with the shape 102 is being built in right now.
`src/redkraken/roster.py:719` declares `mcp__rk2__propose_finding` as a
`Contract("state.propose", REQUEST, writes=("finding_proposals",), ...)` with
three arguments, and `src/redkraken/_launch.py:1101` is its handler. Three more
Contracts in that group, each naming its own proposal table, is the same
mechanism repeated; three runtime steps and one operator read need no new
mechanism at all.

### What would change the answer

Three things, each of which is checkable rather than arguable.

If `chain_proposals.flow` acquires a reader, `build_kill_chain` moves to the
served side, because the model would then be contributing a value the system
uses. Today the comment at `20260818T000000Z...:520-522` and the catalogue
search agree that it does not.

If a Program is ever expected to hold pivot stamps that form two components and
report only one of them, the choice of member set becomes a judgement and
`build_kill_chain` moves. `rk2_chain_problem` refuses a disconnected proposal
with "is joined to nothing else here, so this is two chains"
(`20260818T000000Z...:316-318`), so the runtime would have to decide which
component matters, and today it has no reason to prefer one.

If `report_blockers` stops emitting `cvss_stale` with the computed vector in
its detail, `apply_computed_cvss` loses its trigger and the case for making it a
step weakens. That arm is at
`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1874` and was
observed firing.

## Ticket 117 — the CIDR arm

### What was measured

A Program was opened from the standard configuration, which compiled two rules:

```
ord effect          kind   pattern_text        match_key           net   protocol port path_prefix
1   exclude         exact  admin.example.com   admin.example.com   NULL  https    443  /
2   target          exact  app.example.com     app.example.com     NULL  https    443  /api/
```

Then one row was inserted by hand, as the owner, in the shape the compiler would
have written it if it could: `effect = 'target'`, `effect_rank = 2`,
`pattern_kind = 'cidr'`, `pattern_text = '10.0.0.0/8'`, `match_key = NULL`,
`net = '10.0.0.0/8'::cidr`, `protocol = 'https'`, `port = 443`. Both paired
CHECKs at `0021_scope_policy.sql:109-110` accepted it.

The live classifier was then asked, six ways:

```
scope_class_of: an address inside 10.0.0.0/8, asked as a request
  [("target", "matched_target", 3, None)]
scope_class_of: the same address with no protocol and no port
  [("target", "matched_target", 3, None)]
scope_class_of: the same address, asked as coverage (what an Entity asks)
  [("target", "matched_target", 3, None)]
scope_class_of: an address outside the range
  [("denied", "unlisted", None, None)]
scope_class_of: the same address, asked as a subtree
  [("denied", "unlisted", None, None)]
scope_class_of: the configured wildcard host, for comparison
  [("target", "matched_target", 2, None)]
```

The containment arm fires. It fires for the `request` question the egress door
asks and for the `coverage` question an Entity asks, it cites the right rule
ordinal, and it correctly denies an address outside the range. The `subtree`
answer is not a defect: the arm is guarded `p_question <> 'subtree'` at
`20260810T193000Z__scope_policy_compilation.sql:341-343`, because a range is not
a domain and cannot cover one.

The Entity projection was then exercised end to end. An `application` Entity was
inserted at `10.0.0.5:443`, `refresh_scope_projection` was run, and the row came
back:

```
the Entity at 10.0.0.5 after refresh_scope_projection
  (scope_class, scope_reason, scope_tier, scope_version_at)
  [("target", "matched_target", None, 1)]
```

So the arm reaches the column the rest of the system reads, and
`check_scope_policy()` over the whole database returned zero rows with that
hand-written CIDR rule in place.

Three things do not follow, and they are what makes recommendation A larger than
"only the compiler is missing".

The loader refuses the string. `config.load` on the same document with
`host = "10.0.0.0/8"` answered:

```
config.load: configuration is refused
  invalid_configuration | config:scope.include[0].host |
  must be a hostname, a wildcard such as *.example.com, or an address
```

which is `_HOST_SHAPE` at `src/redkraken/config.py:135`. The grammar has no word
for a range, so A begins one layer above the compiler.

The Python evaluator cannot hold one either. `scope.parse_pattern` was called on
every spelling an operator might reach for:

```
'10.0.0.0/8'                 REFUSED: PolicyError: '10.0.0.0/8' carries the label '0/8'
'10.0.0.5'                   -> Pattern(kind='exact', match_key='10.0.0.5', spec_kind=2, spec_len=4)
'*.10.0.0.0'                 REFUSED: PolicyError: '*.10.0.0.0' wildcards an address
'10.0.0.0-10.255.255.255'    -> Pattern(kind='exact', match_key='10.0.0.0-10.255.255.255', ...)
```

The refusal is at `src/redkraken/scope.py:288`. The function has exactly two
`Pattern(...)` returns, `kind="wildcard"` and `kind="exact"`, and
`Pattern.spec_kind` (`src/redkraken/scope.py:540`) reads
`return SPEC_EXACT if self.kind == "exact" else SPEC_WILDCARD`, so a third kind
has no specificity value to sort by. The database is not the only evaluator:
`scope.decide_request` is what the proxy consults, so A has to be implemented
twice and the two implementations have to agree, which is exactly the failure
mode `20260810T193000Z...:410-412` says the corpus already removed once.

The last one is a behaviour gap rather than a missing edit.
`record_configured_subjects` filters `AND r.pattern_kind = 'exact'`
(`20260831T000000Z__a_program_opens_the_first_task_of_its_own_scope.sql:203`).
Run against the Program with the CIDR rule in it, it returned `0`, and the only
configured Entities in the Program were the ones the exact rule and the identity
declaration had already produced:

```
record_configured_subjects: subjects seeded from the rules
  0
the Entities it seeded (dedup_key, selector)
  ("application:https://app.example.com/api", "app.example.com")
  ("app:protob-inside", "10.0.0.5")            # inserted by this probe, not seeded
  ("configured-identity:member", None)
```

A Program whose scope is only `10.0.0.0/8` therefore compiles, projects and
classifies correctly, and opens no first Task, because there is no single
address to name. That is not a bug in the filter; a range has no base URL. It is
a fourth piece of work A has to answer for, and it is the piece that decides
whether a CIDR-scoped Program can hunt at all rather than merely be evaluated.

One more thing A as currently scoped would not fix. `allow_private_ips`
(`0021_scope_policy.sql:95`) is not referenced by the containment arm at
`20260810T193000Z...:341-343`, nor anywhere else in the tree: the only
occurrence under `src/`, `tests/` and `tools/` is its own declaration. Teaching
the compiler to emit `net` leaves that column exactly as dead as it is today,
and a `10.0.0.0/8` rule would be evaluated with no private-address guard at all.

### What it decides

The reasoning behind A survives its test on the point it was made about, and
fails on the word "only". The classifier arm and the partial GiST index are not
dead code waiting for a writer; they are working code with no writer, and I have
now written one by hand and watched it work. So the two CHECKs at `0021:109-110`
and the index at `0021:119-121` are load-bearing rather than decorative, and
removing them would remove a working evaluator.

But "only the compiler is missing" understates the work by a factor. A is four
edits and one design question: the loader grammar (`config.py:135`),
`scope.parse_pattern` and `Pattern.spec_kind` on the Python side
(`scope.py:288`, `:540`, and the two `Pattern(...)` returns at `:579` and
`:584`), the thirteen-column INSERT in `src/redkraken/program.py:911`, and an
answer for `record_configured_subjects` at `20260831T000000Z...:203`, which
today gives a CIDR-scoped Program nothing to start from. If `allow_private_ips`
is meant to mean anything, that is a fifth. Anyone choosing A should choose it
knowing that, because the number in the ticket is one and the number measured
here is four or five.

I would still take A over B on the product question, because the arm works and
the range scope is real, but the case for B is stronger than the ticket makes
it, and B is one migration against four files.

The tier half is separate and it is not close. It has no producer and no
consumer at either end. The only live writer of `program_scope_rules` is
`src/redkraken/program.py:911` and its column list omits `tier`; the only live
writer of `program_scope_versions` is `program.py:877` and its column list omits
`default_tier`. So both arms of the coalesce at
`20260810T193000Z...:394-399` are NULL for every verdict,
`refresh_scope_projection` writes NULL into `entities.scope_tier`
(`0021_scope_policy.sql:539`) for every Entity, and `CHECK (tier IS NULL OR
effect = 'target')` (`0021:112`) can never fail. At the reading end, the only
thing that ever reads the column after it is written is the JSON key in
`v_records` (latest definition
`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1171`). That is not a
theoretical publication. The Entity this probe classified as `target` renders,
today, as:

```
{"kind": "entity", "type": "application", "label": "protob-inside-the-range",
 "in_scope": true, "scope_tier": null, "scope_class": "target", ...}
```

`grep -rn "scope_tier" src/ tests/ tools/` returns no Python hit at all, and
`grep -rn "scope_tier\|default_tier\|allow_private_ips" tests/ tools/` exits 1
with no output, so nothing reads the key and no test asserts on it. The tier
half should come out whichever way the CIDR half is decided, and it should come
out with `allow_private_ips`, which is one declaration and nothing else.

### What would change the answer

If a consumer for `entities.scope_tier` appears, in ranking or in scheduling,
the tier half stops being separable and has to be built rather than removed.
Today the index at `0021:493` carries it `INCLUDE (scope_tier)` for an index-only
scan that no query performs.

If `record_configured_subjects` is given an answer for range rules, so that a
CIDR-scoped Program has something to open a Task against, A shrinks back towards
what the ticket claims it is. Without that answer, a Program scoped only by
range compiles a policy it can enforce and cannot hunt.

If the Python evaluator is retired in favour of the SQL one, A becomes three
edits instead of four. There is no sign of that in the tree:
`src/redkraken/proxy.py` reaches `scope.decide_request` on the live egress path.

## Ticket 126 — the eval store

### What was measured

The command was run. `rk playbook evaluate` is defined at
`src/redkraken/cli.py:1425-1479` and its handler `_playbook_evaluate`
(`cli.py:2156`) calls `evaluation.evaluate(...)` at `cli.py:2183`; the probe
entered at that same call with the same arguments, because the CLI would have
needed a role password this machine deliberately does not set. The invocation
was:

```
rk playbook evaluate --playbook playbooks/api-authorization/playbook.md \
                     --fixture edge-rule-pair --workspace /tmp/rk2-proto-b-eval-jz92lqje
```

with no Agent boundary described, which is the `loopback` route the handler's
own docstring says is the floor. It succeeded:

```
{"ok": true, "exit_code": 0,
 "facts": {"playbook": "playbooks/api-authorization/playbook.md",
           "fixture": "edge-rule-pair", "route": "loopback", "repeats": 3,
           "runs": [{"index": 0, "programs": {"vulnerable": "...", "secure": "..."},
                     "run_id": "01a02843-2f98-7bac-b302-2cb19b8d52c5"}, ...],
           "verdict": {"verdict": "untested",
                       "reason": "54 fixture(s) in the binding have no run at this text"}},
 "violations": []}
```

Every table in the database was counted before and after. These are the ones
that moved:

```
applications:            1 -> 7
entities:               11 -> 17
evaluation_programs:     0 -> 6
events:                196 -> 226
label_counters:         14 -> 26
playbook_test_runs:      0 -> 3
program_configurations:  1 -> 7
program_scope_rules:     2 -> 8
program_scope_versions:  1 -> 7
programs:                1 -> 7
tasks:                  10 -> 16
```

and these are the ones that did not:

```
eval_runs:            0 row(s)
eval_pair_scores:     0 row(s)
eval_fn_attribution:  0 row(s)
eval_family_coverage: 0 row(s)
```

The claim that `src/redkraken/evaluation.py` writes only `evaluation_programs`
is true of its own SQL and needs one qualification. Its single INSERT is
`evaluation.py:139-142`, `INSERT INTO evaluation_programs (program_id,
playbook_id, fixture_id, variant) ... ON CONFLICT (program_id) DO NOTHING`, and
the six rows it left are exactly a vulnerable and a secure Program for each of
three repeats:

```
('01a02843-24f1-...', '01a0283f-4f56-...', 'edge-rule-pair', 'vulnerable')
('01a02843-2ee4-...', '01a0283f-4f56-...', 'edge-rule-pair', 'secure')
... four more, one pair per repeat
```

But it also reaches two writes inside SQL functions it calls:
`open_fixture_address` (`evaluation.py:539`) and `record_playbook_test_run`
(`evaluation.py:869`), and the second of those is where the grade goes. Three
rows were filed:

```
(fixture_id, side, repeat_index, claims, ungrounded, fired_in_scope, out_of_scope,
 false_positives, discriminating_tp, admitted_secure, tool_runs, route, run_key)
('edge-rule-pair','out',0,0,0,0,0,0,0,0,0,'loopback','6086bc1f663abd1d236228cbf8874aae')
('edge-rule-pair','out',1, ... same ... )
('edge-rule-pair','out',2, ... same ... )
```

Zeroes, because nothing was attempted, which is the honest answer for a machine
with no Agent boundary. The shape is what matters: `playbook_test_runs` already
carries a `run_key`, a per-run false positive count, a discriminating true
positive count and an `admitted_secure` count, computed in SQL by
`record_playbook_test_run`
(`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:535-540`),
and `evaluation.py:32-34` says why the counting lives there: "The counting is not
here. `record_playbook_test_run` derives every number from the rows the two
Programs produced."

Then the real question: how far is it from that to a row in each of the four
eval tables. Asked of the database rather than of the file, the columns a writer
must supply are:

```
eval_runs:            program_id uuid, run_key text, key_components jsonb, sut text
eval_pair_scores:     program_id uuid, eval_run_id uuid, fixture_id text,
                      fixture_kind text, gt_declared integer, gt_recallable integer
eval_fn_attribution:  program_id uuid, pair_score_id uuid, gt_id text,
                      bucket text, owner text
eval_family_coverage: program_id uuid, eval_run_id uuid, family_id text
```

(`program_id` is filled by the `derive_program_id` triggers at
`0033_eval_store.sql:218-228` for three of the four, so it is not a writer's
problem.)

Of those, `evaluation.py` already holds the material for `eval_runs.program_id`
and `repeat_index`, and for `eval_pair_scores.eval_run_id`, `fixture_id` and
`fixture_kind`; `fixture.Fixture.kind` even uses the same two words the CHECK
admits, `own_pair` and `third_party`.

Everything that carries the measurement has no producer anywhere in the repo.
`run_key` exists in the tree only as a different key over a different pre-image:
`playbook_test_runs.run_key` is a digest over playbook, fixture, fixture source,
ground truth and skills, and it is not returned to Python, whereas the eval
store's `run_key` is described at `0033_eval_store.sql:31-36` as covering
catalogue, fixture app, ground truth, `grading.py`, `metrics.py`, the playbook
set, the sut and the config. Two of those named components, `grading.py` and
`metrics.py`, do not exist in this repository. `sut` occurs three times in the
whole tree: the comment at `0033:33`, the column at `0033:43`, and a row in
`docs/research/wiring/23-database-wiring.md:144`. `gt_declared` and
`gt_recallable` have no producer; the nearest artefact is a fixture's `bb:classes`
list, and a list of classes is not an enumeration of ground truth entries.
`gt_id` has no producer and no such identifier exists, so
`UNIQUE (pair_score_id, gt_id)` has nothing to key on. And the accounting
constraint at `0033:104-106`, `CHECK (tp + fn_not_found + fn_unproven +
fn_suppressed + fn_near_miss = gt_recallable)`, requires that every recallable
ground truth entry be classified into exactly one of five buckets, which is a
per-entry labelling model, not a number.

Finally, the five read functions have no caller, and the database agrees. Asked
which function bodies in the whole `public` schema mention the eval store or its
readers, the answer was the five readers themselves and nothing else:

```
eval_comparable, eval_family_coverage_of, eval_key_diff, eval_precision,
eval_recall_by_kind
```

### What it decides

The reasoning behind A does not survive. It rests on two claims and both are
wrong.

"`rk playbook evaluate` already registers which Playbook is measured against
which fixture; only the score is missing." The registration is real, and it is
in `evaluation_programs`, which is a different table with a different key: it is
keyed on `program_id`, one row per Program, and the eval store is keyed on a
`run_key` that nothing computes. The gap is not one insert. It is
`gt_declared`, `gt_recallable`, a true positive and false positive labelling per
ground truth entry, a five-way classification of every miss, a `gt_id` namespace
that the fixture corpus does not carry, a `sut` identifier, and a `run_key` over
an eight-component pre-image two of whose components are files that do not
exist. That is a scoring model, and writing it is a ticket several times the size
of the one that would wire it.

"Tickets 78 and 84 produce grades that go nowhere." This is false. Ticket 78 is
`resolved` and produced the door route and the Receipts behind it; ticket 84 is
`ready-for-human` and its criteria name `playbook_test_runs.route`,
`check_playbook_tests`, `playbook_test_verdict` and
`playbook_promotion_evidence`. Every one of those has a recorded consumer, and I
watched the last link close: the run above filed three `playbook_test_runs` rows
and the command read the verdict back out of `playbook_test_verdict` into its own
report as `{"verdict": "untested", "reason": "54 fixture(s) in the binding have
no run at this text"}`. The grades of 78 and 84 do go somewhere. What they do not
do is go into `0033_eval_store.sql`, and neither ticket ever said they would:
neither mentions `eval_runs`, `eval_pair_scores`, `run_key`, `recall_strict` or
`precision_strict` anywhere.

So the eval store is not the missing half of a measurement that exists. It is a
second, richer measurement design that was written down and then overtaken by a
simpler one that shipped. `playbook_test_runs` plus `playbook_test_verdict` is
the grading path this harness actually has, it is wired at both ends, and it
answers the question the corpus asks of a Playbook.

A is the wrong answer. The choice is between retiring the four tables and their
five readers, and recording the deferral in the migration corpus with the
missing scoring model named, which is what ticket 126's own fifth criterion asks
for. The evidence favours retiring, on one ground: the design's distinguishing
value is A/B comparability through `run_key`, `eval_key_diff` and
`eval_comparable`, and that value cannot be recovered incrementally, because the
pre-image `0033:31-36` describes is a pre-image of files that do not exist. A
deferral note that says "later" for a design whose own key names two absent
modules is a note the next audit will read the same way this one did. If it is
kept, the note must say what would have to be built first, not that it is
pending.

The one thing not to re-decide stays as it is: the exclusion from the agent read
surface at `0033:17-20`, "an eval score is a measurement of the hunter, and
letting the hunter read it is the one thing that would make the measurement
worthless", is right whichever way this goes, and it applies equally to
`playbook_test_verdict`.

### What would change the answer

If `grading.py` and `metrics.py` arrive, or whatever replaces them, and something
in this repo computes a per-ground-truth-entry verdict, then `gt_id`,
`gt_declared`, `gt_recallable` and the five buckets acquire producers and A
becomes small. Until then the number of missing values is fourteen, not one.

If ticket 84 is executed and its results are wanted A/B rather than pass or fail,
the comparability machinery in `0033` becomes the cheapest way to get it, and
retiring it would be a decision to write it again. That is the strongest
argument for keeping the tables, and it is an argument about intent rather than
about evidence: nothing in 84's criteria asks for a comparison across runs.

If `playbook_test_runs` grows a per-fixture recall or precision column, the two
designs collide and one of them has to go. Today they do not overlap: the eval
store scores a run against a fixture, and `playbook_test_runs` counts what one
Playbook did against one fixture on one side of a pair.
