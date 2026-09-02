# 228 — One broken notifier halts the whole harness, and every POST costs an answer

**What to build:** Wall 1, a refusal that names the notifier that failed
rather than the question that went undelivered. Wall 2 is an operator
decision and is written down here so it can be made, not built.

**Blocked by:** nothing.

**Status:** resolved

Both walls were built and applied. Wall 1 shipped as `T228-01` in
`20270106T000000Z__a_finding_announces_itself_through_the_pipe_a_decision_uses.sql`
(`applied_seq 243`), together with ticket 229, because both rewrite
`check_control_surface` and a migration replaces a function WHOLE.

## What was measured, 2026-08-30

`rk2here` stopped at 10:10 and stayed stopped. Every `rk run` and every
`rk db migrate` exited 9 with the same refusal:

```
integrity_failed  standing:control_surface
  2 problem(s): (decision_unannounced,D27); (decision_unannounced,D28)
```

The supervisor restarted the hunt four times inside fifteen minutes, saw
`lap 01..03 -> refused | exit 9` each time, and stood down correctly. Nothing
else on the machine was wrong.

Four levels down, this is what had happened:

```
channel | enabled | argv
desktop | t       | notify-send redKrakenV2 {label} {body}
push    | f       | (empty)

label | channel | attempts | delivered | last_error
D26   | desktop |    4     | never     | exit 1: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown
D27   | desktop |    5     | never     | exit 1: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown
D28   | desktop |    5     | never     | exit 1: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown
```

`notify-send` needs a session bus. This host has none. `desktop` was the only
enabled channel, it spent its five attempts, `check_control_surface` arm 4
then held -- correctly, by its own text: *"an open question that nobody was
told about and nobody will be"* -- and the harness refused to do anything at
all until a human intervened. The seed comment on `push` predicted the shape
of this exactly: *"Disabled until an operator fills it in."*

Cleared by filling it in. `push` now carries an argv against the operator's
own ntfy server and both questions were delivered on the first sweep:

```
D27 was carried to the push channel
D28 was carried to the push channel
every open question reached a human or is still being tried
```

## WALL 1 — the refusal names the wrong thing

`check_control_surface`, arm 4
(`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:960-971`).

Both ends read. The sender: `decisions.py:50` asks the database for the
predicate rather than deciding it in Python, on purpose and rightly -- *"a
second copy in Python would be a second answer."* The receiver: the arm
returns `d.label`, so `detail` is `D27`, and the operator is handed the name
of a question when what is broken is a channel.

`decision_notifications.last_error` already holds the sentence that ends the
investigation. It is written by `record_notification_attempt` and read by
nothing that refuses.

### PRICE

One migration. The arm returns the channel and its complaint beside the
label, so the refusal reads

```
(decision_unannounced,D27 -- desktop: GDBus.Error:...ServiceUnknown, 5/5 attempts)
```

`ERROR_BYTES` is already 200 and already clipped at write time, so nothing
new bounds it. No Python: `decisions.py` prints `detail` verbatim today.

`check_control_surface` is replaced whole by every migration that touches
it, which is the corpus idiom, so the diff is one arm inside a reproduced
body. One test class over a channel with a spent attempt count.

### RULE

*Capability before catalogue.* The capability -- an error column, populated,
on the row the arm already joins -- is built. Nothing reads it.

## WALL 2 — an approval covers one request, and a POST needs one every time

Not a defect. An operator decision, priced here so it can be made.

`canonical_request`
(`20260924T000000Z__a_request_may_carry_a_body.sql:511-530`):

```sql
bb := coalesce(p_args -> 'body_allowed' = 'true'::jsonb, false);
...
    'reusable', NOT bb,
...
  || CASE WHEN bb THEN jsonb_build_object('nonce', p_nonce) ELSE '{}'::jsonb END;
```

`equivalence_key` is `sha256(digest::text)` and the digest carries the
nonce, so a body-bearing call's key is unique by construction. The grant
lookup (`0026_human_control.sql:711-714`) matches on that key, so it can
never hit. D25 and D27 are the same question by every field except one:

