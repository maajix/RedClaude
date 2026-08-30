# 228 — One broken notifier halts the whole harness, and every POST costs an answer

**What to build:** Wall 1, a refusal that names the notifier that failed
rather than the question that went undelivered. Wall 2 is an operator
decision and is written down here so it can be made, not built.

**Blocked by:** nothing.

**Status:** proposed

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
   refusal that names `desktop` and its last error.
2. Wall 2 is answered by the operator: (a), (b), or neither, recorded here.
