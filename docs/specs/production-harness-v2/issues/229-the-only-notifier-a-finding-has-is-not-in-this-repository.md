# 229 — The only notifier a Finding has is not in this repository

**What to build:** The finding-notification *mechanism* as harness code, on the
outbox the decision pipe already owns, with the same guarantees: a durable row,
a retry, an attempt ceiling, a backoff, a timeout, a delivered stamp, and a
standing check that fires when nobody was told. ntfy stays one argv an operator
fills in, and its URL and topic never enter this repository.

**Blocked by:** nothing. 228 wall 2 is built and the `push` channel is live and
delivering; this ticket is about the second subject the pipe cannot carry.

**Status:** resolved

Option (b) shipped as
`20270106T000000Z__a_finding_announces_itself_through_the_pipe_a_decision_uses.sql`
(`applied_seq 243`), in one file with ticket 228 wall 1 because both rewrite
`check_control_surface`. `tests.test_database.FindingNotificationTest` holds it.
`git diff src/redkraken/decisions.py` is empty, as the recommendation predicted.
Steps 9 and 10 remain ungradable by the running system, as this ticket says.

## What was measured, 2026-08-30

All read-only against live `rk2here` under
`PGOPTIONS='-c default_transaction_read_only=on'`, with a hunt running.

The decision pipe, which is the half that works:

```sql
SELECT n.channel, count(*), count(n.delivered_at), max(n.attempts)
  FROM decision_notifications n GROUP BY n.channel ORDER BY 1;
```
```
channel | rows | delivered | max attempts
desktop |   28 |         0 | 5
push    |    2 |         2 | 1
```

```sql
SELECT channel, enabled, cardinality(argv), max_attempts, backoff
  FROM notification_channels ORDER BY 1;
```
```
desktop | f | 3  | 5 | 00:00:30
push    | t | 14 | 5 | 00:00:30
```

`desktop` is disabled by D-10 -- this host is headless, `notify-send` has no
session bus, and every question was burning five failed attempts on a channel
that tells nobody. `push` carries the operator's own ntfy argv and has delivered
2 of 2 on the first attempt. Its 14 argv elements were **not** read for this
ticket; the count is the whole measurement that was needed.

The finding pipe, which is the half that is not here:

```sql
SELECT severity, status, count(*) FROM findings GROUP BY 1,2 ORDER BY 1,2;
```
```
info | candidate | 8
low  | validated | 1
```

```
wc -l out/notified.txt                 ->  0
out/rk2here-w2-notify.log              ->  empty
```

The state file is empty and the log is empty, so the finding notifier has
delivered **nothing** on this engagement at its own default floor
(`RK_NOTIFY_MIN=medium`, `notify.sh:31`) -- and nothing in the harness knows
that, because nothing in the harness is watching. `hunt.sh:103` runs it once per
lap and ends `|| true`.

And ntfy is not integrated anywhere:

```
grep -rn "ntfy" . --exclude-dir=.git
  src/redkraken/migrations/0026_human_control.sql:549          (a comment)
  docs/prototype/schema/migrations/20260807T190900Z__...:549   (the same comment)
  docs/specs/production-harness-v2/issues/228-...md:46         (prose)

find /home/majix/redKrakenV2 -name 'notify*.sh' -not -path '*/.git/*'
  (nothing)
```

Two comments and one ticket's prose. `notify.sh` lives only at
`/home/majix/engagements/here-technologies-2026-08-25/notify.sh`. It queries the
database itself, runs `curl` itself, dedups in its own `out/notified.txt`, and
does not travel: a second engagement gets no finding notification until somebody
copies the file.

## WALL

`record_notification_attempt` (`src/redkraken/migrations/0026_human_control.sql:635`)
hardcodes one table:

```sql
    UPDATE decision_notifications n
       SET attempts = n.attempts + 1, ...
```

Both ends read, because a wall is a claim about an interface.

* **Sender.** `due_notifications(p_program uuid)`
  (`0026_human_control.sql:618`) returns
  `(notification_id, label, body, deadline_at, channel, argv)` over
  `decision_notifications JOIN pending_decisions JOIN notification_channels`.
  It cannot return a subject that is not a decision.