```
D25  ... "nonce": "T887" ...  approved, grant to 08-31 08:45
D27  ... "nonce": "T474" ...  pending
```

The reasoning is sound and is written in the file: *"the bytes themselves
are never in this document to be hashed: they are chosen by the child after
the row was written, and the door that carries them holds no write on
`tool_runs`."*

The consequence is the cost. `st.p.account.here.com/token` is an OAuth token
endpoint the hunt must POST to repeatedly. Four approvals were spent on it in
one day -- D25, D26, D27, D28 -- and each one halted the campaign until a
human answered. There is no route-level grant in this schema: `grep` finds no
table named for one, and `grant_expires_at` hangs off `pending_decisions`,
which is keyed by digest.

### PRICE, two ways out

**(a) Hash the bytes.** The door writes the body digest before the call, and
the key becomes reusable because it describes what was really sent. This is
the honest fix and it is large: the door holds no write on `tool_runs` by
design, so it means a new writer across a trust boundary, and the boundary is
the thing being protected.

**(b) A standing route grant.** The operator states, once, that
`POST https://st.p.account.here.com/token` with identity `here-secondary` is
approved until T, whatever body it carries. One new table keyed on
`(program, method, scheme, host, port, path_template, identity_slot)`, one
lookup ahead of the digest lookup, one operator verb, one closure arm so a
grant with no expiry cannot exist. Small.

It is also a real widening: an approval that used to cover one call would
cover a route for a period. That is the operator's judgement to make and not
this ticket's, which is why it is written here rather than built.

### PURPOSE

The harness is meant to run unattended for hours. Under (b) it can. Under
neither, a campaign against any API with a token endpoint stops at every
POST, and the operator's own approval from an hour ago does not help.

## Acceptance

1. A host with no session bus and a failing `desktop` channel produces a
   refusal that names `desktop` and its last error. **Done**, `T228-01`. The
   arm returns
   `D5 -- desktop: exit 1: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown, 5/5 attempts`,
   a disabled channel is marked as such, and a decision fanned out to nothing
   says `fanned out to no channel`. `ProxyEgressTest` holds both cases.
2. Wall 2 is answered by the operator: **(b), on 2026-08-30.** Built as
   `20270102T000000Z__an_approved_route_stays_approved_until_it_expires.sql`,
   applied to `rk2here`, and driven end to end: `RG1` over
   `POST st.p.account.here.com/token` answers a second body-bearing call
   without opening a question. Two follow-ups are owed and are named below.

## What (b) shipped as

`route_grants`, one row per standing statement, plus `live_route_grant_for`,
`grant_route`, `revoke_route_grant`, and `rk decision grant-route` /
`revoke-route`. `tests.test_database.RouteGrantTest` holds the database's half
of it and `tests.test_operator.RouteGrantTest` holds the console's.

The verb takes a decision **label**, not a route, and that is the safety
property rather than a convenience: the route, the port, the path template,
the identity slot and the risk rule all come from the digest the runtime
built, so an operator can widen a question they answered yes to and cannot
manufacture one they were never asked. A decision that is not `approved` is
refused by name.

Five lookups against the live `rk2here` digests, inside a rolled-back
transaction. One matches and four deliberately do not:

```
D27 itself (same route)      -> RG1
D28 (different identity)     -> no match
D21 (different route)        -> no match
host_in_scope false          -> no match
unapproved_identity_slot set -> no match
```

* Only `gate_tool_call` reads it. `open_impact_replay` and `rk2_pivot_refusal`
  reach `live_grant_for` too and keep asking: a grant to POST a token endpoint
  is not consent to demonstrate impact, and ticket 226's whole point is that a
  demonstration costs an operator answer. A `DO` block in the migration fails
  if either of them ever starts reading it.
