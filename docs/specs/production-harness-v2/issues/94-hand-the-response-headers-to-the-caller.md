# 94 — Hand the response headers to the caller

**What to build:** The target's response header names and values on the child's
side of `mcp__rk2__http_request`, and the decision about which surface carries
them. The bytes are already in this process and already hashed; what is missing
is the one statement that hands them over.

**Blocked by:** nothing. Nothing in this ticket widens what the door may send,
so it waits on no other capability.

**Status:** resolved

- [x] A child that called `mcp__rk2__http_request` can read the response headers
      of the exchange it just made. Today it cannot, and the loss is one dict
      wide: the door passes them into `_answer` as `headers=agent_back`
      (`proxy.py:3123-3128`) and the handler returns exactly `served`, `status`,
      `receipt`, `decision`, `detail`, `byte_size`, `truncated` and `body`
      (`_launch.py:726-735`). The headers reach the boundary and stop there.
- [x] The ticket says which surface carries them -- the tool result, the
      transcript Artifact the Receipt already names, or both -- and says which
      of *reading* and *citing* each surface answers. The transcript is not a
      third option that avoids the choice: `transcript` is the start line, the
      headers and the body concatenated (`proxy.py:789-798`), `wire_received` is
      built from it (`proxy.py:2831`) and the Receipt names it by hash, so every
      header of every exchange is already stored. What no child can do is name
      that Artifact and get a header out of it.
- [x] The six names the agent view already drops are absent from whatever the
      child reads. `WIRE_RESPONSE_HEADERS` is `authentication-info`,
      `proxy-authenticate`, `proxy-authentication-info`, `set-cookie`,
      `set-cookie2` and `www-authenticate` (`proxy.py:348-357`), removed by
      `response_for_agent` (`proxy.py:645-656`); a leased Identity's own
      renderings are removed on top of that by `project_identity_response`
      (`proxy.py:659-698`). A reading that wants a cookie attribute states that
      it is reading the target's behaviour and the request side, not the
      `Set-Cookie` line.
- [x] What the child reads is bounded. The body already is -- `_launch.py:726`
      truncates it at `packet.DEFAULT_EXCERPT`, 4096 bytes -- and a header list
      with no ceiling is a second unbounded path into the model's context out of
      a document the target wrote.
- [x] `header_policy_observed` becomes fillable by a child from something the
      child can actually read. The kind is evidential with provenance
      `{receipt,tool_run}` (`0018_vocabularies.sql:235`) and has been since 018;
      no agent-reachable surface has ever carried a header, so an Observation of
      that kind is a claim with a provenance record that does not hold the fact.
- [x] If the answer is that a header is *citable* and not merely readable, the
      projected column lands on the live receipt projection. Research file 09
      names `20260813T090000Z__a_recon_run_becomes_typed_surface.sql:1449-1475`
      for this; that reference does not check out any more -- `v_records` was
      redefined twice after it, and the live receipt arm is
      `20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1263-1286`. What
      09 says about it is still true there: nineteen fields, and no header, no
      `ts_egress` and no `query_sha256` among them.

## Why

Capability B in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md`, which ranks
it second of twelve on techniques unblocked and calls it "the cheapest large
win in the file": 18 of the 131 techniques the eight research files propose are
waiting on it, and the cache cluster is the bulk of them. File `02` proposes
fifteen cache techniques, and without `Age`, `X-Cache`, `Vary` and
`Cache-Control` there is no cache technique at all -- not a weak one, none.

The matrix's own summary of the state is the reason this is a small ticket and
not a lane: **present on the wire, discarded on the way out**. Every other
capability in that file asks the door to do something it does not do. This one
asks the handler to stop dropping something the door already produced.

## What was built

`Answer` carries the target's headers (`proxy.py:3577-3612`) as pairs in the
order they arrived rather than as a mapping, because a target that answered with
two `Vary` lines said two things and a mapping keeps one of them. `_answered`
fills the field (`proxy.py:3615-3651`) and `_spend` hands it to the child beside
the body, bounded, with a flag when it was cut (`_launch.py:707-793`).

## Which surface carries them, and what each surface answers

The tool result carries them and answers *reading*. The transcript Artifact the
Receipt already names answers *citing*, and it did before this ticket: the
transcript is the start line, the headers and the body, and `wire_received` is
built from it, so every header of every exchange was already stored exactly.
Nothing was added to the receipt projection, no column was projected and no
migration was written. A child that reads a header and files an Observation
cites the Receipt it was already going to cite, and the header it read is inside
the Artifact that Receipt names.

The ticket's sixth criterion asked what would have to happen *if* a header were
made citable in its own right. It is not, so the projection was not touched --
and the reference the research gave for it was stale in the way the ticket
already said.

## One filter, not two

The three runtime headers and every hop-by-hop name are left out by
`describes_this_hop`, which is the predicate that already keeps an internal name
off a wire. `RECEIPT`, `DECISION` and `DETAIL` all begin with the internal
prefix, so the same call that drops `Content-Length` drops them, and they are
read into their own named fields first.

The six `WIRE_RESPONSE_HEADERS` are absent by construction rather than by a
second filter: `response_for_agent` removed them and `project_identity_response`
removed a leased Identity's renderings, both before the door answered. A second
filter here would be a second place that rule lives, and a rule with two places
is one that can be changed in one of them.

## The one change beyond the ticket

`_answer` now calls `send_response_only` instead of `send_response`
(`proxy.py:3269`). The difference is that `send_response` stamps a `Server` and
a `Date` of the door's own. That was harmless while the caller read three named
headers off this hop and stops being harmless the moment the caller reads the
hop's header list as the target's answer: a target's own `Date` would arrive
beside this process's clock with nothing telling them apart, and `Date` and `Age`
arithmetic is exactly the cache reading this ticket exists for. The CONNECT path
already made the same call for its own reason.

## What it is asserted with

`tests/test_proxy.py:1201-1328` and `tests/test_agent.py:1337-1551`. A live door
answering with `Cache-Control`, `Age`, `X-Cache` and two `Vary` lines, read back
in order. A target emitting all six `WIRE_RESPONSE_HEADERS` with markers, none
of which is read back, with `response_wire_sha` still set so the citation path
is unchanged. The refusal path, which is the only case carrying all three
runtime headers, where the read list is empty. A header list over the ceiling,
cut on a whole pair. And one test spanning both tools: a header read off the
`http_request` result and filed through `submit_mission_result` as a
`header_policy_observed` Observation citing the Receipt that same result named.