* **Receiver.** `src/redkraken/decisions.py:42-46` selects those columns by name
  and hands `notification_id` straight back to `record_notification_attempt`
  (`decisions.py:46`, `:179`). The Python is entirely generic over whatever the
  two verbs say -- and that is deliberate, `decisions.py:47-52`: *"a second copy
  in Python would be a second answer."*

The pipe is therefore generic in Python and subject-bound in SQL at **both**
ends. A second subject cannot be unioned in without first deciding whose id a
`notification_id` is, and that is the load-bearing decision priced below.

Second half of the same wall: `check_control_surface()`'s `decision_unannounced`
arm
(`20260814T020000Z__the_operator_answers_and_the_work_resumes.sql:960-971`)
proves that a pending decision reached a human, and there is **no equivalent for
a Finding**. A Finding nobody was told about is not a shape any standing check in
this corpus can see -- the same vacuous-green failure ticket 226 names for the
kill chain.

## PRICE

### The exposure chain, hop by hop

A capability that exists is not a capability that is reachable. Four of the
eight hops are already built and already running.

| # | hop | state |
|---|-----|-------|
| 1 | **A fan-out seam on the finding side.** `state_severity(uuid, text, text, text)` (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1725`) is the *only* writer of `findings.severity`, asserted at `:2176`, and it writes one `severity_statements` row per statement. That table already carries `severity_statements_emit_event`. It is the exact counterpart of `pending_decisions` under `fan_out_decision_notification` (`0026:599`). | **exists** |
| 2 | **A severity floor.** `rk2_severity_rank(text)` (`20260905T000000Z__v1_state_crosses_into_this_schema_as_imported.sql:233`) already orders the five bands. This is the `medium` that `notify.sh` keeps in an env var. | **exists** |
| 3 | **A channel.** `notification_channels` (`0026:532`) holds argv, `enabled`, `max_attempts`, `backoff`, a rationale, and a placeholder whitelist (`assert_channel_placeholders`, `0026:553`, exactly `{label}`, `{body}`, `{deadline}`). | **exists** |
| 4 | **A sweep that runs.** `hunt.sh:70` runs `rk decision sweep` once per lap. `decisions.py:236` executes an argv with no shell, `DELIVERY_SECONDS = 10`, `BODY_BYTES = 400`, `ERROR_BYTES = 200`. | **exists and running** |
| 5 | `due_notifications()` returning a Finding. | **owed** |
| 6 | `record_notification_attempt` recording one. | **owed** |
| 7 | A `check_control_surface` arm that fires on an unannounced Finding. | **owed** |
| 8 | The `decision_queue_reachable_by_agent` arm (`20260814T020000Z__...:898-903`) names `decision_notifications` and `notification_channels` in a **fixed string list**. A new table not added there is reachable by `rk2_state` with nothing to say so. This hop is invisible unless somebody walks it. | **owed** |

### What removing the wall costs

* **One migration.** No applied migration may be edited; `0026_human_control.sql`
  and the 2026-08-14 file are both applied. `check_control_surface` is in the
  corpus idiom that is replaced WHOLE by any migration touching it, so the diff
  is two arms inside a reproduced body.
* **Registrations, each enforced by a standing check.** A new table owes
  `event_table_exempt` (the sibling row is
  `0030_corpus_corrections.sql:128`: *"outbound notification attempts;
  decision.requested is the event"* -- notifications are audited through their
  subject, not on their own), `purge_cascade_edges(<table>, program_id)`, and one
  `runtime_table_surface` row per privilege. `decision_notifications` holds
  SELECT, INSERT, UPDATE and DELETE for `rk2_runtime`, so four. A new function
  owes a `runtime_verb_surface` row, and the verb string has a SPACE after each
  comma.
* **Tests.** The sibling is `tests.test_database.ProxyEgressTest` -- it opens at
  `:8203`, runs to the next top-level class at `:11663`, and already holds the
  three sweep cases at `:10744`, `:10774` and `:10820`. Do not go looking for a
  class named for notifications; there is none, and that is where these live.
  `tests/test_decisions.py` (130 lines, `CommandTest` and
  `ChannelTest`) needs nothing if `_command` and `_run_channel` are unchanged.
* **`src/redkraken/decisions.py`.** Zero changes under the recommended option.
  Say so in the acceptance and prove it with an empty `git diff` on that file.
* **`tests/test_audit.py:76`** freezes the audit report line, including the
  ticket count. Writing *this* ticket already moved it 227 -> 228. Any further
  ticket moves it again.

### What verifying it costs, honestly

Gate 5 is a full `tests.test_database` run -- 1533 tests at the last green run.
The operator's own figure is **about 25 minutes**; it was not re-timed for this
ticket, because timing it means running it. The part that is certain and is the
real cost is written in the engagement SPEC: the run **rotates every
cluster-global `rk2_*` password on 127.0.0.1:55433**, which is the cluster the
LIVE `rk2here` engagement database runs on. Building this means:

1. `touch out/STOP` and wait for the lap in flight to finish.
2. Run the suite.
3. `/home/majix/engagements/yekta-first-hunt-2026-08-22/restore-roles.sh`.
4. `rm -f out/STOP && setsid nohup ./supervise.sh >/dev/null 2>&1 &`

Budget the hunt outage, not the test minutes. Do not run
`tests.test_database`, `tests.test_isolation` or `tests.test_release` while the
hunt is live.

## PURPOSE

SPEC condition 2 is *"At least one Finding reaches severity `medium` or above
and is `validated`."* The medium+ Finding is what the run exists to produce, and
the operator learning about it is the deliverable, not a courtesy.

**Does the workaround still serve that purpose? No, and it is measured.**
`notified.txt` is 0 lines and the notify log is empty: the script has never
delivered a message on this engagement at its default floor. When it does fire,
a failed `curl` prints one line to `out/<tag>-notify.log` and the lap continues,
because `hunt.sh:103` ends `|| true`. If the ntfy container is down at the moment
the first medium+ Finding lands, that Finding is swallowed silently, there is no
retry, no attempt ceiling, no delivered/undelivered record and no standing check,
and nothing in the harness knows.

## RULE

**Capability before catalogue** -- the same rule 228 wall 1 cites, for the same
reason. The outbox, the fan-out trigger shape, the retry, the backoff, the
attempt ceiling, the placeholder whitelist, the no-shell executor with a timeout,
and a sweep that already runs once per lap are all built and all in production.
What is missing is the catalogue entry: one more subject the pipe is allowed to
carry. Not "none".

## The ntfy URL and the topic never enter this repository

An ntfy topic is a bearer secret: whoever knows it can both read and publish to
it. It stays in `notification_channels.argv` on the operator's own row in the
database, exactly where the live `push` channel carries it today.

Three reasons, all already argued in the corpus:

1. `notification_channels` is registered in `program_global_tables`
   (`0026_human_control.sql:542`): *"operator configuration of the machine, not
   of a program: a program that could add a channel could exfiltrate its own
   decisions."*
2. The `push` seed rationale (`0026_human_control.sql:545-549`) is precisely this
   position: *"an operator-supplied argv (ntfy, Pushover, an SSH-triggered
   script). Disabled until an operator fills it in, because an empty argv
   silently delivering nothing is worse than a channel that says it is off."*
3. `tools/check_secrets.py` treats the whole tree as publishable: *"it is a
   checkout an operator clones, and everything tracked or unignored in it
   travels."*

**A follow-up that proposes shipping a default ntfy endpoint is wrong.** Both
shapes of it fail. A *seeded* default is a shared secret committed to a
publishable checkout. A *non-secret* default is a topic anyone can subscribe to,
which is worse than no notification, because it looks like one. So:

* do not seed the `push` argv with a URL, host or topic;
* do not add an `RK_NTFY_URL` or `RK_NOTIFY_TOPIC` default anywhere in `src/`;
* do not add one to a migration, a test fixture, or a sample env file.

`notify.sh:32` carries a hardcoded LAN default for `RK_NTFY_URL`. Open the file
if you need the value; it is deliberately not quoted here, because a ticket that
printed the endpoint into the checkout would be doing the exact thing it is
telling you not to do. That default is correct *in an engagement directory that
is not a git repository* and becomes a defect the moment the same line lives in
this tree.

"Integrate ntfy into the harness" therefore means: the finding-notification
**mechanism** becomes harness code with the decision pipe's guarantees, and ntfy
remains one possible argv an operator fills in. The build is finished when a
fresh checkout on a fresh machine can carry a Finding to whatever channel its
operator configures, having shipped no endpoint of its own.

## The load-bearing question: whose id is a `notification_id`?

`record_notification_attempt` updates one named table. Carrying a second subject
means choosing. Three options, priced; there is not only one.

### (a) One generalised `notifications` table

* New table with a subject discriminator, plus a **backfill of the 30 live rows
  on `rk2here`** (28 `desktop`, 2 `push`). A data migration against a live
  engagement is the one shape this corpus has no idiom for.
* `fan_out_decision_notification` (`0026:599`), `due_notifications` (`:618`) and
  `record_notification_attempt` (`:635`) all re-pointed, each as a
  `CREATE OR REPLACE` in the new file.
* `check_control_surface` arms `decision_unannounced` **and**
  `decision_queue_reachable_by_agent` both re-pointed; the second names
  `decision_notifications` as a literal string.
* Registrations for the new name, and a decision about the old name's four
  `runtime_table_surface` rows, its `event_table_exempt` row and its
  `purge_cascade_edges` row -- leaving them points the catalogue at a dead table,
  removing them is a fifth thing to get right under a standing check.
* `decisions.py`: unchanged.
* **Cleanest end state. Largest migration, and the most ways to be wrong on a
  live database in the middle of a hunt.**

### (b) A sibling `finding_notifications`, UNION ALL'd into `due_notifications()` — RECOMMENDED

* One new table shaped on `decision_notifications` (`0026:576`), with
  `finding_id` where the decision table has `pending_decision_id`, and the same
  `attempts` / `next_attempt_at` / `delivered_at` / `last_error` columns and the
  same composite FK discipline.
* `due_notifications()` becomes a `UNION ALL` over the two, returning
  `deadline_at` as NULL for a Finding. **The signature does not change**, so the
  existing `runtime_verb_surface` row `due_notifications(uuid)` is untouched, and
  `decisions.py` is untouched: it selects `notification_id, label, body, channel,
  to_json(argv)` by name (`decisions.py:42-45`) and never reads `deadline_at`.
* `record_notification_attempt` becomes two UPDATEs, one per table. **The
  signature does not change**, so `record_notification_attempt(uuid, boolean,
  text)` is untouched. Ids are `uuidv7` primary keys in both tables, so exactly
  one UPDATE can ever match -- write that as a comment in the function, not as an
  assumption. The alternative, a second verb, costs a new `runtime_verb_surface`
  row **and** a change in `decisions.py`, and buys nothing.
* New registrations: `event_table_exempt`, `purge_cascade_edges`, four
  `runtime_table_surface` rows, and the new name added to the
  `decision_queue_reachable_by_agent` string list (hop 8).
* `check_control_surface` gains a `finding_unannounced` arm mirroring `:960-971`.
* **One migration, five registrations, one new check arm, one test class, no
  live backfill, no Python.**

### (c) A discriminator column on `decision_notifications`

* Cheapest migration on paper: add `finding_id uuid`, make
  `pending_decision_id` nullable, add a CHECK that exactly one is set.
* But `UNIQUE (pending_decision_id, channel)` (`0026:589`) does not constrain a
  Finding row, so a second unique index is owed anyway.
* The composite FK `(pending_decision_id, program_id) REFERENCES
  pending_decisions (id, program_id)` (`0026:590-592`) is the constraint that
  makes a notification *provably* about a decision in the same Program. A
  nullable column weakens it to "about a decision in the same Program, or about
  something this constraint cannot see."
* `due_notifications()`'s `JOIN pending_decisions` becomes a LEFT JOIN and
  `d.status = 'pending'` becomes a predicate that must be written not to drop
  every Finding row. A filter that silently becomes wrong is the exact D-09
  failure mode.
* The `decision_unannounced` arm at `:960-971` would keep passing **by accident**:
  its `NOT EXISTS` subqueries key on `n.pending_decision_id = d.id`, so a NULL
  row simply falls out of the join. Correct by luck is not correct.
* And the table's name becomes a lie, which is the cost that never shows in a
  diff.
* **Rejected.**

**Recommendation: (b).** It is the only option that changes no function
signature, therefore no `runtime_verb_surface` row for an existing verb, and
therefore no Python at all -- while leaving each subject its own table, its own
FK and its own check arm. (a) is the better schema and should be revisited only
if a third subject ever appears; doing it now means a live backfill during a
hunt for an end state that is not yet needed.

## Acceptance

- [ ] A `medium` severity statement written through `state_severity` on a
      fixture Program produces exactly one `finding_notifications` row per
      ENABLED channel, and an `info` statement produces none. The floor uses
      `rk2_severity_rank(text)` and is not a second spelling of the five bands.
- [ ] `due_notifications()` returns a decision row and a finding row in one
      call, and `rk decision sweep` delivers both.
      `git diff src/redkraken/decisions.py` is empty.
- [ ] `record_notification_attempt` on a finding notification id increments
      `attempts` on `finding_notifications` and leaves every
      `decision_notifications` row byte-identical.
- [ ] `check_control_surface()` gains a `finding_unannounced` arm that fires
      when a medium-or-above Finding has no delivered notification and no
      enabled channel with attempts left, and returns zero rows on a green
      fixture. The arm names the CHANNEL and its last error, not only the
      Finding -- 228 wall 1's lesson, applied here rather than repeated.
- [ ] All four registrations exist and all four standing checks return zero
      rows: `event_table_exempt`, `purge_cascade_edges(finding_notifications,
      program_id)`, four `runtime_table_surface` rows, and
      `finding_notifications` added to the `decision_queue_reachable_by_agent`
      string list.
- [ ] `PYTHONPATH=$PWD/src:$PWD .venv/bin/python tools/check_secrets.py` exits
      0, and `grep -rniE 'ntfy|192\.168|:8090|NOTIFY_TOPIC' <the new migration>
      src/` returns nothing.
- [ ] Full `tests.test_database` green, then `restore-roles.sh`, then the hunt
      restarted. Record the outage window in the engagement HANDOFF.
- [ ] The migration applied to live `rk2here` inside `BEGIN; ... ROLLBACK;`
      first and driven through the caller the runtime drives -- D-09: a SQL
      change is proven by driving the caller, not the function under test --
      then applied for real, and `rk db verify` exits 0.
- [ ] A real medium-or-above Finding on live `rk2here` reaches the operator's
      phone through the `push` channel and sets `finding_notifications
      .delivered_at`.
- [ ] `notify.sh` and its `notified.txt` are either retired from the engagement
      or explicitly kept as a deliberate second, independent path, and which one
      is recorded.

**2 of 10 steps cannot be graded by the running system.**

* Step 9. Nothing in the harness can observe that a phone buzzed. `delivered_at`
  records that `curl` exited 0, which is the ntfy server accepting the message --
  not a human reading it. The decision pipe has exactly the same ceiling and does
  not claim more; do not build a claim here that the older half of the same pipe
  cannot make. Grade it by hand: the operator says whether the push arrived.
* Step 10. `notify.sh` is not in this checkout (`find` returns nothing), so no
  gate in this repository can see it, assert on it, or notice it was deleted. It
  is an operator decision recorded in the engagement's `HANDOFF.md`, not a repo
  test. Pricing it to become gradable would mean moving the script into the
  repository -- which is the opposite of what this ticket builds, since the
  script is exactly the thing being replaced.

The other eight are gradable by a test in `tests.test_database`, by a standing
check returning zero rows, or by a gate exit code.