* The risk rule is matched against the grant that answers. It was not at
  first: `live_route_grant_for` took no rule argument and `gate_tool_call`
  guarded the call with
  `EXISTS (SELECT 1 FROM route_grants g WHERE g.program_id = tr.program_id AND
  g.risk_rule = verdict ->> 'rule' ...)`, which asks whether the *Program* holds
  a grant under that rule and not whether *this* grant does. A Program holding a
  grant on route A under rule R and a grant on route B under rule R2 let a call
  on route B firing rule R be answered by the route-B grant, because the
  unrelated route-A grant satisfied the `EXISTS`. With exactly one live grant
  the hole could not fire, so `rk2here` was held at one until `T228-02` closed
  it. **Closed** in `20270107T000000Z`: the rule is an argument,
  `live_route_grant_for(uuid, jsonb, text)`, so the row that answers is the row
  that was checked, and the Program-wide `EXISTS` is gone.
* `host_in_scope` and `unapproved_identity_slot` are read from the **live**
  digest at every lookup rather than stored at grant time, so a host leaving
  scope withdraws its grants in the same breath, with no sweep to run.
* An expiry is mandatory and is a CHECK.
* `live_grant_for` is untouched, asserted against its own text, so no approval
  that exists today means anything different tomorrow.

A `pending_decisions` row was tried first and refused by the schema, which was
right to: `pending_decisions_key_matches_digest` requires the key to be
`sha256(request_digest)`, and `pending_decisions_names_one_subject` requires
every row to name an agent run, a tool run or a test. A standing grant names
none of them, because it is not about a run.

## What the dry run did not catch, and could not

Those five lookups called `live_route_grant_for` directly, so not one of them
went through the guard in front of it -- and the guard was wrong. The first
build of `gate_tool_call`'s route-grant branch read `verdict ->> 'risk_rule'`.
`assess_call_risk` returns
`jsonb_build_object('risk_class', base, 'rule', rule, 'question_code', qc)`
(`0026_human_control.sql:310`), so that key was NULL on every call, the `EXISTS`
never held, and the whole branch was dead: the table would have been filled,
audited and never read. `risk_rule` is the `pending_decisions` COLUMN the value
lands in once `park_for_human` has written it down, which is where the wrong
name came from; every other reader in the corpus uses `->> 'rule'`.

The lesson is the one the file now carries as a comment: a SQL change is proven
by driving the caller the runtime drives, not the function under test.

## The follow-ups, and what closed them

`T228-02` and `T228-03` shipped together as
`20270107T000000Z__a_route_grant_answers_only_the_rule_it_was_granted_under.sql`
-- one file, because all three defects rewrite `gate_tool_call` or `grant_route`
and a migration replaces a function WHOLE, so two files would mean the later one
silently discarding the earlier one's change.

* `T228-02` -- the Program-wide `EXISTS` is gone and the rule is an argument.
  `live_route_grant_for(uuid, jsonb, text)`, registered with a space after each
  comma; the two-argument row was deleted in the same transaction. **The
  one-grant ceiling on `rk2here` is lifted.** Proved on live inside a rolled-back
  transaction: with a second grant added over the same route under
  `net_borrowed_identity`, the old code admitted `TR792` under that grant and
  named `D25` as its authority; the new code admits it under `RG1` and names
  `D27`, which is what it answered before the second grant existed.
* `T228-03(a)` -- `grant_route` computes its window once and refuses one that
  rounds down to nothing in its own words, instead of letting `p_hours < 1/60`
  fall through to a raw `route_grants_expires_after_grant` violation.
* `T228-03(b)` -- `event_table_config` names one `updated_type` per table and
  cannot say two things, so the single `route_grant.revoked` was made true rather
  than weakened: `route_grants_revocation_only` refuses any UPDATE that is not
  the revocation, the way `callback_channel_bindings` holds its own single
  `callback.released`. It closes a second thing on the way -- an
  `UPDATE route_grants SET expires_at = ...` would have extended a standing
  egress grant without passing `grant_route`'s "widen a yes, never manufacture
  one" gate, and the audit would have called that extension a revocation.
* `T228-03(c)`, carried from an earlier handoff -- `grant_route` now requires
  `grant_expires_at IS NOT NULL` on the decision it widens. `answer_decision`
  writes `now() + p_grant`, so an approval given with no period lands NULL, and
  since `20270103T000000Z` the gate resolves a grant back through `granted_from`
  under arm (e)'s two conditions. A grant widened from such an approval was
  written, audited, and unable to admit a single call.
