# 108 — A tool result is narrower than the value it was built from

**What to build:** The three fields a tool answer loses at the last hop --
`stderr`, the scope class of an exchange and the Identity it was made as -- and
the rule that a field is either carried or declared dropped.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `stderr` reaches the model. `tool._streams`
      (`src/redkraken/tool.py:790-806`) files both streams deliberately --
      "Stdout and stderr are always kept, empty or not. An empty stream is a
      fact about the run" -- and `tool.serve` (`tool.py:519-536`) returns
      `stdout` as a bounded head and an `outputs` list carrying only
      `("stream", "output_name", "kind", "label", "byte_size")` per item. The
      stderr bytes are never returned in any form. A tool that failed tells the
      model its exit code and its possibly empty stdout and hides the
      diagnostic it wrote.
- [ ] The exchange's scope class reaches the model. The door resolves it and
      writes it on the Receipt; it is the value `src/redkraken/browser.py:454`
      reads back out of Receipts to fill `browser_step_results.scope_class`, and
      the browser driver is forbidden from computing its own for a stated reason
      (`src/redkraken/browser_driver.py:525-528`: "`scope_class` is not here on
      purpose. What class a URL belongs to is the door's answer"). The agent's
      `http_request` answer carries no scope class, so a model cannot tell an
      in-scope 404 from an out-of-scope one.
- [ ] The Identity the exchange was made as is named in the answer. The runtime
      chooses it before the run opens, which `roster.py:800-805` gives as the
      reason there is no `identity_slot` argument, and the same paragraph is why
      the answer has to say which one was spent: an identity-differential
      reading cannot tell the model which of two runs was which. Ticket 97 owns
      what an identity slot is; this ticket owns naming the one that was used.
- [ ] The rule is written down where it can be checked rather than restated per
      field. For each boundary where a rich runtime value becomes a
      model-facing dict, every field of the source is either carried or named in
      a constant with a reason: `proxy._answered` against
      `http.client.HTTPResponse`, `_launch._spend` against `proxy.Answer`,
      `tool.serve` against `isolation.ToolProcess`. Adding a field to one of
      those sources without deciding about it fails.
- [ ] Ticket 94 owns the response headers at the same boundary and is not
      re-opened here. Its finding is that the loss is two layers deep --
      `proxy.Answer` never carried them, so fixing `_spend` alone is not enough
      -- and the same is true of the scope class, which is on the Receipt rather
      than on the response.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` sections 5.3 and 5.5, and its
gate G7, which is the one that generalises them: "A result is not narrower than
the value it was built from." Section 5.6 lists what does not lose information,
so the finding is read as specific rather than as a general complaint: the
validation packet is handed over whole, the bounded reads report what they
dropped and why, and `_spend` already reports `byte_size` and `truncated` beside
the excerpt so a truncated body is legible as truncated.

`docs/research/wiring/22-corpus-instruction-wiring.md` section 2.4 counts the
corpus cost of the same boundary: twenty-six Playbook bodies tell the model to
read a response header, six tell it to measure timing, and the answer shape is
eight keys.
