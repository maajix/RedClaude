# 106 — Hand back the Artifact labels for the exchange the door just filed

**What to build:** The Artifact labels for a request and its response, returned
from `mcp__rk2__http_request` beside the Receipt label, so that a run can name
the bytes it just fetched.

**Blocked by:** nothing. It is independent of ticket 94, which hands back the
response headers out of the same answer, and the two touch the same return
statement.

**Status:** ready-for-agent

- [ ] The label already exists at the moment the Receipt does, and the ticket
      rests on that rather than minting anything.
      `hold_receipt_transcripts()`
      (`src/redkraken/migrations/20260811T220000Z__a_stored_transcript_is_held_by_name.sql:45-68`)
      is an `AFTER INSERT` trigger on `receipts`, enabled `ALWAYS` at `:83`,
      that writes one `artifact_references` row per agent-visible transcript the
      Receipt names -- request and response both -- and the `AF` label comes off
      that row. So an exchange that produced a Receipt label has produced two
      Artifact labels in the same transaction, and nothing hands them over.
- [ ] `_launch._spend` returns them. Today it returns eight keys and none is a
      label but `receipt`: `served`, `status`, `receipt`, `decision`, `detail`,
      `byte_size`, `truncated`, `body` (`src/redkraken/_launch.py`, in `_spend`,
      declared at `:680` as of commit `cf70c5f`; the file is under concurrent
      edit for ticket 94, so the symbol is the reference and the line is not).
- [ ] The Contract needs no change and the ticket says so.
      `mcp__rk2__http_request` already declares
      `writes=("receipts", "artifacts", "artifact_refs")`
      (`src/redkraken/roster.py:750`), which is exactly what
      `register_proxy_artifacts` (`0040_receipt_contract.sql:13-36`) and the
      transcript trigger write between them. What changes is the answer, not
      the declaration.
- [ ] The two labels are distinguishable as request and response in the answer.
      `compare_responses` takes `first` and `second` and the registry says why
      order is part of the call
      (`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:457-467`:
      "`only_in_first` is a different claim from `only_in_second`"), so an
      answer that returned an unordered pair would push that decision onto a
      model.
- [ ] Only agent-visible bytes get a label, and the ticket does not widen that.
      The trigger's `WHERE` clause admits a hash only where the Artifact is
      `agent_visible`, unencrypted and unpurged, and the migration says why at
      `:40-43`: "What it must not do is name a wire hash: those are the sealed,
      credential-bearing halves, and a label pointing at one would be exactly
      the reachability `check_wire_artifact_secrecy` rule 3 exists to refuse."
- [ ] The label is returned and is not yet resolvable in the same run, and the
      ticket states that plainly rather than implying otherwise. Ticket 107 is
      what makes `mcp__rk2__get_artifact` answer for it; this ticket is what
      makes there be something to ask about.

## Why

`docs/research/wiring/22-corpus-instruction-wiring.md` section 6 ranks this
first of the three highest-leverage surface repairs: "Return an `artifact_label`
from `http_request` -- unblocks the evidence step of 39 playbooks and all 5
partials." Thirty-nine of the fifty shipped Playbooks name `compare-responses`
in the body and are told to difference two answers the run just fetched, and
neither label is obtainable; the five Playbooks the same report grades `partial`
rather than `not runnable` all break at this exact step and at no other.

`docs/research/wiring/21-agent-surface-wiring.md` section 5.2 states the same
finding from the tool side: "`net.request` and `exec.tool_run` are designed to
compose -- `jq`, `js_parse`, `js_map`, `js_routes` and both skill scripts all
take an `artifact`-kind argument -- and an agent that has just fetched a
JavaScript bundle has no label to hand to `js_parse`."

The Contract's own comment at `roster.py:648-656` explains the narrowing it does
make and, read today, describes the gap exactly: "no label lists the ones this
packet reached, which is the only way a child learns a label exists".
