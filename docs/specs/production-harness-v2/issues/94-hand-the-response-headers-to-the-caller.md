# 94 — Hand the response headers to the caller

**What to build:** The target's response header names and values on the child's
side of `mcp__rk2__http_request`, and the decision about which surface carries
them. The bytes are already in this process and already hashed; what is missing
is the one statement that hands them over.

**Blocked by:** nothing. Nothing in this ticket widens what the door may send,
so it waits on no other capability.

**Status:** ready-for-agent

- [ ] A child that called `mcp__rk2__http_request` can read the response headers
      of the exchange it just made. Today it cannot, and the loss is one dict
      wide: the door passes them into `_answer` as `headers=agent_back`
      (`proxy.py:3123-3128`) and the handler returns exactly `served`, `status`,
      `receipt`, `decision`, `detail`, `byte_size`, `truncated` and `body`
      (`_launch.py:726-735`). The headers reach the boundary and stop there.
- [ ] The ticket says which surface carries them -- the tool result, the
      transcript Artifact the Receipt already names, or both -- and says which
      of *reading* and *citing* each surface answers. The transcript is not a
      third option that avoids the choice: `transcript` is the start line, the
      headers and the body concatenated (`proxy.py:789-798`), `wire_received` is
      built from it (`proxy.py:2831`) and the Receipt names it by hash, so every
      header of every exchange is already stored. What no child can do is name
      that Artifact and get a header out of it.
- [ ] The six names the agent view already drops are absent from whatever the
      child reads. `WIRE_RESPONSE_HEADERS` is `authentication-info`,
      `proxy-authenticate`, `proxy-authentication-info`, `set-cookie`,
      `set-cookie2` and `www-authenticate` (`proxy.py:348-357`), removed by
      `response_for_agent` (`proxy.py:645-656`); a leased Identity's own
      renderings are removed on top of that by `project_identity_response`
      (`proxy.py:659-698`). A reading that wants a cookie attribute states that
      it is reading the target's behaviour and the request side, not the
      `Set-Cookie` line.
- [ ] What the child reads is bounded. The body already is -- `_launch.py:726`
      truncates it at `packet.DEFAULT_EXCERPT`, 4096 bytes -- and a header list
      with no ceiling is a second unbounded path into the model's context out of
      a document the target wrote.
- [ ] `header_policy_observed` becomes fillable by a child from something the
      child can actually read. The kind is evidential with provenance
      `{receipt,tool_run}` (`0018_vocabularies.sql:235`) and has been since 018;
      no agent-reachable surface has ever carried a header, so an Observation of
      that kind is a claim with a provenance record that does not hold the fact.
- [ ] If the answer is that a header is *citable* and not merely readable, the
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
