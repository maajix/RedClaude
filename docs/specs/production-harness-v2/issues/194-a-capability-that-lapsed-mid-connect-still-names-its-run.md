# 194 — A capability that lapsed mid-connect still names its run

**What to build:** A refusal written after the Tool run that authorised it has closed is still filed under that run.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** Database `rk2here`, 2026-08-25.
      `rk run` and `rk db migrate` both refused on the standing gate:

      ```
      standing:receipt_integrity
      1 problem(s): (egress_without_tool_run,"stg.spot.account.here.com OPTIONS /",1)
      ```

      R453 is `OPTIONS https://stg.spot.account.here.com/`, `blocked / target
      unreachable`, `scope_class = 'target'`, both pinned addresses on the row,
      `ts_egress` set, `waited_ms = 30059`, no Tool run. Its nine siblings to
      the same host under TR104 all carry the run. TR104 is the only run whose
      window covers the arrival, it closed `error` under `decision = 'allow'`,
      and it closed at 23:57:07 — while R453, which left at 23:56:54, was still
      waiting out its connect timeout.

- [x] **The writer that did it.** `write_blocked_receipt` attributed the row by
      resolving the capability a second time, at write time, and
      `resolve_egress_capability` answers only for a run that is still
      `running` with an unexpired token. A host that never answers holds the
      request for the whole timeout, which is long enough for the run to close
      underneath it. The refusal that finally lands names nothing, and arm (a)
      reads it as egress with no hook receipt behind it — the one thing it
      exists to catch. One dead host stops the campaign.

- [x] **The door says which run it authorised.** Recovering it afterwards is
      not available: the runtime clears `egress_token_sha256` when it closes a
      run, and arm (h) requires exactly that. `proxy._refuse` writes
      `Authorization.tool_run_id`, resolved while the capability was live, onto
      the Receipt. The agent never reaches this field.

- [x] **Used only where it cannot loosen anything.** The stated run is read
      only when the capability resolves to nothing, only for a run in the same
      Program, and only for a run whose `decision` is `allow` — the last one so
      that arm (b) cannot be given an egress a denied run never had.

- [x] **The row corrected, with both guards.** Arm (a) is empty and arm (b) is
      empty, checked over the whole record in the migration itself.

- [x] **And the correction says a person meant it.** `receipts_emit_event` is
      AFTER INSERT, because `receipts` are insert-only, so correcting a column
      on one emits nothing and `check_event_log_integrity` arm (d) reported
      `row_last_write_unaccounted, receipts, 1` on the next gate. That is the
      check working. 20261123T000000Z registers the transaction in
      `suppressed_writes`, which is the row that says the silence was
      deliberate, rather than relaxing the arm.

## Why

The gate is right to stop a hunt for this shape. Egress with no receipt behind
it is the one claim this harness makes about itself, and a row that reads that
way must stop everything until somebody says which it was.

Which is why the fix is the writer and not the row. 20261114T000000Z corrected
rows for a sibling defect and left the writer making more; this file does both,
because a standing check that a normal dead host trips is a check that will be
answered by hand until it is ignored.

## What this does not change

Nothing about who may send what. The capability still decides authority, alone,
while it resolves. This is only about which run a refusal is filed under after
the target has already failed to answer.
