# 218 — A corpus rewrite strands every open Task that already chose

**What to build:** A supported way for a pending Task whose frozen Playbook
selection no longer matches the installed corpus to choose again, so that
rewriting the corpus does not require hand-written SQL against a live
engagement.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

Ticket 101 rewrote all 50 Playbooks, so every `source_sha256` in the corpus
moved. The `rk2here` engagement was migrated onto it on 2026-08-29 and the next
`rk run` refused:

```
integrity_failed | corpus | T731 was selected playbooks/browser-framing/playbook.md,
                           which this installation does not carry at the digest
                           the selection froze
```

Measured over the whole engagement rather than off the one Task the run named:

```
316 selections, all 316 stale, across 142 Tasks
766 Tasks pending; 14 of them carry a stale selection; 36 rows, 8 of them active
223 Tasks done, 80 abandoned -- none touched, and none should be
```

The refusal is correct and this ticket does not ask for it to soften.
`execution.py:2775-2779` states why: a selection whose text moved "would
describe something other than what the model read, and a grading run against it
would be reading the wrong document."

## Where the mechanism is

Two lines decide it together.

`execution.py:357` — `RECORDED` counts **every** row for the Task:

```sql
SELECT count(*)::int FROM playbook_selections WHERE task_id = $1::uuid
```

`execution.py:2785-2788` only records a fresh selection when that count is zero.
So one surviving row -- including a row already `dropped_because` -- means the
Task never chooses again.

`execution.py:389-394` — `SELECTED` then returns the rows with
`dropped_because IS NULL`, and `:2800-2812` refuses on the first whose digest or
version does not match the installed Playbook.

The two together are the trap: the rows that keep `RECORDED` above zero are not
the same rows that `SELECTED` reads, so a Task can be permanently pinned to a
corpus that no longer exists by rows that were themselves already discarded.

## Why there is no way out today

`rk playbook` offers `evaluate` and `cost`. Neither re-opens a selection.
Nothing else in the CLI writes `playbook_selections`, and `went_stale_at` is a
warning surface only -- `0035_corpus_promotion.sql:237-239` reports
`stale_during_run` and changes nothing.

So the only path is SQL against a live engagement database, which is what was
done here, and it is written down as `drop-stale-selections.sh` in the
engagement directory rather than typed at a prompt.

## The wall, priced

```
WALL    execution.py:357 with :2785-2788. RECORDED counts dropped rows, so any
        surviving selection row -- active or discarded -- stops a Task from
        choosing again, and :2800-2812 then refuses on the frozen digest.
PRICE   Small either way, and both ends already exist. Either RECORDED counts
        only rows a run could still use (`dropped_because IS NULL`), which makes
        a Task with nothing but discarded rows choose again on its own; or a
        verb re-opens one Task's selection explicitly. The first is one
        predicate and needs no new surface; the second is auditable, which the
        first is not -- a selection that quietly disappears is a selection
        nobody can show an auditor.
PURPOSE An engagement should survive a corpus rewrite without hand-written SQL.
        The corpus is meant to be rewritten; ticket 101 is the second time.
RULE    capability before catalogue.
```

The two prices are not exclusive and the ticket leans to both: narrow
`RECORDED`, and record the re-open in `playbook_demotions` or beside it so the
row that vanished is still answerable.

## Why it is worth a ticket rather than a note

The engagement it was found in holds 4 Findings, 229 Hypotheses, 1847
Observations, 2408 Receipts and 833 Surface entities, and 766 Tasks that have
never run. Losing them to a corpus rewrite would be a real cost, and the only
thing standing between the rewrite and that cost was a person willing to write
a `DELETE` against a live database.

## Acceptance criteria

- [ ] **A pending Task with only stale selections runs again with no SQL.**
      Measured on a database where the corpus moved under it, not on a fixture
      built after the fact.
- [ ] **A finished Task keeps its frozen digest.** The audit reading of a
      completed run is what the freeze is for, and nothing here may touch it.
- [ ] **The re-open is answerable.** Whichever price is paid, an operator can
      ask later which selection was dropped and when. A row that silently
      disappears fails this.
- [ ] **The refusal at `execution.py:2800-2812` still fires** for a Task whose
      *active* selection is stale and which has not been re-opened. This ticket
      widens no door.

## What this does not change

`playbook_selections` freezing `playbook_sha256` and `playbook_version` at
selection. That is the mechanism that makes an old hunt result readable at all,
and this ticket depends on it.
