# 228 — One broken notifier halts the whole harness, and every POST costs an answer

**What to build:** Wall 1, a refusal that names the notifier that failed
rather than the question that went undelivered. Wall 2 is an operator
decision and is written down here so it can be made, not built.

**Blocked by:** nothing.

**Status:** in-progress -- wall 2 built and applied, wall 1 owed as `T228-01`

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
   refusal that names `desktop` and its last error. **Owed**, carried as
   `T228-01`.
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
* The risk rule is matched, but only at Program granularity, and that is a hole
  rather than a design. `live_route_grant_for` takes no rule argument at all;
  `gate_tool_call` guards the call with
  `EXISTS (SELECT 1 FROM route_grants g WHERE g.program_id = tr.program_id AND
  g.risk_rule = verdict ->> 'rule' ...)`, which asks whether the *Program* holds
  a grant under that rule and not whether *this* grant does. A Program holding a
  grant on route A under rule R and a grant on route B under rule R2 would let a
  call on route B firing rule R be answered by the route-B grant, because the
  unrelated route-A grant satisfies the `EXISTS`. With exactly one live grant
  the hole cannot fire -- the only row the `EXISTS` can match is the one
  `live_route_grant_for` would return -- so `rk2here` holds at most one until
  `T228-02` closes it. Closing it means giving `live_route_grant_for` a rule
  argument, which changes its signature and therefore its
  `runtime_verb_surface` row, so it is a migration and not an edit.
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

## Still owed

* `T228-01` -- acceptance 1. Wall 1 itself, untouched by any of the above.
* `T228-02` -- the Program-wide `EXISTS`, matched against the grant it returns
  instead. Until it lands, `rk2here` holds at most one live `route_grants` row.
* `T228-03` -- two rough edges on the applied migration, which needs a follow-up
  migration because an applied one may never be edited. `grant_route` lets an
  hours value that floors to zero fall through to a raw
  `route_grants_expires_after_grant` violation rather than refusing it in its
  own words, and the audit trigger calls every UPDATE on `route_grants`
  `route_grant.revoked`, including one that revokes nothing.
